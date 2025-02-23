from flask import Blueprint, jsonify
from sqlalchemy import func
from app.models import StreamCapture, CaptureMetrics, Proxy, ProxyUsage
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

        # Proxy performance
        proxy_stats = db.session.query(
            func.count(ProxyUsage.id).label('total_uses'),
            func.sum(case((ProxyUsage.success == True, 1), else_=0)).label('successful_uses'),
            func.avg(ProxyUsage.response_time).label('avg_response_time')
        ).filter(ProxyUsage.used_at >= day_ago).first()

        return jsonify({
            'period': '24h',
            'captures': {
                'total': captures.total,
                'successful': captures.successful,
                'failed': captures.failed,
                'success_rate': (captures.successful / captures.total * 100 if captures.total else 0),
                'avg_duration_seconds': round(captures.avg_duration or 0, 2)
            },
            'performance': {
                'avg_cpu_usage': round(metrics.avg_cpu or 0, 2),
                'avg_memory_usage': round(metrics.avg_memory or 0, 2),
                'avg_fps': round(metrics.avg_fps or 0, 2)
            },
            'proxies': {
                'total_uses': proxy_stats.total_uses,
                'successful_uses': proxy_stats.successful_uses,
                'success_rate': (proxy_stats.successful_uses / proxy_stats.total_uses * 100 
                               if proxy_stats.total_uses else 0),
                'avg_response_time': round(proxy_stats.avg_response_time or 0, 3)
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@analytics_bp.route('/proxy-performance')
def get_proxy_performance():
    """Get detailed proxy performance metrics"""
    try:
        # Get per-proxy statistics
        proxy_stats = db.session.query(
            Proxy.address,
            Proxy.protocol,
            func.count(ProxyUsage.id).label('total_uses'),
            func.sum(case((ProxyUsage.success == True, 1), else_=0)).label('successes'),
            func.avg(ProxyUsage.response_time).label('avg_response'),
            func.min(ProxyUsage.response_time).label('min_response'),
            func.max(ProxyUsage.response_time).label('max_response')
        ).join(
            ProxyUsage, Proxy.id == ProxyUsage.proxy_id
        ).group_by(
            Proxy.id
        ).all()

        return jsonify({
            'proxies': [{
                'address': stats.address,
                'protocol': stats.protocol,
                'total_uses': stats.total_uses,
                'success_rate': (stats.successes / stats.total_uses * 100 
                               if stats.total_uses else 0),
                'response_times': {
                    'avg': round(stats.avg_response or 0, 3),
                    'min': round(stats.min_response or 0, 3),
                    'max': round(stats.max_response or 0, 3)
                }
            } for stats in proxy_stats]
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
            for error in capture.errors:
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