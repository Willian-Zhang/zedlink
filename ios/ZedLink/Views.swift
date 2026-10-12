import AVFoundation
import SwiftUI
import CoreText
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
    @State private var showingContext = false
    @State private var proposedTitle = ""
    @State private var rewindPoint: NativeRewindPoint?
    @FocusState private var composerFocused: Bool

    var body: some View {
        VStack(spacing: 0) {
            if let snapshot = session.snapshot, snapshot.threadID == threadID {
                conversation(snapshot)
                if !snapshot.pendingApprovals.isEmpty { approvalStack(snapshot.pendingApprovals) }
                if !session.elicitations.isEmpty { elicitationStack }
                if session.editReview != nil || !session.queuedMessages.isEmpty { nativeControls }
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
            ToolbarItem(placement: .topBarTrailing) { Button { showingContext = true } label: { Image(systemName: "doc.text.magnifyingglass") } }
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
        .sheet(isPresented: $showingContext) { NativeContextSheet() }
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
        .confirmationDialog("Rewind this conversation?", isPresented: Binding(
            get: { rewindPoint != nil }, set: { if !$0 { rewindPoint = nil } }
        )) {
            Button("Rewind", role: .destructive) {
                if let point = rewindPoint { Task { await session.rewind(to: point) } }
                rewindPoint = nil
            }
        } message: { Text("Messages and Agent edits after this point may be removed.") }
    }

    private func conversation(_ snapshot: ThreadSnapshot) -> some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 0) {
                    threadMeta(snapshot)
                    ForEach(snapshot.subagents) { subagent in
                        DisclosureGroup("\(subagent.title) · \(subagent.status)") {
                            ForEach(Array(subagent.entries.enumerated()), id: \.offset) { _, entry in
                                Text(entry).font(.caption.monospaced()).textSelection(.enabled).padding(.vertical, 4)
                            }
                            if subagent.currentTurnID != nil {
                                Button("Stop parallel agent", role: .destructive) { Task { await session.cancelSubagent(subagent) } }
                            }
                        }.padding(12).background(ZLTheme.surface)
                    }
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
                        VStack(alignment: .leading, spacing: 0) {
                            NativeMessageView(
                                message: NativeEntryPresentation(entry.markdown, index: entry.id),
                                thinkingLive: snapshot.isBusy && entry.id == snapshot.totalEntries - 1
                            )
                            if !snapshot.isBusy, session.capabilities.contains("thread.rewind"),
                               let point = snapshot.rewindPoints.first(where: { $0.entryIndex == entry.id }) {
                                Button("Rewind conversation here", role: .destructive) { rewindPoint = point }
                                .font(.caption).padding(.horizontal, 16).padding(.bottom, 8)
                            }
                        }
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

    private var elicitationStack: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 10) {
                ForEach(session.elicitations) { NativeElicitationView(elicitation: $0) }
            }.padding(.horizontal, 12).padding(.vertical, 9)
        }
        .background(ZLTheme.warning.opacity(0.07))
        .overlay(alignment: .top) { Hairline() }
    }

    private var nativeControls: some View {
        VStack(spacing: 8) {
            if let review = session.editReview {
                HStack {
                    VStack(alignment: .leading) {
                        Text("Review Agent edits").font(.subheadline.weight(.semibold))
                        Text("\(review.changedFiles) files · +\(review.linesAdded) −\(review.linesRemoved)")
                            .font(.caption.monospaced()).foregroundStyle(ZLTheme.muted)
                    }
                    Spacer()
                    Button("Reject all", role: .destructive) { Task { await session.resolveEditReview("reject_all") } }
                    Button("Keep all") { Task { await session.resolveEditReview("keep_all") } }
                }
            }
            if !session.queuedMessages.isEmpty {
                HStack {
                    Text("\(session.queuedMessages.count) queued message\(session.queuedMessages.count == 1 ? "" : "s")")
                    Spacer()
                    Button("Clear queue", role: .destructive) { Task { await session.clearQueue() } }
                }.font(.footnote)
            }
        }
        .padding(12).background(ZLTheme.surface).overlay(alignment: .top) { Hairline() }
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

private struct NativeContextSheet: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var session: SessionManager
    @State private var terminalInput = ""
    @State private var showingTerminal = false
    var body: some View {
        NavigationStack {
            List {
                if !session.previewContent.isEmpty {
                    Section(session.previewTitle) { Text(session.previewContent).font(.caption.monospaced()).textSelection(.enabled) }
                }
                Section("Project files") {
                    ForEach(session.projectFiles.filter { $0.kind == "file" }) { file in
                        HStack { Button(file.id) { Task { await session.previewFile(file.id) } }; Spacer()
                            Button(session.contextPaths.contains(file.id) ? "Attached" : "Attach") {
                                if session.contextPaths.contains(file.id) { session.contextPaths.remove(file.id) } else { session.contextPaths.insert(file.id) }
                            }.disabled(session.contextPaths.contains(file.id))
                        }
                    }
                }
                Section("Git changes") {
                    Button("Load full diff") { Task { await session.loadDiff() } }
                    ForEach(session.changes) { change in
                        HStack { VStack(alignment: .leading) { Text(change.id); Text("\(change.status) · \(change.staging)").font(.caption) }; Spacer()
                            Button(change.staging == "staged" ? "Unstage" : "Stage") { Task { await session.mutateChange(change) } }
                        }
                    }
                }
                if session.capabilities.contains("task.catalog") {
                    Section("Run configured task") {
                    if session.configuredTasks.isEmpty {
                        Text("No configured Zed tasks are available for this project.").foregroundStyle(.secondary)
                    }
                    ForEach(session.configuredTasks) { task in
                        Button {
                            Task { await session.runConfiguredTask(task) }
                        } label: {
                            HStack { Text(task.label); Spacer(); Text(task.source.uppercased()).font(.caption.monospaced()).foregroundStyle(.secondary) }
                        }
                        .disabled(!session.capabilities.contains("task.run"))
                    }
                    }
                }
                Section("Zed terminals") {
                    if session.terminalSnapshot != nil { Button("Open full-screen terminal", systemImage: "arrow.up.left.and.arrow.down.right") { showingTerminal = true } }
                    if !session.capabilities.contains("terminal.list") {
                        Text("Enable View Project Terminals in ZedLink settings. Changes apply without restarting Zed.")
                            .font(.caption).foregroundStyle(.secondary)
                    } else if session.terminals.isEmpty {
                        Text("No terminal is open for this project in Zed.").foregroundStyle(.secondary)
                    }
                    if !session.terminals.isEmpty {
                        Menu {
                            ForEach(session.terminals) { terminal in
                                Button(terminal.title) { Task { await session.loadTerminal(terminal) } }
                            }
                        } label: {
                            HStack {
                                Image(systemName: "terminal")
                                Text(session.terminalSnapshot?.terminal.title ?? "Choose terminal")
                                    .lineLimit(1)
                                Spacer()
                                Text(session.capabilities.contains("terminal.input") ? "Interactive" : "Read only")
                                    .font(.caption.monospaced())
                                    .foregroundStyle(session.capabilities.contains("terminal.input") ? ZLTheme.healthy : ZLTheme.warning)
                            }
                        }
                    }
                    if let snapshot = session.terminalSnapshot {
                        VStack(spacing: 0) {
                            HStack(spacing: 8) {
                                Circle().fill(ZLTheme.healthy).frame(width: 7, height: 7)
                                Text(snapshot.terminal.title).font(.caption.monospaced()).lineLimit(1)
                                Spacer()
                                if snapshot.terminal.taskState == "running" && session.capabilities.contains("task.stop") {
                                    Button("Stop", role: .destructive) { Task { await session.stopTerminalTask() } }
                                        .font(.caption)
                                }
                            }
                            .padding(.horizontal, 11).frame(minHeight: 40)
                            .background(Color(red: 0.03, green: 0.035, blue: 0.04))
                            ScrollView([.horizontal, .vertical]) {
                                terminalText(snapshot)
                                    .font(.system(size: 12, design: .monospaced))
                                    .foregroundStyle(Color(red: 0.85, green: 0.88, blue: 0.86))
                                    .textSelection(.enabled).fixedSize(horizontal: true, vertical: true)
                                    .frame(maxWidth: .infinity, minHeight: 260, alignment: .topLeading)
                                    .padding(13)
                            }
                            .frame(height: 300)
                            .background(Color(red: 0.005, green: 0.008, blue: 0.008))
                        }
                        .overlay(Rectangle().stroke(ZLTheme.line, lineWidth: 1))
                        if session.capabilities.contains("terminal.input") {
                            HStack {
                                Text("›").font(.body.monospaced()).foregroundStyle(ZLTheme.healthy)
                                TextField("Type into this Zed terminal", text: $terminalInput)
                                    .textInputAutocapitalization(.never).autocorrectionDisabled()
                                    .font(.callout.monospaced()).textFieldStyle(.plain)
                                    .onSubmit { sendTerminalInput() }
                                Button { sendTerminalInput() } label: { Image(systemName: "arrow.up") }
                                    .buttonStyle(.borderedProminent).disabled(terminalInput.isEmpty)
                            }
                            .padding(9).background(Color(red: 0.03, green: 0.035, blue: 0.04))
                            .overlay(Rectangle().stroke(ZLTheme.line, lineWidth: 1))
                        } else {
                            Label("Read only · Enable Send Terminal Input in ZedLink settings to type here.", systemImage: "lock")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
                Section("Debugger") {
                    if !session.capabilities.contains("debugger.catalog") {
                        Text("Enable Start Configured Debuggers in desktop ZedLink settings and restart patched Zed.")
                            .font(.caption).foregroundStyle(.secondary)
                    } else if session.debuggerCatalog.isEmpty {
                        Text("No configured Zed debuggers are available for this project.").foregroundStyle(.secondary)
                    }
                    ForEach(session.debuggerCatalog) { scenario in
                        Button {
                            Task { await session.launchDebugger(scenario) }
                        } label: {
                            HStack { Text(scenario.label); Spacer(); Text(scenario.adapter.uppercased()).font(.caption.monospaced()).foregroundStyle(.secondary) }
                        }
                        .disabled(!session.capabilities.contains("debugger.launch"))
                    }
                    if !session.capabilities.contains("debugger.snapshot") {
                        Text("Enable View Debugger Sessions in desktop ZedLink settings and restart patched Zed.")
                            .font(.caption).foregroundStyle(.secondary)
                    } else if session.debuggerSessions.isEmpty {
                        Text("No debugger session is running in this Zed project.").foregroundStyle(.secondary)
                    }
                    ForEach(session.debuggerSessions) { debugger in
                        VStack(alignment: .leading, spacing: 8) {
                            HStack {
                                VStack(alignment: .leading) {
                                    Text(debugger.label)
                                    Text(debugger.adapter).font(.caption.monospaced()).foregroundStyle(.secondary)
                                }
                                Spacer()
                                if !debugger.terminated {
                                    Menu("Session") {
                                        if debugger.canRestart {
                                            Button("Restart") { Task { await session.controlDebugger(debugger, action: "restart") } }
                                        }
                                        Button("Stop", role: .destructive) { Task { await session.controlDebugger(debugger, action: "stop") } }
                                    }.disabled(!session.capabilities.contains("debugger.control"))
                                }
                            }
                            ForEach(debugger.threads) { thread in
                                HStack {
                                    VStack(alignment: .leading) {
                                        Text(thread.name)
                                        Text(thread.status.uppercased()).font(.caption.monospaced()).foregroundStyle(.secondary)
                                    }
                                    Spacer()
                                    Menu("Controls") {
                                        if thread.status == "running" {
                                            Button("Pause") { Task { await session.controlDebugger(debugger, action: "pause", thread: thread) } }
                                        } else if thread.status == "stopped" {
                                            Button("Continue") { Task { await session.controlDebugger(debugger, action: "continue", thread: thread) } }
                                            Button("Step over") { Task { await session.controlDebugger(debugger, action: "step_over", thread: thread) } }
                                            Button("Step into") { Task { await session.controlDebugger(debugger, action: "step_in", thread: thread) } }
                                            Button("Step out") { Task { await session.controlDebugger(debugger, action: "step_out", thread: thread) } }
                                            if debugger.canStepBack {
                                                Button("Step back") { Task { await session.controlDebugger(debugger, action: "step_back", thread: thread) } }
                                            }
                                        }
                                    }.disabled(!session.capabilities.contains("debugger.control"))
                                }
                            }
                        }
                    }
                }
            }
            .navigationTitle("Project context").toolbar { Button("Done") { dismiss() } }
            .sheet(isPresented: $showingTerminal) { NativeTerminalScreen() }
            .task {
                await session.loadProjectContext()
                while !Task.isCancelled {
                    try? await Task.sleep(for: .milliseconds(1500))
                    if let terminal = session.terminalSnapshot?.terminal { await session.loadTerminal(terminal) }
                }
            }
        }
    }

    private func sendTerminalInput() {
        let value = terminalInput
        guard !value.isEmpty else { return }
        terminalInput = ""
        Task { await session.sendTerminalInput(value) }
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
    @EnvironmentObject private var session: SessionManager
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
            Text(approval.authorizationKind == "action_choice" ? "Choose an action" : "Permission requested")
                .font(.caption2.monospaced()).foregroundStyle(ZLTheme.warning)
            if approval.decisions.isEmpty {
                Text("Update patched Zed to resolve this request remotely.")
                    .font(.caption2).foregroundStyle(ZLTheme.muted)
            } else {
                ForEach(approval.decisions) { decision in
                    Button {
                        Task { await session.respond(to: approval, with: decision) }
                    } label: {
                        Text(decision.displayLabel)
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(decision.isRejecting ? ZLTheme.warning : ZLTheme.focus)
                    .disabled(approval.detailsTruncated && (!decision.isRejecting || approval.authorizationKind == "action_choice"))
                }
            }
        }
        .padding(12).frame(width: 290, alignment: .leading)
        .background(ZLTheme.surface).overlay(Rectangle().stroke(ZLTheme.warning.opacity(0.45), lineWidth: 1))
        .accessibilityIdentifier("native-approval")
    }
}

private struct NativeElicitationView: View {
    @EnvironmentObject private var session: SessionManager
    let elicitation: NativeElicitation
    @State private var values: [String: String] = [:]
    @State private var flags: Set<String> = []

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("INPUT REQUESTED").font(.caption2.monospaced().weight(.semibold)).foregroundStyle(ZLTheme.warning)
            Text(elicitation.message).font(.subheadline.weight(.semibold))
            if let url = elicitation.url, let destination = URL(string: url) {
                Link("Open secure input page", destination: destination)
            }
            ForEach(elicitation.fields) { field in
                if field.type == "boolean" {
                    Toggle(field.title, isOn: Binding(
                        get: { flags.contains(field.id) },
                        set: { enabled in if enabled { flags.insert(field.id) } else { flags.remove(field.id) } }
                    ))
                } else if !field.choices.isEmpty {
                    Picker(field.title, selection: Binding(
                        get: { values[field.id] ?? field.choices.first ?? "" },
                        set: { values[field.id] = $0 }
                    )) { ForEach(field.choices, id: \.self) { Text($0).tag($0) } }
                } else {
                    TextField(field.title, text: Binding(
                        get: { values[field.id] ?? "" }, set: { values[field.id] = $0 }
                    )).textFieldStyle(.roundedBorder)
                }
            }
            HStack {
                Button("Decline", role: .destructive) { Task { await session.respondToElicitation(elicitation, action: "decline") } }
                Button("Submit") {
                    var content = Dictionary(uniqueKeysWithValues: values.map { ($0.key, $0.value as Any) })
                    for field in elicitation.fields {
                        if field.type == "boolean" { content[field.id] = flags.contains(field.id) }
                        else if field.type == "integer", let value = Int(values[field.id] ?? "") { content[field.id] = value }
                        else if field.type == "number", let value = Double(values[field.id] ?? "") { content[field.id] = value }
                        else if field.type == "array" { content[field.id] = (values[field.id] ?? "").split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty } }
                    }
                    Task { await session.respondToElicitation(elicitation, action: "accept", content: content) }
                }.buttonStyle(.borderedProminent)
            }
        }
        .padding(14).frame(width: 330, alignment: .leading)
        .background(ZLTheme.surface).overlay(RoundedRectangle(cornerRadius: 12).stroke(ZLTheme.warning.opacity(0.5)))
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
                if let active = session.profile, !session.targets.isEmpty {
                    Section("Zed instances on \(active.name)") {
                        ForEach(session.targets) { target in
                            Button {
                                Task { await session.selectTarget(target.id) }
                            } label: {
                                HStack {
                                    VStack(alignment: .leading, spacing: 3) {
                                        Text(target.label).foregroundStyle(.primary)
                                        Text(target.available ? "Available" : "Unavailable")
                                            .font(.caption).foregroundStyle(target.available ? ZLTheme.healthy : ZLTheme.muted)
                                    }
                                    Spacer()
                                    if session.targetID == target.id { Image(systemName: "checkmark").foregroundStyle(ZLTheme.focus) }
                                }
                            }
                            .disabled(!target.available || session.targetID == target.id)
                            .accessibilityIdentifier("switch-target-\(target.id)")
                        }
                    }
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

    private var savedGateway: ConnectionProfile? {
        profiles.profiles.first {
            $0.gatewayID.caseInsensitiveCompare(expectedID.trimmingCharacters(in: .whitespacesAndNewlines)) == .orderedSame
        }
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
                    if savedGateway != nil {
                        Button("Save as another connection") { Task { await saveExistingRoute() } }
                            .disabled(busy || observedID.isEmpty || observedID.caseInsensitiveCompare(expectedID) != .orderedSame)
                            .accessibilityIdentifier("save-existing-route")
                        Text("This gateway is already paired. Save this address as another connection and reuse its protected Keychain credential.")
                            .font(.footnote).foregroundStyle(.secondary)
                    }
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
        Task { await finishScannedPairing() }
    }

    private func finishScannedPairing() async {
        await testEndpoint()
        guard observedID.caseInsensitiveCompare(expectedID) == .orderedSame else { return }
        if savedGateway != nil, await CredentialVault.shared.read(candidate) != nil {
            await saveExistingRoute()
        } else if !code.isEmpty {
            await pair()
        }
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
            let saved = profiles.save(profile)
            try await CredentialVault.shared.write(paired.token, for: saved)
            code = ""
            await session.connect(saved)
            if session.state == .live {
                profiles.markUsed(saved)
                dismiss()
            } else {
                issue = "Pairing was saved. Connection failed: \(session.issue)"
            }
        } catch { issue = error.localizedDescription }
    }

    private func saveExistingRoute() async {
        busy = true; defer { busy = false }
        let profile = candidate
        guard observedID.caseInsensitiveCompare(profile.gatewayID) == .orderedSame, savedGateway != nil else {
            issue = "Test the new HTTPS address and confirm the same gateway identity first."; return
        }
        let saved = profiles.save(profile)
        guard await CredentialVault.shared.read(saved) != nil else {
            issue = "The saved device credential is missing. Pair this device again once."; return
        }
        await session.connect(saved)
        if session.state == .live {
            profiles.markUsed(saved)
            dismiss()
        } else {
            issue = "Connection was saved. \(session.issue)"
        }
    }
}

struct SettingsView: View {
    @EnvironmentObject private var session: SessionManager
    @AppStorage("zedlink.appearance") private var appearance = "dark"

    var body: some View {
        NavigationStack {
            List {
                if let settings = session.threadSettings {
                    Section("Selected Agent session") {
                        if !settings.models.isEmpty {
                            Picker("Model", selection: Binding(
                                get: { "\(settings.providerID ?? "")\n\(settings.modelID ?? "")" },
                                set: { id in if let option = settings.models.first(where: { $0.id == id }) { Task { await session.selectModel(option) } } }
                            )) {
                                ForEach(settings.models) { Text("\($0.name) · \($0.providerID)").tag($0.id) }
                            }
                        }
                        if let used = settings.usedTokens, let maximum = settings.maxTokens {
                            LabeledContent("Context", value: "\(used.formatted()) / \(maximum.formatted()) tokens")
                        }
                    }
                }
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


private struct NativeTerminalScreen: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var session: SessionManager
    @State private var input = ""
    @State private var sending = false
    @State private var followOutput = true
    @FocusState private var keyboardFocused: Bool
    private let keys: [(String, String)] = [("Esc", "\u{1b}"), ("Tab", "\t"), ("Ctrl C", "\u{03}"), ("↑", "\u{1b}[A"), ("↓", "\u{1b}[B"), ("←", "\u{1b}[D"), ("→", "\u{1b}[C")]

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                HStack {
                    Menu {
                        ForEach(session.terminals) { terminal in
                            Button(terminal.title) { keyboardFocused = false; Task { await session.loadTerminal(terminal) } }
                        }
                    } label: { Text(session.terminalSnapshot?.terminal.title ?? "Choose terminal").lineLimit(1) }.disabled(sending)
                    Spacer()
                    Text(session.capabilities.contains("terminal.input") ? "Interactive" : "Read only").font(.caption)
                    if !followOutput { Button("Latest") { followOutput = true }.font(.caption) }
                    if session.terminalSnapshot?.terminal.taskState == "running" && session.capabilities.contains("task.stop") {
                        Button("Stop", role: .destructive) { Task { await session.stopTerminalTask() } }.font(.caption)
                    }
                }.padding(10)
                ScrollViewReader { reader in
                ScrollView([.horizontal, .vertical]) {
                    VStack(alignment: .leading, spacing: 0) {
                    terminalText(session.terminalSnapshot)
                        .font(.system(size: 12, design: .monospaced)).textSelection(.enabled)
                        .fixedSize(horizontal: true, vertical: true)
                        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading).padding(10)
                    Color.clear.frame(height: 1).id("terminal-bottom")
                    }
                }.simultaneousGesture(DragGesture().onChanged { _ in followOutput = false })
                .onChange(of: session.terminalSnapshot?.content) { _, _ in if followOutput { reader.scrollTo("terminal-bottom", anchor: .bottom) } }
                .onChange(of: followOutput) { _, follow in if follow { reader.scrollTo("terminal-bottom", anchor: .bottom) } }
                }.frame(maxWidth: .infinity, maxHeight: .infinity).background(Color.black)
                if session.capabilities.contains("terminal.input") {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 4) {
                            ForEach(keys, id: \.0) { key in
                                Button(key.0) {
                                    let pending = input; sending = true
                                    Task {
                                        defer { sending = false }
                                        if !pending.isEmpty {
                                            guard await session.sendTerminalInput(pending, appendReturn: false) else { return }
                                            if input == pending { input = "" }
                                        }
                                        await session.sendTerminalInput(key.1, appendReturn: false)
                                    }
                                }.font(.system(size: 13, design: .monospaced)).frame(minWidth: 44, minHeight: 44)
                                    .background(Color(red: 0.08, green: 0.09, blue: 0.10), in: RoundedRectangle(cornerRadius: 7)).disabled(sending)
                            }
                        }.padding(6)
                    }
                    HStack {
                        Text("›").foregroundStyle(ZLTheme.healthy)
                        TextField("Command or reply", text: $input).focused($keyboardFocused)
                            .textInputAutocapitalization(.never).autocorrectionDisabled().font(.body.monospaced())
                            .submitLabel(.send).onSubmit { send() }
                        Button { send() } label: { Image(systemName: "return") }.frame(width: 44, height: 44).disabled(sending)
                    }.padding(.horizontal, 10)
                } else { Text("Enable Send Terminal Input in desktop ZedLink settings.").font(.caption).padding(10) }
            }
            .navigationTitle("Terminal").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) { Button("Done") { keyboardFocused = false; dismiss() } }
                ToolbarItemGroup(placement: .keyboard) { Spacer(); Button("Hide keyboard") { keyboardFocused = false } }
            }
            .task {
                while !Task.isCancelled {
                    if let terminal = session.terminalSnapshot?.terminal { await session.loadTerminal(terminal) }
                    do { try await Task.sleep(for: .milliseconds(1000)) } catch { return }
                }
            }
        }.presentationDetents([.large])
    }

    private func send() {
        guard !sending else { return }
        let value = input; sending = true
        Task {
            defer { sending = false }
            if await session.sendTerminalInput(value.isEmpty ? "\r" : value + "\n", appendReturn: false) { if input == value { input = "" } }
        }
    }
}


