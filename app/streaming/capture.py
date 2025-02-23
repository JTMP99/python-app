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
from selenium.webdriver.common.by import By  # Import By for element selection
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import random
import tempfile
import shutil
import requests  # For pre-flight connection check
from app.config import Config  # Import the Config class

# We're NOT using Celery, so no Celery imports

# STREAMS is now managed by the Flask app, so import it at the top-level
from streams import STREAMS



class StreamCapture:
    def __init__(self, stream_url: str):
        self.stream_url = stream_url
        self.id = str(uuid.uuid4())  # Unique ID for each capture
        self.capture_dir = f"/app/captures/{self.id}"  # Main capture directory
        self.debug_dir = f"{self.capture_dir}/debug"  # Debug screenshots
        self.temp_dir = tempfile.mkdtemp(prefix="streamcapture_") # Temp dir
        self.user_data_dir = os.path.join(self.temp_dir, "chrome-data")  # Chrome user data

        # File paths
        self.video_file = os.path.join(self.capture_dir, "video.mp4")
        self.metadata_file = os.path.join(self.capture_dir, "metadata.json")

        # Ensure directories exist
        os.makedirs(self.capture_dir, exist_ok=True)
        os.makedirs(self.debug_dir, exist_ok=True)  # Debug directory
        os.makedirs(self.user_data_dir, exist_ok=True)  # User data directory


        # Capture state
        self.process = None  # FFmpeg process
        self.capturing = False
        self.driver = None  # Selenium WebDriver instance
        self.start_time = None
        self.end_time = None

        # Initialize metadata.  Store *everything* we might need.
        self.metadata = {
            "id": self.id,
            "stream_url": stream_url,
            "start_time": None,
            "end_time": None,
            "duration": None,
            "status": "initialized",  # Initial status
            "video_path": self.video_file,
            "errors": [],
            "page_analysis": {},  # Placeholder for page analysis (future)
            "debug_screenshots": []  # List of screenshot paths
        }
        self._save_metadata()  # Save initial metadata



    def validate_connection(self):
        """Pre-check connection before starting selenium"""
        try:
            # First try a simple HEAD request
            response = requests.head(self.stream_url,
                                     timeout=10,
                                     allow_redirects=True,
                                     headers={
                                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0'
                                     })

            if response.status_code == 524:  # Cloudflare timeout
                time.sleep(5)  # Wait before retry
                response = requests.head(self.stream_url,
                                        timeout=30,  # Longer timeout
                                        allow_redirects=True)

            if response.status_code >= 400:
                self.metadata["errors"].append(f"HTTP error: {response.status_code}")
                return False

            return True
        except Exception as e:
            self.metadata["errors"].append(f"Connection error: {str(e)}")
            return False


    def setup_selenium(self):
        """Sets up the Selenium WebDriver with appropriate options."""
        try:
            logging.info(f"Using temporary user data directory: {self.user_data_dir}")

            chrome_options = Options()
            chrome_options.add_argument(f'--user-data-dir={self.user_data_dir}')
            chrome_options.add_argument('--headless')  # Run Chrome in headless mode
            chrome_options.add_argument('--no-sandbox')  # Necessary in Docker
            chrome_options.add_argument('--disable-dev-shm-usage') # Overcome limited resource problems
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_argument('--disable-infobars')  # Disable info bars
            chrome_options.add_argument('--ignore-certificate-errors') # Insecure, but useful for testing
            chrome_options.add_argument('--disable-web-security') # ONLY for trusted sources.  DANGEROUS.
            chrome_options.add_argument('--allow-running-insecure-content') # DANGEROUS
            chrome_options.binary_location = Config.GOOGLE_CHROME_BIN

            # Randomize window size (within reasonable bounds)
            width = random.randint(1280, 1920)  # Reduced min width
            height = random.randint(720, 1080)   # Reduced min height
            chrome_options.add_argument(f'--window-size={width},{height}')

            # Rotate user agents (add more as needed)
            user_agents = [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
            ]
            chrome_options.add_argument(f'--user-agent={random.choice(user_agents)}')


            # Set up retries for connection issues
            max_retries = 3
            retry_delay = 2  # seconds

            for attempt in range(max_retries):
                try:
                    self.driver = webdriver.Chrome(options=chrome_options)

                     # Additional stealth techniques
                    self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                        'source': '''
                            Object.defineProperty(navigator, 'webdriver', {
                                get: () => undefined
                            });
                            Object.defineProperty(navigator, 'plugins', {
                                get: () => [1, 2, 3, 4, 5]
                            });
                            window.chrome = { runtime: {} };
                        '''
                    })

                    # Set some extra headers to look less like a bot
                    self.driver.execute_cdp_cmd('Network.setExtraHTTPHeaders', {
                        'headers': {
                            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                            'Accept-Language': 'en-US,en;q=0.5',
                            'Accept-Encoding': 'gzip, deflate, br',
                            'Connection': 'keep-alive',
                            'Upgrade-Insecure-Requests': '1'
                        }
                    })
                    self.driver.execute_cdp_cmd('Network.enable', {})  # Enable network events
                    self.driver.set_page_load_timeout(30) #timeout

                    # Introduce small, random mouse movements.
                    actions = ActionChains(self.driver)
                    actions.move_by_offset(random.randint(10, 50), random.randint(10, 50))
                    actions.perform()


                    self.driver.get(self.stream_url)
                    self.take_debug_screenshot("initial_load") #Take screenshot
                    if self.check_for_blocks():  # Check for bot detection
                        raise Exception("Access blocked") # Raise a generic exception

                    time.sleep(random.uniform(3, 5)) # wait
                    break # Success

                except Exception as e:
                    logging.error(f"Attempt {attempt + 1} failed: {e}")
                    self.take_debug_screenshot(f"error_attempt_{attempt}")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay * (2 ** attempt))  # Exponential backoff
                    else:
                        raise  # Re-raise exception after max retries

            return True # Setup successful

        except Exception as e:
            logging.exception("Selenium setup error")
            self.metadata["errors"].append(f"Selenium setup error: {str(e)}")
            self.cleanup() #Clean up.
            return False

    def check_for_blocks(self):
        """Checks for common bot detection mechanisms (placeholders)"""
        try:
            # Check for reCAPTCHA
            if self.driver.find_elements(By.TAG_NAME, 'iframe[src*="recaptcha"]'):
                self.metadata["errors"].append("reCAPTCHA detected")
                return True  # Or some other signal

            # Check for Cloudflare's "I'm Under Attack Mode" (IUAM)
            if "I'm Under Attack Mode" in self.driver.title:
                self.metadata["errors"].append("Cloudflare IUAM detected")
                return True
            
            #Check for a button with id="challenge-running"
            if self.driver.find_elements(By.ID, 'challenge-running'):
                self.metadata["errors"].append("Detected element with id='challenge-running'")
                return True

            # Check for a div with id="cf-challenge-running"
            if self.driver.find_elements(By.ID, "cf-challenge-running"):
                self.metadata["errors"].append("Cloudflare challenge detected (cf-challenge-running)")
                return True

            # Add more checks here, based on common patterns.  This is an
            # ongoing process; you'll need to adapt to the specific sites
            # you're targeting.

            return False  # No blocking detected (so far)
        except Exception as e:
            logging.error(f"Error during block check: {e}")
            return True #Treat errors as blocks

    def start_capture(self):
        """Starts the video capture process."""
        try:

            if not self.validate_connection():
                 self._update_status("failed", "Connection validation failed")
                 return

            time.sleep(3)

            if not self.setup_selenium():
                self._update_status("failed", "Setup failed")
                return

            self.start_time = datetime.now()
            self.capturing = True
            self._update_status("capturing") # update metadata
            self.metadata["start_time"] = self.start_time.isoformat()

            # FFmpeg command (simplified for now, adjust as needed)
            command = [
                "ffmpeg",
                "-f", "x11grab",  # Input format (X11 screen grabbing)
                "-video_size", "1280x720", # Example size
                "-framerate", "15", # Lower framerate
                "-i", os.getenv("DISPLAY", ":99"), # Get display
                "-c:v", "libx264", # Video codec
                "-preset", "ultrafast", # Balance of speed and quality
                "-tune", "zerolatency", #For low-latency
                "-t", "60", #Timeout
                self.video_file #Output file
            ]
            logging.info(f"Running FFmpeg command: {' '.join(command)}") #log
            self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # Monitor the FFmpeg process, but don't block *indefinitely*.
            start_wait = time.time()
            while time.time() - start_wait < 65:  # Wait slightly longer than FFmpeg timeout
                if self.process.poll() is not None:
                    break  # FFmpeg process finished (or crashed)
                if int(time.time()-start_wait) % 10 == 0:
                    self.take_debug_screenshot(f"progress_{int(time.time() - start_wait)}")
                time.sleep(1) # check every second
                self._update_metadata(duration=int(time.time() - start_wait))

            self.take_debug_screenshot("final_state")

            # Check if FFmpeg exited cleanly
            if self.process.poll() is not None:
                stdout, stderr = self.process.communicate() # Get the output
                if stderr:
                    logging.error(f"FFmpeg stderr: {stderr.decode()}")
                    self.metadata["errors"].append(f"FFmpeg error: {stderr.decode()}")

            # check and make sure the file was created
            if not os.path.exists(self.video_file):
                raise Exception("Video file not created") #Raise if file not made


        except Exception as e:
            logging.exception("Error during stream capture")  # Detailed error logging
            self._update_status("failed", str(e))
            self.cleanup()

    def stop_capture(self):
        """Stops the capture and cleans up resources."""
        try:
            if self.process and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=10)  # Give it some time to terminate gracefully
                except subprocess.TimeoutExpired:
                    self.process.kill()  # Forcefully kill it if it doesn't stop
                    logging.warning(f"FFmpeg process for capture {self.id} had to be killed.")
                finally:
                    stdout, stderr = self.process.communicate()
                    if stderr:
                        logging.debug(f"FFmpeg stderr on stop: {stderr.decode()}")


            if self.driver:
                self.take_debug_screenshot("before_quit")
                self.driver.quit()
                self.driver = None

            self.cleanup() #Clean up temp files

            self.end_time = datetime.now()
            duration = (self.end_time - self.start_time).total_seconds() if self.start_time else None
            self._update_status("completed")
            self._update_metadata(
                end_time=self.end_time.isoformat() if self.end_time else None,
                duration=duration
                )
            logging.info(f"Capture stopped for {self.stream_url}, duration: {duration} seconds")
        except Exception as e:
            logging.exception("Error stopping capture")
            self._update_status("failed", str(e))
            self.cleanup()  # Clean up even on error

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

        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
                logging.info(f"Deleted temp directory: {self.temp_dir}")
            except Exception as e:
                logging.warning(f"Error deleting temp dir: {e}")
            self.temp_dir = None


    def _update_status(self, status: str, error: str = None):
        """Helper function to update the status and save metadata."""
        self.metadata["status"] = status
        if error:
            self.metadata["errors"].append({"time": datetime.now().isoformat(), "error": error})
        self._save_metadata()

    def _update_metadata(self, **kwargs):
        """Updates the metadata with provided keyword arguments and saves it."""
        self.metadata.update(kwargs)
        self._save_metadata()

    def _save_metadata(self):
        """Saves the current metadata to the metadata.json file."""
        try:
            with open(self.metadata_file, 'w') as f:
                json.dump(self.metadata, f, indent=2, default=str)
            logging.debug(f"Metadata saved for {self.id}")
        except Exception as e:
            logging.error(f"Failed to save metadata: {e}")


    def get_status(self):
        """Returns the current metadata."""
        return self.metadata

    def take_debug_screenshot(self, name: str):
        """Take a debug screenshot"""
        try:
            if not self.driver:
                return #Dont take screenshot if driver not running

            timestamp = int(time.time())
            filename = f"{timestamp}_{name}.png"
            path = os.path.join(self.debug_dir, filename)

            self.driver.save_screenshot(path)
            self.metadata["debug_screenshots"] = self.metadata.get("debug_screenshots", [])
            self.metadata["debug_screenshots"].append(path)
            self._save_metadata()

        except Exception as e:
            logging.error(f"Screenshot error: {e}")