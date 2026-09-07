import Foundation
import Security

enum KeychainStore {
    static func set(_ key: String, _ value: String) {
        let data = Data(value.utf8)
        let query: [String:Any] = [kSecClass as String:kSecClassGenericPassword, kSecAttrAccount as String:key]
        SecItemDelete(query as CFDictionary)
        var item = query; item[kSecValueData as String] = data
        SecItemAdd(item as CFDictionary, nil)
    }
    static func get(_ key: String) -> String? {
        let query: [String:Any] = [kSecClass as String:kSecClassGenericPassword, kSecAttrAccount as String:key, kSecReturnData as String:true, kSecMatchLimit as String:kSecMatchLimitOne]
        var result: CFTypeRef?; guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess, let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }
    static func delete(_ key: String) { SecItemDelete([kSecClass as String:kSecClassGenericPassword, kSecAttrAccount as String:key] as CFDictionary) }
}
