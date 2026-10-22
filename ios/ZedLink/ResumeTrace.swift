import Foundation
import os

/// Timing only. Never attach gateway IDs, thread IDs, credentials, or transcript text.
@MainActor final class ResumeTrace {
    private static let signposter = OSSignposter(subsystem: "dev.zedlink.app", category: .pointsOfInterest)
    private let started = ProcessInfo.processInfo.systemUptime
    private let interval: OSSignpostIntervalState
    private var ended = false
    private var milestones: [String: Int] = [:]
    private static let historyKey = "zedlink.resume.timings.v1"

    static var recent: [[String: Int]] {
        UserDefaults.standard.array(forKey: historyKey) as? [[String: Int]] ?? []
    }

    init() {
        interval = Self.signposter.beginInterval("Gateway resume")
    }

    func mark(_ name: StaticString) {
        let elapsed = Int((ProcessInfo.processInfo.systemUptime - started) * 1_000)
        milestones[String(describing: name)] = elapsed
        Self.signposter.emitEvent(name, id: .exclusive, "elapsed_ms=\(elapsed)")
    }

    func finish() {
        guard !ended else { return }
        ended = true
        milestones["Resume ended"] = Int((ProcessInfo.processInfo.systemUptime - started) * 1_000)
        if !milestones.isEmpty {
            var history = Self.recent
            history.insert(milestones, at: 0)
            UserDefaults.standard.set(Array(history.prefix(20)), forKey: Self.historyKey)
        }
        Self.signposter.endInterval("Gateway resume", interval)
    }

    static func streamReady() { signposter.emitEvent("Event stream ready", id: .exclusive, "") }
}
