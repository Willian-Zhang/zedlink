package dev.zedlink.app

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import org.json.JSONObject

/** Phone notifications may bridge to Wear OS. No FCM or background service is configured. */
class ApprovalNotifications(private val context: Context) {
    private val manager = context.getSystemService(NotificationManager::class.java)
    private val preferences = context.getSharedPreferences("zedlink-notifications", Context.MODE_PRIVATE)
    private val receipts = NotificationReceipts(preferences)
    private val alertReceipts = AgentAlertReceipts(preferences)
    private var current = preferences.getStringSet("current", emptySet()).orEmpty().toSet()
    private var scope = ""
    val enabled get() = preferences.getBoolean("enabled", false)
    data class DeliveryStatus(val allowed: Boolean, val message: String, val requestable: Boolean = false)
    private fun baseDeliveryStatus(): DeliveryStatus {
        if (Build.VERSION.SDK_INT >= 33 && context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED)
            return DeliveryStatus(false, "Permission not granted in Android Settings", requestable = true)
        if (!manager.areNotificationsEnabled()) return DeliveryStatus(false, "Blocked in Android Settings")
        return DeliveryStatus(true, "Allowed")
    }
    fun generalDeliveryStatus(): DeliveryStatus = baseDeliveryStatus()
    fun deliveryStatus(): DeliveryStatus {
        val base = baseDeliveryStatus()
        if (!base.allowed) return base
        if (manager.getNotificationChannel("zedlink-approvals")?.importance == NotificationManager.IMPORTANCE_NONE)
            return DeliveryStatus(false, "Agent approval channel is blocked")
        return base
    }
    fun sendTest() {
        check(enabled && deliveryStatus().allowed) { "Enable alerts and allow notifications in Android Settings first." }
        manager.createNotificationChannel(NotificationChannel("zedlink-approvals", "Agent approvals", NotificationManager.IMPORTANCE_HIGH))
        manager.notify("zedlink-test", 2, Notification.Builder(context, "zedlink-approvals")
            .setSmallIcon(R.drawable.ic_notification).setContentTitle("ZedLink")
            .setContentText("Test notification. No Agent approval is requested.")
            .setVisibility(Notification.VISIBILITY_PRIVATE).setAutoCancel(true).build())
    }
    fun sendActivityTest() {
        check(enabled && activityDeliveryStatus().allowed) { "Enable Agent activity alerts in Android Settings first." }
        manager.createNotificationChannel(NotificationChannel("zedlink-activity", "Agent activity", NotificationManager.IMPORTANCE_HIGH))
        manager.notify("zedlink-activity-test", 2, Notification.Builder(context, "zedlink-activity")
            .setSmallIcon(R.drawable.ic_notification).setContentTitle("ZedLink · Activity test")
            .setContentText("Test notification. No Agent session changed.")
            .setVisibility(Notification.VISIBILITY_PRIVATE).setAutoCancel(true).build())
    }
    fun enable() { preferences.edit().putBoolean("enabled", true).apply() }
    fun disable() {
        preferences.edit().putBoolean("enabled", false).apply()
        clear()
        receipts.prune { false }
        preferences.getStringSet("activity-alerts", emptySet()).orEmpty().forEach { manager.cancel(it, 1) }
        manager.cancel("zedlink-test", 2)
        manager.cancel("zedlink-activity-test", 2)
        preferences.edit().remove("activity-alerts").apply()
    }
    fun clear(preserveReceipts: Boolean = false) {
        current.forEach { manager.cancel(it, 1) }; current = emptySet()
        if (!preserveReceipts) receipts.prune { it["type"] in setOf("turn_status", "input_needed", "compaction") }
        scope = ""
        preferences.edit().remove("current").apply()
    }
    fun consume(intent: Intent): Pair<Map<String, String>, String>? =
        intent.getStringExtra("zedlink_notification_receipt")?.let(receipts::consume)

    private fun pending(action: String, fields: Map<String, String>): PendingIntent {
        val nonce = receipts.put(fields, action)
        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
            data = Uri.parse("zedlink://notification/$nonce")
            putExtra("zedlink_notification_receipt", nonce)
        }
        return PendingIntent.getActivity(context, 0, intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
    }

