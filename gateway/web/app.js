"use strict";

const $ = (id) => document.getElementById(id);
const state = {
  gatewayId: null,
  token: null,
  instanceId: null,
  epoch: null,
  threads: [],
  threadId: null,
  sequence: 0,
  polling: false,
  pending: null,
};
const safeSession = {
  read(key) { try { return sessionStorage.getItem(key); } catch { return null; } },
  write(key, value) { try { sessionStorage.setItem(key, value); } catch { /* private storage unavailable */ } },
  remove(key) { try { sessionStorage.removeItem(key); } catch { /* private storage unavailable */ } },
};

function connection(message, status = "") {
  const element = $("connection");
  element.textContent = message;
  element.className = `connection ${status}`;
}
function notice(message) {
  $("notice").textContent = message;
  $("notice").classList.toggle("hidden", !message);
}
function delivery(message, uncertain = false) {
  $("delivery").textContent = message;
  $("delivery").classList.toggle("hidden", !message);
  $("retry").classList.toggle("hidden", !uncertain || !state.pending?.text);
  $("clear-pending").classList.toggle("hidden", !uncertain);
  $("send").disabled = !state.threadId || !!state.pending || !state.token;
}
function pendingKey() { return `zedlink.pending.${state.gatewayId}`; }
function tokenKey() { return `zedlink.token.${state.gatewayId}`; }
function savePending() {
  if (state.pending) {
    const { id, instanceId, epoch, threadId } = state.pending;
    safeSession.write(pendingKey(), JSON.stringify({ id, instanceId, epoch, threadId }));
  } else {
    safeSession.remove(pendingKey());
  }
}
function clearPending() {
  state.pending = null;
  savePending();
  delivery("");
}
function identity(result) {
  if (result.instance_id !== state.instanceId || result.epoch !== state.epoch) {
    throw new Error("Zed instance or event epoch changed. Reconnect before sending.");
  }
}
function apiError(code) {
  if (code === "UNAUTHENTICATED") return "Browser credential revoked or missing. Pair again.";
  if (code === "THREAD_NOT_EXPOSED") return "This thread is no longer exposed in desktop Zed.";
  if (code === "INSTANCE_UNAVAILABLE") return "Desktop Zed is unavailable. Check that it is running.";
  if (code === "RESYNC_REQUIRED") return "Event history changed. Reloading the native snapshot.";
  return code || "Gateway request failed.";
}
async function rpc(method, params = {}, requestId = crypto.randomUUID()) {
  const response = await fetch("/v1/rpc", {
    method: "POST", cache: "no-store", redirect: "error",
    headers: { "Content-Type": "application/json", "Authorization": `Bearer ${state.token}` },
    body: JSON.stringify({ version: 1, request_id: requestId, method, params }),
  });
  const data = await response.json();
  if (response.status === 401) {
    state.token = null;
    safeSession.remove(tokenKey());
    $("pair-panel").classList.remove("hidden");
    $("sessions-panel").classList.add("hidden");
  }
  if (!response.ok) throw new Error(apiError(data.error));
  if (data.version !== 1 || data.request_id !== requestId || (!!data.result === !!data.error)) {
    throw new Error("Gateway response did not match this request.");
  }
  if (data.error) {
    const error = new Error(apiError(data.error.code));
    error.code = data.error.code;
    throw error;
  }
  return data.result;
}

async function loadGateway() {
  try {
    const response = await fetch("/v1/gateway", { cache: "no-store", redirect: "error" });
    const result = await response.json();
    if (!response.ok || result.version !== 1 || typeof result.gateway_id !== "string") {
      throw new Error("Unsupported gateway identity response.");
    }
    state.gatewayId = result.gateway_id;
    $("gateway-id").textContent = result.gateway_id;
    const token = safeSession.read(tokenKey());
    if (token) {
      state.token = token;
      await connect();
    } else {
      connection("Pair this browser");
    }
  } catch (error) {
    connection("Gateway unavailable", "offline");
    notice(error.message);
  }
}

