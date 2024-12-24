from flask import Flask, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# For version checking
import subprocess
import re

app = Flask(__name__)

def get_chrome_major_version():
    """
    Tries several commands to detect installed Chrome/Chromium,
    returning its major version (or -1 if not found).
    """
    for cmd in ["google-chrome", "chromium", "chromium-browser"]:
        try:
            out = subprocess.check_output([cmd, "--version"], stderr=subprocess.STDOUT)
            version_str = out.decode().strip()  # e.g. "Google Chrome 114.0.5735.90"
            match = re.search(r"(\d+)\.\d+\.\d+\.\d+", version_str)
            if match:
                return int(match.group(1))
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass
    return -1

def get_chromedriver_major_version():
    """
    Runs `chromedriver --version` to parse its major version (or -1 if not found).
    """
    try:
        out = subprocess.check_output(["chromedriver", "--version"], stderr=subprocess.STDOUT)
        # e.g. "ChromeDriver 114.0.5735.90 (abc123)"
        version_str = out.decode().strip()
        match = re.search(r"ChromeDriver\s+(\d+)\.\d+\.\d+\.\d+", version_str)
        if match:
            return int(match.group(1))
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    return -1

@app.route("/")
def home():
    return "Hello from DigitalOcean sample-python with Selenium!"

@app.route("/versions")
def versions():
    """
    Returns JSON showing the detected major versions of Chrome/Chromium and ChromeDriver.
    Helpful for diagnosing 'session not created' errors due to mismatched versions.
    """
    chrome_v = get_chrome_major_version()
    driver_v = get_chromedriver_major_version()
    match = (chrome_v == driver_v and chrome_v != -1)
    return jsonify({
        "chrome_major_version": chrome_v,
        "driver_major_version": driver_v,
        "match": match
    })

@app.route("/scrape")
def scrape():
    """
    Example endpoint that uses Selenium + headless Chrome.
    If versions mismatch, you may see 'SessionNotCreatedException' unless you align them.
    """
    # Optional: You could run a quick check here before creating the driver:
    # if get_chrome_major_version() != get_chromedriver_major_version():
    #     return jsonify({"error": "Chrome & ChromeDriver versions do not match!"}), 500

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")

    # If you need a specific driver version (e.g., 114), do:
    # driver_manager = ChromeDriverManager(driver_version="114.0.5735.90")
    # Otherwise, let webdriver_manager auto-detect:
    driver_manager = ChromeDriverManager()

    driver = webdriver.Chrome(
        service=Service(driver_manager.install()),
        options=options
    )

    driver.get("https://legislature.maine.gov/audio/")
    message = "Scrape ran successfully!"
    driver.quit()
    return jsonify({"result": message})

if __name__ == "__main__":
    # For local debug only. On DO, Gunicorn runs:  gunicorn --bind 0.0.0.0:8080 server:app
    app.run(host="0.0.0.0", port=8080, debug=True)