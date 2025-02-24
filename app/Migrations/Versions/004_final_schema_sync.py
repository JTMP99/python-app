# migrations/versions/004_final_schema_sync.py
"""Sync final schema

Revision ID: 004
Revises: 003
Create Date: 2025-02-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None

def upgrade():
    # Ensure all columns have consistent types
    with op.batch_alter_table('stream_captures') as batch_op:
        # Ensure JSON fields are JSONB and have proper defaults
        batch_op.alter_column('capture_metadata',
            type_=postgresql.JSONB(),
            nullable=False,
            server_default='{}')
        batch_op.alter_column('errors',
            type_=postgresql.JSONB(),
            nullable=False,
            server_default='[]')
        batch_op.alter_column('screenshot_paths',
            type_=postgresql.JSONB(),
            nullable=False,
            server_default='[]')
        batch_op.alter_column('debug_info',
            type_=postgresql.JSONB(),
            nullable=False,
            server_default='{}')

    with op.batch_alter_table('capture_metrics') as batch_op:
        # Convert metrics to Float type if not already
        batch_op.alter_column('cpu_usage',
            type_=sa.Float(),
            existing_type=sa.Integer())
        batch_op.alter_column('memory_usage',
            type_=sa.Float(),
            existing_type=sa.Integer())
        batch_op.alter_column('frame_rate',
            type_=sa.Float(),
            existing_type=sa.Integer())
        batch_op.alter_column('capture_metadata',
            type_=postgresql.JSONB(),
            nullable=False,
            server_default='{}')

def downgrade():
    pass  # No downgrade needed as this is schema sync