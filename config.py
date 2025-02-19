import os

class Config:
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    CHROME_OPTIONS = [
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--disable-software-rasterizer",
        "--disable-extensions",
        "--remote-debugging-port=9222",
        "--window-size=1920,1080"
    ]
    # App Platform health check settings
    HEALTH_CHECK_INTERVAL = 30  # seconds
    MAX_RETRIES = 3
    RETRY_DELAY = 5  # seconds