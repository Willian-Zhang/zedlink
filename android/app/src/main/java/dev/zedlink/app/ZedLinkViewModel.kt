package dev.zedlink.app

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID
import okhttp3.WebSocket

data class AppState(
    val profile: ConnectionProfile? = null,
    val profiles: List<ConnectionProfile> = emptyList(),
    val targets: List<ZedTarget> = emptyList(),
    val targetId: String? = null,
    val status: String = "Offline",
    val live: Boolean = false,
    val connecting: Boolean = false,
    val connectionBusy: Boolean = false,
    val connectionIssue: String = "",
    val threads: List<NativeThread> = emptyList(),
    val pinnedThreads: Set<String> = emptySet(),
    val updatedThreads: Set<String> = emptySet(),
    val selectedThreadId: String? = null,
    val snapshot: ThreadSnapshot? = null,
    val commands: List<NativeCommand> = emptyList(),
    val localConfirmation: NativeCommand? = null,
    val createAgents: List<AgentOption> = emptyList(),
    val creatingThread: Boolean = false,
    val capabilities: Set<String> = emptySet(),
    val instanceId: String? = null,
    val epoch: String? = null,
    val draft: String = "",
    val delivery: String = "",
    val issue: String = "",
    val sending: Boolean = false,
    val elicitations: List<NativeElicitation> = emptyList(),
    val resolvingElicitations: Set<String> = emptySet(),
    val queuedMessages: List<NativeQueueEntry> = emptyList(),
    val editReview: NativeEditReview? = null,
    val threadSettings: NativeThreadSettings? = null,
    val projectFiles: List<NativeProjectFile> = emptyList(),
    val changes: List<NativeChange> = emptyList(),
    val changesRevision: String? = null,
    val terminals: List<NativeTerminal> = emptyList(),
    val terminalSnapshot: NativeTerminalSnapshot? = null,
    val configuredTasks: List<NativeConfiguredTask> = emptyList(),
    val debuggerCatalog: List<NativeDebugScenario> = emptyList(),
    val debuggerSessions: List<NativeDebuggerSession> = emptyList(),
    val notificationsEnabled: Boolean = false,
    val appearance: String = "dark",
    val updatingModel: Boolean = false,
    val projectFolderEntries: List<NativeProjectFile>? = null,
    val projectFolderTruncated: Boolean = false,
    val projectFilesTruncated: Boolean = false,
    val previewReadable: Boolean = false,
    val previewLoading: Boolean = false,
    val previewTruncated: Boolean = false,
    val previewTitle: String = "",
    val previewContent: String = "",
    val contextPaths: Set<String> = emptySet(),
)

class ZedLinkViewModel(application: Application) : AndroidViewModel(application) {
    var state by mutableStateOf(AppState())
        private set
    var notificationRevision by mutableStateOf(0)
        private set
    var notificationMessage by mutableStateOf("")
        private set
    fun notificationPermissionResult(allowed: Boolean) {
        notificationRevision++
        notificationMessage = if (allowed) "" else "Permission was not granted. Allow notifications in Android Settings."
        if (allowed) enableNotifications()
    }
    var pairingDraft by mutableStateOf(ConnectionDraft())
    val approvalNotifications = ApprovalNotifications(application)
    fun enableNotifications() { approvalNotifications.enable(); state = state.copy(notificationsEnabled = true); approvalNotifications.update(state) }
    fun disableNotifications() { approvalNotifications.disable(); state = state.copy(notificationsEnabled = false) }
    private var directoryRequest = 0
    private var previewRequest = 0
    private var client: GatewayClient? = null
    private var pollJob: Job? = null
    private var connectionJob: Job? = null
    private var connectionGeneration = 0L
    private var eventSocket: WebSocket? = null
    private var eventStreamLive = false
    private var pendingId: String? = null
    private var pendingText: String? = null
    private var pendingScope: List<String?>? = null
    private var pendingContextPaths: Set<String> = emptySet()
    private var pendingLocalConfirmed = false
    private var localConfirmationScope: List<String?>? = null
    private var localConfirmationText = ""
    private var lastCommandsRefresh = 0L
    private val preferences = application.getSharedPreferences("zedlink-profile", 0)

    init {
        val saved = loadProfiles()
        val preferred = loadProfile(saved)
        state = state.copy(profile = preferred, profiles = saved, notificationsEnabled = approvalNotifications.enabled, appearance = preferences.getString("appearance", "dark") ?: "dark")
        preferred?.let { profile ->
            if (TokenVault.read(application, profile.gatewayId) != null) connect()
        }
    }

    fun setAppearance(value: String) {
        if (value !in setOf("system", "dark", "light")) return
        preferences.edit().putString("appearance", value).apply()
        state = state.copy(appearance = value)
    }

    fun applyPairingLink(text: String): Pair<ConnectionProfile, String?> = GatewayClient.profileFromPairingLink(text)

    fun pair(profile: ConnectionProfile, code: String, deviceName: String, finished: (Boolean) -> Unit = {}) = viewModelScope.launch {
        if (state.connectionBusy || state.connecting) return@launch
        val generation = connectionGeneration
        state = state.copy(connectionBusy = true, connectionIssue = "")
        try {
            val (_, token) = GatewayClient(profile, null).pair(code.trim(), deviceName.trim().ifBlank { "Android" })
            if (generation != connectionGeneration) return@launch
            TokenVault.write(getApplication(), profile.gatewayId, token)
            val saved = saveProfile(profile)
            state = state.copy(profiles = loadProfiles(), connectionBusy = false)
            connect(saved)
            finished(true)
        } catch (error: Exception) {
            if (generation == connectionGeneration) {
                state = state.copy(connectionIssue = connectionFailure(error))
                finished(false)
            }
        } finally { state = state.copy(connectionBusy = false) }
    }

    fun updateRoute(profile: ConnectionProfile, finished: (Boolean) -> Unit = {}) = viewModelScope.launch {
        if (state.connectionBusy || state.connecting) return@launch
        val generation = connectionGeneration
        state = state.copy(connectionBusy = true, connectionIssue = "")
        try {
            val observed = GatewayClient(profile, null).gatewayId()
            if (generation != connectionGeneration) return@launch
            if (!observed.equals(profile.gatewayId, ignoreCase = true)) throw GatewayException("This address belongs to a different gateway. No credential was sent.")
            if (TokenVault.read(getApplication(), profile.gatewayId) == null) throw GatewayException("The saved credential is missing. Pair this device again.")
            val saved = saveProfile(profile)
            state = state.copy(profiles = loadProfiles(), connectionBusy = false)
            connect(saved)
            finished(true)
        } catch (error: Exception) {
            if (generation == connectionGeneration) { state = state.copy(connectionIssue = connectionFailure(error)); finished(false) }
        } finally { state = state.copy(connectionBusy = false) }
    }

    fun connect() {
        if (connectionJob?.isActive == true || state.connectionBusy) return
        requestedTerminalId = null
        approvalNotifications.clear()
        val profile = state.profile ?: return
        pollJob?.cancel(); eventSocket?.cancel()
        val generation = ++connectionGeneration
        client = null; eventStreamLive = false
        val token = TokenVault.read(getApplication(), profile.gatewayId) ?: run {
            state = state.copy(status = "Pair this device", live = false, connecting = false); return
        }
        connectionJob = viewModelScope.launch {
            state = state.copy(status = "Connecting…", live = false, connecting = true, issue = "")
            try {
                val discovery = GatewayClient(profile, token)
                val registry = discovery.rpc("instance.list")
                if (generation != connectionGeneration) return@launch
                val targets = registry.optJSONArray("targets").objects().mapNotNull { row ->
                    val id = row.optString("target_id")
                    val label = row.optString("label")
                    if (id.isBlank() || label.isBlank()) null else ZedTarget(id, label, row.optBoolean("available"))
                }
                if (targets.isEmpty()) throw GatewayException("This gateway has no configured Zed targets.")
                val savedTarget = preferences.getString("target.${profile.gatewayId}", null)
                val preferredTarget = state.targetId ?: savedTarget ?: registry.optString("default_target_id")
                val selectedTarget = targets.firstOrNull { it.id == preferredTarget }
                    ?: targets.firstOrNull { it.available } ?: targets.first()
                preferences.edit().putString("target.${profile.gatewayId}", selectedTarget.id).apply()
                val next = GatewayClient(profile, token, selectedTarget.id)
                val info = next.rpc("instance.info")
                if (generation != connectionGeneration) return@launch
                client = next
                val sameEpoch = state.instanceId == info.getString("instance_id") && state.epoch == info.getString("epoch")
                if (!sameEpoch) state = state.copy(snapshot = null, commands = emptyList(), threadSettings = null, elicitations = emptyList(), queuedMessages = emptyList(), editReview = null)
                state = state.copy(
                    status = "Loading sessions…", live = false, connecting = true,
                    targets = targets, targetId = selectedTarget.id,
                    instanceId = info.getString("instance_id"), epoch = info.getString("epoch"),
                    capabilities = info.optJSONArray("capabilities").strings().toSet(), issue = "",
                )
                loadThreads()
                if (generation != connectionGeneration) return@launch
                if (state.selectedThreadId != null) loadSnapshot(state.selectedThreadId!!)
                if (generation != connectionGeneration) return@launch
                state = state.copy(status = "Connected to Zed", live = true, connecting = false)
                pollJob = viewModelScope.launch { poll(generation) }
            } catch (error: Exception) {
                if (generation == connectionGeneration) state = state.copy(status = "Connection failed", live = false, connecting = false, issue = connectionFailure(error))
            }
        }
    }

