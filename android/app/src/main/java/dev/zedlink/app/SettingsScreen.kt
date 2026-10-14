package dev.zedlink.app

import android.content.Intent
import android.provider.Settings
import androidx.activity.compose.LocalActivity
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner

@Composable internal fun SettingsScreen(state: AppState, model: ZedLinkViewModel, connections: () -> Unit) {
    val activity = LocalActivity.current as? MainActivity
    val context = LocalContext.current
    val lifecycle = LocalLifecycleOwner.current
    var notificationRevision by remember { mutableIntStateOf(0) }
    var feedback by remember { mutableStateOf("") }
    var removing by remember { mutableStateOf<ConnectionProfile?>(null) }
    var diagnostics by remember { mutableStateOf(false) }
    var help by remember { mutableStateOf(false) }
    DisposableEffect(lifecycle) {
        val observer = LifecycleEventObserver { _, event -> if (event == Lifecycle.Event.ON_RESUME) notificationRevision++ }
        lifecycle.lifecycle.addObserver(observer)
        onDispose { lifecycle.lifecycle.removeObserver(observer) }
    }
    // Refresh after system Settings, and after the activity's permission result.
    val permission = remember(notificationRevision, state.notificationsEnabled, model.notificationRevision) { model.approvalNotifications.deliveryStatus() }
    removing?.let { profile -> ForgetAccessDialog(profile, { removing = null }) { model.forget(profile); removing = null } }
    if (diagnostics) SettingsDetailDialog("Diagnostics", { diagnostics = false }) {
        SettingsValue("Connection", state.status)
        state.profile?.let { SettingsValue("Gateway identity", it.gatewayId) }
        SettingsValue("Workspace", state.targets.firstOrNull { it.id == state.targetId }?.label ?: "Not selected")
        val prefix = if (state.live) "" else "Last known · "
        listOf("Files" to "project.files", "Terminal viewing" to "terminal.list", "Terminal input" to "terminal.input",
            "Debugger" to "debugger.snapshot", "Clipboard read" to "clipboard.read", "Clipboard write" to "clipboard.write").forEach { (label, id) ->
            SettingsValue(label, if (state.capabilities.isEmpty()) "Unknown" else prefix + if (id in state.capabilities) "Available" else "Unavailable")
        }
        Text("Change remote access permissions in desktop Zed.", color = Muted, fontSize = 12.sp)
        if (state.issue.isNotBlank()) Text(state.issue, color = MaterialTheme.colorScheme.error)
        if (state.profile != null) TextButton(onClick = model::connect) { Text("Reconnect") }
    }
    if (help) SettingsDetailDialog("Help & about", { help = false }) {
        SettingsValue("Version", "${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE})")
        SettingsValue("Interface revision", BuildConfig.UI_REVISION)
        TextButton(onClick = { context.startActivity(Intent(Intent.ACTION_VIEW, android.net.Uri.parse("https://github.com/tjnull/zedlink/blob/main/wiki/Running-and-Pairing.md"))) }) { Text("Setup & pairing") }
        TextButton(onClick = { context.startActivity(Intent(Intent.ACTION_VIEW, android.net.Uri.parse("https://github.com/tjnull/zedlink/blob/main/wiki/Security.md"))) }) { Text("Security & access") }
        TextButton(onClick = { context.startActivity(Intent(Intent.ACTION_VIEW, android.net.Uri.parse("https://github.com/tjnull/zedlink/blob/main/LICENSE"))) }) { Text("License") }
    }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp)) {
        Text("Settings", fontSize = 26.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(vertical = 16.dp))
        SettingsSection("This device")
        SettingsValue("Appearance", state.appearance.replaceFirstChar { it.uppercase() })
        Row(Modifier.fillMaxWidth()) {
            listOf("system", "dark", "light").forEach { value ->
                TextButton(onClick = { model.setAppearance(value) }, modifier = Modifier.weight(1f)) {
                    Text((if (state.appearance == value) "✓ " else "") + value.replaceFirstChar { it.uppercase() })
                }
            }
        }
        SettingsSection("Notifications")
        SettingsValue("Local approval alerts", if (!permission.allowed) permission.message else if (state.notificationsEnabled) "Enabled" else "Disabled")
        if (permission.allowed && state.notificationsEnabled) {
            TextButton(onClick = { feedback = runCatching { model.approvalNotifications.sendTest(); "Test sent. Check Notification Center if no banner appears." }.getOrElse { it.message ?: "Test failed." } }) { Text("Send test notification") }
            TextButton(onClick = { model.disableNotifications(); feedback = "" }) { Text("Disable alerts") }
        } else {
            if (permission.allowed || permission.requestable) TextButton(onClick = { activity?.enableApprovalNotifications(); feedback = "" }, enabled = activity != null) { Text("Enable alerts") }
            if (state.notificationsEnabled) TextButton(onClick = { model.disableNotifications() }) { Text("Disable alerts") }
        }
        TextButton(onClick = {
            context.startActivity(Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, context.packageName))
        }) { Text("System notification settings") }
        if (feedback.isNotBlank()) Text(feedback, fontSize = 12.sp)
        if (model.notificationMessage.isNotBlank()) Text(model.notificationMessage, color = MaterialTheme.colorScheme.error, fontSize = 12.sp)
        SettingsValue("Native push", "Not configured")
        SettingsValue("Watch alerts", "Phone mirroring only")
        Text("Local alerts need incoming app updates. They cannot guarantee delivery while suspended or force-stopped. Browser push is the available background option.", color = Muted, fontSize = 12.sp, modifier = Modifier.padding(vertical = 8.dp))
        state.profile?.let { profile ->
            TextButton(onClick = { context.startActivity(Intent(Intent.ACTION_VIEW, android.net.Uri.parse(profile.endpoint))) }) { Text("Set up browser push") }
        }
        SettingsSection("Connection & access")
        SettingsValue(state.profile?.name ?: "No connection", state.status)
        TextButton(onClick = connections) { Text("Manage connections") }
        TextButton(onClick = { diagnostics = true }) { Text("Diagnostics") }
        state.profile?.let { profile -> TextButton(onClick = { removing = profile }) { Text("Remove local access", color = MaterialTheme.colorScheme.error) } }
        SettingsSection("Support")
        TextButton(onClick = { help = true }) { Text("Help & about") }
        Spacer(Modifier.height(16.dp))
    }
}

