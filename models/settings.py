"""
Моделі налаштувань сайту та контактних повідомлень
"""
from datetime import datetime
from extensions import db


class SiteSettings(db.Model):
    """Налаштування сайту (синглтон)."""
    __tablename__ = "site_settings"
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Головна сторінка
    hero_subtitle = db.Column(db.String(255), nullable=True)
    about_title = db.Column(db.String(120), nullable=True)
    about_text = db.Column(db.Text, nullable=True)
    blog_title = db.Column(db.String(200), nullable=True)
    blog_excerpt = db.Column(db.Text, nullable=True)
    
    # Соцмережі
    social_telegram = db.Column(db.String(255), nullable=True)
    social_whatsapp = db.Column(db.String(255), nullable=True)
    social_instagram = db.Column(db.String(255), nullable=True)
    social_facebook = db.Column(db.String(255), nullable=True)
    social_youtube = db.Column(db.String(255), nullable=True)
    social_tiktok = db.Column(db.String(255), nullable=True)
    
    # AI
    ai_instructions = db.Column(db.Text, nullable=True)
    
    # Основні
    site_name = db.Column(db.String(120), nullable=True)
    site_tagline = db.Column(db.String(255), nullable=True)
    logo_url = db.Column(db.String(500), nullable=True)
    favicon_url = db.Column(db.String(500), nullable=True)
    
    # Контакти
    contact_email = db.Column(db.String(255), nullable=True)
    contact_phone = db.Column(db.String(100), nullable=True)
    contact_address = db.Column(db.String(500), nullable=True)
    working_hours = db.Column(db.String(255), nullable=True)
    google_maps_url = db.Column(db.String(500), nullable=True)
    
    # SEO
    meta_title = db.Column(db.String(100), nullable=True)
    meta_description = db.Column(db.String(200), nullable=True)
    meta_keywords = db.Column(db.String(255), nullable=True)
    
    # Аналітика
    google_analytics_id = db.Column(db.String(50), nullable=True)
    facebook_pixel_id = db.Column(db.String(50), nullable=True)
    custom_head_code = db.Column(db.Text, nullable=True)
    
    # Магазин
    default_currency = db.Column(db.String(8), nullable=True, default="UAH")
    products_per_page = db.Column(db.Integer, nullable=True, default=12)
    min_order_amount = db.Column(db.Float, nullable=True, default=0.0)
    shipping_info = db.Column(db.Text, nullable=True)
    
    # B2B налаштування
    b2b_enabled = db.Column(db.Boolean, default=True)
    b2b_registration_open = db.Column(db.Boolean, default=True)
    b2b_auto_approve = db.Column(db.Boolean, default=False)
    b2b_min_order_amount = db.Column(db.Float, default=0.0)
    
    # ========== АДМІНІСТРАТОР ==========
    # Логін/пароль адміна
    admin_username = db.Column(db.String(100), nullable=True)
    admin_password_hash = db.Column(db.String(255), nullable=True)
    
    # Дані юрособи адміністратора (для запитів до реєстрів)
    admin_company_name = db.Column(db.String(255), nullable=True)
    admin_company_legal_name = db.Column(db.String(255), nullable=True)
    admin_vat_number = db.Column(db.String(50), nullable=True)
    admin_vat_country = db.Column(db.String(2), nullable=True)
    admin_company_address = db.Column(db.String(500), nullable=True)
    admin_company_city = db.Column(db.String(100), nullable=True)
    admin_company_postal_code = db.Column(db.String(20), nullable=True)
    admin_company_country = db.Column(db.String(100), nullable=True)
    admin_company_country_code = db.Column(db.String(2), nullable=True)
    admin_handelsregister_id = db.Column(db.String(100), nullable=True)
    admin_company_email = db.Column(db.String(255), nullable=True)
    admin_company_phone = db.Column(db.String(50), nullable=True)
    admin_company_website = db.Column(db.String(255), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    @staticmethod
    def get_or_create():
        """Отримує або створює налаштування."""
        settings = SiteSettings.query.first()
        if not settings:
            settings = SiteSettings(
                hero_subtitle="Магазин, який ви налаштовуєте з адмінки за 1 годину.",
                about_title="Про компанію",
                about_text="Тут ви зможете розповісти про свій бренд, команду та цінності.",
                blog_title="Як ми автоматизуємо ваш онлайн-магазин",
                blog_excerpt="Автоматичний блог на базі ІІ: статті, огляди, відповіді на питання клієнтів.",
                social_telegram="https://t.me/your_channel",
                social_whatsapp="https://wa.me/380123456789",
                ai_instructions=(
                    "Ти — ввічливий продавець цього магазину. Твоє завдання — "
                    "допомогти клієнту обрати товар, ставити уточнюючі запитання, "
                    "пропонувати релевантні позиції з каталогу та не вигадувати того, "
                    "чого немає на сайті."
                ),
                site_name="SmartShop",
                default_currency="UAH",
            )
            db.session.add(settings)
            db.session.commit()
        return settings


class ContactMessage(db.Model):
    """Повідомлення з форми контактів."""
    __tablename__ = "contact_messages"
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    
    name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(50), nullable=True)
    subject = db.Column(db.String(255), nullable=True)
    message = db.Column(db.Text, nullable=False)
    
    is_read = db.Column(db.Boolean, default=False)
    replied_at = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<ContactMessage from {self.email}>"
    
    def mark_as_read(self):
        """Позначає як прочитане."""
        self.is_read = True
        db.session.commit()
