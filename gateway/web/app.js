"use strict";

const $ = (id) => document.getElementById(id);
const UI_BUILD = "2026.10.05.7";
const state = {
  gatewayId: null,
  token: null,
  instanceId: null,
  epoch: null,
  capabilities: [],
  commands: [],
  threads: [],
  threadId: null,
  turnId: null,
  threadStatus: null,
  sequence: 0,
  polling: false,
  live: false,
  pending: null,
  activitySignature: null,
  activityCollapsed: false,
  activityBusy: false,
  renderedEntries: [],
  renderedThreadId: null,
  creatingThread: false,
  eventSocket: null,
  eventThreadId: null,
  eventReconnectTimer: null,
  snapshotPromise: null,
  snapshotQueued: false,
  lastSnapshotAt: 0,
  gatewayVerified: false,
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
  state.live = status === "online";
  const element = $("connection");
  element.textContent = message;
  element.className = `connection ${status}`;
  $("mobile-connection-state").textContent = message;
  showStop();
  showCreateAvailability();
}
function pairingStatus() {
  return matchMedia("(display-mode: standalone)").matches ? "Pair this app" : "Pair this browser";
}
function showCreateAvailability() {
  const available = state.live && state.capabilities.includes("thread.create") && !state.creatingThread;
  $("new-session").disabled = !available;
  $("new-session").title = available
    ? "Create a native Zed Agent session"
    : "Start patched Zed to create a session";
}
function notice(message) {
  for (const id of ["notice", "pair-notice"]) {
    $(id).textContent = message;
    $(id).classList.toggle("hidden", !message);
  }
}
function delivery(message, uncertain = false) {
  $("delivery").textContent = message;
  $("delivery").classList.toggle("hidden", !message);
  $("delivery-details").classList.toggle("hidden", !uncertain);
  const retryable = uncertain && !!state.pending?.text
    && state.pending.instanceId === state.instanceId && state.pending.epoch === state.epoch;
  $("retry").classList.toggle("hidden", !retryable);
  $("clear-pending").classList.toggle("hidden", !uncertain);
  $("send").disabled = !state.threadId || !!state.pending || !state.token;
}
function pendingKey() { return `zedlink.pending.${state.gatewayId}`; }
function tokenKey() { return `zedlink.token.${state.gatewayId}`; }
function selectedThreadKey() { return `zedlink.selectedThread.${state.gatewayId}`; }
function sidebarKey() { return `zedlink.sidebarCollapsed.${state.gatewayId}`; }
function updateSidebarToggle() {
  const mobile = matchMedia("(max-width: 760px)").matches;
  const collapsed = document.body.classList.contains("sidebar-collapsed");
  const mobileOpen = document.body.classList.contains("mobile-sessions");
  const button = $("show-sessions");
  button.textContent = mobile ? "‹ Sessions" : collapsed ? "Sessions" : "Hide sessions";
  button.setAttribute("aria-label", mobile ? "Show sessions" : collapsed ? "Show sessions" : "Hide sessions");
  button.setAttribute("aria-expanded", String(mobile ? mobileOpen : !collapsed));
}
function requireManualGatewayVerification() {
  state.gatewayVerified = false;
  if (state.gatewayId) $("expected-id").value = state.gatewayId;
  $("verify-gateway").checked = false;
  $("manual-confirm").classList.remove("hidden");
  $("pair-button").disabled = true;
  requestAnimationFrame(() => {
    window.scrollTo(0, 0);
    $("main").scrollTop = 0;
    $("pair-panel").scrollTop = 0;
  });
}
function acceptLinkedGateway() {
  state.gatewayVerified = true;
  $("verify-gateway").checked = true;
  $("manual-confirm").classList.add("hidden");
  $("pair-button").disabled = false;
}
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
function settledDelivery(message) {
  clearPending();
  delivery(message);
  setTimeout(() => {
    if (!state.pending && $("delivery").textContent === message) delivery("");
  }, 4500);
}
function identity(result) {
  if (result.instance_id !== state.instanceId || result.epoch !== state.epoch) {
    const error = new Error("Zed instance or event epoch changed. Reconnect before sending.");
    error.code = "IDENTITY_CHANGED";
    throw error;
  }
}
function showStop() {
  $("stop-turn").classList.toggle("hidden", !state.live || !state.threadId || !Number.isInteger(state.turnId)
    || !state.capabilities.includes("thread.cancel"));
}
function apiError(code) {
  if (code === "UNAUTHENTICATED") return "Browser credential revoked or missing. Pair again.";
  if (code === "THREAD_NOT_EXPOSED") return "This thread is no longer exposed in desktop Zed.";
  if (code === "INSTANCE_UNAVAILABLE") return "Desktop Zed is unavailable. Check that it is running.";
  if (code === "RESYNC_REQUIRED") return "Event history changed. Reloading the native snapshot.";
  if (code === "UNSUPPORTED_CAPABILITY") return "This command is unavailable in this Zed thread.";
  if (code === "REQUEST_CONFLICT") return "That request ID was already used for different content.";
  if (code === "PAIRING_UNAVAILABLE") return "No active pairing request. Create a fresh pairing link in desktop Zed.";
  if (code === "PAIRING_EXPIRED") return "That pairing link expired. Create a fresh one in desktop Zed.";
  if (code === "PAIRING_INVALID") return "That pairing code is incorrect. Check the code or create a fresh pairing link.";
  if (code === "RATE_LIMITED") return "The gateway cannot add another device. Revoke an old device in desktop Zed first.";
  return code || "Gateway request failed.";
}

function browserDeviceName(agent = navigator.userAgent || "") {
  const browser = /Edg\//.test(agent) ? "Edge"
    : /Firefox\//.test(agent) ? "Firefox"
      : /(?:Chrome|CriOS)\//.test(agent) ? "Chrome"
        : /Safari\//.test(agent) ? "Safari" : "Browser";
  const platform = /Windows/i.test(agent) ? "Windows"
    : /Android/i.test(agent) ? "Android"
      : /iPhone/i.test(agent) ? "iPhone"
        : /iPad/i.test(agent) ? "iPad"
          : /Macintosh|Mac OS X/i.test(agent) ? "macOS"
            : /Linux/i.test(agent) ? "Linux" : "this device";
  return `${browser} on ${platform}`;
}

