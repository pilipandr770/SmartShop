"""
Налаштування служб доставки (DHL/UPS) для магазину.
"""
from datetime import datetime
from extensions import db


class Carrier:
    DHL = "dhl"
    UPS = "ups"

    CHOICES = [DHL, UPS]
    LABELS = {DHL: "DHL", UPS: "UPS"}


class CarrierAccount(db.Model):
    """Обліковий запис служби доставки одного магазину (одна на carrier)."""
    __tablename__ = "carrier_accounts"
    __table_args__ = (
        db.UniqueConstraint('store_id', 'carrier', name='uq_carrier_accounts_store_carrier'),
        {'extend_existing': True},
    )

    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=False, index=True)

    carrier = db.Column(db.String(20), nullable=False)  # dhl, ups
    is_enabled = db.Column(db.Boolean, default=True)
    is_sandbox = db.Column(db.Boolean, default=True)

    # Креденшели - форма відрізняється між DHL і UPS, тому JSON
    # DHL: {"api_key": "...", "api_secret": "...", "account_number": "..."}
    # UPS: {"client_id": "...", "client_secret": "...", "account_number": "..."}
    credentials = db.Column(db.JSON, nullable=True)

    # Адреса відправлення (звідки їде посилка)
    origin_name = db.Column(db.String(200), nullable=True)
    origin_phone = db.Column(db.String(50), nullable=True)
    origin_street = db.Column(db.String(255), nullable=True)
    origin_city = db.Column(db.String(100), nullable=True)
    origin_postal_code = db.Column(db.String(20), nullable=True)
    origin_country_code = db.Column(db.String(2), nullable=True)  # ISO2, напр. DE

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<CarrierAccount {self.carrier} store={self.store_id}>"

    @property
    def carrier_label(self):
        return Carrier.LABELS.get(self.carrier, self.carrier)

    @property
    def origin_address(self):
        """Повертає адресу відправлення у форматі, очікуваному ShippingProvider."""
        return {
            "name": self.origin_name or "",
            "phone": self.origin_phone or "",
            "street": self.origin_street or "",
            "city": self.origin_city or "",
            "postal_code": self.origin_postal_code or "",
            "country_code": (self.origin_country_code or "").upper(),
        }

    @property
    def is_test_mode(self):
        """Тестовий провайдер вмикається, якщо sandbox + креденшели-заглушки 'test'."""
        if not self.is_sandbox or not self.credentials:
            return False
        values = [v for v in self.credentials.values() if isinstance(v, str)]
        return bool(values) and all(v == "test" for v in values)

    @staticmethod
    def get_enabled_for_store(store_id):
        return CarrierAccount.query.filter_by(store_id=store_id, is_enabled=True).all()
