const API_BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL || 'http://localhost:8000';

function getUrl(path) {
  return `${API_BASE_URL}${path}`;
}

export function rewriteImagePath(imagePath) {
  if (!imagePath) return null;
  if (/^https?:\/\//i.test(imagePath)) return imagePath;
  if (imagePath.startsWith('/')) return `${API_BASE_URL}${imagePath}`;
  return imagePath;
}

export async function queryAssistant({ query, session_id }) {
  const res = await fetch(getUrl('/query'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, session_id }),
  });
  if (!res.ok) throw new Error(`API Error: ${res.status}`);
  return await res.json();
}

export async function resetConversation({ session_id }) {
  const res = await fetch(getUrl('/conversation/reset'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id }),
  });
  if (!res.ok) throw new Error(`API Error: ${res.status}`);
  return await res.json();
}

export async function getAlerts(status = 'open') {
  const res = await fetch(getUrl(`/alerts/patient?status=${encodeURIComponent(status)}`), {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) throw new Error(`API Error: ${res.status}`);
  return await res.json();
}

export async function getAlert(alertId) {
  const res = await fetch(getUrl(`/alerts/${encodeURIComponent(alertId)}`), {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) throw new Error(`API Error: ${res.status}`);
  return await res.json();
}

export async function ackAlert(alertId, action) {
  const res = await fetch(getUrl(`/alerts/${encodeURIComponent(alertId)}/ack`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action }),
  });
  if (!res.ok) throw new Error(`API Error: ${res.status}`);
  return await res.json();
}

export async function getGeofence() {
  const res = await fetch(getUrl('/geofence/current'), {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) throw new Error(`API Error: ${res.status}`);
  return await res.json();
}

export async function recordGeofenceEvent({ event_type, latitude, longitude, device_id }) {
  const res = await fetch(getUrl('/geofence/events'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ event_type, latitude, longitude, device_id }),
  });
  if (!res.ok) throw new Error(`API Error: ${res.status}`);
  return await res.json();
}

export async function registerDevice({ device_id, platform, push_provider, push_token, role }) {
  const res = await fetch(getUrl('/devices/register'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ device_id, platform, push_provider, push_token, role }),
  });
  if (!res.ok) throw new Error(`API Error: ${res.status}`);
  return await res.json();
}
