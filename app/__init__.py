# app/__init__.py
from flask import Flask, render_template
from .config import Config  # Import the Config class
from celery import Celery

# Create the Celery instance *outside* the app factory.  This is crucial.
celery = Celery(__name__, broker=Config.BROKER_URL, backend=Config.BROKER_URL)

# Global dictionary to store StreamCapture objects. Accessible to Flask and Celery.
STREAMS = {}

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize Celery with the Flask app's configuration.  VERY IMPORTANT.
    celery.conf.update(app.config)

    # Import and register blueprints (within the app context)
    from app.streaming import streaming_bp
    app.register_blueprint(streaming_bp, url_prefix='/streams')

    # --- Other blueprints (if you have them - keep them commented out for now) ---
    # from app.scraping import scraping_bp
    # app.register_blueprint(scraping_bp, url_prefix='/scraping')

    # from app.documents import documents_bp
    # app.register_blueprint(documents_bp, url_prefix='/documents')

    # --- Dashboard route (at the root URL) ---
    @app.route("/")
    def dashboard():
        return render_template("dashboard.html")

    return app