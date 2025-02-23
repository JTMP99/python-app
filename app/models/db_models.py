# app/models/db_models.py
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy import Column, String, DateTime, JSON, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app import db
import uuid

class StreamCapture(db.Model):
    """Model representing a stream capture session.
    
    Attributes:
        id (UUID): Unique identifier for the capture
        stream_url (str): URL of the stream being captured
        status (str): Current status of the capture
        capture_metadata (dict): Additional metadata about the capture
        created_at (datetime): When the capture was created
        updated_at (datetime): When the capture was last updated
        start_time (datetime): When the capture started
        end_time (datetime): When the capture ended
        errors (list): List of errors encountered during capture
        video_path (str): Path to the captured video file
        video_size (int): Size of the video file in bytes
    """
    __tablename__ = 'stream_captures'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stream_url = Column(String, nullable=False)
    status = Column(String, nullable=False, default='created')
    capture_metadata = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    errors = Column(JSON, default=list)
    video_path = Column(String)
    video_size = Column(Integer)
    
    metrics = db.relationship('CaptureMetrics', backref='capture', lazy=True)

    VALID_STATUSES = {
        'created',
        'initialized',
        'capturing',
        'stopping',
        'completed',
        'failed'
    }

    def to_dict(self) -> Dict[str, Any]:
        """Convert the model instance to a dictionary.
        
        Returns:
            Dict[str, Any]: Dictionary representation of the capture
        """
        return {
            'id': str(self.id),
            'stream_url': self.stream_url,
            'status': self.status,
            'capture_metadata': self.capture_metadata,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'errors': self.errors,
            'video_path': self.video_path,
            'video_size': self.video_size
        }

    def update_status(self, status: str, error: Optional[str] = None) -> None:
        """Update status and optionally add error.
        
        Args:
            status (str): New status value
            error (Optional[str]): Error message to add
        """
        if status not in self.VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}")
        self.status = status
        self.updated_at = datetime.utcnow()
        
        if error:
            if not self.errors:
                self.errors = []
            self.errors.append({
                'time': datetime.utcnow().isoformat(),
                'error': str(error)
            })
        
        db.session.commit()

    def update_metadata(self, metadata_updates: Dict[str, Any]) -> None:
        """Update capture metadata.
        
        Args:
            metadata_updates (Dict[str, Any]): New metadata to merge
        """
        if not self.capture_metadata:
            self.capture_metadata = {}
        self.capture_metadata.update(metadata_updates)
        self.updated_at = datetime.utcnow()
        db.session.commit()

    @property
    def duration(self) -> Optional[int]:
        """Calculate capture duration in seconds.
        
        Returns:
            Optional[int]: Duration in seconds or None if incomplete
        """
        if self.start_time and self.end_time:
            return int((self.end_time - self.start_time).total_seconds())
        return None

class CaptureMetrics(db.Model):
    """Track performance metrics for a capture session.
    
    Attributes:
        id (UUID): Unique identifier for the metric record
        capture_id (UUID): ID of associated capture
        timestamp (datetime): When metrics were recorded
        cpu_usage (int): CPU usage percentage (0-100)
        memory_usage (int): Memory usage in MB
        frame_rate (int): Frames per second
        capture_metadata (dict): Additional metric metadata
    """
    __tablename__ = 'capture_metrics'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    capture_id = Column(UUID(as_uuid=True), ForeignKey('stream_captures.id'), nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    cpu_usage = Column(Integer)
    memory_usage = Column(Integer)
    frame_rate = Column(Integer)
    capture_metadata = Column(JSON, default=dict)

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
        """Convert the model instance to a dictionary.
        
        Returns:
            Dict[str, Any]: Dictionary representation of the metrics
        """
        return {
            'id': str(self.id),
            'capture_id': str(self.capture_id),
            'timestamp': self.timestamp.isoformat(),
            'cpu_usage': self.cpu_usage,
            'memory_usage': self.memory_usage,
            'frame_rate': self.frame_rate,
            'capture_metadata': self.capture_metadata
        }

    @property
    def age(self) -> float:
        """Calculate age of metrics in seconds.
        
        Returns:
            float: Seconds since metrics were recorded
        """
        return (datetime.utcnow() - self.timestamp).total_seconds()