"""
Блоки на головній сторінці магазину ("Про нас" / "Магазин" / "Блог" / "ШІ-помічник"
та будь-які власні блоки, які власник додає сам). Раніше ці 4 картки були жорстко
зашиті в templates/index.html (заголовок, картинка, посилання) однаково для всіх
магазинів - ця модель робить їх повністю редагованими per-store: власник може
змінювати текст/картинку/посилання, вимикати блок або додавати нові.
"""
from datetime import datetime
from extensions import db

LINK_TYPE_CHOICES = ("about", "shop", "blog", "ai_assistant", "category", "custom")

# Дефолтні 4 блоки - точна копія того, що раніше було жорстко зашито в index.html,
# щоб для існуючих і нових магазинів, які ніколи не заходили в редактор блоків,
# головна сторінка виглядала так само, як і до впровадження цієї фічі.
DEFAULT_BLOCKS = [
    {
        "title": "About",
        "subtitle": "Learn more",
        "image_url": "https://images.pexels.com/photos/6476587/pexels-photo-6476587.jpeg?auto=compress&cs=tinysrgb&w=800",
        "link_type": "about",
        "link_value": None,
    },
    {
        "title": "Shop",
        "subtitle": "View all",
        "image_url": "https://images.pexels.com/photos/5632389/pexels-photo-5632389.jpeg?auto=compress&cs=tinysrgb&w=800",
        "link_type": "shop",
        "link_value": None,
    },
    {
        "title": "Blog",
        "subtitle": "Read more",
        "image_url": "https://images.pexels.com/photos/1181675/pexels-photo-1181675.jpeg?auto=compress&cs=tinysrgb&w=800",
        "link_type": "blog",
        "link_value": None,
    },
    {
        "title": "AI Assistant",
        "subtitle": "Ask me anything...",
        "image_url": "https://images.pexels.com/photos/8867439/pexels-photo-8867439.jpeg?auto=compress&cs=tinysrgb&w=800",
        "link_type": "ai_assistant",
        "link_value": None,
    },
]


class HomepageBlock(db.Model):
    __tablename__ = "homepage_blocks"

    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=False, index=True)

    title = db.Column(db.String(100), nullable=False)
    subtitle = db.Column(db.String(100), nullable=True)
    image_url = db.Column(db.String(500), nullable=True)

    # link_type визначає, куди веде картка: одна з фіксованих сторінок магазину
    # (about/shop/blog/ai_assistant), конкретна категорія каталогу (category,
    # link_value = slug категорії) або довільне посилання (custom, link_value = URL).
    link_type = db.Column(db.String(20), nullable=False, default="custom")
    link_value = db.Column(db.String(500), nullable=True)

    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def resolve_url(self):
        """URL картки на публічній сторінці. Викликається лише всередині
        request-контексту (потребує url_for)."""
        from flask import url_for

        if self.link_type == "about":
            return url_for("about_page")
        if self.link_type == "shop":
            return url_for("shop")
        if self.link_type == "blog":
            return url_for("blog.blog_page")
        if self.link_type == "ai_assistant":
            return url_for("ai_assistant_page")
        if self.link_type == "category" and self.link_value:
            from models.product import Category

            category = Category.query.filter_by(slug=self.link_value, store_id=self.store_id).first()
            if category:
                return url_for("category_page", slug=category.slug)
            return url_for("shop")
        return self.link_value or "#"

    @staticmethod
    def get_active_for_store(store_id):
        """Активні блоки для публічної головної сторінки, за порядком показу."""
        HomepageBlock.seed_defaults_if_empty(store_id)
        return (
            HomepageBlock.query.filter_by(store_id=store_id, is_active=True)
            .order_by(HomepageBlock.sort_order)
            .all()
        )

    @staticmethod
    def get_all_for_store(store_id):
        """Усі блоки (активні й вимкнені) для редактора в адмінці."""
        HomepageBlock.seed_defaults_if_empty(store_id)
        return (
            HomepageBlock.query.filter_by(store_id=store_id)
            .order_by(HomepageBlock.sort_order)
            .all()
        )

    @staticmethod
    def seed_defaults_if_empty(store_id):
        """Ліниве створення дефолтних 4 блоків при першому зверненні -
        той самий патерн, що й SiteSettings.get_or_create."""
        exists = HomepageBlock.query.filter_by(store_id=store_id).first()
        if exists:
            return
        for i, data in enumerate(DEFAULT_BLOCKS):
            db.session.add(HomepageBlock(store_id=store_id, sort_order=i, is_active=True, **data))
        db.session.commit()
