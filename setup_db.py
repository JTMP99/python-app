# setup_db.py
import os
import sys
from app import create_app, db
from app.models.db_models import StreamCapture, CaptureMetrics

# Create the Flask app
app = create_app()

def init_db():
    """Initialize the database."""
    with app.app_context():
        # Print database URI (for debugging)
        print(f"Using database: {app.config['SQLALCHEMY_DATABASE_URI']}")
        
        # Check if tables exist
        try:
            tables = db.engine.table_names()
            print(f"Existing tables: {tables}")
        except Exception as e:
            print(f"Error checking tables: {e}")
            tables = []
        
        # Create all tables
        if not tables:
            print("Creating database tables...")
            try:
                db.create_all()
                print("Tables created successfully.")
            except Exception as e:
                print(f"Error creating tables: {e}")
                return False
        
        return True

def check_connection():
    """Check database connection."""
    with app.app_context():
        try:
            db.session.execute('SELECT 1')
            print("Database connection successful.")
            return True
        except Exception as e:
            print(f"Database connection failed: {e}")
            return False

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        # Just check the connection
        success = check_connection()
    else:
        # Initialize the database
        success = init_db()
    
    sys.exit(0 if success else 1)