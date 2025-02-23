from app.models import Proxy, ProxyUsage
from app import db
from datetime import datetime, timedelta
import requests
import random
from sqlalchemy import func

class ProxyService:
    @staticmethod
    def get_best_proxy():
        """Get the best available proxy based on success rate and usage"""
        return (
            Proxy.query
            .filter_by(is_active=True)
            .filter(Proxy.last_used <= datetime.utcnow() - timedelta(seconds=30))
            .order_by((Proxy.success_count / (Proxy.success_count + Proxy.fail_count + 1)).desc())
            .first()
        )

    @staticmethod
    def record_proxy_use(proxy_id, capture_id, success, error=None, response_time=None):
        """Record proxy usage result"""
        proxy = Proxy.query.get(proxy_id)
        if not proxy:
            return

        # Update proxy stats
        if success:
            proxy.success_count += 1
        else:
            proxy.fail_count += 1

        proxy.last_used = datetime.utcnow()

        # Record usage
        usage = ProxyUsage(
            proxy_id=proxy_id,
            capture_id=capture_id,
            used_at=datetime.utcnow(),
            success=success,
            error=error,
            response_time=response_time
        )
        
        db.session.add(usage)
        db.session.commit()

    @staticmethod
    def test_proxy(proxy):
        """Test proxy connectivity"""
        try:
            test_url = 'https://api.ipify.org?format=json'
            proxies = {
                'http': f"{proxy.protocol}://{proxy.username}:{proxy.password}@{proxy.address}:{proxy.port}",
                'https': f"{proxy.protocol}://{proxy.username}:{proxy.password}@{proxy.address}:{proxy.port}"
            }
            
            start_time = datetime.utcnow()
            response = requests.get(test_url, proxies=proxies, timeout=10)
            response_time = (datetime.utcnow() - start_time).total_seconds()
            
            return True, response_time
            
        except Exception as e:
            return False, str(e)

    @staticmethod
    def rotate_proxies():
        """Test and update all proxies"""
        proxies = Proxy.query.all()
        for proxy in proxies:
            success, result = ProxyService.test_proxy(proxy)
            if isinstance(result, float):  # Success with response time
                proxy.is_active = True
                proxy.metadata = {
                    **(proxy.metadata or {}),
                    'last_test': datetime.utcnow().isoformat(),
                    'response_time': result
                }
            else:  # Failed with error message
                proxy.is_active = False
                proxy.metadata = {
                    **(proxy.metadata or {}),
                    'last_test': datetime.utcnow().isoformat(),
                    'last_error': result
                }
            
        db.session.commit()

    @staticmethod
    def get_proxy_analytics():
        """Get proxy performance analytics"""
        return db.session.query(
            Proxy.address,
            Proxy.protocol,
            Proxy.is_active,
            func.count(ProxyUsage.id).label('total_uses'),
            func.avg(ProxyUsage.response_time).label('avg_response_time'),
            func.sum(ProxyUsage.success.cast(db.Integer)).label('successes'),
            func.count(ProxyUsage.error).label('failures')
        ).join(
            ProxyUsage, Proxy.id == ProxyUsage.proxy_id
        ).group_by(
            Proxy.id
        ).all()