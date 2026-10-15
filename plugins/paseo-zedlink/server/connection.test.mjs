import test from "node:test";
import assert from "node:assert/strict";
import { createConnection, modelId, threadId } from "./connection.mjs";

function fixture() {
  const calls = [];
  const state = { entries: ["## User\n\nDesktop prompt\n\n", "## Assistant\n\nDesktop answer\n\n"], sent: 0 };
  const gateway = {
    targetId: "primary",
    async identity() { return "gateway-1"; },
    async list() { return { instance_id: "instance-1", epoch: "epoch-1", threads: [
      { thread_id: "native-1", title: "Desktop thread", agent: { name: "Zed Agent", kind: "zed" } },
      { thread_id: "acp-1", title: "External agent", agent: { name: "ACP", kind: "external_acp" } },
    ] }; },
    async snapshot(thread, instance, epoch) {
      calls.push(["snapshot", thread, instance, epoch]);
      return { thread_id: thread, instance_id: instance, epoch, status: "Idle", entries_markdown: [...state.entries],
        entry_start_index: 0, entry_end_index: state.entries.length, pending_approvals: [] };
    },
    async send(thread, instance, epoch, text, requestId) {
      calls.push(["send", thread, instance, epoch, text, requestId]);
      state.sent++;
      state.entries.push(`## User\n\n${text}\n\n`, "## Assistant\n\nReply\n\n");
      return { outcome: "unknown" };
    },
    async status(instance, epoch, requestId) {
      assert.equal(instance, "instance-1");
      assert.equal(epoch, "epoch-1");
      calls.push(["status", requestId]);
      return { known: true };
    },
  };
  return { gateway, state, calls };
}

test("selected Paseo model maps to exactly one native thread", () => {
  assert.equal(threadId(modelId("native-1")), "native-1");
  assert.throws(() => threadId("thread-bad="));
});

test("native event cursor refreshes changed state without repeating unchanged snapshots", async (t) => {
  const { gateway, state } = fixture();
  let sequence = 0;
  let snapshots = 0;
  const originalSnapshot = gateway.snapshot;
  gateway.snapshot = async (...args) => {
    snapshots++;
    return { ...await originalSnapshot(...args), last_sequence: sequence };
  };
  gateway.events = async (thread, instance, epoch, afterSequence) => ({
    thread_id: thread, instance_id: instance, epoch, last_sequence: sequence,
    events: sequence > afterSequence ? [{ sequence }] : [],
  });
  const connection = createConnection(["prompt.message"], gateway);
  t.after(() => connection.close());
  const events = [];
  connection.onEvent((event) => events.push(event));
  await connection.send({ type: "session.open", requestId: "open", sessionId: "paseo",
    config: { model: modelId("native-1"), cwd: "/disposable" }, history: "replay" });
  await new Promise((resolve) => setTimeout(resolve, 1550));
  assert.equal(snapshots, 1);
  state.entries.push("## Assistant\n\nDesktop update\n\n");
  sequence = 1;
  await new Promise((resolve) => setTimeout(resolve, 1550));
  assert.equal(snapshots, 2);
  assert.equal(events.filter((event) => event.type === "timeline.item" && event.item.text === "Desktop update").length, 1);
});

test("a late native receipt attaches the client ID to an unchanged user row", async (t) => {
  const { gateway, state } = fixture();
  const originalSnapshot = gateway.snapshot;
  let requestId = null;
  let receiptReady = false;
  let status = "Idle";
  gateway.snapshot = async (...args) => ({ ...await originalSnapshot(...args), status,
    current_turn_id: status === "Generating" ? 7 : null,
    active_request_id: status === "Generating" ? requestId : null,
    active_request_entry_index: receiptReady ? 2 : null });
  gateway.send = async (...args) => {
    requestId = args[4];
    state.entries.push(`## User\n\n${args[3]}\n\n`);
    status = "Generating";
    return { outcome: "queued", native_request_id: args[4] };
  };
  const connection = createConnection(["prompt.message"], gateway);
  t.after(() => connection.close());
  const events = [];
  connection.onEvent((event) => events.push(event));
  await connection.send({ type: "session.open", requestId: "open", sessionId: "paseo",
    config: { model: modelId("native-1"), cwd: "/disposable" }, history: "skip" });
  await connection.send({ type: "session.prompt", sessionId: "paseo", prompt: {
    clientMessageId: "mobile-1", input: { type: "message", content: [{ type: "text", text: "Phone prompt" }] }
  } });
  await new Promise((resolve) => setTimeout(resolve, 30));
  assert.equal(events.some((event) => event.type === "timeline.item" && event.item.clientMessageId === "mobile-1"), false);
  assert.equal(events.filter((event) => event.type === "timeline.item" && event.item.text === "Phone prompt").length, 0);
  receiptReady = true;
  await new Promise((resolve) => setTimeout(resolve, 400));
  assert.equal(events.some((event) => event.type === "timeline.item" && event.item.clientMessageId === "mobile-1"), true);
  assert.equal(events.filter((event) => event.type === "timeline.item" && event.item.text === "Phone prompt").length, 1);
  state.entries.push("## Assistant\n\nReply\n\n");
  status = "Idle";
  await new Promise((resolve) => setTimeout(resolve, 400));
  assert.equal(events.some((event) => event.type === "session.turn" && event.state === "completed"), true);
});

