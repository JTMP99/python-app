# migrations/versions/add_screenshot_paths.py
"""Add screenshot_paths column

Revision ID: add_screenshot_paths
Revises: 0002
Create Date: 2025-02-24 00:10:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision = 'add_screenshot_paths'
down_revision = '0002'  # Replace with your previous migration ID
branch_labels = None
depends_on = None

def upgrade():
    # Add screenshot_paths column
    op.add_column('stream_captures', 
        sa.Column('screenshot_paths', postgresql.JSON, nullable=False, server_default='[]')
    )

def downgrade():
    # Remove screenshot_paths column
    op.drop_column('stream_captures', 'screenshot_paths')