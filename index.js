let recognition;
const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const originalText = document.getElementById('originalText');
const redactedText = document.getElementById('redactedText');

// Initialize Socket.IO with reconnection options and client type
const urlParams = new URLSearchParams(window.location.search);
const clientType = urlParams.get('type') || 'customer'; // Default to customer if not specified

// New chat UI elements
const chatContainer = document.getElementById('chatContainer');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const clientTypeDisplay = document.getElementById('clientTypeDisplay');
const SOCKET_URL = 'http://10.1.30.89:5000'; // 'https://speech-to-text-wetd.onrender.com';

// Display client type
clientTypeDisplay.textContent = `Connected as: ${clientType}`;

// Add connection status indicator
const connectionStatus = document.createElement('div');
connectionStatus.id = 'connectionStatus';
clientTypeDisplay.parentNode.insertBefore(connectionStatus, clientTypeDisplay.nextSibling);

function updateConnectionStatus(status) {
    connectionStatus.textContent = `Status: ${status}`;
    connectionStatus.className = `status-${status.toLowerCase()}`;
}

// Connect to your IP address
// https://speech-to-text-wetd.onrender.com - vikram
// https://speech-to-text-5lxk.onrender.com' - murthy
const socket = io(SOCKET_URL, {
    reconnection: true,
    reconnectionAttempts: Infinity,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000,
    timeout: 20000,
    query: { type: clientType } // Send client type with connection
});

// Add a flag to track if we should maintain connection
let maintainConnection = true;

// Move all socket event setup to this function
function setupSocketListeners() {
    socket.on('connect', () => {
        console.log('Connected to server');
        updateConnectionStatus('Connected');
    });

    socket.on('disconnect', () => {
        console.log('Disconnected from server, attempting to reconnect...');
        updateConnectionStatus('Disconnecting');
        if (maintainConnection) {
            reconnectSocket();
        }
    });

    socket.on('reconnect', (attemptNumber) => {
        console.log('Reconnected to server after', attemptNumber, 'attempts');
    });

    socket.on('reconnect_error', (error) => {
        console.error('Reconnection error:', error);
    });

    socket.on('redacted_text', (data) => {
        redactedText.value = data.redacted_text;
    });

    socket.on('chat_message', (data) => {
        console.log(`${data.sender_type}: ${data.message}`);
        addMessageToChat(data.sender_type, data.message);
    });
}

// Call setupSocketListeners initially
setupSocketListeners();

// Function to add message to chat
function addMessageToChat(senderType, message) {
    const messageEl = document.createElement('div');
    messageEl.className = `message ${senderType}`;
    
    const timestamp = new Date().toLocaleTimeString();
    messageEl.innerHTML = `
        <span class="message-time">${timestamp}</span>
        <span class="message-text">${message}</span>
    `;
    
    chatContainer.appendChild(messageEl);
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

// Send chat message
sendBtn.addEventListener('click', sendMessage);
messageInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        sendMessage();
    }
});

function sendMessage() {
    const message = messageInput.value.trim();
    if (message) {
        // Send message to server
        socket.emit('text', { 
            text: message,
            clientType: clientType
        });
        
        // Add message to own chat (optionally, you can wait for server response)
        addMessageToChat(clientType, message);
        
        // Clear input
        messageInput.value = '';
    }
}

// Initialize speech recognition
if ('webkitSpeechRecognition' in window) {
    recognition = new webkitSpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-US';
    recognition.maxAlternatives = 1;

    recognition.onresult = (event) => {
        let interim_transcript = '';
        let final_transcript = '';
        
        for (let i = event.resultIndex; i < event.results.length; i++) {
            const transcript = event.results[i][0].transcript;
            if (event.results[i].isFinal) {
                final_transcript += transcript;
            } else {
                interim_transcript += transcript;
            }
        }
        
        // Update original text immediately with both interim and final results
        originalText.value = final_transcript || interim_transcript;
        
        // Only send final transcripts to server for redaction
        if (final_transcript) {
            // Chat message to server
            socket.emit('text', { 
                text: final_transcript,
                clientType: clientType
            });
             addMessageToChat(clientType, final_transcript);
        }
    };

    recognition.onerror = (event) => {
        console.error('Speech recognition error:', event.error);
        if (event.error === 'network') {
            recognition.stop();
            setTimeout(() => recognition.start(), 1000);
        }
    };

    recognition.onend = () => {
        if (!stopBtn.disabled) {
            recognition.start();
        }
    };
} else {
    alert('Speech recognition is not supported in this browser.');
}

// Event listeners for buttons
startBtn.addEventListener('click', () => {
    maintainConnection = true;
    if (!socket.connected) {
        reconnectSocket();
    }
    recognition.start();
    startBtn.disabled = true;
    stopBtn.disabled = false;
});

stopBtn.addEventListener('click', () => {
    recognition.stop();
    startBtn.disabled = false;
    stopBtn.disabled = true;
    maintainConnection = false;
    socket.disconnect();
});

// Add reconnection function
function reconnectSocket() {
    if (!maintainConnection) return;
    
    if (!socket.connected) {
        socket.connect();
    }
}
