import uuid
import json
import os
import shutil
import logging
import random
import time
from datetime import datetime
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
import subprocess
from app.config import Config

# Ensure directories exist
os.makedirs("/app/captures", exist_ok=True)
os.makedirs("/app/logs", exist_ok=True)

class StreamCapture:
    def __init__(self, stream_url: str):
        self.stream_url = stream_url
        self.id = str(uuid.uuid4())
        # Base directory structure
        self.base_dir = os.path.join("/app/captures", self.id)
        self.debug_dir = os.path.join(self.base_dir, "debug")
        self.temp_dir = os.path.join(self.base_dir, "temp")
        self.user_data_dir = os.path.join(self.temp_dir, "chrome-data")
        self.video_file = os.path.join(self.base_dir, "video.mp4")
        self.metadata_file = os.path.join(self.base_dir, "metadata.json")

        # State tracking
        self.driver = None
        self.process = None
        self.capturing = False
        self.start_time = None
        
        # Initialize metadata
        self.metadata = {
            "id": self.id,
            "stream_url": stream_url,
            "status": "initializing",
            "errors": [],
            "created_at": datetime.now().isoformat(),
            "video_path": self.video_file,
            "debug_screenshots": []
        }
        
        self.setup_directories()
        self._save_metadata()

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
        try:
            chrome_options = Options()
            chrome_options.add_argument(f'--user-data-dir={self.user_data_dir}')
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_argument('--disable-infobars')
            chrome_options.add_argument('--ignore-certificate-errors')
            chrome_options.add_argument('--disable-web-security')
            chrome_options.add_argument('--allow-running-insecure-content')
            chrome_options.binary_location = Config.GOOGLE_CHROME_BIN

            # Random window size
            width = random.randint(1800, 1920)
            height = random.randint(1000, 1080)
            chrome_options.add_argument(f'--window-size={width},{height}')

            # Rotate user agents
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
                    
                    # Better stealth
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
                            'Upgrade-Insecure-Requests': '1'
                        }
                    })

                    self.driver.execute_cdp_cmd('Network.enable', {})
                    self.driver.set_page_load_timeout(30)

                    # Random mouse movement
                    actions = ActionChains(self.driver)
                    actions.move_by_offset(random.randint(10, 50), random.randint(10, 50))
                    actions.perform()

                    self.driver.get(self.stream_url)
                    self.take_debug_screenshot("initial_load")
                    
                    if self.check_for_blocks():
                        raise Exception("Access blocked")

                    time.sleep(random.uniform(3, 5))
                    break

                except Exception as e:
                    logging.error(f"Attempt {attempt + 1} failed: {e}")
                    self.take_debug_screenshot(f"error_attempt_{attempt}")
                    
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay * (2 ** attempt))
                    else:
                        raise

            return True

        except Exception as e:
            logging.exception("Selenium setup error")
            self.metadata["errors"].append(f"Selenium setup error: {str(e)}")
            self.cleanup()
            return False

    def check_for_blocks(self):
        """Check for blocking mechanisms"""
        try:
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
                        return True

            return False

        except Exception as e:
            logging.error(f"Error during block check: {e}")
            return True

    @classmethod
    def from_metadata(cls, metadata):
        """Create instance from stored metadata"""
        instance = cls(metadata["stream_url"])
        instance.id = metadata["id"]
        instance.metadata = metadata
        return instance

    def setup_directories(self):
        """Set up directory structure"""
        os.makedirs(self.base_dir, exist_ok=True)
        os.makedirs(self.debug_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)

    def start_capture(self):
        """Start capturing video"""
        try:
            if not self.validate_connection():
                self._update_status("failed", "Connection validation failed")
                return

            time.sleep(3)  # Cool down

            if not self.setup_selenium():
                self._update_status("failed", "Setup failed")
                return

            self.start_time = datetime.now()
            self._update_status("capturing")
            self.metadata["start_time"] = self.start_time.isoformat()

            # Start FFmpeg
            command = [
                "ffmpeg",
                "-f", "x11grab",
                "-video_size", "1280x720",
                "-framerate", "15",
                "-i", os.getenv("DISPLAY", ":99"),
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-tune", "zerolatency",
                "-t", "60",
                self.video_file
            ]

            self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # Monitor process
            start_wait = time.time()
            while time.time() - start_wait < 65:
                if self.process.poll() is not None:
                    break
                
                if int(time.time() - start_wait) % 10 == 0:
                    self.take_debug_screenshot(f"progress_{int(time.time() - start_wait)}")
                
                time.sleep(1)
                self._update_metadata(duration=int(time.time() - start_wait))

            self.take_debug_screenshot("final_state")

            # Check process output
            if self.process.poll() is not None:
                stdout, stderr = self.process.communicate()
                if stderr:
                    logging.error(f"FFmpeg stderr: {stderr.decode()}")
                    self.metadata["errors"].append(f"FFmpeg error: {stderr.decode()}")

            if not os.path.exists(self.video_file):
                raise Exception("Video file not created")

        except Exception as e:
            logging.exception("Capture error")
            self._update_status("failed", str(e))
            self.cleanup()

    def stop_capture(self):
        """Stop capturing"""
        try:
            if self.process:
                self.process.terminate()
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.process.kill()

            self.cleanup()
            
            self.end_time = datetime.now()
            duration = (self.end_time - self.start_time).total_seconds() if self.start_time else None
            
            self._update_status("completed")
            self._update_metadata(
                end_time=self.end_time.isoformat(),
                duration=duration
            )

        except Exception as e:
            logging.exception("Error stopping capture")
            self._update_status("failed", str(e))
            self.cleanup()

    def cleanup(self):
        """Clean up resources"""
        if self.driver:
            try:
                self.take_debug_screenshot("cleanup")
                self.driver.quit()
            except:
                pass
            self.driver = None

        if self.user_data_dir and os.path.exists(self.user_data_dir):
            try:
                shutil.rmtree(self.user_data_dir)
            except:
                pass

    def _update_status(self, status: str, error: str = None):
        """Update status and optionally add error"""
        self.metadata["status"] = status
        if error:
            self.metadata["errors"].append({
                "time": datetime.now().isoformat(),
                "error": error
            })
        self._save_metadata()

    def _update_metadata(self, **kwargs):
        """Update metadata fields"""
        self.metadata.update(kwargs)
        self._save_metadata()

    def _save_metadata(self):
        """Save metadata to file"""
        try:
            with open(self.metadata_file, 'w') as f:
                json.dump(self.metadata, f, indent=2, default=str)
        except Exception as e:
            logging.error(f"Failed to save metadata: {e}")

    def get_status(self):
        """Get current status"""
        return self.metadata

    def take_debug_screenshot(self, name: str):
        """Take a debug screenshot"""
        try:
            if not self.driver:
                return
                
            timestamp = int(time.time())
            filename = f"{timestamp}_{name}.png"
            path = os.path.join(self.debug_dir, filename)
            
            self.driver.save_screenshot(path)
            self.metadata["debug_screenshots"] = self.metadata.get("debug_screenshots", [])
            self.metadata["debug_screenshots"].append(path)
            self._save_metadata()
            
        except Exception as e:
            logging.error(f"Screenshot error: {e}")