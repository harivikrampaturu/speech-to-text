from spacy.lang.en import English
from spacy.matcher import Matcher
from typing import List, Tuple
import re
from flask import Flask, request
from flask_socketio import SocketIO, emit
import json

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
            elif number_count> 0 and len(token.text.strip()) > 15:
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

        for i, text in enumerate(transcripts_list):
            if text["channel_tag"] == "customer":
                continue
            else:
                doc = self.nlp(text["transcript"])
                matches = self.matcher(doc)
            if len(matches) > 0:
                cvv_found = True
                cvv_index = i

                break

        if cvv_found:
            customer_messages_searched = 0
            for customer_text in transcripts_list[cvv_index:]:
                if customer_text["channel_tag"] == "agent":
                    continue
                customer_messages_searched += 1
                text = customer_text["transcript"]
                doc = self.nlp(customer_text["transcript"])
                num_start, num_end = self._find_numbers_after_match(doc, 0)

                if num_start is not None and num_end is not None:
                    redacted = True
                    customer_text["transcript"] = text[:num_start] + "REDACTED" + text[num_end:]

            if customer_messages_searched >= 5:
                redacted = True

        return transcripts_list, redacted

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")
redactor = SpacyRedactor()

# Track connected clients
connected_clients = {}

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
            "transcript": "Can I have your CVV?"
        },
        {
            "timestamp": 2,
            "channel_tag": "customer",
            "transcript": text
        }
    ]
    
    # Apply redaction
    redacted_transcript, was_redacted = redactor.redact_list(transcript)
    
    # Get the redacted customer text
    redacted_text = redacted_transcript[1]["transcript"] if was_redacted else text
    
    # Log the redaction
    print(f"Original: {text}")
    print(f"Redacted: {redacted_text}")
    print(f"Was redacted: {was_redacted}")
    
    # Send back to originating client
    emit('redacted_text', {'redacted_text': redacted_text})
    
    # Broadcast to all clients (except sender)
    emit('chat_message', {
        'sender_type': client_type,
        'message': f"{client_type}: {redacted_text}"    
    }, broadcast=True, include_self=False)

if __name__ == '__main__':
    # Keep the existing test code if needed for debugging
    # ... existing test code ...
    
    # Start the Flask-SocketIO server
    socketio.run(app, debug=True, host='10.1.30.58', port=5000)