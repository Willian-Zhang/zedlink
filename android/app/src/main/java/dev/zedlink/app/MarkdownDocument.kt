package dev.zedlink.app

sealed interface MarkdownBlock {
    data class Paragraph(val text: String) : MarkdownBlock
    data class Heading(val level: Int, val text: String) : MarkdownBlock
    data class Item(val marker: String, val indent: Int, val text: String) : MarkdownBlock
    data class Quote(val text: String) : MarkdownBlock
    data class Code(val language: String, val text: String) : MarkdownBlock
    data class Table(val headers: List<String>, val rows: List<List<String>>, val alignments: List<ColumnAlignment>) : MarkdownBlock
    data object Rule : MarkdownBlock
}

enum class ColumnAlignment { LEADING, CENTER, TRAILING }

object MarkdownDocument {
    private val itemPattern = Regex("^(?:[-+*]|[0-9]+[.)]) +")
    private val separatorPattern = Regex("^:?-{3,}:?$")
    private val rulePattern = Regex("^(?:-{3,}|\\*{3,}|_{3,})$")

    fun cells(line: String): List<String> {
        val text = line.trim()
        val parts = mutableListOf<String>()
        val cell = StringBuilder()
        var escaped = false
        var inCode = false
        text.forEach { character ->
            when {
                escaped -> { if (character != '|') cell.append('\\'); cell.append(character); escaped = false }
                character == '\\' -> escaped = true
                character == '`' -> { inCode = !inCode; cell.append(character) }
                character == '|' && !inCode -> { parts.add(cell.toString()); cell.clear() }
                else -> cell.append(character)
            }
        }
        if (escaped) cell.append('\\')
        parts.add(cell.toString())
        if (text.startsWith('|') && parts.first() == "") parts.removeAt(0)
        if (text.endsWith('|') && parts.lastOrNull() == "") parts.removeAt(parts.lastIndex)
        return parts.map(String::trim)
    }

    private fun separator(line: String): List<ColumnAlignment>? {
        val values = cells(line)
        if (values.isEmpty() || values.any { !separatorPattern.matches(it) }) return null
        return values.map { if (it.endsWith(':')) { if (it.startsWith(':')) ColumnAlignment.CENTER else ColumnAlignment.TRAILING } else ColumnAlignment.LEADING }
    }

    private fun item(line: String): MarkdownBlock.Item? {
        val normalized = line.replace("\t", "    ")
        val text = normalized.trim()
        val match = itemPattern.find(text) ?: return null
        val marker = match.value.trim()
        return MarkdownBlock.Item(if (marker in listOf("-", "+", "*")) "•" else marker,
            normalized.takeWhile { it == ' ' }.length, text.substring(match.range.last + 1))
    }

    fun parse(markdown: String): List<MarkdownBlock> {
        val lines = markdown.replace("\r\n", "\n").split('\n')
        val blocks = mutableListOf<MarkdownBlock>()
        val prose = mutableListOf<String>()
        var index = 0
        fun flush() { if (prose.isNotEmpty()) { blocks.add(MarkdownBlock.Paragraph(prose.joinToString("\n"))); prose.clear() } }
        while (index < lines.size) {
            val line = lines[index]
            val text = line.trim()
            if (text.isEmpty()) { flush(); index++; continue }
            if (text.startsWith("```") || text.startsWith("~~~")) {
                flush()
                val character = text.first()
                val count = text.takeWhile { it == character }.length
                val language = text.drop(count).trim()
                val code = mutableListOf<String>(); index++
                while (index < lines.size) {
                    val closing = lines[index].trim()
                    if (closing.takeWhile { it == character }.length >= count && closing.all { it == character }) break
                    code.add(lines[index]); index++
                }
                blocks.add(MarkdownBlock.Code(language, code.joinToString("\n"))); index++; continue
            }
            val alignments = if (index + 1 < lines.size && '|' in line) separator(lines[index + 1]) else null
            if (alignments != null && cells(line).size == alignments.size) {
                flush(); val headers = cells(line); val rows = mutableListOf<List<String>>(); index += 2
                while (index < lines.size && '|' in lines[index] && lines[index].isNotBlank()) {
                    rows.add((cells(lines[index]) + List(headers.size) { "" }).take(headers.size)); index++
                }
                blocks.add(MarkdownBlock.Table(headers, rows, alignments)); continue
            }
            if (rulePattern.matches(text)) { flush(); blocks.add(MarkdownBlock.Rule); index++; continue }
            val heading = text.takeWhile { it == '#' }.length
            if (heading in 1..6 && text.drop(heading).startsWith(' ')) {
                flush(); blocks.add(MarkdownBlock.Heading(heading, text.drop(heading + 1))); index++; continue
            }
            val listItem = item(line)
            if (listItem != null) {
                flush(); var content = listItem.text; index++
                while (index < lines.size && item(lines[index]) == null && lines[index].isNotBlank() && lines[index].takeWhile { it == ' ' }.length > listItem.indent) {
                    content += "\n" + lines[index].trim(); index++
                }
                blocks.add(listItem.copy(text = content)); continue
            }
            if (text.startsWith('>')) { flush(); blocks.add(MarkdownBlock.Quote(text.drop(1).trim())); index++; continue }
            prose.add(line); index++
        }
        flush(); return blocks
    }
}
