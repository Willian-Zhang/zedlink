import Foundation
import Combine

@MainActor final class SessionManager: ObservableObject {
    @Published private(set) var profile: ConnectionProfile?
    @Published private(set) var targets: [ZedTarget] = []
    @Published private(set) var targetID: String?
    @Published private(set) var state: LinkState = .offline
    @Published private(set) var threads: [NativeThread] = []
    @Published private(set) var snapshot: ThreadSnapshot?
    @Published private(set) var instanceID: String?
    @Published private(set) var epoch: String?
    @Published private(set) var capabilities: Set<String> = []
    @Published private(set) var commands: [NativeCommand] = []
    @Published private(set) var createAgents: [AgentOption] = []
    @Published private(set) var creatingThread = false
    @Published private(set) var selectedThreadID: String?
    @Published private(set) var delivery = ""
    @Published private(set) var issue = ""
    @Published private(set) var pending: PendingSend?
    @Published var draft = "" {
        didSet {
            guard let profile, let selectedThreadID else { return }
            let key = draftKey(profileID: profile.id, targetID: targetID, threadID: selectedThreadID)
            if draft.isEmpty { UserDefaults.standard.removeObject(forKey: key) }
            else { UserDefaults.standard.set(draft, forKey: key) }
        }
    }

    private var client: GatewayClient?
    private var pollTask: Task<Void, Never>?
    private var generation = UUID()
    private let threadExposureIssue = "The selected thread is no longer exposed in desktop Zed."

    var canSend: Bool { state == .live && selectedThreadID != nil && pending == nil }
    var canCancel: Bool {
        state == .live && capabilities.contains("thread.cancel") && snapshot?.threadID == selectedThreadID
            && snapshot?.currentTurnID != nil
    }

    func disconnect() {
        generation = UUID()
        pollTask?.cancel()
        pollTask = nil
        client = nil
        profile = nil
        targets = []
        targetID = nil
        state = .offline
        threads = []
        snapshot = nil
        selectedThreadID = nil
        instanceID = nil
        epoch = nil
        capabilities = []
        commands = []
        createAgents = []
        creatingThread = false
        pending = nil
        delivery = ""
        issue = ""
    }

    func connect(_ nextProfile: ConnectionProfile, target requestedTargetID: String? = nil) async {
        let sameProfile = profile?.id == nextProfile.id
        let previousThread = sameProfile ? selectedThreadID : nil
        let previousPending = sameProfile ? pending : nil
        let previousTarget = sameProfile ? targetID : nil
        disconnect()
        if !sameProfile { draft = "" }
        let current = generation
        profile = nextProfile
        state = .connecting
        do {
            guard let token = await CredentialVault.shared.read(nextProfile) else {
                throw GatewayFailure.native("Pair this device first.")
            }
            let discoveryClient = GatewayClient(profile: nextProfile, token: token)
            try await discoveryClient.verifyIdentity()
            let registry = try await discoveryClient.rpc("instance.list")
            guard let rows = registry["targets"] as? [[String: Any]], !rows.isEmpty else {
                throw GatewayFailure.native("This gateway has no configured Zed targets.")
            }
            targets = rows.compactMap { row in
                guard let id = row["target_id"] as? String, let label = row["label"] as? String else { return nil }
                return ZedTarget(id: id, label: label, available: row["available"] as? Bool ?? false)
            }
            let savedTarget = UserDefaults.standard.string(forKey: targetKey(nextProfile))
            let preferredTarget = requestedTargetID ?? previousTarget ?? savedTarget
                ?? registry["default_target_id"] as? String
            guard let selectedTarget = targets.first(where: { $0.id == preferredTarget })
                    ?? targets.first(where: { $0.available }) ?? targets.first else {
                throw GatewayFailure.native("This gateway has no configured Zed targets.")
            }
            targetID = selectedTarget.id
            UserDefaults.standard.set(selectedTarget.id, forKey: targetKey(nextProfile))
            let nextClient = GatewayClient(profile: nextProfile, token: token, targetID: selectedTarget.id)
            let info = try await nextClient.rpc("instance.info")
            guard current == generation,
                  let instance = info["instance_id"] as? String,
                  let nextEpoch = info["epoch"] as? String else { return }
            client = nextClient
            instanceID = instance
            epoch = nextEpoch
            capabilities = Set(info["capabilities"] as? [String] ?? [])
            restorePending(for: nextProfile)
            if let previousPending, pending?.id == previousPending.id {
                pending?.text = previousPending.text
            }
            try await loadThreads()
            if let previousThread, threads.contains(where: { $0.id == previousThread }) {
                selectedThreadID = previousThread
                try await loadSnapshot(previousThread)
                try await loadCommands(previousThread)
            }
            guard current == generation else { return }
            state = .live
            issue = ""
            pollTask = Task { [weak self] in
                guard let self else { return }
                await self.pollLoop(current)
            }
        } catch {
            guard current == generation else { return }
            state = .offline
            issue = error.localizedDescription
        }
    }

