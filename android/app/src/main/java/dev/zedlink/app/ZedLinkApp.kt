package dev.zedlink.app

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import kotlinx.coroutines.delay
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.graphics.RectangleShape
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.codescanner.GmsBarcodeScannerOptions
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning

private val Black = Color.Black
private val Surface = Color(0xFF0D0E10)
private val Raised = Color(0xFF151719)
private val Line = Color(0xFF2B2D30)
private val Ink = Color(0xFFF3F3F1)
private val Muted = Color(0xFFA2A5AA)
private val Subtle = Color(0xFF797C82)
private val Blue = Color(0xFFD5E7FF)
private val Green = Color(0xFF79C79B)
private val Warning = Color(0xFFE2BC80)

private val scheme = darkColorScheme(
    primary = Ink, onPrimary = Black, background = Black, onBackground = Ink,
    surface = Surface, onSurface = Ink, outline = Line, secondary = Blue,
)

private enum class Tab { Sessions, Connections, Settings }

@Composable
fun ZedLinkApp(model: ZedLinkViewModel) {
    val state = model.state
    var tab by remember { mutableStateOf(Tab.Sessions) }
    MaterialTheme(colorScheme = scheme, typography = Typography()) {
        Surface(modifier = Modifier.fillMaxSize(), color = Black) {
            Column(Modifier.fillMaxSize().statusBarsPadding()) {
                Box(Modifier.weight(1f)) {
                    when {
                        state.selectedThreadId != null -> ConversationScreen(state, model)
                        tab == Tab.Sessions -> SessionsScreen(state, model) { tab = Tab.Connections }
                        tab == Tab.Connections -> ConnectionsScreen(state, model)
                        else -> SettingsScreen(state, model)
                    }
                }
                if (state.selectedThreadId == null) {
                    BottomTabs(tab, false) { next -> tab = next }
                }
            }
        }
    }
}

@Composable
private fun BottomTabs(selected: Tab, inThread: Boolean, onSelect: (Tab) -> Unit) {
    Row(Modifier.fillMaxWidth().navigationBarsPadding().height(66.dp).border(1.dp, Line)) {
        listOf(Triple(Tab.Sessions, Icons.Default.Forum, "Sessions"), Triple(Tab.Connections, Icons.Default.Language, "Connections"),
            Triple(Tab.Settings, Icons.Default.Settings, "Settings")).forEach { (tab, icon, label) ->
            val active = !inThread && selected == tab || inThread && tab == Tab.Sessions
            Column(Modifier.weight(1f).fillMaxHeight().clickable { onSelect(tab) },
                horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
                Icon(icon, null, tint = if (active) Blue else Subtle, modifier = Modifier.size(24.dp))
                Text(label, color = if (active) Blue else Subtle, fontSize = 11.sp)
            }
        }
    }
}

@Composable
private fun SessionsScreen(state: AppState, model: ZedLinkViewModel, showConnections: () -> Unit) {
    var query by remember { mutableStateOf("") }
    var showingNew by remember { mutableStateOf(false) }
    val focusManager = LocalFocusManager.current
    val threads = state.threads.filter { it.title.contains(query, true) || it.id.contains(query, true) }
    LazyColumn(Modifier.fillMaxSize()) {
        item {
            Header("ZedLink", if (state.live) state.status else "Private native Agent access") {
                Row {
                    IconButton(onClick = { showingNew = true }, enabled = "thread.create" in state.capabilities) {
                        Icon(Icons.Default.Add, "Create Agent session", tint = Ink)
                    }
                    IconButton(onClick = model::refresh, enabled = state.profile != null) { Icon(Icons.Default.Refresh, "Refresh", tint = Ink) }
                }
            }
            if (state.profile == null) {
                Column(Modifier.fillMaxWidth().background(Surface).clickable(onClick = showConnections).padding(20.dp)) {
                    Text("Choose a connection", fontSize = 22.sp, fontWeight = FontWeight.SemiBold)
                    Text("Pair a private ZedLink gateway from Connections.", color = Muted, modifier = Modifier.padding(top = 8.dp))
                }
            } else ConnectionStrip(state, model)
            if (state.issue.isNotBlank()) Notice(state.issue)
            FlatInput(query, { query = it }, "Search exposed sessions", Modifier.padding(16.dp))
            SectionHeading("EXPOSED ZED THREADS", state.threads.size.toString())
        }
        if (threads.isEmpty()) item {
            Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Icon(Icons.Default.DesktopWindows, null, tint = Muted)
                Text("No exposed sessions", fontSize = 19.sp, fontWeight = FontWeight.SemiBold)
                Text("In patched Zed, open a native Agent conversation and select /remote-control.", color = Muted)
            }
        }
        items(threads, key = { it.id }) { thread -> ThreadRow(thread) {
            focusManager.clearFocus(force = true)
            model.selectThread(thread.id)
        } }
    }
    if (showingNew) NewSessionDialog(state, model, { showingNew = false })
}

@Composable
private fun NewSessionDialog(state: AppState, model: ZedLinkViewModel, dismiss: () -> Unit) {
    var title by remember { mutableStateOf("") }
    var agentId by remember { mutableStateOf("zed-agent") }
    var expanded by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { model.loadCreateOptions() }
    LaunchedEffect(state.createAgents) {
        if (state.createAgents.none { it.id == agentId }) agentId = state.createAgents.firstOrNull()?.id ?: "zed-agent"
    }
    AlertDialog(
        onDismissRequest = dismiss,
        title = { Text("New Agent session") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedTextField(title, { title = it }, label = { Text("Optional title") }, singleLine = true)
                Box {
                    OutlinedButton(onClick = { expanded = true }, Modifier.fillMaxWidth()) {
                        Text(state.createAgents.firstOrNull { it.id == agentId }?.name ?: "Choose agent")
                    }
                    DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                        state.createAgents.forEach { agent ->
                            DropdownMenuItem(text = { Text("${agent.name}${if (agent.kind == "external_acp") " · ACP" else ""}") },
                                onClick = { agentId = agent.id; expanded = false })
                        }
                    }
                }
                Text("The agent, model, tools, permissions, and project remain configured in desktop Zed.", color = Muted, fontSize = 12.sp)
            }
        },
        confirmButton = {
            TextButton(enabled = state.createAgents.isNotEmpty() && !state.creatingThread, onClick = {
                model.createThread(title, agentId); dismiss()
            }) { Text("CREATE") }
        },
        dismissButton = { TextButton(onClick = dismiss) { Text("CANCEL") } },
        containerColor = Surface,
    )
}

@Composable
private fun ConnectionStrip(state: AppState, model: ZedLinkViewModel) {
    Column(Modifier.fillMaxWidth().background(Surface).padding(16.dp)) {
      Row(verticalAlignment = Alignment.Top) {
        Icon(Icons.Default.Bolt, null, tint = if (state.live) Green else Warning)
        Column(Modifier.padding(start = 12.dp).weight(1f)) {
            Text(state.profile?.name.orEmpty(), fontWeight = FontWeight.SemiBold)
            Text(state.profile?.endpoint.orEmpty(), color = Muted, fontFamily = FontFamily.Monospace, fontSize = 11.sp,
                maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text("Private HTTPS · Native Zed Agent", color = Subtle, fontFamily = FontFamily.Monospace, fontSize = 10.sp)
        }
        Text(state.status.uppercase(), color = if (state.live) Green else Muted, fontFamily = FontFamily.Monospace, fontSize = 10.sp)
      }
      if (state.targets.size > 1) {
        var expanded by remember { mutableStateOf(false) }
        Box(Modifier.padding(top = 12.dp)) {
            TextButton(onClick = { expanded = true }) {
                val label = state.targets.firstOrNull { it.id == state.targetId }?.label ?: "Choose Zed target"
                Text("$label  ▾")
            }
            DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                state.targets.forEach { target ->
                    DropdownMenuItem(text = { Text("${target.label}${if (target.available) "" else " · unavailable"}") },
                        enabled = target.available, onClick = { expanded = false; model.selectTarget(target.id) })
                }
            }
        }
      }
    }
    Rule()
}

