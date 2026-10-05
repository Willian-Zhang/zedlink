import SwiftUI

private struct StatusBadge: View {
    let state: LinkState
    var body: some View {
        Label(state.label, systemImage: state == .live ? "checkmark.circle.fill" : "exclamationmark.circle")
            .font(.caption.weight(.semibold))
            .foregroundStyle(state == .live ? .green : .secondary)
            .accessibilityLabel("Connection \(state.label)")
    }
}

struct SessionsView: View {
    @EnvironmentObject private var profiles: ProfileStore
    @EnvironmentObject private var session: SessionManager

    var body: some View {
        NavigationStack {
            List {
                Section("Connection") {
                    if let profile = session.profile {
                        HStack {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(profile.name).font(.headline)
                                Text(profile.route.rawValue).font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                            StatusBadge(state: session.state)
                        }
                        Button("Reconnect") { Task { await session.refresh() } }
                            .accessibilityIdentifier("reconnect")
                    } else {
                        VStack(alignment: .leading, spacing: 8) {
                            Label("Choose a connection", systemImage: "network").font(.headline)
                            Text("Add and pair a private HTTPS connection in the Connections tab.")
                                .font(.subheadline).foregroundStyle(.secondary)
                        }
                        .padding(.vertical, 10)
                    }
                    if !session.issue.isEmpty {
                        Text(session.issue).foregroundStyle(.orange).font(.footnote)
                            .accessibilityIdentifier("connection-diagnostic")
                    }
                }
                Section("Exposed Agent threads") {
                    if session.threads.isEmpty {
                        Text("In desktop Zed, open a native Agent thread and choose /remote-control to expose it.")
                            .foregroundStyle(.secondary)
                    }
                    ForEach(session.threads) { thread in
                        NavigationLink(value: thread.id) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(thread.title).font(.headline)
                                Text(thread.status).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                        .accessibilityIdentifier("thread-\(thread.id)")
                    }
                }
            }
            .navigationTitle("Sessions")
            .navigationDestination(for: String.self) { id in ConversationView(threadID: id) }
            .refreshable { await session.refresh() }
        }
    }
}

struct ConversationView: View {
    @EnvironmentObject private var session: SessionManager
    let threadID: String
    @State private var showingClearConfirmation = false

