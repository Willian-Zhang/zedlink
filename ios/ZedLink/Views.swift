import AVFoundation
import SwiftUI
import UIKit
import VisionKit

struct SessionsView: View {
    @EnvironmentObject private var profiles: ProfileStore
    @EnvironmentObject private var session: SessionManager
    @State private var search = ""
    @State private var showingNewSession = false
    @FocusState private var searchFocused: Bool

    private var visibleThreads: [NativeThread] {
        guard !search.isEmpty else { return session.threads }
        return session.threads.filter { $0.title.localizedCaseInsensitiveContains(search) }
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 0) {
                    connectionHeader
                    if !session.issue.isEmpty { diagnostic }
                    HStack(spacing: 9) {
                        Image(systemName: "magnifyingglass").foregroundStyle(ZLTheme.muted)
                        TextField("Search exposed sessions", text: $search)
                            .textInputAutocapitalization(.never)
                            .submitLabel(.search)
                            .focused($searchFocused)
                            .onSubmit { searchFocused = false }
                            .accessibilityIdentifier("session-search")
                    }
                    .padding(.horizontal, 12).frame(minHeight: 44)
                    .background(ZLTheme.surface)
                    .overlay(Rectangle().stroke(ZLTheme.line, lineWidth: 1))
                    .padding(.horizontal, 16).padding(.top, 18)

                    HStack {
                        SectionLabel("Exposed Zed threads")
                        Spacer()
                        Text("\(session.threads.count)").font(.caption.monospaced()).foregroundStyle(ZLTheme.muted)
                    }
                    .padding(.horizontal, 16).padding(.top, 24).padding(.bottom, 9)

                    if visibleThreads.isEmpty {
                        emptyThreads
                    } else {
                        ForEach(visibleThreads) { thread in
                            NavigationLink(value: thread.id) { SessionRow(thread: thread) }
                                .buttonStyle(.plain)
                                .accessibilityIdentifier("thread-\(thread.id)")
                                .simultaneousGesture(TapGesture().onEnded { searchFocused = false })
                            Hairline().padding(.leading, 48)
                        }
                    }
                }
                .padding(.bottom, 30)
            }
            .background(ZLTheme.background)
            .scrollDismissesKeyboard(.interactively)
            .navigationTitle("ZedLink")
            .navigationBarTitleDisplayMode(.large)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showingNewSession = true } label: { Image(systemName: "plus") }
                        .disabled(!session.capabilities.contains("thread.create"))
                        .accessibilityLabel("Create Agent session")
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button { Task { await session.refresh() } } label: { Image(systemName: "arrow.clockwise") }
                        .disabled(session.profile == nil)
                        .accessibilityLabel("Refresh sessions")
                        .accessibilityIdentifier("reconnect")
                }
            }
            .sheet(isPresented: $showingNewSession) { NewSessionView() }
            .navigationDestination(for: String.self) { ConversationView(threadID: $0) }
            .refreshable { await session.refresh() }
            .toolbar {
                ToolbarItemGroup(placement: .keyboard) {
                    Spacer()
                    Button("Done") { searchFocused = false }
                }
            }
        }
    }

    @ViewBuilder private var connectionHeader: some View {
        if let profile = session.profile {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: "bolt.fill").font(.headline).foregroundStyle(ZLTheme.healthy)
                    .frame(width: 22, height: 22)
                VStack(alignment: .leading, spacing: 5) {
                    HStack {
                        Text(profile.name).font(.headline)
                        Spacer()
                        ConnectionStatusView(state: session.state)
                    }
                    Text(profile.endpoint).font(.caption.monospaced()).foregroundStyle(ZLTheme.muted)
                        .lineLimit(1).truncationMode(.middle)
                    if session.targets.count > 1 {
                        Picker("Zed target", selection: Binding(
                            get: { session.targetID ?? "" },
                            set: { target in Task { await session.selectTarget(target) } }
                        )) {
                            ForEach(session.targets) { target in
                                Text("\(target.label)\(target.available ? "" : " · unavailable")")
                                    .tag(target.id).disabled(!target.available)
                            }
                        }
                        .pickerStyle(.menu)
                        .accessibilityIdentifier("zed-target-picker")
                    }
                    Text("\(profile.route.rawValue) · \(session.targets.first(where: { $0.id == session.targetID })?.label ?? "Native Zed Agent")")
                        .font(.caption2.monospaced()).foregroundStyle(ZLTheme.muted)
                }
            }
            .padding(16)
            .background(ZLTheme.surface)
            .overlay(alignment: .bottom) { Hairline() }
        } else {
            VStack(alignment: .leading, spacing: 8) {
                Text("Choose a connection").font(.title3.weight(.semibold))
                Text("Pair a private ZedLink gateway from the Connections tab.")
                    .font(.subheadline).foregroundStyle(ZLTheme.muted)
            }
            .frame(maxWidth: .infinity, alignment: .leading).padding(20)
            .background(ZLTheme.surface)
        }
    }

    private var diagnostic: some View {
        HStack(alignment: .top, spacing: 9) {
            Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(ZLTheme.warning)
            Text(session.issue).font(.footnote).foregroundStyle(.secondary)
        }
        .padding(12).frame(maxWidth: .infinity, alignment: .leading)
        .background(ZLTheme.warning.opacity(0.08))
        .overlay(alignment: .bottom) { Hairline() }
        .accessibilityIdentifier("connection-diagnostic")
    }

    private var emptyThreads: some View {
        VStack(alignment: .leading, spacing: 10) {
            Image(systemName: "rectangle.connected.to.line.below").font(.title2).foregroundStyle(ZLTheme.muted)
            Text(session.threads.isEmpty ? "No exposed sessions" : "No matching sessions").font(.headline)
            Text(session.threads.isEmpty
                 ? "In Zed Dev, open a native Agent conversation and select /remote-control."
                 : "Try another search term.")
                .font(.subheadline).foregroundStyle(ZLTheme.muted)
        }
        .padding(20).frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct NewSessionView: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var session: SessionManager
    @State private var title = ""
    @State private var agentID = "zed-agent"

    var body: some View {
        NavigationStack {
            Form {
                Section("Session") {
                    TextField("Optional title", text: $title)
                    Picker("Agent", selection: $agentID) {
                        ForEach(session.createAgents) { agent in
                            Text("\(agent.name)\(agent.kind == "external_acp" ? " · ACP" : "")").tag(agent.id)
                        }
                    }
                }
                Section {
                    Text("The selected agent, model, tools, permissions, and project remain configured in desktop Zed.")
                        .font(.footnote).foregroundStyle(ZLTheme.muted)
                }
            }
            .navigationTitle("New Agent session")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button(session.creatingThread ? "Creating…" : "Create") {
                        Task { if await session.createThread(title: title, agentID: agentID) { dismiss() } }
                    }.disabled(session.creatingThread || session.createAgents.isEmpty)
                }
            }
            .task {
                await session.loadCreateOptions()
                if !session.createAgents.contains(where: { $0.id == agentID }) {
                    agentID = session.createAgents.first?.id ?? "zed-agent"
                }
            }
        }
    }
}

