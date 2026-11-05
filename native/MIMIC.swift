import Cocoa
import WebKit
import AVFoundation
import CoreAudio
import AudioToolbox
import UniformTypeIdentifiers

func deviceString(_ id: AudioDeviceID, _ selector: AudioObjectPropertySelector) -> String {
    var address = AudioObjectPropertyAddress(mSelector:selector,mScope:kAudioObjectPropertyScopeGlobal,mElement:kAudioObjectPropertyElementMain)
    let value=UnsafeMutablePointer<CFString?>.allocate(capacity:1)
    value.initialize(to:nil)
    defer { value.deinitialize(count:1); value.deallocate() }
    var size = UInt32(MemoryLayout<CFString?>.size)
    guard AudioObjectGetPropertyData(id,&address,0,nil,&size,value) == noErr,
          let text=value.pointee else { return "Device \(id)" }
    return text as String
}
func deviceName(_ id: AudioDeviceID) -> String { deviceString(id,kAudioObjectPropertyName) }
func defaultDevice(_ selector: AudioObjectPropertySelector) -> AudioDeviceID {
    var address = AudioObjectPropertyAddress(mSelector:selector,mScope:kAudioObjectPropertyScopeGlobal,mElement:kAudioObjectPropertyElementMain)
    var value: AudioDeviceID = 0
    var size = UInt32(MemoryLayout<AudioDeviceID>.size)
    AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject),&address,0,nil,&size,&value)
    return value
}
func deviceTransport(_ id:AudioDeviceID)->UInt32 {
    var address=AudioObjectPropertyAddress(mSelector:kAudioDevicePropertyTransportType,mScope:kAudioObjectPropertyScopeGlobal,mElement:0)
    var value:UInt32=0;var size:UInt32=4
    AudioObjectGetPropertyData(id,&address,0,nil,&size,&value);return value
}
func devices(_ scope:AudioObjectPropertyScope=kAudioDevicePropertyScopeOutput) -> [[String:Any]] {
    var address = AudioObjectPropertyAddress(mSelector:kAudioHardwarePropertyDevices,mScope:kAudioObjectPropertyScopeGlobal,mElement:kAudioObjectPropertyElementMain)
    var size:UInt32=0
    AudioObjectGetPropertyDataSize(AudioObjectID(kAudioObjectSystemObject),&address,0,nil,&size)
    var ids=[AudioDeviceID](repeating:0,count:Int(size)/MemoryLayout<AudioDeviceID>.size)
    _ = ids.withUnsafeMutableBytes { AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject),&address,0,nil,&size,$0.baseAddress!) }
    return ids.compactMap { id in
        var streamAddress=AudioObjectPropertyAddress(mSelector:kAudioDevicePropertyStreams,mScope:scope,mElement:kAudioObjectPropertyElementMain)
        var bytes:UInt32=0
        AudioObjectGetPropertyDataSize(id,&streamAddress,0,nil,&bytes)
        return bytes > 0 ? ["id":id,"name":deviceName(id),"uid":deviceString(id,kAudioDevicePropertyDeviceUID),"transport":deviceTransport(id)] : nil
    }
}
enum AudioFailure: LocalizedError {
    case message(String)
    var errorDescription:String? { if case let .message(s)=self { return s }; return nil }
}
final class WindowDelegate:NSObject,NSApplicationDelegate,WKNavigationDelegate,WKUIDelegate,WKScriptMessageHandler {
    var window:NSWindow!
    var process:Process?
    var outputPipe:Pipe?
    var outputBuffer=""
    var web:WKWebView!
    var retryCount=0
    var launchTimer:Timer?
    var launchFile:URL?
    var interfaceLoaded=false
    var errorPipe:Pipe?
    var errorBuffer=""
    var statusLabel:NSTextField!
    var appURL:URL?
    var updateBusy=false
    let root=Bundle.main.bundleURL.deletingLastPathComponent()
    func applicationDidFinishLaunching(_ notification:Notification) {
        let app=NSApplication.shared
        app.setActivationPolicy(.regular)
        let menu=NSMenu(); let item=NSMenuItem(); menu.addItem(item)
        let sub=NSMenu()
        sub.addItem(withTitle:"About VUPIO",action:#selector(NSApplication.orderFrontStandardAboutPanel(_:)),keyEquivalent:"")
        sub.addItem(NSMenuItem.separator())
        sub.addItem(withTitle:"Quit VUPIO",action:#selector(NSApplication.terminate(_:)),keyEquivalent:"q"); item.submenu=sub; app.mainMenu=menu
        let editItem=NSMenuItem(title:"Edit",action:nil,keyEquivalent:"");let editMenu=NSMenu(title:"Edit")
        editMenu.addItem(withTitle:"Cut",action:#selector(NSText.cut(_:)),keyEquivalent:"x")
        editMenu.addItem(withTitle:"Copy",action:#selector(NSText.copy(_:)),keyEquivalent:"c")
        editMenu.addItem(withTitle:"Paste",action:#selector(NSText.paste(_:)),keyEquivalent:"v")
        editMenu.addItem(withTitle:"Select All",action:#selector(NSText.selectAll(_:)),keyEquivalent:"a")
        editItem.submenu=editMenu;menu.addItem(editItem)
        window=NSWindow(contentRect:NSRect(x:0,y:0,width:1200,height:820),styleMask:[.titled,.closable,.miniaturizable,.resizable],backing:.buffered,defer:false)
        window.title="VUPIO Alpha v0.4.3 · starting…"
        window.minSize=NSSize(width:660,height:490)
        window.appearance=NSAppearance(named:.darkAqua)
        window.backgroundColor=NSColor(srgbRed:23/255.0,green:25/255.0,blue:29/255.0,alpha:1)
        window.center()
        let content=NSView(frame:NSRect(x:0,y:0,width:1200,height:820))
        let config=WKWebViewConfiguration()
        config.userContentController.add(self,name:"mimicNative")
        web=WKWebView(frame:content.bounds,configuration:config)
        web.navigationDelegate=self;web.uiDelegate=self
        web.underPageBackgroundColor=window.backgroundColor
        web.autoresizingMask=[.width,.height]; web.isHidden=true
        statusLabel=NSTextField(wrappingLabelWithString:"Starting the VUPIO local server…")
        statusLabel.frame=NSRect(x:60,y:300,width:1000,height:280)
        statusLabel.autoresizingMask=[.width,.minYMargin,.maxYMargin]
        statusLabel.font=NSFont.systemFont(ofSize:18)
        content.addSubview(web); content.addSubview(statusLabel); window.contentView=content
        window.makeKeyAndOrderFront(nil); app.activate(ignoringOtherApps:true)
        let proc=Process()
        // build/MIMIC.app → project root is one more directory above build.
        let project=root.deletingLastPathComponent()
        let resources=Bundle.main.resourceURL!
        let packed=resources.appendingPathComponent("server/mimic-server")
        let portable=FileManager.default.isExecutableFile(atPath:packed.path)
        if portable {
            proc.executableURL=packed
            proc.arguments=["--audio",Bundle.main.executablePath!]
            proc.currentDirectoryURL=resources
        } else {
            proc.executableURL=URL(fileURLWithPath:"/bin/zsh")
            proc.arguments=["-f",project.appendingPathComponent("scripts/server.sh").path]
            proc.currentDirectoryURL=project
        }
        proc.standardInput=FileHandle.nullDevice
        var env=ProcessInfo.processInfo.environment
        env["MIMIC_AUDIO_EXECUTABLE"]=Bundle.main.executablePath!
        env["MIMIC_BUILD_NUMBER"]=Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String
        if portable {
            let tools=resources.appendingPathComponent("Tools").path
            env["MIMIC_TOOLS"]=tools
            env["MIMIC_BUNDLED_MODELS"]=resources.appendingPathComponent("Models").path
            env["PATH"]=tools+":/usr/bin:/bin:/usr/sbin:/sbin"
            if !FileManager.default.isExecutableFile(atPath:tools+"/llama-server/llama-server") {
                env["GGML_METAL_PATH_RESOURCES"]=tools
            }
        }
        let readyFile=FileManager.default.temporaryDirectory.appendingPathComponent("mimic-"+UUID().uuidString+".json")
        launchFile=readyFile
        env["MIMIC_LAUNCH_FILE"]=readyFile.path
        proc.environment=env
        let pipe=Pipe(); outputPipe=pipe; proc.standardOutput=pipe
        let errors=Pipe(); errorPipe=errors; proc.standardError=errors
        errors.fileHandleForReading.readabilityHandler = { handle in
            let data=handle.availableData
            if data.isEmpty { return }
            let text=String(data:data,encoding:.utf8) ?? ""
            DispatchQueue.main.async { self.errorBuffer += text; self.statusLabel.stringValue="Starting server…\n"+self.errorBuffer }
        }
        process=proc
        pipe.fileHandleForReading.readabilityHandler = { handle in
            let data=handle.availableData
            if data.isEmpty { return }
            let text=String(data:data,encoding:.utf8) ?? ""
            DispatchQueue.main.async {
                self.outputBuffer += text
                while let newline=self.outputBuffer.firstIndex(of:"\n") {
                    let line=String(self.outputBuffer[..<newline])
                    self.outputBuffer.removeSubrange(...newline)
                    if line.hasPrefix("MIMIC Mac: "), let target=URL(string:String(line.dropFirst(11))) {
                        self.openInterface(target)
                    }
                }
            }
        }
        proc.terminationHandler = { _ in DispatchQueue.main.async {
            self.web.isHidden=true; self.statusLabel.isHidden=false
            self.window.title="VUPIO · server stopped"
            self.statusLabel.stringValue="The VUPIO server stopped.\n"+self.errorBuffer+"\nClose the app. For details, run scripts/start.sh in Terminal."
        }}
        do { try proc.run() } catch {
            statusLabel.stringValue="Could not start the server:\n"+error.localizedDescription
        }
        launchTimer=Timer.scheduledTimer(withTimeInterval:0.2,repeats:true) { timer in
            if self.interfaceLoaded { timer.invalidate(); return }
            if let data=try? Data(contentsOf:readyFile),
               let object=try? JSONSerialization.jsonObject(with:data) as? [String:Any],
               let value=object["url"] as? String,let url=URL(string:value) {
                self.openInterface(url)
                timer.invalidate()
            }
        }
    }
    func openInterface(_ url:URL) {
        if interfaceLoaded { return }
        interfaceLoaded=true
        window.title="VUPIO Alpha v0.4.3"
        statusLabel.isHidden=true; web.isHidden=false
        appURL=url
        web.load(URLRequest(url:url))
    }
    func trusted(_ url:URL?) -> Bool {
        guard let url=url,let appURL=appURL else{return false}
        return url.host=="127.0.0.1" && url.port==appURL.port && url.scheme==appURL.scheme
    }
    func webView(_ webView:WKWebView,decidePolicyFor action:WKNavigationAction,decisionHandler:@escaping(WKNavigationActionPolicy)->Void) {
        if trusted(action.request.url) {decisionHandler(.allow)}
        else {
            if action.navigationType == .linkActivated, trusted(action.sourceFrame.request.url),
               let url=action.request.url,["https","http"].contains(url.scheme ?? ""),url.user==nil,url.password==nil {
                NSWorkspace.shared.open(url)
            }
            decisionHandler(.cancel)
        }
    }
    func webView(_ webView:WKWebView,createWebViewWith configuration:WKWebViewConfiguration,for action:WKNavigationAction,windowFeatures:WKWindowFeatures)->WKWebView? {
        if action.navigationType == .linkActivated, trusted(action.sourceFrame.request.url),
           let url=action.request.url,["https","http"].contains(url.scheme ?? ""),url.user==nil,url.password==nil {
            NSWorkspace.shared.open(url)
        }
        return nil
    }
    func webView(_ webView:WKWebView,runJavaScriptConfirmPanelWithMessage message:String,initiatedByFrame frame:WKFrameInfo,completionHandler:@escaping(Bool)->Void){
        guard trusted(frame.request.url) else{completionHandler(false);return}
        let alert=NSAlert();alert.messageText=message
        alert.addButton(withTitle:"Continue");alert.addButton(withTitle:"Cancel")
        alert.beginSheetModal(for:window){completionHandler($0 == .alertFirstButtonReturn)}
    }
    func webView(_ webView:WKWebView,runOpenPanelWith parameters:WKOpenPanelParameters,initiatedByFrame frame:WKFrameInfo,completionHandler:@escaping([URL]?)->Void) {
        guard frame.isMainFrame,trusted(frame.request.url) else{completionHandler(nil);return}
        let panel=NSOpenPanel()
        panel.canChooseDirectories=false
        panel.allowsMultipleSelection=parameters.allowsMultipleSelection
        panel.allowedContentTypes=[.audio,.mpeg4Movie]+["ogg","opus","flac","m4a","webm"].compactMap{UTType(filenameExtension:$0)}
        panel.message="Choose an audio file for your VUPIO library."
        panel.beginSheetModal(for:window){result in completionHandler(result == .OK ? panel.urls : nil)}
    }
    func userContentController(_ userContentController:WKUserContentController,didReceive message:WKScriptMessage) {
        guard message.frameInfo.isMainFrame,trusted(message.frameInfo.request.url),let action=message.body as? String else{return}
        if action == "checkUpdates" {
            checkLocalUpdate()
            return
        }
        if action=="importModel" {
            let panel=NSOpenPanel();panel.canChooseDirectories=false
            panel.allowedContentTypes=[UTType(filenameExtension:"gguf") ?? .data]
            panel.beginSheetModal(for:window){response in
                guard response == .OK,let url=panel.url,url.pathExtension.lowercased()=="gguf" else{return}
                self.web.callAsyncJavaScript("return window.mimicImportModel(path,title)",arguments:["path":url.path,"title":url.deletingPathExtension().lastPathComponent],in:nil,in:.page,completionHandler:nil)
            }
            return
        }
        let packages=["installDriver":"MIMIC-Audio-0.3.pkg","uninstallDriver":"MIMIC-Audio-Uninstall-0.3.pkg"]
        guard let name=packages[action] else{return}
        guard let url=Bundle.main.resourceURL?.appendingPathComponent("Audio/"+name),FileManager.default.fileExists(atPath:url.path),NSWorkspace.shared.open(url) else{
            web.callAsyncJavaScript("window.mimicNativeError(message)",arguments:["message":"The installer is unavailable. Open a full VUPIO build."],in:nil,in:.page,completionHandler:nil)
            return
        }
    }
    func updateStatus(_ text: String, error: Bool = false, busy: Bool = false) {
        updateBusy = busy
        web.callAsyncJavaScript("window.vupioUpdateStatus(text,error,busy)",arguments:["text":text,"error":error,"busy":busy],in:nil,in:.page,completionHandler:nil)
    }

    func checkLocalUpdate() {
        guard !updateBusy else { return }
        let installed = Bundle.main.bundleURL
        guard let folder = Bundle.main.object(forInfoDictionaryKey: "VUPIOLocalUpdateFolder") as? String,
              let value = Bundle.main.object(forInfoDictionaryKey: "VUPIOLocalUpdatePublicKey") as? String,
              let key = Data(base64Encoded: value), let build = LocalUpdate.version(of: installed) else {
            updateStatus("This build has no local update channel configured.")
            return
        }
        let channel = URL(fileURLWithPath: folder, isDirectory: true)
        updateStatus("Checking the local channel…", busy: true)
        DispatchQueue.global(qos: .userInitiated).async {
            do {
                let release = try LocalRelease.verified(in: channel, publicKey: key)
                DispatchQueue.main.async {
                    guard let release, release.build > build else {
                        self.updateStatus("Your local build is up to date · " + String(build))
                        return
                    }
                    let alert = NSAlert()
                    alert.messageText = "VUPIO build available " + String(release.build)
                    alert.informativeText = "VUPIO will update and restart. Save any audio edits before updating."
                    alert.addButton(withTitle: "Update and restart")
                    alert.addButton(withTitle: "Later")
                    alert.beginSheetModal(for: self.window) { response in
                        guard response == .alertFirstButtonReturn else { self.updateStatus("Update postponed."); return }
                        self.applyLocalUpdate(release, channel: channel, installed: installed)
                    }
                }
            } catch {
                DispatchQueue.main.async { self.updateStatus(error.localizedDescription, error: true) }
            }
        }
    }

    func applyLocalUpdate(_ release: LocalRelease, channel: URL, installed: URL) {
        updateStatus("Preparing and verifying the build…", busy: true)
        DispatchQueue.global(qos: .userInitiated).async {
            do {
                let staged = try LocalUpdate.stage(release, channel: channel, installed: installed)
                DispatchQueue.main.async {
                    do {
                        let pid = ProcessInfo.processInfo.processIdentifier
                        let serverPID = self.process.flatMap { $0.isRunning ? $0.processIdentifier : nil } ?? 0
                        try LocalUpdate.install(staged, at: installed, appPID: pid, serverPID: serverPID)
                        NSApplication.shared.terminate(nil)
                    } catch {
                        self.updateStatus(error.localizedDescription, error: true)
                    }
                }
            } catch {
                DispatchQueue.main.async { self.updateStatus(error.localizedDescription, error: true) }
            }
        }
    }
    func webView(_ webView:WKWebView,didFailProvisionalNavigation navigation:WKNavigation!,withError error:Error) {
        if retryCount<5 {
            retryCount += 1
            DispatchQueue.main.asyncAfter(deadline:.now()+0.5) { webView.reload() }
        } else {
            let alert=NSAlert(); alert.messageText="Could not open the VUPIO interface"; alert.informativeText=error.localizedDescription; alert.runModal()
        }
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender:NSApplication)->Bool { true }
    func applicationWillTerminate(_ notification:Notification) {
        process?.terminationHandler=nil
        web.configuration.userContentController.removeScriptMessageHandler(forName:"mimicNative")
        launchTimer?.invalidate()
        process?.terminate()
        if let launchFile=launchFile { try? FileManager.default.removeItem(at:launchFile) }
    }
}

if CommandLine.arguments.dropFirst().first == "--vupio-relaunch" {
    LocalUpdate.relaunch(Array(CommandLine.arguments.dropFirst(2)))
} else if CommandLine.arguments.contains("--analyze"),let index=CommandLine.arguments.firstIndex(of:"--analyze"),CommandLine.arguments.count>index+1 {
    let result=classifyFile(CommandLine.arguments[index+1])
    let data=try! JSONSerialization.data(withJSONObject:result)
    print(String(data:data,encoding:.utf8)!)
} else if CommandLine.arguments.contains("--audio-helper") {
    let sound=SoundEngine()
    DispatchQueue.global().async {
        while let line=readLine() {
            let semaphore=DispatchSemaphore(value:0)
            DispatchQueue.main.async {
                var response:[String:Any]
                do {
                    guard let data=line.data(using:.utf8), let c=try JSONSerialization.jsonObject(with:data) as? [String:Any] else { throw AudioFailure.message("Invalid JSON") }
                    response=try sound.command(c)
                } catch { response=["error":error.localizedDescription] }
                if let data=try? JSONSerialization.data(withJSONObject:response,options:[.sortedKeys]), let text=String(data:data,encoding:.utf8) { print(text); fflush(stdout) }
                semaphore.signal()
            }
            semaphore.wait()
        }
        DispatchQueue.main.async { sound.stopCapture(); sound.engine.stop(); exit(0) }
    }
    RunLoop.main.run()
} else {
    let app=NSApplication.shared
    let delegate=WindowDelegate(); app.delegate=delegate
    app.run()
}