    fun refresh() = connect()

    fun loadCreateOptions() = viewModelScope.launch {
        if ("thread.create.options" !in state.capabilities) {
            state = state.copy(createAgents = listOf(AgentOption("zed-agent", "Zed Agent", "zed")))
            return@launch
        }
        try {
            val result = client!!.rpc("thread.create.options", JSONObject()
                .put("instance_id", state.instanceId).put("epoch", state.epoch))
            checkIdentity(result)
            val agents = result.optJSONArray("agents").objects().mapNotNull { row ->
                val id = row.optString("id"); val name = row.optString("name")
                if (id.isBlank() || name.isBlank()) null else AgentOption(id, name, row.optString("kind", "external_acp"))
            }
            state = state.copy(createAgents = agents)
        } catch (error: Exception) { state = state.copy(issue = error.message.orEmpty()) }
    }

    fun createThread(title: String, agentId: String) = viewModelScope.launch {
        val activeClient = client ?: return@launch
        val instance = state.instanceId ?: return@launch
        val epoch = state.epoch ?: return@launch
        if (state.creatingThread || "thread.create" !in state.capabilities) return@launch
        val requestId = UUID.randomUUID().toString()
        state = state.copy(creatingThread = true, issue = "")
        try {
            repeat(40) {
                val params = JSONObject().put("instance_id", instance).put("epoch", epoch)
                    .put("title", title.trim().ifEmpty { JSONObject.NULL }).put("agent_id", agentId)
                val result = activeClient.rpc("thread.create", params, requestId)
                if (result.optString("outcome") == "ready" && result.optString("thread_id").isNotBlank()) {
                    loadThreads(); selectThread(result.getString("thread_id")); return@launch
                }
                if (result.optString("outcome") != "creating") throw GatewayException("Zed returned an invalid creation state.")
                delay(250)
            }
            throw GatewayException("Zed is still creating the session. Refresh to check its status.")
        } catch (error: Exception) { state = state.copy(issue = error.message.orEmpty()) }
        finally { state = state.copy(creatingThread = false) }
    }

    fun selectTarget(id: String) {
        if (state.connecting || state.connectionBusy) return
        approvalNotifications.clear(); directoryRequest += 1; previewRequest += 1
        val target = state.targets.firstOrNull { it.id == id && it.available } ?: return
        val profile = state.profile ?: return
        pollJob?.cancel(); client = null; pendingId = null; pendingText = null
        preferences.edit().putString("target.${profile.gatewayId}", target.id).apply()
        state = state.copy(targetId = target.id, threads = emptyList(), selectedThreadId = null, updatedThreads = emptySet(), pinnedThreads = emptySet(),
            snapshot = null, commands = emptyList(), instanceId = null, epoch = null, live = false,
            projectFiles = emptyList(), projectFolderEntries = null, previewLoading = false, previewReadable = false, previewTitle = "", previewContent = "")
        connect()
    }

    fun connect(profile: ConnectionProfile) {
        if (state.connectionBusy || state.connecting) return
        connectionGeneration++; connectionJob?.cancel(); connectionJob = null
        if (state.profile?.gatewayId?.equals(profile.gatewayId, true) != true) {
            pollJob?.cancel(); client = null; pendingId = null; pendingText = null
            state = state.copy(profile = profile, threads = emptyList(), selectedThreadId = null, updatedThreads = emptySet(), pinnedThreads = emptySet(),
                snapshot = null, commands = emptyList(), capabilities = emptySet(), targets = emptyList(), targetId = null,
                instanceId = null, epoch = null, issue = "", delivery = "",
                projectFiles = emptyList(), projectFolderEntries = null, previewLoading = false, previewReadable = false, previewTitle = "", previewContent = "")
        }
        state = state.copy(profile = profile)
        preferences.edit().putString("active_profile", profile.id).putString("active_gateway", profile.gatewayId).apply()
        connect()
    }

    fun selectThread(id: String) = viewModelScope.launch {
        if (state.selectedThreadId != id) childHistory.clear()
        if (state.threads.none { it.id == id }) return@launch
        val generation = connectionGeneration
        val draft = preferences.getString("draft.$id", "").orEmpty()
        previewRequest += 1; directoryRequest += 1
        state = state.copy(selectedThreadId = id, snapshot = null, commands = emptyList(), draft = draft, issue = "",
            updatedThreads = state.updatedThreads - id,
            projectFolderEntries = null, projectFiles = emptyList(), projectFilesTruncated = false, previewReadable = false, previewLoading = false, previewContent = "", previewTitle = "")
        runCatching { loadSnapshot(id); if (generation == connectionGeneration && state.selectedThreadId == id) loadCommands(id) }
            .onFailure { if (generation == connectionGeneration && state.selectedThreadId == id) state = state.copy(issue = it.message.orEmpty()) }
        if (generation == connectionGeneration && state.selectedThreadId == id) startEventStream(id)
    }

    fun closeThread() { approvalNotifications.clear(); eventSocket?.cancel(); eventSocket = null; eventStreamLive = false; state = state.copy(selectedThreadId = null, snapshot = null, commands = emptyList()) }

    private fun startEventStream(threadId: String) {
        eventSocket?.cancel()
        val activeClient = client ?: return
        val generation = connectionGeneration
        eventSocket = activeClient.eventStream(threadId, state.snapshot?.lastSequence ?: 0, { result ->
            viewModelScope.launch {
                if (generation != connectionGeneration || activeClient !== client || state.selectedThreadId != threadId) return@launch
                eventStreamLive = true
                runCatching { checkIdentity(result); loadSnapshot(threadId) }
                    .onFailure { state = state.copy(issue = it.message.orEmpty()) }
            }
        }, { error -> viewModelScope.launch {
            if (generation != connectionGeneration || activeClient !== client) return@launch
            eventStreamLive = false
            if (state.selectedThreadId == threadId) {
                state = state.copy(issue = "Live updates reconnecting: ${error.message}")
                delay(1_500)
                if (generation == connectionGeneration && activeClient === client && state.selectedThreadId == threadId && !eventStreamLive) startEventStream(threadId)
            }
        } })
    }

    fun renameSelectedThread(proposedTitle: String) = viewModelScope.launch {
        val title = proposedTitle.trim()
        val activeClient = client ?: return@launch
        val threadId = state.selectedThreadId ?: return@launch
        val instance = state.instanceId ?: return@launch
        val epoch = state.epoch ?: return@launch
        if (title.isEmpty() || "thread.rename" !in state.capabilities) return@launch
        try {
            val result = activeClient.rpc("thread.rename", JSONObject()
                .put("instance_id", instance).put("epoch", epoch)
                .put("thread_id", threadId).put("title", title))
            if (result.optString("outcome") != "requested") throw GatewayException("Zed did not accept the title change.")
            loadThreads()
            state = state.copy(delivery = "Session renamed in desktop Zed.", issue = "")
        } catch (error: Exception) { state = state.copy(issue = error.message.orEmpty()) }
    }

    fun unexposeSelectedThread() = viewModelScope.launch {
        val activeClient = client ?: return@launch
        val threadId = state.selectedThreadId ?: return@launch
        val instance = state.instanceId ?: return@launch
        val epoch = state.epoch ?: return@launch
        if ("thread.unexpose" !in state.capabilities) return@launch
        try {
            val result = activeClient.rpc("thread.unexpose", JSONObject()
                .put("instance_id", instance).put("epoch", epoch).put("thread_id", threadId))
            if (result.optString("outcome") != "unexposed") throw GatewayException("Zed did not stop exposure.")
            state = state.copy(selectedThreadId = null, snapshot = null, commands = emptyList(),
                delivery = "Remote exposure stopped. The Agent thread remains open in desktop Zed.", issue = "")
            loadThreads()
        } catch (error: Exception) { state = state.copy(issue = error.message.orEmpty()) }
    }

    fun setDraft(value: String) {
        state = state.copy(draft = value)
        state.selectedThreadId?.let { preferences.edit().putString("draft.$it", value).apply() }
    }

    fun insertCommand(command: NativeCommand) = setDraft("/${command.name}${if (command.requiresArgument) " " else ""}")