@Composable
private fun ThreadRow(thread: NativeThread, open: () -> Unit) {
    Row(Modifier.fillMaxWidth().clickable(onClick = open).padding(horizontal = 16.dp, vertical = 15.dp), verticalAlignment = Alignment.CenterVertically) {
        Icon(if (thread.status == "Idle") Icons.Default.ChatBubbleOutline else Icons.Default.GraphicEq, null,
            tint = if (thread.status == "Idle") Muted else Blue, modifier = Modifier.size(21.dp))
        Column(Modifier.padding(horizontal = 12.dp).weight(1f)) {
            Text(thread.title, maxLines = 2, overflow = TextOverflow.Ellipsis)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(if (thread.status == "Idle") "● READY" else "● WORKING", color = if (thread.status == "Idle") Green else Blue,
                    fontFamily = FontFamily.Monospace, fontSize = 10.sp)
                Text("  ·  ${thread.id.take(8)}", color = Subtle, fontFamily = FontFamily.Monospace, fontSize = 10.sp)
            }
        }
        Icon(Icons.Default.ChevronRight, null, tint = Subtle)
    }
    Rule(48.dp)
}

@Composable
private fun ConversationScreen(state: AppState, model: ZedLinkViewModel) {
    val snapshot = state.snapshot
    var showCommands by remember { mutableStateOf(false) }
    var showClipboard by remember { mutableStateOf(false) }
    if (showClipboard) RemoteClipboardDialog(state, model, model::setDraft, { showClipboard = false }, "prompt")
    var showActions by remember { mutableStateOf(false) }
    var showRename by remember { mutableStateOf(false) }
    var showUnexpose by remember { mutableStateOf(false) }
    var showContext by remember { mutableStateOf(false) }
    var proposedTitle by remember(snapshot?.threadId) { mutableStateOf(snapshot?.title.orEmpty()) }
    Column(Modifier.fillMaxSize().navigationBarsPadding().imePadding()) {
        Row(Modifier.fillMaxWidth().heightIn(min = 58.dp).border(1.dp, Line).padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = model::closeThread) { Icon(Icons.Default.ArrowBack, "Sessions", tint = Ink) }
            Column(Modifier.weight(1f)) {
                Text(snapshot?.title ?: "Loading native thread", fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(if (snapshot?.isBusy == true) "ZED IS WORKING" else "NATIVE THREAD READY", color = if (snapshot?.isBusy == true) Blue else Green,
                    fontFamily = FontFamily.Monospace, fontSize = 10.sp)
            }
            Box {
                IconButton(onClick = { showContext = true; model.loadProjectContext() }) { Icon(Icons.Default.Description, "Project context", tint = Ink) }
            }
            Box {
                IconButton(onClick = { showActions = true }) { Icon(Icons.Default.MoreVert, "Session actions", tint = Ink) }
                DropdownMenu(expanded = showActions, onDismissRequest = { showActions = false }) {
                    if (state.delivery.isNotBlank()) DropdownMenuItem(text = { Text(state.delivery) }, enabled = false, onClick = {})
                    DropdownMenuItem(text = { Text("Rename session") }, leadingIcon = { Icon(Icons.Default.Edit, null) },
                        enabled = "thread.rename" in state.capabilities,
                        onClick = { proposedTitle = snapshot?.title.orEmpty(); showActions = false; showRename = true })
                    DropdownMenuItem(text = { Text("Stop exposing") }, leadingIcon = { Icon(Icons.Default.VisibilityOff, null) },
                        enabled = "thread.unexpose" in state.capabilities,
                        onClick = { showActions = false; showUnexpose = true })
                }
            }
        }
        if (state.issue.isNotBlank()) Notice(state.issue)
        if (snapshot == null) Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) { CircularProgressIndicator(color = Ink) }
        else Messages(snapshot, model, Modifier.weight(1f))
        if (showCommands) CommandList(state.commands, {
            model.prepareSubagentTask(); showCommands = false
        }, { showClipboard = true; showCommands = false }, { model.refresh(); showCommands = false }) { model.insertCommand(it); showCommands = false }
        if (state.delivery.isNotBlank() && (!state.live || state.sending || state.delivery.startsWith("Delivery unknown"))) Text(state.delivery, color = Warning, fontSize = 11.sp,
            modifier = Modifier.fillMaxWidth().background(Color(0xFF1C1915)).padding(8.dp))
        if (snapshot?.isBusy == true) AgentProgress(snapshot.status, snapshot.currentTurnId != null && "thread.cancel" in state.capabilities)
        Composer(state, model, { showCommands = !showCommands })
    }
    if (showRename) AlertDialog(
        onDismissRequest = { showRename = false },
        title = { Text("Rename session") },
        text = { OutlinedTextField(proposedTitle, { proposedTitle = it }, label = { Text("Session title") }, singleLine = true) },
        confirmButton = { TextButton(enabled = proposedTitle.isNotBlank(), onClick = {
            model.renameSelectedThread(proposedTitle); showRename = false
        }) { Text("RENAME") } },
        dismissButton = { TextButton(onClick = { showRename = false }) { Text("CANCEL") } },
        containerColor = Surface,
    )
    if (showUnexpose) AlertDialog(
        onDismissRequest = { showUnexpose = false },
        title = { Text("Stop exposing this session?") },
        text = { Text("The Agent keeps running in desktop Zed. Remote access to this session stops.") },
        confirmButton = { TextButton(onClick = { model.unexposeSelectedThread(); showUnexpose = false }) { Text("STOP EXPOSING") } },
        dismissButton = { TextButton(onClick = { showUnexpose = false }) { Text("CANCEL") } },
        containerColor = Surface,
    )
    if (showContext) ProjectContextDialog(state, model) { showContext = false }
}

