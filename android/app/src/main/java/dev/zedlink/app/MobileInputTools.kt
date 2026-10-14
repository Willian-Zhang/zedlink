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
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first

@Composable
internal fun VoiceDraftButton(text: String, scope: String, update: (String) -> Unit) {
    val context = androidx.compose.ui.platform.LocalContext.current
    var consent by remember { mutableStateOf(false) }
    var issue by remember { mutableStateOf("") }
    var listening by remember { mutableStateOf(false) }
    var original by remember { mutableStateOf("") }
    var originalScope by remember { mutableStateOf("") }
    val latestText by rememberUpdatedState(text)
    val latestScope by rememberUpdatedState(scope)
    val latestUpdate by rememberUpdatedState(update)
    val offline = remember { runCatching { android.os.Build.VERSION.SDK_INT >= 31 && android.speech.SpeechRecognizer.isOnDeviceRecognitionAvailable(context) }.getOrDefault(false) }
    // The platform speech activity is the default; on-device recognition remains opt-in.
    val inlineAvailable = remember { runCatching { android.speech.SpeechRecognizer.isRecognitionAvailable(context) || offline }.getOrDefault(false) }
    var useDeviceService by remember { mutableStateOf(true) }
    var pendingRecognition by remember { mutableStateOf(false) }
    val keyboard = androidx.compose.ui.platform.LocalSoftwareKeyboardController.current
    var recognitionGeneration by remember { mutableStateOf(0) }
    var recognizer by remember { mutableStateOf<android.speech.SpeechRecognizer?>(null) }
    fun result(words: String) {
        listening = false
        if (latestScope == originalScope && latestText == original && words.isNotBlank())
            latestUpdate((original + if (original.isEmpty()) words else " $words").take(3000))
    }
    fun startInline() {
        if (!inlineAvailable) { issue = "No in-app speech service is available."; return }
        recognitionGeneration++
        val currentGeneration = recognitionGeneration
        recognizer?.destroy()
        val speech = if (offline && android.os.Build.VERSION.SDK_INT >= 31)
            android.speech.SpeechRecognizer.createOnDeviceSpeechRecognizer(context)
        else android.speech.SpeechRecognizer.createSpeechRecognizer(context)
        recognizer = speech
        speech.setRecognitionListener(object : android.speech.RecognitionListener {
            override fun onReadyForSpeech(params: android.os.Bundle?) { if (currentGeneration == recognitionGeneration) listening = true }
            override fun onBeginningOfSpeech() {}
            override fun onRmsChanged(rmsdB: Float) {}
            override fun onBufferReceived(buffer: ByteArray?) {}
            override fun onEndOfSpeech() {}
            override fun onError(error: Int) {
                if (currentGeneration != recognitionGeneration || latestScope != originalScope) return
                listening = false
                recognizer?.destroy(); recognizer = null
                issue = when (error) {
                    android.speech.SpeechRecognizer.ERROR_AUDIO -> "Android could not record audio. Check that microphone access is enabled and close other apps using it. You can also try the device speech service."
                    android.speech.SpeechRecognizer.ERROR_RECOGNIZER_BUSY -> "The speech service is busy. Close other dictation or recording sessions and try again."
                    android.speech.SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> "Microphone permission is required. Enable it for ZedLink in Android settings."
                    android.speech.SpeechRecognizer.ERROR_NO_MATCH, android.speech.SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> "No speech recognized. Try again."
                    else -> "In-app dictation failed ($error). Try again or use your keyboard microphone."
                }
            }
            override fun onResults(results: android.os.Bundle?) {
                if (currentGeneration == recognitionGeneration) {
                    result(results?.getStringArrayList(android.speech.SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull().orEmpty())
                    recognizer?.destroy(); recognizer = null
                }
            }
            override fun onPartialResults(partialResults: android.os.Bundle?) {}
            override fun onEvent(eventType: Int, params: android.os.Bundle?) {}
        })
        listening = true
        speech.startListening(Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
            .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM))
    }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { allowed ->
        if (allowed && latestScope == originalScope && latestText == original) pendingRecognition = true
        else if (!allowed) issue = "Microphone permission was denied. Use keyboard input or change Android permissions."
    }
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { response ->
        listening = false
        if (response.resultCode == Activity.RESULT_OK) {
            val words = response.data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.firstOrNull().orEmpty()
            if (words.isBlank()) issue = "The speech service returned no text. Try again or use keyboard input."
            else result(words)
        }
    }
    val lifecycle = androidx.lifecycle.compose.LocalLifecycleOwner.current
    LaunchedEffect(pendingRecognition, scope) {
        if (pendingRecognition) {
            lifecycle.lifecycle.currentStateFlow.first { it.isAtLeast(androidx.lifecycle.Lifecycle.State.RESUMED) }
            // Let permission/consent windows close and keyboard audio input release capture.
            delay(250)
            lifecycle.lifecycle.currentStateFlow.first { it.isAtLeast(androidx.lifecycle.Lifecycle.State.RESUMED) }
            pendingRecognition = false
            if (latestScope == originalScope && latestText == original) {
                runCatching { startInline() }.onFailure {
                    listening = false; recognizer?.destroy(); recognizer = null
                    issue = "In-app speech service is unavailable. Try the device speech service."
                }
            }
        }
    }
    fun stopSpeech() {
        recognitionGeneration++
        recognizer?.cancel(); recognizer?.destroy(); recognizer = null; listening = false
    }
    DisposableEffect(scope, lifecycle) {
        val observer = androidx.lifecycle.LifecycleEventObserver { _, event ->
            if (event == androidx.lifecycle.Lifecycle.Event.ON_STOP) stopSpeech()
        }
        lifecycle.lifecycle.addObserver(observer)
        onDispose { lifecycle.lifecycle.removeObserver(observer); stopSpeech() }
    }
    IconButton(onClick = { if (listening) { recognizer?.stopListening() } else consent = true }) {
        Icon(Icons.Default.Mic, if (listening) "Finish dictation" else "Dictate draft text", tint = if (listening) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface)
    }
    if (consent) AlertDialog(onDismissRequest = { consent = false }, title = { Text("Dictate a draft") }, text = {
        Column {
            Text(if (offline && !useDeviceService) "On-device recognition keeps audio on this phone. Text is added to an editable draft and never sent automatically."
                else "Your device’s speech service may process audio online. Text is added to an editable draft and never sent automatically.")
            if (inlineAvailable) TextButton(onClick = { useDeviceService = !useDeviceService }) {
                Text(if (useDeviceService) { if (offline) "Use on-device recognition instead" else "Use in-app recognition instead" } else "Use device speech popup instead")
            }
        }
    }, confirmButton = { TextButton(onClick = {
        consent = false; original = text; originalScope = scope; keyboard?.hide()
        if (!useDeviceService && inlineAvailable) permission.launch(android.Manifest.permission.RECORD_AUDIO)
        else try {
            listening = true
            launcher.launch(Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
                .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                .putExtra(RecognizerIntent.EXTRA_PROMPT, "Draft text — review before sending"))
        } catch (_: ActivityNotFoundException) { listening = false; issue = "No speech service is installed. Use the microphone on your keyboard." }
        catch (_: SecurityException) { listening = false; issue = "Android blocked the speech service. Check its microphone permission in Android settings." }
    }) { Text(if (!useDeviceService) { if (offline) "Use on-device speech" else "Use in-app speech" } else "Use device speech service") } }, dismissButton = { TextButton(onClick = { consent = false }) { Text("Cancel") } })
    if (issue.isNotEmpty()) AlertDialog(onDismissRequest = { issue = "" }, text = { Text(issue) },
        confirmButton = { TextButton(onClick = { issue = "" }) { Text("OK") } },
        dismissButton = { if (!useDeviceService) TextButton(onClick = {
            issue = ""; useDeviceService = true; consent = true
        }) { Text("Try device speech service") } })
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
