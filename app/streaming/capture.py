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
from selenium.webdriver.remote.webdriver import WebElement
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
        os.makedirs(self.capture_dir, exist_ok=True)
        
        # File paths
        self.video_file = f"{self.capture_dir}/video.mp4"
        self.metadata_file = f"{self.capture_dir}/metadata.json"
        self.debug_dir = f"{self.capture_dir}/debug"
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

    def analyze_page_elements(self):
        """Analyze all elements on the page and log their info"""
        try:
            all_elements = self.driver.find_elements(By.XPATH, "//*")
            element_data = []
            
            for elem in all_elements:
                try:
                    elem_info = {
                        "tag_name": elem.tag_name,
                        "id": elem.get_attribute("id"),
                        "class": elem.get_attribute("class"),
                        "text": elem.text[:100] if elem.text else None,  # Truncate long text
                        "visible": elem.is_displayed(),
                        "location": elem.location,
                    }
                    element_data.append(elem_info)
                except:
                    continue  # Skip elements that can't be analyzed
                    
            self.metadata["page_analysis"]["elements"] = element_data
            logging.info(f"Found {len(element_data)} elements on page")
            
        except Exception as e:
            logging.error(f"Error analyzing page elements: {e}")
            self.metadata["errors"].append(f"Page analysis error: {str(e)}")

    def take_debug_screenshot(self, name):
        """Take a screenshot and save it to the debug directory"""
        try:
            timestamp = datetime.now().strftime("%H%M%S")
            filename = f"{self.debug_dir}/{timestamp}_{name}.png"
            self.driver.save_screenshot(filename)
            self.metadata["debug_screenshots"].append(filename)
            logging.info(f"Saved debug screenshot: {filename}")
            return filename
        except Exception as e:
            logging.error(f"Screenshot error: {e}")
            return None

    def setup_selenium(self):
        """Configure Selenium WebDriver and navigate to stream page"""
        try:
            logging.info("Initializing Selenium WebDriver...")

            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--disable-gpu')  # Added for headless stability
            chrome_options.binary_location = os.getenv('GOOGLE_CHROME_BIN', '/usr/bin/chromium')

            logging.debug("Chrome options configured, creating WebDriver...")
            self.driver = webdriver.Chrome(options=chrome_options)
            logging.info("Selenium WebDriver initialized successfully")

            # Navigate to the stream page
            logging.info(f"Navigating to stream URL: {self.stream_url}")
            self.driver.get(self.stream_url)
            self.take_debug_screenshot("initial_load")

            # Wait for page load and analyze
            time.sleep(5)  # Initial wait
            self.take_debug_screenshot("after_initial_wait")
            self.analyze_page_elements()
            
            logging.info("Checking for common video elements...")
            video_selectors = [
                "video",
                "iframe",
                ".video-player",
                "[aria-label*='video']",
                "[aria-label*='player']",
                "button[aria-label='Play']",
                ".ytp-play-button",  # YouTube
                ".vjs-play-control"  # VideoJS
            ]
            
            found_elements = []
            for selector in video_selectors:
                try:
                    elems = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elems:
                        found_elements.append({
                            "selector": selector,
                            "count": len(elems),
                            "visible": any(e.is_displayed() for e in elems)
                        })
                except Exception as e:
                    logging.error(f"Error checking selector {selector}: {e}")
                    continue

            self.metadata["page_analysis"]["video_elements"] = found_elements
            
            # Take another screenshot before attempting to click play
            self.take_debug_screenshot("before_play_attempt")
            
            # Look for and try to click play button with longer timeout
            try:
                # Try multiple selectors for play button
                play_selectors = [
                    "button[aria-label='Play']",
                    ".ytp-play-button",
                    ".vjs-play-control",
                    "[aria-label*='Play']",
                    "[title*='Play']"
                ]
                
                for selector in play_selectors:
                    try:
                        play_button = WebDriverWait(self.driver, 10).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                        )
                        play_button.click()
                        logging.info(f"Clicked play button with selector: {selector}")
                        self.take_debug_screenshot("after_play_click")
                        break
                    except:
                        continue
                        
            except Exception as e:
                logging.error(f"Play button not found or couldn't be clicked: {e}")
                self.metadata["errors"].append(f"Play button error: {str(e)}")
                # Continue anyway - some streams might autoplay

            # Final pre-capture screenshot
            self.take_debug_screenshot("pre_capture")
            return True

        except Exception as e:
            logging.exception("Selenium setup error")
            self.metadata["errors"].append(f"Selenium setup error: {str(e)}")
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
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
            self.metadata["start_time"] = self.start_time
            self._save_metadata()
            
            logging.info(f"Capture started for {self.stream_url}")

            # Start FFmpeg process
            command = [
                "ffmpeg",
                "-f", "x11grab",
                "-video_size", "1920x1080",
                "-i", os.getenv("DISPLAY", ":99"),
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-t", "60",  # Limit to 60 seconds
                self.video_file
            ]

            logging.debug(f"Running FFmpeg command: {' '.join(command)}")
            self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # Wait for capture to complete or timeout
            start_wait = time.time()
            while time.time() - start_wait < 65:  # Give slightly more than 60s
                if self.process.poll() is not None:
                    break
                time.sleep(1)
                self._update_metadata(duration=int(time.time() - start_wait))
                
            # Take final screenshot
            self.take_debug_screenshot("final_state")
            
            # Check process output
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
        """Stop capturing"""
        try:
            if self.process:
                self.process.terminate()
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    
            if self.driver:
                self.take_debug_screenshot("before_quit")
                self.driver.quit()

            self.end_time = datetime.now()
            duration = (self.end_time - self.start_time).total_seconds() if self.start_time else None
            
            self.metadata["status"] = "completed"
            self.metadata["end_time"] = self.end_time
            self.metadata["duration"] = duration
            self._save_metadata()
            
            logging.info(f"Capture stopped for {self.stream_url}, duration: {duration} seconds")

        except Exception as e:
            logging.exception("Error stopping capture")
            self.metadata["errors"].append(f"Stop error: {str(e)}")
            self.metadata["status"] = "failed"
            self._save_metadata()

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