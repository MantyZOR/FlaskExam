import io  # Для работы с файлами в памяти
import markdown
from flask import abort, current_app
from flask import (
    render_template, request, flash, redirect, url_for, send_file  # Добавлены send_file, make_response, current_app
)
from flask_login import login_required, current_user
from sqlalchemy import or_  # Нужен для index
from werkzeug.utils import secure_filename  # Для безопасных имен файлов

from app import db
from app.forms import NoteForm, NotebookForm, ShareNoteForm, ImportForm
from app.main import bp
from app.models import User, Note, Tag, Notebook, note_collaborators, note_tags  # Импорт всех моделей


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

# --- Маршруты Заметок (Обновленные для Collaboration) ---

@bp.route('/')
@bp.route('/notes')
@login_required
def index():
    """Показывает заметки, где пользователь автор ИЛИ соавтор."""
    # Получаем ID заметок, где текущий пользователь является соавтором
    # Это можно сделать через subquery или直接 через relationship
    notes_query = Note.query.filter(
        or_(
            Note.user_id == current_user.id, # Заметки автора
            Note.collaborators.any(User.id == current_user.id) # Заметки, где он соавтор
        )
    ).order_by(Note.updated_at.desc())

    notes = notes_query.all()
    # Передаем в шаблон app/templates/main/index.html
    return render_template('index.html', notes=notes, title='Мои и общие заметки')

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
    return render_template('note_form.html', title='Новая заметка', form=form, legend='Создать новую заметку')


# new_note - без изменений для коллаборации (создает только автор)

@bp.route('/notes/<int:note_id>')
@login_required
def view_note(note_id):
    note = Note.query.get_or_404(note_id)

    is_owner = (note.user_id == current_user.id)
    # Правильная проверка статуса соавтора
    is_collaborator_check = note.collaborators.filter(User.id == current_user.id).count() > 0

    if not is_owner and not is_collaborator_check: # Используем правильную проверку
        abort(403)

    html_content = markdown.markdown(note.content, extensions=['fenced_code', 'tables', 'extra'])
    share_form = ShareNoteForm() if is_owner else None

    return render_template(
        'note_view.html',
        title=note.title,
        note=note,
        html_content=html_content,
        share_form=share_form,
        is_owner=is_owner,
        is_collaborator=is_collaborator_check, # <--- ПЕРЕДАЕМ РЕАЛЬНЫЙ СТАТУС
        # Этот флаг можно оставить, если он где-то нужен для отображения
        is_shared_only=is_collaborator_check and not is_owner
    )