async function connect() {
  if (!state.token) return;
  connection("Connecting…");
  try {
    const info = await rpc("instance.info");
    if (typeof info.instance_id !== "string" || typeof info.epoch !== "string") {
      throw new Error("Invalid Zed instance identity.");
    }
    const changed = state.instanceId && (state.instanceId !== info.instance_id || state.epoch !== info.epoch);
    state.instanceId = info.instance_id;
    state.epoch = info.epoch;
    if (changed) {
      state.threadId = null;
      state.sequence = 0;
      notice("Desktop Zed restarted. Select an exposed thread again; uncertain sends were not repeated.");
    }
    $("host-label").textContent = `Zed instance ${info.instance_id.slice(0, 8)}…`;
    $("pair-panel").classList.add("hidden");
    $("sessions-panel").classList.remove("hidden");
    const prior = safeSession.read(pendingKey());
    if (prior && !state.pending) {
      try { state.pending = { ...JSON.parse(prior), text: null }; } catch { safeSession.remove(pendingKey()); }
      if (state.pending) delivery("A previous send has uncertain delivery. Check its status before making another request.", true);
    }
    await loadThreads();
    connection("Connected to Zed", "online");
  } catch (error) {
    connection("Reconnect needed", "offline");
    notice(error.message);
  }
}

async function loadThreads() {
  const result = await rpc("thread.list");
  identity(result);
  if (!Array.isArray(result.threads)) throw new Error("Invalid thread list.");
  state.threads = result.threads;
  const list = $("thread-list");
  list.replaceChildren();
  if (state.threads.length === 0) {
    const text = document.createElement("p");
    text.className = "muted";
    text.textContent = "No exposed threads. Choose /remote-control in a native Zed Agent thread.";
    list.append(text);
  }
  for (const thread of state.threads) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `thread-item ${thread.thread_id === state.threadId ? "active" : ""}`;
    const title = document.createElement("strong");
    title.textContent = thread.title || "Untitled Agent thread";
    const detail = document.createElement("small");
    detail.textContent = `${thread.status || "Unknown"} · ${String(thread.thread_id).slice(0, 10)}…`;
    button.append(title, detail);
    button.addEventListener("click", () => selectThread(thread.thread_id));
    list.append(button);
  }
  if (state.threadId && !state.threads.some((thread) => thread.thread_id === state.threadId)) {
    state.threadId = null;
    state.sequence = 0;
    $("messages").replaceChildren();
    $("prompt").disabled = true;
    $("thread-title").textContent = "Choose a session";
    notice("The selected thread is no longer exposed in desktop Zed.");
  }
}

async function selectThread(threadId) {
  if (state.pending && state.pending.threadId !== threadId) {
    notice("Resolve or clear the uncertain send before switching threads.");
    return;
  }
  state.threadId = threadId;
  state.sequence = 0;
  $("prompt").disabled = false;
  $("send").disabled = !!state.pending;
  $("thread-title").textContent = state.threads.find((thread) => thread.thread_id === threadId)?.title || "Untitled Agent thread";
  await loadThreads();
  try {
    await snapshot();
    notice("");
  } catch (error) { notice(error.message); }
}

async function snapshot() {
  if (!state.threadId) return;
  const result = await rpc("thread.snapshot", { thread_id: state.threadId });
  identity(result);
  if (result.thread_id !== state.threadId || !Array.isArray(result.entries_markdown)) {
    throw new Error("Snapshot belongs to another thread.");
  }
  state.sequence = result.last_sequence;
  const container = $("messages");
  const follow = container.scrollHeight - container.scrollTop - container.clientHeight < 90;
  const fragment = document.createDocumentFragment();
  for (const [index, markdown] of result.entries_markdown.entries()) {
    const article = document.createElement("article");
    article.className = "message";
    const label = document.createElement("div");
    label.className = "message-label";
    label.textContent = `Native entry ${index + 1}`;
    const content = document.createElement("pre");
    content.textContent = markdown;
    article.append(label, content);
    fragment.append(article);
  }
  container.replaceChildren(fragment);
  if (follow) container.scrollTop = container.scrollHeight;
  $("thread-title").textContent = result.title || "Untitled Agent thread";
  $("thread-meta").textContent = result.truncated ? "Transcript truncated by native probe" : `Thread ${result.thread_id.slice(0, 12)}…`;
  $("thread-state").textContent = result.status;
  $("thread-state").className = `state-pill ${result.status === "Idle" ? "online" : ""}`;
  if (result.pending_approvals?.length) {
    notice("Approval pending in desktop Zed. Remote approval controls are awaiting native race validation.");
  }
}

