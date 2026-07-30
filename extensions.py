"""
Flask extensions - ініціалізація розширень
"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf import CSRFProtect

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
