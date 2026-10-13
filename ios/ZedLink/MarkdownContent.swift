import SwiftUI
import UIKit

enum MarkdownBlock: Equatable {
    enum ColumnAlignment: Equatable { case leading, center, trailing }
    case paragraph(String)
    case heading(Int, String)
    case item(String, Int, String)
    case quote(String)
    case code(String, String)
    case table([String], [[String]], [ColumnAlignment])
    case rule
}

/// Block layout is explicit; SwiftUI Text only renders the inline Markdown styles.
enum MarkdownDocument {
    static func cells(_ line: String) -> [String] {
        var parts: [String] = [], cell = "", escaped = false, inCode = false
        let text = line.trimmingCharacters(in: .whitespaces)
        for character in text {
            if escaped {
                if character != "|" { cell.append("\\") }
                cell.append(character); escaped = false
            } else if character == "\\" { escaped = true }
            else if character == "`" { inCode.toggle(); cell.append(character) }
            else if character == "|", !inCode { parts.append(cell); cell = "" }
            else { cell.append(character) }
        }
        if escaped { cell.append("\\") }
        parts.append(cell)
        if text.hasPrefix("|"), parts.first == "" { parts.removeFirst() }
        if text.hasSuffix("|"), parts.last == "" { parts.removeLast() }
        return parts.map { $0.trimmingCharacters(in: .whitespaces) }
    }

    private static func separator(_ line: String) -> [MarkdownBlock.ColumnAlignment]? {
        let values = cells(line)
        guard !values.isEmpty, values.allSatisfy({ $0.range(of: "^:?-{3,}:?$", options: .regularExpression) != nil }) else { return nil }
        return values.map { $0.hasSuffix(":") ? ($0.hasPrefix(":") ? .center : .trailing) : .leading }
    }

    private static func item(_ line: String) -> (String, Int, String)? {
        let normalized = line.replacingOccurrences(of: "\t", with: "    ")
        let trimmed = normalized.trimmingCharacters(in: .whitespaces)
        guard let range = trimmed.range(of: "^(?:[-+*]|[0-9]+[.)]) +", options: .regularExpression) else { return nil }
        let marker = String(trimmed[range]).trimmingCharacters(in: .whitespaces)
        return (["-", "+", "*"].contains(marker) ? "•" : marker,
                normalized.prefix(while: { $0 == " " }).count, String(trimmed[range.upperBound...]))
    }

    static func parse(_ markdown: String) -> [MarkdownBlock] {
        let lines = markdown.replacingOccurrences(of: "\r\n", with: "\n").components(separatedBy: "\n")
        var blocks: [MarkdownBlock] = [], prose: [String] = [], index = 0
        func flush() {
            if !prose.isEmpty { blocks.append(.paragraph(prose.joined(separator: "\n"))); prose = [] }
        }
        while index < lines.count {
            let line = lines[index], trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.isEmpty { flush(); index += 1; continue }
            if trimmed.hasPrefix("```") || trimmed.hasPrefix("~~~") {
                flush()
                let character = trimmed.first!
                let count = trimmed.prefix(while: { $0 == character }).count
                let language = String(trimmed.dropFirst(count)).trimmingCharacters(in: .whitespaces)
                var code: [String] = []; index += 1
                while index < lines.count {
                    let closing = lines[index].trimmingCharacters(in: .whitespaces)
                    if closing.prefix(while: { $0 == character }).count >= count,
                       closing.allSatisfy({ $0 == character }) { break }
                    code.append(lines[index]); index += 1
                }
                blocks.append(.code(language, code.joined(separator: "\n"))); index += 1; continue
            }
            if index + 1 < lines.count, line.contains("|"), let alignment = separator(lines[index + 1]), cells(line).count == alignment.count {
                flush(); let headers = cells(line); var rows: [[String]] = []; index += 2
                while index < lines.count, lines[index].contains("|"), !lines[index].trimmingCharacters(in: .whitespaces).isEmpty {
                    let values = cells(lines[index])
                    rows.append(Array((values + Array(repeating: "", count: headers.count)).prefix(headers.count))); index += 1
                }
                blocks.append(.table(headers, rows, alignment)); continue
            }
            if trimmed.range(of: "^(?:-{3,}|\\*{3,}|_{3,})$", options: .regularExpression) != nil {
                flush(); blocks.append(.rule); index += 1; continue
            }
            let headingCount = trimmed.prefix(while: { $0 == "#" }).count
            if (1...6).contains(headingCount), trimmed.dropFirst(headingCount).hasPrefix(" ") {
                flush(); blocks.append(.heading(headingCount, String(trimmed.dropFirst(headingCount + 1)))); index += 1; continue
            }
            if let (marker, indent, value) = item(line) {
                flush(); var content = value; index += 1
                while index < lines.count, item(lines[index]) == nil,
                      !lines[index].trimmingCharacters(in: .whitespaces).isEmpty,
                      lines[index].prefix(while: { $0 == " " }).count > indent {
                    content += "\n" + lines[index].trimmingCharacters(in: .whitespaces); index += 1
                }
                blocks.append(.item(marker, indent, content)); continue
            }
            if trimmed.hasPrefix(">") {
                flush(); blocks.append(.quote(String(trimmed.dropFirst()).trimmingCharacters(in: .whitespaces))); index += 1; continue
            }
            prose.append(line); index += 1
        }
        flush(); return blocks
    }
}

