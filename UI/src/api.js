const SAFE_ERROR = "Memoria is having a little trouble connecting. Please try again.";

export async function apiRequest(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const error = new Error(SAFE_ERROR);
    error.status = response.status;
    throw error;
  }
  return payload;
}

export const api = {
  query: (query, sessionId) =>
    apiRequest("/query", {
      method: "POST",
      body: JSON.stringify({ query, session_id: sessionId }),
    }),
  resetConversation: (sessionId) =>
    apiRequest("/conversation/reset", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId }),
    }),
  pendingProactive: (sessionId) =>
    apiRequest(`/proactive/pending?session_id=${encodeURIComponent(sessionId)}`),
  acknowledgeProactive: (messageId) =>
    apiRequest(`/proactive/${encodeURIComponent(messageId)}/ack`, { method: "POST" }),
  listReminders: () => apiRequest("/reminders"),
  createReminder: (value) =>
    apiRequest("/reminders", { method: "POST", body: JSON.stringify(value) }),
  completeReminder: (reminderId) =>
    apiRequest(`/reminders/${encodeURIComponent(reminderId)}/done`, { method: "POST" }),
  listAlerts: () => apiRequest("/alerts/patient?status=open"),
  acknowledgeAlert: (alertId, action = "ok") =>
    apiRequest(`/alerts/${encodeURIComponent(alertId)}/ack`, {
      method: "POST",
      body: JSON.stringify({ action }),
    }),
  geofenceSettings: () => apiRequest("/geofence/current"),
  listFacts: () => apiRequest("/memory/profile"),
  pinFact: (factId) =>
    apiRequest(`/memory/profile/${encodeURIComponent(factId)}/pin`, { method: "POST" }),
  archiveFact: (factId) =>
    apiRequest(`/memory/profile/${encodeURIComponent(factId)}/archive`, { method: "POST" }),
  summaries: (days = 7) => apiRequest(`/memory/summaries?days=${days}`),
  consolidate: () => apiRequest("/memory/consolidate", { method: "POST" }),
  simulateExit: (body) =>
    apiRequest("/geofence/events", { method: "POST", body: JSON.stringify(body) }),
  vapidKey: () => apiRequest("/push/vapid-public-key"),
  testPush: () => apiRequest("/push/test", { method: "POST" }),
};

export function mediaUrl(value) {
  if (!value) return null;
  const normalized = String(value).replaceAll("\\", "/");
  const encodePath = (path) => {
    try { return encodeURI(decodeURI(path)); }
    catch { return encodeURI(path); }
  };
  if (normalized.startsWith("/")) return encodePath(normalized);
  const storage = normalized.toLowerCase().indexOf("storage/");
  if (storage >= 0) return encodePath(`/storage/${normalized.slice(storage + 8)}`);
  const capture = normalized.toLowerCase().indexOf("capture/");
  if (capture >= 0) return encodePath(`/capture/${normalized.slice(capture + 8)}`);
  return encodePath(normalized);
}
