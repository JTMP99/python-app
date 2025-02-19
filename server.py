from flask import Flask, jsonify, request
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from functools import wraps
import logging
import time
import traceback
from config import Config

# Initialize Flask app
app = Flask(__name__)

# Configure logging
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def setup_chrome_options() -> Options:
    """Configure Chrome options for headless operation."""
    options = Options()
    for option in Config.CHROME_OPTIONS:
        options.add_argument(option)
    return options

def retry_on_failure(max_retries=Config.MAX_RETRIES, delay=Config.RETRY_DELAY):
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

@app.before_request
def log_request_info():
    """Log incoming request details."""
    logger.info(f"Request: {request.method} {request.url}")

@app.after_request
def log_response_info(response):
    """Log response details."""
    logger.info(f"Response: {response.status}")
    return response

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
        driver = webdriver.Chrome(options=options)
        browser_version = driver.capabilities['browserVersion']
        driver_version = driver.capabilities['chrome']['chromedriverVersion'].split(' ')[0]
        
        return jsonify({
            "status": "success",
            "browser_version": browser_version,
            "chromedriver_version": driver_version,
            "timestamp": time.time()
        })
    except Exception as e:
        logger.error(f"Version check failed: {traceback.format_exc()}")
        raise
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
        driver = webdriver.Chrome(options=options)
        
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
        raise
    except Exception as e:
        logger.error(f"Scrape failed: {traceback.format_exc()}")
        raise
    finally:
        if driver:
            driver.quit()

@app.errorhandler(Exception)
def handle_error(error):
    """Global error handler."""
    logger.error(f"Unhandled error: {traceback.format_exc()}")
    return jsonify({
        "error": str(error),
        "type": error.__class__.__name__,
        "timestamp": time.time()
    }), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)