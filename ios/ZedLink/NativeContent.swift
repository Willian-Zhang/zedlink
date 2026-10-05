import SwiftUI

struct NativeEntryPresentation: Identifiable, Equatable {
    enum Kind: Equatable { case user, assistant, tool, plan, approval, context, other }

    let id: Int
    let kind: Kind
    let label: String
    let body: String
    let reasoning: [String]
    let toolName: String?
    let toolStatus: String?

    init(_ markdown: String, index: Int) {
        id = index
        let prefixes: [(String, Kind, String)] = [
            ("## User\n\n", .user, "You"),
            ("## User (checkpoint)\n\n", .user, "You · checkpoint"),
            ("## Assistant\n\n", .assistant, "Zed Agent"),
            ("## Input Requested\n\n", .approval, "Input requested"),
            ("## Plan\n\n", .plan, "Plan"),
            ("## Context Compaction", .context, "Context")
        ]
        if let match = prefixes.first(where: { markdown.hasPrefix($0.0) }) {
            let payload = String(markdown.dropFirst(match.0.count))
            kind = match.1
            label = match.2
            reasoning = Self.extractReasoning(payload)
            body = Self.removingReasoning(payload).trimmingCharacters(in: .whitespacesAndNewlines)
            toolName = nil
            toolStatus = nil
        } else {
            let cleaned = Self.removingReasoning(markdown).trimmingCharacters(in: .whitespacesAndNewlines)
            reasoning = Self.extractReasoning(markdown)
            if cleaned.hasPrefix("**Tool Call: ") {
                kind = .tool
                let firstLine = cleaned.split(separator: "\n", maxSplits: 1).first.map(String.init) ?? "Tool"
                toolName = firstLine
                    .replacingOccurrences(of: "**Tool Call: ", with: "")
                    .replacingOccurrences(of: "**", with: "")
                let statusLine = cleaned.split(separator: "\n").first { $0.hasPrefix("Status: ") }
                toolStatus = statusLine.map { String($0.dropFirst("Status: ".count)) }
                label = "Zed tool"
                body = cleaned
            } else {
                kind = .other
                label = "Native entry \(index + 1)"
                body = cleaned
                toolName = nil
                toolStatus = nil
            }
        }
    }

    private static func extractReasoning(_ markdown: String) -> [String] {
        var values: [String] = []
        var remainder = markdown[...]
        while let start = remainder.range(of: "<thinking>\n") {
            let contentStart = start.upperBound
            guard let end = remainder[contentStart...].range(of: "\n</thinking>") else {
                let value = remainder[contentStart...].trimmingCharacters(in: .whitespacesAndNewlines)
                if !value.isEmpty { values.append(value) }
                break
            }
            let value = remainder[contentStart..<end.lowerBound].trimmingCharacters(in: .whitespacesAndNewlines)
            if !value.isEmpty { values.append(value) }
            remainder = remainder[end.upperBound...]
        }
        return values
    }

    private static func removingReasoning(_ markdown: String) -> String {
        var result = markdown
        while let start = result.range(of: "<thinking>\n") {
            if let end = result[start.upperBound...].range(of: "\n</thinking>") {
                result.removeSubrange(start.lowerBound..<end.upperBound)
            } else {
                result.removeSubrange(start.lowerBound..<result.endIndex)
            }
        }
        return result
    }
}

private enum MarkdownBlock: Identifiable {
    case prose(Int, String)
    case code(Int, String, String)
    var id: Int {
        switch self { case .prose(let id, _), .code(let id, _, _): id }
    }
}

struct NativeMarkdownView: View {
    let markdown: String

    private var blocks: [MarkdownBlock] {
        let pieces = markdown.components(separatedBy: "```")
        return pieces.enumerated().compactMap { index, value in
            guard !value.isEmpty else { return nil }
            if index.isMultiple(of: 2) { return .prose(index, value) }
            let lines = value.split(separator: "\n", omittingEmptySubsequences: false)
            let language = lines.first.map(String.init) ?? ""
            return .code(index, language, lines.dropFirst().joined(separator: "\n"))
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            ForEach(blocks) { block in
                switch block {
                case .prose(_, let text):
                    if let attributed = try? AttributedString(markdown: text) {
                        Text(attributed).textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    } else {
                        Text(text).textSelection(.enabled)
                    }
                case .code(_, let language, let code):
                    VStack(alignment: .leading, spacing: 7) {
                        if !language.isEmpty {
                            Text(language.uppercased())
                                .font(.caption2.monospaced()).foregroundStyle(ZLTheme.muted)
                        }
                        ScrollView(.horizontal, showsIndicators: false) {
                            Text(code).font(.footnote.monospaced()).textSelection(.enabled)
                                .fixedSize(horizontal: true, vertical: false)
                        }
                    }
                    .padding(11)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(ZLTheme.background)
                    .overlay(Rectangle().stroke(ZLTheme.line, lineWidth: 1))
                }
            }
        }
    }
}
