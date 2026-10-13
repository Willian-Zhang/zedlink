package dev.zedlink.app

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

private val inlinePattern = Regex("`([^`]+)`|\\*\\*(.+?)\\*\\*|__(.+?)__|\\*([^*]+)\\*|_([^_]+)_|~~(.+?)~~|\\[([^]]+)]\\(([^)]+)\\)")
fun inlineMarkdown(text: String): AnnotatedString = buildAnnotatedString {
    var offset = 0
    inlinePattern.findAll(text).forEach { match ->
        append(text.substring(offset, match.range.first))
        val group = (1..8).first { match.groups[it] != null }
        val value = match.groups[group]!!.value
        val style = when (group) {
            1 -> SpanStyle(fontFamily = FontFamily.Monospace)
            2, 3 -> SpanStyle(fontWeight = FontWeight.Bold)
            4, 5 -> SpanStyle(fontStyle = FontStyle.Italic)
            6 -> SpanStyle(textDecoration = TextDecoration.LineThrough)
            else -> SpanStyle(textDecoration = TextDecoration.Underline)
        }
        pushStyle(style)
        if (group == 7) pushStringAnnotation("URL", match.groups[8]!!.value)
        append(if (group == 1) AnnotatedString(value) else inlineMarkdown(value))
        if (group == 7) pop()
        pop()
        offset = match.range.last + 1
    }
    append(text.substring(offset))
}

@Composable
fun NativeMarkdown(text: String, modifier: Modifier, ink: Color, muted: Color, line: Color, surface: Color) {
    val blocks = remember(text) { MarkdownDocument.parse(text) }
    Column(modifier, verticalArrangement = Arrangement.spacedBy(10.dp)) {
        blocks.forEach { block ->
            when (block) {
                is MarkdownBlock.Paragraph -> Text(inlineMarkdown(block.text), color = ink, fontSize = 15.sp, lineHeight = 23.sp)
                is MarkdownBlock.Heading -> Text(inlineMarkdown(block.text), color = ink, fontWeight = FontWeight.Bold, fontSize = if (block.level <= 2) 20.sp else 17.sp)
                is MarkdownBlock.Item -> Row(Modifier.padding(start = (block.indent.coerceAtMost(16) * 6).dp), verticalAlignment = Alignment.Top) {
                    Text(block.marker, color = ink, modifier = Modifier.widthIn(min = 18.dp).padding(end = 8.dp))
                    Text(inlineMarkdown(block.text), color = ink, fontSize = 15.sp, lineHeight = 23.sp, modifier = Modifier.weight(1f))
                }
                is MarkdownBlock.Quote -> Text(inlineMarkdown(block.text), color = muted, modifier = Modifier.border(1.dp, line).padding(10.dp))
                is MarkdownBlock.Code -> Column(Modifier.fillMaxWidth().background(surface).border(1.dp, line).padding(10.dp)) {
                    if (block.language.isNotEmpty()) Text(block.language, color = muted, fontSize = 11.sp)
                    Text(block.text, color = ink, fontFamily = FontFamily.Monospace, fontSize = 12.sp, softWrap = true)
                }
                MarkdownBlock.Rule -> Box(Modifier.fillMaxWidth().height(1.dp).background(line))
                is MarkdownBlock.Table -> Column(Modifier.horizontalScroll(rememberScrollState()).border(1.dp, line)) {
                    MarkdownTableRow(block.headers, block.alignments, true, ink, line, surface)
                    block.rows.forEach { MarkdownTableRow(it, block.alignments, false, ink, line, surface) }
                }
            }
        }
    }
}

@Composable
private fun MarkdownTableRow(cells: List<String>, alignments: List<ColumnAlignment>, header: Boolean, ink: Color, line: Color, surface: Color) {
    Column {
        Row(Modifier.background(if (header) surface else Color.Transparent), verticalAlignment = Alignment.Top) {
            cells.forEachIndexed { index, text ->
                Text(inlineMarkdown(text), color = ink, fontSize = 14.sp,
                    fontWeight = if (header) FontWeight.Bold else FontWeight.Normal,
                    textAlign = when (alignments[index]) { ColumnAlignment.LEADING -> TextAlign.Start; ColumnAlignment.CENTER -> TextAlign.Center; ColumnAlignment.TRAILING -> TextAlign.End },
                    modifier = Modifier.width(156.dp).padding(10.dp))
            }
        }
        Box(Modifier.fillMaxWidth().height(1.dp).background(line))
    }
}
