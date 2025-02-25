# Add to the imports at the top
from flask import Flask, render_template, jsonify

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
    
    # --- Register diagnostics blueprint ---
    from app.diagnostics import diagnostics_bp
    app.register_blueprint(diagnostics_bp, url_prefix='/diagnostics')
    
    # --- Other blueprints (commented out for now) ---
    # from app.scraping import scraping_bp
    # app.register_blueprint(scraping_bp, url_prefix='/scraping')

    # --- Dashboard route (at the root URL) ---
    @app.route("/")
    def dashboard():
        return render_template("dashboard.html")
        
    # Add a database configuration endpoint
    @app.route('/db-config')
    def db_config():
        return jsonify({
            'database_url': app.config.get('SQLALCHEMY_DATABASE_URI', 'Not set'),
            'debug': app.config.get('DEBUG', False),
            'env': os.environ.get('FLASK_ENV', 'development')
        })
    
    return app