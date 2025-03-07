from flask import Flask
from flask_socketio import SocketIO, emit
import re
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "https://speech-to-text-six-tau.vercel.app"}})
socketio = SocketIO(app, cors_allowed_origins="https://speech-to-text-six-tau.vercel.app")

def redact_text(text):
    # CVV variations and common mispronunciations
    cvv_terms = r'(?i)(?:cvv|cvc|cvv2|cid|security code|verification code|' \
                'cbb|cbv|ccv|cdd|cdv|csv|' \
                'see vv|see v v|c v v|c vv|cv v)'  # Spelled out variations
    
    # Redact CVV patterns with context
    text = re.sub(fr'(?i){cvv_terms}.*?\d{{3,4}}', '[CVV]', text)  # CVV followed by numbers
    text = re.sub(fr'(?i)\d{{3,4}}.*?{cvv_terms}', '[CVV]', text)  # Numbers followed by CVV
    text = re.sub(r'(?i)(?:code|number|num).*?\d{3,4}', '[CVV]', text)  # Generic "code" + numbers
    text = re.sub(r'\b\d{3,4}\b', '[CVV]', text)  # Standalone 3-4 digits
    
    # Redact credit card numbers but preserve last 4 digits
    card_patterns = [
        (r'\b[3-6]\d{3}[\s-]?\d{4}[\s-]?\d{4}[\s-]?(\d{4})\b', r'[CARD ENDING IN \1]'),  # Standard 16-digit cards
        (r'\b3[47]\d{9}(\d{4})\b', r'[AMEX ENDING IN \1]'),  # American Express
        (r'\b(?:4\d{8}(\d{4})(?:\d{3})?)\b', r'[VISA ENDING IN \1]'),  # Visa
        (r'\b(?:5[1-5]\d{10}(\d{4}))\b', r'[MC ENDING IN \1]'),  # MasterCard
        (r'(?i)(?:card|credit|debit).*?(\d{4})\b', r'[CARD ENDING IN \1]'),  # Card mentions with numbers
        (r'(?i)(?:visa|mastercard|amex).*?(\d{4})\b', r'[CARD ENDING IN \1]')  # Card brand mentions
    ]
    for pattern, replacement in card_patterns:
        text = re.sub(pattern, replacement, text)
    
    # Redact email addresses with variations
    email_patterns = [
        r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',  # Standard email
        r'(?i)(?:email|e-mail|mail).*?@.*?\.[a-z]{2,}',  # Spoken email addresses
        r'(?i)(?:at|@).*?(?:dot|\.)\s*[a-z]{2,}'  # Spelled out email addresses
    ]
    for pattern in email_patterns:
        text = re.sub(pattern, '[EMAIL]', text)
    
    # Redact phone numbers with variations
    phone_patterns = [
        r'(\+\d{1,2}\s?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}',  # Standard format
        r'(?:\d{3}[-.\s]?){2}\d{4}',  # XXX-XXX-XXXX
        r'(?i)(?:phone|call|tel|telephone).*?\d{3}.*?\d{3}.*?\d{4}',  # Spoken phone numbers
        r'\b\d{10}\b'  # Plain 10 digits
    ]
    for pattern in phone_patterns:
        text = re.sub(pattern, '[PHONE]', text)
    
    return text


@socketio.on('text')
def handle_text(data):
    text = data.get('text', '')
    redacted = redact_text(text)
    emit('redacted_text', {'redacted_text': redacted})

if __name__ == '__main__':
    socketio.run(app, debug=True)
