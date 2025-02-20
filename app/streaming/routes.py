from flask import request, jsonify, send_from_directory, current_app
from . import streaming_bp
from .capture import StreamCapture
import os

# In-memory store for active stream captures.
STREAMS = {}

@streaming_bp.route("/start", methods=["POST"])
def start_capture():
    data = request.get_json()
    stream_url = data.get("stream_url")
    if not stream_url:
        return jsonify({"error": "stream_url parameter is required"}), 400
    stream_capture = StreamCapture(stream_url)
    STREAMS[stream_capture.id] = stream_capture
    stream_capture.start_capture()
    return jsonify({"stream_id": stream_capture.id, "message": "Capture started"})

@streaming_bp.route("/stop", methods=["POST"])
def stop_capture():
    data = request.get_json()
    stream_id = data.get("stream_id")
    if not stream_id or stream_id not in STREAMS:
        return jsonify({"error": "Valid stream_id is required"}), 400
    stream_capture = STREAMS[stream_id]
    stream_capture.stop_capture()
    return jsonify({"stream_id": stream_id, "message": "Capture stopped"})

@streaming_bp.route("/transcript", methods=["GET"])
def get_transcript():
    stream_id = request.args.get("stream_id")
    if not stream_id or stream_id not in STREAMS:
        return jsonify({"error": "Valid stream_id is required"}), 400
    stream_capture = STREAMS[stream_id]
    if not os.path.exists(stream_capture.transcript_file):
        return jsonify({"message": "Transcript not available yet"}), 202
    with open(stream_capture.transcript_file, "r") as f:
        transcript = f.read()
    return jsonify({"stream_id": stream_id, "transcript": transcript})

@streaming_bp.route("/download/<stream_id>")
def download(stream_id):
    stream_capture = STREAMS.get(stream_id)
    if stream_capture and os.path.exists(stream_capture.capture_file):
        return send_from_directory(directory=current_app.root_path, path=stream_capture.capture_file, as_attachment=True)
    return jsonify({"error": "File not found"}), 404
