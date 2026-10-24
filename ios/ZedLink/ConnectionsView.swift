import AVFoundation
import SwiftUI
import UIKit
import VisionKit

/// Pairing codes remain in memory only, and survive closing/reopening Add connection.
struct ConnectionDraft {
    var id = UUID()
    var name = "Desktop"
    var route: RouteKind = .tailscale
    var endpoint = ""
    var expectedID = ""
    var code = ""
    var deviceName = "iPhone"
    var editing = false
    init() {}
    init(_ profile: ConnectionProfile) {
        id = profile.id; name = profile.name; route = profile.route
        endpoint = profile.endpoint; expectedID = profile.gatewayID; editing = true
    }
}

struct ConnectionsView: View {
    @EnvironmentObject private var profiles: ProfileStore
    @EnvironmentObject private var session: SessionManager
    @State private var showingAdd = false
    @State private var checking = false
    @State private var checkStage = ""
    @State private var checkRun = UUID()
    @State private var checkedProfileID: UUID?
    @State private var checkedAt: Date?
    @State private var checks: [ConnectionCheck] = []
    @State private var checkedThreads: [String] = []
    @Binding var draft: ConnectionDraft
    private var currentProfile: ConnectionProfile? { session.profile ?? profiles.preferredProfile }
    private var currentIsLive: Bool { session.state == .live && session.profile?.id == currentProfile?.id }

