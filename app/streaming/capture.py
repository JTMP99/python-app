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
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import random
import tempfile
import shutil
import requests
from urllib.parse import urlparse
from app.config import Config

# Ensure directories exist
os.makedirs("/app/captures", exist_ok=True)
os.makedirs("/app/logs", exist_ok=True)

class StreamCapture:
    def __init__(self, stream_url: str):
        self.stream_url = stream_url
        self.id = str(uuid.uuid4())
        self.capture_dir = f"/app/captures/{self.id}"
        self.debug_dir = f"{self.capture_dir}/debug"
        
        # Create directories
        os.makedirs(self.capture_dir, exist_ok=True)
        os.makedirs(self.debug_dir, exist_ok=True)

        # Create a unique temporary directory for Chrome user data
        self.user_data_dir = tempfile.mkdtemp()

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
            "errors": [],
            "page_analysis": {},
            "debug_screenshots": []
        }
        self._save_metadata()

    def validate_connection(self):
        """Pre-check connection before starting selenium"""
        try:
            # Parse domain from URL
            parsed = urlparse(self.stream_url)
            domain = parsed.netloc
            
            # First try a simple HEAD request to the domain
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            
            session = requests.Session()
            
            # Try HTTPS first
            try:
                probe_url = f"https://{domain}"
                response = session.head(probe_url, headers=headers, timeout=10, allow_redirects=True)
                logging.info(f"Probe response: {response.status_code}")
                
                if response.status_code == 524:
                    # If we get a 524, try with a longer timeout
                    time.sleep(5)  # Wait before retry
                    response = session.head(probe_url, headers=headers, timeout=30)
                
                if response.status_code >= 400:
                    raise Exception(f"Domain probe failed with status {response.status_code}")
                    
            except requests.RequestException as e:
                logging.warning(f"HTTPS probe failed: {e}")
                # Try HTTP fallback
                probe_url = f"http://{domain}"
                response = session.head(probe_url, headers=headers, timeout=10)
                
            return True
                
        except Exception as e:
            logging.error(f"Connection validation failed: {e}")
            self.metadata["errors"].append(f"Connection validation failed: {str(e)}")
            return False

    def setup_selenium(self):
        try:
            logging.info(f"Using temporary user data directory: {self.user_data_dir}")

            chrome_options = Options()
            chrome_options.add_argument(f'--user-data-dir={self.user_data_dir}')
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            
            # Enhanced anti-detection options
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_argument('--disable-infobars')
            chrome_options.add_argument('--ignore-certificate-errors')
            chrome_options.add_argument('--disable-web-security')
            chrome_options.add_argument('--allow-running-insecure-content')
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            chrome_options.binary_location = Config.GOOGLE_CHROME_BIN

            # Randomize window size
            width = random.randint(1800, 1920)
            height = random.randint(1000, 1080)
            chrome_options.add_argument(f'--window-size={width},{height}')

            # Rotate user agents
            user_agents = [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            ]
            chrome_options.add_argument(f'--user-agent={random.choice(user_agents)}')

            max_retries = 3
            retry_delay = 2

            for attempt in range(max_retries):
                try:
                    self.driver = webdriver.Chrome(options=chrome_options)
                    
                    # Add CDP commands for better stealth
                    self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                        'source': '''
                            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                            window.chrome = { runtime: {} };
                        '''
                    })

                    # Set extra headers
                    self.driver.execute_cdp_cmd('Network.setExtraHTTPHeaders', {
                        'headers': {
                            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                            'Accept-Language': 'en-US,en;q=0.5',
                            'Accept-Encoding': 'gzip, deflate, br',
                            'Connection': 'keep-alive',
                            'Upgrade-Insecure-Requests': '1',
                            'Sec-Fetch-Dest': 'document',
                            'Sec-Fetch-Mode': 'navigate',
                            'Sec-Fetch-Site': 'none',
                            'Sec-Fetch-User': '?1',
                            'DNT': '1'
                        }
                    })

                    # Enable request/response monitoring
                    self.driver.execute_cdp_cmd('Network.enable', {})
                    
                    # Increased page load timeout
                    self.driver.set_page_load_timeout(30)
                    
                    # Random mouse movements before loading page
                    actions = ActionChains(self.driver)
                    actions.move_by_offset(random.randint(10, 50), random.randint(10, 50))
                    actions.perform()

                    # Load the page
                    self.driver.get(self.stream_url)
                    
                    # Take screenshot
                    self.take_debug_screenshot("initial_load")
                    
                    # Check for blocks
                    if self.check_for_blocks():
                        raise Exception("Detected access blocking")

                    time.sleep(random.uniform(3, 5))

                    if attempt > 0:
                        logging.info(f"Successfully connected on attempt {attempt + 1}")
                    break

                except Exception as e:
                    logging.error(f"Attempt {attempt + 1} failed: {e}")
                    self.take_debug_screenshot(f"error_attempt_{attempt}")
                    
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

    def check_for_blocks(self):
        """Comprehensive check for various blocking mechanisms"""
        try:
            # Check page source for error indicators
            page_source = self.driver.page_source.lower()
            error_indicators = {
                'cloudflare': ['cloudflare', 'checking your browser', 'challenge-running', 'cf-', 'ray id:', 'timeout occurred'],
                'bot_detection': ['bot detected', 'automated browser', 'recaptcha', 'captcha', 'are you human'],
                'timeout': ['timeout', 'timed out', 'no response', 'failed to respond'],
                'access_denied': ['access denied', 'forbidden', '403', 'blocked', 'unauthorized']
            }

            for category, indicators in error_indicators.items():
                for indicator in indicators:
                    if indicator in page_source:
                        self.metadata["errors"].append(f"{category}: {indicator} detected")
                        logging.warning(f"Blocking detected: {category} - {indicator}")
                        return True

            # Check HTTP status code
            try:
                status_code = self.driver.execute_script(
                    "return window.performance.getEntries()[0].responseStatus"
                )
                if status_code and status_code >= 400:
                    self.metadata["errors"].append(f"HTTP error: {status_code}")
                    return True
            except:
                pass

            return False

        except Exception as e:
            logging.error(f"Error during block check: {e}")
            return True

    def start_capture(self) -> None:
        """Start capturing video with pre-validation"""
        try:
            # First validate basic connectivity
            if not self.validate_connection():
                self.metadata["status"] = "failed"
                self.metadata["errors"].append("Failed initial connection check")
                self._save_metadata()
                return

            # Add delay after validation
            time.sleep(3)

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

            # Start FFmpeg with reduced initial load
            command = [
                "ffmpeg",
                "-f", "x11grab",
                "-video_size", "1280x720",  # Start with lower resolution
                "-framerate", "15",  # Lower framerate to start
                "-i", os.getenv("DISPLAY", ":99"),
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-tune", "zerolatency",
                "-t", "60",
                self.video_file
            ]

            logging.debug(f"Running FFmpeg command: {' '.join(command)}")
            self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # Poll with better error handling
            start_wait = time.time()
            while time.time() - start_wait < 65:
                if self.process.poll() is not None:
                    break
                
                # Take progress screenshots every 10 seconds
                if int(time.time() - start_wait) % 10 == 0:
                    self.take_debug_screenshot(f"progress_{int(time.time() - start_wait)}")
                
                time.sleep(1)
                self._update_metadata(duration=int(time.time() - start_wait))

            self.take_debug_screenshot("final_state")

            if self.process.poll() is not None:
                stdout, stderr = self.process.communicate()
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
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    logging.warning(f"Forced termination of FFmpeg process for capture {self.id}")
                finally:
                    stdout, stderr = self.process.communicate()
                    if stderr:
                        logging.debug(f"FFmpeg stderr on stop: {stderr.decode()}")

            # Quit Selenium driver
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
                self.user_data_dir = None

            # Update metadata
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

    def take_debug_screenshot(self, name: str):
        """Take a screenshot for debugging and add its path to metadata."""
        try:
            screenshot_path = f"{self.debug_dir}/{name}_{int(time.time())}.png"
            self.driver.save_screenshot(screenshot_path)
            self.metadata["debug_screenshots"].append(screenshot_path)
            logging.debug(f"Screenshot saved: {screenshot_path}")
        except Exception as e:
            logging.error(f"Failed to take screenshot: {e}")