    func refresh() async {
        guard let profile else { return }
        await connect(profile)
    }

    func selectTarget(_ id: String) async {
        guard let profile, targets.contains(where: { $0.id == id && $0.available }) else { return }
        await connect(profile, target: id)
    }

    func loadCreateOptions() async {
        guard capabilities.contains("thread.create.options"), let client, let instanceID, let epoch else {
            createAgents = [AgentOption(id: "zed-agent", name: "Zed Agent", kind: "zed")]
            return
        }
        do {
            let result = try await client.rpc("thread.create.options", params: [
                "instance_id": instanceID,
                "epoch": epoch,
            ])
            try checkIdentity(result)
            createAgents = (result["agents"] as? [[String: Any]] ?? []).compactMap { row in
                guard let id = row["id"] as? String, let name = row["name"] as? String else { return nil }
                return AgentOption(id: id, name: name, kind: row["kind"] as? String ?? "external_acp")
            }
        } catch { issue = error.localizedDescription }
    }

    func createThread(title: String, agentID: String) async -> Bool {
        guard capabilities.contains("thread.create"), let client, let instanceID, let epoch,
              !creatingThread else { return false }
        creatingThread = true
        defer { creatingThread = false }
        let requestID = UUID().uuidString
        do {
            for _ in 0..<40 {
                let result = try await client.rpc("thread.create", params: [
                    "instance_id": instanceID,
                    "epoch": epoch,
                    "title": title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                        ? NSNull() : title.trimmingCharacters(in: .whitespacesAndNewlines),
                    "agent_id": agentID,
                ], requestID: requestID)
                if result["outcome"] as? String == "ready", let id = result["thread_id"] as? String {
                    try await loadThreads()
                    await select(id)
                    return true
                }
                guard result["outcome"] as? String == "creating" else {
                    throw GatewayFailure.invalidResponse
                }
                try await Task.sleep(for: .milliseconds(250))
            }
            throw GatewayFailure.native("Zed is still creating the session. Refresh to check its status.")
        } catch {
            issue = error.localizedDescription
            return false
        }
    }

    private func loadThreads() async throws {
        guard let client else { return }
        let result = try await client.rpc("thread.list")
        try checkIdentity(result)
        guard let rows = result["threads"] as? [[String: Any]] else { throw GatewayFailure.invalidResponse }
        threads = rows.compactMap { row in
            guard let id = row["thread_id"] as? String else { return nil }
            return NativeThread(id: id, title: row["title"] as? String ?? "Untitled Agent thread",
                                status: row["status"] as? String ?? "Unknown",
                                currentTurnID: row["current_turn_id"] as? Int)
        }
        if let selectedThreadID, !threads.contains(where: { $0.id == selectedThreadID }) {
            self.selectedThreadID = nil
            snapshot = nil
            commands = []
            issue = threadExposureIssue
        }
    }

    func select(_ id: String) async {
        guard threads.contains(where: { $0.id == id }) else { return }
        selectedThreadID = id
        snapshot = nil
        commands = []
        if let profile {
            draft = UserDefaults.standard.string(forKey: draftKey(profileID: profile.id, targetID: targetID, threadID: id)) ?? ""
        }
        do {
            try await loadSnapshot(id)
            try await loadCommands(id)
            issue = ""
        }
        catch { issue = error.localizedDescription; state = .stale }
    }