    private fun routing(state: AppState, threadId: String): Map<String, String>? {
        val profile = state.profile ?: return null
        val target = state.targetId ?: return null
        val instance = state.instanceId ?: return null
        val epoch = state.epoch ?: return null
        if (state.selectedThreadId != threadId || !state.live && !state.connecting) return null
        return mapOf("gateway" to profile.gatewayId, "target" to target, "instance" to instance,
            "epoch" to epoch, "thread" to threadId)
    }

    fun activityDeliveryStatus(): DeliveryStatus {
        val general = baseDeliveryStatus()
        if (!general.allowed) return general
        if (manager.getNotificationChannel("zedlink-activity")?.importance == NotificationManager.IMPORTANCE_NONE)
            return DeliveryStatus(false, "Agent activity channel is blocked")
        return general
    }

    private fun activity(state: AppState, threadId: String, token: String, type: String, title: String, body: String) {
        if (!enabled || !activityDeliveryStatus().allowed) return
        val fields = routing(state, threadId) ?: return
        val eventScope = listOf(fields.getValue("gateway"), fields.getValue("target"), fields.getValue("instance"),
            fields.getValue("epoch"), threadId).joinToString(":")
        if (!alertReceipts.claim(eventScope, token)) return
        manager.createNotificationChannel(NotificationChannel("zedlink-activity", "Agent activity", NotificationManager.IMPORTANCE_HIGH))
        val key = "zedlink:$eventScope:$token"
        val prior = preferences.getStringSet("activity-alerts", emptySet()).orEmpty().toMutableSet()
        if (prior.size >= 128) prior.firstOrNull()?.let { prior.remove(it); manager.cancel(it, 1) }
        prior.add(key)
        preferences.edit().putStringSet("activity-alerts", prior).apply()
        manager.notify(key, 1, Notification.Builder(context, "zedlink-activity")
            .setSmallIcon(R.drawable.ic_notification).setContentTitle(title).setContentText(body)
            .setContentIntent(pending("review", fields + ("type" to type))).setAutoCancel(true).setOnlyAlertOnce(true)
            .setVisibility(Notification.VISIBILITY_PRIVATE).build())
    }

    fun notifyTurnEvents(state: AppState, threadId: String, events: List<JSONObject>) {
        events.filter { it.optString("kind") == "turn.stopped" }.forEach { event ->
            val sequence = event.optLong("sequence", 0L)
            if (sequence <= 0) return@forEach
            val reason = event.optString("stop_reason")
            val message = when (reason) {
                "completed" -> "Session completed" to "The Zed Agent finished its turn. Open the session to review the result."
                "cancelled" -> "Session stopped" to "The Zed Agent turn was cancelled. Open the session to review its current state."
                "max_turn_requests" -> "Session stopped" to "The Agent reached its turn request limit. Open the session to review its current state."
                else -> return@forEach // Failures are handled by the authoritative snapshot error.
            }
            activity(state, threadId, "turn:$sequence", "turn_status", "ZedLink · ${message.first}", message.second)
        }
    }

    fun notifyInputs(state: AppState, threadId: String, inputIds: List<String>) {
        inputIds.filter { it.isNotBlank() && it.length <= 256 }.forEach { id ->
            activity(state, threadId, "input:$id", "input_needed", "ZedLink · Input needed",
                "The Zed Agent is waiting for your response. Open the session to review the request.")
        }
    }

    fun notifyCompaction(state: AppState, threadId: String, turnId: Int?, phase: String) {
        if (phase == "compacting" && turnId != null) activity(state, threadId, "compaction:$turnId", "compaction",
            "ZedLink · Compacting context", "Zed is summarizing earlier conversation history before continuing.")
    }