private let terminalFontRegistered: Bool = {
    guard let url = Bundle.main.url(forResource: "terminal-icons", withExtension: "ttf") else { return false }
    return CTFontManagerRegisterFontsForURL(url as CFURL, .process, nil)
}()

private func terminalColor(_ hex: String) -> Color? {
    guard hex.count == 7, hex.first == "#", let value = UInt32(hex.dropFirst(), radix: 16) else { return nil }
    return Color(red: Double((value >> 16) & 255) / 255, green: Double((value >> 8) & 255) / 255, blue: Double(value & 255) / 255)
}

private func terminalText(_ snapshot: NativeTerminalSnapshot?) -> Text {
    guard let snapshot else { return Text("") }
    var text = AttributedString()
    let runs = snapshot.styledRuns.isEmpty ? [NativeTerminalRun(text: snapshot.content, foreground: "", background: "", bold: false, italic: false, underline: false, dim: false)] : snapshot.styledRuns
    for run in runs {
        var segments: [(String, Bool)] = []
        for character in run.text {
            let scalar = character.unicodeScalars.first?.value ?? 0
            let icon = (0xe5fa...0xe6b7).contains(scalar) || (0xf000...0xf2e0).contains(scalar)
            if segments.last?.1 == icon {
                segments[segments.count - 1].0.append(character)
            } else { segments.append((String(character), icon)) }
        }
        for (segment, icon) in segments {
            var part = AttributedString(segment)
            var font = icon && terminalFontRegistered ? Font.custom("SymbolsNFM", size: 12) : Font.system(size: 12, design: .monospaced)
            if run.bold { font = font.bold() }
            if run.italic { font = font.italic() }
            part.font = font
            if let color = terminalColor(run.foreground) { part.foregroundColor = run.dim ? color.opacity(0.7) : color }
            if let color = terminalColor(run.background) { part.backgroundColor = color }
            if run.underline { part.underlineStyle = Text.LineStyle(pattern: .solid) }
            text += part
        }
    }
    return Text(text)
}