    var body: some View {
        NavigationStack {
            List {
                if let profile = currentProfile {
                    Section("Current connection") {
                        HStack(alignment: .top) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(profile.name).font(.headline)
                                Text(profile.route.rawValue).font(.subheadline).foregroundStyle(ZLTheme.muted)
                            }
                            Spacer()
                            if session.profile?.id == profile.id { ConnectionStatusView(state: session.state) }
                            else { Text("Saved").font(.caption).foregroundStyle(ZLTheme.muted) }
                        }
                        VStack(alignment: .leading, spacing: 5) {
                            Text("Private HTTPS address").font(.footnote).foregroundStyle(ZLTheme.muted)
                            Text(profile.endpoint).font(.footnote.monospaced()).textSelection(.enabled)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        Text(profile.route.guidance).font(.footnote).foregroundStyle(ZLTheme.muted)
                        if session.profile?.id == profile.id, !session.issue.isEmpty {
                            Label {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(ConnectionHelp.forMessage(session.issue)?.title ?? "Connection needs attention")
                                        .font(.subheadline.weight(.semibold))
                                    Text(ConnectionHelp.forMessage(session.issue)?.detail ?? session.issue)
                                        .font(.footnote)
                                }
                            } icon: { Image(systemName: "exclamationmark.triangle") }
                                .foregroundStyle(ZLTheme.warning)
                        }
                        Button {
                            Task { await checkConnection(profile) }
                        } label: {
                            HStack(spacing: 10) {
                                if checking { ProgressView().controlSize(.small) }
                                else { Image(systemName: "waveform.path.ecg") }
                                Text(checking ? "Checking \(checkStage)…" : "Check connection")
                                Spacer()
                            }
                            .frame(minHeight: 44)
                        }
                        .disabled(checking)
                        .accessibilityIdentifier("check-connection")
                    }

                    Section("Connection path") {
                        pathRow("Phone to gateway", checkID: "https", liveDetail: "Connected earlier; check again for current reachability", pendingDetail: "Run checks to verify the HTTPS route")
                        pathRow("Paired device", checkID: "device", liveDetail: "Authorized when this session connected", pendingDetail: "Run checks to verify this device's credential")
                        pathRow("Desktop Zed", checkID: "zed", liveDetail: "Selected workspace responded when this session connected", pendingDetail: "Run checks to verify the selected Zed workspace")
                    }

                    if checkedProfileID == profile.id, !checks.isEmpty {
                        Section {
                            if let checkedAt {
                                Text("Checked \(checkedAt.formatted(date: .abbreviated, time: .shortened))")
                                    .font(.footnote).foregroundStyle(ZLTheme.muted)
                            }
                            ForEach(checks) { check in
                                ConnectionPathRow(title: check.title, detail: check.detail, passed: check.passed, failed: !check.passed)
                            }
                        } header: { Text("Latest checks") }
                    }

                    Section("Remote control sessions") {
                        if checkedProfileID == profile.id,
                           checks.first(where: { $0.id == "sessions" })?.passed == true {
                            Text(checkedThreads.isEmpty
                                 ? "No sessions exposed at the last check. Use /remote-control in a desktop Agent thread."
                                 : "\(checkedThreads.count) exposed session\(checkedThreads.count == 1 ? "" : "s") at the last check.")
                                .font(.footnote).foregroundStyle(ZLTheme.muted)
                            ForEach(checkedThreads.indices, id: \.self) { index in
                                Label(checkedThreads[index], systemImage: "bubble.left.and.bubble.right")
                                    .font(.subheadline).lineLimit(2)
                            }
                        } else if currentIsLive {
                            Text(session.threads.isEmpty
                                 ? "Zed is connected. No sessions are exposed. In a desktop Agent thread, use /remote-control to share it."
                                 : "\(session.threads.count) exposed session\(session.threads.count == 1 ? "" : "s") from the selected workspace.")
                                .font(.footnote).foregroundStyle(ZLTheme.muted)
                            ForEach(session.threads) { thread in
                                Label(thread.title, systemImage: "bubble.left.and.bubble.right")
                                    .font(.subheadline).lineLimit(2)
                            }
                        } else {
                            Text("Connect to Zed to see which Agent sessions are enabled for remote control.")
                                .font(.footnote).foregroundStyle(ZLTheme.muted)
                        }
                    }
                }
                Section("Saved connections") {
                    if profiles.profiles.isEmpty {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("No connections").font(.headline)
                            Text("Use Pair a device on your workstation, then scan its QR or paste its pairing link here.")
                                .font(.subheadline).foregroundStyle(ZLTheme.muted)
                        }.padding(.vertical, 8)
                    }
                    ForEach(profiles.profiles) { profile in
                        NavigationLink { ConnectionDetailView(profileID: profile.id) } label: {
                            HStack {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(profile.name).font(.headline)
                                    Text(profile.route.rawValue).font(.caption).foregroundStyle(ZLTheme.muted)
                                }
                                Spacer()
                                if session.profile?.id == profile.id { ConnectionStatusView(state: session.state) }
                                else { Text("Saved").font(.caption).foregroundStyle(ZLTheme.muted) }
                            }.padding(.vertical, 6)
                        }.accessibilityIdentifier("connection-\(profile.id)")
                    }
                    Button("Add connection") { showingAdd = true }.accessibilityIdentifier("add-connection")
                }
                if let profile = session.profile {
                    Section("Workspaces · \(profile.name)") {
                        if session.targets.isEmpty { Text("Connect to load workspaces.").font(.caption).foregroundStyle(ZLTheme.muted) }
                        ForEach(session.targets) { target in
                            Button { Task { await session.selectTarget(target.id) } } label: {
                                HStack {
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text(target.label).foregroundStyle(ZLTheme.ink)
                                        Text(session.state == .live ? (target.available ? "Available" : "Unavailable") : "Last known · \(target.available ? "Available" : "Unavailable")").font(.caption).foregroundStyle(ZLTheme.muted)
                                    }
                                    Spacer()
                                    Text(session.targetID == target.id ? "Selected" : "Switch").font(.caption)
                                }.padding(.vertical, 4)
                            }.disabled(session.state != .live || !target.available || session.targetID == target.id)
                                .accessibilityIdentifier("switch-target-\(target.id)")
                        }
                    }
                }
            }.listStyle(.insetGrouped).scrollContentBackground(.hidden).background(ZLTheme.background)
                .navigationTitle("Connections").navigationBarTitleDisplayMode(.inline)
                .sheet(isPresented: $showingAdd) { AddConnectionView(draft: $draft) }
                .onChange(of: currentProfile) { _, _ in resetChecks() }
                .onChange(of: session.targetID) { _, _ in resetChecks() }
        }
    }

    private func pathRow(_ title: String, checkID: String, liveDetail: String,
                         pendingDetail: String) -> some View {
        let hasChecks = checkedProfileID == currentProfile?.id && !checks.isEmpty
        let latest = hasChecks ? checks.first(where: { $0.id == checkID }) : nil
        return ConnectionPathRow(
            title: title,
            detail: latest?.detail ?? (hasChecks ? "Not checked because an earlier step did not pass." : currentIsLive ? liveDetail : pendingDetail),
            passed: latest?.passed ?? (!hasChecks && currentIsLive),
            failed: latest?.passed == false
        )
    }

    private func resetChecks() {
        checkRun = UUID()
        checking = false
        checkStage = ""
        checks = []
        checkedThreads = []
        checkedProfileID = nil
    }

    @MainActor private func checkConnection(_ profile: ConnectionProfile) async {
        let run = UUID()
        checkRun = run
        checking = true
        checkStage = "HTTPS"
        checkedProfileID = profile.id
        checkedAt = nil
        checks = []
        checkedThreads = []
        defer {
            if checkRun == run { checking = false; checkStage = ""; checkedAt = Date() }
        }

        let client = GatewayClient(profile: profile, token: nil)
        do {
            let observedID = try await client.gatewayID()
            guard checkRun == run else { return }
            checks.append(.init(id: "https", title: "Private HTTPS", detail: "Gateway answered over trusted HTTPS.", passed: true))
            guard observedID.caseInsensitiveCompare(profile.gatewayID) == .orderedSame else {
                checks.append(.init(id: "identity", title: "Gateway identity", detail: "The gateway ID changed. Review this saved address before sending a credential.", passed: false))
                return
            }
            checks.append(.init(id: "identity", title: "Gateway identity", detail: "Matches this saved connection.", passed: true))
        } catch {
            guard checkRun == run else { return }
            checks.append(.init(id: "https", title: "Private HTTPS", detail: error.localizedDescription, passed: false))
            return
        }

        checkStage = "device"
        guard let token = await CredentialVault.shared.read(profile) else {
            guard checkRun == run else { return }
            checks.append(.init(id: "device", title: "Paired device", detail: "No local credential is saved. Pair this iPhone again.", passed: false))
            return
        }
        guard checkRun == run else { return }
        let authorized = GatewayClient(profile: profile, token: token)
        let targets: [[String: Any]]
        let registry: [String: Any]
        do {
            registry = try await authorized.rpc("instance.list")
            guard checkRun == run else { return }
            guard let rows = registry["targets"] as? [[String: Any]] else { throw GatewayFailure.invalidResponse }
            targets = rows
            checks.append(.init(id: "device", title: "Paired device", detail: "Gateway accepted this device's credential.", passed: true))
        } catch {
            guard checkRun == run else { return }
            checks.append(.init(id: "device", title: "Paired device", detail: error.localizedDescription, passed: false))
            return
        }

        checkStage = "Zed"
        let preferredTargetID = session.profile?.id == profile.id
            ? (session.targetID ?? session.savedTargetID(for: profile))
            : session.savedTargetID(for: profile)
        let targetID = preferredTargetID ?? (registry["default_target_id"] as? String)
        let selectedTarget = targetID == nil
            ? targets.first(where: { $0["available"] as? Bool == true })
            : targets.first(where: { $0["target_id"] as? String == targetID })
        guard let target = selectedTarget,
              let selectedID = target["target_id"] as? String else {
            checks.append(.init(id: "zed", title: "Desktop Zed", detail: "No Zed workspace is configured or available.", passed: false))
            return
        }
        guard target["available"] as? Bool == true else {
            checks.append(.init(id: "zed", title: "Desktop Zed", detail: "The selected Zed workspace is offline. Open desktop Zed and its project.", passed: false))
            return
        }
        let targetClient = GatewayClient(profile: profile, token: token, targetID: selectedID)
        let instanceID: String
        let epoch: String
        do {
            let info = try await targetClient.rpc("instance.info")
            guard checkRun == run else { return }
            guard let currentInstance = info["instance_id"] as? String,
                  let currentEpoch = info["epoch"] as? String else { throw GatewayFailure.invalidResponse }
            instanceID = currentInstance
            epoch = currentEpoch
            checks.append(.init(id: "zed", title: "Desktop Zed", detail: "\(target["label"] as? String ?? "Selected workspace") is responding.", passed: true))
        } catch {
            guard checkRun == run else { return }
            checks.append(.init(id: "zed", title: "Desktop Zed", detail: error.localizedDescription, passed: false))
            return
        }

        checkStage = "sessions"
        do {
            let result = try await targetClient.rpc("thread.list")
            guard checkRun == run else { return }
            guard result["instance_id"] as? String == instanceID,
                  result["epoch"] as? String == epoch else {
                throw GatewayFailure.native("Desktop Zed restarted during the check. Run checks again.")
            }
            guard let rows = result["threads"] as? [[String: Any]] else { throw GatewayFailure.invalidResponse }
            checkedThreads = rows.map { $0["title"] as? String ?? "Untitled Agent thread" }
            checks.append(.init(id: "sessions", title: "Remote control sessions", detail: rows.isEmpty
                                ? "None exposed. Use /remote-control in a desktop Agent thread."
                                : "\(rows.count) exposed session\(rows.count == 1 ? "" : "s") available.", passed: true))
        } catch {
            guard checkRun == run else { return }
            checks.append(.init(id: "sessions", title: "Remote control sessions", detail: error.localizedDescription, passed: false))
        }
    }
}

