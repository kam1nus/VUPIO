#include "../driver/Loopback.h"
#include <pthread.h>
#include <assert.h>
#include <stdio.h>
static _Atomic uint64_t latest;
static _Atomic int done;
static void* writer(void*unused){for(int64_t t=1;t<=2000000;t++){float pair[2]={(t%997)/2000.f,-(t%997)/2000.f};mimic_loop_write(t,pair,1,1);atomic_store(&latest,t);}atomic_store(&done,1);return NULL;}
static void* reader(void*unused){unsigned n=0;do{uint64_t now=atomic_load(&latest);int64_t t=(int64_t)now-(n++%131072);if(t<0)continue;float pair[2];mimic_loop_read(t+MIMIC_LOOP_DELAY,pair,1,1);if(pair[0]!=0){float expected=(t%997)/2000.f;assert(fabsf(pair[0]-expected)<1e-6);assert(pair[1]==-pair[0]);}}while(!atomic_load(&done));return NULL;}
int main(){mimic_loop_reset();pthread_t w,r1,r2;pthread_create(&w,NULL,writer,NULL);pthread_create(&r1,NULL,reader,NULL);pthread_create(&r2,NULL,reader,NULL);pthread_join(w,NULL);pthread_join(r1,NULL);pthread_join(r2,NULL);puts("PASS: 2,000,000 timestamped stereo frames, concurrent writer and two independent readers, wrap and missing frames; no mismatched time/sample pairs.");}
