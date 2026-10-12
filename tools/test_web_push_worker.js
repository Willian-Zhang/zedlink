"use strict";
// Exercise production worker handlers without a push provider or native runtime.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const handlers = {};
const notifications = [];
const navigated = [];
const origin = "https://gateway.example.test";
const client = { url: origin + "/", navigate: async url => navigated.push(url), focus: async () => {} };
vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../gateway/web/service-worker.js"), "utf8"), {
  URL, URLSearchParams, Promise,
  self: {
    location: { origin }, navigator: { setAppBadge: async () => {} },
    addEventListener: (name, callback) => handlers[name] = callback,
    registration: { showNotification: async (title, options) => notifications.push({ title, options }) },
    clients: { matchAll: async () => [client], openWindow: async url => navigated.push(url) },
  },
  // Notification actions must navigate to authenticated review, never send a decision.
  fetch: () => { throw Error("Worker must not approve or deny an agent request"); },
});
async function dispatch(name, event) {
  let promise;
  handlers[name]({ ...event, waitUntil: value => promise = value });
  await promise;
}
(async () => {
  await dispatch("push", { data: { json: () => ({ kind: "approval", thread_id: "thread a", target_id: "target b" }) } });
  assert.equal(notifications[0].options.actions[0].action, "review");
  assert.equal(notifications[0].options.requireInteraction, true);
  await dispatch("notificationclick", { action: "review", notification: { close() {}, data: notifications[0].options.data } });
  const route = new URL(navigated.pop());
  assert.equal(route.origin, origin);
  assert.equal(route.searchParams.get("thread"), "thread a");
  assert.equal(route.searchParams.get("target"), "target b");
  await dispatch("notificationclick", { notification: { close() {}, data: { url: "https://outside.example.test/" } } });
  assert.equal(navigated.pop(), origin + "/");
  await dispatch("push", { data: { json: () => { throw Error("Malformed payload"); } } });
  assert.equal(notifications[1].title, "ZedLink");
  assert.equal(notifications[1].options.actions, undefined);
  console.log("PASS: approval review action, exact route, same-origin navigation, generic malformed fallback; no automatic decisions");
})().catch(error => { console.error(error); process.exitCode = 1; });
