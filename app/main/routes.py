# app/main/routes.py
from flask import (
    Blueprint, render_template, request, flash, redirect, url_for, abort,
    send_file, make_response, current_app # Добавлены send_file, make_response, current_app
)
from flask_login import login_required, current_user # Добавлены
from sqlalchemy import or_ # Добавлено для сложных запросов
from werkzeug.utils import secure_filename # Для безопасных имен файлов
import markdown
import io # Для работы с файлами в памяти
import os # Если понадобится работа с файловой системой

from app import db
from app.models import User, Note, Tag, Notebook, note_collaborators, note_tags # Импорт всех моделей
# Убедитесь, что Blueprint импортируется из app.main, а не app
# from app import main_bp as bp - если bp определен в app/__init__.py
# Или если он определен в app/main/__init__.py:
from app.main import bp
# Импорт всех форм (предполагая, что они в app/forms.py)
from app.forms import NoteForm, NotebookForm, ShareNoteForm, ImportForm


# --- Вспомогательная функция для обработки тегов ---
def process_tags(tag_string):
    """Находит или создает теги из строки, возвращает список объектов Tag."""
    if not tag_string:
        return []
    # Приводим к нижнему регистру, удаляем лишние пробелы, игнорируем пустые, убираем дубликаты
    tag_names = list(set(name.strip().lower() for name in tag_string.split(',') if name.strip()))
    tags = []
    # Находим существующие теги одним запросом
    existing_tags = Tag.query.filter(Tag.name.in_(tag_names)).all()
    existing_names = {tag.name for tag in existing_tags}
    tags.extend(existing_tags)

    # Создаем новые теги
    new_tag_names = [name for name in tag_names if name not in existing_names]
    for name in new_tag_names:
        tag = Tag(name=name)
        db.session.add(tag) # Добавляем в сессию
        tags.append(tag)
    # Коммит не нужен здесь, он будет сделан после добавления/обновления заметки
    return tags

# --- Маршруты Заметок (Обновленные) ---

@bp.route('/')
@bp.route('/notes')
@login_required # Заметки видны только авторизованным
def index():
    """Показывает заметки, где пользователь автор ИЛИ соавтор."""
    # Получаем ID заметок, где пользователь соавтор
    collaborating_note_ids = db.session.query(note_collaborators.c.note_id)\
        .filter_by(user_id=current_user.id)\
        .subquery() # Используем subquery для чистоты

    # Фильтруем заметки: автор = текущий пользователь ИЛИ ID заметки есть в списке соавторства
    notes = Note.query.filter(
        or_(
            Note.user_id == current_user.id,
            Note.id.in_(collaborating_note_ids)
        )
    ).order_by(Note.updated_at.desc()).all()

    return render_template('main/index.html', notes=notes, title='Мои и общие заметки')

@bp.route('/notes/new', methods=['GET', 'POST'])
@login_required
def new_note():
    # Передаем request.form в форму для сохранения данных при ошибке валидации
    form = NoteForm(request.form)
    if form.validate_on_submit():
        note = Note(title=form.title.data, content=form.content.data, author=current_user) # Устанавливаем автора

        # Устанавливаем блокнот, если выбран и принадлежит пользователю
        if form.notebook.data != -1:
            notebook = Notebook.query.filter_by(id=form.notebook.data, user_id=current_user.id).first()
            if notebook:
                 note.notebook_id = form.notebook.data
            else:
                flash("Выбранный блокнот не найден или не принадлежит вам.", "warning")
                # note.notebook_id остается None

        # Обрабатываем и привязываем теги
        processed_tags = process_tags(form.tags.data)
        note.tags = processed_tags # SQLAlchemy обработает добавление в ассоциативную таблицу

        db.session.add(note)
        try:
            db.session.commit() # Коммитим все изменения (заметка, новые теги)
            flash('Заметка успешно создана!', 'success')
            return redirect(url_for('main.view_note', note_id=note.id))
        except Exception as e:
             db.session.rollback()
             current_app.logger.error(f"Ошибка создания заметки: {e}")
             flash('Ошибка при создании заметки.', 'danger')

    # Если GET или ошибка валидации, рендерим форму
    return render_template('main/note_form.html', title='Новая заметка', form=form, legend='Создать новую заметку')


