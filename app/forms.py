# app/forms.py
from flask import request
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import StringField, TextAreaField, SubmitField, SelectField, PasswordField, BooleanField
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError
from app.models import User, Notebook, Note # Добавил Note для примера, но он не нужен будет в валидаторе ShareNoteForm
from flask_login import current_user
from flask import request # Импортируем request
from flask_login import current_user

# --- Форма для добавления соавтора ---
class ShareNoteForm(FlaskForm):
    username = StringField('Имя пользователя', validators=[
        DataRequired(message="Введите имя пользователя для шаринга.")
    ])
    submit = SubmitField('Поделиться')

    # Валидатор для проверки существования пользователя и других условий
    def validate_username(self, username_field):
        user_to_share = User.query.filter(User.username.ilike(username_field.data)).first() # Регистронезависимый поиск

        if not user_to_share:
            raise ValidationError(f'Пользователь "{username_field.data}" не найден.')

        if user_to_share.id == current_user.id:
            raise ValidationError('Вы не можете поделиться заметкой с самим собой.')

# --- Форма блокнота ---
class NotebookForm(FlaskForm):
    name = StringField('Название блокнота', validators=[
        DataRequired(message="Введите название."),
        Length(min=1, max=100, message="Название должно быть от 1 до 100 символов.")])
    submit = SubmitField('Сохранить блокнот')

    def __init__(self, *args, **kwargs): # Добавляем __init__ для сохранения оригинального имени при редактировании
        super(NotebookForm, self).__init__(*args, **kwargs)
        self.original_name = None
        notebook_id = request.view_args.get('notebook_id')
        if notebook_id and not self.name.data: # Если это редактирование и форма не была отправлена (GET)
             notebook = Notebook.query.filter_by(id=notebook_id, user_id=current_user.id).first()
             if notebook:
                 self.original_name = notebook.name

    # Валидация уникальности имени для текущего пользователя
    def validate_name(self, name):
        # Проверяем, изменилось ли имя (или это новая запись)
        if name.data != self.original_name:
             # request должен быть доступен во время валидации, импортируйте `from flask import request`
            notebook_id = request.view_args.get('notebook_id') # Получаем ID при редактировании из URL
            query = Notebook.query.filter_by(user_id=current_user.id, name=name.data)
            # Исключать текущий блокнот из проверки не нужно, т.к. мы проверяем только если имя ИЗМЕНИЛОСЬ
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
    notebook = SelectField('Блокнот', coerce=int) # coerce=int важен для обработки значения
    submit = SubmitField('Сохранить заметку')

    def __init__(self, *args, **kwargs):
        super(NoteForm, self).__init__(*args, **kwargs)
        # Получаем блокноты ТОЛЬКО текущего пользователя
        if current_user.is_authenticated:
            notebook_choices = [(nb.id, nb.name) for nb in Notebook.query.filter_by(user_id=current_user.id).order_by('name').all()]
        else:
             notebook_choices = []
        self.notebook.choices = [(-1, '-- Без блокнота --')] + notebook_choices

        # Установка значения по умолчанию при редактировании (если передан obj)
        # WTForms может сам установить значение для SelectField, если `obj` передан и `coerce` правильный
        # Убедимся, что если у obj нет notebook_id или он None, ставим -1
        if 'obj' in kwargs and kwargs['obj']:
            obj_notebook_id = getattr(kwargs['obj'], 'notebook_id', None)
            self.notebook.data = obj_notebook_id if obj_notebook_id is not None else -1
        # Если значение не установлено из obj или не было obj, установим -1
        elif self.notebook.data is None:
             self.notebook.data = -1


# --- Форма для импорта ---
class ImportForm(FlaskForm):
    md_file = FileField('Markdown файл (.md)', validators=[
        FileRequired(message="Выберите файл для импорта."),
        FileAllowed(['md', 'markdown', 'txt'], 'Разрешены только текстовые файлы Markdown (.md, .markdown, .txt)!')
    ])
    submit = SubmitField('Импортировать')