@Composable
private fun ProjectContextDialog(state: AppState, model: ZedLinkViewModel, close: () -> Unit) {
    var terminalInput by remember { mutableStateOf("") }
    var terminalMenu by remember { mutableStateOf(false) }
    var fullFiles by remember { mutableStateOf(false) }
    if (fullFiles) ProjectFileBrowser(state, model) { fullFiles = false }
    var fullTerminal by remember { mutableStateOf(false) }
    if (fullTerminal) TerminalScreen(state, model) { fullTerminal = false }
    LaunchedEffect(state.terminalSnapshot?.terminal?.id) {
        while (true) {
            delay(1500)
            state.terminalSnapshot?.terminal?.let { model.loadTerminal(it, refresh = true) }
        }
    }
    AlertDialog(onDismissRequest = close, title = { Text("Project context") },
        text = { Column(Modifier.heightIn(max = 560.dp).verticalScroll(rememberScrollState())) {
            if (state.previewTitle == "Working tree diff" && state.previewContent.isNotEmpty()) {
                Text(state.previewTitle, fontWeight = FontWeight.SemiBold)
                SelectionContainer { Text(state.previewContent, fontFamily = FontFamily.Monospace, fontSize = 11.sp) }
            }
            Text("PROJECT FILES", style = monoLabel(), modifier = Modifier.padding(top = 12.dp))
            TextButton(onClick = { fullFiles = true }) { Icon(Icons.Default.FolderOpen, null); Text("Browse files and folders") }
            Text("GIT CHANGES", style = monoLabel(), modifier = Modifier.padding(top = 12.dp))
            TextButton(onClick = model::loadDiff) { Text("LOAD FULL DIFF") }
            state.changes.forEach { change -> Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text("${change.id}\n${change.status} · ${change.staging}", modifier = Modifier.weight(1f), fontSize = 12.sp)
                TextButton(onClick = { model.mutateChange(change) }) { Text(if (change.staging == "staged") "UNSTAGE" else "STAGE") }
            } }
            if ("task.catalog" in state.capabilities) {
                Text("RUN CONFIGURED TASK", style = monoLabel(), modifier = Modifier.padding(top = 12.dp))
                if (state.configuredTasks.isEmpty()) {
                    Text("No configured Zed tasks are available for this project.", color = Muted, fontSize = 12.sp)
                }
                state.configuredTasks.forEach { task ->
                    TextButton(onClick = { model.runConfiguredTask(task) }, enabled = "task.run" in state.capabilities,
                        modifier = Modifier.fillMaxWidth()) {
                        Row(Modifier.fillMaxWidth()) {
                            Text(task.label, modifier = Modifier.weight(1f), maxLines = 1)
                            Text(task.source.uppercase(), color = Muted, fontSize = 10.sp, fontFamily = FontFamily.Monospace)
                        }
                    }
                }
            }
            Text("ZED TERMINALS", style = monoLabel(), modifier = Modifier.padding(top = 12.dp))
            if ("terminal.list" !in state.capabilities) {
                Text("Enable View Project Terminals in ZedLink settings. Changes apply without restarting Zed.", color = Muted, fontSize = 12.sp)
            } else if (state.terminals.isEmpty()) {
                Text("No terminal is open for this project in Zed.", color = Muted, fontSize = 12.sp)
            }
            if (state.terminals.isNotEmpty()) {
                Box {
                    OutlinedButton(onClick = { terminalMenu = true }, modifier = Modifier.fillMaxWidth(), shape = RectangleShape) {
                        Icon(Icons.Default.Code, null, modifier = Modifier.size(17.dp))
                        Spacer(Modifier.width(8.dp))
                        Text(state.terminalSnapshot?.terminal?.title ?: "Choose terminal", modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                        Text(if ("terminal.input" in state.capabilities) "INTERACTIVE" else "READ ONLY", color = if ("terminal.input" in state.capabilities) Green else Warning, fontSize = 9.sp, fontFamily = FontFamily.Monospace)
                    }
                    DropdownMenu(expanded = terminalMenu, onDismissRequest = { terminalMenu = false }) {
                        state.terminals.forEach { terminal -> DropdownMenuItem(text = {
                            Column { Text(terminal.title, maxLines = 1); Text((terminal.taskState ?: terminal.workingDirectory ?: "terminal").uppercase(), color = Muted, fontSize = 10.sp, fontFamily = FontFamily.Monospace) }
                        }, onClick = { terminalMenu = false; model.loadTerminal(terminal) }) }
                    }
                }
            }
            state.terminalSnapshot?.let { snapshot ->
                TextButton(onClick = { fullTerminal = true }) { Icon(Icons.Default.Fullscreen, null); Text("Open full-screen terminal") }
                Column(Modifier.fillMaxWidth().border(1.dp, Line).background(Color(0xFF020303))) {
                    Row(Modifier.fillMaxWidth().heightIn(min = 40.dp).background(Color(0xFF08090A)).padding(horizontal = 11.dp), verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(7.dp).background(Green))
                        Spacer(Modifier.width(8.dp))
                        Text(snapshot.terminal.title, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis, fontSize = 12.sp, fontFamily = FontFamily.Monospace)
                        if (snapshot.terminal.taskState == "running" && "task.stop" in state.capabilities) {
                            TextButton(onClick = model::stopTerminalTask) { Text("STOP", color = MaterialTheme.colorScheme.error, fontSize = 11.sp) }
                        }
                    }
                    val verticalTerminalScroll = rememberScrollState()
                    val horizontalTerminalScroll = rememberScrollState()
                    SelectionContainer {
                        Text(terminalText(snapshot), color = Color(0xFFD9DEDB), fontFamily = FontFamily.Monospace, fontSize = 12.sp,
                            modifier = Modifier.fillMaxWidth().height(280.dp).verticalScroll(verticalTerminalScroll).padding(13.dp))
                    }
                }
                if ("terminal.input" in state.capabilities) {
                    Row(Modifier.fillMaxWidth().border(1.dp, Line).background(Color(0xFF08090A)).padding(9.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text("›", color = Green, fontFamily = FontFamily.Monospace, fontSize = 17.sp)
                        Spacer(Modifier.width(8.dp))
                        BasicTextField(value = terminalInput, onValueChange = { terminalInput = it }, singleLine = true,
                            textStyle = TextStyle(color = Ink, fontFamily = FontFamily.Monospace, fontSize = 13.sp), cursorBrush = SolidColor(Green), modifier = Modifier.weight(1f), keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                            keyboardActions = KeyboardActions(onSend = { if (terminalInput.isNotBlank()) { model.sendTerminalInput(terminalInput); terminalInput = "" } }))
                        IconButton(onClick = { model.sendTerminalInput(terminalInput); terminalInput = "" }, enabled = terminalInput.isNotBlank()) { Icon(Icons.Default.ArrowUpward, "Send terminal input") }
                    }
                } else {
                    Row(Modifier.fillMaxWidth().padding(vertical = 9.dp), verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Default.Lock, null, tint = Muted, modifier = Modifier.size(15.dp)); Spacer(Modifier.width(7.dp))
                        Text("Read only · Enable Send Terminal Input in ZedLink settings to type here.", color = Muted, fontSize = 11.sp)
                    }
                }
            }
            Text("DEBUGGER", style = monoLabel(), modifier = Modifier.padding(top = 12.dp))
            if ("debugger.catalog" !in state.capabilities) {
                Text("Enable Start Configured Debuggers in desktop ZedLink settings and restart patched Zed.", color = Muted, fontSize = 12.sp)
            } else if (state.debuggerCatalog.isEmpty()) {
                Text("No configured Zed debuggers are available for this project.", color = Muted, fontSize = 12.sp)
            }
            state.debuggerCatalog.forEach { scenario ->
                TextButton(onClick = { model.launchDebugger(scenario) }, enabled = "debugger.launch" in state.capabilities,
                    modifier = Modifier.fillMaxWidth()) {
                    Row(Modifier.fillMaxWidth()) {
                        Text(scenario.label, modifier = Modifier.weight(1f), maxLines = 1)
                        Text(scenario.adapter.uppercase(), color = Muted, fontSize = 10.sp, fontFamily = FontFamily.Monospace)
                    }
                }
            }
            if ("debugger.snapshot" !in state.capabilities) {
                Text("Enable View Debugger Sessions in desktop ZedLink settings and restart patched Zed.", color = Muted, fontSize = 12.sp)
            } else if (state.debuggerSessions.isEmpty()) {
                Text("No debugger session is running in this Zed project.", color = Muted, fontSize = 12.sp)
            }
            state.debuggerSessions.forEach { debugger ->
                Column(Modifier.fillMaxWidth().padding(vertical = 8.dp)) {
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(debugger.label, fontWeight = FontWeight.SemiBold)
                            Text(debugger.adapter, color = Muted, fontSize = 10.sp, fontFamily = FontFamily.Monospace)
                        }
                        if (!debugger.terminated) {
                            if (debugger.canRestart) {
                                TextButton(onClick = { model.controlDebugger(debugger, "restart") }, enabled = "debugger.control" in state.capabilities) { Text("RESTART") }
                            }
                            TextButton(onClick = { model.controlDebugger(debugger, "stop") }, enabled = "debugger.control" in state.capabilities) { Text("STOP", color = MaterialTheme.colorScheme.error) }
                        }
                    }
                    debugger.threads.forEach { thread ->
                        Column(Modifier.fillMaxWidth().padding(start = 12.dp, top = 6.dp)) {
                            Text("${thread.name} · ${thread.status.uppercase()}", fontSize = 12.sp)
                            Row(Modifier.horizontalScroll(rememberScrollState())) {
                                if (thread.status == "running") {
                                    TextButton(onClick = { model.controlDebugger(debugger, "pause", thread) }, enabled = "debugger.control" in state.capabilities) { Text("PAUSE") }
                                } else if (thread.status == "stopped") {
                                    listOf("continue" to "CONTINUE", "step_over" to "OVER", "step_in" to "INTO", "step_out" to "OUT").forEach { (action, label) ->
                                        TextButton(onClick = { model.controlDebugger(debugger, action, thread) }, enabled = "debugger.control" in state.capabilities) { Text(label) }
                                    }
                                    if (debugger.canStepBack) {
                                        TextButton(onClick = { model.controlDebugger(debugger, "step_back", thread) }, enabled = "debugger.control" in state.capabilities) { Text("BACK") }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        } }, confirmButton = { TextButton(onClick = close) { Text("DONE") } }, containerColor = Surface)
}

@Composable
private fun AgentProgress(status: String, canCancel: Boolean) {
    val detail = when {
        status.contains("generat", true) -> "Generating in desktop Zed"
        status.contains("tool", true) || status.contains("run", true) -> "Running native tools"
        status.contains("wait", true) || status.contains("queue", true) -> "Waiting in desktop Zed"
        else -> "$status in desktop Zed"
    }
    Row(Modifier.fillMaxWidth().padding(horizontal = 10.dp, vertical = 4.dp)
        .border(1.dp, Blue.copy(alpha = 0.35f), RoundedCornerShape(10.dp))
        .background(Blue.copy(alpha = 0.08f), RoundedCornerShape(10.dp)).padding(horizontal = 11.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically) {
        CircularProgressIndicator(color = Blue, strokeWidth = 2.dp, modifier = Modifier.size(18.dp))
        Column(Modifier.padding(start = 10.dp).weight(1f)) {
            Text("Zed Agent is working", fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
            Text(detail, color = Muted, fontFamily = FontFamily.Monospace, fontSize = 10.sp)
        }
        Text(if (canCancel) "STOP AVAILABLE" else "LIVE", color = Blue, fontFamily = FontFamily.Monospace, fontSize = 9.sp)
    }
}

@Composable
private fun Messages(snapshot: ThreadSnapshot, model: ZedLinkViewModel, modifier: Modifier = Modifier) {
    val list = rememberLazyListState()
    var rewindPoint by remember { mutableStateOf<NativeRewindPoint?>(null) }
    LaunchedEffect(snapshot.lastSequence) { if (snapshot.entries.isNotEmpty()) list.animateScrollToItem(snapshot.entries.lastIndex + 1) }
    LazyColumn(modifier.fillMaxWidth(), state = list, contentPadding = PaddingValues(bottom = 10.dp)) {
        if (snapshot.hasOlderEntries) item {
            TextButton(onClick = model::loadEarlierHistory, shape = androidx.compose.ui.graphics.RectangleShape) {
                Text("LOAD EARLIER CONVERSATION · ${snapshot.entryStartIndex} REMAINING", color = Muted)
            }
        }
        items(snapshot.subagents, key = { "subagent:${it.id}" }) { subagent ->
            var expanded by remember(subagent.id) { mutableStateOf(subagent.currentTurnId != null) }
            Column(Modifier.fillMaxWidth().background(Surface).border(1.dp, Line).padding(12.dp)) {
                Row(Modifier.fillMaxWidth().clickable { expanded = !expanded }) {
                    Text("${subagent.title} · ${subagent.status}", modifier = Modifier.weight(1f))
                    Text(if (expanded) "HIDE" else "VIEW", style = monoLabel())
                }
                if (expanded) {
                    subagent.entries.forEach { Message(NativeEntry.parse(it), subagent.currentTurnId != null) }
                    if (subagent.currentTurnId != null) TextButton(onClick = { model.cancelSubagent(subagent) }) { Text("STOP PARALLEL AGENT") }
                }
            }
        }
        itemsIndexed(snapshot.entries, key = { index, _ -> snapshot.entryStartIndex + index }) { index, markdown ->
            val absoluteIndex = snapshot.entryStartIndex + index
            Message(NativeEntry.parse(markdown), snapshot.isBusy && index == snapshot.entries.lastIndex)
            snapshot.rewindPoints.firstOrNull { it.entryIndex == absoluteIndex }?.let { point ->
                if (!snapshot.isBusy && "thread.rewind" in model.state.capabilities) {
                    TextButton(onClick = { rewindPoint = point }) { Text("REWIND CONVERSATION HERE", color = Warning) }
                }
            }
        }
        items(snapshot.approvals, key = { it.id }) { ApprovalCard(it, model::respondApproval) }
        items(model.state.elicitations, key = { "elicitation:${it.id}" }) { ElicitationCard(it, model) }
        model.state.editReview?.let { review -> item("edit-review") { EditReviewCard(review, model) } }
        if (model.state.queuedMessages.isNotEmpty()) item("queue") { QueueCard(model.state.queuedMessages, model) }
    }
    rewindPoint?.let { point -> AlertDialog(
        onDismissRequest = { rewindPoint = null }, title = { Text("Rewind this conversation?") },
        text = { Text("Messages and Agent edits after this point may be removed.") },
        confirmButton = { TextButton(onClick = { rewindPoint = null; model.rewind(point) }) { Text("REWIND") } },
        dismissButton = { TextButton(onClick = { rewindPoint = null }) { Text("CANCEL") } }, containerColor = Surface,
    ) }
}

@Composable
private fun ElicitationCard(item: NativeElicitation, model: ZedLinkViewModel) {
    val scope = listOf(model.state.profile?.gatewayId, model.state.targetId, model.state.instanceId, model.state.epoch, model.state.selectedThreadId)
    val values = remember(item.id, scope) { mutableStateMapOf<String, String>() }
    val selections = remember(item.id, scope) { mutableStateMapOf<String, Set<String>>() }
    var validation by remember(item.id, scope) { mutableStateOf("") }
    val submitting = (scope + item.id).joinToString("\n") in model.state.resolvingElicitations
    val enabled = model.state.live && "elicitation.respond" in model.state.capabilities && !submitting
    Column(Modifier.fillMaxWidth().background(Color(0xFF1C1915)).border(1.dp, Warning).padding(14.dp)) {
        Text("INPUT REQUESTED", color = Warning, fontSize = 10.sp, fontFamily = FontFamily.Monospace)
        Text(item.message, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(vertical = 8.dp))
        item.url?.let { Text(it, color = Blue, fontSize = 12.sp) }
        item.fields.forEach { field ->
            val title = field.title + if (field.required) " *" else ""
            when {
                field.type == "boolean" -> Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(ElicitationForm.value(field, values) == "true", { values[field.id] = it.toString() }, enabled = enabled)
                    Text(title)
                }
                field.type == "array" && field.choices.isNotEmpty() -> {
                    Text(title)
                    field.choices.forEach { choice ->
                        val selected = selections[field.id] ?: field.defaultArray.orEmpty().toSet()
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Checkbox(choice in selected, { selections[field.id] = if (it) selected + choice else selected - choice }, enabled = enabled)
                            Text(choice)
                        }
                    }
                }
                field.choices.isNotEmpty() -> {
                    var expanded by remember(item.id, field.id) { mutableStateOf(false) }
                    Box {
                        TextButton(onClick = { expanded = true }, enabled = enabled) { Text("$title: ${ElicitationForm.value(field, values).ifEmpty { "No value" }}") }
                        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                            if (!field.required) DropdownMenuItem(text = { Text("No value") }, onClick = { values[field.id] = ""; expanded = false })
                            field.choices.forEach { choice -> DropdownMenuItem(text = { Text(choice) }, onClick = { values[field.id] = choice; expanded = false }) }
                        }
                    }
                }
                else -> OutlinedTextField(ElicitationForm.value(field, values), { values[field.id] = it }, label = { Text(title) }, enabled = enabled, modifier = Modifier.fillMaxWidth())
            }
        }
        if (validation.isNotEmpty()) Text(validation, color = Warning)
        if (submitting) LinearProgressIndicator(Modifier.fillMaxWidth())
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
            TextButton(onClick = { model.respondElicitation(item, "decline") }, enabled = enabled) { Text("DECLINE") }
            Button(onClick = {
                try { val content = ElicitationForm.content(item.fields, values, selections); validation = ""; model.respondElicitation(item, "accept", org.json.JSONObject(content)) }
                catch (error: IllegalArgumentException) { validation = error.message.orEmpty() }
            }, enabled = enabled, shape = androidx.compose.ui.graphics.RectangleShape) { Text("SUBMIT") }
        }
    }
}

@Composable
private fun EditReviewCard(review: NativeEditReview, model: ZedLinkViewModel) {
    Column(Modifier.fillMaxWidth().background(Surface).border(1.dp, Line).padding(14.dp)) {
        Text("REVIEW AGENT EDITS", style = monoLabel())
        Text("${review.changedFiles} files · +${review.linesAdded} −${review.linesRemoved}", color = Muted)
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
            TextButton(onClick = { model.resolveEditReview("reject_all") }) { Text("REJECT ALL") }
            Button(onClick = { model.resolveEditReview("keep_all") }, shape = androidx.compose.ui.graphics.RectangleShape) { Text("KEEP ALL") }
        }
    }
}

@Composable
private fun QueueCard(entries: List<NativeQueueEntry>, model: ZedLinkViewModel) {
    Column(Modifier.fillMaxWidth().background(Surface).border(1.dp, Line).padding(14.dp)) {
        Text("${entries.size} QUEUED MESSAGE${if (entries.size == 1) "" else "S"}", style = monoLabel())
        entries.forEach { Text(it.preview, maxLines = 2, overflow = TextOverflow.Ellipsis, color = Muted, fontSize = 12.sp) }
        TextButton(onClick = model::clearQueue) { Text("CLEAR QUEUE") }
    }
}

@Composable
private fun ActivityPanel(snapshot: ThreadSnapshot) {
    var expanded by remember { mutableStateOf(true) }
    val activity = snapshot.activityEntries.map(NativeEntry::parse).flatMap { entry ->
        entry.reasoning.map { "Reasoning" to it } + if (entry.kind == EntryKind.TOOL || entry.kind == EntryKind.PLAN) listOf(entry.label to entry.body) else emptyList()
    }
    Column(Modifier.fillMaxWidth().padding(12.dp).border(1.dp, Line).background(Surface)) {
        Row(Modifier.fillMaxWidth().clickable { expanded = !expanded }.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(if (snapshot.isBusy) "●" else "○", color = if (snapshot.isBusy) Green else Subtle)
            Text(" Zed is working", fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
            Text(if (expanded) "HIDE" else "SHOW", color = Muted, fontSize = 10.sp, fontFamily = FontFamily.Monospace)
        }
        if (expanded) {
            Rule()
            activity.forEach { (label, body) ->
                Text(label.uppercase(), color = Subtle, fontSize = 10.sp, fontFamily = FontFamily.Monospace,
                    modifier = Modifier.padding(start = 12.dp, end = 12.dp, top = 10.dp))
                Text(body, color = Muted, fontSize = 13.sp, modifier = Modifier.padding(horizontal = 12.dp, vertical = 5.dp))
            }
            if (activity.isEmpty()) Text("Waiting for native activity…", color = Muted, modifier = Modifier.padding(12.dp))
        }
    }
}

@Composable
private fun Message(entry: NativeEntry, thinkingLive: Boolean = false) {
    var reasoningExpanded by remember(entry.reasoning, thinkingLive) { mutableStateOf(thinkingLive) }
    when (entry.kind) {
        EntryKind.TOOL -> ToolCard(entry)
        EntryKind.USER -> Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp)) {
            Spacer(Modifier.width(42.dp))
            Column(Modifier.weight(1f).wrapContentWidth(Alignment.End).widthIn(max = 760.dp)
                .background(Raised).padding(horizontal = 14.dp, vertical = 11.dp)) {
                Text(entry.label.uppercase(), color = Subtle, fontSize = 10.sp, fontFamily = FontFamily.Monospace,
                    fontWeight = FontWeight.SemiBold)
                SelectionContainer { MarkdownLikeText(entry.body) }
            }
        }
        else -> Column(Modifier.fillMaxWidth().padding(16.dp)) {
            Text(entry.label.uppercase(), color = if (entry.kind == EntryKind.ASSISTANT) Color(0xFFB8C5D1) else Subtle,
                fontSize = 10.sp, fontFamily = FontFamily.Monospace, fontWeight = FontWeight.SemiBold)
            if (entry.reasoning.isNotEmpty()) {
                TextButton(onClick = { reasoningExpanded = !reasoningExpanded }, shape = androidx.compose.ui.graphics.RectangleShape) {
                    Text(if (reasoningExpanded) "HIDE THINKING" else "SHOW THINKING", color = Muted)
                }
                if (reasoningExpanded) entry.reasoning.forEach { thought ->
                    SelectionContainer { MarkdownLikeText(thought, Modifier.padding(vertical = 6.dp)) }
                }
            }
            SelectionContainer { MarkdownLikeText(entry.body) }
        }
    }
    Rule(14.dp)
}

