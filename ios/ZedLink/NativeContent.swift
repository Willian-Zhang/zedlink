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
