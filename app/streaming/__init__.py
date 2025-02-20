from flask import Blueprint

streaming_bp = Blueprint('streaming', __name__)

from . import routes