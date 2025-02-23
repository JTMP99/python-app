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
from app.config import Config
from app import celery, STREAMS  # Import Celery and STREAMS

# Ensure /app/captures exists (created in Dockerfile, but good to be sure)
os.makedirs("/app/captures", exist_ok=True)


class StreamCapture:
    def __init__(self, stream_url: str):
        self.stream_url = stream_url
        self.id = str(uuid.uuid4())
        self.capture_dir = f"/app/captures/{self.id}"
        self.debug_dir = f"{self.capture_dir}/debug"

        # Create a unique temporary directory for Chrome user data
        self.user_data_dir = tempfile.mkdtemp()

        # File paths
        self.video_file = f"{self.capture_dir}/video.mp4"
        self.metadata_file = f"{self.capture_dir}/metadata.json"
        os.makedirs(self.debug_dir, exist_ok=True)

        # Capture state
        self.process = None  # FFmpeg process
        self.capturing = False
        self.driver = None  # Selenium WebDriver instance
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
            "errors": [],
            "page_analysis": {},  # Placeholder for page analysis results
            "debug_screenshots": []
        }
        self._save_metadata()

    def setup_selenium(self):
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
            self.metadata["errors"].append(f"Selenium setup error: {str(e)}")
            # Clean up if setup fails
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
            if self.user_data_dir and os.path.exists(self.user_data_dir):
                shutil.rmtree(self.user_data_dir, ignore_errors=True)
            return False

    def start_capture(self) -> None:
        """Start capturing video"""
        try:
            if not self.setup_selenium():
                self.metadata["status"] = "failed"
                self._save_metadata()
                return

            self.start_time = datetime.now()
            self.capturing = True
            self.metadata["status"] = "capturing"
            self.metadata["start_time"] = self.start_time.isoformat()
            self._save_metadata()

            logging.info(f"Capture started for {self.stream_url}")

            command = [
                "ffmpeg",
                "-f", "x11grab",  # Input format for X11 screen grabbing
                "-video_size", "1920x1080",  # Capture size (match or exceed window size)
                "-i", os.getenv("DISPLAY", ":99"),  # Display to capture from (defaults to :99)
                "-c:v", "libx264",  # Video codec (H.264)
                "-preset", "ultrafast",  # Encoding preset (balance speed/quality)
                "-t", "60", # Added timeout
                "-c:a", "aac",  # Add audio codec
                "-ac", "2",      # Stereo audio
                self.video_file  # Output file
            ]

            logging.debug(f"Running FFmpeg command: {' '.join(command)}")
            self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # Monitor the FFmpeg process. Wait for it to finish, or for a timeout
            start_wait = time.time()
            while time.time() - start_wait < 65:  # Check for up to 65 seconds
                if self.process.poll() is not None:  # Check if process has terminated
                    break  # Exit loop if FFmpeg has finished/failed
                time.sleep(1)
                self._update_metadata(duration=int(time.time() - start_wait))

            self.take_debug_screenshot("final_state")

            if self.process.poll() is not None:  # Process terminated
                stdout, stderr = self.process.communicate()
                logging.debug(f"FFmpeg stdout: {stdout.decode() if stdout else ''}")
                if stderr:
                    logging.error(f"FFmpeg stderr: {stderr.decode()}")
                    self.metadata["errors"].append(f"FFmpeg error: {stderr.decode()}")


        except Exception as e:
            logging.exception("Error during stream capture")
            self.metadata["errors"].append(f"Capture error: {str(e)}")
            self.metadata["status"] = "failed"
            self._save_metadata()
            self.stop_capture()  # Ensure resources are released

    def stop_capture(self) -> None:
        """Stop capturing with enhanced termination and cleanup"""
        try:
            # Terminate FFmpeg process if it exists
            if self.process and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=10)  # Wait up to 10 seconds for graceful termination
                except subprocess.TimeoutExpired:
                    self.process.kill()  # Force kill if timeout occurs
                    logging.warning(f"Forced termination of FFmpeg process for capture {self.id}")
                finally:
                    stdout, stderr = self.process.communicate()
                    if stderr:
                        logging.debug(f"FFmpeg stderr on stop: {stderr.decode()}")


            # Quit Selenium driver and take a screenshot before quitting
            if self.driver:
                self.take_debug_screenshot("before_quit")
                try:
                    self.driver.quit()
                except Exception as e:
                    logging.warning(f"Error quitting Selenium driver: {e}")

            # Clean up temporary user data directory
            if self.user_data_dir and os.path.exists(self.user_data_dir):
                shutil.rmtree(self.user_data_dir, ignore_errors=True)
                logging.info(f"Deleted temporary user data directory: {self.user_data_dir}")
                self.user_data_dir = None  # Reset to avoid reuse


            # Update capture state and metadata
            self.capturing = False
            self.end_time = datetime.now()
            duration = (self.end_time - self.start_time).total_seconds() if self.start_time else None

            self.metadata.update({
                "status": "completed",
                "end_time": self.end_time.isoformat(),
                "duration": duration
            })
            self._save_metadata()

            logging.info(f"Capture stopped for {self.stream_url}, duration: {duration} seconds")

        except Exception as e:
            logging.exception("Error stopping capture")
            self.metadata["errors"].append(f"Stop error: {str(e)}")
            self.metadata["status"] = "failed"
            self._save_metadata()
            # Clean up even on error
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
            if self.user_data_dir and os.path.exists(self.user_data_dir):
                shutil.rmtree(self.user_data_dir, ignore_errors=True)


    def _save_metadata(self):
        """Save metadata to file"""
        try:
            with open(self.metadata_file, 'w') as f:
                json.dump(self.metadata, f, indent=2, default=str)  # Use default=str for serialization
            logging.debug(f"Metadata saved for {self.id}")
        except Exception as e:
            logging.error(f"Failed to save metadata: {e}")

    def _update_metadata(self, **kwargs):
        """Update metadata fields and save"""
        self.metadata.update(kwargs)
        self._save_metadata()

    def get_status(self) -> dict:
        """Get capture status"""
        return self.metadata

    def take_debug_screenshot(self, name: str):
        """Take a screenshot for debugging"""
        try:
            screenshot_path = f"{self.debug_dir}/{name}_{int(time.time())}.png"
            self.driver.save_screenshot(screenshot_path)
            self.metadata["debug_screenshots"].append(screenshot_path)
            logging.debug(f"Screenshot saved: {screenshot_path}")
        except Exception as e:
            logging.error(f"Failed to take screenshot: {e}")

    def check_for_bot_detection(self):
        """Check for common bot detection mechanisms."""
        try:
            # Check for reCAPTCHA
            if self.driver.find_elements(By.TAG_NAME, 'iframe[src*="recaptcha"]'):
                self.metadata["errors"].append("reCAPTCHA detected")
                logging.warning("reCAPTCHA detected")
                return True  # Or some other signal

            # Check for Cloudflare's "I'm Under Attack Mode" (IUAM)
            if "I'm Under Attack Mode" in self.driver.title:
                self.metadata["errors"].append("Cloudflare IUAM detected")
                logging.warning("Cloudflare IUAM detected")
                return True

            #Check for a button with id="challenge-running"
            if self.driver.find_elements(By.ID, 'challenge-running'):
                self.metadata["errors"].append("Detected element with id='challenge-running'")
                logging.warning("Detected element with id='challenge-running'")
                return True

            # Check for a div with id="cf-challenge-running"
            if self.driver.find_elements(By.ID, "cf-challenge-running"):
                self.metadata["errors"].append("Cloudflare challenge detected (cf-challenge-running)")
                logging.warning("Cloudflare challenge detected (cf-challenge-running)")
                return True

            # Generic check for common bot detection strings
            for phrase in ["bot detection", "access denied", "are you a human", "please wait"]:
                if phrase in self.driver.page_source.lower():
                    self.metadata["errors"].append(f"Bot detection phrase found: {phrase}")
                    logging.warning(f"Bot detection phrase found: {phrase}")
                    return True  # Or handle differently


            # Add more checks as needed, based on the sites you are targeting

            return False  # No bot detection found (so far)

        except Exception as e:
            logging.exception("Error during bot detection check")
            self.metadata["errors"].append(f"Bot detection check error: {str(e)}")
            return True  # Treat errors as potential bot detection

# --- Celery Task ---
@celery.task(bind=True)  # Use bind=True to access task instance (self)
def start_capture_task(self, stream_url):
    stream_capture = StreamCapture(stream_url)
    # Store stream_capture in STREAMS *before* starting capture. VERY IMPORTANT
    STREAMS[stream_capture.id] = stream_capture
    try:
        stream_capture.start_capture()
    except Exception as exc:
        # You can retry the task here if you want.
        # raise self.retry(exc=exc, countdown=5)  # Retry in 5 seconds (example)
        return  # Or just return without retrying

    return stream_capture.id  # Return the stream ID