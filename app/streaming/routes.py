# app/streaming/routes.py
from flask import request, jsonify, send_from_directory, current_app, send_file
from app.streaming import streaming_bp
from app.streaming.capture import StreamCapture
from app.services.capture_service import CaptureService, CaptureNotFoundError
from app.models.db_models import CaptureMetrics
import os
import logging
import threading
import psutil
from datetime import datetime

logger = logging.getLogger(__name__)

def cleanup_chrome_processes():
    """Cleanup any stray chrome processes"""
    try:
        keywords = ['chrome', 'chromedriver', 'crashpad']
        for proc in psutil.process_iter(['pid', 'name', 'status']):
            if any(k in str(proc.info['name']).lower() for k in keywords):
                try:
                    logger.info(f"Killing process: {proc.info}")
                    proc.kill()  # Using kill() instead of terminate()
                    proc.wait(timeout=1)
                except (psutil.NoSuchProcess, psutil.TimeoutExpired) as e:
                    logger.warning(f"Error killing process {proc.info['pid']}: {e}")
                    # Force kill if terminate failed
                    try:
                        os.kill(proc.info['pid'], 9)
                    except Exception as e:
                        logger.error(f"Force kill failed for {proc.info['pid']}: {e}")
    except Exception as e:
        logger.warning(f"Error in cleanup_chrome_processes: {e}")

