from typing import Optional, Dict, Any, List, Union
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
        'initialized',
        'capturing',
        'stopping',
        'completed',
        'failed'
    }

    @staticmethod
    def create_capture(stream_url: str) -> Optional[StreamCapture]:
        """Creates a new StreamCapture record in the database.
        
        Args:
            stream_url (str): URL of the stream to capture
            
        Returns:
            Optional[StreamCapture]: The created capture record or None if failed
        """
        try:
            capture = StreamCapture(
                stream_url=stream_url,
                status="initialized",
                created_at=datetime.utcnow()
            )
            db.session.add(capture)
            db.session.commit()
            logging.info(f"Created capture record in DB: {capture.id}")
            return capture
        except SQLAlchemyError as e:
            logging.error(f"Database error creating capture: {e}")
            db.session.rollback()
            return None

    @staticmethod
    def get_capture(capture_id: str) -> Optional[StreamCapture]:
        """Retrieves a StreamCapture record by its ID.
        
        Args:
            capture_id (str): The ID of the capture to retrieve
            
        Returns:
            Optional[StreamCapture]: The found capture or None
            
        Raises:
            DatabaseError: If database query fails
        """
        try:
            return StreamCapture.query.get(capture_id)
        except SQLAlchemyError as e:
            logging.error(f"Database error retrieving capture {capture_id}: {e}")
            raise DatabaseError(f"Failed to retrieve capture: {e}")

    @staticmethod
    def update_capture_status(
        capture_id: str, 
        status: str, 
        error: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        duration: Optional[int] = None
    ) -> Optional[StreamCapture]:
        """Updates the status and related timing fields of a StreamCapture record.
        
        Args:
            capture_id (str): ID of the capture to update
            status (str): New status value
            error (Optional[str]): Error message if any
            start_time (Optional[datetime]): Capture start time
            end_time (Optional[datetime]): Capture end time
            duration (Optional[int]): Capture duration in seconds
        """
        try:
            if status not in CaptureService.VALID_STATUSES:
                raise ValueError(f"Invalid status: {status}")

            capture = StreamCapture.query.get(capture_id)
            if not capture:
                return None

            capture.status = status
            if start_time:
                capture.start_time = start_time
            if end_time:
                capture.end_time = end_time
            if duration:
                capture.duration = duration
                
            if error:
                if not capture.errors:
                    capture.errors = []
                capture.errors.append({
                    "time": datetime.utcnow().isoformat(),
                    "error": str(error)
                })
            
            db.session.commit()
            return capture
        except SQLAlchemyError as e:
            logging.error(f"Database error updating capture status: {e}")
            db.session.rollback()
            return None

    @staticmethod
    def update_capture_metadata(capture_id: str, **kwargs: Any) -> Optional[StreamCapture]:
        """Updates the metadata for a capture record
        
        Args:
            capture_id (str): ID of the capture to update
            **kwargs: Key-value pairs to update in metadata
        """
        try:
            capture = StreamCapture.query.get(capture_id)
            if not capture:
                return None

            if not capture.capture_metadata:
                capture.capture_metadata = {}

            # Update specific fields that should be at root level
            root_fields = {'video_path', 'screenshot_paths', 'debug_info'}
            for field in root_fields & set(kwargs.keys()):
                setattr(capture, field, kwargs.pop(field))

            # Update remaining fields in metadata dict
            capture.capture_metadata.update(kwargs)
            db.session.commit()
            return capture
        except SQLAlchemyError as e:
            logging.error(f"Database error updating capture metadata: {e}")
            db.session.rollback()
            return None

    @staticmethod
    def stop_capture(capture_id: str) -> bool:
        """Stops the capture.
        
        Args:
            capture_id (str): The ID of the capture to stop
            
        Returns:
            bool: True if stopped successfully
            
        Raises:
            CaptureNotFoundError: If capture doesn't exist
            DatabaseError: If database operation fails
        """
        try:
            capture = StreamCapture.query.get(capture_id)
            if not capture:
                raise CaptureNotFoundError(f"Capture {capture_id} not found")
                
            capture.status = "stopping"
            capture.end_time = datetime.utcnow()
            db.session.commit()
            return True
        except SQLAlchemyError as e:
            db.session.rollback()
            logging.error(f"Database error stopping capture: {e}")
            raise DatabaseError(f"Failed to stop capture: {e}")

    @staticmethod
    def delete_capture(capture_id):
        """Deletes a StreamCapture record from the database."""
        capture = StreamCapture.query.get(capture_id)
        if capture:
            db.session.delete(capture)
            db.session.commit()

    @staticmethod
    def bulk_delete_captures(capture_ids: List[str]) -> bool:
        """Deletes multiple StreamCapture records.
        
        Args:
            capture_ids (List[str]): List of capture IDs to delete
            
        Returns:
            bool: True if all deletions successful
            
        Raises:
            DatabaseError: If database operation fails
        """
        try:
            result = StreamCapture.query.filter(
                StreamCapture.id.in_(capture_ids)
            ).delete(synchronize_session=False)
            db.session.commit()
            return bool(result)
        except SQLAlchemyError as e:
            db.session.rollback()
            logging.error(f"Database error in bulk delete: {e}")
            raise DatabaseError(f"Failed to bulk delete captures: {e}")

    @staticmethod
    def add_metric(
        capture_id: str,
        cpu_usage: float,
        memory_usage: float,
        frame_rate: float
    ) -> bool:
        """Adds a CaptureMetrics record associated with a capture.
        
        Args:
            capture_id (str): The ID of the capture
            cpu_usage (float): CPU usage percentage
            memory_usage (float): Memory usage in MB
            frame_rate (float): Frames per second
            
        Returns:
            bool: True if metric was added successfully
            
        Raises:
            CaptureNotFoundError: If capture doesn't exist
            DatabaseError: If database operation fails
        """
        try:
            capture = StreamCapture.query.get(capture_id)
            if not capture:
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
            return True
        except SQLAlchemyError as e:
            db.session.rollback()
            logging.error(f"Database error adding metric: {e}")
            raise DatabaseError(f"Failed to add metric: {e}")

    @staticmethod
    def get_capture_with_metrics(capture_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a StreamCapture object with its associated metrics.
        
        Args:
            capture_id (str): ID of the capture to retrieve
            
        Returns:
            Optional[Dict[str, Any]]: Capture data with metrics or None if not found
            
        Raises:
            DatabaseError: If database query fails
        """
        try:
            capture = StreamCapture.query.get(capture_id)
            if not capture:
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
            logging.error(f"Database error retrieving capture with metrics: {e}")
            raise DatabaseError(f"Failed to retrieve capture with metrics: {e}")