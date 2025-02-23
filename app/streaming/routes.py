# app/streaming/routes.py
from flask import request, jsonify, send_from_directory, current_app, send_file
from app.streaming import streaming_bp  # Import the blueprint
from app.streaming.capture import StreamCapture  # Import StreamCapture class
import os
import logging
from app.services.capture_service import CaptureService
import threading


# Use file-based state tracking instead of memory
def get_capture_path(capture_id):
    return os.path.join("/app/captures", capture_id)

def get_capture_status(capture_id):
    """Get status from filesystem instead of memory"""
    capture_path = get_capture_path(capture_id)
    metadata_file = os.path.join(capture_path, "metadata.json")
    if os.path.exists(metadata_file):
        with open(metadata_file, 'r') as f:
            return json.load(f)
    return None

@streaming_bp.route("/start", methods=["POST"])
def start_capture():
    """Initialize capture and return immediately"""
    try:
        data = request.get_json()
        stream_url = data.get("stream_url")
        if not stream_url:
            return jsonify({"error": "stream_url required"}), 400

        # Just create the capture object
        capture = StreamCapture(stream_url)
        
        # Start setup in background thread
        def setup_capture():
            capture.initialize()  # New method for staged setup
            
        thread = threading.Thread(target=setup_capture)
        thread.daemon = True
        thread.start()

        # Return immediately with ID
        return jsonify({
            "id": capture.id,
            "status": "initializing",
            "stream_url": stream_url
        }), 202

    except Exception as e:
        current_app.logger.exception("Error starting capture")
        return jsonify({"error": str(e)}), 500

@streaming_bp.route("/status/<capture_id>", methods=["GET"])
def get_status(capture_id):
    """Get status from filesystem"""
    try:
        status = get_capture_status(capture_id)
        if not status:
            return jsonify({"error": "Capture not found"}), 404
        return jsonify(status)
    except Exception as e:
        current_app.logger.exception("Error getting status")
        return jsonify({"error": str(e)}), 500

@streaming_bp.route("/stop/<capture_id>", methods=["POST"])
def stop_capture(capture_id):
    """Stop an active capture"""
    try:
        status = get_capture_status(capture_id)
        if not status:
            return jsonify({"error": "Capture not found"}), 404
            
        # Create new StreamCapture instance from stored metadata
        capture = StreamCapture.from_metadata(status)
        capture.stop_capture()
        
        return jsonify(get_capture_status(capture_id))
    except Exception as e:
        current_app.logger.exception("Error stopping capture")
        return jsonify({"error": str(e)}), 500


@streaming_bp.route("/stop", methods=["POST"])
def stop_capture():
    """Stop an existing stream capture."""
    data = request.get_json()
    stream_id = data.get("stream_id")

    if not stream_id:
        return jsonify({"error": "stream_id parameter is required"}), 400

    if stream_id in current_app.STREAMS:
        stream_capture = current_app.STREAMS[stream_id]
        current_app.logger.info(f"Stopping capture for stream ID: {stream_id}")
        stream_capture.stop_capture()
        # Remove from active streams
        del current_app.STREAMS[stream_id]
        return jsonify({"status": "stopped"})
    else:
        current_app.logger.error(f"Invalid stream_id: {stream_id}")
        return jsonify({"error": "Stream not found or already stopped"}), 404


@streaming_bp.route("/status/<stream_id>", methods=["GET"])
def get_status(stream_id):
    """Get the status of a specific stream capture."""
    current_app.logger.info(f"Status request for stream_id: {stream_id}")

    if stream_id not in current_app.STREAMS:
        current_app.logger.error(f"Stream not found: {stream_id}")
        return jsonify({"error": "Stream not found"}), 404

    stream_capture = current_app.STREAMS[stream_id]
    status = stream_capture.get_status()
    current_app.logger.info(f"Returning status: {status}")
    return jsonify(status)


@streaming_bp.route("/debug/<stream_id>")
def get_debug_info(stream_id):
    """Get comprehensive debug information for a capture."""
    if stream_id not in current_app.STREAMS:
        return jsonify({"error": "Stream not found"}), 404

    stream_capture = current_app.STREAMS[stream_id]
    metadata = stream_capture.get_status()

    debug_info = {
        "id": stream_id,
        "stream_url": metadata["stream_url"],
        "status": metadata["status"],
        "duration": metadata["duration"],
        "errors": metadata["errors"],
        "page_analysis": metadata.get("page_analysis", {}),
        "screenshots": metadata.get("debug_screenshots", []),
        "start_time": metadata["start_time"],
        "end_time": metadata["end_time"]
    }

    return jsonify(debug_info)


@streaming_bp.route("/debug/<stream_id>/screenshots/<timestamp>")
def get_screenshot(stream_id, timestamp):
    """Retrieve a specific debug screenshot."""

    if stream_id not in current_app.STREAMS:
        return jsonify({"error": "Stream not found"}), 404

    stream_capture = current_app.STREAMS[stream_id]
    debug_dir = f"/app/captures/{stream_id}/debug"

    for filename in os.listdir(debug_dir):
        if timestamp in filename and filename.endswith('.png'):
            return send_file(
                os.path.join(debug_dir, filename),
                mimetype='image/png'
            )

    return jsonify({"error": "Screenshot not found"}), 404


@streaming_bp.route("/download/<stream_id>")
def download(stream_id):
    """Download the captured video for a completed capture."""
    if stream_id not in current_app.STREAMS:
        return jsonify({"error": "Stream not found"}), 404

    stream_capture = current_app.STREAMS[stream_id]
    metadata = stream_capture.get_status()
    if metadata["status"] != "completed":
        return jsonify({"error": "Capture not completed"}), 400
    video_path = metadata["video_path"]
    if os.path.exists(video_path):
        directory = os.path.dirname(video_path)
        filename = os.path.basename(video_path)
        return send_from_directory(directory=directory, path=filename, as_attachment=True)
    return jsonify({"error": "File not found"}), 404