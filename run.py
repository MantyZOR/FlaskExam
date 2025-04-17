from app import create_app, db # Импортируем фабрику и db
# Убедитесь, что модели импортированы *после* создания db,
# что происходит внутри create_app или перед shell context
from app.models import User, Note

# Создаем экземпляр приложения с помощью фабрики
app = create_app()

# Контекст для Flask Shell (удобно для отладки и работы с БД вручную)
@app.shell_context_processor
def make_shell_context():
    return {'db': db, 'User': User, 'Note': Note}

if __name__ == '__main__':
    # При первом запуске или изменениях в моделях, не забудьте выполнить миграции
    # export FLASK_APP=run.py (или set FLASK_APP=run.py в Windows)
    # flask db init (только один раз)
    # flask db migrate -m "Initial migration with Note table"
    # flask db upgrade

    app.run(debug=True) # Запускаем сервер разработки