@Composable
private fun ToolCard(entry: NativeEntry) {
    var expanded by remember { mutableStateOf(false) }
    Column(Modifier.fillMaxWidth().padding(12.dp).border(1.dp, Line).background(Surface)) {
        Text("ZED TOOL", color = Subtle, fontSize = 10.sp, fontFamily = FontFamily.Monospace, modifier = Modifier.padding(12.dp, 10.dp, 12.dp, 0.dp))
        Text(entry.toolName ?: "Native tool", fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(horizontal = 12.dp, vertical = 7.dp))
        Text(entry.toolStatus ?: "Native status", color = Green, fontFamily = FontFamily.Monospace, fontSize = 11.sp, modifier = Modifier.padding(horizontal = 12.dp))
        TextButton(onClick = { expanded = !expanded }, shape = androidx.compose.ui.graphics.RectangleShape) { Text(if (expanded) "HIDE OUTPUT" else "SHOW OUTPUT", color = Ink) }
        if (expanded) SelectionContainer { MarkdownLikeText(entry.body, Modifier.padding(12.dp)) }
    }
}

@Composable
private fun MarkdownLikeText(text: String, modifier: Modifier = Modifier) {
    NativeMarkdown(text, modifier, Ink, Muted, Line, Surface)
}

@Composable
private fun ApprovalCard(approval: NativeApproval, respond: (NativeApproval, NativeApprovalDecision) -> Unit) {
    Column(Modifier.fillMaxWidth().background(Color(0xFF1C1915)).border(1.dp, Warning).padding(14.dp)) {
        Text(if (approval.authorizationKind == "action_choice") "CHOOSE AN ACTION" else "PERMISSION REQUESTED",
            color = Warning, fontSize = 10.sp, fontFamily = FontFamily.Monospace)
        Text(approval.toolName, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 7.dp))
        Text(approval.display, color = Muted)
        approval.rawInput?.let { SelectionContainer { Text(it, fontFamily = FontFamily.Monospace, fontSize = 11.sp, modifier = Modifier.padding(top = 8.dp)) } }
        if (approval.decisions.isEmpty()) {
            Text("Update patched Zed to resolve this request remotely.", color = Warning, fontSize = 11.sp, modifier = Modifier.padding(top = 8.dp))
        } else approval.decisions.forEach { decision ->
            Button(
                onClick = { respond(approval, decision) },
                enabled = !approval.detailsTruncated || (decision.isRejecting && approval.authorizationKind != "action_choice"),
                shape = androidx.compose.ui.graphics.RectangleShape,
                modifier = Modifier.fillMaxWidth().padding(top = 7.dp),
            ) { Text(decision.displayLabel) }
        }
    }
}

