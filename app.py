from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime
from cryptography.fernet import Fernet
import os
import base64

app = Flask(__name__)
CORS(app)

# Generate or load encryption key
def get_or_create_key():
    key_file = 'secret.key'
    if os.path.exists(key_file):
        with open(key_file, 'rb') as f:
            return f.read()
    else:
        key = Fernet.generate_key()
        with open(key_file, 'wb') as f:
            f.write(key)
        return key

# Initialize encryption
ENCRYPTION_KEY = get_or_create_key()
cipher = Fernet(ENCRYPTION_KEY)

# Database configuration
if os.environ.get('DATABASE_URL'):
    database_url = os.environ.get('DATABASE_URL')
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///notes.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Helper functions for encryption/decryption
def encrypt_text(text):
    """Encrypt text and return base64 encoded string"""
    if not text:
        return ''
    encrypted = cipher.encrypt(text.encode('utf-8'))
    return base64.b64encode(encrypted).decode('utf-8')

def decrypt_text(encrypted_text):
    """Decrypt base64 encoded encrypted text"""
    if not encrypted_text:
        return ''
    try:
        encrypted = base64.b64decode(encrypted_text.encode('utf-8'))
        decrypted = cipher.decrypt(encrypted)
        return decrypted.decode('utf-8')
    except Exception as e:
        print(f"Decryption error: {e}")
        return '[Decryption Error]'

class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title_encrypted = db.Column(db.Text, nullable=False)  # Stored encrypted
    content_encrypted = db.Column(db.Text, nullable=False)  # Stored encrypted
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        """Return decrypted note data"""
        return {
            'id': self.id,
            'title': decrypt_text(self.title_encrypted),
            'content': decrypt_text(self.content_encrypted),
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        }
    
    @staticmethod
    def from_dict(data):
        """Create note from plain text data (encrypts automatically)"""
        return Note(
            title_encrypted=encrypt_text(data.get('title', 'Untitled')),
            content_encrypted=encrypt_text(data.get('content', ''))
        )

with app.app_context():
    db.create_all()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/notes', methods=['GET'])
def get_notes():
    """Get all notes (decrypted)"""
    notes = Note.query.order_by(Note.timestamp.desc()).all()
    return jsonify([note.to_dict() for note in notes])

@app.route('/api/notes', methods=['POST'])
def create_note():
    """Create new note (encrypts before storing)"""
    data = request.json
    note = Note.from_dict(data)
    db.session.add(note)
    db.session.commit()
    return jsonify(note.to_dict()), 201

@app.route('/api/notes/<int:note_id>', methods=['PUT'])
def update_note(note_id):
    """Update note (encrypts new data)"""
    note = Note.query.get_or_404(note_id)
    data = request.json
    
    # Update with encrypted data
    note.title_encrypted = encrypt_text(data.get('title', 'Untitled'))
    note.content_encrypted = encrypt_text(data.get('content', ''))
    note.timestamp = datetime.utcnow()
    
    db.session.commit()
    return jsonify(note.to_dict())

@app.route('/api/notes/<int:note_id>', methods=['DELETE'])
def delete_note(note_id):
    """Delete note"""
    note = Note.query.get_or_404(note_id)
    db.session.delete(note)
    db.session.commit()
    return '', 204

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'encryption': 'enabled',
        'notes_count': Note.query.count()
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=True)
