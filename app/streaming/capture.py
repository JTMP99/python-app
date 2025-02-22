import subprocess
import threading
import time
import uuid
import json
import os
import logging
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from app.config import Config  

# Configure logging using Config class
LOG_FILE = Config.LOG_FILE

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filemode="a"
)

class StreamCapture:
    def __init__(self, stream_url: str):
        self.stream_url = stream_url
        self.id = str(uuid.uuid4())

        # Setup directory structure
        self.capture_dir = f"/app/captures/{self.id}"
        os.makedirs(self.capture_dir, exist_ok=True)

        # File paths
        self.video_file = f"{self.capture_dir}/video.mp4"
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
            "errors": []
        }
        self._save_metadata()

    def _save_metadata(self):
        """Save metadata to file"""
        try:
            with open(self.metadata_file, 'w') as f:
                json.dump(self.metadata, f, indent=2, default=str)
            logging.debug(f"Metadata saved for {self.id}")
        except Exception as e:
            logging.error(f"Failed to save metadata: {e}")

    def setup_selenium(self):
        """Configure Selenium WebDriver and navigate to stream page"""
    try:
        logging.info("Initializing Selenium WebDriver...")

        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.binary_location = os.getenv('GOOGLE_CHROME_BIN', '/usr/bin/chromium')

        self.driver = webdriver.Chrome(options=chrome_options)
        logging.info("Selenium WebDriver initialized successfully")

        # Navigate to the stream page
        logging.info(f"Navigating to stream URL: {self.stream_url}")
        self.driver.get(self.stream_url)

        time.sleep(10)  # Wait for elements to load
        logging.info("Page should have loaded, checking for play button...")

        # Save a screenshot to see what the browser actually loads
        screenshot_path = "/app/logs/selenium_screenshot.png"
        self.driver.save_screenshot(screenshot_path)
        logging.info(f"Screenshot saved at {screenshot_path}")

        # Check if Play button exists
        try:
            play_button = WebDriverWait(self.driver, 120).until(  # Increased timeout
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[aria-label='Play']"))
            )
            play_button.click()
            logging.info("Clicked play button to start the stream")
        except Exception as e:
            logging.error(f"Play button not found or could not be clicked: {e}")

        return True
    except Exception as e:
        logging.exception("Selenium setup error")
        self._update_metadata(errors=f"Selenium setup error: {str(e)}")
        return False

    def start_capture(self) -> None:
        """Start capturing video"""
        try:
            if not self.setup_selenium():
                return

            self.start_time = datetime.now()
            self.capturing = True
            logging.info(f"Capture started for {self.stream_url}")

            # Start FFmpeg process
            command = [
                "ffmpeg",
                "-f", "x11grab",
                "-video_size", "1920x1080",
                "-i", os.getenv("DISPLAY", ":99"),
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-t", "60",  # Limit to 60 seconds for testing
                self.video_file
            ]

            logging.debug(f"Running FFmpeg command: {' '.join(command)}")
            self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        except Exception as e:
            logging.exception("Error during stream capture")
            self._update_metadata(errors=f"Capture start error: {str(e)}")
            self.stop_capture()

    def stop_capture(self) -> None:
        """Stop capturing"""
        try:
            if self.process:
                self.process.terminate()
                self.process.wait(timeout=10)
            if self.driver:
                self.driver.quit()

            self.end_time = datetime.now()
            duration = (self.end_time - self.start_time).total_seconds() if self.start_time else None
            self._update_metadata(status="completed", end_time=self.end_time, duration=duration)
            logging.info(f"Capture stopped for {self.stream_url}, duration: {duration} seconds")

        except Exception as e:
            logging.exception("Error stopping capture")
            self._update_metadata(errors=f"Capture stop error: {str(e)}")

    def get_status(self) -> dict:
        """Get capture status"""
        return self.metadata
