"""
Спільний декоратор для захисту адмін-маршрутів поточного магазину (g.store).

Раніше жив як closure всередині create_app() (app.py) - винесено сюди, щоб
blueprints (routes/*.py) могли його імпортувати без циклічного імпорту з
app.py (create_app() ще не встиг би визначити closure-версію на момент
імпорту blueprint-модуля).
"""
import os
from functools import wraps

from flask import g, redirect, url_for, flash, request, abort
from flask_babel import gettext as _
from flask_login import current_user

DEMO_MODE = os.environ.get("DEMO_MODE", "true").lower() == "true"


def is_admin_logged_in() -> bool:
    """В демо-режимі завжди авторизовано; інакше - реальний Flask-Login
    користувач, що керує поточним g.store (власник або staff)."""
    if DEMO_MODE:
        return True
    return current_user.is_authenticated and current_user.can_manage_store(g.get("store"))


def admin_required(fn):
    """Декоратор для захисту адмін-маршрутів поточного магазину (g.store)."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if DEMO_MODE:
            return fn(*args, **kwargs)  # В демо-режимі пропускаємо перевірку
        if not current_user.is_authenticated:
            flash(_("Потрібен вхід в адмін-панель."), "warning")
            return redirect(url_for("user_login", next=request.path))
        if not current_user.can_manage_store(g.get("store")):
            abort(403)
        return fn(*args, **kwargs)
    return wrapper
