const chatContainer = document.getElementById('chat-container');
const chatForm = document.getElementById('chat-form');
const userInput = document.getElementById('user-input');
const newChatBtn = document.getElementById('new-chat-btn');
const statusIndicator = document.querySelector('.status-indicator');
const simulateExitBtn = document.getElementById('simulate-exit-btn');
const geofenceStatus = document.getElementById('geofence-status');
const alertList = document.getElementById('alert-list');
const alertDetail = document.getElementById('alert-detail');
const emergencyError = document.getElementById('emergency-error');

// Store the API URL - in this case relative
const API_URL = '/query';
const RESET_URL = '/conversation/reset';
const GEOFENCE_URL = '/geofence/current';
const GEOFENCE_EVENTS_URL = '/geofence/events';
const ALERTS_URL = '/alerts/patient?status=open';
const SESSION_STORAGE_KEY = 'memoriaConversationSessionId';

let conversationSessionId = getOrCreateSessionId();
let currentGeofence = null;
let currentAlert = null;

function createSessionId() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') {
        return window.crypto.randomUUID();
    }
    return `session-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function getOrCreateSessionId() {
    const existingSessionId = sessionStorage.getItem(SESSION_STORAGE_KEY);
    if (existingSessionId) {
        return existingSessionId;
    }
    const nextSessionId = createSessionId();
    sessionStorage.setItem(SESSION_STORAGE_KEY, nextSessionId);
    return nextSessionId;
}

function startFreshSession() {
    conversationSessionId = createSessionId();
    sessionStorage.setItem(SESSION_STORAGE_KEY, conversationSessionId);
}

function renderWelcomeMessage() {
    chatContainer.innerHTML = `
        <div class="message system">
            <div class="bubble">
                <p>Hello, I am Memoria. How can I assist you today?</p>
            </div>
        </div>
    `;
    scrollToBottom();
}

chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const query = userInput.value.trim();
    if (!query) return;

    // Add user message to UI
    addMessage(query, 'user');
    userInput.value = '';

    // Small animation for logo
    const logo = document.querySelector('.logo-slime');
    if (logo) {
        logo.style.transform = 'scale(1.1) rotate(5deg)';
        setTimeout(() => logo.style.transform = 'scale(1) rotate(0deg)', 300);
    }

    // Show loading state
    const loadingId = addLoadingIndicator();

    try {
        const response = await fetch(API_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                query: query,
                session_id: conversationSessionId
            })
        });

        if (!response.ok) {
            throw new Error(`API Error: ${response.statusText}`);
        }

        const data = await response.json();
        
        // Remove loading indicator
        removeMessage(loadingId);

        // Process answer
        handleJeevesResponse(data);

    } catch (error) {
        removeMessage(loadingId);
        addMessage(`Error: ${error.message}`, 'bot');
        console.error('Error querying Jeeves:', error);
    }
});

newChatBtn.addEventListener('click', async () => {
    const sessionIdToReset = conversationSessionId;
    startFreshSession();
    renderWelcomeMessage();
    userInput.focus();

    try {
        await fetch(RESET_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ session_id: sessionIdToReset })
        });
    } catch (error) {
        console.error('Error resetting conversation:', error);
    }
});

if (simulateExitBtn) {
    simulateExitBtn.addEventListener('click', simulateSafeZoneExit);
}

document.addEventListener('DOMContentLoaded', () => {
    refreshEmergencyDemo();
});

async function fetchJson(url, options = {}) {
    const response = await fetch(url, {
        headers: {
            'Content-Type': 'application/json',
            ...(options.headers || {})
        },
        ...options
    });

    if (!response.ok) {
        let detail = response.statusText;
        try {
            const errorBody = await response.json();
            detail = errorBody.detail || detail;
        } catch (_) {
            // Keep the status text when the response is not JSON.
        }
        throw new Error(`${response.status}: ${detail}`);
    }

    return response.json();
}

async function refreshEmergencyDemo() {
    await Promise.allSettled([
        loadGeofence(),
        loadPatientAlerts()
    ]);
}

async function loadGeofence() {
    if (!geofenceStatus) return;
    geofenceStatus.textContent = 'Loading geofence...';
    try {
        currentGeofence = await fetchJson(GEOFENCE_URL);
        renderGeofence(currentGeofence);
        setEmergencyError('');
    } catch (error) {
        currentGeofence = null;
        renderGeofence(null);
        setEmergencyError(`Could not load geofence from backend: ${error.message}`);
    }
}

async function loadPatientAlerts(selectFirst = false) {
    if (!alertList) return;
    alertList.textContent = 'Loading alerts...';
    try {
        const data = await fetchJson(ALERTS_URL);
        const alerts = Array.isArray(data.alerts) ? data.alerts : [];
        renderAlertList(alerts);
        if (selectFirst && alerts.length > 0) {
            await selectAlert(alerts[0].alert_id);
        }
        setEmergencyError('');
    } catch (error) {
        alertList.innerHTML = '<div class="status-card danger">Alert list unavailable.</div>';
        setEmergencyError(`Could not load patient alerts: ${error.message}`);
    }
}

function renderGeofence(geofence) {
    const lat = geofence?.home_lat;
    const lng = geofence?.home_lng;
    const radius = Number(geofence?.radius_meters);

    if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
        geofenceStatus.classList.remove('muted');
        geofenceStatus.classList.add('danger');
        geofenceStatus.textContent = 'Home coordinates are not configured.';
        return;
    }

    const source = geofence.source || 'backend';

    geofenceStatus.classList.remove('muted', 'danger');
    geofenceStatus.innerHTML = `
        <div class="geo-line">
            <strong>${formatCoord(lat)}, ${formatCoord(lng)}</strong>
            <span>${Number.isFinite(radius) ? Math.round(radius) : 100}m radius</span>
        </div>
        <div class="meta-row">
            <span>Source: ${escapeHtml(source)}</span>
            <button type="button" class="link-button" id="guide-home-mini">Open Maps</button>
        </div>
    `;

    const mapsButton = document.getElementById('guide-home-mini');
    if (mapsButton) {
        mapsButton.addEventListener('click', openMapsHome);
    }
}

function renderAlertList(alerts) {
    if (!alerts.length) {
        alertList.innerHTML = '<div class="status-card muted">No open patient alerts yet.</div>';
        return;
    }

    alertList.innerHTML = '';
    alerts.slice(0, 5).forEach((alert) => {
        const item = document.createElement('button');
        item.type = 'button';
        item.className = 'alert-list-item';
        item.innerHTML = `
            <span>
                <strong>${escapeHtml(alert.title || 'Memoria alert')}</strong>
                <small>${escapeHtml(alert.severity || 'unknown')} severity</small>
            </span>
            <i class="fa-solid fa-chevron-right"></i>
        `;
        item.addEventListener('click', () => selectAlert(alert.alert_id));
        alertList.appendChild(item);
    });
}

async function selectAlert(alertId) {
    if (!alertId) return;
    alertDetail.classList.remove('empty');
    alertDetail.innerHTML = '<div class="status-card muted">Loading alert detail...</div>';
    try {
        currentAlert = await fetchJson(`/alerts/${encodeURIComponent(alertId)}`);
        renderAlertDetail(currentAlert);
        setEmergencyError('');
    } catch (error) {
        alertDetail.innerHTML = '<div class="status-card danger">Alert detail unavailable.</div>';
        setEmergencyError(`Could not load alert detail: ${error.message}`);
    }
}

function renderAlertDetail(alert) {
    const status = alert.status || 'open';
    const deliveryStatus = alert.delivery_status || 'unknown';
    const showGuideHome = alert.recommended_action === 'confirm_ok_or_guide_home';
    const location = alert.location || {};
    const lat = Number(location.latitude);
    const lng = Number(location.longitude);

    alertDetail.classList.remove('empty');
    alertDetail.innerHTML = `
        <div class="alert-topline">
            <span class="severity-pill ${escapeHtml(alert.severity || 'medium')}">${escapeHtml(alert.severity || 'medium')}</span>
            <span class="status-pill">${escapeHtml(status)}</span>
            <span class="delivery-pill">Delivery: ${escapeHtml(deliveryStatus)}</span>
        </div>
        <h3>${escapeHtml(alert.title || 'Memoria alert')}</h3>
        <p class="alert-body">${escapeHtml(alert.body || alert.message || 'Patient safety alert created.')}</p>
        <div class="alert-meta">
            <span><strong>Action:</strong> ${escapeHtml(alert.recommended_action || 'review')}</span>
            <span><strong>Deep link:</strong> ${escapeHtml(alert.deep_link || 'not available')}</span>
            ${Number.isFinite(lat) && Number.isFinite(lng) ? `<span><strong>Reported at:</strong> ${formatCoord(lat)}, ${formatCoord(lng)}</span>` : ''}
        </div>
        ${alert.detailed_explanation ? `<p class="detail-note">${escapeHtml(alert.detailed_explanation)}</p>` : ''}
        <div class="alert-actions">
            ${showGuideHome ? '<button type="button" class="guide-btn" id="guide-home-btn"><i class="fa-solid fa-route"></i><span>Guide me home</span></button>' : ''}
            <button type="button" class="ack-btn" data-action="returning">I'm returning</button>
            <button type="button" class="ack-btn" data-action="ok">I'm OK</button>
            <button type="button" class="ack-btn subtle" data-action="dismissed">Dismiss</button>
        </div>
    `;

    const guideButton = document.getElementById('guide-home-btn');
    if (guideButton) {
        guideButton.addEventListener('click', openMapsHome);
    }

    alertDetail.querySelectorAll('[data-action]').forEach((button) => {
        button.addEventListener('click', () => acknowledgeSelectedAlert(button.dataset.action));
    });
}

async function simulateSafeZoneExit() {
    if (!simulateExitBtn) return;
    simulateExitBtn.disabled = true;
    simulateExitBtn.classList.add('busy');
    simulateExitBtn.querySelector('span').textContent = 'Creating alert...';
    setEmergencyError('');

    try {
        const homeLat = currentGeofence?.home_lat;
        const homeLng = currentGeofence?.home_lng;
        if (!Number.isFinite(homeLat) || !Number.isFinite(homeLng)) {
            throw new Error('Home coordinates are not configured.');
        }
        const radiusMeters = Number(currentGeofence.radius_meters) || 100;
        const latitudeOffset = Math.max((radiusMeters * 1.5) / 111320, 0.001);
        const alert = await fetchJson(GEOFENCE_EVENTS_URL, {
            method: 'POST',
            body: JSON.stringify({
                event_type: 'exit',
                latitude: homeLat + latitudeOffset,
                longitude: homeLng,
                device_id: 'web-demo'
            })
        });
        currentAlert = alert;
        renderAlertDetail(alert);
        await loadPatientAlerts();
    } catch (error) {
        setEmergencyError(`Could not create emergency alert: ${error.message}`);
    } finally {
        simulateExitBtn.disabled = false;
        simulateExitBtn.classList.remove('busy');
        simulateExitBtn.querySelector('span').textContent = 'Simulate safe-zone exit';
    }
}

async function acknowledgeSelectedAlert(action) {
    if (!currentAlert || !currentAlert.alert_id) return;
    setEmergencyError('');
    try {
        const updated = await fetchJson(`/alerts/${encodeURIComponent(currentAlert.alert_id)}/ack`, {
            method: 'POST',
            body: JSON.stringify({ action })
        });
        currentAlert = updated;
        renderAlertDetail(updated);
        await loadPatientAlerts();
    } catch (error) {
        setEmergencyError(`Could not acknowledge alert: ${error.message}`);
    }
}

function openMapsHome() {
    const lat = currentGeofence?.home_lat;
    const lng = currentGeofence?.home_lng;
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
        setEmergencyError('Home coordinates are not available.');
        return;
    }
    window.open(`https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}`, '_blank', 'noopener,noreferrer');
}

function setEmergencyError(message) {
    if (!emergencyError) return;
    emergencyError.textContent = message || '';
}

function formatCoord(value) {
    const numberValue = Number(value);
    return Number.isFinite(numberValue) ? numberValue.toFixed(5) : 'unknown';
}

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function handleJeevesResponse(data) {
    // data matches the JeevesResponse model from api.py
    // { response_type: str, text: str, image_path: str | null, data: obj | null }
    
    addMessage(data.text, 'bot', data.image_path);
}

function addMessage(text, sender, imagePath = null) {
    const messageDiv = document.createElement('div');
    messageDiv.classList.add('message', sender);

    const bubble = document.createElement('div');
    bubble.classList.add('bubble');
    bubble.textContent = text;
    messageDiv.appendChild(bubble);

    if (imagePath) {
        const img = document.createElement('img');
        img.src = imagePath;
        img.alt = 'Search Result';
        img.classList.add('message-image');
        img.onerror = () => { img.style.display = 'none'; bubble.textContent += ' [Image failed to load]'; };
        
        messageDiv.appendChild(img);
    }

    chatContainer.appendChild(messageDiv);
    scrollToBottom();
    return messageDiv.id = 'msg-' + Date.now();
}

function addLoadingIndicator() {
    const messageDiv = document.createElement('div');
    messageDiv.classList.add('message', 'bot');
    messageDiv.id = 'loading-' + Date.now();

    const bubble = document.createElement('div');
    bubble.classList.add('bubble');
    
    const typingIndicator = document.createElement('div');
    typingIndicator.classList.add('typing-indicator');
    
    typingIndicator.innerHTML = `
        <div class="dot"></div>
        <div class="dot"></div>
        <div class="dot"></div>
    `;
    
    bubble.appendChild(typingIndicator);
    messageDiv.appendChild(bubble);
    chatContainer.appendChild(messageDiv);
    scrollToBottom();
    
    return messageDiv.id;
}

function removeMessage(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

function scrollToBottom() {
    chatContainer.scrollTop = chatContainer.scrollHeight;
}
