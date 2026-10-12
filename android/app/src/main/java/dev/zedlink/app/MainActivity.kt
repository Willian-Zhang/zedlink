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
        if (allowed) model.enableNotifications()
    }
    fun enableApprovalNotifications() {
        if (Build.VERSION.SDK_INT >= 33) notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        else model.enableNotifications()
    }
    private fun handleNotification(intent: Intent) {
        model.approvalNotifications.consume(intent)?.let { (data, action) -> model.handleApprovalNotification(data, action) }
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