test("catalog, attach, prompt, and close use the exposed native thread", async (t) => {
  const { gateway, state, calls } = fixture();
  const connection = createConnection(["prompt.message", "session.persistence"], gateway);
  t.after(() => connection.close());
  assert.equal(connection.version, 1);
  assert.deepEqual(connection.capabilities, ["prompt.message", "session.persistence"]);
  const events = [];
  connection.onEvent((event) => events.push(event));
  await connection.send({ type: "catalog", requestId: "catalog-1" });
  assert.equal(events.find((event) => event.type === "catalog").catalog.models[0].id, modelId("native-1"));
  assert.equal(events.find((event) => event.type === "catalog").catalog.models.length, 1);
  await connection.send({ type: "session.open", requestId: "open-1", sessionId: "paseo-1",
    config: { model: modelId("native-1"), cwd: "/disposable" }, history: "replay" });
  assert.equal(events.filter((event) => event.type === "timeline.item").length, 2);
  assert.equal(events.find((event) => event.type === "session.opened").persistence.data.threadId, "native-1");
  await connection.send({ type: "session.prompt", sessionId: "paseo-1", prompt: {
    clientMessageId: "mobile-1", delivery: "auto", input: { type: "message", content: [{ type: "text", text: "Phone prompt" }] }
  } });
  assert.equal(state.sent, 1);
  assert.ok(calls.filter((call) => call[0] === "status").length >= 1);
  assert.equal(events.find((event) => event.type === "session.prompt_result").result.type, "turn");
  await connection.send({ type: "session.close", requestId: "close-1", sessionId: "paseo-1" });
  assert.equal(state.sent, 1);
  assert.equal(events.find((event) => event.type === "session.closed")?.sessionId, "paseo-1");
  assert.equal(events.find((event) => event.type === "request.completed")?.requestId, "close-1");
  await connection.close();
});

test("saved session cannot attach to another gateway", async () => {
  const { gateway } = fixture();
  const connection = createConnection(["prompt.message"], gateway);
  await assert.rejects(connection.send({ type: "session.open", requestId: "open", sessionId: "paseo",
    config: { model: modelId("native-1"), cwd: "/disposable" },
    persistence: { version: 1, data: { gatewayId: "other", targetId: "primary", threadId: "native-1" } }
  }), /another ZedLink gateway/);
  await connection.close();
});

test("unknown delivery is not resent", async () => {
  const { gateway, state } = fixture();
  gateway.send = async () => { state.sent++; throw new Error("socket closed after submit"); };
  gateway.status = async () => ({ known: false });
  const connection = createConnection(["prompt.message"], gateway);
  const events = [];
  connection.onEvent((event) => events.push(event));
  await connection.send({ type: "session.open", requestId: "open", sessionId: "paseo",
    config: { model: modelId("native-1"), cwd: "/disposable" }, history: "skip" });
  await connection.send({ type: "session.prompt", sessionId: "paseo", prompt: {
    clientMessageId: "mobile-1", delivery: "auto", input: { type: "message", content: [{ type: "text", text: "Phone prompt" }] }
  } });
  assert.equal(state.sent, 1);
  assert.equal(events.filter((event) => event.type === "session.prompt_result").length, 0);
  assert.equal(events.find((event) => event.type === "session.notice" && event.notice.id === "zedlink-delivery-unknown")?.notice.title,
    "Message delivery unknown");
  await connection.send({ type: "session.prompt", sessionId: "paseo", prompt: {
    clientMessageId: "mobile-2", delivery: "auto", input: { type: "message", content: [{ type: "text", text: "Another prompt" }] }
  } });
  assert.equal(state.sent, 1);
  assert.equal(events.find((event) => event.type === "session.prompt_result")?.result.type, "failed");
  await connection.close();
});

