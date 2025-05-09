from gevent import monkey
monkey.patch_all()

from spacy.lang.en import English
from spacy.matcher import Matcher
from typing import List, Tuple
import re
from flask import Flask, request
from flask_socketio import SocketIO, emit
import json
from flask_cors import CORS

time_pattern = r"\b(?=[2]?\d{2}[0-3]):\d{2}(:\d{2})?\b"

class SpacyRedactor:
    def __init__(self):
        self.nlp = English()
        self.matcher = Matcher(self.nlp.vocab)
        self.trigger_patterns = [
            [{"LOWER": "cvv"}],
            [{"LOWER": "cvc"}],
            [{"LOWER": "cvc2"}],
            [{"LOWER": "cvv2"}],
            [{"LOWER": "security"}, {"LOWER": "code"}],
            [{"LOWER": "verification"}, {"LOWER": "code"}],
            [{"LOWER": "verification"}, {"LOWER": "value"}],
            [{"LOWER": "three"}, {"LOWER": "digits"}],
            [{"LOWER": "three"}, {"LOWER": "numbers"}],
            [{"LOWER": "back"}, {"LOWER": "of"}, {"OP": "*"}, {"LOWER": "card"}]
        ]

        for idx, pattern in enumerate(self.trigger_patterns):
            self.matcher.add(f"cvv_trigger_{idx}", [pattern])

    def _find_numbers_after_match(self, doc, match_end: int) -> Tuple[int, int]:
        number_count = 0
        start_idx = None
        last_num_end = None
        return_tuple = (None, None)

        for token in doc[match_end:]:
            is_number = token.like_num or token.text.isdigit()

            if is_number:
                if number_count == 0:
                    start_idx = token.idx
                if token.text.isdigit():
                    number_count += len(token.text)
                elif token.like_num:
                    number_count += 1
                last_num_end = token.idx + len(token.text)

                if number_count >= 3:
                    return_tuple = (start_idx, last_num_end)
            elif number_count > 0 and len(token.text.strip()) > 15:
                number_count = 0
                start_idx = None
            else:
                for match in re.finditer(time_pattern, token.text):
                    start_idx = token.idx
                    last_num_end = token.idx + len(token.text)
                    return_tuple = (start_idx, last_num_end)

        return return_tuple

    def collect_texts(self, texts):
        collect_texts = []
        current_speaker = None
        current_timestamp = None
        current_text = []

        for text in texts:
            next_text = text['transcript']
            next_speaker = text['channel_tag']
            next_timestamp = text['timestamp']
            if next_speaker != current_speaker:
                if current_speaker is not None:
                    collect_texts.append(
                        {
                            "timestamp": current_timestamp,
                            "channel_tag": current_speaker,
                            "transcript": "\n".join(current_text)
                        }
                    )
                current_speaker = next_speaker
                current_timestamp = next_timestamp
                current_text = [next_text]
            else:
                current_text.append(next_text)

        if current_speaker is not None:
            collect_texts.append({
                "timestamp": current_timestamp,
                "channel_tag": current_speaker,
                "transcript": "\n".join(current_text)
            })
        return collect_texts

    def redact_list(self, transcripts_list):
        cvv_found = False
        redacted = False
        cvv_index = -1

        # First pass: look for CVV triggers in agent messages
        for i, text in enumerate(transcripts_list):
            if text["channel_tag"] == "agent":
                doc = self.nlp(text["transcript"].lower())  # Convert to lowercase for matching
                matches = self.matcher(doc)
                if matches:  # If any CVV trigger is found
                    cvv_found = True
                    cvv_index = i
                    break

        # Second pass: look for numbers in customer messages after CVV trigger
        if cvv_found:
            for text in transcripts_list[cvv_index:]:
                if text["channel_tag"] == "customer":
                    doc = self.nlp(text["transcript"])
                    # Look for 3-4 digit numbers
                    for token in doc:
                        if token.text.isdigit() and 3 <= len(token.text) <= 4:
                            redacted = True
                            text["transcript"] = text["transcript"].replace(token.text, "REDACTED")
                        # Also check for numbers in text like "567" or "my CVV is 567"
                        matches = re.findall(r'\b\d{3,4}\b', text["transcript"])
                        if matches:
                            redacted = True
                            for match in matches:
                                text["transcript"] = text["transcript"].replace(match, "REDACTED")

        return transcripts_list, redacted

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": [
    "https://speech-to-text-six-tau.vercel.app",
    "http://localhost:5000",
    "https://localhost:5000"
]}})
socketio = SocketIO(app, cors_allowed_origins=[
    "https://speech-to-text-six-tau.vercel.app",
    "http://localhost:5000",
    "https://localhost:5000"
])
redactor = SpacyRedactor()

# Track connected clients
connected_clients = {}

@app.route('/')
def index():
    return 'Server is running'

@socketio.on('connect')
def handle_connect():
    client_id = request.sid
    client_type = request.args.get('type', 'customer')  # Default to customer
    connected_clients[client_id] = {
        'type': client_type,
        'id': client_id
    }
    print(f"Client connected: {client_id} as {client_type}")

@socketio.on('disconnect')
def handle_disconnect():
    client_id = request.sid
    if client_id in connected_clients:
        print(f"Client disconnected: {client_id} ({connected_clients[client_id]['type']})")
        del connected_clients[client_id]

def redact_text(text):
    # Use the existing SpacyRedactor instance
    global redactor
    texts = [{
        'transcript': text,
        'channel_tag': 'agent',  # Assume text is from agent to trigger CVV detection
        'timestamp': ''
    }]
    
    # Use the existing redaction logic
    redacted_texts, was_redacted = redactor.redact_list(texts)
    return redacted_texts[0]['transcript']

@socketio.on('text')
def handle_text(data):
    text = data.get('text', '')
    client_id = request.sid
    client_type = connected_clients.get(client_id, {}).get('type', 'customer')
    
    # Create a simple transcript structure for the redactor
    transcript = [
        {
            "timestamp": 1,
            "channel_tag": "agent",
            "transcript": "Can I have your CVV?"  # Mock trigger
        },
        {
            "timestamp": 2,
            "channel_tag": client_type,
            "transcript": text
        }
    ]
    
    # Apply redaction
    redacted_transcript, was_redacted = redactor.redact_list(transcript)
    
    # Get the redacted text
    redacted_text = redacted_transcript[1]["transcript"] if was_redacted else text
    
    # Log for debugging
    print(f"Original: {text}")
    print(f"Redacted: {redacted_text}")
    print(f"Was redacted: {was_redacted}")
    
    # Send back to originating client
    emit('redacted_text', {'redacted_text': redacted_text})
    
    # Broadcast to all clients
    emit('chat_message', {
        'message': redacted_text,
        'sender_type': client_type,
        'timestamp': data.get('timestamp', '')
    }, broadcast=True)

if __name__ == '__main__':
    import os
    port = int(os.environ.get("PORT", 5000))
    
    if os.environ.get('ENVIRONMENT') == 'production':
        # Production: Let Gunicorn handle SSL
        socketio.run(app, host='0.0.0.0', port=port)
    else:
        # Development: Use SSL locally
        from OpenSSL import SSL
        context = SSL.Context(SSL.TLSv1_2_METHOD)
        context.use_privatekey_file('server.key')
        context.use_certificate_file('server.crt')
        socketio.run(app, 
                    host='0.0.0.0', 
                    port=port,
                    ssl_context=(context.get_certificate(), context.get_privatekey()))