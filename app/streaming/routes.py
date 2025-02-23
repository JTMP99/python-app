# app/streaming/routes.py
from flask import request, jsonify, send_from_directory, current_app, send_file
from app.streaming import streaming_bp
from app.streaming.capture import StreamCapture
import os
import logging
import json
import threading

def get_capture_path(capture_id):
    return os.path.join("/app/captures", capture_id)

def get_capture_status(capture_id):
    """Get status from filesystem"""
    capture_path = get_capture_path(capture_id)
    metadata_file = os.path.join(capture_path, "metadata.json")
    if os.path.exists(metadata_file):
        try:
            with open(metadata_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            current_app.logger.error(f"Error reading metadata: {e}")
    return None

@streaming_bp.route("/start", methods=["POST"])
def start_capture():
    """Initialize capture and return immediately"""
    try:
        data = request.get_json()
        stream_url = data.get("stream_url")
        if not stream_url:
            return jsonify({"error": "stream_url required"}), 400

        # Create capture object
        capture = StreamCapture(stream_url)
        current_app.logger.info(f"Created capture {capture.id} for {stream_url}")
        
        # Start capture in background thread
        def capture_thread():
            try:
                capture.start_capture()
            except Exception as e:
                current_app.logger.exception(f"Error in capture thread: {e}")
                capture._update_status("failed", str(e))
            
        thread = threading.Thread(target=capture_thread)
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
def get_status_endpoint(capture_id):
    """Get capture status"""
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
        
        final_status = get_capture_status(capture_id)
        return jsonify(final_status)
    except Exception as e:
        current_app.logger.exception("Error stopping capture")
        return jsonify({"error": str(e)}), 500

@streaming_bp.route("/debug/<capture_id>")
def get_debug_info(capture_id):
    """Get comprehensive debug information"""
    try:
        status = get_capture_status(capture_id)
        if not status:
            return jsonify({"error": "Capture not found"}), 404

        debug_info = {
            "id": capture_id,
            "stream_url": status["stream_url"],
            "status": status["status"],
            "duration": status.get("duration"),
            "errors": status.get("errors", []),
            "page_analysis": status.get("page_analysis", {}),
            "screenshots": status.get("debug_screenshots", []),
            "start_time": status.get("start_time"),
            "end_time": status.get("end_time")
        }

        return jsonify(debug_info)
    except Exception as e:
        current_app.logger.exception("Error getting debug info")
        return jsonify({"error": str(e)}), 500

@streaming_bp.route("/debug/<capture_id>/screenshots/<timestamp>")
def get_screenshot(capture_id, timestamp):
    """Get a specific screenshot"""
    try:
        debug_dir = os.path.join(get_capture_path(capture_id), "debug")
        if not os.path.exists(debug_dir):
            return jsonify({"error": "Debug directory not found"}), 404

        for filename in os.listdir(debug_dir):
            if timestamp in filename and filename.endswith('.png'):
                return send_file(
                    os.path.join(debug_dir, filename),
                    mimetype='image/png'
                )

        return jsonify({"error": "Screenshot not found"}), 404
    except Exception as e:
        current_app.logger.exception("Error getting screenshot")
        return jsonify({"error": str(e)}), 500

@streaming_bp.route("/download/<capture_id>")
def download(capture_id):
    """Download captured video"""
    try:
        status = get_capture_status(capture_id)
        if not status:
            return jsonify({"error": "Capture not found"}), 404

        if status["status"] != "completed":
            return jsonify({"error": "Capture not completed"}), 400

        video_path = status.get("video_path")
        if not video_path or not os.path.exists(video_path):
            return jsonify({"error": "Video file not found"}), 404

        directory = os.path.dirname(video_path)
        filename = os.path.basename(video_path)
        return send_from_directory(directory=directory, path=filename, as_attachment=True)
    except Exception as e:
        current_app.logger.exception("Error downloading video")
        return jsonify({"error": str(e)}), 500