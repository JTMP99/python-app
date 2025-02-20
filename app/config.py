import os

class Config:
    DEBUG = os.getenv("DEBUG", False)
    SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key")
    DATABASE_URI = os.getenv("DATABASE_URI", "sqlite:///legislative_documents.db")
    GOOGLE_CHROME_BIN = os.getenv("GOOGLE_CHROME_BIN", "/usr/bin/google-chrome")
