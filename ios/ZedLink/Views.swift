import AVFoundation
import SwiftUI
import CoreText
import UIKit
import VisionKit
import PhotosUI

struct SessionsView: View {
    @EnvironmentObject private var session: SessionManager
    @EnvironmentObject private var library: SessionLibrary
    @State private var search = ""
    @State private var filter = "All"
    @State private var showingNewSession = false
    @Binding var navigationPath: [String]
    @FocusState private var searchFocused: Bool
    private let groups = ["Needs attention", "Running", "Ready & other"]
    private func key(_ thread: NativeThread) -> String {
        SessionLibrary.key(profile: session.profile?.gatewayID ?? "", target: session.targetID ?? "", thread: thread.id)
    }
    private var visibleThreads: [NativeThread] {
        session.threads.filter { thread in
            let activity = SessionActivity(thread)
            return (search.isEmpty || (thread.title + " " + thread.agentName + " " + thread.id).localizedCaseInsensitiveContains(search)) &&
                (filter == "All" || filter == "Needs attention" && activity.attention || filter == "Running" && activity.running || filter == "Pinned" && library.pins.contains(key(thread)))
        }.sorted { left, right in
            let lp = library.pins.contains(key(left)), rp = library.pins.contains(key(right))
            if lp != rp { return lp }
            return left.title.localizedStandardCompare(right.title) == .orderedAscending
        }
    }
    var body: some View {
        NavigationStack(path: $navigationPath) {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 0) {
                    connectionHeader
                    if session.demoPreview { Text("DEMO PREVIEW · Sample sessions, no live connection").font(.caption).foregroundStyle(ZLTheme.warning).padding(.horizontal, 16).padding(.vertical, 8) }
                    if !session.issue.isEmpty { SessionIssueBanner() }
                    HStack(spacing: 9) {
                        Image(systemName: "magnifyingglass").foregroundStyle(ZLTheme.muted)
                        TextField("Search sessions or agents", text: $search)
                            .textInputAutocapitalization(.never).submitLabel(.search).focused($searchFocused)
                            .onSubmit { searchFocused = false }.accessibilityIdentifier("session-search")
                    }.padding(.horizontal, 12).frame(minHeight: 44).background(ZLTheme.surface)
                        .overlay(Rectangle().stroke(ZLTheme.line)).padding(.horizontal, 16).padding(.top, 12)
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 16) {
                            ForEach(["All", "Needs attention", "Running", "Pinned"], id: \.self) { label in
                                Button { filter = label; searchFocused = false } label: {
                                    Text(label).font(.subheadline).foregroundStyle(filter == label ? ZLTheme.ink : ZLTheme.muted)
                                        .frame(minHeight: 44).overlay(alignment: .bottom) { if filter == label { Rectangle().fill(ZLTheme.ink).frame(height: 2) } }
                                }.buttonStyle(.plain).accessibilityIdentifier("session-filter-" + label)
                            }
                        }.padding(.horizontal, 16)
                    }
                    Hairline()
                    if visibleThreads.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text(session.profile == nil ? "Choose a connection" : session.threads.isEmpty ? (session.state == .live ? "No exposed sessions" : "Sessions unavailable") : "No matching sessions").font(.headline)
                            Text(session.profile == nil ? "Pair a private gateway in Connections." : session.threads.isEmpty ? (session.state == .live ? "Expose a conversation with /remote-control in desktop Zed, or create a session using +." : "Reconnect to refresh your sessions.") : "Try another search or filter.").font(.subheadline).foregroundStyle(ZLTheme.muted)
                        }.padding(20)
                    }
                    ForEach(groups, id: \.self) { group in
                        let rows = visibleThreads.filter { SessionActivity($0).group == group }
                        if !rows.isEmpty {
                            HStack { SectionLabel(group); Spacer(); Text("\(rows.count)").font(.caption.monospaced()).foregroundStyle(ZLTheme.muted) }
                                .padding(.horizontal, 16).padding(.top, 18).padding(.bottom, 6)
                            ForEach(rows) { thread in
                                HStack(spacing: 0) {
                                    NavigationLink(value: thread.id) {
                                        SessionRow(thread: thread, live: session.state == .live, updated: library.updated.contains(key(thread)))
                                    }.buttonStyle(.plain).accessibilityIdentifier("thread-" + thread.id)
                                        .allowsHitTesting(!session.demoPreview)
                                        .simultaneousGesture(TapGesture().onEnded { searchFocused = false; library.seen(key(thread)) })
                                    Button { library.toggle(key(thread)) } label: {
                                        Image(systemName: library.pins.contains(key(thread)) ? "pin.fill" : "pin")
                                            .foregroundStyle(library.pins.contains(key(thread)) ? ZLTheme.focus : ZLTheme.muted).frame(width: 44, height: 44)
                                    }.accessibilityLabel(library.pins.contains(key(thread)) ? "Unpin session" : "Pin session").accessibilityIdentifier("pin-" + thread.id)
                                }
                                Hairline().padding(.leading, 16)
                            }
                        }
                    }
                }.padding(.bottom, 16)
            }.background(ZLTheme.background).scrollDismissesKeyboard(.interactively)
                .toolbar(.visible, for: .navigationBar).navigationTitle("Sessions").navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button { showingNewSession = true } label: { Image(systemName: "plus") }
                            .disabled(session.state != .live || !session.capabilities.contains("thread.create")).accessibilityLabel("Create Agent session")
                    }
                    ToolbarItem(placement: .topBarTrailing) {
                        Button { Task { await session.refresh() } } label: { Image(systemName: "arrow.clockwise") }
                            .disabled(session.profile == nil).accessibilityLabel("Refresh sessions").accessibilityIdentifier("reconnect")
                    }
                }
                .sheet(isPresented: $showingNewSession) { NewSessionView() }
                .navigationDestination(for: String.self) { ConversationView(threadID: $0) }
                .onChange(of: session.threads, initial: true) { _, threads in
                    library.observe(threads, profile: session.profile?.gatewayID ?? "", target: session.targetID ?? "", selected: session.selectedThreadID)
                }
                .onChange(of: session.notificationThreadID) { _, thread in
                    if let thread { searchFocused = false; navigationPath = [thread]; session.notificationThreadID = nil }
                }
                .refreshable { await session.refresh() }
        }
    }
    private var connectionHeader: some View {
        HStack(spacing: 8) {
            Menu {
                if let profile = session.profile {
                    Text(profile.name); Text(profile.endpoint)
                    ForEach(session.targets) { target in
                        Button(target.label + (target.available ? "" : " · unavailable")) { Task { await session.selectTarget(target.id) } }
                            .disabled(!target.available || session.demoPreview)
                    }
                }
                Button("Manage connections") { session.showConnections = true }
            } label: {
                HStack(spacing: 5) {
                    Text(session.profile?.name ?? "Choose a connection").lineLimit(1)
                    Image(systemName: "chevron.right").font(.caption2)
                    Text(session.targets.first(where: { $0.id == session.targetID })?.label ?? "Workspace").lineLimit(1)
                    Image(systemName: "chevron.down").font(.caption2)
                }.font(.caption).frame(minHeight: 44).foregroundStyle(ZLTheme.ink)
            }.accessibilityIdentifier("zed-target-picker")
            Spacer(minLength: 0)
            if !session.demoPreview { ConnectionStatusView(state: session.state) }
        }.padding(.horizontal, 16).background(ZLTheme.surface)
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
    let live: Bool
    let updated: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    private var activity: SessionActivity { SessionActivity(thread) }
    private var tint: Color { activity.attention ? ZLTheme.warning : activity.running ? ZLTheme.focus : ZLTheme.muted }
    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: activity.attention ? "exclamationmark.circle" : activity.running ? "waveform" : "bubble.left")
                .symbolEffect(.variableColor, isActive: live && activity.running && !reduceMotion)
                .foregroundStyle(tint).frame(width: 20)
            VStack(alignment: .leading, spacing: 5) {
                Text(thread.title).font(.body.weight(.medium)).foregroundStyle(ZLTheme.ink).lineLimit(2)
                Text(thread.agentName + " · " + (live ? "" : "Last known: ") + activity.rawValue +
                     (activity == .approval ? " (\(thread.approvalCount ?? 0))" : activity == .input ? " (\(thread.inputCount ?? 0))" : ""))
                    .font(.caption).foregroundStyle(tint)
                if updated { Text("New activity").font(.caption2).foregroundStyle(ZLTheme.focus) }
            }.frame(maxWidth: .infinity, alignment: .leading)
            Image(systemName: "chevron.right").font(.caption).foregroundStyle(ZLTheme.muted)
        }.padding(.leading, 16).padding(.vertical, 14).contentShape(Rectangle())
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
    @State private var reviewExpanded = false
    @State private var selectedChildID: String?
    @State private var showingAgentHistory = false
    @State private var lastKnownTitle = ""
    @State private var showingModelControls = false
    @State private var dismissedSlashDraft = ""
    @State private var followsConversation = true
    @State private var scrollHeight: CGFloat = 0
    @State private var userScrolling = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var proposedTitle = ""
    @State private var rewindPoint: NativeRewindPoint?
    @FocusState private var composerFocused: Bool

    var body: some View {
        VStack(spacing: 0) {
            SessionIssueBanner()
            if let snapshot = session.snapshot, snapshot.threadID == threadID {
                conversation(snapshot)
                if let error = snapshot.agentError {
                    VStack(alignment: .leading, spacing: 6) {
                        Label(error.title, systemImage: "exclamationmark.triangle").font(.caption.bold())
                        ScrollView { Text(error.message).font(.caption).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading) }.frame(maxHeight: 100)
                        if error.retrying { Text("Desktop Zed is retrying this request.").font(.caption) }
                    }.foregroundStyle(ZLTheme.warning).padding(12).frame(maxWidth: .infinity, alignment: .leading)
                        .background(ZLTheme.surface).accessibilityIdentifier("native-agent-error")
                }
                if !snapshot.pendingApprovals.isEmpty { approvalStack(snapshot.pendingApprovals) }
                if !session.elicitations.isEmpty { elicitationStack }
                if session.editReview != nil || !session.queuedMessages.isEmpty { nativeControls }
            } else {
                ContentUnavailableView(session.state == .live && !session.threads.contains(where: { $0.id == threadID }) ? "Session is not exposed" : "Loading native thread", systemImage: "bubble.left", description: Text("Keep this conversation exposed with /remote-control in desktop Zed. Its contents will reload when it becomes available."))
                    .frame(maxHeight: .infinity)
            }
        }
        .background(ZLTheme.background)
        .safeAreaInset(edge: .bottom, spacing: 0) { composer }
        .safeAreaInset(edge: .top, spacing: 0) { conversationHeader }
        .toolbar(.hidden, for: .navigationBar)
        .task(id: [threadID, session.profile?.id.uuidString ?? "", session.targetID ?? "", session.instanceID ?? "", session.epoch ?? "", String(session.state == .live), String(session.threads.contains(where: { $0.id == threadID }))]) {
            guard session.state == .live, session.threads.contains(where: { $0.id == threadID }) else { return }
            lastKnownTitle = session.threads.first { $0.id == threadID }?.title ?? "Agent thread"
            if session.selectedThreadID != threadID || session.snapshot == nil { await session.select(threadID) }
            if let snapshot = session.snapshot, snapshot.threadID == threadID, !snapshot.title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { lastKnownTitle = snapshot.title }
        }
        .onChange(of: session.snapshot?.title) { _, title in
            if session.snapshot?.threadID == threadID, let title, !title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { lastKnownTitle = title }
        }
        .sheet(isPresented: $showingAgentHistory) { SubagentHistoryView() }
        .onDisappear { composerFocused = false }
        .sheet(isPresented: Binding(get: { selectedChildID != nil }, set: { if !$0 { selectedChildID = nil } })) {
            if let id = selectedChildID { SubagentReader(childID: id) }
        }
        .sheet(isPresented: $showingCommands) { CommandPicker() }
        .sheet(isPresented: $showingModelControls) { SessionModelControls() }
        .confirmationDialog("Run desktop action?", isPresented: Binding(get: { session.localCommandConfirmation != nil }, set: { if !$0 { session.localCommandConfirmation = nil } })) {
            Button("Run /" + (session.localCommandConfirmation?.name ?? "")) { Task { await session.confirmLocalCommand() } }
        } message: { Text(session.localCommandConfirmation?.confirmation ?? "Confirm this desktop action.") }
        .onChange(of: session.localExposureStopped) { _, stopped in if stopped { dismiss() } }
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

    private var conversationHeader: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Button { composerFocused = false; dismiss() } label: {
                    Image(systemName: "arrow.left").frame(width: 44, height: 44)
                }.accessibilityLabel("Back to sessions").accessibilityIdentifier("back-to-sessions")
                VStack(alignment: .leading, spacing: 2) {
                    Text(lastKnownTitle.isEmpty ? "Agent thread" : lastKnownTitle).font(.headline).lineLimit(2)
                    if session.state != .live { ConnectionStatusView(state: session.state) }
                }.frame(maxWidth: .infinity, alignment: .leading).accessibilityIdentifier("conversation-title")
                Button { composerFocused = false; showingContext = true } label: {
                    Image(systemName: "square.grid.2x2").frame(width: 44, height: 44)
                }.accessibilityLabel("Workspace").accessibilityIdentifier("open-workspace")
                Menu {
                    Text("Connection: \(session.state.label)")
                    if !session.delivery.isEmpty { Menu("Recent delivery status") { Text(session.delivery) } }
                    Button("Agent history", systemImage: "person.2") { composerFocused = false; showingAgentHistory = true }
                    Button("Agent settings", systemImage: "slider.horizontal.3") { composerFocused = false; showingModelControls = true }
                    Button("Rename session", systemImage: "pencil") {
                        proposedTitle = session.snapshot?.title ?? ""; showingRename = true
                    }.disabled(!session.capabilities.contains("thread.rename"))
                    Button("Stop exposing", systemImage: "eye.slash", role: .destructive) { showingUnexposeConfirmation = true }
                        .disabled(!session.capabilities.contains("thread.unexpose"))
                } label: { Image(systemName: "ellipsis").frame(width: 44, height: 44) }
                    .accessibilityLabel("Session actions")
            }.padding(.horizontal, 8).padding(.vertical, 4).buttonStyle(.plain)
            Hairline()
        }.background(ZLTheme.background).foregroundStyle(ZLTheme.ink)
    }

    private func conversation(_ snapshot: ThreadSnapshot) -> some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 0) {
                    let activeChildren = snapshot.subagents.filter { child in child.isActive || snapshot.pendingApprovals.contains { $0.subagentID == child.id } }
                    if !activeChildren.isEmpty {
                        Text("PARALLEL AGENTS · \(snapshot.subagents.filter(\.isActive).count) ACTIVE")
                            .font(.caption.monospaced()).foregroundStyle(ZLTheme.muted).padding(.horizontal, 16).padding(.top, 8)
                        ForEach(activeChildren) { child in
                            let needsApproval = snapshot.pendingApprovals.contains { $0.subagentID == child.id }
                            Button { composerFocused = false; selectedChildID = child.id } label: {
                                HStack(spacing: 10) {
                                    if needsApproval { Image(systemName: "hand.raised").foregroundStyle(ZLTheme.warning) }
                                    else if child.isActive { ProgressView().controlSize(.small) }
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text(child.title).font(.subheadline).lineLimit(2)
                                        Text("\(needsApproval ? "Approval needed" : child.status) · \(child.totalEntries > 0 ? child.totalEntries : child.entries.count) entries").font(.caption).foregroundStyle(ZLTheme.muted)
                                    }.frame(maxWidth: .infinity, alignment: .leading)
                                    Image(systemName: "chevron.right")
                                }.padding(.horizontal, 16).padding(.vertical, 10)
                            }.buttonStyle(.plain)
                            Hairline()
                        }
                    }
                    if snapshot.hasOlderEntries {
                        Button("Load earlier conversation · \(snapshot.entryStartIndex) remaining") {
                            followsConversation = false
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
                        .background(GeometryReader { geometry in
                            Color.clear.preference(key: ConversationScrollMetrics.self, value: ["bottom": geometry.frame(in: .named("conversation-scroll")).maxY])
                        })
                }
            }
            .coordinateSpace(name: "conversation-scroll")
            .background(GeometryReader { geometry in Color.clear.preference(key: ConversationScrollMetrics.self, value: ["height": geometry.size.height]) })
            .onPreferenceChange(ConversationScrollMetrics.self) { metrics in
                if let height = metrics["height"] { scrollHeight = height }
                if userScrolling, let bottom = metrics["bottom"], scrollHeight > 0 { followsConversation = bottom >= 0 && bottom <= scrollHeight + 50 }
            }
            .simultaneousGesture(DragGesture().onChanged { _ in userScrolling = true; followsConversation = false }.onEnded { _ in userScrolling = false })
            .defaultScrollAnchor(.bottom)
            .scrollDismissesKeyboard(.interactively)
            .safeAreaInset(edge: .bottom, spacing: 0) {
                if !followsConversation {
                    HStack {
                        Spacer()
                        Button {
                            followsConversation = true; dismissZedLinkKeyboard()
                            proxy.scrollTo("conversation-bottom", anchor: .bottom)
                        } label: { Label("Latest", systemImage: "arrow.down").font(.caption).frame(minHeight: 44) }
                            .buttonStyle(.plain).accessibilityIdentifier("jump-to-latest")
                    }.padding(.horizontal, 16).background(ZLTheme.background)
                        .overlay(alignment: .top) { Hairline() }
                }
            }
            .task(id: [snapshot.instanceID, snapshot.epoch, snapshot.threadID]) {
                // Explicit initial placement after restored transcript layout, without animation.
                followsConversation = true
                await Task.yield()
                proxy.scrollTo("conversation-bottom", anchor: .bottom)
            }
            .onChange(of: snapshot.entries) { _, _ in
                if followsConversation {
                    withAnimation(reduceMotion ? nil : .easeOut(duration: 0.18)) { proxy.scrollTo("conversation-bottom", anchor: .bottom) }
                }
            }
        }
    }

    private func approvalStack(_ approvals: [NativeApproval]) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 10) {
                ForEach(approvals, id: \.viewIdentity) { NativeApprovalView(approval: $0) }
            }
            .padding(.horizontal, 12).padding(.vertical, 9)
        }
        .background(ZLTheme.warning.opacity(0.07))
        .overlay(alignment: .top) { Hairline() }
    }

    private var elicitationStack: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 10) {
                ForEach(session.elicitations) { elicitation in
                    NativeElicitationView(elicitation: elicitation).id((session.operationScope + [elicitation.id]).joined(separator: "\n"))
                }
            }.padding(.horizontal, 12).padding(.vertical, 9)
        }
        .background(ZLTheme.warning.opacity(0.07))
        .overlay(alignment: .top) { Hairline() }
    }

    private var nativeControls: some View {
        VStack(spacing: 8) {
            if let review = session.editReview {
                DisclosureGroup(isExpanded: $reviewExpanded) {
                    HStack {
                    VStack(alignment: .leading) {
                        Text("Review Agent edits").font(.subheadline.weight(.semibold))
                        Text("\(review.changedFiles) files · +\(review.linesAdded) −\(review.linesRemoved)")
                            .font(.caption.monospaced()).foregroundStyle(ZLTheme.muted)
                    }
                    Spacer()
                    Button("Reject all", role: .destructive) { Task { await session.resolveEditReview("reject_all") } }
                    Button("Keep all") { Task { await session.resolveEditReview("keep_all") } }
                    }.disabled(session.state != .live)
                } label: {
                    Label("Edits · \(review.changedFiles) files · +\(review.linesAdded) −\(review.linesRemoved)", systemImage: "square.and.pencil")
                        .font(.caption)
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
        .disabled(session.state != .live)
    }

    private var composer: some View {
        VStack(alignment: .leading, spacing: 8) {
            if !session.attachments.isEmpty || !session.contextPaths.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack {
                        ForEach(session.attachments) { image in
                            Button { session.attachments.removeAll { $0.id == image.id } } label: { Label(image.name, systemImage: "xmark.circle") }
                        }
                        ForEach(Array(session.contextPaths).sorted(), id: \.self) { path in
                            Button { session.contextPaths.remove(path) } label: { Label(path, systemImage: "xmark.circle") }
                        }
                    }.font(.caption).padding(4)
                }.accessibilityIdentifier("prompt-attachments")
            }
            if let snapshot = session.snapshot, snapshot.threadID == threadID, snapshot.isBusy {
                agentProgress(snapshot)
            }
            if !session.delivery.isEmpty && (session.pending != nil || session.state != .live) {
                Text(session.delivery).font(.caption).foregroundStyle(ZLTheme.muted)
                    .lineLimit(2).accessibilityIdentifier("delivery-status")
            }
            if session.pending != nil { uncertainDelivery }
            if session.draft.hasPrefix("/"), session.draft != dismissedSlashDraft, !session.draft.contains(where: { $0.isWhitespace }) {
                NativeSlashSuggestions(commands: session.commands, query: String(session.draft.dropFirst())) { command in
                    session.insertCommand(command); dismissedSlashDraft = session.draft
                }.task { await session.refreshCommands() }
            }
            HStack(alignment: .bottom, spacing: 8) {
                Button { composerFocused = false; showingCommands = true } label: {
                    Image(systemName: "plus").font(.title3).frame(width: 44, height: 44)
                }
                .foregroundStyle(.primary)
                .accessibilityLabel("Zed Agent actions and commands")

                TextField("Message Zed Agent…", text: $session.draft, axis: .vertical)
                    .lineLimit(1...6).padding(.horizontal, 11).padding(.vertical, 10)
                    .focused($composerFocused)
                    .submitLabel(.send)
                    .onSubmit { sendAndDismissKeyboard() }
                    .accessibilityLabel("Message to native Zed Agent")
                    .accessibilityIdentifier("composer")

                VoiceDraftButton(text: $session.draft, scope: "\(session.profile?.id.uuidString ?? "").\(session.targetID ?? "").\(session.instanceID ?? "").\(session.epoch ?? "").\(session.selectedThreadID ?? "")")
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
                    .disabled(!session.canSend || session.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && session.attachments.isEmpty && session.contextPaths.isEmpty)
                    .accessibilityLabel("Send").accessibilityIdentifier("send-prompt")
                }
            }
            .padding(4)
            .background(ZLTheme.surface)
            .overlay(Rectangle().stroke(ZLTheme.line, lineWidth: 1))
        }
        .padding(.horizontal, 10).padding(.top, 9).padding(.bottom, 8)
        .background(ZLTheme.background)
        .overlay(alignment: .top) { Hairline() }
    }

    private func agentProgress(_ snapshot: ThreadSnapshot) -> some View {
        HStack(spacing: 8) {
            if session.state == .live { ProgressView().controlSize(.mini).tint(ZLTheme.focus) }
            else { Image(systemName: "pause.circle").foregroundStyle(ZLTheme.warning) }
            Text(session.state == .live ? progressDetail(snapshot.status) : "Last known: " + snapshot.status).font(.caption).foregroundStyle(ZLTheme.muted)
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 8).padding(.vertical, 3)
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
        guard session.canSend, !session.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !session.attachments.isEmpty || !session.contextPaths.isEmpty else { return }
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

private enum WorkspaceTab: String, CaseIterable, Identifiable {
    case files = "Files", changes = "Changes", terminal = "Terminal", debug = "Debug", activity = "Activity"
    var id: String { rawValue }
}

private struct NativeContextSheet: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var session: SessionManager
    @State private var tab: WorkspaceTab = .files
    @State private var activityExpanded = true

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                SessionIssueBanner()
                if session.workspaceLoading { ProgressView().controlSize(.small).accessibilityLabel("Loading workspace") }
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 4) {
                        ForEach(WorkspaceTab.allCases) { item in
                            Button {
                                dismissZedLinkKeyboard()
                                tab = item
                            } label: {
                                Text(item.rawValue).font(.caption.weight(tab == item ? .semibold : .regular))
                                    .padding(.horizontal, 8).frame(minWidth: 44, minHeight: 44)
                                    .overlay(alignment: .bottom) {
                                        if tab == item { Rectangle().fill(ZLTheme.ink).frame(height: 2) }
                                    }
                            }
                            .buttonStyle(.plain)
                            .accessibilityAddTraits(tab == item ? .isSelected : [])
                            .accessibilityIdentifier("workspace-" + item.rawValue.lowercased())
                        }
                    }.padding(.horizontal, 8)
                }
                Hairline()
                Group {
                    switch tab {
                    case .files:
                        if session.capabilities.contains("project.files") {
                            ProjectFileBrowser()
                        } else {
                            ContentUnavailableView("Files unavailable", systemImage: "folder", description: Text("Enable project file access in desktop ZedLink settings."))
                        }
                    case .changes:
                        changes
                    case .terminal:
                        NativeTerminalScreen(embedded: true)
                    case .debug:
                        debugger
                    case .activity:
                        ScrollView {
                            if let snapshot = session.snapshot {
                                ActivityPanel(snapshot: snapshot, expanded: $activityExpanded).padding(12)
                            } else {
                                ContentUnavailableView("No activity", systemImage: "clock")
                            }
                        }
                    }
                }.frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            .background(ZLTheme.background)
            .navigationTitle("Workspace").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { dismissZedLinkKeyboard(); dismiss() } label: { Image(systemName: "xmark") }
                        .accessibilityLabel("Close workspace").accessibilityIdentifier("close-workspace")
                }
            }
            .task(id: tab) { await session.loadProjectContext(page: WorkspacePage(rawValue: tab.rawValue.lowercased())) }
        }
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
    }

    private var changes: some View {
        VStack(spacing: 0) {
            HStack {
                Button("Refresh diff") { Task { await session.loadDiff() } }
                    .disabled(session.state != .live || !session.capabilities.contains("changes.diff") || session.changesRevision == nil || session.diffLoading)
                Spacer()
                Menu("Files · \(session.changes.count)") {
                    ForEach(session.changes) { change in
                        Button("\(change.staging == "staged" ? "Unstage" : "Stage") \(change.id)") { Task { await session.mutateChange(change) } }
                            .disabled(session.state != .live || !session.capabilities.contains(change.staging == "staged" ? "changes.unstage" : "changes.stage"))
                    }
                }
            }.padding(12)
            if session.diffLoading { ProgressView("Loading diff…").frame(maxHeight: .infinity) }
            else if !session.capabilities.contains("changes.snapshot") {
                ContentUnavailableView("Changes unavailable", systemImage: "lock")
            } else if session.changes.isEmpty {
                ContentUnavailableView("No working tree changes", systemImage: "checkmark.circle")
            } else if session.diffContent.isEmpty {
                ContentUnavailableView("Review changes", systemImage: "doc.text", description: Text("Choose Refresh diff to load the current native revision."))
            } else {
                CodeReviewView(content: session.diffContent, title: "Changes", diff: true, truncated: session.diffTruncated)
            }
        }
    }

    private var debugger: some View {
        List {
                Section("Debugger") {
                    if !session.capabilities.contains("debugger.catalog") {
                        Text("Enable Start Configured Debuggers in desktop ZedLink settings.")
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
                        .disabled(session.state != .live || !session.capabilities.contains("debugger.launch"))
                    }
                    if !session.capabilities.contains("debugger.snapshot") {
                        Text("Enable View Debugger Sessions in desktop ZedLink settings.")
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
                                    }.disabled(session.state != .live || !session.capabilities.contains("debugger.control"))
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
                                    }.disabled(session.state != .live || !session.capabilities.contains("debugger.control"))
                                }
                            }
                        }
                    }
                }
        }.scrollContentBackground(.hidden)
            .refreshable { await session.loadProjectContext(page: .debug) }
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

