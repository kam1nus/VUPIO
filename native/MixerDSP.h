#pragma once
#include <stdint.h>
typedef struct MimicMix MimicMix;
MimicMix *mimic_mix_create(void);
void mimic_mix_destroy(MimicMix *m);
uint64_t mimic_voice_begin(MimicMix *m,int slot);
uint64_t mimic_voice_generation(MimicMix *m,int slot);
int mimic_voice_active(MimicMix *m,int slot);
unsigned mimic_voice_free(MimicMix *m,int slot);
unsigned mimic_voice_push(MimicMix *m,int slot,uint64_t ticket,const float *left,const float *right,unsigned n);
void mimic_voice_end(MimicMix *m,int slot,uint64_t ticket);
void mimic_voice_stop(MimicMix *m,int slot);
void mimic_mix_stop(MimicMix *m,int panic);
void mimic_mix_gains(MimicMix *m,float clips,float microphone);
void mimic_mix_monitor(MimicMix *m,int enabled);
void mimic_mix_render(MimicMix *m,float *left,float *right,unsigned n);
void mimic_monitor_render(MimicMix *m,float *left,float *right,unsigned n);
float mimic_mix_meter(MimicMix *m,int which);
uint64_t mimic_mix_underruns(MimicMix *m);

uint64_t mimic_mix_input_frames(MimicMix *m);
void mimic_install_panic_signal(MimicMix *m);
void mimic_mix_emergency(MimicMix *m);
void mimic_mix_resume(MimicMix *m);
int mimic_mix_is_emergency(MimicMix *m);

uint64_t mimic_mix_consumed_mic_frames(MimicMix *m);
