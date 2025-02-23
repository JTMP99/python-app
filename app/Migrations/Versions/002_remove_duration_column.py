# migrations/versions/0002_remove_duration_column.py
"""Remove duration column

Revision ID: 0002
Revises: previous_revision
Create Date: 2025-02-23 21:17:04.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0002'
down_revision = '0001'  # Replace with your previous migration
branch_labels = None
depends_on = None

def upgrade():
    # Remove the duration column as it's now calculated
    op.drop_column('stream_captures', 'duration')

def downgrade():
    # Add back the duration column if needed
    op.add_column('stream_captures', sa.Column('duration', sa.Integer(), nullable=True))