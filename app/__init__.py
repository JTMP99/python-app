# app/__init__.py
from flask import Flask, render_template
from .config import Config
from celery import Celery
import os #For making directory

# Create the Celery instance *outside* the app factory.
celery = Celery(__name__, broker=Config.BROKER_URL, backend=Config.BROKER_URL)

# Global dictionary to store StreamCapture objects.
STREAMS = {}

# --- Celery Task (Defined *here*, not in capture.py) ---
@celery.task(bind=True)
def start_capture_task(self, stream_url):
    from app.streaming.capture import StreamCapture  # Import INSIDE the task
    stream_capture = StreamCapture(stream_url)
    STREAMS[stream_capture.id] = stream_capture  # Add to STREAMS *before* starting
    try:
        stream_capture.start_capture()
    except Exception as exc:
        # Handle exceptions (optional: retry)
        # raise self.retry(exc=exc, countdown=5)
        return  # Or return an error indicator

    return stream_capture.id

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize Celery with the Flask app's configuration.
    celery.conf.update(app.config)
    #Ensure that logs directory exists
    os.makedirs(app.config['LOG_DIR'], exist_ok=True)

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