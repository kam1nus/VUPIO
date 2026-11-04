import Foundation
import AVFoundation
// Synthetic telemetry regression tests. No device is opened.
enum AudioFailure:LocalizedError {case message(String)}
func check(_ format:AVAudioFormat,_ fill:(AVAudioPCMBuffer)->Void){
    let b=AVAudioPCMBuffer(pcmFormat:format,frameCapacity:128)!;b.frameLength=128;fill(b)
    let t=CaptureTelemetry();t.observe(b);t.converted(128,100)
    let s=t.snapshot();print(format,s);fflush(stdout);precondition(s["physicalFrames"] as? UInt64==128);precondition(s["pushedMicFrames"] as? UInt64==100);precondition(s["droppedMicFrames"] as? UInt64==28)
    precondition(abs((s["physicalMicLevel"] as? Float ?? 0)-0.25)<0.0001)
}
@main struct Test {
 static func main(){
  check(AVAudioFormat(standardFormatWithSampleRate:48000,channels:1)!){b in for n in 0..<128{b.floatChannelData![0][n]=0.25}}
  check(AVAudioFormat(commonFormat:.pcmFormatInt16,sampleRate:16000,channels:2,interleaved:true)!){b in for n in 0..<256{b.int16ChannelData![0][n]=8192}}
  check(AVAudioFormat(commonFormat:.pcmFormatInt32,sampleRate:48000,channels:1,interleaved:false)!){b in for n in 0..<128{b.int32ChannelData![0][n]=536870912}}
  check(AVAudioFormat(commonFormat:.pcmFormatFloat64,sampleRate:44100,channels:2,interleaved:false)!){b in let a=UnsafeMutableAudioBufferListPointer(b.mutableAudioBufferList);for ch in 0..<2{for n in 0..<128{a[ch].mData!.assumingMemoryBound(to:Double.self)[n]=ch==0 ? 0:0.25}}}
  let t=CaptureTelemetry();precondition(t.snapshot()["physicalMicLevel"] as? Float==0)
  print("PASS: raw physical telemetry without a running mixer; float32/int16/int32/float64 stereo; counts, drops and separate channels")
 }
}
