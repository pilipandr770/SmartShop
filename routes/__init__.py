"""
Маршрути SmartShop
"""
from routes.auth import auth_bp
from routes.cabinet import cabinet_bp

__all__ = [
    "auth_bp",
    "cabinet_bp",
]
