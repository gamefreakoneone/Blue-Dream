const chatContainer = document.getElementById('chat-container');
const chatForm = document.getElementById('chat-form');
const userInput = document.getElementById('user-input');
const newChatBtn = document.getElementById('new-chat-btn');
const statusIndicator = document.querySelector('.status-indicator');

// Store the API URL - in this case relative
const API_URL = '/query';
const RESET_URL = '/conversation/reset';
const SESSION_STORAGE_KEY = 'memoriaConversationSessionId';

let conversationSessionId = getOrCreateSessionId();

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
        // Adjust path if necessary. Provided path might be absolute or relative.
        // We mounted 'Capture' folder at '/capture' in api.py.
        // We need to detect if the path is within the Capture folder and rewrite it.
        
        let normalizedPath = imagePath.replace(/\\/g, '/');
        
        // Handle Capture mount
        if (normalizedPath.toLowerCase().includes('/capture/')) {
             const parts = normalizedPath.split(/\/capture\//i);
             if (parts.length > 1) {
                 normalizedPath = '/capture/' + parts[1];
             }
        }
        // Handle Storage mount
        else if (normalizedPath.toLowerCase().includes('/storage/')) {
             const parts = normalizedPath.split(/\/storage\//i);
             if (parts.length > 1) {
                 normalizedPath = '/storage/' + parts[1];
             }
        }
        
        const img = document.createElement('img');
        img.src = normalizedPath; 
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