private struct SessionRow: View {
    let thread: NativeThread
    private var busy: Bool { thread.status != "Idle" }

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: busy ? "waveform" : "bubble.left")
                .font(.subheadline).foregroundStyle(busy ? ZLTheme.focus : ZLTheme.muted).frame(width: 20)
            VStack(alignment: .leading, spacing: 5) {
                Text(thread.title).font(.body.weight(.medium)).foregroundStyle(.primary).lineLimit(2)
                HStack(spacing: 7) {
                    Circle().fill(busy ? ZLTheme.focus : ZLTheme.healthy).frame(width: 6, height: 6)
                    Text(busy ? "Working" : "Ready").font(.caption.monospaced()).foregroundStyle(ZLTheme.muted)
                    Text("·").foregroundStyle(ZLTheme.muted)
                    Text(String(thread.id.prefix(8))).font(.caption2.monospaced()).foregroundStyle(ZLTheme.muted)
                }
            }
            Spacer(minLength: 8)
            Image(systemName: "chevron.right").font(.caption.weight(.semibold)).foregroundStyle(ZLTheme.muted)
        }
        .padding(.horizontal, 16).padding(.vertical, 14)
        .contentShape(Rectangle())
    }
}

struct ConversationView: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var session: SessionManager
    let threadID: String
    @State private var showingClearConfirmation = false
    @State private var showingCommands = false
    @State private var showingRename = false
    @State private var showingUnexposeConfirmation = false
    @State private var proposedTitle = ""
    @FocusState private var composerFocused: Bool

    var body: some View {
        VStack(spacing: 0) {
            if let snapshot = session.snapshot, snapshot.threadID == threadID {
                conversation(snapshot)
                if !snapshot.pendingApprovals.isEmpty { approvalStack(snapshot.pendingApprovals) }
            } else {
                ContentUnavailableView("Loading native thread", systemImage: "bubble.left")
                    .frame(maxHeight: .infinity)
            }
        }
        .background(ZLTheme.background)
        .safeAreaInset(edge: .bottom, spacing: 0) { composer }
        .navigationTitle(session.snapshot?.title ?? "Agent thread")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) { ConnectionStatusView(state: session.state) }
            ToolbarItem(placement: .topBarTrailing) {
                Menu {
                    Button("Rename session", systemImage: "pencil") {
                        proposedTitle = session.snapshot?.title ?? ""
                        showingRename = true
                    }
                    .disabled(!session.capabilities.contains("thread.rename"))
                    Button("Stop exposing", systemImage: "eye.slash", role: .destructive) {
                        showingUnexposeConfirmation = true
                    }
                    .disabled(!session.capabilities.contains("thread.unexpose"))
                } label: { Image(systemName: "ellipsis.circle") }
                .accessibilityLabel("Session actions")
            }
        }
        .task(id: threadID) { await session.select(threadID) }
        .onDisappear { composerFocused = false }
        .sheet(isPresented: $showingCommands) { CommandPicker() }
        .confirmationDialog("Clear uncertain delivery?", isPresented: $showingClearConfirmation) {
            Button("Clear locally", role: .destructive) { session.clearPending() }
        } message: {
            Text("Inspect the desktop transcript first. Clearing this record does not cancel a native turn.")
        }
        .alert("Rename session", isPresented: $showingRename) {
            TextField("Session title", text: $proposedTitle)
            Button("Cancel", role: .cancel) {}
            Button("Rename") { Task { _ = await session.renameSelectedThread(to: proposedTitle) } }
                .disabled(proposedTitle.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        } message: { Text("The title also changes in desktop Zed.") }
        .confirmationDialog("Stop exposing this session?", isPresented: $showingUnexposeConfirmation) {
            Button("Stop exposing", role: .destructive) {
                Task { if await session.unexposeSelectedThread() { dismiss() } }
            }
        } message: { Text("The Agent keeps running in desktop Zed. Remote access to this session stops.") }
    }

    private func conversation(_ snapshot: ThreadSnapshot) -> some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 0) {
                    threadMeta(snapshot)
                    if snapshot.hasOlderEntries {
                        Button("Load earlier conversation · \(snapshot.entryStartIndex) remaining") {
                            Task { await session.loadEarlierHistory() }
                        }
                        .font(.footnote).foregroundStyle(ZLTheme.muted)
                        .padding(.horizontal, 16).padding(.vertical, 12)
                    }
                    ForEach(Array(snapshot.entries.enumerated()).map {
                        IndexedTranscriptEntry(id: snapshot.entryStartIndex + $0.offset, markdown: $0.element)
                    }) { entry in
                        NativeMessageView(
                            message: NativeEntryPresentation(entry.markdown, index: entry.id),
                            thinkingLive: snapshot.isBusy && entry.id == snapshot.totalEntries - 1
                        )
                            .id(entry.id)
                        Hairline().padding(.horizontal, 14)
                    }
                    Color.clear.frame(height: 1).id("conversation-bottom")
                }
            }
            .defaultScrollAnchor(.bottom)
            .scrollDismissesKeyboard(.interactively)
            .onChange(of: snapshot.lastSequence) { _, _ in
                withAnimation(.easeOut(duration: 0.18)) { proxy.scrollTo("conversation-bottom", anchor: .bottom) }
            }
        }
    }

    private func threadMeta(_ snapshot: ThreadSnapshot) -> some View {
        HStack(spacing: 8) {
            Circle().fill(snapshot.isBusy ? ZLTheme.focus : ZLTheme.healthy).frame(width: 7, height: 7)
            Text(snapshot.isBusy ? "ZED IS WORKING" : "NATIVE THREAD READY")
                .font(.caption2.monospaced().weight(.semibold)).tracking(0.8)
            Spacer()
            Text("\(snapshot.entries.count) / \(snapshot.totalEntries)")
                .font(.caption2.monospaced()).foregroundStyle(ZLTheme.muted)
        }
        .foregroundStyle(snapshot.isBusy ? ZLTheme.focus : ZLTheme.healthy)
        .padding(.horizontal, 16).padding(.vertical, 9)
        .background(ZLTheme.surface)
        .overlay(alignment: .bottom) { Hairline() }
    }

    private func approvalStack(_ approvals: [NativeApproval]) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 10) {
                ForEach(approvals) { NativeApprovalView(approval: $0) }
            }
            .padding(.horizontal, 12).padding(.vertical, 9)
        }
        .background(ZLTheme.warning.opacity(0.07))
        .overlay(alignment: .top) { Hairline() }
    }

    private var composer: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let snapshot = session.snapshot, snapshot.threadID == threadID, snapshot.isBusy {
                agentProgress(snapshot)
            }
            if !session.delivery.isEmpty {
                Text(session.delivery).font(.caption).foregroundStyle(ZLTheme.muted)
                    .lineLimit(2).accessibilityIdentifier("delivery-status")
            }
            if session.pending != nil { uncertainDelivery }
            HStack(alignment: .bottom, spacing: 8) {
                Button { showingCommands = true } label: {
                    Image(systemName: "slash.circle").font(.title3).frame(width: 42, height: 42)
                }
                .foregroundStyle(.primary)
                .accessibilityLabel("Zed Agent actions and commands")

                TextField("Message Zed Agent…", text: $session.draft, axis: .vertical)
                    .lineLimit(1...6).padding(.horizontal, 11).padding(.vertical, 10)
                    .background(ZLTheme.surface)
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(ZLTheme.line, lineWidth: 1))
                    .focused($composerFocused)
                    .submitLabel(.send)
                    .onSubmit { sendAndDismissKeyboard() }
                    .accessibilityLabel("Message to native Zed Agent")
                    .accessibilityIdentifier("composer")

                if session.canCancel {
                    Button { composerFocused = false; Task { await session.cancelCurrentTurn() } } label: {
                        Image(systemName: "stop.fill").font(.headline).frame(width: 42, height: 42)
                    }
                    .foregroundStyle(.white).background(ZLTheme.danger)
                    .clipShape(Circle())
                    .accessibilityLabel("Stop current turn").accessibilityIdentifier("stop-current-turn")
                } else {
                    Button { sendAndDismissKeyboard() } label: {
                        Image(systemName: "arrow.up").font(.headline).frame(width: 42, height: 42)
                    }
                    .foregroundStyle(ZLTheme.background).background(ZLTheme.ink)
                    .clipShape(Circle())
                    .disabled(!session.canSend || session.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    .accessibilityLabel("Send").accessibilityIdentifier("send-prompt")
                }
            }
        }
        .padding(.horizontal, 10).padding(.top, 9).padding(.bottom, 8)
        .background(ZLTheme.background)
        .overlay(alignment: .top) { Hairline() }
        .toolbar {
            ToolbarItemGroup(placement: .keyboard) {
                Spacer()
                Button("Done") { composerFocused = false }
            }
        }
    }

    private func agentProgress(_ snapshot: ThreadSnapshot) -> some View {
        HStack(spacing: 10) {
            ProgressView().controlSize(.small).tint(ZLTheme.focus)
            VStack(alignment: .leading, spacing: 2) {
                Text("Zed Agent is working").font(.caption.weight(.semibold))
                Text(progressDetail(snapshot.status)).font(.caption2.monospaced()).foregroundStyle(ZLTheme.muted)
            }
            Spacer(minLength: 8)
            Text(session.canCancel ? "STOP AVAILABLE" : "LIVE")
                .font(.caption2.monospaced().weight(.semibold)).foregroundStyle(ZLTheme.focus)
        }
        .padding(.horizontal, 11).padding(.vertical, 8)
        .background(ZLTheme.focus.opacity(0.07))
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(ZLTheme.focus.opacity(0.28), lineWidth: 1))
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("agent-working-indicator")
    }

    private func progressDetail(_ status: String) -> String {
        if status.localizedCaseInsensitiveContains("generat") { return "Generating in desktop Zed" }
        if status.localizedCaseInsensitiveContains("tool") || status.localizedCaseInsensitiveContains("run") { return "Running native tools" }
        if status.localizedCaseInsensitiveContains("wait") || status.localizedCaseInsensitiveContains("queue") { return "Waiting in desktop Zed" }
        return "\(status) in desktop Zed"
    }

    private func sendAndDismissKeyboard() {
        guard session.canSend, !session.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        composerFocused = false
        Task { await session.send() }
    }

    private var uncertainDelivery: some View {
        HStack(spacing: 14) {
            Text("Delivery needs review").font(.caption.monospaced()).foregroundStyle(ZLTheme.warning)
            Spacer()
            Button("Check") { Task { await session.reconcilePending() } }
                .accessibilityIdentifier("check-request-status")
            if session.pending?.text != nil {
                Button("Retry") { Task { await session.retryPending() } }
                    .accessibilityIdentifier("retry-same-request")
            }
            Button("Clear") { showingClearConfirmation = true }
        }
        .font(.caption)
    }
}