async function keepPairingStorage() {
  if (!navigator.storage?.persist) return;
  try { await navigator.storage.persist(); } catch { /* Browser storage remains usable without persistence. */ }
}
async function rpc(method, params = {}, requestId = crypto.randomUUID()) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);
  let response;
  try {
    response = await fetch("/v1/rpc", {
      method: "POST", cache: "no-store", redirect: "error", signal: controller.signal,
      headers: { "Content-Type": "application/json", "Authorization": `Bearer ${state.token}` },
      body: JSON.stringify({ version: 1, request_id: requestId, method, params }),
    });
  } catch (cause) {
    const error = new Error(cause?.name === "AbortError" ? "The gateway request timed out." : "The gateway connection was interrupted.");
    error.code = "TRANSPORT_UNAVAILABLE";
    throw error;
  } finally { clearTimeout(timeout); }
  const data = await response.json();
  if (response.status === 401) {
    closeEventStream();
    state.token = null;
    state.instanceId = null;
    state.epoch = null;
    state.threadId = null;
    state.commands = [];
    state.turnId = null;
    state.threadStatus = null;
    safeStore.remove(tokenKey());
    requireManualGatewayVerification();
    document.body.classList.remove("thread-open", "mobile-sessions", "mobile-connections", "mobile-settings");
    $("pair-panel").classList.remove("hidden");
    $("sessions-panel").classList.add("hidden");
    document.body.classList.add("pairing");
    connection(pairingStatus(), "offline");
  }
  if (!response.ok) {
    const error = new Error(apiError(data.error));
    error.code = data.error;
    error.httpStatus = response.status;
    throw error;
  }
  if (data.version !== 1 || data.request_id !== requestId || (!!data.result === !!data.error)) {
    throw new Error("Gateway response did not match this request.");
  }
  if (data.error) {
    const error = new Error(apiError(data.error.code));
    error.code = data.error.code;
    error.probeRejection = true;
    throw error;
  }
  return data.result;
}

function closeEventStream() {
  if (state.eventReconnectTimer) clearTimeout(state.eventReconnectTimer);
  state.eventReconnectTimer = null;
  const socket = state.eventSocket;
  state.eventSocket = null;
  state.eventThreadId = null;
  document.body.dataset.liveTransport = "polling";
  if (socket && socket.readyState < WebSocket.CLOSING) socket.close(1000, "Client view changed");
}

function startEventStream() {
  if (!state.token || !state.threadId || document.visibilityState === "hidden") return;
  if (state.eventSocket && state.eventThreadId === state.threadId
      && state.eventSocket.readyState <= WebSocket.OPEN) return;
  closeEventStream();
  const threadId = state.threadId;
  const url = new URL("/v1/events", location.href);
  url.protocol = location.protocol === "https:" ? "wss:" : "ws:";
  url.searchParams.set("thread_id", threadId);
  url.searchParams.set("after_sequence", String(state.sequence));
  const socket = new WebSocket(url, ["zedlink-v1", `zedlink-token-${state.token}`]);
  document.body.dataset.liveTransport = "connecting";
  state.eventSocket = socket;
  state.eventThreadId = threadId;
  socket.addEventListener("open", () => {
    if (state.eventSocket === socket) {
      document.body.dataset.liveTransport = "websocket";
    }
  });
  socket.addEventListener("message", (event) => {
    if (state.eventSocket !== socket || state.threadId !== threadId) return;
    try {
      const data = JSON.parse(event.data);
      if (data.error) throw Object.assign(new Error(apiError(data.error.code)), { code: data.error.code });
      const result = data.result;
      identity(result);
      if (result.thread_id !== threadId || !Array.isArray(result.events)) throw new Error("Invalid live event response.");
      connection("Live with Zed", "online");
      if (Number.isInteger(result.last_sequence)) state.sequence = Math.max(state.sequence, result.last_sequence);
      if (result.events.length || (state.threadStatus && state.threadStatus !== "Idle")) {
        refreshSnapshot().catch((error) => notice(error.message));
      }
    } catch (error) {
      if (error.code === "UNAUTHENTICATED") {
        state.token = null;
        safeStore.remove(tokenKey());
      }
      connection(error.code === "INSTANCE_UNAVAILABLE" ? "Zed unavailable" : "Reconnecting…", "offline");
      socket.close();
    }
  });
  socket.addEventListener("close", () => {
    if (state.eventSocket !== socket) return;
    state.eventSocket = null;
    state.eventThreadId = null;
    document.body.dataset.liveTransport = "polling";
    if (state.token && state.threadId === threadId && document.visibilityState !== "hidden") {
      state.eventReconnectTimer = setTimeout(startEventStream, 1200);
    }
  });
  socket.addEventListener("error", () => { /* Close triggers bounded polling and reconnect. */ });
}

