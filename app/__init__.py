# app/__init__.py
from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate  # Keep for database migrations
from .config import Config, DevelopmentConfig, ProductionConfig
import os

db = SQLAlchemy()
migrate = Migrate()  # Create Migrate instance

def create_app(config_class=Config):
    app = Flask(__name__)

    # Choose configuration based on environment
    if os.environ.get('FLASK_ENV') == 'production':
        app.config.from_object(ProductionConfig)
    else:
        app.config.from_object(DevelopmentConfig)  # Default to development

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)  # Initialize Migrate, passing in app and db

    # Make STREAMS available on the app object
    app.STREAMS = {}

    # Import and register blueprints
    from app.streaming import streaming_bp
    app.register_blueprint(streaming_bp, url_prefix='/streams')
    
    # --- Other blueprints (commented out for now) ---
    # from app.scraping import scraping_bp
    # app.register_blueprint(scraping_bp, url_prefix='/scraping')

    # --- Dashboard route (at the root URL) ---
    @app.route("/")
    def dashboard():
        return render_template("dashboard.html")
    
    return app