@Composable
private fun CommandList(commands: List<NativeCommand>, delegate: () -> Unit, clipboard: () -> Unit, recover: () -> Unit, choose: (NativeCommand) -> Unit) {
    Column(Modifier.fillMaxWidth().heightIn(max = 260.dp).border(1.dp, Line).background(Raised).verticalScroll(rememberScrollState())) {
        Row(Modifier.fillMaxWidth().clickable(onClick = delegate).padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Default.AccountTree, null, tint = Blue, modifier = Modifier.size(19.dp))
            Column(Modifier.padding(start = 11.dp)) {
                Text("Delegate a parallel task", fontWeight = FontWeight.SemiBold)
                Text("Ask native Zed to use spawn_agent", color = Muted, fontSize = 12.sp)
            }
        }
        Rule()
        TextButton(onClick = clipboard) { Text("Remote clipboard") }
        TextButton(onClick = recover) { Text("Recover session") }
        if (commands.isEmpty()) Text("No commands are advertised by this native thread.", color = Muted, modifier = Modifier.padding(14.dp))
        commands.forEach { command ->
            Row(Modifier.fillMaxWidth().clickable { choose(command) }.padding(12.dp)) {
                Text("/${command.name}", fontFamily = FontFamily.Monospace, modifier = Modifier.widthIn(min = 100.dp))
                Text(command.description, color = Muted, fontSize = 12.sp, modifier = Modifier.weight(1f))
            }
            Rule()
        }
    }
}