async function loadGateway() {
  const pairingLink = new URLSearchParams(location.hash.slice(1));
  const oneScanCode = pairingLink.get("pair");
  const expectedFromLink = pairingLink.get("gateway");
  if (oneScanCode) history.replaceState(null, "", location.pathname + location.search);
  try {
    const response = await fetch("/v1/gateway", { cache: "no-store", redirect: "error" });
    const result = await response.json();
    if (!response.ok || result.version !== 1 || typeof result.gateway_id !== "string") {
      throw new Error("Unsupported gateway identity response.");
    }
    state.gatewayId = result.gateway_id;
    $("gateway-id").textContent = result.gateway_id;
    $("mobile-gateway-id").textContent = result.gateway_id;
    $("pair-origin").textContent = location.origin;
    $("expected-id").value = result.gateway_id;
    requireManualGatewayVerification();
    document.body.classList.toggle("sidebar-collapsed", safeStore.read(sidebarKey()) === "true");
    updateSidebarToggle();
    if (expectedFromLink) {
      $("expected-id").value = expectedFromLink;
      if (expectedFromLink !== result.gateway_id) {
        throw new Error("The gateway identity differs from the desktop pairing link. Do not enter a code.");
      }
      acceptLinkedGateway();
    }
    const token = safeStore.read(tokenKey());
    if (token) {
      state.token = token;
      await connect();
    } else if (oneScanCode) {
      if (pairingLink.get("v") !== "1" || !expectedFromLink || !/^[0-9]{10}$/.test(oneScanCode)) {
        throw new Error("Invalid one-scan pairing link. Use the manual 10-digit code instead.");
      }
      connection("Pairing this browser…");
      $("pair-button").disabled = true;
      try {
        await pairBrowser(oneScanCode, browserDeviceName());
      } catch (error) {
        connection(pairingStatus());
        notice(`Automatic pairing failed: ${error.message} Enter a fresh code from the workstation.`);
      } finally { $("pair-button").disabled = !state.gatewayVerified; }
    } else {
      connection(pairingStatus());
    }
  } catch (error) {
    connection(error.message.includes("gateway identity differs") ? "Gateway identity mismatch"
      : error.message.includes("pairing link") ? "Pairing link invalid" : "Gateway unavailable", "offline");
    notice(error.message);
  }
}

async function pairBrowser(code, deviceName) {
  const response = await fetch("/v1/pair", {
    method: "POST", cache: "no-store", redirect: "error",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code, device_name: deviceName }),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(apiError(result.error));
  if (result.gateway_id !== state.gatewayId || !/^[0-9a-f]{64}$/.test(result.token)) {
    throw new Error("Pairing identity or token was invalid.");
  }
  state.token = result.token;
  const remembered = safeStore.write(tokenKey(), result.token);
  await keepPairingStorage();
  $("pair-code").value = "";
  notice(remembered ? "" : "This browser did not allow persistent storage; pairing may be needed after this tab closes.");
  await connect();
}

async function connect() {
  if (!state.token) return;
  connection("Connecting…");
  document.body.classList.remove("pairing");
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
    state.capabilities = Array.isArray(info.capabilities) ? info.capabilities : [];
    showCreateAvailability();
    if (changed) {
      closeEventStream();
      state.threadId = null;
      state.commands = [];
      renderCommands();
      state.turnId = null;
      state.threadStatus = null;
      showStop();
      document.body.classList.remove("thread-open", "mobile-sessions");
      state.sequence = 0;
      notice("Desktop Zed restarted. Select an exposed thread again; uncertain sends were not repeated.");
    }
    $("host-label").textContent = `Zed instance ${info.instance_id.slice(0, 8)}…`;
    const prior = safeStore.read(pendingKey());
    if (prior && !state.pending) {
      try { state.pending = { ...JSON.parse(prior), text: null }; } catch { safeStore.remove(pendingKey()); }
      if (state.pending) delivery("A previous message may have reached Zed. Check the conversation before continuing.", true);
    }
    await loadThreads();
    if (!state.threadId) {
      const selected = safeStore.read(selectedThreadKey());
      if (selected && state.threads.some((thread) => thread.thread_id === selected)) {
        await selectThread(selected);
      }
    }
    if (state.threadId) startEventStream();
    connection(state.eventSocket?.readyState === WebSocket.OPEN ? "Live with Zed" : "Connected to Zed", "online");
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
    closeEventStream();
    state.threadId = null;
    safeStore.remove(selectedThreadKey());
    state.commands = [];
    renderCommands();
    state.turnId = null;
    state.threadStatus = null;
    showStop();
    document.body.classList.remove("thread-open", "mobile-sessions");
    state.sequence = 0;
    $("transcript-entries").replaceChildren();
    $("activity").classList.add("hidden");
    $("prompt").disabled = true;
    $("thread-title").textContent = "Choose a session";
    $("thread-state").textContent = "Select session";
    $("thread-state").className = "state-pill";
    notice("The selected thread is no longer exposed in desktop Zed.");
  }
}

