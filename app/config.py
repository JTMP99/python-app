import os
import logging

class Config:
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"  # Correctly parse boolean
    SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key") # !!! CHANGE THIS IN A REAL APP !!!
    DATABASE_URI = os.getenv("DATABASE_URI", "sqlite:///legislative_documents.db") # Future use
    GOOGLE_CHROME_BIN = os.getenv("GOOGLE_CHROME_BIN", "/usr/bin/chromium")
    BROKER_URL = os.getenv("BROKER_URL", "redis://localhost:6379/0") # For Celery

    # Logging configuration
    LOG_DIR = "/app/logs"
    os.makedirs(LOG_DIR, exist_ok=True)  # Ensure logs directory exists

    LOG_FILE = f"{LOG_DIR}/app.log"
    LOG_LEVEL = logging.DEBUG if DEBUG else logging.INFO # Use INFO for production

    # Set up logging
    logging.basicConfig(
        filename=LOG_FILE,
        level=LOG_LEVEL,
        format="%(asctime)s - %(levelname)s - %(message)s",
        filemode="a"
    )