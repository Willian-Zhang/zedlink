"use strict";

const $ = (id) => document.getElementById(id);
const UI_BUILD = "2026.10.12.14";
const DELEGATE_TASK_TEMPLATE = "Use the native spawn_agent tool to delegate the following task to a child Zed Agent. Keep the child scoped to this project and return its result in this conversation:\n\nTask: ";
const state = {
  gatewayId: null,
  token: null,
  targets: [],
  targetId: null,
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
  renderedEntryStart: 0,
  totalEntries: 0,
  historyLoading: false,
  creatingThread: false,
  createOptions: null,
  eventSocket: null,
  eventThreadId: null,
  eventReconnectTimer: null,
  eventConnectTimer: null,
  streamState: "idle",
  streamReconnectAttempt: 0,
  lastLiveEventAt: 0,
  gatewayReachable: null,
  desktopReachable: null,
  connectionMessage: "Checking gateway…",
  connectionStatus: "",
  threadError: null,
  retryStatus: null,
  imageRecovery: null,
  rewindingImage: false,
  errorSignature: null,
  snapshotPromise: null,
  snapshotQueued: false,
  lastSnapshotAt: 0,
  lastThreadsAt: 0,
  gatewayVerified: false,
  stoppingTurn: false,
  threadSettings: null,
  settingsBusy: false,
  notificationConfig: null,
  projectFolderEntries: null,
  fileListLimit: 250,
  directoryRequest: 0,
  projectDirectory: "",
  previewRequest: 0,
  projectFiles: [],
  projectFilesTruncated: false,
  projectSearchMatches: [],
  projectSearchTruncated: false,
  changes: null,
  terminals: [],
  selectedTerminalId: null,
  terminalSnapshot: null,
  lastTerminalSnapshotAt: 0,
  taskCatalog: [],
  debuggerCatalog: [],
  debuggerSessions: [],
  lastDebuggerSnapshotAt: 0,
  contextPaths: [],
  uploads: [],
  previewPath: null,
  previewContent: "",
  previewFocusLine: null,
  diffContent: "",
  reviewSource: "",
  reviewLanguage: "text",
  approvals: [],
  approvalsSignature: null,
  subagents: [],
  subagentsSignature: null,
  stoppingSubagent: null,
  elicitations: [],
  editReview: null,
  queue: null,
  rewindPoints: [],
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
  state.desktopReachable = status === "online" ? true : status === "offline" ? false : null;
  state.connectionMessage = message;
  state.connectionStatus = status;
  renderConnectionHealth();
  updateComposerAction();
  showCreateAvailability();
  renderEmptyWorkspace();
}
function setHealthText(id, text, status = "") {
  const element = $(id);
  element.textContent = text;
  element.className = status;
}
function relativeLiveTime() {
  if (!state.lastLiveEventAt) return "None yet";
  const seconds = Math.max(0, Math.round((Date.now() - state.lastLiveEventAt) / 1000));
  if (seconds < 2) return "Just now";
  if (seconds < 60) return `${seconds}s ago`;
  return `${Math.floor(seconds / 60)}m ago`;
}
function compactConnectionMessage(message) {
  if (!matchMedia("(max-width: 760px)").matches) return message;
  const compact = {
    "Zed connected · live updates": "Zed · Live",
    "Zed connected · polling": "Zed · Polling",
    "Zed connected · restoring live updates": "Zed · Reconnecting",
    "Zed connected · live updates timed out": "Zed · Polling",
    "Checking gateway…": "Checking…",
    "Gateway unavailable": "Gateway offline",
    "Device offline": "Device offline",
  };
  return compact[message] || message;
}
function renderConnectionHealth() {
  const deviceOnline = navigator.onLine !== false;
  let message = state.connectionMessage;
  let status = state.connectionStatus;
  if (!deviceOnline) {
    message = "Device offline";
    status = "offline";
  } else if (state.live && state.threadId && state.streamState === "reconnecting") {
    message = "Zed connected · restoring live updates";
    status = "warning";
  } else if (state.live && state.threadId && state.streamState === "timed_out") {
    message = "Zed connected · live updates timed out";
    status = "warning";
  }
  const element = $("connection");
  element.textContent = compactConnectionMessage(message);
  element.className = `connection ${status}`;
  element.title = "Browser, gateway, and desktop Zed connection. Model availability is shown separately.";
  $("mobile-connection-state").textContent = message;
  setHealthText("device-network-state", deviceOnline ? "Online" : "Offline", deviceOnline ? "online" : "offline");
  setHealthText("gateway-connection-state", state.gatewayReachable === true ? "Reachable" : state.gatewayReachable === false ? "Unavailable" : "Checking…", state.gatewayReachable === true ? "online" : state.gatewayReachable === false ? "offline" : "");
  setHealthText("zed-connection-state", state.desktopReachable === true ? "Connected" : state.desktopReachable === false ? "Unavailable" : "Checking…", state.desktopReachable === true ? "online" : state.desktopReachable === false ? "offline" : "");
  const stream = state.streamState === "live" ? ["Live", "online"]
    : state.streamState === "connecting" ? ["Connecting…", "warning"]
      : state.streamState === "reconnecting" ? [`Reconnecting · attempt ${state.streamReconnectAttempt}`, "warning"]
        : state.streamState === "timed_out" ? ["Timed out · polling", "offline"]
          : state.streamState === "paused" ? ["Paused while app is hidden", "warning"]
            : state.threadId ? ["Polling", "warning"] : ["No session", ""];
  setHealthText("stream-connection-state", stream[0], stream[1]);
  const agent = state.retryStatus ? ["Retrying model request", "warning"]
    : state.threadError ? ["Last request failed", "error"]
      : state.threadId && state.threadStatus && state.threadStatus !== "Idle" ? ["Working", "online"]
        : state.threadId ? ["Idle · model not probed", ""] : ["No session", ""];
  setHealthText("agent-connection-state", agent[0], agent[1]);
  $("last-live-update").textContent = relativeLiveTime();
  renderMobileSessionMeta();
}
function pairingStatus() {
  return matchMedia("(display-mode: standalone)").matches ? "Pair this app" : "Pair this browser";
}
function showCreateAvailability() {
  const available = state.live && state.capabilities.includes("thread.create") && !state.creatingThread;
  $("new-session").disabled = !available;
  $("empty-create").disabled = !available;
  $("empty-create").classList.toggle("hidden", !state.capabilities.includes("thread.create"));
  $("new-session").title = available
    ? "Create a native Zed Agent session"
    : "Start patched Zed to create a session";
}

function renderEmptyWorkspace() {
  const noSession = !state.threadId;
  document.body.classList.toggle("no-session", noSession && !!state.token);
  $("empty-state").classList.toggle("hidden", !noSession);
  if (!noSession) return;
  const connected = state.desktopReachable === true;
  $("empty-description").textContent = connected
    ? state.threads.length
      ? "Choose an exposed session from the sidebar to continue its conversation."
      : "Desktop Zed is connected, but no agent thread is currently exposed. Start a Zed Agent session here or expose an existing Zed or ACP conversation."
    : "Start the patched Zed Dev window, then refresh this page when the desktop bridge is online.";
  $("thread-title").textContent = state.threads.length ? "Choose a session" : "No remote sessions";
  $("thread-meta").textContent = connected
    ? "Remote control is ready when an agent thread is exposed."
    : "Waiting for the patched desktop Zed bridge.";
  $("thread-state").textContent = connected ? "Connected" : "Zed unavailable";
  $("thread-state").className = `state-pill ${connected ? "online" : "offline"}`;
  $("show-context").disabled = true;
  showCreateAvailability();
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
  updateComposerAction();
}
function targetKey() { return `zedlink.target.${state.gatewayId}`; }
function targetScope() { return `${state.gatewayId}.${state.targetId || "default"}`; }
function pendingKey() { return `zedlink.pending.${targetScope()}`; }
function tokenKey() { return `zedlink.token.${state.gatewayId}`; }
function selectedThreadKey() { return `zedlink.selectedThread.${targetScope()}`; }

function normalizeAgent(agent) {
  if (!agent || typeof agent !== "object") return { id: "zed-agent", name: "Zed Agent", kind: "zed" };
  return {
    id: typeof agent.id === "string" && agent.id ? agent.id : "unknown-agent",
    name: typeof agent.name === "string" && agent.name ? agent.name : "Agent",
    kind: agent.kind === "external_acp" ? "external_acp" : "zed",
  };
}

function selectedAgent() {
  const thread = state.threads.find((item) => item.thread_id === state.threadId);
  return normalizeAgent(state.threadSettings?.agent || thread?.agent);
}

function renderSelectedAgent() {
  const agent = selectedAgent();
  const selected = state.threads.find((item) => item.thread_id === state.threadId);
  const external = agent.kind === "external_acp";
  const canManageSession = !!state.threadId
    && (state.capabilities.includes("thread.rename") || state.capabilities.includes("thread.unexpose"));
  $("session-management").classList.toggle("hidden", !canManageSession);
  if (selected && document.activeElement !== $("session-title-input")) {
    $("session-title-input").value = selected.title || "";
  }
  $("rename-session").disabled = !state.capabilities.includes("thread.rename") || !state.threadId;
  $("unexpose-session").disabled = !state.capabilities.includes("thread.unexpose") || !state.threadId;
  $("thread-agent-kind").textContent = external ? "EXTERNAL ACP AGENT" : "NATIVE ZED AGENT";
  $("settings-agent-kind").textContent = external ? "EXTERNAL ACP AGENT" : "NATIVE ZED AGENT";
  $("prompt").placeholder = `Message ${agent.name}…`;
  $("prompt-label").textContent = `Message ${agent.name}`;
  return agent;
}

async function renameSelectedSession() {
  const title = $("session-title-input").value.trim();
  if (!state.threadId || !title || !state.capabilities.includes("thread.rename")) return;
  const result = await rpc("thread.rename", { ...baseThreadParams(), title });
  if (result.outcome !== "requested") throw new Error("Zed did not accept the title change.");
  await loadThreads();
  $("thread-title").textContent = title;
  renderThreadSettings();
  notice("Session renamed in desktop Zed.");
}

async function unexposeSelectedSession() {
  if (!state.threadId || !state.capabilities.includes("thread.unexpose")) return;
  const selected = state.threads.find((thread) => thread.thread_id === state.threadId);
  if (!confirm(`Stop exposing “${selected?.title || "this session"}” to ZedLink?\n\nThe Agent thread stays open in desktop Zed.`)) return;
  const result = await rpc("thread.unexpose", baseThreadParams());
  if (result.outcome !== "unexposed") throw new Error("Zed did not stop exposure.");
  const retainedTarget = state.targetId;
  closeEventStream();
  safeStore.remove(selectedThreadKey());
  resetTargetSession();
  state.targetId = retainedTarget;
  await connect();
  notice("Remote exposure stopped. The Agent thread remains in desktop Zed.");
}

function pushSupported() {
  return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

function setHeaderRuntime(id, text, status = "", title = text) {
  const element = $(id);
  element.textContent = text;
  element.className = `runtime-item ${status}`.trim();
  element.title = title;
}

function renderHeaderModel() {
  const supported = state.capabilities.includes("thread.settings");
  const agent = selectedAgent();
  if (!state.threadId) {
    setHeaderRuntime("header-model", "No session", "", "Select an exposed agent session.");
  } else if (agent.kind === "external_acp") {
    const suffix = state.retryStatus ? " · retrying" : state.threadError ? " · request failed" : "";
    const status = state.retryStatus ? "warning" : state.threadError ? "error" : "";
    setHeaderRuntime("header-model", `Agent · ${agent.name}${suffix}`, status,
      `${agent.name} owns its model, authentication, and runtime configuration. The session is hosted in desktop Zed.`);
  } else if (!supported) {
    setHeaderRuntime("header-model", "Model · update Zed", "warning", "Restart the updated patched Zed build to report this session's model.");
  } else if (state.settingsBusy && !state.threadSettings?.model?.name) {
    setHeaderRuntime("header-model", "Model · loading…");
  } else if (state.threadSettings?.model?.name) {
    const model = state.threadSettings.model;
    const suffix = state.retryStatus ? " · retrying" : state.threadError ? " · request failed" : "";
    const status = state.retryStatus ? "warning" : state.threadError ? "error" : "";
    const detail = state.retryStatus ? "Zed is retrying this native model request."
      : state.threadError ? "The selected native model request failed. Open the conversation for details."
        : `${model.name} · ${model.provider_id || "provider unavailable"}`;
    setHeaderRuntime("header-model", `Model · ${model.name}${suffix}`, status, detail);
  } else {
    setHeaderRuntime("header-model", "Model unavailable", "error", "Desktop Zed did not return model identity for this session.");
  }
  renderMobileSessionMeta();
}

function renderMobileSessionMeta() {
  if (!$("mobile-session-meta")) return;
  const agent = selectedAgent();
  const model = agent.kind === "external_acp"
    ? agent.name
    : state.threadSettings?.model?.name || "Local model";
  const activity = state.retryStatus ? "Retrying"
    : state.threadError ? "Request failed"
      : state.threadStatus && state.threadStatus !== "Idle"
        ? (/tool|execut|run/i.test(state.threadStatus) ? "Running tools" : /wait|pending|queue/i.test(state.threadStatus) ? "Waiting" : "Generating")
        : state.desktopReachable === false ? "Zed unavailable"
          : state.live ? "Live" : "Reconnecting";
  $("mobile-session-meta").textContent = `${model} · ${activity}`;
}

function renderNotificationState(status) {
  const label = $("notification-state");
  const enable = $("enable-notifications");
  const test = $("test-notifications");
  label.className = "";
  test.classList.add("hidden");
  enable.disabled = true;
  if (!window.isSecureContext) {
    label.textContent = "Secure URL required";
    label.classList.add("blocked");
    enable.textContent = "Use trusted HTTPS";
    $("notification-help").textContent = "Open ZedLink at its trusted HTTPS hostname. Push notifications cannot run from an untrusted IP address.";
    setHeaderRuntime("header-notifications", "Notifications · secure URL", "error", "Notifications require the gateway's trusted HTTPS hostname.");
    return;
  }
  if (!pushSupported()) {
    label.textContent = "Not supported";
    $("notification-help").textContent = /iPhone|iPad/i.test(navigator.userAgent || "")
      ? "Add ZedLink to the Home Screen, open that app, and enable notifications there."
      : "This browser does not expose standards-based Web Push.";
    setHeaderRuntime("header-notifications", "Notifications unavailable", "warning", label.textContent);
    return;
  }
  if (Notification.permission === "denied") {
    label.textContent = "Blocked";
    label.classList.add("blocked");
    enable.textContent = "Blocked by browser";
    $("notification-help").textContent = "Allow notifications for this site in the browser or system settings, then return here.";
    setHeaderRuntime("header-notifications", "Notifications blocked", "error", "Notifications are blocked by this browser.");
    return;
  }
  if (status === "enabled") {
    label.textContent = "Enabled";
    label.classList.add("enabled");
    enable.textContent = "Disable notifications";
    enable.disabled = false;
    test.classList.remove("hidden");
    setHeaderRuntime("header-notifications", "Notifications · On", "enabled", "Notifications are enabled for this browser app.");
  } else if (status === "loading") {
    label.textContent = "Checking…";
    enable.textContent = "Enable notifications";
    setHeaderRuntime("header-notifications", "Notifications · checking…");
  } else if (status === "unavailable") {
    label.textContent = "Gateway unavailable";
    enable.textContent = "Enable notifications";
    setHeaderRuntime("header-notifications", "Notifications unavailable", "warning", "Notification status could not be checked.");
  } else {
    label.textContent = "Off";
    enable.textContent = "Enable notifications";
    enable.disabled = !state.token;
    setHeaderRuntime("header-notifications", "Notifications · Off", "", "Notifications are off for this browser app.");
  }
}

async function notificationRequest(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8000);
  let response;
  try {
    response = await fetch(path, {
      method: options.method || "GET",
      cache: "no-store",
      redirect: "error",
      signal: controller.signal,
      headers: {
        Authorization: `Bearer ${state.token}`,
        ...(options.body ? { "Content-Type": "application/json" } : {}),
      },
      body: options.body ? JSON.stringify(options.body) : undefined,
    });
  } catch (error) {
    throw new Error(error?.name === "AbortError" ? "Notification status timed out." : "Notification service is unavailable.");
  } finally {
    clearTimeout(timeout);
  }
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(apiError(result.error || "INTERNAL_ERROR"));
  return result;
}

async function readyServiceWorker() {
  if (!window.isSecureContext) throw new Error("Use the gateway's trusted HTTPS hostname.");
  await navigator.serviceWorker.register("/service-worker.js");
  let timeout;
  try {
    return await Promise.race([
      navigator.serviceWorker.ready,
      new Promise((_, reject) => {
        timeout = setTimeout(() => reject(new Error("The browser app did not finish starting notifications.")), 8000);
      }),
    ]);
  } finally {
    if (timeout) clearTimeout(timeout);
  }
}

function applicationServerKey(encoded) {
  const padding = "=".repeat((4 - encoded.length % 4) % 4);
  const binary = atob((encoded + padding).replaceAll("-", "+").replaceAll("_", "/"));
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

function sameApplicationServerKey(subscription, expected) {
  const actual = subscription?.options?.applicationServerKey;
  if (!actual) return false;
  const left = new Uint8Array(actual);
  const right = applicationServerKey(expected);
  return left.length === right.length && left.every((byte, index) => byte === right[index]);
}

async function refreshNotifications() {
  renderNotificationState("loading");
  if (!state.token || !pushSupported()) {
    renderNotificationState("off");
    return;
  }
  state.notificationConfig = await notificationRequest("/v1/notifications/config");
  const registration = await readyServiceWorker();
  const subscription = await registration.pushManager.getSubscription();
  if (subscription) {
    const status = await notificationRequest("/v1/notifications/status", {
      method: "POST",
      body: { endpoint: subscription.endpoint },
    });
    state.notificationConfig.enabled = status.enabled === true;
  } else {
    state.notificationConfig.enabled = false;
  }
  renderNotificationState(state.notificationConfig.enabled ? "enabled" : "off");
}

async function enableNotifications() {
  if (!state.token || !pushSupported()) return;
  if (state.notificationConfig?.enabled) {
    await disableNotifications(true);
    return;
  }
  $("enable-notifications").disabled = true;
  try {
    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      renderNotificationState("off");
      return;
    }
    const config = await notificationRequest("/v1/notifications/config");
    const registration = await readyServiceWorker();
    let subscription = await registration.pushManager.getSubscription();
    if (subscription && !sameApplicationServerKey(subscription, config.application_server_key)) {
      try {
        await notificationRequest("/v1/notifications/unsubscribe", {
          method: "POST",
          body: { endpoint: subscription.endpoint },
        });
      } catch { /* The old endpoint may not exist in current gateway state. */ }
      await subscription.unsubscribe();
      subscription = null;
    }
    if (!subscription) {
      subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: applicationServerKey(config.application_server_key),
      });
    }
    await notificationRequest("/v1/notifications/subscribe", {
      method: "POST",
      body: subscription.toJSON(),
    });
    state.notificationConfig = { ...config, enabled: true };
    renderNotificationState("enabled");
    notice("Notifications enabled for this paired device.");
  } catch (error) {
    renderNotificationState("off");
    notice(`Could not enable notifications: ${error.message}`);
  }
}

async function disableNotifications(showNotice = true) {
  if (!pushSupported()) return;
  const registration = await readyServiceWorker();
  const subscription = await registration.pushManager.getSubscription();
  if (subscription && state.token) {
    await notificationRequest("/v1/notifications/unsubscribe", {
      method: "POST",
      body: { endpoint: subscription.endpoint },
    });
  }
  if (subscription) await subscription.unsubscribe();
  state.notificationConfig = state.notificationConfig
    ? { ...state.notificationConfig, enabled: false }
    : null;
  renderNotificationState("off");
  if (showNotice) notice("Notifications disabled on this device.");
}

