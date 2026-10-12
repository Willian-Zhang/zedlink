import SwiftUI

struct ProjectFileBrowser: View {
    @EnvironmentObject private var session: SessionManager
    @State private var directory = ""
    @State private var query = ""
    @State private var reading = false
    @State private var contentQuery = ""
    @State private var matches: [ProjectSearchMatch] = []
    @State private var searchStatus = ""
    @State private var searchTask: Task<Void, Never>?
    @State private var selectedLine: Int?

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
                        ShareLink(item: session.previewContent) { Image(systemName: "square.and.arrow.up") }
                            .disabled(session.previewLoading)
                    }.padding()
                    if session.previewLoading {
                        ProgressView("Loading file…").frame(maxWidth: .infinity, maxHeight: .infinity)
                    } else {
                        CodeReviewView(content: session.previewContent, title: session.previewTitle, truncated: session.previewTruncated, initialLine: selectedLine)
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
                    if session.capabilities.contains("project.search") {
                        Section("Search contents") {
                            HStack {
                                TextField("Text in project", text: $contentQuery)
                                    .textInputAutocapitalization(.never).autocorrectionDisabled()
                                    .accessibilityIdentifier("project-content-query")
                                    .onSubmit { searchContents() }
                                Button("Search") { searchContents() }.disabled(contentQuery.count < 2)
                            }
                            if !searchStatus.isEmpty { Text(searchStatus).font(.caption) }
                            ForEach(matches) { match in
                                Button {
                                    selectedLine = match.line; reading = true; dismissZedLinkKeyboard()
                                    Task { await session.previewFile(match.path) }
                                } label: {
                                    VStack(alignment: .leading) {
                                        Text("\(match.path):\(match.line)").font(.caption.monospaced())
                                        Text(match.preview).font(.caption).lineLimit(2)
                                    }
                                }.accessibilityIdentifier("project-search-result-" + match.id)
                            }
                        }
                    }
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
                                else { selectedLine = nil; reading = true; Task { await session.previewFile(entry.id) } }
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
            .onDisappear { searchTask?.cancel() }
            .onChange(of: session.operationScope) { _, _ in searchTask?.cancel(); matches = []; searchStatus = ""; reading = false }
    }

    private func searchContents() {
        searchTask?.cancel(); matches = []; searchStatus = "Searching…"; dismissZedLinkKeyboard()
        let query = contentQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        guard query.count >= 2 else { searchStatus = "Enter at least two characters."; return }
        searchTask = Task {
            do {
                let result = try await session.searchProject(query)
                try Task.checkCancellation()
                matches = result.matches
                searchStatus = "\(matches.count) matches" + (result.truncated ? " · results limited" : "")
            } catch is CancellationError {} catch { searchStatus = error.localizedDescription }
        }
    }
}

// Lightweight source colors; rendering is bounded by the native file-read limit.
func highlightedSource(_ source: String) -> AttributedString {
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