struct NativeMarkdownView: View {
    let markdown: String
    private func inline(_ value: String) -> Text {
        let parsed = try? AttributedString(markdown: value, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace))
        return Text(parsed ?? AttributedString(value))
    }
    var body: some View {
        let blocks = MarkdownDocument.parse(markdown)
        VStack(alignment: .leading, spacing: 10) {
            ForEach(Array(blocks.enumerated()), id: \.offset) { _, block in
                switch block {
                case .paragraph(let value): inline(value).frame(maxWidth: .infinity, alignment: .leading)
                case .heading(let level, let value): inline(value).font(level <= 2 ? .title3.bold() : .headline)
                case .item(let marker, let indent, let value):
                    HStack(alignment: .top, spacing: 8) {
                        Text(marker).frame(minWidth: 18, alignment: .trailing)
                        inline(value).frame(maxWidth: .infinity, alignment: .leading)
                    }.padding(.leading, CGFloat(min(indent, 16)) * 6)
                case .quote(let value):
                    inline(value).foregroundStyle(ZLTheme.muted).padding(.leading, 12)
                        .overlay(alignment: .leading) { Rectangle().fill(ZLTheme.line).frame(width: 2) }
                case .rule: Hairline()
                case .code(let language, let code):
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Text(language.isEmpty ? "Code" : language).font(.caption.monospaced()).foregroundStyle(ZLTheme.muted)
                            Spacer()
                            Button("Copy") { UIPasteboard.general.string = code }.font(.caption).frame(minHeight: 44)
                        }
                        Text(code).font(.footnote.monospaced()).frame(maxWidth: .infinity, alignment: .leading)
                    }.padding(10).background(ZLTheme.surface)
                case .table(let headers, let rows, let alignments):
                    ScrollView(.horizontal) {
                        VStack(alignment: .leading, spacing: 0) {
                            tableRow(headers, alignments: alignments, header: true)
                            ForEach(Array(rows.enumerated()), id: \.offset) { _, row in tableRow(row, alignments: alignments, header: false) }
                        }.overlay(Rectangle().stroke(ZLTheme.line, lineWidth: 1))
                    }.accessibilityIdentifier("markdown-table")
                }
            }
        }.foregroundStyle(ZLTheme.ink).textSelection(.enabled)
    }
    private func tableRow(_ cells: [String], alignments: [MarkdownBlock.ColumnAlignment], header: Bool) -> some View {
        VStack(spacing: 0) {
            HStack(alignment: .top, spacing: 0) {
                ForEach(Array(cells.enumerated()), id: \.offset) { index, value in
                    inline(value).font(header ? .subheadline.bold() : .subheadline)
                        .frame(width: 136, alignment: alignments[index] == .center ? .center : alignments[index] == .trailing ? .trailing : .leading)
                        .multilineTextAlignment(alignments[index] == .center ? .center : alignments[index] == .trailing ? .trailing : .leading)
                        .padding(10)
                }
            }.background(header ? ZLTheme.surface : ZLTheme.background)
            Hairline()
        }
    }
}
