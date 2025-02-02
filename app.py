import os
import subprocess
import threading
import time
import uuid
import sqlite3
from flask import Flask, request, jsonify

# Try to import the Whisper library for transcription.
try:
    import whisper
except ImportError:
    whisper = None

app = Flask(__name__)

# In-memory registry for active stream captures.
STREAMS = {}

# Database filename for legislative documents.
DATABASE = 'legislative_documents.db'

def init_db():
    """Initialize the SQLite database for legislative documents."""
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            date TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

class StreamCapture:
    """
    Handles capturing a live stream using FFmpeg,
    and transcribing the captured audio using Whisper.
    """
    def __init__(self, stream_url):
        self.stream_url = stream_url
        self.id = str(uuid.uuid4())
        self.capture_file = f"{self.id}.mp4"
        self.transcript_file = f"{self.id}.txt"
        self.process = None
        self.capturing = False
        self.transcription_thread = None

    def start_capture(self):
        """
        Launch FFmpeg to capture the stream.
        The command uses a direct copy codec; adjust options as needed.
        """
        self.capturing = True
        command = [
            "ffmpeg",
            "-i", self.stream_url,
            "-c", "copy",
            self.capture_file
        ]
        # Start FFmpeg as a subprocess.
        self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # Start a background thread that will transcribe the capture once finished.
        self.transcription_thread = threading.Thread(target=self.run_transcription)
        self.transcription_thread.start()

    def stop_capture(self):
        """Terminate the FFmpeg process to stop capturing."""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.capturing = False

    def run_transcription(self):
        """
        Wait until capturing has finished and then run the transcription.
        This is a simple approach; in a production system you might split
        the stream into segments and transcribe continuously.
        """
        # Wait until capturing stops.
        while self.capturing:
            time.sleep(5)

        transcript = ""
        if whisper:
            # Load a Whisper model (here "base" is used; you can select another size).
            model = whisper.load_model("base")
            result = model.transcribe(self.capture_file)
            transcript = result.get("text", "")
        else:
            transcript = "Transcription not available. Install Whisper for transcription."
        
        with open(self.transcript_file, "w") as f:
            f.write(transcript)

# Flask endpoint to start a new stream capture.
@app.route('/start_capture', methods=['POST'])
def start_capture():
    data = request.get_json()
    stream_url = data.get("stream_url")
    if not stream_url:
        return jsonify({"error": "stream_url parameter is required"}), 400

    stream_capture = StreamCapture(stream_url)
    STREAMS[stream_capture.id] = stream_capture
    stream_capture.start_capture()
    return jsonify({
        "stream_id": stream_capture.id,
        "message": "Capture started"
    })

# Flask endpoint to stop an active stream capture.
@app.route('/stop_capture', methods=['POST'])
def stop_capture():
    data = request.get_json()
    stream_id = data.get("stream_id")
    if not stream_id or stream_id not in STREAMS:
        return jsonify({"error": "Valid stream_id is required"}), 400

    stream_capture = STREAMS[stream_id]
    stream_capture.stop_capture()
    return jsonify({
        "stream_id": stream_id,
        "message": "Capture stopped"
    })

# Flask endpoint to retrieve the transcript for a given stream.
@app.route('/get_transcript', methods=['GET'])
def get_transcript():
    stream_id = request.args.get("stream_id")
    if not stream_id or stream_id not in STREAMS:
        return jsonify({"error": "Valid stream_id is required"}), 400

    stream_capture = STREAMS[stream_id]
    if not os.path.exists(stream_capture.transcript_file):
        return jsonify({"message": "Transcript not available yet"}), 202

    with open(stream_capture.transcript_file, "r") as f:
        transcript = f.read()
    return jsonify({
        "stream_id": stream_id,
        "transcript": transcript
    })

# Legislative Document API Endpoints

@app.route('/documents', methods=['GET', 'POST'])
def documents():
    if request.method == 'GET':
        # Return a list of documents with basic details.
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute("SELECT id, title, date FROM documents")
        docs = c.fetchall()
        conn.close()
        docs_list = [{"id": doc[0], "title": doc[1], "date": doc[2]} for doc in docs]
        return jsonify({"documents": docs_list})
    
    elif request.method == 'POST':
        # Add a new legislative document.
        data = request.get_json()
        doc_id = data.get("id") or str(uuid.uuid4())
        title = data.get("title")
        content = data.get("content")
        date = data.get("date")
        if not title or not content or not date:
            return jsonify({"error": "title, content, and date are required"}), 400

        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute("""
            INSERT INTO documents (id, title, content, date)
            VALUES (?, ?, ?, ?)
        """, (doc_id, title, content, date))
        conn.commit()
        conn.close()
        return jsonify({"message": "Document added", "id": doc_id}), 201

# Endpoint to retrieve a specific legislative document.
@app.route('/documents/<doc_id>', methods=['GET'])
def get_document(doc_id):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT id, title, content, date FROM documents WHERE id=?", (doc_id,))
    doc = c.fetchone()
    conn.close()
    if not doc:
        return jsonify({"error": "Document not found"}), 404
    return jsonify({
        "id": doc[0],
        "title": doc[1],
        "content": doc[2],
        "date": doc[3]
    })

if __name__ == '__main__':
    # Run the Flask app on all interfaces on port 5000.
    app.run(host='0.0.0.0', port=5000)
