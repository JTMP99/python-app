# requirements.txt
"""
Flask>=2.3.0
Werkzeug>=3.0.0
selenium>=4.15.0
webdriver-manager>=4.0.1
gunicorn>=21.2.0
"""

from flask import Flask, jsonify, current_app
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from functools import wraps
import subprocess
import re
import logging
from logging.handlers import RotatingFileHandler
import os
from typing import Tuple, Dict, Any, Optional
from datetime import datetime

class Config:
    """Application configuration."""
    CHROME_BINARY_PATHS = ["google-chrome", "chromium", "chromium-browser"]
    SELENIUM_TIMEOUT = 30
    LOG_FILE = "app.log"
    MAX_LOG_SIZE = 10 * 1024 * 1024  # 10MB
    LOG_BACKUP_COUNT = 5
    CHROME_OPTIONS = [
        "--headless=new",  # Updated for newer Chrome versions
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--window-size=1920,1080",
        "--disable-extensions",
        "--disable-logging",
        "--log-level=3",
        "--silent"
    ]
    VERSION_CHECK_CACHE_SECONDS = 300  # Cache version check results for 5 minutes

def setup_logging(app: Flask) -> None:
    """Configure application logging with rotation and proper formatting."""
    os.makedirs('logs', exist_ok=True)
    
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s'
    )
    
    file_handler = RotatingFileHandler(
        f"logs/{Config.LOG_FILE}",
        maxBytes=Config.MAX_LOG_SIZE,
        backupCount=Config.LOG_BACKUP_COUNT
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    
    # Also log to console in development
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.DEBUG if app.debug else logging.INFO)
    
    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)
    app.logger.setLevel(logging.DEBUG if app.debug else logging.INFO)

def create_app() -> Flask:
    """Application factory with proper initialization."""
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object(Config)
    
    # Setup logging
    setup_logging(app)
    
    # Register error handlers
    register_error_handlers(app)
    
    return app

def register_error_handlers(app: Flask) -> None:
    """Register global error handlers."""
    @app.errorhandler(404)
    def not_found_error(error):
        return jsonify({"error": "Resource not found"}), 404

    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({"error": "Internal server error"}), 500