    fun prepareSubagentTask() = setDraft("Use the native spawn_agent tool to delegate the following task to a child Zed Agent. Keep the child scoped to this project and return its result in this conversation:\n\nTask: ")

    fun dismissLocalCommand() { state = state.copy(localConfirmation = null) }
    fun confirmLocalCommand() {
        if (state.localConfirmation == null || state.draft.trim() != localConfirmationText || localConfirmationScope != listOf(state.profile?.gatewayId, state.targetId, state.instanceId, state.epoch, state.selectedThreadId)) { dismissLocalCommand(); return }
        dismissLocalCommand(); send(localConfirmed = true)
    }

    fun send(localConfirmed: Boolean = false) = viewModelScope.launch {
        val text = state.draft.trim()
        val threadId = state.selectedThreadId ?: return@launch
        val instance = state.instanceId ?: return@launch
        val epoch = state.epoch ?: return@launch
        val activeClient = client ?: return@launch
        if (text.isEmpty() || state.sending || !state.live) return@launch
        val command = state.commands.firstOrNull { "/${it.name}" == text && it.execution == "local" }
        if (command != null && !localConfirmed) {
            localConfirmationText = text
            localConfirmationScope = listOf(state.profile?.gatewayId, state.targetId, instance, epoch, threadId)
            state = state.copy(localConfirmation = command); return@launch
        }
        if (command != null && state.contextPaths.isNotEmpty()) { state = state.copy(issue = "Run local commands without attachments."); return@launch }
        pendingLocalConfirmed = localConfirmed
        pendingId = UUID.randomUUID().toString(); pendingText = text
        pendingScope = listOf(state.profile?.gatewayId, state.targetId, instance, epoch, threadId)
        pendingContextPaths = state.contextPaths.toSet()
        state = state.copy(sending = true, delivery = "Sending to native Zed…")
        try {
            val result = activeClient.rpc("thread.send", JSONObject()
                .put("instance_id", instance).put("epoch", epoch).put("thread_id", threadId).put("text", text)
                .apply { if (pendingContextPaths.isNotEmpty()) put("context_paths", JSONArray(pendingContextPaths.toList())); if (pendingLocalConfirmed) put("local_confirmed", true) }, pendingId!!)
            pendingId = null; pendingText = null
            setDraft("")
            state = state.copy(sending = false, contextPaths = emptySet(), delivery = if (result.optString("outcome") == "queued")
                "Queued in desktop Zed." else "Received by desktop Zed. Watching native progress.")
            if (result.optString("outcome") == "local_completed" || result.optString("outcome") == "desktop_review_required") {
                state = state.copy(delivery = if (text == "/not-helpful") "Complete the feedback form in desktop Zed." else "Desktop action completed.")
                if (text == "/remote-control") { closeThread(); loadThreads(); return@launch }
            }
            loadSnapshot(threadId)
        } catch (error: Exception) {
            state = state.copy(sending = false, delivery = "Delivery unknown: ${error.message}. Check desktop Zed before retrying.")
        }
    }

    fun retryPending() = viewModelScope.launch {
        val id = pendingId ?: return@launch
        val text = pendingText ?: return@launch
        val threadId = state.selectedThreadId ?: return@launch
        val instance = state.instanceId ?: return@launch
        val epoch = state.epoch ?: return@launch
        val activeClient = client ?: return@launch
        if (pendingScope != listOf(state.profile?.gatewayId, state.targetId, instance, epoch, threadId)) {
            state = state.copy(delivery = "Delivery remains unknown for the original Zed instance/session. The request was not resent.")
            return@launch
        }
        state = state.copy(sending = true)
        try {
            activeClient.rpc("thread.send", JSONObject().put("instance_id", instance).put("epoch", epoch)
                .put("thread_id", threadId).put("text", text).apply { if (pendingContextPaths.isNotEmpty()) put("context_paths", JSONArray(pendingContextPaths.toList())); if (pendingLocalConfirmed) put("local_confirmed", true) }, id)
            pendingId = null; pendingText = null
            setDraft("")
            state = state.copy(sending = false, delivery = "Request reached desktop Zed.")
            loadSnapshot(threadId)
        } catch (error: Exception) { state = state.copy(sending = false, issue = error.message.orEmpty()) }
    }

    fun cancel() = viewModelScope.launch {
        val snapshot = state.snapshot ?: return@launch
        val turn = snapshot.currentTurnId ?: return@launch
        try {
            client?.rpc("thread.cancel", JSONObject().put("instance_id", state.instanceId).put("epoch", state.epoch)
                .put("thread_id", snapshot.threadId).put("turn_id", turn))
            state = state.copy(delivery = "Stop requested for this desktop Zed turn.")
            loadSnapshot(snapshot.threadId)
        } catch (error: Exception) { state = state.copy(issue = error.message.orEmpty()) }
    }

    fun loadEarlierHistory() = viewModelScope.launch {
        val old = state.snapshot ?: return@launch
        val activeClient = client ?: return@launch
        if (old.entryStartIndex <= 0 || "thread.history" !in state.capabilities) return@launch
        try {
            val result = activeClient.rpc("thread.history", JSONObject()
                .put("thread_id", old.threadId).put("before_entry_index", old.entryStartIndex))
            checkIdentity(result)
            val current = state.snapshot
            if (state.selectedThreadId != old.threadId || current == null
                || current.threadId != old.threadId || current.entryStartIndex != old.entryStartIndex
                || result.optString("thread_id") != old.threadId
                || result.optInt("entry_end_index", -1) != old.entryStartIndex) return@launch
            val start = result.optInt("entry_start_index", -1)
            val entries = result.optJSONArray("entries_markdown").strings()
            if (start < 0 || start + entries.size != old.entryStartIndex) return@launch
            state = state.copy(snapshot = current.copy(
                entries = entries + current.entries,
                entryStartIndex = start,
                totalEntries = maxOf(current.totalEntries, result.optInt("total_entries")),
                hasOlderEntries = start > 0,
                truncated = start > 0,
            ))
        } catch (error: Exception) {
            state = state.copy(issue = error.message.orEmpty())
        }
    }

    fun forget() {
        approvalNotifications.clear()
        state.profile?.let(::forget)
    }

    fun removeConnection(profile: ConnectionProfile) {
        if (state.connectionBusy || state.connecting) return
        val remaining = loadProfiles().filterNot { it.id == profile.id }
        val linked = remaining.any { it.gatewayId.equals(profile.gatewayId, true) }
        if (!linked) TokenVault.clear(getApplication(), profile.gatewayId)
        persistProfiles(remaining)
        if (state.profile?.id != profile.id) { state = state.copy(profiles = remaining); return }
        connectionGeneration++; connectionJob?.cancel(); connectionJob = null
        pollJob?.cancel(); eventSocket?.cancel(); eventSocket = null; eventStreamLive = false; client = null
        approvalNotifications.clear()
        val next = remaining.firstOrNull()
        preferences.edit().putString("active_profile", next?.id).putString("active_gateway", next?.gatewayId).apply()
        state = AppState(profile = next, profiles = remaining, appearance = state.appearance,
            notificationsEnabled = approvalNotifications.enabled, status = if (next == null) "Pair this device" else "Offline")
    }

    fun forget(profile: ConnectionProfile) {
        val active = state.profile?.gatewayId?.equals(profile.gatewayId, true) == true
        if (active) {
            connectionGeneration++; connectionJob?.cancel(); connectionJob = null
            approvalNotifications.clear()
            pollJob?.cancel(); eventSocket?.cancel(); eventSocket = null; eventStreamLive = false; client = null
        }
        TokenVault.clear(getApplication(), profile.gatewayId)
        val remaining = loadProfiles().filterNot { it.gatewayId.equals(profile.gatewayId, true) }
        persistProfiles(remaining)
        if (!active) { state = state.copy(profiles = remaining); return }
        val next = remaining.firstOrNull()
        preferences.edit().putString("active_profile", next?.id).putString("active_gateway", next?.gatewayId).apply()
        state = AppState(profile = next, profiles = remaining, appearance = state.appearance,
            notificationsEnabled = approvalNotifications.enabled, status = if (next == null) "Pair this device" else "Offline")
    }

