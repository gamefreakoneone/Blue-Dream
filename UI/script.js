const chatContainer = document.getElementById('chat-container');
const chatForm = document.getElementById('chat-form');
const userInput = document.getElementById('user-input');
const statusIndicator = document.querySelector('.status-indicator');

// Store the API URL - in this case relative
const API_URL = '/query';

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
            body: JSON.stringify({ query: query })
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
