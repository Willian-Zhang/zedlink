import SwiftUI
import UIKit

struct SessionIssueBanner: View {
    @EnvironmentObject private var session: SessionManager
    var body: some View {
        if !session.issue.isEmpty {
            HStack(alignment: .top, spacing: 8) {
                Image(systemName: "exclamationmark.triangle").foregroundStyle(ZLTheme.warning)
                VStack(alignment: .leading, spacing: 6) {
                    if let help = ConnectionHelp.forMessage(session.issue) {
                        Text(help.title).font(.caption.bold())
                        Text(help.detail).font(.caption).textSelection(.enabled)
                        Button(help.action == .connections ? "Open Connections" : "Reconnect") {
                            dismissZedLinkKeyboard()
                            if help.action == .connections { session.showConnections = true }
                            else { Task { await session.refresh() } }
                        }.font(.caption).frame(minHeight: 44)
                    } else { Text(session.issue).font(.caption).textSelection(.enabled) }
                }
                Spacer(minLength: 0)
                Button { session.clearIssue() } label: { Image(systemName: "xmark").frame(width: 44, height: 44) }
                    .accessibilityLabel("Dismiss error")
            }.padding(.leading, 12).background(ZLTheme.surface)
                .accessibilityIdentifier("session-error")
        }
    }
}

struct ReviewLine: Identifiable {
    enum Kind: Equatable { case plain, added, removed, header }
    let id: Int
    let text: String
    var kind: Kind {
        if text.hasPrefix("+++") || text.hasPrefix("---") || text.hasPrefix("@@") || text.hasPrefix("diff ") { return .header }
        if text.hasPrefix("+") { return .added }
        if text.hasPrefix("-") { return .removed }
        return .plain
    }
    static func lines(_ content: String) -> [ReviewLine] {
        content.components(separatedBy: "\n").enumerated().map { ReviewLine(id: $0.offset + 1, text: $0.element) }
    }
}

struct ReviewIndex {
    struct Section: Identifiable { let id: Int; let title: String }
    let lines: [ReviewLine]
    let sections: [Section]
    private(set) var matches: [Int] = []
    private(set) var hits: Set<Int> = []
    init(_ content: String) {
        lines = ReviewLine.lines(content)
        var sections: [Section] = [], start = 1, oldPath = ""
        for line in lines {
            if line.text.hasPrefix("diff --git ") { start = line.id }
            if line.text.hasPrefix("--- a/") { oldPath = String(line.text.dropFirst(6)) }
            if line.text.hasPrefix("+++ ") {
                let path = String(line.text.dropFirst(4))
                sections.append(Section(id: sections.contains(where: { $0.id == start }) ? line.id : start, title: path == "/dev/null" ? oldPath : path.hasPrefix("b/") ? String(path.dropFirst(2)) : path))
            }
        }
        self.sections = sections
    }
    mutating func find(_ query: String) {
        matches = query.isEmpty ? [] : lines.filter { $0.text.localizedCaseInsensitiveContains(query) }.map(\.id)
        hits = Set(matches)
    }
    static func nextMatch(_ current: Int, delta: Int, count: Int) -> Int {
        guard count > 0 else { return 0 }
        return (current + delta + count) % count
    }
}

