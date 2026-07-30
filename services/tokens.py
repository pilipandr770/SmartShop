"""
Токени для підтвердження email та скидання пароля.

Використовує itsdangerous.URLSafeTimedSerializer з SECRET_KEY застосунку -
токен самодостатній (не потребує зберігання в БД) і має вбудований TTL.
"""
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from flask import current_app

EMAIL_VERIFY_SALT = "email-verify"
PASSWORD_RESET_SALT = "password-reset"

EMAIL_VERIFY_MAX_AGE = 60 * 60 * 24 * 3  # 3 дні
PASSWORD_RESET_MAX_AGE = 60 * 60  # 1 година


def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def generate_token(email, salt):
    return _serializer().dumps(email, salt=salt)


def verify_token(token, salt, max_age):
    """Повертає email, закодований у токені, або None якщо токен
    невірний/протермінований."""
    try:
        return _serializer().loads(token, salt=salt, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
