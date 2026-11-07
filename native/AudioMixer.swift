import Cocoa
import AVFoundation
import CoreAudio
import AudioToolbox

func physicalInputs()->[[String:Any]] {devices(kAudioDevicePropertyScopeInput).filter { d in
    let n=(d["name"] as? String ?? "").lowercased(),uid=d["uid"] as? String ?? ""
    let transport=d["transport"] as? UInt32 ?? 0
    return transport != kAudioDeviceTransportTypeVirtual && transport != kAudioDeviceTransportTypeAggregate && uid != "MIMICAudioDevice_UID" && !["blackhole","aggregate","multi-output","mimic microphone"].contains(where:n.contains)
}}
func suggestedInput()->AudioDeviceID? {
    let list=physicalInputs(),current=defaultDevice(kAudioHardwarePropertyDefaultInputDevice)
    return list.first(where:{($0["uid"] as? String)=="BuiltInMicrophoneDevice"})?["id"] as? UInt32 ?? list.first(where:{$0["id"] as? UInt32 == current})?["id"] as? UInt32 ?? list.first?["id"] as? UInt32
}
let mixFormat=AVAudioFormat(standardFormatWithSampleRate:48000,channels:2)!

// File decoding/resampling is off the audio callback. Each of eight voices owns
// its serial producer queue; the mixer consumes fixed-size atomic stereo FIFOs.
final class ClipFeed {
    let queue:DispatchQueue
    let dsp:OpaquePointer;let slot:Int32;let ticket:UInt64
    let file:AVAudioFile;let converter:AVAudioConverter
    var timer:DispatchSourceTimer?
    init(dsp:OpaquePointer,slot:Int32,ticket:UInt64,path:String)throws {
        self.dsp=dsp;self.slot=slot;self.ticket=ticket
        queue=DispatchQueue(label:"mimic.decode.\(slot)",qos:.userInitiated)
        file=try AVAudioFile(forReading:URL(fileURLWithPath:path))
        guard file.processingFormat.sampleRate>0,let convert=AVAudioConverter(from:file.processingFormat,to:mixFormat) else{throw AudioFailure.message("Unsupported file format")}
        converter=convert
    }
    func start(){let t=DispatchSource.makeTimerSource(queue:queue);timer=t;t.schedule(deadline:.now(),repeating:.milliseconds(15));t.setEventHandler{[weak self] in self?.pump()};t.resume()}
    func cancel(){timer?.cancel();timer=nil}
    func pump(){
        if mimic_voice_generation(dsp,slot) != ticket {cancel();return}
        for _ in 0..<4 {
            guard mimic_voice_free(dsp,slot)>=8192,let out=AVAudioPCMBuffer(pcmFormat:mixFormat,frameCapacity:8192) else{return}
            var error:NSError?
            let result=converter.convert(to:out,error:&error){[self] count,status in
                if file.framePosition>=file.length{status.pointee = .endOfStream;return nil}
                let n=min(AVAudioFrameCount(file.length-file.framePosition),min(count,16384))
                guard let b=AVAudioPCMBuffer(pcmFormat:file.processingFormat,frameCapacity:n) else{status.pointee = .endOfStream;return nil}
                do{try file.read(into:b,frameCount:n);status.pointee = .haveData;return b}catch{status.pointee = .endOfStream;return nil}
            }
            if out.frameLength>0,let p=out.floatChannelData {_ = mimic_voice_push(dsp,slot,ticket,p[0],p[1],out.frameLength)}
            if result == .endOfStream || result == .error {mimic_voice_end(dsp,slot,ticket);cancel();return}
            if out.frameLength==0{return}
        }
    }
    deinit{cancel()}
}

