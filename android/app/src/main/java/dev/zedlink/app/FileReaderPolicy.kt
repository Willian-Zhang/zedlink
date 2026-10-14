package dev.zedlink.app

/** Literal, case-insensitive matches within the loaded preview; bounded for UI work. */
internal fun fileMatchRanges(source: String, query: String, limit: Int = 2000): List<IntRange> {
    if (query.isEmpty() || limit <= 0) return emptyList()
    return Regex(Regex.escape(query), RegexOption.IGNORE_CASE).findAll(source).take(limit).map { it.range }.toList()
}

internal fun scopedAttachments(paths: Set<String>, savedScope: List<String?>, currentScope: List<String?>): Set<String> =
    if (savedScope == currentScope && currentScope.size == 5 && currentScope.all { !it.isNullOrBlank() }) paths else emptySet()

/** These native errors reject input before writing bytes; other failures may be uncertain. */
internal fun terminalInputRejected(code: String?): Boolean = code in setOf(
    "INVALID_REQUEST", "UNSUPPORTED_CAPABILITY", "UNAUTHENTICATED", "FORBIDDEN",
    "TERMINAL_UNAVAILABLE", "INSTANCE_UNAVAILABLE", "THREAD_NOT_EXPOSED", "REQUEST_ID_CONFLICT",
)