    private suspend fun poll(generation: Long) {
        while (viewModelScope.isActive && generation == connectionGeneration) {
            try {
                val selected = state.selectedThreadId
                if (selected == null) loadThreads() else {
                    val events = client!!.rpc("thread.events", JSONObject().put("thread_id", selected)
                        .put("after_sequence", state.snapshot?.lastSequence ?: 0))
                    if (generation != connectionGeneration) return
                    checkIdentity(events)
                    val eventRows = events.optJSONArray("events").objects()
                    if (eventRows.any { it.optString("kind") == "entry.removed" }) {
                        state = state.copy(snapshot = null)
                    }
                    if (eventRows.isNotEmpty() || state.snapshot?.isBusy == true || (state.snapshot?.subagents?.isNotEmpty() == true && System.currentTimeMillis() - lastChildSnapshot > 3000)) loadSnapshot(selected)
                }
                if (state.selectedThreadId != null && System.currentTimeMillis() - lastCommandsRefresh >= 5000) loadCommands(state.selectedThreadId!!)
                if (generation != connectionGeneration) return
                state = state.copy(live = true, status = "Connected to Zed", issue = "")
            } catch (error: Exception) {
                if (generation != connectionGeneration) return
                if (error.message?.contains("no longer exposed") == true) {
                    state = state.copy(selectedThreadId = null, snapshot = null, commands = emptyList(), issue = error.message.orEmpty())
                    runCatching { loadThreads() }
                } else if (error.message?.contains("event history changed") == true && state.selectedThreadId != null) {
                    state = state.copy(snapshot = null)
                    runCatching { loadSnapshot(state.selectedThreadId!!) }
                } else state = state.copy(live = false, status = "Reconnecting", issue = error.message.orEmpty())
            }
            delay(if (state.live) if (eventStreamLive) 10_000 else 1_000 else 3_000)
        }
    }

    private suspend fun loadThreads() {
        val rpcClient = client ?: return
        val scope = listOf(connectionGeneration, state.profile?.gatewayId, state.targetId, state.instanceId, state.epoch)
        val result = rpcClient.rpc("thread.list")
        if (scope != listOf(connectionGeneration, state.profile?.gatewayId, state.targetId, state.instanceId, state.epoch)) return
        checkIdentity(result)
        val threads = result.optJSONArray("threads").objects().mapNotNull { row ->
            val id = row.optString("thread_id"); if (id.isBlank()) null else NativeThread(
                id, row.optString("title", "Untitled Agent thread"), row.optString("status", "Unknown"), row.optIntOrNull("current_turn_id"),
                row.optJSONObject("agent")?.optString("name")?.takeIf { it.isNotBlank() } ?: "Zed Agent",
                row.optJSONObject("retry_status") != null, row.optBoolean("had_error") || row.optJSONObject("agent_error") != null)
        }.map { thread ->
            if (scope != listOf(connectionGeneration, state.profile?.gatewayId, state.targetId, state.instanceId, state.epoch)) return
            if (state.selectedThreadId != null) thread else {
                val cacheKey = (scope + thread.id).joinToString("\n")
                val cached = sessionCounts[cacheKey]
                if (cached != null && System.currentTimeMillis() - cached.first < 5000 && cached.second.currentTurnId == thread.currentTurnId && cached.second.status == thread.status) {
                    thread.copy(approvalCount = cached.second.approvalCount, inputCount = cached.second.inputCount)
                } else {
                    val params = JSONObject().put("thread_id", thread.id).put("instance_id", state.instanceId).put("epoch", state.epoch)
                    val approvals = if ("thread.approvals" in state.capabilities) rpcClient.rpc("thread.approvals", params).optJSONArray("approvals")?.length() else null
                    if (scope != listOf(connectionGeneration, state.profile?.gatewayId, state.targetId, state.instanceId, state.epoch)) return
                    val inputs = if ("thread.elicitations" in state.capabilities) rpcClient.rpc("thread.elicitations", params).optJSONArray("elicitations").objects().count { it.optString("status") == "pending" } else null
                    thread.copy(approvalCount = approvals, inputCount = inputs).also { sessionCounts[cacheKey] = System.currentTimeMillis() to it }
                }
            }
        }
        if (scope != listOf(connectionGeneration, state.profile?.gatewayId, state.targetId, state.instanceId, state.epoch)) return
        val changed = threads.filter { thread -> state.threads.any { it.id == thread.id && it != thread } && thread.id != state.selectedThreadId }.map { it.id }.toSet()
        val selected = state.selectedThreadId?.takeIf { id -> threads.any { it.id == id } }
        state = state.copy(threads = threads, selectedThreadId = selected,
            pinnedThreads = preferences.getStringSet(sessionPinsKey(), emptySet()).orEmpty().toSet(),
            updatedThreads = (state.updatedThreads + changed) - setOfNotNull(selected),
            snapshot = if (selected == null) null else state.snapshot)
    }

    private val sessionCounts = mutableMapOf<String, Pair<Long, NativeThread>>()
    private fun sessionPinsKey() = "sessionPins." + listOf(state.profile?.gatewayId, state.targetId).joinToString("\n")
    fun toggleSessionPin(id: String) {
        val pins = if (id in state.pinnedThreads) state.pinnedThreads - id else state.pinnedThreads + id
        preferences.edit().putStringSet(sessionPinsKey(), pins).apply()
        state = state.copy(pinnedThreads = pins)
    }

    private suspend fun loadSnapshot(id: String) {
        val transport = client ?: return
        val scope = listOf(connectionGeneration, state.profile?.gatewayId, state.targetId, state.instanceId, state.epoch, id)
        fun current() = scope == listOf(connectionGeneration, state.profile?.gatewayId, state.targetId, state.instanceId, state.epoch, state.selectedThreadId)
        if (!current()) return
        val params = JSONObject().put("thread_id", id)
        if (state.snapshot?.threadId == id) params.put("tail_entry_count", 16)
        val result = transport.rpc("thread.snapshot", params)
        if (!current()) return
        checkIdentity(result)
        if (state.selectedThreadId != id) return
        val pageEntries = result.optJSONArray("entries_markdown").strings()
        val pageStart = result.optInt("entry_start_index", 0)
        val pageEnd = result.optInt("entry_end_index", pageStart + pageEntries.size)
        val totalEntries = result.optInt("total_entries", pageEnd)
        if (pageStart < 0 || pageEnd != pageStart + pageEntries.size || totalEntries < pageEnd) {
            throw GatewayException("Invalid transcript page from desktop Zed.")
        }
        val old = state.snapshot
        val canMerge = old?.instanceId == state.instanceId && old?.epoch == state.epoch && old?.threadId == id && pageStart >= old.entryStartIndex
            && pageStart <= old.entryStartIndex + old.entries.size
        val mergedStart = if (canMerge) old!!.entryStartIndex else pageStart
        val mergedEntries = if (canMerge) old!!.entries.take(pageStart - old.entryStartIndex) + pageEntries else pageEntries
        val approvalRows = result.optJSONArray("pending_approvals").objects() +
            result.optJSONArray("subagents").objects().flatMap { child ->
                child.optJSONArray("pending_approvals").objects()
            }
        val approvals = approvalRows.mapNotNull { row ->
            val approvalId = row.optString("approval_id"); if (approvalId.isBlank()) null else NativeApproval(
                approvalId, row.optIntOrNull("turn_id"), row.optString("tool_name", "Zed tool"),
                row.optString("display", "Permission requested"), row.opt("raw_input")?.takeUnless { it == JSONObject.NULL }?.toString(),
                row.optBoolean("details_truncated", true), row.optString("subagent_id").takeIf { it.isNotBlank() },
                row.optString("authorization_kind", "permission_grant"),
                row.optJSONObject("permission_options")?.optJSONArray("decisions").objects().mapNotNull { decision ->
                    val optionId = decision.optString("option_id")
                    if (optionId.isBlank()) null else NativeApprovalDecision(
                        optionId, decision.optString("label", "Choose"), decision.optString("option_kind", "unknown"),
                        decision.optIntOrNull("choice_index"),
                        decision.optJSONArray("selected_pattern_indices").integers(),
                        if (decision.isNull("action")) null else decision.optString("action").takeIf { it.isNotBlank() })
                })
        }
        state = state.copy(snapshot = ThreadSnapshot(
            id, result.optString("title").takeIf { it.isNotBlank() && it != "null" }
                ?: state.snapshot?.takeIf { it.threadId == id }?.title ?: state.threads.firstOrNull { it.id == id }?.title ?: "Untitled Agent thread", result.optString("status", "Unknown"),
            result.optIntOrNull("current_turn_id"), state.instanceId.orEmpty(), state.epoch.orEmpty(),
            result.optInt("last_sequence"), mergedEntries,
            mergedStart, totalEntries, mergedStart > 0,
            result.optJSONArray("activity_entries_markdown").strings(), result.optBoolean("truncated"),
            result.optBoolean("activity_truncated"), approvals,
            result.optJSONArray("rewind_points").objects().mapNotNull { row ->
                val clientId = row.optString("client_user_message_id")
                if (clientId.isBlank()) null else NativeRewindPoint(clientId, row.optInt("entry_index"), row.optInt("entries_removed"))
            }, result.optJSONArray("subagents").objects().mapNotNull { row ->
                val sessionId = row.optString("session_id")
                if (sessionId.isBlank()) null else NativeSubagent(sessionId, row.optString("title", row.optString("label", "Parallel agent")),
                    row.optString("status", "Unknown"), row.optIntOrNull("current_turn_id"), row.optJSONArray("entries_markdown").strings(), row.optInt("entry_start_index"), row.optInt("total_entries"), row.optBoolean("entries_truncated"))
            }.associateBy { it.id }.values.map { child ->
                val history = childHistory[child.id]
                val merged = if (history != null && history.scope == childScope() && history.start <= child.entryStartIndex && history.end >= child.entryStartIndex && history.end <= child.totalEntries)
                    child.copy(entries = history.entries.take(child.entryStartIndex - history.start) + child.entries, entryStartIndex = history.start, entriesTruncated = history.start > 0)
                else child
                childHistory[child.id] = ChildHistory(childScope(), merged.entryStartIndex, merged.entryStartIndex + merged.entries.size, merged.entries)
                merged
            }))
        lastChildSnapshot = System.currentTimeMillis()
        approvalNotifications.update(state)
        loadAuxiliaryState(id)
    }

