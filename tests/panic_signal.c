#include "../native/MixerDSP.h"
#include <signal.h>
#include <assert.h>
#include <stdio.h>
int main(){MimicMix*m=mimic_mix_create();float data[512],l[512],r[512];for(int i=0;i<512;i++)data[i]=.2f;uint64_t t=mimic_voice_begin(m,0);mimic_voice_push(m,0,t,data,data,512);mimic_install_panic_signal(m);raise(SIGUSR1);assert(mimic_mix_is_emergency(m));mimic_mix_render(m,l,r,512);for(int i=0;i<512;i++)assert(l[i]==0&&r[i]==0);mimic_mix_resume(m);mimic_mix_render(m,l,r,512);for(int i=0;i<512;i++)assert(l[i]==0);t=mimic_voice_begin(m,0);mimic_voice_push(m,0,t,data,data,512);mimic_mix_render(m,l,r,512);assert(l[100]>.1f);puts("PASS: SIGUSR1 immediately gates DSP, clears voices, explicit resume does not resurrect old buffers; new Play works.");}