    func renameSelectedThread(to proposedTitle: String) async -> Bool {
        let title = proposedTitle.trimmingCharacters(in: .whitespacesAndNewlines)
        guard capabilities.contains("thread.rename"), !title.isEmpty,
              let client, let instanceID, let epoch, let threadID = selectedThreadID else { return false }
        do {
            let result = try await client.rpc("thread.rename", params: [
                "instance_id": instanceID, "epoch": epoch,
                "thread_id": threadID, "title": title,
            ])
            guard result["outcome"] as? String == "requested" else { throw GatewayFailure.invalidResponse }
            try await loadThreads()
            delivery = "Session renamed in desktop Zed."
            return true
        } catch {
            issue = error.localizedDescription
            return false
        }
    }

    func unexposeSelectedThread() async -> Bool {
        guard capabilities.contains("thread.unexpose"), let client, let instanceID, let epoch,
              let threadID = selectedThreadID else { return false }
        do {
            let result = try await client.rpc("thread.unexpose", params: [
                "instance_id": instanceID, "epoch": epoch, "thread_id": threadID,
            ])
            guard result["outcome"] as? String == "unexposed" else { throw GatewayFailure.invalidResponse }
            selectedThreadID = nil
            snapshot = nil
            commands = []
            try await loadThreads()
            delivery = "Remote exposure stopped. The Agent thread remains open in desktop Zed."
            issue = ""
            return true
        } catch {
            issue = error.localizedDescription
            return false
        }
    }

    private func loadSnapshot(_ id: String) async throws {
        guard let client else { return }
        var params: [String: Any] = ["thread_id": id]
        if snapshot?.threadID == id { params["tail_entry_count"] = 16 }
        let result = try await client.rpc("thread.snapshot", params: params)
        try checkIdentity(result)
        guard result["thread_id"] as? String == id,
              let entries = result["entries_markdown"] as? [String],
              let sequence = result["last_sequence"] as? Int else { throw GatewayFailure.invalidResponse }
        guard selectedThreadID == id else { return }
        let pageStart = result["entry_start_index"] as? Int ?? 0
        let pageEnd = result["entry_end_index"] as? Int ?? pageStart + entries.count
        let totalEntries = result["total_entries"] as? Int ?? pageEnd
        guard pageStart >= 0, pageEnd == pageStart + entries.count, totalEntries >= pageEnd else {
            throw GatewayFailure.invalidResponse
        }
        var mergedEntries = entries
        var mergedStart = pageStart
        if let old = snapshot, old.threadID == id,
           pageStart >= old.entryStartIndex,
           pageStart <= old.entryStartIndex + old.entries.count {
            mergedEntries = Array(old.entries.prefix(pageStart - old.entryStartIndex)) + entries
            mergedStart = old.entryStartIndex
        }
        let approvals = (result["pending_approvals"] as? [[String: Any]] ?? []).compactMap { row -> NativeApproval? in
            guard let approvalID = row["approval_id"] as? String else { return nil }
            let permissionOptions = row["permission_options"] as? [String: Any]
            let decisions = (permissionOptions?["decisions"] as? [[String: Any]] ?? []).compactMap { decision -> NativeApprovalDecision? in
                guard let optionID = decision["option_id"] as? String else { return nil }
                return NativeApprovalDecision(
                    optionID: optionID,
                    label: decision["label"] as? String ?? "Choose",
                    optionKind: decision["option_kind"] as? String ?? "unknown",
                    choiceIndex: decision["choice_index"] as? Int,
                    selectedPatternIndices: decision["selected_pattern_indices"] as? [Int] ?? [],
                    action: decision["action"] as? String
                )
            }
            return NativeApproval(id: approvalID,
                                  turnID: row["turn_id"] as? Int,
                                  toolName: row["tool_name"] as? String ?? "Zed tool",
                                  display: row["display"] as? String ?? "Permission requested",
                                  rawInput: Self.jsonText(row["raw_input"]),
                                  detailsTruncated: row["details_truncated"] as? Bool ?? true,
                                  canApproveOnce: row["can_approve_once"] as? Bool ?? false,
                                  canDenyOnce: row["can_deny_once"] as? Bool ?? false,
                                  subagentID: row["subagent_id"] as? String,
                                  authorizationKind: row["authorization_kind"] as? String ?? "permission_grant",
                                  decisions: decisions)
        }
        snapshot = ThreadSnapshot(threadID: id,
                                  title: result["title"] as? String ?? "Untitled Agent thread",
                                  status: result["status"] as? String ?? "Unknown",
                                  currentTurnID: result["current_turn_id"] as? Int,
                                  instanceID: instanceID ?? "", epoch: epoch ?? "",
                                  lastSequence: sequence, entries: mergedEntries,
                                  entryStartIndex: mergedStart, totalEntries: totalEntries,
                                  hasOlderEntries: mergedStart > 0,
                                  activityEntries: result["activity_entries_markdown"] as? [String] ?? entries,
                                  truncated: result["truncated"] as? Bool ?? false,
                                  activityTruncated: result["activity_truncated"] as? Bool ?? false,
                                  pendingApprovals: approvals)
    }

