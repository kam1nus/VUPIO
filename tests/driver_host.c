// Loads the actual .driver binary in this process, never installs into HAL.
#include <CoreAudio/AudioServerPlugIn.h>
#include <CoreFoundation/CFPlugInCOM.h>
#include <dlfcn.h>
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
static OSStatus copy(AudioServerPlugInHostRef h,CFStringRef k,CFPropertyListRef *v){*v=NULL;return 0;}
static OSStatus changed(AudioServerPlugInHostRef h,AudioObjectID o,UInt32 n,const AudioObjectPropertyAddress*a){return 0;}
int main(int argc,char**argv){
 alarm(15);assert(argc==2);fprintf(stderr,"load\n");void*image=dlopen(argv[1],RTLD_NOW);if(!image){fprintf(stderr,"%s\n",dlerror());return 1;}
 fprintf(stderr,"loaded\n");void*(*create)(CFAllocatorRef,CFUUIDRef)=dlsym(image,"MIMICAudio_Create");assert(create);
 AudioServerPlugInDriverRef d=create(NULL,kAudioServerPlugInTypeUUID);assert(d);
 struct AudioServerPlugInHostInterface host={.PropertiesChanged=changed,.CopyFromStorage=copy};
 fprintf(stderr,"init\n");assert((*d)->Initialize(d,&host)==0);
 fprintf(stderr,"initialized\n");AudioObjectPropertyAddress address={kAudioObjectPropertyName,kAudioObjectPropertyScopeGlobal,0};CFStringRef name=NULL;UInt32 size=sizeof(name);
 assert((*d)->GetPropertyData(d,3,0,&address,0,NULL,size,&size,&name)==0);assert(CFEqual(name,CFSTR("MIMIC Microphone")));CFRelease(name);
 fprintf(stderr,"start\n");assert((*d)->StartIO(d,3,1)==0);assert((*d)->StartIO(d,3,2)==0);
 fprintf(stderr,"started\n");float in[1024],out[1024],second[1024];for(int i=0;i<1024;i++)in[i]=.2f*sinf(i*.1f);
 AudioServerPlugInIOCycleInfo cycle={0};cycle.mOutputTime.mSampleTime=5000;cycle.mInputTime.mSampleTime=6024;
 assert((*d)->DoIOOperation(d,3,8,1,kAudioServerPlugInIOOperationWriteMix,512,&cycle,in,NULL)==0);
 assert((*d)->DoIOOperation(d,3,4,2,kAudioServerPlugInIOOperationReadInput,512,&cycle,out,NULL)==0);
 assert((*d)->DoIOOperation(d,3,4,3,kAudioServerPlugInIOOperationReadInput,512,&cycle,second,NULL)==0);
 for(int i=0;i<1024;i++){assert(fabs(in[i]-out[i])<1e-6);assert(second[i]==out[i]);}
 AudioObjectPropertyAddress volume={kAudioLevelControlPropertyScalarValue,kAudioObjectPropertyScopeGlobal,0};float gain=.5f;
 assert((*d)->SetPropertyData(d,5,0,&volume,0,NULL,4,&gain)==0);
 assert((*d)->DoIOOperation(d,3,4,2,kAudioServerPlugInIOOperationReadInput,512,&cycle,out,NULL)==0);
 for(int i=0;i<1024;i++)assert(fabsf(out[i]-.5f*in[i])<1e-6);
 volume.mSelector=kAudioLevelControlPropertyDecibelValue;float db=0;size=4;
 assert((*d)->GetPropertyData(d,5,0,&volume,0,NULL,4,&size,&db)==0);assert(fabsf(db+6.0206f)<.001f);
 volume.mSelector=kAudioLevelControlPropertyScalarValue;gain=NAN;assert((*d)->SetPropertyData(d,5,0,&volume,0,NULL,4,&gain)!=0);
 AudioObjectPropertyAddress mute={kAudioBooleanControlPropertyValue,kAudioObjectPropertyScopeGlobal,0};UInt32 muted=1;
 assert((*d)->SetPropertyData(d,6,0,&mute,0,NULL,4,&muted)==0);
 assert((*d)->DoIOOperation(d,3,4,2,kAudioServerPlugInIOOperationReadInput,512,&cycle,out,NULL)==0);
 for(int i=0;i<1024;i++)assert(out[i]==0);
 muted=0;assert((*d)->SetPropertyData(d,6,0,&mute,0,NULL,4,&muted)==0);
 cycle.mInputTime.mSampleTime+=65536;
 assert((*d)->DoIOOperation(d,3,4,2,kAudioServerPlugInIOOperationReadInput,512,&cycle,out,NULL)==0);
 for(int i=0;i<1024;i++)assert(out[i]==0); // no stale replay after wrap/no writer
 double sample;UInt64 time,seed;assert((*d)->GetZeroTimeStamp(d,3,1,&sample,&time,&seed)==0);usleep(60000);double later;assert((*d)->GetZeroTimeStamp(d,3,1,&later,&time,&seed)==0);assert(later>sample);
 assert((*d)->StopIO(d,3,1)==0);assert((*d)->StopIO(d,3,2)==0);
 puts("PASS: real plug-in factory/host Initialize, MIMIC name, two IO clients, stereo WriteMix→ReadInput, independent readers, no stale replay, advancing clock, real gain/mute, decibel conversion, nonfinite control rejection. Not system registration.");return 0;
}