@bp.route('/notes/<int:note_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_note(note_id):
    note = Note.query.get_or_404(note_id)

    # --- ОБНОВЛЕННАЯ ПРОВЕРКА ДОСТУПА ---
    is_owner = (note.user_id == current_user.id)
    # Проверяем, является ли текущий пользователь соавтором
    is_collaborator = note.collaborators.filter(User.id == current_user.id).count() > 0

    # Запрещаем доступ, если пользователь НЕ владелец И НЕ соавтор
    if not is_owner and not is_collaborator:
        abort(403)
    # --- КОНЕЦ ОБНОВЛЕННОЙ ПРОВЕРКИ ---

    # При GET-запросе передаем объект note для предзаполнения
    # При POST-запросе передаем request.form для получения данных
    form = NoteForm(request.form if request.method == 'POST' else None, obj=note)

    # Динамически заполняем поле notebook, если это не было сделано в __init__
    # (NoteForm.__init__ уже должен это делать, но для надежности можно оставить)
    if current_user.is_authenticated:
         notebook_choices = [(nb.id, nb.name) for nb in Notebook.query.filter_by(user_id=current_user.id).order_by('name').all()]
         form.notebook.choices = [(-1, '-- Без блокнота --')] + notebook_choices
         # Устанавливаем текущее значение, если оно есть и форма не отправлена
         if request.method == 'GET' and note.notebook_id is not None:
             form.notebook.data = note.notebook_id
         elif request.method == 'GET':
              form.notebook.data = -1


    if form.validate_on_submit():
        # --- Обновляем поля, доступные и соавторам ---
        note.title = form.title.data
        note.content = form.content.data
        # Обновляем теги
        processed_tags = process_tags(form.tags.data)
        note.tags = processed_tags # SQLAlchemy обновит связи

        # --- Обновляем блокнот (ТОЛЬКО ДЛЯ АВТОРА) ---
        # Решаем, что менять блокнот может только владелец для упрощения
        if is_owner:
            if form.notebook.data != -1:
                # Автор может выбрать только СВОЙ блокнот
                notebook = Notebook.query.filter_by(id=form.notebook.data, user_id=current_user.id).first()
                if notebook:
                    note.notebook_id = form.notebook.data
                else:
                    # Если автор выбрал несуществующий/чужой блокнот
                    flash("Выбранный блокнот не найден или не принадлежит вам. Связь с блокнотом убрана.", "warning")
                    note.notebook_id = None # Сбрасываем связь
            else:
                # Автор выбрал "Без блокнота"
                note.notebook_id = None # Убираем связь
        # Если редактирует соавтор, поле notebook_id не трогаем

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
        # Предзаполняем теги вручную (SelectField заполняется выше или в __init__)
        form.tags.data = ', '.join([tag.name for tag in note.tags])

    return render_template('note_form.html', title='Редактировать заметку',
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
    return render_template('notebooks.html', notebooks=notebooks, title="Мои блокноты")

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
    return render_template('notebook_form.html', form=form, title="Новый блокнот", legend="Создать блокнот")

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
    return render_template('notebook_form.html', form=form, title="Редактировать блокнот", legend=f"Редактировать: {notebook.name}")

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
    return render_template('index.html', notes=notes, notebook_context=notebook, title=f'Заметки в блокноте: {notebook.name}')


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

    return render_template('index.html', notes=notes, tag_context=tag, title=f'Заметки с тегом: {tag.name}')


# --- Маршруты Сотрудничества (Collaboration) ---
@bp.route('/notes/<int:note_id>/share', methods=['POST'])
@login_required
def share_note(note_id):
    note = Note.query.get_or_404(note_id)
    # >>> ПРОВЕРКА: Только автор может делиться <<<
    if note.user_id != current_user.id:
        abort(403)

    form = ShareNoteForm() # Используем форму для валидации CSRF и базовых проверок
    if form.validate_on_submit():
        # Валидаторы в форме уже проверили существование пользователя и не-самого-себя
        user_to_share = User.query.filter(User.username.ilike(form.username.data)).first()

        # >>> ДОБАВЛЕНА ПРОВЕРКА: Не является ли пользователь уже соавтором? <<<
        if note.collaborators.filter(User.id == user_to_share.id).count() > 0:
            flash(f'Пользователь "{user_to_share.username}" уже является соавтором этой заметки.', 'warning')
        else:
            # Если все проверки пройдены, добавляем в соавторы
            note.collaborators.append(user_to_share)
            try:
                db.session.commit()
                flash(f'Заметка "{note.title}" теперь доступна пользователю "{user_to_share.username}".', 'success')
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Ошибка шаринга заметки {note_id} для {user_to_share.username}: {e}")
                flash('Не удалось поделиться заметкой из-за ошибки.', 'danger')
    else:
        # Если форма не прошла базовую валидацию (не найден, сам себя, пустое поле)
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{getattr(form, field).label.text if hasattr(getattr(form, field), 'label') else field}: {error}", 'danger')

    return redirect(url_for('main.view_note', note_id=note_id))

@bp.route('/notes/<int:note_id>/unshare/<int:user_id>', methods=['POST'])
@login_required
def unshare_note(note_id, user_id):
    note = Note.query.get_or_404(note_id)
    # >>> ПРОВЕРКА: Только автор может отменять доступ <<<
    if note.user_id != current_user.id:
        abort(403)

    # CSRF-защита сработает автоматически, т.к. вызывается из формы с токеном

    user_to_unshare = User.query.get_or_404(user_id)

    # Проверяем, действительно ли этот пользователь соавтор
    if note.collaborators.filter(User.id == user_to_unshare.id).count() > 0:
        note.collaborators.remove(user_to_unshare) # Удаляем из связи
        try:
            db.session.commit()
            flash(f'Доступ к заметке для пользователя "{user_to_unshare.username}" отозван.', 'success')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Ошибка отмены шаринга заметки {note_id} для user {user_id}: {e}")
            flash('Не удалось отозвать доступ из-за ошибки.', 'danger')
    else:
        flash(f'Пользователь "{user_to_unshare.username}" не является соавтором этой заметки.', 'warning')

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
    return render_template('public_note_view.html', note=note, html_content=html_content, title=note.title)


# --- Маршруты Импорта/Экспорта ---

@bp.route('/notes/<int:note_id>/export/md')
@login_required
def export_note_md(note_id):
    note = Note.query.get_or_404(note_id)

    # >>> ИСПРАВЛЕННАЯ ПРОВЕРКА ДОСТУПА: Автор ИЛИ Соавтор <<<
    is_owner = note.user_id == current_user.id
    # Используем .any() для эффективной проверки наличия пользователя в соавторах
    is_collaborator = note.collaborators.filter(User.id == current_user.id).count() > 0

    if not is_owner and not is_collaborator:
        abort(403) # Доступ запрещен

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

    # >>> ИСПРАВЛЕННАЯ ПРОВЕРКА ДОСТУПА: Автор ИЛИ Соавтор <<<
    is_owner = note.user_id == current_user.id
    is_collaborator = note.collaborators.filter(User.id == current_user.id).count() > 0

    if not is_owner and not is_collaborator:
        abort(403) # Доступ запрещен

    html_content = markdown.markdown(note.content, extensions=['fenced_code', 'tables', 'extra'])
    # Создаем полный HTML документ со стилями (ваш код HTML здесь без изменений)
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

    return render_template('import.html', title='Импорт заметок', form=form)


# --- Обработчики ошибок ---
@bp.app_errorhandler(403) # Обработчик для всего приложения
def forbidden_error(error):
    return render_template('403.html'), 403

@bp.app_errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@bp.app_errorhandler(500)
def internal_error(error):
    db.session.rollback() # Откатываем транзакцию
    # Логирование ошибки можно добавить здесь, если не настроено глобально
    current_app.logger.error(f"Server Error: {error}", exc_info=True)
    return render_template('500.html'), 500