    private suspend fun loadAuxiliaryState(id: String) {
        if (System.currentTimeMillis() - lastCommandsRefresh >= 5000) loadCommands(id)
        val activeClient = client ?: return
        val scope = listOf(connectionGeneration, state.profile?.gatewayId, state.targetId, state.instanceId, state.epoch, id)
        fun current() = scope == listOf(connectionGeneration, state.profile?.gatewayId, state.targetId, state.instanceId, state.epoch, state.selectedThreadId)
        if (!current()) return
        val base = JSONObject().put("instance_id", state.instanceId).put("epoch", state.epoch).put("thread_id", id)
        var elicitations = emptyList<NativeElicitation>()
        var queued = emptyList<NativeQueueEntry>()
        var review: NativeEditReview? = null
        var settings: NativeThreadSettings? = null
        if ("thread.elicitations" in state.capabilities) {
            val result = activeClient.rpc("thread.elicitations", JSONObject(base.toString()))
            if (!current()) return
            elicitations = result.optJSONArray("elicitations").objects().mapNotNull { row ->
                if (row.optString("status") != "pending") return@mapNotNull null
                val request = row.optJSONObject("request") ?: return@mapNotNull null
                val schema = request.optJSONObject("requestedSchema")
                val required = schema?.optJSONArray("required").strings().toSet()
                val properties = schema?.optJSONObject("properties")
                val fields = properties?.keys()?.asSequence()?.mapNotNull { name ->
                    val field = properties.optJSONObject(name) ?: return@mapNotNull null
                    val items = field.optJSONObject("items")
                    val choices = listOf(
                        field.optJSONArray("enum").strings(),
                        field.optJSONArray("oneOf").objects().mapNotNull { it.opt("const")?.toString() },
                        (items?.optJSONArray("enum")).strings(),
                        (items?.optJSONArray("oneOf")).objects().mapNotNull { it.opt("const")?.toString() },
                    ).flatten()
                    NativeElicitationField(name, field.optString("title", name), field.optString("type", "string"),
                        name in required, choices,
                        field.opt("default")?.takeIf { it != JSONObject.NULL && it !is JSONArray }?.toString(),
                        field.optJSONArray("default")?.strings(),
                        field.opt("minimum")?.let { (it as? Number)?.toDouble() }, field.opt("maximum")?.let { (it as? Number)?.toDouble() },
                        field.opt("minLength")?.let { (it as? Number)?.toInt() }, field.opt("maxLength")?.let { (it as? Number)?.toInt() })
                }?.sortedBy { it.id }?.toList().orEmpty()
                NativeElicitation(row.optString("elicitation_id"), request.optString("message", "Agent needs more information"),
                    request.optString("url").takeIf { it.isNotBlank() }, fields)
            }
        }
        if ("thread.queue" in state.capabilities) {
            val result = activeClient.rpc("thread.queue", JSONObject(base.toString()))
            if (!current()) return
            queued = result.optJSONArray("entries").objects().map { row ->
                NativeQueueEntry(row.optInt("index"), row.optString("preview", "Attachment"), row.optBoolean("steer"))
            }
        }
        if ("thread.edit_review" in state.capabilities) {
            val result = activeClient.rpc("thread.edit_review", JSONObject(base.toString()))
            if (!current()) return
            if (result.optBoolean("pending")) review = NativeEditReview(result.optInt("changed_files"), result.optInt("lines_added"), result.optInt("lines_removed"))
        }
        if ("thread.settings" in state.capabilities) {
            val result = activeClient.rpc("thread.settings", JSONObject(base.toString()))
            if (!current()) return
            val selected = result.optJSONObject("model")
            val usage = result.optJSONObject("context_usage")
            settings = NativeThreadSettings(selected?.optString("id"), selected?.optString("provider_id"),
                result.optJSONArray("models").objects().mapNotNull { row ->
                    val modelId = row.optString("id"); val providerId = row.optString("provider_id")
                    if (modelId.isBlank() || providerId.isBlank()) null else NativeModelOption("$providerId\n$modelId", modelId, providerId, row.optString("name", modelId))
                }, usage?.optInt("used_tokens"), usage?.optInt("max_tokens"),
                result.optString("profile_id").takeIf { it.isNotBlank() && it != "null" }, result.optJSONArray("profiles").objects().mapNotNull { row ->
                    val profileId = row.optString("id"); if (profileId.isBlank()) null else NativeAgentProfile(profileId, row.optString("name", profileId))
                }, if (result.isNull("thinking_enabled")) null else result.optBoolean("thinking_enabled"), result.optBoolean("thinking_supported"), result.optBoolean("thinking_can_disable"))
        }
        if (current()) state = state.copy(elicitations = elicitations, queuedMessages = queued, editReview = review, threadSettings = settings)
    }

    fun respondElicitation(item: NativeElicitation, action: String, content: JSONObject = JSONObject()) = viewModelScope.launch {
        val threadId = state.selectedThreadId ?: return@launch
        val scope = listOf(state.profile?.gatewayId, state.targetId, state.instanceId, state.epoch, threadId)
        val key = (scope + item.id).joinToString("\n")
        if (!state.live || "elicitation.respond" !in state.capabilities || key in state.resolvingElicitations || state.elicitations.none { it.id == item.id }) return@launch
        val rpcClient = client ?: return@launch
        state = state.copy(resolvingElicitations = state.resolvingElicitations + key)
        fun current() = scope == listOf(state.profile?.gatewayId, state.targetId, state.instanceId, state.epoch, state.selectedThreadId)
        try {
            val result = rpcClient.rpc("elicitation.respond", JSONObject().put("instance_id", state.instanceId).put("epoch", state.epoch)
                .put("thread_id", threadId).put("elicitation_id", item.id).put("action", action).put("content", content))
            if (current()) {
                require(result.optString("outcome") == "resolved") { "Zed did not confirm this response." }
                loadAuxiliaryState(threadId)
            }
        } catch (error: Exception) { if (current()) state = state.copy(issue = error.message.orEmpty()) }
        finally { state = state.copy(resolvingElicitations = state.resolvingElicitations - key) }
    }

    fun clearQueue() = viewModelScope.launch {
        val threadId = state.selectedThreadId ?: return@launch
        try { client?.rpc("thread.queue.clear", JSONObject().put("instance_id", state.instanceId).put("epoch", state.epoch).put("thread_id", threadId)); loadAuxiliaryState(threadId) }
        catch (error: Exception) { state = state.copy(issue = error.message.orEmpty()) }
    }

    fun resolveEditReview(action: String) = viewModelScope.launch {
        val threadId = state.selectedThreadId ?: return@launch
        try { client?.rpc("thread.edit_review.respond", JSONObject().put("instance_id", state.instanceId).put("epoch", state.epoch).put("thread_id", threadId).put("action", action).put("expected_last_sequence", state.snapshot?.lastSequence ?: 0)); loadAuxiliaryState(threadId) }
        catch (error: Exception) { state = state.copy(issue = error.message.orEmpty()) }
    }

    fun rewind(point: NativeRewindPoint) = viewModelScope.launch {
        val threadId = state.selectedThreadId ?: return@launch
        try {
            client?.rpc("thread.rewind", JSONObject().put("instance_id", state.instanceId).put("epoch", state.epoch)
                .put("thread_id", threadId).put("client_user_message_id", point.id)
                .put("expected_last_sequence", state.snapshot?.lastSequence ?: 0))
            state = state.copy(snapshot = null)
            loadSnapshot(threadId)
        } catch (error: Exception) { state = state.copy(issue = error.message.orEmpty()) }
    }

    private data class ChildHistory(val scope: List<Any?>, val start: Int, val end: Int, val entries: List<String>)
    private var lastChildSnapshot = 0L
    private val childHistory = mutableMapOf<String, ChildHistory>()
    var loadingChildHistory by mutableStateOf(false)
        private set
    private fun childScope(): List<Any?> = listOf(connectionGeneration, state.profile?.gatewayId, state.targetId, state.instanceId, state.epoch, state.selectedThreadId)