@bp.route('/notes/<int:note_id>')
@login_required
def view_note(note_id):
    note = Note.query.get_or_404(note_id)

    # Проверяем доступ: автор ИЛИ соавтор
    is_owner = (note.user_id == current_user.id)
    is_collaborator = current_user in note.collaborators # Более читаемо

    if not is_owner and not is_collaborator:
        abort(403) # Нет доступа

    html_content = markdown.markdown(note.content, extensions=['fenced_code', 'tables', 'extra']) # Добавил 'extra' для доп. фич

    # Форма для шаринга нужна только владельцу
    share_form = ShareNoteForm() if is_owner else None

    return render_template(
        'main/note_view.html',
        title=note.title,
        note=note,
        html_content=html_content,
        share_form=share_form,
        is_owner=is_owner,
        is_collaborator=is_collaborator # Передаем для логики кнопок/отображения
    )

@bp.route('/notes/<int:note_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_note(note_id):
    note = Note.query.get_or_404(note_id)

    # Редактировать может только автор
    if note.user_id != current_user.id:
        abort(403)

    # При GET-запросе передаем объект note для предзаполнения
    # При POST-запросе передаем request.form для получения данных
    form = NoteForm(request.form if request.method == 'POST' else None, obj=note)

    if form.validate_on_submit():
        note.title = form.title.data
        note.content = form.content.data

        # Обновляем блокнот
        if form.notebook.data != -1:
            notebook = Notebook.query.filter_by(id=form.notebook.data, user_id=current_user.id).first()
            if notebook:
                note.notebook_id = form.notebook.data
            else:
                flash("Выбранный блокнот не найден или не принадлежит вам. Связь с блокнотом убрана.", "warning")
                note.notebook_id = None # Сбрасываем связь
        else:
            note.notebook_id = None # Убираем связь, если выбрано "Без блокнота"

        # Обновляем теги
        processed_tags = process_tags(form.tags.data)
        note.tags = processed_tags # SQLAlchemy обновит связи

        # updated_at обновится автоматически благодаря onupdate
        try:
            db.session.commit()
            flash('Заметка успешно обновлена!', 'success')
            return redirect(url_for('main.view_note', note_id=note.id))
        except Exception as e:
             db.session.rollback()
             current_app.logger.error(f"Ошибка обновления заметки {note_id}: {e}")
             flash('Ошибка при обновлении заметки.', 'danger')

    elif request.method == 'GET':
        # Предзаполняем теги вручную (SelectField заполняется в __init__ формы)
        form.tags.data = ', '.join([tag.name for tag in note.tags])

    return render_template('main/note_form.html', title='Редактировать заметку',
                           form=form, legend=f'Редактировать: {note.title}')


@bp.route('/notes/<int:note_id>/delete', methods=['POST']) # Только POST
@login_required
def delete_note(note_id):
    note = Note.query.get_or_404(note_id)

    # Удалять может только автор
    if note.user_id != current_user.id:
        abort(403)

    db.session.delete(note)
    try:
        db.session.commit()
        flash('Заметка удалена.', 'info')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Ошибка удаления заметки {note_id}: {e}")
        flash('Ошибка при удалении заметки.', 'danger')

    return redirect(url_for('main.index'))

# --- Маршруты Блокнотов ---

@bp.route('/notebooks')
@login_required
def list_notebooks():
    notebooks = Notebook.query.filter_by(user_id=current_user.id).order_by(Notebook.name).all()
    return render_template('main/notebooks.html', notebooks=notebooks, title="Мои блокноты")

@bp.route('/notebooks/new', methods=['GET', 'POST'])
@login_required
def new_notebook():
    form = NotebookForm()
    if form.validate_on_submit():
        # Валидация уникальности имени уже в форме
        notebook = Notebook(name=form.name.data, user_id=current_user.id)
        db.session.add(notebook)
        try:
            db.session.commit()
            flash('Блокнот создан!', 'success')
            return redirect(url_for('main.list_notebooks'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Ошибка создания блокнота: {e}")
            flash('Ошибка при создании блокнота.', 'danger')
    return render_template('main/notebook_form.html', form=form, title="Новый блокнот", legend="Создать блокнот")

@bp.route('/notebooks/<int:notebook_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_notebook(notebook_id):
    notebook = Notebook.query.filter_by(id=notebook_id, user_id=current_user.id).first_or_404()
    # Передаем obj для предзаполнения и request.form для POST
    form = NotebookForm(request.form if request.method == 'POST' else None, obj=notebook)
    if form.validate_on_submit():
         # Валидация уникальности уже в форме
        notebook.name = form.name.data
        try:
            db.session.commit()
            flash('Блокнот обновлен.', 'success')
            return redirect(url_for('main.list_notebooks'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Ошибка обновления блокнота {notebook_id}: {e}")
            flash('Ошибка при обновлении блокнота.', 'danger')
    return render_template('main/notebook_form.html', form=form, title="Редактировать блокнот", legend=f"Редактировать: {notebook.name}")

@bp.route('/notebooks/<int:notebook_id>/delete', methods=['POST'])
@login_required
def delete_notebook(notebook_id):
    notebook = Notebook.query.filter_by(id=notebook_id, user_id=current_user.id).first_or_404()
    # Заметки в блокноте станут "без блокнота" из-за ondelete='SET NULL' в модели Note
    db.session.delete(notebook)
    try:
        db.session.commit()
        flash('Блокнот удален. Заметки из него теперь не привязаны к блокноту.', 'info')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Ошибка удаления блокнота {notebook_id}: {e}")
        flash('Ошибка при удалении блокнота.', 'danger')
    return redirect(url_for('main.list_notebooks'))

@bp.route('/notebooks/<int:notebook_id>/notes')
@login_required
def notes_in_notebook(notebook_id):
    notebook = Notebook.query.filter_by(id=notebook_id, user_id=current_user.id).first_or_404()
    # Показываем заметки только из этого блокнота
    # Доступ (автор/соавтор) проверяется при отображении списка или при переходе к заметке
    notes = Note.query.filter_by(notebook_id=notebook.id).order_by(Note.updated_at.desc()).all()
    return render_template('main/index.html', notes=notes, notebook_context=notebook, title=f'Заметки в блокноте: {notebook.name}')


# --- Маршруты Тегов ---

@bp.route('/tags/<string:tag_name>')
@login_required
def notes_by_tag(tag_name):
    tag = Tag.query.filter(Tag.name.ilike(tag_name)).first_or_404() # Регистронезависимый поиск тега

    # Получаем ID доступных заметок (автор или соавтор)
    collaborating_note_ids = db.session.query(note_collaborators.c.note_id)\
        .filter_by(user_id=current_user.id)\
        .subquery()

    # Фильтруем заметки с этим тегом, которые доступны пользователю
    notes = Note.query.join(note_tags).join(Tag).filter(
        Tag.id == tag.id, # Присоединяем по тегу
        or_(
            Note.user_id == current_user.id,
            Note.id.in_(collaborating_note_ids)
        )
    ).order_by(Note.updated_at.desc()).all()

    return render_template('main/index.html', notes=notes, tag_context=tag, title=f'Заметки с тегом: {tag.name}')


# --- Маршруты Сотрудничества (Collaboration) ---

@bp.route('/notes/<int:note_id>/share', methods=['POST'])
@login_required
def share_note(note_id):
    note = Note.query.get_or_404(note_id)
    if note.user_id != current_user.id: # Только автор может делиться
        abort(403)

    # Используем форму для валидации и CSRF
    form = ShareNoteForm()
    if form.validate_on_submit():
        user_to_share = User.query.filter(User.username.ilike(form.username.data)).first()
        # Дополнительные проверки (не найден, не сам себе, не добавлен ли уже) - теперь в форме
        note.collaborators.append(user_to_share)
        try:
            db.session.commit()
            flash(f'Заметка теперь доступна пользователю "{user_to_share.username}".', 'success')
            # TODO: Здесь можно добавить уведомление для user_to_share (если нужна система уведомлений)
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Ошибка шаринга заметки {note_id} для user {user_to_share.username}: {e}")
            flash(f'Ошибка при добавлении соавтора.', 'danger')
    else:
        # Выводим ошибки валидации формы
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Ошибка в поле '{getattr(form, field).label.text}': {error}", 'danger')

    return redirect(url_for('main.view_note', note_id=note_id))


@bp.route('/notes/<int:note_id>/unshare/<int:user_id>', methods=['POST'])
@login_required
def unshare_note(note_id, user_id):
    """Удаляет пользователя из соавторов."""
    note = Note.query.get_or_404(note_id)
    if note.user_id != current_user.id: # Только автор может управлять доступом
        abort(403)
    # CSRF защита через токен в форме шаблона note_view.html
    # csrf.protect() - может быть применен глобально или через request hook

    user_to_unshare = User.query.get_or_404(user_id)

    if user_to_unshare in note.collaborators:
        note.collaborators.remove(user_to_unshare)
        try:
            db.session.commit()
            flash(f'Доступ для пользователя "{user_to_unshare.username}" отозван.', 'success')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Ошибка отмены шаринга заметки {note_id} для user {user_id}: {e}")
            flash(f'Ошибка при отмене доступа.', 'danger')
    else:
        flash(f'Пользователь "{user_to_unshare.username}" не является соавтором этой заметки.', 'info')

    return redirect(url_for('main.view_note', note_id=note_id))


# --- Маршруты Публикации ---

@bp.route('/notes/<int:note_id>/publish', methods=['POST'])
@login_required
def publish_note(note_id):
    note = Note.query.get_or_404(note_id)
    if note.user_id != current_user.id:
        abort(403)

    if not note.is_public:
        note.is_public = True
        note.generate_slug() # Генерируем slug (только если его нет)
        try:
            db.session.commit()
            flash('Заметка опубликована. Доступна по публичной ссылке.', 'success')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Ошибка публикации заметки {note_id}: {e}")
            flash('Ошибка при публикации заметки.', 'danger')
    else:
        flash('Заметка уже была опубликована.', 'info')
    return redirect(url_for('main.view_note', note_id=note_id))

@bp.route('/notes/<int:note_id>/unpublish', methods=['POST'])
@login_required
def unpublish_note(note_id):
    note = Note.query.get_or_404(note_id)
    if note.user_id != current_user.id:
        abort(403)

    if note.is_public:
        note.is_public = False
        # note.public_slug = None # Опционально: можно очищать slug при снятии с публикации
        try:
            db.session.commit()
            flash('Заметка снята с публикации.', 'success')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Ошибка снятия с публикации заметки {note_id}: {e}")
            flash('Ошибка при снятии с публикации.', 'danger')
    else:
        flash('Заметка не была опубликована.', 'info')
    return redirect(url_for('main.view_note', note_id=note_id))

# Публичный просмотр (БЕЗ @login_required!)
@bp.route('/public/<string:slug>')
def public_view_note(slug):
    # Ищем опубликованную заметку по slug
    note = Note.query.filter_by(public_slug=slug, is_public=True).first_or_404()
    html_content = markdown.markdown(note.content, extensions=['fenced_code', 'tables', 'extra'])
    # Используем отдельный шаблон для публичного просмотра
    return render_template('main/public_note_view.html', note=note, html_content=html_content, title=note.title)


# --- Маршруты Импорта/Экспорта ---

@bp.route('/notes/<int:note_id>/export/md')
@login_required
def export_note_md(note_id):
    note = Note.query.get_or_404(note_id)
    # Доступ: автор или соавтор
    if note.user_id != current_user.id and current_user not in note.collaborators:
        abort(403)

    # Формируем безопасное имя файла
    filename = secure_filename(note.title[:50].replace(' ', '_') or 'note') + '.md'
    # Создаем response в памяти
    mem_file = io.BytesIO()
    mem_file.write(f"# {note.title}\n\n".encode('utf-8')) # Добавляем заголовок в файл
    mem_file.write(note.content.encode('utf-8'))
    mem_file.seek(0) # Перемещаем курсор в начало файла

    return send_file(
        mem_file,
        mimetype='text/markdown; charset=utf-8', # Указываем кодировку
        download_name=filename,
        as_attachment=True # Скачать как файл
    )

@bp.route('/notes/<int:note_id>/export/html')
@login_required
def export_note_html(note_id):
    note = Note.query.get_or_404(note_id)
    # Доступ: автор или соавтор
    if note.user_id != current_user.id and current_user not in note.collaborators:
        abort(403)

    html_content = markdown.markdown(note.content, extensions=['fenced_code', 'tables', 'extra'])
    # Создаем полный HTML документ со стилями
    full_html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{note.title}</title>
    <style>
        body {{ font-family: sans-serif; margin: 2em; line-height: 1.6; }}
        h1 {{ border-bottom: 1px solid #eee; padding-bottom: 0.3em; }}
        pre {{ background-color: #f8f8f8; padding: 1em; border: 1px solid #ddd; overflow: auto; border-radius: 3px; }}
        code {{ font-family: monospace; background-color: #f8f8f8; padding: 0.2em 0.4em; border-radius: 3px;}}
        pre > code {{ background-color: transparent; padding: 0; border-radius: 0;}}
        table {{ border-collapse: collapse; margin-bottom: 1em; width: auto; }}
        th, td {{ border: 1px solid #ddd; padding: 0.5em; text-align: left; }}
        th {{ background-color: #f8f8f8; }}
        blockquote {{ border-left: 4px solid #ddd; padding-left: 1em; color: #666; margin-left: 0; }}
        img {{ max-width: 100%; height: auto; }}
    </style>
</head>
<body>
    <h1>{note.title}</h1>
    <hr>
    {html_content}
    <hr>
    <p><small>Экспортировано из Заметок Markdown</small></p>
</body>
</html>"""

    filename = secure_filename(note.title[:50].replace(' ', '_') or 'note') + '.html'
    mem_file = io.BytesIO()
    mem_file.write(full_html.encode('utf-8'))
    mem_file.seek(0)

    return send_file(
        mem_file,
        mimetype='text/html; charset=utf-8',
        download_name=filename,
        as_attachment=True
    )

@bp.route('/import', methods=['GET', 'POST'])
@login_required
def import_notes():
    form = ImportForm()
    # Динамическая загрузка блокнотов для формы импорта (если поле добавлено)
    # if current_user.is_authenticated:
    #    form.notebook.choices = [(-1, '-- Без блокнота --')] + [(nb.id, nb.name) for nb in Notebook.query.filter_by(user_id=current_user.id).order_by('name').all()]
    # else:
    #    form.notebook.choices = [(-1, '-- Без блокнота --')]

    if form.validate_on_submit():
        f = form.md_file.data
        filename = secure_filename(f.filename)
        try:
            content = f.read().decode('utf-8')
            # Определение заголовка: первая строка вида "# Заголовок"
            lines = content.split('\n', 1)
            title = f"Импорт: {filename}" # Заголовок по умолчанию
            note_content = content # Содержимое по умолчанию

            if lines[0].strip().startswith('# '): # Решетка и пробел
                potential_title = lines[0].strip()[2:].strip() # Убираем '# ' и пробелы
                if potential_title: # Убедимся, что заголовок не пустой
                    title = potential_title
                    note_content = lines[1].strip() if len(lines) > 1 else '' # Остальное - содержимое

            new_note = Note(title=title, content=note_content, author=current_user)

            # Опционально: добавляем в выбранный блокнот
            # notebook_id = form.notebook.data
            # if notebook_id != -1:
            #     notebook = Notebook.query.filter_by(id=notebook_id, user_id=current_user.id).first()
            #     if notebook:
            #         new_note.notebook_id = notebook_id
            #     else:
            #         flash(f"Выбранный блокнот ({notebook_id}) не найден, импортировано без блокнота.", "warning")

            db.session.add(new_note)
            db.session.commit()
            flash(f'Заметка "{new_note.title}" успешно импортирована!', 'success')
            return redirect(url_for('main.view_note', note_id=new_note.id))

        except UnicodeDecodeError:
             flash('Ошибка декодирования файла. Убедитесь, что файл сохранен в кодировке UTF-8.', 'danger')
             current_app.logger.warning(f"Ошибка декодирования при импорте файла {filename}")
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Ошибка импорта файла {filename}: {e}", exc_info=True) # Логируем с трейсбеком
            flash(f'Произошла непредвиденная ошибка при импорте файла. См. логи сервера.', 'danger')

    return render_template('main/import.html', title='Импорт заметок', form=form)


# --- Обработчики ошибок ---
@bp.app_errorhandler(403) # Обработчик для всего приложения
def forbidden_error(error):
    return render_template('errors/403.html'), 403

@bp.app_errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404

@bp.app_errorhandler(500)
def internal_error(error):
    db.session.rollback() # Откатываем транзакцию
    # Логирование ошибки можно добавить здесь, если не настроено глобально
    current_app.logger.error(f"Server Error: {error}", exc_info=True)
    return render_template('errors/500.html'), 500