test("history pages replay in native order and a fast native reply completes one turn", async (t) => {
  const { gateway, state } = fixture();
  gateway.snapshot = async (thread, instance, epoch) => ({ thread_id: thread, instance_id: instance, epoch,
    status: "Idle", entries_markdown: state.entries.slice(-1), entry_start_index: state.entries.length - 1,
    entry_end_index: state.entries.length, had_error: false, pending_approvals: [] });
  gateway.history = async (thread, instance, epoch, before) => ({ thread_id: thread, instance_id: instance, epoch,
    entries_markdown: state.entries.slice(0, before), entry_start_index: 0, entry_end_index: before });
  const connection = createConnection(["prompt.message"], gateway);
  t.after(() => connection.close());
  const events = [];
  connection.onEvent((event) => events.push(event));
  await connection.send({ type: "session.open", requestId: "open", sessionId: "paseo",
    config: { model: modelId("native-1"), cwd: "/disposable" }, history: "replay" });
  assert.deepEqual(events.filter((event) => event.type === "timeline.item").map((event) => event.item.type),
    ["user_message", "assistant_message"]);
  await connection.send({ type: "session.prompt", sessionId: "paseo", prompt: {
    clientMessageId: "mobile-1", delivery: "auto", input: { type: "message", content: [{ type: "text", text: "Phone prompt" }] }
  } });
  await new Promise((resolve) => setTimeout(resolve, 1700));
  assert.equal(events.filter((event) => event.type === "session.turn" && event.state === "completed").length, 1);
  assert.equal(events.find((event) => event.type === "timeline.item" && event.item.clientMessageId === "mobile-1")?.item.text, "Phone prompt");
});

test("a desktop reply before a queued phone prompt does not complete the phone turn", async (t) => {
  const { gateway, state } = fixture();
  gateway.send = async () => { state.sent++; return { outcome: "queued" }; };
  const connection = createConnection(["prompt.message"], gateway);
  t.after(() => connection.close());
  const events = [];
  connection.onEvent((event) => events.push(event));
  await connection.send({ type: "session.open", requestId: "open", sessionId: "paseo",
    config: { model: modelId("native-1"), cwd: "/disposable" }, history: "skip" });
  await connection.send({ type: "session.prompt", sessionId: "paseo", prompt: {
    clientMessageId: "mobile-1", input: { type: "message", content: [{ type: "text", text: "Queued phone prompt" }] }
  } });
  state.entries.push("## User\n\nDesktop prompt after queue\n\n", "## Assistant\n\nDesktop reply\n\n");
  await new Promise((resolve) => setTimeout(resolve, 1700));
  assert.equal(events.filter((event) => event.type === "session.turn" && event.state === "completed").length, 0);
  state.entries.push("## User\n\nQueued phone prompt\n\n", "## Assistant\n\nPhone reply\n\n");
  await new Promise((resolve) => setTimeout(resolve, 1700));
  assert.equal(events.filter((event) => event.type === "session.turn" && event.state === "completed").length, 1);
});

test("Stop removes only the phone's queued native entry while a desktop turn runs", async (t) => {
  const { gateway, state } = fixture();
  const originalSnapshot = gateway.snapshot;
  gateway.snapshot = async (...args) => ({ ...await originalSnapshot(...args),
    status: "Generating", current_turn_id: 41, active_request_id: "desktop-request" });
  gateway.send = async (...args) => {
    state.sent++;
    return { outcome: "queued", native_request_id: args[4], queue_entry_id: 7 };
  };
  let removed = 0;
  gateway.removeQueued = async (thread, instance, epoch, requestId, queueEntryId) => {
    assert.deepEqual([thread, instance, epoch, queueEntryId], ["native-1", "instance-1", "epoch-1", 7]);
    assert.equal(typeof requestId, "string");
    removed++;
    return { outcome: "removed" };
  };
  gateway.cancel = async () => { throw new Error("Desktop turn must stay running"); };
  const connection = createConnection(["prompt.message", "session.persistence"], gateway);
  t.after(() => connection.close());
  const events = [];
  connection.onEvent((event) => events.push(event));
  await connection.send({ type: "session.open", requestId: "open", sessionId: "paseo",
    config: { model: modelId("native-1"), cwd: "/disposable" }, history: "skip" });
  await connection.send({ type: "session.prompt", sessionId: "paseo", prompt: {
    clientMessageId: "mobile-1", input: { type: "message", content: [{ type: "text", text: "Queued phone prompt" }] }
  } });
  await connection.send({ type: "session.interrupt", requestId: "stop-queued", sessionId: "paseo" });
  assert.equal(removed, 1);
  assert.equal(events.filter((event) => event.type === "session.turn" && event.state === "canceled").length, 1);
  assert.equal(events.filter((event) => event.type === "request.completed" && event.requestId === "stop-queued").length, 1);
  assert.equal(events.filter((event) => event.type === "session.persistence").at(-1).persistence.data.active, undefined);
});

