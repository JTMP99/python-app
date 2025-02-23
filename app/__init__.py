# app/__init__.py
from flask import Flask, render_template
from .config import Config, DevelopmentConfig, ProductionConfig  # Import config classes
#from celery import Celery  <- REMOVE
import os

# Create the Celery instance *outside* the app factory.  This is crucial.
#celery = Celery(__name__, broker=Config.BROKER_URL, backend=Config.BROKER_URL) <- REMOVE

# Global dictionary to store StreamCapture objects. Accessible to both Flask and Celery.
#STREAMS = {} <- Change this to app level variable

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    # Ensure that logs directory exists
    os.makedirs(app.config['LOG_DIR'], exist_ok=True)

    #Global Dictionary
    app.STREAMS = {}

    # Import and register blueprints (within the app context)
    from app.streaming import streaming_bp
    app.register_blueprint(streaming_bp, url_prefix='/streams')

    # --- Other blueprints (commented out for now) ---
    # from app.scraping import scraping_bp
    # app.register_blueprint(scraping_bp, url_prefix='/scraping')

    # from app.documents import documents_bp
    # app.register_blueprint(documents_bp, url_prefix='/documents')

    # --- Dashboard route (at the root URL) ---
    @app.route("/")
    def dashboard():
        return render_template("dashboard.html")

    return app