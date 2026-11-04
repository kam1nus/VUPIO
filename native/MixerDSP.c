#include "MixerDSP.h"
#include <stdatomic.h>
#include <stdlib.h>
#include <math.h>
#include <string.h>
#include <pthread.h>
#include <signal.h>
#define CAP 96000u
#define VOICES 8
// SPSC queues. Audio samples are atomic packed stereo words so a control-thread
// stop/reuse cannot race with the callback reading the previous generation.
typedef struct { _Atomic uint64_t r,w,ticket; _Atomic uint64_t active,eof; pthread_mutex_t producer; _Atomic uint64_t data[CAP]; } Queue;
struct MimicMix { Queue q[10]; _Atomic float clips,mic,meter[4]; _Atomic int monitor,emergency; _Atomic uint64_t underruns,input_frames,consumed_mic_frames; };
MimicMix *mimic_mix_create(void) {MimicMix*m=calloc(1,sizeof(*m));if(m){for(int s=0;s<10;s++)pthread_mutex_init(&m->q[s].producer,NULL);atomic_store(&m->clips,.65f);atomic_store(&m->mic,.7f);}return m;}
void mimic_mix_destroy(MimicMix*m){for(int s=0;s<10;s++)pthread_mutex_destroy(&m->q[s].producer);free(m);}
uint64_t mimic_voice_generation(MimicMix*m,int s){return atomic_load(&m->q[s].ticket);}
uint64_t mimic_voice_begin(MimicMix*m,int s){Queue*q=&m->q[s];pthread_mutex_lock(&q->producer);atomic_store(&q->active,0);uint64_t t=atomic_fetch_add(&q->ticket,1)+1;atomic_store(&q->r,atomic_load(&q->w));atomic_store(&q->eof,0);atomic_store(&q->active,t);pthread_mutex_unlock(&q->producer);return t;}
int mimic_voice_active(MimicMix*m,int s){return atomic_load(&m->q[s].active)!=0;}
unsigned mimic_voice_free(MimicMix*m,int s){Queue*q=&m->q[s];uint64_t w=atomic_load(&q->w),r=atomic_load(&q->r);return w>=r&&w-r<CAP ? CAP-(unsigned)(w-r):0;}
unsigned mimic_voice_push(MimicMix*m,int s,uint64_t ticket,const float*l,const float*r,unsigned n){Queue*q=&m->q[s];pthread_mutex_lock(&q->producer);if(ticket!=atomic_load(&q->ticket)||!atomic_load(&q->active)){pthread_mutex_unlock(&q->producer);return 0;}unsigned free=mimic_voice_free(m,s);if(n>free)n=free;uint64_t w=atomic_load(&q->w);for(unsigned i=0;i<n;i++){float pair[2]={isfinite(l[i])?l[i]:0,isfinite(r?r[i]:l[i])?(r?r[i]:l[i]):0};uint64_t b;memcpy(&b,pair,8);atomic_store_explicit(&q->data[(w+i)%CAP],b,memory_order_relaxed);}if(ticket!=atomic_load(&q->ticket)){pthread_mutex_unlock(&q->producer);return 0;}atomic_store_explicit(&q->w,w+n,memory_order_release);if(s==8)atomic_fetch_add(&m->input_frames,n);pthread_mutex_unlock(&q->producer);return n;}
void mimic_voice_end(MimicMix*m,int s,uint64_t ticket){if(ticket==atomic_load(&m->q[s].ticket))atomic_store(&m->q[s].eof,ticket);}
void mimic_voice_stop(MimicMix*m,int s){atomic_store(&m->q[s].active,0);atomic_fetch_add(&m->q[s].ticket,1);}
void mimic_mix_stop(MimicMix*m,int panic){if(panic)atomic_store(&m->monitor,0);atomic_store(&m->q[9].r,atomic_load(&m->q[9].w));for(int s=0;s<(panic?10:8);s++)mimic_voice_stop(m,s);for(int i=0;i<4;i++)atomic_store(&m->meter[i],0);}
void mimic_mix_gains(MimicMix*m,float c,float v){atomic_store(&m->clips,fmaxf(0,fminf(1,c)));atomic_store(&m->mic,fmaxf(0,fminf(1,v)));}
void mimic_mix_monitor(MimicMix*m,int enabled){atomic_store(&m->monitor,enabled);if(enabled)mimic_voice_begin(m,9);else mimic_voice_stop(m,9);}
static uint64_t available(Queue*q,unsigned n,uint64_t*r,uint64_t*t){*t=atomic_load(&q->ticket);*r=atomic_load(&q->r);uint64_t w=atomic_load_explicit(&q->w,memory_order_acquire);return w>=*r ? ((w-*r)<n?w-*r:n):0;}
static void read_pair(Queue*q,uint64_t pos,float *l,float *r){uint64_t b=atomic_load_explicit(&q->data[pos%CAP],memory_order_relaxed);float pair[2];memcpy(pair,&b,8);*l=pair[0];*r=pair[1];}
// Identity below knee; bounded smooth saturation above it, no interdependent
// player/capture state and no graph mutations when starting/stopping a clip.
static float limit(float x){float a=fabsf(x);return a<=.8f?x:copysignf(.8f+.18f*tanhf((a-.8f)/.18f),x);}
void mimic_mix_render(MimicMix*m,float*l,float*r,unsigned n){
 if(atomic_load(&m->emergency)){memset(l,0,n*sizeof(float));memset(r,0,n*sizeof(float));return;}
 uint64_t rp[9],ticket[9],count[9];int on[9];float cg=atomic_load(&m->clips),mg=atomic_load(&m->mic);float mp=0,cp=0,op=0,lim=0;
 for(int s=0;s<9;s++){Queue*q=&m->q[s];on[s]=atomic_load(&q->active);if(s==8&&on[s]){uint64_t w=atomic_load(&q->w),r=atomic_load(&q->r);if(w>r+4800)atomic_compare_exchange_strong(&q->r,&r,w-1024); }count[s]=on[s]?available(q,n,&rp[s],&ticket[s]):0;if(s==8&&on[s]&&count[s]<n)atomic_fetch_add(&m->underruns,1);}
 if(on[8])atomic_fetch_add(&m->consumed_mic_frames,count[8]);
 int monitor=atomic_load(&m->monitor);Queue*mq=&m->q[9];uint64_t mw=atomic_load(&mq->w);unsigned mf=monitor?mimic_voice_free(m,9):0;
 for(unsigned i=0;i<n;i++){float cl=0,cr=0,ml=0,mr=0;for(int s=0;s<9;s++)if(i<count[s]){float a,b;read_pair(&m->q[s],rp[s]+i,&a,&b);if(s==8){ml=a;mr=b;}else{cl+=a;cr+=b;}}mp=fmaxf(mp,fmaxf(fabsf(ml),fabsf(mr)));cl*=cg;cr*=cg;cp=fmaxf(cp,fmaxf(fabsf(cl),fabsf(cr)));float a=cl+ml*mg,b=cr+mr*mg;lim=fmaxf(lim,fmaxf(fabsf(a),fabsf(b))>.8f?1:0);l[i]=limit(a);r[i]=limit(b);op=fmaxf(op,fmaxf(fabsf(l[i]),fabsf(r[i])));
  if(i<mf){float p[2]={limit(cl),limit(cr)};uint64_t bits;memcpy(&bits,p,8);atomic_store(&mq->data[(mw+i)%CAP],bits);}
 }
 if(monitor)atomic_store_explicit(&mq->w,mw+(n<mf?n:mf),memory_order_release);
 for(int s=0;s<9;s++)if(on[s]&&ticket[s]==atomic_load(&m->q[s].ticket)){uint64_t expected=rp[s];atomic_compare_exchange_strong(&m->q[s].r,&expected,rp[s]+count[s]);if(s<8&&atomic_load(&m->q[s].eof)==ticket[s]&&atomic_load(&m->q[s].r)==atomic_load(&m->q[s].w)){uint64_t active=ticket[s];atomic_compare_exchange_strong(&m->q[s].active,&active,0);}}
 atomic_store(&m->meter[0],mp);atomic_store(&m->meter[1],cp);atomic_store(&m->meter[2],op);atomic_store(&m->meter[3],lim);
}
void mimic_monitor_render(MimicMix*m,float*l,float*r,unsigned n){if(atomic_load(&m->emergency)){memset(l,0,n*sizeof(float));memset(r,0,n*sizeof(float));return;}Queue*q=&m->q[9];uint64_t pos,t,count=available(q,n,&pos,&t);uint64_t w=atomic_load(&q->w);if(w>pos+4800){pos=w-2400;atomic_store(&q->r,pos);count=available(q,n,&pos,&t);}for(unsigned i=0;i<n;i++){l[i]=r[i]=0;if(atomic_load(&m->monitor)&&i<count)read_pair(q,pos+i,&l[i],&r[i]);}uint64_t expected=pos;atomic_compare_exchange_strong(&q->r,&expected,pos+count);}
float mimic_mix_meter(MimicMix*m,int n){return atomic_load(&m->meter[n]);}
uint64_t mimic_mix_underruns(MimicMix*m){return atomic_load(&m->underruns);}

uint64_t mimic_mix_input_frames(MimicMix*m){return atomic_load(&m->input_frames);}

// Out-of-band mute remains available even if the Core Audio control thread is
// negotiating a disconnected device. Only lock-free atomics in the handler.
_Static_assert(ATOMIC_LLONG_LOCK_FREE==2 && ATOMIC_INT_LOCK_FREE==2,"PANIC requires lock-free atomics");
static MimicMix *signal_mix;
void mimic_mix_emergency(MimicMix*m){atomic_store(&m->emergency,1);mimic_mix_stop(m,1);}
void mimic_mix_resume(MimicMix*m){atomic_store(&m->emergency,0);}
int mimic_mix_is_emergency(MimicMix*m){return atomic_load(&m->emergency);}
static void panic_signal(int unused){if(signal_mix)mimic_mix_emergency(signal_mix);}
void mimic_install_panic_signal(MimicMix*m){signal_mix=m;struct sigaction action;memset(&action,0,sizeof(action));action.sa_handler=panic_signal;sigemptyset(&action.sa_mask);sigaction(SIGUSR1,&action,NULL);}

uint64_t mimic_mix_consumed_mic_frames(MimicMix*m){return atomic_load(&m->consumed_mic_frames);}