test("a reopened Paseo session resumes and stops the exact native turn without resending", async (t) => {
  const { gateway, state } = fixture();
  const originalSnapshot = gateway.snapshot;
  let activeRequestId = null;
  let currentTurnId = null;
  gateway.snapshot = async (...args) => ({ ...await originalSnapshot(...args),
    status: currentTurnId === null ? "Idle" : "Generating", current_turn_id: currentTurnId,
    active_request_id: activeRequestId, active_request_entry_index: currentTurnId === null ? null : 2 });
  gateway.send = async (...args) => {
    state.sent++;
    activeRequestId = args[4]; currentTurnId = 51;
    state.entries.push(`## User\n\n${args[3]}\n\n`);
    return { outcome: "unknown", native_request_id: args[4] };
  };
  gateway.status = async () => ({ known: true, outcome: "unknown", native_request_id: activeRequestId,
    entry_index: 2 });
  gateway.cancel = async (_thread, _instance, _epoch, turnId) => {
    assert.equal(turnId, 51); currentTurnId = null; return { outcome: "requested" };
  };
  const first = createConnection(["prompt.message", "session.persistence"], gateway);
  t.after(() => first.close());
  const firstEvents = [];
  first.onEvent((event) => firstEvents.push(event));
  await first.send({ type: "session.open", requestId: "open-1", sessionId: "paseo-1",
    config: { model: modelId("native-1"), cwd: "/disposable" }, history: "skip" });
  await first.send({ type: "session.prompt", sessionId: "paseo-1", prompt: {
    clientMessageId: "mobile-1", input: { type: "message", content: [{ type: "text", text: "Resume me" }] }
  } });
  const saved = firstEvents.filter((event) => event.type === "session.persistence").at(-1).persistence;
  assert.equal(saved.data.active.nativeRequestId, activeRequestId);
  await first.close();

  const second = createConnection(["prompt.message", "session.persistence"], gateway);
  t.after(() => second.close());
  const events = [];
  second.onEvent((event) => events.push(event));
  await second.send({ type: "session.open", requestId: "open-2", sessionId: "paseo-2",
    config: { model: modelId("native-1"), cwd: "/disposable" }, persistence: saved, history: "replay" });
  await second.send({ type: "session.interrupt", requestId: "stop-resumed", sessionId: "paseo-2" });
  assert.equal(state.sent, 1);
  assert.equal(events.some((event) => event.type === "session.turn" && event.state === "started"), true);
  assert.equal(events.some((event) => event.type === "request.completed" && event.requestId === "stop-resumed"), true);
});

test("structured native reasoning, tools, model, and usage reach Paseo", async (t) => {
  const { gateway } = fixture();
  gateway.snapshot = async (thread, instance, epoch) => ({ thread_id: thread, instance_id: instance, epoch,
    status: "Idle", entry_start_index: 0, entry_end_index: 2, last_sequence: 1, pending_approvals: [],
    entries_markdown: ["## Assistant\n\n<thinking>check</thinking>\n\nDone\n\n", "## Tool\n\nRead file\n\n"],
    entries_meta: [
      { kind: "assistant", segments: [{ kind: "reasoning", text: "check" }, { kind: "assistant", text: "Done" }] },
      { kind: "tool", call_id: "tool-1", name: "read_file", status: "completed" },
    ] });
  gateway.settings = async () => ({ configuration_owner: "zed", model: { name: "Local model" },
    profile_id: "write", context_usage: { used_tokens: 20, max_tokens: 1000, input_tokens: 12, output_tokens: 8 } });
  const connection = createConnection(["prompt.message"], gateway);
  t.after(() => connection.close());
  const events = [];
  connection.onEvent((event) => events.push(event));
  await connection.send({ type: "session.open", requestId: "open", sessionId: "paseo",
    config: { model: modelId("native-1"), cwd: "/disposable" }, history: "replay" });
  assert.deepEqual(events.filter((event) => event.type === "timeline.item").map((event) => event.item.type),
    ["reasoning", "assistant_message", "tool_call"]);
  assert.equal(events.find((event) => event.type === "session.notice" && event.notice.id === "zedlink-native-model")?.notice.title,
    "Zed model: Local model");
  assert.equal(events.find((event) => event.type === "session.usage")?.usage.contextWindowUsedTokens, 20);
});