async function createSession(event) {
  event.preventDefault();
  if (state.creatingThread || !state.capabilities.includes("thread.create")) return;
  const requestId = crypto.randomUUID();
  const title = $("new-session-title").value.trim();
  state.creatingThread = true;
  $("create-session").disabled = true;
  showCreateAvailability();
  notice("Creating a native Zed Agent session…");
  try {
    for (let attempt = 0; attempt < 40; attempt += 1) {
      const result = await rpc("thread.create", {
        instance_id: state.instanceId,
        epoch: state.epoch,
        title: title || null,
      }, requestId);
      if (result.outcome === "ready" && typeof result.thread_id === "string") {
        $("new-session-title").value = "";
        $("new-session-form").classList.add("hidden");
        await loadThreads();
        await selectThread(result.thread_id);
        notice("");
        return;
      }
      if (result.outcome !== "creating") throw new Error("Zed returned an invalid creation state.");
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
    throw new Error("Zed is still connecting the new session. Refresh Sessions to check its status.");
  } catch (error) {
    notice(`Could not create the session: ${error.message}`);
  } finally {
    state.creatingThread = false;
    $("create-session").disabled = false;
    showCreateAvailability();
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
  closeEventStream();
  state.threadId = threadId;
  safeStore.write(selectedThreadKey(), threadId);
  state.commands = [];
  renderCommands();
  state.turnId = null;
  state.threadStatus = null;
  showStop();
  document.body.classList.add("thread-open");
  document.body.classList.remove("mobile-sessions");
  updateSidebarToggle();
  state.sequence = 0;
  state.renderedEntries = [];
  state.renderedThreadId = null;
  state.activitySignature = null;
  state.activityCollapsed = true;
  state.activityBusy = false;
  $("activity").classList.add("hidden");
  $("prompt").disabled = false;
  $("jump-latest").classList.add("hidden");
  $("send").disabled = !!state.pending;
  $("thread-title").textContent = state.threads.find((thread) => thread.thread_id === threadId)?.title || "Untitled Agent thread";
  await loadThreads();
  try {
    await refreshSnapshot();
    await loadCommands();
    startEventStream();
    notice("");
  } catch (error) { notice(error.message); }
}

async function loadCommands() {
  if (!state.capabilities.includes("thread.commands") || !state.threadId) return;
  const threadId = state.threadId;
  const result = await rpc("thread.commands", {
    instance_id: state.instanceId, epoch: state.epoch, thread_id: threadId,
  });
  if (result.thread_id !== threadId || !Array.isArray(result.commands)) throw new Error("Invalid command list.");
  if (state.threadId === threadId) {
    state.commands = result.commands.filter((command) =>
      typeof command.name === "string" && typeof command.description === "string");
    renderCommands();
  }
}

function renderCommands() {
  const menu = $("command-menu");
  const query = $("prompt").value.trimStart();
  const searching = query.startsWith("/") && !query.slice(1).includes(" ") && !query.includes("\n");
  const visible = state.commands.filter((command) =>
    !searching || command.name.toLocaleLowerCase().includes(query.slice(1).toLocaleLowerCase()));
  menu.replaceChildren();
  for (const command of visible) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "command-option";
    button.setAttribute("role", "option");
    const name = document.createElement("strong");
    name.textContent = `/${command.name}`;
    const description = document.createElement("span");
    description.textContent = command.description;
    const category = document.createElement("small");
    category.textContent = command.category === "native" ? "Zed" : command.category === "mcp" ? "MCP" : "Agent";
    button.append(name, description, category);
    button.addEventListener("click", () => {
      $("prompt").value = `/${command.name}${command.requires_argument ? " " : ""}`;
      menu.classList.add("hidden");
      $("prompt").focus();
    });
    menu.append(button);
  }
  if (searching && !visible.length) {
    const empty = document.createElement("p");
    empty.textContent = state.commands.length ? "No matching command in this thread." : "This Zed build has not provided a command list.";
    menu.append(empty);
  } else if (searching && query === "/") {
    const hint = document.createElement("p");
    hint.className = "command-hint";
    hint.textContent = "Shows commands available in this Agent thread. Desktop controls stay in Zed.";
    menu.append(hint);
  }
  menu.classList.toggle("hidden", !searching || (!state.threadId && !visible.length));
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
  if (tool) return { kind: "tool", label: tool[1], status: tool[2], body: markdown.slice(tool[0].length) };
  return { kind: "native", label: `Native entry ${index + 1}`, body: markdown };
}

function appendInline(target, value) {
  const pattern = /(!?\[[^\]\n]+\]\([^\s)]+\)|`[^`\n]+`|\*\*[^*\n]+\*\*)/g;
  let cursor = 0;
  for (const match of value.matchAll(pattern)) {
    if (match.index > cursor) target.append(document.createTextNode(value.slice(cursor, match.index)));
    if (match[0].startsWith("`")) {
      const code = document.createElement("code");
      code.textContent = match[0].slice(1, -1);
      target.append(code);
    } else if (match[0].startsWith("**")) {
      const strong = document.createElement("strong");
      strong.textContent = match[0].slice(2, -2);
      target.append(strong);
    } else {
      const parsed = match[0].match(/^(!?)\[([^\]]+)\]\(([^)]+)\)$/);
      const url = parsed?.[3];
      let safe = null;
      try {
        const candidate = new URL(url, location.href);
        if (["https:", "http:"].includes(candidate.protocol)) safe = candidate.href;
      } catch { /* Render invalid or local links as plain text. */ }
      if (safe) {
        const link = document.createElement("a");
        link.href = safe;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = parsed[1] ? `Image: ${parsed[2]}` : parsed[2];
        target.append(link);
      } else {
        target.append(document.createTextNode(parsed ? parsed[2] : match[0]));
      }
    }
    cursor = match.index + match[0].length;
  }
  if (cursor < value.length) target.append(document.createTextNode(value.slice(cursor)));
}

function appendCodeBlock(target, value, language = "") {
  const wrapper = document.createElement("section");
  wrapper.className = "code-block";
  const heading = document.createElement("div");
  heading.className = "code-block-head";
  const label = document.createElement("span");
  label.textContent = language || "Code";
  const copy = document.createElement("button");
  copy.type = "button";
  copy.className = "message-copy";
  copy.textContent = "Copy code";
  copy.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(value); copy.textContent = "Copied"; }
    catch { notice("Clipboard access is unavailable in this browser."); }
  });
  heading.append(label, copy);
  const pre = document.createElement("pre");
  const code = document.createElement("code");
  if (language) code.className = `language-${language.replace(/[^a-z0-9_-]/gi, "")}`;
  code.textContent = value;
  pre.append(code);
  wrapper.append(heading, pre);
  target.append(wrapper);
}

function tableCells(line) {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
}

