# app/streaming/routes.py
from flask import request, jsonify, send_from_directory, current_app, send_file
from app.streaming import streaming_bp
from app.streaming.capture import StreamCapture
from app.services.capture_service import CaptureService, CaptureNotFoundError, DatabaseError
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
            try:
                if any(k in str(proc.info['name']).lower() for k in keywords):
                    logger.info(f"Killing process: {proc.info}")
                    proc.kill()  # Using kill() instead of terminate()
                    proc.wait(timeout=1)
            except (psutil.NoSuchProcess, psutil.TimeoutExpired, psutil.AccessDenied) as e:
                logger.warning(f"Error killing process {proc.info.get('pid')}: {e}")
                # Force kill if terminate failed
                try:
                    os.kill(proc.info.get('pid'), 9)
                except (ProcessLookupError, PermissionError) as ke:
                    logger.error(f"Force kill failed: {ke}")
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

            # Add detailed logging here
            logger.info(f"Starting capture for URL: {stream_url}")
            logger.info(f"Environment: DISPLAY={os.environ.get('DISPLAY')}, CHROME_BIN={os.environ.get('GOOGLE_CHROME_BIN')}")
            
            # Cleanup any stray processes
            cleanup_chrome_processes()

            # Create capture object
            try:
                capture = StreamCapture(stream_url)
                logger.info(f"Created capture {capture.id} for {stream_url}")
            except Exception as e:
                logger.exception("Error creating capture object")
                return jsonify({"error": f"Failed to create capture: {str(e)}"}), 500
            
            # Start capture in background thread
            def capture_thread():
                try:
                    logger.info(f"Starting capture thread for {capture.id}")
                    capture.start_capture()
                    logger.info(f"Capture thread completed for {capture.id}")
                except Exception as e:
                    logger.exception(f"Error in capture thread: {e}")
                    try:
                        CaptureService.update_capture_status(
                            capture.id,
                            "failed",
                            error=str(e)
                        )
                    except Exception as se:
                        logger.error(f"Failed to update error status: {se}")
                finally:
                    cleanup_chrome_processes()
                
            thread = threading.Thread(target=capture_thread)
            thread.daemon = True
            thread.start()
            logger.info(f"Started background thread for capture {capture.id}")

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
        try:
            capture = CaptureService.get_capture_with_metrics(capture_id)
            if not capture:
                return jsonify({"error": "Capture not found"}), 404

            # Get complete status
            capture_model = CaptureService.get_capture(capture_id)
            capture_dict = capture.copy()
        except DatabaseError as e:
            logger.error(f"Database error getting status: {e}")
            return jsonify({"error": "Database error", "details": str(e)}), 500
        
        # Add process information
        try:
            chrome_procs = [p for p in psutil.process_iter(['name']) 
                         if 'chrome' in str(p.info['name']).lower()]
            ffmpeg_procs = [p for p in psutil.process_iter(['name']) 
                         if 'ffmpeg' in str(p.info['name'])]
        except Exception as e:
            logger.warning(f"Error getting process info: {e}")
            chrome_procs = []
            ffmpeg_procs = []
        
        if capture_model:
            capture_dict.update({
                'duration': capture_model.duration,
                'current_time': datetime.utcnow().isoformat(),
                'process_info': {
                    'chrome_running': bool(chrome_procs),
                    'ffmpeg_running': bool(ffmpeg_procs),
                    'chrome_processes': len(chrome_procs),
                    'ffmpeg_processes': len(ffmpeg_procs)
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
        try:
            capture_model = CaptureService.get_capture(capture_id)
            if not capture_model:
                logger.error(f"Capture {capture_id} not found")
                return jsonify({"error": "Capture not found"}), 404
        except DatabaseError as e:
            logger.error(f"Database error getting capture: {e}")
            return jsonify({"error": "Database error", "details": str(e)}), 500
            
        logger.info(f"Found capture. Current status: {capture_model.status}")
        
        # Validate current status
        if capture_model.status in ['completed', 'failed']:
            msg = f"Cannot stop capture in {capture_model.status} state"
            logger.warning(msg)
            return jsonify({
                "error": msg,
                "status": capture_model.status
            }), 400

        # Clean up any existing Chrome processes before stopping
        logger.info("Cleaning up existing Chrome processes")
        cleanup_chrome_processes()
            
        try:
            # Create new StreamCapture instance with logging
            logger.info("Creating StreamCapture instance")
            stream_capture = StreamCapture(
                stream_url=capture_model.stream_url,
                capture_id=capture_id
            )
            
            # Update status before stopping
            logger.info("Updating status to stopping")
            CaptureService.update_capture_status(capture_id, "stopping")
            
            # Stop with logging
            logger.info("Calling stop_capture()")
            success = stream_capture.stop_capture()
            logger.info(f"Stop result: {success}")
            
            if not success:
                logger.error("Stop capture returned False")
                return jsonify({
                    "error": "Failed to stop capture",
                    "details": "Stop operation returned False"
                }), 500
            
        except Exception as inner_e:
            logger.exception("Error during stop operation")
            return jsonify({
                "error": "Stop operation failed",
                "details": str(inner_e)
            }), 500
        
        # Cleanup processes again after stopping
        logger.info("Final Chrome process cleanup")
        cleanup_chrome_processes()
        
        try:
            # Get final status with metrics
            logger.info("Getting final status")
            final_status = CaptureService.get_capture_with_metrics(capture_id)
            if not final_status:
                logger.error("Failed to get final status")
                return jsonify({
                    "error": "Failed to get final status",
                    "details": "Status query returned None"
                }), 500
                
            logger.info(f"Successfully stopped capture {capture_id}")
            return jsonify(final_status)
            
        except Exception as status_e:
            logger.exception("Error getting final status")
            return jsonify({
                "error": "Failed to get final status",
                "details": str(status_e)
            }), 500
        
    except Exception as e:
        logger.exception(f"Error stopping capture {capture_id}")
        cleanup_chrome_processes()
        return jsonify({
            "error": "Stop capture failed",
            "details": str(e),
            "error_type": e.__class__.__name__
        }), 500

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
            "current_time": datetime.utcnow().isoformat()
        }

        # Add process info
        try:
            debug_info["process_info"] = {
                "chrome_processes": [p.info['name'] for p in psutil.process_iter(['name']) 
                                  if 'chrome' in str(p.info['name']).lower()],
                "ffmpeg_processes": [p.info['name'] for p in psutil.process_iter(['name']) 
                                  if 'ffmpeg' in str(p.info['name'])]
            }
        except Exception as e:
            logger.warning(f"Error getting process info: {e}")
            debug_info["process_info"] = {"error": str(e)}

        # Add metrics
        try:
            metrics = CaptureMetrics.query\
                .filter_by(capture_id=capture_id)\
                .order_by(CaptureMetrics.timestamp.desc())\
                .limit(10)\
                .all()
            debug_info['recent_metrics'] = [m.to_dict() for m in metrics]
        except Exception as e:
            logger.warning(f"Error getting metrics: {e}")
            debug_info['recent_metrics'] = []

        # Add directory info
        capture_dir = f"/app/captures/{capture_id}"
        if os.path.exists(capture_dir):
            try:
                debug_info['directory_contents'] = os.listdir(capture_dir)
            except Exception as e:
                logger.warning(f"Error listing directory: {e}")
                debug_info['directory_contents'] = f"Error: {str(e)}"
        else:
            debug_info['directory_contents'] = "Directory not found"

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
                try:
                    return send_file(
                        os.path.join(debug_dir, filename),
                        mimetype='image/png'
                    )
                except Exception as e:
                    logger.error(f"Error sending file: {e}")
                    return jsonify({"error": f"Error sending file: {str(e)}"}), 500

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

        try:
            directory = os.path.dirname(video_path)
            filename = os.path.basename(video_path)
            return send_from_directory(
                directory=directory,
                path=filename,
                as_attachment=True
            )
        except Exception as e:
            logger.error(f"Error sending video file: {e}")
            return jsonify({"error": f"Error sending video: {str(e)}"}), 500
    except Exception as e:
        logger.exception(f"Error downloading video for {capture_id}")
        return jsonify({"error": str(e)}), 500
    
    @streaming_bp.route("/system-status")
    def system_status():
        """Check system status and running processes"""
        try:
            # Check Chrome processes
            chrome_procs = [p.info for p in psutil.process_iter(['pid', 'name', 'cmdline']) 
                        if 'chrome' in str(p.info.get('name', '')).lower()]
            
            # Check FFmpeg processes
            ffmpeg_procs = [p.info for p in psutil.process_iter(['pid', 'name', 'cmdline']) 
                        if 'ffmpeg' in str(p.info.get('name', '')).lower()]
            
            # Check available space
            disk_usage = psutil.disk_usage('/')
            
            # Check environment variables
            env_vars = {
                'DISPLAY': os.environ.get('DISPLAY'),
                'GOOGLE_CHROME_BIN': os.environ.get('GOOGLE_CHROME_BIN'),
                'DATABASE_URL_SET': bool(os.environ.get('DATABASE_URL'))
            }
            
            return jsonify({
                'chrome_processes': len(chrome_procs),
                'ffmpeg_processes': len(ffmpeg_procs),
                'disk_space': {
                    'total_gb': round(disk_usage.total / (1024**3), 2),
                    'used_gb': round(disk_usage.used / (1024**3), 2),
                    'free_gb': round(disk_usage.free / (1024**3), 2),
                    'percent_used': disk_usage.percent
                },
                'environment': env_vars,
                'time': datetime.utcnow().isoformat()
            })
        except Exception as e:
            logger.exception("Error in system status")
            return jsonify({'error': str(e)}), 500
            
@streaming_bp.route("/test", methods=["GET"])
def test_endpoint():
    """Simple test endpoint to verify the blueprint is working."""
    return jsonify({
        "status": "success", 
        "message": "Streaming routes are working!",
        "blueprint": "streaming_bp",
        "url_prefix": "/streams"
    })