def error_handler(f):
    """Enhanced error handling decorator with detailed logging."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except WebDriverException as e:
            error_msg = f"Selenium error in {f.__name__}: {str(e)}"
            current_app.logger.error(error_msg)
            return jsonify({
                "error": "Browser automation error",
                "details": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }), 500
        except Exception as e:
            error_msg = f"Unexpected error in {f.__name__}: {str(e)}"
            current_app.logger.error(error_msg, exc_info=True)
            return jsonify({
                "error": "Internal server error",
                "timestamp": datetime.utcnow().isoformat()
            }), 500
    return wrapper

class BrowserVersionChecker:
    """Handle browser and driver version checking with caching."""
    _last_check = None
    _cached_versions = None
    
    @classmethod
    def get_versions(cls) -> Dict[str, int]:
        """Get Chrome and ChromeDriver versions with caching."""
        now = datetime.utcnow()
        if (cls._last_check is None or 
            (now - cls._last_check).total_seconds() > Config.VERSION_CHECK_CACHE_SECONDS):
            cls._cached_versions = {
                "chrome": cls._get_chrome_major_version(),
                "driver": cls._get_chromedriver_major_version()
            }
            cls._last_check = now
        return cls._cached_versions

    @staticmethod
    def _get_chrome_major_version() -> int:
        """Get Chrome/Chromium major version with improved error handling."""
        for cmd in Config.CHROME_BINARY_PATHS:
            try:
                out = subprocess.check_output(
                    [cmd, "--version"],
                    stderr=subprocess.STDOUT,
                    timeout=5,
                    encoding='utf-8'
                )
                match = re.search(r"(\d+)\.\d+\.\d+\.\d+", out.strip())
                if match:
                    return int(match.group(1))
            except Exception as e:
                current_app.logger.debug(f"Failed to get version for {cmd}: {str(e)}")
        return -1

    @staticmethod
    def _get_chromedriver_major_version() -> int:
        """Get ChromeDriver major version with improved error handling."""
        try:
            out = subprocess.check_output(
                ["chromedriver", "--version"],
                stderr=subprocess.STDOUT,
                timeout=5,
                encoding='utf-8'
            )
            match = re.search(r"ChromeDriver\s+(\d+)\.\d+\.\d+\.\d+", out.strip())
            if match:
                return int(match.group(1))
        except Exception as e:
            current_app.logger.debug(f"Failed to get ChromeDriver version: {str(e)}")
        return -1

class SeleniumManager:
    """Manage Selenium WebDriver instances with improved error handling."""
    
    @staticmethod
    def create_driver() -> webdriver.Chrome:
        """Create and configure Chrome WebDriver instance with retry logic."""
        options = Options()
        for option in Config.CHROME_OPTIONS:
            options.add_argument(option)
        
        try:
            driver_manager = ChromeDriverManager(cache_valid_range=1)  # 1 day cache
            driver = webdriver.Chrome(
                service=Service(driver_manager.install()),
                options=options
            )
            driver.set_page_load_timeout(Config.SELENIUM_TIMEOUT)
            return driver
        except Exception as e:
            current_app.logger.error(f"Failed to create WebDriver: {str(e)}")
            raise

    @staticmethod
    def safe_quit(driver: Optional[webdriver.Chrome]) -> None:
        """Safely quit WebDriver instance with timeout."""
        if driver:
            try:
                driver.quit()
            except Exception as e:
                current_app.logger.warning(f"Error quitting driver: {str(e)}")

app = create_app()

@app.route("/health")
def health() -> Tuple[Dict[str, Any], int]:
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }), 200

@app.route("/")
def home() -> str:
    """Home endpoint."""
    return "Flask Selenium Service - Running"

@app.route("/versions")
@error_handler
def versions() -> Tuple[Dict[str, Any], int]:
    """Get Chrome and ChromeDriver versions with caching."""
    versions = BrowserVersionChecker.get_versions()
    match = (versions["chrome"] == versions["driver"] and versions["chrome"] != -1)
    
    response = {
        "chrome_major_version": versions["chrome"],
        "driver_major_version": versions["driver"],
        "match": match,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    if not match:
        current_app.logger.warning(
            f"Version mismatch: Chrome={versions['chrome']}, "
            f"ChromeDriver={versions['driver']}"
        )
        return response, 409
    
    return response, 200

@app.route("/scrape")
@error_handler
def scrape() -> Tuple[Dict[str, Any], int]:
    """Example endpoint that uses Selenium with proper error handling."""
    driver = None
    try:
        # Version check
        versions = BrowserVersionChecker.get_versions()
        if versions["chrome"] != versions["driver"]:
            return jsonify({
                "error": "Chrome & ChromeDriver versions do not match!",
                "chrome_version": versions["chrome"],
                "driver_version": versions["driver"],
                "timestamp": datetime.utcnow().isoformat()
            }), 409

        driver = SeleniumManager.create_driver()
        
        # Example scraping with timeout handling
        try:
            driver.get("https://legislature.maine.gov/audio/")
            # Add WebDriverWait for dynamic content if needed
            # WebDriverWait(driver, Config.SELENIUM_TIMEOUT).until(
            #     EC.presence_of_element_located((By.ID, "some-element"))
            # )
        except TimeoutException:
            return jsonify({
                "error": "Page load timeout",
                "timestamp": datetime.utcnow().isoformat()
            }), 504
        
        current_app.logger.info("Scrape completed successfully")
        
        return jsonify({
            "result": "Scrape ran successfully!",
            "timestamp": datetime.utcnow().isoformat()
        }), 200
        
    finally:
        SeleniumManager.safe_quit(driver)

if __name__ == "__main__":
    # For local debug only
    app.run(host="0.0.0.0", port=8080, debug=True)