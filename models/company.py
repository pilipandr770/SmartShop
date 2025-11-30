"""
Модель компанії для B2B та логів верифікації
"""
from datetime import datetime
from enum import Enum
from extensions import db


class CompanyStatus(str, Enum):
    """Статуси компанії."""
    PENDING = "pending"        # Очікує перевірки
    VERIFIED = "verified"      # Перевірено
    REJECTED = "rejected"      # Відхилено
    SUSPENDED = "suspended"    # Призупинено


class VerificationType(str, Enum):
    """Типи перевірок."""
    VAT = "vat"                    # VIES перевірка VAT
    HANDELSREGISTER = "handelsregister"  # Торговий реєстр
    WHOIS = "whois"                # WHOIS домену
    FULL = "full"                  # Повна перевірка


class ReliabilityLevel(str, Enum):
    """Рівні надійності."""
    HIGH = "high"           # 80-100
    MEDIUM = "medium"       # 50-79
    LOW = "low"             # 20-49
    CRITICAL = "critical"   # 0-19


class AlertSeverity(str, Enum):
    """Важливість алерту."""
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class Company(db.Model):
    """Модель компанії для B2B партнерів."""
    __tablename__ = "companies"
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Основна інформація
    name = db.Column(db.String(255), nullable=False)  # Назва компанії
    legal_name = db.Column(db.String(255), nullable=True)  # Юридична назва
    
    # VAT / ПДВ
    vat_number = db.Column(db.String(50), nullable=True, index=True)
    vat_country = db.Column(db.String(2), nullable=True)  # ISO код країни (DE, UA, PL)
    vat_verified = db.Column(db.Boolean, default=False)
    vat_verified_at = db.Column(db.DateTime, nullable=True)
    vat_data = db.Column(db.JSON, nullable=True)  # Дані з VIES
    
    # Handelsregister (Німеччина)
    handelsregister_id = db.Column(db.String(100), nullable=True)
    hr_verified = db.Column(db.Boolean, default=False)
    hr_data = db.Column(db.JSON, nullable=True)
    
    # Веб-сайт та WHOIS
    website = db.Column(db.String(255), nullable=True)
    domain = db.Column(db.String(255), nullable=True)  # Домен без http
    whois_data = db.Column(db.JSON, nullable=True)
    whois_checked_at = db.Column(db.DateTime, nullable=True)
    
    # Адреса
    address = db.Column(db.String(500), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    postal_code = db.Column(db.String(20), nullable=True)
    country = db.Column(db.String(100), nullable=True)
    country_code = db.Column(db.String(2), nullable=True)  # ISO код
    
    # Контакт
    contact_person = db.Column(db.String(200), nullable=True)
    contact_email = db.Column(db.String(255), nullable=True)
    contact_phone = db.Column(db.String(50), nullable=True)
    
    # B2B налаштування
    credit_limit = db.Column(db.Float, default=0.0)  # Кредитний ліміт
    payment_terms = db.Column(db.Integer, default=0)  # Днів на оплату (0 = prepaid)
    discount_percent = db.Column(db.Float, default=0.0)  # % знижки
    
    # Статус
    status = db.Column(db.String(20), default=CompanyStatus.PENDING.value)
    rejection_reason = db.Column(db.Text, nullable=True)
    
    # Reliability Score (0-100)
    reliability_score = db.Column(db.Integer, default=0)
    reliability_level = db.Column(db.String(20), default=ReliabilityLevel.CRITICAL.value)
    last_verification_at = db.Column(db.DateTime, nullable=True)
    last_verification_data = db.Column(db.JSON, nullable=True)  # Повний результат верифікації
    
    # WHOIS верифікація
    is_whois_verified = db.Column(db.Boolean, default=False)
    
    # Handelsregister верифікація
    is_hr_verified = db.Column(db.Boolean, default=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    verified_at = db.Column(db.DateTime, nullable=True)
    
    # Зв'язки
    users = db.relationship("User", back_populates="company", lazy="dynamic")
    verification_logs = db.relationship("VerificationLog", back_populates="company", lazy="dynamic")
    
    def __repr__(self):
        return f"<Company {self.name}>"
    
    @property
    def is_verified(self):
        """Чи верифікована компанія."""
        return self.status == CompanyStatus.VERIFIED.value
    
    @property
    def is_pending(self):
        """Чи очікує перевірки."""
        return self.status == CompanyStatus.PENDING.value
    
    @property
    def full_vat_number(self):
        """Повний VAT номер з кодом країни."""
        if self.vat_country and self.vat_number:
            if self.vat_number.upper().startswith(self.vat_country.upper()):
                return self.vat_number.upper()
            return f"{self.vat_country.upper()}{self.vat_number}"
        return self.vat_number
    
    @property
    def full_address(self):
        """Повна адреса."""
        parts = [self.address, self.postal_code, self.city, self.country]
        return ", ".join(filter(None, parts))
    
    def verify(self):
        """Підтверджує компанію."""
        self.status = CompanyStatus.VERIFIED.value
        self.verified_at = datetime.utcnow()
        db.session.commit()
    
    def reject(self, reason=None):
        """Відхиляє компанію."""
        self.status = CompanyStatus.REJECTED.value
        self.rejection_reason = reason
        db.session.commit()
    
    def suspend(self, reason=None):
        """Призупиняє компанію."""
        self.status = CompanyStatus.SUSPENDED.value
        self.rejection_reason = reason
        db.session.commit()


class VerificationLog(db.Model):
    """Логи верифікації компаній."""
    __tablename__ = "verification_logs"
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)
    
    # Тип перевірки
    check_type = db.Column(db.String(30), nullable=False)  # vat, handelsregister, whois
    
    # Результат
    status = db.Column(db.String(20), nullable=False)  # success, failed, error
    is_valid = db.Column(db.Boolean, nullable=True)
    
    # Дані
    request_data = db.Column(db.JSON, nullable=True)
    response_data = db.Column(db.JSON, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    
    # Зміни виявлено?
    changes_detected = db.Column(db.Boolean, default=False)
    changes_description = db.Column(db.Text, nullable=True)
    
    # Timestamps
    checked_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Зв'язки
    company = db.relationship("Company", back_populates="verification_logs")
    
    def __repr__(self):
        return f"<VerificationLog {self.check_type} for Company #{self.company_id}>"
    
    @staticmethod
    def log_check(company_id, check_type, status, is_valid=None, 
                  request_data=None, response_data=None, error_message=None,
                  changes_detected=False, changes_description=None):
        """Створює запис логу."""
        log = VerificationLog(
            company_id=company_id,
            check_type=check_type,
            status=status,
            is_valid=is_valid,
            request_data=request_data,
            response_data=response_data,
            error_message=error_message,
            changes_detected=changes_detected,
            changes_description=changes_description,
        )
        db.session.add(log)
        db.session.commit()
        return log


class AdminAlert(db.Model):
    """Алерти для адміністраторів в CRM."""
    __tablename__ = "admin_alerts"
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=True)
    
    # Тип алерту
    alert_type = db.Column(db.String(50), nullable=False)
    severity = db.Column(db.String(20), default=AlertSeverity.INFO.value)
    
    # Повідомлення
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=True)
    
    # Дані
    data = db.Column(db.JSON, nullable=True)  # Додаткові дані
    
    # Статус
    is_read = db.Column(db.Boolean, default=False)
    is_resolved = db.Column(db.Boolean, default=False)
    resolved_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    resolution_note = db.Column(db.Text, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Зв'язки
    company = db.relationship("Company", backref="alerts")
    
    def __repr__(self):
        return f"<AdminAlert {self.alert_type} - {self.severity}>"
    
    @staticmethod
    def create_alert(
        alert_type: str,
        title: str,
        message: str = None,
        company_id: int = None,
        severity: str = "info",
        data: dict = None
    ):
        """Створює новий алерт."""
        alert = AdminAlert(
            alert_type=alert_type,
            title=title,
            message=message,
            company_id=company_id,
            severity=severity,
            data=data,
        )
        db.session.add(alert)
        db.session.commit()
        return alert
    
    @staticmethod
    def get_unread_count():
        """Повертає кількість непрочитаних алертів."""
        return AdminAlert.query.filter_by(is_read=False).count()
    
    @staticmethod
    def get_critical_unresolved():
        """Повертає критичні невирішені алерти."""
        return AdminAlert.query.filter_by(
            severity=AlertSeverity.CRITICAL.value,
            is_resolved=False
        ).order_by(AdminAlert.created_at.desc()).all()
    
    def mark_read(self):
        """Позначає алерт як прочитаний."""
        self.is_read = True
        db.session.commit()
    
    def resolve(self, user_id: int, note: str = None):
        """Вирішує алерт."""
        self.is_resolved = True
        self.resolved_by = user_id
        self.resolved_at = datetime.utcnow()
        self.resolution_note = note
        db.session.commit()