test("uncertain send reconciles by original request ID without a second submission", async (t) => {
  const { gateway, state } = fixture();
  let known = false;
  gateway.send = async () => { state.sent++; throw new Error("response lost"); };
  gateway.status = async () => ({ known });
  const connection = createConnection(["prompt.message", "session.persistence"], gateway);
  t.after(() => connection.close());
  const events = [];
  connection.onEvent((event) => events.push(event));
  await connection.send({ type: "session.open", requestId: "open", sessionId: "paseo",
    config: { model: modelId("native-1"), cwd: "/disposable" }, history: "skip" });
  await connection.send({ type: "session.prompt", sessionId: "paseo", prompt: {
    clientMessageId: "mobile-1", delivery: "auto", input: { type: "message", content: [{ type: "text", text: "Phone prompt" }] }
  } });
  const pending = events.find((event) => event.type === "session.persistence")?.persistence.data.uncertain;
  assert.equal(typeof pending.requestId, "string");
  assert.equal(events.filter((event) => event.type === "session.prompt_result").length, 0);
  known = true;
  await new Promise((resolve) => setTimeout(resolve, 1700));
  assert.equal(state.sent, 1);
  assert.equal(events.filter((event) => event.type === "session.prompt_result" && event.clientMessageId === "mobile-1").length, 1);
  assert.equal(events.filter((event) => event.type === "session.persistence").at(-1).persistence.data.uncertain, undefined);
});

test("concurrent prompts cannot pass the same preflight and submit twice", async (t) => {
  const { gateway, state } = fixture();
  const originalSnapshot = gateway.snapshot;
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  let entered;
  const started = new Promise((resolve) => { entered = resolve; });
  let hold = false;
  gateway.snapshot = async (...args) => {
    if (hold) { entered(); await gate; }
    return originalSnapshot(...args);
  };
  const connection = createConnection(["prompt.message"], gateway);
  t.after(() => connection.close());
  const events = [];
  connection.onEvent((event) => events.push(event));
  await connection.send({ type: "session.open", requestId: "open", sessionId: "paseo",
    config: { model: modelId("native-1"), cwd: "/disposable" }, history: "skip" });
  hold = true;
  const first = connection.send({ type: "session.prompt", sessionId: "paseo", prompt: {
    clientMessageId: "mobile-1", input: { type: "message", content: [{ type: "text", text: "First" }] }
  } });
  await started;
  await connection.send({ type: "session.prompt", sessionId: "paseo", prompt: {
    clientMessageId: "mobile-2", input: { type: "message", content: [{ type: "text", text: "Second" }] }
  } });
  release();
  await first;
  assert.equal(state.sent, 1);
  assert.equal(events.find((event) => event.type === "session.prompt_result" && event.clientMessageId === "mobile-2")?.result.type, "failed");
});

test("invalid older history leaves no half-open Paseo session", async (t) => {
  const { gateway } = fixture();
  gateway.snapshot = async (thread, instance, epoch) => ({ thread_id: thread, instance_id: instance, epoch,
    status: "Idle", entries_markdown: ["## Assistant\n\nReply\n\n"], entry_start_index: 1,
    entry_end_index: 2, pending_approvals: [] });
  gateway.history = async (thread, instance, epoch) => ({ thread_id: thread, instance_id: instance, epoch,
    entries_markdown: [], entry_start_index: 1, entry_end_index: 1 });
  const connection = createConnection(["prompt.message"], gateway);
  t.after(() => connection.close());
  const events = [];
  connection.onEvent((event) => events.push(event));
  await assert.rejects(connection.send({ type: "session.open", requestId: "open", sessionId: "paseo",
    config: { model: modelId("native-1"), cwd: "/disposable" }, history: "replay" }), /history is not contiguous/);
  assert.equal(events.filter((event) => event.type === "session.opened").length, 0);
});

test("Stop targets only the native turn correlated with the phone prompt", async (t) => {
  const { gateway, state } = fixture();
  const originalSnapshot = gateway.snapshot;
  let currentTurnId = null;
  let activeRequestId = null;
  gateway.snapshot = async (...args) => ({ ...await originalSnapshot(...args),
    status: currentTurnId === null ? "Idle" : "Generating", current_turn_id: currentTurnId,
    active_request_id: currentTurnId === null ? null : activeRequestId });
  gateway.send = async (...args) => {
    state.sent++;
    state.entries.push(`## User\n\n${args[3]}\n\n`);
    currentTurnId = 17;
    activeRequestId = args[4];
    return { outcome: "queued", native_request_id: args[4] };
  };
  const cancellations = [];
  gateway.cancel = async (...args) => { cancellations.push(args); currentTurnId = null; return { outcome: "requested" }; };
  const connection = createConnection(["prompt.message"], gateway);
  t.after(() => connection.close());
  const events = [];
  connection.onEvent((event) => events.push(event));
  await connection.send({ type: "session.open", requestId: "open", sessionId: "paseo",
    config: { model: modelId("native-1"), cwd: "/disposable" }, history: "skip" });
  await connection.send({ type: "session.prompt", sessionId: "paseo", prompt: {
    clientMessageId: "mobile-1", input: { type: "message", content: [{ type: "text", text: "Stop this" }] }
  } });
  await new Promise((resolve) => setTimeout(resolve, 1700));
  activeRequestId = "desktop-request";
  await assert.rejects(connection.send({ type: "session.interrupt", requestId: "stop-desktop",
    sessionId: "paseo" }), /not the current native Zed turn/);
  assert.equal(cancellations.length, 0);
  activeRequestId = events.find((event) => event.type === "session.prompt_result")?.result.turnId.slice(8);
  currentTurnId = 18;
  await assert.rejects(connection.send({ type: "session.interrupt", requestId: "stop-wrong",
    sessionId: "paseo" }), /turn changed/);
  assert.equal(cancellations.length, 0);
  currentTurnId = 17;
  await connection.send({ type: "session.interrupt", requestId: "stop-right", sessionId: "paseo" });
  assert.deepEqual(cancellations, [["native-1", "instance-1", "epoch-1", 17]]);
  assert.equal(events.find((event) => event.type === "request.completed" && event.requestId === "stop-right")?.requestId, "stop-right");
  await new Promise((resolve) => setTimeout(resolve, 30));
  assert.equal(events.find((event) => event.type === "session.turn" && event.state === "canceled")?.turnId !== undefined, true);
});

