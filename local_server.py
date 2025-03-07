from spacy.lang.en import English
from spacy.matcher import Matcher
from typing import List, Tuple
import re
from flask import Flask, request
from flask_socketio import SocketIO, emit
import json
from transformers import pipeline

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
socketio = SocketIO(app, cors_allowed_origins=["https://speech-to-text-six-tau.vercel.app", 
                                             "http://localhost:5000",
                                             "https://speech-to-text-six-tau.vercel.app"])
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

def redact_text(text):
    # CVV variations and common mispronunciations
    cvv_terms = r'(?i)(?:cvv|cvc|cvv2|cid|security code|verification code|' \
                'cbb|cbv|ccv|cdd|cdv|csv|' \
                'see vv|see v v|c v v|c vv|cv v)'  # Spelled out variations
    
    # ... existing code ...
    
    return text

def enhance_redaction(text):
    classifier = pipeline("ner", model="dlb/pii-bert-base-uncased")
    results = classifier(text)
    # Process results and apply additional redaction
    return text

@socketio.on('text')
def handle_text(data):
    text = data.get('text', '')
    client_type = data.get('clientType', 'unknown')
    redacted = redact_text(text)
    
    # Send redacted text back to the client who sent it
    emit('redacted_text', {'redacted_text': redacted})
    
    # Broadcast chat message to all clients
    emit('chat_message', {
        'message': redacted,
        'sender_type': client_type
    }, broadcast=True)

if __name__ == '__main__':
    import os
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port)