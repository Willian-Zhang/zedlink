import SwiftUI
import UIKit

struct SettingsView: View {
    @EnvironmentObject private var session: SessionManager
    @ObservedObject private var notifications = ApprovalNotifications.shared
    @AppStorage("zedlink.appearance") private var appearance = "dark"

    var body: some View {
        NavigationStack {
            List {
                Section("This device") {
                    Picker("Appearance", selection: $appearance) {
                        Text("System").tag("system")
                        Text("Dark").tag("dark")
                        Text("Light").tag("light")
                    }.accessibilityIdentifier("settings-appearance")
                    NavigationLink { NotificationSettingsView() } label: {
                        SettingsSummary(title: "Notifications", value: notifications.status)
                    }
                }
                Section("Connection & access") {
                    Button { session.showConnections = true } label: {
                        SettingsSummary(title: session.profile?.name ?? "Choose a connection", value: "Manage connections")
                    }.accessibilityIdentifier("settings-connections")
                    ConnectionStatusView(state: session.state)
                    NavigationLink("Diagnostics") { ConnectionDiagnosticsView() }
                }
                Section {
                    NavigationLink("Help & about") { SettingsHelpView() }
                }
            }.settingsList().navigationTitle("Settings").navigationBarTitleDisplayMode(.inline)
                .task { await notifications.refreshStatus() }
        }
    }
}

private struct SettingsSummary: View {
    let title: String
    let value: String
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).foregroundStyle(ZLTheme.ink)
            Text(value).font(.caption).foregroundStyle(ZLTheme.muted).fixedSize(horizontal: false, vertical: true)
        }.padding(.vertical, 4)
    }
}

private extension View {
    func settingsList() -> some View {
        self.listStyle(.plain).scrollContentBackground(.hidden).background(ZLTheme.background)
    }
}

private struct NotificationSettingsView: View {
    @EnvironmentObject private var session: SessionManager
    @Environment(\.openURL) private var openURL
    @Environment(\.scenePhase) private var scenePhase
    @ObservedObject private var notifications = ApprovalNotifications.shared
    @State private var busy = false
    @State private var result = ""

    var body: some View {
        List {
            Section("Local approval alerts") {
                Text(notifications.status).foregroundStyle(ZLTheme.muted)
                if notifications.blocked {
                    Button("Open iPhone notification settings", action: openSystemSettings)
                } else if !notifications.enabled {
                    Button("Enable alerts") {
                        run {
                            let allowed = try await notifications.enable()
                            result = allowed ? "Alerts enabled." : "Permission was not granted."
                        }
                    }.disabled(busy)
                }
                if notifications.enabled {
                    if notifications.permitted {
                        Button("Send test notification") {
                            run { try await notifications.sendTest(); result = "Test scheduled in three seconds. Check Notification Center if Focus hides the banner." }
                        }.disabled(busy)
                    }
                    Button("Disable alerts") { notifications.disable(); result = "" }.disabled(busy)
                }
                if !notifications.blocked { Button("System notification settings", action: openSystemSettings) }
                if !result.isEmpty { Text(result).font(.caption) }
                if !notifications.lastError.isEmpty { Text(notifications.lastError).font(.caption).foregroundStyle(ZLTheme.danger) }
            }
            Section("Background delivery") {
                LabeledContent("Native push", value: "Not configured")
                LabeledContent("Watch alerts", value: "Phone mirroring only")
                Text("Local alerts need incoming app updates. They cannot guarantee delivery while the app is suspended or closed. Browser push is the available background option.").font(.footnote).foregroundStyle(ZLTheme.muted)
                if let profile = session.profile, let url = URL(string: profile.endpoint), url.scheme == "https" {
                    Link("Set up browser push", destination: url)
                }
            }
        }.settingsList().navigationTitle("Notifications").navigationBarTitleDisplayMode(.inline)
            .task { await notifications.refreshStatus() }
            .onChange(of: scenePhase) { _, phase in if phase == .active { Task { await notifications.refreshStatus() } } }
    }
    private func openSystemSettings() {
        if let url = URL(string: UIApplication.openSettingsURLString) { openURL(url) }
    }
    private func run(_ operation: @escaping @MainActor () async throws -> Void) {
        busy = true; result = ""
        Task {
            defer { busy = false }
            do { try await operation() } catch { result = error.localizedDescription }
        }
    }
}

private struct ConnectionDiagnosticsView: View {
    @EnvironmentObject private var session: SessionManager
    private var prefix: String { session.state == .live ? "" : "Last known · " }
    private func capability(_ id: String) -> String {
        if session.capabilities.isEmpty { return "Unknown" }
        return prefix + (session.capabilities.contains(id) ? "Available" : "Unavailable")
    }
    var body: some View {
        List {
            Section("Current connection") {
                ConnectionStatusView(state: session.state)
                if let profile = session.profile {
                    SettingsSummary(title: profile.name, value: profile.endpoint)
                    SettingsSummary(title: "Gateway identity", value: profile.gatewayID).textSelection(.enabled)
                    SettingsSummary(title: "Workspace", value: session.targets.first { $0.id == session.targetID }?.label ?? "Not selected")
                    Button("Reconnect") { Task { await session.refresh() } }.disabled(session.state == .connecting)
                } else { Text("Choose a connection to inspect access.") }
                if !session.issue.isEmpty { Text(session.issue).font(.caption).foregroundStyle(ZLTheme.danger) }
            }
            Section("Advertised access") {
                LabeledContent("Files", value: capability("project.files"))
                LabeledContent("Terminal viewing", value: capability("terminal.list"))
                LabeledContent("Terminal input", value: capability("terminal.input"))
                LabeledContent("Debugger", value: capability("debugger.snapshot"))
                LabeledContent("Clipboard read", value: capability("clipboard.read"))
                LabeledContent("Clipboard write", value: capability("clipboard.write"))
                Text("Change remote access permissions in desktop Zed.").font(.caption).foregroundStyle(ZLTheme.muted)
            }
        }.settingsList().navigationTitle("Diagnostics").navigationBarTitleDisplayMode(.inline)
    }
}

private struct SettingsHelpView: View {
    var body: some View {
        List {
            Section("App") {
                LabeledContent("Version", value: Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "Unavailable")
                LabeledContent("Build", value: Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "Unavailable")
            }
            Section("Documentation") {
                Link("Setup & pairing", destination: URL(string: "https://github.com/tjnull/zedlink/blob/main/wiki/Running-and-Pairing.md")!)
                Link("Security & access", destination: URL(string: "https://github.com/tjnull/zedlink/blob/main/wiki/Security.md")!)
                Link("License", destination: URL(string: "https://github.com/tjnull/zedlink/blob/main/LICENSE")!)
            }
        }.settingsList().navigationTitle("Help & about").navigationBarTitleDisplayMode(.inline)
    }
}
