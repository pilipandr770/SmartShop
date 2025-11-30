"""
Конфігурація додатку SmartShop
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Базова конфігурація."""
    
    # Flask
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    
    # Database
    DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///shop.db")
    DB_SCHEMA = os.environ.get("DB_SCHEMA", "smartshop")
    
    # Якщо PostgreSQL - додаємо схему
    if "postgresql" in DATABASE_URL:
        SQLALCHEMY_DATABASE_URI = DATABASE_URL
        SQLALCHEMY_ENGINE_OPTIONS = {
            "pool_pre_ping": True,
            "pool_recycle": 300,
            "connect_args": {"options": f"-c search_path={DB_SCHEMA}"}
        }
    else:
        SQLALCHEMY_DATABASE_URI = DATABASE_URL
        SQLALCHEMY_ENGINE_OPTIONS = {}
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Uploads
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB
    UPLOAD_FOLDER = "static/uploads"
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
    
    # Stripe
    STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
    STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
    STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    
    # OpenAI
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
    
    # Admin
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")
    
    # Demo mode
    DEMO_MODE = os.environ.get("DEMO_MODE", "false").lower() == "true"
    
    # Mail (для майбутнього)
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "noreply@smartshop.com")
    
    # B2B Settings
    B2B_AUTO_VERIFY = os.environ.get("B2B_AUTO_VERIFY", "false").lower() == "true"
    VAT_CHECK_ENABLED = os.environ.get("VAT_CHECK_ENABLED", "true").lower() == "true"


class DevelopmentConfig(Config):
    """Конфігурація для розробки."""
    DEBUG = True


class ProductionConfig(Config):
    """Конфігурація для продакшену."""
    DEBUG = False


class TestingConfig(Config):
    """Конфігурація для тестування."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


# Вибір конфігурації
config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
