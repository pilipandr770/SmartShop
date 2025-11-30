"""
Моделі замовлень
"""
from datetime import datetime
from enum import Enum
from extensions import db


class OrderStatus(str, Enum):
    """Статуси замовлення."""
    CREATED = "created"        # Створено
    PENDING = "pending"        # Очікує оплати
    PAID = "paid"              # Оплачено
    PROCESSING = "processing"  # В обробці
    SHIPPED = "shipped"        # Відправлено
    DELIVERED = "delivered"    # Доставлено
    CANCELLED = "cancelled"    # Скасовано
    REFUNDED = "refunded"      # Повернено


class PaymentMethod(str, Enum):
    """Способи оплати."""
    CARD = "card"              # Карткою (Stripe)
    INVOICE = "invoice"        # По рахунку (B2B)
    CASH = "cash"              # Готівкою при отриманні
    PREPAID = "prepaid"        # Передоплата


class Order(db.Model):
    """Замовлення."""
    __tablename__ = "orders"
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(50), unique=True, nullable=True)  # SM-2025-0001
    
    # Користувач (може бути NULL для гостей)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=True)
    
    # Тип замовлення
    is_b2b = db.Column(db.Boolean, default=False)
    
    # Клієнт (для гостей або додаткова інфо)
    customer_name = db.Column(db.String(200), nullable=True)
    customer_email = db.Column(db.String(255), nullable=True)
    customer_phone = db.Column(db.String(50), nullable=True)
    
    # Доставка
    shipping_address = db.Column(db.Text, nullable=True)
    shipping_city = db.Column(db.String(100), nullable=True)
    shipping_postal_code = db.Column(db.String(20), nullable=True)
    shipping_country = db.Column(db.String(100), nullable=True)
    shipping_method = db.Column(db.String(50), nullable=True)  # nova_poshta, ukrposhta, etc.
    shipping_cost = db.Column(db.Float, default=0.0)
    tracking_number = db.Column(db.String(100), nullable=True)
    
    # Оплата
    payment_method = db.Column(db.String(20), default=PaymentMethod.CARD.value)
    payment_status = db.Column(db.String(20), nullable=True)
    stripe_payment_intent = db.Column(db.String(255), nullable=True)
    stripe_session_id = db.Column(db.String(255), nullable=True)
    
    # Суми
    subtotal = db.Column(db.Float, nullable=False, default=0.0)  # Сума товарів
    discount = db.Column(db.Float, default=0.0)  # Знижка
    tax = db.Column(db.Float, default=0.0)  # Податок
    amount = db.Column(db.Float, nullable=False, default=0.0)  # Фінальна сума
    currency = db.Column(db.String(8), nullable=False, default="UAH")
    
    # Статус
    status = db.Column(db.String(20), nullable=False, default=OrderStatus.CREATED.value)
    
    # Нотатки
    notes = db.Column(db.Text, nullable=True)  # Коментар клієнта
    admin_notes = db.Column(db.Text, nullable=True)  # Нотатки адміна
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    paid_at = db.Column(db.DateTime, nullable=True)
    shipped_at = db.Column(db.DateTime, nullable=True)
    delivered_at = db.Column(db.DateTime, nullable=True)
    
    # Зв'язки
    items = db.relationship("OrderItem", backref="order", lazy=True, cascade="all, delete-orphan")
    company = db.relationship("Company", backref="orders")
    
    def __repr__(self):
        return f"<Order #{self.id}>"
    
    @property
    def status_display(self):
        """Людський статус."""
        statuses = {
            "created": "Створено",
            "pending": "Очікує оплати",
            "paid": "Оплачено",
            "processing": "В обробці",
            "shipped": "Відправлено",
            "delivered": "Доставлено",
            "cancelled": "Скасовано",
            "refunded": "Повернено",
        }
        return statuses.get(self.status, self.status)
    
    @property
    def items_count(self):
        """Кількість позицій."""
        return sum(item.quantity for item in self.items)
    
    def generate_order_number(self):
        """Генерує номер замовлення."""
        year = datetime.utcnow().year
        prefix = "B2B" if self.is_b2b else "SM"
        self.order_number = f"{prefix}-{year}-{self.id:05d}"
        db.session.commit()
    
    def calculate_totals(self):
        """Перераховує суми."""
        self.subtotal = sum(item.total for item in self.items)
        self.amount = self.subtotal - self.discount + self.shipping_cost + self.tax
        db.session.commit()


class OrderItem(db.Model):
    """Позиція замовлення."""
    __tablename__ = "order_items"
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=True)
    
    # Дані товару на момент замовлення (snapshot)
    product_name = db.Column(db.String(200), nullable=False)
    product_sku = db.Column(db.String(64), nullable=True)
    
    # Ціни
    price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    currency = db.Column(db.String(8), nullable=False, default="UAH")
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Зв'язки
    product = db.relationship("Product", backref="order_items")
    
    def __repr__(self):
        return f"<OrderItem {self.product_name} x{self.quantity}>"
    
    @property
    def total(self):
        """Сума позиції."""
        return self.price * self.quantity
