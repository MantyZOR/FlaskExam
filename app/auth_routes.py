from flask import Blueprint, render_template, flash, redirect, url_for, request
from flask_login import login_user, logout_user, current_user, login_required
from werkzeug.urls import url_parse
from app import db #, bcrypt # Если используете bcrypt
from app.models import User
from app.forms import LoginForm, RegistrationForm

bp = Blueprint('auth', __name__) # Создаем Blueprint 'auth'

@bp.route('/register', methods=['GET', 'POST'])
def register():
    # Если пользователь уже вошел, перенаправляем на главную
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data) # Хешируем пароль
        db.session.add(user)
        db.session.commit()
        flash('Поздравляем, вы успешно зарегистрированы!', 'success')
        # Можно сразу войти после регистрации или перенаправить на страницу входа
        login_user(user) # Сразу входим
        return redirect(url_for('main.index')) # Перенаправляем на главную страницу заметок
        # Или: return redirect(url_for('auth.login')) # Перенаправляем на страницу входа
    return render_template('auth/register.html', title='Регистрация', form=form)


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = LoginForm()
    if form.validate_on_submit():
        # Ищем пользователя по email или username
        user = User.query.filter((User.username == form.email_or_username.data) | (User.email == form.email_or_username.data)).first()

        # Проверяем, найден ли пользователь и верен ли пароль
        if user is None or not user.check_password(form.password.data):
            flash('Неверное имя пользователя/email или пароль.', 'danger')
            return redirect(url_for('auth.login'))

        # Входим пользователем
        login_user(user, remember=form.remember_me.data)
        flash(f'Добро пожаловать, {user.username}!', 'success')

        # Перенаправляем на предыдущую страницу или на главную
        next_page = request.args.get('next')
        if not next_page or url_parse(next_page).netloc != '':
            next_page = url_for('main.index')
        return redirect(next_page)

    return render_template('auth/login.html', title='Вход', form=form)


@bp.route('/logout')
@login_required # Выйти может только залогиненный пользователь
def logout():
    logout_user()
    flash('Вы успешно вышли из системы.', 'info')
    return redirect(url_for('main.index')) # Или на страницу входа: url_for('auth.login')