function renderBody(target, source) {
  const lines = source.trim().split(/\r?\n/);
  for (let i = 0; i < lines.length;) {
    const line = lines[i];
    if (!line.trim()) { i += 1; continue; }
    if (line.startsWith("```")) {
      const language = line.slice(3).trim().split(/\s+/, 1)[0];
      const block = [];
      i += 1;
      while (i < lines.length && !lines[i].startsWith("```")) block.push(lines[i++]);
      if (i < lines.length) i += 1;
      appendCodeBlock(target, block.join("\n"), language);
      continue;
    }
    if (line === "<thinking>") {
      const block = [];
      i += 1;
      while (i < lines.length && lines[i] !== "</thinking>") block.push(lines[i++]);
      if (i < lines.length) i += 1;
      const details = document.createElement("details");
      details.className = "thinking-block";
      const summary = document.createElement("summary");
      summary.textContent = "Thinking";
      const content = document.createElement("div");
      renderBody(content, block.join("\n"));
      details.append(summary, content);
      target.append(details);
      continue;
    }
    if (line.includes("|") && i + 1 < lines.length
        && /^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(lines[i + 1])) {
      const headers = tableCells(line);
      i += 2;
      const wrapper = document.createElement("div");
      wrapper.className = "table-scroll";
      const table = document.createElement("table");
      const thead = document.createElement("thead");
      const headerRow = document.createElement("tr");
      for (const value of headers) {
        const cell = document.createElement("th");
        appendInline(cell, value);
        headerRow.append(cell);
      }
      thead.append(headerRow);
      const tbody = document.createElement("tbody");
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) {
        const row = document.createElement("tr");
        for (const value of tableCells(lines[i])) {
          const cell = document.createElement("td");
          appendInline(cell, value);
          row.append(cell);
        }
        tbody.append(row);
        i += 1;
      }
      table.append(thead, tbody);
      wrapper.append(table);
      target.append(wrapper);
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

function toolPreview(body, status) {
  const line = body.split(/\r?\n/).map((value) => value.trim())
    .find((value) => value && !value.startsWith("```") && value !== "Terminal:" && !value.startsWith("Diff: "));
  if (line) return line.slice(0, 240);
  return /Pending|InProgress|Waiting/i.test(status) ? "Waiting for tool output…" : "No text output shared by Zed.";
}

function renderToolBody(target, body) {
  const pattern = /^(Terminal:|Diff: ([^\n]+))\r?\n```([^\n]*)\r?\n([\s\S]*?)\r?\n```(?=\r?\n|$)/gm;
  let cursor = 0;
  let matched = false;
  for (const match of body.matchAll(pattern)) {
    matched = true;
    if (match.index > cursor) {
      const before = document.createElement("div");
      before.className = "message-body";
      renderBody(before, body.slice(cursor, match.index));
      target.append(before);
    }
    const section = document.createElement("section");
    section.className = "tool-output";
    const heading = document.createElement("div");
    heading.className = "tool-output-heading";
    const label = document.createElement("strong");
    label.textContent = match[1] === "Terminal:" ? "Terminal output" : `File content · ${match[2]}`;
    const copy = document.createElement("button");
    copy.type = "button";
    copy.className = "message-copy";
    copy.textContent = "Copy output";
    copy.setAttribute("aria-label", `Copy ${match[1] === "Terminal:" ? "terminal output" : "file content"}`);
    copy.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(match[4]); copy.textContent = "Copied"; }
      catch { notice("Clipboard access is unavailable in this browser."); }
    });
    heading.append(label, copy);
    const pre = document.createElement("pre");
    const code = document.createElement("code");
    code.textContent = match[4];
    pre.append(code);
    section.append(heading, pre);
    target.append(section);
    cursor = match.index + match[0].length;
  }
  if (!matched || cursor < body.length) {
    const remaining = document.createElement("div");
    remaining.className = "message-body";
    renderBody(remaining, body.slice(cursor));
    target.append(remaining);
  }
}

function makeEntry(markdown, index) {
  const presentation = entryPresentation(markdown, index);
  const article = document.createElement("article");
  article.className = `message ${presentation.kind}`;
  article.dataset.entryIndex = String(index);
  const heading = document.createElement("div");
  heading.className = "message-heading";
  const label = document.createElement("div");
  label.className = "message-label";
  label.textContent = presentation.kind === "tool" ? "Zed tool" : presentation.label;
  const copy = document.createElement("button");
  copy.type = "button";
  copy.className = "message-copy";
  copy.textContent = "Copy";
  copy.setAttribute("aria-label", `Copy ${presentation.label} content`);
  copy.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(presentation.body); copy.textContent = "Copied"; }
    catch { notice("Clipboard access is unavailable in this browser."); }
  });
  heading.append(label, copy);
  if (presentation.kind === "tool") {
    const title = document.createElement("div");
    title.className = "tool-title";
    title.textContent = presentation.label;
    const status = document.createElement("span");
    status.className = `tool-state ${/Failed|Rejected|Canceled/i.test(presentation.status) ? "failed" : /Pending|InProgress|Waiting/i.test(presentation.status) ? "working" : ""}`;
    status.textContent = presentation.status;
    const preview = document.createElement("p");
    preview.className = "tool-preview";
    preview.textContent = toolPreview(presentation.body, presentation.status);
    const details = document.createElement("details");
    details.className = "tool-details";
    const active = /Pending|InProgress|In Progress|Waiting/i.test(presentation.status);
    details.open = active;
    details.dataset.autoOpen = String(active);
    details.dataset.userToggled = "false";
    const summary = document.createElement("summary");
    summary.textContent = active ? "Hide live tool output" : "Read tool output";
    summary.addEventListener("click", () => { details.dataset.userToggled = "true"; });
    details.addEventListener("toggle", () => {
      summary.textContent = details.open
        ? active ? "Hide live tool output" : "Hide tool output"
        : active ? "Show live tool output" : "Read tool output";
    });
    const content = document.createElement("div");
    content.className = "tool-content";
    renderToolBody(content, presentation.body);
    details.append(summary, content);
    article.append(heading, title, status, preview, details);
  } else {
    const content = document.createElement("div");
    content.className = "message-body";
    renderBody(content, presentation.body);
    article.append(heading, content);
  }
  return article;
}

