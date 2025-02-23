import subprocess
import time
import uuid
import json
import os
import logging
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By  # Import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import random
import tempfile
import shutil
import requests
from app.config import Config  # Import the Config class
# from app import celery, STREAMS  <- NO, task is in __init__.py now
from app.services.capture_service import CaptureService  # Import service
from typing import Optional, Dict, Any, List


# Ensure /app/captures exists (created in Dockerfile, but good to be sure)
os.makedirs("/app/captures", exist_ok=True)


class CaptureError(Exception):
    """Base exception for capture-related errors"""
    pass

class SeleniumSetupError(CaptureError):
    """Raised when Selenium setup fails"""
    pass

class FFmpegError(CaptureError):
    """Raised when FFmpeg operations fail"""
    pass


class StreamCapture:
    CAPTURE_BASE_DIR = "/app/captures"
    FFMPEG_TIMEOUT = 65
    RETRY_MAX_ATTEMPTS = 3
    RETRY_DELAY = 2
    BOT_DETECTION_PHRASES = [
        "bot detection", 
        "access denied", 
        "are you a human", 
        "please wait", 
        "not human"
    ]

    def __init__(self, stream_url: str, capture_id: Optional[str] = None) -> None:
        """Initialize a new StreamCapture instance.
        
        Args:
            stream_url (str): URL of the stream to capture
            capture_id (Optional[str]): Existing capture ID to load
        """
        self.stream_url = stream_url
        #If we are passed a capture ID, this is an existing stream.  Load it.
        if capture_id:
            self.id = capture_id
            self._load_metadata()
        else:
            self.id = str(uuid.uuid4()) # Generate new UUID
            self._create_metadata() # Create metadata.


        self.capture_dir = f"/app/captures/{self.id}"
        self.debug_dir = f"{self.capture_dir}/debug"

        # Create a unique temporary directory for Chrome user data
        self.user_data_dir = tempfile.mkdtemp()

        # File paths
        self.video_file = f"{self.capture_dir}/video.mp4"
        self.metadata_file = f"{self.capture_dir}/metadata.json" # Still useful for storing specific things
        os.makedirs(self.debug_dir, exist_ok=True)

        # Capture state
        self.process = None  # FFmpeg process
        self.capturing = False
        self.driver = None  # Selenium WebDriver instance
        self.start_time = None
        self.end_time = None

        # Initialize metadata.  Store *everything* we might need.
        #self.metadata = { # We don't need to manage this here any more.
        #    "id": self.id,
        #    "stream_url": stream_url,
        #    "start_time": None,
        #    "end_time": None,
        #    "duration": None,
        #    "status": "initialized",
        #    "video_path": self.video_file,
        #    "errors": [],
        #   "page_analysis": {},  # Placeholder for page analysis results
        #    "debug_screenshots": []
        #}
        #self._save_metadata() # No longer save metadata to a file.


    def _create_metadata(self):
      """Creates a new StreamCapture in the database."""
      self.db_capture = CaptureService.create_capture(self.stream_url)
      if not self.db_capture:
        raise Exception("Failed to create capture in database")
      # Ensure the capture id is consistent.
      self.id = str(self.db_capture.id)

    def _load_metadata(self):
        """Loads metadata from database."""
        self.db_capture = CaptureService.get_capture(self.id)
        if not self.db_capture:
            raise Exception(f"Capture with id {self.id} not found")
        # Load any other required data from db_capture, like the created timestamp:
        #self.metadata = self.db_capture.to_dict() #NO longer need a local copy.


    def setup_selenium(self) -> bool:
        try:
            logging.info(f"Using temporary user data directory: {self.user_data_dir}")

            chrome_options = Options()
            chrome_options.add_argument(f'--user-data-dir={self.user_data_dir}')
            chrome_options.add_argument('--headless')  # Run Chrome in headless mode
            chrome_options.add_argument('--no-sandbox')  # Necessary for Docker
            chrome_options.add_argument('--disable-dev-shm-usage') # Overcome limited resource problems
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_argument('--disable-infobars')
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            chrome_options.binary_location = Config.GOOGLE_CHROME_BIN  # Get Chrome path from config

            # Randomize window size
            width = random.randint(1800, 1920)
            height = random.randint(1000, 1080)
            chrome_options.add_argument(f'--window-size={width},{height}')

            # Add realistic user agent
            user_agents = [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
            ]
            chrome_options.add_argument(f'--user-agent={random.choice(user_agents)}')

            max_retries = 3
            retry_delay = 2

            for attempt in range(max_retries):
                try:
                    self.driver = webdriver.Chrome(options=chrome_options)
                    self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                        'source': '''
                            Object.defineProperty(navigator, 'webdriver', {
                                get: () => undefined
                            });
                        '''
                    })
                    # Introduce small, random mouse movements.
                    actions = ActionChains(self.driver)
                    actions.move_by_offset(random.randint(10, 50), random.randint(10, 50))
                    actions.perform()

                    self.driver.get(self.stream_url)
                    self.check_for_bot_detection()  # Call bot detection check
                    time.sleep(random.uniform(3, 5))  # Wait a random time

                    if attempt > 0:
                        logging.info(f"Successfully connected on attempt {attempt + 1}")
                    break  # Exit loop if successful
                except Exception as e:
                    logging.error(f"Attempt {attempt + 1} failed: {e}")
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (2 ** attempt) # Exponential backoff
                        time.sleep(wait_time)
                    else:
                        raise  # Re-raise the exception after all retries

            return True # Indicate successful setup
        except Exception as e:
            logging.exception("Selenium setup error")
            CaptureService.update_capture_status(self.id, "failed", f"Selenium setup error: {str(e)}")
            self.cleanup()
            return False

    def check_for_bot_detection(self) -> bool:
        """Check for common bot detection mechanisms."""
        try:
            # Check for reCAPTCHA
            if self.driver.find_elements(By.TAG_NAME, 'iframe[src*="recaptcha"]'):
                CaptureService.update_capture_status(self.id, "failed", "reCAPTCHA detected")
                logging.warning("reCAPTCHA detected")
                return True

            # Check for Cloudflare's "I'm Under Attack Mode" (IUAM)
            if "I'm Under Attack Mode" in self.driver.title:
                CaptureService.update_capture_status(self.id, "failed", "Cloudflare IUAM detected")
                logging.warning("Cloudflare IUAM detected")
                return True
            
            #Check for a button with id="challenge-running"
            if self.driver.find_elements(By.ID, 'challenge-running'):
                CaptureService.update_capture_status(self.id, "failed", "Detected element with id='challenge-running'")
                return True

            # Check for a div with id="cf-challenge-running"
            if self.driver.find_elements(By.ID, "cf-challenge-running"):
                CaptureService.update_capture_status(self.id, "failed", "Cloudflare challenge detected (cf-challenge-running)")
                logging.warning("Cloudflare challenge detected (cf-challenge-running)")
                return True

            # Generic check for common bot detection strings
            for phrase in ["bot detection", "access denied", "are you a human", "please wait", "not human"]:
                if phrase in self.driver.page_source.lower():
                    CaptureService.update_capture_status(self.id, "failed", f"Bot detection phrase found: {phrase}")
                    logging.warning(f"Bot detection phrase found: {phrase}")
                    return True

            return False  # No bot detection found (so far)
        except Exception as e:
            logging.exception("Error during bot detection check")
            CaptureService.update_capture_status(self.id, "failed", f"Bot detection check error: {str(e)}")
            return True  # Treat errors as potential blocking
        
    def validate_connection(self) -> bool:
        """Pre-check connection before starting selenium"""
        try:
            # First try a simple HEAD request
            response = requests.head(self.stream_url,
                                        timeout=10,
                                        allow_redirects=True,
                                        headers={
                                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124 Safari/537.36'
                                        })

            if response.status_code == 524:  # Cloudflare timeout
                logging.warning("Cloudflare timeout (524) on initial HEAD request. Retrying...")
                time.sleep(5)  # Wait before retry
                response = requests.head(self.stream_url,
                                        timeout=30,  # Longer timeout
                                        allow_redirects=True)

            if response.status_code >= 400:
                CaptureService.update_capture_status(self.id, 'failed', error=f"HTTP Error: {response.status_code}")
                return False

            return True
        except requests.exceptions.RequestException as e:
            logging.exception(f"Connection error: {e}")
            CaptureService.update_capture_status(self.id, 'failed', error=f"Connection error: {e}")
            return False
        except Exception as e: #Catch any other exceptions
            logging.exception(f"An unexpected error occurred: {e}")
            CaptureService.update_capture_status(self.id, "failed", f"An unexpected error occurred: {e}")
            return False

    def start_capture(self):
        """Start capturing video"""
        try:
            if not self.validate_connection():
                CaptureService.update_capture_status(self.id, "failed", "Connection validation failed")
                return

            time.sleep(3)

            if not self.setup_selenium():
                CaptureService.update_capture_status(self.id, "failed", "Selenium setup failed")
                return

            self.start_time = datetime.now()
            self.capturing = True
            CaptureService.update_capture_status(self.id, "capturing", start_time=self.start_time)
            logging.info(f"Capture started for {self.stream_url}")

            command = self._build_ffmpeg_command()
            logging.debug(f"Running FFmpeg command: {' '.join(command)}")
            self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # Monitor the FFmpeg process.
            start_wait = time.time()
            while time.time() - start_wait < 65:
                if self.process.poll() is not None:
                    break
                time.sleep(1)
                CaptureService.update_capture_metadata(self.id, duration=int(time.time() - start_wait))

            self.take_debug_screenshot("final_state")

            if self.process.poll() is not None:
                stdout, stderr = self.process.communicate()
                logging.debug(f"FFmpeg stdout: {stdout.decode() if stdout else ''}")
                if stderr:
                    logging.error(f"FFmpeg stderr: {stderr.decode()}")
                    CaptureService.update_capture_status(self.id, "failed", error=f"FFmpeg error: {stderr.decode()}")

            if not os.path.exists(self.video_file):
                raise Exception("Video file not created")

            # If we get here, the capture was likely successful
            self.end_time = datetime.now()
            duration = (self.end_time - self.start_time).total_seconds()
            CaptureService.update_capture_status(self.id, 'completed', end_time = self.end_time, duration = int(duration))


        except Exception as e:
            logging.exception("Error during stream capture")
            CaptureService.update_capture_status(self.id, "failed", error=f"Capture error: {str(e)}")
            self.cleanup() #Clean up


    def stop_capture(self):
        """Stop capturing with enhanced termination and cleanup"""
        try:
            if self.process and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    logging.warning(f"Forced termination of FFmpeg process for capture {self.id}")
                finally:
                    stdout, stderr = self.process.communicate()
                    if stderr:
                        logging.debug(f"FFmpeg stderr on stop: {stderr.decode()}")

            if self.driver:
                self.take_debug_screenshot("before_quit")
                try:
                    self.driver.quit()
                except Exception as e:
                    logging.warning(f"Error quitting Selenium driver: {e}")

            self.cleanup() # Clean up temporary files

            self.capturing = False
            self.end_time = datetime.now()
            duration = (self.end_time - self.start_time).total_seconds() if self.start_time else None

            CaptureService.update_capture_status(self.id, "completed", end_time=self.end_time, duration=int(duration))
            logging.info(f"Capture stopped for {self.stream_url}, duration: {duration} seconds")
        except Exception as e:
            logging.exception("Error stopping capture")
            CaptureService.update_capture_status(self.id, "failed", error=f"Stop error: {str(e)}")

    def cleanup(self):
        """Clean up resources (driver, temp files)"""
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                logging.warning(f"Error quitting Selenium driver: {e}")
            self.driver = None

        if self.user_data_dir and os.path.exists(self.user_data_dir):
            try:
                shutil.rmtree(self.user_data_dir)
                logging.info(f"Deleted user data directory: {self.user_data_dir}")
            except Exception as e:
                logging.warning(f"Error deleting user data dir: {e}")
            self.user_data_dir = None

        if hasattr(self, 'temp_dir') and self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
                logging.info(f"Deleted temp directory: {self.temp_dir}")
            except Exception as e:
                logging.warning(f"Error deleting tempdir: {e}")
            self.temp_dir = None

    def _save_metadata(self):
      """Saves metadata using CaptureService."""
      #No longer use this function, use the database.
      pass

    def _update_metadata(self, **kwargs):
        """Update metadata using CaptureService"""
        try:
            CaptureService.update_capture_metadata(self.id, **kwargs)
        except Exception as e:
            logging.error(f"Error updating metadata: {e}")

    def get_status(self) -> dict:
        """Get capture status - now from the database"""
        return CaptureService.get_capture(self.id).to_dict() #Use service layer.


    def take_debug_screenshot(self, name: str):
        """Take a screenshot for debugging and add its path to metadata."""
        try:
            if not self.driver:
                return  # Don't take screenshots if driver isn't running

            timestamp = int(time.time())
            filename = f"{timestamp}_{name}.png"
            path = os.path.join(self.debug_dir, filename)

            self.driver.save_screenshot(path)
            #Now we use capture service to add this to the db.
            CaptureService.update_capture_metadata(self.id, debug_screenshots = self.db_capture.debug_screenshots + [path])
            logging.debug(f"Screenshot saved: {path}")
        except Exception as e:
            logging.error(f"Screenshot error: {e}")

    def _build_ffmpeg_command(self) -> List[str]:
        """Build FFmpeg command with current settings"""
        return [
            "ffmpeg",
            "-f", "x11grab",
            "-video_size", "1920x1080",
            "-i", os.getenv("DISPLAY", ":99"),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-t", "60",
            "-c:a", "aac",
            "-ac", "2",
            self.video_file
        ]

    def __enter__(self):
        """Support for context manager protocol"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Ensure cleanup on exit"""
        self.cleanup()