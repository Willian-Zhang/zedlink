import SwiftUI
import UIKit

struct SessionIssueBanner: View {
    @EnvironmentObject private var session: SessionManager
    var body: some View {
        if !session.issue.isEmpty {
            HStack(alignment: .top, spacing: 8) {
                Image(systemName: "exclamationmark.triangle").foregroundStyle(ZLTheme.warning)
                Text(session.issue).font(.caption).textSelection(.enabled)
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
    private var lines: [ReviewLine] { ReviewLine.lines(content) }
    private var matches: [Int] { query.isEmpty ? [] : lines.filter { $0.text.localizedCaseInsensitiveContains(query) }.map(\.id) }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                TextField("Find in \(diff ? "diff" : "file")", text: $query)
                    .textInputAutocapitalization(.never).autocorrectionDisabled()
                    .accessibilityIdentifier("find-in-file")
                Text("\(matches.count)").font(.caption.monospaced())
                Button { if !matches.isEmpty { matchIndex = (matchIndex + 1) % matches.count } } label: { Image(systemName: "chevron.down").frame(width: 44, height: 44) }
                    .disabled(matches.isEmpty).accessibilityLabel("Next match")
                Menu {
                    Toggle("Wrap lines", isOn: $wrap)
                    if allowsExpansion { Button("Expand") { expanded = true } }
                    Button("Copy text") { UIPasteboard.general.string = content }
                } label: { Image(systemName: "ellipsis").frame(width: 44, height: 44) }
            }.padding(.horizontal, 12)
            Hairline()
            ScrollViewReader { reader in
                ScrollView(wrap ? [.vertical] : [.horizontal, .vertical]) {
                    LazyVStack(alignment: .leading, spacing: 0) {
                        ForEach(lines) { line in
                            HStack(alignment: .top, spacing: 10) {
                                Text("\(line.id)").foregroundStyle(.secondary).frame(width: 38, alignment: .trailing)
                                Text(diff ? AttributedString(line.text.isEmpty ? " " : line.text) : highlightedSource(line.text))
                                    .foregroundStyle(diff ? lineColor(line) : Color.primary)
                                    .frame(maxWidth: wrap ? .infinity : nil, alignment: .leading)
                                    .fixedSize(horizontal: !wrap, vertical: true)
                            }
                            .font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                            .padding(.vertical, 3).padding(.horizontal, 8)
                            .background(matches.contains(line.id) ? ZLTheme.warning.opacity(0.25) : lineBackground(line))
                            .id(line.id)
                        }
                    }
                }
                .task { if let initialLine { reader.scrollTo(initialLine, anchor: .center) } }
                .onChange(of: query) { _, _ in matchIndex = 0; if let first = matches.first { reader.scrollTo(first, anchor: .center) } }
                .onChange(of: matchIndex) { _, index in if matches.indices.contains(index) { reader.scrollTo(matches[index], anchor: .center) } }
            }
            if truncated { Label("Partial content · native size limit", systemImage: "exclamationmark.triangle").font(.caption).padding(8) }
        }
        .fullScreenCover(isPresented: $expanded) {
            NavigationStack {
                CodeReviewView(content: content, title: title, diff: diff, truncated: truncated, allowsExpansion: false)
                    .navigationTitle(title).navigationBarTitleDisplayMode(.inline)
                    .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Done") { expanded = false } } }
            }
        }
    }
    private func lineColor(_ line: ReviewLine) -> Color {
        switch line.kind { case .added: ZLTheme.healthy; case .removed: ZLTheme.danger; case .header: .cyan; case .plain: .primary }
    }
    private func lineBackground(_ line: ReviewLine) -> Color {
        guard diff else { return .clear }
        switch line.kind { case .added: ZLTheme.healthy.opacity(0.08); case .removed: ZLTheme.danger.opacity(0.08); default: .clear }
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