function renderActivity(entries, status, activityTruncated = false) {
  const panel = $("activity");
  const busy = status !== "Idle";
  if (busy !== state.activityBusy) {
    state.activityCollapsed = !busy;
    state.activityBusy = busy;
  }
  panel.classList.toggle("busy", busy);
  $("activity-state").textContent = busy ? "Live" : "Complete";
  const lastUser = entries.findLastIndex((entry) => /^## User(?: \(checkpoint\))?\n\n/.test(entry));
  const recent = entries.slice(Math.max(0, lastUser + 1));
  const updates = [];
  for (const markdown of recent) {
    if (markdown.startsWith("## Assistant\n\n")) {
      for (const match of markdown.matchAll(/<thinking>\n([\s\S]*?)(?:\n<\/thinking>|$)/g)) {
        const value = match[1].trim();
        if (value) updates.push({ kind: "reasoning", label: "Thinking", body: value });
      }
    } else {
      const tool = markdown.match(/^\*\*Tool Call: ([^\n]*?)\*\*\nStatus: ([^\n]*)\n\n/);
      if (tool) updates.push({ kind: "tool", label: tool[1], status: tool[2], body: markdown.slice(tool[0].length) });
      else if (markdown.startsWith("## Plan\n\n")) updates.push({ kind: "plan", label: "Plan", body: markdown.slice(9).trim() });
      else if (markdown.startsWith("## Context Compaction")) updates.push({ kind: "context", label: "Context compaction", body: markdown.replace(/^## Context Compaction[^\n]*\n\n/, "").trim() });
      else if (markdown.startsWith("## Input Requested")) updates.push({ kind: "approval", label: "Approval", body: "Input requested in desktop Zed" });
    }
  }
  $("activity-title").textContent = busy ? "Zed is working" : `Turn activity${updates.length ? ` · ${updates.length}` : ""}`;
  panel.classList.toggle("hidden", !busy && !updates.length);
  panel.classList.toggle("collapsed", state.activityCollapsed);
  $("activity-toggle").textContent = state.activityCollapsed ? "View" : "Close";
  $("activity-toggle").setAttribute("aria-expanded", String(!state.activityCollapsed));
  const content = $("activity-content");
  const signature = JSON.stringify([status, updates, activityTruncated]);
  if (state.activitySignature === signature) return;
  state.activitySignature = signature;
  content.replaceChildren();
  if (!updates.length) {
    const empty = document.createElement("div");
    empty.className = "activity-item";
    empty.textContent = "Waiting for reasoning or tool activity shared by the native Zed thread…";
    content.append(empty);
  }
  for (const update of updates) {
    const item = document.createElement("section");
    item.className = "activity-item";
    const heading = document.createElement("strong");
    heading.textContent = update.kind === "tool" ? `Tool · ${update.label}` : update.label;
    item.append(heading);
    if (update.kind === "tool") {
      const status = document.createElement("span");
      status.className = `tool-state ${/Failed|Rejected|Canceled/i.test(update.status) ? "failed" : /Pending|InProgress|In Progress|Waiting/i.test(update.status) ? "working" : ""}`;
      status.textContent = update.status;
      const output = document.createElement("div");
      output.className = "tool-content";
      renderToolBody(output, update.body);
      item.append(status, output);
    } else {
      const body = document.createElement("div");
      body.className = "message-body";
      renderBody(body, update.body);
      item.append(body);
    }
    content.append(item);
  }
  if (activityTruncated) {
    const note = document.createElement("p");
    note.className = "activity-note";
    note.textContent = "Earlier activity is omitted from this live window.";
    content.prepend(note);
  }
}

async function refreshSnapshot() {
  state.snapshotQueued = true;
  if (!state.snapshotPromise) {
    state.snapshotPromise = (async () => {
      while (state.snapshotQueued && state.threadId) {
        state.snapshotQueued = false;
        await snapshot();
      }
    })();
    try { await state.snapshotPromise; }
    finally { state.snapshotPromise = null; }
  } else {
    await state.snapshotPromise;
  }
}

async function snapshot() {
  if (!state.threadId) return;
  const threadId = state.threadId;
  const result = await rpc("thread.snapshot", { thread_id: threadId });
  if (state.threadId !== threadId) return;
  identity(result);
  if (result.thread_id !== state.threadId || !Array.isArray(result.entries_markdown)
      || !result.entries_markdown.every((entry) => typeof entry === "string")) {
    throw new Error("Snapshot belongs to another thread.");
  }
  state.sequence = result.last_sequence;
  state.lastSnapshotAt = Date.now();
  const scroller = $("messages");
  const container = $("transcript-entries");
  const follow = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 90;
  if (state.renderedThreadId !== result.thread_id) {
    container.replaceChildren();
    state.renderedEntries = [];
    state.renderedThreadId = result.thread_id;
  }
  for (const [index, markdown] of result.entries_markdown.entries()) {
    if (state.renderedEntries[index] === markdown) continue;
    const article = makeEntry(markdown, index);
    const previous = container.children[index];
    if (previous) {
      const oldDetails = previous.querySelector("details");
      const newDetails = article.querySelector("details");
      if (oldDetails && newDetails && oldDetails.dataset.userToggled === "true") {
        newDetails.open = oldDetails.open;
        newDetails.dataset.userToggled = "true";
      }
      previous.replaceWith(article);
    } else container.append(article);
    state.renderedEntries[index] = markdown;
  }
  while (container.children.length > result.entries_markdown.length) container.lastElementChild.remove();
  state.renderedEntries.length = result.entries_markdown.length;
  const busy = result.status !== "Idle";
  for (const details of container.querySelectorAll("details.thinking-block")) details.open = false;
  if (busy) {
    const assistants = container.querySelectorAll(".message.assistant");
    assistants[assistants.length - 1]?.querySelectorAll("details.thinking-block").forEach((details) => { details.open = true; });
  }
  $("thread-title").textContent = result.title || "Untitled Agent thread";
  $("thread-meta").textContent = result.truncated ? "Older conversation omitted here · Full history remains in Zed" : `Thread ${result.thread_id.slice(0, 12)}…`;
  $("thread-state").textContent = result.status;
  $("thread-state").className = `state-pill ${result.status === "Idle" ? "online" : ""}`;
  const activityEntries = Array.isArray(result.activity_entries_markdown)
    && result.activity_entries_markdown.every((entry) => typeof entry === "string")
    ? result.activity_entries_markdown : result.entries_markdown;
  renderActivity(activityEntries, result.status, result.activity_truncated === true);
  if (follow) {
    scroller.scrollTop = scroller.scrollHeight;
    $("jump-latest").classList.add("hidden");
  } else if (result.entries_markdown.length) {
    $("jump-latest").classList.remove("hidden");
  }
  state.turnId = Number.isInteger(result.current_turn_id) ? result.current_turn_id : null;
  state.threadStatus = result.status;
  showStop();
  if (result.pending_approvals?.length) {
    notice("Approval pending in desktop Zed. Remote approval controls are awaiting native race validation.");
  }
}

async function reconcilePending() {
  if (!state.pending || !state.token) return;
  const pending = state.pending;
  if (pending.instanceId !== state.instanceId || pending.epoch !== state.epoch) {
    delivery("Zed restarted while a message was pending. Check the desktop conversation before continuing.", true);
    return;
  }
  const result = await rpc("request.status", {
    instance_id: pending.instanceId, epoch: pending.epoch, original_request_id: pending.id,
  });
  if (result.known) {
    settledDelivery("Zed recorded the original request. The conversation will show its progress.");
    if (state.threadId === pending.threadId) await refreshSnapshot();
  } else {
    delivery("The previous send is still unconfirmed. It has not been sent again.", true);
  }
}

async function poll() {
  if (!state.token || state.polling) return;
  state.polling = true;
  try {
    if (!state.instanceId) { await connect(); return; }
    if (state.threadId) {
      const streamLive = state.eventSocket?.readyState === WebSocket.OPEN
        && state.eventThreadId === state.threadId;
      if (!streamLive) {
        const result = await rpc("thread.events", { thread_id: state.threadId, after_sequence: state.sequence });
        identity(result);
        if (result.thread_id !== state.threadId) throw new Error("Event feed changed threads.");
        if (result.events?.length) await refreshSnapshot();
        else state.sequence = result.last_sequence;
        startEventStream();
      }
      if ((state.threadStatus && state.threadStatus !== "Idle") || Date.now() - state.lastSnapshotAt > 3000) {
        await refreshSnapshot();
      }
    } else await loadThreads();
    if (state.pending) await reconcilePending();
    connection(state.eventSocket?.readyState === WebSocket.OPEN ? "Live with Zed" : "Connected to Zed", "online");
  } catch (error) {
    if (error.code === "RESYNC_REQUIRED") {
      try { await refreshSnapshot(); return; } catch (snapshotError) { notice(snapshotError.message); }
    } else if (error.code === "THREAD_NOT_EXPOSED" || error.code === "IDENTITY_CHANGED") {
      await connect();
      return;
    } else {
      notice(error.message);
    }
    connection(error.code === "UNAUTHENTICATED" ? pairingStatus()
      : error.code === "INSTANCE_UNAVAILABLE" ? "Zed unavailable" : "Reconnecting…", "offline");
  } finally { state.polling = false; }
}

async function sendPrompt(event) {
  event.preventDefault();
  if (!state.threadId || !state.token || state.pending) return;
  const text = $("prompt").value.trim();
  if (!text) return;
  if (text.startsWith("/")) {
    const name = text.slice(1).split(/\s/, 1)[0];
    if (!state.capabilities.includes("thread.commands")) {
      notice("This running Zed build cannot execute slash commands remotely yet. Restart the updated build and re-expose the thread.");
      return;
    }
    if (!state.commands.some((command) => command.name === name)) {
      notice(`/${name} is not available in this native Agent thread. Choose a command from the list.`);
      renderCommands();
      return;
    }
  }
  $("command-menu").classList.add("hidden");
  const pending = { id: crypto.randomUUID(), instanceId: state.instanceId,
    epoch: state.epoch, threadId: state.threadId, text };
  state.pending = pending;
  savePending();
  delivery("Sending to Zed…");
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
    $("prompt").value = "";
    settledDelivery(result.outcome === "queued"
      ? "Queued in desktop Zed."
      : "Request reached Zed. Watch the native conversation for execution.");
  } catch (error) {
    if (error.probeRejection || (error.httpStatus >= 400 && error.httpStatus < 500)) {
      clearPending();
      notice(`Zed rejected the message: ${error.message}`);
    } else {
      delivery(`Could not confirm delivery. ${error.message} Check the conversation before continuing.`, true);
    }
    return;
  }
  try {
    if (state.threadId === pending.threadId) await refreshSnapshot();
    $("messages").scrollTop = $("messages").scrollHeight;
  } catch (error) { notice(`Request reached Zed; conversation refresh failed: ${error.message}`); }
}

$("pair-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.gatewayId) return;
  if (!state.gatewayVerified) {
    notice("Compare the HTTPS address and Gateway ID with the workstation pairing page, then check the confirmation box.");
    return;
  }
  if ($("expected-id").value.trim() !== state.gatewayId) {
    notice("Gateway ID differs from the workstation value. Pairing code was not sent.");
    return;
  }
  const code = $("pair-code").value.trim().replace(/[\s-]/g, "");
  if (!/^([0-9]{10}|[0-9a-fA-F]{64})$/.test(code)) { notice("Enter the 10-digit pairing code from the workstation."); return; }
  $("pair-button").disabled = true;
  try {
    await pairBrowser(code, $("device-name").value.trim());
  } catch (error) { notice(error.message); }
  finally { $("pair-button").disabled = !state.gatewayVerified; }
});
$("verify-gateway").addEventListener("change", () => {
  state.gatewayVerified = $("verify-gateway").checked;
  $("pair-button").disabled = !state.gatewayVerified;
});
$("refresh").addEventListener("click", () => connect());
$("new-session").addEventListener("click", () => {
  const form = $("new-session-form");
  form.classList.toggle("hidden");
  if (!form.classList.contains("hidden")) $("new-session-title").focus();
});
$("new-session-form").addEventListener("submit", createSession);
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
$("stop-turn").addEventListener("click", async () => {
  const { instanceId, epoch, threadId, turnId } = state;
  if (!threadId || !Number.isInteger(turnId) || !state.capabilities.includes("thread.cancel")) return;
  $("stop-turn").disabled = true;
  try {
    const result = await rpc("thread.cancel", {
      instance_id: instanceId, epoch, thread_id: threadId, turn_id: turnId,
    });
    if (result.outcome !== "requested" || result.turn_id !== turnId) {
      throw new Error("Zed did not confirm the stop request for this turn.");
    }
    notice("Stop requested for this turn.");
    setTimeout(() => {
      if ($("notice").textContent === "Stop requested for this turn.") notice("");
    }, 5000);
  } catch (error) {
    notice(error.message);
  } finally {
    try { await refreshSnapshot(); } catch (error) { notice(error.message); }
    $("stop-turn").disabled = false;
  }
});
$("show-sessions").addEventListener("click", () => {
  if (matchMedia("(max-width: 760px)").matches) {
    document.body.classList.add("mobile-sessions");
  } else {
    document.body.classList.toggle("sidebar-collapsed");
    safeStore.write(sidebarKey(), String(document.body.classList.contains("sidebar-collapsed")));
  }
  updateSidebarToggle();
});
$("prompt").addEventListener("input", () => {
  const prompt = $("prompt");
  prompt.style.height = "auto";
  prompt.style.height = `${Math.min(prompt.scrollHeight, 150)}px`;
  renderCommands();
});
$("show-commands").addEventListener("click", () => {
  if (!state.threadId) return;
  $("prompt").value = "/";
  $("prompt").focus();
  renderCommands();
});
$("prompt").addEventListener("keydown", (event) => {
  if (event.key === "Escape") $("command-menu").classList.add("hidden");
  if (event.key === "ArrowDown" && !$("command-menu").classList.contains("hidden")) {
    const first = $("command-menu").querySelector(".command-option");
    if (first) { event.preventDefault(); first.focus(); }
  }
  if (event.key === "Enter" && !event.shiftKey && (event.ctrlKey || event.metaKey || matchMedia("(pointer: fine)").matches)) {
    event.preventDefault();
    $("composer-form").requestSubmit();
  }
});
function forgetBrowser() {
  closeEventStream();
  safeStore.remove(tokenKey());
  safeStore.remove(pendingKey());
  safeStore.remove(selectedThreadKey());
  state.token = null;
  state.pending = null;
  state.threadId = null;
  requireManualGatewayVerification();
  document.body.classList.remove("thread-open", "mobile-sessions", "mobile-connections", "mobile-settings");
  document.body.classList.add("pairing");
  $("pair-panel").classList.remove("hidden");
  $("sessions-panel").classList.add("hidden");
  $("transcript-entries").replaceChildren();
  $("activity").classList.add("hidden");
  $("prompt").disabled = true;
  delivery("");
  connection("Browser token forgotten");
  notice("This only removes the tab token. Revoke the paired device through the workstation admin command.");
}
$("forget").addEventListener("click", forgetBrowser);
$("mobile-forget").addEventListener("click", forgetBrowser);
$("composer-form").addEventListener("submit", sendPrompt);
$("activity-toggle").addEventListener("click", () => {
  state.activityCollapsed = !state.activityCollapsed;
  $("activity").classList.toggle("collapsed", state.activityCollapsed);
  $("activity-toggle").textContent = state.activityCollapsed ? "View" : "Close";
  $("activity-toggle").setAttribute("aria-expanded", String(!state.activityCollapsed));
});
$("retry").addEventListener("click", sendPending);
$("clear-pending").addEventListener("click", () => {
  clearPending();
  notice("You can send again. If the previous message appears in Zed, avoid sending it a second time.");
});
setInterval(poll, 750);
window.addEventListener("hashchange", () => loadGateway());
function resumeLiveUpdates() {
  if (!state.token || document.visibilityState === "hidden") return;
  if (!state.instanceId) {
    connect();
    return;
  }
  if (state.threadId) {
    startEventStream();
    refreshSnapshot().catch((error) => notice(error.message));
  }
  poll();
}
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") closeEventStream();
  else resumeLiveUpdates();
});
window.addEventListener("pageshow", resumeLiveUpdates);
window.addEventListener("focus", resumeLiveUpdates);
window.addEventListener("online", resumeLiveUpdates);

