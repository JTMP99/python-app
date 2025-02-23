# app/streaming/analytics.py
from flask import Blueprint, jsonify
from sqlalchemy import func
from app.models import StreamCapture, CaptureMetrics
from app import db
from datetime import datetime, timedelta

analytics_bp = Blueprint('analytics', __name__)

@analytics_bp.route('/summary')
def get_summary():
    """Get overall system performance summary"""
    try:
        now = datetime.utcnow()
        day_ago = now - timedelta(days=1)
        
        # Capture statistics
        captures = db.session.query(
            func.count(StreamCapture.id).label('total'),
            func.sum(case((StreamCapture.status == 'completed', 1), else_=0)).label('successful'),
            func.sum(case((StreamCapture.status == 'failed', 1), else_=0)).label('failed'),
            func.avg(
                func.extract('epoch', StreamCapture.end_time - StreamCapture.start_time)
            ).label('avg_duration')
        ).filter(StreamCapture.created_at >= day_ago).first()

        # Performance metrics
        metrics = db.session.query(
            func.avg(CaptureMetrics.cpu_usage).label('avg_cpu'),
            func.avg(CaptureMetrics.memory_usage).label('avg_memory'),
            func.avg(CaptureMetrics.frame_rate).label('avg_fps')
        ).filter(CaptureMetrics.timestamp >= day_ago).first()

        return jsonify({
            'period': '24h',
            'captures': {
                'total': captures.total or 0,
                'successful': captures.successful or 0,
                'failed': captures.failed or 0,
                'success_rate': (captures.successful / captures.total * 100 if captures.total else 0),
                'avg_duration_seconds': round(captures.avg_duration or 0, 2)
            },
            'performance': {
                'avg_cpu_usage': round(metrics.avg_cpu or 0, 2),
                'avg_memory_usage': round(metrics.avg_memory or 0, 2),
                'avg_fps': round(metrics.avg_fps or 0, 2)
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@analytics_bp.route('/error-analysis')
def get_error_analysis():
    """Analyze common error patterns"""
    try:
        # Get recent errors
        recent_errors = (
            StreamCapture.query
            .filter(StreamCapture.status == 'failed')
            .order_by(StreamCapture.created_at.desc())
            .limit(100)
            .all()
        )

        # Analyze error patterns
        error_patterns = {}
        for capture in recent_errors:
            for error in capture.errors or []:
                error_msg = error.get('error', '')
                if error_msg:
                    if error_msg in error_patterns:
                        error_patterns[error_msg] += 1
                    else:
                        error_patterns[error_msg] = 1

        return jsonify({
            'total_analyzed': len(recent_errors),
            'common_errors': sorted(
                [{'error': k, 'count': v} for k, v in error_patterns.items()],
                key=lambda x: x['count'],
                reverse=True
            )
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500