    var body: some View {
        VStack(spacing: 0) {
            if let snapshot = session.snapshot, snapshot.threadID == threadID {
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 14) {
                            if snapshot.truncated {
                                Label("Native transcript was truncated by the adapter", systemImage: "exclamationmark.triangle")
                                    .font(.footnote).foregroundStyle(.orange)
                            }
                            ForEach(Array(snapshot.entries.enumerated()), id: \.offset) { index, entry in
                                VStack(alignment: .leading, spacing: 8) {
                                    Text("Native entry \(index + 1)")
                                        .font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                                    Text(entry).textSelection(.enabled)
                                        .font(.body.monospaced())
                                        .frame(maxWidth: .infinity, alignment: .leading)
                                }
                                .padding(14)
                                .background(.quaternary, in: RoundedRectangle(cornerRadius: 16))
                                .id(index)
                            }
                        }
                        .padding()
                    }
                    .defaultScrollAnchor(.bottom)
                }
                if snapshot.pendingApprovalCount > 0 {
                    Label("Approval pending in desktop Zed. Mobile approval awaits native race validation.",
                          systemImage: "hand.raised")
                        .font(.footnote)
                        .padding(12)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(.orange.opacity(0.15))
                        .accessibilityIdentifier("approval-unavailable")
                }
            } else {
                ContentUnavailableView("Loading native thread", systemImage: "bubble.left")
                    .frame(maxHeight: .infinity)
            }
            VStack(alignment: .leading, spacing: 8) {
                if !session.delivery.isEmpty {
                    Text(session.delivery).font(.footnote).foregroundStyle(.secondary)
                        .accessibilityIdentifier("delivery-status")
                }
                if session.pending != nil {
                    HStack {
                        Button("Check status") { Task { await session.reconcilePending() } }
                            .accessibilityIdentifier("check-request-status")
                        if session.pending?.text != nil {
                            Button("Retry same ID") { Task { await session.retryPending() } }
                                .accessibilityIdentifier("retry-same-request")
                        }
                        Button("Clear") { showingClearConfirmation = true }
                    }
                    .font(.footnote)
                }
                TextEditor(text: $session.draft)
                    .frame(minHeight: 68, maxHeight: 110)
                    .scrollContentBackground(.hidden)
                    .padding(8)
                    .background(.quaternary, in: RoundedRectangle(cornerRadius: 12))
                    .accessibilityLabel("Message to native Zed Agent")
                    .accessibilityIdentifier("composer")
                HStack {
                    Text(session.snapshot?.status ?? "Unknown")
                        .font(.caption).foregroundStyle(.secondary)
                    Spacer()
                    Button { Task { await session.send() } } label: {
                        Label("Send", systemImage: "arrow.up")
                            .frame(minWidth: 76, minHeight: 44)
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(!session.canSend || session.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    .accessibilityIdentifier("send-prompt")
                }
            }
            .padding()
            .background(.regularMaterial)
        }
        .navigationTitle(session.snapshot?.title ?? "Agent thread")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar { ToolbarItem(placement: .topBarTrailing) { StatusBadge(state: session.state) } }
        .task(id: threadID) { await session.select(threadID) }
        .confirmationDialog("Clear uncertain delivery?", isPresented: $showingClearConfirmation) {
            Button("Clear locally", role: .destructive) { session.clearPending() }
        } message: {
            Text("Inspect the desktop transcript first. Clearing this record does not cancel a native turn.")
        }
    }
}

struct ConnectionsView: View {
    @EnvironmentObject private var profiles: ProfileStore
    @EnvironmentObject private var session: SessionManager
    @State private var showingAdd = false
    @State private var profileToForget: ConnectionProfile?

    var body: some View {
        NavigationStack {
            List {
                if profiles.profiles.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        Label("No connections", systemImage: "network").font(.headline)
                        Text("Add an HTTPS gateway profile, then pair this iPhone.")
                            .font(.subheadline).foregroundStyle(.secondary)
                    }
                    .padding(.vertical, 10)
                }
                ForEach(profiles.profiles) { profile in
                    VStack(alignment: .leading, spacing: 8) {
                        Text(profile.name).font(.headline)
                        Text(profile.route.rawValue).font(.caption).foregroundStyle(.secondary)
                        Text(profile.endpoint).font(.footnote).textSelection(.enabled)
                        HStack {
                            Button("Connect") { Task { await session.connect(profile) } }
                                .buttonStyle(.borderedProminent)
                                .accessibilityIdentifier("connect-\(profile.id)")
                            Button("Forget") { profileToForget = profile }
                                .foregroundStyle(.red)
                        }
                    }
                    .padding(.vertical, 6)
                }
            }
            .navigationTitle("Connections")
            .toolbar {
                Button { showingAdd = true } label: { Image(systemName: "plus") }
                    .accessibilityLabel("Add connection")
                    .accessibilityIdentifier("add-connection")
            }
            .sheet(isPresented: $showingAdd) { AddConnectionView() }
            .confirmationDialog("Forget this connection?", isPresented: Binding(
                get: { profileToForget != nil }, set: { if !$0 { profileToForget = nil } }
            )) {
                Button("Forget local profile and credential", role: .destructive) {
                    guard let target = profileToForget else { return }
                    if session.profile?.id == target.id { session.disconnect() }
                    Task { await profiles.remove(target) }
                    profileToForget = nil
                }
            } message: {
                Text("This removes the local credential. Revoke the device separately on the workstation.")
            }
        }
    }
}