async function testNotifications() {
  $("test-notifications").disabled = true;
  try {
    const registration = await readyServiceWorker();
    const subscription = await registration.pushManager.getSubscription();
    if (!subscription) throw new Error("This browser no longer has a push subscription.");
    await notificationRequest("/v1/notifications/test", {
      method: "POST",
      body: { endpoint: subscription.endpoint },
    });
    notice("Test notification sent through this browser's push service.");
  } catch (error) {
    notice(`Test notification failed: ${error.message}`);
  } finally {
    $("test-notifications").disabled = false;
  }
}
function sidebarKey() { return `zedlink.sidebarCollapsed.${state.gatewayId}`; }
function updateSidebarToggle() {
  const mobile = matchMedia("(max-width: 760px)").matches;
  const collapsed = document.body.classList.contains("sidebar-collapsed");
  const mobileOpen = document.body.classList.contains("mobile-sessions");
  const button = $("show-sessions");
  const sessionsVisible = mobile ? mobileOpen || !state.threadId : !collapsed;
  const label = sessionsVisible && mobile && state.threadId ? "Return to conversation"
    : sessionsVisible ? "Hide sessions" : "Show sessions";
  button.setAttribute("aria-label", label);
  button.title = label;
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

async function refreshCapabilities() {
  const info = await rpc("instance.info");
  identity(info);
  state.capabilities = Array.isArray(info.capabilities) ? info.capabilities : [];
}
function canStopTurn() {
  return state.live && !!state.threadId && Number.isInteger(state.turnId)
    && state.capabilities.includes("thread.cancel");
}
function workingStatusLabel(status) {
  const value = typeof status === "string" ? status.trim() : "";
  if (!value || value === "Idle") return "Waiting for native activity…";
  if (/generat/i.test(value)) return "Generating a response in desktop Zed";
  if (/tool|execut|run/i.test(value)) return "Running native tools in desktop Zed";
  if (/wait|pending|queue/i.test(value)) return "Waiting in desktop Zed";
  return `${value} in desktop Zed`;
}
function renderTurnProgress() {
  const busy = !!state.threadId && !!state.threadStatus && state.threadStatus !== "Idle";
  const status = $("thread-state");
  status.classList.toggle("working", busy);
  status.disabled = !busy;
  if (!busy) {
    status.removeAttribute("title");
    status.setAttribute("aria-label", state.threadId ? "Agent is idle" : "No selected agent session");
    renderMobileSessionMeta();
    return;
  }
  const detail = state.retryStatus ? "Retrying the model request in desktop Zed" : workingStatusLabel(state.threadStatus);
  status.textContent = state.retryStatus ? "Retrying" : /tool|execut|run/i.test(state.threadStatus) ? "Running tools" : /wait|pending|queue/i.test(state.threadStatus) ? "Waiting" : "Generating";
  status.title = `${detail}. Select to view live activity.`;
  status.setAttribute("aria-label", `${selectedAgent().name} is working. ${detail}. View live activity.`);
  renderMobileSessionMeta();
}
function updateComposerAction() {
  const button = $("send");
  const stopping = canStopTurn();
  const agent = selectedAgent();
  button.dataset.mode = stopping ? "stop" : "send";
  button.classList.toggle("stop-mode", stopping);
  button.textContent = stopping ? "■" : "↑";
  button.setAttribute("aria-label", stopping ? `Stop current ${agent.name} turn` : "Send message");
  button.title = stopping ? `Stop current ${agent.name} turn` : "Send message";
  button.disabled = stopping
    ? state.stoppingTurn
    : !state.threadId || !!state.pending || !state.token || !state.live
      || navigator.onLine === false || state.gatewayReachable === false;
  $("show-actions").disabled = !state.threadId || !state.token || !state.live;
  renderTurnProgress();
}

function focusLiveActivity() {
  const entries = $("transcript-entries");
  const targets = entries.querySelectorAll(".message.assistant, .message.native, .message.tool");
  const target = targets[targets.length - 1];
  (target || entries).scrollIntoView({ behavior: "smooth", block: "end" });
  target?.querySelector("details.thinking-block, .tool-details")?.setAttribute("open", "");
}
function apiError(code) {
  if (code === "UNAUTHENTICATED") return "Browser credential revoked or missing. Pair again.";
  if (code === "THREAD_NOT_EXPOSED") return "This thread is no longer exposed in desktop Zed.";
  if (code === "INSTANCE_UNAVAILABLE") return "Desktop Zed is unavailable. Check that it is running.";
  if (code === "RESYNC_REQUIRED") return "Event history changed. Reloading the native snapshot.";
  if (code === "UNSUPPORTED_CAPABILITY") return "This command is unavailable in this Zed thread.";
  if (code === "REQUEST_CONFLICT") return "That request ID was already used for different content.";
  if (code === "THREAD_BUSY") return "Wait for the current Zed turn to finish before changing its settings.";
  if (code === "STALE_SEQUENCE") return "The native thread changed. Refresh it before trying this action again.";
  if (code === "FILE_UNAVAILABLE") return "That file is unavailable or excluded from remote project access.";
  if (code === "UNSUPPORTED_FILE") return "That file type cannot be previewed or attached.";
  if (code === "FILE_TOO_LARGE") return "That file is too large to attach. The limit is 256 KiB for text files.";
  if (code === "PAYLOAD_TOO_LARGE") return "The selected upload is too large. The limit is 1 MiB per file.";
  if (code === "STALE_REVISION") return "The repository changed. Refresh Changes before applying this action.";
  if (code === "DIFF_UNAVAILABLE" || code === "REPOSITORY_UNAVAILABLE") return "The repository diff is unavailable in desktop Zed.";
  if (code === "OPERATION_FAILED") return "Desktop Zed could not complete that Git operation.";
  if (code === "TASK_UNAVAILABLE") return "That configured Zed task is no longer available. Refresh the task list.";
  if (code === "DEBUGGER_UNAVAILABLE") return "That debugger session is no longer available in desktop Zed.";
  if (code === "DEBUGGER_STATE_CONFLICT") return "The debugger changed state before that control could be applied. Refresh and try again.";
  if (code === "APPROVAL_EXPIRED" || code === "APPROVAL_ALREADY_RESOLVED" || code === "STALE_TURN") return "That approval is no longer pending. Refreshing the native thread.";
  if (code === "PAIRING_UNAVAILABLE") return "No active pairing request. Create a fresh pairing link in desktop Zed.";
  if (code === "PAIRING_EXPIRED") return "That pairing link expired. Create a fresh one in desktop Zed.";
  if (code === "PAIRING_INVALID") return "That pairing code is incorrect. Check the code or create a fresh pairing link.";
  if (code === "RATE_LIMITED") return "The gateway cannot add another device. Revoke an old device in desktop Zed first.";
  if (code === "INVALID_SUBSCRIPTION") return "This browser returned an unsupported push subscription.";
  if (code === "NOTIFICATIONS_DISABLED") return "Enable notifications on this device first.";
  if (code === "SUBSCRIPTION_EXPIRED") return "This browser subscription expired. Disable notifications, then enable them again.";
  if (code === "PUSH_DELIVERY_FAILED") return "The gateway could not reach this browser's push service.";
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
      body: JSON.stringify({ version: 1, request_id: requestId, method, params,
        ...(method !== "instance.list" && state.targetId ? { target_id: state.targetId } : {}) }),
    });
    state.gatewayReachable = true;
    renderConnectionHealth();
  } catch (cause) {
    state.gatewayReachable = false;
    renderConnectionHealth();
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
    state.threadError = null;
    state.retryStatus = null;
    state.imageRecovery = null;
    state.rewindingImage = false;
    state.errorSignature = null;
    renderAgentHealth();
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

function closeEventStream(nextState = "idle") {
  if (state.eventReconnectTimer) clearTimeout(state.eventReconnectTimer);
  if (state.eventConnectTimer) clearTimeout(state.eventConnectTimer);
  state.eventReconnectTimer = null;
  state.eventConnectTimer = null;
  const socket = state.eventSocket;
  state.eventSocket = null;
  state.eventThreadId = null;
  state.streamState = nextState;
  document.body.dataset.liveTransport = "polling";
  if (socket && socket.readyState < WebSocket.CLOSING) socket.close(1000, "Client view changed");
  renderConnectionHealth();
}

function startEventStream() {
  if (!state.token || !state.threadId || document.visibilityState === "hidden") return;
  if (state.eventReconnectTimer) return;
  if (state.eventSocket && state.eventThreadId === state.threadId
      && state.eventSocket.readyState <= WebSocket.OPEN) return;
  closeEventStream("connecting");
  const threadId = state.threadId;
  const targetId = state.targetId;
  const url = new URL("/v1/events", location.href);
  url.protocol = location.protocol === "https:" ? "wss:" : "ws:";
  url.searchParams.set("thread_id", threadId);
  url.searchParams.set("after_sequence", String(state.sequence));
  if (targetId) url.searchParams.set("target_id", targetId);
  const socket = new WebSocket(url, ["zedlink-v1", `zedlink-token-${state.token}`]);
  state.streamState = state.streamReconnectAttempt ? "reconnecting" : "connecting";
  document.body.dataset.liveTransport = "connecting";
  state.eventSocket = socket;
  state.eventThreadId = threadId;
  renderConnectionHealth();
  state.eventConnectTimer = setTimeout(() => {
    if (state.eventSocket === socket && socket.readyState !== WebSocket.OPEN) {
      state.streamState = "timed_out";
      renderConnectionHealth();
      socket.close(4000, "Live update connection timed out");
    }
  }, 8000);
  socket.addEventListener("open", () => {
    if (state.eventSocket === socket) {
      if (state.eventConnectTimer) clearTimeout(state.eventConnectTimer);
      state.eventConnectTimer = null;
      state.streamState = "live";
      state.streamReconnectAttempt = 0;
      state.lastLiveEventAt = Date.now();
      document.body.dataset.liveTransport = "websocket";
      renderConnectionHealth();
    }
  });
  socket.addEventListener("message", (event) => {
    if (state.eventSocket !== socket || state.threadId !== threadId || state.targetId !== targetId) return;
    try {
      const data = JSON.parse(event.data);
      if (data.error) throw Object.assign(new Error(apiError(data.error.code)), { code: data.error.code });
      const result = data.result;
      identity(result);
      if (result.thread_id !== threadId || !Array.isArray(result.events)) throw new Error("Invalid live event response.");
      state.streamState = "live";
      state.lastLiveEventAt = Date.now();
      connection("Zed connected · live updates", "online");
      if (Number.isInteger(result.last_sequence)) state.sequence = Math.max(state.sequence, result.last_sequence);
      if (result.events.some((item) => item?.kind === "entry.removed")) {
        state.renderedEntries = [];
        state.renderedEntryStart = 0;
        state.totalEntries = 0;
        $("transcript-entries").replaceChildren();
      }
      if (result.events.length || (state.threadStatus && state.threadStatus !== "Idle")) {
        refreshSnapshot().catch((error) => notice(error.message));
      }
    } catch (error) {
      if (error.code === "UNAUTHENTICATED") {
        state.token = null;
        safeStore.remove(tokenKey());
      }
      if (error.code === "INSTANCE_UNAVAILABLE") connection("Zed unavailable", "offline");
      else {
        state.streamState = "reconnecting";
        renderConnectionHealth();
      }
      socket.close();
    }
  });
  socket.addEventListener("close", () => {
    if (state.eventSocket !== socket) return;
    if (state.eventConnectTimer) clearTimeout(state.eventConnectTimer);
    state.eventConnectTimer = null;
    state.eventSocket = null;
    state.eventThreadId = null;
    document.body.dataset.liveTransport = "polling";
    if (state.token && state.threadId === threadId && document.visibilityState !== "hidden") {
      state.streamReconnectAttempt += 1;
      if (state.streamState !== "timed_out") state.streamState = "reconnecting";
      const delay = Math.min(10000, 800 * (2 ** Math.min(state.streamReconnectAttempt, 4)));
      state.eventReconnectTimer = setTimeout(() => {
        state.eventReconnectTimer = null;
        startEventStream();
      }, delay);
    } else {
      state.streamState = document.visibilityState === "hidden" ? "paused" : "idle";
    }
    renderConnectionHealth();
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
    state.gatewayReachable = true;
    renderConnectionHealth();
    const result = await response.json();
    if (!response.ok || result.version !== 1 || typeof result.gateway_id !== "string") {
      throw new Error("Unsupported gateway identity response.");
    }
    state.gatewayId = result.gateway_id;
    $("gateway-id").textContent = result.gateway_id;
    $("mobile-gateway-id").textContent = result.gateway_id;
    $("pair-origin").textContent = location.origin;
    $("expected-id").value = result.gateway_id;
    const routeOrigins = Array.isArray(result.route_origins)
      ? result.route_origins.filter((origin) => typeof origin === "string" && origin.startsWith("https://")) : [];
    const routeElement = $("gateway-route-addresses");
    if (routeElement) {
      routeElement.replaceChildren(...(routeOrigins.length ? routeOrigins : [location.origin]).map((origin, index) => {
        const link = document.createElement("a");
        link.href = origin;
        link.textContent = origin === location.origin ? `${origin} (current)` : origin;
        link.rel = "noreferrer";
        if (index) link.className = "route-address-next";
        return link;
      }));
    }
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
    state.gatewayReachable = false;
    renderConnectionHealth();
    connection(error.message.includes("gateway identity differs") ? "Gateway identity mismatch"
      : error.message.includes("pairing link") ? "Pairing link invalid" : "Gateway unavailable", "offline");
    notice(error.message);
  }
}

async function pairBrowser(code, deviceName) {
  let response;
  try {
    response = await fetch("/v1/pair", {
      method: "POST", cache: "no-store", redirect: "error",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, device_name: deviceName }),
    });
    state.gatewayReachable = true;
  } catch {
    state.gatewayReachable = false;
    renderConnectionHealth();
    throw new Error("The gateway connection was interrupted while pairing.");
  }
  renderConnectionHealth();
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

function renderTargets() {
  const select = $("target-select");
  select.replaceChildren();
  for (const target of state.targets) {
    const option = document.createElement("option");
    option.value = target.target_id;
    option.textContent = `${target.label}${target.available ? "" : " · unavailable"}`;
    option.disabled = !target.available;
    select.append(option);
  }
  select.value = state.targetId || "";
  $("target-field").classList.toggle("hidden", state.targets.length < 2);
  const selected = state.targets.find((target) => target.target_id === state.targetId);
  $("target-help").textContent = selected?.available
    ? "Sessions and sends are routed only to this Zed instance."
    : "This Zed instance is currently unavailable.";
  $("connection-target").textContent = selected?.label || "Not selected";
}

function resetTargetSession() {
  closeEventStream();
  state.instanceId = null;
  state.epoch = null;
  state.capabilities = [];
  state.commands = [];
  state.threads = [];
  state.threadId = null;
  state.turnId = null;
  state.threadStatus = null;
  state.threadError = null;
  state.retryStatus = null;
  state.threadSettings = null;
  state.createOptions = null;
  state.pending = null;
  state.sequence = 0;
  state.renderedEntries = [];
  state.renderedThreadId = null;
  state.renderedEntryStart = 0;
  state.totalEntries = 0;
  state.subagents = [];
  state.approvals = [];
  state.terminals = [];
  state.selectedTerminalId = null;
  state.terminalSnapshot = null;
  state.taskCatalog = [];
  state.debuggerCatalog = [];
  state.debuggerSessions = [];
  $("transcript-entries").replaceChildren();
  renderThreads();
  renderCommands();
  renderSubagents([]);
  renderApprovals([]);
  renderTaskCatalog();
  renderDebugger();
  renderAgentHealth();
  renderThreadSettings();
  renderEmptyWorkspace();
  updateComposerAction();
  document.body.classList.remove("thread-open", "mobile-sessions");
}

async function connect() {
  if (!state.token) return;
  connection("Connecting…");
  document.body.classList.remove("pairing");
  $("pair-panel").classList.add("hidden");
  $("sessions-panel").classList.remove("hidden");
  refreshNotifications().catch(() => renderNotificationState("unavailable"));
  try {
    const registry = await rpc("instance.list");
    if (!Array.isArray(registry.targets) || !registry.targets.length) {
      throw new Error("This gateway has no configured Zed targets.");
    }
    state.targets = registry.targets.filter((target) => typeof target.target_id === "string" && typeof target.label === "string");
    const requestedTarget = new URLSearchParams(location.search).get("target");
    const savedTarget = safeStore.read(targetKey());
    const preferred = requestedTarget || state.targetId || savedTarget || registry.default_target_id;
    const selected = state.targets.find((target) => target.target_id === preferred)
      || state.targets.find((target) => target.available)
      || state.targets[0];
    if (state.targetId && state.targetId !== selected.target_id) resetTargetSession();
    state.targetId = selected.target_id;
    safeStore.write(targetKey(), state.targetId);
    renderTargets();
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
      state.threadError = null;
      state.retryStatus = null;
      state.imageRecovery = null;
      state.rewindingImage = false;
      renderAgentHealth();
      state.threadSettings = null;
      updateComposerAction();
      renderThreadSettings();
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
    const requestedThread = new URLSearchParams(location.search).get("thread");
    if (requestedThread && state.threads.some((thread) => thread.thread_id === requestedThread)) {
      await selectThread(requestedThread);
      history.replaceState(null, "", location.pathname);
    }
    if (!state.threadId) {
      const selected = safeStore.read(selectedThreadKey());
      if (selected && state.threads.some((thread) => thread.thread_id === selected)) {
        await selectThread(selected);
      }
    }
    if (!state.threadId && state.threads.length) await selectThread(state.threads[0].thread_id);
    if (state.threadId) startEventStream();
    connection(state.eventSocket?.readyState === WebSocket.OPEN ? "Zed connected · live updates" : "Zed connected · polling", "online");
  } catch (error) {
    connection("Zed unavailable", "offline");
    notice(`Pairing is saved. ${error.message} Refresh when desktop Zed is ready.`);
  }
}

async function loadThreads() {
  const result = await rpc("thread.list");
  identity(result);
  if (!Array.isArray(result.threads)) throw new Error("Invalid thread list.");
  const priorSelected = state.threads.find((thread) => thread.thread_id === state.threadId);
  const nextSelected = result.threads.find((thread) => thread.thread_id === state.threadId);
  const priorHealth = priorSelected ? JSON.stringify([
    priorSelected.status, priorSelected.current_turn_id, priorSelected.had_error,
    priorSelected.agent_error, priorSelected.retry_status,
  ]) : null;
  const nextHealth = nextSelected ? JSON.stringify([
    nextSelected.status, nextSelected.current_turn_id, nextSelected.had_error,
    nextSelected.agent_error, nextSelected.retry_status,
  ]) : null;
  const scope = JSON.stringify([state.gatewayId, state.targetId, state.instanceId, state.epoch]);
  for (const thread of result.threads) {
    const key = sessionKey(thread);
    const cached = sessionSummaryCache.get(key);
    if (cached && Date.now() - cached.at < 5000 && cached.turn === thread.current_turn_id && cached.status === thread.status && cached.epoch === state.epoch) {
      thread.approval_count = cached.approvals; thread.input_count = cached.inputs;
    } else {
      const params = { ...baseInstanceParams(), thread_id: thread.thread_id };
      if (state.capabilities.includes("thread.approvals")) {
        const result = await rpc("thread.approvals", params);
        if (scope !== JSON.stringify([state.gatewayId, state.targetId, state.instanceId, state.epoch])) return;
        thread.approval_count = Array.isArray(result.approvals) ? result.approvals.length : null;
      }
      if (state.capabilities.includes("thread.elicitations")) {
        const result = await rpc("thread.elicitations", params);
        if (scope !== JSON.stringify([state.gatewayId, state.targetId, state.instanceId, state.epoch])) return;
        thread.input_count = Array.isArray(result.elicitations) ? result.elicitations.filter((row) => row.status === "pending").length : null;
      }
      sessionSummaryCache.set(key, { at: Date.now(), epoch: state.epoch, turn: thread.current_turn_id, status: thread.status, approvals: thread.approval_count, inputs: thread.input_count });
    }
    const signature = JSON.stringify([thread.status, thread.current_turn_id, !!thread.had_error, !!validRetryStatus(thread.retry_status), thread.approval_count, thread.input_count]);
    if (sessionObserved.has(key) && sessionObserved.get(key) !== signature && state.threadId !== thread.thread_id) sessionUpdated.add(key);
    sessionObserved.set(key, signature);
  }
  state.threads = result.threads;
  state.lastThreadsAt = Date.now();
  renderThreads();
  if (state.threadId && !state.threads.some((thread) => thread.thread_id === state.threadId)) {
    closeEventStream();
    state.threadId = null;
    safeStore.remove(selectedThreadKey());
    state.commands = [];
    renderCommands();
    state.turnId = null;
    state.threadStatus = null;
    state.threadError = null;
    state.retryStatus = null;
    state.imageRecovery = null;
    state.rewindingImage = false;
    renderAgentHealth();
    state.threadSettings = null;
    updateComposerAction();
    renderThreadSettings();
    document.body.classList.remove("thread-open", "mobile-sessions");
    state.sequence = 0;
    state.renderedEntries = [];
    state.renderedThreadId = null;
    state.renderedEntryStart = 0;
    state.totalEntries = 0;
    state.activitySignature = null;
    state.activityBusy = false;
    state.subagents = [];
    state.subagentsSignature = null;
    state.stoppingSubagent = null;
    state.approvals = [];
    $("transcript-entries").replaceChildren();
    $("activity").classList.add("hidden");
    renderSubagents([]);
    renderApprovals([]);
    $("prompt").disabled = true;
    $("thread-title").textContent = "Agent session";
    renderSelectedAgent();
    $("thread-state").textContent = "No session";
    $("thread-state").className = "state-pill";
    renderEmptyWorkspace();
    notice("The selected thread is no longer exposed in desktop Zed.");
  } else if (state.threadId && priorHealth !== null && priorHealth !== nextHealth) {
    await refreshSnapshot();
  }
}

async function createSession(event) {
  event.preventDefault();
  if (state.creatingThread || !state.capabilities.includes("thread.create")) return;
  const requestId = crypto.randomUUID();
  const title = $("new-session-title").value.trim();
  const agentId = $("new-session-agent").value || null;
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
        agent_id: agentId,
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

async function loadCreateOptions() {
  const row = $("new-session-agent-row");
  const select = $("new-session-agent");
  state.createOptions = null;
  select.replaceChildren();
  row.classList.add("hidden");
  if (!state.capabilities.includes("thread.create.options")) return;
  const result = await rpc("thread.create.options", {
    instance_id: state.instanceId,
    epoch: state.epoch,
  });
  identity(result);
  if (!Array.isArray(result.agents) || !result.agents.length) return;
  state.createOptions = result;
  for (const agent of result.agents) {
    if (typeof agent.id !== "string" || typeof agent.name !== "string") continue;
    const option = document.createElement("option");
    option.value = agent.id;
    option.textContent = `${agent.name}${agent.kind === "external_acp" ? " · ACP" : ""}`;
    select.append(option);
  }
  row.classList.toggle("hidden", select.options.length < 2);
  $("new-session-help").textContent = `Project ${result.project || "approved in Zed"} · configuration remains in the selected agent.`;
}

function validAgentError(error) {
  if (!error || typeof error !== "object") return null;
  if (typeof error.title !== "string" || typeof error.message !== "string") return null;
  const unsupportedImage = /image input/i.test(error.message) && /vision/i.test(error.message);
  return {
    kind: unsupportedImage ? "unsupported_image_input" : typeof error.kind === "string" ? error.kind : "agent_error",
    title: unsupportedImage ? "Image input unavailable" : error.title,
    message: error.message,
    retrying: unsupportedImage ? false : error.retrying === true,
  };
}

function validRetryStatus(retry) {
  if (!retry || typeof retry !== "object") return null;
  if (!Number.isInteger(retry.attempt) || !Number.isInteger(retry.max_attempts)) return null;
  return {
    lastError: typeof retry.last_error === "string" ? retry.last_error : "The model request failed.",
    attempt: retry.attempt,
    maxAttempts: retry.max_attempts,
    nextAttemptMs: Number.isFinite(retry.next_attempt_in_ms) ? Math.max(0, retry.next_attempt_in_ms) : 0,
  };
}

function validImageRecovery(recovery) {
  if (!recovery || typeof recovery !== "object") return null;
  if (typeof recovery.client_user_message_id !== "string" || !recovery.client_user_message_id) return null;
  if (!Number.isInteger(recovery.entry_index) || !Number.isInteger(recovery.entries_removed)) return null;
  return {
    clientUserMessageId: recovery.client_user_message_id,
    entryIndex: recovery.entry_index,
    entriesRemoved: recovery.entries_removed,
  };
}

function renderAgentHealth() {
  const panel = $("agent-health");
  const retry = state.retryStatus;
  const error = state.threadError;
  const signature = retry
    ? `retry:${retry.lastError}:${retry.attempt}:${retry.maxAttempts}`
    : error ? `error:${error.kind}:${error.message}` : null;
  const newlyVisible = signature && signature !== state.errorSignature;
  state.errorSignature = signature;
  panel.classList.toggle("hidden", !retry && !error);
  panel.classList.toggle("retrying", !!retry);
  const rewind = $("rewind-image");
  const canRewind = error?.kind === "unsupported_image_input" && !!state.imageRecovery
    && state.capabilities.includes("thread.rewind_image") && state.threadStatus === "Idle";
  rewind.classList.toggle("hidden", !canRewind);
  rewind.disabled = state.rewindingImage;
  rewind.textContent = state.rewindingImage ? "Rewinding…" : "Rewind before image";
  renderHeaderModel();
  if (!retry && !error) return;
  if (retry) {
    const seconds = Math.max(1, Math.ceil(retry.nextAttemptMs / 1000));
    $("agent-health-title").textContent = "Zed is retrying the model request";
    $("agent-health-message").textContent = retry.lastError;
    $("agent-health-recovery").textContent = `Attempt ${retry.attempt} of ${retry.maxAttempts} · ${seconds}s`;
  } else {
    $("agent-health-title").textContent = error.title;
    $("agent-health-message").textContent = error.message;
    if (error.kind === "unsupported_image_input") {
      $("agent-health-message").textContent = state.imageRecovery
        ? `${error.message} This thread still contains that image, so another message will repeat the failure.`
        : error.message;
      $("agent-health-recovery").textContent = canRewind
        ? `${state.imageRecovery.entriesRemoved} conversation item${state.imageRecovery.entriesRemoved === 1 ? "" : "s"} will be removed`
        : state.imageRecovery ? "Wait until the current turn is idle" : "Use a vision model or a new text-only thread";
    } else {
      $("agent-health-recovery").textContent = error.retrying
        ? "Zed may retry · restore the model endpoint"
        : "Check desktop Zed";
    }
  }
  renderConnectionHealth();
  if (newlyVisible) requestAnimationFrame(() => panel.scrollIntoView({
    block: "nearest",
    behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
  }));
}

let sessionFilter = "All";
const sessionSummaryCache = new Map();
const sessionObserved = new Map();
const sessionUpdated = new Set();
function sessionKey(thread) { return JSON.stringify([state.gatewayId, state.targetId, thread.thread_id]); }
function sessionPins() {
  try { const saved = JSON.parse(safeStore.read(`zedlink.sessionPins.${targetScope()}`) || "[]"); return new Set(Array.isArray(saved) ? saved.filter((id) => typeof id === "string") : []); }
  catch { return new Set(); }
}
function sessionActivity(thread) {
  if (thread.approval_count > 0) return { label: `Approval needed (${thread.approval_count})`, attention: true };
  if (thread.input_count > 0) return { label: `Input needed (${thread.input_count})`, attention: true };
  if (validRetryStatus(thread.retry_status)) return { label: "Retrying", running: true };
  if (thread.status === "Idle" && (thread.had_error || validAgentError(thread.agent_error))) return { label: "Request failed", attention: true };
  if (thread.status === "Generating") return { label: "Generating", running: true };
  return { label: thread.status === "Idle" ? "Ready" : "Unknown" };
}
function renderThreads() {
  const list = $("thread-list"); list.replaceChildren();
  const pins = sessionPins();
  const query = $("session-search").value.trim().toLocaleLowerCase();
  const visible = state.threads.filter((thread) => {
    const activity = sessionActivity(thread);
    return `${thread.title || ""} ${normalizeAgent(thread.agent).name} ${thread.thread_id}`.toLocaleLowerCase().includes(query) &&
      (sessionFilter === "All" || sessionFilter === "Needs attention" && activity.attention || sessionFilter === "Running" && activity.running || sessionFilter === "Pinned" && pins.has(thread.thread_id));
  }).sort((a, b) => Number(pins.has(b.thread_id)) - Number(pins.has(a.thread_id)) || (a.title || "").localeCompare(b.title || ""));
  $("thread-count").textContent = String(visible.length);
  if (!visible.length) {
    const text = document.createElement("p"); text.className = "muted";
    text.textContent = state.threads.length ? "No sessions match this search or filter." : state.live ? "No exposed sessions. Choose /remote-control in desktop Zed or create a session using +." : "Sessions unavailable. Reconnect to refresh the list.";
    list.append(text);
  }
  for (const group of ["Needs attention", "Running", "Ready & other"]) {
    const rows = visible.filter((thread) => { const a = sessionActivity(thread); return (a.attention ? "Needs attention" : a.running ? "Running" : "Ready & other") === group; });
    if (!rows.length) continue;
    const heading = document.createElement("h3"); heading.className = "session-group"; heading.textContent = `${group} · ${rows.length}`; list.append(heading);
    for (const thread of rows) {
      const activity = sessionActivity(thread);
      const row = document.createElement("div"); row.className = "session-row";
      const button = document.createElement("button"); button.type = "button";
      button.className = `thread-item ${thread.thread_id === state.threadId ? "active" : ""} ${activity.running && state.live ? "running" : ""} ${activity.attention ? "error" : ""}`;
      const badge = document.createElement("span"); badge.className = "thread-badge"; badge.textContent = normalizeAgent(thread.agent).name.toLocaleUpperCase();
      const status = document.createElement("span"); status.className = `thread-status ${activity.running ? "busy" : ""} ${activity.attention ? "error" : ""}`;
      if (activity.running && state.live) { const progress = document.createElement("span"); progress.className = "thread-progress"; progress.setAttribute("aria-hidden", "true"); progress.append(document.createElement("i"), document.createElement("i"), document.createElement("i")); status.append(progress); }
      const label = document.createElement("span"); label.textContent = `${state.live ? "" : "Last known: "}${activity.label}`; status.append(label);
      const title = document.createElement("strong"); title.textContent = thread.title || "Untitled Agent thread";
      button.append(badge, status, title);
      if (sessionUpdated.has(sessionKey(thread))) { const update = document.createElement("small"); update.textContent = "New activity"; button.append(update); }
      button.addEventListener("click", () => { sessionUpdated.delete(sessionKey(thread)); selectThread(thread.thread_id); });
      const pin = document.createElement("button"); pin.type = "button"; pin.className = "session-pin"; pin.textContent = "⌖";
      pin.setAttribute("aria-label", `${pins.has(thread.thread_id) ? "Unpin" : "Pin"} ${thread.title || "session"}`); pin.setAttribute("aria-pressed", String(pins.has(thread.thread_id)));
      pin.addEventListener("click", () => { const saved = sessionPins(); if (saved.has(thread.thread_id)) saved.delete(thread.thread_id); else saved.add(thread.thread_id); safeStore.write(`zedlink.sessionPins.${targetScope()}`, JSON.stringify([...saved])); renderThreads(); });
      row.append(button, pin); list.append(row);
    }
  }
  renderEmptyWorkspace();
}
$("session-filters").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-filter]"); if (!button) return;
  sessionFilter = button.dataset.filter;
  for (const item of $("session-filters").querySelectorAll("button")) item.setAttribute("aria-pressed", String(item === button));
  renderThreads();
});

