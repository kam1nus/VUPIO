import Foundation
import Security

func accountCredentialCommand() {
    var response: [String: Any] = [:]
    do {
        let data = FileHandle.standardInput.readDataToEndOfFile()
        guard data.count < 4096,
              let command = try JSONSerialization.jsonObject(with: data) as? [String: String],
              let scope = command["scope"], scope.range(of: "^[a-f0-9]{24}$", options: .regularExpression) != nil
        else { throw NSError(domain: "Account", code: 1) }
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: "local.mimic.soundboard.account", kSecAttrAccount as String: scope]
        switch command["action"] {
        case "read":
            var read = query
            read[kSecReturnData as String] = true
            read[kSecMatchLimit as String] = kSecMatchLimitOne
            var item: CFTypeRef?
            let status = SecItemCopyMatching(read as CFDictionary, &item)
            guard status == errSecSuccess || status == errSecItemNotFound else { throw NSError(domain: "Account", code: Int(status)) }
            response["token"] = (item as? Data).flatMap { String(data: $0, encoding: .utf8) } ?? ""
        case "write":
            guard let token = command["token"], token.range(of: "^[a-f0-9]{64}$", options: .regularExpression) != nil
            else { throw NSError(domain: "Account", code: 2) }
            let attributes: [String: Any] = [kSecValueData as String: Data(token.utf8)]
            var status = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
            if status == errSecItemNotFound {
                var item = query
                item[kSecValueData as String] = Data(token.utf8)
                item[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
                status = SecItemAdd(item as CFDictionary, nil)
            }
            guard status == errSecSuccess else { throw NSError(domain: "Account", code: Int(status)) }
        case "delete":
            let status = SecItemDelete(query as CFDictionary)
            guard status == errSecSuccess || status == errSecItemNotFound else { throw NSError(domain: "Account", code: Int(status)) }
        default: throw NSError(domain: "Account", code: 3)
        }
    } catch { response = ["error": "Credential store unavailable"] }
    if let data = try? JSONSerialization.data(withJSONObject: response), let text = String(data: data, encoding: .utf8) { print(text) }
}
