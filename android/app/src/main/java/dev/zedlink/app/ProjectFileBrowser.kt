package dev.zedlink.app

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import kotlinx.coroutines.launch

@Composable
fun ProjectFileBrowser(state: AppState, model: ZedLinkViewModel, close: () -> Unit) {
    val focus = LocalFocusManager.current
    val scopeKey = projectAccessScope(state)
    val preferences = LocalContext.current.getSharedPreferences("zedlink-file-reader", 0)
    val coroutineScope = rememberCoroutineScope()
    var directory by rememberSaveable(scopeKey) { mutableStateOf("") }
    var query by rememberSaveable(scopeKey) { mutableStateOf("") }
    var selectedPath by rememberSaveable(scopeKey) { mutableStateOf<String?>(null) }
    var wrap by remember { mutableStateOf(preferences.getBoolean("wrap", true)) }
    var finding by remember(selectedPath) { mutableStateOf(false) }
    var findQuery by remember(selectedPath) { mutableStateOf("") }
    var matchIndex by remember(findQuery, selectedPath) { mutableStateOf(0) }
    val vertical = key(selectedPath) { rememberScrollState() }
    val horizontal = key(selectedPath) { rememberScrollState() }
    var textLayout by remember(selectedPath, wrap) { mutableStateOf<TextLayoutResult?>(null) }
    LaunchedEffect(directory, state.live, state.capabilities, if ("project.directory" !in state.capabilities) state.projectFiles else emptyList<NativeProjectFile>()) { model.loadDirectory(directory).join() }
    val prefix = if (directory.isEmpty()) "" else "$directory/"
    val entries = (if (query.isBlank()) state.projectFolderEntries.orEmpty() else state.projectFiles).filter { entry ->
        if (query.isNotBlank()) entry.id.contains(query, ignoreCase = true)
        else entry.id.startsWith(prefix) && !entry.id.removePrefix(prefix).contains('/')
    }.sortedWith(compareBy<NativeProjectFile> { it.kind != "directory" }.thenBy { it.id.lowercase() })
    val matches = remember(state.previewContent, findQuery) { fileMatchRanges(state.previewContent, findQuery) }
    LaunchedEffect(matches) { matchIndex = 0 }
    fun findNext(direction: Int) {
        if (matches.isEmpty()) return
        matchIndex = (matchIndex + direction + matches.size) % matches.size
        textLayout?.takeIf { it.layoutInput.text.text == state.previewContent }?.let { layout ->
            val line = layout.getLineForOffset(matches[matchIndex].first.coerceAtMost(state.previewContent.length))
            coroutineScope.launch { vertical.animateScrollTo(layout.getLineTop(line).toInt()) }
        }
    }
    fun refreshFolder() { coroutineScope.launch { model.loadProjectContext().join(); model.loadDirectory(directory).join() } }
    Dialog(onDismissRequest = { if (selectedPath != null) selectedPath = null else close() },
        properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        Surface(Modifier.fillMaxSize().safeDrawingPadding()) {
            Column(Modifier.fillMaxSize().imePadding()) {
                Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp)) {
                    IconButton(onClick = { focus.clearFocus(); if (selectedPath != null) selectedPath = null else close() }) { Icon(Icons.Default.ArrowBack, "Back to files or workspace") }
                    Text(selectedPath?.substringAfterLast('/') ?: "Project files", modifier = Modifier.weight(1f).padding(12.dp), maxLines = 2)
                    if (selectedPath != null) {
                        IconButton(onClick = { finding = !finding; if (!finding) { findQuery = ""; focus.clearFocus() } }, enabled = state.previewReadable) { Icon(Icons.Default.Search, "Find in file") }
                        TextButton(onClick = { wrap = !wrap; preferences.edit().putBoolean("wrap", wrap).apply() }) { Text(if (wrap) "Wrap on" else "Wrap off") }
                    } else IconButton(onClick = { refreshFolder() }, enabled = state.live && !state.projectFolderLoading) { Icon(Icons.Default.Refresh, "Refresh files") }
                }
                val path = selectedPath
                if (path != null) {
                    SelectionContainer { Text(path, color = Muted, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp)) }
                    when {
                        state.previewLoading || state.previewTitle != path -> { LinearProgressIndicator(Modifier.fillMaxWidth()); Spacer(Modifier.weight(1f)) }
                        state.previewError.isNotBlank() -> {
                            Text(state.previewError, color = Warning, modifier = Modifier.padding(16.dp))
                            TextButton(onClick = { model.previewFile(path) }, enabled = state.live && "project.file" in state.capabilities) { Text("Retry file") }
                            Spacer(Modifier.weight(1f))
                        }
                        else -> {
                            if (finding) Row(verticalAlignment = Alignment.CenterVertically) {
                                OutlinedTextField(findQuery, { findQuery = it }, label = { Text(if (state.previewTruncated) "Find in loaded preview" else "Find in file") }, singleLine = true, modifier = Modifier.weight(1f).padding(8.dp))
                                Text(if (matches.isEmpty()) "0" else "${matchIndex + 1}/${matches.size}${if (matches.size == 2000) "+" else ""}", fontSize = 11.sp)
                                IconButton(onClick = { findNext(-1) }, enabled = matches.isNotEmpty()) { Icon(Icons.Default.KeyboardArrowUp, "Previous match") }
                                IconButton(onClick = { findNext(1) }, enabled = matches.isNotEmpty()) { Icon(Icons.Default.KeyboardArrowDown, "Next match") }
                            }
                            val stringColor = Green; val keywordColor = Blue; val commentColor = Muted
                            val content = remember(state.previewContent, stringColor, keywordColor, commentColor, matches, matchIndex) {
                                highlightedSource(state.previewContent, stringColor, keywordColor, commentColor, matches, matchIndex)
                            }
                            Box(Modifier.weight(1f).fillMaxWidth()) {
                                SelectionContainer(Modifier.fillMaxSize()) {
                                    Text(content, fontFamily = FontFamily.Monospace, fontSize = 13.sp, softWrap = wrap,
                                        onTextLayout = { textLayout = it }, modifier = Modifier.fillMaxSize().verticalScroll(vertical)
                                            .then(if (wrap) Modifier else Modifier.horizontalScroll(horizontal)).padding(16.dp))
                                }
                            }
                            Text(if (state.previewTruncated) "Partial text preview · 256 KiB limit · Cannot attach" else if (state.previewContent.isEmpty()) "Empty text file" else "Read-only project file",
                                modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp), fontSize = 12.sp)
                            TextButton(onClick = { model.toggleContextPath(path) }, enabled = path in state.contextPaths || state.live && "project.file" in state.capabilities && "thread.attachments" in state.capabilities && state.previewReadable && !state.previewTruncated) {
                                Text(if (path in state.contextPaths) "Remove from prompt" else if ("thread.attachments" !in state.capabilities) "Prompt attachments unavailable" else "Attach to prompt")
                            }
                        }
                    }
                } else {
                    if (!state.live) Text("Offline · Reconnect to refresh paths and read files.", color = Warning, fontSize = 12.sp, modifier = Modifier.padding(12.dp))
                    LazyRow {
                        item { TextButton(onClick = { directory = ""; query = "" }) { Text("Project") } }
                        directory.split('/').filter { it.isNotEmpty() }.forEachIndexed { index, part ->
                            item { TextButton(onClick = { directory = directory.split('/').take(index + 1).joinToString("/"); query = "" }) { Text("› $part") } }
                        }
                    }
                    OutlinedTextField(query, { query = it }, label = { Text("Filter loaded project paths") }, singleLine = true, modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp))
                    if (query.isNotBlank()) Text("Filtering ${state.projectFiles.size} loaded paths${if (state.projectFilesTruncated) " · Catalog incomplete; browse folders to find more files" else ""}.", color = Muted, fontSize = 12.sp, modifier = Modifier.padding(12.dp))
                    else if ("project.directory" !in state.capabilities && "project.files" in state.capabilities) Text("Browsing the loaded catalog. Folder refresh requires an updated Zed bridge.", color = Muted, fontSize = 12.sp, modifier = Modifier.padding(12.dp))
                    if ("project.file" !in state.capabilities) Text("File reading is unavailable. Enable project file access in desktop ZedLink settings.", color = Warning, fontSize = 12.sp, modifier = Modifier.padding(12.dp))
                    val catalogOnly = "project.directory" !in state.capabilities && "project.files" in state.capabilities
                    val awaitingFolder = state.projectFolderEntries == null && state.projectFolderError.isBlank() && state.live &&
                        ("project.directory" in state.capabilities || "project.files" in state.capabilities)
                    val loading = if (query.isBlank()) awaitingFolder || state.projectFolderLoading || state.projectFolderPath != directory || catalogOnly && state.projectFilesLoading else state.projectFilesLoading
                    val listingError = if (query.isBlank()) state.projectFolderError.ifBlank { if (catalogOnly) state.projectFilesError else "" } else state.projectFilesError
                    if (loading) LinearProgressIndicator(Modifier.fillMaxWidth())
                    LazyColumn(Modifier.weight(1f)) {
                        if (listingError.isNotBlank()) item {
                            Text(listingError, color = Warning, modifier = Modifier.padding(16.dp))
                            TextButton(onClick = { if (query.isBlank() && !catalogOnly) model.loadDirectory(directory) else model.loadProjectContext() }, enabled = state.live) { Text(if (query.isBlank()) "Retry folder" else "Retry catalog") }
                        }
                        items(entries, key = { it.id }) { entry ->
                            TextButton(onClick = {
                                focus.clearFocus()
                                if (entry.kind == "directory") { directory = entry.id; query = "" }
                                else { selectedPath = entry.id; model.previewFile(entry.id) }
                            }, enabled = state.live && !state.projectFolderLoading && (entry.kind == "directory" || "project.file" in state.capabilities), modifier = Modifier.fillMaxWidth()) {
                                Icon(if (entry.kind == "directory") Icons.Default.Folder else Icons.Default.Description, null)
                                Text(if (query.isNotBlank()) entry.id else entry.id.substringAfterLast('/'), modifier = Modifier.weight(1f).padding(10.dp), maxLines = 2)
                                if (entry.kind == "directory") Icon(Icons.Default.ChevronRight, null)
                            }
                        }
                        if (entries.isEmpty() && !loading && listingError.isBlank()) item { Text(if (query.isBlank()) "This folder has no remotely readable entries." else "No matching loaded paths. Browse folders or refresh the catalog.", modifier = Modifier.padding(16.dp)) }
                        if (if (query.isBlank()) state.projectFolderTruncated else state.projectFilesTruncated) item { Text("Listing limited to 1,000 entries. Hidden, ignored and private files are excluded.", modifier = Modifier.padding(16.dp), fontSize = 12.sp) }
                    }
                }
            }
        }
    }
}

private fun highlightedSource(source: String, stringColor: Color, keywordColor: Color, commentColor: Color, matches: List<IntRange> = emptyList(), selectedMatch: Int = 0) = buildAnnotatedString {
    append(source)
    matches.forEachIndexed { index, range -> addStyle(SpanStyle(background = keywordColor.copy(alpha = if (index == selectedMatch) 0.35f else 0.16f)), range.first, range.last + 1) }
    val pattern = Regex("""(?m)(//[^\n]*|#[^\n]*|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\b(?:fn|func|let|var|const|class|struct|enum|import|from|def|return|if|else|for|while|public|private|fun|val|true|false|null|nil|async|await)\b|\b\d+(?:\.\d+)?\b)""")
    pattern.findAll(source).take(10000).forEach { match ->
        val token = match.value
        val color = if (token.startsWith("//") || token.startsWith("#")) commentColor
            else if (token.startsWith('"') || token.startsWith('\'')) stringColor else keywordColor
        addStyle(SpanStyle(color = color), match.range.first, match.range.last + 1)
    }
}
