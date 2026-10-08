package dev.zedlink.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class NativeEntryTest {
    @Test fun gatewayIdentityIsIndependentOfRouteAddress() {
        val oldRoute = ConnectionProfile("Zed", "https://old.example", "gateway-1")
        val newRoute = ConnectionProfile("Zed", "https://new.example", "gateway-1")
        assertEquals(oldRoute.gatewayId, newRoute.gatewayId)
        assertTrue(oldRoute.endpoint != newRoute.endpoint)
    }

    @Test fun separatesReasoningFromAssistantAnswer() {
        val entry = NativeEntry.parse("## Assistant\n\n<thinking>\nInspecting\n</thinking>\n\nReady.")
        assertEquals(EntryKind.ASSISTANT, entry.kind)
        assertEquals(listOf("Inspecting"), entry.reasoning)
        assertEquals("Ready.", entry.body)
    }

    @Test fun keepsUnfinishedReasoningVisibleWithoutFakeBody() {
        val entry = NativeEntry.parse("## Assistant\n\n<thinking>\nStill working")
        assertEquals(listOf("Still working"), entry.reasoning)
        assertTrue(entry.body.isEmpty())
    }

    @Test fun readsToolMetadata() {
        val entry = NativeEntry.parse("**Tool Call: Run tests**\nStatus: InProgress\n\nTerminal:\n```\ncargo test\n```")
        assertEquals(EntryKind.TOOL, entry.kind)
        assertEquals("Run tests", entry.toolName)
        assertEquals("InProgress", entry.toolStatus)
    }
}