    fun update(state: AppState) {
        if (!enabled || !deliveryStatus().allowed) {
            clear(); return
        }
        val snapshot = state.snapshot ?: return
        val data = mapOf("gateway" to (state.profile?.gatewayId ?: return), "target" to (state.targetId ?: return),
            "instance" to snapshot.instanceId, "epoch" to snapshot.epoch, "thread" to snapshot.threadId)
        val nextScope = data.values.joinToString(":")
        if (scope != nextScope) { clear(); scope = nextScope }
        manager.createNotificationChannel(NotificationChannel("zedlink-approvals", "Agent approvals", NotificationManager.IMPORTANCE_HIGH))
        val next = mutableSetOf<String>()
        snapshot.approvals.forEach { approval ->
            val turn = approval.turnId ?: return@forEach
            val info = data + mapOf("turn" to turn.toString(), "approval" to approval.id, "child" to approval.subagentId.orEmpty())
            val key = "$nextScope:${approval.subagentId.orEmpty()}:$turn:${approval.id}"
            next.add(key)
            if (key in current) return@forEach
            val review = pending("review", info)
            val builder = Notification.Builder(context, "zedlink-approvals")
                .setSmallIcon(R.drawable.ic_notification)
                .setContentTitle("ZedLink · Approval needed")
                .setContentText("A Zed Agent is waiting. Review the request before allowing it.")
                .setContentIntent(review).setAutoCancel(true).setOnlyAlertOnce(true)
                .setVisibility(Notification.VISIBILITY_PRIVATE)
            fun action(label: String, kind: String, fields: Map<String, String>) {
                val action = Notification.Action.Builder(null, label, pending(kind, fields))
                if (Build.VERSION.SDK_INT >= 31) action.setAuthenticationRequired(true)
                builder.addAction(action.build())
            }
            action("Review request", "review", info)
            val allow = approval.decisions.firstOrNull { it.optionKind == "allow_once" && it.choiceIndex == null && it.selectedPatternIndices.isEmpty() && it.action == null }
            val deny = approval.decisions.firstOrNull { it.optionKind == "reject_once" && it.choiceIndex == null && it.selectedPatternIndices.isEmpty() && it.action == null }
            if ("approval.respond" in state.capabilities && approval.authorizationKind == "permission_grant" && !approval.detailsTruncated && allow != null && deny != null) {
                action("Deny once", "deny", info + ("option" to deny.optionId))
                action("Approve once", "approve", info + ("option" to allow.optionId))
            }
            manager.notify(key, 1, builder.build())
        }
        snapshot.agentError?.takeUnless { it.retrying }?.let { error ->
            val material = listOf(error.kind, error.title, error.message).joinToString("\n")
            val digest = java.security.MessageDigest.getInstance("SHA-256").digest(material.toByteArray(Charsets.UTF_8))
                .joinToString("") { "%02x".format(it.toInt() and 255) }
            val key = "$nextScope:error:$digest"
            next.add(key)
            if (key !in current) {
                val review = pending("review", data + ("error" to key))
                val text = when (error.kind) {
                    "refusal" -> "Request refused" to "The model refused this request. Open the session to review it."
                    "max_output_tokens" -> "Output limit reached" to "The model stopped at its output limit. Open the session to review its response."
                    "prompt_too_large" -> "Context limit reached" to "The request was too large for the model. Open the session to review it."
                    "authentication_required", "authentication_failed", "no_credentials" -> "Model sign-in needed" to "Desktop Zed needs model credentials before this session can continue."
                    "permission_denied" -> "Request denied" to "The model provider denied the request. Open the session to review it."
                    else -> "Agent request failed" to "Open the session to review the error reported by desktop Zed."
                }
                manager.notify(key, 1, Notification.Builder(context, "zedlink-approvals")
                    .setSmallIcon(R.drawable.ic_notification).setContentTitle("ZedLink · ${text.first}")
                    .setContentText(text.second)
                    .setContentIntent(review).setAutoCancel(true).setOnlyAlertOnce(true)
                    .setVisibility(Notification.VISIBILITY_PRIVATE).build())
            }
        }
        val removed = current - next
        removed.forEach { manager.cancel(it, 1) }
        receipts.prune { fields ->
            fields["type"] in setOf("turn_status", "input_needed", "compaction") ||
                (data.all { (key, value) -> fields[key] == value } &&
                    (fields["error"]?.let { it in next } == true || snapshot.approvals.any {
                        fields["approval"] == it.id && fields["turn"] == it.turnId?.toString() && fields["child"] == it.subagentId.orEmpty()
                    }))
        }
        current = next
        preferences.edit().putStringSet("current", next).apply()
    }
}
