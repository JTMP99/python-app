from flask import Blueprint

scraping_bp = Blueprint('scraping', __name__)

from . import routes