@Composable
private fun Composer(state: AppState, model: ZedLinkViewModel, commands: () -> Unit) {
    val focusManager = LocalFocusManager.current
    val keyboard = LocalSoftwareKeyboardController.current
    val submit = {
        if (state.live && state.draft.isNotBlank() && !state.sending) {
            focusManager.clearFocus(force = true)
            keyboard?.hide()
            model.send()
        }
    }
    Row(Modifier.fillMaxWidth().padding(horizontal = 10.dp, vertical = 8.dp)
        .border(1.dp, Line).background(Surface).padding(5.dp),
        verticalAlignment = Alignment.Bottom) {
        FlatIconButton("/", commands)
        BasicTextField(state.draft, model::setDraft, Modifier.weight(1f).heightIn(min = 44.dp, max = 140.dp).padding(11.dp),
            textStyle = TextStyle(color = Ink, fontSize = 16.sp), cursorBrush = SolidColor(Ink),
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
            keyboardActions = KeyboardActions(onSend = { submit() }),
            decorationBox = { inner ->
                Box { if (state.draft.isEmpty()) Text("Message Zed Agent…", color = Subtle); inner() }
            })
        VoiceDraftButton(state.draft, "${state.targetId}.${state.instanceId}.${state.epoch}.${state.selectedThreadId}", model::setDraft)
        val canCancel = state.live && state.snapshot?.currentTurnId != null && "thread.cancel" in state.capabilities
        val sendEnabled = state.live && state.draft.isNotBlank() && !state.sending
        IconButton(onClick = { if (canCancel) model.cancel() else submit() }, enabled = if (canCancel) !state.sending else sendEnabled,
            modifier = Modifier.background(if (canCancel) Color(0xFF592828) else if (sendEnabled) Ink else Line, RoundedCornerShape(50))) {
            Icon(if (canCancel) Icons.Default.Stop else Icons.Default.ArrowUpward, if (canCancel) "Stop current turn" else "Send",
                tint = if (canCancel) Color(0xFFFFD4D4) else if (sendEnabled) Black else Subtle)
        }
    }
}

@Composable
private fun ConnectionsScreen(state: AppState, model: ZedLinkViewModel) {
    val clipboard = LocalClipboardManager.current
    val context = LocalContext.current
    val scanner = remember {
        GmsBarcodeScanning.getClient(context, GmsBarcodeScannerOptions.Builder()
            .setBarcodeFormats(Barcode.FORMAT_QR_CODE).enableAutoZoom().build())
    }
    var name by remember(state.profile) { mutableStateOf(state.profile?.name ?: "My Zed") }
    var endpoint by remember(state.profile) { mutableStateOf(state.profile?.endpoint.orEmpty()) }
    var gateway by remember(state.profile) { mutableStateOf(state.profile?.gatewayId.orEmpty()) }
    var code by remember { mutableStateOf("") }
    var device by remember { mutableStateOf("Android phone") }
    var localIssue by remember { mutableStateOf("") }
    fun applyLink(link: String) {
        runCatching { model.applyPairingLink(link) }
            .onSuccess { (profile, pairCode) ->
                name = profile.name; endpoint = profile.endpoint; gateway = profile.gatewayId
                if (pairCode != null) code = pairCode
                localIssue = ""
            }
            .onFailure { localIssue = it.message ?: "Pairing link could not be read." }
    }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        Header("Connections", "Private HTTPS profiles")
        if (state.profiles.isNotEmpty()) {
            SectionHeading("SAVED ZED HOSTS", "${state.profiles.size}")
            state.profiles.forEach { profile ->
                Column(Modifier.fillMaxWidth().background(if (state.profile?.gatewayId == profile.gatewayId) Raised else Surface)
                    .border(1.dp, Line).padding(14.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(profile.name, fontWeight = FontWeight.SemiBold)
                            Text(profile.endpoint, color = Muted, fontFamily = FontFamily.Monospace,
                                fontSize = 11.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        }
                        TextButton(onClick = { model.connect(profile) }) {
                            Text(if (state.profile?.gatewayId == profile.gatewayId && state.live) "RECONNECT" else "CONNECT")
                        }
                        TextButton(onClick = { model.forget(profile) }) { Text("FORGET", color = Color(0xFFE6A0A0)) }
                    }
                }
            }
        }
        Text("QUICK PAIR", style = monoLabel(), modifier = Modifier.padding(16.dp, 24.dp, 16.dp, 8.dp))
        Text("Scan the workstation QR, or copy its trusted HTTPS link and paste it here.", color = Muted, modifier = Modifier.padding(horizontal = 16.dp))
        FlatButton("SCAN PAIRING QR", Modifier.padding(horizontal = 16.dp, vertical = 8.dp)) {
            scanner.startScan().addOnSuccessListener { barcode -> barcode.rawValue?.let(::applyLink) }
                .addOnFailureListener { localIssue = it.message ?: "QR scanner unavailable." }
        }
        FlatButton("PASTE PAIRING LINK", Modifier.padding(16.dp)) {
            applyLink(clipboard.getText()?.text.orEmpty())
        }
        if (localIssue.isNotBlank()) Notice(localIssue)
        SectionHeading("CONNECTION DETAILS", "HTTPS")
        FlatInput(name, { name = it }, "Profile name", Modifier.padding(horizontal = 16.dp, vertical = 5.dp))
        FlatInput(endpoint, { endpoint = it }, "https://host:port", Modifier.padding(horizontal = 16.dp, vertical = 5.dp))
        FlatInput(gateway, { gateway = it }, "Gateway identity", Modifier.padding(horizontal = 16.dp, vertical = 5.dp))
        FlatInput(code, { code = it }, "10-digit pairing code", Modifier.padding(horizontal = 16.dp, vertical = 5.dp))
        FlatInput(device, { device = it }, "Device name", Modifier.padding(horizontal = 16.dp, vertical = 5.dp))
        val alreadyPaired = state.profiles.any { it.gatewayId.equals(gateway, ignoreCase = true) }
        if (alreadyPaired) {
            FlatButton("SAVE NEW ADDRESS AND RECONNECT", Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                endpoint.startsWith("https://") && gateway.isNotBlank()) {
                model.updateRoute(ConnectionProfile(name, endpoint, gateway))
            }
            Text("This gateway is already paired. The encrypted credential follows its gateway identity to the new private HTTPS address.",
                color = Muted, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 16.dp))
        }
        FlatButton("PAIR AND CONNECT", Modifier.padding(16.dp), endpoint.startsWith("https://") && gateway.isNotBlank() && code.isNotBlank()) {
            model.pair(ConnectionProfile(name, endpoint, gateway), code, device)
        }
        if (state.issue.isNotBlank()) Notice(state.issue)
        Text("The gateway identity is checked before the device token is sent. Model credentials never leave desktop Zed.", color = Muted,
            fontSize = 12.sp, modifier = Modifier.padding(16.dp))
    }
}

