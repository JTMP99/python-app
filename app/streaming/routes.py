from flask import request, jsonify, send_from_directory, current_app, send_file
from . import streaming_bp
from .capture import StreamCapture
import os
import logging

# In-memory store for active stream captures.
STREAMS = {}

@streaming_bp.route("/start", methods=["POST"])
def start_capture():
    """Start a new stream capture. Expects JSON with 'stream_url'."""
    try:
        current_app.logger.debug(f"Headers: {dict(request.headers)}")
        current_app.logger.debug(f"Raw data: {request.get_data()}")
        current_app.logger.debug(f"Form data: {request.form}")
        current_app.logger.debug(f"Files: {request.files}")
        
        try:
            data = request.get_json()
            current_app.logger.debug(f"Parsed JSON data: {data}")
        except Exception as e:
            current_app.logger.error(f"Failed to parse JSON: {e}")
            return jsonify({"error": "Invalid JSON data"}), 400
            
        stream_url = data.get("stream_url")
        if not stream_url:
            current_app.logger.error("No stream_url provided in request")
            return jsonify({"error": "stream_url parameter is required"}), 400
        
        current_app.logger.info(f"Creating StreamCapture for URL: {stream_url}")
        stream_capture = StreamCapture(stream_url)
        STREAMS[stream_capture.id] = stream_capture
        
        current_app.logger.info(f"Starting capture with ID: {stream_capture.id}")
        stream_capture.start_capture()
        
        status = stream_capture.get_status()
        current_app.logger.info(f"Capture started. Status: {status}")
        return jsonify(status)
        
    except Exception as e:
        current_app.logger.exception("Error in start_capture route")
        return jsonify({"error": str(e)}), 500

@streaming_bp.route("/stop", methods=["POST"])
def stop_capture():
    """Stop an existing stream capture. Expects JSON with 'stream_id'."""
    try:
        data = request.get_json()
        current_app.logger.info(f"Received stop request with data: {data}")
        
        stream_id = data.get("stream_id")
        if not stream_id or stream_id not in STREAMS:
            current_app.logger.error(f"Invalid stream_id: {stream_id}")
            return jsonify({"error": "Valid stream_id is required"}), 400
        
        stream_capture = STREAMS[stream_id]
        current_app.logger.info(f"Stopping capture for ID: {stream_id}")
        stream_capture.stop_capture()
        
        status = stream_capture.get_status()
        current_app.logger.info(f"Capture stopped. Status: {status}")
        return jsonify(status)
        
    except Exception as e:
        current_app.logger.exception("Error in stop_capture route")
        return jsonify({"error": str(e)}), 500

@streaming_bp.route("/status/<stream_id>", methods=["GET"])
def get_status(stream_id):
    """Get the status of a specific stream capture."""
    try:
        current_app.logger.info(f"Status request for stream_id: {stream_id}")
        
        if stream_id not in STREAMS:
            current_app.logger.error(f"Stream not found: {stream_id}")
            return jsonify({"error": "Stream not found"}), 404
        
        stream_capture = STREAMS[stream_id]
        status = stream_capture.get_status()
        current_app.logger.info(f"Returning status: {status}")
        return jsonify(status)
        
    except Exception as e:
        current_app.logger.exception("Error in get_status route")
        return jsonify({"error": str(e)}), 500

@streaming_bp.route("/debug/<stream_id>")
def get_debug_info(stream_id):
    """Get comprehensive debug information for a capture."""
    try:
        if stream_id not in STREAMS:
            return jsonify({"error": "Stream not found"}), 404
            
        stream_capture = STREAMS[stream_id]
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
        
    except Exception as e:
        current_app.logger.exception("Error getting debug info")
        return jsonify({"error": str(e)}), 500

@streaming_bp.route("/debug/<stream_id>/screenshots/<timestamp>")
def get_screenshot(stream_id, timestamp):
    """Retrieve a specific debug screenshot."""
    try:
        if stream_id not in STREAMS:
            return jsonify({"error": "Stream not found"}), 404
            
        stream_capture = STREAMS[stream_id]
        debug_dir = f"/app/captures/{stream_id}/debug"
        
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

@streaming_bp.route("/download/<stream_id>")
def download(stream_id):
    """Download the captured video for a completed capture."""
    try:
        current_app.logger.info(f"Download request for stream_id: {stream_id}")
        
        if stream_id not in STREAMS:
            current_app.logger.error(f"Stream not found: {stream_id}")
            return jsonify({"error": "Stream not found"}), 404
        
        stream_capture = STREAMS[stream_id]
        metadata = stream_capture.get_status()
        
        if metadata["status"] != "completed":
            current_app.logger.error(f"Capture not completed. Status: {metadata['status']}")
            return jsonify({"error": "Capture not completed"}), 400
            
        video_path = metadata["video_path"]
        current_app.logger.info(f"Checking video path: {video_path}")
        
        if os.path.exists(video_path):
            directory = os.path.dirname(video_path)
            filename = os.path.basename(video_path)
            current_app.logger.info(f"Sending file: {filename} from directory: {directory}")
            return send_from_directory(directory=directory, path=filename, as_attachment=True)
        
        current_app.logger.error(f"Video file not found at path: {video_path}")
        return jsonify({"error": "File not found"}), 404
        
    except Exception as e:
        current_app.logger.exception("Error in download route")
        return jsonify({"error": str(e)}), 500