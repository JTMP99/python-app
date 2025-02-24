# app/models/db_models.py
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy import Column, String, DateTime, Integer, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app import db
import uuid
import logging

class StreamCapture(db.Model):
    """Model representing a stream capture session."""
    __tablename__ = 'stream_captures'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stream_url = Column(String, nullable=False)
    status = Column(String, nullable=False, default='created')
    capture_metadata = Column(JSONB, nullable=False, default=dict, server_default='{}')
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    errors = Column(JSONB, nullable=False, default=list, server_default='[]')
    video_path = Column(String, nullable=True)
    video_size = Column(Integer, nullable=True)
    screenshot_paths = Column(JSONB, nullable=False, default=list, server_default='[]')
    debug_info = Column(JSONB, nullable=False, default=dict, server_default='{}')
    
    metrics = db.relationship('CaptureMetrics', backref='capture', lazy=True,
                            cascade='all, delete-orphan')

    VALID_STATUSES = {
        'created',        # Initial state when record is created
        'initialized',    # Capture process has been initialized
        'capturing',      # Actively capturing
        'stopping',       # Stop requested
        'completed',      # Successfully completed
        'failed'         # Failed with error
    }

    def __init__(self, **kwargs):
        """Initialize a new StreamCapture instance with validation."""
        super().__init__(**kwargs)
        if not self.stream_url:
            raise ValueError("stream_url cannot be empty")
        if self.status not in self.VALID_STATUSES:
            raise ValueError(f"Invalid status: {self.status}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert the model instance to a dictionary."""
        return {
            'id': str(self.id),
            'stream_url': self.stream_url,
            'status': self.status,
            'capture_metadata': self.capture_metadata,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'duration': self.duration,
            'errors': self.errors or [],
            'video_path': self.video_path,
            'video_size': self.video_size,
            'screenshot_paths': self.screenshot_paths or [],
            'debug_info': self.debug_info or {}
        }

    @property
    def duration(self) -> Optional[int]:
        """Calculate capture duration in seconds."""
        if self.start_time and self.end_time:
            return int((self.end_time - self.start_time).total_seconds())
        return None

class CaptureMetrics(db.Model):
    """Track performance metrics for a capture session."""
    __tablename__ = 'capture_metrics'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    capture_id = Column(UUID(as_uuid=True), ForeignKey('stream_captures.id', ondelete='CASCADE'), nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    cpu_usage = Column(Float)       # CPU usage percentage (0-100)
    memory_usage = Column(Float)    # Memory usage in MB
    frame_rate = Column(Float)      # Frames per second
    capture_metadata = Column(JSONB, nullable=False, default=dict, server_default='{}')

    def __init__(self, **kwargs):
        """Initialize a new CaptureMetrics instance with validation."""
        super().__init__(**kwargs)
        self.validate()

    def validate(self) -> None:
        """Validate metric values."""
        if self.cpu_usage is not None and not 0 <= self.cpu_usage <= 100:
            raise ValueError("CPU usage must be between 0 and 100")
        if self.memory_usage is not None and self.memory_usage < 0:
            raise ValueError("Memory usage cannot be negative")
        if self.frame_rate is not None and self.frame_rate < 0:
            raise ValueError("Frame rate cannot be negative")

    def to_dict(self) -> Dict[str, Any]:
        """Convert the model instance to a dictionary."""
        return {
            'id': str(self.id),
            'capture_id': str(self.capture_id),
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'cpu_usage': self.cpu_usage,
            'memory_usage': self.memory_usage,
            'frame_rate': self.frame_rate,
            'capture_metadata': self.capture_metadata or {}
        }

    @property
    def age(self) -> float:
        """Calculate age of metrics in seconds."""
        return (datetime.utcnow() - self.timestamp).total_seconds()