async function reconcilePending() {
  if (!state.pending || !state.token) return;
  const pending = state.pending;
  if (pending.instanceId !== state.instanceId || pending.epoch !== state.epoch) {
    delivery("Zed restarted. Delivery of the previous request is unknown; inspect the desktop thread before clearing it.", true);
    return;
  }
  const result = await rpc("request.status", {
    instance_id: pending.instanceId, epoch: pending.epoch, original_request_id: pending.id,
  });
  delivery(result.known
    ? `Zed knows request ${pending.id.slice(0, 8)}…; native acceptance remains ${result.outcome}. Check the transcript before another send.`
    : `Request ${pending.id.slice(0, 8)}… is unknown to this Zed instance. It was not resent.`, true);
}

async function poll() {
  if (!state.token || state.polling) return;
  state.polling = true;
  try {
    if (state.threadId) {
      const result = await rpc("thread.events", { thread_id: state.threadId, after_sequence: state.sequence });
      identity(result);
      if (result.thread_id !== state.threadId) throw new Error("Event feed changed threads.");
      if (result.events?.length) await snapshot();
      else state.sequence = result.last_sequence;
    }
    if (state.pending) await reconcilePending();
    connection("Connected to Zed", "online");
  } catch (error) {
    if (error.code === "RESYNC_REQUIRED") {
      try { await snapshot(); return; } catch (snapshotError) { notice(snapshotError.message); }
    } else if (error.code === "THREAD_NOT_EXPOSED") {
      await loadThreads().catch(() => {});
    } else {
      notice(error.message);
    }
    connection("Reconnecting…", "offline");
  } finally { state.polling = false; }
}

async function sendPrompt(event) {
  event.preventDefault();
  if (!state.threadId || !state.token || state.pending) return;
  const text = $("prompt").value.trim();
  if (!text) return;
  const pending = { id: crypto.randomUUID(), instanceId: state.instanceId,
    epoch: state.epoch, threadId: state.threadId, text };
  state.pending = pending;
  savePending();
  delivery("Sending to native Zed…", true);
  await sendPending();
}
async function sendPending() {
  const pending = state.pending;
  if (!pending?.text || pending.instanceId !== state.instanceId || pending.epoch !== state.epoch) return;
  try {
    const result = await rpc("thread.send", {
      instance_id: pending.instanceId, epoch: pending.epoch,
      thread_id: pending.threadId, text: pending.text,
    }, pending.id);
    if (result.outcome === "queued") {
      $("prompt").value = "";
      clearPending();
      delivery("Queued in desktop Zed. Watch the native thread for execution.");
    } else {
      delivery("Sent to Zed, but native acceptance is unconfirmed. The draft remains here; do not send it under a new ID.", true);
    }
    await snapshot();
  } catch (error) {
    delivery(`Delivery unknown: ${error.message} The same request ID can be retried; no automatic resend occurred.`, true);
  }
}

$("pair-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.gatewayId) return;
  if ($("expected-id").value.trim() !== state.gatewayId) {
    notice("Gateway ID differs from the workstation value. Pairing code was not sent.");
    return;
  }
  const code = $("pair-code").value.trim();
  if (!/^[0-9a-fA-F]{64}$/.test(code)) { notice("Enter the 64-character pairing code."); return; }
  $("pair-button").disabled = true;
  try {
    const response = await fetch("/v1/pair", {
      method: "POST", cache: "no-store", redirect: "error",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, device_name: $("device-name").value.trim() }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(apiError(result.error));
    if (result.gateway_id !== state.gatewayId || !/^[0-9a-f]{64}$/.test(result.token)) {
      throw new Error("Pairing identity or token was invalid.");
    }
    state.token = result.token;
    safeSession.write(tokenKey(), result.token);
    $("pair-code").value = "";
    notice("");
    await connect();
  } catch (error) { notice(error.message); }
  finally { $("pair-button").disabled = false; }
});
$("refresh").addEventListener("click", () => connect());
$("forget").addEventListener("click", () => {
  safeSession.remove(tokenKey());
  safeSession.remove(pendingKey());
  state.token = null;
  state.pending = null;
  state.threadId = null;
  $("pair-panel").classList.remove("hidden");
  $("sessions-panel").classList.add("hidden");
  $("messages").replaceChildren();
  $("prompt").disabled = true;
  delivery("");
  connection("Browser token forgotten");
  notice("This only removes the tab token. Revoke the paired device through the workstation admin command.");
});
$("composer-form").addEventListener("submit", sendPrompt);
$("retry").addEventListener("click", sendPending);
$("clear-pending").addEventListener("click", () => {
  clearPending();
  notice("Uncertain delivery was cleared locally. Check the desktop thread before sending similar text again.");
});
setInterval(poll, 1000);
loadGateway();