async function selectThread(threadId) {
  stopDictation();
  if ($("clipboard-dialog").open) closeClipboard();
  closeEventStream("connecting");
  state.errorSignature = null;
  state.threadId = threadId;
  document.body.classList.remove("no-session");
  $("empty-state").classList.add("hidden");
  $("show-context").disabled = false;
  safeStore.write(selectedThreadKey(), threadId);
  state.commands = [];
  renderCommands();
  state.turnId = null;
  state.threadStatus = null;
  state.threadError = null;
  state.retryStatus = null;
  state.imageRecovery = null;
  state.rewindingImage = false;
  renderAgentHealth();
  state.threadSettings = null;
  state.projectFolderEntries = null;
  state.directoryRequest += 1;
  state.projectDirectory = "";
  state.previewRequest += 1;
  $("context-files").classList.remove("file-reading");
  state.projectFiles = [];
  state.projectSearchMatches = [];
  state.projectSearchTruncated = false;
  state.changes = null;
  state.previewPath = null;
  state.previewContent = "";
  state.diffContent = "";
  state.contextPaths = [];
  state.uploads = [];
  renderAttachmentStrip();
  closeCodeReview();
  closeContextPanel();
  updateComposerAction();
  renderThreadSettings();
  document.body.classList.add("thread-open");
  document.body.classList.remove("mobile-sessions");
  updateSidebarToggle();
  state.sequence = 0;
  state.renderedEntries = [];
  state.renderedThreadId = null;
  state.renderedEntryStart = 0;
  state.totalEntries = 0;
  state.activitySignature = null;
  state.activityCollapsed = true;
  state.activityBusy = false;
  $("activity").classList.add("hidden");
  state.subagents = [];
  state.subagentsSignature = null;
  state.stoppingSubagent = null;
  renderSubagents([]);
  $("prompt").disabled = false;
  $("jump-latest").classList.add("hidden");
  updateComposerAction();
  $("thread-title").textContent = state.threads.find((thread) => thread.thread_id === threadId)?.title || "Untitled Agent thread";
  renderSelectedAgent();
  $("prompt").value = safeStore.read(promptDraftKey()) || "";
  $("prompt").dispatchEvent(new Event("input", { bubbles: true }));
  await loadThreads();
  try {
    await refreshSnapshot();
    await loadCommands();
    await loadThreadSettings();
    await Promise.all([loadProjectFiles(), loadChanges()]);
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

function baseThreadParams() {
  return { instance_id: state.instanceId, epoch: state.epoch, thread_id: state.threadId };
}

function baseInstanceParams() {
  return { instance_id: state.instanceId, epoch: state.epoch };
}

function renderAttachmentStrip() {
  const strip = $("attachment-strip");
  strip.replaceChildren();
  const attachments = [
    ...state.contextPaths.map((path) => ({ type: "context", label: path, key: path })),
    ...state.uploads.map((upload, index) => ({ type: "upload", label: upload.name, key: index })),
  ];
  strip.classList.toggle("hidden", attachments.length === 0);
  for (const attachment of attachments) {
    const chip = document.createElement("span");
    chip.className = "attachment-chip";
    const label = document.createElement("span");
    label.textContent = attachment.label;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "×";
    remove.setAttribute("aria-label", `Remove ${attachment.label}`);
    remove.addEventListener("click", () => {
      if (attachment.type === "context") state.contextPaths = state.contextPaths.filter((path) => path !== attachment.key);
      else state.uploads.splice(attachment.key, 1);
      renderAttachmentStrip();
    });
    chip.append(label, remove);
    strip.append(chip);
  }
}

const LANGUAGE_KEYWORDS = {
  rust: new Set("as async await break const continue crate dyn else enum extern false fn for if impl in let loop match mod move mut pub ref return self Self static struct super trait true type unsafe use where while".split(" ")),
  javascript: new Set("async await break case catch class const continue debugger default delete do else export extends false finally for from function get if import in instanceof let new null of return set static super switch this throw true try typeof undefined var void while with yield".split(" ")),
  typescript: new Set("abstract any as async await boolean break case catch class const constructor continue declare default delete do else enum export extends false finally for from function get if implements import in infer instanceof interface keyof let namespace never new null number object of private protected public readonly return set static string super switch symbol this throw true try type typeof undefined unknown var void while with yield".split(" ")),
  python: new Set("and as assert async await break class continue def del elif else except False finally for from global if import in is lambda None nonlocal not or pass raise return True try while with yield".split(" ")),
  shell: new Set("case do done elif else esac fi for function if in select then time until while".split(" ")),
  swift: new Set("actor any as associatedtype async await break case catch class continue convenience default defer deinit do dynamic else enum extension fallthrough false fileprivate final for func get guard if import in indirect init inout internal is isolated let mutating nil nonisolated open operator override private protocol public repeat required rethrows return self Self set some static struct subscript super switch throw throws true try typealias var weak where while".split(" ")),
  go: new Set("break case chan const continue default defer else fallthrough false for func go goto if import interface map nil package range return select struct switch true type var".split(" ")),
  java: new Set("abstract assert boolean break byte case catch char class const continue default do double else enum extends false final finally float for goto if implements import instanceof int interface long native new null package private protected public return short static strictfp super switch synchronized this throw throws transient true try void volatile while".split(" ")),
  c: new Set("auto break case char const continue default do double else enum extern float for goto if inline int long register restrict return short signed sizeof static struct switch typedef union unsigned void volatile while".split(" ")),
};

function languageFromPath(path) {
  const name = String(path || "").toLocaleLowerCase();
  if (name.endsWith(".diff") || name.endsWith(".patch")) return "diff";
  const extension = name.includes(".") ? name.split(".").pop() : "";
  return ({
    rs: "rust", js: "javascript", mjs: "javascript", cjs: "javascript", jsx: "javascript",
    ts: "typescript", tsx: "typescript", py: "python", sh: "shell", bash: "shell", zsh: "shell",
    json: "json", toml: "toml", yaml: "yaml", yml: "yaml", html: "html", htm: "html",
    xml: "html", css: "css", scss: "css", c: "c", h: "c", cc: "c", cpp: "c", hpp: "c",
    java: "java", go: "go", swift: "swift", kt: "java", kts: "java", md: "markdown",
  })[extension] || "text";
}

function appendSyntaxLine(target, line, language) {
  if (language === "diff") {
    target.textContent = line;
    return;
  }
  const keywords = LANGUAGE_KEYWORDS[language] || new Set();
  const tokenPattern = /("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`|\/\/.*$|#.*$|\b(?:0x[\da-fA-F]+|\d+(?:\.\d+)?)\b|\b[A-Za-z_$][\w$]*\b)/g;
  let offset = 0;
  for (const match of line.matchAll(tokenPattern)) {
    if (match.index > offset) target.append(document.createTextNode(line.slice(offset, match.index)));
    const token = match[0];
    const span = document.createElement("span");
    if (token.startsWith("//") || token.startsWith("#")) span.className = "syntax-comment";
    else if (/^["'`]/.test(token)) span.className = "syntax-string";
    else if (/^(?:0x[\da-f]+|\d)/i.test(token)) span.className = "syntax-number";
    else if (keywords.has(token)) span.className = "syntax-keyword";
    else if (/^[A-Z][A-Za-z0-9_]*$/.test(token)) span.className = "syntax-type";
    span.textContent = token;
    target.append(span);
    offset = match.index + token.length;
  }
  if (offset < line.length) target.append(document.createTextNode(line.slice(offset)));
}

function renderReviewCode(target, source, language = "text", focusLine = null, query = "") {
  target.replaceChildren();
  const normalizedQuery = query.toLocaleLowerCase();
  let hits = 0;
  let focused = null;
  String(source).split("\n").forEach((line, index) => {
    const row = document.createElement("span");
    row.className = "code-line";
    if (language === "diff") {
      if (line.startsWith("+") && !line.startsWith("+++")) row.classList.add("syntax-diff-add");
      else if (line.startsWith("-") && !line.startsWith("---")) row.classList.add("syntax-diff-remove");
      else if (line.startsWith("@@") || line.startsWith("diff --git") || line.startsWith("index ")) row.classList.add("syntax-diff-hunk");
    }
    const lineNumber = document.createElement("span");
    lineNumber.className = "code-line-number";
    lineNumber.textContent = String(index + 1);
    lineNumber.setAttribute("aria-hidden", "true");
    const text = document.createElement("span");
    text.className = "code-line-text";
    appendSyntaxLine(text, line, language);
    if (focusLine === index + 1) {
      row.classList.add("focus-line");
      focused = row;
    }
    if (normalizedQuery) {
      const haystack = line.toLocaleLowerCase();
      let position = 0;
      let lineHits = 0;
      while ((position = haystack.indexOf(normalizedQuery, position)) !== -1) {
        lineHits += 1;
        position += Math.max(1, normalizedQuery.length);
      }
      if (lineHits) row.classList.add("search-hit");
      hits += lineHits;
    }
    row.append(lineNumber, text);
    target.append(row);
  });
  if (focused) requestAnimationFrame(() => focused.scrollIntoView({ block: "center" }));
  return hits;
}

function setWrap(pre, button, wrapped) {
  pre.classList.toggle("wrap", wrapped);
  button.setAttribute("aria-pressed", String(wrapped));
  button.textContent = wrapped ? "Unwrap" : "Wrap";
}

function openCodeReview(title, source, language, focusLine = null) {
  state.reviewSource = source;
  state.reviewLanguage = language;
  state.previewFocusLine = focusLine;
  $("code-review-title").textContent = title;
  $("code-review-query").value = "";
  $("code-review-count").textContent = "";
  const panel = $("code-review");
  panel.classList.remove("hidden");
  document.body.classList.add("review-open");
  setWrap(panel.querySelector(".review-code"), $("code-review-wrap"), true);
  renderReviewCode($("code-review-content"), source, language, focusLine);
  $("code-review-query").focus();
}

function closeCodeReview() {
  $("code-review").classList.add("hidden");
  document.body.classList.remove("review-open");
  state.reviewSource = "";
  $("code-review-query").value = "";
  $("code-review-count").textContent = "";
}

async function loadProjectFiles() {
  if (!state.threadId || !state.capabilities.includes("project.files")) {
    state.projectFolderEntries = null;
    state.directoryRequest += 1;
    state.projectDirectory = "";
    state.previewRequest += 1;
    $("context-files").classList.remove("file-reading");
    state.projectFiles = [];
    state.projectFilesTruncated = false;
    renderProjectFiles();
    return;
  }
  const threadId = state.threadId;
  const result = await rpc("project.files", baseThreadParams());
  if (state.threadId !== threadId || !Array.isArray(result.entries)) return;
  state.projectFiles = result.entries.filter((entry) => typeof entry.path === "string");
  state.projectFilesTruncated = result.truncated === true;
  await navigateProjectDirectory(state.projectDirectory);
}

async function navigateProjectDirectory(path) {
  state.projectDirectory = path;
  state.fileListLimit = 250;
  $("file-search").value = "";
  const request = ++state.directoryRequest;
  const scope = JSON.stringify(baseThreadParams());
  state.projectFolderEntries = null;
  renderProjectFiles();
  if (!state.capabilities.includes("project.directory")) return;
  try {
    const result = await rpc("project.directory", { ...baseThreadParams(), path });
    if (request !== state.directoryRequest || scope !== JSON.stringify(baseThreadParams())) return;
    if (result.directory !== path || !Array.isArray(result.entries)) throw new Error("Invalid directory listing.");
    state.projectFolderEntries = result.entries.filter((entry) => typeof entry.path === "string");
    state.projectFolderTruncated = result.truncated === true;
    renderProjectFiles();
  } catch (error) {
    if (request === state.directoryRequest && scope === JSON.stringify(baseThreadParams())) notice(error.message);
  }
}

function renderProjectFiles() {
  const list = $("file-list");
  if (!state.capabilities.includes("project.files")) {
    list.replaceChildren();
    state.fileRenderSignature = null;
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = "Restart the updated patched Zed build to browse project files.";
    list.append(empty);
    return;
  }
  const query = $("file-search").value.trim().toLocaleLowerCase();
  const prefix = state.projectDirectory ? `${state.projectDirectory}/` : "";
  const entries = (query ? state.projectFiles : state.projectFolderEntries || state.projectFiles).filter((entry) => query
    ? entry.path.toLocaleLowerCase().includes(query)
    : entry.path.startsWith(prefix) && !entry.path.slice(prefix.length).includes("/"));
  entries.sort((a, b) => Number(b.kind === "directory") - Number(a.kind === "directory") || a.path.localeCompare(b.path));
  const truncated = query ? state.projectFilesTruncated : state.projectFolderEntries ? state.projectFolderTruncated : state.projectFilesTruncated;
  const signature = JSON.stringify([baseThreadParams(), state.projectDirectory, query, state.fileListLimit, truncated, entries]);
  if (signature === state.fileRenderSignature) return;
  state.fileRenderSignature = signature;
  list.replaceChildren();
  const breadcrumbs = $("file-breadcrumbs");
  breadcrumbs.replaceChildren();
  const parts = state.projectDirectory.split("/").filter(Boolean);
  for (let index = 0; index <= parts.length; index++) {
    const path = parts.slice(0, index).join("/");
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = index ? parts[index - 1] : "Project";
    button.setAttribute("aria-current", index === parts.length ? "location" : "false");
    button.addEventListener("click", () => navigateProjectDirectory(path));
    breadcrumbs.append(button);
  }
  for (const entry of entries.slice(0, state.fileListLimit)) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = `context-row ${entry.kind === "directory" ? "directory" : ""}`;
    row.dataset.path = entry.path;
    row.setAttribute("aria-label", `${entry.kind === "directory" ? "Open folder" : "Read file"} ${entry.path}`);
    const icon = document.createElement("span");
    icon.className = "file-entry-icon";
    icon.textContent = entry.kind === "directory" ? "▸" : "≡";
    icon.setAttribute("aria-hidden", "true");
    const name = document.createElement("span");
    name.textContent = query ? entry.path : entry.path.slice(prefix.length);
    const detail = document.createElement("small");
    detail.textContent = entry.kind === "directory" ? "Folder" : Number.isFinite(entry.size) ? `${entry.size} B` : "File";
    row.append(icon, name, detail);
    row.addEventListener("click", () => {
      if (entry.kind === "directory") navigateProjectDirectory(entry.path);
      else previewProjectFile(entry.path);
    });
    list.append(row);
  }
  if (!entries.length) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = query ? "No project files match this search." : "No remotely readable project files.";
    list.append(empty);
  }
  if (entries.length > state.fileListLimit) {
    const more = document.createElement("button");
    more.type = "button"; more.className = "quiet"; more.textContent = "Show more files";
    more.addEventListener("click", () => { state.fileListLimit += 250; renderProjectFiles(); });
    list.append(more);
  }
  if (query ? state.projectFilesTruncated : state.projectFolderEntries ? state.projectFolderTruncated : state.projectFilesTruncated) {
    const note = document.createElement("p");
    note.className = "muted";
    note.textContent = "Listing limited to 1,000 entries. Browse a folder to read its contents. Hidden, ignored and private files are excluded.";
    list.append(note);
  }
}

async function previewProjectFile(path, focusLine = null) {
  $("file-search").blur();
  $("project-search").blur();
  const request = ++state.previewRequest;
  const scope = JSON.stringify(baseThreadParams());
  $("file-preview-name").textContent = path;
  $("file-preview-content").textContent = "Loading file…";
  $("file-preview-note").textContent = "";
  $("attach-preview").disabled = true;
  $("expand-file").disabled = true;
  $("file-preview").classList.remove("hidden");
  $("context-files").classList.add("file-reading");
  try {
    const result = await rpc("project.file", { ...baseThreadParams(), path });
    if (request !== state.previewRequest || scope !== JSON.stringify(baseThreadParams())) return;
    if (result.path !== path || typeof result.content !== "string") throw new Error("Zed returned an invalid file preview.");
    $("expand-file").disabled = false;
    state.previewPath = path;
    state.previewContent = result.content;
    state.previewFocusLine = focusLine;
    const language = languageFromPath(path);
    $("file-preview-name").textContent = path;
    renderReviewCode($("file-preview-content"), result.content, language, focusLine);
    setWrap($("file-preview").querySelector(".review-code"), $("wrap-file"), true);
    const lineCount = result.content.split("\n").length;
    $("file-preview-note").textContent = result.truncated
      ? `${language.toUpperCase()} · ${lineCount} lines · Preview truncated at 256 KiB. Truncated files cannot be attached.`
      : `${language.toUpperCase()} · ${lineCount} lines · Read-only preview from the exposed Zed project.`;
    $("attach-preview").disabled = result.truncated === true || state.contextPaths.includes(path);
    $("file-preview").classList.remove("hidden");
  } catch (error) {
    if (request !== state.previewRequest || scope !== JSON.stringify(baseThreadParams())) return;
    $("file-preview-content").textContent = "File unavailable.";
    $("file-preview-note").textContent = error.message;
  }
}

function renderProjectSearchResults() {
  const list = $("project-search-results");
  const status = $("project-search-status");
  list.replaceChildren();
  list.classList.toggle("hidden", state.projectSearchMatches.length === 0);
  if (!state.projectSearchMatches.length) return;
  for (const match of state.projectSearchMatches) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "search-result";
    const path = document.createElement("strong");
    path.textContent = match.path;
    const location = document.createElement("small");
    location.textContent = `${match.line}:${match.column}`;
    const preview = document.createElement("span");
    preview.textContent = match.preview;
    row.append(path, location, preview);
    row.addEventListener("click", () => previewProjectFile(match.path, match.line));
    list.append(row);
  }
  status.classList.remove("hidden");
  status.textContent = `${state.projectSearchMatches.length} match${state.projectSearchMatches.length === 1 ? "" : "es"}${state.projectSearchTruncated ? " · results limited" : ""}`;
}

async function searchProject(event) {
  event.preventDefault();
  const query = $("project-search").value.trim();
  const status = $("project-search-status");
  state.projectSearchMatches = [];
  state.projectSearchTruncated = false;
  $("project-search-results").replaceChildren();
  $("project-search-results").classList.add("hidden");
  if (query.length < 2) {
    status.textContent = "Enter at least two characters.";
    status.classList.remove("hidden");
    return;
  }
  if (!state.capabilities.includes("project.search")) {
    status.textContent = "Restart the updated patched Zed build to search inside project files.";
    status.classList.remove("hidden");
    return;
  }
  const threadId = state.threadId;
  const button = $("project-search-form").querySelector("button");
  button.disabled = true;
  button.textContent = "Searching…";
  status.textContent = "Searching the exposed project in desktop Zed…";
  status.classList.remove("hidden");
  try {
    for (let attempt = 0; attempt < 40; attempt += 1) {
      const result = await rpc("project.search", { ...baseThreadParams(), query, case_sensitive: false });
      if (state.threadId !== threadId) return;
      if (result.outcome === "ready") {
        if (!Array.isArray(result.matches)) throw new Error("Zed returned invalid search results.");
        state.projectSearchMatches = result.matches.filter((match) =>
          typeof match.path === "string" && Number.isInteger(match.line) && Number.isInteger(match.column) && typeof match.preview === "string");
        state.projectSearchTruncated = result.truncated === true;
        if (!state.projectSearchMatches.length) status.textContent = `No project text matches “${query}”.`;
        renderProjectSearchResults();
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
    throw new Error("Project search timed out. Try again.");
  } catch (error) {
    status.textContent = error.message;
    status.classList.remove("hidden");
  } finally {
    button.disabled = false;
    button.textContent = "Search";
  }
}

function attachPreview() {
  if (!state.previewPath || state.contextPaths.includes(state.previewPath)) return;
  if (state.contextPaths.length + state.uploads.length >= 8) {
    notice("A prompt can include at most eight attachments.");
    return;
  }
  state.contextPaths.push(state.previewPath);
  $("attach-preview").disabled = true;
  renderAttachmentStrip();
  closeContextPanel();
  $("prompt").focus();
}

async function loadChanges() {
  if (!state.threadId || !state.capabilities.includes("changes.snapshot")) {
    state.changes = null;
    renderChanges();
    return;
  }
  const threadId = state.threadId;
  const result = await rpc("changes.snapshot", baseThreadParams());
  if (state.threadId !== threadId || !Array.isArray(result.entries)) return;
  state.changes = result;
  renderChanges();
}

function renderChanges() {
  const summary = $("changes-summary");
  const list = $("changes-list");
  list.replaceChildren();
  $("git-diff").classList.add("hidden");
  $("diff-search").classList.add("hidden");
  $("wrap-diff").classList.add("hidden");
  $("expand-diff").classList.add("hidden");
  $("diff-search-count").textContent = "";
  state.diffContent = "";
  $("load-diff").disabled = true;
  if (!state.capabilities.includes("changes.snapshot")) {
    summary.textContent = "Restart the updated patched Zed build to inspect repository changes.";
    return;
  }
  if (!state.changes?.repository) {
    summary.textContent = "No active Git repository is available for this exposed project.";
    return;
  }
  const repository = state.changes.repository;
  $("load-diff").disabled = !state.capabilities.includes("changes.diff");
  summary.textContent = `${repository.branch || "Detached HEAD"} · ${state.changes.entries.length} changed file${state.changes.entries.length === 1 ? "" : "s"}`;
  for (const entry of state.changes.entries) {
    const item = document.createElement("div");
    item.className = "change-item";
    const row = document.createElement("button");
    row.type = "button";
    row.className = "context-row";
    const path = document.createElement("span");
    path.textContent = entry.path;
    const status = document.createElement("small");
    status.textContent = `${String(entry.status || "changed").toUpperCase()} · ${String(entry.staging || "unstaged").toUpperCase()}`;
    row.append(path, status);
    row.addEventListener("click", () => {
      const projectPath = state.projectFiles.find((file) => file.kind === "file" && (file.path === entry.path || entry.path.endsWith(`/${file.path}`)))?.path;
      if (projectPath) previewProjectFile(projectPath);
      switchContextTab("files");
    });
    item.append(row);
    const operation = document.createElement("button");
    operation.type = "button";
    operation.className = "quiet change-action";
    const unstage = entry.staging === "staged";
    operation.textContent = unstage ? "Unstage" : "Stage";
    operation.disabled = !state.capabilities.includes(unstage ? "changes.unstage" : "changes.stage");
    operation.addEventListener("click", () => mutateChanges(entry.path, unstage ? "changes.unstage" : "changes.stage", operation));
    item.append(operation);
    list.append(item);
  }
  if (!state.changes.entries.length) {
    const clean = document.createElement("p");
    clean.className = "muted";
    clean.textContent = "Working tree clean.";
    list.append(clean);
  }
}

async function mutateChanges(path, method, button) {
  const revision = state.changes?.repository?.revision;
  if (!revision) return;
  const requestId = crypto.randomUUID();
  button.disabled = true;
  const original = button.textContent;
  button.textContent = `${original}…`;
  try {
    for (let attempt = 0; attempt < 40; attempt += 1) {
      const result = await rpc(method, { ...baseThreadParams(), revision, paths: [path] }, requestId);
      if (result.outcome === "succeeded") {
        notice(`${original}d ${path} in desktop Zed.`);
        await loadChanges();
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
    throw new Error(`Zed did not finish ${original.toLocaleLowerCase()}ing ${path}.`);
  } catch (error) { notice(error.message); }
  finally {
    button.textContent = original;
    button.disabled = false;
  }
}

async function loadGitDiff() {
  const revision = state.changes?.repository?.revision;
  if (!revision || !state.capabilities.includes("changes.diff")) return;
  const button = $("load-diff");
  button.disabled = true;
  button.textContent = "Loading diff…";
  try {
    for (let attempt = 0; attempt < 40; attempt += 1) {
      const result = await rpc("changes.diff", { ...baseThreadParams(), revision });
      if (result.revision !== revision) throw new Error("Zed returned a diff for another repository revision.");
      if (result.outcome === "ready") {
        state.diffContent = result.diff || "No textual diff.";
        renderReviewCode($("git-diff").querySelector("code"), state.diffContent, "diff", null, $("diff-search").value);
        setWrap($("git-diff"), $("wrap-diff"), true);
        for (const id of ["git-diff", "diff-search", "wrap-diff", "expand-diff"]) $(id).classList.remove("hidden");
        button.textContent = result.truncated ? "Diff truncated" : "Refresh unified diff";
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
    throw new Error("The native Git diff timed out. Try again.");
  } catch (error) {
    notice(error.message);
    button.textContent = "View unified diff";
  } finally {
    button.disabled = false;
  }
}

async function loadTerminals() {
  await refreshCapabilities();
  await loadTaskCatalog();
  if (!state.capabilities.includes("terminal.list")) {
    state.terminals = [];
    state.selectedTerminalId = null;
    state.terminalSnapshot = null;
    renderTerminals();
    return;
  }
  const result = await rpc("terminal.list", baseInstanceParams());
  state.terminals = Array.isArray(result.terminals) ? result.terminals : [];
  if (!state.terminals.some((terminal) => terminal.terminal_id === state.selectedTerminalId)) {
    const remembered = safeStore.read(terminalRecoveryKey());
    state.selectedTerminalId = state.terminals.find((terminal) => terminal.terminal_id === remembered)?.terminal_id || state.terminals[0]?.terminal_id || null;
  }
  renderTerminals();
  if (state.selectedTerminalId) {
    safeStore.write(terminalRecoveryKey(), state.selectedTerminalId);
    await loadTerminalSnapshot();
  }
}

async function loadTaskCatalog() {
  if (!state.capabilities.includes("task.catalog")) {
    state.taskCatalog = [];
    renderTaskCatalog();
    return;
  }
  const result = await rpc("task.catalog", baseInstanceParams());
  state.taskCatalog = Array.isArray(result.tasks) ? result.tasks : [];
  renderTaskCatalog();
}

function renderTaskCatalog() {
  const select = $("task-select");
  const supported = state.capabilities.includes("task.catalog");
  $("task-launcher").classList.toggle("hidden", !supported);
  const prior = select.value;
  select.replaceChildren();
  for (const task of state.taskCatalog) {
    const option = document.createElement("option");
    option.value = task.task_id;
    option.textContent = task.source ? `${task.label} · ${task.source}` : task.label;
    select.append(option);
  }
  if (!state.taskCatalog.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = supported ? "No configured tasks" : "Task launching unavailable";
    select.append(option);
  }
  if (state.taskCatalog.some((task) => task.task_id === prior)) select.value = prior;
  const enabled = state.capabilities.includes("task.run") && state.taskCatalog.length > 0;
  select.disabled = !enabled;
  $("run-task").disabled = !enabled;
  $("task-help").textContent = supported
    ? "Runs the selected task through Zed's configured task inventory."
    : "Enable Start Configured Tasks in ZedLink settings.";
}

async function runConfiguredTask(event) {
  event.preventDefault();
  const taskId = $("task-select").value;
  if (!taskId || !state.capabilities.includes("task.run")) return;
  $("run-task").disabled = true;
  try {
    await rpc("task.run", { ...baseInstanceParams(), task_id: taskId }, crypto.randomUUID());
    notice("Zed started the configured task.");
    await new Promise((resolve) => setTimeout(resolve, 250));
    await loadTerminals();
  } catch (error) { notice(error.message); }
  finally { $("run-task").disabled = false; }
}

async function loadDebugger() {
  if (state.capabilities.includes("debugger.catalog")) {
    const catalog = await rpc("debugger.catalog", baseInstanceParams());
    state.debuggerCatalog = Array.isArray(catalog.scenarios) ? catalog.scenarios : [];
  } else {
    state.debuggerCatalog = [];
  }
  if (!state.capabilities.includes("debugger.snapshot")) {
    state.debuggerSessions = [];
    renderDebugger();
    return;
  }
  const result = await rpc("debugger.snapshot", baseInstanceParams());
  state.debuggerSessions = Array.isArray(result.sessions) ? result.sessions : [];
  state.lastDebuggerSnapshotAt = Date.now();
  renderDebugger();
}

function debuggerButton(label, action, session, thread = null) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = action === "stop" ? "danger" : "quiet";
  button.textContent = label;
  button.disabled = !state.capabilities.includes("debugger.control");
  button.addEventListener("click", () => controlDebugger(session.session_id, action, thread?.thread_id));
  return button;
}

function renderDebugger() {
  const select = $("debugger-select");
  const prior = select.value;
  select.replaceChildren();
  for (const scenario of state.debuggerCatalog) {
    const option = document.createElement("option");
    option.value = scenario.scenario_id;
    option.textContent = `${scenario.label} · ${scenario.adapter}`;
    select.append(option);
  }
  if (!state.debuggerCatalog.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = state.capabilities.includes("debugger.catalog") ? "No configured debuggers" : "Debugger launching disabled";
    select.append(option);
  }
  if (state.debuggerCatalog.some((scenario) => scenario.scenario_id === prior)) select.value = prior;
  const launchEnabled = state.capabilities.includes("debugger.launch") && state.debuggerCatalog.length > 0;
  select.disabled = !launchEnabled;
  $("launch-debugger").disabled = !launchEnabled;
  $("debugger-launch-help").textContent = state.capabilities.includes("debugger.catalog")
    ? "Starts only a debugger configuration already saved in Zed for this project."
    : "Enable Start Configured Debuggers in desktop ZedLink settings, then restart patched Zed.";
  const list = $("debugger-list");
  list.replaceChildren();
  const supported = state.capabilities.includes("debugger.snapshot");
  $("debug-help").textContent = supported
    ? "Controls use the same native DAP session shown in desktop Zed."
    : "Enable View Debugger Sessions in desktop ZedLink settings, then restart patched Zed.";
  for (const session of state.debuggerSessions) {
    const article = document.createElement("article");
    article.className = "debug-session";
    const header = document.createElement("header");
    const identity = document.createElement("div");
    const label = document.createElement("strong");
    label.textContent = session.label || "Debugger";
    const adapter = document.createElement("small");
    adapter.textContent = `${session.adapter || "DAP"}${session.terminated ? " · stopped" : ""}`;
    identity.append(label, adapter);
    const sessionActions = document.createElement("div");
    sessionActions.className = "debug-actions";
    if (!session.terminated) {
      if (session.capabilities?.restart) sessionActions.append(debuggerButton("Restart", "restart", session));
      sessionActions.append(debuggerButton("Stop", "stop", session));
    }
    header.append(identity, sessionActions);
    article.append(header);
    for (const thread of session.threads || []) {
      const row = document.createElement("div");
      row.className = "debug-thread";
      const info = document.createElement("div");
      const name = document.createElement("span");
      name.textContent = thread.name || `Thread ${thread.thread_id}`;
      const status = document.createElement("small");
      status.textContent = String(thread.status || "unknown").toUpperCase();
      info.append(name, status);
      const actions = document.createElement("div");
      actions.className = "debug-actions";
      if (thread.status === "running") actions.append(debuggerButton("Pause", "pause", session, thread));
      if (thread.status === "stopped") {
        actions.append(
          debuggerButton("Continue", "continue", session, thread),
          debuggerButton("Over", "step_over", session, thread),
          debuggerButton("Into", "step_in", session, thread),
          debuggerButton("Out", "step_out", session, thread),
        );
        if (session.capabilities?.step_back) actions.append(debuggerButton("Back", "step_back", session, thread));
      }
      row.append(info, actions);
      article.append(row);
    }
    list.append(article);
  }
  if (!state.debuggerSessions.length) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = supported ? "No debugger session is running in this Zed project." : "Debugger access is unavailable.";
    list.append(empty);
  }
}

async function launchConfiguredDebugger(event) {
  event.preventDefault();
  const scenarioId = $("debugger-select").value;
  if (!scenarioId || !state.capabilities.includes("debugger.launch")) return;
  $("launch-debugger").disabled = true;
  try {
    await rpc("debugger.launch", { ...baseInstanceParams(), scenario_id: scenarioId }, crypto.randomUUID());
    notice("Zed started the configured debugger.");
    await new Promise((resolve) => setTimeout(resolve, 350));
    await loadDebugger();
  } catch (error) { notice(error.message); }
  finally { $("launch-debugger").disabled = false; }
}

async function controlDebugger(sessionId, action, threadId) {
  const params = { ...baseInstanceParams(), session_id: sessionId, action };
  if (threadId !== undefined && threadId !== null) params.thread_id = threadId;
  try {
    await rpc("debugger.control", params, crypto.randomUUID());
    await new Promise((resolve) => setTimeout(resolve, 180));
    await loadDebugger();
  } catch (error) { notice(error.message); }
}

async function loadTerminalSnapshot() {
  if (!state.selectedTerminalId || !state.capabilities.includes("terminal.snapshot")) return;
  const terminalId = state.selectedTerminalId;
  const result = await rpc("terminal.snapshot", { ...baseInstanceParams(), terminal_id: terminalId });
  if (state.selectedTerminalId !== terminalId) return;
  state.terminalSnapshot = result;
  state.lastTerminalSnapshotAt = Date.now();
  renderTerminalSnapshot();
}

function renderTerminals() {
  const select = $("terminal-select");
  const prior = state.selectedTerminalId;
  select.replaceChildren();
  const supported = state.capabilities.includes("terminal.list");
  const canInput = state.capabilities.includes("terminal.input");
  $("terminal-mode").textContent = supported ? (canInput ? "Interactive" : "Read only") : "Access off";
  $("terminal-mode").title = $("terminal-mode").textContent;
  $("terminal-mode").setAttribute("aria-label", $("terminal-mode").textContent);
  $("copy-terminal").disabled = !state.terminalSnapshot;
  $("terminal-mode").dataset.state = supported ? (canInput ? "interactive" : "readonly") : "off";
  $("terminal-help").textContent = supported
    ? (canInput ? "Live output and input from the selected terminal in desktop Zed." : "Terminal output is available. Enable Send Terminal Input in ZedLink settings to type here.")
    : "Enable View Project Terminals in ZedLink settings. Changes now apply without restarting Zed.";
  for (const terminal of state.terminals) {
    const option = document.createElement("option");
    option.value = terminal.terminal_id;
    const status = terminal.task?.status?.state;
    option.textContent = `${terminal.title || "Terminal"}${status ? ` · ${status}` : ""}`;
    select.append(option);
  }
  if (!state.terminals.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = supported ? "No terminal open in Zed" : "Terminal access unavailable";
    select.append(option);
  }
  select.disabled = !supported || !state.terminals.length;
  if (state.terminals.some((terminal) => terminal.terminal_id === prior)) select.value = prior;
  $("terminal-preview").classList.toggle("hidden", !state.selectedTerminalId);
}

function appendTerminalText(container, text) {
  // Private-use shell icons must not expand a native one-cell column into a tofu box.
  for (const segment of text.split(/([\uE000-\uF8FF\u{F0000}-\u{FFFFD}\u{100000}-\u{10FFFD}])/u)) {
    if (!segment) continue;
    const code = segment.codePointAt(0);
    if ((code >= 0xe000 && code <= 0xf8ff) || code >= 0xf0000) {
      const glyph = document.createElement("span");
      glyph.className = "terminal-glyph";
      glyph.textContent = segment;
      container.append(glyph);
    } else container.append(document.createTextNode(segment));
  }
}

function renderTerminalSnapshot() {
  $("copy-terminal").disabled = !state.terminalSnapshot;
  const snapshot = state.terminalSnapshot;
  if (!snapshot || snapshot.terminal?.terminal_id !== state.selectedTerminalId) return;
  const draftKey = `${terminalRecoveryKey()}.${state.selectedTerminalId}.draft`;
  if ($("terminal-input").dataset.draftKey !== draftKey) {
    setTerminalInputMode(false);
    $("terminal-input").dataset.draftKey = draftKey;
    $("terminal-input").value = safeStore.read(draftKey) || "";
  }
  $("terminal-title").textContent = snapshot.terminal.title || "Terminal";
  const output = $("terminal-output");
  const followOutput = !output.textContent || output.scrollHeight - output.scrollTop - output.clientHeight < 36;
  const runs = snapshot.styled_runs;
  if (Array.isArray(runs) && runs.length > 0 && runs.length <= 2048 && runs.every(run => typeof run.text === "string")) {
    const fragment = document.createDocumentFragment();
    for (const run of runs) {
      const span = document.createElement("span");
      appendTerminalText(span, run.text);
      if (/^#[0-9a-f]{6}$/i.test(run.foreground)) span.style.color = run.foreground;
      if (/^#[0-9a-f]{6}$/i.test(run.background)) span.style.backgroundColor = run.background;
      if (run.bold) span.style.fontWeight = "700";
      if (run.italic) span.style.fontStyle = "italic";
      if (run.underline) span.style.textDecoration = "underline";
      if (run.dim) span.style.opacity = "0.7";
      fragment.append(span);
    }
    output.replaceChildren(fragment);
  } else {
    output.replaceChildren();
    appendTerminalText(output, snapshot.content || "");
  }
  if (followOutput) output.scrollTop = output.scrollHeight;
  const canInput = state.capabilities.includes("terminal.input");
  $("terminal-input-form").classList.toggle("hidden", !canInput);
  $("terminal-read-only").classList.toggle("hidden", canInput);
  $("terminal-input").disabled = !canInput;
  $("terminal-keys").classList.toggle("hidden", !canInput);
  $("terminal-hide-keyboard").classList.toggle("hidden", !canInput);
  $("terminal-help").classList.toggle("hidden", canInput);
  const running = snapshot.terminal.task?.status?.state === "running";
  $("terminal-stop").classList.toggle("hidden", !running || !state.capabilities.includes("task.stop"));
}

let terminalLiveInput = false;
let terminalInputQueue = Promise.resolve();
let terminalInputGeneration = 0;
let terminalPendingBytes = 0;
const terminalKeys = { escape: "\x1b", tab: "\t", interrupt: "\x03", up: "\x1b[A", down: "\x1b[B", left: "\x1b[D", right: "\x1b[C", backspace: "\x7f", enter: "\r" };

function queueTerminalInput(input) {
  if (!input || !state.selectedTerminalId || !state.capabilities.includes("terminal.input")) return;
  const bytes = new TextEncoder().encode(input).length;
  if (bytes > 16384 || terminalPendingBytes + bytes > 16384) { notice("Terminal input is too large. Wait for pending input to finish."); return; }
  const params = { ...baseInstanceParams(), terminal_id: state.selectedTerminalId, input };
  const target = state.targetId;
  const generation = terminalInputGeneration;
  const requestId = crypto.randomUUID();
  terminalPendingBytes += bytes;
  terminalInputQueue = terminalInputQueue.then(async () => {
    if (generation !== terminalInputGeneration || params.terminal_id !== state.selectedTerminalId || target !== state.targetId || params.instance_id !== baseInstanceParams().instance_id || params.epoch !== baseInstanceParams().epoch) return;
    try {
      await rpc("terminal.input", params, requestId);
    } catch (error) {
      // Do not replay keystrokes whose delivery is unknown, or send queued input after an error.
      terminalInputGeneration += 1;
      notice(`Terminal input stopped: ${error.message}. Check the terminal before typing again.`);
    }
  }).finally(() => { terminalPendingBytes -= bytes; });
  return terminalInputQueue;
}

async function sendTerminalInput(event) {
  event.preventDefault();
  const input = $("terminal-input");
  const pending = queueTerminalInput(terminalLiveInput || !input.value ? "\r" : `${input.value}\n`);
  if (!pending) return;
  input.value = terminalLiveInput ? "\u200b" : "";
  if (input.dataset.draftKey) safeStore.remove(input.dataset.draftKey);
  await pending;
  await loadTerminalSnapshot();
}

function setTerminalInputMode(live) {
  terminalLiveInput = live;
  $("terminal-live-hint").classList.toggle("hidden", !live);
  const input = $("terminal-input");
  input.value = live ? "\u200b" : "";
  input.placeholder = live ? "Type directly in terminal" : "Type a command";
  $("terminal-live-input").textContent = live ? "Keyboard" : "Command";
  $("terminal-live-input").setAttribute("aria-pressed", String(live));
}

function terminalTypedInput(event) {
  if (!terminalLiveInput || event.isComposing) return;
  const input = $("terminal-input");
  const text = input.value.replaceAll("\u200b", "");
  if (text) queueTerminalInput(text);
  input.value = "\u200b";
}

async function stopSelectedTask() {
  if (!state.selectedTerminalId || !state.capabilities.includes("task.stop")) return;
  try {
    await rpc("task.stop", { ...baseInstanceParams(), terminal_id: state.selectedTerminalId }, crypto.randomUUID());
    await new Promise((resolve) => setTimeout(resolve, 150));
    await loadTerminals();
  } catch (error) { notice(error.message); }
}

function renderActivityIndex() {
  const list = $("activity-index");
  list.replaceChildren();
  const items = $("transcript-entries").querySelectorAll(".message.tool, details.thinking-block");
  items.forEach((item, index) => {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "context-row";
    const label = document.createElement("span");
    label.textContent = item.matches(".message.tool")
      ? item.querySelector(".tool-title")?.textContent || `Tool ${index + 1}`
      : `Thinking ${index + 1}`;
    const kind = document.createElement("small");
    kind.textContent = item.matches(".message.tool") ? "TOOL" : "THINKING";
    row.append(label, kind);
    row.addEventListener("click", () => {
      closeContextPanel();
      item.scrollIntoView({ behavior: "smooth", block: "center" });
      if (item.tagName === "DETAILS") item.open = true;
    });
    list.append(row);
  });
  if (!items.length) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = "No thinking or tool activity is present in the loaded transcript.";
    list.append(empty);
  }
}

$("context-mobile-view").addEventListener("change", (event) => switchContextTab(event.target.value));

function switchContextTab(tab) {
  if (tab === "terminal" && safeStore.read("zedlink.terminalWrap") === null) {
    terminalWrap = matchMedia("(max-width: 760px)").matches;
    renderTerminalWrap();
  }
  document.querySelector(".terminal-tools").open = false;
  $("context-mobile-view").value = tab;
  $("context-panel").classList.toggle("terminal-context", tab === "terminal");
  $("context-panel").classList.toggle("files-context", tab === "files");
  for (const name of ["files", "changes", "terminal", "debug", "activity"]) {
    $(`context-${name}-tab`).setAttribute("aria-selected", String(name === tab));
    $(name === "activity" ? "context-activity-view" : `context-${name}`).classList.toggle("hidden", name !== tab);
  }
  if (tab === "files") loadProjectFiles().catch((error) => notice(error.message));
  if (tab === "changes") loadChanges().catch((error) => notice(error.message));
  if (tab === "terminal") loadTerminals().catch((error) => notice(error.message));
  if (tab === "debug") loadDebugger().catch((error) => notice(error.message));
  if (tab === "activity") renderActivityIndex();
}

function openContextPanel(tab = "files") {
  if (!state.threadId) return;
  document.body.classList.add("context-open");
  $("context-panel").classList.remove("hidden");
  $("show-context").setAttribute("aria-expanded", "true");
  switchContextTab(tab);
}

function closeContextPanel() {
  $("terminal-input").blur();
  terminalInputGeneration += 1;
  document.body.classList.remove("context-open");
  $("context-panel").classList.add("hidden");
  $("show-context").setAttribute("aria-expanded", "false");
}

function readUpload(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error(`Could not read ${file.name}.`));
    reader.onload = () => {
      const value = String(reader.result || "");
      const comma = value.indexOf(",");
      if (comma < 0) reject(new Error(`Could not encode ${file.name}.`));
      else resolve({ name: file.name, mime_type: file.type || "text/plain", data: value.slice(comma + 1) });
    };
    reader.readAsDataURL(file);
  });
}

async function addUploads(files) {
  for (const file of Array.from(files)) {
    if (state.contextPaths.length + state.uploads.length >= 8) {
      notice("A prompt can include at most eight attachments.");
      break;
    }
    if (file.size > 1024 * 1024) {
      notice(`${file.name} is larger than the 1 MiB upload limit.`);
      continue;
    }
    const allowed = file.type.startsWith("text/") || ["application/json", "application/xml", "image/png", "image/jpeg", "image/webp"].includes(file.type);
    if (!allowed) {
      notice(`${file.name} is not a supported text or image file.`);
      continue;
    }
    if (file.type.startsWith("image/") && state.threadSettings?.supports_images === false) {
      notice("The selected Zed model does not support images. Switch to a vision-capable model in desktop Zed, or attach text instead.");
      continue;
    }
    state.uploads.push(await readUpload(file));
  }
  renderAttachmentStrip();
  $("upload-file").value = "";
}

function renderApprovals(approvals) {
  const next = Array.isArray(approvals) ? approvals : [];
  const signature = JSON.stringify(next);
  state.approvals = next;
  if (signature === state.approvalsSignature) return;
  state.approvalsSignature = signature;
  const panel = $("approvals");
  panel.replaceChildren();
  panel.classList.toggle("hidden", state.approvals.length === 0 || !state.capabilities.includes("approval.respond"));
  for (const approval of state.approvals) {
    const card = document.createElement("article");
    card.className = "approval-card";
    const details = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = approval.display || approval.tool_name || "Zed tool approval";
    const kind = document.createElement("span");
    kind.className = "approval-kind";
    kind.textContent = approval.authorization_kind === "action_choice" ? "Choose an action" : "Permission requested";
    if (approval.subagent_id) {
      const origin = document.createElement("span");
      origin.className = "approval-origin";
      const agent = state.subagents.find((item) => item.session_id === approval.subagent_id);
      origin.textContent = `Parallel agent · ${agent?.title || agent?.label || String(approval.subagent_id).slice(0, 10)}`;
      details.append(origin);
    }
    const input = document.createElement("small");
    input.textContent = approval.raw_input
      ? (typeof approval.raw_input === "string" ? approval.raw_input : JSON.stringify(approval.raw_input))
      : "Details unavailable. Actions that can make changes are disabled.";
    details.append(kind, title, input);
    const actions = document.createElement("div");
    actions.className = "approval-actions";
    const permissionOptions = approval.permission_options;
    const decisions = Array.isArray(permissionOptions?.decisions) ? permissionOptions.decisions : [];
    if (permissionOptions?.presentation === "dropdown" || permissionOptions?.presentation === "dropdown_with_patterns") {
      const choices = [...new Map(decisions.filter((decision) => Number.isInteger(decision.choice_index)
          && !Array.isArray(decision.selected_pattern_indices))
        .map((decision) => [decision.choice_index, decision.label])).entries()];
      const selector = document.createElement("select");
      selector.setAttribute("aria-label", "Permission scope");
      for (const [index, label] of choices) selector.add(new Option(label || `Choice ${index + 1}`, String(index)));
      if (permissionOptions.presentation === "dropdown_with_patterns" && Array.isArray(permissionOptions.patterns)
          && permissionOptions.patterns.length) selector.add(new Option("Selected command patterns", "patterns"));
      selector.value = String(choices.at(-1)?.[0] ?? 0);
      const patternList = document.createElement("div");
      patternList.className = "approval-patterns hidden";
      for (const pattern of permissionOptions.patterns || []) {
        const label = document.createElement("label");
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.value = String(pattern.index);
        checkbox.checked = true;
        label.append(checkbox, document.createTextNode(pattern.display_name || `Pattern ${pattern.index + 1}`));
        patternList.append(label);
      }
      selector.addEventListener("change", () => patternList.classList.toggle("hidden", selector.value !== "patterns"));
      const choose = (action) => {
        const patternMode = selector.value === "patterns";
        const choiceIndex = patternMode ? 0 : Number(selector.value);
        const decision = decisions.find((item) => item.choice_index === choiceIndex && item.action === action);
        if (!decision) return;
        const selectedPatternIndices = patternMode
          ? [...patternList.querySelectorAll("input:checked")].map((item) => Number(item.value)) : [];
        respondApproval(approval, decision, selectedPatternIndices);
      };
      const deny = document.createElement("button");
      deny.type = "button"; deny.className = "quiet"; deny.textContent = "Deny";
      deny.addEventListener("click", () => choose("deny"));
      const allow = document.createElement("button");
      allow.type = "button"; allow.className = "primary"; allow.textContent = "Allow";
      allow.disabled = approval.details_truncated;
      allow.addEventListener("click", () => choose("allow"));
      actions.append(selector, patternList, deny, allow);
    } else if (decisions.length) {
      for (const decision of decisions) {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = decision.label || "Choose";
        const rejecting = String(decision.option_kind || "").startsWith("reject");
        button.className = rejecting ? "quiet" : "primary";
        button.disabled = approval.details_truncated && (!rejecting || approval.authorization_kind === "action_choice");
        button.addEventListener("click", () => respondApproval(approval, decision));
        actions.append(button);
      }
    } else {
      const deny = document.createElement("button");
      deny.type = "button"; deny.className = "quiet"; deny.textContent = "Deny";
      deny.disabled = !approval.can_deny_once;
      deny.addEventListener("click", () => respondApproval(approval, { legacyDecision: "deny_once" }));
      const approve = document.createElement("button");
      approve.type = "button"; approve.className = "primary"; approve.textContent = "Approve once";
      approve.disabled = !approval.can_approve_once;
      approve.addEventListener("click", () => respondApproval(approval, { legacyDecision: "approve_once" }));
      actions.append(deny, approve);
    }
    card.append(details, actions);
    panel.append(card);
  }
}

async function respondApproval(approval, decision, selectedPatternIndices = []) {
  const patternIndices = selectedPatternIndices.length
    ? selectedPatternIndices : (Array.isArray(decision.selected_pattern_indices) ? decision.selected_pattern_indices : []);
  try {
    await rpc("approval.respond", {
      ...baseThreadParams(), approval_id: approval.approval_id,
      turn_id: approval.turn_id,
      ...(decision.legacyDecision ? { decision: decision.legacyDecision } : {
        option_id: decision.option_id,
        ...(Number.isInteger(decision.choice_index) ? { choice_index: decision.choice_index } : {}),
        ...(patternIndices.length ? { selected_pattern_indices: patternIndices } : {}),
      }),
      ...(approval.subagent_id ? { subagent_id: approval.subagent_id } : {}),
    });
    notice(`Sent “${decision.label || (decision.legacyDecision === "approve_once" ? "Approve once" : "Deny")}” to Zed.`);
  } catch (error) { notice(error.message); }
  await refreshSnapshot().catch((error) => notice(error.message));
}

function renderElicitations(items) {
  state.elicitations = Array.isArray(items) ? items : [];
  const panel = $("elicitations");
  panel.replaceChildren();
  const pending = state.elicitations.filter((item) => item.status === "pending");
  panel.classList.toggle("hidden", !pending.length || !state.capabilities.includes("elicitation.respond"));
  for (const item of pending) {
    const card = document.createElement("article");
    card.className = "approval-card";
    const form = document.createElement("form");
    const title = document.createElement("strong");
    title.textContent = item.request?.message || "Agent needs more information";
    form.append(title);
    const schema = item.request?.requestedSchema;
    const values = {};
    if (schema?.properties && typeof schema.properties === "object") {
      for (const [name, field] of Object.entries(schema.properties)) {
        const label = document.createElement("label");
        label.className = "setting-field";
        const caption = document.createElement("span");
        caption.textContent = field.title || name;
        let input;
        const choices = Array.isArray(field.enum) ? field.enum
          : Array.isArray(field.oneOf) ? field.oneOf.map((option) => option.const)
          : Array.isArray(field.items?.enum) ? field.items.enum
          : Array.isArray(field.items?.oneOf) ? field.items.oneOf.map((option) => option.const) : [];
        if (field.type === "array") {
          input = document.createElement("fieldset");
          values[name] = [];
          for (const option of choices) {
            const row = document.createElement("label");
            const checkbox = document.createElement("input"); checkbox.type = "checkbox"; checkbox.value = String(option);
            checkbox.addEventListener("change", () => { values[name] = [...input.querySelectorAll("input:checked")].map((item) => item.value); });
            row.append(checkbox, document.createTextNode(String(option))); input.append(row);
          }
        } else if (choices.length) {
          input = document.createElement("select");
          for (const option of choices) input.add(new Option(String(option), String(option)));
        } else {
          input = document.createElement("input");
          input.type = field.type === "boolean" ? "checkbox" : field.type === "number" || field.type === "integer" ? "number" : "text";
        }
        if (Array.isArray(schema.required) && schema.required.includes(name)) input.required = true;
        if (field.type !== "array") {
          input.addEventListener("input", () => {
            values[name] = input.type === "checkbox" ? input.checked
              : field.type === "integer" ? Number.parseInt(input.value, 10)
              : field.type === "number" ? Number(input.value) : input.value;
          });
          input.dispatchEvent(new Event("input"));
        }
        label.append(caption, input);
        form.append(label);
      }
    } else if (typeof item.request?.url === "string") {
      const link = document.createElement("a");
      link.href = item.request.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = "Open secure input page";
      form.append(link);
    }
    const actions = document.createElement("div");
    actions.className = "approval-actions";
    const decline = document.createElement("button");
    decline.type = "button"; decline.className = "quiet"; decline.textContent = "Decline";
    decline.addEventListener("click", () => respondElicitation(item, "decline"));
    const accept = document.createElement("button");
    accept.type = "submit"; accept.className = "primary"; accept.textContent = schema ? "Submit" : "Continue";
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      respondElicitation(item, "accept", values);
    });
    actions.append(decline, accept);
    form.append(actions);
    card.append(form);
    panel.append(card);
  }
}

async function respondElicitation(item, action, content = {}) {
  try {
    await rpc("elicitation.respond", { ...baseThreadParams(), elicitation_id: item.elicitation_id, action, content });
    notice(action === "accept" ? "Input sent to the Agent." : "Input request declined.");
    await refreshAuxiliaryState();
  } catch (error) { notice(error.message); }
}

function renderEditReview(review) {
  state.editReview = review;
  const control = $("edit-review");
  const panel = control.querySelector(".edit-review-menu");
  panel.replaceChildren();
  const visible = !!review?.pending && state.capabilities.includes("thread.edit_review.respond");
  control.classList.toggle("hidden", !visible);
  if (!visible) {
    control.open = false;
    return;
  }
  $("edit-review-count").textContent = String(review.changed_files);
  control.querySelector("summary").setAttribute("aria-label", `Review edits in ${review.changed_files} file${review.changed_files === 1 ? "" : "s"}`);
  const card = document.createElement("article");
  card.className = "approval-card";
  const summary = document.createElement("div");
  const title = document.createElement("strong"); title.textContent = "Review Agent edits";
  const detail = document.createElement("small");
  detail.textContent = `${review.changed_files} file${review.changed_files === 1 ? "" : "s"} · +${review.lines_added} −${review.lines_removed}`;
  summary.append(title, detail);
  const actions = document.createElement("div"); actions.className = "approval-actions";
  for (const [action, label, className] of [["reject_all", "Reject all", "quiet"], ["keep_all", "Keep all", "primary"]]) {
    const button = document.createElement("button"); button.type = "button"; button.textContent = label; button.className = className;
    button.addEventListener("click", async () => {
      if (action === "reject_all" && !confirm("Reject every unreviewed Agent edit in this session?")) return;
      try { await rpc("thread.edit_review.respond", { ...baseThreadParams(), action, expected_last_sequence: state.sequence }); control.open = false; await refreshAuxiliaryState(); }
      catch (error) { notice(error.message); }
    });
    actions.append(button);
  }
  card.append(summary, actions); panel.append(card);
}

function renderQueue(queue) {
  state.queue = queue;
  const panel = $("queue-review");
  panel.replaceChildren();
  panel.classList.toggle("hidden", !queue?.count);
  if (!queue?.count) return;
  const card = document.createElement("article"); card.className = "approval-card";
  const body = document.createElement("div");
  const title = document.createElement("strong"); title.textContent = `${queue.count} queued message${queue.count === 1 ? "" : "s"}`;
  body.append(title);
  for (const entry of queue.entries || []) { const text = document.createElement("small"); text.textContent = entry.preview || "Attachment"; body.append(text); }
  const clear = document.createElement("button"); clear.type = "button"; clear.className = "quiet"; clear.textContent = "Clear queue";
  clear.disabled = !state.capabilities.includes("thread.queue.clear");
  clear.addEventListener("click", async () => { try { await rpc("thread.queue.clear", baseThreadParams()); await refreshAuxiliaryState(); } catch (error) { notice(error.message); } });
  card.append(body, clear); panel.append(card);
}

async function refreshAuxiliaryState() {
  if (!state.threadId) return;
  const requests = [
    state.capabilities.includes("thread.elicitations") ? rpc("thread.elicitations", baseThreadParams()) : Promise.resolve({ elicitations: [] }),
    state.capabilities.includes("thread.edit_review") ? rpc("thread.edit_review", baseThreadParams()) : Promise.resolve(null),
    state.capabilities.includes("thread.queue") ? rpc("thread.queue", baseThreadParams()) : Promise.resolve(null),
  ];
  const [elicitations, edits, queue] = await Promise.all(requests);
  renderElicitations(elicitations?.elicitations);
  renderEditReview(edits);
  renderQueue(queue);
}

function validSubagents(value) {
  if (!Array.isArray(value)) return [];
  return value.filter((agent) => agent && typeof agent.session_id === "string"
    && typeof agent.status === "string" && Array.isArray(agent.entries_markdown)
    && agent.entries_markdown.every((entry) => typeof entry === "string"));
}

function subagentIsActive(agent) {
  return /Pending|Running|InProgress|In Progress|Waiting|Generating/i.test(agent.status)
    || Number.isInteger(agent.current_turn_id);
}

function renderSubagents(subagents) {
  const next = validSubagents(subagents);
  const signature = JSON.stringify([next, state.stoppingSubagent]);
  if (signature === state.subagentsSignature) return;
  const panel = $("subagents");
  const disclosure = new Map(Array.from(panel.querySelectorAll(".subagent")).map((details) => [
    details.dataset.sessionId,
    { open: details.open, userToggled: details.dataset.userToggled === "true" },
  ]));
  state.subagents = next;
  state.subagentsSignature = signature;
  panel.replaceChildren();
  panel.classList.toggle("hidden", state.subagents.length === 0);
  if (!state.subagents.length) return;
  const head = document.createElement("div");
  head.className = "subagents-head";
  const title = document.createElement("strong");
  title.textContent = "Parallel agents";
  const activeCount = state.subagents.filter(subagentIsActive).length;
  const count = document.createElement("span");
  count.textContent = activeCount ? `${activeCount} active · ${state.subagents.length} total` : `${state.subagents.length} complete`;
  head.append(title, count);
  panel.append(head);
  const grid = document.createElement("div");
  grid.className = "subagent-grid";
  for (const agent of state.subagents) {
    const active = subagentIsActive(agent);
    const details = document.createElement("details");
    details.className = `subagent ${active ? "active" : ""}`;
    details.dataset.sessionId = agent.session_id;
    const previous = disclosure.get(agent.session_id);
    details.open = previous?.userToggled ? previous.open : active;
    details.dataset.userToggled = String(previous?.userToggled === true);
    details.addEventListener("toggle", () => { details.dataset.userToggled = "true"; });
    const summary = document.createElement("summary");
    const indicator = document.createElement("span");
    indicator.className = "subagent-indicator";
    const names = document.createElement("span");
    names.className = "subagent-names";
    const name = document.createElement("strong");
    name.textContent = agent.title || agent.label || "Zed subagent";
    const id = document.createElement("small");
    id.textContent = `Child ${agent.session_id.slice(0, 10)}…`;
    names.append(name, id);
    const status = document.createElement("span");
    status.className = "subagent-status";
    status.textContent = agent.status;
    summary.append(indicator, names, status);
    const body = document.createElement("div");
    body.className = "subagent-body";
    if (agent.entries_markdown.length) {
      for (const [index, markdown] of agent.entries_markdown.entries()) body.append(makeEntry(markdown, index));
    } else {
      const waiting = document.createElement("p");
      waiting.className = "muted";
      waiting.textContent = active ? "Waiting for this agent’s first update…" : "No child transcript is loaded.";
      body.append(waiting);
    }
    if (agent.entries_truncated) {
      const note = document.createElement("p");
      note.className = "subagent-note";
      note.textContent = "Earlier child activity remains available in desktop Zed.";
      body.prepend(note);
    }
    const followUp = document.createElement("button");
    followUp.type = "button";
    followUp.className = "quiet subagent-follow-up";
    followUp.textContent = "Continue this agent";
    followUp.addEventListener("click", (event) => {
      event.preventDefault();
      $("prompt").value = `Use the native spawn_agent tool with session_id "${agent.session_id}" to continue this existing child agent. Return its result in this conversation:\n\nTask: `;
      $("prompt").dispatchEvent(new Event("input", { bubbles: true }));
      $("prompt").focus();
      $("prompt").setSelectionRange($("prompt").value.length, $("prompt").value.length);
    });
    body.prepend(followUp);
    if (active && Number.isInteger(agent.current_turn_id) && state.capabilities.includes("subagent.cancel")) {
      const stop = document.createElement("button");
      stop.type = "button";
      stop.className = "quiet subagent-stop";
      stop.textContent = state.stoppingSubagent === agent.session_id ? "Stopping…" : "Stop agent";
      stop.disabled = state.stoppingSubagent !== null;
      stop.addEventListener("click", (event) => { event.preventDefault(); cancelSubagent(agent); });
      body.prepend(stop);
    }
    details.append(summary, body);
    grid.append(details);
  }
  panel.append(grid);
}

async function cancelSubagent(agent) {
  if (!Number.isInteger(agent.current_turn_id) || state.stoppingSubagent) return;
  state.stoppingSubagent = agent.session_id;
  renderSubagents(state.subagents);
  try {
    const result = await rpc("subagent.cancel", {
      ...baseThreadParams(), subagent_id: agent.session_id, turn_id: agent.current_turn_id,
    });
    if (result.outcome !== "requested" || result.subagent_id !== agent.session_id) {
      throw new Error("Zed did not confirm the child-agent stop request.");
    }
    notice(`Stop requested for ${agent.title || agent.label || "parallel agent"}.`);
  } catch (error) { notice(error.message); }
  finally {
    state.stoppingSubagent = null;
    await refreshSnapshot().catch((error) => notice(error.message));
  }
}

async function loadThreadSettings() {
  const threadId = state.threadId;
  if (!threadId || !state.capabilities.includes("thread.settings")) {
    state.threadSettings = null;
    renderThreadSettings();
    return;
  }
  state.settingsBusy = true;
  renderThreadSettings();
  try {
    const result = await rpc("thread.settings", {
      instance_id: state.instanceId, epoch: state.epoch, thread_id: threadId,
    });
    if (state.threadId !== threadId) return;
    if (result.thread_id !== threadId || !Array.isArray(result.profiles)) {
      throw new Error("Zed returned invalid thread settings.");
    }
    state.threadSettings = result;
  } finally {
    state.settingsBusy = false;
    renderThreadSettings();
  }
}

function renderThreadSettings() {
  const settings = state.threadSettings;
  const selected = state.threads.find((thread) => thread.thread_id === state.threadId);
  const supported = state.capabilities.includes("thread.settings")
    && state.capabilities.includes("thread.settings.update");
  const busy = state.threadStatus && state.threadStatus !== "Idle";
  const agent = normalizeAgent(settings?.agent || selected?.agent);
  const external = agent.kind === "external_acp";
  renderSelectedAgent();
  $("zed-model-label").textContent = external ? "Agent configuration" : "Current model";
  $("zed-profile-field").classList.toggle("hidden", external);
  $("zed-thinking-row").classList.toggle("hidden", external);
  $("save-zed-settings").classList.toggle("hidden", external);
  renderHeaderModel();
  const stateLabel = $("zed-settings-state");
  $("zed-settings-thread").textContent = selected?.title || "Select an exposed session to manage its native Zed options.";
  const model = $("zed-model");
  model.replaceChildren();
  for (const item of settings?.models || []) {
    if (typeof item.id !== "string" || typeof item.provider_id !== "string") continue;
    const option = new Option(`${item.name || item.id} · ${item.provider_id}`, `${item.provider_id}\n${item.id}`);
    option.selected = item.id === settings?.model?.id && item.provider_id === settings?.model?.provider_id;
    model.add(option);
  }
  if (!model.options.length) model.add(new Option(external ? `Managed by ${agent.name}` : state.threadId ? "Model identity unavailable" : "No session selected", ""));
  const usage = settings?.context_usage;
  $("zed-context-usage").textContent = usage
    ? `${Number(usage.used_tokens).toLocaleString()} / ${Number(usage.max_tokens).toLocaleString()} tokens`
    : "Unavailable";
  const profile = $("zed-profile");
  profile.replaceChildren();
  for (const item of settings?.profiles || []) {
    if (typeof item.id !== "string" || typeof item.name !== "string") continue;
    const option = document.createElement("option");
    option.value = item.id;
    option.textContent = item.name;
    option.selected = item.id === settings.profile_id;
    profile.append(option);
  }
  if (!profile.options.length) {
    const option = document.createElement("option");
    option.textContent = state.threadId ? "Unavailable" : "Select a session";
    profile.append(option);
  }
  const thinking = $("zed-thinking");
  thinking.checked = settings?.thinking_enabled === true;
  const thinkingEditable = !!settings?.thinking_supported && !!settings?.thinking_can_disable;
  const editable = supported && !!settings && settings.editable !== false && !external && !busy && !state.settingsBusy;
  model.disabled = !editable || !settings?.models?.length;
  profile.disabled = !editable;
  thinking.disabled = !editable || !thinkingEditable;
  $("save-zed-settings").disabled = !editable || (!profile.options.length && !thinkingEditable);
  stateLabel.className = editable ? "ready" : "";
  if (state.settingsBusy) stateLabel.textContent = "Loading";
  else if (!state.threadId) stateLabel.textContent = "No session";
  else if (external) stateLabel.textContent = agent.name;
  else if (!supported) stateLabel.textContent = "Update required";
  else if (busy) stateLabel.textContent = "Agent running";
  else stateLabel.textContent = "Ready";
  if (!state.threadId) {
    $("zed-settings-help").textContent = "Select an exposed session to edit its native options.";
  } else if (external) {
    $("zed-settings-help").textContent = `${agent.name} owns its model, authentication, and configuration. Change those options in its desktop Zed controls; ZedLink can still stream, send, cancel, run commands, and resolve approvals.`;
  } else if (!supported) {
    $("zed-settings-help").textContent = "Restart the updated patched Zed build to enable native session settings.";
  } else if (busy) {
    $("zed-settings-help").textContent = "Settings are locked while this Agent turn is running.";
  } else if (settings && !thinkingEditable) {
    $("zed-settings-help").textContent = "The Agent profile is editable. This model does not expose an on/off thinking control.";
  } else {
    $("zed-settings-help").textContent = "Changes apply to this native Zed Agent thread. Model credentials remain in Zed.";
  }
}

async function saveThreadSettings(event) {
  event.preventDefault();
  if (!state.threadId || !state.threadSettings || state.settingsBusy
      || !state.capabilities.includes("thread.settings.update")) return;
  const threadId = state.threadId;
  const profileId = $("zed-profile").value;
  const thinkingEnabled = $("zed-thinking").checked;
  const [providerId, modelId] = $("zed-model").value.split("\n", 2);
  state.settingsBusy = true;
  renderThreadSettings();
  try {
    const params = {
      instance_id: state.instanceId, epoch: state.epoch, thread_id: threadId,
      profile_id: profileId,
      ...(providerId && modelId ? { provider_id: providerId, model_id: modelId } : {}),
    };
    if (state.threadSettings.thinking_supported && state.threadSettings.thinking_can_disable) {
      params.thinking_enabled = thinkingEnabled;
    }
    const result = await rpc("thread.settings.update", params);
    if (state.threadId !== threadId || result.thread_id !== threadId) return;
    state.threadSettings = result;
    notice("Native Zed session settings updated.");
    setTimeout(() => {
      if ($("notice").textContent === "Native Zed session settings updated.") notice("");
    }, 4000);
  } catch (error) {
    notice(error.message);
    try { await loadThreadSettings(); } catch { /* Keep the original settings error visible. */ }
  } finally {
    state.settingsBusy = false;
    renderThreadSettings();
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
  const agentName = selectedAgent().name;
  const headings = [
    [/^## User(?: \(checkpoint\))?\n\n/, "user", "You"],
    [/^## Assistant\n\n/, "assistant", agentName],
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
  if (presentation.kind === "user") {
    article.setAttribute("aria-label", "Your message");
    copy.classList.add("message-copy-compact");
    copy.textContent = "⧉";
    heading.append(copy);
  } else heading.append(label, copy);
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
  $("activity-title").textContent = busy ? `${selectedAgent().name} is working` : `Turn activity${updates.length ? ` · ${updates.length}` : ""}`;
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
    empty.textContent = `Waiting for reasoning or tool activity shared by ${selectedAgent().name} through Zed…`;
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

function renderTranscript() {
  const container = $("transcript-entries");
  for (const [offset, markdown] of state.renderedEntries.entries()) {
    const absoluteIndex = state.renderedEntryStart + offset;
    const previous = container.children[offset];
    if (previous?.dataset.entryIndex === String(absoluteIndex)
        && previous._zedlinkMarkdown === markdown) continue;
    const article = makeEntry(markdown, absoluteIndex);
    const rewind = state.rewindPoints.find((item) => item.entry_index === absoluteIndex);
    if (rewind && state.capabilities.includes("thread.rewind") && state.threadStatus === "Idle") {
      const button = document.createElement("button");
      button.type = "button"; button.className = "message-copy"; button.textContent = "Rewind here";
      button.addEventListener("click", () => rewindConversation(rewind));
      article.prepend(button);
    }
    article._zedlinkMarkdown = markdown;
    if (previous) {
      const oldDetails = previous.querySelector("details");
      const newDetails = article.querySelector("details");
      if (oldDetails && newDetails && oldDetails.dataset.userToggled === "true") {
        newDetails.open = oldDetails.open;
        newDetails.dataset.userToggled = "true";
      }
      previous.replaceWith(article);
    } else container.append(article);
  }
  while (container.children.length > state.renderedEntries.length) container.lastElementChild.remove();
  const canLoad = state.renderedEntryStart > 0 && state.capabilities.includes("thread.history");
  $("load-history").classList.toggle("hidden", !canLoad);
  $("load-history").disabled = state.historyLoading;
  $("load-history").textContent = state.historyLoading
    ? "Loading earlier conversation…"
    : `Load earlier conversation · ${state.renderedEntryStart} remaining`;
}

async function loadEarlierConversation() {
  if (!state.threadId || state.renderedEntryStart <= 0 || state.historyLoading
      || !state.capabilities.includes("thread.history")) return;
  const threadId = state.threadId;
  const before = state.renderedEntryStart;
  const scroller = $("messages");
  const priorHeight = scroller.scrollHeight;
  state.historyLoading = true;
  renderTranscript();
  try {
    const result = await rpc("thread.history", { thread_id: threadId, before_entry_index: before });
    if (state.threadId !== threadId || state.renderedEntryStart !== before) return;
    identity(result);
    if (result.thread_id !== threadId || result.entry_end_index !== before
        || !Number.isInteger(result.entry_start_index)
        || !Array.isArray(result.entries_markdown)
        || !result.entries_markdown.every((entry) => typeof entry === "string")) {
      throw new Error("Conversation history changed. Refresh the session and try again.");
    }
    state.renderedEntries = [...result.entries_markdown, ...state.renderedEntries];
    state.renderedEntryStart = result.entry_start_index;
    state.totalEntries = Math.max(state.totalEntries, Number(result.total_entries) || 0);
    renderTranscript();
    scroller.scrollTop += scroller.scrollHeight - priorHeight;
  } catch (error) {
    notice(error.message);
  } finally {
    state.historyLoading = false;
    renderTranscript();
  }
}

async function snapshot() {
  if (!state.threadId) return;
  const threadId = state.threadId;
  const params = { thread_id: threadId };
  if (state.renderedThreadId === threadId && state.renderedEntries.length) params.tail_entry_count = 16;
  const result = await rpc("thread.snapshot", params);
  if (state.threadId !== threadId) return;
  identity(result);
  if (result.thread_id !== state.threadId || !Array.isArray(result.entries_markdown)
      || !result.entries_markdown.every((entry) => typeof entry === "string")) {
    throw new Error("Snapshot belongs to another thread.");
  }
  state.sequence = result.last_sequence;
  state.rewindPoints = Array.isArray(result.rewind_points) ? result.rewind_points : [];
  state.lastSnapshotAt = Date.now();
  const scroller = $("messages");
  const container = $("transcript-entries");
  const follow = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 90;
  const pageStart = Number.isInteger(result.entry_start_index) ? result.entry_start_index : 0;
  const pageEnd = Number.isInteger(result.entry_end_index)
    ? result.entry_end_index : pageStart + result.entries_markdown.length;
  const totalEntries = Number.isInteger(result.total_entries) ? result.total_entries : pageEnd;
  if (pageEnd !== pageStart + result.entries_markdown.length || totalEntries < pageEnd) {
    throw new Error("Invalid transcript page from desktop Zed.");
  }
  if (state.renderedThreadId !== result.thread_id) {
    container.replaceChildren();
    state.renderedEntries = [];
    state.renderedThreadId = result.thread_id;
    state.renderedEntryStart = pageStart;
  }
  const loadedEnd = state.renderedEntryStart + state.renderedEntries.length;
  if (pageStart >= state.renderedEntryStart && pageStart <= loadedEnd) {
    state.renderedEntries = [
      ...state.renderedEntries.slice(0, pageStart - state.renderedEntryStart),
      ...result.entries_markdown,
    ];
  } else {
    state.renderedEntryStart = pageStart;
    state.renderedEntries = [...result.entries_markdown];
  }
  state.totalEntries = totalEntries;
  renderTranscript();
  const busy = result.status !== "Idle";
  state.threadStatus = result.status;
  const summary = state.threads.find((thread) => thread.thread_id === result.thread_id);
  if (summary && result.agent) summary.agent = result.agent;
  renderSelectedAgent();
  state.threadError = validAgentError(result.agent_error);
  state.retryStatus = validRetryStatus(result.retry_status);
  state.imageRecovery = validImageRecovery(result.image_recovery);
  renderAgentHealth();
  for (const details of container.querySelectorAll("details.thinking-block")) details.open = false;
  if (busy) {
    const assistants = container.querySelectorAll(".message.assistant");
    assistants[assistants.length - 1]?.querySelectorAll("details.thinking-block").forEach((details) => { details.open = true; });
  }
  $("thread-title").textContent = result.title || "Untitled Agent thread";
  $("thread-title").title = result.title || "Untitled Agent thread";
  $("thread-meta").textContent = state.renderedEntryStart > 0
    ? `Showing ${state.renderedEntries.length} of ${state.totalEntries} entries · Earlier history available`
    : `${state.totalEntries} conversation entries · Thread ${result.thread_id.slice(0, 12)}…`;
  const failed = !busy && !state.retryStatus && (result.had_error === true || !!state.threadError);
  $("thread-state").textContent = state.retryStatus ? "Retrying" : failed ? "Request failed" : result.status;
  $("thread-state").className = `state-pill ${result.status === "Idle" && !failed ? "online" : ""} ${failed ? "offline" : ""}`;
  // Thinking and tool output are rendered in their exact transcript positions.
  // Keep the former aggregate activity surface hidden to avoid duplicate or reordered content.
  $("activity").classList.add("hidden");
  state.activitySignature = null;
  renderSubagents(result.subagents);
  const childApprovals = state.subagents.flatMap((agent) => Array.isArray(agent.pending_approvals) ? agent.pending_approvals : []);
  renderApprovals([...(Array.isArray(result.pending_approvals) ? result.pending_approvals : []), ...childApprovals]);
  await refreshAuxiliaryState();
  if (document.body.classList.contains("context-open")) renderActivityIndex();
  if (follow) {
    scroller.scrollTop = scroller.scrollHeight;
    $("jump-latest").classList.add("hidden");
  } else if (state.renderedEntries.length) {
    $("jump-latest").classList.remove("hidden");
  }
  state.turnId = Number.isInteger(result.current_turn_id) ? result.current_turn_id : null;
  if (summary && (summary.status !== result.status || summary.current_turn_id !== state.turnId
      || summary.had_error !== result.had_error || summary.agent_error !== result.agent_error
      || summary.retry_status !== result.retry_status)) {
    summary.status = result.status;
    summary.current_turn_id = state.turnId;
    summary.had_error = result.had_error === true;
    summary.agent_error = result.agent_error || null;
    summary.retry_status = result.retry_status || null;
    renderThreads();
  }
  if (state.threadSettings && state.threadSettings.status !== result.status) {
    state.threadSettings.status = result.status;
    renderThreadSettings();
  }
  updateComposerAction();
}

async function rewindConversation(point) {
  if (!confirm(`Rewind this conversation and remove ${point.entries_removed} entries after this message? Agent edits after this point may also be rejected.`)) return;
  try {
    await rpc("thread.rewind", { ...baseThreadParams(), client_user_message_id: point.client_user_message_id, expected_last_sequence: state.sequence });
    state.renderedEntries = []; state.renderedEntryStart = 0; state.totalEntries = 0;
    await refreshSnapshot();
  } catch (error) { notice(error.message); }
}

async function rewindImage() {
  const recovery = state.imageRecovery;
  if (!state.threadId || !recovery || state.rewindingImage || state.threadStatus !== "Idle") return;
  const count = recovery.entriesRemoved;
  const confirmed = confirm(`Rewind this native Zed thread before the first image?\n\nThis removes the image message and ${count - 1} later conversation item${count - 1 === 1 ? "" : "s"} from this thread. Zed may also reject edits made by the Agent after that point. This cannot be undone from ZedLink.`);
  if (!confirmed) return;
  state.rewindingImage = true;
  renderAgentHealth();
  const requestId = crypto.randomUUID();
  try {
    for (let attempt = 0; attempt < 40; attempt += 1) {
      const result = await rpc("thread.rewind_image", {
        ...baseThreadParams(),
        client_user_message_id: recovery.clientUserMessageId,
        expected_last_sequence: state.sequence,
      }, requestId);
      if (result.outcome === "succeeded") break;
      if (result.outcome !== "running") throw new Error("Desktop Zed returned an invalid rewind result.");
      await new Promise((resolve) => setTimeout(resolve, 100));
      if (attempt === 39) throw new Error("Desktop Zed is still rewinding the thread. Refresh to check its state.");
    }
    state.threadError = null;
    state.retryStatus = null;
    state.imageRecovery = null;
    state.errorSignature = null;
    notice("Image turn removed. Describe what you need in text, or switch Zed to a vision-capable model before attaching another image.");
    await refreshSnapshot();
    await loadThreads();
  } catch (error) {
    notice(error.message);
    await refreshSnapshot().catch(() => {});
  } finally {
    state.rewindingImage = false;
    renderAgentHealth();
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
    }
    if (!state.threadId || Date.now() - state.lastThreadsAt > 2000) await loadThreads();
    if (state.selectedTerminalId && $("context-terminal-tab").getAttribute("aria-selected") === "true"
        && !$("context-panel").classList.contains("hidden") && Date.now() - state.lastTerminalSnapshotAt > 1500) {
      await loadTerminalSnapshot();
    }
    if ($("context-debug-tab").getAttribute("aria-selected") === "true"
        && !$("context-panel").classList.contains("hidden") && Date.now() - state.lastDebuggerSnapshotAt > 1500) {
      await loadDebugger();
    }
    if (state.pending) await reconcilePending();
    connection(state.eventSocket?.readyState === WebSocket.OPEN ? "Zed connected · live updates" : "Zed connected · polling", "online");
  } catch (error) {
    if (error.code === "RESYNC_REQUIRED") {
      state.renderedEntries = [];
      state.renderedEntryStart = 0;
      state.totalEntries = 0;
      $("transcript-entries").replaceChildren();
      try { await refreshSnapshot(); return; } catch (snapshotError) { notice(snapshotError.message); }
    } else if (error.code === "THREAD_NOT_EXPOSED" || error.code === "IDENTITY_CHANGED") {
      await connect();
      return;
    } else {
      notice(error.message);
    }
    connection(error.code === "UNAUTHENTICATED" ? pairingStatus()
      : error.code === "INSTANCE_UNAVAILABLE" ? "Zed unavailable"
        : error.message.includes("timed out") ? "Gateway request timed out"
          : navigator.onLine === false ? "Device offline" : "Gateway disconnected", "offline");
  } finally { state.polling = false; }
}

async function sendPrompt(event) {
  event.preventDefault();
  if (!state.threadId || !state.token || state.pending) return;
  const text = $("prompt").value.trim();
  if (!text) return;
  if (text.startsWith("/")) {
    if (state.contextPaths.length || state.uploads.length) {
      notice("Send attachments with a normal prompt, then run the slash command separately.");
      return;
    }
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
    epoch: state.epoch, threadId: state.threadId, text,
    contextPaths: [...state.contextPaths], uploads: [...state.uploads] };
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
      ...(pending.contextPaths?.length ? { context_paths: pending.contextPaths } : {}),
      ...(pending.uploads?.length ? { uploads: pending.uploads } : {}),
    }, pending.id);
    $("prompt").value = "";
    safeStore.remove(promptDraftKey());
    $("prompt").style.height = "auto";
    state.contextPaths = [];
    state.uploads = [];
    renderAttachmentStrip();
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

async function cancelCurrentTurn() {
  const { instanceId, epoch, threadId, turnId } = state;
  if (!canStopTurn()) return;
  state.stoppingTurn = true;
  updateComposerAction();
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
    state.stoppingTurn = false;
    updateComposerAction();
  }
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
$("target-select").addEventListener("change", () => {
  const targetId = $("target-select").value;
  if (!targetId || targetId === state.targetId) return;
  resetTargetSession();
  state.targetId = targetId;
  safeStore.write(targetKey(), targetId);
  renderTargets();
  connect();
});
$("empty-refresh").addEventListener("click", () => connect());
$("empty-create").addEventListener("click", () => {
  if ($("new-session").disabled) return;
  if (matchMedia("(max-width: 760px)").matches) showMobileView("sessions");
  $("new-session-form").classList.remove("hidden");
  loadCreateOptions().catch((error) => notice(error.message));
  $("new-session-title").focus();
});
$("new-session").addEventListener("click", () => {
  const form = $("new-session-form");
  form.classList.toggle("hidden");
  if (!form.classList.contains("hidden")) {
    loadCreateOptions().catch((error) => notice(error.message));
    $("new-session-title").focus();
  }
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
$("load-history").addEventListener("click", loadEarlierConversation);
$("send").addEventListener("click", () => {
  if (canStopTurn()) cancelCurrentTurn();
  else $("composer-form").requestSubmit();
});
$("show-sessions").addEventListener("click", () => {
  if (matchMedia("(max-width: 760px)").matches) {
    document.body.classList.remove("mobile-connections", "mobile-settings");
    if (state.threadId) document.body.classList.toggle("mobile-sessions");
    else document.body.classList.add("mobile-sessions");
  } else {
    document.body.classList.toggle("sidebar-collapsed");
    safeStore.write(sidebarKey(), String(document.body.classList.contains("sidebar-collapsed")));
  }
  updateSidebarToggle();
});
$("prompt").addEventListener("input", () => {
  if (state.threadId) safeStore.write(promptDraftKey(), $("prompt").value);
  const prompt = $("prompt");
  prompt.style.height = "auto";
  prompt.style.height = `${Math.min(prompt.scrollHeight, 132)}px`;
  $("action-menu").classList.add("hidden");
  $("show-actions").setAttribute("aria-expanded", "false");
  renderCommands();
});
$("show-actions").addEventListener("click", () => {
  if (!state.threadId) return;
  const menu = $("action-menu");
  menu.classList.toggle("hidden");
  $("show-actions").setAttribute("aria-expanded", String(!menu.classList.contains("hidden")));
});
$("action-commands").addEventListener("click", () => {
  if (!state.threadId) return;
  $("action-menu").classList.add("hidden");
  $("show-actions").setAttribute("aria-expanded", "false");
  $("prompt").value = "/";
  $("prompt").focus();
  renderCommands();
});
$("action-delegate").addEventListener("click", () => {
  if (!state.threadId) return;
  $("action-menu").classList.add("hidden");
  $("show-actions").setAttribute("aria-expanded", "false");
  $("prompt").value = DELEGATE_TASK_TEMPLATE;
  $("prompt").dispatchEvent(new Event("input", { bubbles: true }));
  $("prompt").focus();
  $("prompt").setSelectionRange($("prompt").value.length, $("prompt").value.length);
});
$("action-file").addEventListener("click", () => {
  $("action-menu").classList.add("hidden");
  $("show-actions").setAttribute("aria-expanded", "false");
  openContextPanel("files");
});
$("action-upload").addEventListener("click", () => {
  $("action-menu").classList.add("hidden");
  $("show-actions").setAttribute("aria-expanded", "false");
  if (!state.capabilities.includes("thread.attachments")) {
    notice("Restart the updated patched Zed build to upload prompt attachments.");
    return;
  }
  $("upload-file").click();
});
$("upload-file").addEventListener("change", (event) => addUploads(event.target.files).catch((error) => notice(error.message)));
$("show-context").addEventListener("click", () => document.body.classList.contains("context-open") ? closeContextPanel() : openContextPanel("files"));
$("back-sessions").addEventListener("click", () => showMobileView("sessions"));
$("close-context").addEventListener("click", closeContextPanel);
$("context-files-tab").addEventListener("click", () => switchContextTab("files"));
$("context-changes-tab").addEventListener("click", () => switchContextTab("changes"));
$("context-terminal-tab").addEventListener("click", () => switchContextTab("terminal"));
$("context-debug-tab").addEventListener("click", () => switchContextTab("debug"));
$("context-activity-tab").addEventListener("click", () => switchContextTab("activity"));
$("terminal-select").addEventListener("change", async (event) => {
  terminalInputGeneration += 1;
  setTerminalInputMode(false);
  state.selectedTerminalId = event.target.value || null;
  if (state.selectedTerminalId) safeStore.write(terminalRecoveryKey(), state.selectedTerminalId);
  state.terminalSnapshot = null;
  renderTerminals();
  if (state.selectedTerminalId) await loadTerminalSnapshot().catch((error) => notice(error.message));
});
$("refresh-terminal").addEventListener("click", () => loadTerminals().catch((error) => notice(error.message)));
$("terminal-stop").addEventListener("click", stopSelectedTask);
$("copy-terminal").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText($("terminal-output").textContent || "");
    notice("Terminal output copied.");
  } catch { notice("Terminal output could not be copied."); }
});
$("terminal-input-form").addEventListener("submit", sendTerminalInput);
$("terminal-live-input").addEventListener("click", () => {
  if (!terminalLiveInput && $("terminal-input").value) queueTerminalInput($("terminal-input").value);
  setTerminalInputMode(!terminalLiveInput); $("terminal-input").focus();
});
$("terminal-hide-keyboard").addEventListener("click", (event) => { $("terminal-input").blur(); event.currentTarget.blur(); syncVisualViewport(); });
$("terminal-keys").addEventListener("pointerdown", (event) => { if (event.target.closest("button")) event.preventDefault(); });
$("terminal-keys").addEventListener("click", async (event) => {
  const key = event.target.closest("[data-terminal-key]")?.dataset.terminalKey;
  if (!key) return;
  // Flush a partial command before completion or cursor movement.
  const input = $("terminal-input");
  if (!terminalLiveInput && input.value) { queueTerminalInput(input.value); input.value = ""; setTerminalInputMode(true); }
  await queueTerminalInput(terminalKeys[key]);
  await loadTerminalSnapshot();
});
$("terminal-input").addEventListener("input", terminalTypedInput);
$("terminal-input").addEventListener("compositionstart", () => $("terminal-live-hint").classList.add("hidden"));
$("terminal-input").addEventListener("compositionend", (event) => { terminalTypedInput(event); $("terminal-live-hint").classList.toggle("hidden", !terminalLiveInput); });
$("terminal-input").addEventListener("beforeinput", (event) => {
  if (terminalLiveInput && event.inputType === "deleteContentBackward") { event.preventDefault(); queueTerminalInput("\x7f"); }
});
$("terminal-input").addEventListener("keydown", (event) => {
  if (!terminalLiveInput || event.isComposing) return;
  const key = { Escape: "escape", Tab: "tab", ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right", Backspace: "backspace" }[event.key];
  let bytes = key ? terminalKeys[key] : null;
  if (event.ctrlKey && !event.altKey && event.key.length === 1 && /^[a-z@\[\]\\^_]$/i.test(event.key)) bytes = String.fromCharCode(event.key.toUpperCase().charCodeAt(0) & 31);
  if (bytes !== null) { event.preventDefault(); queueTerminalInput(bytes); }
});
$("task-run-form").addEventListener("submit", runConfiguredTask);
$("debugger-launch-form").addEventListener("submit", launchConfiguredDebugger);
$("file-search").addEventListener("input", renderProjectFiles);
$("project-search-form").addEventListener("submit", searchProject);
$("project-search").addEventListener("input", () => {
  if (!$("project-search").value) {
    state.projectSearchMatches = [];
    state.projectSearchTruncated = false;
    $("project-search-results").replaceChildren();
    $("project-search-results").classList.add("hidden");
    $("project-search-status").classList.add("hidden");
  }
});
$("attach-preview").addEventListener("click", attachPreview);
$("wrap-file").addEventListener("click", () => {
  const pre = $("file-preview").querySelector(".review-code");
  setWrap(pre, $("wrap-file"), !pre.classList.contains("wrap"));
});
$("expand-file").addEventListener("click", () => {
  if (state.previewPath) openCodeReview(state.previewPath, state.previewContent, languageFromPath(state.previewPath), state.previewFocusLine);
});
$("load-diff").addEventListener("click", loadGitDiff);
$("diff-search").addEventListener("input", () => {
  const hits = renderReviewCode($("git-diff").querySelector("code"), state.diffContent, "diff", null, $("diff-search").value);
  $("diff-search-count").textContent = $("diff-search").value ? `${hits} match${hits === 1 ? "" : "es"}` : "";
});
$("wrap-diff").addEventListener("click", () => setWrap($("git-diff"), $("wrap-diff"), !$("git-diff").classList.contains("wrap")));
$("expand-diff").addEventListener("click", () => {
  if (state.diffContent) openCodeReview("Working tree diff", state.diffContent, "diff");
});
$("close-code-review").addEventListener("click", closeCodeReview);
$("code-review-wrap").addEventListener("click", () => {
  const pre = $("code-review").querySelector(".review-code");
  setWrap(pre, $("code-review-wrap"), !pre.classList.contains("wrap"));
});
$("code-review-query").addEventListener("input", () => {
  const query = $("code-review-query").value;
  const hits = renderReviewCode($("code-review-content"), state.reviewSource, state.reviewLanguage, state.previewFocusLine, query);
  $("code-review-count").textContent = query ? `${hits} match${hits === 1 ? "" : "es"}` : "";
});
$("prompt").addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    $("command-menu").classList.add("hidden");
    $("action-menu").classList.add("hidden");
    $("show-actions").setAttribute("aria-expanded", "false");
  }
  if (event.key === "ArrowDown" && !$("command-menu").classList.contains("hidden")) {
    const first = $("command-menu").querySelector(".command-option");
    if (first) { event.preventDefault(); first.focus(); }
  }
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing && event.keyCode !== 229) {
    event.preventDefault();
    $("composer-form").requestSubmit();
  }
});
async function signOut() {
  try { await disableNotifications(false); } catch { /* Revoking the paired device remains authoritative. */ }
  closeEventStream();
  safeStore.remove(tokenKey());
  safeStore.remove(pendingKey());
  safeStore.remove(selectedThreadKey());
  state.token = null;
  state.pending = null;
  state.threadId = null;
  state.threadStatus = null;
  state.threadError = null;
  state.retryStatus = null;
  state.imageRecovery = null;
  state.rewindingImage = false;
  state.desktopReachable = null;
  state.threadSettings = null;
  state.contextPaths = [];
  state.uploads = [];
  state.projectFolderEntries = null;
  state.directoryRequest += 1;
  state.projectDirectory = "";
  state.previewRequest += 1;
  $("context-files").classList.remove("file-reading");
  state.projectFiles = [];
  state.projectSearchMatches = [];
  state.projectSearchTruncated = false;
  state.changes = null;
  state.previewPath = null;
  state.previewContent = "";
  state.diffContent = "";
  renderAttachmentStrip();
  closeCodeReview();
  closeContextPanel();
  requireManualGatewayVerification();
  document.body.classList.remove("thread-open", "mobile-sessions", "mobile-connections", "mobile-settings", "no-session");
  document.body.classList.add("pairing");
  $("pair-panel").classList.remove("hidden");
  $("sessions-panel").classList.add("hidden");
  $("settings-panel").classList.add("hidden");
  $("transcript-entries").replaceChildren();
  $("activity").classList.add("hidden");
  renderAgentHealth();
  $("prompt").disabled = true;
  delivery("");
  renderThreadSettings();
  connection("Signed out");
  notice("Signed out on this device. Revoke its paired-device record from desktop Zed if this device should not connect again.");
}
$("sign-out").addEventListener("click", signOut);
$("enable-notifications").addEventListener("click", enableNotifications);
$("test-notifications").addEventListener("click", testNotifications);
$("native-settings-form").addEventListener("submit", saveThreadSettings);
$("rename-session").addEventListener("click", () => renameSelectedSession().catch((error) => notice(error.message)));
$("unexpose-session").addEventListener("click", () => unexposeSelectedSession().catch((error) => notice(error.message)));
$("open-settings").addEventListener("click", () => {
  if (matchMedia("(max-width: 760px)").matches) showMobileView("settings");
  else {
    $("sessions-panel").classList.add("hidden");
    $("settings-panel").classList.remove("hidden");
  }
  loadThreadSettings().catch((error) => notice(error.message));
});
$("settings-back").addEventListener("click", () => {
  if (matchMedia("(max-width: 760px)").matches) showMobileView("sessions");
  else {
    $("settings-panel").classList.add("hidden");
    $("sessions-panel").classList.remove("hidden");
  }
});
$("composer-form").addEventListener("submit", sendPrompt);
$("thread-state").addEventListener("click", () => {
  if (state.threadStatus && state.threadStatus !== "Idle") focusLiveActivity();
});
$("rewind-image").addEventListener("click", rewindImage);
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
  if (document.visibilityState === "hidden") closeEventStream("paused");
  else resumeLiveUpdates();
});
window.addEventListener("pageshow", resumeLiveUpdates);
window.addEventListener("focus", resumeLiveUpdates);
window.addEventListener("online", () => {
  renderConnectionHealth();
  resumeLiveUpdates();
});
window.addEventListener("offline", () => {
  state.gatewayReachable = false;
  if (state.threadId) state.streamState = "reconnecting";
  renderConnectionHealth();
  updateComposerAction();
});

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
    loadThreadSettings().catch((error) => notice(error.message));
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
if ("clearAppBadge" in navigator) navigator.clearAppBadge().catch(() => {});
$("ui-build").textContent = UI_BUILD;
$("device-name").value = browserDeviceName();
showInstallHelp();
window.addEventListener("resize", () => {
  updateSidebarToggle();
  renderConnectionHealth();
});
function appViewportHeight(viewport, standalone, keyboardOpen, fullHeight) {
  const visibleBottom = viewport ? viewport.height + viewport.offsetTop : window.innerHeight;
  if (standalone && !keyboardOpen) return fullHeight;
  return Math.min(fullHeight, visibleBottom);
}
function syncVisualViewport(viewport = window.visualViewport) {
  // A Home Screen app owns the full screen. Its safe-area padding keeps controls
  // clear of the home indicator, so do not shorten the app to innerHeight.
  const standalone = matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
  const fullHeight = Math.max(window.innerHeight, document.documentElement.clientHeight, window.screen?.height || 0);
  const active = document.activeElement;
  const acceptsKeyboard = active?.matches?.("input:not([type=button]):not([type=checkbox]):not([type=radio]), textarea, [contenteditable=true]") === true;
  const keyboardOpen = acceptsKeyboard && viewport && viewport.height < fullHeight - 120;
  const height = appViewportHeight(viewport, standalone, keyboardOpen, fullHeight);
  document.documentElement.style.setProperty("--app-height", `${Math.round(height)}px`);
}
syncVisualViewport();
window.visualViewport?.addEventListener("resize", () => syncVisualViewport());
window.visualViewport?.addEventListener("scroll", () => syncVisualViewport());
window.addEventListener("orientationchange", () => syncVisualViewport());
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !$("code-review").classList.contains("hidden")) closeCodeReview();
});
updateSidebarToggle();
loadGateway();

