import Cocoa
import CryptoKit
import Security

enum LocalUpdateError: LocalizedError {
    case message(String)
    var errorDescription: String? {
        if case let .message(text) = self { return text }
        return nil
    }
}

struct LocalRelease: Codable {
    let build: Int
    let codeHash: String
    let signature: Data

    var signedBytes: Data { Data("vupio-local-mac-arm64-v1\n\(build)\n\(codeHash)\n".utf8) }

    static func verified(in channel: URL, publicKey: Data) throws -> LocalRelease? {
        let path = channel.appendingPathComponent("latest.json")
        let handle: FileHandle
        do { handle = try FileHandle(forReadingFrom: path) }
        catch let error as NSError where error.domain == NSCocoaErrorDomain && [NSFileNoSuchFileError, NSFileReadNoSuchFileError].contains(error.code) { return nil }
        defer { try? handle.close() }
        let data = try handle.read(upToCount: 4097) ?? Data()
        guard data.count <= 4096 else { throw LocalUpdateError.message("Манифест обновления слишком большой.") }
        let release = try JSONDecoder().decode(LocalRelease.self, from: data)
        let key = try Curve25519.Signing.PublicKey(rawRepresentation: publicKey)
        guard release.build > 0, release.codeHash.count == 40,
              key.isValidSignature(release.signature, for: release.signedBytes) else {
            throw LocalUpdateError.message("Подпись обновления не совпала с ключом этой сборки.")
        }
        return release
    }

    static func codeHash(of bundle: URL) throws -> String {
        var code: SecStaticCode?
        guard SecStaticCodeCreateWithPath(bundle as CFURL, [], &code) == errSecSuccess, let code,
              SecStaticCodeCheckValidity(code, SecCSFlags(rawValue: kSecCSStrictValidate | kSecCSCheckNestedCode), nil) == errSecSuccess else {
            throw LocalUpdateError.message("Проверка целостности приложения не прошла.")
        }
        var details: CFDictionary?
        guard SecCodeCopySigningInformation(code, SecCSFlags(rawValue: kSecCSSigningInformation), &details) == errSecSuccess,
              let hash = (details as? [String: Any])?[kSecCodeInfoUnique as String] as? Data else {
            throw LocalUpdateError.message("У сборки отсутствует контрольный отпечаток подписи.")
        }
        return hash.map { String(format: "%02x", $0) }.joined()
    }
}

enum LocalUpdate {
    static func version(of app: URL) -> Int? {
        let plist = app.appendingPathComponent("Contents/Info.plist")
        guard let data = try? Data(contentsOf: plist),
              let info = (try? PropertyListSerialization.propertyList(from: data, format: nil)) as? [String: Any],
              info["CFBundleIdentifier"] as? String == "local.mimic.soundboard",
              let value = info["CFBundleVersion"] as? String else { return nil }
        return Int(value)
    }

    static func run(_ command: String, _ arguments: [String]) throws {
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: command)
        proc.arguments = arguments
        proc.standardInput = FileHandle.nullDevice
        proc.standardOutput = FileHandle.nullDevice
        proc.standardError = FileHandle.nullDevice
        try proc.run()
        proc.waitUntilExit()
        guard proc.terminationStatus == 0 else {
            throw LocalUpdateError.message("Не удалось выполнить обновление. Проверьте права на папку приложения и свободное место.")
        }
    }

    static func stage(_ release: LocalRelease, channel: URL, installed: URL) throws -> URL {
        let candidate = channel.appendingPathComponent(String(release.build)).appendingPathComponent("VUPIO.app")
        guard let current = version(of: installed), release.build > current, version(of: candidate) == release.build else {
            throw LocalUpdateError.message("В локальном канале отсутствует подходящая более новая сборка.")
        }
        let directory = installed.deletingLastPathComponent().appendingPathComponent(".vupio-update-" + UUID().uuidString)
        let manager = FileManager.default
        try manager.createDirectory(at: directory, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        let staged = directory.appendingPathComponent(installed.lastPathComponent)
        do {
            // APFS clones share unchanged bytes. rsync replaces only changed files.
            try run("/bin/cp", ["-cRP", installed.path, staged.path])
            try run("/usr/bin/rsync", ["-rltp", "--checksum", "--delete", candidate.path + "/", staged.path + "/"])
            guard version(of: staged) == release.build, try LocalRelease.codeHash(of: staged) == release.codeHash else {
                throw LocalUpdateError.message("Подготовленная сборка отличается от подписанного релиза.")
            }
            return staged
        } catch {
            try? manager.removeItem(at: directory)
            throw error
        }
    }

    static func exchange(_ installed: URL, _ staged: URL) throws {
        guard renameatx_np(AT_FDCWD, installed.path, AT_FDCWD, staged.path, UInt32(RENAME_SWAP)) == 0 else {
            throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO)
        }
    }

    static func install(_ staged: URL, at installed: URL, appPID: Int32, serverPID: Int32) throws {
        try exchange(installed, staged)
        do {
            let helper = Process()
            helper.executableURL = staged.appendingPathComponent("Contents/MacOS/MIMIC")
            helper.arguments = ["--vupio-relaunch", String(appPID), String(serverPID)]
            try helper.run()
        } catch {
            try exchange(installed, staged)
            try? FileManager.default.removeItem(at: staged.deletingLastPathComponent())
            throw error
        }
    }

    static func relaunch(_ args: [String]) {
        let previous = Bundle.main.bundleURL
        let directory = previous.deletingLastPathComponent()
        guard args.count == 2, let appPID = Int32(args[0]), appPID > 1, let serverPID = Int32(args[1]),
              previous.pathExtension == "app", directory.lastPathComponent.hasPrefix(".vupio-update-") else { return }
        let installed = directory.deletingLastPathComponent().appendingPathComponent(previous.lastPathComponent)
        for _ in 0..<150 {
            if kill(appPID, 0) != 0 && (serverPID <= 1 || kill(serverPID, 0) != 0) { break }
            Thread.sleep(forTimeInterval: 0.1)
        }
        do {
            try run("/usr/bin/open", ["-n", installed.path])
            try? FileManager.default.removeItem(at: directory)
        } catch {
            if (try? exchange(installed, previous)) != nil {
                try? run("/usr/bin/open", ["-n", installed.path])
            }
        }
    }
}
