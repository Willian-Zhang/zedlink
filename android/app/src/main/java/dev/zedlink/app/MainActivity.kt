package dev.zedlink.app

import android.os.Bundle
import android.os.Build
import android.Manifest
import android.content.pm.PackageManager
import androidx.core.content.ContextCompat
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import com.journeyapps.barcodescanner.ScanIntentResult
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
    // Unconditional registration keeps the result available after activity/process recreation.
    private val pairingScanner = registerForActivityResult(ScanContract(), ::acceptPairingScanResult)
    internal fun acceptPairingScanResult(result: ScanIntentResult) {
        model.pairingScanInFlight = false
        val contents = result.contents
        if (contents != null) model.importPairingLink(contents)
        else model.reportPairingScanIssue(
            if (result.originalIntent?.getBooleanExtra(com.google.zxing.client.android.Intents.Scan.MISSING_CAMERA_PERMISSION, false) == true)
                "Camera permission was denied. Allow camera access in Android Settings or paste the pairing link."
            else "No QR was received. Scan again or paste the workstation pairing link.")
    }
    private val cameraPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { allowed ->
        if (model.pairingScanInFlight) {
            if (allowed) launchPairingScanner()
            else model.reportPairingScanIssue("Camera permission was denied. Allow camera access in Android Settings or paste the pairing link.")
        }
    }
    fun scanPairingQR() {
        if (model.pairingScanInFlight) return
        model.clearPairingScanIssue()
        model.pairingScanInFlight = true
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) launchPairingScanner()
        else runCatching { cameraPermission.launch(Manifest.permission.CAMERA) }
            .onFailure { model.reportPairingScanIssue("Camera permission could not be requested. Paste the pairing link instead.") }
    }
    private fun launchPairingScanner() {
        runCatching {
            pairingScanner.launch(ScanOptions().setCaptureActivity(PairingCaptureActivity::class.java)
                .setDesiredBarcodeFormats(ScanOptions.QR_CODE)
                .setBeepEnabled(false).setBarcodeImageEnabled(false).setOrientationLocked(true)
                .setPrompt("Scan the workstation pairing QR"))
        }.onFailure { model.reportPairingScanIssue("The QR camera could not be opened. Paste the pairing link instead.") }
    }
    override fun onSaveInstanceState(outState: Bundle) {
        outState.putBoolean("zedlink.pairingScanInFlight", model.pairingScanInFlight)
        super.onSaveInstanceState(outState)
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
        if (savedInstanceState?.getBoolean("zedlink.pairingScanInFlight") == true) model.pairingScanInFlight = true
        setContent { ZedLinkApp(model) }
        handleNotification(intent)
    }
}
