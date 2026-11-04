// MIMIC timestamped stereo loopback. One HAL WriteMix producer; independent readers.
// No allocation, waits, filesystem access, or mutexes in the IO data path.
#pragma once
#include <stdatomic.h>
#include <stdint.h>
#include <string.h>
#include <math.h>
#define MIMIC_LOOP_FRAMES 65536u
#define MIMIC_LOOP_DELAY 1024
static _Atomic(uint64_t) mimic_samples[MIMIC_LOOP_FRAMES];
static _Atomic(uint64_t) mimic_tags[MIMIC_LOOP_FRAMES];
static void mimic_loop_reset(void) {
    for (unsigned i=0;i<MIMIC_LOOP_FRAMES;i++) atomic_store(&mimic_tags[i],0);
}
static void mimic_loop_write(int64_t time,const float *audio,unsigned frames,float gain) {
    for(unsigned i=0;i<frames;i++) {
        int64_t t=time+i;if(t<0)continue;unsigned slot=(uint64_t)t%MIMIC_LOOP_FRAMES;
        float pair[2];for(unsigned c=0;c<2;c++) {
            float x=audio[2*i+c]*gain;pair[c]=isfinite(x)?fmaxf(-.98f,fminf(.98f,x)):0;
        }
        uint64_t bits;memcpy(&bits,pair,8);
        atomic_store_explicit(&mimic_tags[slot],0,memory_order_release);
        // A reader must observe invalidation before a replacement sample.
        atomic_thread_fence(memory_order_release);
        atomic_store_explicit(&mimic_samples[slot],bits,memory_order_relaxed);
        atomic_store_explicit(&mimic_tags[slot],(uint64_t)t+1,memory_order_release);
    }
}
static void mimic_loop_read(int64_t time,float *audio,unsigned frames,float gain) {
    for(unsigned i=0;i<frames;i++) {
        int64_t t=time+i-MIMIC_LOOP_DELAY;float pair[2]={0,0};
        if(t>=0) {
            unsigned slot=(uint64_t)t%MIMIC_LOOP_FRAMES;uint64_t tag=(uint64_t)t+1;
            if(atomic_load_explicit(&mimic_tags[slot],memory_order_acquire)==tag) {
                uint64_t bits=atomic_load_explicit(&mimic_samples[slot],memory_order_relaxed);
                atomic_thread_fence(memory_order_acquire);
                if(atomic_load_explicit(&mimic_tags[slot],memory_order_acquire)==tag)memcpy(pair,&bits,8);
            }
        }
        audio[2*i]=pair[0]*gain;audio[2*i+1]=pair[1]*gain;
    }
}