private struct ConnectionCheck: Identifiable {
    let id: String
    let title: String
    let detail: String
    let passed: Bool
}

private struct ConnectionPathRow: View {
    let title: String
    let detail: String
    let passed: Bool
    var failed = false

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: passed ? "checkmark.circle.fill" : failed ? "exclamationmark.circle.fill" : "circle.dotted")
                .foregroundStyle(passed ? ZLTheme.healthy : failed ? ZLTheme.warning : ZLTheme.muted)
                .frame(width: 22)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(.subheadline.weight(.medium))
                Text(detail).font(.footnote).foregroundStyle(ZLTheme.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(title): \(passed ? "Passed" : failed ? "Failed" : "Not checked"). \(detail)")
    }
}

private struct ConnectionDetailView: View {
    let profileID: UUID
    @EnvironmentObject private var profiles: ProfileStore
    @EnvironmentObject private var session: SessionManager
    @Environment(\.dismiss) private var dismiss
    @State private var editing = false
    @State private var draft = ConnectionDraft()
    @State private var removing = false
    @State private var connecting = false
    private var profile: ConnectionProfile? { profiles.profiles.first { $0.id == profileID } }
    var body: some View {
        List {
            if let profile {
                Section("Connection") {
                    Text(profile.name).font(.headline)
                    Text(profile.route.rawValue).foregroundStyle(ZLTheme.muted)
                    Text(profile.endpoint).font(.caption.monospaced()).textSelection(.enabled)
                    if session.profile?.id == profile.id {
                        ConnectionStatusView(state: session.state)
                        if !session.issue.isEmpty {
                            if let help = ConnectionHelp.forMessage(session.issue) { Text(help.title).font(.headline); Text(help.detail).font(.caption) }
                            else { Text(session.issue).font(.caption).foregroundStyle(ZLTheme.warning) }
                        }
                    }
                    Button(session.profile?.id == profile.id ? "Reconnect" : "Connect") {
                        connecting = true
                        Task {
                            defer { connecting = false }
                            await session.connect(profile)
                            if session.state == .live, session.profile?.id == profile.id { profiles.markUsed(profile) }
                        }
                    }.disabled(connecting || session.state == .connecting || session.state == .reconnecting)
                        .accessibilityIdentifier("connect-\(profile.id)")
                    Button("Edit connection") { draft = ConnectionDraft(profile); editing = true }.disabled(connecting)
                }
                Section {
                    DisclosureGroup("Identity & access") {
                        Text(profile.gatewayID).font(.caption.monospaced()).textSelection(.enabled)
                        Text("HTTPS and gateway identity are checked before the credential is sent. Manage remote permissions in desktop Zed.").font(.caption).foregroundStyle(ZLTheme.muted)
                    }
                    Button("Remove saved connection", role: .destructive) { removing = true }.disabled(connecting)
                }
            } else { Text("This connection was removed.") }
        }.listStyle(.plain).scrollContentBackground(.hidden).background(ZLTheme.background)
            .navigationTitle("Connection details").navigationBarTitleDisplayMode(.inline)
            .sheet(isPresented: $editing) { AddConnectionView(draft: $draft) }
            .confirmationDialog("Remove this saved connection?", isPresented: $removing) {
                Button("Remove connection", role: .destructive) {
                    guard let profile else { return }
                    if session.profile?.id == profile.id { session.disconnect() }
                    Task { await profiles.remove(profile); dismiss() }
                }
            } message: {
                if let profile {
                    let linked = profiles.profiles.contains { $0.id != profile.id && $0.gatewayID.caseInsensitiveCompare(profile.gatewayID) == .orderedSame }
                    Text(linked ? "Only this saved address is removed. Other addresses retain their shared gateway credential. Remote access is not revoked." : "This removes the saved address and its local credential. Pair again to reconnect. Remote access is not revoked; revoke the device separately on the workstation.")
                }
            }
    }
}

