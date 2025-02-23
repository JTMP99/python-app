# app/streaming/routes.py
from flask import request, jsonify, send_from_directory, current_app, send_file
from app.streaming import streaming_bp  # Import the blueprint
from app.streaming.capture import start_capture_task  # Import Celery *task*
from app import STREAMS, celery  # Import STREAMS and celery
import os
import logging


@streaming_bp.route("/start", methods=["POST"])
def start_capture():
    """Start a new stream capture (asynchronously via Celery)."""
    data = request.get_json()
    stream_url = data.get("stream_url")

    if not stream_url:
        return jsonify({"error": "stream_url parameter is required"}), 400

    # Start the Celery task *asynchronously*
    task = start_capture_task.delay(stream_url)
    current_app.logger.info(f"Started Celery task with ID: {task.id}")  # Log task ID

    # Immediately return the task ID to the client
    return jsonify({"task_id": task.id, "status": "pending"})


@streaming_bp.route("/stop", methods=["POST"])
def stop_capture():
    """Stop an existing stream capture."""
    data = request.get_json()
    stream_id = data.get("stream_id")  # This is the *capture* ID

    if not stream_id:
        return jsonify({"error": "stream_id parameter is required"}), 400

    # Check if the stream_id exists and try to revoke the task
    if stream_id in STREAMS:
        stream_capture = STREAMS[stream_id]
        current_app.logger.info(f"Stopping capture for stream ID: {stream_id}") #log
        # Attempt to stop the running capture process.
        stream_capture.stop_capture()
        # Remove from active streams
        del STREAMS[stream_id]  # Remove from the dictionary
        return jsonify({"status": "stopped"})
    else:
        current_app.logger.error(f"Invalid stream_id: {stream_id}") #log
        return jsonify({"error": "Stream not found or already stopped"}), 404 #Correct status code.

@streaming_bp.route("/status/<task_id>", methods=["GET"])
def get_status(task_id):
    """Get the status of a Celery task (and the capture, if finished)."""
    current_app.logger.debug(f"Checking status for task ID: {task_id}") # Log the task ID being checked
    task = celery.AsyncResult(task_id)
    current_app.logger.debug(f"Task state: {task.state}") # Log the raw task state

    if task.state == 'PENDING':
        response = {
            'state': task.state,
            'status': 'Pending...'  # Initial status
        }
    elif task.state != 'FAILURE':
        response = {
            'state': task.state,
            'status': task.info.get('status', '') if isinstance(task.info, dict) else str(task.info),  # Get status, handle non-dict
        }
        if task.state == 'SUCCESS':
            stream_id = task.result # This now holds the *stream ID*.
            current_app.logger.debug(f"Task succeeded. Stream ID: {stream_id}") # Log stream ID
            if stream_id in STREAMS:
              stream_capture = STREAMS[stream_id]
              # Update response with status
              response.update(stream_capture.get_status()) # Use get_status for the rest.
            else:
              response['status'] = "Capture data not found" # Error

    else:
        # Something went wrong in the task.
        response = {
            'state': task.state,
            'status': str(task.info),  # this is the exception raised
        }
    current_app.logger.debug(f"Returning status: {response}")  # Log the *entire* response
    return jsonify(response)



@streaming_bp.route("/debug/<stream_id>")
def get_debug_info(stream_id):
    """Get comprehensive debug information for a capture."""
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


@streaming_bp.route("/debug/<stream_id>/screenshots/<timestamp>")
def get_screenshot(stream_id, timestamp):
    """Retrieve a specific debug screenshot."""

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


@streaming_bp.route("/download/<stream_id>")
def download(stream_id):
    """Download the captured video for a completed capture."""
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