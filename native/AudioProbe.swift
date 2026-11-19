import AVFoundation
import CoreAudio

// Only recognized virtual inputs; stores energy/count, never a waveform file.
final class VirtualProbe {
    var input:CoreInput?
    let lock=NSLock();var squares=0.0;var count=0
    var deviceName="";var deviceUID=""
    var level:Float=0;var maximum:Float=0;var last=Date.distantPast
    func start(device selected:AudioDeviceID)throws {
        stop();lock.lock();squares=0;count=0;level=0;maximum=0;last=Date.distantPast;lock.unlock()
        let list=devices(kAudioDevicePropertyScopeInput)
        guard let device=list.first(where:{$0["id"] as? UInt32 == selected}),
              device["uid"] as? String == "MIMICAudioDevice_UID" || (device["name"] as? String ?? "").lowercased().contains("blackhole"),
              let id=device["id"] as? UInt32 else{throw AudioFailure.message("Select MIMIC Microphone or BlackHole as the output before testing its virtual input.")}
        deviceName=device["name"] as? String ?? "Virtual input";deviceUID=device["uid"] as? String ?? ""
        let capture=try CoreInput(device:id)
        guard capture.format.commonFormat == .pcmFormatFloat32 else{throw AudioFailure.message("Diagnostics expects a Float32 virtual input")}
        try capture.start{[weak self] b in
            guard let self=self,let p=b.floatChannelData,self.lock.try()else{return};defer{self.lock.unlock()}
            let channels=Int(b.format.channelCount),stride=b.format.isInterleaved ? Int(b.format.channelCount):1
            var peak:Float=0
            for n in 0..<Int(b.frameLength){
                for ch in 0..<channels{
                    let x=p[b.format.isInterleaved ? 0:ch][n*stride+(b.format.isInterleaved ? ch:0)]
                    if x.isFinite{self.squares+=Double(x)*Double(x)/Double(channels);peak=max(peak,abs(x))}
                }
            }
            self.count+=Int(b.frameLength);self.level=peak;self.maximum=max(self.maximum,peak);self.last=Date()
        }
        input=capture
    }
    func stop(){input?.stop();input=nil}
    func snapshot()->[String:Any]{lock.lock();defer{lock.unlock()};return ["probeRunning":input?.running ?? false,"probeRMS":count>0 ? sqrt(squares/Double(count)):0,"probeFrames":count,"probeDevice":deviceName,"probeUID":deviceUID,"virtualMicLevel":input?.running == true && Date().timeIntervalSince(last)<0.5 ? level:0,"virtualMicMaxPeak":maximum,"virtualMeterAvailable":input?.running == true]}
    deinit{stop()}
}
