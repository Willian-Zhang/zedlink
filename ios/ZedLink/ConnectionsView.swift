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
    @Binding var draft: ConnectionDraft
    var body: some View {
        NavigationStack {
            List {
                Section("Saved connections") {
                    if profiles.profiles.isEmpty {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("No connections").font(.headline)
                            Text("Add your workstation using its private pairing QR or link.").font(.subheadline).foregroundStyle(ZLTheme.muted)
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
            }.listStyle(.plain).scrollContentBackground(.hidden).background(ZLTheme.background)
                .navigationTitle("Connections").navigationBarTitleDisplayMode(.inline)
                .sheet(isPresented: $showingAdd) { AddConnectionView(draft: $draft) }
        }
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
                        if !observedID.isEmpty { LabeledContent("Observed gateway ID", value: observedID).textSelection(.enabled) }
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
                    Text("The observed identity must match before the one-use code is sent.")
                        .font(.footnote).foregroundStyle(.secondary)
                    Button("Pair and save") { Task { await pair() } }
                        .disabled(busy || observedID.isEmpty || observedID.caseInsensitiveCompare(candidate.gatewayID) != .orderedSame || code.isEmpty)
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
                if !issue.isEmpty { Section("Connection diagnostic") { Text(issue).foregroundStyle(ZLTheme.warning) } }
            }
            .disabled(busy)
            .navigationTitle(draft.editing ? "Edit connection" : "Add connection").navigationBarTitleDisplayMode(.inline)
            .interactiveDismissDisabled(busy)
            .onChange(of: endpoint) { _, _ in observedID = "" }
            .onChange(of: expectedID) { _, _ in observedID = "" }
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
            issue = observedID.caseInsensitiveCompare(candidate.gatewayID) == .orderedSame
                ? "HTTPS and gateway identity verified. Choose Pair or Save to continue."
                : "HTTPS reached, but the gateway identity must match the workstation value before continuing."
        } catch { issue = error.localizedDescription }
    }

    private func pair() async {
        guard !busy else { return }
        busy = true; defer { busy = false }
        let profile = candidate
        guard !profile.name.isEmpty, observedID == profile.gatewayID else {
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