private struct IndexedTranscriptEntry: Identifiable {
    let id: Int
    let markdown: String
}

private struct ActivityPanel: View {
    let snapshot: ThreadSnapshot
    @Binding var expanded: Bool

    private var items: [NativeEntryPresentation] {
        snapshot.activityEntries.enumerated().map { NativeEntryPresentation($0.element, index: $0.offset) }
    }
    private var reasoning: [String] { items.flatMap(\.reasoning) }
    private var tools: [NativeEntryPresentation] { items.filter { $0.kind == .tool } }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button { withAnimation(.easeInOut(duration: 0.16)) { expanded.toggle() } } label: {
                HStack(spacing: 8) {
                    Image(systemName: snapshot.isBusy ? "waveform" : "clock.arrow.circlepath")
                        .foregroundStyle(snapshot.isBusy ? ZLTheme.focus : ZLTheme.muted)
                    Text(snapshot.isBusy ? "Zed is working" : "Recent activity").font(.subheadline.weight(.semibold))
                    Spacer()
                    Text(snapshot.isBusy ? "LIVE" : "DONE").font(.caption2.monospaced())
                        .foregroundStyle(snapshot.isBusy ? ZLTheme.focus : ZLTheme.muted)
                    Image(systemName: expanded ? "chevron.up" : "chevron.down").font(.caption)
                }
                .padding(11).contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            if expanded {
                Hairline()
                VStack(alignment: .leading, spacing: 12) {
                    if reasoning.isEmpty && tools.isEmpty {
                        Text("Waiting for reasoning or tool activity shared by native Zed…")
                            .font(.footnote).foregroundStyle(ZLTheme.muted)
                    }
                    ForEach(Array(reasoning.enumerated()), id: \.offset) { _, value in
                        VStack(alignment: .leading, spacing: 5) {
                            SectionLabel("Reasoning shared by Zed")
                            NativeMarkdownView(markdown: value)
                        }
                    }
                    ForEach(tools) { tool in
                        HStack {
                            Image(systemName: "wrench.and.screwdriver")
                            Text(tool.toolName ?? "Zed tool").lineLimit(1)
                            Spacer()
                            Text(tool.toolStatus ?? "Updated").font(.caption.monospaced()).foregroundStyle(ZLTheme.muted)
                        }
                        .font(.footnote)
                    }
                    if snapshot.activityTruncated {
                        Text("Earlier activity is omitted from this live window.")
                            .font(.caption).foregroundStyle(ZLTheme.muted)
                    }
                }
                .padding(12)
            }
        }
        .background(ZLTheme.surface)
        .overlay(Rectangle().stroke(ZLTheme.line, lineWidth: 1))
        .accessibilityIdentifier("live-activity")
    }
}