@Composable private fun SettingsSection(title: String) {
    HorizontalDivider(color = Line)
    Text(title, color = Muted, fontSize = 12.sp, modifier = Modifier.padding(top = 18.dp, bottom = 8.dp))
}
@Composable private fun SettingsValue(label: String, value: String) {
    Column(Modifier.fillMaxWidth().padding(vertical = 8.dp)) {
        Text(label, fontWeight = FontWeight.Medium)
        Text(value, color = Muted, fontSize = 13.sp)
    }
}
@Composable private fun SettingsDetailDialog(title: String, close: () -> Unit, content: @Composable ColumnScope.() -> Unit) {
    AlertDialog(onDismissRequest = close, title = { Text(title) }, text = {
        Column(Modifier.fillMaxWidth().heightIn(max = 460.dp).verticalScroll(rememberScrollState()), content = content)
    }, confirmButton = { TextButton(onClick = close) { Text("Close") } }, shape = androidx.compose.ui.graphics.RectangleShape)
}
@Composable internal fun ForgetAccessDialog(profile: ConnectionProfile, close: () -> Unit, confirm: () -> Unit) {
    AlertDialog(onDismissRequest = close, title = { Text("Remove local access?") }, text = {
        Text("This removes the saved credential and every local address for ${profile.name}'s gateway. You will need to pair again. It does not revoke the device on the gateway or stop Zed.")
    }, confirmButton = { TextButton(onClick = confirm) { Text("Remove", color = MaterialTheme.colorScheme.error) } },
        dismissButton = { TextButton(onClick = close) { Text("Cancel") } }, shape = androidx.compose.ui.graphics.RectangleShape)
}
@Composable internal fun AgentSettingsDialog(state: AppState, model: ZedLinkViewModel, close: () -> Unit) {
    SettingsDetailDialog("Agent settings", close) {
        val settings = state.threadSettings
        if (settings == null || settings.models.isEmpty()) Text("This agent does not advertise a remote model selector. Configure it in desktop Zed.")
        settings?.let {
            SettingsValue("Context", if (it.usedTokens != null && it.maxTokens != null) "${it.usedTokens} / ${it.maxTokens} tokens" else "Unavailable")
            val editable = state.live && state.snapshot?.status == "Idle" && !state.updatingModel && "thread.settings.update" in state.capabilities
            if (it.profiles.isNotEmpty()) {
                SettingsValue("Agent profile", it.profiles.firstOrNull { profile -> profile.id == it.profileId }?.name ?: "Unavailable")
                it.profiles.forEach { profile -> TextButton(onClick = { model.updateAgentSettings(profileId = profile.id) }, enabled = editable) { Text((if (profile.id == it.profileId) "✓ " else "") + profile.name) } }
            }
            if (it.thinkingSupported && it.thinkingEnabled != null) {
                Row { Text("Model thinking", modifier = Modifier.weight(1f)); Switch(it.thinkingEnabled, { value -> model.updateAgentSettings(thinking = value) }, enabled = editable && it.thinkingCanDisable) }
                if (!it.thinkingCanDisable) Text("This model requires thinking.", color = Muted, fontSize = 12.sp)
            }
            it.models.forEach { option ->
                TextButton(onClick = { model.selectModel(option) }, enabled = state.live && state.snapshot?.status == "Idle" && !state.updatingModel && "thread.settings.update" in state.capabilities) {
                    Text((if (option.modelId == it.modelId && option.providerId == it.providerId) "✓ " else "") + "${option.name} · ${option.providerId}")
                }
            }
        }
        if (state.updatingModel) Text("Applying in Zed…")
        if (state.issue.isNotBlank()) Text(state.issue, color = MaterialTheme.colorScheme.error)
    }
}
