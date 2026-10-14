package dev.zedlink.app

import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test

class NotificationReceiptsTest {
    @Test fun receiptsSurviveRecreationAndAreConsumedOnlyOnce() {
        val preferences = InstrumentationRegistry.getInstrumentation().targetContext
            .getSharedPreferences("receipt-test-${java.util.UUID.randomUUID()}", 0)
        try {
            val fields = mapOf("gateway" to "fixture", "thread" to "thread", "approval" to "approval")
            val nonce = NotificationReceipts(preferences) { 1000L }.put(fields, "review")
            val restored = NotificationReceipts(preferences) { 2000L }
            assertEquals(fields to "review", restored.consume(nonce))
            assertNull(restored.consume(nonce))
            assertNull(restored.consume("forged"))
        } finally { preferences.edit().clear().commit() }
    }
    @Test fun expiredAndResolvedApprovalsCannotBeReplayed() {
        val preferences = InstrumentationRegistry.getInstrumentation().targetContext
            .getSharedPreferences("receipt-test-${java.util.UUID.randomUUID()}", 0)
        try {
            val store = NotificationReceipts(preferences) { 1000L }
            val expired = store.put(mapOf("approval" to "old"), "approve")
            assertNull(NotificationReceipts(preferences) { 86401001L }.consume(expired))
            val resolved = store.put(mapOf("approval" to "resolved"), "approve")
            store.prune { it["approval"] == "pending" }
            assertNull(store.consume(resolved))
        } finally { preferences.edit().clear().commit() }
    }
}
