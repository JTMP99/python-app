# fix_migrations.py
import os
from app import create_app, db
from flask_migrate import upgrade, current, stamp
from alembic.config import Config as AlembicConfig
from alembic import command

app = create_app()

def fix_migrations():
    with app.app_context():
        print("Checking database and migrations...")
        
        try:
            # Check if the database tables exist
            inspector = db.inspect(db.engine)
            tables = inspector.get_table_names()
            
            print(f"Database tables: {tables}")
            
            # Check migration version
            try:
                version = current()
                print(f"Current migration version: {version}")
            except Exception as e:
                print(f"Error getting migration version: {e}")
                version = None
            
            # If tables exist but no migration version, stamp the database
            if 'stream_captures' in tables and version is None:
                print("Tables exist but no migration version found. Stamping as head...")
                try:
                    stamp('head')
                    print("Database stamped as head.")
                except Exception as e:
                    print(f"Error stamping database: {e}")
            
            # If no tables exist, run migrations
            if 'stream_captures' not in tables:
                print("Tables don't exist. Running migrations...")
                try:
                    upgrade()
                    print("Migrations applied.")
                except Exception as e:
                    print(f"Error running migrations: {e}")
                    
                    # If migrations fail, try creating tables directly
                    print("Creating tables directly...")
                    db.create_all()
                    print("Tables created directly.")
                    
                    # Stamp as head
                    print("Stamping database as head...")
                    stamp('head')
                    print("Database stamped as head.")
            
            print("Migration check completed.")
            
        except Exception as e:
            print(f"Database error: {e}")

if __name__ == "__main__":
    fix_migrations()