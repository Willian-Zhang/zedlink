import Foundation
import UserNotifications
import Combine

/// Local delivery while the client receives native snapshots. APNs is not configured.
@MainActor final class ApprovalNotifications: NSObject, ObservableObject, UNUserNotificationCenterDelegate {
    static let shared = ApprovalNotifications()
    var handler: (([String: String], String) async -> Void)? {
        didSet { Task { await drainResponses() } }
    }
    private let responses = NotificationResponseQueue()
    private var drainingResponses = false
    private func drainResponses() async {
        guard !drainingResponses, let handler else { return }
        drainingResponses = true
        defer { drainingResponses = false }
        while let response = responses.claim() { await handler(response.data, response.action) }
    }
    private var currentIDs: Set<String> = []
    private var scope = ""
    @Published private(set) var status = "Checking permission…"
    @Published private(set) var lastError = ""
    @Published private(set) var permitted = false
    @Published private(set) var blocked = false
    var enabled: Bool { UserDefaults.standard.bool(forKey: "zedlink.approvalNotifications") }

    func refreshStatus() async {
        let settings = await UNUserNotificationCenter.current().notificationSettings()
        permitted = [.authorized, .provisional, .ephemeral].contains(settings.authorizationStatus)
        blocked = settings.authorizationStatus == .denied
        switch settings.authorizationStatus {
        case .denied: status = "Blocked in iPhone Settings"
        case .notDetermined: status = "Permission not requested"
        case .authorized, .provisional, .ephemeral:
            status = enabled ? "Local approval alerts enabled" : "Local approval alerts disabled"
        @unknown default: status = "Permission status unavailable"
        }
    }

    func enable() async throws -> Bool {
        let center = UNUserNotificationCenter.current()
        lastError = ""
        do {
            let settings = await center.notificationSettings()
            if settings.authorizationStatus == .denied {
                throw GatewayFailure.native("Notifications are blocked. Open iPhone notification settings and allow alerts for ZedLink.")
            }
            let allowed = try await center.requestAuthorization(options: [.alert, .sound, .badge])
            UserDefaults.standard.set(allowed, forKey: "zedlink.approvalNotifications")
            configure()
            await refreshStatus()
            return allowed
        } catch {
            lastError = error.localizedDescription
            await refreshStatus()
            throw error
        }
    }

    func sendTest() async throws {
        let center = UNUserNotificationCenter.current()
        let settings = await center.notificationSettings()
        guard enabled, settings.authorizationStatus == .authorized || settings.authorizationStatus == .provisional || settings.authorizationStatus == .ephemeral else {
            throw GatewayFailure.native("Enable local approval alerts and allow notifications in iPhone Settings first.")
        }
        let content = UNMutableNotificationContent()
        content.title = "ZedLink"
        content.body = "Test notification. No Agent approval is requested."
        content.sound = .default
        try await center.add(UNNotificationRequest(identifier: "zedlink-test", content: content,
            trigger: UNTimeIntervalNotificationTrigger(timeInterval: 3, repeats: false)))
    }

    func disable() {
        UserDefaults.standard.set(false, forKey: "zedlink.approvalNotifications")
        status = blocked ? "Blocked in iPhone Settings" : "Local approval alerts disabled"
        responses.clear()
        clear()
    }

    func configure() {
        let center = UNUserNotificationCenter.current()
        center.delegate = self
        let review = UNNotificationAction(identifier: "review", title: "Review request", options: [.foreground, .authenticationRequired])
        let deny = UNNotificationAction(identifier: "deny", title: "Deny once", options: [.foreground, .authenticationRequired, .destructive])
        let approve = UNNotificationAction(identifier: "approve", title: "Approve once", options: [.foreground, .authenticationRequired])
        center.setNotificationCategories([
            UNNotificationCategory(identifier: "ZEDLINK_REVIEW", actions: [review], intentIdentifiers: []),
            // Keep the default action harmless on watch gestures; approval is never first.
            UNNotificationCategory(identifier: "ZEDLINK_PERMISSION", actions: [review, deny, approve], intentIdentifiers: [])
        ])
    }

    func clear() {
        let ids = Array(currentIDs)
        UNUserNotificationCenter.current().removePendingNotificationRequests(withIdentifiers: ids)
        UNUserNotificationCenter.current().removeDeliveredNotifications(withIdentifiers: ids)
        currentIDs = []; scope = ""
    }

    func update(gateway: String, target: String, instance: String, epoch: String, thread: String, approvals: [NativeApproval], allowActions: Bool) {
        guard enabled else { clear(); return }
        let nextScope = [gateway, target, instance, epoch, thread].joined(separator: ":")
        if nextScope != scope { clear(); scope = nextScope }
        let center = UNUserNotificationCenter.current()
        var nextIDs: Set<String> = []
        for approval in approvals {
            guard let turn = approval.turnID else { continue }
            let id = "zedlink:\(nextScope):\(approval.subagentID ?? ""):\(turn):\(approval.id)"
            nextIDs.insert(id)
            guard !currentIDs.contains(id) else { continue }
            let content = UNMutableNotificationContent()
            content.title = "ZedLink · Approval needed"
            content.body = "A Zed Agent is waiting. Review the request before allowing it."
            content.sound = .default
            var data = ["gateway": gateway, "target": target, "instance": instance, "epoch": epoch,
                        "thread": thread, "turn": String(turn), "approval": approval.id, "child": approval.subagentID ?? "", "created": String(Date().timeIntervalSince1970)]
            let allow = approval.decisions.first { $0.optionKind == "allow_once" && $0.choiceIndex == nil && $0.selectedPatternIndices.isEmpty && $0.action == nil }
            let deny = approval.decisions.first { $0.optionKind == "reject_once" && $0.choiceIndex == nil && $0.selectedPatternIndices.isEmpty && $0.action == nil }
            if allowActions, approval.authorizationKind == "permission_grant", !approval.detailsTruncated, let allow, let deny {
                content.categoryIdentifier = "ZEDLINK_PERMISSION"
                data["approve"] = allow.optionID; data["deny"] = deny.optionID
            } else { content.categoryIdentifier = "ZEDLINK_REVIEW" }
            content.userInfo = data
            center.add(UNNotificationRequest(identifier: id, content: content, trigger: nil)) { error in
                guard let error else { return }
                let message = error.localizedDescription
                Task { @MainActor in
                    self.lastError = message
                    self.currentIDs.remove(id)
                }
            }
        }
        let removed = Array(currentIDs.subtracting(nextIDs))
        center.removePendingNotificationRequests(withIdentifiers: removed)
        center.removeDeliveredNotifications(withIdentifiers: removed)
        currentIDs = nextIDs
    }

    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                           withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .list, .sound])
    }

    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse,
                                           withCompletionHandler completionHandler: @escaping () -> Void) {
        let data = response.notification.request.content.userInfo.reduce(into: [String: String]()) { result, pair in
            if let key = pair.key as? String, let value = pair.value as? String { result[key] = value }
        }
        Task { @MainActor in
            if response.actionIdentifier != UNNotificationDismissActionIdentifier {
                self.responses.enqueue(id: response.notification.request.identifier, data: data, action: self.enabled ? response.actionIdentifier : "review")
            }
            // Acknowledge OS delivery promptly; network readiness is handled by the app.
            completionHandler()
            await self.drainResponses()
        }
    }
}
