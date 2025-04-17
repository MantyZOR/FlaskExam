import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager # Импорт LoginManager
from flask_bcrypt import Bcrypt # Импорт Bcrypt (опционально, если используете)
from config import Config

db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()
login_manager = LoginManager() # Создаем экземпляр LoginManager
bcrypt = Bcrypt() # Создаем экземпляр Bcrypt (опционально)

# Указываем Flask-Login, где находится view-функция для входа
# 'auth.login' - 'auth' это имя Blueprint, 'login' - имя функции
login_manager.login_view = 'auth.login'
# Сообщение, которое будет показываться при попытке доступа к защищенной странице без входа
login_manager.login_message = 'Пожалуйста, войдите, чтобы получить доступ к этой странице.'
login_manager.login_message_category = 'info' # Категория для flash сообщения

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    login_manager.init_app(app) # Инициализируем LoginManager
    bcrypt.init_app(app) # Инициализируем Bcrypt (опционально)

    # Регистрация Blueprints
    from app.main.routes import bp as main_bp # Переименовываем импорт (см. шаг 5)
    app.register_blueprint(main_bp)

    from app.auth.routes import bp as auth_bp # Регистрируем новый Blueprint аутентификации
    app.register_blueprint(auth_bp, url_prefix='/auth') # Добавляем префикс /auth

    # Контекст приложения
    # Импортируйте User после его определения
    from app.models import User, Note
    @app.shell_context_processor
    def make_shell_context():
        return {'db': db, 'User': User, 'Note': Note} # Добавляем User

    return app