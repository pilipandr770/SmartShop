"""
Flask extensions - ініціалізація розширень
"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

# Database
db = SQLAlchemy()

# Login Manager
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Будь ласка, увійдіть для доступу до цієї сторінки."
login_manager.login_message_category = "warning"
