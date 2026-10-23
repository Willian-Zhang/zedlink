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
    private final class BlocksBox: NSObject {
        let value: [MarkdownBlock]
        init(_ value: [MarkdownBlock]) { self.value = value }
    }
    private final class InlineBox: NSObject {
        let value: AttributedString
        init(_ value: AttributedString) { self.value = value }
    }
    private static let blockCache: NSCache<NSString, BlocksBox> = {
        let cache = NSCache<NSString, BlocksBox>()
        cache.countLimit = 256
        cache.totalCostLimit = 4 * 1024 * 1024
        return cache
    }()
    private static let inlineCache: NSCache<NSString, InlineBox> = {
        let cache = NSCache<NSString, InlineBox>()
        cache.countLimit = 512
        cache.totalCostLimit = 2 * 1024 * 1024
        return cache
    }()

    static func cachedBlocks(_ markdown: String) -> [MarkdownBlock] {
        let key = markdown as NSString
        if let cached = blockCache.object(forKey: key) { return cached.value }
        let blocks = parse(markdown)
        if markdown.utf8.count <= 512 * 1024 {
            blockCache.setObject(BlocksBox(blocks), forKey: key, cost: markdown.utf8.count)
        }
        return blocks
    }

    static func cachedInline(_ value: String) -> AttributedString {
        let key = value as NSString
        if let cached = inlineCache.object(forKey: key) { return cached.value }
        let parsed = (try? AttributedString(markdown: value, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)))
            ?? AttributedString(value)
        if value.utf8.count <= 128 * 1024 {
            inlineCache.setObject(InlineBox(parsed), forKey: key, cost: value.utf8.count)
        }
        return parsed
    }

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

    @ViewBuilder private func inline(_ value: String, style: SelectableMarkdownStyle = .body) -> some View {
        if #available(iOS 27, *) {
            Text(MarkdownDocument.cachedInline(value))
                .font(style.swiftUIFont)
                .foregroundStyle(style == .quote ? ZLTheme.muted : ZLTheme.ink)
                .textSelection(.enabled)
        } else {
            InlineSelectableMarkdownText(value: value, style: style, markdown: true)
        }
    }

    @ViewBuilder private func code(_ value: String) -> some View {
        if #available(iOS 27, *) {
            Text(value).font(.footnote.monospaced()).textSelection(.enabled)
        } else {
            InlineSelectableMarkdownText(value: value, style: .code, markdown: false)
        }
    }
    var body: some View {
        let blocks = MarkdownDocument.cachedBlocks(markdown)
        VStack(alignment: .leading, spacing: 10) {
            ForEach(Array(blocks.enumerated()), id: \.offset) { _, block in
                switch block {
                case .paragraph(let value): inline(value).frame(maxWidth: .infinity, alignment: .leading)
                case .heading(let level, let value): inline(value, style: level <= 2 ? .headingLarge : .headingSmall)
                case .item(let marker, let indent, let value):
                    HStack(alignment: .top, spacing: 8) {
                        Text(marker).frame(minWidth: 18, alignment: .trailing)
                        inline(value).frame(maxWidth: .infinity, alignment: .leading)
                    }.padding(.leading, CGFloat(min(indent, 16)) * 6)
                case .quote(let value):
                    inline(value, style: .quote).padding(.leading, 12)
                        .overlay(alignment: .leading) { Rectangle().fill(ZLTheme.line).frame(width: 2) }
                case .rule: Hairline()
                case .code(let language, let code):
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Text(language.isEmpty ? "Code" : language).font(.caption.monospaced()).foregroundStyle(ZLTheme.muted)
                            Spacer()
                            Button("Copy") { UIPasteboard.general.string = code }.font(.caption).frame(minHeight: 44)
                        }
                        self.code(code).frame(maxWidth: .infinity, alignment: .leading)
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
                    inline(value, style: header ? .tableHeader : .tableCell)
                        .frame(width: 136, alignment: alignments[index] == .center ? .center : alignments[index] == .trailing ? .trailing : .leading)
                        .multilineTextAlignment(alignments[index] == .center ? .center : alignments[index] == .trailing ? .trailing : .leading)
                        .padding(10)
                }
            }.background(header ? ZLTheme.surface : ZLTheme.background)
            Hairline()
        }
    }
}

private enum SelectableMarkdownStyle: Equatable {
    case body, headingLarge, headingSmall, quote, code, tableHeader, tableCell

    var swiftUIFont: Font {
        switch self {
        case .body, .quote: .body
        case .headingLarge: .title3.bold()
        case .headingSmall: .headline
        case .code: .footnote.monospaced()
        case .tableHeader: .subheadline.bold()
        case .tableCell: .subheadline
        }
    }

    func uiFont(compatibleWith traits: UITraitCollection) -> UIFont {
        let textStyle: UIFont.TextStyle = switch self {
        case .body, .quote: .body
        case .headingLarge: .title3
        case .headingSmall: .headline
        case .code: .footnote
        case .tableHeader, .tableCell: .subheadline
        }
        let preferred = UIFont.preferredFont(forTextStyle: textStyle, compatibleWith: traits)
        if self == .code { return .monospacedSystemFont(ofSize: preferred.pointSize, weight: .regular) }
        guard self == .headingLarge || self == .headingSmall || self == .tableHeader,
              let descriptor = preferred.fontDescriptor.withSymbolicTraits(preferred.fontDescriptor.symbolicTraits.union(.traitBold)) else {
            return preferred
        }
        return UIFont(descriptor: descriptor, size: preferred.pointSize)
    }
}

