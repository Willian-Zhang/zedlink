import SwiftUI

struct ProjectFileBrowser: View {
    @EnvironmentObject private var session: SessionManager
    @State private var directory = ""
    @State private var query = ""
    @State private var reading = false
    @State private var wrap = true

    private var entries: [NativeProjectFile] {
        let prefix = directory.isEmpty ? "" : directory + "/"
        return (query.isEmpty ? session.projectFolderEntries ?? session.projectFiles : session.projectFiles).filter { entry in
            query.isEmpty ? entry.id.hasPrefix(prefix) && !entry.id.dropFirst(prefix.count).contains("/")
                : entry.id.localizedCaseInsensitiveContains(query)
        }.sorted { left, right in
            if left.kind != right.kind { return left.kind == "directory" }
            return left.id.localizedStandardCompare(right.id) == .orderedAscending
        }
    }

    var body: some View {
        Group {
            if reading {
                VStack(alignment: .leading, spacing: 0) {
                    HStack {
                        Button { reading = false } label: { Label("Files", systemImage: "chevron.left") }
                        Spacer()
                        Toggle("Wrap", isOn: $wrap).toggleStyle(.button)
                        ShareLink(item: session.previewContent) { Image(systemName: "square.and.arrow.up") }
                            .disabled(session.previewLoading)
                    }.padding()
                    if session.previewLoading {
                        ProgressView("Loading file…").frame(maxWidth: .infinity, maxHeight: .infinity)
                    } else {
                        ScrollView(wrap ? [.vertical] : [.horizontal, .vertical]) {
                            Text(highlightedSource(session.previewContent))
                                .font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                                .frame(maxWidth: wrap ? .infinity : nil, alignment: .leading).padding()
                        }
                        Text(session.previewTruncated ? "Partial preview · 256 KiB limit · Cannot attach" : "Read-only project file")
                            .font(.caption).foregroundStyle(.secondary).padding(.horizontal)
                        Button(session.contextPaths.contains(session.previewTitle) ? "Attached" : "Attach to prompt") {
                            session.contextPaths.insert(session.previewTitle)
                        }.disabled(!session.previewReadable || session.previewLoading || session.previewTruncated || session.contextPaths.contains(session.previewTitle))
                            .padding()
                    }
                }
                .navigationTitle(session.previewTitle.split(separator: "/").last.map(String.init) ?? "File")
            } else {
                List {
                    Section {
                        Button("Project") { directory = ""; query = "" }
                        if !directory.isEmpty {
                            Text(directory).font(.caption.monospaced()).textSelection(.enabled)
                            Button { directory = directory.split(separator: "/").dropLast().joined(separator: "/") } label: {
                                Label("Parent folder", systemImage: "arrow.up")
                            }
                        }
                    }
                    Section {
                        ForEach(entries) { entry in
                            Button {
                                dismissZedLinkKeyboard()
                                if entry.kind == "directory" { directory = entry.id; query = "" }
                                else { reading = true; Task { await session.previewFile(entry.id) } }
                            } label: {
                                HStack {
                                    Image(systemName: entry.kind == "directory" ? "folder.fill" : "doc.text")
                                        .foregroundStyle(entry.kind == "directory" ? Color.blue : Color.secondary)
                                    Text(query.isEmpty ? entry.id.split(separator: "/").last.map(String.init) ?? entry.id : entry.id)
                                        .lineLimit(2)
                                    Spacer()
                                    if entry.kind == "directory" { Image(systemName: "chevron.right").foregroundStyle(.secondary) }
                                }.padding(.vertical, 4)
                            }
                        }
                        if entries.isEmpty { Text("No readable files in this folder or filter.").foregroundStyle(.secondary) }
                    }
                    if query.isEmpty ? (session.projectFolderEntries == nil ? session.projectFilesTruncated : session.projectFolderTruncated) : session.projectFilesTruncated {
                        Text("Project listing is limited to 1,000 entries. Hidden, ignored and private files are excluded.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }.searchable(text: $query, prompt: "Filter project paths")
                    .navigationTitle("Project files")
            }
        }.navigationBarTitleDisplayMode(.inline)
            .task(id: directory) { await session.loadDirectory(directory) }
    }
}

// Lightweight source colors; rendering is bounded by the native file-read limit.
private func highlightedSource(_ source: String) -> AttributedString {
    var result = AttributedString(source)
    let pattern = #"(?m)(//[^\n]*|#[^\n]*|\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|\b(?:fn|func|let|var|const|class|struct|enum|import|from|def|return|if|else|for|while|public|private|fun|val|true|false|null|nil|async|await)\b|\b\d+(?:\.\d+)?\b)"#
    guard let expression = try? NSRegularExpression(pattern: pattern) else { return result }
    for match in expression.matches(in: source, range: NSRange(source.startIndex..., in: source)).prefix(10000) {
        guard let range = Range(match.range, in: source),
              let lower = AttributedString.Index(range.lowerBound, within: result),
              let upper = AttributedString.Index(range.upperBound, within: result) else { continue }
        let attributedRange = lower..<upper
        let token = source[range]
        result[attributedRange].foregroundColor = token.hasPrefix("//") || token.hasPrefix("#") ? .gray
            : token.hasPrefix("\"") || token.hasPrefix("'") ? .green : .cyan
    }
    return result
}
