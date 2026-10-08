package dev.zedlink.app

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

data class AppState(
    val profile: ConnectionProfile? = null,
    val profiles: List<ConnectionProfile> = emptyList(),
    val targets: List<ZedTarget> = emptyList(),
    val targetId: String? = null,
    val status: String = "Offline",
    val live: Boolean = false,
    val threads: List<NativeThread> = emptyList(),
    val selectedThreadId: String? = null,
    val snapshot: ThreadSnapshot? = null,
    val commands: List<NativeCommand> = emptyList(),
    val createAgents: List<AgentOption> = emptyList(),
    val creatingThread: Boolean = false,
    val capabilities: Set<String> = emptySet(),
    val instanceId: String? = null,
    val epoch: String? = null,
    val draft: String = "",
    val delivery: String = "",
    val issue: String = "",
    val sending: Boolean = false,
)

class ZedLinkViewModel(application: Application) : AndroidViewModel(application) {
    var state by mutableStateOf(AppState())
        private set
    private var client: GatewayClient? = null
    private var pollJob: Job? = null
    private var pendingId: String? = null
    private var pendingText: String? = null
    private val preferences = application.getSharedPreferences("zedlink-profile", 0)

    init {
        val saved = loadProfiles()
        val preferred = loadProfile(saved)
        state = state.copy(profile = preferred, profiles = saved)
        preferred?.let { profile ->
            if (TokenVault.read(application, profile.gatewayId) != null) connect()
        }
    }

    fun applyPairingLink(text: String): Pair<ConnectionProfile, String?> = GatewayClient.profileFromPairingLink(text)

    fun pair(profile: ConnectionProfile, code: String, deviceName: String) = viewModelScope.launch {
        state = state.copy(status = "Pairing…", issue = "")
        try {
            val pairingClient = GatewayClient(profile, null)
            val (_, token) = pairingClient.pair(code.trim(), deviceName.trim().ifBlank { "Android" })
            TokenVault.write(getApplication(), profile.gatewayId, token)
            saveProfile(profile)
            state = state.copy(profile = profile, profiles = loadProfiles())
            connect()
        } catch (error: Exception) {
            state = state.copy(status = "Offline", issue = error.message ?: "Pairing failed.")
        }
    }

    fun updateRoute(profile: ConnectionProfile) = viewModelScope.launch {
        state = state.copy(status = "Checking new address…", issue = "")
        try {
            val observed = GatewayClient(profile, null).gatewayId()
            if (!observed.equals(profile.gatewayId, ignoreCase = true)) {
                throw GatewayException("The new address belongs to a different gateway. No credential was sent.")
            }
            if (TokenVault.read(getApplication(), profile.gatewayId) == null) {
                throw GatewayException("The saved device credential is missing. Pair this device again once.")
            }
            saveProfile(profile)
            state = state.copy(profile = profile, profiles = loadProfiles())
            connect()
        } catch (error: Exception) {
            state = state.copy(status = "Offline", issue = error.message ?: "Address update failed.")
        }
    }