    fun loadEarlierSubagent(childId: String) = viewModelScope.launch {
        val child = state.snapshot?.subagents?.firstOrNull { it.id == childId } ?: return@launch
        val threadId = state.selectedThreadId ?: return@launch
        val activeClient = client ?: return@launch
        if (loadingChildHistory || child.entryStartIndex <= 0) return@launch
        val scope = childScope(); loadingChildHistory = true
        try {
            val result = activeClient.rpc("thread.history", JSONObject().put("instance_id", state.instanceId).put("epoch", state.epoch)
                .put("thread_id", threadId).put("subagent_id", childId).put("before_entry_index", child.entryStartIndex))
            if (scope != childScope() || result.optString("thread_id") != threadId || result.optString("subagent_id") != childId) return@launch
            val start = result.optInt("entry_start_index", -1); val end = result.optInt("entry_end_index", -1)
            val entries = result.optJSONArray("entries_markdown").strings()
            if (start < 0 || end != child.entryStartIndex || start + entries.size != end) return@launch
            childHistory[childId] = ChildHistory(scope, start, child.entryStartIndex + child.entries.size, entries + child.entries)
            loadSnapshot(threadId)
        } catch (error: Exception) { if (scope == childScope()) state = state.copy(issue = error.message.orEmpty()) }
        finally { loadingChildHistory = false }
    }

    fun cancelSubagent(subagent: NativeSubagent) = viewModelScope.launch {
        val threadId = state.selectedThreadId ?: return@launch
        val turnId = subagent.currentTurnId ?: return@launch
        try { client?.rpc("subagent.cancel", JSONObject().put("instance_id", state.instanceId).put("epoch", state.epoch)
            .put("thread_id", threadId).put("subagent_id", subagent.id).put("turn_id", turnId)); loadSnapshot(threadId) }
        catch (error: Exception) { state = state.copy(issue = error.message.orEmpty()) }
    }

    fun selectModel(option: NativeModelOption) = updateAgentSettings(modelOption = option)

    fun updateAgentSettings(modelOption: NativeModelOption? = null, profileId: String? = null, thinking: Boolean? = null) = viewModelScope.launch {
        val threadId = state.selectedThreadId ?: return@launch
        val frozenClient = client ?: return@launch
        if (!state.live || state.snapshot?.threadId != threadId || state.snapshot?.status != "Idle" || state.updatingModel ||
            "thread.settings.update" !in state.capabilities) return@launch
        val settings = state.threadSettings ?: return@launch
        if (modelOption != null && modelOption !in settings.models) return@launch
        if (profileId != null && settings.profiles.none { it.id == profileId }) return@launch
        if (thinking != null && (!settings.thinkingSupported || (!thinking && !settings.thinkingCanDisable))) return@launch
        val scope = listOf(state.profile?.gatewayId, state.targetId, state.instanceId, state.epoch, threadId)
        fun current() = scope == listOf(state.profile?.gatewayId, state.targetId, state.instanceId, state.epoch, state.selectedThreadId)
        state = state.copy(updatingModel = true)
        try {
            frozenClient.rpc("thread.settings.update", JSONObject().put("instance_id", scope[2]).put("epoch", scope[3])
                .put("thread_id", threadId).apply {
                    modelOption?.let { put("provider_id", it.providerId); put("model_id", it.modelId) }
                    profileId?.let { put("profile_id", it) }; thinking?.let { put("thinking_enabled", it) }
                })
            if (current()) loadAuxiliaryState(threadId)
        } catch (error: Exception) { if (current()) state = state.copy(issue = error.message.orEmpty()) }
        finally { state = state.copy(updatingModel = false) }
    }

