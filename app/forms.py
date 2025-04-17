# app/forms.py
from flask import request # <--- ДОБАВИТЬ ЭТОТ ИМПОРТ
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import StringField, TextAreaField, SubmitField, SelectField, PasswordField, BooleanField
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError
from app.models import User, Notebook, Note # Добавил Note для примера, но он не нужен будет в валидаторе ShareNoteForm
from flask_login import current_user

# --- Форма блокнота ---
class NotebookForm(FlaskForm):
    name = StringField('Название блокнота', validators=[
        DataRequired(message="Введите название."),
        Length(min=1, max=100, message="Название должно быть от 1 до 100 символов.")])
    submit = SubmitField('Сохранить блокнот')

    # Валидация уникальности имени для текущего пользователя
    def validate_name(self, name):
        # Теперь request будет доступен здесь во время выполнения валидации
        notebook_id = request.view_args.get('notebook_id') # Получаем ID при редактировании из URL
        query = Notebook.query.filter_by(user_id=current_user.id, name=name.data)
        if notebook_id: # Исключаем текущий блокнот при редактировании
            try:
                # Убедимся, что notebook_id - это число
                current_notebook_id = int(notebook_id)
                query = query.filter(Notebook.id != current_notebook_id)
            except (ValueError, TypeError):
                # Если notebook_id невалиден, пропускаем фильтр (или можно вызвать ValidationError)
                 pass # Или raise ValidationError("Некорректный ID блокнота в URL.")
        if query.first():
            raise ValidationError('Блокнот с таким именем у вас уже существует.')


# --- Форма заметки (обновленная) ---
class NoteForm(FlaskForm):
    title = StringField('Заголовок', validators=[
        DataRequired(message="Пожалуйста, введите заголовок."),
        Length(min=1, max=120, message="Заголовок должен быть от 1 до 120 символов.")
    ])
    content = TextAreaField('Содержимое (Markdown)', validators=[
        DataRequired(message="Пожалуйста, введите содержимое заметки.")
    ])
    tags = StringField('Теги (через запятую)', validators=[Length(max=255)])
    notebook = SelectField('Блокнот', coerce=int)
    submit = SubmitField('Сохранить заметку')

    def __init__(self, *args, **kwargs):
        super(NoteForm, self).__init__(*args, **kwargs)
        # Получаем блокноты ТОЛЬКО текущего пользователя
        # `current_user` доступен через proxy Flask-Login
        if current_user.is_authenticated:
            notebook_choices = [(nb.id, nb.name) for nb in Notebook.query.filter_by(user_id=current_user.id).order_by('name').all()]
        else:
             notebook_choices = []
        self.notebook.choices = [(-1, '-- Без блокнота --')] + notebook_choices

        # Устанавливаем значение по умолчанию при редактировании (если obj передан)
        # WTForms может сам установить значение для SelectField, если `obj` передан и `coerce` правильный
        # Убедимся, что если у obj нет notebook_id или он None, ставим -1
        if 'obj' in kwargs and kwargs['obj']:
            self.notebook.data = kwargs['obj'].notebook_id if kwargs['obj'].notebook_id else -1
        # Если значение не установлено из obj, установим -1
        if self.notebook.data is None:
             self.notebook.data = -1


# --- Форма для добавления соавтора ---
class ShareNoteForm(FlaskForm):
    username = StringField('Имя пользователя', validators=[DataRequired(message="Введите имя пользователя для шаринга.")])
    submit = SubmitField('Поделиться')

    def validate_username(self, username):
        user = User.query.filter(User.username.ilike(username.data)).first() # Регистронезависимый поиск
        if not user:
             raise ValidationError('Пользователь с таким именем не найден.')
        if user.id == current_user.id:
            raise ValidationError('Нельзя поделиться заметкой с самим собой.')
        # !!! УБРАЛИ ПРОВЕРКУ НА СУЩЕСТВУЮЩЕЕ СОАВТОРСТВО ОТСЮДА !!!
        # Эта проверка будет в маршруте share_note


# --- Форма для импорта ---
class ImportForm(FlaskForm):
    md_file = FileField('Markdown файл (.md)', validators=[
        FileRequired(message="Выберите файл для импорта."),
        FileAllowed(['md', 'markdown', 'txt'], 'Разрешены только текстовые файлы Markdown (.md, .markdown, .txt)!')
    ])
    submit = SubmitField('Импортировать')