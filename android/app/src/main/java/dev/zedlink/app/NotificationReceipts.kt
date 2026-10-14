package dev.zedlink.app

import android.content.SharedPreferences
import org.json.JSONObject
import java.util.UUID

/** Bounded, one-use routing receipts. No credentials, transcript or tool arguments. */
internal class NotificationReceipts(private val preferences: SharedPreferences, private val now: () -> Long = System::currentTimeMillis) {
    private val prefix = "receipt."
    @Synchronized fun put(fields: Map<String, String>, action: String): String {
        prune()
        val existing = preferences.all.filterKeys { it.startsWith(prefix) }
        if (existing.size >= 96) existing.keys.firstOrNull()?.let { preferences.edit().remove(it).commit() }
        val nonce = UUID.randomUUID().toString()
        check(preferences.edit().putString(prefix + nonce, JSONObject().put("created", now()).put("action", action).put("fields", JSONObject(fields)).toString()).commit())
        return nonce
    }
    @Synchronized fun consume(nonce: String): Pair<Map<String, String>, String>? {
        if (nonce.length != 36 || !Regex("[a-f0-9-]{36}").matches(nonce)) return null
        val value = preferences.getString(prefix + nonce, null) ?: return null
        if (!preferences.edit().remove(prefix + nonce).commit()) return null
        return runCatching {
            val row = JSONObject(value)
            val age = now() - row.getLong("created")
            if (age !in 0..86400000) return null
            val fields = row.getJSONObject("fields")
            fields.keys().asSequence().associateWith { fields.getString(it) } to row.getString("action")
        }.getOrNull()
    }
    @Synchronized fun prune(retain: ((Map<String, String>) -> Boolean)? = null) {
        val edit = preferences.edit()
        preferences.all.filterKeys { it.startsWith(prefix) }.forEach { (key, value) ->
            val valid = runCatching {
                val row = JSONObject(value as String)
                val fields = row.getJSONObject("fields")
                now() - row.getLong("created") in 0..86400000 &&
                    (retain == null || retain(fields.keys().asSequence().associateWith { fields.getString(it) }))
            }.getOrDefault(false)
            if (!valid) edit.remove(key)
        }
        edit.commit()
    }
}