struct CodeReviewView: View {
    let content: String
    var title = "File"
    var diff = false
    var truncated = false
    var initialLine: Int? = nil
    var allowsExpansion = true
    @State private var wrap = true
    @State private var query = ""
    @State private var matchIndex = 0
    @State private var expanded = false
    @State private var index = ReviewIndex("")
    @State private var highlighted: [Int: AttributedString] = [:]
    @State private var scrollTarget: Int?
    @State private var scrollRequest = UUID()
    @State private var showingJump = false
    @State private var lineNumber = ""
    private func jump(_ line: Int) { scrollTarget = line; scrollRequest = UUID() }
    private func moveMatch(_ delta: Int) {
        guard !index.matches.isEmpty else { return }
        matchIndex = ReviewIndex.nextMatch(matchIndex, delta: delta, count: index.matches.count)
        jump(index.matches[matchIndex])
    }
    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 4) {
                TextField("Find in \(diff ? "diff" : "file")", text: $query)
                    .textInputAutocapitalization(.never).autocorrectionDisabled().accessibilityIdentifier("find-in-file")
                Text(index.matches.isEmpty ? "0" : "\(matchIndex + 1)/\(index.matches.count)").font(.caption.monospaced())
                Button { moveMatch(-1) } label: { Image(systemName: "chevron.up").frame(width: 44, height: 44) }
                    .disabled(index.matches.isEmpty).accessibilityLabel("Previous match")
                Button { moveMatch(1) } label: { Image(systemName: "chevron.down").frame(width: 44, height: 44) }
                    .disabled(index.matches.isEmpty).accessibilityLabel("Next match")
                Menu {
                    Toggle("Wrap lines", isOn: $wrap)
                    Button("Jump to line") { showingJump = true }
                    if diff, !index.sections.isEmpty {
                        Menu("Jump to file") { ForEach(index.sections) { section in Button(section.title) { jump(section.id) } } }
                    }
                    if allowsExpansion { Button("Expand") { expanded = true } }
                    Button("Copy text") { UIPasteboard.general.string = content }
                } label: { Image(systemName: "ellipsis").frame(width: 44, height: 44) }
            }.padding(.horizontal, 12)
            Hairline()
            ScrollViewReader { reader in
                ScrollView(wrap ? [.vertical] : [.horizontal, .vertical]) {
                    LazyVStack(alignment: .leading, spacing: 0) {
                        ForEach(index.lines) { line in
                            HStack(alignment: .top, spacing: 10) {
                                Text("\(line.id)").foregroundStyle(ZLTheme.muted).frame(width: 38, alignment: .trailing)
                                Text(diff ? AttributedString(line.text.isEmpty ? " " : line.text) : highlighted[line.id] ?? AttributedString(line.text))
                                    .foregroundStyle(diff ? lineColor(line) : Color.primary)
                                    .frame(maxWidth: wrap ? .infinity : nil, alignment: .leading)
                                    .fixedSize(horizontal: !wrap, vertical: true)
                            }.font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                                .padding(.vertical, 3).padding(.horizontal, 8)
                                .background(index.hits.contains(line.id) ? ZLTheme.warning.opacity(0.25) : lineBackground(line)).id(line.id)
                        }
                    }
                }
                .task(id: content) {
                    index = ReviewIndex(content); index.find(query); matchIndex = 0
                    highlighted = diff ? [:] : Dictionary(uniqueKeysWithValues: index.lines.map { ($0.id, highlightedSource($0.text.isEmpty ? " " : $0.text)) })
                    await Task.yield()
                    guard !Task.isCancelled else { return }
                    if let initialLine { reader.scrollTo(initialLine, anchor: .center) }
                }
                .onChange(of: query) { _, value in
                    index.find(value); matchIndex = 0
                    if let first = index.matches.first { jump(first) }
                }
                .onChange(of: scrollRequest) { _, _ in if let scrollTarget { reader.scrollTo(scrollTarget, anchor: .center) } }
            }
            if truncated { Label("Partial content · native size limit", systemImage: "exclamationmark.triangle").font(.caption).padding(8) }
        }
        .alert("Jump to line", isPresented: $showingJump) {
            TextField("Line number", text: $lineNumber).keyboardType(.numberPad)
            Button("Go") { if let line = Int(lineNumber), (1...max(1, index.lines.count)).contains(line) { jump(line) } }
                .disabled(Int(lineNumber).map { !(1...max(1, index.lines.count)).contains($0) } ?? true)
            Button("Cancel", role: .cancel) {}
        } message: { Text("Enter a line between 1 and \(index.lines.count).") }
        .fullScreenCover(isPresented: $expanded) {
            NavigationStack {
                CodeReviewView(content: content, title: title, diff: diff, truncated: truncated, initialLine: scrollTarget, allowsExpansion: false)
                    .navigationTitle(title).navigationBarTitleDisplayMode(.inline)
                    .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Done") { expanded = false } } }
            }
        }
    }
    private func lineColor(_ line: ReviewLine) -> Color {
        switch line.kind { case .added: ZLTheme.healthy; case .removed: ZLTheme.danger; case .header: ZLTheme.focus; case .plain: .primary }
    }
    private func lineBackground(_ line: ReviewLine) -> Color {
        guard diff else { return .clear }
        return switch line.kind { case .added: ZLTheme.healthy.opacity(0.08); case .removed: ZLTheme.danger.opacity(0.08); default: .clear }
    }
}

struct SessionModelControls: View {
    @EnvironmentObject private var session: SessionManager
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        NavigationStack {
            Form {
                SessionIssueBanner()
                if let settings = session.threadSettings {
                    Section("Zed model") {
                        if settings.models.isEmpty { Text("This Agent does not advertise a remote model selector. Configure it in desktop Zed.").font(.caption) }
                        ForEach(settings.models) { model in
                            Button { Task { await session.selectModel(model) } } label: {
                                HStack {
                                    VStack(alignment: .leading) { Text(model.name); Text(model.providerID).font(.caption).foregroundStyle(.secondary) }
                                    Spacer()
                                    if model.id == "\(settings.providerID ?? "")\n\(settings.modelID ?? "")" { Image(systemName: "checkmark") }
                                }
                            }.disabled(session.state != .live || !session.capabilities.contains("thread.settings.update"))
                        }
                        if let used = settings.usedTokens, let max = settings.maxTokens { LabeledContent("Context", value: "\(used) / \(max)") }
                    }
                } else { Text("Model selection is not advertised by this Agent. Its configuration stays in desktop Zed.") }
            }.navigationTitle("Agent settings").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Done") { dismiss() } } }
        }
    }
}

struct ConversationScrollMetrics: PreferenceKey {
    static var defaultValue: [String: CGFloat] = [:]
    static func reduce(value: inout [String: CGFloat], nextValue: () -> [String: CGFloat]) { value.merge(nextValue(), uniquingKeysWith: { _, next in next }) }
}

func promptJPEG(_ image: UIImage) -> Data? {
    let size = image.size
    guard size.width > 0, size.height > 0 else { return nil }
    let scale = min(1, 1600 / max(size.width, size.height))
    let format = UIGraphicsImageRendererFormat(); format.scale = 1
    let outputSize = CGSize(width: size.width * scale, height: size.height * scale)
    let renderer = UIGraphicsImageRenderer(size: outputSize, format: format)
    let resized = renderer.image { _ in image.draw(in: CGRect(origin: .zero, size: outputSize)) }
    for quality in [0.85, 0.65, 0.45, 0.25] {
        if let data = resized.jpegData(compressionQuality: quality), data.count <= 1024 * 1024 { return data }
    }
    return nil
}
