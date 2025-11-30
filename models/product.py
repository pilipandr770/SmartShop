"""
Моделі товарів та категорій
"""
from datetime import datetime
from extensions import db


class Category(db.Model):
    """Категорія товарів."""
    __tablename__ = "categories"
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    slug = db.Column(db.String(120), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.String(500), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    products = db.relationship("Product", backref="category", lazy=True)
    
    def __repr__(self):
        return f"<Category {self.name}>"


class Product(db.Model):
    """Товар."""
    __tablename__ = "products"
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    sku = db.Column(db.String(64), nullable=True, unique=True)
    
    # Ціни
    price = db.Column(db.Float, nullable=False, default=0.0)
    old_price = db.Column(db.Float, nullable=True)  # Для знижок
    cost_price = db.Column(db.Float, nullable=True)  # Собівартість
    currency = db.Column(db.String(8), nullable=False, default="UAH")
    
    # B2B ціна (опційно, якщо відрізняється)
    b2b_price = db.Column(db.Float, nullable=True)
    min_b2b_quantity = db.Column(db.Integer, default=1)  # Мін. кількість для B2B
    
    # Склад
    stock = db.Column(db.Integer, nullable=False, default=0)
    reserved = db.Column(db.Integer, default=0)  # Зарезервовано в замовленнях
    min_stock = db.Column(db.Integer, default=0)  # Мін. залишок (для alert)
    
    # Описи
    short_description = db.Column(db.String(255), nullable=True)
    long_description = db.Column(db.Text, nullable=True)
    
    # Медіа
    image_url = db.Column(db.String(500), nullable=True)
    gallery = db.Column(db.JSON, nullable=True)  # Список URL додаткових фото
    
    # Зв'язки
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)
    
    # Статус
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    is_featured = db.Column(db.Boolean, default=False)  # Рекомендований
    
    # SEO
    meta_title = db.Column(db.String(100), nullable=True)
    meta_description = db.Column(db.String(200), nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<Product {self.name}>"
    
    @property
    def available_stock(self):
        """Доступний залишок (загальний - зарезервований)."""
        return max(0, self.stock - self.reserved)
    
    @property
    def is_in_stock(self):
        """Чи є в наявності."""
        return self.available_stock > 0
    
    @property
    def is_low_stock(self):
        """Чи низький залишок."""
        return self.stock <= self.min_stock and self.min_stock > 0
    
    @property
    def has_discount(self):
        """Чи є знижка."""
        return self.old_price and self.old_price > self.price
    
    @property
    def discount_percent(self):
        """Відсоток знижки."""
        if self.has_discount:
            return round((1 - self.price / self.old_price) * 100)
        return 0
    
    def get_price_for_user(self, user=None):
        """Повертає ціну для користувача (B2B або B2C)."""
        if user and user.is_b2b and self.b2b_price:
            return self.b2b_price
        return self.price
