# app/models.py
import uuid
from datetime import datetime, timezone
# Убедитесь, что Table, Column, Integer, ForeignKey импортированы из sqlalchemy
from sqlalchemy import Table, Column, Integer, ForeignKey
from app import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# --- Ассоциативная таблица для связи Пользователь <-> Заметка (Соавторы) ---
note_collaborators = db.Table('note_collaborators',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), primary_key=True),
    db.Column('note_id', db.Integer, db.ForeignKey('note.id', ondelete='CASCADE'), primary_key=True)
    # ondelete='CASCADE' означает, что если удаляется пользователь или заметка,
    # соответствующая запись в этой таблице тоже удалится.
)

# --- Таблица Тегов (если еще нет, но нужна для полноты) ---
note_tags = db.Table('note_tags',
    db.Column('note_id', db.Integer, db.ForeignKey('note.id', ondelete='CASCADE'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id', ondelete='CASCADE'), primary_key=True)
)

# --- Модель User (добавляем связь с коллаборациями) ---
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True, nullable=False)
    email = db.Column(db.String(120), index=True, unique=True, nullable=False)
    password_hash = db.Column(db.String(256)) # Увеличил длину

    # Связь с заметками, где пользователь автор (переименовано для ясности)
    notes_authored = db.relationship(
        'Note',
        back_populates='author',
        lazy='dynamic',
        foreign_keys='Note.user_id', # Явно указываем foreign key
        cascade="all, delete-orphan"
    )
    # Связь с блокнотами пользователя
    notebooks = db.relationship(
        'Notebook', back_populates='user', lazy='dynamic',
        cascade="all, delete-orphan"
    )
    # >>> НОВАЯ СВЯЗЬ: Заметки, где пользователь является соавтором <<<
    notes_collaborating = db.relationship(
        'Note',
        secondary=note_collaborators, # Через ассоциативную таблицу
        back_populates='collaborators', # Связь с полем collaborators в Note
        lazy='dynamic' # Загружать по запросу
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'

# --- Модель Tag (если еще нет) ---
class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), index=True, unique=True, nullable=False)
    notes = db.relationship(
        'Note', secondary=note_tags,
        back_populates='tags', lazy='dynamic'
    )
    def __repr__(self): return f'<Tag {self.name}>'

# --- Модель Notebook (если еще нет) ---
class Notebook(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    user = db.relationship('User', back_populates='notebooks')
    notes = db.relationship('Note', back_populates='notebook', lazy='dynamic', passive_deletes=True)
    def __repr__(self): return f'<Notebook {self.name}>'


# --- Модель Note (добавляем связь с соавторами) ---
class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Связь с автором
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    author = db.relationship('User', back_populates='notes_authored', foreign_keys=[user_id])

    # Связь с блокнотом
    notebook_id = db.Column(db.Integer, db.ForeignKey('notebook.id', ondelete='SET NULL'), nullable=True)
    notebook = db.relationship('Notebook', back_populates='notes')

    # Связь с тегами
    tags = db.relationship(
        'Tag', secondary=note_tags,
        back_populates='notes', lazy='dynamic',
        cascade="all, delete"
    )

    # >>> НОВАЯ СВЯЗЬ: Соавторы этой заметки <<<
    collaborators = db.relationship(
        'User',
        secondary=note_collaborators, # Через ассоциативную таблицу
        back_populates='notes_collaborating', # Связь с полем notes_collaborating в User
        lazy='dynamic' # Загружать по запросу
    )

    # Поля для публикации (оставим пока, не мешают)
    is_public = db.Column(db.Boolean, default=False, index=True)
    public_slug = db.Column(db.String(36), unique=True, index=True, nullable=True)

    def generate_slug(self):
        if not self.public_slug:
            while True:
                slug = uuid.uuid4().hex
                if not Note.query.filter_by(public_slug=slug).first():
                    self.public_slug = slug
                    break

    def __repr__(self):
        return f'<Note {self.title}>'