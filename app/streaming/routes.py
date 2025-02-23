# app/streaming/routes.py
from flask import request, jsonify, send_from_directory, current_app, send_file
from app.streaming import streaming_bp  # Import the blueprint
from app.streaming.capture import StreamCapture  # Import StreamCapture class
import os
import logging


@streaming_bp.route("/start", methods=["POST"])
def start_capture():
    """Start a new stream capture (now synchronous)."""
    data = request.get_json()
    stream_url = data.get("stream_url")

    if not stream_url:
        return jsonify({"error": "stream_url parameter is required"}), 400

    # Create and start the StreamCapture directly
    stream_capture = StreamCapture(stream_url)
    current_app.STREAMS[stream_capture.id] = stream_capture  # Add to STREAMS
    try:
        stream_capture.start_capture()
    except Exception as e:
        #Make sure to catch and return errors.
        logging.exception(f"Error starting stream capture: {e}")
        return jsonify({"error": str(e)}), 500

    # Return stream data
    return jsonify(stream_capture.get_status())



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