import AVFoundation
import CoreAudio

// Numeric telemetry only. Never stores audio, speech text or waveform files.
final class CaptureTelemetry {
    let lock=NSLock()
    var callbacks:UInt64=0,rawFrames:UInt64=0,convertedFrames:UInt64=0,pushedFrames:UInt64=0,droppedFrames:UInt64=0
    var peak:Float=0,rms:Float=0,maxPeak:Float=0
    var last=Date.distantPast
    var error="",layout=""
    func failure(_ message:String){lock.lock();error=message;lock.unlock()}
    func observe(_ b:AVAudioPCMBuffer){
        var p:Float=0,sum:Double=0;let frames=Int(b.frameLength),channels=Int(b.format.channelCount)
        // Core Audio PCM formats accepted by AVAudioFormat; metering before gains/conversion.
        let stride=b.format.isInterleaved ? channels:1
        for ch in 0..<channels {
            for n in 0..<frames {
                let index=n*stride+(b.format.isInterleaved ? ch:0)
                let value:Float
                switch b.format.commonFormat {
                case .pcmFormatFloat32:value=b.floatChannelData![b.format.isInterleaved ? 0:ch][index]
                case .pcmFormatFloat64:value=Float(UnsafeMutableAudioBufferListPointer(b.mutableAudioBufferList)[b.format.isInterleaved ? 0:ch].mData!.assumingMemoryBound(to:Double.self)[index])
                case .pcmFormatInt16:value=Float(b.int16ChannelData![b.format.isInterleaved ? 0:ch][index])/32768
                case .pcmFormatInt32:value=Float(b.int32ChannelData![b.format.isInterleaved ? 0:ch][index])/2147483648
                default:value=0
                }
                if value.isFinite {p=max(p,abs(value));sum+=Double(value)*Double(value)}
            }
        }
        lock.lock();callbacks+=1;rawFrames+=UInt64(frames);peak=p;rms=Float(sqrt(sum/Double(max(1,frames*channels))));maxPeak=max(maxPeak,p);last=Date();lock.unlock()
    }
    func converted(_ frames:UInt32,_ pushed:UInt32,_ message:String=""){
        lock.lock();convertedFrames+=UInt64(frames);pushedFrames+=UInt64(pushed);droppedFrames+=UInt64(frames-pushed);if !message.isEmpty{error=message};lock.unlock()
    }
    func snapshot()->[String:Any]{
        lock.lock();defer{lock.unlock()}
        return ["captureCallbacks":callbacks,"physicalFrames":rawFrames,"physicalMicLevel":Date().timeIntervalSince(last)<0.5 ? peak:Float(0),"physicalMicRMS":Date().timeIntervalSince(last)<0.5 ? rms:Float(0),"physicalMicMaxPeak":maxPeak,"convertedFrames":convertedFrames,"pushedMicFrames":pushedFrames,"droppedMicFrames":droppedFrames,"captureError":error,"captureBufferLayout":layout]
    }
}

func audioStatus(_ status:OSStatus)->String {
    let bits=UInt32(bitPattern:status)
    let bytes=[UInt8((bits>>24)&255),UInt8((bits>>16)&255),UInt8((bits>>8)&255),UInt8(bits&255)]
    let code=bytes.allSatisfy{$0>=32 && $0<127} ? " '"+String(bytes:bytes,encoding:.ascii)!+"'":""
    return "\(status)"+code
}