    func loadEarlierHistory() async {
        guard capabilities.contains("thread.history"), let client, let old = snapshot,
              old.threadID == selectedThreadID, old.entryStartIndex > 0 else { return }
        do {
            let result = try await client.rpc("thread.history", params: [
                "thread_id": old.threadID, "before_entry_index": old.entryStartIndex
            ])
            try checkIdentity(result)
            guard selectedThreadID == old.threadID, let current = snapshot,
                  current.threadID == old.threadID,
                  current.entryStartIndex == old.entryStartIndex,
                  result["thread_id"] as? String == old.threadID,
                  result["entry_end_index"] as? Int == old.entryStartIndex,
                  let start = result["entry_start_index"] as? Int,
                  let entries = result["entries_markdown"] as? [String] else {
                throw GatewayFailure.invalidResponse
            }
            snapshot = ThreadSnapshot(threadID: current.threadID, title: current.title, status: current.status,
                                      currentTurnID: current.currentTurnID,
                                      instanceID: current.instanceID, epoch: current.epoch,
                                      lastSequence: current.lastSequence,
                                      entries: entries + current.entries,
                                      entryStartIndex: start,
                                      totalEntries: max(current.totalEntries, result["total_entries"] as? Int ?? 0),
                                      hasOlderEntries: start > 0,
                                      activityEntries: current.activityEntries,
                                      truncated: start > 0, activityTruncated: current.activityTruncated,
                                      pendingApprovals: current.pendingApprovals)
        } catch {
            issue = error.localizedDescription
        }
    }

    private func loadCommands(_ id: String) async throws {
        guard capabilities.contains("thread.commands"), let client else { return }
        let result = try await client.rpc("thread.commands", params: [
            "instance_id": instanceID ?? "", "epoch": epoch ?? "", "thread_id": id
        ])
        guard selectedThreadID == id, result["thread_id"] as? String == id,
              let rows = result["commands"] as? [[String: Any]] else { return }
        commands = rows.compactMap { row in
            guard let name = row["name"] as? String else { return nil }
            return NativeCommand(name: name,
                                 description: row["description"] as? String ?? "Zed Agent command",
                                 category: row["category"] as? String ?? "agent",
                                 requiresArgument: row["requires_argument"] as? Bool ?? false)
        }.sorted { $0.name.localizedStandardCompare($1.name) == .orderedAscending }
    }

    private func checkIdentity(_ result: [String: Any]) throws {
        guard result["instance_id"] as? String == instanceID,
              result["epoch"] as? String == epoch else { throw GatewayFailure.native("Zed restarted. Reconnect before sending.") }
    }

