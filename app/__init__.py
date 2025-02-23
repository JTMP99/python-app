# app/__init__.py
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from .config import Config

db = SQLAlchemy()
migrate = Migrate()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)

    with app.app_context():
        # Create all tables. In production, use migrations instead
        db.create_all()

    # Import blueprints
    from app.streaming import streaming_bp
    from app.streaming.analytics import analytics_bp
    
    app.register_blueprint(streaming_bp, url_prefix='/streams')
    app.register_blueprint(analytics_bp, url_prefix='/analytics')

    return app