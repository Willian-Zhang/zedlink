package dev.zedlink.app

import org.junit.Assert.*
import org.junit.Test

class FileReaderPolicyTest {
    @Test fun projectResetDropsPrivateSelectionsPreviewsAndTerminalState() {
        val profile = ConnectionProfile("Fixture", "https://fixture.example", "gateway")
        val state = AppState(profile = profile, targetId = "workspace", selectedThreadId = "thread",
            contextPaths = setOf("src/demo.kt"), contextScope = listOf("gateway", "workspace", "instance", "epoch", "thread"),
            previewTitle = "src/demo.kt", previewContent = "fixture text", previewReadable = true,
            projectFolderEntries = listOf(NativeProjectFile("src/demo.kt", "file", 12)),
            projectFolderLoading = true, terminalInputPending = true, terminalInputUncertain = true,
            terminalDelivery = "fixture delivery", terminalAcceptedDraft = "echo fixture")
        val reset = state.clearProjectAccess()
        assertTrue(reset.contextPaths.isEmpty())
        assertTrue(reset.contextScope.isEmpty())
        assertEquals("", reset.previewContent)
        assertFalse(reset.previewReadable)
        assertNull(reset.projectFolderEntries)
        assertFalse(reset.projectFolderLoading)
        assertFalse(reset.terminalInputPending)
        assertFalse(reset.terminalInputUncertain)
        assertNull(reset.terminalAcceptedDraft)
        assertEquals(profile, reset.profile)
    }
    @Test fun selectedFilesCannotCrossAnyScopeBoundary() {
        val scope = listOf("gateway", "workspace", "instance", "epoch", "thread")
        val files = setOf("src/demo.kt")
        assertEquals(files, scopedAttachments(files, scope, scope))
        scope.indices.forEach { changed ->
            val other = scope.toMutableList().also { it[changed] = "different" }
            assertTrue(scopedAttachments(files, scope, other).isEmpty())
        }
        assertTrue(scopedAttachments(files, emptyList(), scope).isEmpty())
        assertTrue(scopedAttachments(files, listOf(null, null, null, null, null), listOf(null, null, null, null, null)).isEmpty())
    }

    @Test fun findIsLiteralCaseInsensitiveAndBounded() {
        assertEquals(listOf(0..2, 8..10), fileMatchRanges("a.b and A.B", "a.b"))
        assertTrue(fileMatchRanges("abc", "").isEmpty())
        assertEquals(3, fileMatchRanges("aaaaaa", "a", 3).size)
        assertTrue(fileMatchRanges("a", "a", 0).isEmpty())
    }

    @Test fun onlyExplicitNativeRejectionsAreSafeToTreatAsRejected() {
        assertTrue(terminalInputRejected("UNSUPPORTED_CAPABILITY"))
        assertTrue(terminalInputRejected("TERMINAL_UNAVAILABLE"))
        assertFalse(terminalInputRejected(null))
        assertFalse(terminalInputRejected("INTERNAL_ERROR"))
        assertFalse(terminalInputRejected("TIMEOUT"))
    }
}