    private func pollLoop(_ current: UUID) async {
        while !Task.isCancelled && current == generation {
            do {
                if let id = selectedThreadID, let client {
                    let result = try await client.rpc("thread.events", params: [
                        "thread_id": id, "after_sequence": snapshot?.lastSequence ?? 0
                    ])
                    try checkIdentity(result)
                    guard result["thread_id"] as? String == id else { throw GatewayFailure.invalidResponse }
                    if let events = result["events"] as? [[String: Any]], !events.isEmpty {
                        if events.contains(where: { $0["kind"] as? String == "entry.removed" }) {
                            snapshot = nil
                        }
                        try await loadSnapshot(id)
                    } else if snapshot?.isBusy == true {
                        try await loadSnapshot(id)
                    } else if let sequence = result["last_sequence"] as? Int,
                              var old = snapshot, sequence >= old.lastSequence {
                        old = ThreadSnapshot(threadID: old.threadID, title: old.title, status: old.status,
                                             currentTurnID: old.currentTurnID,
                                             instanceID: old.instanceID, epoch: old.epoch,
                                             lastSequence: sequence, entries: old.entries,
                                             entryStartIndex: old.entryStartIndex,
                                             totalEntries: old.totalEntries,
                                             hasOlderEntries: old.hasOlderEntries,
                                             activityEntries: old.activityEntries,
                                             truncated: old.truncated, activityTruncated: old.activityTruncated,
                                             pendingApprovals: old.pendingApprovals)
                        snapshot = old
                    }
                } else {
                    try await loadThreads()
                }
                if pending != nil { await reconcilePending() }
                if current == generation {
                    state = .live
                    if issue != threadExposureIssue { issue = "" }
                }
            } catch {
                if case GatewayFailure.native("RESYNC_REQUIRED") = error, let id = selectedThreadID {
                    snapshot = nil
                    do { try await loadSnapshot(id); state = .live }
                    catch { state = .stale; issue = error.localizedDescription }
                } else if case GatewayFailure.native("THREAD_NOT_EXPOSED") = error {
                    guard current == generation else { break }
                    selectedThreadID = nil
                    snapshot = nil
                    commands = []
                    do {
                        try await loadThreads()
                        guard current == generation else { break }
                        state = .live
                        issue = threadExposureIssue
                    } catch {
                        guard current == generation else { break }
                        state = .reconnecting
                        issue = error.localizedDescription
                    }
                } else if current == generation {
                    state = .reconnecting
                    issue = error.localizedDescription
                }
            }
            do { try await Task.sleep(for: .seconds(state == .live ? 1 : 3)) }
            catch { break }
        }
    }

    func cancelCurrentTurn() async {
        guard canCancel, let client, let instanceID, let epoch,
              let threadID = selectedThreadID, let turnID = snapshot?.currentTurnID else { return }
        do {
            let result = try await client.rpc("thread.cancel", params: [
                "instance_id": instanceID, "epoch": epoch,
                "thread_id": threadID, "turn_id": turnID
            ])
            guard result["outcome"] as? String == "requested",
                  result["turn_id"] as? Int == turnID else { throw GatewayFailure.invalidResponse }
            delivery = "Stop requested for this desktop Zed turn. Completed tool effects remain."
            try await loadSnapshot(threadID)
        } catch {
            issue = error.localizedDescription
            try? await loadSnapshot(threadID)
        }
    }

    func respond(to approval: NativeApproval, with decision: NativeApprovalDecision) async {
        guard capabilities.contains("approval.respond"), let client, let instanceID, let epoch,
              let threadID = selectedThreadID, let turnID = approval.turnID else { return }
        var params: [String: Any] = [
            "instance_id": instanceID, "epoch": epoch, "thread_id": threadID,
            "turn_id": turnID, "approval_id": approval.id, "option_id": decision.optionID
        ]
        if let choiceIndex = decision.choiceIndex { params["choice_index"] = choiceIndex }
        if !decision.selectedPatternIndices.isEmpty {
            params["selected_pattern_indices"] = decision.selectedPatternIndices
        }
        if let subagentID = approval.subagentID { params["subagent_id"] = subagentID }
        do {
            let result = try await client.rpc("approval.respond", params: params)
            guard result["outcome"] as? String == "resolved" else { throw GatewayFailure.invalidResponse }
            delivery = "Sent “\(decision.displayLabel)” to desktop Zed."
            try await loadSnapshot(threadID)
        } catch {
            issue = error.localizedDescription
            try? await loadSnapshot(threadID)
        }
    }

