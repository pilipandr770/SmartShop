"""
Моделі товарів та категорій
Updated: 2025-12-07 - Force reload for Render deployment
"""
from datetime import datetime
import base64
from extensions import db


class Image(db.Model):
    """Зображення, що зберігаються в базі даних."""
    __tablename__ = "images"
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), unique=True, nullable=False)
    data = db.Column(db.LargeBinary, nullable=False)  # Binary image data
    mime_type = db.Column(db.String(50), nullable=False)  # image/jpeg, image/png, etc.
    size = db.Column(db.Integer, nullable=False)  # File size in bytes
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<Image {self.filename}>"
    
    def to_base64(self):
        """Convert image data to base64 for embedding in HTML."""
        return base64.b64encode(self.data).decode('utf-8')
    
    def get_data_uri(self):
        """Get data URI for direct embedding in HTML."""
        return f"data:{self.mime_type};base64,{self.to_base64()}"


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
    
    # Мультимовність
    name_en = db.Column(db.String(120), nullable=True)
    name_de = db.Column(db.String(120), nullable=True)
    description_en = db.Column(db.Text, nullable=True)
    description_de = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    products = db.relationship("Product", backref="category", lazy=True)
    
    def __repr__(self):
        return f"<Category {self.name}>"
    
    def get_name(self, locale='uk'):
        """Повертає назву відповідно до мови."""
        if locale == 'en' and self.name_en:
            return self.name_en
        elif locale == 'de' and self.name_de:
            return self.name_de
        return self.name
    
    def get_description(self, locale='uk'):
        """Повертає опис відповідно до мови."""
        if locale == 'en' and self.description_en:
            return self.description_en
        elif locale == 'de' and self.description_de:
            return self.description_de
        return self.description or ''


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
    
    # Мультимовність
    name_en = db.Column(db.String(200), nullable=True)
    name_de = db.Column(db.String(200), nullable=True)
    short_description_en = db.Column(db.String(255), nullable=True)
    short_description_de = db.Column(db.String(255), nullable=True)
    long_description_en = db.Column(db.Text, nullable=True)
    long_description_de = db.Column(db.Text, nullable=True)
    
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
    
    def get_name(self, locale='uk'):
        """Повертає назву відповідно до мови."""
        if locale == 'en' and self.name_en:
            return self.name_en
        elif locale == 'de' and self.name_de:
            return self.name_de
        return self.name
    
    def get_short_description(self, locale='uk'):
        """Повертає короткий опис відповідно до мови."""
        if locale == 'en' and self.short_description_en:
            return self.short_description_en
        elif locale == 'de' and self.short_description_de:
            return self.short_description_de
        return self.short_description or ''
    
    def get_long_description(self, locale='uk'):
        """Повертає повний опис відповідно до мови."""
        if locale == 'en' and self.long_description_en:
            return self.long_description_en
        elif locale == 'de' and self.long_description_de:
            return self.long_description_de
        return self.long_description or ''
