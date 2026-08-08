"""
Flask extensions - ініціалізація розширень
"""
import os

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Database
db = SQLAlchemy()
migrate = Migrate()

# Login Manager
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Будь ласка, увійдіть для доступу до цієї сторінки."
login_manager.login_message_category = "warning"

# CSRF Protection - застосовується до всіх POST/PUT/PATCH/DELETE запитів
csrf = CSRFProtect()

# Rate limiting - захист /login, /register, /signup від brute-force та
# credential-stuffing. За замовчуванням немає глобальних лімітів, тільки
# явно позначені маршрути (default_limits=[] нижче). Лічильники зберігаються
# в Redis (REDIS_URL), якщо він налаштований - це ОБОВ'ЯЗКОВО, а не "на
# майбутнє": gunicorn вже сьогодні працює з кількома воркерами (--workers 3,
# Dockerfile), і in-memory storage веде окремий лічильник у КОЖНОМУ воркері,
# тобто фактичний ліміт "5 на хвилину" на практиці міг бути ~15 на хвилину.
# Якщо REDIS_URL не заданий (напр. в тестах, tests/conftest.py), тихо
# відкочується на in-memory - не ламає локальну розробку/CI без Redis.
_redis_url = os.environ.get("REDIS_URL", "")
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri=_redis_url or "memory://",
)
