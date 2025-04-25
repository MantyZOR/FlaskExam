# file: app/__init__.py
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager # Импорт LoginManager
from flask_bcrypt import Bcrypt # Импорт Bcrypt (опционально, если используете)
# --- Важно импортировать Config ДО его использования ---
from config import Config
from datetime import datetime, timezone
import os # Добавлен для отладки

# --- Инициализация расширений ---
db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()
login_manager = LoginManager() # Создаем экземпляр LoginManager
bcrypt = Bcrypt() # Создаем экземпляр Bcrypt (опционально)

# --- Настройки Flask-Login ---
# Указываем Flask-Login, где находится view-функция для входа
# 'auth.login' - 'auth' это имя Blueprint, 'login' - имя функции
login_manager.login_view = 'auth.login'
# Сообщение, которое будет показываться при попытке доступа к защищенной странице без входа
login_manager.login_message = 'Пожалуйста, войдите, чтобы получить доступ к этой странице.'
login_manager.login_message_category = 'info' # Категория для flash сообщения

# --- Фабрика приложения ---
def create_app(config_class=Config):
    app = Flask(__name__)

    # --- Отладочная информация о SECRET_KEY ---
    print("-" * 40)
    print(f"--- [create_app] Initial app.config['SECRET_KEY'] (before from_object): {app.config.get('SECRET_KEY')}")
    # Загружаем конфигурацию из объекта Config
    app.config.from_object(config_class)
    # Проверяем ключ СРАЗУ ПОСЛЕ загрузки из объекта
    print(f"--- [create_app] app.config['SECRET_KEY'] AFTER from_object: {app.config.get('SECRET_KEY')}")
    # Дополнительно проверим ключ прямо из os.environ на этом этапе
    print(f"--- [create_app] os.environ.get('SECRET_KEY') at this point: {os.environ.get('SECRET_KEY')}")
    print("-" * 40)
    # --- Конец отладочной информации ---

    # --- Инициализация расширений с приложением ---
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app) # CSRF должен быть инициализирован ПОСЛЕ установки SECRET_KEY
    login_manager.init_app(app) # Инициализируем LoginManager
    bcrypt.init_app(app) # Инициализируем Bcrypt (опционально)

    # --- Контекстный процессор для шаблонов ---
    @app.context_processor
    def inject_now():
        # Используем UTC для единообразия или datetime.now() для локального времени сервера
        return {'now': datetime.now(timezone.utc)}

    # --- Регистрация Blueprints ---
    # Важно: импортируем блюпринты ПОСЛЕ создания 'app'
    from app.main import bp as main_bp # Переименовываем импорт
    app.register_blueprint(main_bp)

    from app.auth import bp as auth_bp # Регистрируем новый Blueprint аутентификации
    app.register_blueprint(auth_bp, url_prefix='/auth') # Добавляем префикс /auth

    # --- Контекст для Flask Shell ---
    # Импортируйте модели ПОСЛЕ определения 'db' и инициализации
    from app.models import User, Note, Tag, Notebook
    @app.shell_context_processor
    def make_shell_context():
        # Добавь все нужные модели сюда
        return {'db': db, 'User': User, 'Note': Note, 'Tag': Tag, 'Notebook': Notebook}

    return app