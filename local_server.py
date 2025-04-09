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
import requests
 
# time_pattern = r"\b(?=[2]?\d{2}[0-3]):\d{2}(:\d{2})?\b"
 
time_pattern = r"\b(?:[01]?\d|2[0-3]):([0-5]?\d)(?:\d?[][APap][Mm])?\b"
public_url = 'http://64.74.143.76:8800/generate/'
 
class SpacyRedactor:
    def __init__(self):
        self.nlp = English()
        self.matcher = Matcher(self.nlp.vocab)
        self.trigger_patterns = [
            [{"LOWER": "cvv"}],
            [{"LOWER": "cvc"}],
            [{"LOWER": "cvc2"}],
            [{"LOWER": "cvv2"}],
            [{"LOWER": "cbb"}],
            [{"LOWER": "cbb2"}],
            [{"LOWER": "cbv"}],
            [{"LOWER": "cbv2"}],
            [{"LOWER": "cv"}],
            [{"LOWER": "security"}, {"LOWER": "code"}],
            [{"LOWER": "verification"}, {"LOWER": "code"}],
            [{"LOWER": "verification"}, {"LOWER": "value"}],
            [{"LOWER": "verification"}, {"LOWER": "number"}],
            [{"LOWER": "three"}, {"LOWER": "numbers"}],
            [{"LOWER": "three"}, {"LOWER": "digits"}],
            [{"LOWER": "3"}, {"LOWER": "numbers"}],
            [{"LOWER": "3"}, {"LOWER": "digits"}],
            [{"LOWER": "reverse"}],
            [{"LOWER": "rivers"}],
            [{"LOWER": "back"}, {"LOWER": "side"}],
            [{"LOWER": "back"}, {"LOWER": "of"}, {"OP": "*"}]
        ]
 
        for idx, pattern in enumerate(self.trigger_patterns):
            self.matcher.add(f"cvv_trigger_{idx}", [pattern])
 
        self.customer_messages_searched = 0
        self.cvv_found = False
        self.redacted = False
 
 
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
            cvv_found = False
            if text["channel_tag"] == "customer":
                continue
            else:
                doc = self.nlp(text["transcript"])
                matches = self.matcher(doc)
            if len(matches) > 0:
                cvv_found = True
                cvv_index = i
 
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
                        break
 
                if customer_messages_searched >= 5:
                    redacted = True
 
        return transcripts_list, redacted
 
    def redact_list_new(self, transcripts_dict):
 
        text = transcripts_dict
 
        if text["channel_tag"] == "agent":
            doc = self.nlp(text["transcript"])
            matches = self.matcher(doc)
 
            if len(matches) > 0:
                self.cvv_found = True
                
            
        if self.cvv_found:
            if text["channel_tag"] == "customer":
                customer_text = text
        
                self.customer_messages_searched += 1
                temp_text = customer_text["transcript"]
                doc = self.nlp(customer_text["transcript"])
                num_start, num_end = self._find_numbers_after_match(doc, 0)
 
                if num_start is not None and num_end is not None:
                    self.redacted = True
                    self.cvv_found = False
                    self.customer_messages_searched = 0
                    customer_text["transcript"] = temp_text[:num_start] + "REDACTED" + temp_text[num_end:]
                    
 
                if self.customer_messages_searched >= 5:
                    self.redacted = True
        
 
                return transcripts_dict, self.redacted
        
        return transcripts_dict, self.redacted
 
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*")
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
    print(f"All connected clients: {connected_clients}")
 
@socketio.on('disconnect')
def handle_disconnect():
    client_id = request.sid
    if client_id in connected_clients:
        print(f"Client disconnected: {client_id} ({connected_clients[client_id]['type']})")
        print(f"Before disconnect - connected clients: {connected_clients}")
        del connected_clients[client_id]
        print(f"After disconnect - connected clients: {connected_clients}")
 
@socketio.on('text')
def handle_text(data):
    text = data.get('text', '')
    client_id = request.sid
    client_type = connected_clients.get(client_id, {}).get('type', 'customer')
    
    print(f"Message received from client {client_id} ({client_type})")
    print(f"Current connected clients: {connected_clients}")
    
    # Create a simple transcript structure for the redactor
    transcript = [{
            #    "timestamp": 1,
                ##"channel_tag": "agent",
                ##"transcript": "Can I have your CVV?"

                # "channel_tag": client_type,
                "role": client_type,
                "content": text
               }]
    

    # user_input = [{'role':'Agent','content':'What are the 3 numbers next to the signature strip of your card'},
    #             {'role':'Customer','content':'let me check, it is 3:52'}]

    # vpn_url = "http://172.16.0.11:8800/generate/"

    data = {"prompt": transcript, "max_tokens": 32, "temperature": 0.2}
    print(data)
    response = requests.post(public_url, json=data)
    print(response.json())
    
    # Apply redaction
    # redacted_transcript, was_redacted = redactor.redact_list_new(transcript)
    
    # Get the redacted customer text
    #redacted_text = redacted_transcript[1]["transcript"] if was_redacted else text
    redacted_text = response.json() #redacted_transcript["transcript"] if was_redacted else text
    
    # Log the redaction
    print(f"Original: {text}")
    print(f"Redacted: {redacted_text}")
    # print(f"Was redacted: {was_redacted}")
    
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
    import os
    port = int(os.environ.get("PORT", 5000))
    
    if os.environ.get('ENVIRONMENT') == 'production':
        # Production: Let Gunicorn handle SSL
        socketio.run(app, host='0.0.0.0', port=port)
    else:
        # Development:  locally
        socketio.run(app, debug=True, host='10.1.30.89', port=5000)
 