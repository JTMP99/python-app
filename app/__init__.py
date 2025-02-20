from flask import Flask, render_template
from .config import Config
from .streaming.routes import streaming_bp
from .scraping.routes import scraping_bp
from .documents.routes import documents_bp

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Register blueprints for modular functionality.
    app.register_blueprint(streaming_bp, url_prefix="/streams")
    app.register_blueprint(scraping_bp, url_prefix="/scraping")
    app.register_blueprint(documents_bp, url_prefix="/documents")

    # Dashboard route (renders the dashboard.html template)
    @app.route("/dashboard")
    def dashboard():
        return render_template("dashboard.html")

    return app
