"""
Модель користувача та ролі
"""
import json
import secrets
from datetime import datetime
from enum import Enum
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from extensions import db


class UserRole(str, Enum):
    """Ролі користувачів."""
    CUSTOMER = "customer"          # B2C клієнт
    PARTNER = "partner"            # B2B партнер
    MANAGER = "manager"            # Менеджер магазину (staff)
    ADMIN = "admin"                # Адміністратор (legacy, один магазин)
    STORE_OWNER = "store_owner"    # Власник магазину (SaaS-орендар)
    PLATFORM_OWNER = "platform_owner"  # Оператор SaaS-платформи (усі магазини)


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

    # Магазин, до якого належить цей акаунт (покупець/співробітник конкретного
    # store). NULL для власника (він посилається через Store.owner_user_id) і
    # для акаунтів, створених до впровадження multi-tenancy.
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=True, index=True)
    
    # Двофакторна автентифікація (опційна, вмикається користувачем самостійно
    # в адмінці). Секрет зберігається ЗАШИФРОВАНИМ (Fernet, той самий ключ,
    # що й для креденшелів перевізників - services/crypto.py) - витік БД сам
    # по собі не дав би змоги генерувати коди. Резервні коди зберігаються як
    # ХЕШІ (як пароль) - навіть застосунок не може їх "прочитати" назад,
    # лише звірити введений код з хешем.
    _totp_secret_encrypted = db.Column("totp_secret_encrypted", db.Text, nullable=True)
    totp_enabled = db.Column(db.Boolean, default=False, nullable=False)
    _totp_backup_codes = db.Column("totp_backup_codes", db.Text, nullable=True)

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
        """Чи є адміністратором (legacy, одномагазинний режим)."""
        return self.role == UserRole.ADMIN.value

    @property
    def is_store_owner(self):
        """Чи є власником магазину (SaaS-орендар)."""
        return self.role == UserRole.STORE_OWNER.value

    @property
    def is_platform_owner(self):
        """Чи є оператором усієї SaaS-платформи (бачить усі магазини)."""
        return self.role == UserRole.PLATFORM_OWNER.value

    @property
    def is_manager(self):
        """Чи має права керування магазином (адмінка)."""
        return self.role in [
            UserRole.ADMIN.value,
            UserRole.MANAGER.value,
            UserRole.STORE_OWNER.value,
        ]

    def can_manage_store(self, store):
        """Чи може цей користувач керувати конкретним магазином store."""
        if store is None:
            return False
        if store.owner_user_id == self.id:
            return True
        return self.store_id == store.id and self.is_manager
    
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

    # ----- Двофакторна автентифікація (TOTP) -----

    @property
    def totp_secret(self):
        from services.crypto import decrypt_str
        return decrypt_str(self._totp_secret_encrypted)

    def start_totp_setup(self):
        """Генерує НОВИЙ секрет і зберігає його (зашифрованим), але ще НЕ
        вмикає 2FA - totp_enabled лишається False, доки користувач не
        підтвердить, що дійсно додав акаунт у застосунок-автентифікатор
        (confirm_totp_setup). Повторний виклик перезаписує попередній
        непідтверджений секрет - нешкідливо, бо він ще ніде не активний."""
        import pyotp
        from services.crypto import encrypt_str
        secret = pyotp.random_base32()
        self._totp_secret_encrypted = encrypt_str(secret)
        self.totp_enabled = False
        return secret

    def get_totp_uri(self, issuer="SmartShop AI"):
        import pyotp
        secret = self.totp_secret
        if not secret:
            return None
        return pyotp.totp.TOTP(secret).provisioning_uri(name=self.email, issuer_name=issuer)

    def verify_totp_code(self, code):
        """Перевіряє 6-значний код з застосунку-автентифікатора. valid_window=1
        дозволяє невеликий дрейф годинника (±30с) - стандартна практика для TOTP."""
        import pyotp
        secret = self.totp_secret
        if not secret or not code:
            return False
        return pyotp.TOTP(secret).verify(code.strip(), valid_window=1)

    def confirm_totp_setup(self, code):
        """Підтверджує налаштування 2FA введеним кодом і вмикає його.
        Повертає список ОДНОРАЗОВО показаних резервних кодів (plaintext) -
        застосунок сам їх більше ніколи не зможе показати, лише звірити хеш."""
        if not self.verify_totp_code(code):
            return None
        self.totp_enabled = True
        return self.regenerate_backup_codes()

    def regenerate_backup_codes(self, count=8):
        """Створює новий набір резервних кодів (на випадок втрати телефону),
        інвалідуючи всі попередні. Повертає plaintext-коди для одноразового
        показу - у БД лишаються тільки їхні хеші."""
        codes = ["-".join([secrets.token_hex(2), secrets.token_hex(2)]) for _ in range(count)]
        self._totp_backup_codes = json.dumps([
            {"hash": generate_password_hash(code), "used": False} for code in codes
        ])
        return codes

    def verify_backup_code(self, code):
        """Звіряє одноразовий резервний код і, якщо він валідний і ще не
        використаний, позначає його використаним (одноразовість)."""
        if not self._totp_backup_codes or not code:
            return False
        entries = json.loads(self._totp_backup_codes)
        code = code.strip()
        for entry in entries:
            if not entry["used"] and check_password_hash(entry["hash"], code):
                entry["used"] = True
                self._totp_backup_codes = json.dumps(entries)
                return True
        return False

    def disable_totp(self):
        self.totp_enabled = False
        self._totp_secret_encrypted = None
        self._totp_backup_codes = None
    
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
