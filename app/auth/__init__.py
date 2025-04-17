from flask import Blueprint

bp = Blueprint('auth', __name__, template_folder='templates') # Указываем папку относительно Blueprint

from app.auth import routes