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
  listAlerts: () => apiRequest("/alerts/open?target_role=patient"),
  acknowledgeAlert: (alertId, action = "ok") =>
    apiRequest(`/alerts/${encodeURIComponent(alertId)}/ack`, {
      method: "POST",
      body: JSON.stringify({ action }),
    }),
  geofenceSettings: () => apiRequest("/geofence/settings"),
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
