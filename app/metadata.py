import sqlite3
from datetime import datetime

db_file = "stream_metadata.db"

def init_db():
    """Initialize the database and create tables."""
    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS captures (
                id TEXT PRIMARY KEY,
                stream_url TEXT,
                start_time TEXT,
                end_time TEXT,
                capture_mode TEXT,
                transcript_status TEXT DEFAULT 'pending'
            )
        ''')
        conn.commit()

def store_capture_metadata(stream_id, stream_url, start_time, capture_mode):
    """Store metadata for a new capture."""
    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO captures (id, stream_url, start_time, capture_mode)
            VALUES (?, ?, ?, ?)
        ''', (stream_id, stream_url, start_time, capture_mode))
        conn.commit()

def update_capture_end_time(stream_id, end_time):
    """Update end time when a capture stops."""
    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE captures SET end_time = ? WHERE id = ?
        ''', (end_time, stream_id))
        conn.commit()

def update_transcript_status(stream_id, status):
    """Update transcription status."""
    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE captures SET transcript_status = ? WHERE id = ?
        ''', (status, stream_id))
        conn.commit()

# Initialize DB on first run
init_db()