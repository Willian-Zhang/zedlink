import Foundation
import CryptoKit

/// Keeps replayed native stop events from producing another device alert.
@MainActor final class TurnNotificationReceipts {
    private let defaults: UserDefaults
    private let key: String
    private let now: () -> TimeInterval
    private var seen: [String: TimeInterval]
    private let lifetime: TimeInterval = 7 * 86400

    init(defaults: UserDefaults = .standard, key: String = "zedlink.turnNotificationReceipts",
         now: @escaping () -> TimeInterval = { Date().timeIntervalSince1970 }) {
        self.defaults = defaults; self.key = key; self.now = now
        seen = defaults.dictionary(forKey: key) as? [String: TimeInterval] ?? [:]
    }

    func claim(scope: String, sequence: Int, reason: String) -> Bool {
        guard sequence > 0, ["completed", "cancelled", "max_turn_requests"].contains(reason) else { return false }
        return claim(scope: scope, token: "turn:\(sequence)")
    }

    func claim(scope: String, inputID: String) -> Bool {
        guard !inputID.isEmpty, inputID.utf8.count <= 256 else { return false }
        return claim(scope: scope, token: "input:\(inputID)")
    }

    private func claim(scope: String, token: String) -> Bool {
        let digest = SHA256.hash(data: Data("\(scope):\(token)".utf8))
            .map { String(format: "%02x", $0) }.joined()
        let time = now()
        seen = seen.filter { time - $0.value >= 0 && time - $0.value <= lifetime }
        guard seen[digest] == nil else { return false }
        seen[digest] = time
        if seen.count > 128 {
            for old in seen.sorted(by: { $0.value < $1.value }).prefix(seen.count - 128) {
                seen.removeValue(forKey: old.key)
            }
        }
        defaults.set(seen, forKey: key)
        return true
    }
}
