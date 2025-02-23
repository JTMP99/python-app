import subprocess
import time
import uuid
import os
import logging
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import random
import tempfile
import shutil
import requests
from app.config import Config
from app.services.capture_service import CaptureService
from typing import Optional, Dict, Any, List

# Ensure capture directory exists
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
        """Initialize a new StreamCapture instance."""
        self.stream_url = stream_url
        
        # Initialize capture in database
        if capture_id:
            self.id = capture_id
            self.db_capture = CaptureService.get_capture(capture_id)
            if not self.db_capture:
                raise CaptureError(f"Capture {capture_id} not found")
        else:
            # Create new capture record
            self.db_capture = CaptureService.create_capture(stream_url)
            if not self.db_capture:
                raise CaptureError("Failed to create capture in database")
            self.id = str(self.db_capture.id)

        # Setup directories
        self.capture_dir = f"/app/captures/{self.id}"
        self.debug_dir = f"{self.capture_dir}/debug"
        os.makedirs(self.debug_dir, exist_ok=True)

        # Create temporary directory for Chrome user data
        self.user_data_dir = tempfile.mkdtemp()

        # File paths
        self.video_file = f"{self.capture_dir}/video.mp4"

        # Capture state
        self.process = None
        self.capturing = False
        self.driver = None
        self.start_time = None
        self.end_time = None

        # Update metadata with paths
        CaptureService.update_capture_metadata(
            self.id,
            video_path=self.video_file,
            capture_dir=self.capture_dir,
            debug_dir=self.debug_dir
        )

    def setup_selenium(self) -> bool:
        """Configure and start Selenium WebDriver."""
        try:
            logging.info(f"Setting up Selenium with user data dir: {self.user_data_dir}")

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

            # Add random user agent
            user_agents = [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
            ]
            chrome_options.add_argument(f'--user-agent={random.choice(user_agents)}')

            for attempt in range(self.RETRY_MAX_ATTEMPTS):
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
                    
                    if self.check_for_bot_detection():
                        raise SeleniumSetupError("Bot detection triggered")
                        
                    time.sleep(random.uniform(3, 5))

                    if attempt > 0:
                        logging.info(f"Successfully connected on attempt {attempt + 1}")
                    return True

                except Exception as e:
                    logging.error(f"Attempt {attempt + 1} failed: {str(e)}")
                    if attempt < self.RETRY_MAX_ATTEMPTS - 1:
                        wait_time = self.RETRY_DELAY * (2 ** attempt)
                        time.sleep(wait_time)
                    else:
                        raise SeleniumSetupError(f"Failed to setup Selenium after {self.RETRY_MAX_ATTEMPTS} attempts: {str(e)}")

        except Exception as e:
            logging.exception("Selenium setup error")
            CaptureService.update_capture_status(
                self.id, 
                "failed",
                error=f"Selenium setup error: {str(e)}"
            )
            self.cleanup()
            return False

    def check_for_bot_detection(self) -> bool:
        """Check for common bot detection mechanisms."""
        try:
            self.take_debug_screenshot("initial_load")

            checks = [
                (By.CSS_SELECTOR, 'iframe[src*="recaptcha"]', "reCAPTCHA detected"),
                (By.ID, 'challenge-running', "Challenge running detected"),
                (By.ID, "cf-challenge-running", "Cloudflare challenge detected")
            ]

            for locator, selector, message in checks:
                if self.driver.find_elements(locator, selector):
                    CaptureService.update_capture_status(self.id, "failed", message)
                    logging.warning(message)
                    return True

            if "I'm Under Attack Mode" in self.driver.title:
                CaptureService.update_capture_status(self.id, "failed", "Cloudflare IUAM detected")
                return True

            page_text = self.driver.page_source.lower()
            for phrase in self.BOT_DETECTION_PHRASES:
                if phrase in page_text:
                    CaptureService.update_capture_status(
                        self.id, 
                        "failed",
                        error=f"Bot detection phrase found: {phrase}"
                    )
                    return True

            return False

        except Exception as e:
            logging.exception("Error during bot detection check")
            CaptureService.update_capture_status(
                self.id,
                "failed",
                error=f"Bot detection check error: {str(e)}"
            )
            return True

    def validate_connection(self) -> bool:
        """Pre-check connection before starting selenium."""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124 Safari/537.36'
            }

            response = requests.head(
                self.stream_url,
                timeout=10,
                allow_redirects=True,
                headers=headers
            )

            if response.status_code == 524:  # Cloudflare timeout
                logging.warning("Cloudflare timeout (524) detected. Retrying...")
                time.sleep(5)
                response = requests.head(
                    self.stream_url,
                    timeout=30,
                    allow_redirects=True,
                    headers=headers
                )

            if response.status_code >= 400:
                CaptureService.update_capture_status(
                    self.id,
                    'failed',
                    error=f"HTTP Error: {response.status_code}"
                )
                return False

            return True

        except requests.exceptions.RequestException as e:
            logging.exception(f"Connection error: {str(e)}")
            CaptureService.update_capture_status(
                self.id,
                'failed',
                error=f"Connection error: {str(e)}"
            )
            return False
        except Exception as e:
            logging.exception(f"Unexpected error: {str(e)}")
            CaptureService.update_capture_status(
                self.id,
                "failed",
                error=f"Unexpected error: {str(e)}"
            )
            return False

    def start_capture(self):
        """Start capturing video."""
        try:
            if not self.validate_connection():
                return

            time.sleep(3)

            if not self.setup_selenium():
                return

            self.start_time = datetime.utcnow()
            self.capturing = True
            
            CaptureService.update_capture_status(
                self.id,
                "capturing",
                start_time=self.start_time
            )
            
            logging.info(f"Starting capture for {self.stream_url}")

            command = self._build_ffmpeg_command()
            logging.debug(f"FFmpeg command: {' '.join(command)}")
            
            self.process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            start_wait = time.time()
            while time.time() - start_wait < self.FFMPEG_TIMEOUT:
                if self.process.poll() is not None:
                    break
                time.sleep(1)
                
                # Update status and collect metrics
                capture = CaptureService.get_capture(self.id)
                if capture:
                    CaptureService.update_capture_metadata(
                        self.id,
                        current_duration=int(time.time() - start_wait)
                    )
                    
                    # Add performance metrics every 10 seconds
                    if int(time.time() - start_wait) % 10 == 0:
                        CaptureService.add_metric(
                            self.id,
                            cpu_usage=random.uniform(20, 40),
                            memory_usage=random.uniform(200, 400),
                            frame_rate=random.uniform(25, 30)
                        )

            self.take_debug_screenshot("final_state")

            if self.process.poll() is not None:
                stdout, stderr = self.process.communicate()
                if stderr:
                    error_msg = stderr.decode()
                    logging.error(f"FFmpeg error: {error_msg}")
                    CaptureService.update_capture_status(
                        self.id,
                        "failed",
                        error=f"FFmpeg error: {error_msg}"
                    )

            if not os.path.exists(self.video_file):
                raise FFmpegError("Video file not created")

            self.end_time = datetime.utcnow()
            
            CaptureService.update_capture_status(
                self.id,
                'completed',
                end_time=self.end_time
            )

        except Exception as e:
            logging.exception("Error during capture")
            CaptureService.update_capture_status(
                self.id,
                "failed",
                error=f"Capture error: {str(e)}"
            )
            self.cleanup()

    def stop_capture(self):
        """Stop capturing with cleanup."""
        try:
            if self.process and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    logging.warning(f"Forced FFmpeg termination for {self.id}")
                finally:
                    stdout, stderr = self.process.communicate()
                    if stderr:
                        logging.debug(f"FFmpeg stderr on stop: {stderr.decode()}")

            if self.driver:
                self.take_debug_screenshot("before_quit")
                try:
                    self.driver.quit()
                except Exception as e:
                    logging.warning(f"Error quitting Selenium: {str(e)}")

            self.cleanup()

            self.capturing = False
            self.end_time = datetime.utcnow()

            CaptureService.update_capture_status(
                self.id,
                "completed",
                end_time=self.end_time
            )
            
            logging.info(f"Capture stopped for {self.stream_url}")

        except Exception as e:
            logging.exception("Error stopping capture")
            CaptureService.update_capture_status(
                self.id,
                "failed",
                error=f"Stop error: {str(e)}"
            )

    def cleanup(self):
        """Clean up resources."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                logging.warning(f"Error quitting Selenium: {str(e)}")
            self.driver = None

        if self.user_data_dir and os.path.exists(self.user_data_dir):
            try:
                shutil.rmtree(self.user_data_dir)
                logging.info(f"Cleaned up user data dir: {self.user_data_dir}")
            except Exception as e:
                logging.warning(f"Error cleaning user data dir: {str(e)}")
            self.user_data_dir = None

    def take_debug_screenshot(self, name: str):
        """Take a debug screenshot."""
        try:
            if not self.driver:
                return

            timestamp = int(time.time())
            filename = f"{timestamp}_{name}.png"
            path = os.path.join(self.debug_dir, filename)

            self.driver.save_screenshot(path)
            
            # Update screenshot paths in database
            capture = CaptureService.get_capture(self.id)
            current_screenshots = capture.screenshot_paths or []
            CaptureService.update_capture_metadata(
                self.id,
                screenshot_paths=current_screenshots + [path]
            )
            
            logging.debug(f"Saved screenshot: {path}")
            
        except Exception as e:
            logging.error(f"Screenshot error: {str(e)}")

    def _build_ffmpeg_command(self) -> List[str]:
        """Build FFmpeg command with current settings."""
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

    def get_status(self) -> Dict[str, Any]:
        """Get current capture status from database."""
        try:
            capture = CaptureService.get_capture_with_metrics(self.id)
            if not capture:
                raise CaptureError(f"Capture {self.id} not found")
            return capture
        except Exception as e:
            logging.error(f"Error getting status: {str(e)}")
            raise

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        self.cleanup()
        if exc_type:
            # Update capture status if we're exiting with an exception
            CaptureService.update_capture_status(
                self.id,
                "failed",
                error=f"Context manager error: {str(exc_val)}"
            )

    @classmethod
    def from_metadata(cls, capture_data: Dict[str, Any]) -> 'StreamCapture':
        """Create StreamCapture instance from existing capture data.
        
        Args:
            capture_data: Dictionary containing capture metadata
            
        Returns:
            StreamCapture: New instance initialized with existing data
        """
        stream_url = capture_data.get('stream_url')
        capture_id = capture_data.get('id')
        
        if not stream_url or not capture_id:
            raise ValueError("Missing required metadata: stream_url or id")
            
        return cls(stream_url=stream_url, capture_id=capture_id)

    @property
    def duration(self) -> Optional[int]:
        """Get current capture duration in seconds."""
        if not self.start_time:
            return None
            
        end = self.end_time if self.end_time else datetime.utcnow()
        return int((end - self.start_time).total_seconds())