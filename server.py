from flask import Flask, jsonify, request
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
from functools import wraps
import logging
import time
import traceback
import os

# Initialize Flask app
app = Flask(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def setup_chrome_options() -> Options:
    """Configure Chrome options for headless operation."""
    chrome_options = Options()
    # If an environment variable for chrome binary is set, use it.
    chrome_bin = os.environ.get("GOOGLE_CHROME_BIN")
    if chrome_bin:
        chrome_options.binary_location = chrome_bin

    # Headless options and flags
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-setuid-sandbox')
    chrome_options.add_argument('--disable-software-rasterizer')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--single-process')
    chrome_options.add_argument('--ignore-certificate-errors')
    chrome_options.add_argument('--remote-debugging-port=9222')
    chrome_options.add_argument('--user-data-dir=/tmp/chrome-data')
    return chrome_options

def retry_on_failure(max_retries=3, delay=5):
    """Decorator to retry operations on failure."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
                    if attempt < max_retries - 1:
                        time.sleep(delay)
            logger.error(f"All {max_retries} attempts failed. Last error: {str(last_exception)}")
            raise last_exception
        return wrapper
    return decorator

@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "timestamp": time.time()})

@app.route("/")
def home():
    """Home endpoint."""
    return jsonify({
        "status": "running",
        "service": "Flask Selenium Service",
        "version": "1.0.0"
    })

@app.route("/versions")
@retry_on_failure()
def versions():
    """Get Chrome and ChromeDriver versions."""
    driver = None
    try:
        options = setup_chrome_options()
        # Use webdriver_manager to install and locate chromedriver
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        browser_version = driver.capabilities.get('browserVersion', 'unknown')
        driver_info = driver.capabilities.get('chrome', {})
        driver_version = driver_info.get('chromedriverVersion', 'unknown').split(' ')[0]
        
        return jsonify({
            "status": "success",
            "browser_version": browser_version,
            "chromedriver_version": driver_version,
            "timestamp": time.time()
        })
    except Exception as e:
        logger.error(f"Version check failed: {traceback.format_exc()}")
        return jsonify({
            "status": "error",
            "error": str(e),
            "timestamp": time.time()
        }), 500
    finally:
        if driver:
            driver.quit()

@app.route("/scrape")
@retry_on_failure()
def scrape():
    """Scrape endpoint with enhanced error handling."""
    driver = None
    try:
        options = setup_chrome_options()
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        # Set page load timeout
        driver.set_page_load_timeout(30)
        
        # Perform the scrape
        start_time = time.time()
        driver.get("https://legislature.maine.gov/audio/")
        
        # Wait for page to be interactive
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script('return document.readyState') == 'complete'
        )
        
        # Calculate timing metrics
        load_time = time.time() - start_time
        
        return jsonify({
            "status": "success",
            "message": "Scrape completed successfully",
            "metrics": {
                "load_time_seconds": round(load_time, 2),
                "timestamp": time.time()
            }
        })
        
    except TimeoutException:
        logger.error("Page load timed out")
        return jsonify({
            "status": "error",
            "error": "Page load timed out",
            "timestamp": time.time()
        }), 504
    except Exception as e:
        logger.error(f"Scrape failed: {traceback.format_exc()}")
        return jsonify({
            "status": "error",
            "error": str(e),
            "timestamp": time.time()
        }), 500
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
