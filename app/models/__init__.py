from flask import Blueprint

db_models_bp = Blueprint('db_models', __name__)

from . import db_models
from .db_models import StreamCapture, CaptureMetrics

__all__ = ['StreamCapture', 'CaptureMetrics']