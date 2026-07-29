"""
Модель магазину (tenant) для SaaS-режиму: кожен Store — ізольований магазин
одного клієнта платформи, прив'язаний до власного User (власника) та
підписки Stripe.
"""
from datetime import datetime
from extensions import db


class StoreSubscriptionStatus:
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"


# Плани підписки: назва -> (людська назва, Stripe Price ID з env, ліміт товарів)
# Стрип Price ID навмисно НЕ хардкодяться тут — вони читаються з env у
# config.py/app.py (STRIPE_PRICE_STARTER, STRIPE_PRICE_PRO, ...), тут лишається
# тільки список валідних ключів планів.
PLAN_CHOICES = ["starter", "pro", "business"]
DEFAULT_PLAN = "starter"


class Store(db.Model):
    """Магазин (tenant) — один клієнт SaaS-платформи."""
    __tablename__ = "stores"
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(255), nullable=False)
    # Використовується як піддомен: <slug>.smartshop.example
    slug = db.Column(db.String(63), unique=True, nullable=False, index=True)

    owner_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    owner = db.relationship("User", foreign_keys=[owner_user_id], backref="owned_stores")

    plan = db.Column(db.String(30), nullable=False, default=DEFAULT_PLAN)
    subscription_status = db.Column(db.String(20), nullable=False, default=StoreSubscriptionStatus.TRIALING)

    stripe_customer_id = db.Column(db.String(255), nullable=True)
    stripe_subscription_id = db.Column(db.String(255), nullable=True)

    trial_ends_at = db.Column(db.DateTime, nullable=True)

    is_active = db.Column(db.Boolean, default=True)  # ручне блокування адміном платформи

    # Власний домен клієнта (напр. myshop.com), додатково до <slug>.<BASE_DOMAIN>.
    # custom_domain_verified=True означає, що ми реально перевірили DNS-резолюцію
    # на наш VPS - без цього resolve_current_store() не довіряє цьому домену
    # (інакше будь-який власник міг би просто вписати чужий домен в налаштування).
    custom_domain = db.Column(db.String(255), unique=True, nullable=True, index=True)
    custom_domain_verified = db.Column(db.Boolean, default=False)
    custom_domain_verified_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Store {self.slug}>"

    @property
    def is_subscription_active(self):
        """Чи має магазин право на роботу (активна підписка або триває trial)."""
        if not self.is_active:
            return False
        if self.subscription_status == StoreSubscriptionStatus.ACTIVE:
            return True
        if self.subscription_status == StoreSubscriptionStatus.TRIALING:
            return not self.trial_ends_at or self.trial_ends_at > datetime.utcnow()
        return False

    @staticmethod
    def get_by_slug(slug):
        if not slug:
            return None
        return Store.query.filter_by(slug=slug.lower().strip()).first()

    @staticmethod
    def slug_is_available(slug):
        return Store.query.filter_by(slug=slug.lower().strip()).first() is None

    @staticmethod
    def get_by_custom_domain(domain):
        """Повертає Store лише якщо його custom_domain підтверджено (DNS-перевірка пройдена)."""
        if not domain:
            return None
        return Store.query.filter_by(
            custom_domain=domain.lower().strip(),
            custom_domain_verified=True,
        ).first()