@Composable
private fun SettingsScreen(state: AppState, model: ZedLinkViewModel) {
    val activity = LocalContext.current as? MainActivity
    var modelMenu by remember { mutableStateOf(false) }
    Column(Modifier.fillMaxSize()) {
        Header("Settings", "ZedLink for Android")
        state.threadSettings?.let { settings ->
            SectionHeading("SELECTED AGENT SESSION", "")
            Box(Modifier.fillMaxWidth().padding(horizontal = 16.dp)) {
                OutlinedButton(onClick = { modelMenu = true }, modifier = Modifier.fillMaxWidth()) {
                    Text(settings.models.firstOrNull { it.modelId == settings.modelId && it.providerId == settings.providerId }?.name ?: "Select model")
                }
                DropdownMenu(expanded = modelMenu, onDismissRequest = { modelMenu = false }) {
                    settings.models.forEach { option -> DropdownMenuItem(
                        text = { Text("${option.name} · ${option.providerId}") },
                        onClick = { modelMenu = false; model.selectModel(option) }) }
                }
            }
            if (settings.usedTokens != null && settings.maxTokens != null) SettingRow("Context", "${settings.usedTokens} / ${settings.maxTokens} tokens")
        }
        TextButton(onClick = { if (state.notificationsEnabled) model.disableNotifications() else activity?.enableApprovalNotifications() }) {
            Text(if (state.notificationsEnabled) "Disable approval notifications" else "Enable lock-screen and paired watch alerts")
        }
        Text("Local alerts require this app to receive updates. Background FCM is not configured. Use browser push while suspended; Wear OS may mirror phone alerts.", color = Muted, fontSize = 12.sp, modifier = Modifier.padding(16.dp))
        SettingRow("Appearance", "OLED dark")
        SettingRow("Runtime", "Native Zed Agent")
        SettingRow("Connection", state.profile?.endpoint ?: "Not paired")
        Text("ZedLink displays only explicitly exposed native threads. It does not contain a model client or remote shell.", color = Muted,
            modifier = Modifier.padding(16.dp))
        if (state.profile != null) FlatButton("FORGET THIS DEVICE", Modifier.padding(16.dp), action = model::forget)
    }
}

@Composable private fun SettingRow(label: String, value: String) {
    Row(Modifier.fillMaxWidth().border(1.dp, Line).padding(16.dp)) { Text(label, color = Muted); Spacer(Modifier.weight(1f)); Text(value, fontSize = 12.sp) }
}

@Composable private fun Header(title: String, subtitle: String, action: @Composable () -> Unit = {}) {
    Row(Modifier.fillMaxWidth().padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) { Text(title, fontSize = 31.sp, fontWeight = FontWeight.Bold); Text(subtitle, color = Muted, fontSize = 12.sp) }
        action()
    }
    Rule()
}
@Composable private fun SectionHeading(label: String, value: String) { Row(Modifier.fillMaxWidth().padding(16.dp, 22.dp, 16.dp, 9.dp)) { Text(label, style = monoLabel()); Spacer(Modifier.weight(1f)); Text(value, color = Subtle, style = monoLabel()) } }
@Composable private fun Notice(text: String) { Text(text, color = Warning, fontSize = 12.sp, modifier = Modifier.fillMaxWidth().background(Color(0xFF1C1915)).padding(11.dp)) }
@Composable private fun Rule(start: androidx.compose.ui.unit.Dp = 0.dp) { HorizontalDivider(Modifier.padding(start = start), color = Line, thickness = 1.dp) }
@Composable private fun FlatInput(value: String, change: (String) -> Unit, hint: String, modifier: Modifier = Modifier) { BasicTextField(value, change, modifier.fillMaxWidth().heightIn(min = 48.dp).border(1.dp, Line).background(Surface).padding(13.dp), textStyle = TextStyle(color = Ink), cursorBrush = SolidColor(Ink), decorationBox = { inner -> Box { if (value.isEmpty()) Text(hint, color = Subtle); inner() } }) }
@Composable private fun FlatButton(label: String, modifier: Modifier = Modifier, enabled: Boolean = true, action: () -> Unit) { Button(action, modifier.fillMaxWidth().heightIn(min = 48.dp), enabled = enabled, shape = androidx.compose.ui.graphics.RectangleShape, colors = ButtonDefaults.buttonColors(containerColor = Ink, contentColor = Black)) { Text(label, fontWeight = FontWeight.Bold) } }
@Composable private fun FlatIconButton(label: String, action: () -> Unit) { Box(Modifier.size(44.dp).border(1.dp, Line).clickable(onClick = action), contentAlignment = Alignment.Center) { Text(label, fontFamily = FontFamily.Monospace, fontSize = 20.sp) } }
private fun monoLabel() = TextStyle(color = Subtle, fontFamily = FontFamily.Monospace, fontWeight = FontWeight.SemiBold, fontSize = 10.sp, letterSpacing = 1.sp)


