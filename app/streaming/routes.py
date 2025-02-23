from flask import request, jsonify, send_from_directory, current_app, send_file
from app.streaming import streaming_bp
from app.streaming.capture import StreamCapture
from app.services.capture_service import CaptureService, CaptureNotFoundError
import os
import logging
import threading

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
                CaptureService.update_capture_status(capture.id, "failed", str(e))
            
        thread = threading.Thread(target=capture_thread)
        thread.daemon = True
        thread.start()

        # Return immediately with ID
        return jsonify({
            "id": str(capture.id),
            "status": "initialized",
            "stream_url": stream_url
        }), 202

    except Exception as e:
        current_app.logger.exception("Error starting capture")
        return jsonify({"error": str(e)}), 500

@streaming_bp.route("/status/<capture_id>", methods=["GET"])
def get_status_endpoint(capture_id):
    """Get capture status from database"""
    try:
        capture = CaptureService.get_capture_with_metrics(capture_id)
        if not capture:
            return jsonify({"error": "Capture not found"}), 404
        return jsonify(capture)
    except Exception as e:
        current_app.logger.exception("Error getting status")
        return jsonify({"error": str(e)}), 500

@streaming_bp.route("/stop/<capture_id>", methods=["POST"])
def stop_capture(capture_id):
    """Stop an active capture"""
    try:
        # First check if capture exists
        capture_data = CaptureService.get_capture(capture_id)
        if not capture_data:
            return jsonify({"error": "Capture not found"}), 404
            
        # Create new StreamCapture instance from existing data
        capture = StreamCapture(capture_data.stream_url, capture_id=capture_id)
        capture.stop_capture()
        
        # Get final status
        final_status = CaptureService.get_capture_with_metrics(capture_id)
        return jsonify(final_status)
    except CaptureNotFoundError:
        return jsonify({"error": "Capture not found"}), 404
    except Exception as e:
        current_app.logger.exception("Error stopping capture")
        return jsonify({"error": str(e)}), 500

@streaming_bp.route("/debug/<capture_id>")
def get_debug_info(capture_id):
    """Get comprehensive debug information"""
    try:
        capture = CaptureService.get_capture_with_metrics(capture_id)
        if not capture:
            return jsonify({"error": "Capture not found"}), 404

        debug_info = {
            "id": capture_id,
            "stream_url": capture.get("stream_url"),
            "status": capture.get("status"),
            "duration": capture.get("duration"),
            "errors": capture.get("errors", []),
            "capture_metadata": capture.get("capture_metadata", {}),
            "debug_screenshots": capture.get("screenshot_paths", []),
            "start_time": capture.get("start_time"),
            "end_time": capture.get("end_time"),
            "recent_metrics": capture.get("recent_metrics", [])
        }

        return jsonify(debug_info)
    except Exception as e:
        current_app.logger.exception("Error getting debug info")
        return jsonify({"error": str(e)}), 500

@streaming_bp.route("/debug/<capture_id>/screenshots/<timestamp>")
def get_screenshot(capture_id, timestamp):
    """Get a specific screenshot"""
    try:
        capture = CaptureService.get_capture(capture_id)
        if not capture:
            return jsonify({"error": "Capture not found"}), 404

        debug_dir = os.path.join("/app/captures", capture_id, "debug")
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
        capture = CaptureService.get_capture(capture_id)
        if not capture:
            return jsonify({"error": "Capture not found"}), 404

        if capture.status != "completed":
            return jsonify({"error": "Capture not completed"}), 400

        video_path = capture.video_path
        if not video_path or not os.path.exists(video_path):
            return jsonify({"error": "Video file not found"}), 404

        directory = os.path.dirname(video_path)
        filename = os.path.basename(video_path)
        return send_from_directory(directory=directory, path=filename, as_attachment=True)
    except Exception as e:
        current_app.logger.exception("Error downloading video")
        return jsonify({"error": str(e)}), 500