struct AddConnectionView: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var profiles: ProfileStore
    @EnvironmentObject private var session: SessionManager
    @Binding var draft: ConnectionDraft
    private var name: String { get { draft.name } nonmutating set { draft.name = newValue } }
    private var route: RouteKind { get { draft.route } nonmutating set { draft.route = newValue } }
    private var endpoint: String { get { draft.endpoint } nonmutating set { draft.endpoint = newValue } }
    private var expectedID: String { get { draft.expectedID } nonmutating set { draft.expectedID = newValue } }
    private var code: String { get { draft.code } nonmutating set { draft.code = newValue } }
    private var deviceName: String { get { draft.deviceName } nonmutating set { draft.deviceName = newValue } }
    @State private var issue = ""
    @State private var busy = false
    @State private var showingScanner = false
    @State private var showingIdentity = false
    @State private var observedID = "" // the gateway identity seen by the last Test; never kept in the draft

    private var candidate: ConnectionProfile {
        ConnectionProfile(id: draft.id, name: name.trimmingCharacters(in: .whitespacesAndNewlines), route: route,
                          endpoint: endpoint.trimmingCharacters(in: .whitespacesAndNewlines),
                          gatewayID: expectedID.trimmingCharacters(in: .whitespacesAndNewlines).lowercased())
    }

    private var savedGateway: ConnectionProfile? {
        profiles.profiles.first {
            $0.gatewayID.caseInsensitiveCompare(expectedID.trimmingCharacters(in: .whitespacesAndNewlines)) == .orderedSame
        }
    }

    var body: some View {
        NavigationStack {
            Form {
                if !draft.editing { Section("Quick setup") {
                    Button("Scan workstation QR") { Task { await scanPairingLink() } }
                        .disabled(!DataScannerViewController.isSupported || busy).accessibilityIdentifier("scan-pairing-qr")
                    Button("Use pairing link from clipboard") {
                        if let link = UIPasteboard.general.string { applyPairingLink(link) }
                        else { issue = "Copy the desktop pairing link first." }
                    }
                    if !DataScannerViewController.isSupported {
                        Text("QR scanning needs a supported iPhone camera. Paste the desktop link or enter the address below.")
                            .font(.footnote).foregroundStyle(.secondary)
                    }
                }
                }
                Section("Route") {
                    Picker("Connection type", selection: $draft.route) {
                        ForEach(RouteKind.allCases) { Text($0.rawValue).tag($0) }
                    }
                    Text(route.guidance).font(.footnote).foregroundStyle(.secondary)
                }
                Section("Gateway") {
                    TextField("Name", text: $draft.name)
                    TextField("https://hostname:port", text: $draft.endpoint)
                        .textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL)
                        .accessibilityIdentifier("gateway-endpoint")
                    Button("Test HTTPS endpoint") { Task { await testEndpoint() } }
                        .disabled(busy).accessibilityIdentifier("test-connection")
                    
                    DisclosureGroup("Gateway identity", isExpanded: $showingIdentity) {
                        if !observedID.isEmpty {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Observed gateway ID").font(.footnote).foregroundStyle(ZLTheme.muted)
                                Text(observedID).font(.footnote.monospaced()).textSelection(.enabled)
                            }
                        }
                        TextField("Expected gateway ID from workstation", text: $draft.expectedID)
                            .textInputAutocapitalization(.never).autocorrectionDisabled()
                            .disabled(draft.editing).accessibilityIdentifier("expected-gateway-id")
                    }
                }
                Section(draft.editing ? "Save connection" : "Pair this iPhone") {
                    if !draft.editing {
                    TextField("Device name", text: $draft.deviceName)
                    SecureField("10-digit pairing code", text: $draft.code)
                        .textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.numberPad)
                        .accessibilityIdentifier("pairing-code")
                    if !code.isEmpty {
                        Label("One-time code loaded", systemImage: "checkmark.circle")
                            .font(.footnote).foregroundStyle(ZLTheme.healthy)
                    }
                    Text(pairingNextStep)
                        .font(.footnote).foregroundStyle(ZLTheme.muted)
                    Button("Pair and save") { Task { await pair() } }
                        .disabled(busy || observedID.isEmpty || observedID.caseInsensitiveCompare(candidate.gatewayID) != .orderedSame || code.isEmpty)
                        .buttonStyle(ZLPrimaryButtonStyle())
                        .accessibilityIdentifier("pair-and-save")
                    }
                    if savedGateway != nil {
                        Button(draft.editing ? "Save changes and connect" : "Save another address") { Task { await saveExistingRoute() } }
                            .disabled(busy || observedID.isEmpty || observedID.caseInsensitiveCompare(expectedID) != .orderedSame)
                            .accessibilityIdentifier("save-existing-route")
                        Text("This gateway is already paired. Save this address as another connection and reuse its protected Keychain credential.")
                            .font(.footnote).foregroundStyle(.secondary)
                    }
                }
                if !issue.isEmpty {
                    Section("Connection diagnostic") {
                        Label {
                            Text(issue).foregroundStyle(ZLTheme.ink).fixedSize(horizontal: false, vertical: true)
                        } icon: {
                            Image(systemName: issue.hasPrefix("HTTPS and gateway identity verified") ? "checkmark.circle" : "exclamationmark.triangle")
                                .foregroundStyle(issue.hasPrefix("HTTPS and gateway identity verified") ? ZLTheme.healthy : ZLTheme.warning)
                        }
                        if issue.hasPrefix("Gateway request timed out") ||
                            issue.hasPrefix("Could not connect to the gateway") ||
                            issue.hasPrefix("Gateway connection dropped") {
                            Text("If Safari opens this HTTPS address but this test fails, retry while the phone's VPN is connected. No pairing code has been sent.")
                                .font(.footnote).foregroundStyle(ZLTheme.muted)
                        }
                    }
                }
            }
            .disabled(busy)
            .navigationTitle(draft.editing ? "Edit connection" : "Add connection").navigationBarTitleDisplayMode(.inline)
            .interactiveDismissDisabled(busy)
            .onChange(of: endpoint) { _, _ in observedID = "" }
            .onChange(of: expectedID) { _, _ in
                if !observedID.isEmpty { issue = identityIssue }
            }
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Close") { dismiss() }.disabled(busy) } }
            .sheet(isPresented: $showingScanner) {
                NavigationStack {
                    PairingQRScanner(onPayload: { showingScanner = false; applyPairingLink($0) },
                                     onError: { showingScanner = false; issue = "Camera scanner unavailable: \($0)" })
                        .navigationTitle("Scan desktop QR")
                        .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Cancel") { showingScanner = false } } }
                }
            }
        }
    }

    private func scanPairingLink() async {
        guard !busy else { return }
        busy = true; defer { busy = false }
        guard DataScannerViewController.isSupported else {
            issue = "This iPhone does not support live QR scanning. Use the clipboard or manual fields."; return
        }
        guard await AVCaptureDevice.requestAccess(for: .video), DataScannerViewController.isAvailable else {
            issue = "Allow camera access for ZedLink in iPhone Settings, or use the clipboard."; return
        }
        showingScanner = true
    }

    private func applyPairingLink(_ value: String) {
        guard let components = URLComponents(string: value.trimmingCharacters(in: .whitespacesAndNewlines)),
              components.scheme == "https", components.host != nil,
              components.user == nil, components.password == nil, components.query == nil,
              components.path.isEmpty || components.path == "/", let fragment = components.fragment,
              let query = URLComponents(string: "?\(fragment)")?.queryItems,
              Set(query.map(\.name)).count == query.count,
              (Set(query.map(\.name)) == Set(["gateway"]) || Set(query.map(\.name)) == Set(["v", "gateway", "pair"])),
              let gatewayID = query.first(where: { $0.name == "gateway" })?.value,
              UUID(uuidString: gatewayID) != nil,
              (query.count == 1 || (query.first(where: { $0.name == "v" })?.value == "1" &&
                                    query.first(where: { $0.name == "pair" })?.value?.count == 10 &&
                                    query.first(where: { $0.name == "pair" })?.value?.allSatisfy(\.isNumber) == true)) else {
            issue = "Scan the ZedLink desktop QR, or paste its HTTPS pairing link."; return
        }
        var endpointParts = components
        endpointParts.fragment = nil
        guard let address = endpointParts.url?.absoluteString else { issue = "The pairing address is invalid."; return }
        endpoint = address
        expectedID = gatewayID
        code = query.first(where: { $0.name == "pair" })?.value ?? ""
        observedID = ""
        issue = "Address and gateway identity loaded. Checking HTTPS before pairing."
        Task { await testEndpoint() }
    }

    private func testEndpoint() async {
        guard !busy else { return }
        busy = true; defer { busy = false }; observedID = ""
        do {
            observedID = try await GatewayClient(profile: candidate, token: nil).gatewayID()
            showingIdentity = true
            issue = identityIssue
        } catch { issue = error.localizedDescription }
    }

    private var identityIssue: String {
        if candidate.gatewayID.isEmpty {
            return "HTTPS reached. Compare the observed gateway ID below with the ID shown on your workstation, then enter that expected ID."
        }
        if observedID.caseInsensitiveCompare(candidate.gatewayID) != .orderedSame {
            return "HTTPS reached, but this gateway ID differs from the workstation value. Check the address and expected ID before pairing."
        }
        return code.isEmpty
            ? "HTTPS and gateway identity verified. Enter a fresh one-time code, then choose Pair and save."
            : "HTTPS and gateway identity verified. Choose Pair and save to continue."
    }

    private var pairingNextStep: String {
        if observedID.isEmpty { return "Test HTTPS above before pairing. No code will be sent until the gateway identity is verified." }
        if expectedID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return "Compare the observed gateway ID with the workstation, then enter the expected ID under Gateway identity."
        }
        if observedID.caseInsensitiveCompare(candidate.gatewayID) != .orderedSame {
            return "The gateway IDs differ. Check the workstation identity and address before pairing."
        }
        if code.isEmpty { return "Use Pair a device on the workstation to get a fresh one-time code, then enter it above." }
        return "Identity verified. Pair and save will send the one-time code to this gateway."
    }

    private func pair() async {
        guard !busy else { return }
        busy = true; defer { busy = false }
        let profile = candidate
        guard !profile.name.isEmpty, observedID.caseInsensitiveCompare(profile.gatewayID) == .orderedSame else {
            issue = "Gateway ID differs from the workstation value. No pairing code was sent."; return
        }
        let shortCode = code.count == 10 && code.utf8.allSatisfy { $0 >= 48 && $0 <= 57 }
        let legacyCode = code.count == 64 && code.allSatisfy(\.isHexDigit)
        guard shortCode || legacyCode else { issue = "Enter the 10-digit one-use pairing code."; return }
        do {
            let paired = try await GatewayClient(profile: profile, token: nil).pair(code: code, deviceName: deviceName)
            code = ""
            try await CredentialVault.shared.write(paired.token, for: profile)
            let saved = profiles.save(profile)
            await session.connect(saved)
            if session.state == .live, session.profile?.id == saved.id { profiles.markUsed(saved) }
            draft = ConnectionDraft()
            dismiss()
        } catch { issue = error.localizedDescription }
    }

    private func saveExistingRoute() async {
        guard !busy else { return }
        busy = true; defer { busy = false }
        let profile = candidate
        guard observedID.caseInsensitiveCompare(profile.gatewayID) == .orderedSame, savedGateway != nil else {
            issue = "Test the new HTTPS address and confirm the same gateway identity first."; return
        }
        guard await CredentialVault.shared.read(profile) != nil else {
            issue = "The saved device credential is missing. Pair this device again once."; return
        }
        let saved = profiles.save(profile)
        await session.connect(saved)
        if session.state == .live, session.profile?.id == saved.id { profiles.markUsed(saved) }
        draft = ConnectionDraft()
        dismiss()
    }
}