private struct NativeMessageView: View {
    let message: NativeEntryPresentation
    let thinkingLive: Bool

    var body: some View {
        switch message.kind {
        case .user:
            HStack {
                Spacer(minLength: 42)
                VStack(alignment: .leading, spacing: 7) {
                    SectionLabel(message.label)
                    NativeMarkdownView(markdown: message.body)
                }
                .padding(.horizontal, 14).padding(.vertical, 11)
                .background(ZLTheme.raised)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            }
            .padding(.horizontal, 14).padding(.vertical, 12)
        case .tool:
            ToolMessageView(message: message).padding(.horizontal, 14).padding(.vertical, 10)
        default:
            VStack(alignment: .leading, spacing: 10) {
                SectionLabel(message.label)
                ForEach(Array(message.reasoning.enumerated()), id: \.offset) { _, thought in
                    ThinkingDisclosure(thought: thought, live: thinkingLive)
                }
                if !message.body.isEmpty { NativeMarkdownView(markdown: message.body) }
            }
            .padding(.horizontal, 16).padding(.vertical, 14)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

private struct ThinkingDisclosure: View {
    let thought: String
    let live: Bool
    @State private var expanded: Bool

    init(thought: String, live: Bool) {
        self.thought = thought
        self.live = live
        _expanded = State(initialValue: live)
    }

    var body: some View {
        DisclosureGroup(isExpanded: $expanded) {
            NativeMarkdownView(markdown: thought).padding(.top, 8)
        } label: {
            HStack(spacing: 7) {
                if live {
                    ProgressView().controlSize(.mini).tint(ZLTheme.focus)
                }
                Text(live ? "Thinking" : "Thinking · complete")
            }
        }
        .font(.footnote)
        .tint(ZLTheme.muted)
        .padding(.vertical, 8)
        .padding(.horizontal, 10)
        .background(ZLTheme.surface)
        .overlay(alignment: .leading) { Rectangle().fill(ZLTheme.line).frame(width: 2) }
        .onChange(of: live) { _, active in if active { expanded = true } }
    }
}

private struct ToolMessageView: View {
    let message: NativeEntryPresentation
    @State private var expanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            Button { expanded.toggle() } label: {
                HStack(spacing: 9) {
                    Image(systemName: "terminal").foregroundStyle(ZLTheme.muted)
                    VStack(alignment: .leading, spacing: 3) {
                        Text(message.toolName ?? "Zed tool").font(.subheadline.weight(.medium)).lineLimit(2)
                        Text(message.toolStatus ?? "Native tool activity")
                            .font(.caption.monospaced()).foregroundStyle(ZLTheme.muted)
                    }
                    Spacer()
                    Image(systemName: expanded ? "chevron.up" : "chevron.down").font(.caption)
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            if expanded { Hairline(); NativeMarkdownView(markdown: message.body) }
        }
        .padding(12).background(ZLTheme.surface)
        .overlay(Rectangle().stroke(ZLTheme.line, lineWidth: 1))
    }
}

private struct NativeApprovalView: View {
    let approval: NativeApproval
    @State private var expanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: "hand.raised.fill").foregroundStyle(ZLTheme.warning)
                Text("NEEDS YOU").font(.caption2.monospaced().weight(.bold)).foregroundStyle(ZLTheme.warning)
                Spacer()
            }
            Text(approval.display).font(.subheadline.weight(.medium)).lineLimit(expanded ? nil : 2)
            Text(approval.toolName).font(.caption.monospaced()).foregroundStyle(ZLTheme.muted)
            if let input = approval.rawInput, expanded {
                ScrollView(.horizontal, showsIndicators: false) {
                    Text(input).font(.caption.monospaced()).textSelection(.enabled)
                }
            }
            Button(expanded ? "Hide details" : "Review details") { expanded.toggle() }.font(.caption)
            Text("Decide in desktop Zed").font(.caption2).foregroundStyle(ZLTheme.muted)
        }
        .padding(12).frame(width: 290, alignment: .leading)
        .background(ZLTheme.surface).overlay(Rectangle().stroke(ZLTheme.warning.opacity(0.45), lineWidth: 1))
        .accessibilityIdentifier("approval-unavailable")
    }
}

