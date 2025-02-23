# app/services/capture_service.py
from app.models import StreamCapture, CaptureMetrics
from app import db
import psutil
import json

class CaptureService:
    @staticmethod
    def create_capture(stream_url):
        """Create new capture record"""
        capture = StreamCapture(
            stream_url=stream_url,
            status='created',
            metadata={
                'stages_completed': [],
                'browser_info': {},
                'network_info': {}
            }
        )
        db.session.add(capture)
        db.session.commit()
        return capture

    @staticmethod
    def update_capture_status(capture_id, status, error=None, **kwargs):
        """Update capture status and metadata"""
        capture = StreamCapture.query.get(capture_id)
        if not capture:
            return None

        capture.status = status
        capture.metadata.update(kwargs)
        
        if error:
            if not capture.errors:
                capture.errors = []
            capture.errors.append({
                'time': datetime.utcnow().isoformat(),
                'error': str(error)
            })

        db.session.commit()
        return capture

    @staticmethod
    def record_metrics(capture_id):
        """Record current performance metrics"""
        metrics = CaptureMetrics(
            capture_id=capture_id,
            cpu_usage=psutil.cpu_percent(),
            memory_usage=psutil.virtual_memory().percent,
            metadata={
                'disk_usage': psutil.disk_usage('/').percent,
                'network': json.dumps(psutil.net_io_counters()._asdict())
            }
        )
        db.session.add(metrics)
        db.session.commit()

    @staticmethod
    def get_capture_with_metrics(capture_id):
        """Get capture details with its metrics"""
        capture = StreamCapture.query.get(capture_id)
        if not capture:
            return None

        metrics = CaptureMetrics.query.filter_by(
            capture_id=capture_id
        ).order_by(CaptureMetrics.timestamp.desc()).limit(10).all()

        return {
            **capture.to_dict(),
            'recent_metrics': [m.to_dict() for m in metrics]
        }