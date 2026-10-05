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
const safeStore = {
  read(key) {
    try {
      const saved = localStorage.getItem(key);
      if (saved !== null) return saved;
    } catch { /* persistent storage unavailable */ }
    try {
      const prior = sessionStorage.getItem(key);
      if (prior !== null) this.write(key, prior);
      return prior;
    } catch { return null; }
  },
  write(key, value) {
    try { localStorage.setItem(key, value); sessionStorage.removeItem(key); return true; }
    catch {
      try { sessionStorage.setItem(key, value); } catch { /* storage unavailable */ }
      return false;
    }
  },
  remove(key) {
    try { localStorage.removeItem(key); } catch { /* storage unavailable */ }
    try { sessionStorage.removeItem(key); } catch { /* storage unavailable */ }
  },
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
    safeStore.write(pendingKey(), JSON.stringify({ id, instanceId, epoch, threadId }));
  } else {
    safeStore.remove(pendingKey());
  }
}
function clearPending() {
  state.pending = null;
  savePending();
  delivery("");
}
function identity(result) {
  if (result.instance_id !== state.instanceId || result.epoch !== state.epoch) {
    const error = new Error("Zed instance or event epoch changed. Reconnect before sending.");
    error.code = "IDENTITY_CHANGED";
    throw error;
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
    safeStore.remove(tokenKey());
    $("pair-panel").classList.remove("hidden");
    $("sessions-panel").classList.add("hidden");
  }
  if (!response.ok) {
    const error = new Error(apiError(data.error));
    error.code = data.error;
    throw error;
  }
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
    const expectedFromLink = new URLSearchParams(location.hash.slice(1)).get("gateway");
    if (expectedFromLink) {
      $("expected-id").value = expectedFromLink;
      if (expectedFromLink !== result.gateway_id) {
        throw new Error("The gateway identity differs from the desktop pairing link. Do not enter a code.");
      }
    }
    const token = safeStore.read(tokenKey());
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
  $("pair-panel").classList.add("hidden");
  $("sessions-panel").classList.remove("hidden");
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
      document.body.classList.remove("thread-open", "mobile-sessions");
      state.sequence = 0;
      notice("Desktop Zed restarted. Select an exposed thread again; uncertain sends were not repeated.");
    }
    $("host-label").textContent = `Zed instance ${info.instance_id.slice(0, 8)}…`;
    const prior = safeStore.read(pendingKey());
    if (prior && !state.pending) {
      try { state.pending = { ...JSON.parse(prior), text: null }; } catch { safeStore.remove(pendingKey()); }
      if (state.pending) delivery("A previous send has uncertain delivery. Check its status before making another request.", true);
    }
    await loadThreads();
    connection("Connected to Zed", "online");
  } catch (error) {
    connection("Zed unavailable", "offline");
    notice(`Pairing is saved. ${error.message} Refresh when desktop Zed is ready.`);
  }
}

async function loadThreads() {
  const result = await rpc("thread.list");
  identity(result);
  if (!Array.isArray(result.threads)) throw new Error("Invalid thread list.");
  state.threads = result.threads;
  renderThreads();
  if (state.threadId && !state.threads.some((thread) => thread.thread_id === state.threadId)) {
    state.threadId = null;
    document.body.classList.remove("thread-open", "mobile-sessions");
    state.sequence = 0;
    $("messages").replaceChildren();
    $("prompt").disabled = true;
    $("thread-title").textContent = "Choose a session";
    notice("The selected thread is no longer exposed in desktop Zed.");
  }
}

function renderThreads() {
  const list = $("thread-list");
  list.replaceChildren();
  const query = $("session-search").value.trim().toLocaleLowerCase();
  const visible = state.threads.filter((thread) =>
    `${thread.title || ""} ${thread.thread_id}`.toLocaleLowerCase().includes(query));
  $("thread-count").textContent = String(state.threads.length);
  if (visible.length === 0) {
    const text = document.createElement("p");
    text.className = "muted";
    text.textContent = state.threads.length
      ? "No sessions match this search."
      : "No exposed threads. Choose /remote-control in a native Zed Agent thread.";
    list.append(text);
  }
  for (const thread of visible) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `thread-item ${thread.thread_id === state.threadId ? "active" : ""}`;
    const badge = document.createElement("span");
    badge.className = "thread-badge";
    badge.textContent = "ZED AGENT";
    const status = document.createElement("span");
    status.className = `thread-status ${thread.status === "Idle" ? "" : "busy"}`;
    status.textContent = thread.status || "Unknown";
    const title = document.createElement("strong");
    title.textContent = thread.title || "Untitled Agent thread";
    const detail = document.createElement("small");
    detail.textContent = `Native thread · ${String(thread.thread_id).slice(0, 10)}…`;
    button.append(badge, status, title, detail);
    button.addEventListener("click", () => selectThread(thread.thread_id));
    list.append(button);
  }
}

