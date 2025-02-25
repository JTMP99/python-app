# run.py
import os
import logging
from app import create_app, db

app = create_app()

def check_database():
    """Validate database connection before starting the app."""
    try:
        with app.app_context():
            db.session.execute('SELECT 1')
            app.logger.info("Database connection successful")
            return True
    except Exception as e:
        app.logger.error(f"Database connection failed: {e}")
        
        # Fall back to SQLite for development
        if not app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite'):
            app.logger.warning("Falling back to SQLite database")
            app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////app/app.db'
            
            try:
                with app.app_context():
                    db.session.execute('SELECT 1')
                    app.logger.info("SQLite database connection successful")
                    return True
            except Exception as e2:
                app.logger.error(f"SQLite database connection failed: {e2}")
                return False
        return False

# Check database before starting
if not check_database():
    app.logger.error("Failed to connect to database. Check your configuration.")

if __name__ == "__main__":
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)  # Enable debug mode