$("file-preview-back").addEventListener("click", () => {
  state.previewRequest += 1;
  $("context-files").classList.remove("file-reading");
  $("file-preview").classList.add("hidden");
  $("file-search").focus();
});

function terminalRecoveryKey() { return `zedlink.terminal.${state.gatewayId}.${state.targetId}.${state.instanceId}.${state.epoch}`; }
function promptDraftKey() { return `zedlink.draft.${state.gatewayId}.${state.targetId}.${state.threadId}`; }
let terminalWrap = safeStore.read("zedlink.terminalWrap") === null ? matchMedia("(max-width: 760px)").matches : safeStore.read("zedlink.terminalWrap") === "true";
function renderTerminalWrap() {
  $("terminal-output").classList.toggle("wrap-output", terminalWrap);
  $("terminal-wrap").setAttribute("aria-pressed", String(terminalWrap));
  $("terminal-wrap").textContent = terminalWrap ? "Keep original columns" : "Wrap output";
}
renderTerminalWrap();
$("terminal-wrap").addEventListener("click", () => {
  terminalWrap = !terminalWrap;
  safeStore.write("zedlink.terminalWrap", String(terminalWrap));
  renderTerminalWrap();
  document.querySelector(".terminal-tools").open = false;
});
$("terminal-recover").addEventListener("click", async () => {
  document.querySelector(".terminal-tools").open = false;
  const scope = [state.gatewayId, state.targetId, state.threadId];
  await connect();
  if (scope.every((value, index) => value === [state.gatewayId, state.targetId, state.threadId][index])) {
    openContextPanel("terminal");
    notice("Session refreshed. No terminal commands were resent.");
  }
});
let clipboardScope = null;
$("terminal-clipboard").addEventListener("click", () => {
  document.querySelector(".terminal-tools").open = false;
  clipboardScope = JSON.stringify(baseThreadParams());
  $("clipboard-text").value = "";
  $("clipboard-status").textContent = state.capabilities.includes("clipboard.read") ? "" : "Enable Remote Clipboard in desktop ZedLink settings for desktop transfers.";
  $("clipboard-dialog").showModal();
});
function closeClipboard() { $("clipboard-dialog").close(); $("clipboard-text").value = ""; clipboardScope = null; }
$("clipboard-close").addEventListener("click", closeClipboard);
$("clipboard-dialog").addEventListener("cancel", closeClipboard);
async function clipboardAction(action) {
  if (action === "read" || action === "write") await refreshCapabilities();
  if (clipboardScope !== JSON.stringify(baseThreadParams())) throw new Error("Session changed. Close and reopen the clipboard.");
  const input = $("clipboard-text");
  if (action === "read") {
    if (!state.capabilities.includes("clipboard.read")) throw new Error("Enable Remote Clipboard in desktop ZedLink settings.");
    const result = await rpc("clipboard.read", baseThreadParams());
    if (clipboardScope !== JSON.stringify(baseThreadParams())) return;
    if (typeof result.text !== "string" || new TextEncoder().encode(result.text).length > 65536) throw new Error("Invalid clipboard response.");
    input.value = result.text;
  } else if (action === "write") {
    if (!state.capabilities.includes("clipboard.write")) throw new Error("Enable Remote Clipboard in desktop ZedLink settings.");
    await rpc("clipboard.write", { ...baseThreadParams(), text: input.value }, crypto.randomUUID());
  } else if (action === "phone-paste") {
    const text = await navigator.clipboard.readText();
    if (clipboardScope !== JSON.stringify(baseThreadParams())) return;
    if (new TextEncoder().encode(text).length > 65536) throw new Error("Clipboard exceeds 64 KiB.");
    input.value = text;
  } else if (action === "phone-copy") {
    await navigator.clipboard.writeText(input.value);
  } else if (action === "prompt") {
    if (!state.threadId || input.value.length > 3000) throw new Error("Select a session and use up to 3000 characters for the prompt.");
    $("prompt").value = input.value;
    $("prompt").dispatchEvent(new Event("input", { bubbles: true }));
    closeClipboard();
    $("prompt").focus();
    return;
  } else {
    if (!state.capabilities.includes("terminal.input")) throw new Error("Terminal input is disabled.");
    if (new TextEncoder().encode(input.value).length > 16384 || /[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/.test(input.value)) throw new Error("Paste plain text up to 16 KiB without terminal control characters.");
    setTerminalInputMode(false);
    $("terminal-input").value = input.value;
    $("terminal-input").dispatchEvent(new Event("input", { bubbles: true }));
    closeClipboard();
    $("terminal-input").focus();
    return;
  }
  $("clipboard-status").textContent = action === "write" ? "Desktop clipboard updated." : "Ready. Review the text before transferring.";
}
for (const action of ["read", "write", "phone-paste", "phone-copy", "terminal", "prompt"]) {
  $(`clipboard-${action}`).addEventListener("click", () => clipboardAction(action).catch((error) => $("clipboard-status").textContent = error.message));
}
let speech = null;
function dictationStatus(message) {
  $("dictation-status").textContent = message;
  $("dictation-status").classList.toggle("hidden", !message);
  notice(message);
}
function renderDictationState(listening) {
  $("dictate-prompt").setAttribute("aria-pressed", String(listening));
  $("dictate-prompt").setAttribute("aria-label", listening ? "Stop dictation" : "Dictate message");
  $("dictate-prompt").title = listening ? "Stop dictation" : "Dictate message";
  $("terminal-dictate").textContent = listening ? "Stop dictation" : "Dictate input";
  document.querySelector(".terminal-tools").classList.toggle("listening", listening);
}
// Cancellation is reserved for leaving a session. User Stop must allow final results.
function stopDictation() {
  if (speech) { const active = speech; speech = null; active.abort(); }
  renderDictationState(false);
  $("dictation-status").classList.add("hidden");
}
function dictateInto(id) {
  if (speech) {
    try { speech.stop(); dictationStatus("Finishing dictation…"); }
    catch (error) { stopDictation(); dictationStatus(error.message); }
    return;
  }
  const input = $(id);
  if (input.disabled || (id === "terminal-input" && !state.capabilities.includes("terminal.input"))) return;
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition) {
    input.focus();
    dictationStatus("Use the microphone on your phone keyboard. This browser does not support speech recognition.");
    return;
  }
  if (safeStore.read("zedlink.voiceConsent") !== "true") {
    if (!confirm("Your browser’s speech service may process audio online. Start dictation? Text stays in the draft until you send it.")) return;
    safeStore.write("zedlink.voiceConsent", "true");
  }
  if (id === "terminal-input" && terminalLiveInput) setTerminalInputMode(false);
  const scope = JSON.stringify(baseThreadParams());
  const initial = input.value;
  let lastApplied = initial;
  let receivedText = false;
  let failed = false;
  const recognizer = new Recognition();
  speech = recognizer;
  recognizer.lang = navigator.language || "en-US";
  recognizer.interimResults = true;
  recognizer.continuous = false;
  renderDictationState(true);
  recognizer.onresult = (event) => {
    if (speech !== recognizer) return;
    if (scope !== JSON.stringify(baseThreadParams()) || input.value !== lastApplied) {
      stopDictation();
      dictationStatus("Dictation stopped because the draft or session changed. Your edits were kept.");
      return;
    }
    // Safari result lists are array-like; do not assume they support iteration.
    const parts = [];
    let interim = false;
    for (let i = 0; i < event.results.length; i++) {
      const result = event.results[i];
      if (result[0]?.transcript) parts.push(result[0].transcript);
      if (!result.isFinal) interim = true;
    }
    const text = parts.join(" ").trim();
    if (!text) return;
    receivedText = true;
    lastApplied = `${initial}${initial ? " " : ""}${text}`.slice(0, input.maxLength > 0 ? input.maxLength : 16384);
    input.value = lastApplied;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    dictationStatus(interim ? "Listening… Text is appearing in your draft." : "Text added. Review your draft before sending.");
  };
  recognizer.onerror = (event) => {
    if (speech !== recognizer) return;
    failed = true;
    const reasons = {
      "not-allowed": "Microphone or speech permission was denied.",
      "service-not-allowed": "Your browser’s speech service is unavailable.",
      "audio-capture": "The microphone could not be accessed.",
      "network": "Your browser’s speech service could not connect.",
      "no-speech": "No speech was detected.",
      "language-not-supported": "Your browser cannot transcribe this language."
    };
    dictationStatus(`${reasons[event.error] || "Speech recognition stopped."} Use your phone keyboard’s microphone instead. Any draft text was kept.`);
  };
  recognizer.onend = () => {
    if (speech !== recognizer) return;
    speech = null;
    renderDictationState(false);
    if (!failed) dictationStatus(receivedText ? "Dictation added to the draft. Review it before sending." : "No text returned. Try again or use your phone keyboard’s microphone.");
  };
  recognizer.onstart = () => { if (speech === recognizer) dictationStatus("Listening… Speak, then tap the microphone to finish."); };
  try { dictationStatus("Starting microphone…"); recognizer.start(); }
  catch (error) { stopDictation(); dictationStatus(error.message); }
}
$("dictate-prompt").addEventListener("click", () => dictateInto("prompt"));
$("terminal-dictate").addEventListener("click", () => { document.querySelector(".terminal-tools").open = false; dictateInto("terminal-input"); });
document.addEventListener("visibilitychange", () => { if (document.hidden) stopDictation(); });

$("terminal-input").addEventListener("input", () => {
  const input = $("terminal-input");
  if (!terminalLiveInput && input.dataset.draftKey) safeStore.write(input.dataset.draftKey, input.value);
});

$("action-recover").addEventListener("click", async () => { $("action-menu").classList.add("hidden"); await connect(); notice("Session refreshed. No commands or prompts were resent."); });
$("action-clipboard").addEventListener("click", () => { $("action-menu").classList.add("hidden"); $("terminal-clipboard").click(); });
