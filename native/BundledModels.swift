import Foundation
import CryptoKit

enum BundledModels {
    static func prepare(resources: URL, data: URL) throws -> URL {
        let manager = FileManager.default
        let manifest = resources.appendingPathComponent("model-components.json")
        let embedded = resources.appendingPathComponent("Models")
        let bytes = try Data(contentsOf: manager.fileExists(atPath: manifest.path) ? manifest : embedded.appendingPathComponent("components.json"))
        let hash = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
        let parent = data.appendingPathComponent("bundled-models", isDirectory: true)
        let destination = parent.appendingPathComponent(hash, isDirectory: true)
        if (try? Data(contentsOf: destination.appendingPathComponent("components.json"))) == bytes {
            return destination
        }
        guard manager.fileExists(atPath: embedded.path) else {
            throw LocalUpdateError.message("The bundled AI models are missing. Open the full VUPIO installer to restore them.")
        }
        try manager.createDirectory(at: parent, withIntermediateDirectories: true)
        let staged = parent.appendingPathComponent(".prepare-" + UUID().uuidString)
        defer { try? manager.removeItem(at: staged) }
        try LocalUpdate.run("/bin/cp", ["-cRP", embedded.path, staged.path])
        guard let components = try JSONSerialization.jsonObject(with: bytes) as? [[String: Any]] else {
            throw LocalUpdateError.message("Invalid AI model manifest.")
        }
        for component in components {
            guard let name = component["filename"] as? String, name == URL(fileURLWithPath: name).lastPathComponent,
                  let expected = component["sha256"] as? String else {
                throw LocalUpdateError.message("Invalid AI model component.")
            }
            let handle = try FileHandle(forReadingFrom: staged.appendingPathComponent(name))
            var digest = SHA256()
            do {
                while let chunk = try handle.read(upToCount: 1024 * 1024), !chunk.isEmpty { digest.update(data: chunk) }
                try handle.close()
            } catch { try? handle.close(); throw error }
            guard digest.finalize().map({ String(format: "%02x", $0) }).joined() == expected else {
                throw LocalUpdateError.message("AI model verification failed. Restore the full VUPIO build.")
            }
        }
        // A concurrent launch may have finished the same immutable model set.
        if manager.fileExists(atPath: destination.path) {
            guard (try? Data(contentsOf: destination.appendingPathComponent("components.json"))) == bytes else {
                throw LocalUpdateError.message("AI model storage is incomplete. Restore the full VUPIO build.")
            }
        } else {
            do { try manager.moveItem(at: staged, to: destination) }
            catch {
                guard (try? Data(contentsOf: destination.appendingPathComponent("components.json"))) == bytes else { throw error }
            }
        }
        return destination
    }
}