struct AddConnectionView: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var profiles: ProfileStore
    @EnvironmentObject private var session: SessionManager
    @State private var name = "My Zed"
    @State private var route: RouteKind = .tailscale
    @State private var endpoint = ""
    @State private var expectedID = ""
    @State private var observedID = ""
    @State private var code = ""
    @State private var deviceName = "iPhone"
    @State private var issue = ""
    @State private var busy = false

    private var candidate: ConnectionProfile {
        ConnectionProfile(name: name.trimmingCharacters(in: .whitespacesAndNewlines),
                          route: route, endpoint: endpoint.trimmingCharacters(in: .whitespacesAndNewlines),
                          gatewayID: expectedID.trimmingCharacters(in: .whitespacesAndNewlines))
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Route") {
                    Picker("Connection type", selection: $route) {
                        ForEach(RouteKind.allCases) { route in Text(route.rawValue).tag(route) }
                    }
                    Text(route.guidance).font(.footnote).foregroundStyle(.secondary)
                }
                Section("Gateway") {
                    TextField("Name", text: $name)
                    TextField("https://hostname:port", text: $endpoint)
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                        .keyboardType(.URL).accessibilityIdentifier("gateway-endpoint")
                    Button("Test HTTPS endpoint") { Task { await testEndpoint() } }
                        .disabled(busy).accessibilityIdentifier("test-connection")
                    if !observedID.isEmpty {
                        LabeledContent("Observed gateway ID", value: observedID)
                            .textSelection(.enabled)
                    }
                    TextField("Expected gateway ID from workstation", text: $expectedID)
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                        .accessibilityIdentifier("expected-gateway-id")
                }
                Section("Pair this iPhone") {
                    TextField("Device name", text: $deviceName)
                    SecureField("One-use pairing code", text: $code)
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                        .accessibilityIdentifier("pairing-code")
                    Text("Confirm that the observed ID matches the workstation ID before pairing. HTTPS certificate verification must succeed first.")
                        .font(.footnote).foregroundStyle(.secondary)
                    Button("Pair and save") { Task { await pair() } }
                        .disabled(busy || observedID.isEmpty || expectedID.isEmpty || code.isEmpty)
                        .accessibilityIdentifier("pair-and-save")
                }
                if !issue.isEmpty {
                    Section("Connection diagnostic") { Text(issue).foregroundStyle(.orange) }
                }
            }
            .navigationTitle("Add connection")
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Done") { dismiss() } } }
        }
    }

    private func testEndpoint() async {
        busy = true
        defer { busy = false }
        observedID = ""
        do {
            observedID = try await GatewayClient(profile: candidate, token: nil).gatewayID()
            issue = "HTTPS and protocol identity verified. Compare the ID with the workstation."
        } catch { issue = error.localizedDescription }
    }

    private func pair() async {
        busy = true
        defer { busy = false }
        let profile = candidate
        guard !profile.name.isEmpty, observedID == profile.gatewayID else {
            issue = "Gateway ID differs from the workstation value. No pairing code was sent."
            return
        }
        guard code.count == 64, code.allSatisfy({ $0.isHexDigit }) else {
            issue = "Enter the 64-character one-use pairing code."
            return
        }
        do {
            let paired = try await GatewayClient(profile: profile, token: nil)
                .pair(code: code, deviceName: deviceName)
            try await CredentialVault.shared.write(paired.token, for: profile.id)
            code = ""
            profiles.save(profile)
            await session.connect(profile)
            dismiss()
        } catch { issue = error.localizedDescription }
    }
}

struct SettingsView: View {
    var body: some View {
        NavigationStack {
            List {
                Section("About") {
                    LabeledContent("Protocol", value: "ZedLink v1")
                    Text("Zed's native Agent owns the model, tools, permissions, and conversation. This app stores only its paired gateway credential.")
                }
                Section("Current adapter limits") {
                    Text("Mobile approval, cancellation, and diff inspection are unavailable until their native adapter paths pass live validation.")
                    Text("A private VPN route still requires verified HTTPS and device pairing.")
                }
            }
            .navigationTitle("Settings")
        }
    }
}