final class SoundEngine {
    let dsp:OpaquePointer=mimic_mix_create()!
    var engine=AVAudioEngine();var monitorEngine:AVAudioEngine?
    var source:AVAudioSourceNode?
    var capture:CoreInput?
    var output:AudioDeviceID
    var selectedOutputUID=""
    var preferredInput:AudioDeviceID?=suggestedInput()
    var selectedInputUID:String=""
    var inputBaseline:UInt64=0;var lastInputFrames:UInt64=0;var lastInputTime=Date()
    var mic=false;var gain:Float=0.7;var volume:Float=0.65
    var ready=false;var parallel=false;var monitor=true
    var monitorDevice:AudioDeviceID=defaultDevice(kAudioHardwarePropertyDefaultOutputDevice)
    var selectedMonitorUID="";var monitorNotice="";var monitorRetryAfter=Date.distantPast
    var feeds:[Int32:ClipFeed]=[:];var names:[Int32:String]=[:];var order:[Int32:UInt64]=[:];var counter:UInt64=0
    let probe=VirtualProbe()
    var notice="";var watch:Timer?
    var micRequested=false;var permissionEpoch=0;var permissionPending=false;var sleeping=false
    var retainedTelemetry:CaptureTelemetry?;var retainedFormat=""
    var audioLog:[String]=[];var retryAfter=Date.distantPast
    var diagnosticActive=false;var diagnosticReady=false;var diagnosticUntil=Date.distantPast
    var diagnosticRestore=false;var diagnosticHadClips=false;var diagnosticConsumed:UInt64=0
    var diagnosticReport:[String:Any]=[:]
    var observers:[NSObjectProtocol]=[]
    init(){
        mimic_install_panic_signal(dsp)
        output=devices().first(where:{$0["uid"] as? String == "MIMICAudioDevice_UID"})?["id"] as? UInt32 ?? defaultDevice(kAudioHardwarePropertyDefaultOutputDevice)
        selectedOutputUID=deviceString(output,kAudioDevicePropertyDeviceUID)
        if let input=preferredInput{selectedInputUID=deviceString(input,kAudioDevicePropertyDeviceUID)}
        watch=Timer.scheduledTimer(withTimeInterval:1,repeats:true){[weak self] _ in self?.checkDevices()}
        observers.append(NSWorkspace.shared.notificationCenter.addObserver(forName:NSWorkspace.willSleepNotification,object:nil,queue:.main){[weak self] _ in self?.suspendForSleep()})
        observers.append(NSWorkspace.shared.notificationCenter.addObserver(forName:NSWorkspace.didWakeNotification,object:nil,queue:.main){[weak self] _ in self?.sleeping=false;self?.checkDevices()})
    }
    func setDevice(_ e:AVAudioEngine,_ id:AudioDeviceID)throws {
        var d=id;guard let unit=e.outputNode.audioUnit else{throw AudioFailure.message("No audio output")}
        // These engines only render audio. Capture uses a separate, authorized CoreInput.
        var inputEnabled:UInt32=0,inputSize=UInt32(MemoryLayout<UInt32>.size)
        let inputState=AudioUnitGetProperty(unit,kAudioOutputUnitProperty_EnableIO,kAudioUnitScope_Input,1,&inputEnabled,&inputSize)
        guard inputState==noErr else{throw AudioFailure.message("Core Audio: could not check the output input scope (\(inputState))")}
        if inputEnabled != 0 {
            inputEnabled=0
            let code=AudioUnitSetProperty(unit,kAudioOutputUnitProperty_EnableIO,kAudioUnitScope_Input,1,&inputEnabled,inputSize)
            guard code==noErr else{throw AudioFailure.message("Core Audio: could not disable the output input scope (\(code))")}
        }
        let code=AudioUnitSetProperty(unit,kAudioOutputUnitProperty_CurrentDevice,kAudioUnitScope_Global,0,&d,UInt32(MemoryLayout<AudioDeviceID>.size))
        guard code==noErr else{throw AudioFailure.message("Core Audio: could not select the output (\(code))")}
    }
    func configure()throws {
        engine.stop();monitorEngine?.stop();ready=false
        guard devices().contains(where:{$0["id"] as? UInt32 == output})else{throw AudioFailure.message("Output disconnected. Select MIMIC Microphone or a fallback output.")}
        engine=AVAudioEngine();try setDevice(engine,output)
        let p=dsp
        let s=AVAudioSourceNode(format:mixFormat){_,_,n,list in
            let b=UnsafeMutableAudioBufferListPointer(list)
            guard b.count>=2,let l=b[0].mData?.assumingMemoryBound(to:Float.self),let r=b[1].mData?.assumingMemoryBound(to:Float.self)else{return noErr}
            mimic_mix_render(p,l,r,n);return noErr
        }
        source=s;engine.attach(s);engine.connect(s,to:engine.mainMixerNode,format:mixFormat)
        mimic_mix_gains(dsp,volume,gain);engine.prepare();try engine.start();ready=true
        if monitor{do{try startMonitor()}catch{monitorNotice=error.localizedDescription;monitorRetryAfter=Date(timeIntervalSinceNow:3);log("Local listening: \(monitorNotice)")}}
    }
    func monitorTarget()->AudioDeviceID? {
        let physical=devices().filter{d in
            let name=(d["name"] as? String ?? "").lowercased(),transport=d["transport"] as? UInt32 ?? 0
            return transport != kAudioDeviceTransportTypeVirtual && transport != kAudioDeviceTransportTypeAggregate && !["blackhole","mimic microphone","aggregate","multi-output"].contains(where:name.contains)
        }
        if !selectedMonitorUID.isEmpty{return physical.first(where:{$0["uid"] as? String==selectedMonitorUID})?["id"] as? UInt32}
        let current=defaultDevice(kAudioHardwarePropertyDefaultOutputDevice)
        return physical.first(where:{$0["id"] as? UInt32==current})?["id"] as? UInt32 ?? physical.first?["id"] as? UInt32
    }
    func startMonitor()throws {
        monitorEngine?.stop();monitorEngine=nil;mimic_mix_monitor(dsp,0)
        monitorNotice=""
        guard monitor else{return}
        guard let target=monitorTarget()else{throw AudioFailure.message("Local listening is waiting for your selected headphones or speakers. Reconnect them or choose System output.")}
        monitorDevice=target
        // A physical main output already plays the clips. Never duplicate it.
        guard monitorDevice != output else{return}
        let e=AVAudioEngine();try setDevice(e,monitorDevice);let p=dsp
        let s=AVAudioSourceNode(format:mixFormat){_,_,n,list in let b=UnsafeMutableAudioBufferListPointer(list);if b.count>=2,let l=b[0].mData?.assumingMemoryBound(to:Float.self),let r=b[1].mData?.assumingMemoryBound(to:Float.self){mimic_monitor_render(p,l,r,n)};return noErr}
        e.attach(s);e.connect(s,to:e.mainMixerNode,format:mixFormat);try e.start();monitorEngine=e;mimic_mix_monitor(dsp,1)
    }
    func stopCapture(){
        mic=false;mimic_voice_stop(dsp,8);capture?.stop();if let c=capture{retainedTelemetry=c.telemetry;retainedFormat=c.formatDescription};capture=nil
    }
    func startCapture()throws {
        stopCapture()
        guard let input=preferredInput ?? suggestedInput(),physicalInputs().contains(where:{$0["id"] as? UInt32 == input})else{throw AudioFailure.message("Select an available physical microphone")}
        let recorder=try CoreInput(device:input);let f=recorder.format
        guard let converter=AVAudioConverter(from:f,to:mixFormat)else{throw AudioFailure.message("Cannot convert microphone format")}
        let p=dsp,ticket=mimic_voice_begin(dsp,8),stats=recorder.telemetry
        do{try recorder.start{buffer in
            let cap=AVAudioFrameCount(ceil(Double(buffer.frameLength)*48000/f.sampleRate))+64
            guard let out=AVAudioPCMBuffer(pcmFormat:mixFormat,frameCapacity:cap)else{return}
            var used=false,error:NSError?
            let result=converter.convert(to:out,error:&error){_,status in if used{status.pointee = .noDataNow;return nil};used=true;status.pointee = .haveData;return buffer}
            if result == .error || error != nil{stats.failure("AVAudioConverter: \(error?.localizedDescription ?? "conversion error")");return}
            if out.frameLength>0,let channels=out.floatChannelData{let written=mimic_voice_push(p,8,ticket,channels[0],channels[1],out.frameLength);stats.converted(out.frameLength,written)}
        }}catch{mimic_voice_stop(dsp,8);throw error}
        inputBaseline=mimic_mix_input_frames(dsp);lastInputFrames=inputBaseline;lastInputTime=Date();capture=recorder;mic=true;preferredInput=input;selectedInputUID=deviceString(input,kAudioDevicePropertyDeviceUID);retainedTelemetry=recorder.telemetry;retainedFormat=recorder.formatDescription;log("Capture started: \(deviceName(input)); \(retainedFormat)")
    }
    func stopClips(){mimic_mix_stop(dsp,0);for f in feeds.values{f.cancel()};feeds.removeAll();names.removeAll();order.removeAll()}
    func log(_ text:String){let message="\(ISO8601DateFormatter().string(from:Date())) \(text)";audioLog.append(message);if audioLog.count>60{audioLog.removeFirst(audioLog.count-60)};fputs("MIMIC Audio: \(text)\n",stderr)}
    func panic(){
        permissionEpoch+=1;permissionPending=false;micRequested=false;diagnosticActive=false;diagnosticReady=false
        mimic_mix_emergency(dsp);probe.stop();stopClips();stopCapture();mimic_mix_stop(dsp,1);monitorEngine?.stop();engine.stop();ready=false;log("PANIC: capture/playback stopped; pending permission/recovery cancelled")
    }
    func suspendForSleep(){
        sleeping=true;permissionEpoch+=1;permissionPending=false
        if diagnosticActive{finishDiagnostic()}
        probe.stop();stopClips();stopCapture();mimic_mix_stop(dsp,1);monitorEngine?.stop();engine.stop();ready=false
        notice=micRequested ? "Mac is sleeping. The previously selected microphone will reconnect after wake.":"Mac is sleeping. Microphone disabled."
        log("Sleep: physical capture suspended")
    }
    func activateRequestedMic()throws {
        guard micRequested,!sleeping else{return}
        let permission=AVCaptureDevice.authorizationStatus(for:.audio)
        if permission == .notDetermined {
            if !permissionPending {
                permissionPending=true;let epoch=permissionEpoch
                notice="Waiting for macOS microphone permission. Capture will start after access is granted."
                log("Microphone permission requested by MIMIC --audio-helper (pid \(ProcessInfo.processInfo.processIdentifier))")
                AVCaptureDevice.requestAccess(for:.audio){[weak self] allowed in DispatchQueue.main.async{
                    guard let self=self,self.permissionEpoch==epoch,self.micRequested,!self.sleeping,mimic_mix_is_emergency(self.dsp)==0 else{return}
                    self.permissionPending=false
                    if allowed {do{try self.activateRequestedMic()}catch{self.notice=error.localizedDescription;self.log("Capture failed: \(self.notice)");self.micRequested=false}}
                    else {self.micRequested=false;self.notice="Microphone access denied. Open macOS → Privacy & Security → Microphone → VUPIO.";self.log("Microphone permission denied");if self.diagnosticActive{self.finishDiagnostic()}}
                }}
            }
            return
        }
        guard permission == .authorized else{micRequested=false;throw AudioFailure.message("Microphone access denied or restricted. Allow VUPIO in macOS Settings.")}
        let uid=deviceString(output,kAudioDevicePropertyDeviceUID)
        let route=deviceName(output).lowercased()
        guard uid=="MIMICAudioDevice_UID" || route.contains("blackhole") || route.contains("multi-output") || route.contains("aggregate") else{throw AudioFailure.message("Select MIMIC Microphone as the output to enable microphone routing.")}
        guard mimic_mix_is_emergency(dsp)==0 else{return}
        if !ready || !engine.isRunning{try configure()}
        if !mic{try startCapture()}
        notice=""
        if diagnosticActive && !diagnosticReady {
            diagnosticReady=true;diagnosticUntil=Date(timeIntervalSinceNow:10);diagnosticConsumed=mimic_mix_consumed_mic_frames(dsp)
            try? probe.start()
            log("Physical mic diagnostic started: no tone; say a few words")
        }
    }
    func requestMic(_ enabled:Bool)throws {
        permissionEpoch+=1;permissionPending=false;micRequested=enabled
        if enabled{mimic_mix_resume(dsp)}
        if enabled {do{try activateRequestedMic()}catch{notice=error.localizedDescription;log("Capture failed: \(notice)");micRequested=false;throw error}}
        else {stopCapture();notice="Microphone off";log("Microphone disabled by user")}
    }
    func finishDiagnostic(){
        let raw=retainedTelemetry?.snapshot() ?? [:],read=probe.snapshot()
        let consumed=mimic_mix_consumed_mic_frames(dsp)-diagnosticConsumed
        let rawFrames=raw["physicalFrames"] as? UInt64 ?? 0,converted=raw["pushedMicFrames"] as? UInt64 ?? 0
        let maxPeak=raw["physicalMicMaxPeak"] as? Float ?? 0
        let virtualPeak=read["virtualMicMaxPeak"] as? Float ?? 0
        diagnosticReport=["completedAt":ISO8601DateFormatter().string(from:Date()),"deviceDetected":preferredInput.map{id in physicalInputs().contains{$0["id"] as? UInt32==id}} ?? false,"permissionGranted":AVCaptureDevice.authorizationStatus(for:.audio) == .authorized,"captureStarted":mic,"samplesReceived":rawFrames>0,"nonzeroPhysicalSignal":maxPeak>0.00001,"physicalFrames":rawFrames,"physicalPeak":maxPeak,"pushedFrames":converted,"mixerConsumedFrames":consumed,"signalReachedMixer":converted>0 && consumed>0,"virtualFrames":read["probeFrames"] ?? 0,"virtualPeak":virtualPeak,"virtualReaderAvailable":read["virtualMeterAvailable"] ?? false,"virtualSignalWithNoClips":!diagnosticHadClips && virtualPeak>0.00001 && converted>0 && consumed>0 && gain>0,"clipsDuringTest":diagnosticHadClips,"speechConfirmedByHuman":false,"instruction":"The meter may include background noise. Confirm it responds to your voice to check speech capture.","error":raw["captureError"] ?? ""]
        diagnosticActive=false;diagnosticReady=false
        probe.stop()
        if !diagnosticRestore{micRequested=false;stopCapture()}
        log("Physical mic diagnostic finished: frames=\(rawFrames), mixer consumed=\(consumed), peak=\(maxPeak), virtual peak=\(virtualPeak)")
    }
    func checkDevices(){
        if sleeping{return}
        if mimic_mix_is_emergency(dsp) != 0{micRequested=false;permissionEpoch+=1;permissionPending=false;return}
        if !ready,let id=devices().first(where:{$0["uid"] as? String==selectedOutputUID})?["id"] as? UInt32{output=id}
        if mic {
            let frames=mimic_mix_input_frames(dsp)
            if frames != lastInputFrames{lastInputFrames=frames;lastInputTime=Date()}
            else if Date().timeIntervalSince(lastInputTime)>3{stopCapture();retryAfter=Date(timeIntervalSinceNow:2);notice="No capture frames received. Check captureError. Retrying the selected input.";log(notice)}
        }
        if ready && (!engine.isRunning || !devices().contains(where:{$0["id"] as? UInt32 == output})){
            engine.stop();monitorEngine?.stop();mimic_mix_monitor(dsp,0);ready=false;stopClips();stopCapture();probe.stop();notice="Output disconnected. Waiting for the selected device.";log(notice)
        }
        if ready && monitor && Date()>monitorRetryAfter {
            let target=monitorTarget()
            if target != monitorDevice || (target != output && monitorEngine?.isRunning != true) {
                do{try startMonitor()}catch{monitorNotice=error.localizedDescription;monitorRetryAfter=Date(timeIntervalSinceNow:3)}
            }
        }
        if mic && (capture?.running != true || capture?.formatStillMatches() != true || !physicalInputs().contains(where:{$0["uid"] as? String == selectedInputUID})){
            stopCapture();retryAfter=Date(timeIntervalSinceNow:1);notice="Input disconnected or changed format. Waiting for the selected microphone.";log(notice)
        }
        if let replacement=physicalInputs().first(where:{$0["uid"] as? String == selectedInputUID})?["id"] as? UInt32{
            preferredInput=replacement
            if micRequested && !mic && !permissionPending && Date()>retryAfter {
                do{try activateRequestedMic()}catch{retryAfter=Date(timeIntervalSinceNow:3);notice=error.localizedDescription;log("Recovery: \(notice)")}
            }
        }
        if diagnosticActive && diagnosticReady && Date()>=diagnosticUntil{finishDiagnostic()}
    }
    func status()->[String:Any]{
        let slots=names.keys.sorted().filter{mimic_voice_active(dsp,$0) != 0}
        let active=slots.compactMap{names[$0]}
        let virtual=devices().first(where:{$0["uid"] as? String == "MIMICAudioDevice_UID"})
        var result:[String:Any] = ["playing":active.last as Any? ?? NSNull(),"activeClips":active,"polyphony":parallel,"maxVoices":8,
                "volume":volume,"mic":mic && (capture?.running ?? false) && mimic_mix_is_emergency(dsp)==0,"micGain":gain,"running":engine.isRunning,
                "output":output,"outputName":deviceName(output),"outputUID":deviceString(output,kAudioDevicePropertyDeviceUID),
                "input":preferredInput ?? 0,"inputName":preferredInput.map{deviceName($0)} ?? "Select a microphone","inputUID":selectedInputUID,
                "micPermission":AVCaptureDevice.authorizationStatus(for:.audio).rawValue,
                "micLevel":mimic_mix_meter(dsp,0),"clipLevel":mimic_mix_meter(dsp,1),"outputLevel":mimic_mix_meter(dsp,2),"limiting":mimic_mix_meter(dsp,3)>0,
                "micFrames":mimic_mix_input_frames(dsp),"captureHealthy":mic && mimic_mix_input_frames(dsp)>inputBaseline,"micUnderruns":mimic_mix_underruns(dsp),"monitor":monitor,"monitorDevice":monitorDevice,
                "driverInstalled":FileManager.default.fileExists(atPath:"/Library/Audio/Plug-Ins/HAL/MIMICMicrophone.driver"),
                "driverRegistered":virtual != nil,"virtualConnected":virtual?["id"] as? UInt32 == output && engine.isRunning,
                "monitorUID":selectedMonitorUID,"monitorRunning":monitorEngine?.isRunning ?? false,"monitorNotice":monitorNotice,
                "notice":notice,"sampleRate":48000]
        let telemetry=retainedTelemetry?.snapshot() ?? [:]
        result.merge(telemetry){_,new in new}
        if !mic{result["physicalMicLevel"]=0;result["physicalMicRMS"]=0}
        result["mixerOutputLevel"]=mimic_mix_meter(dsp,2)
        result["micConsumedFrames"]=mimic_mix_consumed_mic_frames(dsp)
        result["micRequested"]=micRequested;result["permissionPending"]=permissionPending
        result["captureFormat"]=capture?.formatDescription ?? retainedFormat
        result["captureProcess"]="MIMIC --audio-helper";result["capturePID"]=ProcessInfo.processInfo.processIdentifier
        result["diagnosticActive"]=diagnosticActive;result["diagnosticReady"]=diagnosticReady;result["physicalDiagnostic"]=diagnosticReport
        result["audioLog"]=audioLog
        result.merge(probe.snapshot()){_,new in new};return result
    }
    func command(_ c:[String:Any])throws->[String:Any]{
        if !["status","devices"].contains(c["op"] as? String ?? ""){notice=""}
        switch c["op"] as? String ?? ""{
        case "devices":return ["devices":devices(),"inputs":devices(kAudioDevicePropertyScopeInput),"physicalInputs":physicalInputs(),"defaultInput":suggestedInput() ?? 0]
        case "status":return status()
        case "probe":
            if c["enabled"] as? Bool ?? false{
                let permission=AVCaptureDevice.authorizationStatus(for:.audio)
                if permission == .notDetermined{AVCaptureDevice.requestAccess(for:.audio){_ in};return ["notice":"Allow VUPIO microphone access in macOS, then run the test again."]}
                guard permission == .authorized else{throw AudioFailure.message("Allow VUPIO microphone access in macOS to test the virtual input")}
                try probe.start()
            }else{probe.stop()}
        case "input":
            let id=AudioDeviceID(c["device"] as? Int ?? 0)
            guard physicalInputs().contains(where:{$0["id"] as? UInt32 == id})else{throw AudioFailure.message("Select a physical input")}
            stopCapture();preferredInput=id;selectedInputUID=deviceString(id,kAudioDevicePropertyDeviceUID);if micRequested{try activateRequestedMic()}
        case "output":
            guard let value=c["device"] as? Int,value>0,value<=Int(UInt32.max),devices().contains(where:{$0["id"] as? UInt32==UInt32(value)})else{throw AudioFailure.message("Audio output unavailable")}
            let next=UInt32(value),name=deviceName(UInt32(value)).lowercased()
            if micRequested && deviceString(next,kAudioDevicePropertyDeviceUID) != "MIMICAudioDevice_UID" && !["blackhole","aggregate","multi-output"].contains(where:name.contains){try requestMic(false);notice="Microphone disabled for physical output. Select MIMIC Microphone to route your voice."}
            stopClips();probe.stop();output=next;selectedOutputUID=deviceString(output,kAudioDevicePropertyDeviceUID)
            if c["start"] as? Bool ?? true {try configure()}
            else{engine.stop();monitorEngine?.stop();ready=false}
        case "play":
            if diagnosticActive{diagnosticHadClips=true}
            if mimic_mix_is_emergency(dsp) != 0{stopCapture();mimic_mix_resume(dsp)}
            guard let path=c["path"] as? String else{throw AudioFailure.message("No file")}
            if !ready || !engine.isRunning{try configure()}
            if !parallel{stopClips()}
            let slot=(Int32(0)..<Int32(8)).first(where:{mimic_voice_active(dsp,$0)==0}) ?? order.min(by:{$0.value<$1.value})!.key
            feeds[slot]?.cancel();let ticket=mimic_voice_begin(dsp,slot)
            do{let feed=try ClipFeed(dsp:dsp,slot:slot,ticket:ticket,path:path);feeds[slot]=feed;names[slot]=c["id"] as? String ?? "clip";counter+=1;order[slot]=counter;feed.start()}catch{mimic_voice_stop(dsp,slot);throw error}
        case "stop":stopClips()
        case "panic":panic()
        case "volume":volume=min(1,max(0,Float(c["value"] as? Double ?? 0.65)));mimic_mix_gains(dsp,volume,gain)
        case "mixer":
            if let v=c["polyphony"] as? Bool{parallel=v}
            if let v=c["gain"] as? Double{gain=min(1,max(0,Float(v)));mimic_mix_gains(dsp,volume,gain)}
            if let v=c["monitorUID"] as? String{selectedMonitorUID=v}
            if let v=c["monitorDevice"] as? Int{
                if v==0{selectedMonitorUID=""}
                else{
                    guard v>0,v<=Int(UInt32.max),let row=devices().first(where:{$0["id"] as? UInt32==UInt32(v)}) else{throw AudioFailure.message("Local listening device unavailable")}
                    let name=(row["name"] as? String ?? "").lowercased(),transport=row["transport"] as? UInt32 ?? 0
                    guard transport != kAudioDeviceTransportTypeVirtual,transport != kAudioDeviceTransportTypeAggregate,!["blackhole","mimic microphone","aggregate","multi-output"].contains(where:name.contains)else{throw AudioFailure.message("Choose physical headphones or speakers for local listening.")}
                    selectedMonitorUID=row["uid"] as? String ?? ""
                }
            }
            if c["monitorUID"] != nil || c["monitorDevice"] != nil{monitorDevice=monitorTarget() ?? 0}
            if let v=c["monitor"] as? Bool{
                monitor=v;monitorRetryAfter = .distantPast;monitorNotice=""
                if c["start"] as? Bool == false || !monitor{monitorEngine?.stop();monitorEngine=nil;mimic_mix_monitor(dsp,0)}
                else{do{if !ready{try configure()}else{try startMonitor()}}catch{monitorNotice=error.localizedDescription;throw error}}
            }
        case "mic", "mic_test":
            let test=(c["op"] as? String)=="mic_test"
            if let id=c["device"] as? Int,id>0 {
                guard physicalInputs().contains(where:{$0["id"] as? UInt32==UInt32(id)})else{throw AudioFailure.message("The selected input is not an available physical microphone")}
                if UInt32(id) != preferredInput{stopCapture();preferredInput=UInt32(id);selectedInputUID=deviceString(UInt32(id),kAudioDevicePropertyDeviceUID)}
            }
            gain=min(1,max(0,Float(c["gain"] as? Double ?? Double(gain))));mimic_mix_gains(dsp,volume,gain)
            if test{
                if diagnosticActive{finishDiagnostic()}
                diagnosticRestore=micRequested;diagnosticActive=true;diagnosticReady=false;diagnosticHadClips=false;diagnosticReport=[:]
                stopClips();stopCapture();retainedTelemetry=CaptureTelemetry();retainedFormat="";diagnosticConsumed=mimic_mix_consumed_mic_frames(dsp)
                do{try requestMic(true)}catch{diagnosticActive=false;diagnosticReady=false;throw error}
            }else{
                if diagnosticActive{finishDiagnostic()}
                try requestMic(c["enabled"] as? Bool ?? false)
            }
        case "mic_test_stop":if diagnosticActive{finishDiagnostic()}
        default:throw AudioFailure.message("Unknown audio command")
        }
        return status()
    }
}
