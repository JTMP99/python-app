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
    
    # Now we can return more detailed status info
    return jsonify(stream_capture.get_status())

@streaming_bp.route("/stop", methods=["POST"])
def stop_capture():
    data = request.get_json()
    stream_id = data.get("stream_id")
    if not stream_id or stream_id not in STREAMS:
        return jsonify({"error": "Valid stream_id is required"}), 400
    
    stream_capture = STREAMS[stream_id]
    stream_capture.stop_capture()
    
    # Return final status after stopping
    return jsonify(stream_capture.get_status())

@streaming_bp.route("/status/<stream_id>", methods=["GET"])
def get_status(stream_id):
    if stream_id not in STREAMS:
        return jsonify({"error": "Stream not found"}), 404
    
    stream_capture = STREAMS[stream_id]
    return jsonify(stream_capture.get_status())

@streaming_bp.route("/download/<stream_id>")
def download(stream_id):
    if stream_id not in STREAMS:
        return jsonify({"error": "Stream not found"}), 404
    
    stream_capture = STREAMS[stream_id]
    metadata = stream_capture.get_status()
    
    if metadata["status"] != "completed":
        return jsonify({"error": "Capture not completed"}), 400
        
    video_path = metadata["video_path"]
    if os.path.exists(video_path):
        directory = os.path.dirname(video_path)
        filename = os.path.basename(video_path)
        return send_from_directory(directory=directory, path=filename, as_attachment=True)
    
    return jsonify({"error": "File not found"}), 404