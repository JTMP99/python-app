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
from selenium.webdriver.common.action_chains import ActionChains
import random
import tempfile
import shutil
from app.config import Config

# Ensure directories exist
os.makedirs("/app/logs", exist_ok=True)
os.makedirs("/app/captures", exist_ok=True)

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
        self.capture_dir = f"/app/captures/{self.id}"
        self.debug_dir = f"{self.capture_dir}/debug"
        
        # Create a unique temporary directory for Chrome user data
        self.user_data_dir = tempfile.mkdtemp()
        
        # File paths
        self.video_file = f"{self.capture_dir}/video.mp4"
        self.metadata_file = f"{self.capture_dir}/metadata.json"
        os.makedirs(self.debug_dir, exist_ok=True)

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
            "errors": [],
            "page_analysis": {},
            "debug_screenshots": []
        }
        self._save_metadata()

    def setup_selenium(self):
        try:
            logging.info(f"Using temporary user data directory: {self.user_data_dir}")

            chrome_options = Options()
            chrome_options.add_argument(f'--user-data-dir={self.user_data_dir}')
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_argument('--disable-infobars')
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            chrome_options.binary_location = Config.GOOGLE_CHROME_BIN

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
                    actions = ActionChains(self.driver)
                    actions.move_by_offset(random.randint(10, 50), random.randint(10, 50))
                    actions.perform()
                    self.driver.get(self.stream_url)
                    self.check_for_bot_detection()
                    time.sleep(random.uniform(3, 5))
                    if attempt > 0:
                        logging.info(f"Successfully connected on attempt {attempt + 1}")
                    break
                except Exception as e:
                    logging.error(f"Attempt {attempt + 1} failed: {e}")
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (2 ** attempt)
                        time.sleep(wait_time)
                    else:
                        raise
            return True
        except Exception as e:
            logging.exception("Selenium setup error")
            self.metadata["errors"].append(f"Selenium setup error: {str(e)}")
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
                "-f", "x11grab",
                "-video_size", "1920x1080",
                "-i", os.getenv("DISPLAY", ":99"),
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-t", "60",
                self.video_file
            ]

            logging.debug(f"Running FFmpeg command: {' '.join(command)}")
            self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            start_wait = time.time()
            while time.time() - start_wait < 65:
                if self.process.poll() is not None:
                    break
                time.sleep(1)
                self._update_metadata(duration=int(time.time() - start_wait))

            self.take_debug_screenshot("final_state")

            if self.process.poll() is not None:
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
            self.stop_capture()

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
                json.dump(self.metadata, f, indent=2, default=str)
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

    # Placeholder for methods assumed to exist based on usage
    def take_debug_screenshot(self, name: str):
        """Take a screenshot for debugging (implementation assumed)"""
        try:
            screenshot_path = f"{self.debug_dir}/{name}_{int(time.time())}.png"
            self.driver.save_screenshot(screenshot_path)
            self.metadata["debug_screenshots"].append(screenshot_path)
            logging.debug(f"Screenshot saved: {screenshot_path}")
        except Exception as e:
            logging.error(f"Failed to take screenshot: {e}")

    def check_for_bot_detection(self):
        """Check for bot detection (implementation assumed)"""
        pass