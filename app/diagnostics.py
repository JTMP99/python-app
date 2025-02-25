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