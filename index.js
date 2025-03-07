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

// Display client type
clientTypeDisplay.textContent = `Connected as: ${clientType}`;

// Connect to your IP address
// https://speech-to-text-wetd.onrender.com - vikram
// https://speech-to-text-5lxk.onrender.com' - murthy
const socket = io('https://speech-to-text-wetd.onrender.com', {
    reconnection: true,
    reconnectionAttempts: Infinity,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000,
    timeout: 20000,
    query: { type: clientType } // Send client type with connection
});

socket.on('connect', () => {
    console.log('Connected to server');
});

socket.on('disconnect', () => {
    console.log('Disconnected from server, attempting to reconnect...');
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

// Display chat messages
socket.on('chat_message', (data) => {
    // Display the message in the UI
    console.log(`${data.sender_type}: ${data.message}`);
    
    // Add message to chat container
    addMessageToChat(data.sender_type, data.message);
});

// Function to add message to chat
function addMessageToChat(senderType, message) {
    const messageEl = document.createElement('div');
    messageEl.className = `message ${senderType}`;
    messageEl.textContent = message;
    chatContainer.appendChild(messageEl);
    
    // Scroll to bottom of chat
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
            // Send message to server once
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
    recognition.start();
    startBtn.disabled = true;
    stopBtn.disabled = false;
});

stopBtn.addEventListener('click', () => {
    recognition.stop();
    startBtn.disabled = false;
    stopBtn.disabled = true;
});
