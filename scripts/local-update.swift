import Foundation
import CryptoKit

func privateKey(_ path: String, create: Bool) throws -> Curve25519.Signing.PrivateKey {
    if create {
        let fd = open(path, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0o600)
        if fd >= 0 {
            let key = Curve25519.Signing.PrivateKey()
            let handle = FileHandle(fileDescriptor: fd, closeOnDealloc: true)
            try handle.write(contentsOf: key.rawRepresentation)
            try handle.close()
            return key
        }
        guard errno == EEXIST else { throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO) }
    }
    var info = stat()
    guard lstat(path, &info) == 0, info.st_mode & S_IFMT == S_IFREG,
          info.st_uid == getuid(), info.st_mode & 0o077 == 0 else {
        throw LocalUpdateError.message("Ключ должен быть обычным файлом текущего пользователя с правами 600.")
    }
    return try Curve25519.Signing.PrivateKey(rawRepresentation: Data(contentsOf: URL(fileURLWithPath: path)))
}

@main
struct ReleaseTool {
    static func main() throws {
        let args = Array(CommandLine.arguments.dropFirst())
        if args.count == 2 && args[0] == "key" {
            print(try privateKey(args[1], create: true).publicKey.rawRepresentation.base64EncodedString())
            return
        }
        guard args.count == 4, args[0] == "publish" else {
            throw LocalUpdateError.message("Используйте key <keyfile> или publish <keyfile> <folder> <app>.")
        }
        let key = try privateKey(args[1], create: false)
        let channel = URL(fileURLWithPath: args[2], isDirectory: true).standardizedFileURL
        let app = URL(fileURLWithPath: args[3], isDirectory: true).standardizedFileURL
        guard let build = LocalUpdate.version(of: app), build > 0 else {
            throw LocalUpdateError.message("Не удалось прочитать номер сборки VUPIO.")
        }
        let hash = try LocalRelease.codeHash(of: app)
        let metadata = LocalRelease(build: build, codeHash: hash, signature: Data())
        let release = LocalRelease(build: build, codeHash: hash, signature: try key.signature(for: metadata.signedBytes))
        let fm = FileManager.default
        try fm.createDirectory(at: channel, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        if let last = try LocalRelease.verified(in: channel, publicKey: key.publicKey.rawRepresentation), last.build > build {
            throw LocalUpdateError.message("Номер сборки меньше уже опубликованного.")
        }
        let versionDir = channel.appendingPathComponent(String(build))
        let target = versionDir.appendingPathComponent("VUPIO.app")
        if fm.fileExists(atPath: versionDir.path) {
            guard try LocalRelease.codeHash(of: target) == hash else {
                throw LocalUpdateError.message("Этот номер уже занят другой сборкой. Увеличьте CFBundleVersion.")
            }
        } else {
            let temp = channel.appendingPathComponent(".release-" + UUID().uuidString)
            try fm.createDirectory(at: temp, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
            defer { try? fm.removeItem(at: temp) }
            let copy = temp.appendingPathComponent("VUPIO.app")
            try LocalUpdate.run("/bin/cp", ["-cRP", app.path, copy.path])
            guard try LocalRelease.codeHash(of: copy) == hash else {
                throw LocalUpdateError.message("Скопированная сборка не прошла проверку подписи.")
            }
            try fm.moveItem(at: temp, to: versionDir)
        }
        try JSONEncoder().encode(release).write(to: channel.appendingPathComponent("latest.json"), options: .atomic)
        print("VUPIO local build \(build): \(channel.path)")
    }
}
