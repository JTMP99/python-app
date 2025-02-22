import subprocess
import threading
import time
import uuid
import json
import os
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

class StreamCapture:
    def __init__(self, stream_url: str):
        self.stream_url = stream_url
        self.id = str(uuid.uuid4())
        
        # Setup directory structure
        self.capture_dir = f"/app/captures/{self.id}"
        os.makedirs(self.capture_dir, exist_ok=True)
        
        # File paths
        self.video_file = f"{self.capture_dir}/video.mp4"
        self.audio_file = f"{self.capture_dir}/audio.wav"
        self.metadata_file = f"{self.capture_dir}/metadata.json"
        
        # Capture state
        self.process = None
        self.capturing = False
        self.driver = None
        self.start_time = None
        self.end_time = None
        
        # Initialize metadata
        self.metadata = {
            "id": self.id,
            "stream_url": stream_url,
            "start_time": None,
            "end_time": None,
            "duration": None,
            "status": "initialized",
            "video_path": self.video_file,
            "audio_path": self.audio_file,
            "errors": []
        }
        self._save_metadata()

    def _save_metadata(self):
        """Save current metadata to file"""
        with open(self.metadata_file, 'w') as f:
            json.dump(self.metadata, f, indent=2, default=str)

    def _update_metadata(self, **kwargs):
        """Update metadata with new values"""
        self.metadata.update(kwargs)
        self._save_metadata()

    def setup_selenium(self):
        """Configure and start Selenium WebDriver"""
        try:
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--start-maximized')
            chrome_options.add_argument('--autoplay-policy=no-user-gesture-required')
            chrome_options.binary_location = os.getenv('GOOGLE_CHROME_BIN', '/usr/bin/chromium')
            
            self.driver = webdriver.Chrome(options=chrome_options)
            return True
        except Exception as e:
            self._update_metadata(
                status="error",
                errors=self.metadata["errors"] + [f"Selenium setup error: {str(e)}"]
            )
            return False

    def start_capture(self) -> None:
        """Start capturing video and audio"""
        try:
            if not self.setup_selenium():
                return
            
            self.start_time = datetime.now()
            self.capturing = True
            
            # Update metadata
            self._update_metadata(
                status="recording",
                start_time=self.start_time
            )
            
            # Navigate to stream
            self.driver.get(self.stream_url)
            time.sleep(5)  # Wait for stream to load
            
            # Start FFmpeg to capture both screen and audio
            command = [
                "ffmpeg",
                "-f", "x11grab",  # Screen capture
                "-video_size", "1920x1080",  # Adjust as needed
                "-i", os.getenv("DISPLAY", ":99"),
                "-f", "alsa",  # Audio capture
                "-i", "default",
                "-c:v", "libx264",
                "-c:a", "aac",
                "-strict", "experimental",
                self.video_file
            ]
            
            self.process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
        except Exception as e:
            self._update_metadata(
                status="error",
                errors=self.metadata["errors"] + [f"Capture start error: {str(e)}"]
            )
            self.stop_capture()

    def stop_capture(self) -> None:
        """Stop capturing and cleanup"""
        try:
            self.capturing = False
            self.end_time = datetime.now()
            
            # Stop FFmpeg process
            if self.process:
                self.process.terminate()
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.process.kill()
            
            # Close Selenium
            if self.driver:
                self.driver.quit()
            
            # Calculate duration
            if self.start_time and self.end_time:
                duration = (self.end_time - self.start_time).total_seconds()
            else:
                duration = None
            
            # Update final metadata
            self._update_metadata(
                status="completed",
                end_time=self.end_time,
                duration=duration
            )
            
        except Exception as e:
            self._update_metadata(
                status="error",
                errors=self.metadata["errors"] + [f"Capture stop error: {str(e)}"]
            )

    def get_status(self) -> dict:
        """Get current capture status and metadata"""
        return self.metadata