"""Initial migration

Revision ID: 001
Create Date: 2025-02-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    # Main capture table
    op.create_table(
        'stream_captures',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('stream_url', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('metadata', postgresql.JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('start_time', sa.DateTime()),
        sa.Column('end_time', sa.DateTime()),
        sa.Column('errors', postgresql.JSONB()),
        sa.Column('video_path', sa.String()),
        sa.Column('video_size', sa.Integer())
    )

    # Metrics table
    op.create_table(
        'capture_metrics',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('capture_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('cpu_usage', sa.Integer()),
        sa.Column('memory_usage', sa.Integer()),
        sa.Column('frame_rate', sa.Integer()),
        sa.Column('metadata', postgresql.JSONB())
    )

    # Proxy management table
    op.create_table(
        'proxies',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('address', sa.String(), nullable=False),
        sa.Column('port', sa.Integer(), nullable=False),
        sa.Column('protocol', sa.String(), nullable=False),
        sa.Column('username', sa.String()),
        sa.Column('password', sa.String()),
        sa.Column('last_used', sa.DateTime()),
        sa.Column('success_count', sa.Integer(), default=0),
        sa.Column('fail_count', sa.Integer(), default=0),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('metadata', postgresql.JSONB())
    )

    # Proxy usage history
    op.create_table(
        'proxy_usage',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('proxy_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('capture_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('used_at', sa.DateTime(), nullable=False),
        sa.Column('success', sa.Boolean()),
        sa.Column('error', sa.String()),
        sa.Column('response_time', sa.Float())
    )

    # Create indexes
    op.create_index('idx_capture_status', 'stream_captures', ['status'])
    op.create_index('idx_capture_created', 'stream_captures', ['created_at'])
    op.create_index('idx_metrics_capture', 'capture_metrics', ['capture_id'])
    op.create_index('idx_proxy_active', 'proxies', ['is_active'])
    op.create_index('idx_proxy_success_rate', 'proxies', ['success_count', 'fail_count'])

def downgrade():
    op.drop_table('proxy_usage')
    op.drop_table('proxies')
    op.drop_table('capture_metrics')
    op.drop_table('stream_captures')