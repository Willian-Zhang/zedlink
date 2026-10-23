package dev.zedlink.app

import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class AgentAlertReceiptsTest {
    @Test fun nativeReplayAndRecreationShowOneAlertPerScope() {
        val preferences = InstrumentationRegistry.getInstrumentation().targetContext
            .getSharedPreferences("agent-alert-test-${java.util.UUID.randomUUID()}", 0)
        try {
            val first = AgentAlertReceipts(preferences) { 1_000L }
            assertTrue(first.claim("gateway:target:instance:epoch:thread", "turn:12"))
            assertFalse(first.claim("gateway:target:instance:epoch:thread", "turn:12"))
            val restored = AgentAlertReceipts(preferences) { 2_000L }
            assertFalse(restored.claim("gateway:target:instance:epoch:thread", "turn:12"))
            assertTrue(restored.claim("gateway:target:instance:new-epoch:thread", "turn:12"))
            assertFalse(restored.claim("gateway:target:instance:epoch:thread", ""))
        } finally { preferences.edit().clear().commit() }
    }

    @Test fun expiredEntriesArePrunedAndStoreStaysBounded() {
        val preferences = InstrumentationRegistry.getInstrumentation().targetContext
            .getSharedPreferences("agent-alert-test-${java.util.UUID.randomUUID()}", 0)
        try {
            assertTrue(AgentAlertReceipts(preferences) { 1_000L }.claim("scope", "input:a"))
            val later = AgentAlertReceipts(preferences) { 8 * 86_400_000L + 1_001L }
            assertTrue(later.claim("scope", "input:a"))
            for (index in 0 until 140) assertTrue(later.claim("scope", "turn:$index"))
            val stored = JSONObject(preferences.getString("agent-alert-receipts", "{}") ?: "{}")
            assertTrue(stored.length() <= 128)
        } finally { preferences.edit().clear().commit() }
    }
}
