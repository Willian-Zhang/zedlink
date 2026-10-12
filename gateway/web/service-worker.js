"use strict";

const SHELL_CACHE = "zedlink-shell-v45";
const SHELL = [
  "/",
  "/style.css",
  "/app.js",
  "/fonts/terminal-icons.woff2",
  "/manifest.webmanifest",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(
    keys.filter((key) => key !== SHELL_CACHE).map((key) => caches.delete(key)),
  )));
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin || url.pathname.startsWith("/v1/")) return;
  event.respondWith(fetch(event.request).then((response) => {
    if (response.ok && SHELL.includes(url.pathname)) {
      const copy = response.clone();
      caches.open(SHELL_CACHE).then((cache) => cache.put(event.request, copy));
    }
    return response;
  }).catch(() => caches.match(event.request).then((cached) => cached || caches.match("/"))));
});

self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data?.json() || {}; } catch { /* Show a generic notification. */ }
  const title = typeof data.title === "string" ? data.title : "ZedLink";
  const body = typeof data.body === "string" ? data.body : "A Zed Agent session changed.";
  const thread = typeof data.thread_id === "string" ? data.thread_id : null;
  const target = typeof data.target_id === "string" ? data.target_id : null;
  const parameters = new URLSearchParams();
  if (target) parameters.set("target", target);
  if (thread) parameters.set("thread", thread);
  const url = parameters.size ? `/?${parameters}` : "/";
  event.waitUntil(Promise.all([
    self.registration.showNotification(title, {
      body,
      tag: typeof data.tag === "string" ? data.tag : "zedlink",
      icon: "/icons/icon-192.png",
      badge: "/icons/icon-192.png",
      data: { url },
    }),
    "setAppBadge" in self.navigator ? self.navigator.setAppBadge(1) : Promise.resolve(),
  ]));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL(event.notification.data?.url || "/", self.location.origin).href;
  event.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(async (clients) => {
    for (const client of clients) {
      if (new URL(client.url).origin === self.location.origin) {
        await client.navigate(target);
        return client.focus();
      }
    }
    return self.clients.openWindow(target);
  }));
});