function showMobileView(view) {
  document.body.classList.remove("mobile-connections", "mobile-settings");
  for (const button of document.querySelectorAll("[data-mobile-view]")) {
    if (button.dataset.mobileView === view) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  }
  if (view === "sessions") {
    document.body.classList.add("mobile-sessions");
  } else if (view === "connections") {
    document.body.classList.remove("mobile-sessions");
    if (state.token) document.body.classList.add("mobile-connections");
    else {
      document.body.classList.remove("thread-open");
      $("pair-panel").classList.remove("hidden");
      $("sessions-panel").classList.add("hidden");
    }
  } else {
    document.body.classList.remove("mobile-sessions");
    document.body.classList.add("mobile-settings");
  }
  updateSidebarToggle();
}
for (const button of document.querySelectorAll("[data-mobile-view]")) {
  button.addEventListener("click", () => showMobileView(button.dataset.mobileView));
}

let installPrompt = null;
window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  installPrompt = event;
  $("install-app").classList.remove("hidden");
  $("install-help").textContent = "Install ZedLink as a standalone home-screen app.";
});
$("install-app").addEventListener("click", async () => {
  if (!installPrompt) return;
  await installPrompt.prompt();
  installPrompt = null;
  $("install-app").classList.add("hidden");
});
window.addEventListener("appinstalled", () => {
  $("install-app").classList.add("hidden");
  $("install-help").textContent = "ZedLink is installed on this device.";
});
function showInstallHelp() {
  const agent = navigator.userAgent || "";
  if (/Firefox\//.test(agent) && !/Android/i.test(agent)) {
    $("install-help").textContent = "Firefox desktop does not install this PWA. Bookmark or pin this secure page; all ZedLink features still work.";
  } else if (/iPhone|iPad/i.test(agent)) {
    $("install-help").textContent = "In Safari, open Share and choose Add to Home Screen.";
  } else if (/Android/i.test(agent)) {
    $("install-help").textContent = "Open the browser menu and choose Install app or Add to Home screen.";
  } else {
    $("install-help").textContent = "Chrome and Edge can install ZedLink from the address bar. You can also bookmark this page.";
  }
}
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/service-worker.js")
    .catch(() => { /* HTTPS app remains usable without offline shell caching. */ }));
}
$("ui-build").textContent = UI_BUILD;
$("device-name").value = browserDeviceName();
showInstallHelp();
window.addEventListener("resize", updateSidebarToggle);
updateSidebarToggle();
loadGateway();
