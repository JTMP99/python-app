from typing import Optional, Dict, Any, List
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError
from app.models.db_models import StreamCapture, CaptureMetrics
from app import db
import logging

class CaptureServiceError(Exception):
    """Base exception for capture service errors"""
    pass

class CaptureNotFoundError(CaptureServiceError):
    """Raised when a capture record is not found"""
    pass

class DatabaseError(CaptureServiceError):
    """Raised when a database operation fails"""
    pass

class CaptureService:
    VALID_STATUSES = {
        'created',
        'initialized',
        'capturing',
        'stopping',
        'completed',
        'failed'
    }

    @staticmethod
    def create_capture(stream_url: str) -> Optional[StreamCapture]:
        """Creates a new StreamCapture record in the database."""
        try:
            # Create with initial status 'created'
            capture = StreamCapture(
                stream_url=stream_url,
                status="created",
                created_at=datetime.utcnow(),
                capture_metadata={},
                errors=[]
            )
            logging.info(f"Creating new capture for URL: {stream_url}")
            db.session.add(capture)
            db.session.commit()
            logging.info(f"Successfully created capture: {capture.id}")
            return capture
        except SQLAlchemyError as e:
            logging.error(f"Database error creating capture: {str(e)}")
            db.session.rollback()
            raise DatabaseError(f"Failed to create capture: {str(e)}")

    @staticmethod
    def get_capture(capture_id: str) -> Optional[StreamCapture]:
        """Retrieves a StreamCapture record by its ID."""
        try:
            capture = StreamCapture.query.get(capture_id)
            if not capture:
                logging.warning(f"Capture not found: {capture_id}")
                raise CaptureNotFoundError(f"Capture {capture_id} not found")
            return capture
        except SQLAlchemyError as e:
            logging.error(f"Database error retrieving capture {capture_id}: {str(e)}")
            raise DatabaseError(f"Failed to retrieve capture: {str(e)}")

    @staticmethod
    def update_capture_status(
        capture_id: str, 
        status: str, 
        error: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Optional[StreamCapture]:
        """Updates the status of a StreamCapture record."""
        try:
            if status not in CaptureService.VALID_STATUSES:
                raise ValueError(f"Invalid status: {status}")

            capture = StreamCapture.query.get(capture_id)
            if not capture:
                logging.error(f"Capture not found for status update: {capture_id}")
                raise CaptureNotFoundError(f"Capture {capture_id} not found")

            logging.info(f"Updating capture {capture_id} status to: {status}")
            capture.status = status
            capture.updated_at = datetime.utcnow()

            if start_time:
                capture.start_time = start_time
            if end_time:
                capture.end_time = end_time
                
            if error:
                if not capture.errors:
                    capture.errors = []
                capture.errors.append({
                    "time": datetime.utcnow().isoformat(),
                    "error": str(error)
                })
            
            db.session.commit()
            logging.info(f"Successfully updated capture {capture_id} status")
            return capture
        except SQLAlchemyError as e:
            logging.error(f"Database error updating capture status: {str(e)}")
            db.session.rollback()
            raise DatabaseError(f"Failed to update capture status: {str(e)}")

    @staticmethod
    def update_capture_metadata(capture_id: str, **kwargs: Any) -> Optional[StreamCapture]:
        """Updates the metadata for a capture record."""
        try:
            capture = StreamCapture.query.get(capture_id)
            if not capture:
                logging.error(f"Capture not found for metadata update: {capture_id}")
                raise CaptureNotFoundError(f"Capture {capture_id} not found")

            if not capture.capture_metadata:
                capture.capture_metadata = {}

            # Update specific fields that should be at root level
            root_fields = {'video_path', 'screenshot_paths', 'debug_info'}
            for field in root_fields & set(kwargs.keys()):
                setattr(capture, field, kwargs.pop(field))

            # Update remaining fields in metadata dict
            capture.capture_metadata.update(kwargs)
            capture.updated_at = datetime.utcnow()
            
            db.session.commit()
            logging.info(f"Successfully updated capture {capture_id} metadata")
            return capture
        except SQLAlchemyError as e:
            logging.error(f"Database error updating capture metadata: {str(e)}")
            db.session.rollback()
            raise DatabaseError(f"Failed to update capture metadata: {str(e)}")

    @staticmethod
    def add_metric(
        capture_id: str,
        cpu_usage: float,
        memory_usage: float,
        frame_rate: float
    ) -> bool:
        """Adds a CaptureMetrics record associated with a capture."""
        try:
            capture = StreamCapture.query.get(capture_id)
            if not capture:
                logging.error(f"Capture not found for adding metrics: {capture_id}")
                raise CaptureNotFoundError(f"Capture {capture_id} not found")

            metric = CaptureMetrics(
                capture_id=capture.id,
                cpu_usage=cpu_usage,
                memory_usage=memory_usage,
                frame_rate=frame_rate,
                timestamp=datetime.utcnow()
            )
            db.session.add(metric)
            db.session.commit()
            logging.info(f"Successfully added metrics for capture {capture_id}")
            return True
        except SQLAlchemyError as e:
            logging.error(f"Database error adding metric: {str(e)}")
            db.session.rollback()
            raise DatabaseError(f"Failed to add metric: {str(e)}")

    @staticmethod
    def get_capture_with_metrics(capture_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a StreamCapture object with its associated metrics."""
        try:
            capture = StreamCapture.query.get(capture_id)
            if not capture:
                logging.warning(f"Capture not found: {capture_id}")
                return None
                
            metrics = (CaptureMetrics.query
                      .filter_by(capture_id=capture_id)
                      .order_by(CaptureMetrics.timestamp.desc())
                      .limit(10)
                      .all())

            capture_data = capture.to_dict()
            capture_data['recent_metrics'] = [m.to_dict() for m in metrics]
            return capture_data
        except SQLAlchemyError as e:
            logging.error(f"Database error retrieving capture with metrics: {str(e)}")
            raise DatabaseError(f"Failed to retrieve capture with metrics: {str(e)}")