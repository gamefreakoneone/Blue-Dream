import { api, apiRequest } from "./api";

function urlBase64ToUint8Array(value) {
  const padding = "=".repeat((4 - (value.length % 4)) % 4);
  const base64 = (value + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = window.atob(base64);
  return Uint8Array.from([...raw].map((character) => character.charCodeAt(0)));
}

export async function getPushStatus() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
    return { state: "unsupported", subscription: null };
  }
  if (Notification.permission === "denied") {
    return { state: "denied", subscription: null };
  }
  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.getSubscription();
  return {
    state: subscription ? "enabled" : Notification.permission === "granted" ? "available" : "prompt",
    subscription,
  };
}

export async function enablePush() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
    return { state: "unsupported" };
  }
  const permission = await Notification.requestPermission();
  if (permission !== "granted") return { state: permission === "denied" ? "denied" : "prompt" };

  const config = await api.vapidKey();
  if (!config.enabled || !config.key) return { state: "not_configured" };
  const registration = await navigator.serviceWorker.ready;
  let subscription = await registration.pushManager.getSubscription();
  if (!subscription) {
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(config.key),
    });
  }
  await apiRequest("/push/subscribe", {
    method: "POST",
    body: JSON.stringify({ subscription: subscription.toJSON(), role: "patient" }),
  });
  return { state: "enabled", subscription };
}

export async function disablePush() {
  if (!("serviceWorker" in navigator)) return { state: "unsupported" };
  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.getSubscription();
  if (subscription) {
    await apiRequest("/push/unsubscribe", {
      method: "POST",
      body: JSON.stringify({ endpoint: subscription.endpoint }),
    });
    await subscription.unsubscribe();
  }
  return { state: "disabled" };
}
