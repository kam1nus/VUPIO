import Cocoa
import Sparkle
import CryptoKit

final class AppUpdater: NSObject, SPUUserDriver, SPUUpdaterDelegate {
    private var updater: SPUUpdater!
    private var reply: ((SPUUserUpdateChoice) -> Void)?
    private let changed: ([String: Any]) -> Void
    private let installed = Int(Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "") ?? 0
    private var latest = 0
    private var size: UInt64 = 0
    private var received: UInt64 = 0
    private var state = "idle"
    private var error = ""
    private var message = ""
    var automaticDownload: Bool {
        get { UserDefaults.standard.object(forKey: "VUPIOAutoDownload") as? Bool ?? true }
        set {
            UserDefaults.standard.set(newValue, forKey: "VUPIOAutoDownload")
            publish()
            if newValue && state == "available" { download() }
        }
    }

    init(changed: @escaping ([String: Any]) -> Void) {
        self.changed = changed
        super.init()
        updater = SPUUpdater(hostBundle: .main, applicationBundle: .main, userDriver: self, delegate: self)
        do { try updater.start() }
        catch { self.error = error.localizedDescription; state = "failed" }
        updater.automaticallyChecksForUpdates = false
        updater.automaticallyDownloadsUpdates = false
    }

    func publish() {
        changed(["installed": installed, "latest": latest, "platform": "darwin", "supported": true,
                 "app_update": latest > installed, "state": state, "received": received, "size": size,
                 "auto": automaticDownload, "error": error, "message": message,
                 "download": "https://github.com/kam1nus/VUPIO/releases"])
    }

    func check(automatic: Bool = false) {
        if updater.canCheckForUpdates {
            error = ""; message = "Checking for updates…"; state = "checking"
            publish()
            updater.checkForUpdates()
        } else { publish() }
    }

    func download() {
        guard state == "available", let action = reply else { publish(); return }
        reply = nil
        action(.install)
    }

    func install() {
        guard state == "ready", let action = reply else { publish(); return }
        reply = nil
        state = "installing"; message = "Installing and restarting VUPIO…"; publish()
        action(.install)
    }

    func show(_ request: SPUUpdatePermissionRequest, reply: @escaping (SUUpdatePermissionResponse) -> Void) {
        reply(SUUpdatePermissionResponse(automaticUpdateChecks: false, sendSystemProfile: false))
    }
    func showUserInitiatedUpdateCheck(cancellation: @escaping () -> Void) {}
    func showUpdateFound(with appcastItem: SUAppcastItem, state updateState: SPUUserUpdateState, reply: @escaping (SPUUserUpdateChoice) -> Void) {
        latest = Int(appcastItem.versionString) ?? 0
        let components = appcastItem.fileURL.flatMap { URLComponents(url:$0,resolvingAgainstBaseURL:false) }
        let expectedModels = components?.queryItems?.first(where: { $0.name == "models" })?.value
        let resources = Bundle.main.resourceURL!
        let manifest = (try? Data(contentsOf:resources.appendingPathComponent("model-components.json"))) ??
            (try? Data(contentsOf:resources.appendingPathComponent("Models/components.json")))
        let actualModels = manifest.map { SHA256.hash(data:$0).map { String(format:"%02x",$0) }.joined() }
        guard let expectedModels, expectedModels == actualModels else {
            state = "failed"; error = "This release includes new AI models. Use the full installer from GitHub."; publish()
            reply(.dismiss)
            return
        }
        guard !appcastItem.isInformationOnlyUpdate else {
            state = "failed"; error = "This release needs the full installer from GitHub."; publish()
            reply(.dismiss)
            return
        }
        size = appcastItem.contentLength
        self.reply = reply
        received = updateState.stage == .notDownloaded ? 0 : size
        state = updateState.stage == .notDownloaded ? "available" : "ready"
        message = ""
        publish()
        if state == "available" && automaticDownload { download() }
    }
    func showUpdateReleaseNotes(with downloadData: SPUDownloadData) {}
    func showUpdateReleaseNotesFailedToDownloadWithError(_ error: Error) {}
    func showUpdateNotFoundWithError(_ error: Error, acknowledgement: @escaping () -> Void) {
        latest = installed; state = "idle"; message = "Your build is up to date."; self.error = ""; publish()
        acknowledgement()
    }
    func showUpdaterError(_ error: Error, acknowledgement: @escaping () -> Void) {
        state = "failed"; self.error = error.localizedDescription; message = ""; publish()
        acknowledgement()
    }
    func showDownloadInitiated(cancellation: @escaping () -> Void) {
        state = "downloading"; received = 0; message = ""; publish()
    }
    func showDownloadDidReceiveExpectedContentLength(_ expectedContentLength: UInt64) {
        size = expectedContentLength; publish()
    }
    func showDownloadDidReceiveData(ofLength length: UInt64) {
        received += length; publish()
    }
    func showDownloadDidStartExtractingUpdate() {
        state = "preparing"; message = "Verifying and preparing the update…"; publish()
    }
    func showExtractionReceivedProgress(_ progress: Double) {}
    func showReady(toInstallAndRelaunch reply: @escaping (SPUUserUpdateChoice) -> Void) {
        self.reply = reply; state = "ready"; message = ""; received = size; publish()
    }
    func showInstallingUpdate(withApplicationTerminated applicationTerminated: Bool, retryTerminatingApplication: @escaping () -> Void) {
        state = "installing"; message = "Installing and restarting VUPIO…"; publish()
    }
    func showUpdateInstalledAndRelaunched(_ relaunched: Bool, acknowledgement: @escaping () -> Void) {
        state = "idle"; message = "Update installed."; publish(); acknowledgement()
    }
    func dismissUpdateInstallation() { reply = nil }
    func updaterWillRelaunchApplication(_ updater: SPUUpdater) {}
}