@streaming_bp.route("/start", methods=["POST"])
def start_capture():
    """Initialize capture and return immediately"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
            
        stream_url = data.get("stream_url")
        if not stream_url:
            return jsonify({"error": "stream_url required"}), 400

        # Cleanup any stray processes
        cleanup_chrome_processes()

        # Create capture object
        capture = StreamCapture(stream_url)
        logger.info(f"Created capture {capture.id} for {stream_url}")
        
        # Start capture in background thread
        def capture_thread():
            try:
                capture.start_capture()
            except Exception as e:
                logger.exception(f"Error in capture thread: {e}")
                CaptureService.update_capture_status(
                    capture.id,
                    "failed",
                    error=str(e)
                )
            finally:
                cleanup_chrome_processes()
            
        thread = threading.Thread(target=capture_thread)
        thread.daemon = True
        thread.start()

        # Return immediately with ID
        return jsonify({
            "id": str(capture.id),
            "status": "initialized",
            "stream_url": stream_url,
            "created_at": datetime.utcnow().isoformat()
        }), 202

    except Exception as e:
        logger.exception("Error starting capture")
        cleanup_chrome_processes()
        return jsonify({"error": str(e)}), 500

@streaming_bp.route("/status/<capture_id>", methods=["GET"])
def get_status_endpoint(capture_id):
    """Get capture status from database"""
    try:
        logger.info(f"Status request for capture {capture_id}")
        capture = CaptureService.get_capture_with_metrics(capture_id)
        if not capture:
            return jsonify({"error": "Capture not found"}), 404

        # Get complete status
        capture_model = CaptureService.get_capture(capture_id)
        capture_dict = capture.copy()
        
        if capture_model:
            capture_dict.update({
                'duration': capture_model.duration,
                'current_time': datetime.utcnow().isoformat(),
                'process_info': {
                    'chrome_running': bool([p for p in psutil.process_iter(['name']) 
                                         if 'chrome' in str(p.info['name']).lower()]),
                    'ffmpeg_running': bool([p for p in psutil.process_iter(['name']) 
                                         if 'ffmpeg' in str(p.info['name'])])
                }
            })
            
        return jsonify(capture_dict)
    except Exception as e:
        logger.exception(f"Error getting status for {capture_id}")
        return jsonify({"error": str(e)}), 500

@streaming_bp.route("/stop/<capture_id>", methods=["POST"])
def stop_capture(capture_id):
    """Stop an active capture"""
    logger.info(f"Stop request received for capture {capture_id}")
    
    try:
        # Get capture with detailed logging
        logger.info("Fetching capture from database")
        capture_model = CaptureService.get_capture(capture_id)
        if not capture_model:
            logger.error(f"Capture {capture_id} not found")
            return jsonify({"error": "Capture not found"}), 404
            
        logger.info(f"Found capture. Current status: {capture_model.status}")
        
        # Validate current status
        if capture_model.status in ['completed', 'failed']:
            logger.warning(f"Cannot stop capture in {capture_model.status} state")
            return jsonify({
                "error": f"Cannot stop capture in {capture_model.status} state",
                "status": capture_model.status
            }), 400

        # Clean up any existing Chrome processes
        cleanup_chrome_processes()
            
        # Create new StreamCapture instance with logging
        logger.info("Creating StreamCapture instance")
        stream_capture = StreamCapture(
            stream_url=capture_model.stream_url,
            capture_id=capture_id
        )
        
        # Update status before stopping
        CaptureService.update_capture_status(capture_id, "stopping")
        
        # Stop with logging
        logger.info("Calling stop_capture()")
        success = stream_capture.stop_capture()
        logger.info(f"Stop result: {success}")
        
        if not success:
            return jsonify({"error": "Failed to stop capture"}), 500
        
        # Cleanup processes again
        cleanup_chrome_processes()
        
        # Get final status with metrics
        final_status = CaptureService.get_capture_with_metrics(capture_id)
        if not final_status:
            return jsonify({"error": "Failed to get final status"}), 500
            
        return jsonify(final_status)
        
    except Exception as e:
        logger.exception(f"Error stopping capture {capture_id}")
        cleanup_chrome_processes()
        return jsonify({"error": str(e)}), 500

@streaming_bp.route("/debug/<capture_id>")
def get_debug_info(capture_id):
    """Get comprehensive debug information"""
    try:
        capture_model = CaptureService.get_capture(capture_id)
        if not capture_model:
            return jsonify({"error": "Capture not found"}), 404

        debug_info = {
            "id": str(capture_model.id),
            "stream_url": capture_model.stream_url,
            "status": capture_model.status,
            "duration": capture_model.duration,
            "errors": capture_model.errors or [],
            "capture_metadata": capture_model.capture_metadata or {},
            "debug_screenshots": capture_model.screenshot_paths or [],
            "start_time": capture_model.start_time.isoformat() if capture_model.start_time else None,
            "end_time": capture_model.end_time.isoformat() if capture_model.end_time else None,
            "video_path": capture_model.video_path,
            "video_size": capture_model.video_size,
            "current_time": datetime.utcnow().isoformat(),
            "process_info": {
                "chrome_processes": [p.info['name'] for p in psutil.process_iter(['name']) 
                                  if 'chrome' in str(p.info['name']).lower()],
                "ffmpeg_processes": [p.info['name'] for p in psutil.process_iter(['name']) 
                                  if 'ffmpeg' in str(p.info['name'])]
            }
        }

        # Add metrics
        metrics = CaptureMetrics.query\
            .filter_by(capture_id=capture_id)\
            .order_by(CaptureMetrics.timestamp.desc())\
            .limit(10)\
            .all()
        debug_info['recent_metrics'] = [m.to_dict() for m in metrics]

        return jsonify(debug_info)
    except Exception as e:
        logger.exception(f"Error getting debug info for {capture_id}")
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
        logger.exception(f"Error getting screenshot for {capture_id}")
        return jsonify({"error": str(e)}), 500

@streaming_bp.route("/download/<capture_id>")
def download(capture_id):
    """Download captured video"""
    try:
        capture = CaptureService.get_capture(capture_id)
        if not capture:
            return jsonify({"error": "Capture not found"}), 404

        if capture.status != "completed":
            return jsonify({
                "error": "Capture not completed",
                "status": capture.status
            }), 400

        video_path = capture.video_path
        if not video_path or not os.path.exists(video_path):
            return jsonify({"error": "Video file not found"}), 404

        directory = os.path.dirname(video_path)
        filename = os.path.basename(video_path)
        return send_from_directory(
            directory=directory,
            path=filename,
            as_attachment=True
        )
    except Exception as e:
        logger.exception(f"Error downloading video for {capture_id}")
        return jsonify({"error": str(e)}), 500