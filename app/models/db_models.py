# app/models.py
from datetime import datetime
from sqlalchemy import Column, String, DateTime, JSON, Integer
from sqlalchemy.dialects.postgresql import UUID
from app import db
import uuid

class StreamCapture(db.Model):
    __tablename__ = 'stream_captures'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stream_url = Column(String, nullable=False)
    status = Column(String, nullable=False, default='created')
    capture_metadata = Column(JSON, nullable=False, default=dict)  # Changed from 'metadata'
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    errors = Column(JSON, default=list)
    video_path = Column(String)
    video_size = Column(Integer)
    
    def to_dict(self):
        return {
            'id': str(self.id),
            'stream_url': self.stream_url,
            'status': self.status,
            'capture_metadata': self.capture_metadata,  # Updated to new name
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'errors': self.errors,
            'video_path': self.video_path,
            'video_size': self.video_size
        }

    def update_status(self, status, error=None):
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

class CaptureMetrics(db.Model):
    """Track performance metrics"""
    __tablename__ = 'capture_metrics'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    capture_id = Column(UUID(as_uuid=True), ForeignKey('stream_captures.id'), nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    cpu_usage = Column(Integer)
    memory_usage = Column(Integer)
    frame_rate = Column(Integer)
    capture_metadata = Column(JSON, default=dict)  # Changed from 'metadata'