import Foundation
import Security
import Combine

actor CredentialVault {
    static let shared = CredentialVault()
    private let service = "dev.zedlink.gateway"

    func read(_ id: UUID) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: id.uuidString,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]
        var result: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    func write(_ token: String, for id: UUID) throws {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: id.uuidString
        ]
        SecItemDelete(query as CFDictionary)
        var add = query
        add[kSecValueData as String] = Data(token.utf8)
        add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        guard SecItemAdd(add as CFDictionary, nil) == errSecSuccess else {
            throw GatewayFailure.native("Could not save the device credential in Keychain.")
        }
    }

    func delete(_ id: UUID) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: id.uuidString
        ]
        SecItemDelete(query as CFDictionary)
    }
}

@MainActor final class ProfileStore: ObservableObject {
    @Published private(set) var profiles: [ConnectionProfile] = []
    private let key = "zedlink.profiles.v1"

    init() {
        if let data = UserDefaults.standard.data(forKey: key),
           let profiles = try? JSONDecoder().decode([ConnectionProfile].self, from: data) {
            self.profiles = profiles
        }
    }

    func save(_ profile: ConnectionProfile) {
        profiles.removeAll { $0.id == profile.id }
        profiles.append(profile)
        persist()
    }

    func remove(_ profile: ConnectionProfile) async {
        profiles.removeAll { $0.id == profile.id }
        persist()
        await CredentialVault.shared.delete(profile.id)
    }

    private func persist() {
        if let data = try? JSONEncoder().encode(profiles) {
            UserDefaults.standard.set(data, forKey: key)
        }
    }
}
