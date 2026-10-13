import SwiftUI

struct SubagentReader: View {
    @EnvironmentObject private var session: SessionManager
    @Environment(\.dismiss) private var dismiss
    let childID: String
    @State private var following = true
    private var child: NativeSubagent? { session.snapshot?.subagents.first { $0.id == childID } }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Button { dismiss() } label: { Label("Back", systemImage: "arrow.left") }
                Spacer()
                if let child { Text(child.status).font(.caption.monospaced()).foregroundStyle(ZLTheme.muted) }
            }.frame(minHeight: 44).padding(.horizontal, 16)
            if let child {
                Text(child.title).font(.headline).frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 16).padding(.bottom, 8)
                Hairline()
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 0) {
                            if child.entryStartIndex > 0, session.capabilities.contains("thread.history") {
                                Button(session.loadingChildHistory ? "Loading…" : "Load earlier activity") {
                                    following = false
                                    Task { await session.loadEarlierSubagent(childID) }
                                }.disabled(session.loadingChildHistory).padding(16)
                            } else if child.entriesTruncated {
                                Text("Earlier activity requires an updated desktop bridge.").font(.caption).foregroundStyle(ZLTheme.muted).padding(16)
                            }
                            ForEach(Array(child.entries.enumerated()).map { ChildTranscriptEntry(id: child.entryStartIndex + $0.offset, markdown: $0.element) }) { entry in
                                NativeMessageView(message: NativeEntryPresentation(entry.markdown, index: entry.id), thinkingLive: child.isActive && entry.id == child.entryStartIndex + child.entries.count - 1)
                                Hairline().padding(.horizontal, 16)
                            }
                            if child.entries.isEmpty { Text("Waiting for the first activity…").foregroundStyle(ZLTheme.muted).padding(16) }
                            ForEach(session.snapshot?.pendingApprovals.filter { $0.subagentID == childID } ?? [], id: \.viewIdentity) { approval in
                                NativeApprovalView(approval: approval).padding(16)
                            }
                            Color.clear.frame(height: 1).id("child-bottom")
                        }
                    }.defaultScrollAnchor(.bottom)
                        .simultaneousGesture(DragGesture().onChanged { _ in following = false })
                        .onChange(of: child.entries) { _, _ in if following { proxy.scrollTo("child-bottom", anchor: .bottom) } }
                    if !following {
                        Button("Latest ↓") { following = true; proxy.scrollTo("child-bottom", anchor: .bottom) }.frame(maxWidth: .infinity, minHeight: 44)
                    }
                }
                Hairline()
                HStack {
                    Button("Continue agent") {
                        session.draft = "Use the native spawn_agent tool with session_id \"\(child.id)\" to continue this existing child agent. Return its result in this conversation:\n\nTask: "
                        dismiss()
                    }
                    Spacer()
                    if child.currentTurnID != nil, session.capabilities.contains("subagent.cancel") {
                        Button("Stop agent", role: .destructive) { Task { await session.cancelSubagent(child) } }
                    }
                }.frame(minHeight: 44).padding(.horizontal, 16)
            } else { ContentUnavailableView("Agent unavailable", systemImage: "person.crop.circle.badge.questionmark") }
        }.background(ZLTheme.background).foregroundStyle(ZLTheme.ink).buttonStyle(.plain)
    }
}

private struct ChildTranscriptEntry: Identifiable { let id: Int; let markdown: String }

struct SubagentHistoryView: View {
    @EnvironmentObject private var session: SessionManager
    @Environment(\.dismiss) private var dismiss
    @State private var childID: String?
    var body: some View {
        VStack(spacing: 0) {
            HStack { Text("Agent history").font(.headline); Spacer(); Button("Close") { dismiss() } }.padding(16)
            Hairline()
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 0) {
                    ForEach(session.snapshot?.subagents ?? []) { child in
                        Button { childID = child.id } label: {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(child.title).font(.subheadline)
                                Text(child.status).font(.caption).foregroundStyle(ZLTheme.muted)
                            }.frame(maxWidth: .infinity, alignment: .leading).padding(16)
                        }.buttonStyle(.plain)
                        Hairline()
                    }
                    if session.snapshot?.subagents.isEmpty != false { Text("No parallel agents in this conversation yet.").foregroundStyle(ZLTheme.muted).padding(16) }
                }
            }
        }.background(ZLTheme.background).foregroundStyle(ZLTheme.ink)
        .sheet(isPresented: Binding(get: { childID != nil }, set: { if !$0 { childID = nil } })) { if let id = childID { SubagentReader(childID: id) } }
    }
}
