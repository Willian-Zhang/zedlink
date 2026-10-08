import Foundation
import Security
import Combine

actor CredentialVault {
    static let shared = CredentialVault()
    private let service = "dev.zedlink.gateway"

    private func read(account: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]
        var result: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    private func gatewayAccount(_ gatewayID: String) -> String {
        "gateway:\(gatewayID.lowercased())"
    }

    /// Credentials follow the gateway identity, rather than a route or profile UUID.
    /// The UUID fallback migrates credentials written by ZedLink 1.x in place.
    func read(_ profile: ConnectionProfile) -> String? {
        let account = gatewayAccount(profile.gatewayID)
        if let token = read(account: account) { return token }
        guard let legacy = read(account: profile.id.uuidString) else { return nil }
        do {
            try write(legacy, for: profile)
            delete(account: profile.id.uuidString)
        } catch { /* Keep the legacy entry if migration cannot be committed. */ }
        return legacy
    }

    func write(_ token: String, for profile: ConnectionProfile) throws {
        let account = gatewayAccount(profile.gatewayID)
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]
        SecItemDelete(query as CFDictionary)
        var add = query
        add[kSecValueData as String] = Data(token.utf8)
        add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        guard SecItemAdd(add as CFDictionary, nil) == errSecSuccess else {
            throw GatewayFailure.native("Could not save the device credential in Keychain.")
        }
    }

    private func delete(account: String) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]
        SecItemDelete(query as CFDictionary)
    }

    func delete(_ profile: ConnectionProfile) {
        delete(account: gatewayAccount(profile.gatewayID))
        delete(account: profile.id.uuidString)
    }
}

@MainActor final class ProfileStore: ObservableObject {
    @Published private(set) var profiles: [ConnectionProfile] = []
    private let key = "zedlink.profiles.v1"
    private let lastProfileKey = "zedlink.last-profile.v1"

    init() {
        if let data = UserDefaults.standard.data(forKey: key),
           let profiles = try? JSONDecoder().decode([ConnectionProfile].self, from: data) {
            self.profiles = profiles
        }
    }

    @discardableResult
    func save(_ profile: ConnectionProfile) -> ConnectionProfile {
        let saved = Self.profileForSave(profile, among: profiles)
        profiles.removeAll { $0.id == saved.id }
        profiles.append(saved)
        persist()
        return saved
    }

    static func profileForSave(_ profile: ConnectionProfile, among profiles: [ConnectionProfile]) -> ConnectionProfile {
        guard let existing = profiles.first(where: {
            $0.id == profile.id ||
                ($0.gatewayID.caseInsensitiveCompare(profile.gatewayID) == .orderedSame &&
                 normalizedEndpoint($0.endpoint) == normalizedEndpoint(profile.endpoint))
        }) else { return profile }
        var saved = profile
        saved.id = existing.id
        return saved
    }

    private static func normalizedEndpoint(_ value: String) -> String {
        value.trimmingCharacters(in: CharacterSet(charactersIn: "/")).lowercased()
    }

    var preferredProfile: ConnectionProfile? {
        if let value = UserDefaults.standard.string(forKey: lastProfileKey),
           let id = UUID(uuidString: value),
           let profile = profiles.first(where: { $0.id == id }) { return profile }
        return profiles.first
    }

    func markUsed(_ profile: ConnectionProfile) {
        UserDefaults.standard.set(profile.id.uuidString, forKey: lastProfileKey)
    }

    func remove(_ profile: ConnectionProfile) async {
        profiles.removeAll { $0.id == profile.id }
        if UserDefaults.standard.string(forKey: lastProfileKey) == profile.id.uuidString {
            UserDefaults.standard.removeObject(forKey: lastProfileKey)
        }
        persist()
        let stillUsesCredential = profiles.contains {
            $0.gatewayID.caseInsensitiveCompare(profile.gatewayID) == .orderedSame
        }
        if !stillUsesCredential { await CredentialVault.shared.delete(profile) }
    }

    private func persist() {
        if let data = try? JSONEncoder().encode(profiles) {
            UserDefaults.standard.set(data, forKey: key)
        }
    }
}
