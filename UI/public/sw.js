const CHAT_URL = "/#chat";

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

// Deliberately network-only: demo-morning builds must never be hidden by a stale cache.
self.addEventListener("fetch", (event) => {
  event.respondWith(fetch(event.request));
});

self.addEventListener("push", (event) => {
  event.waitUntil(
    (async () => {
      let data = {};
      try {
        data = event.data ? event.data.json() : {};
      } catch {
        data = { title: "Memoria", body: "There is a new note for you." };
      }

      const windows = await self.clients.matchAll({
        type: "window",
        includeUncontrolled: true,
      });
      const focusedClient = windows.find(
        (client) => client.visibilityState === "visible" && client.focused,
      );
      if (focusedClient) {
        focusedClient.postMessage({ type: "proactive-push", ...data });
        return;
      }

      await self.registration.showNotification(data.title || "Memoria", {
        body: data.body || "There is a new note for you.",
        tag: data.message_id || data.tag,
        icon: "/icons/icon-192.png",
        badge: "/icons/icon-192.png",
        image: data.image || undefined,
        data: {
          url: data.url || CHAT_URL,
          message_id: data.message_id || data.tag || null,
        },
      });
    })(),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    (async () => {
      const target = event.notification.data?.url || CHAT_URL;
      const windows = await self.clients.matchAll({
        type: "window",
        includeUncontrolled: true,
      });
      if (windows.length) {
        const existing = windows[0];
        if ("navigate" in existing) {
          await existing.navigate(target);
        }
        await existing.focus();
        existing.postMessage({
          type: "notification-opened",
          message_id: event.notification.data?.message_id || null,
        });
        return;
      }
      const opened = await self.clients.openWindow(target);
      opened?.postMessage({
        type: "notification-opened",
        message_id: event.notification.data?.message_id || null,
      });
    })(),
  );
});

function urlBase64ToUint8Array(value) {
  const padding = "=".repeat((4 - (value.length % 4)) % 4);
  const base64 = (value + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  return Uint8Array.from([...raw].map((character) => character.charCodeAt(0)));
}

self.addEventListener("pushsubscriptionchange", (event) => {
  event.waitUntil(
    (async () => {
      let applicationServerKey = event.oldSubscription?.options?.applicationServerKey;
      if (!applicationServerKey) {
        const response = await fetch("/push/vapid-public-key");
        const config = await response.json();
        if (!config.enabled || !config.key) return;
        applicationServerKey = urlBase64ToUint8Array(config.key);
      }

      const subscription = await self.registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey,
      });
      await fetch("/push/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ subscription: subscription.toJSON(), role: "patient" }),
      });
    })(),
  );
});