async function selectThread(threadId) {
  state.threadId = threadId;
  document.body.classList.add("thread-open");
  document.body.classList.remove("mobile-sessions");
  state.sequence = 0;
  $("prompt").disabled = false;
  $("jump-latest").classList.add("hidden");
  $("send").disabled = !!state.pending;
  $("thread-title").textContent = state.threads.find((thread) => thread.thread_id === threadId)?.title || "Untitled Agent thread";
  await loadThreads();
  try {
    await snapshot();
    notice("");
  } catch (error) { notice(error.message); }
}

function entryPresentation(markdown, index) {
  const headings = [
    [/^## User(?: \(checkpoint\))?\n\n/, "user", "You"],
    [/^## Assistant\n\n/, "assistant", "Zed Agent"],
    [/^## Input Requested\n\n/, "tool", "Input requested in Zed"],
    [/^## Plan\n\n/, "tool", "Plan"],
    [/^## Context Compaction[^\n]*\n\n/, "tool", "Context summary"],
  ];
  for (const [pattern, kind, label] of headings) {
    const match = markdown.match(pattern);
    if (match) return { kind, label, body: markdown.slice(match[0].length) };
  }
  const tool = markdown.match(/^\*\*Tool Call: ([^\n]*?)\*\*\nStatus: ([^\n]*)\n\n/);
  if (tool) return { kind: "tool", label: `Tool · ${tool[1]} · ${tool[2]}`, body: markdown.slice(tool[0].length) };
  return { kind: "native", label: `Native entry ${index + 1}`, body: markdown };
}

function appendInline(target, value) {
  const pattern = /(`[^`\n]+`|\*\*[^*\n]+\*\*)/g;
  let cursor = 0;
  for (const match of value.matchAll(pattern)) {
    if (match.index > cursor) target.append(document.createTextNode(value.slice(cursor, match.index)));
    const code = match[0].startsWith("`");
    const element = document.createElement(code ? "code" : "strong");
    element.textContent = code ? match[0].slice(1, -1) : match[0].slice(2, -2);
    target.append(element);
    cursor = match.index + match[0].length;
  }
  if (cursor < value.length) target.append(document.createTextNode(value.slice(cursor)));
}

function renderBody(target, source) {
  const lines = source.trim().split(/\r?\n/);
  for (let i = 0; i < lines.length;) {
    const line = lines[i];
    if (!line.trim()) { i += 1; continue; }
    if (line.startsWith("```")) {
      const block = [];
      i += 1;
      while (i < lines.length && !lines[i].startsWith("```")) block.push(lines[i++]);
      if (i < lines.length) i += 1;
      const pre = document.createElement("pre");
      const code = document.createElement("code");
      code.textContent = block.join("\n");
      pre.append(code);
      target.append(pre);
      continue;
    }
    if (line === "<thinking>") {
      const block = [];
      i += 1;
      while (i < lines.length && lines[i] !== "</thinking>") block.push(lines[i++]);
      if (i < lines.length) i += 1;
      const details = document.createElement("details");
      const summary = document.createElement("summary");
      summary.textContent = "Reasoning";
      const content = document.createElement("p");
      content.textContent = block.join("\n");
      details.append(summary, content);
      target.append(details);
      continue;
    }
    const heading = line.match(/^#{1,4} (.+)$/);
    if (heading) {
      const element = document.createElement("h3");
      appendInline(element, heading[1]);
      target.append(element);
      i += 1;
      continue;
    }
    const bullet = line.match(/^([-*] |\d+\. )/);
    if (bullet) {
      const ordered = /^\d/.test(bullet[0]);
      const list = document.createElement(ordered ? "ol" : "ul");
      while (i < lines.length && (ordered ? /^\d+\. / : /^[-*] /).test(lines[i])) {
        const item = document.createElement("li");
        appendInline(item, lines[i].replace(ordered ? /^\d+\. / : /^[-*] /, ""));
        list.append(item);
        i += 1;
      }
      target.append(list);
      continue;
    }
    if (line.startsWith("> ")) {
      const quote = document.createElement("blockquote");
      while (i < lines.length && lines[i].startsWith("> ")) {
        if (quote.childNodes.length) quote.append(document.createElement("br"));
        appendInline(quote, lines[i].slice(2));
        i += 1;
      }
      target.append(quote);
      continue;
    }
    const paragraph = document.createElement("p");
    while (i < lines.length && lines[i].trim() && !/^(?:```|#{1,4} |[-*] |\d+\. |> |<thinking>)/.test(lines[i])) {
      if (paragraph.childNodes.length) paragraph.append(document.createElement("br"));
      appendInline(paragraph, lines[i]);
      i += 1;
    }
    if (paragraph.childNodes.length) target.append(paragraph);
    else i += 1;
  }
}

async function snapshot() {
  if (!state.threadId) return;
  const result = await rpc("thread.snapshot", { thread_id: state.threadId });
  identity(result);
  if (result.thread_id !== state.threadId || !Array.isArray(result.entries_markdown)
      || !result.entries_markdown.every((entry) => typeof entry === "string")) {
    throw new Error("Snapshot belongs to another thread.");
  }
  state.sequence = result.last_sequence;
  const container = $("messages");
  const follow = container.scrollHeight - container.scrollTop - container.clientHeight < 90;
  const expandedTools = new Set([...container.querySelectorAll(".message.tool details[open]")]
    .map((details) => details.closest(".message")?.dataset.entryIndex));
  const fragment = document.createDocumentFragment();
  for (const [index, markdown] of result.entries_markdown.entries()) {
    const presentation = entryPresentation(markdown, index);
    const article = document.createElement("article");
    article.className = `message ${presentation.kind}`;
    article.dataset.entryIndex = String(index);
    const heading = document.createElement("div");
    heading.className = "message-heading";
    const label = document.createElement("div");
    label.className = "message-label";
    label.textContent = presentation.label;
    const copy = document.createElement("button");
    copy.type = "button";
    copy.className = "message-copy";
    copy.textContent = "Copy";
    copy.setAttribute("aria-label", `Copy ${presentation.label} content`);
    copy.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(presentation.body);
        copy.textContent = "Copied";
      } catch { notice("Clipboard access is unavailable in this browser."); }
    });
    heading.append(label, copy);
    const content = document.createElement("div");
    content.className = "message-body";
    if (presentation.kind === "tool") {
      const details = document.createElement("details");
      details.open = expandedTools.has(String(index));
      const summary = document.createElement("summary");
      summary.textContent = "View tool details";
      details.append(summary, content);
      renderBody(content, presentation.body);
      article.append(heading, details);
    } else {
      renderBody(content, presentation.body);
      article.append(heading, content);
    }
    fragment.append(article);
  }
  container.replaceChildren(fragment);
  if (follow) {
    container.scrollTop = container.scrollHeight;
    $("jump-latest").classList.add("hidden");
  } else if (result.entries_markdown.length) {
    $("jump-latest").classList.remove("hidden");
  }
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
    if (!state.instanceId) { await connect(); return; }
    if (state.threadId) {
      const result = await rpc("thread.events", { thread_id: state.threadId, after_sequence: state.sequence });
      identity(result);
      if (result.thread_id !== state.threadId) throw new Error("Event feed changed threads.");
      if (result.events?.length) await snapshot();
      else state.sequence = result.last_sequence;
    } else await loadThreads();
    if (state.pending) await reconcilePending();
    connection("Connected to Zed", "online");
  } catch (error) {
    if (error.code === "RESYNC_REQUIRED") {
      try { await snapshot(); return; } catch (snapshotError) { notice(snapshotError.message); }
    } else if (error.code === "THREAD_NOT_EXPOSED" || error.code === "IDENTITY_CHANGED") {
      await connect();
      return;
    } else {
      notice(error.message);
    }
    connection(error.code === "INSTANCE_UNAVAILABLE" ? "Zed unavailable" : "Reconnecting…", "offline");
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
    $("messages").scrollTop = $("messages").scrollHeight;
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
  if (!/^([0-9]{10}|[0-9a-fA-F]{64})$/.test(code)) { notice("Enter the 10-digit pairing code from the workstation."); return; }
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
    const remembered = safeStore.write(tokenKey(), result.token);
    $("pair-code").value = "";
    notice(remembered ? "" : "This browser did not allow persistent storage; pairing may be needed after this tab closes.");
    await connect();
  } catch (error) { notice(error.message); }
  finally { $("pair-button").disabled = false; }
});
$("refresh").addEventListener("click", () => connect());
$("session-search").addEventListener("input", renderThreads);
$("messages").addEventListener("scroll", () => {
  const container = $("messages");
  if (container.scrollHeight - container.scrollTop - container.clientHeight < 90) {
    $("jump-latest").classList.add("hidden");
  }
});
$("jump-latest").addEventListener("click", () => {
  const container = $("messages");
  container.scrollTop = container.scrollHeight;
  $("jump-latest").classList.add("hidden");
});
$("show-sessions").addEventListener("click", () => {
  document.body.classList.add("mobile-sessions");
});
$("prompt").addEventListener("input", () => {
  const prompt = $("prompt");
  prompt.style.height = "auto";
  prompt.style.height = `${Math.min(prompt.scrollHeight, 150)}px`;
});
$("forget").addEventListener("click", () => {
  safeStore.remove(tokenKey());
  safeStore.remove(pendingKey());
  state.token = null;
  state.pending = null;
  state.threadId = null;
  document.body.classList.remove("thread-open", "mobile-sessions");
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