test("Stop immediately after submission identifies the running native turn", async (t) => {
  const { gateway, state } = fixture();
  const originalSnapshot = gateway.snapshot;
  let currentTurnId = null;
  let activeRequestId = null;
  gateway.snapshot = async (...args) => ({ ...await originalSnapshot(...args),
    status: currentTurnId === null ? "Idle" : "Generating", current_turn_id: currentTurnId,
    active_request_id: currentTurnId === null ? null : activeRequestId });
  gateway.send = async (...args) => {
    state.sent++;
    state.entries.push(`## User\n\n${args[3]}\n\n`);
    currentTurnId = 29;
    activeRequestId = args[4];
    return { outcome: "queued", native_request_id: args[4] };
  };
  const cancellations = [];
  gateway.cancel = async (...args) => { cancellations.push(args); currentTurnId = null; return { outcome: "requested" }; };
  const connection = createConnection(["prompt.message"], gateway);
  t.after(() => connection.close());
  const events = [];
  connection.onEvent((event) => events.push(event));
  await connection.send({ type: "session.open", requestId: "open", sessionId: "paseo",
    config: { model: modelId("native-1"), cwd: "/disposable" }, history: "skip" });
  await connection.send({ type: "session.prompt", sessionId: "paseo", prompt: {
    clientMessageId: "mobile-1", input: { type: "message", content: [{ type: "text", text: "Stop immediately" }] }
  } });
  await connection.send({ type: "session.interrupt", requestId: "stop-now", sessionId: "paseo" });
  assert.deepEqual(cancellations, [["native-1", "instance-1", "epoch-1", 29]]);
  assert.equal(events.some((event) => event.type === "request.completed" && event.requestId === "stop-now"), true);
});

test("Stop is not confirmed when native Zed declines cancellation", async (t) => {
  const { gateway, state } = fixture();
  const originalSnapshot = gateway.snapshot;
  let activeRequestId = null;
  gateway.snapshot = async (...args) => ({ ...await originalSnapshot(...args),
    status: "Generating", current_turn_id: 31, active_request_id: activeRequestId });
  gateway.send = async (...args) => {
    state.sent++;
    state.entries.push(`## User\n\n${args[3]}\n\n`);
    activeRequestId = args[4];
    return { outcome: "queued", native_request_id: args[4] };
  };
  gateway.cancel = async () => ({ outcome: "stale_turn" });
  const connection = createConnection(["prompt.message"], gateway);
  t.after(() => connection.close());
  const events = [];
  connection.onEvent((event) => events.push(event));
  await connection.send({ type: "session.open", requestId: "open", sessionId: "paseo",
    config: { model: modelId("native-1"), cwd: "/disposable" }, history: "skip" });
  await connection.send({ type: "session.prompt", sessionId: "paseo", prompt: {
    clientMessageId: "mobile-1", input: { type: "message", content: [{ type: "text", text: "Stop declined" }] }
  } });
  await assert.rejects(connection.send({ type: "session.interrupt", requestId: "stop-declined",
    sessionId: "paseo" }), /did not confirm/);
  assert.equal(events.some((event) => event.type === "request.completed" && event.requestId === "stop-declined"), false);
});

