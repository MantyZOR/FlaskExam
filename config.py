import os
from dotenv import load_dotenv

# Определяем базовую директорию проекта
basedir = os.path.abspath(os.path.dirname(__file__))
# Загружаем переменные окружения из .env файла
load_dotenv(os.path.join(basedir, '.env'))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'
    # Используем DATABASE_URL из .env или значение по умолчанию
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'app.db') # База данных SQLite в корне проекта
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Дополнительные настройки, если понадобятся