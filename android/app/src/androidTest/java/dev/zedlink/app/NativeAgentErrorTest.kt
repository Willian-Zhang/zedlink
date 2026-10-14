package dev.zedlink.app

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

/** Uses Android's real JSON implementation, rather than the host's stub android.jar. */
class NativeAgentErrorTest {
    @Test fun nativeContextAndConnectionErrorsArePreserved() {
        listOf("Input too long (~76332 tokens, max 65536). Shorten your context.", "Connection refused by model server").forEach { message ->
            val snapshot = JSONObject().put("agent_error", JSONObject().put("kind", "model_error")
                .put("title", "An error happened").put("message", message).put("retrying", false))
            val decoded = NativeAgentError.decode(snapshot)
            assertEquals(message, decoded?.message)
            assertEquals("model_error", decoded?.kind)
            assertEquals(false, decoded?.retrying)
        }
    }
    @Test fun malformedErrorsFallbackAndRecovery() {
        assertNotNull(NativeAgentError.decode(JSONObject().put("had_error", true)))
        assertNull(NativeAgentError.decode(JSONObject().put("had_error", false).put("agent_error", JSONObject.NULL)))
        assertNull(NativeAgentError.decode(JSONObject().put("agent_error", JSONObject().put("title", 42).put("message", "invalid"))))
        assertEquals(true, NativeAgentError.decode(JSONObject().put("agent_error", JSONObject()
            .put("title", "Retry").put("message", "Busy").put("retrying", true)))?.retrying)
    }
}
