package dev.zedlink.app

import android.os.Bundle
import android.os.Build
import android.Manifest
import android.content.Intent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels

class MainActivity : ComponentActivity() {
    private val model: ZedLinkViewModel by viewModels()

    private val notificationPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { allowed ->
        model.notificationPermissionResult(allowed)
    }
    fun enableApprovalNotifications() {
        if (Build.VERSION.SDK_INT >= 33) notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        else model.notificationPermissionResult(true)
    }
    private fun handleNotification(intent: Intent) {
        val receipt = model.approvalNotifications.consume(intent)
        if (receipt == null && intent.hasExtra("zedlink_notification_receipt")) model.expiredNotification()
        receipt?.let { (data, action) ->
            val locked = getSystemService(android.app.KeyguardManager::class.java).isDeviceLocked
            model.handleApprovalNotification(data, if (locked) "review" else action)
        }
        val link = when (intent.action) {
            Intent.ACTION_VIEW -> intent.dataString
            Intent.ACTION_SEND -> if (intent.type == "text/plain") intent.getStringExtra(Intent.EXTRA_TEXT) else null
            else -> null
        }
        link?.let { model.importPairingLink(it) }
        // One-use draft imports and receipts must not replay when the activity is recreated.
        intent.data = null
        intent.clipData = null
        intent.removeExtra(Intent.EXTRA_TEXT)
        intent.removeExtra("zedlink_notification_receipt")
    }
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleNotification(intent)
    }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { ZedLinkApp(model) }
        handleNotification(intent)
    }
}
