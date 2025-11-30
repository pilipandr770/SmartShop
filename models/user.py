"""
Модель користувача та ролі
"""
from datetime import datetime
from enum import Enum
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from extensions import db


class UserRole(str, Enum):
    """Ролі користувачів."""
    CUSTOMER = "customer"      # B2C клієнт
    PARTNER = "partner"        # B2B партнер
    MANAGER = "manager"        # Менеджер
    ADMIN = "admin"            # Адміністратор


class User(UserMixin, db.Model):
    """Модель користувача."""
    __tablename__ = "users"
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    
    # Роль та статус
    role = db.Column(db.String(20), nullable=False, default=UserRole.CUSTOMER.value)
    is_active = db.Column(db.Boolean, default=True)
    is_verified = db.Column(db.Boolean, default=False)  # Email підтверджено
    
    # Профіль
    first_name = db.Column(db.String(100), nullable=True)
    last_name = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    
    # B2B - зв'язок з компанією
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=True)
    company = db.relationship("Company", back_populates="users")
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)
    
    # Зв'язки
    orders = db.relationship("Order", backref="user", lazy="dynamic")
    
    def __repr__(self):
        return f"<User {self.email}>"
    
    def set_password(self, password):
        """Хешує та зберігає пароль."""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Перевіряє пароль."""
        return check_password_hash(self.password_hash, password)
    
    @property
    def full_name(self):
        """Повне ім'я."""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name or self.last_name or self.email.split("@")[0]
    
    @property
    def is_admin(self):
        """Чи є адміністратором."""
        return self.role == UserRole.ADMIN.value
    
    @property
    def is_manager(self):
        """Чи є менеджером або адміном."""
        return self.role in [UserRole.ADMIN.value, UserRole.MANAGER.value]
    
    @property
    def is_b2b(self):
        """Чи є B2B партнером."""
        return self.role == UserRole.PARTNER.value and self.company_id is not None
    
    @property
    def is_b2c(self):
        """Чи є B2C клієнтом."""
        return self.role == UserRole.CUSTOMER.value
    
    def update_last_login(self):
        """Оновлює час останнього входу."""
        self.last_login = datetime.utcnow()
        db.session.commit()
    
    @staticmethod
    def get_by_email(email):
        """Знаходить користувача за email."""
        return User.query.filter_by(email=email.lower().strip()).first()
    
    @staticmethod
    def create_user(email, password, role=UserRole.CUSTOMER, **kwargs):
        """Створює нового користувача."""
        user = User(
            email=email.lower().strip(),
            role=role.value if isinstance(role, UserRole) else role,
            **kwargs
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return user
