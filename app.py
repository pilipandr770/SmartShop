
import os
from datetime import datetime
from functools import wraps

# Завантаження змінних з .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
    abort,
)
from flask_sqlalchemy import SQLAlchemy

# Опціональні залежності
try:
    import stripe
    STRIPE_AVAILABLE = True
except ImportError:
    STRIPE_AVAILABLE = False

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# Ініціалізація SQLAlchemy
db = SQLAlchemy()


def create_app():
    """
    Фабрика Flask-додатку SmartShop AI.
    Запускає сайт-магазин з адмінкою, товарами та базовою статистикою.
    """
    app = Flask(__name__)

    # Базові налаштування
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")
    
    # Database configuration
    # Підтримка DATABASE_URL (Render, Heroku, Railway) та SQLALCHEMY_DATABASE_URI
    database_url = os.environ.get("DATABASE_URL") or os.environ.get(
        "SQLALCHEMY_DATABASE_URI", "sqlite:///smartshop_ai.db"
    )
    # Render/Heroku використовують postgres://, але SQLAlchemy потребує postgresql://
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    
    # DB Schema for PostgreSQL (to isolate from other projects)
    db_schema = os.environ.get("DB_SCHEMA", "smartshop")
    app.config["DB_SCHEMA"] = db_schema
    
    # Для PostgreSQL - налаштування пулу з'єднань та схеми
    engine_options = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    # Додаємо search_path для PostgreSQL
    if "postgresql" in database_url:
        engine_options["connect_args"] = {"options": f"-csearch_path={db_schema}"}
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = engine_options

    # Stripe налаштування
    app.config["STRIPE_SECRET_KEY"] = os.environ.get("STRIPE_SECRET_KEY", "")
    app.config["STRIPE_PUBLISHABLE_KEY"] = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
    app.config["STRIPE_WEBHOOK_SECRET"] = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    
    if STRIPE_AVAILABLE and app.config["STRIPE_SECRET_KEY"]:
        stripe.api_key = app.config["STRIPE_SECRET_KEY"]

    # OpenAI налаштування
    app.config["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY", "")
    openai_client = None
    if OPENAI_AVAILABLE and app.config["OPENAI_API_KEY"]:
        openai_client = OpenAI(api_key=app.config["OPENAI_API_KEY"])

    db.init_app(app)

    # ----- МОДЕЛІ -----

    class SiteSettings(db.Model):
        __tablename__ = "site_settings"

        id = db.Column(db.Integer, primary_key=True)
        hero_subtitle = db.Column(db.String(255), nullable=True)
        about_title = db.Column(db.String(120), nullable=True)
        about_text = db.Column(db.Text, nullable=True)
        blog_title = db.Column(db.String(200), nullable=True)
        blog_excerpt = db.Column(db.Text, nullable=True)

        social_telegram = db.Column(db.String(255), nullable=True)
        social_whatsapp = db.Column(db.String(255), nullable=True)
        social_instagram = db.Column(db.String(255), nullable=True)
        social_facebook = db.Column(db.String(255), nullable=True)
        social_youtube = db.Column(db.String(255), nullable=True)
        social_tiktok = db.Column(db.String(255), nullable=True)

        ai_instructions = db.Column(db.Text, nullable=True)

        # Нові поля для налаштувань сайту
        site_name = db.Column(db.String(120), nullable=True)
        site_tagline = db.Column(db.String(255), nullable=True)
        logo_url = db.Column(db.String(500), nullable=True)
        favicon_url = db.Column(db.String(500), nullable=True)
        
        # Контактна інформація
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
        default_currency = db.Column(db.String(8), nullable=True, default="EUR")
        products_per_page = db.Column(db.Integer, nullable=True, default=12)
        min_order_amount = db.Column(db.Float, nullable=True, default=0.0)
        shipping_info = db.Column(db.Text, nullable=True)

        created_at = db.Column(db.DateTime, default=datetime.utcnow)
        updated_at = db.Column(
            db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
        )

        @staticmethod
        def get_or_create():
            settings = SiteSettings.query.first()
            if not settings:
                settings = SiteSettings(
                    hero_subtitle=(
                        "Магазин, який ви налаштовуєте з адмінки за 1 годину."
                    ),
                    about_title="Про компанію",
                    about_text=(
                        "Тут ви зможете розповісти про свій бренд, команду та цінності. "
                        "Усе редагується через адмін-панель без розробника."
                    ),
                    blog_title="Як ми автоматизуємо ваш онлайн-магазин",
                    blog_excerpt=(
                        "Автоматичний блог на базі ІІ: статті, огляди, відповіді на "
                        "питання клієнтів — усе за контент-планом на 30 днів."
                    ),
                    social_telegram="https://t.me/your_channel",
                    social_whatsapp="https://wa.me/49123456789",
                    ai_instructions=(
                        "Ти — ввічливий продавець цього магазину. Твоє завдання — "
                        "допомогти клієнту обрати товар, ставити уточнюючі запитання, "
                        "пропонувати релевантні позиції з каталогу та не вигадувати того, "
                        "чого немає на сайті."
                    ),
                )
                db.session.add(settings)
                db.session.commit()
            return settings

    class Category(db.Model):
        __tablename__ = "categories"

        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(120), nullable=False)
        slug = db.Column(db.String(120), unique=True, nullable=False)
        description = db.Column(db.Text, nullable=True)

        products = db.relationship("Product", backref="category", lazy=True)

    class Product(db.Model):
        __tablename__ = "products"

        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(200), nullable=False)
        sku = db.Column(db.String(64), nullable=True)
        price = db.Column(db.Float, nullable=False, default=0.0)
        old_price = db.Column(db.Float, nullable=True)  # Стара ціна для знижок
        currency = db.Column(db.String(8), nullable=False, default="EUR")
        stock = db.Column(db.Integer, nullable=False, default=0)  # Кількість на складі

        short_description = db.Column(db.String(255), nullable=True)
        long_description = db.Column(db.Text, nullable=True)

        image_url = db.Column(db.String(500), nullable=True)

        category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)

        is_active = db.Column(db.Boolean, nullable=False, default=True)

        created_at = db.Column(db.DateTime, default=datetime.utcnow)
        updated_at = db.Column(
            db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
        )

    class Order(db.Model):
        __tablename__ = "orders"

        id = db.Column(db.Integer, primary_key=True)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)
        status = db.Column(db.String(32), nullable=False, default="created")
        amount = db.Column(db.Float, nullable=False, default=0.0)
        currency = db.Column(db.String(8), nullable=False, default="EUR")
        
        # Stripe
        stripe_session_id = db.Column(db.String(255), nullable=True)
        stripe_payment_intent = db.Column(db.String(255), nullable=True)
        
        # Клієнт
        customer_email = db.Column(db.String(255), nullable=True)
        customer_name = db.Column(db.String(255), nullable=True)
        customer_phone = db.Column(db.String(50), nullable=True)
        shipping_address = db.Column(db.Text, nullable=True)
        
        # Адмін нотатки
        notes = db.Column(db.Text, nullable=True)
        
        # Зв'язок з товарами
        items = db.relationship("OrderItem", backref="order", lazy=True)

    class OrderItem(db.Model):
        __tablename__ = "order_items"

        id = db.Column(db.Integer, primary_key=True)
        order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
        product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=True)
        product_name = db.Column(db.String(200), nullable=False)
        price = db.Column(db.Float, nullable=False)
        quantity = db.Column(db.Integer, nullable=False, default=1)
        currency = db.Column(db.String(8), nullable=False, default="EUR")

    class ContactMessage(db.Model):
        """Модель для збереження повідомлень з форми контактів."""
        __tablename__ = "contact_messages"

        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(200), nullable=False)
        email = db.Column(db.String(255), nullable=False)
        phone = db.Column(db.String(50), nullable=True)
        subject = db.Column(db.String(255), nullable=True)
        message = db.Column(db.Text, nullable=False)
        is_read = db.Column(db.Boolean, nullable=False, default=False)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Робимо моделі доступними через app
    app.SiteSettings = SiteSettings
    app.Category = Category
    app.Product = Product
    app.Order = Order
    app.OrderItem = OrderItem
    app.ContactMessage = ContactMessage

    # ----- СЛУЖБОВІ ФУНКЦІЇ -----

    def init_db():
        """Створити схему, таблиці й дефолтні налаштування, якщо їх ще немає."""
        with app.app_context():
            # Для PostgreSQL - створюємо окрему схему
            db_schema = app.config.get("DB_SCHEMA", "smartshop")
            database_url = app.config.get("SQLALCHEMY_DATABASE_URI", "")
            
            if "postgresql" in database_url:
                # Створюємо схему, якщо не існує
                from sqlalchemy import text
                with db.engine.connect() as conn:
                    conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {db_schema}"))
                    conn.commit()
                print(f"✅ PostgreSQL схема '{db_schema}' готова")
            
            db.create_all()
            SiteSettings.get_or_create()
            
            # Створюємо тестові дані, якщо БД порожня
            if Category.query.count() == 0:
                # Тестова категорія
                test_category = Category(
                    name="Електроніка",
                    slug="electronics",
                    description="Смартфони, ноутбуки, планшети та інша техніка"
                )
                db.session.add(test_category)
                db.session.flush()  # Отримуємо ID категорії
                
                # Тестовий товар
                test_product = Product(
                    name="iPhone 15 Pro",
                    sku="IPHONE15PRO-256",
                    price=54999.00,
                    old_price=59999.00,
                    currency="UAH",
                    short_description="Новий iPhone з титановим корпусом",
                    long_description="Apple iPhone 15 Pro з чіпом A17 Pro, камерою 48 Мп та USB-C. Титановий корпус, Dynamic Island, Always-On дисплей.",
                    image_url="https://images.pexels.com/photos/788946/pexels-photo-788946.jpeg?auto=compress&cs=tinysrgb&w=800",
                    category_id=test_category.id,
                    stock=15,
                    is_active=True
                )
                db.session.add(test_product)
                
                # Ще кілька тестових товарів
                products_data = [
                    {
                        "name": "MacBook Air M3",
                        "sku": "MBA-M3-256",
                        "price": 52999.00,
                        "old_price": None,
                        "stock": 8,
                        "short_description": "Ультратонкий ноутбук з чіпом M3",
                        "long_description": "Apple MacBook Air з чіпом M3, 13.6 дюймів Liquid Retina дисплей, до 18 годин автономної роботи.",
                        "image_url": "https://images.pexels.com/photos/812264/pexels-photo-812264.jpeg?auto=compress&cs=tinysrgb&w=800",
                    },
                    {
                        "name": "AirPods Pro 2",
                        "sku": "APP2-USB-C",
                        "price": 10999.00,
                        "old_price": 12499.00,
                        "stock": 25,
                        "short_description": "Бездротові навушники з активним шумоподавленням",
                        "long_description": "Apple AirPods Pro 2 з USB-C, активне шумоподавлення, адаптивний звук, до 6 годин прослуховування.",
                        "image_url": "https://images.pexels.com/photos/3780681/pexels-photo-3780681.jpeg?auto=compress&cs=tinysrgb&w=800",
                    },
                    {
                        "name": "iPad Air",
                        "sku": "IPAD-AIR-256",
                        "price": 32999.00,
                        "old_price": None,
                        "stock": 5,
                        "short_description": "Потужний планшет для роботи та розваг",
                        "long_description": "Apple iPad Air з чіпом M1, 10.9 дюймів Liquid Retina дисплей, підтримка Apple Pencil та Magic Keyboard.",
                        "image_url": "https://images.pexels.com/photos/1334597/pexels-photo-1334597.jpeg?auto=compress&cs=tinysrgb&w=800",
                    },
                ]
                
                for p_data in products_data:
                    product = Product(
                        name=p_data["name"],
                        sku=p_data["sku"],
                        price=p_data["price"],
                        old_price=p_data.get("old_price"),
                        currency="UAH",
                        short_description=p_data["short_description"],
                        long_description=p_data["long_description"],
                        image_url=p_data["image_url"],
                        category_id=test_category.id,
                        stock=p_data.get("stock", 0),
                        is_active=True
                    )
                    db.session.add(product)
                
                db.session.commit()
                print("✅ Створено тестову категорію та 4 товари")

    # DEMO MODE: Авторизація вимкнена для демонстрації
    DEMO_MODE = os.environ.get("DEMO_MODE", "true").lower() == "true"

    def is_admin_logged_in() -> bool:
        if DEMO_MODE:
            return True  # В демо-режимі завжди авторизовано
        return session.get("is_admin", False)

    def admin_required(fn):
        """Декоратор для захисту адмін-маршрутів."""
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if DEMO_MODE:
                return fn(*args, **kwargs)  # В демо-режимі пропускаємо перевірку
            if not is_admin_logged_in():
                flash("Потрібен вхід в адмін-панель.", "warning")
                return redirect(url_for("admin_login"))
            return fn(*args, **kwargs)
        return wrapper

    # ----- ПУБЛІЧНІ СТОРІНКИ -----

    @app.route("/")
    def index():
        settings = SiteSettings.get_or_create()
        products = Product.query.filter_by(is_active=True).limit(8).all()
        categories = Category.query.all()

        total_products = Product.query.count()
        total_orders = Order.query.count()
        total_revenue = (
            db.session.query(db.func.coalesce(db.func.sum(Order.amount), 0.0))
            .filter(Order.status == "paid")
            .scalar()
        )

        return render_template(
            "index.html",
            settings=settings,
            products=products,
            categories=categories,
            total_products=total_products,
            total_orders=total_orders,
            total_revenue=total_revenue,
        )

    # ----- ПУБЛІЧНІ: СТАТИЧНІ СТОРІНКИ -----

    @app.route("/about")
    def about_page():
        """Сторінка Про компанію."""
        settings = SiteSettings.get_or_create()
        return render_template("pages/about.html", settings=settings)

    @app.route("/blog")
    def blog_page():
        """Сторінка Блогу."""
        settings = SiteSettings.get_or_create()
        return render_template("pages/blog.html", settings=settings)

    @app.route("/contacts")
    def contacts_page():
        """Сторінка Контакти."""
        settings = SiteSettings.get_or_create()
        return render_template("pages/contacts.html", settings=settings)

    @app.route("/ai-assistant")
    def ai_assistant_page():
        """Сторінка ІІ-продавця."""
        settings = SiteSettings.get_or_create()
        products = Product.query.filter_by(is_active=True).all()
        categories = Category.query.all()
        return render_template(
            "pages/ai_assistant.html",
            settings=settings,
            products=products,
            categories=categories,
        )

    # ----- ПУБЛІЧНІ: МАГАЗИН -----

    @app.route("/shop")
    def shop():
        """Сторінка всіх товарів з пагінацією."""
        settings = SiteSettings.get_or_create()
        page = request.args.get("page", 1, type=int)
        per_page = 12

        products = (
            Product.query.filter_by(is_active=True)
            .order_by(Product.created_at.desc())
            .paginate(page=page, per_page=per_page, error_out=False)
        )
        categories = Category.query.order_by(Category.name.asc()).all()

        return render_template(
            "shop.html",
            settings=settings,
            products=products,
            categories=categories,
        )

    @app.route("/category/<slug>")
    def category_page(slug):
        """Сторінка категорії з товарами."""
        settings = SiteSettings.get_or_create()
        category = Category.query.filter_by(slug=slug).first_or_404()
        page = request.args.get("page", 1, type=int)
        per_page = 12

        products = (
            Product.query.filter_by(is_active=True, category_id=category.id)
            .order_by(Product.created_at.desc())
            .paginate(page=page, per_page=per_page, error_out=False)
        )
        categories = Category.query.order_by(Category.name.asc()).all()

        return render_template(
            "category.html",
            settings=settings,
            category=category,
            products=products,
            categories=categories,
        )

    @app.route("/product/<int:product_id>")
    def product_page(product_id):
        """Сторінка окремого товару."""
        settings = SiteSettings.get_or_create()
        product = Product.query.get_or_404(product_id)

        if not product.is_active:
            abort(404)

        # Схожі товари з тієї ж категорії
        related = []
        if product.category_id:
            related = (
                Product.query.filter(
                    Product.is_active == True,
                    Product.category_id == product.category_id,
                    Product.id != product.id,
                )
                .limit(4)
                .all()
            )

        return render_template(
            "product.html",
            settings=settings,
            product=product,
            related=related,
        )

    # ----- ПУБЛІЧНІ: КОШИК -----

    def get_cart():
        """Отримати кошик з сесії."""
        return session.get("cart", {})

    def save_cart(cart):
        """Зберегти кошик у сесію."""
        session["cart"] = cart
        session.modified = True

    @app.route("/cart")
    def cart_page():
        """Сторінка кошика."""
        settings = SiteSettings.get_or_create()
        cart = get_cart()
        items = []
        total = 0.0

        for product_id_str, qty in cart.items():
            product = Product.query.get(int(product_id_str))
            if product and product.is_active:
                item_total = product.price * qty
                total += item_total
                items.append({
                    "product": product,
                    "quantity": qty,
                    "item_total": item_total,
                })

        return render_template(
            "cart.html",
            settings=settings,
            items=items,
            total=total,
        )

    @app.route("/cart/add/<int:product_id>", methods=["POST"])
    def cart_add(product_id):
        """Додати товар у кошик."""
        product = Product.query.get_or_404(product_id)
        if not product.is_active:
            abort(404)

        cart = get_cart()
        product_id_str = str(product_id)
        quantity = request.form.get("quantity", 1, type=int)

        if quantity < 1:
            quantity = 1

        if product_id_str in cart:
            cart[product_id_str] += quantity
        else:
            cart[product_id_str] = quantity

        save_cart(cart)
        flash(f"«{product.name}» додано в кошик.", "success")

        # Повернутись на попередню сторінку або на сторінку товару
        next_url = request.form.get("next") or url_for("product_page", product_id=product_id)
        return redirect(next_url)

    @app.route("/cart/update/<int:product_id>", methods=["POST"])
    def cart_update(product_id):
        """Оновити кількість товару в кошику."""
        cart = get_cart()
        product_id_str = str(product_id)
        quantity = request.form.get("quantity", 1, type=int)

        if product_id_str in cart:
            if quantity > 0:
                cart[product_id_str] = quantity
            else:
                del cart[product_id_str]
            save_cart(cart)

        return redirect(url_for("cart_page"))

    @app.route("/cart/remove/<int:product_id>", methods=["POST"])
    def cart_remove(product_id):
        """Видалити товар з кошика."""
        cart = get_cart()
        product_id_str = str(product_id)

        if product_id_str in cart:
            del cart[product_id_str]
            save_cart(cart)
            flash("Товар видалено з кошика.", "info")

        return redirect(url_for("cart_page"))

    @app.route("/cart/clear", methods=["POST"])
    def cart_clear():
        """Очистити весь кошик."""
        save_cart({})
        flash("Кошик очищено.", "info")
        return redirect(url_for("cart_page"))

    # ----- STRIPE CHECKOUT -----

    @app.route("/checkout", methods=["POST"])
    def checkout():
        """Створити Stripe Checkout сесію."""
        if not STRIPE_AVAILABLE or not app.config["STRIPE_SECRET_KEY"]:
            flash("Stripe не налаштовано. Зверніться до адміністратора.", "danger")
            return redirect(url_for("cart_page"))

        cart = get_cart()
        if not cart:
            flash("Ваш кошик порожній.", "warning")
            return redirect(url_for("cart_page"))

        line_items = []
        order_items_data = []
        total = 0.0

        for product_id_str, qty in cart.items():
            product = Product.query.get(int(product_id_str))
            if product and product.is_active:
                line_items.append({
                    "price_data": {
                        "currency": product.currency.lower(),
                        "product_data": {
                            "name": product.name,
                            "description": product.short_description or "",
                            "images": [product.image_url] if product.image_url else [],
                        },
                        "unit_amount": int(product.price * 100),  # Stripe працює з центами
                    },
                    "quantity": qty,
                })
                order_items_data.append({
                    "product_id": product.id,
                    "product_name": product.name,
                    "price": product.price,
                    "quantity": qty,
                    "currency": product.currency,
                })
                total += product.price * qty

        if not line_items:
            flash("Не вдалося знайти товари в кошику.", "danger")
            return redirect(url_for("cart_page"))

        try:
            # Створюємо замовлення в БД
            order = Order(
                status="pending",
                amount=total,
                currency="EUR",
            )
            db.session.add(order)
            db.session.flush()  # Отримуємо ID

            # Додаємо товари до замовлення
            for item_data in order_items_data:
                order_item = OrderItem(
                    order_id=order.id,
                    product_id=item_data["product_id"],
                    product_name=item_data["product_name"],
                    price=item_data["price"],
                    quantity=item_data["quantity"],
                    currency=item_data["currency"],
                )
                db.session.add(order_item)

            # Створюємо Stripe Checkout сесію
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=line_items,
                mode="payment",
                success_url=url_for("checkout_success", _external=True) + "?session_id={CHECKOUT_SESSION_ID}",
                cancel_url=url_for("checkout_cancel", _external=True),
                metadata={"order_id": str(order.id)},
            )

            order.stripe_session_id = checkout_session.id
            db.session.commit()

            return redirect(checkout_session.url)

        except stripe.error.StripeError as e:
            db.session.rollback()
            flash(f"Помилка Stripe: {str(e)}", "danger")
            return redirect(url_for("cart_page"))

    @app.route("/checkout/success")
    def checkout_success():
        """Сторінка успішної оплати."""
        settings = SiteSettings.get_or_create()
        session_id = request.args.get("session_id")
        
        order = None
        if session_id and STRIPE_AVAILABLE and app.config["STRIPE_SECRET_KEY"]:
            try:
                checkout_session = stripe.checkout.Session.retrieve(session_id)
                order = Order.query.filter_by(stripe_session_id=session_id).first()
                
                if order and order.status == "pending":
                    order.status = "paid"
                    order.customer_email = checkout_session.customer_details.email if checkout_session.customer_details else None
                    order.customer_name = checkout_session.customer_details.name if checkout_session.customer_details else None
                    order.stripe_payment_intent = checkout_session.payment_intent
                    db.session.commit()
                    
                    # Очищаємо кошик
                    save_cart({})
            except Exception:
                pass

        return render_template("checkout_success.html", settings=settings, order=order)

    @app.route("/checkout/cancel")
    def checkout_cancel():
        """Сторінка скасованої оплати."""
        settings = SiteSettings.get_or_create()
        flash("Оплату скасовано. Ви можете спробувати ще раз.", "info")
        return redirect(url_for("cart_page"))

    @app.route("/webhook/stripe", methods=["POST"])
    def stripe_webhook():
        """Webhook для Stripe."""
        if not STRIPE_AVAILABLE:
            return jsonify({"error": "Stripe not available"}), 400

        payload = request.get_data()
        sig_header = request.headers.get("Stripe-Signature")
        webhook_secret = app.config["STRIPE_WEBHOOK_SECRET"]

        try:
            if webhook_secret:
                event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
            else:
                event = stripe.Event.construct_from(
                    request.get_json(), stripe.api_key
                )
        except ValueError:
            return jsonify({"error": "Invalid payload"}), 400
        except stripe.error.SignatureVerificationError:
            return jsonify({"error": "Invalid signature"}), 400

        # Обробка події
        if event["type"] == "checkout.session.completed":
            session_data = event["data"]["object"]
            session_id = session_data["id"]
            
            order = Order.query.filter_by(stripe_session_id=session_id).first()
            if order:
                order.status = "paid"
                order.customer_email = session_data.get("customer_details", {}).get("email")
                order.customer_name = session_data.get("customer_details", {}).get("name")
                order.stripe_payment_intent = session_data.get("payment_intent")
                db.session.commit()

        return jsonify({"status": "success"}), 200

    # ----- AI CHAT -----

    @app.route("/api/chat", methods=["POST"])
    def api_chat():
        """API для чату з ІІ-продавцем."""
        if not OPENAI_AVAILABLE or not openai_client:
            return jsonify({"error": "AI не налаштовано"}), 400

        data = request.get_json()
        user_message = data.get("message", "").strip()

        if not user_message:
            return jsonify({"error": "Повідомлення порожнє"}), 400

        # Отримуємо налаштування та каталог
        settings = SiteSettings.get_or_create()
        products = Product.query.filter_by(is_active=True).all()
        categories = Category.query.all()

        # Формуємо контекст каталогу
        catalog_info = "Каталог товарів:\n"
        for cat in categories:
            catalog_info += f"\nКатегорія: {cat.name}\n"
            cat_products = [p for p in products if p.category_id == cat.id]
            for p in cat_products:
                catalog_info += f"  - {p.name}: {p.price} {p.currency}"
                if p.short_description:
                    catalog_info += f" ({p.short_description})"
                catalog_info += "\n"
        
        # Товари без категорії
        no_cat_products = [p for p in products if not p.category_id]
        if no_cat_products:
            catalog_info += "\nІнші товари:\n"
            for p in no_cat_products:
                catalog_info += f"  - {p.name}: {p.price} {p.currency}\n"

        system_prompt = f"""
{settings.ai_instructions or "Ти — ввічливий продавець цього магазину."}

{catalog_info}

Важливо:
- Відповідай тільки на питання про товари з каталогу
- Не вигадуй товарів, яких немає
- Пропонуй релевантні товари
- Будь ввічливим та корисним
- Відповідай українською мовою
"""

        try:
            response = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                max_tokens=500,
                temperature=0.7,
            )
            
            ai_message = response.choices[0].message.content
            return jsonify({"message": ai_message})

        except Exception as e:
            return jsonify({"error": f"Помилка AI: {str(e)}"}), 500

    @app.context_processor
    def cart_context():
        """Додає cart_count у всі шаблони."""
        cart = get_cart()
        cart_count = sum(cart.values()) if cart else 0
        return {"cart_count": cart_count}

    # ----- АДМІНКА: АВТОРИЗАЦІЯ -----

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        # В демо-режимі одразу переходимо в адмінку
        if DEMO_MODE:
            return redirect(url_for("admin_dashboard"))
            
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()

            expected_user = os.environ.get("ADMIN_USERNAME", "admin")
            expected_pass = os.environ.get("ADMIN_PASSWORD", "admin123")

            if username == expected_user and password == expected_pass:
                session["is_admin"] = True
                flash("Вітаю, ви увійшли в адмін-панель.", "success")
                return redirect(url_for("admin_dashboard"))
            else:
                flash("Невірний логін або пароль.", "danger")

        return render_template("admin/login.html")

    @app.route("/admin/logout")
    def admin_logout():
        session.pop("is_admin", None)
        flash("Ви вийшли з адмін-панелі.", "info")
        return redirect(url_for("admin_login"))

    # ----- АДМІНКА: ДАШБОРД -----

    @app.route("/admin/")
    @admin_required
    def admin_dashboard():
        settings = SiteSettings.get_or_create()
        product_count = Product.query.count()
        category_count = Category.query.count()
        order_count = Order.query.count()

        total_revenue = (
            db.session.query(db.func.coalesce(db.func.sum(Order.amount), 0.0))
            .filter(Order.status == "paid")
            .scalar()
        )

        last_orders = (
            Order.query.order_by(Order.created_at.desc()).limit(5).all()
        )

        return render_template(
            "admin/dashboard.html",
            settings=settings,
            product_count=product_count,
            category_count=category_count,
            order_count=order_count,
            total_revenue=total_revenue,
            last_orders=last_orders,
        )

    # ----- АДМІНКА: НАЛАШТУВАННЯ БЛОКІВ + СОЦМЕРЕЖІ + ІІ -----

    @app.route("/admin/blocks", methods=["GET", "POST"])
    @admin_required
    def admin_blocks():
        settings = SiteSettings.get_or_create()

        if request.method == "POST":
            settings.hero_subtitle = request.form.get("hero_subtitle") or ""
            settings.about_title = request.form.get("about_title") or ""
            settings.about_text = request.form.get("about_text") or ""
            settings.blog_title = request.form.get("blog_title") or ""
            settings.blog_excerpt = request.form.get("blog_excerpt") or ""

            settings.social_telegram = request.form.get("social_telegram") or ""
            settings.social_whatsapp = request.form.get("social_whatsapp") or ""

            settings.ai_instructions = request.form.get("ai_instructions") or ""

            db.session.commit()
            flash("Налаштування головної сторінки збережені.", "success")
            return redirect(url_for("admin_blocks"))

        return render_template("admin/blocks.html", settings=settings)

    # ----- АДМІНКА: КАТЕГОРІЇ -----

    @app.route("/admin/categories", methods=["GET", "POST"])
    @admin_required
    def admin_categories():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            slug = request.form.get("slug", "").strip()
            description = request.form.get("description", "").strip()

            if not name or not slug:
                flash("Назва і slug категорії обовʼязкові.", "danger")
            else:
                exists = Category.query.filter_by(slug=slug).first()
                if exists:
                    flash("Категорія з таким slug уже існує.", "warning")
                else:
                    category = Category(
                        name=name,
                        slug=slug,
                        description=description or None,
                    )
                    db.session.add(category)
                    db.session.commit()
                    flash("Категорія створена.", "success")
            return redirect(url_for("admin_categories"))

        categories = Category.query.order_by(Category.name.asc()).all()
        return render_template("admin/categories.html", categories=categories)

    # ----- АДМІНКА: ТОВАРИ -----

    @app.route("/admin/products")
    @admin_required
    def admin_products():
        products = (
            Product.query.order_by(Product.created_at.desc())
            .all()
        )
        categories = Category.query.order_by(Category.name.asc()).all()
        return render_template(
            "admin/products.html", products=products, categories=categories
        )

    @app.route("/admin/products/new", methods=["POST"])
    @admin_required
    def admin_products_new():
        name = request.form.get("name", "").strip()
        price = request.form.get("price", "0").replace(",", ".").strip()
        old_price = request.form.get("old_price", "").replace(",", ".").strip()
        category_id = request.form.get("category_id") or None
        description = request.form.get("description", "").strip()
        image_url = request.form.get("image_url", "").strip()
        stock = request.form.get("stock", "0").strip()
        is_active = request.form.get("is_active") == "on"

        try:
            price_value = float(price)
        except ValueError:
            price_value = 0.0
        
        try:
            old_price_value = float(old_price) if old_price else None
        except ValueError:
            old_price_value = None
            
        try:
            stock_value = int(stock)
        except ValueError:
            stock_value = 0

        product = Product(
            name=name,
            price=price_value,
            old_price=old_price_value,
            currency="UAH",
            category_id=int(category_id) if category_id else None,
            short_description=description or None,
            image_url=image_url or None,
            stock=stock_value,
            is_active=is_active,
        )
        db.session.add(product)
        db.session.commit()
        flash("Товар створено.", "success")
        return redirect(url_for("admin_products"))

    @app.route("/admin/products/<int:product_id>/toggle", methods=["POST"])
    @admin_required
    def admin_products_toggle(product_id):
        product = Product.query.get_or_404(product_id)
        product.is_active = not product.is_active
        db.session.commit()
        flash("Статус товару оновлено.", "info")
        return redirect(url_for("admin_products"))

    @app.route("/admin/products/<int:product_id>/delete", methods=["POST"])
    @admin_required
    def admin_products_delete(product_id):
        product = Product.query.get_or_404(product_id)
        db.session.delete(product)
        db.session.commit()
        flash("Товар видалено.", "info")
        return redirect(url_for("admin_products"))

    @app.route("/admin/products/<int:product_id>/edit", methods=["GET", "POST"])
    @admin_required
    def admin_products_edit(product_id):
        """Редагування товару."""
        product = Product.query.get_or_404(product_id)
        categories = Category.query.order_by(Category.name.asc()).all()

        if request.method == "POST":
            product.name = request.form.get("name", "").strip()
            price = request.form.get("price", "0").replace(",", ".").strip()
            old_price = request.form.get("old_price", "").replace(",", ".").strip()
            stock = request.form.get("stock", "0").strip()
            
            try:
                product.price = float(price)
            except ValueError:
                product.price = 0.0
            
            try:
                product.old_price = float(old_price) if old_price else None
            except ValueError:
                product.old_price = None
                
            try:
                product.stock = int(stock)
            except ValueError:
                product.stock = 0
                
            category_id = request.form.get("category_id")
            product.category_id = int(category_id) if category_id else None
            product.short_description = request.form.get("short_description", "").strip() or None
            product.long_description = request.form.get("long_description", "").strip() or None
            product.image_url = request.form.get("image_url", "").strip() or None
            product.sku = request.form.get("sku", "").strip() or None
            product.is_active = request.form.get("is_active") == "on"

            db.session.commit()
            flash("Товар оновлено.", "success")
            return redirect(url_for("admin_products"))

        return render_template(
            "admin/product_edit.html",
            product=product,
            categories=categories,
        )

    # ----- АДМІНКА: КАТЕГОРІЇ (повний CRUD) -----

    @app.route("/admin/categories/<int:category_id>/edit", methods=["GET", "POST"])
    @admin_required
    def admin_categories_edit(category_id):
        """Редагування категорії."""
        category = Category.query.get_or_404(category_id)

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            slug = request.form.get("slug", "").strip()
            description = request.form.get("description", "").strip()

            if not name or not slug:
                flash("Назва і slug категорії обовʼязкові.", "danger")
            else:
                # Перевіряємо, чи slug не зайнятий іншою категорією
                exists = Category.query.filter(
                    Category.slug == slug,
                    Category.id != category_id
                ).first()
                if exists:
                    flash("Категорія з таким slug уже існує.", "warning")
                else:
                    category.name = name
                    category.slug = slug
                    category.description = description or None
                    db.session.commit()
                    flash("Категорія оновлена.", "success")
                    return redirect(url_for("admin_categories"))

        return render_template("admin/category_edit.html", category=category)

    @app.route("/admin/categories/<int:category_id>/delete", methods=["POST"])
    @admin_required
    def admin_categories_delete(category_id):
        """Видалення категорії."""
        category = Category.query.get_or_404(category_id)
        # Товари в цій категорії стануть без категорії
        Product.query.filter_by(category_id=category_id).update({"category_id": None})
        db.session.delete(category)
        db.session.commit()
        flash("Категорія видалена. Товари залишились без категорії.", "info")
        return redirect(url_for("admin_categories"))

    # ----- АДМІНКА: СТАТИСТИКА -----

    @app.route("/admin/stats")
    @admin_required
    def admin_stats():
        total_orders = Order.query.count()
        paid_orders = Order.query.filter_by(status="paid").count()
        total_revenue = (
            db.session.query(db.func.coalesce(db.func.sum(Order.amount), 0.0))
            .filter(Order.status == "paid")
            .scalar()
        )
        latest_orders = (
            Order.query.order_by(Order.created_at.desc()).limit(20).all()
        )

        return render_template(
            "admin/stats.html",
            total_orders=total_orders,
            paid_orders=paid_orders,
            total_revenue=total_revenue,
            latest_orders=latest_orders,
        )

    # ----- АДМІНКА: ЗАМОВЛЕННЯ -----

    @app.route("/admin/orders")
    @admin_required
    def admin_orders():
        """Список усіх замовлень з фільтрацією та пагінацією."""
        page = request.args.get("page", 1, type=int)
        per_page = 20
        status_filter = request.args.get("status", "").strip()

        query = Order.query.order_by(Order.created_at.desc())
        
        if status_filter:
            query = query.filter(Order.status == status_filter)

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        orders = pagination.items

        # Статистика
        stats = {
            "total": Order.query.count(),
            "paid": Order.query.filter_by(status="paid").count(),
            "pending": Order.query.filter_by(status="pending").count(),
            "revenue": db.session.query(db.func.coalesce(db.func.sum(Order.amount), 0.0))
                .filter(Order.status == "paid").scalar(),
        }

        return render_template(
            "admin/orders.html",
            orders=orders,
            pagination=pagination,
            stats=stats,
        )

    @app.route("/admin/orders/<int:order_id>")
    @admin_required
    def admin_order_detail(order_id):
        """Деталі замовлення."""
        order = Order.query.get_or_404(order_id)
        return render_template("admin/order_detail.html", order=order)

    @app.route("/admin/orders/<int:order_id>/status", methods=["POST"])
    @admin_required
    def admin_order_update_status(order_id):
        """Оновити статус замовлення."""
        order = Order.query.get_or_404(order_id)
        new_status = request.form.get("status", "").strip()
        
        valid_statuses = ["created", "pending", "paid", "shipped", "delivered", "cancelled"]
        if new_status in valid_statuses:
            order.status = new_status
            db.session.commit()
            flash(f"Статус змінено на «{new_status}».", "success")
        else:
            flash("Невірний статус.", "danger")
        
        return redirect(url_for("admin_order_detail", order_id=order_id))

    @app.route("/admin/orders/<int:order_id>/notes", methods=["POST"])
    @admin_required
    def admin_order_update_notes(order_id):
        """Оновити нотатки замовлення."""
        order = Order.query.get_or_404(order_id)
        order.notes = request.form.get("notes", "").strip() or None
        db.session.commit()
        flash("Нотатки збережено.", "success")
        return redirect(url_for("admin_order_detail", order_id=order_id))

    @app.route("/admin/orders/<int:order_id>/delete", methods=["POST"])
    @admin_required
    def admin_order_delete(order_id):
        """Видалити замовлення."""
        order = Order.query.get_or_404(order_id)
        # Видаляємо товари замовлення
        OrderItem.query.filter_by(order_id=order_id).delete()
        db.session.delete(order)
        db.session.commit()
        flash("Замовлення видалено.", "info")
        return redirect(url_for("admin_orders"))

    # ----- АДМІНКА: КОНТАКТИ -----

    @app.route("/admin/contacts")
    @admin_required
    def admin_contacts():
        """Список заявок з форми контактів."""
        page = request.args.get("page", 1, type=int)
        per_page = 20

        pagination = ContactMessage.query.order_by(
            ContactMessage.is_read.asc(),
            ContactMessage.created_at.desc()
        ).paginate(page=page, per_page=per_page, error_out=False)
        
        contacts = pagination.items

        # Статистика
        today = datetime.utcnow().date()
        stats = {
            "total": ContactMessage.query.count(),
            "unread": ContactMessage.query.filter_by(is_read=False).count(),
            "today": ContactMessage.query.filter(
                db.func.date(ContactMessage.created_at) == today
            ).count(),
        }

        return render_template(
            "admin/contacts.html",
            contacts=contacts,
            pagination=pagination,
            stats=stats,
        )

    @app.route("/admin/contacts/<int:contact_id>/read", methods=["POST"])
    @admin_required
    def admin_contact_mark_read(contact_id):
        """Позначити заявку як прочитану."""
        contact = ContactMessage.query.get_or_404(contact_id)
        contact.is_read = True
        db.session.commit()
        flash("Заявку позначено як прочитану.", "success")
        return redirect(url_for("admin_contacts"))

    @app.route("/admin/contacts/<int:contact_id>/delete", methods=["POST"])
    @admin_required
    def admin_contact_delete(contact_id):
        """Видалити заявку."""
        contact = ContactMessage.query.get_or_404(contact_id)
        db.session.delete(contact)
        db.session.commit()
        flash("Заявку видалено.", "info")
        return redirect(url_for("admin_contacts"))

    @app.route("/admin/contacts/mark-all-read", methods=["POST"])
    @admin_required
    def admin_contacts_mark_all_read():
        """Позначити всі заявки як прочитані."""
        ContactMessage.query.filter_by(is_read=False).update({"is_read": True})
        db.session.commit()
        flash("Усі заявки позначено як прочитані.", "success")
        return redirect(url_for("admin_contacts"))

    @app.route("/admin/contacts/delete-read", methods=["POST"])
    @admin_required
    def admin_contacts_delete_read():
        """Видалити всі прочитані заявки."""
        ContactMessage.query.filter_by(is_read=True).delete()
        db.session.commit()
        flash("Прочитані заявки видалено.", "info")
        return redirect(url_for("admin_contacts"))

    # ----- АДМІНКА: НАЛАШТУВАННЯ САЙТУ -----

    @app.route("/admin/settings", methods=["GET", "POST"])
    @admin_required
    def admin_settings():
        """Глобальні налаштування сайту."""
        settings = SiteSettings.get_or_create()

        if request.method == "POST":
            # Основні
            settings.site_name = request.form.get("site_name") or None
            settings.site_tagline = request.form.get("site_tagline") or None
            settings.logo_url = request.form.get("logo_url") or None
            settings.favicon_url = request.form.get("favicon_url") or None
            
            # Контакти
            settings.contact_email = request.form.get("contact_email") or None
            settings.contact_phone = request.form.get("contact_phone") or None
            settings.contact_address = request.form.get("contact_address") or None
            settings.working_hours = request.form.get("working_hours") or None
            settings.google_maps_url = request.form.get("google_maps_url") or None
            
            # Соцмережі
            settings.social_telegram = request.form.get("social_telegram") or None
            settings.social_whatsapp = request.form.get("social_whatsapp") or None
            settings.social_instagram = request.form.get("social_instagram") or None
            settings.social_facebook = request.form.get("social_facebook") or None
            settings.social_youtube = request.form.get("social_youtube") or None
            settings.social_tiktok = request.form.get("social_tiktok") or None
            
            # SEO
            settings.meta_title = request.form.get("meta_title") or None
            settings.meta_description = request.form.get("meta_description") or None
            settings.meta_keywords = request.form.get("meta_keywords") or None
            
            # Аналітика
            settings.google_analytics_id = request.form.get("google_analytics_id") or None
            settings.facebook_pixel_id = request.form.get("facebook_pixel_id") or None
            settings.custom_head_code = request.form.get("custom_head_code") or None
            
            # Магазин
            settings.default_currency = request.form.get("default_currency") or "EUR"
            try:
                settings.products_per_page = int(request.form.get("products_per_page", 12))
            except ValueError:
                settings.products_per_page = 12
            try:
                settings.min_order_amount = float(request.form.get("min_order_amount", 0))
            except ValueError:
                settings.min_order_amount = 0.0
            settings.shipping_info = request.form.get("shipping_info") or None

            db.session.commit()
            flash("Налаштування сайту збережено.", "success")
            return redirect(url_for("admin_settings"))

        return render_template("admin/settings.html", settings=settings)

    # ----- ПУБЛІЧНИЙ: ФОРМА КОНТАКТІВ -----

    @app.route("/api/contact", methods=["POST"])
    def api_contact():
        """API для збереження повідомлень з форми контактів."""
        data = request.get_json() if request.is_json else request.form
        
        name = data.get("name", "").strip()
        email = data.get("email", "").strip()
        phone = data.get("phone", "").strip()
        subject = data.get("subject", "").strip()
        message = data.get("message", "").strip()
        
        if not name or not email or not message:
            if request.is_json:
                return jsonify({"error": "Заповніть обов'язкові поля"}), 400
            flash("Заповніть обов'язкові поля: ім'я, email, повідомлення.", "danger")
            return redirect(url_for("contacts_page"))
        
        contact = ContactMessage(
            name=name,
            email=email,
            phone=phone or None,
            subject=subject or None,
            message=message,
        )
        db.session.add(contact)
        db.session.commit()
        
        if request.is_json:
            return jsonify({"success": True, "message": "Дякуємо за ваше повідомлення!"})
        
        flash("Дякуємо! Ваше повідомлення надіслано.", "success")
        return redirect(url_for("contacts_page"))

    # Ініціалізація БД при старті
    init_db()
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="127.0.0.1", port=5000, debug=True)
