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
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.foundation.shape.RoundedCornerShape
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
                BottomTabs(tab, state.selectedThreadId != null) { next ->
                    if (state.selectedThreadId != null) model.closeThread()
                    tab = next
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
    var showActions by remember { mutableStateOf(false) }
    var showRename by remember { mutableStateOf(false) }
    var showUnexpose by remember { mutableStateOf(false) }
    var proposedTitle by remember(snapshot?.threadId) { mutableStateOf(snapshot?.title.orEmpty()) }
    Column(Modifier.fillMaxSize()) {
        Row(Modifier.fillMaxWidth().heightIn(min = 58.dp).border(1.dp, Line).padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = model::closeThread) { Icon(Icons.Default.ArrowBack, "Sessions", tint = Ink) }
            Column(Modifier.weight(1f)) {
                Text(snapshot?.title ?: "Loading native thread", fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(if (snapshot?.isBusy == true) "ZED IS WORKING" else "NATIVE THREAD READY", color = if (snapshot?.isBusy == true) Blue else Green,
                    fontFamily = FontFamily.Monospace, fontSize = 10.sp)
            }
            Box {
                IconButton(onClick = { showActions = true }) { Icon(Icons.Default.MoreVert, "Session actions", tint = Ink) }
                DropdownMenu(expanded = showActions, onDismissRequest = { showActions = false }) {
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
        }) { model.insertCommand(it); showCommands = false }
        if (state.delivery.isNotBlank()) Text(state.delivery, color = Warning, fontSize = 11.sp,
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
    LaunchedEffect(snapshot.lastSequence) { if (snapshot.entries.isNotEmpty()) list.animateScrollToItem(snapshot.entries.lastIndex + 1) }
    LazyColumn(modifier.fillMaxWidth(), state = list, contentPadding = PaddingValues(bottom = 10.dp)) {
        if (snapshot.hasOlderEntries) item {
            TextButton(onClick = model::loadEarlierHistory, shape = androidx.compose.ui.graphics.RectangleShape) {
                Text("LOAD EARLIER CONVERSATION · ${snapshot.entryStartIndex} REMAINING", color = Muted)
            }
        }
        itemsIndexed(snapshot.entries, key = { index, _ -> snapshot.entryStartIndex + index }) { index, markdown ->
            Message(NativeEntry.parse(markdown), snapshot.isBusy && index == snapshot.entries.lastIndex)
        }
        items(snapshot.approvals, key = { it.id }) { ApprovalCard(it, model::respondApproval) }
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
                .background(Raised, RoundedCornerShape(12.dp, 12.dp, 3.dp, 12.dp)).padding(horizontal = 14.dp, vertical = 11.dp)) {
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
    val parts = text.split("```")
    Column(modifier, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        parts.forEachIndexed { index, part ->
            if (part.isBlank()) return@forEachIndexed
            if (index % 2 == 1) Box(Modifier.fillMaxWidth().background(Black).border(1.dp, Line).horizontalScroll(rememberScrollState()).padding(11.dp)) {
                Text(part.substringAfter('\n', part), color = Ink, fontFamily = FontFamily.Monospace, fontSize = 12.sp, softWrap = false)
            } else Text(part, color = Ink, fontSize = 15.sp, lineHeight = 23.sp)
        }
    }
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
private fun CommandList(commands: List<NativeCommand>, delegate: () -> Unit, choose: (NativeCommand) -> Unit) {
    Column(Modifier.fillMaxWidth().heightIn(max = 260.dp).border(1.dp, Line).background(Raised).verticalScroll(rememberScrollState())) {
        Row(Modifier.fillMaxWidth().clickable(onClick = delegate).padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Default.AccountTree, null, tint = Blue, modifier = Modifier.size(19.dp))
            Column(Modifier.padding(start = 11.dp)) {
                Text("Delegate a parallel task", fontWeight = FontWeight.SemiBold)
                Text("Ask native Zed to use spawn_agent", color = Muted, fontSize = 12.sp)
            }
        }
        Rule()
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
        .border(1.dp, Line, RoundedCornerShape(14.dp)).background(Surface, RoundedCornerShape(14.dp)).padding(5.dp),
        verticalAlignment = Alignment.Bottom) {
        FlatIconButton("/", commands)
        BasicTextField(state.draft, model::setDraft, Modifier.weight(1f).heightIn(min = 44.dp, max = 140.dp).padding(11.dp),
            textStyle = TextStyle(color = Ink, fontSize = 16.sp), cursorBrush = SolidColor(Ink),
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
            keyboardActions = KeyboardActions(onSend = { submit() }),
            decorationBox = { inner ->
                Box { if (state.draft.isEmpty()) Text("Message Zed Agent…", color = Subtle); inner() }
            })
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
    Column(Modifier.fillMaxSize()) {
        Header("Settings", "ZedLink for Android")
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
