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
    val status: String = "Offline",
    val live: Boolean = false,
    val threads: List<NativeThread> = emptyList(),
    val selectedThreadId: String? = null,
    val snapshot: ThreadSnapshot? = null,
    val commands: List<NativeCommand> = emptyList(),
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
        loadProfile()?.let { profile ->
            state = state.copy(profile = profile)
            if (TokenVault.read(application) != null) connect()
        }
    }

    fun applyPairingLink(text: String): Pair<ConnectionProfile, String?> = GatewayClient.profileFromPairingLink(text)

    fun pair(profile: ConnectionProfile, code: String, deviceName: String) = viewModelScope.launch {
        state = state.copy(status = "Pairing…", issue = "")
        try {
            val pairingClient = GatewayClient(profile, null)
            val (_, token) = pairingClient.pair(code.trim(), deviceName.trim().ifBlank { "Android" })
            TokenVault.write(getApplication(), token)
            saveProfile(profile)
            state = state.copy(profile = profile)
            connect()
        } catch (error: Exception) {
            state = state.copy(status = "Offline", issue = error.message ?: "Pairing failed.")
        }
    }

    fun connect() {
        val profile = state.profile ?: return
        val token = TokenVault.read(getApplication()) ?: run {
            state = state.copy(status = "Pair this device", live = false); return
        }
        pollJob?.cancel()
        viewModelScope.launch {
            state = state.copy(status = "Connecting…", live = false, issue = "")
            try {
                val next = GatewayClient(profile, token)
                val info = next.rpc("instance.info")
                client = next
                state = state.copy(
                    status = "Connected to Zed", live = true,
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

    fun selectThread(id: String) = viewModelScope.launch {
        if (state.threads.none { it.id == id }) return@launch
        val draft = preferences.getString("draft.$id", "").orEmpty()
        state = state.copy(selectedThreadId = id, snapshot = null, commands = emptyList(), draft = draft, issue = "")
        runCatching { loadSnapshot(id); loadCommands(id) }
            .onFailure { state = state.copy(issue = it.message.orEmpty()) }
    }

    fun closeThread() { state = state.copy(selectedThreadId = null, snapshot = null, commands = emptyList()) }

    fun setDraft(value: String) {
        state = state.copy(draft = value)
        state.selectedThreadId?.let { preferences.edit().putString("draft.$it", value).apply() }
    }

    fun insertCommand(command: NativeCommand) = setDraft("/${command.name}${if (command.requiresArgument) " " else ""}")

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

    fun forget() {
        pollJob?.cancel(); client = null; TokenVault.clear(getApplication())
        preferences.edit().clear().apply()
        state = AppState(status = "Pair this device")
    }

    private suspend fun poll() {
        while (viewModelScope.isActive) {
            try {
                val selected = state.selectedThreadId
                if (selected == null) loadThreads() else {
                    val events = client!!.rpc("thread.events", JSONObject().put("thread_id", selected)
                        .put("after_sequence", state.snapshot?.lastSequence ?: 0))
                    checkIdentity(events)
                    if ((events.optJSONArray("events")?.length() ?: 0) > 0 || state.snapshot?.isBusy == true) loadSnapshot(selected)
                }
                state = state.copy(live = true, status = "Connected to Zed", issue = "")
            } catch (error: Exception) {
                if (error.message?.contains("no longer exposed") == true) {
                    state = state.copy(selectedThreadId = null, snapshot = null, commands = emptyList(), issue = error.message.orEmpty())
                    runCatching { loadThreads() }
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
        val result = client!!.rpc("thread.snapshot", JSONObject().put("thread_id", id)); checkIdentity(result)
        if (state.selectedThreadId != id) return
        val approvals = result.optJSONArray("pending_approvals").objects().mapNotNull { row ->
            val approvalId = row.optString("approval_id"); if (approvalId.isBlank()) null else NativeApproval(
                approvalId, row.optIntOrNull("turn_id"), row.optString("tool_name", "Zed tool"),
                row.optString("display", "Permission requested"), row.opt("raw_input")?.takeUnless { it == JSONObject.NULL }?.toString(),
                row.optBoolean("details_truncated", true))
        }
        state = state.copy(snapshot = ThreadSnapshot(
            id, result.optString("title", "Untitled Agent thread"), result.optString("status", "Unknown"),
            result.optIntOrNull("current_turn_id"), state.instanceId.orEmpty(), state.epoch.orEmpty(),
            result.optInt("last_sequence"), result.optJSONArray("entries_markdown").strings(),
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

    private fun saveProfile(profile: ConnectionProfile) {
        preferences.edit().putString("name", profile.name).putString("endpoint", profile.endpoint)
            .putString("gateway", profile.gatewayId).apply()
    }

    private fun loadProfile(): ConnectionProfile? {
        val endpoint = preferences.getString("endpoint", null) ?: return null
        val gateway = preferences.getString("gateway", null) ?: return null
        return ConnectionProfile(preferences.getString("name", "My Zed")!!, endpoint, gateway)
    }
}

private fun JSONArray?.objects(): List<JSONObject> = if (this == null) emptyList() else (0 until length()).mapNotNull { optJSONObject(it) }
private fun JSONArray?.strings(): List<String> = if (this == null) emptyList() else (0 until length()).mapNotNull { optString(it).takeIf(String::isNotBlank) }
private fun JSONObject.optIntOrNull(key: String): Int? = if (!has(key) || isNull(key)) null else optInt(key)
