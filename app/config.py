import os
import logging

class Config:
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"
    SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key")  # !!! CHANGE THIS
    DATABASE_URI = os.getenv("DATABASE_URI", "sqlite:///legislative_documents.db") # Future
    GOOGLE_CHROME_BIN = os.getenv("GOOGLE_CHROME_BIN", "/usr/bin/chromium")
    BROKER_URL = os.getenv("BROKER_URL", "redis://localhost:6379/0")  # Celery

    # Logging configuration
    LOG_DIR = "/app/logs"
    os.makedirs(LOG_DIR, exist_ok=True)  # Ensure logs directory exists

    LOG_FILE = f"{LOG_DIR}/app.log"
    LOG_LEVEL = logging.DEBUG if DEBUG else logging.INFO

    # Set up logging (Correctly here, and ONLY here)
    logging.basicConfig(
        filename=LOG_FILE,
        level=LOG_LEVEL,
        format="%(asctime)s - %(levelname)s - %(message)s",
        filemode="a"
    )

class DevelopmentConfig(Config):
    DEBUG = True  # Enable debug mode in development
    LOG_LEVEL = logging.DEBUG
    DATABASE_URI = "sqlite:///dev_legislative_documents.db"  # SQLite for dev


class ProductionConfig(Config):
    # Get DATABASE_URL from environment variable (set on DigitalOcean)
    DATABASE_URI = os.environ.get('DATABASE_URL')  # Use DATABASE_URL for production
    # Other production settings (e.g., disable debug mode, set log level)
    DEBUG = False
    LOG_LEVEL = logging.INFO

    #Add secret key and ensure its a boolean
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError("No SECRET_KEY set for Flask application. Set it as an environment variable.")