// Explicit input-only IOProc on the selected physical device, independent of output AUHAL.
final class CoreInput {
    let device:AudioDeviceID,stream:AudioStreamID
    let format:AVAudioFormat
    let telemetry=CaptureTelemetry()
    var proc:AudioDeviceIOProcID?
    var running=false
    let queue=DispatchQueue(label:"mimic.coreinput",qos:.userInteractive)
    init(device:AudioDeviceID)throws {
        self.device=device
        var a=AudioObjectPropertyAddress(mSelector:kAudioDevicePropertyStreams,mScope:kAudioDevicePropertyScopeInput,mElement:0)
        var size:UInt32=0
        let status=AudioObjectGetPropertyDataSize(device,&a,0,nil,&size)
        guard status==noErr,size>=4 else{throw AudioFailure.message("CoreInput streams: \(audioStatus(status)); нет входного потока")}
        var streams=[AudioStreamID](repeating:0,count:Int(size)/4)
        let result=streams.withUnsafeMutableBytes{AudioObjectGetPropertyData(device,&a,0,nil,&size,$0.baseAddress!)}
        guard result==noErr else{throw AudioFailure.message("CoreInput stream list: \(audioStatus(result))")}
        a.mSelector=kAudioStreamPropertyVirtualFormat;a.mScope=kAudioObjectPropertyScopeGlobal
        var asbd=AudioStreamBasicDescription();size=UInt32(MemoryLayout<AudioStreamBasicDescription>.size)
        let code=AudioObjectGetPropertyData(streams[0],&a,0,nil,&size,&asbd)
        guard code==noErr,asbd.mSampleRate>0,asbd.mChannelsPerFrame>0,let f=AVAudioFormat(streamDescription:&asbd),f.commonFormat != .otherFormat else{throw AudioFailure.message("CoreInput ASBD: \(audioStatus(code)); rate=\(asbd.mSampleRate), channels=\(asbd.mChannelsPerFrame), flags=\(asbd.mFormatFlags)")}
        stream=streams[0];format=f
    }
    var formatDescription:String {let a=format.streamDescription.pointee;return "\(a.mSampleRate) Hz, \(a.mChannelsPerFrame) ch, \(a.mBitsPerChannel) bit, interleaved=\(format.isInterleaved), flags=\(a.mFormatFlags)"}
    func start(_ receive:@escaping(AVAudioPCMBuffer)->Void)throws {
        let f=format,stats=telemetry
        let code=AudioDeviceCreateIOProcIDWithBlock(&proc,device,queue){_,input,_,output,_ in
            for buffer in UnsafeMutableAudioBufferListPointer(output){if let p=buffer.mData{memset(p,0,Int(buffer.mDataByteSize))}}
            let buffers=UnsafeMutableAudioBufferListPointer(UnsafeMutablePointer(mutating:input))
            let expected=f.isInterleaved ? 1:Int(f.channelCount)
            guard buffers.count>=expected else{stats.failure("IOProc: expected \(expected) buffers, received \(buffers.count)");return}
            let bytesPerFrame=f.streamDescription.pointee.mBytesPerFrame
            guard bytesPerFrame>0 else{stats.failure("IOProc: bytesPerFrame=0");return}
            let frames=buffers[0].mDataByteSize/bytesPerFrame
            guard frames>0 else{stats.failure("IOProc: empty input buffer");return}
            // Copy only selected stream's buffers. Additional device streams are not silently rejected.
            guard let b=AVAudioPCMBuffer(pcmFormat:f,frameCapacity:frames)else{stats.failure("IOProc: PCM allocation failed");return}
            let destination=UnsafeMutableAudioBufferListPointer(b.mutableAudioBufferList)
            for i in 0..<expected {
                let source=buffers[i]
                guard source.mNumberChannels==(f.isInterleaved ? f.channelCount:1),let data=source.mData,source.mDataByteSize>=frames*bytesPerFrame,let target=destination[i].mData else{stats.failure("IOProc: incompatible buffer layout (channels/bytes/data)");return}
                memcpy(target,data,Int(frames*bytesPerFrame))
            }
            b.frameLength=frames
            stats.observe(b);receive(b)
        }
        guard code==noErr,let p=proc else{throw AudioFailure.message("AudioDeviceCreateIOProcIDWithBlock: \(audioStatus(code))")}
        let status=AudioDeviceStart(device,p)
        guard status==noErr else{AudioDeviceDestroyIOProcID(device,p);proc=nil;throw AudioFailure.message("AudioDeviceStart(input): \(audioStatus(status))")}
        running=true
    }
    func formatStillMatches()->Bool {
        var a=AudioObjectPropertyAddress(mSelector:kAudioStreamPropertyVirtualFormat,mScope:kAudioObjectPropertyScopeGlobal,mElement:0)
        var actual=AudioStreamBasicDescription();var size=UInt32(MemoryLayout<AudioStreamBasicDescription>.size)
        guard AudioObjectGetPropertyData(stream,&a,0,nil,&size,&actual)==noErr else{return false}
        let old=format.streamDescription.pointee
        return actual.mSampleRate==old.mSampleRate && actual.mChannelsPerFrame==old.mChannelsPerFrame && actual.mFormatID==old.mFormatID && actual.mFormatFlags==old.mFormatFlags && actual.mBitsPerChannel==old.mBitsPerChannel && actual.mBytesPerFrame==old.mBytesPerFrame
    }
    func stop(){if let p=proc{AudioDeviceStop(device,p);AudioDeviceDestroyIOProcID(device,p);proc=nil};running=false}
    deinit{stop()}
}
