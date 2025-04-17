# app/models.py
import uuid
from datetime import datetime, timezone # Используйте timezone-aware datetime
from sqlalchemy import Table, Column, Integer, ForeignKey
from app import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# --- Ассоциативные таблицы ---
note_collaborators = db.Table('note_collaborators',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), primary_key=True),
    db.Column('note_id', db.Integer, db.ForeignKey('note.id', ondelete='CASCADE'), primary_key=True)
)

note_tags = db.Table('note_tags',
    db.Column('note_id', db.Integer, db.ForeignKey('note.id', ondelete='CASCADE'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id', ondelete='CASCADE'), primary_key=True)
)

# --- Модель User ---
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True, nullable=False)
    email = db.Column(db.String(120), index=True, unique=True, nullable=False)
    password_hash = db.Column(db.String(256)) # Увеличил длину для bcrypt

    # Связь с заметками, где пользователь автор (One-to-Many)
    notes_authored = db.relationship(
        'Note', back_populates='author', lazy='dynamic',
        foreign_keys='Note.user_id', # Явно указываем foreign key
        cascade="all, delete-orphan" # Удаление пользователя удалит его заметки
    )
    # Связь с блокнотами пользователя (One-to-Many)
    notebooks = db.relationship(
        'Notebook', back_populates='user', lazy='dynamic',
        cascade="all, delete-orphan" # Удаление пользователя удалит его блокноты
    )
    # Связь с заметками, где пользователь соавтор (Many-to-Many)
    notes_collaborating = db.relationship(
        'Note', secondary=note_collaborators,
        back_populates='collaborators', lazy='dynamic'
    )

    def set_password(self, password):
        # Рекомендуется использовать bcrypt напрямую или через Flask-Bcrypt
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'

# --- Модель Tag ---
class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), index=True, unique=True, nullable=False)
    # Связь с заметками (Many-to-Many)
    notes = db.relationship(
        'Note', secondary=note_tags,
        back_populates='tags', lazy='dynamic'
    )

    def __repr__(self):
        return f'<Tag {self.name}>'

# --- Модель Notebook ---
class Notebook(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False) # Связь с владельцем
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Связь с пользователем (владельцем) (Many-to-One)
    user = db.relationship('User', back_populates='notebooks')
    # Связь с заметками в этом блокноте (One-to-Many)
    # При удалении блокнота, у заметок notebook_id становится NULL (если nullable=True)
    notes = db.relationship('Note', back_populates='notebook', lazy='dynamic', passive_deletes=True) # passive_deletes для SET NULL

    def __repr__(self):
        return f'<Notebook {self.name}>'

# --- Модель Note ---
class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Связь с автором (Many-to-One)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    author = db.relationship('User', back_populates='notes_authored', foreign_keys=[user_id])

    # Связь с блокнотом (Many-to-One, nullable)
    notebook_id = db.Column(db.Integer, db.ForeignKey('notebook.id', ondelete='SET NULL'), nullable=True) # ondelete='SET NULL'
    notebook = db.relationship('Notebook', back_populates='notes')

    # Связь с соавторами (Many-to-Many)
    collaborators = db.relationship(
        'User', secondary=note_collaborators,
        back_populates='notes_collaborating', lazy='dynamic'
    )
    # Связь с тегами (Many-to-Many)
    tags = db.relationship(
        'Tag', secondary=note_tags,
        back_populates='notes', lazy='dynamic',
        cascade="all, delete" # Cascade delete для связи с тегами
    )

    # Поля для публикации
    is_public = db.Column(db.Boolean, default=False, index=True)
    public_slug = db.Column(db.String(36), unique=True, index=True, nullable=True)

    def generate_slug(self):
        """Генерирует уникальный UUID для публичного доступа, если его еще нет."""
        if not self.public_slug:
            while True:
                slug = uuid.uuid4().hex
                # Проверяем уникальность сгенерированного slug
                if not Note.query.filter_by(public_slug=slug).first():
                    self.public_slug = slug
                    break
        # Если slug уже есть, но его нужно перегенерировать (редко нужно)
        # else:
        #     # Логика перегенерации, если требуется

    def __repr__(self):
        return f'<Note {self.title}>'