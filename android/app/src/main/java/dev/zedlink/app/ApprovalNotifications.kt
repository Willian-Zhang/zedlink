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
import java.util.UUID

/** Phone notifications may bridge to Wear OS. No FCM or background service is configured. */
class ApprovalNotifications(private val context: Context) {
    private val manager = context.getSystemService(NotificationManager::class.java)
    private val preferences = context.getSharedPreferences("zedlink-notifications", Context.MODE_PRIVATE)
    private val receipts = mutableMapOf<String, Pair<Map<String, String>, String>>()
    private var current = emptySet<String>()
    private var scope = ""
    val enabled get() = preferences.getBoolean("enabled", false)
    fun enable() { preferences.edit().putBoolean("enabled", true).apply() }
    fun disable() { preferences.edit().putBoolean("enabled", false).apply(); clear() }
    fun clear() {
        current.forEach { manager.cancel(it, 1) }; current = emptySet(); receipts.clear(); scope = ""
    }
    fun consume(intent: Intent): Pair<Map<String, String>, String>? =
        intent.getStringExtra("zedlink_notification_receipt")?.let(receipts::remove)

    fun update(state: AppState) {
        if (!enabled || (Build.VERSION.SDK_INT >= 33 && context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED)) {
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
                val nonce = UUID.randomUUID().toString()
                receipts[nonce] = fields to action
                val intent = Intent(context, MainActivity::class.java).apply {
                    flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
                    this.data = Uri.parse("zedlink://notification/$nonce")
                    putExtra("zedlink_notification_receipt", nonce)
                }
                return PendingIntent.getActivity(context, 0, intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
            }
            val review = pending("review", info)
            val builder = Notification.Builder(context, "zedlink-approvals")
                .setSmallIcon(android.R.drawable.ic_dialog_info)
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
        receipts.entries.removeAll { (_, value) -> value.first["approval"] !in snapshot.approvals.map { it.id } }
        current = next
    }
}
