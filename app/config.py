# app/config.py
import os
import logging

class Config:
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"
    SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key")
    
    # Extended timeouts and capture settings
    CAPTURE_TIMEOUT = 120  # 2 minutes
    CAPTURE_RETRIES = 3
    
    # Database Configuration
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,
        'max_overflow': 20,
        'pool_timeout': 60,
        'pool_recycle': 1800,
        'pool_pre_ping': True,
        'connect_args': {
            'connect_timeout': 30,
            'keepalives': 1,
            'keepalives_idle': 30,
            'keepalives_interval': 10,
            'keepalives_count': 5,
            'application_name': 'whale_capture'
        }
    }
    
    # Browser/Capture Configuration
    GOOGLE_CHROME_BIN = os.getenv("GOOGLE_CHROME_BIN", "/usr/bin/chromium")
    
    # Logging configuration
    LOG_DIR = "/app/logs"
    os.makedirs(LOG_DIR, exist_ok=True)

    LOG_FILE = f"{LOG_DIR}/app.log"
    LOG_LEVEL = logging.DEBUG if DEBUG else logging.INFO

    # Enhanced logging configuration
    logging.basicConfig(
        filename=LOG_FILE,
        level=LOG_LEVEL,
        format="%(asctime)s - %(levelname)s - [%(name)s] %(message)s",
        filemode="a"
    )
    
    # Ensure the SQLAlchemy logger captures important DB events
    logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

class DevelopmentConfig(Config):
    DEBUG = True
    LOG_LEVEL = logging.DEBUG
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'postgresql://localhost:5432/captures')
    
    # Shorter timeouts for development
    CAPTURE_TIMEOUT = 60

class ProductionConfig(Config):
    DEBUG = False
    LOG_LEVEL = logging.INFO
    
    # Production database settings
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 20,
        'max_overflow': 40,
        'pool_timeout': 60,
        'pool_recycle': 1800,
        'pool_pre_ping': True,
        'connect_args': {
            'connect_timeout': 30,
            'keepalives': 1,
            'keepalives_idle': 30,
            'keepalives_interval': 10,
            'keepalives_count': 5,
            'application_name': 'whale_capture_prod'
        }
    }
    
    @classmethod
    def init_app(cls, app):
        required_vars = ['DATABASE_URL', 'SECRET_KEY']
        missing = [var for var in required_vars if not os.getenv(var)]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")