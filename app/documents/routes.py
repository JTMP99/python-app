import sqlite3
import uuid
from flask import request, jsonify
from . import documents_bp

DATABASE = "legislative_documents.db"

def init_db():
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

@documents_bp.route("/", methods=["GET", "POST"])
def documents():
    if request.method == "GET":
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute("SELECT id, title, date FROM documents")
        docs = c.fetchall()
        conn.close()
        docs_list = [{"id": doc[0], "title": doc[1], "date": doc[2]} for doc in docs]
        return jsonify({"documents": docs_list})
    elif request.method == "POST":
        data = request.get_json()
        doc_id = data.get("id") or str(uuid.uuid4())
        title = data.get("title")
        content = data.get("content")
        date = data.get("date")
        if not title or not content or not date:
            return jsonify({"error": "title, content, and date are required"}), 400
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute("INSERT INTO documents (id, title, content, date) VALUES (?, ?, ?, ?)", (doc_id, title, content, date))
        conn.commit()
        conn.close()
        return jsonify({"message": "Document added", "id": doc_id}), 201

@documents_bp.route("/<doc_id>", methods=["GET"])
def get_document(doc_id):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT id, title, content, date FROM documents WHERE id=?", (doc_id,))
    doc = c.fetchone()
    conn.close()
    if not doc:
        return jsonify({"error": "Document not found"}), 404
    return jsonify({"id": doc[0], "title": doc[1], "content": doc[2], "date": doc[3]})
