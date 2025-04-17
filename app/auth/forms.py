from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError
from app.models import User

class LoginForm(FlaskForm):
    username = StringField('Имя пользователя', validators=[DataRequired()])
    password = PasswordField('Пароль', validators=[DataRequired()])
    remember_me = BooleanField('Запомнить меня')
    submit = SubmitField('Войти')

class RegistrationForm(FlaskForm):
    username = StringField('Имя пользователя', validators=[
        DataRequired(message="Пожалуйста, введите имя пользователя."),
        Length(min=3, max=64, message="Имя должно быть от 3 до 64 символов.")])
    email = StringField('Email', validators=[
        DataRequired(message="Пожалуйста, введите email."),
        Email(message="Некорректный email.")])
    password = PasswordField('Пароль', validators=[
        DataRequired(message="Пожалуйста, введите пароль."),
        Length(min=6, message="Пароль должен быть не менее 6 символов.")])
    confirm_password = PasswordField('Подтвердите пароль', validators=[
        DataRequired(message="Пожалуйста, подтвердите пароль."),
        EqualTo('password', message='Пароли должны совпадать.')])
    submit = SubmitField('Зарегистрироваться')

    # Кастомные валидаторы для проверки уникальности
    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('Это имя пользователя уже занято. Пожалуйста, выберите другое.')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('Этот email уже зарегистрирован. Пожалуйста, используйте другой.')