private struct CommandPicker: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var session: SessionManager
    @State private var search = ""

    private var commands: [NativeCommand] {
        guard !search.isEmpty else { return session.commands }
        return session.commands.filter { $0.name.localizedCaseInsensitiveContains(search) ||
            $0.description.localizedCaseInsensitiveContains(search) }
    }

    var body: some View {
        NavigationStack {
            List {
                Section("Agent actions") {
                    Button {
                        session.prepareSubagentTask()
                        dismiss()
                    } label: {
                        Label("Delegate a parallel task", systemImage: "arrow.triangle.branch")
                    }
                    .accessibilityIdentifier("delegate-subagent-task")
                }
                Section("Slash commands") {
                    if commands.isEmpty {
                        Text("No slash commands are advertised by this thread.").foregroundStyle(.secondary)
                    }
                    ForEach(commands) { command in
                        Button {
                            session.insertCommand(command)
                            dismiss()
                        } label: {
                            VStack(alignment: .leading, spacing: 5) {
                                HStack {
                                    Text("/\(command.name)").font(.body.monospaced().weight(.semibold))
                                    Spacer()
                                    Text(command.category.uppercased()).font(.caption2.monospaced()).foregroundStyle(ZLTheme.muted)
                                }
                                Text(command.description).font(.footnote).foregroundStyle(.secondary)
                            }
                            .padding(.vertical, 4)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .scrollContentBackground(.hidden).background(ZLTheme.background)
            .searchable(text: $search, prompt: "Search Zed commands")
            .navigationTitle("Agent commands")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Done") { dismiss() } } }
        }
        .presentationDetents([.medium, .large])
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
                        Text("No connections").font(.headline)
                        Text("Scan the private pairing QR shown by your ZedLink workstation.")
                            .font(.subheadline).foregroundStyle(ZLTheme.muted)
                    }
                    .listRowBackground(ZLTheme.surface).padding(.vertical, 8)
                }
                ForEach(profiles.profiles) { profile in
                    VStack(alignment: .leading, spacing: 9) {
                        HStack {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(profile.name).font(.headline)
                                Text(profile.route.rawValue.uppercased()).font(.caption2.monospaced()).foregroundStyle(ZLTheme.muted)
                            }
                            Spacer()
                            if session.profile?.id == profile.id { ConnectionStatusView(state: session.state) }
                        }
                        Text(profile.endpoint).font(.caption.monospaced()).foregroundStyle(ZLTheme.muted)
                            .textSelection(.enabled)
                        HStack {
                            Button(session.profile?.id == profile.id ? "Reconnect" : "Connect") {
                                Task {
                                    await session.connect(profile)
                                    if session.state == .live { profiles.markUsed(profile) }
                                }
                            }
                            .accessibilityIdentifier("connect-\(profile.id)")
                            Spacer()
                            Button("Forget", role: .destructive) { profileToForget = profile }
                        }
                        .font(.subheadline)
                    }
                    .padding(.vertical, 7).listRowBackground(ZLTheme.surface)
                }
            }
            .scrollContentBackground(.hidden).background(ZLTheme.background)
            .navigationTitle("Connections")
            .toolbar {
                Button { showingAdd = true } label: { Image(systemName: "plus") }
                    .accessibilityLabel("Add connection").accessibilityIdentifier("add-connection")
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
    @State private var showingScanner = false

    private var candidate: ConnectionProfile {
        ConnectionProfile(name: name.trimmingCharacters(in: .whitespacesAndNewlines), route: route,
                          endpoint: endpoint.trimmingCharacters(in: .whitespacesAndNewlines),
                          gatewayID: expectedID.trimmingCharacters(in: .whitespacesAndNewlines))
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Quick setup") {
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
                Section("Route") {
                    Picker("Connection type", selection: $route) {
                        ForEach(RouteKind.allCases) { Text($0.rawValue).tag($0) }
                    }
                    Text(route.guidance).font(.footnote).foregroundStyle(.secondary)
                }
                Section("Gateway") {
                    TextField("Name", text: $name)
                    TextField("https://hostname:port", text: $endpoint)
                        .textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL)
                        .accessibilityIdentifier("gateway-endpoint")
                    Button("Test HTTPS endpoint") { Task { await testEndpoint() } }
                        .disabled(busy).accessibilityIdentifier("test-connection")
                    if !observedID.isEmpty { LabeledContent("Observed gateway ID", value: observedID).textSelection(.enabled) }
                    TextField("Expected gateway ID from workstation", text: $expectedID)
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                        .accessibilityIdentifier("expected-gateway-id")
                }
                Section("Pair this iPhone") {
                    TextField("Device name", text: $deviceName)
                    SecureField("10-digit pairing code", text: $code)
                        .textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.numberPad)
                        .accessibilityIdentifier("pairing-code")
                    Text("The observed identity must match before the one-use code is sent.")
                        .font(.footnote).foregroundStyle(.secondary)
                    Button("Pair and save") { Task { await pair() } }
                        .disabled(busy || observedID.isEmpty || expectedID.isEmpty || code.isEmpty)
                        .accessibilityIdentifier("pair-and-save")
                }
                if !issue.isEmpty { Section("Connection diagnostic") { Text(issue).foregroundStyle(ZLTheme.warning) } }
            }
            .navigationTitle("Add connection")
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Done") { dismiss() } } }
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
        busy = true; defer { busy = false }; observedID = ""
        do {
            observedID = try await GatewayClient(profile: candidate, token: nil).gatewayID()
            issue = "HTTPS and gateway identity verified."
        } catch { issue = error.localizedDescription }
    }

    private func pair() async {
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
            try await CredentialVault.shared.write(paired.token, for: profile.id)
            code = ""
            profiles.save(profile)
            await session.connect(profile)
            dismiss()
        } catch { issue = error.localizedDescription }
    }
}

struct SettingsView: View {
    @AppStorage("zedlink.appearance") private var appearance = "dark"

    var body: some View {
        NavigationStack {
            List {
                Section("Appearance") {
                    Picker("Theme", selection: $appearance) {
                        Text("OLED dark").tag("dark")
                        Text("System").tag("system")
                        Text("Light").tag("light")
                    }
                }
                Section("Native runtime") {
                    LabeledContent("Protocol", value: "ZedLink v1")
                    Text("Your model, tools, MCP servers, permissions, and conversation remain inside native Zed.")
                }
                Section("Capability boundary") {
                    Text("ZedLink shows native tool and terminal output, but does not expose an unrestricted remote shell.")
                    Text("Files and Git changes appear only after the running adapter advertises scoped read-only capabilities.")
                    Text("Tailscale or another private route still requires verified HTTPS and device pairing.")
                }
            }
            .scrollContentBackground(.hidden).background(ZLTheme.background)
            .navigationTitle("Settings")
        }
    }
}