struct NativeApprovalView: View {
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
            if session.resolvingApprovals.contains(approval.id) { ProgressView("Sending decision…") }
            Text(approval.authorizationKind == "action_choice" ? "Choose an action" : "Permission requested")
                .font(.caption2.monospaced()).foregroundStyle(ZLTheme.warning)
            if approval.decisions.isEmpty {
                Text("Update patched Zed to resolve this request remotely.")
                    .font(.caption2).foregroundStyle(ZLTheme.muted)
            } else {
                ForEach(approval.decisions) { decision in
                    Button {
                        dismissZedLinkKeyboard()
                        Task { await session.respond(to: approval, with: decision) }
                    } label: {
                        Text(decision.displayLabel)
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(decision.isRejecting ? ZLTheme.warning : ZLTheme.focus)
                    .disabled(session.state != .live || session.resolvingApprovals.contains(approval.id) || !session.capabilities.contains("approval.respond") || (approval.detailsTruncated && (!decision.isRejecting || approval.authorizationKind == "action_choice")))
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
    @State private var selections: [String: Set<String>] = [:]
    @State private var validation = ""
    private var submitting: Bool { session.isRespondingToElicitation(elicitation.id) }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("INPUT REQUESTED").font(.caption2.monospaced().weight(.semibold)).foregroundStyle(ZLTheme.warning)
            Text(elicitation.message).font(.subheadline.weight(.semibold))
            if let url = elicitation.url, let destination = URL(string: url) { Link("Open secure input page", destination: destination) }
            ForEach(elicitation.fields) { field in
                let title = field.title + (field.required ? " *" : "")
                if field.type == "boolean" {
                    Toggle(title, isOn: Binding(get: { ElicitationForm.value(field, values: values) == "true" }, set: { values[field.id] = $0 ? "true" : "false" }))
                } else if field.type == "array", !field.choices.isEmpty {
                    Text(title).font(.caption)
                    ForEach(field.choices, id: \.self) { choice in
                        Toggle(choice, isOn: Binding(get: { (selections[field.id] ?? ElicitationForm.arrayDefault(field)).contains(choice) }, set: { enabled in
                            var selected = selections[field.id] ?? ElicitationForm.arrayDefault(field)
                            if enabled { selected.insert(choice) } else { selected.remove(choice) }; selections[field.id] = selected
                        }))
                    }
                } else if !field.choices.isEmpty {
                    Picker(title, selection: Binding(get: { ElicitationForm.value(field, values: values) }, set: { values[field.id] = $0 })) {
                        if !field.required { Text("No value").tag("") }
                        ForEach(field.choices, id: \.self) { Text($0).tag($0) }
                    }
                } else {
                    TextField(title, text: Binding(get: { ElicitationForm.value(field, values: values) }, set: { values[field.id] = $0 }))
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                        .padding(8).overlay(Rectangle().stroke(ZLTheme.line))
                    if field.type == "array" { Text("Separate values with commas.").font(.caption) }
                }
            }.disabled(submitting)
            if !validation.isEmpty { Text(validation).font(.caption).foregroundStyle(ZLTheme.danger) }
            if submitting { ProgressView("Submitting response…") }
            HStack {
                Button("Decline", role: .destructive) { dismissZedLinkKeyboard(); Task { await session.respondToElicitation(elicitation, action: "decline") } }
                Button("Submit") {
                    do {
                        let content = try ElicitationForm.content(elicitation.fields, values: values, selections: selections)
                        validation = ""; dismissZedLinkKeyboard()
                        Task { await session.respondToElicitation(elicitation, action: "accept", content: content) }
                    } catch { validation = error.localizedDescription }
                }.buttonStyle(.borderedProminent)
            }.disabled(session.state != .live || submitting || !session.capabilities.contains("elicitation.respond"))
        }.padding(14).frame(width: 330, alignment: .leading)
            .background(ZLTheme.surface).overlay(Rectangle().stroke(ZLTheme.warning.opacity(0.5)))
    }
}

private struct CommandPicker: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var session: SessionManager
    @State private var search = ""
    @State private var photo: PhotosPickerItem?
    @State private var loadingPhoto = false
    @State private var showingClipboard = false

