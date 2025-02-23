# app/models/__init__.py
from .db_models import db, StreamCapture, CaptureMetrics  # Import db here

__all__ = ['StreamCapture', 'CaptureMetrics', 'db'] # for from x import * use