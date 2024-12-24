from flask import Flask, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

app = Flask(__name__)

@app.route("/")
def home():
    return "Hello from DigitalOcean sample-python with Selenium!"

@app.route("/scrape")
def scrape():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager(version="114.0.5735.90").install()),
        options=options
    )

    driver.get("https://legislature.maine.gov/audio/")
    wait = WebDriverWait(driver, 20)

    try:
        play_button = wait.until(EC.element_to_be_clickable((By.ID, "play")))
        play_button.click()
        message = "Play button clicked!"
    except Exception as e:
        message = f"Error: {e}"
    finally:
        driver.quit()

    return jsonify({"result": message})

if __name__ == "__main__":
    # For local debugging only. On DO, Gunicorn runs server:app.
    app.run(host="0.0.0.0", port=8080, debug=True)