    private var commands: [NativeCommand] {
        guard !search.isEmpty else { return session.commands }
        return session.commands.filter { $0.name.localizedCaseInsensitiveContains(search) ||
            $0.description.localizedCaseInsensitiveContains(search) }
    }

    var body: some View {
        NavigationStack {
            List {
                Section("Attachments") {
                    PhotosPicker(selection: $photo, matching: .images) { Label("Attach photo", systemImage: "photo") }
                        .disabled(loadingPhoto || !session.capabilities.contains("thread.attachments") || session.supportsImages == false)
                    Button("Paste image", systemImage: "doc.on.clipboard") {
                        let scope = session.operationScope
                        guard let image = UIPasteboard.general.image, let data = promptJPEG(image) else { session.reportIssue("Clipboard does not contain a supported image."); return }
                        if scope == session.operationScope { session.addImage(data) }; dismiss()
                    }.disabled(!session.capabilities.contains("thread.attachments") || session.supportsImages == false)
                    if loadingPhoto { ProgressView("Preparing image…") }
                }
                Section("Agent actions") {
                    Button("Recover session") { Task { await session.refresh() }; dismiss() }
                    Button("Remote clipboard") { showingClipboard = true }
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
                                if let hint = command.inputHint { Text(hint).font(.caption.monospaced()).foregroundStyle(ZLTheme.muted) }
                                if let warning = command.warning { Text(warning).font(.caption).foregroundStyle(ZLTheme.warning) }
                            }
                            .padding(.vertical, 4)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .listStyle(.plain).scrollContentBackground(.hidden).background(ZLTheme.background)
            .searchable(text: $search, prompt: "Search commands and skills")
            .task { await session.refreshCommands() }
            .task(id: photo) {
                guard let photo else { return }
                loadingPhoto = true; defer { loadingPhoto = false }
                let scope = session.operationScope
                do {
                    let raw = try await photo.loadTransferable(type: Data.self)
                    guard !Task.isCancelled, scope == session.operationScope else { return }
                    guard let raw, let image = UIImage(data: raw), let data = promptJPEG(image) else {
                        session.reportIssue("This image could not be prepared within the 1 MiB upload limit."); dismiss(); return
                    }
                    session.addImage(data); dismiss()
                } catch { if scope == session.operationScope { session.reportIssue("Image unavailable: " + error.localizedDescription) } }
            }
            .navigationTitle("Agent commands")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Done") { dismiss() } } }
        }
        .sheet(isPresented: $showingClipboard) { RemoteClipboardView(destination: "prompt") { session.draft = $0 } }
        .presentationDetents([.medium, .large])
    }
}

private struct NativeTerminalScreen: View {
    var embedded = false
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var session: SessionManager
    @State private var input = ""
    @State private var sending = false
    @State private var followOutput = true
    @AppStorage("zedlink.terminalWrap") private var wrapOutput = true
    @State private var showingClipboard = false
    @FocusState private var keyboardFocused: Bool
    private let keys: [(String, String)] = [("Esc", "\u{1b}"), ("Tab", "\t"), ("Ctrl C", "\u{03}"), ("↑", "\u{1b}[A"), ("↓", "\u{1b}[B"), ("←", "\u{1b}[D"), ("→", "\u{1b}[C")]