    func send() async {
        guard canSend, let client, let profile, let instanceID, let epoch,
              let threadID = selectedThreadID else { return }
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        pending = PendingSend(id: UUID().uuidString, instanceID: instanceID,
                              epoch: epoch, threadID: threadID, text: text)
        persistPending(for: profile)
        delivery = "Sending to native Zed…"
        await retryPending()
    }

    func retryPending() async {
        guard let client, let pending, let text = pending.text,
              pending.instanceID == instanceID, pending.epoch == epoch else { return }
        do {
            let result = try await client.rpc("thread.send", params: [
                "instance_id": pending.instanceID, "epoch": pending.epoch,
                "thread_id": pending.threadID, "text": text
            ], requestID: pending.id)
            let outcome = result["outcome"] as? String ?? "received"
            draft = ""
            settlePending()
            delivery = outcome == "queued"
                ? "Queued in desktop Zed. Native execution is being observed."
                : "Received by desktop Zed. Watching the native conversation for progress."
            try await loadSnapshot(pending.threadID)
        } catch {
            delivery = "Delivery unknown: \(error.localizedDescription) No new request ID was sent."
        }
    }

    func reconcilePending() async {
        guard let client, let pending else { return }
        guard pending.instanceID == instanceID, pending.epoch == epoch else {
            delivery = "Zed restarted. Delivery remains unknown; inspect the desktop thread."
            return
        }
        do {
            let result = try await client.rpc("request.status", params: [
                "instance_id": pending.instanceID, "epoch": pending.epoch,
                "original_request_id": pending.id
            ])
            if result["known"] as? Bool == true {
                delivery = "Zed knows this request (\(result["outcome"] as? String ?? "unknown")); native acceptance remains provisional."
            } else {
                delivery = "Request status is unknown. It was not resent."
            }
        } catch { delivery = "Request status unavailable: \(error.localizedDescription)" }
    }

    func clearPending() {
        pending = nil
        if let profile { UserDefaults.standard.removeObject(forKey: pendingKey(profile)) }
        delivery = "Uncertain delivery cleared locally. Check desktop Zed before sending similar text."
    }

    func insertCommand(_ command: NativeCommand) {
        draft = "/\(command.name)\(command.requiresArgument ? " " : "")"
    }

    func prepareSubagentTask() {
        draft = "Use the native spawn_agent tool to delegate the following task to a child Zed Agent. Keep the child scoped to this project and return its result in this conversation:\n\nTask: "
    }

    private func settlePending() {
        pending = nil
        if let profile { UserDefaults.standard.removeObject(forKey: pendingKey(profile)) }
    }

    private static func jsonText(_ value: Any?) -> String? {
        guard let value, !(value is NSNull) else { return nil }
        if let value = value as? String { return value }
        guard JSONSerialization.isValidJSONObject(value),
              let data = try? JSONSerialization.data(withJSONObject: value, options: [.prettyPrinted, .sortedKeys]) else {
            return String(describing: value)
        }
        return String(data: data, encoding: .utf8)
    }

    private func targetKey(_ profile: ConnectionProfile) -> String { "zedlink.target.\(profile.id)" }

    private func pendingKey(_ profile: ConnectionProfile) -> String {
        "zedlink.pending.\(profile.id).\(targetID ?? "default")"
    }

    private func draftKey(profileID: UUID, targetID: String?, threadID: String) -> String {
        "zedlink.draft.\(profileID.uuidString).\(targetID ?? "default").\(threadID)"
    }

    private func persistPending(for profile: ConnectionProfile) {
        if let pending, let data = try? JSONEncoder().encode(pending) {
            UserDefaults.standard.set(data, forKey: pendingKey(profile))
        }
    }

    private func restorePending(for profile: ConnectionProfile) {
        if let data = UserDefaults.standard.data(forKey: pendingKey(profile)) {
            pending = try? JSONDecoder().decode(PendingSend.self, from: data)
            if pending != nil { delivery = "Previous send has uncertain delivery. Check its status before another send." }
        }
    }
}
