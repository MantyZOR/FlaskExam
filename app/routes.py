from flask import (
    Blueprint, render_template, request, flash, redirect, url_for, abort
)
from app import db
from app.models import Note
from app.models import Tag
from app.forms import NoteForm
import markdown # Для конвертации Markdown в HTML

# Создаем Blueprint 'main'
bp = Blueprint('main', __name__)

def process_tags(tag_string):
    if not tag_string:
        return []
    tag_names = [name.strip().lower() for name in tag_string.split(',') if name.strip()]
    tags = []
    for name in tag_names:
        tag = Tag.query.filter_by(name=name).first()
        if tag is None:
            tag = Tag(name=name)
            db.session.add(tag)
            # Нужно закоммитить здесь или передать сессию, чтобы получить ID,
            # но проще добавить все новые теги и коммитить позже
        tags.append(tag)
    # Коммитим новые теги, если они были созданы внутри цикла
    db.session.commit()
    return tags
    
@bp.route('/')
@bp.route('/notes')
def index():
    """Отображает список всех заметок."""
    notes = Note.query.order_by(Note.updated_at.desc()).all()
    return render_template('index.html', notes=notes, title='Все заметки')

@bp.route('/notes/new', methods=['GET', 'POST'])
def new_note():
    """Создание новой заметки."""
    form = NoteForm()
    if form.validate_on_submit():
        note = Note(title=form.title.data, content=form.content.data)
        db.session.add(note)
        db.session.commit()
        flash('Заметка успешно создана!', 'success')
        return redirect(url_for('main.view_note', note_id=note.id))
    return render_template('note_form.html', title='Новая заметка', form=form, legend='Создать новую заметку')

@bp.route('/notes/<int:note_id>')
def view_note(note_id):
    """Просмотр одной заметки."""
    note = Note.query.get_or_404(note_id)
    # Конвертируем Markdown в HTML
    html_content = markdown.markdown(note.content, extensions=['fenced_code', 'tables']) # Добавляем расширения по желанию
    return render_template('note_view.html', title=note.title, note=note, html_content=html_content)

@bp.route('/notes/<int:note_id>/edit', methods=['GET', 'POST'])
def edit_note(note_id):
    """Редактирование существующей заметки."""
    note = Note.query.get_or_404(note_id)
    # Здесь будет проверка прав доступа, когда добавим пользователей
    # if note.author != current_user:
    #     abort(403) # Forbidden
    form = NoteForm()
    if form.validate_on_submit(): # Если данные POST-запроса валидны
        note.title = form.title.data
        note.content = form.content.data
        # updated_at обновится автоматически благодаря onupdate
        db.session.commit()
        flash('Заметка успешно обновлена!', 'success')
        return redirect(url_for('main.view_note', note_id=note.id))
    elif request.method == 'GET': # Если это GET-запрос, заполняем форму данными из БД
        form.title.data = note.title
        form.content.data = note.content
    return render_template('note_form.html', title='Редактировать заметку',
                           form=form, legend=f'Редактировать: {note.title}')

@bp.route('/notes/<int:note_id>/delete', methods=['POST']) # Только POST для безопасности
def delete_note(note_id):
    """Удаление заметки."""
    note = Note.query.get_or_404(note_id)
    # Здесь будет проверка прав доступа
    # if note.author != current_user:
    #     abort(403)
    db.session.delete(note)
    db.session.commit()
    flash('Заметка удалена.', 'info')
    return redirect(url_for('main.index'))

# Можно добавить обработчики ошибок 404, 500 и т.д.
@bp.app_errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@bp.app_errorhandler(500)
def internal_error(error):
    db.session.rollback() # Откатываем транзакцию в случае ошибки сервера
    return render_template('500.html'), 500