    fun loadProjectContext() = viewModelScope.launch {
        val threadId = state.selectedThreadId ?: return@launch
        val scope = listOf(state.profile?.gatewayId, state.targetId, state.instanceId, state.epoch, threadId)
        fun current() = scope == listOf(state.profile?.gatewayId, state.targetId, state.instanceId, state.epoch, state.selectedThreadId)
        try {
            val info = client!!.rpc("instance.info")
            if (!current()) return@launch
            checkIdentity(info)
            state = state.copy(capabilities = info.optJSONArray("capabilities").strings().toSet())
            val base = JSONObject().put("instance_id", state.instanceId).put("epoch", state.epoch).put("thread_id", threadId)
            var files = state.projectFiles; var entries = state.changes; var revision = state.changesRevision
            var terminals = emptyList<NativeTerminal>(); var configuredTasks = state.configuredTasks; var debuggerCatalog = state.debuggerCatalog; var debuggerSessions = state.debuggerSessions
            if ("project.files" in state.capabilities) {
                val result = client!!.rpc("project.files", JSONObject(base.toString()))
                if (!current()) return@launch
                files = result.optJSONArray("entries").objects().mapNotNull { row ->
                    val path = row.optString("path"); if (path.isBlank()) null else NativeProjectFile(path, row.optString("kind", "file"), row.optIntOrNull("size")) }
                state = state.copy(projectFilesTruncated = result.optBoolean("truncated"))
            }
            if ("changes.snapshot" in state.capabilities) {
                val result = client!!.rpc("changes.snapshot", JSONObject(base.toString()))
                revision = result.optJSONObject("repository")?.optString("revision")
                entries = result.optJSONArray("entries").objects().mapNotNull { row -> val path = row.optString("path"); if (path.isBlank()) null else NativeChange(path, row.optString("status", "changed"), row.optString("staging", "unstaged")) }
            }
            if ("terminal.list" in state.capabilities) {
                terminals = client!!.rpc("terminal.list", JSONObject().put("instance_id", state.instanceId).put("epoch", state.epoch))
                    .optJSONArray("terminals").objects().mapNotNull(::decodeTerminal)
            }
            configuredTasks = if ("task.catalog" in state.capabilities) {
                client!!.rpc("task.catalog", JSONObject().put("instance_id", state.instanceId).put("epoch", state.epoch))
                    .optJSONArray("tasks").objects().mapNotNull { row ->
                        val id = row.optString("task_id"); val label = row.optString("label")
                        if (id.isBlank() || label.isBlank()) null else NativeConfiguredTask(id, label, row.optString("source", "project"))
                    }
            } else emptyList()
            debuggerCatalog = if ("debugger.catalog" in state.capabilities) {
                client!!.rpc("debugger.catalog", JSONObject().put("instance_id", state.instanceId).put("epoch", state.epoch))
                    .optJSONArray("scenarios").objects().mapNotNull { row ->
                        val id = row.optString("scenario_id"); val label = row.optString("label")
                        if (id.isBlank() || label.isBlank()) null else NativeDebugScenario(id, label, row.optString("adapter", "DAP"), row.optString("source", "project"))
                    }
            } else emptyList()
            debuggerSessions = if ("debugger.snapshot" in state.capabilities) {
                client!!.rpc("debugger.snapshot", JSONObject().put("instance_id", state.instanceId).put("epoch", state.epoch))
                    .optJSONArray("sessions").objects().mapNotNull(::decodeDebuggerSession)
            } else emptyList()
            if (!current()) return@launch
            state = state.copy(projectFiles = files, changes = entries, changesRevision = revision, terminals = terminals,
                terminalSnapshot = state.terminalSnapshot?.takeIf { snapshot -> terminals.any { it.id == snapshot.terminal.id } },
                configuredTasks = configuredTasks, debuggerCatalog = debuggerCatalog, debuggerSessions = debuggerSessions)
            if (state.terminalSnapshot == null) {
                val remembered = preferences.getString(terminalRecoveryKey(), null)
                terminals.firstOrNull { it.id == remembered }?.let { loadTerminal(it) }
            }
        } catch (error: Exception) { if (current()) state = state.copy(issue = error.message.orEmpty()) }
    }
    suspend fun transferClipboard(text: String? = null): String? {
        val method = if (text == null) "clipboard.read" else "clipboard.write"
        val transport = client ?: return null
        val scope = listOf(state.profile?.gatewayId, state.targetId, state.instanceId, state.epoch, state.selectedThreadId)
        if (method !in state.capabilities || state.selectedThreadId == null) { state = state.copy(issue = "Enable Remote Clipboard in desktop ZedLink settings."); return null }
        if (text != null && (text.toByteArray().size > 65536 || text.contains('\u0000'))) { state = state.copy(issue = "Clipboard exceeds 64 KiB or contains a null character."); return null }
        return try {
            val params = JSONObject().put("instance_id", state.instanceId).put("epoch", state.epoch).put("thread_id", state.selectedThreadId)
            if (text != null) params.put("text", text)
            val result = transport.rpc(method, params)
            if (transport !== client || scope != listOf(state.profile?.gatewayId, state.targetId, state.instanceId, state.epoch, state.selectedThreadId)) return null
            if (text != null) text else result.getString("text").also { require(it.toByteArray().size <= 65536) }
        } catch (error: Exception) { state = state.copy(issue = error.message.orEmpty()); null }
    }
    private fun terminalRecoveryKey() = "terminal.${state.profile?.gatewayId}.${state.targetId}.${state.instanceId}.${state.epoch}"
    private var requestedTerminalId: String? = null
    fun loadTerminal(terminal: NativeTerminal, refresh: Boolean = false): Job = viewModelScope.launch {
        if (refresh && requestedTerminalId != terminal.id) return@launch
        if (!refresh) requestedTerminalId = terminal.id
        val transport = client ?: return@launch
        val recoveryKey = terminalRecoveryKey()
        try {
        val result = transport.rpc("terminal.snapshot", JSONObject().put("instance_id", state.instanceId).put("epoch", state.epoch).put("terminal_id", terminal.id))
        if (requestedTerminalId != terminal.id || transport !== client || recoveryKey != terminalRecoveryKey() || state.terminals.none { it.id == terminal.id }) return@launch
        val decoded = result.optJSONObject("terminal")?.let(::decodeTerminal) ?: throw GatewayException("Zed returned an invalid terminal snapshot.")
        val runs = result.optJSONArray("styled_runs") ?: JSONArray()
        val styles = (0 until minOf(runs.length(), 2048)).mapNotNull { index ->
            val row = runs.optJSONObject(index) ?: return@mapNotNull null
            NativeTerminalRun(row.optString("text"), row.optString("foreground"), row.optString("background"), row.optBoolean("bold"), row.optBoolean("italic"), row.optBoolean("underline"), row.optBoolean("dim"))
        }
        preferences.edit().putString(recoveryKey, terminal.id).apply()
        state = state.copy(terminalSnapshot = NativeTerminalSnapshot(decoded, result.optString("content"), result.optBoolean("truncated"), styles))
    } catch (error: Exception) { state = state.copy(issue = error.message.orEmpty()) } }
    private val terminalInputMutex = Mutex()
    private var terminalInputGeneration = 0
    fun sendTerminalInput(input: String, appendReturn: Boolean = true): kotlinx.coroutines.Job {
        val terminal = state.terminalSnapshot?.terminal
        val instance = state.instanceId
        val epoch = state.epoch
        val transport = client
        val generation = terminalInputGeneration
        return viewModelScope.launch {
            terminalInputMutex.withLock {
                if (generation != terminalInputGeneration || terminal == null || transport == null || input.isEmpty() || "terminal.input" !in state.capabilities ||
                    instance != state.instanceId || epoch != state.epoch || transport !== client || terminal.id != state.terminalSnapshot?.terminal?.id) return@withLock
                try {
                    transport.rpc("terminal.input", JSONObject().put("instance_id", instance).put("epoch", epoch)
                        .put("terminal_id", terminal.id).put("input", if (appendReturn) "$input\n" else input), UUID.randomUUID().toString())
                    loadTerminal(terminal, refresh = true)
                } catch (error: Exception) { terminalInputGeneration += 1; state = state.copy(issue = "Terminal input failed. Check the terminal before retrying: ${error.message.orEmpty()}") }
            }
        }
    }
    fun stopTerminalTask() = viewModelScope.launch {
        val terminal = state.terminalSnapshot?.terminal ?: return@launch
        if ("task.stop" !in state.capabilities) return@launch
        try {
            client!!.rpc("task.stop", JSONObject().put("instance_id", state.instanceId).put("epoch", state.epoch)
                .put("terminal_id", terminal.id), UUID.randomUUID().toString())
            delay(150); loadProjectContext(); loadTerminal(terminal, refresh = true)
        } catch (error: Exception) { state = state.copy(issue = error.message.orEmpty()) }
    }
    private fun decodeTerminal(row: JSONObject): NativeTerminal? {
        val id = row.optString("terminal_id"); if (id.isBlank()) return null
        val task = row.optJSONObject("task")
        return NativeTerminal(id, row.optString("title", "Terminal"), row.optString("working_directory").takeIf { it.isNotBlank() },
            task?.optString("label")?.takeIf { it.isNotBlank() }, task?.optJSONObject("status")?.optString("state")?.takeIf { it.isNotBlank() })
    }
    fun runConfiguredTask(task: NativeConfiguredTask) = viewModelScope.launch {
        if ("task.run" !in state.capabilities) return@launch
        try {
            client!!.rpc("task.run", JSONObject().put("instance_id", state.instanceId).put("epoch", state.epoch)
                .put("task_id", task.id), UUID.randomUUID().toString())
            delay(250); loadProjectContext()
        } catch (error: Exception) { state = state.copy(issue = error.message.orEmpty()) }
    }
    fun controlDebugger(session: NativeDebuggerSession, action: String, thread: NativeDebuggerThread? = null) = viewModelScope.launch {
        if ("debugger.control" !in state.capabilities) return@launch
        val params = JSONObject().put("instance_id", state.instanceId).put("epoch", state.epoch)
            .put("session_id", session.id).put("action", action)
        if (thread != null) params.put("thread_id", thread.id)
        try {
            client!!.rpc("debugger.control", params, UUID.randomUUID().toString())
            delay(180); loadProjectContext()
        } catch (error: Exception) { state = state.copy(issue = error.message.orEmpty()) }
    }
    fun launchDebugger(scenario: NativeDebugScenario) = viewModelScope.launch {
        if ("debugger.launch" !in state.capabilities) return@launch
        try {
            client!!.rpc("debugger.launch", JSONObject().put("instance_id", state.instanceId).put("epoch", state.epoch)
                .put("scenario_id", scenario.id), UUID.randomUUID().toString())
            delay(350); loadProjectContext()
        } catch (error: Exception) { state = state.copy(issue = error.message.orEmpty()) }
    }
    private fun decodeDebuggerSession(row: JSONObject): NativeDebuggerSession? {
        val id = row.optString("session_id"); if (id.isBlank()) return null
        val capabilities = row.optJSONObject("capabilities")
        val threads = row.optJSONArray("threads").objects().mapNotNull { thread ->
            if (!thread.has("thread_id")) null else NativeDebuggerThread(thread.optLong("thread_id"),
                thread.optString("name", "Thread ${thread.optLong("thread_id")}"), thread.optString("status", "unknown"))
        }
        return NativeDebuggerSession(id, row.optString("label", "Debugger"), row.optString("adapter", "DAP"),
            row.optBoolean("terminated"), capabilities?.optBoolean("restart") ?: false,
            capabilities?.optBoolean("step_back") ?: false, threads)
    }
    fun loadDirectory(path: String) = viewModelScope.launch {
        state = state.copy(projectFolderEntries = null, projectFolderTruncated = false)
        val request = ++directoryRequest
        if ("project.directory" !in state.capabilities) return@launch
        val transport = client ?: return@launch
        val scope = listOf(state.profile?.gatewayId, state.targetId, state.instanceId, state.epoch, state.selectedThreadId)
        try {
            val result = transport.rpc("project.directory", JSONObject().put("instance_id", scope[2]).put("epoch", scope[3]).put("thread_id", scope[4]).put("path", path))
            if (request != directoryRequest || scope != listOf(state.profile?.gatewayId, state.targetId, state.instanceId, state.epoch, state.selectedThreadId)) return@launch
            if (result.optString("directory") != path || !result.has("entries")) throw GatewayException("Invalid directory listing")
            val files = result.optJSONArray("entries").objects().mapNotNull { row ->
                val name = row.optString("path"); if (name.isBlank()) null else NativeProjectFile(name, row.optString("kind", "file"), row.optIntOrNull("size")) }
            state = state.copy(projectFolderEntries = files, projectFolderTruncated = result.optBoolean("truncated"))
        } catch (error: Exception) {
            if (request == directoryRequest && scope == listOf(state.profile?.gatewayId, state.targetId, state.instanceId, state.epoch, state.selectedThreadId)) state = state.copy(issue = error.message.orEmpty())
        }
    }
    fun previewFile(path: String) = viewModelScope.launch {
        val transport = client ?: return@launch
        val scope = listOf(state.profile?.gatewayId, state.targetId, state.instanceId, state.epoch, state.selectedThreadId)
        val request = ++previewRequest
        state = state.copy(previewTitle = path, previewContent = "", previewReadable = false, previewLoading = true, previewTruncated = false)
        fun current() = request == previewRequest && scope == listOf(state.profile?.gatewayId, state.targetId, state.instanceId, state.epoch, state.selectedThreadId)
        try {
            val result = transport.rpc("project.file", JSONObject().put("instance_id", scope[2]).put("epoch", scope[3]).put("thread_id", scope[4]).put("path", path))
            if (!current()) return@launch
            if (result.optString("path") != path || !result.has("content")) throw GatewayException("Invalid file preview")
            state = state.copy(previewContent = result.getString("content"), previewReadable = true, previewLoading = false, previewTruncated = result.optBoolean("truncated"))
        } catch (error: Exception) {
            if (current()) state = state.copy(previewLoading = false, previewContent = "File unavailable: ${error.message.orEmpty()}")
        }
    }
    fun toggleContextPath(path: String) { state = state.copy(contextPaths = state.contextPaths.toMutableSet().apply { if (!add(path)) remove(path) }) }
    fun loadDiff() = viewModelScope.launch { try {
        val result = client!!.rpc("changes.diff", JSONObject().put("instance_id", state.instanceId).put("epoch", state.epoch).put("thread_id", state.selectedThreadId).put("revision", state.changesRevision))
        state = state.copy(previewTitle = "Working tree diff", previewContent = result.optString("diff", "Diff is still loading."))
    } catch (error: Exception) { state = state.copy(issue = error.message.orEmpty()) } }
    fun mutateChange(change: NativeChange) = viewModelScope.launch { try {
        val method = if (change.staging == "staged") "changes.unstage" else "changes.stage"
        client!!.rpc(method, JSONObject().put("instance_id", state.instanceId).put("epoch", state.epoch).put("thread_id", state.selectedThreadId)
            .put("revision", state.changesRevision).put("paths", JSONArray(listOf(change.id))), UUID.randomUUID().toString())
        loadProjectContext()
    } catch (error: Exception) { state = state.copy(issue = error.message.orEmpty()) } }

