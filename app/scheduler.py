from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from .capture import StreamCapture
from .screen_capture import ScreenCapture
from .metadata import store_capture_metadata, update_capture_end_time
import uuid

scheduler = BackgroundScheduler()

def schedule_capture(stream_url, capture_mode, start_time, duration):
    """
    Schedule a stream capture.
    :param stream_url: URL of the stream/archive.
    :param capture_mode: 'audio', 'video', or 'screenshot'.
    :param start_time: Datetime object for when to start.
    :param duration: Duration of capture in seconds.
    """
    stream_id = str(uuid.uuid4())
    store_capture_metadata(stream_id, stream_url, start_time, capture_mode)

    if capture_mode == "video":
        scheduler.add_job(start_video_capture, 'date', run_date=start_time, args=[stream_id, stream_url, duration])
    elif capture_mode == "screenshot":
        scheduler.add_job(start_screenshot_capture, 'date', run_date=start_time, args=[stream_id, stream_url, duration])

    print(f"[+] Scheduled {capture_mode} capture for {start_time} (Stream ID: {stream_id})")
    return stream_id

def start_video_capture(stream_id, stream_url, duration):
    """Start video capture and stop after duration."""
    capture = StreamCapture(stream_url)
    capture.start_capture()
    print(f"[+] Video capture started: {stream_id}")

    scheduler.add_job(stop_capture, 'date', run_date=datetime.now() + timedelta(seconds=duration), args=[stream_id, capture])

def start_screenshot_capture(stream_id, stream_url, duration):
    """Start screenshot capture and stop after duration."""
    capture = ScreenCapture(stream_url)
    capture.start_capture()
    print(f"[+] Screenshot capture started: {stream_id}")

    scheduler.add_job(stop_capture, 'date', run_date=datetime.now() + timedelta(seconds=duration), args=[stream_id, capture])

def stop_capture(stream_id, capture):
    """Stop capture and update metadata."""
    capture.stop_capture()
    update_capture_end_time(stream_id, datetime.now().isoformat())
    print(f"[+] Capture stopped: {stream_id}")

scheduler.start()