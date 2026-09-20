import Foundation
import Security

enum KeychainStore {
    private static let service = Bundle.main.bundleIdentifier ?? "com.joaopedro.kinttany"
    // Build 79: o bot precisa continuar lendo a sessão quando o iPhone estiver
    // bloqueado. AfterFirstUnlock mantém os itens restritos a este aparelho,
    // mas permite acesso em background após o primeiro desbloqueio do boot.
    private static let accessibility = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly

    static func set(_ key: String, _ value: String) {
        let data = Data(value.utf8)
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key
        ]

        SecItemDelete(query as CFDictionary)

        var item = query
        item[kSecValueData as String] = data
        item[kSecAttrAccessible as String] = accessibility
        SecItemAdd(item as CFDictionary, nil)
    }

    static func get(_ key: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]

        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        guard
            status == errSecSuccess,
            let data = result as? Data,
            let value = String(data: data, encoding: .utf8)
        else {
            return nil
        }

        // Migração transparente de itens gravados por builds anteriores com
        // WhenUnlockedThisDeviceOnly. Assim a sessão já existente passa a poder
        // ser reutilizada por reconexões em background sem exigir novo login.
        let updateQuery: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key
        ]
        let attributes: [String: Any] = [
            kSecAttrAccessible as String: accessibility
        ]
        SecItemUpdate(updateQuery as CFDictionary, attributes as CFDictionary)

        return value
    }

    static func delete(_ key: String) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key
        ]
        SecItemDelete(query as CFDictionary)
    }
}
