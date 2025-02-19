from flask import Flask, jsonify, current_app
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from functools import wraps
import subprocess
import re
import logging
from logging.handlers import RotatingFileHandler
import os
from typing import Tuple, Dict, Any, Optional

# Configuration
class Config:
    CHROME_BINARY_PATHS = ["google-chrome", "chromium", "chromium-browser"]
    SELENIUM_TIMEOUT = 30
    LOG_FILE = "app.log"
    MAX_LOG_SIZE = 10 * 1024 * 1024  # 10MB
    LOG_BACKUP_COUNT = 5
    CHROME_OPTIONS = [
        "--headless",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--window-size=1920,1080"
    ]

def setup_logging(app: Flask) -> None:
    """Configure application logging with rotation."""
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
    )
    
    handler = RotatingFileHandler(
        f"logs/{Config.LOG_FILE}",
        maxBytes=Config.MAX_LOG_SIZE,
        backupCount=Config.LOG_BACKUP_COUNT
    )
    handler.setFormatter(formatter)
    
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)

def create_app() -> Flask:
    """Application factory pattern."""
    app = Flask(__name__)
    setup_logging(app)
    return app

app = create_app()

def error_handler(f):
    """Decorator for consistent error handling across routes."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except WebDriverException as e:
            current_app.logger.error(f"Selenium error: {str(e)}")
            return jsonify({"error": "Browser automation error", "details": str(e)}), 500
        except Exception as e:
            current_app.logger.error(f"Unexpected error: {str(e)}")
            return jsonify({"error": "Internal server error"}), 500
    return wrapper

class BrowserVersionChecker:
    @staticmethod
    def get_chrome_major_version() -> int:
        """Get Chrome/Chromium major version."""
        for cmd in Config.CHROME_BINARY_PATHS:
            try:
                out = subprocess.check_output([cmd, "--version"], 
                                           stderr=subprocess.STDOUT,
                                           timeout=5)
                version_str = out.decode().strip()
                match = re.search(r"(\d+)\.\d+\.\d+\.\d+", version_str)
                if match:
                    return int(match.group(1))
            except (FileNotFoundError, subprocess.CalledProcessError, 
                   subprocess.TimeoutExpired) as e:
                current_app.logger.warning(f"Failed to get version for {cmd}: {str(e)}")
        return -1

    @staticmethod
    def get_chromedriver_major_version() -> int:
        """Get ChromeDriver major version."""
        try:
            out = subprocess.check_output(["chromedriver", "--version"], 
                                       stderr=subprocess.STDOUT,
                                       timeout=5)
            version_str = out.decode().strip()
            match = re.search(r"ChromeDriver\s+(\d+)\.\d+\.\d+\.\d+", version_str)
            if match:
                return int(match.group(1))
        except (FileNotFoundError, subprocess.CalledProcessError, 
               subprocess.TimeoutExpired) as e:
            current_app.logger.warning(f"Failed to get ChromeDriver version: {str(e)}")
        return -1

class SeleniumManager:
    @staticmethod
    def create_driver() -> webdriver.Chrome:
        """Create and configure Chrome WebDriver instance."""
        options = Options()
        for option in Config.CHROME_OPTIONS:
            options.add_argument(option)
        
        driver_manager = ChromeDriverManager()
        driver = webdriver.Chrome(
            service=Service(driver_manager.install()),
            options=options
        )
        driver.set_page_load_timeout(Config.SELENIUM_TIMEOUT)
        return driver

    @staticmethod
    def safe_quit(driver: Optional[webdriver.Chrome]) -> None:
        """Safely quit WebDriver instance."""
        if driver:
            try:
                driver.quit()
            except Exception as e:
                current_app.logger.warning(f"Error quitting driver: {str(e)}")

@app.route("/")
def home() -> str:
    return "Hello from DigitalOcean sample-python with Selenium!"

@app.route("/versions")
@error_handler
def versions() -> Tuple[Dict[str, Any], int]:
    """Get Chrome and ChromeDriver versions."""
    checker = BrowserVersionChecker()
    chrome_v = checker.get_chrome_major_version()
    driver_v = checker.get_chromedriver_major_version()
    match = (chrome_v == driver_v and chrome_v != -1)
    
    response = {
        "chrome_major_version": chrome_v,
        "driver_major_version": driver_v,
        "match": match
    }
    
    if not match:
        current_app.logger.warning(
            f"Version mismatch: Chrome={chrome_v}, ChromeDriver={driver_v}"
        )
        return response, 409  # Conflict status code
    
    return response, 200

@app.route("/scrape")
@error_handler
def scrape() -> Tuple[Dict[str, Any], int]:
    """Example endpoint that uses Selenium + headless Chrome."""
    driver = None
    try:
        # Version check
        checker = BrowserVersionChecker()
        if checker.get_chrome_major_version() != checker.get_chromedriver_major_version():
            return jsonify({
                "error": "Chrome & ChromeDriver versions do not match!"
            }), 409

        driver = SeleniumManager.create_driver()
        driver.get("https://legislature.maine.gov/audio/")
        
        # Add more sophisticated scraping logic here
        current_app.logger.info("Scrape completed successfully")
        
        return jsonify({"result": "Scrape ran successfully!"}), 200
        
    finally:
        SeleniumManager.safe_quit(driver)

if __name__ == "__main__":
    # For local debug only
    app.run(host="0.0.0.0", port=8080, debug=True)