@Composable
private fun TerminalScreen(state: AppState, model: ZedLinkViewModel, close: () -> Unit) {
    var input by remember { mutableStateOf("") }
    var menu by remember { mutableStateOf(false) }
    var tools by remember { mutableStateOf(false) }
    var clipboard by remember { mutableStateOf(false) }
    val preferences = LocalContext.current.getSharedPreferences("zedlink-terminal", 0)
    var wrapOutput by remember { mutableStateOf(preferences.getBoolean("wrap", true)) }
    if (clipboard) RemoteClipboardDialog(state, model, { input = it }, { clipboard = false })
    val scrollScope = rememberCoroutineScope()
    val keyboard = LocalSoftwareKeyboardController.current
    val focus = LocalFocusManager.current
    val terminalScroll = rememberScrollState()
    val horizontalScroll = rememberScrollState()
    val latestState by rememberUpdatedState(state)
    val draftKey = "draft.${state.profile?.gatewayId}.${state.targetId}.${state.instanceId}.${state.epoch}.${state.terminalSnapshot?.terminal?.id}"
    var loadedDraftKey by remember { mutableStateOf("") }
    LaunchedEffect(draftKey) { input = preferences.getString(draftKey, "").orEmpty(); loadedDraftKey = draftKey }
    LaunchedEffect(input, loadedDraftKey) { if (loadedDraftKey == draftKey && state.terminalSnapshot != null) preferences.edit().putString(draftKey, input).apply() }
    LaunchedEffect(state.terminalSnapshot?.content) {
        if (terminalScroll.value >= terminalScroll.maxValue - 40) {
            withFrameNanos { }
            terminalScroll.scrollTo(terminalScroll.maxValue)
        }
    }
    LaunchedEffect(state.terminalSnapshot?.terminal?.id) {
        while (true) { latestState.terminalSnapshot?.terminal?.let { model.loadTerminal(it, refresh = true) }; delay(1000) }
    }
    Dialog(onDismissRequest = close, properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        Surface(color = Black, modifier = Modifier.fillMaxSize()) {
            Column(Modifier.fillMaxSize().systemBarsPadding().imePadding()) {
                Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).padding(horizontal = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                    IconButton(onClick = close) { Icon(Icons.Default.ArrowBack, "Back to workspace") }
                    Box(Modifier.weight(1f)) {
                        TextButton(onClick = { menu = true }) { Text(state.terminalSnapshot?.terminal?.title ?: "Terminal", maxLines = 1, overflow = TextOverflow.Ellipsis) }
                        DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                            state.terminals.forEach { terminal -> DropdownMenuItem(text = { Text(terminal.title, maxLines = 1) }, onClick = { menu = false; model.loadTerminal(terminal) }) }
                        }
                    }
                    if (state.terminalSnapshot?.terminal?.taskState == "running" && "task.stop" in state.capabilities) {
                        IconButton(onClick = model::stopTerminalTask) { Icon(Icons.Default.Stop, "Stop task", tint = MaterialTheme.colorScheme.error) }
                    }
                    Box {
                        IconButton(onClick = { tools = true }) { Icon(Icons.Default.MoreVert, "Terminal tools") }
                        DropdownMenu(expanded = tools, onDismissRequest = { tools = false }) {
                            DropdownMenuItem(text = { Text(if (wrapOutput) "Keep original columns" else "Wrap output") }, onClick = { wrapOutput = !wrapOutput; preferences.edit().putBoolean("wrap", wrapOutput).apply(); tools = false })
                            DropdownMenuItem(text = { Text("Remote clipboard") }, onClick = { clipboard = true; tools = false })
                            DropdownMenuItem(text = { Text("Recover session") }, onClick = { model.refresh(); tools = false })
                        }
                    }
                    IconButton(onClick = { scrollScope.launch { terminalScroll.scrollTo(terminalScroll.maxValue) } }) { Icon(Icons.Default.ArrowDownward, "Latest output") }
                }
                SelectionContainer(Modifier.weight(1f).fillMaxWidth()) {
                    Text(terminalText(state.terminalSnapshot), color = Ink, fontFamily = FontFamily.Monospace, fontSize = 12.sp,
                        modifier = Modifier.fillMaxSize().verticalScroll(terminalScroll).then(if (wrapOutput) Modifier else Modifier.horizontalScroll(horizontalScroll)).padding(10.dp))
                }
                if ("terminal.input" in state.capabilities) {
                    Row(Modifier.fillMaxWidth().background(Surface).horizontalScroll(rememberScrollState()).padding(5.dp), horizontalArrangement = Arrangement.spacedBy(3.dp)) {
                        listOf("Esc" to "\u001b", "Tab" to "\t", "Ctrl C" to "\u0003", "↑" to "\u001b[A", "↓" to "\u001b[B", "←" to "\u001b[D", "→" to "\u001b[C").forEach { (label, bytes) ->
                            TextButton(onClick = {
                                if (input.isNotEmpty()) { model.sendTerminalInput(input, appendReturn = false); input = "" }
                                model.sendTerminalInput(bytes, appendReturn = false)
                            }, modifier = Modifier.sizeIn(minWidth = 44.dp, minHeight = 44.dp)) { Text(label, fontFamily = FontFamily.Monospace, fontSize = 13.sp) }
                        }
                    }
                    Row(Modifier.fillMaxWidth().background(Surface).padding(horizontal = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text("›", color = Green); Spacer(Modifier.width(8.dp))
                        BasicTextField(value = input, onValueChange = { input = it }, modifier = Modifier.weight(1f), singleLine = true,
                            textStyle = TextStyle(color = Ink, fontSize = 16.sp, fontFamily = FontFamily.Monospace), cursorBrush = SolidColor(Green),
                            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send, autoCorrectEnabled = false),
                            keyboardActions = KeyboardActions(onSend = { model.sendTerminalInput(if (input.isEmpty()) "\r" else input + "\n", appendReturn = false); input = "" }),
                            decorationBox = { field -> if (input.isEmpty()) Text("Command or reply", color = Muted, fontSize = 16.sp); field() })
                        VoiceDraftButton(input, draftKey) { input = it }
                        IconButton(onClick = { model.sendTerminalInput(if (input.isEmpty()) "\r" else input + "\n", appendReturn = false); input = "" }) { Icon(Icons.Default.KeyboardReturn, "Send or press Enter") }
                        IconButton(onClick = { keyboard?.hide(); focus.clearFocus() }) { Icon(Icons.Default.KeyboardHide, "Hide keyboard") }
                    }
                } else { Text("Enable Send Terminal Input in desktop ZedLink settings.", color = Muted, modifier = Modifier.padding(12.dp)) }
            }
        }
    }
}


private fun terminalColor(hex: String): Color? = if (Regex("#[0-9a-fA-F]{6}").matches(hex)) Color(0xff000000L or hex.drop(1).toLong(16)) else null
private fun terminalText(snapshot: NativeTerminalSnapshot?): AnnotatedString = buildAnnotatedString {
    if (snapshot == null) return@buildAnnotatedString
    val runs = snapshot.styledRuns.ifEmpty { listOf(NativeTerminalRun(snapshot.content, "", "", false, false, false, false)) }
    runs.forEach { run ->
        val start = length
        append(run.text)
        val foreground = terminalColor(run.foreground) ?: Ink
        addStyle(SpanStyle(color = if (run.dim) foreground.copy(alpha = 0.7f) else foreground,
            background = terminalColor(run.background) ?: Color.Unspecified,
            fontWeight = if (run.bold) FontWeight.Bold else FontWeight.Normal,
            fontStyle = if (run.italic) FontStyle.Italic else FontStyle.Normal,
            textDecoration = if (run.underline) TextDecoration.Underline else TextDecoration.None), start, length)
        var index = 0
        while (index < run.text.length) {
            val code = run.text.codePointAt(index)
            val size = Character.charCount(code)
            if (code in 0xe5fa..0xe6b7 || code in 0xe700..0xe8ef || code in 0xf000..0xf2e0 || code in 0xf400..0xf533 || code in 0xf0001..0xf1af0) {
                addStyle(SpanStyle(fontFamily = FontFamily(Font(R.font.terminal_icons))), start + index, start + index + size)
            }
            index += size
        }
    }
}