test("uncertain receipt stays scoped to its original Zed instance and epoch", async (t) => {
  const { gateway } = fixture();
  let statusCalls = 0;
  gateway.status = async () => { statusCalls++; return { known: true }; };
  const connection = createConnection(["prompt.message", "session.persistence"], gateway);
  t.after(() => connection.close());
  const events = [];
  connection.onEvent((event) => events.push(event));
  await connection.send({ type: "session.open", requestId: "open", sessionId: "paseo",
    config: { model: modelId("native-1"), cwd: "/disposable" }, history: "skip",
    persistence: { version: 1, data: { gatewayId: "gateway-1", targetId: "primary", threadId: "native-1",
      uncertain: { requestId: "old-request", clientMessageId: "mobile-1", startIndex: 2,
        instanceId: "old-instance", epoch: "old-epoch" } } } });
  await new Promise((resolve) => setTimeout(resolve, 30));
  assert.equal(statusCalls, 0);
  assert.equal(events.filter((event) => event.type === "session.prompt_result").length, 0);
  assert.match(events.find((event) => event.type === "session.notice")?.notice.description ?? "", /Zed restarted/);
  assert.equal(events.find((event) => event.type === "session.opened")?.persistence.data.uncertain.epoch, "old-epoch");
});

test("only an explicit one-time Paseo choice resolves the exact native approval", async (t) => {
  const { gateway } = fixture();
  let approval = { approval_id: "tool-1", turn_id: 23, tool_name: "terminal",
    display: "Run test command", raw_input: { command: "printf test" }, details_truncated: false,
    authorization_kind: "permission_grant", permission_options: { presentation: "flat", decisions: [
      { option_id: "always", label: "Always allow", option_kind: "allow_always" },
      { option_id: "once", label: "Allow once", option_kind: "allow_once" },
      { option_id: "deny", label: "Deny once", option_kind: "reject_once" },
    ] } };
  const originalSnapshot = gateway.snapshot;
  gateway.snapshot = async (...args) => ({ ...await originalSnapshot(...args), pending_approvals: approval ? [approval] : [] });
  gateway.approvals = async () => ({ approvals: approval ? [approval] : [] });
  const decisions = [];
  gateway.respondApproval = async (...args) => { decisions.push(args); approval = null; return { outcome: "resolved" }; };
  const connection = createConnection(["prompt.message", "permission"], gateway);
  t.after(() => connection.close());
  const events = [];
  connection.onEvent((event) => events.push(event));
  await connection.send({ type: "session.open", requestId: "open", sessionId: "paseo",
    config: { model: modelId("native-1"), cwd: "/disposable" }, history: "replay" });
  const request = events.find((event) => event.type === "session.permission")?.request;
  assert.equal(request.name, "terminal");
  assert.deepEqual(request.actions.map((action) => action.label), ["Allow once", "Deny once"]);
  assert.equal(decisions.length, 0);
  await connection.send({ type: "session.permission", sessionId: "paseo", permissionId: request.id,
    response: { behavior: "allow", selectedActionId: request.actions[0].id } });
  assert.deepEqual(decisions, [["native-1", "instance-1", "epoch-1", "tool-1", 23, "once", undefined, undefined]]);
  assert.equal(events.find((event) => event.type === "session.permission_resolved")?.permissionId, request.id);
});

test("one unambiguous behavior-only Deny reaches native Zed", async (t) => {
  const { gateway } = fixture();
  const row = { approval_id: "tool-deny", turn_id: 24, tool_name: "terminal",
    display: "Run", raw_input: { command: "printf test" }, details_truncated: false,
    authorization_kind: "permission_grant", permission_options: { decisions: [
      { option_id: "allow", label: "Allow once", option_kind: "allow_once" },
      { option_id: "deny", label: "Deny once", option_kind: "reject_once" },
    ] } };
  const originalSnapshot = gateway.snapshot;
  gateway.snapshot = async (...args) => ({ ...await originalSnapshot(...args), pending_approvals: [row] });
  gateway.approvals = async () => ({ approvals: [row] });
  const decisions = [];
  gateway.respondApproval = async (...args) => { decisions.push(args); return { outcome: "resolved" }; };
  const connection = createConnection(["prompt.message", "permission"], gateway);
  t.after(() => connection.close());
  const events = [];
  connection.onEvent((event) => events.push(event));
  await connection.send({ type: "session.open", requestId: "open", sessionId: "paseo",
    config: { model: modelId("native-1"), cwd: "/disposable" }, history: "replay" });
  const request = events.find((event) => event.type === "session.permission").request;
  await connection.send({ type: "session.permission", sessionId: "paseo", permissionId: request.id,
    response: { behavior: "deny", message: "Denied by user" } });
  assert.deepEqual(decisions, [["native-1", "instance-1", "epoch-1", "tool-deny", 24, "deny", undefined, undefined]]);
  assert.equal(events.find((event) => event.type === "session.permission_resolved")?.permissionId, request.id);
});