    fun connect() {
        val profile = state.profile ?: return
        val token = TokenVault.read(getApplication(), profile.gatewayId) ?: run {
            state = state.copy(status = "Pair this device", live = false); return
        }
        pollJob?.cancel()
        viewModelScope.launch {
            state = state.copy(status = "Connecting…", live = false, issue = "")
            try {
                val discovery = GatewayClient(profile, token)
                val registry = discovery.rpc("instance.list")
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
                client = next
                state = state.copy(
                    status = "Connected to Zed", live = true,
                    targets = targets, targetId = selectedTarget.id,
                    instanceId = info.getString("instance_id"), epoch = info.getString("epoch"),
                    capabilities = info.optJSONArray("capabilities").strings().toSet(), issue = "",
                )
                loadThreads()
                pollJob = viewModelScope.launch { poll() }
            } catch (error: Exception) {
                state = state.copy(status = "Zed unavailable", live = false, issue = error.message.orEmpty())
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
        val target = state.targets.firstOrNull { it.id == id && it.available } ?: return
        val profile = state.profile ?: return
        pollJob?.cancel(); client = null; pendingId = null; pendingText = null
        preferences.edit().putString("target.${profile.gatewayId}", target.id).apply()
        state = state.copy(targetId = target.id, threads = emptyList(), selectedThreadId = null,
            snapshot = null, commands = emptyList(), instanceId = null, epoch = null, live = false)
        connect()
    }

    fun connect(profile: ConnectionProfile) {
        if (state.profile?.gatewayId != profile.gatewayId) {
            pollJob?.cancel(); client = null; pendingId = null; pendingText = null
            state = state.copy(profile = profile, threads = emptyList(), selectedThreadId = null,
                snapshot = null, commands = emptyList(), capabilities = emptySet(), targets = emptyList(), targetId = null,
                instanceId = null, epoch = null, issue = "", delivery = "")
        }
        preferences.edit().putString("active_gateway", profile.gatewayId).apply()
        connect()
    }

    fun selectThread(id: String) = viewModelScope.launch {
        if (state.threads.none { it.id == id }) return@launch
        val draft = preferences.getString("draft.$id", "").orEmpty()
        state = state.copy(selectedThreadId = id, snapshot = null, commands = emptyList(), draft = draft, issue = "")
        runCatching { loadSnapshot(id); loadCommands(id) }
            .onFailure { state = state.copy(issue = it.message.orEmpty()) }
    }

    fun closeThread() { state = state.copy(selectedThreadId = null, snapshot = null, commands = emptyList()) }

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

    fun send() = viewModelScope.launch {
        val text = state.draft.trim()
        val threadId = state.selectedThreadId ?: return@launch
        val instance = state.instanceId ?: return@launch
        val epoch = state.epoch ?: return@launch
        val activeClient = client ?: return@launch
        if (text.isEmpty() || state.sending) return@launch
        pendingId = UUID.randomUUID().toString(); pendingText = text
        state = state.copy(sending = true, delivery = "Sending to native Zed…")
        try {
            val result = activeClient.rpc("thread.send", JSONObject()
                .put("instance_id", instance).put("epoch", epoch).put("thread_id", threadId).put("text", text), pendingId!!)
            pendingId = null; pendingText = null
            setDraft("")
            state = state.copy(sending = false, delivery = if (result.optString("outcome") == "queued")
                "Queued in desktop Zed." else "Received by desktop Zed. Watching native progress.")
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
        state = state.copy(sending = true)
        try {
            activeClient.rpc("thread.send", JSONObject().put("instance_id", instance).put("epoch", epoch)
                .put("thread_id", threadId).put("text", text), id)
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

    fun forget() { state.profile?.let(::forget) }

    fun forget(profile: ConnectionProfile) {
        if (state.profile?.gatewayId == profile.gatewayId) { pollJob?.cancel(); client = null }
        TokenVault.clear(getApplication(), profile.gatewayId)
        val remaining = loadProfiles().filterNot { it.gatewayId == profile.gatewayId }
        persistProfiles(remaining)
        val next = if (state.profile?.gatewayId == profile.gatewayId) remaining.firstOrNull() else state.profile
        preferences.edit().putString("active_gateway", next?.gatewayId).apply()
        state = AppState(profile = next, profiles = remaining, status = if (next == null) "Pair this device" else "Offline")
    }

    private suspend fun poll() {
        while (viewModelScope.isActive) {
            try {
                val selected = state.selectedThreadId
                if (selected == null) loadThreads() else {
                    val events = client!!.rpc("thread.events", JSONObject().put("thread_id", selected)
                        .put("after_sequence", state.snapshot?.lastSequence ?: 0))
                    checkIdentity(events)
                    val eventRows = events.optJSONArray("events").objects()
                    if (eventRows.any { it.optString("kind") == "entry.removed" }) {
                        state = state.copy(snapshot = null)
                    }
                    if (eventRows.isNotEmpty() || state.snapshot?.isBusy == true) loadSnapshot(selected)
                }
                state = state.copy(live = true, status = "Connected to Zed", issue = "")
            } catch (error: Exception) {
                if (error.message?.contains("no longer exposed") == true) {
                    state = state.copy(selectedThreadId = null, snapshot = null, commands = emptyList(), issue = error.message.orEmpty())
                    runCatching { loadThreads() }
                } else if (error.message?.contains("event history changed") == true && state.selectedThreadId != null) {
                    state = state.copy(snapshot = null)
                    runCatching { loadSnapshot(state.selectedThreadId!!) }
                } else state = state.copy(live = false, status = "Reconnecting", issue = error.message.orEmpty())
            }
            delay(if (state.live) 1_000 else 3_000)
        }
    }

    private suspend fun loadThreads() {
        val result = client!!.rpc("thread.list"); checkIdentity(result)
        val threads = result.optJSONArray("threads").objects().mapNotNull { row ->
            val id = row.optString("thread_id"); if (id.isBlank()) null else NativeThread(
                id, row.optString("title", "Untitled Agent thread"), row.optString("status", "Unknown"), row.optIntOrNull("current_turn_id"))
        }
        val selected = state.selectedThreadId?.takeIf { id -> threads.any { it.id == id } }
        state = state.copy(threads = threads, selectedThreadId = selected,
            snapshot = if (selected == null) null else state.snapshot)
    }

    private suspend fun loadSnapshot(id: String) {
        val params = JSONObject().put("thread_id", id)
        if (state.snapshot?.threadId == id) params.put("tail_entry_count", 16)
        val result = client!!.rpc("thread.snapshot", params); checkIdentity(result)
        if (state.selectedThreadId != id) return
        val pageEntries = result.optJSONArray("entries_markdown").strings()
        val pageStart = result.optInt("entry_start_index", 0)
        val pageEnd = result.optInt("entry_end_index", pageStart + pageEntries.size)
        val totalEntries = result.optInt("total_entries", pageEnd)
        if (pageStart < 0 || pageEnd != pageStart + pageEntries.size || totalEntries < pageEnd) {
            throw GatewayException("Invalid transcript page from desktop Zed.")
        }
        val old = state.snapshot
        val canMerge = old?.threadId == id && pageStart >= old.entryStartIndex
            && pageStart <= old.entryStartIndex + old.entries.size
        val mergedStart = if (canMerge) old!!.entryStartIndex else pageStart
        val mergedEntries = if (canMerge) old!!.entries.take(pageStart - old.entryStartIndex) + pageEntries else pageEntries
        val approvals = result.optJSONArray("pending_approvals").objects().mapNotNull { row ->
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
            id, result.optString("title", "Untitled Agent thread"), result.optString("status", "Unknown"),
            result.optIntOrNull("current_turn_id"), state.instanceId.orEmpty(), state.epoch.orEmpty(),
            result.optInt("last_sequence"), mergedEntries,
            mergedStart, totalEntries, mergedStart > 0,
            result.optJSONArray("activity_entries_markdown").strings(), result.optBoolean("truncated"),
            result.optBoolean("activity_truncated"), approvals))
    }

    private suspend fun loadCommands(id: String) {
        if ("thread.commands" !in state.capabilities) return
        val result = client!!.rpc("thread.commands", JSONObject().put("instance_id", state.instanceId)
            .put("epoch", state.epoch).put("thread_id", id))
        if (state.selectedThreadId != id) return
        state = state.copy(commands = result.optJSONArray("commands").objects().mapNotNull { row ->
            val name = row.optString("name"); if (name.isBlank()) null else NativeCommand(name,
                row.optString("description", "Zed Agent command"), row.optString("category", "agent"),
                row.optBoolean("requires_argument"))
        }.sortedBy { it.name })
    }

    private fun checkIdentity(result: JSONObject) {
        if (result.optString("instance_id") != state.instanceId || result.optString("epoch") != state.epoch) {
            throw GatewayException("Desktop Zed restarted. Reconnect before sending.")
        }
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

    private fun saveProfile(profile: ConnectionProfile) {
        val profiles = loadProfiles().filterNot { it.gatewayId.equals(profile.gatewayId, ignoreCase = true) } + profile
        persistProfiles(profiles)
        preferences.edit().putString("active_gateway", profile.gatewayId).apply()
    }

    private fun loadProfiles(): List<ConnectionProfile> {
        val saved = runCatching {
            preferences.getString("profiles", null)?.let(::JSONArray)?.objects()?.mapNotNull { row ->
                val endpoint = row.optString("endpoint")
                val gateway = row.optString("gateway_id")
                if (endpoint.isBlank() || gateway.isBlank()) null else ConnectionProfile(
                    row.optString("name", "My Zed"), endpoint, gateway)
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
            .put("endpoint", profile.endpoint).put("gateway_id", profile.gatewayId)) }
        preferences.edit().putString("profiles", rows.toString()).apply()
    }

    private fun loadProfile(profiles: List<ConnectionProfile>): ConnectionProfile? {
        val active = preferences.getString("active_gateway", null)
        return profiles.firstOrNull { it.gatewayId == active } ?: profiles.firstOrNull()
    }
}

private fun JSONArray?.objects(): List<JSONObject> = if (this == null) emptyList() else (0 until length()).mapNotNull { optJSONObject(it) }
private fun JSONArray?.strings(): List<String> = if (this == null) emptyList() else (0 until length()).mapNotNull { optString(it).takeIf(String::isNotBlank) }
private fun JSONArray?.integers(): List<Int> = if (this == null) emptyList() else (0 until length()).mapNotNull { index ->
    if (isNull(index)) null else optInt(index)
}
private fun JSONObject.optIntOrNull(key: String): Int? = if (!has(key) || isNull(key)) null else optInt(key)