    fun refreshCommands() = viewModelScope.launch {
        val id = state.selectedThreadId ?: return@launch
        val scope = listOf(connectionGeneration, state.profile?.gatewayId, state.targetId, state.instanceId, state.epoch, id)
        runCatching { loadCommands(id) }.onFailure {
            if (scope == listOf(connectionGeneration, state.profile?.gatewayId, state.targetId, state.instanceId, state.epoch, state.selectedThreadId)) state = state.copy(issue = it.message.orEmpty())
        }
    }

    private suspend fun loadCommands(id: String) {
        if ("thread.commands" !in state.capabilities) return
        val scope = listOf(connectionGeneration, state.profile?.gatewayId, state.targetId, state.instanceId, state.epoch, id)
        val result = client!!.rpc("thread.commands", JSONObject().put("instance_id", state.instanceId)
            .put("epoch", state.epoch).put("thread_id", id))
        if (scope != listOf(connectionGeneration, state.profile?.gatewayId, state.targetId, state.instanceId, state.epoch, state.selectedThreadId)) return
        lastCommandsRefresh = System.currentTimeMillis()
        state = state.copy(commands = result.optJSONArray("commands").objects().mapNotNull { row ->
            val name = row.optString("name"); if (name.isBlank()) null else NativeCommand(name,
                row.optString("description", "Zed Agent command"), row.optString("category", "agent"),
                row.optBoolean("requires_argument"), row.optString("input_hint").takeIf { it.isNotBlank() && it != "null" },
                row.optString("execution", "prompt"), row.optString("confirmation").takeIf { it.isNotBlank() }, row.optString("warning").takeIf { it.isNotBlank() && it != "null" })
        }.sortedBy { it.name })
    }

    private fun checkIdentity(result: JSONObject) {
        if (result.optString("instance_id") != state.instanceId || result.optString("epoch") != state.epoch) {
            throw GatewayException("Desktop Zed restarted. Reconnect before sending.")
        }
    }

    fun handleApprovalNotification(data: Map<String, String>, action: String) = viewModelScope.launch {
        fun matches() = data["gateway"] == state.profile?.gatewayId && data["target"] == state.targetId &&
            data["instance"] == state.instanceId && data["epoch"] == state.epoch
        val thread = data["thread"] ?: return@launch
        if (!matches() || state.threads.none { it.id == thread }) {
            state = state.copy(issue = "This notification belongs to an older or different connection. Open the session to review current requests.")
            return@launch
        }
        selectThread(thread).join()
        if (!matches() || state.selectedThreadId != thread) return@launch
        if (action != "approve" && action != "deny") return@launch
        val approval = state.snapshot?.approvals?.firstOrNull { it.id == data["approval"] && it.turnId.toString() == data["turn"] && it.subagentId.orEmpty() == data["child"] }
        val kind = if (action == "approve") "allow_once" else "reject_once"
        val decision = approval?.decisions?.firstOrNull { it.optionId == data["option"] && it.optionKind == kind && it.choiceIndex == null && it.selectedPatternIndices.isEmpty() && it.action == null }
        if (approval == null || decision == null || approval.detailsTruncated || approval.authorizationKind != "permission_grant") {
            state = state.copy(issue = "This approval changed or was already resolved. Review the current session.")
            return@launch
        }
        respondApproval(approval, decision).join()
    }

    fun respondApproval(approval: NativeApproval, decision: NativeApprovalDecision) = viewModelScope.launch {
        val activeClient = client ?: return@launch
        val threadId = state.selectedThreadId ?: return@launch
        val turnId = approval.turnId ?: return@launch
        if ("approval.respond" !in state.capabilities) return@launch
        try {
            val params = JSONObject().put("instance_id", state.instanceId).put("epoch", state.epoch)
                .put("thread_id", threadId).put("turn_id", turnId)
                .put("approval_id", approval.id).put("option_id", decision.optionId)
            decision.choiceIndex?.let { params.put("choice_index", it) }
            if (decision.selectedPatternIndices.isNotEmpty()) {
                params.put("selected_pattern_indices", JSONArray(decision.selectedPatternIndices))
            }
            approval.subagentId?.let { params.put("subagent_id", it) }
            val result = activeClient.rpc("approval.respond", params)
            if (result.optString("outcome") != "resolved") throw GatewayException("Zed returned an invalid approval state.")
            state = state.copy(delivery = "Sent “${decision.displayLabel}” to desktop Zed.", issue = "")
            loadSnapshot(threadId)
        } catch (error: Exception) {
            state = state.copy(issue = error.message.orEmpty())
            runCatching { loadSnapshot(threadId) }
        }
    }

    private fun saveProfile(profile: ConnectionProfile): ConnectionProfile {
        val profiles = loadProfiles()
        val saved = ConnectionProfiles.profileForSave(profile, profiles)
        persistProfiles(profiles.filterNot { it.id == saved.id } + saved)
        return saved
    }

    private fun loadProfiles(): List<ConnectionProfile> {
        val saved = runCatching {
            preferences.getString("profiles", null)?.let(::JSONArray)?.objects()?.mapNotNull { row ->
                val endpoint = row.optString("endpoint")
                val gateway = row.optString("gateway_id")
                if (endpoint.isBlank() || gateway.isBlank()) null else ConnectionProfile(
                    row.optString("name", "Desktop"), endpoint, gateway,
                    row.optString("id").ifBlank { java.util.UUID.nameUUIDFromBytes("$gateway|$endpoint".toByteArray()).toString() }, row.optString("route", "Private HTTPS"))
            }
        }.getOrNull().orEmpty()
        if (saved.isNotEmpty()) return saved
        val endpoint = preferences.getString("endpoint", null) ?: return emptyList()
        val gateway = preferences.getString("gateway", null) ?: return emptyList()
        val migrated = listOf(ConnectionProfile(preferences.getString("name", "My Zed")!!, endpoint, gateway))
        persistProfiles(migrated)
        return migrated
    }

    private fun persistProfiles(profiles: List<ConnectionProfile>) {
        val rows = JSONArray()
        profiles.forEach { profile -> rows.put(JSONObject().put("name", profile.name)
            .put("endpoint", profile.endpoint).put("gateway_id", profile.gatewayId).put("id", profile.id).put("route", profile.route)) }
        preferences.edit().putString("profiles", rows.toString()).apply()
    }

    private fun loadProfile(profiles: List<ConnectionProfile>): ConnectionProfile? {
        val active = preferences.getString("active_gateway", null)
        return profiles.firstOrNull { it.id == preferences.getString("active_profile", null) }
            ?: profiles.firstOrNull { it.gatewayId == active } ?: profiles.firstOrNull()
    }
}

private fun JSONArray?.objects(): List<JSONObject> = if (this == null) emptyList() else (0 until length()).mapNotNull { optJSONObject(it) }
private fun JSONArray?.strings(): List<String> = if (this == null) emptyList() else (0 until length()).mapNotNull { optString(it).takeIf(String::isNotBlank) }
private fun JSONArray?.integers(): List<Int> = if (this == null) emptyList() else (0 until length()).mapNotNull { index ->
    if (isNull(index)) null else optInt(index)
}
private fun JSONObject.optIntOrNull(key: String): Int? = if (!has(key) || isNull(key)) null else optInt(key)
