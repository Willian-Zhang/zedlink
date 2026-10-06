package dev.zedlink.app

data class ConnectionProfile(
    val name: String,
    val endpoint: String,
    val gatewayId: String,
)

data class NativeThread(
    val id: String,
    val title: String,
    val status: String,
    val currentTurnId: Int?,
)

data class NativeCommand(
    val name: String,
    val description: String,
    val category: String,
    val requiresArgument: Boolean,
)

data class NativeApproval(
    val id: String,
    val turnId: Int?,
    val toolName: String,
    val display: String,
    val rawInput: String?,
    val detailsTruncated: Boolean,
)

data class ThreadSnapshot(
    val threadId: String,
    val title: String,
    val status: String,
    val currentTurnId: Int?,
    val instanceId: String,
    val epoch: String,
    val lastSequence: Int,
    val entries: List<String>,
    val entryStartIndex: Int,
    val totalEntries: Int,
    val hasOlderEntries: Boolean,
    val activityEntries: List<String>,
    val truncated: Boolean,
    val activityTruncated: Boolean,
    val approvals: List<NativeApproval>,
) { val isBusy: Boolean get() = status != "Idle" || currentTurnId != null }

enum class EntryKind { USER, ASSISTANT, TOOL, PLAN, APPROVAL, CONTEXT, OTHER }

data class NativeEntry(
    val kind: EntryKind,
    val label: String,
    val body: String,
    val reasoning: List<String>,
    val toolName: String? = null,
    val toolStatus: String? = null,
) {
    companion object {
        private val prefixes = listOf(
            Triple("## User\n\n", EntryKind.USER, "You"),
            Triple("## User (checkpoint)\n\n", EntryKind.USER, "You · checkpoint"),
            Triple("## Assistant\n\n", EntryKind.ASSISTANT, "Zed Agent"),
            Triple("## Input Requested\n\n", EntryKind.APPROVAL, "Input requested"),
            Triple("## Plan\n\n", EntryKind.PLAN, "Plan"),
            Triple("## Context Compaction", EntryKind.CONTEXT, "Context"),
        )

        fun parse(markdown: String): NativeEntry {
            val match = prefixes.firstOrNull { markdown.startsWith(it.first) }
            if (match != null) {
                val payload = markdown.drop(match.first.length)
                return NativeEntry(match.second, match.third, removeReasoning(payload).trim(), extractReasoning(payload))
            }
            val reasoning = extractReasoning(markdown)
            val cleaned = removeReasoning(markdown).trim()
            if (cleaned.startsWith("**Tool Call: ")) {
                val first = cleaned.lineSequence().firstOrNull().orEmpty()
                val name = first.removePrefix("**Tool Call: ").removeSuffix("**")
                val status = cleaned.lineSequence().firstOrNull { it.startsWith("Status: ") }?.removePrefix("Status: ")
                return NativeEntry(EntryKind.TOOL, "Zed tool", cleaned, reasoning, name, status)
            }
            return NativeEntry(EntryKind.OTHER, "Native entry", cleaned, reasoning)
        }

        private fun extractReasoning(markdown: String): List<String> {
            val values = mutableListOf<String>()
            var cursor = 0
            while (true) {
                val start = markdown.indexOf("<thinking>\n", cursor)
                if (start < 0) break
                val contentStart = start + "<thinking>\n".length
                val end = markdown.indexOf("\n</thinking>", contentStart)
                val value = if (end < 0) markdown.substring(contentStart).trim() else markdown.substring(contentStart, end).trim()
                if (value.isNotEmpty()) values += value
                if (end < 0) break
                cursor = end + "\n</thinking>".length
            }
            return values
        }

        private fun removeReasoning(markdown: String): String {
            var result = markdown
            while (true) {
                val start = result.indexOf("<thinking>\n")
                if (start < 0) break
                val end = result.indexOf("\n</thinking>", start + 11)
                result = if (end < 0) result.substring(0, start)
                else result.removeRange(start, end + "\n</thinking>".length)
            }
            return result
        }
    }
}