test("behavior-only permission cannot choose among multiple native options", async (t) => {
  const { gateway } = fixture();
  const row = { approval_id: "tool-choices", turn_id: 24, tool_name: "terminal",
    display: "Run", raw_input: { command: "printf test" }, details_truncated: false,
    authorization_kind: "permission_grant", permission_options: { decisions: [
      { option_id: "allow", label: "Allow once", option_kind: "allow_once" },
      { option_id: "deny-a", label: "Deny A", option_kind: "reject_once" },
      { option_id: "deny-b", label: "Deny B", option_kind: "reject_once" },
    ] } };
  const originalSnapshot = gateway.snapshot;
  gateway.snapshot = async (...args) => ({ ...await originalSnapshot(...args), pending_approvals: [row] });
  let decisions = 0;
  gateway.respondApproval = async () => { decisions++; return { outcome: "resolved" }; };
  const connection = createConnection(["prompt.message", "permission"], gateway);
  t.after(() => connection.close());
  const events = [];
  connection.onEvent((event) => events.push(event));
  await connection.send({ type: "session.open", requestId: "open", sessionId: "paseo",
    config: { model: modelId("native-1"), cwd: "/disposable" }, history: "replay" });
  const request = events.find((event) => event.type === "session.permission").request;
  await assert.rejects(connection.send({ type: "session.permission", sessionId: "paseo", permissionId: request.id,
    response: { behavior: "deny" } }), /Choose one/);
  assert.equal(decisions, 0);
  assert.equal(events.filter((event) => event.type === "session.permission_resolved").length, 0);
});

test("stale or incomplete native approval never receives a Paseo authorization", async (t) => {
  const { gateway } = fixture();
  const row = { approval_id: "tool-2", turn_id: 24, tool_name: "terminal",
    display: "Run", raw_input: { command: "printf test" }, details_truncated: false,
    authorization_kind: "permission_grant", permission_options: { decisions: [
      { option_id: "once", label: "Allow once", option_kind: "allow_once" },
      { option_id: "deny", label: "Deny once", option_kind: "reject_once" },
    ] } };
  const originalSnapshot = gateway.snapshot;
  gateway.snapshot = async (...args) => ({ ...await originalSnapshot(...args),
    pending_approvals: [row, { ...row, approval_id: "hidden", details_truncated: true }] });
  gateway.approvals = async () => ({ approvals: [{ ...row, raw_input: { command: "different" } }] });
  let responses = 0;
  gateway.respondApproval = async () => { responses++; return { outcome: "resolved" }; };
  const connection = createConnection(["prompt.message", "permission"], gateway);
  t.after(() => connection.close());
  const events = [];
  connection.onEvent((event) => events.push(event));
  await connection.send({ type: "session.open", requestId: "open", sessionId: "paseo",
    config: { model: modelId("native-1"), cwd: "/disposable" }, history: "replay" });
  const requests = events.filter((event) => event.type === "session.permission");
  assert.equal(requests.length, 1);
  assert.equal(events.some((event) => event.type === "session.notice" && event.notice.id.startsWith("zedlink-approval:")), true);
  await assert.rejects(connection.send({ type: "session.permission", sessionId: "paseo", permissionId: requests[0].request.id,
    response: { behavior: "allow", selectedActionId: requests[0].request.actions[0].id } }), /changed or expired/);
  assert.equal(responses, 0);
  assert.match(events.at(-1).notice.description, /changed or expired/);
});

test("lost approval response remains unconfirmed and is never retried automatically", async (t) => {
  const { gateway } = fixture();
  const row = { approval_id: "tool-3", turn_id: 25, tool_name: "terminal",
    display: "Run", raw_input: { command: "printf test" }, details_truncated: false,
    authorization_kind: "permission_grant", permission_options: { decisions: [
      { option_id: "once", label: "Allow once", option_kind: "allow_once" },
      { option_id: "deny", label: "Deny once", option_kind: "reject_once" },
    ] } };
  const originalSnapshot = gateway.snapshot;
  gateway.snapshot = async (...args) => ({ ...await originalSnapshot(...args), pending_approvals: [row] });
  gateway.approvals = async () => ({ approvals: [row] });
  let attempts = 0;
  gateway.respondApproval = async () => { attempts++; throw new Error("response lost"); };
  const connection = createConnection(["prompt.message", "permission"], gateway);
  t.after(() => connection.close());
  const events = [];
  connection.onEvent((event) => events.push(event));
  await connection.send({ type: "session.open", requestId: "open", sessionId: "paseo",
    config: { model: modelId("native-1"), cwd: "/disposable" }, history: "replay" });
  const request = events.find((event) => event.type === "session.permission").request;
  await assert.rejects(connection.send({ type: "session.permission", sessionId: "paseo", permissionId: request.id,
    response: { behavior: "deny", selectedActionId: request.actions[1].id, message: "Denied by user" } }), /did not confirm/);
  assert.equal(attempts, 1);
  assert.equal(events.filter((event) => event.type === "session.permission_resolved").length, 0);
  assert.match(events.at(-1).notice.description, /did not confirm/);
});
