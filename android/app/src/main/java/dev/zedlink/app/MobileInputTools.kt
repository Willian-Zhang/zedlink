package dev.zedlink.app

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Intent
import android.speech.RecognizerIntent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch

@Composable
internal fun VoiceDraftButton(text: String, scope: String, update: (String) -> Unit) {
    var consent by remember { mutableStateOf(false) }
    var issue by remember { mutableStateOf("") }
    var original by remember { mutableStateOf("") }
    var originalScope by remember { mutableStateOf("") }
    val latestText by rememberUpdatedState(text)
    val latestScope by rememberUpdatedState(scope)
    val latestUpdate by rememberUpdatedState(update)
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        if (result.resultCode == Activity.RESULT_OK && latestScope == originalScope && latestText == original) {
            val words = result.data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.firstOrNull().orEmpty()
            latestUpdate((original + if (original.isEmpty() || words.isEmpty()) words else " $words").take(3000))
        }
    }
    IconButton(onClick = { consent = true }) { Icon(Icons.Default.Mic, "Dictate draft text") }
    if (consent) AlertDialog(onDismissRequest = { consent = false }, title = { Text("Dictate a draft") }, text = {
        Text("Your device’s speech service may process audio online. Offline recognition is preferred when supported. Text is added to a draft and is not sent automatically.")
    }, confirmButton = { TextButton(onClick = {
        consent = false; original = text; originalScope = scope
        try {
            launcher.launch(Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
                .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                .putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true)
                .putExtra(RecognizerIntent.EXTRA_PROMPT, "Draft text — review before sending"))
        } catch (_: ActivityNotFoundException) { issue = "No speech service is installed. Use the microphone on your keyboard." }
    }) { Text("Continue") } }, dismissButton = { TextButton(onClick = { consent = false }) { Text("Cancel") } })
    if (issue.isNotEmpty()) AlertDialog(onDismissRequest = { issue = "" }, text = { Text(issue) }, confirmButton = { TextButton(onClick = { issue = "" }) { Text("OK") } })
}

@Composable
internal fun RemoteClipboardDialog(state: AppState, model: ZedLinkViewModel, insert: (String) -> Unit, close: () -> Unit, destination: String = "terminal") {
    var text by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf("") }
    val jobs = rememberCoroutineScope()
    val clipboard = LocalClipboardManager.current
    val scope = listOf(state.profile?.gatewayId, state.targetId, state.instanceId, state.epoch, state.selectedThreadId)
    val originalScope = remember { scope }
    val latestScope by rememberUpdatedState(scope)
    LaunchedEffect(Unit) { model.loadProjectContext() }
    LaunchedEffect(scope) { if (scope != originalScope) { text = ""; close() } }
    AlertDialog(onDismissRequest = close, title = { Text("Remote clipboard") }, text = {
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("Explicit text transfers only. Terminal paste fills a draft; it does not run it.")
            OutlinedTextField(text, { if (it.toByteArray().size <= 65536) text = it }, label = { Text("Preview") }, modifier = Modifier.fillMaxWidth(), minLines = 3, maxLines = 6)
            TextButton(onClick = { busy = true; jobs.launch { try { model.transferClipboard()?.let { if (latestScope == originalScope) text = it }; status = model.state.issue } finally { busy = false } } }, enabled = !busy && "clipboard.read" in state.capabilities) { Text("Read desktop clipboard") }
            Row {
                TextButton(onClick = { val value = clipboard.getText()?.text.orEmpty(); if (value.toByteArray().size <= 65536) text = value else status = "Clipboard exceeds 64 KiB." }) { Text("Paste phone") }
                TextButton(onClick = { clipboard.setText(AnnotatedString(text)) }) { Text("Copy phone") }
            }
            TextButton(onClick = { busy = true; jobs.launch { try { if (model.transferClipboard(text) != null) status = "Desktop clipboard updated." else status = model.state.issue } finally { busy = false } } }, enabled = !busy && "clipboard.write" in state.capabilities) { Text("Send to desktop clipboard") }
            TextButton(onClick = {
                if (text.toByteArray().size > 16384 || text.any { it.code < 32 && it != '\t' && it != '\n' && it != '\r' || it.code == 127 }) status = "Use plain text up to 16 KiB without terminal controls."
                else if (destination == "prompt" && text.length > 3000) status = "Use up to 3000 characters for the prompt."
                else { insert(text); close() }
            }, enabled = !busy && (destination != "terminal" || "terminal.input" in state.capabilities)) { Text("Insert in $destination draft") }
            if ("clipboard.read" !in state.capabilities) Text("Enable Remote Clipboard in desktop ZedLink settings.")
            if (status.isNotEmpty()) Text(status)
        }
    }, confirmButton = { TextButton(onClick = close) { Text("Done") } })
}
