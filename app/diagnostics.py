# app/diagnostics.py
from flask import Blueprint, jsonify
from sqlalchemy import inspect, text
from app import db

diagnostics_bp = Blueprint('diagnostics', __name__)

@diagnostics_bp.route('/check-db')
def check_db():
    """Check database connection and schema."""
    try:
        # Check if database is accessible
        result = db.session.execute(text('SELECT 1'))
        connection_ok = next(result)[0] == 1

        # Get schema info
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        
        schema_info = {}
        for table in tables:
            columns = []
            for column in inspector.get_columns(table):
                column_info = {
                    'name': column['name'],
                    'type': str(column['type']),
                    'nullable': column['nullable']
                }
                columns.append(column_info)
            
            schema_info[table] = {
                'columns': columns,
                'primary_key': inspector.get_pk_constraint(table),
                'foreign_keys': inspector.get_foreign_keys(table),
                'indexes': inspector.get_indexes(table)
            }
        
        # Check for specific tables
        required_tables = ['stream_captures', 'capture_metrics']
        missing_tables = [t for t in required_tables if t not in tables]
        
        return jsonify({
            'database_connection': {
                'status': 'connected' if connection_ok else 'error',
                'database_url': db.engine.url.render_as_string(hide_password=True)
            },
            'tables': tables,
            'missing_tables': missing_tables,
            'schema': schema_info,
            'environment': {
                'database_url_set': bool(db.engine.url.database)
            }
        })
    except Exception as e:
        return jsonify({
            'error': str(e),
            'type': type(e).__name__
        }), 500

@diagnostics_bp.route('/fix-migrations')
def fix_migrations():
    """Attempt to fix migration versioning."""
    try:
        # Check current alembic version
        version_result = db.session.execute(text('SELECT version_num FROM alembic_version'))
        current_version = next(version_result)[0]
        
        # Check if tables exist but alembic_version is wrong
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        
        result = {
            'current_version': current_version,
            'tables': tables,
            'actions_taken': []
        }
        
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'error': str(e),
            'type': type(e).__name__
        }), 500
        
@diagnostics_bp.route('/check-routes')
def check_routes():
    """List all registered routes in the application."""
    try:
        from flask import current_app
        routes = []
        
        for rule in current_app.url_map.iter_rules():
            routes.append({
                'endpoint': rule.endpoint,
                'methods': [method for method in rule.methods if method not in ('HEAD', 'OPTIONS')],
                'path': str(rule)
            })
        
        return jsonify({
            'total_routes': len(routes),
            'routes': sorted(routes, key=lambda r: r['path'])
        })
    except Exception as e:
        return jsonify({
            'error': str(e),
            'type': type(e).__name__
        }), 500
        
@diagnostics_bp.route('/routes')
def list_routes():
    """List all registered routes in the application."""
    from flask import current_app
    routes = []
    
    for rule in current_app.url_map.iter_rules():
        routes.append({
            'endpoint': rule.endpoint,
            'methods': [method for method in rule.methods if method not in ('HEAD', 'OPTIONS')],
            'path': str(rule)
        })
    
    return jsonify({
        'total_routes': len(routes),
        'routes': sorted(routes, key=lambda r: r['path'])
    })

@diagnostics_bp.route('/environment')
def environment_info():
    """Show environment information."""
    import os
    import sys
    import platform
    
    env_vars = {}
    for key in ['FLASK_APP', 'FLASK_ENV', 'DISPLAY', 'GOOGLE_CHROME_BIN', 'PORT']:
        env_vars[key] = os.environ.get(key, 'Not set')
    
    # Mask DATABASE_URL if present
    if 'DATABASE_URL' in os.environ:
        db_url = os.environ['DATABASE_URL']
        if '@' in db_url:
            masked_url = db_url.split('@')[0].split(':')[0] + ':***@' + db_url.split('@')[1]
            env_vars['DATABASE_URL'] = masked_url
        else:
            env_vars['DATABASE_URL'] = 'Set (masked)'
    else:
        env_vars['DATABASE_URL'] = 'Not set'
        
    return jsonify({
        'python_version': sys.version,
        'platform': platform.platform(),
        'environment_variables': env_vars,
        'working_directory': os.getcwd(),
        'files_in_app_dir': os.listdir('/app') if os.path.exists('/app') else 'Not accessible'
    })

@diagnostics_bp.route('/processes')
def process_info():
    """Show running processes info."""
    import psutil
    
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'username']):
        try:
            processes.append(proc.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    
    # Filter for relevant processes
    relevant = [p for p in processes if any(x in str(p.get('name', '')).lower() 
                for x in ['chrome', 'python', 'flask', 'gunicorn', 'ffmpeg', 'xvfb'])]
    
    return jsonify({
        'total_processes': len(processes),
        'relevant_processes': relevant,
        'memory_usage': {
            'total': psutil.virtual_memory().total / (1024 * 1024),
            'available': psutil.virtual_memory().available / (1024 * 1024),
            'percent': psutil.virtual_memory().percent
        },
        'cpu_percent': psutil.cpu_percent(interval=1)
    })

@diagnostics_bp.route('/captures-summary')
def captures_summary():
    """Show summary of captures in the database."""
    from app.models.db_models import StreamCapture
    from sqlalchemy import func
    from app import db
    
    try:
        total = db.session.query(func.count(StreamCapture.id)).scalar()
        
        by_status = db.session.query(
            StreamCapture.status, 
            func.count(StreamCapture.id)
        ).group_by(StreamCapture.status).all()
        
        status_counts = {status: count for status, count in by_status}
        
        recent = db.session.query(StreamCapture).order_by(
            StreamCapture.created_at.desc()
        ).limit(5).all()
        
        recent_list = [{
            'id': str(c.id),
            'stream_url': c.stream_url,
            'status': c.status,
            'created_at': c.created_at.isoformat() if c.created_at else None,
            'duration': c.duration
        } for c in recent]
        
        return jsonify({
            'total_captures': total,
            'by_status': status_counts,
            'recent_captures': recent_list
        })
    except Exception as e:
        return jsonify({'error': str(e), 'type': type(e).__name__})

@diagnostics_bp.route('/test-selenium')
def test_selenium():
    """Test Selenium setup."""
    import subprocess
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    
    results = {
        'chrome_binary': None,
        'display_env': None,
        'xvfb_running': False,
        'selenium_test': None,
        'errors': []
    }
    
    try:
        # Check Chrome binary
        import os
        chrome_bin = os.environ.get('GOOGLE_CHROME_BIN', '/usr/bin/chromium')
        results['chrome_binary'] = {
            'path': chrome_bin,
            'exists': os.path.exists(chrome_bin)
        }
        
        # Check DISPLAY environment variable
        results['display_env'] = os.environ.get('DISPLAY', 'Not set')
        
        # Check if Xvfb is running
        try:
            ps_output = subprocess.check_output(['ps', 'aux']).decode()
            results['xvfb_running'] = 'Xvfb' in ps_output
        except Exception as e:
            results['errors'].append(f"Error checking Xvfb: {str(e)}")
        
        # Try to initialize Selenium
        try:
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.binary_location = chrome_bin
            
            driver = webdriver.Chrome(options=chrome_options)
            driver.get('https://example.com')
            title = driver.title
            driver.quit()
            
            results['selenium_test'] = {
                'success': True,
                'page_title': title
            }
        except Exception as e:
            results['selenium_test'] = {
                'success': False,
                'error': str(e)
            }
            results['errors'].append(f"Selenium test failed: {str(e)}")
        
        return jsonify(results)
    except Exception as e:
        results['errors'].append(f"Overall error: {str(e)}")
        return jsonify(results)