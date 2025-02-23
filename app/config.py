import os
import logging

class Config:
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"
    SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key")  # !!! CHANGE THIS
    
    # Database Configuration
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')  # DO Managed Database URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 5,
        'max_overflow': 10,
        'pool_timeout': 30,
        'pool_recycle': 1800,
    }
    
    # Browser/Capture Configuration
    GOOGLE_CHROME_BIN = os.getenv("GOOGLE_CHROME_BIN", "/usr/bin/chromium")
    
    # Remove Celery config if not using it
    # BROKER_URL = os.getenv("BROKER_URL", "redis://localhost:6379/0")

    # Logging configuration
    LOG_DIR = "/app/logs"
    os.makedirs(LOG_DIR, exist_ok=True)  # Ensure logs directory exists

    LOG_FILE = f"{LOG_DIR}/app.log"
    LOG_LEVEL = logging.DEBUG if DEBUG else logging.INFO

    # Set up logging
    logging.basicConfig(
        filename=LOG_FILE,
        level=LOG_LEVEL,
        format="%(asctime)s - %(levelname)s - %(message)s",
        filemode="a"
    )

class DevelopmentConfig(Config):
    DEBUG = True
    LOG_LEVEL = logging.DEBUG
    # Use local PostgreSQL for development if needed
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'postgresql://localhost:5432/captures')

class ProductionConfig(Config):
    DEBUG = False
    LOG_LEVEL = logging.INFO
    
    # Stricter database settings for production
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,
        'max_overflow': 20,
        'pool_timeout': 60,
        'pool_recycle': 3600,
    }
    
    # Ensure required environment variables are set
    @classmethod
    def init_app(cls, app):
        required_vars = ['DATABASE_URL', 'SECRET_KEY']
        missing = [var for var in required_vars if not os.getenv(var)]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")