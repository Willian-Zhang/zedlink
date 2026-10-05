import Foundation
import Combine

@MainActor final class SessionManager: ObservableObject {
    @Published private(set) var profile: ConnectionProfile?
    @Published private(set) var state: LinkState = .offline
    @Published private(set) var threads: [NativeThread] = []
    @Published private(set) var snapshot: ThreadSnapshot?
    @Published private(set) var instanceID: String?
    @Published private(set) var epoch: String?
    @Published private(set) var selectedThreadID: String?
    @Published private(set) var delivery = ""
    @Published private(set) var issue = ""
    @Published private(set) var pending: PendingSend?
    @Published var draft = ""

    private var client: GatewayClient?
    private var pollTask: Task<Void, Never>?
    private var generation = UUID()

    var canSend: Bool { state == .live && selectedThreadID != nil && pending == nil }

    func disconnect() {
        generation = UUID()
        pollTask?.cancel()
        pollTask = nil
        client = nil
        profile = nil
        state = .offline
        threads = []
        snapshot = nil
        selectedThreadID = nil
        instanceID = nil
        epoch = nil
        pending = nil
        delivery = ""
        issue = ""
    }

    func connect(_ nextProfile: ConnectionProfile) async {
        let sameProfile = profile?.id == nextProfile.id
        let previousThread = sameProfile ? selectedThreadID : nil
        let previousPending = sameProfile ? pending : nil
        disconnect()
        if !sameProfile { draft = "" }
        let current = generation
        profile = nextProfile
        state = .connecting
        do {
            guard let token = await CredentialVault.shared.read(nextProfile.id) else {
                throw GatewayFailure.native("Pair this device first.")
            }
            let nextClient = GatewayClient(profile: nextProfile, token: token)
            try await nextClient.verifyIdentity()
            let info = try await nextClient.rpc("instance.info")
            guard current == generation,
                  let instance = info["instance_id"] as? String,
                  let nextEpoch = info["epoch"] as? String else { return }
            client = nextClient
            instanceID = instance
            epoch = nextEpoch
            restorePending(for: nextProfile)
            if let previousPending, pending?.id == previousPending.id {
                pending?.text = previousPending.text
            }
            try await loadThreads()
            if let previousThread, threads.contains(where: { $0.id == previousThread }) {
                selectedThreadID = previousThread
                try await loadSnapshot(previousThread)
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

    private func loadThreads() async throws {
        guard let client else { return }
        let result = try await client.rpc("thread.list")
        try checkIdentity(result)
        guard let rows = result["threads"] as? [[String: Any]] else { throw GatewayFailure.invalidResponse }
        threads = rows.compactMap { row in
            guard let id = row["thread_id"] as? String else { return nil }
            return NativeThread(id: id, title: row["title"] as? String ?? "Untitled Agent thread",
                                status: row["status"] as? String ?? "Unknown")
        }
        if let selectedThreadID, !threads.contains(where: { $0.id == selectedThreadID }) {
            self.selectedThreadID = nil
            snapshot = nil
            issue = "The selected thread is no longer exposed in desktop Zed."
        }
    }

    func select(_ id: String) async {
        guard threads.contains(where: { $0.id == id }), pending == nil else { return }
        selectedThreadID = id
        snapshot = nil
        do { try await loadSnapshot(id) }
        catch { issue = error.localizedDescription; state = .stale }
    }

    private func loadSnapshot(_ id: String) async throws {
        guard let client else { return }
        let result = try await client.rpc("thread.snapshot", params: ["thread_id": id])
        try checkIdentity(result)
        guard result["thread_id"] as? String == id,
              let entries = result["entries_markdown"] as? [String],
              let sequence = result["last_sequence"] as? Int else { throw GatewayFailure.invalidResponse }
        guard selectedThreadID == id else { return }
        snapshot = ThreadSnapshot(threadID: id,
                                  title: result["title"] as? String ?? "Untitled Agent thread",
                                  status: result["status"] as? String ?? "Unknown",
                                  instanceID: instanceID ?? "", epoch: epoch ?? "",
                                  lastSequence: sequence, entries: entries,
                                  truncated: result["truncated"] as? Bool ?? false,
                                  pendingApprovalCount: (result["pending_approvals"] as? [Any])?.count ?? 0)
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
                    if let events = result["events"] as? [Any], !events.isEmpty {
                        try await loadSnapshot(id)
                    } else if let sequence = result["last_sequence"] as? Int,
                              var old = snapshot, sequence >= old.lastSequence {
                        old = ThreadSnapshot(threadID: old.threadID, title: old.title, status: old.status,
                                             instanceID: old.instanceID, epoch: old.epoch,
                                             lastSequence: sequence, entries: old.entries,
                                             truncated: old.truncated, pendingApprovalCount: old.pendingApprovalCount)
                        snapshot = old
                    }
                } else {
                    try await loadThreads()
                }
                if pending != nil { await reconcilePending() }
                if current == generation { state = .live; issue = "" }
            } catch {
                if case GatewayFailure.native("RESYNC_REQUIRED") = error, let id = selectedThreadID {
                    do { try await loadSnapshot(id); state = .live }
                    catch { state = .stale; issue = error.localizedDescription }
                } else if current == generation {
                    state = .reconnecting
                    issue = error.localizedDescription
                }
            }
            do { try await Task.sleep(for: .seconds(state == .live ? 1 : 3)) }
            catch { break }
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
            if result["outcome"] as? String == "queued" {
                draft = ""
                clearPending()
                delivery = "Queued in desktop Zed. Native execution is still being observed."
            } else {
                delivery = "Delivery unknown. Check the request status or retry this exact request ID."
            }
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

    private func pendingKey(_ profile: ConnectionProfile) -> String { "zedlink.pending.\(profile.id)" }

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