    private var recoveryKey: String { "zedlink.terminalDraft.\(session.profile?.id.uuidString ?? "").\(session.targetID ?? "").\(session.instanceID ?? "").\(session.epoch ?? "").\(session.terminalSnapshot?.terminal.id ?? "")" }

    var body: some View {
        Group {
            if embedded { content }
            else { NavigationStack { content } }
        }.presentationDetents([.large])
    }

    private var content: some View {
            VStack(spacing: 0) {
                if !embedded { SessionIssueBanner() }
                HStack {
                    Menu {
                        ForEach(session.terminals) { terminal in
                            Button(terminal.title) { keyboardFocused = false; Task { await session.loadTerminal(terminal) } }
                        }
                    } label: { Text(session.terminalSnapshot?.terminal.title ?? "Choose terminal").lineLimit(1) }.disabled(sending)
                    Menu {
                        Toggle("Wrap output", isOn: $wrapOutput)
                        if session.capabilities.contains("task.catalog") {
                            Menu("Run configured task") {
                                ForEach(session.configuredTasks) { task in
                                    Button(task.label) { Task { await session.runConfiguredTask(task) } }
                                        .disabled(!session.capabilities.contains("task.run"))
                                }
                            }
                        }
                        Button("Remote clipboard") { showingClipboard = true }
                        Button("Recover session") { Task { await session.refresh(); await session.loadProjectContext(page: .terminal) } }
                    } label: { Image(systemName: "ellipsis").frame(width: 44, height: 44) }
                    Spacer()
                    Text(session.capabilities.contains("terminal.input") ? "Interactive" : "Read only").font(.caption)
                    if !followOutput { Button("Latest") { followOutput = true }.font(.caption) }
                    if session.terminalSnapshot?.terminal.taskState == "running" && session.capabilities.contains("task.stop") {
                        Button("Stop", role: .destructive) { Task { await session.stopTerminalTask() } }.font(.caption)
                    }
                }.padding(10)
                ScrollViewReader { reader in
                ScrollView(wrapOutput ? .vertical : [.horizontal, .vertical]) {
                    VStack(alignment: .leading, spacing: 0) {
                    if session.terminalSnapshot == nil {
                        ContentUnavailableView("No terminal selected", systemImage: "terminal", description: Text(session.capabilities.contains("terminal.list") ? "Open a terminal in desktop Zed or select one above." : "Enable View Project Terminals in desktop ZedLink settings."))
                    }
                    terminalText(session.terminalSnapshot)
                        .font(.system(size: 12, design: .monospaced)).textSelection(.enabled)
                        .fixedSize(horizontal: !wrapOutput, vertical: true)
                        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading).padding(10)
                    Color.clear.frame(height: 1).id("terminal-bottom")
                    }
                }.background(Color.black).foregroundStyle(Color.white)
                    .simultaneousGesture(DragGesture().onChanged { _ in followOutput = false })
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
                                    .background(ZLTheme.surface).disabled(sending || session.state != .live || session.terminalSnapshot == nil)
                            }
                        }.padding(6)
                    }
                    HStack {
                        Text("›").foregroundStyle(ZLTheme.healthy)
                        TextField("Command or reply", text: $input).focused($keyboardFocused)
                            .textInputAutocapitalization(.never).autocorrectionDisabled().font(.body.monospaced())
                            .submitLabel(.send).onSubmit { send() }
                        VoiceDraftButton(text: $input, scope: recoveryKey)
                        Button { send() } label: { Image(systemName: "return") }.frame(width: 44, height: 44).disabled(sending || session.state != .live || session.terminalSnapshot == nil)
                    }.padding(.horizontal, 10)
                } else { Text("Enable Send Terminal Input in desktop ZedLink settings.").font(.caption).padding(10) }
            }
            .task(id: recoveryKey) { input = UserDefaults.standard.string(forKey: recoveryKey) ?? "" }
            .onChange(of: input) { _, value in if session.terminalSnapshot != nil { UserDefaults.standard.set(value, forKey: recoveryKey) } }
            .sheet(isPresented: $showingClipboard) { RemoteClipboardView { input = $0 } }
            .navigationTitle(embedded ? "Workspace" : "Terminal").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                if !embedded {
                    ToolbarItem(placement: .topBarTrailing) { Button("Done") { keyboardFocused = false; dismiss() } }
                }
                ToolbarItemGroup(placement: .keyboard) { Spacer(); Button("Hide keyboard") { keyboardFocused = false } }
            }
            .task {
                await session.loadProjectContext(page: .terminal)
                if session.terminalSnapshot == nil, let terminal = session.terminals.first {
                    await session.loadTerminal(terminal)
                }
                while !Task.isCancelled {
                    if let terminal = session.terminalSnapshot?.terminal { await session.loadTerminal(terminal, refresh: true) }
                    do { try await Task.sleep(for: .milliseconds(1000)) } catch { return }
                }
            }
    }

    private func send() {
        guard !sending, session.state == .live, session.terminalSnapshot != nil else { return }
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
            let icon = (0xe5fa...0xe6b7).contains(scalar) || (0xe700...0xe8ef).contains(scalar) || (0xf000...0xf2e0).contains(scalar) || (0xf400...0xf533).contains(scalar) || (0xf0001...0xf1af0).contains(scalar)
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
