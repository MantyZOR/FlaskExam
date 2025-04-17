from flask import Blueprint

bp = Blueprint('main', __name__, template_folder='templates') # Указываем папку относительно Blueprint

from app.main import routes