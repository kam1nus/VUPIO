import AVFoundation
import CoreAudio

// Only recognized virtual inputs; stores energy/count, never a waveform file.
final class VirtualProbe {
    var input:CoreInput?
    let lock=NSLock();var squares=0.0;var count=0
    var deviceName="";var deviceUID=""
    var level:Float=0;var maximum:Float=0;var last=Date.distantPast
    func start()throws {
        stop();lock.lock();squares=0;count=0;level=0;maximum=0;last=Date.distantPast;lock.unlock()
        let list=devices(kAudioDevicePropertyScopeInput)
        guard let device=list.first(where:{$0["uid"] as? String == "MIMICAudioDevice_UID"}) ?? list.first(where:{$0["name"] as? String == "BlackHole 2ch"}),let id=device["id"] as? UInt32 else{throw AudioFailure.message("Нет зарегистрированного виртуального входа. Установите драйвер или выберите запасной BlackHole.")}
        deviceName=device["name"] as? String ?? "Virtual input";deviceUID=device["uid"] as? String ?? ""
        let capture=try CoreInput(device:id)
        guard capture.format.commonFormat == .pcmFormatFloat32 else{throw AudioFailure.message("Диагностика ожидает Float32 виртуального входа")}
        try capture.start{[weak self] b in
            guard let self=self,let p=b.floatChannelData,self.lock.try()else{return};defer{self.lock.unlock()}
            let stride=b.format.isInterleaved ? Int(b.format.channelCount):1
            var peak:Float=0
            for n in 0..<Int(b.frameLength){let x=p[0][n*stride];self.squares+=Double(x)*Double(x);peak=max(peak,abs(x))};self.count+=Int(b.frameLength);self.level=peak;self.maximum=max(self.maximum,peak);self.last=Date()
        }
        input=capture
    }
    func stop(){input?.stop();input=nil}
    func snapshot()->[String:Any]{lock.lock();defer{lock.unlock()};return ["probeRunning":input?.running ?? false,"probeRMS":count>0 ? sqrt(squares/Double(count)):0,"probeFrames":count,"probeDevice":deviceName,"probeUID":deviceUID,"virtualMicLevel":input?.running == true && deviceUID=="MIMICAudioDevice_UID" && Date().timeIntervalSince(last)<0.5 ? level:0,"virtualMicMaxPeak":maximum,"virtualMeterAvailable":input?.running == true && deviceUID=="MIMICAudioDevice_UID"]}
    deinit{stop()}
}
