package dev.zedlink.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class MarkdownDocumentTest {
    @Test fun preservesParagraphsAndNestedListMarkers() {
        assertEquals(listOf(
            MarkdownBlock.Paragraph("Intro\ncontinued"),
            MarkdownBlock.Heading(2, "List"),
            MarkdownBlock.Item("•", 0, "**Bold**"),
            MarkdownBlock.Item("•", 2, "Nested `code`"),
            MarkdownBlock.Item("1.", 0, "First"),
            MarkdownBlock.Paragraph("Final paragraph")
        ), MarkdownDocument.parse("Intro\ncontinued\n\n## List\n- **Bold**\n  - Nested `code`\n1. First\n\nFinal paragraph"))
    }
    @Test fun buildsAlignedTablesWithoutLosingEmptyOrEscapedCells() {
        val table = MarkdownDocument.parse("| Feature | Status | Notes |\n| :--- | :---: | ---: |\n| Bullets | ✅ | a\\|b |\n| Files | | `x|y` |").single() as MarkdownBlock.Table
        assertEquals(listOf("Feature", "Status", "Notes"), table.headers)
        assertEquals(listOf(ColumnAlignment.LEADING, ColumnAlignment.CENTER, ColumnAlignment.TRAILING), table.alignments)
        assertEquals(listOf(listOf("Bullets", "✅", "a|b"), listOf("Files", "", "`x|y`")), table.rows)
    }
    @Test fun keepsStreamingCodeAndLiteralMarkdownInFences() {
        assertEquals(listOf(MarkdownBlock.Code("rust", "- literal\n| not a table |")), MarkdownDocument.parse("```rust\n- literal\n| not a table |"))
        assertEquals(listOf(MarkdownBlock.Code("", "hello"), MarkdownBlock.Paragraph("After")), MarkdownDocument.parse("~~~\nhello\n~~~\nAfter"))
    }
    @Test fun malformedTableRemainsReadableAndListContinuationStaysWithItem() {
        assertTrue(MarkdownDocument.parse("a | b\n-- | nope").single() is MarkdownBlock.Paragraph)
        assertEquals(listOf(MarkdownBlock.Item("•", 0, "long\ncontinued"), MarkdownBlock.Item("•", 0, "next")), MarkdownDocument.parse("- long\n  continued\n- next"))
    }
}
