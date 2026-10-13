package dev.zedlink.app

import org.junit.Assert.*
import org.junit.Test

class SessionActivityTest {
    @Test fun respectsNativeActivityAttentionAndRetryPrecedence() {
        val thread = NativeThread("fixture", "Demo", "Unknown", null)
        assertEquals(SessionActivity.UNKNOWN, SessionActivity.from(thread))
        assertEquals(SessionActivity.READY, SessionActivity.from(thread.copy(status = "Idle")))
        assertEquals(SessionActivity.FAILED, SessionActivity.from(thread.copy(status = "Idle", failed = true)))
        assertEquals(SessionActivity.GENERATING, SessionActivity.from(thread.copy(status = "Generating", failed = true)))
        assertEquals(SessionActivity.RETRYING, SessionActivity.from(thread.copy(retrying = true)))
        assertEquals(SessionActivity.INPUT, SessionActivity.from(thread.copy(inputCount = 1)))
        assertEquals(SessionActivity.APPROVAL, SessionActivity.from(thread.copy(retrying = true, approvalCount = 2)))
    }
}
