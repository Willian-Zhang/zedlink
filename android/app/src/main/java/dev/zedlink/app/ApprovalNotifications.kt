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

/** Phone notifications may bridge to Wear OS. No FCM or background service is configured. */
class ApprovalNotifications(private val context: Context) {
    private val manager = context.getSystemService(NotificationManager::class.java)
    private val preferences = context.getSharedPreferences("zedlink-notifications", Context.MODE_PRIVATE)
    private val receipts = NotificationReceipts(preferences)
    private var current = preferences.getStringSet("current", emptySet()).orEmpty().toSet()
    private var scope = ""
    val enabled get() = preferences.getBoolean("enabled", false)
    data class DeliveryStatus(val allowed: Boolean, val message: String, val requestable: Boolean = false)
    fun deliveryStatus(): DeliveryStatus {
        if (Build.VERSION.SDK_INT >= 33 && context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED)
            return DeliveryStatus(false, "Permission not granted in Android Settings", requestable = true)
        if (!manager.areNotificationsEnabled()) return DeliveryStatus(false, "Blocked in Android Settings")
        if (manager.getNotificationChannel("zedlink-approvals")?.importance == NotificationManager.IMPORTANCE_NONE)
            return DeliveryStatus(false, "Agent approval channel is blocked")
        return DeliveryStatus(true, "Allowed")
    }
    fun sendTest() {
        check(enabled && deliveryStatus().allowed) { "Enable alerts and allow notifications in Android Settings first." }
        manager.createNotificationChannel(NotificationChannel("zedlink-approvals", "Agent approvals", NotificationManager.IMPORTANCE_HIGH))
        manager.notify("zedlink-test", 2, Notification.Builder(context, "zedlink-approvals")
            .setSmallIcon(R.drawable.ic_notification).setContentTitle("ZedLink")
            .setContentText("Test notification. No Agent approval is requested.")
            .setVisibility(Notification.VISIBILITY_PRIVATE).setAutoCancel(true).build())
    }
    fun enable() { preferences.edit().putBoolean("enabled", true).apply() }
    fun disable() { preferences.edit().putBoolean("enabled", false).apply(); clear() }
    fun clear(preserveReceipts: Boolean = false) {
        current.forEach { manager.cancel(it, 1) }; current = emptySet(); if (!preserveReceipts) receipts.prune { false }; scope = ""
        preferences.edit().remove("current").apply()
    }
    fun consume(intent: Intent): Pair<Map<String, String>, String>? =
        intent.getStringExtra("zedlink_notification_receipt")?.let(receipts::consume)

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
            fun pending(action: String, fields: Map<String, String>): PendingIntent {
                val nonce = receipts.put(fields, action)
                val intent = Intent(context, MainActivity::class.java).apply {
                    flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
                    this.data = Uri.parse("zedlink://notification/$nonce")
                    putExtra("zedlink_notification_receipt", nonce)
                }
                return PendingIntent.getActivity(context, 0, intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
            }
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
        val removed = current - next
        removed.forEach { manager.cancel(it, 1) }
        receipts.prune { fields ->
            data.all { (key, value) -> fields[key] == value } && snapshot.approvals.any {
                fields["approval"] == it.id && fields["turn"] == it.turnId?.toString() && fields["child"] == it.subagentId.orEmpty()
            }
        }
        current = next
        preferences.edit().putStringSet("current", next).apply()
    }
}
