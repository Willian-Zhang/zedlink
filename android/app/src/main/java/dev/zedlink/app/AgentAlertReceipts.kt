package dev.zedlink.app

import android.content.SharedPreferences
import org.json.JSONObject
import java.security.MessageDigest

/** A bounded record of native events already shown on this device. No transcript is stored. */
internal class AgentAlertReceipts(
    private val preferences: SharedPreferences,
    private val now: () -> Long = System::currentTimeMillis,
) {
    private val key = "agent-alert-receipts"
    private val lifetime = 7 * 86_400_000L

    @Synchronized fun claim(scope: String, token: String): Boolean {
        if (scope.isBlank() || token.isBlank() || token.length > 320) return false
        val digest = MessageDigest.getInstance("SHA-256")
            .digest("$scope:$token".toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it.toInt() and 255) }
        val time = now()
        val saved = runCatching { JSONObject(preferences.getString(key, "{}") ?: "{}") }.getOrDefault(JSONObject())
        val recent = saved.keys().asSequence().mapNotNull { id ->
            val timestamp = saved.optLong(id, -1L)
            if (timestamp in (time - lifetime)..time) id to timestamp else null
        }.toMap().toMutableMap()
        if (digest in recent) return false
        recent[digest] = time
        recent.entries.sortedBy { it.value }.take((recent.size - 128).coerceAtLeast(0)).forEach { recent.remove(it.key) }
        val updated = JSONObject()
        recent.forEach { (id, timestamp) -> updated.put(id, timestamp) }
        return preferences.edit().putString(key, updated.toString()).commit()
    }
}
