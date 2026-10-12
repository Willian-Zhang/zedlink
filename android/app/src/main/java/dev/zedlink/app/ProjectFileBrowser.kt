package dev.zedlink.app

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties

@Composable
fun ProjectFileBrowser(state: AppState, model: ZedLinkViewModel, close: () -> Unit) {
    val focus = LocalFocusManager.current
    var directory by remember { mutableStateOf("") }
    var query by remember { mutableStateOf("") }
    var reading by remember { mutableStateOf(false) }
    var wrap by remember { mutableStateOf(true) }
    val prefix = if (directory.isEmpty()) "" else "$directory/"
    LaunchedEffect(directory) { model.loadDirectory(directory).join() }
    val entries = (if (query.isBlank()) state.projectFolderEntries ?: state.projectFiles else state.projectFiles).filter { entry ->
        if (query.isNotBlank()) entry.id.contains(query, ignoreCase = true)
        else entry.id.startsWith(prefix) && !entry.id.removePrefix(prefix).contains('/')
    }.sortedWith(compareBy<NativeProjectFile> { it.kind != "directory" }.thenBy { it.id.lowercase() })
    Dialog(onDismissRequest = { if (reading) reading = false else close() },
        properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        Surface(Modifier.fillMaxSize().safeDrawingPadding()) {
            Column {
                Row(Modifier.fillMaxWidth().padding(8.dp)) {
                    IconButton(onClick = { if (reading) reading = false else close() }) { Icon(Icons.Default.ArrowBack, "Back to files or workspace") }
                    Text(if (reading) state.previewTitle.substringAfterLast('/') else "Project files", modifier = Modifier.weight(1f).padding(12.dp), maxLines = 2)
                    if (reading) TextButton(onClick = { wrap = !wrap }) { Text(if (wrap) "Wrap on" else "Wrap off") }
                }
                if (reading) {
                    if (state.previewLoading) { LinearProgressIndicator(Modifier.fillMaxWidth()); Spacer(Modifier.weight(1f)) }
                    else {
                        val content = remember(state.previewContent) { highlightedSource(state.previewContent) }
                        SelectionContainer(Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState())
                            .then(if (wrap) Modifier else Modifier.horizontalScroll(rememberScrollState()))) {
                            Text(content, fontFamily = FontFamily.Monospace, fontSize = 13.sp,
                                softWrap = wrap, modifier = Modifier.padding(16.dp))
                        }
                        Text(if (state.previewTruncated) "Partial preview · 256 KiB limit · Cannot attach" else "Read-only project file", modifier = Modifier.padding(12.dp), fontSize = 12.sp)
                        TextButton(onClick = { model.toggleContextPath(state.previewTitle) }, enabled = state.previewReadable && !state.previewTruncated) {
                            Text(if (state.previewTitle in state.contextPaths) "Remove from prompt" else "Attach to prompt")
                        }
                    }
                } else {
                    Row {
                        TextButton(onClick = { directory = ""; query = "" }) { Text("Project") }
                        if (directory.isNotEmpty()) TextButton(onClick = { directory = directory.substringBeforeLast('/', "") }) { Text("↑ Parent") }
                    }
                    if (directory.isNotEmpty()) Text(directory, modifier = Modifier.padding(horizontal = 16.dp), fontSize = 12.sp)
                    OutlinedTextField(query, { query = it }, label = { Text("Filter project paths") }, singleLine = true, modifier = Modifier.fillMaxWidth().padding(12.dp))
                    LazyColumn(Modifier.weight(1f)) {
                        items(entries, key = { it.id }) { entry ->
                            TextButton(onClick = {
                                focus.clearFocus()
                                if (entry.kind == "directory") { directory = entry.id; query = "" }
                                else { model.previewFile(entry.id); reading = true }
                            }, modifier = Modifier.fillMaxWidth()) {
                                Icon(if (entry.kind == "directory") Icons.Default.Folder else Icons.Default.Description, null)
                                Text(if (query.isNotBlank()) entry.id else entry.id.substringAfterLast('/'), modifier = Modifier.weight(1f).padding(10.dp), maxLines = 2)
                                if (entry.kind == "directory") Icon(Icons.Default.ChevronRight, null)
                            }
                        }
                        if (entries.isEmpty()) item { Text("No readable files in this folder or filter.", modifier = Modifier.padding(16.dp)) }
                        if (if (query.isBlank()) state.projectFolderEntries?.let { state.projectFolderTruncated } ?: state.projectFilesTruncated else state.projectFilesTruncated) item { Text("Listing limited to 1,000 entries. Hidden, ignored and private files are excluded.", modifier = Modifier.padding(16.dp), fontSize = 12.sp) }
                    }
                }
            }
        }
    }
}

private fun highlightedSource(source: String) = buildAnnotatedString {
    append(source)
    val pattern = Regex("""(?m)(//[^\n]*|#[^\n]*|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\b(?:fn|func|let|var|const|class|struct|enum|import|from|def|return|if|else|for|while|public|private|fun|val|true|false|null|nil|async|await)\b|\b\d+(?:\.\d+)?\b)""")
    pattern.findAll(source).take(10000).forEach { match ->
        val token = match.value
        val color = if (token.startsWith("//") || token.startsWith("#")) Color.Gray
            else if (token.startsWith('"') || token.startsWith('\'')) Color(0xff9ac79b) else Color(0xff91c8ee)
        addStyle(SpanStyle(color = color), match.range.first, match.range.last + 1)
    }
}
