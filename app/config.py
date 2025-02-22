import os
import logging

class Config:
    DEBUG = os.getenv("DEBUG", False)
    SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key")
    DATABASE_URI = os.getenv("DATABASE_URI", "sqlite:///legislative_documents.db")
    GOOGLE_CHROME_BIN = os.getenv("GOOGLE_CHROME_BIN", "/usr/bin/google-chrome")
    
    # Logging configuration
    LOG_DIR = "/app/logs"
    os.makedirs(LOG_DIR, exist_ok=True)  # Ensure logs directory exists

    LOG_FILE = f"{LOG_DIR}/app.log"
    LOG_LEVEL = logging.DEBUG  # Change to logging.INFO in production

    # Set up logging
    logging.basicConfig(
        filename=LOG_FILE,
        level=LOG_LEVEL,
        format="%(asctime)s - %(levelname)s - %(message)s",
        filemode="a"
    )