/// UITextView provides word-range handles on iOS 17–26, where SwiftUI Text selects a whole view.
private struct InlineSelectableMarkdownText: UIViewRepresentable {
    let value: String
    let style: SelectableMarkdownStyle
    let markdown: Bool
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    final class Coordinator {
        var value: String?
        var style: SelectableMarkdownStyle?
        var markdown: Bool?
        var colorScheme: ColorScheme?
        var dynamicTypeSize: DynamicTypeSize?
        var contentSizeCategory: UIContentSizeCategory?
        var interfaceStyle: UIUserInterfaceStyle?

        func matches(_ source: InlineSelectableMarkdownText, traits: UITraitCollection) -> Bool {
            value == source.value && style == source.style && markdown == source.markdown &&
            colorScheme == source.colorScheme && dynamicTypeSize == source.dynamicTypeSize &&
            contentSizeCategory == traits.preferredContentSizeCategory && interfaceStyle == traits.userInterfaceStyle
        }

        func record(_ source: InlineSelectableMarkdownText, traits: UITraitCollection) {
            value = source.value
            style = source.style
            markdown = source.markdown
            colorScheme = source.colorScheme
            dynamicTypeSize = source.dynamicTypeSize
            contentSizeCategory = traits.preferredContentSizeCategory
            interfaceStyle = traits.userInterfaceStyle
        }
    }

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeUIView(context: Context) -> UITextView {
        let view = UITextView()
        view.isEditable = false
        view.isSelectable = true
        view.isScrollEnabled = false
        view.adjustsFontForContentSizeCategory = true
        view.backgroundColor = .clear
        view.textContainerInset = .zero
        view.textContainer.lineFragmentPadding = 0
        view.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        view.attributedText = Self.styled(markdown ? MarkdownDocument.cachedInline(value) : AttributedString(value),
                                         style: style, traits: view.traitCollection)
        context.coordinator.record(self, traits: view.traitCollection)
        return view
    }

    func updateUIView(_ view: UITextView, context: Context) {
        guard !context.coordinator.matches(self, traits: view.traitCollection) else { return }
        let parsed = markdown ? MarkdownDocument.cachedInline(value) : AttributedString(value)
        let styled = Self.styled(parsed, style: style, traits: view.traitCollection)
        context.coordinator.record(self, traits: view.traitCollection)
        guard !view.attributedText.isEqual(to: styled) else { return }
        let selection = view.selectedRange
        view.attributedText = styled
        if selection.location <= styled.length, selection.length <= styled.length - selection.location {
            view.selectedRange = selection
        }
        view.invalidateIntrinsicContentSize()
    }

    func sizeThatFits(_ proposal: ProposedViewSize, uiView: UITextView, context: Context) -> CGSize? {
        guard let width = proposal.width, width > 0 else { return nil }
        let height = uiView.sizeThatFits(CGSize(width: width, height: .greatestFiniteMagnitude)).height
        return CGSize(width: width, height: ceil(height))
    }

    private static func styled(_ text: AttributedString, style: SelectableMarkdownStyle, traits: UITraitCollection) -> NSAttributedString {
        let result = NSMutableAttributedString(attributedString: NSAttributedString(text))
        guard result.length > 0 else { return result }
        let baseFont = style.uiFont(compatibleWith: traits)
        let baseColor = style == .quote ? UIColor.secondaryLabel : UIColor.label
        result.addAttributes([.font: baseFont, .foregroundColor: baseColor], range: NSRange(location: 0, length: result.length))
        var location = 0
        for run in text.runs {
            let length = (String(text[run.range].characters) as NSString).length
            let range = NSRange(location: location, length: length)
            location += length
            guard length > 0, range.location <= result.length,
                  range.length <= result.length - range.location else { continue }
            if let intent = run.inlinePresentationIntent {
                var font = baseFont
                if intent.contains(.code) { font = .monospacedSystemFont(ofSize: baseFont.pointSize, weight: .regular) }
                var traits = font.fontDescriptor.symbolicTraits
                if intent.contains(.stronglyEmphasized) { traits.insert(.traitBold) }
                if intent.contains(.emphasized) { traits.insert(.traitItalic) }
                if let descriptor = font.fontDescriptor.withSymbolicTraits(traits) {
                    font = UIFont(descriptor: descriptor, size: font.pointSize)
                }
                result.addAttribute(.font, value: font, range: range)
                if intent.contains(.strikethrough) {
                    result.addAttribute(.strikethroughStyle, value: NSUnderlineStyle.single.rawValue, range: range)
                }
            }
            if run.link != nil {
                result.addAttributes([.foregroundColor: UIColor.link, .underlineStyle: NSUnderlineStyle.single.rawValue], range: range)
            }
        }
        return result
    }
}
