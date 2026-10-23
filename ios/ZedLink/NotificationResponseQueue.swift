import Foundation

/// Routing metadata only. Claim before dispatch so a crash cannot replay an approval.
@MainActor final class NotificationResponseQueue {
    struct Response: Codable {
        let id: String
        let data: [String: String]
        let action: String
        let created: TimeInterval
    }
    private struct State: Codable {
        var pending: [Response] = []
        var consumed: [String: TimeInterval] = [:]
    }
    private let defaults: UserDefaults
    private let key: String
    private let now: () -> TimeInterval
    private var state: State
    private let lifetime: TimeInterval = 86400

    init(defaults: UserDefaults = .standard, key: String = "zedlink.notificationResponses", now: @escaping () -> TimeInterval = { Date().timeIntervalSince1970 }) {
        self.defaults = defaults; self.key = key; self.now = now
        state = defaults.data(forKey: key).flatMap { try? JSONDecoder().decode(State.self, from: $0) } ?? State()
        prune()
    }
    func enqueue(id: String, data: [String: String], action: String) {
        prune()
        let reviewOnly = ["agent_error", "turn_status", "compaction", "input_needed"].contains(data["type"] ?? "")
        let required = ["gateway", "target", "instance", "epoch", "thread"] + (reviewOnly ? [] : ["turn", "approval", "child"])
        guard id.utf8.count <= 2048, required.allSatisfy({ data[$0] != nil }),
              data.count <= 12, data.values.allSatisfy({ $0.utf8.count <= 2048 }),
              state.consumed[id] == nil, !state.pending.contains(where: { $0.id == id }) else { return }
        let created = data["created"].flatMap { TimeInterval($0) } ?? now()
        guard created.isFinite, now() - created >= 0, now() - created <= lifetime else { return }
        // Older notifications lack a creation timestamp and can only navigate to review.
        let safeAction = !reviewOnly && data["created"] != nil && ["approve", "deny"].contains(action) ? action : "review"
        state.pending.append(Response(id: id, data: data, action: safeAction, created: created))
        if state.pending.count > 16 { state.pending.removeFirst(state.pending.count - 16) }
        save()
    }
    func claim() -> Response? {
        prune()
        guard !state.pending.isEmpty else { return nil }
        let response = state.pending.removeFirst()
        state.consumed[response.id] = now()
        if state.consumed.count > 96, let oldest = state.consumed.min(by: { $0.value < $1.value })?.key {
            state.consumed.removeValue(forKey: oldest)
        }
        save()
        return response
    }
    func clear() { state = State(); save() }
    private func prune() {
        let time = now()
        state.pending.removeAll { time - $0.created < 0 || time - $0.created > lifetime }
        state.consumed = state.consumed.filter { time - $0.value >= 0 && time - $0.value <= lifetime }
        save()
    }
    private func save() {
        if let encoded = try? JSONEncoder().encode(state) { defaults.set(encoded, forKey: key) }
    }
}
