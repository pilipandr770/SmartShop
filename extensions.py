"""
Flask extensions - ініціалізація розширень
"""
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
# явно позначені маршрути (default_limits=[] нижче) - зберігання лічильників
# in-memory (per-worker, не спільне між gunicorn-воркерами) - для одного
# сервера цього достатньо як перший рівень захисту без додаткової
# інфраструктури (Redis); якщо колись буде декілька інстансів застосунку,
# знадобиться підключити storage_uri="redis://...".
limiter = Limiter(key_func=get_remote_address, default_limits=[])
