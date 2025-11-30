
import os
import uuid
from datetime import datetime
from functools import wraps
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

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
    send_from_directory,
    abort,
)
from flask_login import login_required, current_user

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

# Ініціалізація SQLAlchemy та Flask-Login - імпортуємо з extensions для уникнення дублювання
from extensions import db, login_manager


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

    # Налаштування для завантаження файлів
    UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max
    
    # Створюємо папку uploads якщо не існує
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    
    def allowed_file(filename):
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

    db.init_app(app)
    
    # Ініціалізація Flask-Login
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Будь ласка, увійдіть для доступу до цієї сторінки."
    login_manager.login_message_category = "info"

    # ----- МОДЕЛІ (імпорт з models/) -----
    from models.settings import SiteSettings, ContactMessage
    from models.product import Product, Category
    from models.order import Order, OrderItem
    from models.user import User, UserRole
    from models.company import Company, CompanyStatus
    from models.warehouse import (
        WarehouseTask, StockMovement, ReplenishmentOrder, 
        ReplenishmentItem, WarehouseExpense, LowStockAlert
    )

    # Flask-Login user loader
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Робимо моделі доступними через app
    app.SiteSettings = SiteSettings
    app.Category = Category
    app.Product = Product
    app.Order = Order
    app.OrderItem = OrderItem
    app.ContactMessage = ContactMessage
    app.User = User
    app.UserRole = UserRole
    app.Company = Company
    app.CompanyStatus = CompanyStatus
    # Warehouse
    app.WarehouseTask = WarehouseTask
    app.StockMovement = StockMovement
    app.ReplenishmentOrder = ReplenishmentOrder
    app.ReplenishmentItem = ReplenishmentItem
    app.WarehouseExpense = WarehouseExpense
    app.LowStockAlert = LowStockAlert

    # ----- СЛУЖБОВІ ФУНКЦІЇ -----

    def init_db():
        """Створити схему, таблиці й дефолтні налаштування, якщо їх ще немає."""
        with app.app_context():
            # Для PostgreSQL - створюємо окрему схему
            db_schema = app.config.get("DB_SCHEMA", "smartshop")
            database_url = app.config.get("SQLALCHEMY_DATABASE_URI", "")
            
            from sqlalchemy import text
            
            if "postgresql" in database_url:
                # Створюємо схему, якщо не існує
                with db.engine.connect() as conn:
                    conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {db_schema}"))
                    conn.commit()
                print(f"✅ PostgreSQL схема '{db_schema}' готова")
            
            # Створюємо таблиці
            db.create_all()
            
            if "postgresql" in database_url:
                # МІГРАЦІЇ - додаємо відсутні колонки ПЕРЕД запитами до БД
                
                # site_settings колонки
                site_settings_columns = [
                    ('admin_username', 'VARCHAR(100)'),
                    ('admin_password_hash', 'VARCHAR(255)'),
                    ('admin_company_name', 'VARCHAR(255)'),
                    ('admin_company_legal_name', 'VARCHAR(255)'),
                    ('admin_vat_number', 'VARCHAR(50)'),
                    ('admin_vat_country', 'VARCHAR(2)'),
                    ('admin_company_address', 'VARCHAR(255)'),
                    ('admin_company_city', 'VARCHAR(100)'),
                    ('admin_company_postal_code', 'VARCHAR(20)'),
                    ('admin_company_country', 'VARCHAR(100)'),
                    ('admin_company_country_code', 'VARCHAR(2)'),
                    ('admin_handelsregister_id', 'VARCHAR(50)'),
                    ('admin_company_email', 'VARCHAR(255)'),
                    ('admin_company_phone', 'VARCHAR(50)'),
                    ('admin_company_website', 'VARCHAR(255)'),
                    ('b2b_enabled', 'BOOLEAN DEFAULT TRUE'),
                ]
                
                # categories колонки
                category_columns = [
                    ('image_url', 'VARCHAR(500)'),
                    ('is_active', 'BOOLEAN DEFAULT TRUE'),
                    ('sort_order', 'INTEGER DEFAULT 0'),
                    ('created_at', 'TIMESTAMP DEFAULT NOW()'),
                    ('updated_at', 'TIMESTAMP DEFAULT NOW()'),
                ]
                
                # products колонки
                product_columns = [
                    ('sku', 'VARCHAR(64)'),
                    ('old_price', 'FLOAT'),
                    ('cost_price', 'FLOAT'),
                    ('currency', "VARCHAR(8) DEFAULT 'UAH'"),
                    ('b2b_price', 'FLOAT'),
                    ('min_b2b_quantity', 'INTEGER DEFAULT 1'),
                    ('reserved', 'INTEGER DEFAULT 0'),
                    ('min_stock', 'INTEGER DEFAULT 0'),
                    ('short_description', 'VARCHAR(255)'),
                    ('long_description', 'TEXT'),
                    ('gallery', 'JSON'),
                    ('is_featured', 'BOOLEAN DEFAULT FALSE'),
                    ('meta_title', 'VARCHAR(100)'),
                    ('meta_description', 'VARCHAR(200)'),
                    ('created_at', 'TIMESTAMP DEFAULT NOW()'),
                    ('updated_at', 'TIMESTAMP DEFAULT NOW()'),
                ]
                
                # orders колонки
                order_columns = [
                    ('order_number', 'VARCHAR(50)'),
                    ('user_id', 'INTEGER'),
                    ('company_id', 'INTEGER'),
                    ('is_b2b', 'BOOLEAN DEFAULT FALSE'),
                    ('customer_name', 'VARCHAR(200)'),
                    ('customer_email', 'VARCHAR(255)'),
                    ('customer_phone', 'VARCHAR(50)'),
                    ('shipping_address', 'TEXT'),
                    ('shipping_city', 'VARCHAR(100)'),
                    ('shipping_postal_code', 'VARCHAR(20)'),
                    ('shipping_country', 'VARCHAR(100)'),
                    ('shipping_method', 'VARCHAR(50)'),
                    ('shipping_cost', 'FLOAT DEFAULT 0.0'),
                    ('tracking_number', 'VARCHAR(100)'),
                    ('payment_method', "VARCHAR(20) DEFAULT 'card'"),
                    ('payment_status', 'VARCHAR(20)'),
                    ('stripe_payment_intent', 'VARCHAR(255)'),
                    ('stripe_session_id', 'VARCHAR(255)'),
                    ('subtotal', 'FLOAT DEFAULT 0.0'),
                    ('discount', 'FLOAT DEFAULT 0.0'),
                    ('tax', 'FLOAT DEFAULT 0.0'),
                    ('amount', 'FLOAT DEFAULT 0.0'),
                    ('currency', "VARCHAR(8) DEFAULT 'UAH'"),
                    ('status', "VARCHAR(20) DEFAULT 'created'"),
                    ('notes', 'TEXT'),
                    ('admin_notes', 'TEXT'),
                    ('created_at', 'TIMESTAMP DEFAULT NOW()'),
                    ('updated_at', 'TIMESTAMP DEFAULT NOW()'),
                    ('paid_at', 'TIMESTAMP'),
                    ('shipped_at', 'TIMESTAMP'),
                    ('delivered_at', 'TIMESTAMP'),
                ]
                
                # order_items колонки
                order_item_columns = [
                    ('order_id', 'INTEGER'),
                    ('product_id', 'INTEGER'),
                    ('product_name', 'VARCHAR(200)'),
                    ('product_sku', 'VARCHAR(64)'),
                    ('price', 'FLOAT'),
                    ('quantity', 'INTEGER DEFAULT 1'),
                    ('currency', "VARCHAR(8) DEFAULT 'UAH'"),
                    ('created_at', 'TIMESTAMP DEFAULT NOW()'),
                ]
                
                # companies колонки
                company_columns = [
                    ('name', 'VARCHAR(255)'),
                    ('legal_name', 'VARCHAR(255)'),
                    ('vat_number', 'VARCHAR(50)'),
                    ('vat_country', 'VARCHAR(2)'),
                    ('vat_verified', 'BOOLEAN DEFAULT FALSE'),
                    ('vat_verified_at', 'TIMESTAMP'),
                    ('vat_data', 'JSON'),
                    ('handelsregister_id', 'VARCHAR(100)'),
                    ('hr_verified', 'BOOLEAN DEFAULT FALSE'),
                    ('hr_data', 'JSON'),
                    ('website', 'VARCHAR(255)'),
                    ('domain', 'VARCHAR(255)'),
                    ('whois_data', 'JSON'),
                    ('whois_checked_at', 'TIMESTAMP'),
                    ('address', 'VARCHAR(500)'),
                    ('city', 'VARCHAR(100)'),
                    ('postal_code', 'VARCHAR(20)'),
                    ('country', 'VARCHAR(100)'),
                    ('country_code', 'VARCHAR(2)'),
                    ('contact_person', 'VARCHAR(200)'),
                    ('contact_email', 'VARCHAR(255)'),
                    ('contact_phone', 'VARCHAR(50)'),
                    ('credit_limit', 'FLOAT DEFAULT 0.0'),
                    ('payment_terms', 'INTEGER DEFAULT 0'),
                    ('discount_percent', 'FLOAT DEFAULT 0.0'),
                    ('status', "VARCHAR(20) DEFAULT 'pending'"),
                    ('rejection_reason', 'TEXT'),
                    ('reliability_score', 'INTEGER DEFAULT 0'),
                    ('reliability_level', "VARCHAR(20) DEFAULT 'critical'"),
                    ('last_verification_at', 'TIMESTAMP'),
                    ('last_verification_data', 'JSON'),
                    ('is_whois_verified', 'BOOLEAN DEFAULT FALSE'),
                    ('is_hr_verified', 'BOOLEAN DEFAULT FALSE'),
                    ('created_at', 'TIMESTAMP DEFAULT NOW()'),
                    ('updated_at', 'TIMESTAMP DEFAULT NOW()'),
                    ('verified_at', 'TIMESTAMP'),
                ]
                
                # users колонки
                user_columns = [
                    ('email', 'VARCHAR(255)'),
                    ('password_hash', 'VARCHAR(255)'),
                    ('role', "VARCHAR(20) DEFAULT 'customer'"),
                    ('is_active', 'BOOLEAN DEFAULT TRUE'),
                    ('is_verified', 'BOOLEAN DEFAULT FALSE'),
                    ('first_name', 'VARCHAR(100)'),
                    ('last_name', 'VARCHAR(100)'),
                    ('phone', 'VARCHAR(50)'),
                    ('company_id', 'INTEGER'),
                    ('created_at', 'TIMESTAMP DEFAULT NOW()'),
                    ('updated_at', 'TIMESTAMP DEFAULT NOW()'),
                    ('last_login', 'TIMESTAMP'),
                ]
                
                # verification_logs колонки
                verification_log_columns = [
                    ('company_id', 'INTEGER'),
                    ('check_type', 'VARCHAR(30)'),
                    ('status', 'VARCHAR(20)'),
                    ('is_valid', 'BOOLEAN'),
                    ('request_data', 'JSON'),
                    ('response_data', 'JSON'),
                    ('error_message', 'TEXT'),
                    ('changes_detected', 'BOOLEAN DEFAULT FALSE'),
                    ('changes_description', 'TEXT'),
                    ('checked_at', 'TIMESTAMP DEFAULT NOW()'),
                ]
                
                # admin_alerts колонки
                admin_alert_columns = [
                    ('company_id', 'INTEGER'),
                    ('alert_type', 'VARCHAR(50)'),
                    ('severity', "VARCHAR(20) DEFAULT 'info'"),
                    ('title', 'VARCHAR(200)'),
                    ('message', 'TEXT'),
                    ('data', 'JSON'),
                    ('is_read', 'BOOLEAN DEFAULT FALSE'),
                    ('is_resolved', 'BOOLEAN DEFAULT FALSE'),
                    ('resolved_by', 'INTEGER'),
                    ('resolved_at', 'TIMESTAMP'),
                    ('resolution_note', 'TEXT'),
                    ('created_at', 'TIMESTAMP DEFAULT NOW()'),
                ]
                
                # contact_messages колонки
                contact_message_columns = [
                    ('name', 'VARCHAR(200)'),
                    ('email', 'VARCHAR(255)'),
                    ('phone', 'VARCHAR(50)'),
                    ('subject', 'VARCHAR(255)'),
                    ('message', 'TEXT'),
                    ('is_read', 'BOOLEAN DEFAULT FALSE'),
                    ('replied_at', 'TIMESTAMP'),
                    ('notes', 'TEXT'),
                    ('created_at', 'TIMESTAMP DEFAULT NOW()'),
                ]
                
                # warehouse_tasks колонки
                warehouse_task_columns = [
                    ('order_id', 'INTEGER'),
                    ('task_number', 'VARCHAR(50)'),
                    ('status', "VARCHAR(20) DEFAULT 'pending'"),
                    ('priority', 'INTEGER DEFAULT 3'),
                    ('notes', 'TEXT'),
                    ('admin_notes', 'TEXT'),
                    ('assigned_to', 'VARCHAR(100)'),
                    ('tracking_number', 'VARCHAR(100)'),
                    ('carrier', 'VARCHAR(50)'),
                    ('weight_kg', 'FLOAT'),
                    ('dimensions', 'VARCHAR(50)'),
                    ('shipping_cost', 'FLOAT DEFAULT 0.0'),
                    ('created_at', 'TIMESTAMP DEFAULT NOW()'),
                    ('updated_at', 'TIMESTAMP DEFAULT NOW()'),
                    ('packed_at', 'TIMESTAMP'),
                    ('shipped_at', 'TIMESTAMP'),
                    ('delivered_at', 'TIMESTAMP'),
                ]
                
                # stock_movements колонки
                stock_movement_columns = [
                    ('product_id', 'INTEGER'),
                    ('movement_type', 'VARCHAR(20)'),
                    ('quantity', 'INTEGER'),
                    ('stock_after', 'INTEGER'),
                    ('reason', 'VARCHAR(100)'),
                    ('reference_id', 'INTEGER'),
                    ('notes', 'TEXT'),
                    ('performed_by', 'VARCHAR(100)'),
                    ('created_at', 'TIMESTAMP DEFAULT NOW()'),
                ]
                
                # replenishment_orders колонки
                replenishment_order_columns = [
                    ('order_number', 'VARCHAR(50)'),
                    ('supplier_name', 'VARCHAR(255)'),
                    ('supplier_contact', 'VARCHAR(255)'),
                    ('status', "VARCHAR(20) DEFAULT 'draft'"),
                    ('subtotal', 'FLOAT DEFAULT 0.0'),
                    ('shipping_cost', 'FLOAT DEFAULT 0.0'),
                    ('total', 'FLOAT DEFAULT 0.0'),
                    ('currency', "VARCHAR(8) DEFAULT 'UAH'"),
                    ('is_paid', 'BOOLEAN DEFAULT FALSE'),
                    ('paid_at', 'TIMESTAMP'),
                    ('payment_method', 'VARCHAR(50)'),
                    ('notes', 'TEXT'),
                    ('created_by', 'VARCHAR(100)'),
                    ('created_at', 'TIMESTAMP DEFAULT NOW()'),
                    ('updated_at', 'TIMESTAMP DEFAULT NOW()'),
                    ('ordered_at', 'TIMESTAMP'),
                    ('expected_at', 'TIMESTAMP'),
                    ('received_at', 'TIMESTAMP'),
                ]
                
                # replenishment_items колонки
                replenishment_item_columns = [
                    ('replenishment_id', 'INTEGER'),
                    ('product_id', 'INTEGER'),
                    ('product_name', 'VARCHAR(200)'),
                    ('product_sku', 'VARCHAR(64)'),
                    ('quantity', 'INTEGER DEFAULT 1'),
                    ('unit_price', 'FLOAT DEFAULT 0.0'),
                    ('created_at', 'TIMESTAMP DEFAULT NOW()'),
                ]
                
                # warehouse_expenses колонки
                warehouse_expense_columns = [
                    ('category', "VARCHAR(50) DEFAULT 'other'"),
                    ('description', 'VARCHAR(255)'),
                    ('amount', 'FLOAT'),
                    ('currency', "VARCHAR(8) DEFAULT 'UAH'"),
                    ('warehouse_task_id', 'INTEGER'),
                    ('replenishment_id', 'INTEGER'),
                    ('receipt_number', 'VARCHAR(100)'),
                    ('receipt_url', 'VARCHAR(500)'),
                    ('created_by', 'VARCHAR(100)'),
                    ('expense_date', 'DATE DEFAULT CURRENT_DATE'),
                    ('notes', 'TEXT'),
                    ('created_at', 'TIMESTAMP DEFAULT NOW()'),
                ]
                
                # low_stock_alerts колонки
                low_stock_alert_columns = [
                    ('product_id', 'INTEGER'),
                    ('current_stock', 'INTEGER'),
                    ('min_stock', 'INTEGER'),
                    ('is_resolved', 'BOOLEAN DEFAULT FALSE'),
                    ('resolved_at', 'TIMESTAMP'),
                    ('resolved_by', 'VARCHAR(100)'),
                    ('replenishment_id', 'INTEGER'),
                    ('created_at', 'TIMESTAMP DEFAULT NOW()'),
                ]
                
                migrations = [
                    ('site_settings', site_settings_columns),
                    ('categories', category_columns),
                    ('products', product_columns),
                    ('orders', order_columns),
                    ('order_items', order_item_columns),
                    ('companies', company_columns),
                    ('users', user_columns),
                    ('verification_logs', verification_log_columns),
                    ('admin_alerts', admin_alert_columns),
                    ('contact_messages', contact_message_columns),
                    # Warehouse
                    ('warehouse_tasks', warehouse_task_columns),
                    ('stock_movements', stock_movement_columns),
                    ('replenishment_orders', replenishment_order_columns),
                    ('replenishment_items', replenishment_item_columns),
                    ('warehouse_expenses', warehouse_expense_columns),
                    ('low_stock_alerts', low_stock_alert_columns),
                ]
                
                with db.engine.connect() as conn:
                    for table_name, columns in migrations:
                        for col_name, col_type in columns:
                            try:
                                conn.execute(text(f"ALTER TABLE {db_schema}.{table_name} ADD COLUMN IF NOT EXISTS {col_name} {col_type}"))
                            except Exception as e:
                                pass
                    conn.commit()
                print("✅ Міграції застосовані")
            
            # Тепер безпечно працювати з моделями
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
    print(f"🔧 DEMO_MODE = {DEMO_MODE}")

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

    # ----- РЕЄСТРАЦІЯ BLUEPRINTS -----
    from routes.auth import auth_bp
    from routes.cabinet import cabinet_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(cabinet_bp)

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
                    
                    # Створюємо завдання для складу
                    try:
                        from models.warehouse import WarehouseTask
                        existing_task = WarehouseTask.query.filter_by(order_id=order.id).first()
                        if not existing_task:
                            WarehouseTask.create_from_order(
                                order_id=order.id,
                                priority=2 if getattr(order, 'is_b2b', False) else 3,
                                notes=getattr(order, 'notes', ''),
                            )
                    except Exception:
                        pass  # Якщо модуль складу не доступний
                    
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
                
                # Створюємо завдання для складу
                try:
                    from models.warehouse import WarehouseTask
                    existing_task = WarehouseTask.query.filter_by(order_id=order.id).first()
                    if not existing_task:
                        WarehouseTask.create_from_order(
                            order_id=order.id,
                            priority=2 if getattr(order, 'is_b2b', False) else 3,
                            notes=getattr(order, 'notes', ''),
                        )
                except Exception:
                    pass  # Якщо модуль складу не доступний

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

            # Спочатку перевіряємо в БД
            settings = SiteSettings.get_or_create()
            
            # Якщо є логін/пароль в БД - використовуємо їх
            if settings.admin_username and settings.admin_password_hash:
                if username == settings.admin_username and check_password_hash(settings.admin_password_hash, password):
                    session["is_admin"] = True
                    flash("Вітаю, ви увійшли в адмін-панель.", "success")
                    return redirect(url_for("admin_dashboard"))
                else:
                    flash("Невірний логін або пароль.", "danger")
            else:
                # Fallback на змінні середовища
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

    # ----- АДМІНКА: ЗАВАНТАЖЕННЯ ЗОБРАЖЕНЬ -----

    @app.route("/admin/upload", methods=["POST"])
    @admin_required
    def admin_upload():
        """Завантаження зображення на сервер."""
        if 'file' not in request.files:
            return jsonify({"error": "Файл не обрано"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "Файл не обрано"}), 400
        
        if file and allowed_file(file.filename):
            # Генеруємо унікальне ім'я файлу
            ext = file.filename.rsplit('.', 1)[1].lower()
            filename = f"{uuid.uuid4().hex}.{ext}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Повертаємо URL до файлу
            file_url = url_for('static', filename=f'uploads/{filename}', _external=True)
            return jsonify({
                "success": True, 
                "url": file_url,
                "filename": filename
            })
        
        return jsonify({"error": "Недозволений тип файлу. Дозволено: png, jpg, jpeg, gif, webp"}), 400

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
            
            # ========== АДМІНІСТРАТОР ==========
            # Логін
            new_username = request.form.get("admin_username", "").strip()
            if new_username and len(new_username) >= 3:
                settings.admin_username = new_username
            
            # Пароль (тільки якщо заповнено і співпадає)
            new_password = request.form.get("admin_password", "")
            confirm_password = request.form.get("admin_password_confirm", "")
            if new_password:
                if len(new_password) < 6:
                    flash("Пароль має бути мінімум 6 символів.", "warning")
                elif new_password != confirm_password:
                    flash("Паролі не співпадають.", "warning")
                else:
                    settings.admin_password_hash = generate_password_hash(new_password)
                    flash("Пароль адміністратора змінено.", "success")
            
            # Дані юрособи адміністратора
            settings.admin_company_name = request.form.get("admin_company_name") or None
            settings.admin_company_legal_name = request.form.get("admin_company_legal_name") or None
            settings.admin_vat_number = request.form.get("admin_vat_number") or None
            settings.admin_vat_country = request.form.get("admin_vat_country") or None
            settings.admin_company_address = request.form.get("admin_company_address") or None
            settings.admin_company_city = request.form.get("admin_company_city") or None
            settings.admin_company_postal_code = request.form.get("admin_company_postal_code") or None
            settings.admin_company_country = request.form.get("admin_company_country") or None
            settings.admin_company_country_code = (request.form.get("admin_company_country_code") or "").upper() or None
            settings.admin_handelsregister_id = request.form.get("admin_handelsregister_id") or None
            settings.admin_company_email = request.form.get("admin_company_email") or None
            settings.admin_company_phone = request.form.get("admin_company_phone") or None
            settings.admin_company_website = request.form.get("admin_company_website") or None

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

    # ----- AUTH: ВХІД/РЕЄСТРАЦІЯ B2C/B2B -----

    @app.route("/login", methods=["GET", "POST"])
    def user_login():
        """Сторінка входу для користувачів."""
        if current_user.is_authenticated:
            if current_user.is_b2b:
                return redirect(url_for("b2b_dashboard"))
            return redirect(url_for("user_cabinet"))
        
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            remember = request.form.get("remember") == "on"
            
            user = User.get_by_email(email)
            
            if user and user.check_password(password):
                if not user.is_active:
                    flash("Ваш акаунт деактивовано. Зверніться до підтримки.", "danger")
                    return render_template("auth/login.html")
                
                from flask_login import login_user as flask_login_user
                flask_login_user(user, remember=remember)
                user.update_last_login()
                
                flash(f"Вітаємо, {user.full_name}!", "success")
                
                next_page = request.args.get("next")
                if next_page:
                    return redirect(next_page)
                
                if user.is_admin or user.is_manager:
                    return redirect(url_for("admin_dashboard"))
                elif user.is_b2b:
                    return redirect(url_for("b2b_dashboard"))
                
                return redirect(url_for("user_cabinet"))
            
            flash("Невірний email або пароль.", "danger")
        
        settings = SiteSettings.get_or_create()
        return render_template("auth/login.html", settings=settings)

    @app.route("/logout")
    @login_required
    def user_logout():
        """Вихід з системи."""
        from flask_login import logout_user as flask_logout_user
        flask_logout_user()
        flash("Ви успішно вийшли з системи.", "info")
        return redirect(url_for("user_login"))

    @app.route("/register", methods=["GET", "POST"])
    def user_register():
        """Реєстрація B2C клієнта."""
        if current_user.is_authenticated:
            return redirect(url_for("user_cabinet"))
        
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            password_confirm = request.form.get("password_confirm", "")
            first_name = request.form.get("first_name", "").strip()
            last_name = request.form.get("last_name", "").strip()
            phone = request.form.get("phone", "").strip()
            
            errors = []
            
            if not email:
                errors.append("Email обов'язковий")
            elif User.get_by_email(email):
                errors.append("Користувач з таким email вже існує")
            
            if not password:
                errors.append("Пароль обов'язковий")
            elif len(password) < 6:
                errors.append("Пароль має бути не менше 6 символів")
            elif password != password_confirm:
                errors.append("Паролі не співпадають")
            
            if errors:
                for error in errors:
                    flash(error, "danger")
                settings = SiteSettings.get_or_create()
                return render_template("auth/register.html", settings=settings)
            
            user = User.create_user(
                email=email,
                password=password,
                role=UserRole.CUSTOMER,
                first_name=first_name or None,
                last_name=last_name or None,
                phone=phone or None,
            )
            
            from flask_login import login_user as flask_login_user
            flask_login_user(user)
            flash("Реєстрація успішна! Ласкаво просимо!", "success")
            return redirect(url_for("user_cabinet"))
        
        settings = SiteSettings.get_or_create()
        return render_template("auth/register.html", settings=settings)

    @app.route("/register/b2b", methods=["GET", "POST"])
    def user_register_b2b():
        """Реєстрація B2B партнера."""
        if current_user.is_authenticated:
            return redirect(url_for("b2b_dashboard"))
        
        settings = SiteSettings.get_or_create()
        if not getattr(settings, 'b2b_registration_open', True):
            flash("B2B реєстрація тимчасово закрита.", "warning")
            return redirect(url_for("user_login"))
        
        if request.method == "POST":
            # Дані користувача
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            password_confirm = request.form.get("password_confirm", "")
            first_name = request.form.get("first_name", "").strip()
            last_name = request.form.get("last_name", "").strip()
            phone = request.form.get("phone", "").strip()
            
            # Дані компанії
            company_name = request.form.get("company_name", "").strip()
            vat_number = request.form.get("vat_number", "").strip()
            country = request.form.get("country", "").strip()
            address = request.form.get("address", "").strip()
            city = request.form.get("city", "").strip()
            website = request.form.get("website", "").strip()
            
            # Валідація
            errors = []
            
            if not email:
                errors.append("Email обов'язковий")
            elif User.get_by_email(email):
                errors.append("Користувач з таким email вже існує")
            
            if not password:
                errors.append("Пароль обов'язковий")
            elif len(password) < 8:
                errors.append("Пароль має бути не менше 8 символів")
            elif password != password_confirm:
                errors.append("Паролі не співпадають")
            
            if not company_name:
                errors.append("Назва компанії обов'язкова")
            
            if not first_name or not last_name:
                errors.append("Ім'я та прізвище контактної особи обов'язкові")
            
            if errors:
                for error in errors:
                    flash(error, "danger")
                return render_template("auth/register_b2b.html", settings=settings)
            
            # Перевірка VAT (опціонально)
            vat_verified = False
            vat_data = None
            if vat_number:
                try:
                    from services.vat_checker import VATChecker
                    checker = VATChecker()
                    vat_result = checker.check_vat(vat_number)
                    vat_verified = vat_result.get("valid", False)
                    vat_data = vat_result
                    if vat_verified:
                        flash(f"✅ VAT номер підтверджено!", "success")
                    else:
                        flash(f"⚠️ VAT не підтверджено: {vat_result.get('error', '')}", "warning")
                except Exception as e:
                    flash(f"⚠️ Помилка перевірки VAT: {str(e)}", "warning")
            
            # Створення компанії
            company = Company(
                name=company_name,
                vat_number=vat_number or None,
                vat_country=country[:2].upper() if country else None,
                vat_verified=vat_verified,
                vat_verified_at=datetime.utcnow() if vat_verified else None,
                vat_data=vat_data,
                address=address or None,
                city=city or None,
                country=country or None,
                website=website or None,
                contact_person=f"{first_name} {last_name}",
                contact_email=email,
                contact_phone=phone or None,
                status=CompanyStatus.VERIFIED.value if (getattr(settings, 'b2b_auto_approve', False) and vat_verified) else CompanyStatus.PENDING.value,
            )
            db.session.add(company)
            db.session.flush()
            
            # Створення користувача
            user = User(
                email=email,
                role=UserRole.PARTNER.value,
                first_name=first_name,
                last_name=last_name,
                phone=phone or None,
                company_id=company.id,
                is_verified=vat_verified,
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            
            from flask_login import login_user as flask_login_user
            flask_login_user(user)
            
            if company.is_verified:
                flash("✅ Реєстрація успішна! Ваша компанія верифікована.", "success")
            else:
                flash("📋 Реєстрація успішна! Ваша заявка на розгляді.", "info")
            
            return redirect(url_for("b2b_dashboard"))
        
        return render_template("auth/register_b2b.html", settings=settings)

    # ----- API: ПЕРЕВІРКА VAT -----

    @app.route("/api/verify-vat", methods=["POST"])
    def api_verify_vat():
        """AJAX перевірка VAT номера."""
        data = request.get_json() if request.is_json else request.form
        vat_number = data.get("vat_number", "").strip()
        
        if not vat_number:
            return jsonify({"error": "VAT номер обов'язковий"}), 400
        
        try:
            from services.vat_checker import VATChecker
            checker = VATChecker()
            result = checker.check_vat(vat_number)
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e), "valid": False}), 500

    # ----- КАБІНЕТ B2C -----

    @app.route("/cabinet")
    @login_required
    def user_cabinet():
        """Особистий кабінет B2C клієнта."""
        if current_user.is_b2b:
            return redirect(url_for("b2b_dashboard"))
        
        settings = SiteSettings.get_or_create()
        
        # Статистика
        total_orders = Order.query.filter_by(customer_email=current_user.email).count()
        recent_orders = Order.query.filter_by(customer_email=current_user.email)\
            .order_by(Order.created_at.desc()).limit(5).all()
        
        for order in recent_orders:
            order.status_display = {
                "created": "Створено",
                "pending": "Очікує оплати",
                "paid": "Оплачено",
                "shipped": "Відправлено",
                "delivered": "Доставлено",
                "cancelled": "Скасовано",
            }.get(order.status, order.status)
        
        return render_template(
            "cabinet/b2c/dashboard.html",
            settings=settings,
            total_orders=total_orders,
            recent_orders=recent_orders,
        )

    # ----- КАБІНЕТ B2B -----

    @app.route("/cabinet/b2b")
    @login_required
    def b2b_dashboard():
        """Dashboard B2B партнера."""
        if not current_user.is_b2b:
            return redirect(url_for("user_cabinet"))
        
        settings = SiteSettings.get_or_create()
        company = current_user.company
        
        # Статистика
        total_orders = Order.query.filter_by(customer_email=current_user.email).count()
        pending_orders = Order.query.filter_by(customer_email=current_user.email, status="pending").count()
        total_spent = db.session.query(db.func.coalesce(db.func.sum(Order.amount), 0.0))\
            .filter_by(customer_email=current_user.email, status="paid").scalar()
        
        discount = company.discount_percent if company else 0
        
        recent_orders = Order.query.filter_by(customer_email=current_user.email)\
            .order_by(Order.created_at.desc()).limit(5).all()
        
        for order in recent_orders:
            order.status_display = {
                "created": "Створено",
                "pending": "Очікує оплати",
                "paid": "Оплачено",
                "shipped": "Відправлено",
                "delivered": "Доставлено",
                "cancelled": "Скасовано",
            }.get(order.status, order.status)
        
        return render_template(
            "cabinet/b2b/dashboard.html",
            settings=settings,
            total_orders=total_orders,
            pending_orders=pending_orders,
            total_spent=total_spent,
            discount=discount,
            recent_orders=recent_orders,
            recent_documents=[],  # TODO: Документи
            chart_labels=None,
            chart_data=None,
        )

    @app.route("/cabinet/b2b/orders")
    @login_required
    def b2b_orders():
        """Замовлення B2B партнера."""
        if not current_user.is_b2b:
            return redirect(url_for("user_cabinet"))
        
        settings = SiteSettings.get_or_create()
        
        orders = Order.query.filter_by(customer_email=current_user.email)\
            .order_by(Order.created_at.desc()).all()
        
        for order in orders:
            order.status_display = {
                "created": "Створено",
                "pending": "Очікує оплати",
                "paid": "Оплачено",
                "shipped": "Відправлено",
                "delivered": "Доставлено",
                "cancelled": "Скасовано",
            }.get(order.status, order.status)
        
        return render_template(
            "cabinet/b2b/orders.html",
            settings=settings,
            orders=orders,
        )

    @app.route("/cabinet/b2b/company", methods=["GET", "POST"])
    @login_required
    def b2b_company():
        """Профіль компанії B2B партнера."""
        if not current_user.is_b2b:
            return redirect(url_for("user_cabinet"))
        
        settings = SiteSettings.get_or_create()
        company = current_user.company
        
        if request.method == "POST" and company:
            company.name = request.form.get("name", company.name)
            company.address = request.form.get("address", company.address)
            company.city = request.form.get("city", company.city)
            company.postal_code = request.form.get("postal_code", company.postal_code)
            company.country = request.form.get("country", company.country)
            company.website = request.form.get("website", company.website)
            company.contact_person = request.form.get("contact_person", company.contact_person)
            company.contact_phone = request.form.get("phone", company.contact_phone)
            
            db.session.commit()
            flash("Дані компанії оновлено!", "success")
            return redirect(url_for("b2b_company"))
        
        return render_template(
            "cabinet/b2b/company.html",
            settings=settings,
            company=company,
        )

    # ========== CRM ADMIN ROUTES ==========
    
    @app.route("/admin/crm")
    @admin_required
    def admin_crm():
        """CRM - список партнерів."""
        settings = SiteSettings.query.first()
        
        # Фільтри
        filter_status = request.args.get("status", "")
        filter_reliability = request.args.get("reliability", "")
        filter_country = request.args.get("country", "")
        search = request.args.get("search", "")
        page = request.args.get("page", 1, type=int)
        per_page = 20
        
        # Базовий запит
        query = Company.query
        
        # Застосовуємо фільтри
        if filter_status:
            query = query.filter(Company.status == filter_status)
        if filter_reliability:
            query = query.filter(Company.reliability_level == filter_reliability)
        if filter_country:
            query = query.filter(Company.country_code == filter_country)
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                db.or_(
                    Company.name.ilike(search_term),
                    Company.vat_number.ilike(search_term),
                    Company.domain.ilike(search_term),
                )
            )
        
        # Сортування та пагінація
        query = query.order_by(Company.created_at.desc())
        total = query.count()
        companies = query.offset((page - 1) * per_page).limit(per_page).all()
        total_pages = (total + per_page - 1) // per_page
        
        # Статистика
        all_companies = Company.query.all()
        stats = {
            "total": len(all_companies),
            "verified": len([c for c in all_companies if c.status == "verified"]),
            "pending": len([c for c in all_companies if c.status == "pending"]),
            "rejected": len([c for c in all_companies if c.status == "rejected"]),
            "high_reliability": len([c for c in all_companies if c.reliability_level == "high"]),
            "medium_reliability": len([c for c in all_companies if c.reliability_level == "medium"]),
            "low_reliability": len([c for c in all_companies if c.reliability_level == "low"]),
            "critical_reliability": len([c for c in all_companies if c.reliability_level == "critical"]),
        }
        # Відсотки
        total_r = max(1, stats["total"])
        stats["high_reliability_pct"] = int(stats["high_reliability"] / total_r * 100)
        stats["medium_reliability_pct"] = int(stats["medium_reliability"] / total_r * 100)
        stats["low_reliability_pct"] = int(stats["low_reliability"] / total_r * 100)
        stats["critical_reliability_pct"] = int(stats["critical_reliability"] / total_r * 100)
        
        # Алерти - використовуємо прямі запити замість методів класу
        from models.company import AdminAlert, AlertSeverity
        critical_alerts = AdminAlert.query.filter_by(
            severity=AlertSeverity.CRITICAL.value,
            is_resolved=False
        ).order_by(AdminAlert.created_at.desc()).all()
        unread_alerts_count = AdminAlert.query.filter_by(is_read=False).count()
        
        # Унікальні країни
        countries = db.session.query(Company.country_code, Company.country).distinct().filter(
            Company.country_code.isnot(None)
        ).all()
        
        return render_template(
            "admin/crm.html",
            settings=settings,
            companies=companies,
            stats=stats,
            critical_alerts=critical_alerts,
            unread_alerts_count=unread_alerts_count,
            countries=countries,
            filter_status=filter_status,
            filter_reliability=filter_reliability,
            filter_country=filter_country,
            search=search,
            page=page,
            total_pages=total_pages,
        )
    
    @app.route("/admin/crm/partner/<int:id>")
    @admin_required
    def admin_crm_partner(id):
        """Деталі партнера."""
        settings = SiteSettings.query.first()
        company = Company.query.get_or_404(id)
        
        from models.company import AdminAlert, VerificationLog
        company_alerts = AdminAlert.query.filter_by(
            company_id=id, 
            is_resolved=False
        ).order_by(AdminAlert.created_at.desc()).all()
        
        verification_logs = VerificationLog.query.filter_by(
            company_id=id
        ).order_by(VerificationLog.checked_at.desc()).limit(20).all()
        
        return render_template(
            "admin/crm_partner.html",
            settings=settings,
            company=company,
            company_alerts=company_alerts,
            verification_logs=verification_logs,
        )
    
    @app.route("/admin/crm/partner/<int:id>/verify", methods=["POST"])
    @admin_required
    def admin_crm_partner_verify(id):
        """Запустити верифікацію партнера."""
        company = Company.query.get_or_404(id)
        
        try:
            from services.partner_verifier import partner_verifier
            from models.company import VerificationLog, AdminAlert
            
            # Попередній результат для порівняння
            previous_result = company.last_verification_data
            
            # Повна верифікація
            result = partner_verifier.full_verification(
                company_name=company.name,
                vat_number=company.full_vat_number,
                domain=company.website or company.domain,
                hr_number=company.handelsregister_id,
                country_code=company.country_code,
                city=company.city,
                previous_result=previous_result,
            )
            
            # Оновлюємо компанію
            company.reliability_score = result.get("reliability_score", 0)
            company.reliability_level = result.get("reliability_level", "critical")
            company.last_verification_at = datetime.utcnow()
            company.last_verification_data = result
            
            # Оновлюємо статуси перевірок
            if result.get("vat_result", {}).get("valid"):
                company.vat_verified = True
                company.vat_verified_at = datetime.utcnow()
                company.vat_data = result["vat_result"]
            
            if result.get("whois_result", {}).get("valid"):
                company.is_whois_verified = True
                company.whois_checked_at = datetime.utcnow()
                company.whois_data = result["whois_result"]
            
            if result.get("hr_result", {}).get("valid"):
                company.is_hr_verified = True
                company.hr_data = result["hr_result"]
            
            # Логуємо перевірку
            VerificationLog.log_check(
                company_id=company.id,
                check_type="full",
                status="success",
                is_valid=result.get("reliability_score", 0) >= 50,
                response_data=result,
                changes_detected=len(result.get("changes", [])) > 0,
                changes_description=str(result.get("changes", [])) if result.get("changes") else None,
            )
            
            # Створюємо алерти
            for alert_data in result.get("alerts", []):
                AdminAlert.create_alert(
                    alert_type=alert_data.get("type"),
                    title=alert_data.get("message", "Алерт верифікації"),
                    message=alert_data.get("message"),
                    company_id=company.id,
                    severity=alert_data.get("severity", "info"),
                    data=result,
                )
            
            db.session.commit()
            
            return jsonify({
                "success": True,
                "summary": result.get("summary", ""),
                "score": result.get("reliability_score"),
                "level": result.get("reliability_level"),
            })
            
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
    
    @app.route("/admin/crm/partner/<int:id>/approve", methods=["POST"])
    @admin_required
    def admin_crm_partner_approve(id):
        """Підтвердити партнера."""
        company = Company.query.get_or_404(id)
        company.status = "verified"
        company.verified_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({"success": True})
    
    @app.route("/admin/crm/partner/<int:id>/reject", methods=["POST"])
    @admin_required
    def admin_crm_partner_reject(id):
        """Відхилити партнера."""
        data = request.get_json() or {}
        company = Company.query.get_or_404(id)
        company.status = "rejected"
        company.rejection_reason = data.get("reason", "")
        db.session.commit()
        
        return jsonify({"success": True})
    
    @app.route("/admin/crm/partner/<int:id>/suspend", methods=["POST"])
    @admin_required
    def admin_crm_partner_suspend(id):
        """Призупинити партнера."""
        data = request.get_json() or {}
        company = Company.query.get_or_404(id)
        company.status = "suspended"
        company.rejection_reason = data.get("reason", "")
        db.session.commit()
        
        return jsonify({"success": True})
    
    @app.route("/admin/crm/partner/<int:id>/update", methods=["POST"])
    @admin_required
    def admin_crm_partner_update(id):
        """Оновити B2B налаштування партнера."""
        company = Company.query.get_or_404(id)
        company.credit_limit = float(request.form.get("credit_limit", 0))
        company.payment_terms = int(request.form.get("payment_terms", 0))
        company.discount_percent = float(request.form.get("discount_percent", 0))
        db.session.commit()
        
        flash("Налаштування оновлено!", "success")
        return redirect(url_for("admin_crm_partner", id=id))
    
    @app.route("/admin/crm/alerts")
    @admin_required
    def admin_crm_alerts():
        """Список алертів."""
        settings = SiteSettings.query.first()
        
        from models.company import AdminAlert
        
        filter_severity = request.args.get("severity", "")
        filter_status = request.args.get("status", "")
        page = request.args.get("page", 1, type=int)
        per_page = 30
        
        query = AdminAlert.query
        
        if filter_severity:
            query = query.filter(AdminAlert.severity == filter_severity)
        if filter_status == "unread":
            query = query.filter(AdminAlert.is_read == False)
        elif filter_status == "unresolved":
            query = query.filter(AdminAlert.is_resolved == False)
        elif filter_status == "resolved":
            query = query.filter(AdminAlert.is_resolved == True)
        
        query = query.order_by(AdminAlert.created_at.desc())
        total = query.count()
        alerts = query.offset((page - 1) * per_page).limit(per_page).all()
        total_pages = (total + per_page - 1) // per_page
        
        # Статистика
        all_alerts = AdminAlert.query.all()
        stats = {
            "critical": len([a for a in all_alerts if a.severity == "critical" and not a.is_resolved]),
            "warning": len([a for a in all_alerts if a.severity == "warning" and not a.is_resolved]),
            "info": len([a for a in all_alerts if a.severity == "info" and not a.is_resolved]),
            "unread": len([a for a in all_alerts if not a.is_read]),
        }
        
        return render_template(
            "admin/crm_alerts.html",
            settings=settings,
            alerts=alerts,
            stats=stats,
            filter_severity=filter_severity,
            filter_status=filter_status,
            page=page,
            total_pages=total_pages,
        )
    
    @app.route("/admin/crm/alert/<int:id>/read", methods=["POST"])
    @admin_required
    def admin_crm_alert_read(id):
        """Позначити алерт прочитаним."""
        from models.company import AdminAlert
        alert = AdminAlert.query.get_or_404(id)
        alert.mark_read()
        
        return jsonify({"success": True})
    
    @app.route("/admin/crm/alert/<int:id>/resolve", methods=["POST"])
    @admin_required
    def admin_crm_alert_resolve(id):
        """Вирішити алерт."""
        from models.company import AdminAlert
        data = request.get_json() or {}
        alert = AdminAlert.query.get_or_404(id)
        
        # Знаходимо поточного адміна (потребує ID)
        alert.is_resolved = True
        alert.resolved_at = datetime.utcnow()
        alert.resolution_note = data.get("note", "")
        db.session.commit()
        
        return jsonify({"success": True})
    
    @app.route("/admin/crm/alerts/mark-all-read", methods=["POST"])
    @admin_required
    def admin_crm_alerts_mark_all_read():
        """Позначити всі алерти прочитаними."""
        from models.company import AdminAlert
        AdminAlert.query.filter_by(is_read=False).update({"is_read": True})
        db.session.commit()
        
        return jsonify({"success": True})
    
    @app.route("/admin/crm/run-daily-check", methods=["POST"])
    @admin_required
    def admin_crm_run_daily_check():
        """Запустити щоденну перевірку всіх партнерів."""
        try:
            from services.partner_verifier import partner_verifier
            from models.company import VerificationLog, AdminAlert
            
            companies = Company.query.filter(
                Company.status.in_(["verified", "pending"])
            ).all()
            
            checked = 0
            alerts_created = 0
            
            for company in companies:
                try:
                    previous_result = company.last_verification_data
                    
                    result = partner_verifier.full_verification(
                        company_name=company.name,
                        vat_number=company.full_vat_number,
                        domain=company.website or company.domain,
                        hr_number=company.handelsregister_id,
                        country_code=company.country_code,
                        city=company.city,
                        previous_result=previous_result,
                    )
                    
                    # Оновлюємо компанію
                    company.reliability_score = result.get("reliability_score", 0)
                    company.reliability_level = result.get("reliability_level", "critical")
                    company.last_verification_at = datetime.utcnow()
                    company.last_verification_data = result
                    
                    if result.get("vat_result", {}).get("valid"):
                        company.vat_verified = True
                        company.vat_data = result["vat_result"]
                    
                    if result.get("whois_result", {}).get("valid"):
                        company.is_whois_verified = True
                        company.whois_data = result["whois_result"]
                    
                    if result.get("hr_result", {}).get("valid"):
                        company.is_hr_verified = True
                        company.hr_data = result["hr_result"]
                    
                    # Логуємо
                    VerificationLog.log_check(
                        company_id=company.id,
                        check_type="daily",
                        status="success",
                        is_valid=result.get("reliability_score", 0) >= 50,
                        response_data=result,
                        changes_detected=len(result.get("changes", [])) > 0,
                    )
                    
                    # Алерти
                    for alert_data in result.get("alerts", []):
                        AdminAlert.create_alert(
                            alert_type=alert_data.get("type"),
                            title=f"{company.name}: {alert_data.get('message', 'Алерт')}",
                            message=alert_data.get("message"),
                            company_id=company.id,
                            severity=alert_data.get("severity", "info"),
                        )
                        alerts_created += 1
                    
                    checked += 1
                    
                except Exception as e:
                    # Логуємо помилку
                    VerificationLog.log_check(
                        company_id=company.id,
                        check_type="daily",
                        status="error",
                        is_valid=False,
                        error_message=str(e),
                    )
            
            db.session.commit()
            
            return jsonify({
                "success": True,
                "checked": checked,
                "alerts": alerts_created,
            })
            
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    # =====================================================================
    # СКЛАД (WAREHOUSE) ROUTES
    # =====================================================================
    
    @app.route("/admin/warehouse")
    @admin_required
    def admin_warehouse():
        """Головна сторінка складу - завдання на відправку."""
        from models.warehouse import WarehouseTask, ShipmentStatus
        
        page = request.args.get("page", 1, type=int)
        status_filter = request.args.get("status", "")
        per_page = 20
        
        query = WarehouseTask.query
        
        if status_filter:
            query = query.filter(WarehouseTask.status == status_filter)
        
        # За замовчуванням показуємо активні завдання
        if not status_filter:
            active_statuses = [
                ShipmentStatus.PENDING.value,
                ShipmentStatus.PROCESSING.value,
                ShipmentStatus.PACKED.value,
                ShipmentStatus.READY.value,
            ]
            query = query.filter(WarehouseTask.status.in_(active_statuses))
        
        query = query.order_by(WarehouseTask.priority.asc(), WarehouseTask.created_at.desc())
        
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        tasks = pagination.items
        
        # Статистика
        stats = {
            "pending": WarehouseTask.query.filter_by(status=ShipmentStatus.PENDING.value).count(),
            "processing": WarehouseTask.query.filter_by(status=ShipmentStatus.PROCESSING.value).count(),
            "packed": WarehouseTask.query.filter_by(status=ShipmentStatus.PACKED.value).count(),
            "shipped_today": WarehouseTask.query.filter(
                WarehouseTask.status == ShipmentStatus.SHIPPED.value,
                db.func.date(WarehouseTask.shipped_at) == db.func.current_date()
            ).count(),
        }
        
        return render_template(
            "admin/warehouse/tasks.html",
            tasks=tasks,
            pagination=pagination,
            stats=stats,
            status_filter=status_filter,
            page=page,
            total_pages=pagination.pages,
        )
    
    @app.route("/admin/warehouse/task/<int:id>", methods=["GET", "POST"])
    @admin_required
    def admin_warehouse_task(id):
        """Деталі завдання складу."""
        from models.warehouse import WarehouseTask, ShipmentStatus
        
        task = WarehouseTask.query.get_or_404(id)
        
        if request.method == "POST":
            action = request.form.get("action")
            
            if action == "start_processing":
                task.status = ShipmentStatus.PROCESSING.value
                task.assigned_to = request.form.get("assigned_to", "")
                db.session.commit()
                flash("✅ Завдання взято в роботу", "success")
                
            elif action == "mark_packed":
                task.mark_packed(
                    weight_kg=request.form.get("weight_kg", type=float),
                    dimensions=request.form.get("dimensions", "")
                )
                flash("📦 Замовлення запаковано", "success")
                
            elif action == "mark_ready":
                task.status = ShipmentStatus.READY.value
                db.session.commit()
                flash("✅ Готово до відправки", "success")
                
            elif action == "mark_shipped":
                task.mark_shipped(
                    tracking_number=request.form.get("tracking_number", ""),
                    carrier=request.form.get("carrier", "")
                )
                flash("🚚 Відправлено!", "success")
                
            elif action == "mark_delivered":
                task.mark_delivered()
                flash("✔️ Доставлено!", "success")
                
            elif action == "cancel":
                task.status = ShipmentStatus.CANCELLED.value
                task.admin_notes = request.form.get("cancel_reason", "")
                db.session.commit()
                flash("❌ Завдання скасовано", "warning")
            
            elif action == "update_notes":
                task.admin_notes = request.form.get("admin_notes", "")
                db.session.commit()
                flash("💾 Нотатки збережено", "success")
            
            return redirect(url_for("admin_warehouse_task", id=id))
        
        return render_template("admin/warehouse/task_detail.html", task=task)
    
    @app.route("/admin/warehouse/stock")
    @admin_required
    def admin_warehouse_stock():
        """Залишки товарів на складі."""
        from models.warehouse import LowStockAlert, StockMovement
        
        page = request.args.get("page", 1, type=int)
        show_low = request.args.get("low", "0") == "1"
        search = request.args.get("search", "")
        per_page = 50
        
        query = Product.query.filter_by(is_active=True)
        
        if show_low:
            query = query.filter(
                Product.stock <= Product.min_stock,
                Product.min_stock > 0
            )
        
        if search:
            query = query.filter(
                db.or_(
                    Product.name.ilike(f"%{search}%"),
                    Product.sku.ilike(f"%{search}%")
                )
            )
        
        query = query.order_by(Product.stock.asc(), Product.name.asc())
        
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        products = pagination.items
        
        # Статистика
        stats = {
            "total_products": Product.query.filter_by(is_active=True).count(),
            "out_of_stock": Product.query.filter_by(is_active=True, stock=0).count(),
            "low_stock": Product.query.filter(
                Product.is_active == True,
                Product.stock > 0,
                Product.stock <= Product.min_stock,
                Product.min_stock > 0
            ).count(),
            "unresolved_alerts": LowStockAlert.query.filter_by(is_resolved=False).count(),
        }
        
        return render_template(
            "admin/warehouse/stock.html",
            products=products,
            pagination=pagination,
            stats=stats,
            show_low=show_low,
            search=search,
            page=page,
            total_pages=pagination.pages,
        )
    
    @app.route("/admin/warehouse/stock/<int:product_id>/adjust", methods=["POST"])
    @admin_required
    def admin_warehouse_stock_adjust(product_id):
        """Коригування залишку товару."""
        from models.warehouse import StockMovement
        
        product = Product.query.get_or_404(product_id)
        
        adjustment = request.form.get("adjustment", 0, type=int)
        reason = request.form.get("reason", "adjustment")
        notes = request.form.get("notes", "")
        
        if adjustment == 0:
            flash("Введіть кількість для коригування", "warning")
            return redirect(url_for("admin_warehouse_stock"))
        
        try:
            StockMovement.record_movement(
                product_id=product_id,
                quantity=adjustment,
                movement_type="adjustment",
                reason=reason,
                notes=notes,
                performed_by="admin",
            )
            flash(f"✅ Залишок '{product.name}' скориговано на {adjustment:+d}", "success")
        except ValueError as e:
            flash(f"❌ Помилка: {str(e)}", "danger")
        
        return redirect(url_for("admin_warehouse_stock"))
    
    @app.route("/admin/warehouse/stock/<int:product_id>/history")
    @admin_required
    def admin_warehouse_stock_history(product_id):
        """Історія руху товару."""
        from models.warehouse import StockMovement
        
        product = Product.query.get_or_404(product_id)
        
        page = request.args.get("page", 1, type=int)
        per_page = 50
        
        query = StockMovement.query.filter_by(product_id=product_id)\
            .order_by(StockMovement.created_at.desc())
        
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        movements = pagination.items
        
        return render_template(
            "admin/warehouse/stock_history.html",
            product=product,
            movements=movements,
            pagination=pagination,
        )
    
    @app.route("/admin/warehouse/replenishment")
    @admin_required
    def admin_warehouse_replenishment():
        """Замовлення на поповнення."""
        from models.warehouse import ReplenishmentOrder, ReplenishmentStatus
        
        page = request.args.get("page", 1, type=int)
        status_filter = request.args.get("status", "")
        per_page = 20
        
        query = ReplenishmentOrder.query
        
        if status_filter:
            query = query.filter(ReplenishmentOrder.status == status_filter)
        
        query = query.order_by(ReplenishmentOrder.created_at.desc())
        
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        orders = pagination.items
        
        # Статистика
        stats = {
            "draft": ReplenishmentOrder.query.filter_by(status=ReplenishmentStatus.DRAFT.value).count(),
            "pending": ReplenishmentOrder.query.filter_by(status=ReplenishmentStatus.PENDING.value).count(),
            "ordered": ReplenishmentOrder.query.filter_by(status=ReplenishmentStatus.ORDERED.value).count(),
            "shipped": ReplenishmentOrder.query.filter_by(status=ReplenishmentStatus.SHIPPED.value).count(),
        }
        
        return render_template(
            "admin/warehouse/replenishment.html",
            orders=orders,
            pagination=pagination,
            stats=stats,
            status_filter=status_filter,
            page=page,
            total_pages=pagination.pages,
        )
    
    @app.route("/admin/warehouse/replenishment/new", methods=["GET", "POST"])
    @admin_required
    def admin_warehouse_replenishment_new():
        """Нове замовлення на поповнення."""
        from models.warehouse import ReplenishmentOrder, ReplenishmentItem, LowStockAlert
        
        if request.method == "POST":
            order = ReplenishmentOrder(
                supplier_name=request.form.get("supplier_name", ""),
                supplier_contact=request.form.get("supplier_contact", ""),
                notes=request.form.get("notes", ""),
                status="draft",
                created_by="admin",
            )
            db.session.add(order)
            db.session.flush()
            order.generate_order_number()
            
            # Додаємо товари
            product_ids = request.form.getlist("product_ids")
            quantities = request.form.getlist("quantities")
            prices = request.form.getlist("prices")
            
            for i, product_id in enumerate(product_ids):
                if product_id:
                    product = Product.query.get(int(product_id))
                    if product:
                        item = ReplenishmentItem(
                            replenishment_id=order.id,
                            product_id=product.id,
                            product_name=product.name,
                            product_sku=product.sku,
                            quantity=int(quantities[i]) if i < len(quantities) and quantities[i] else 1,
                            unit_price=float(prices[i]) if i < len(prices) and prices[i] else 0.0,
                        )
                        db.session.add(item)
            
            order.calculate_totals()
            db.session.commit()
            
            flash(f"✅ Замовлення {order.order_number} створено", "success")
            return redirect(url_for("admin_warehouse_replenishment_detail", id=order.id))
        
        # Товари з низьким залишком для пропозиції
        low_stock_products = Product.query.filter(
            Product.is_active == True,
            Product.stock <= Product.min_stock,
            Product.min_stock > 0
        ).all()
        
        return render_template(
            "admin/warehouse/replenishment_new.html",
            low_stock_products=low_stock_products,
            products=Product.query.filter_by(is_active=True).order_by(Product.name).all(),
        )
    
    @app.route("/admin/warehouse/replenishment/<int:id>", methods=["GET", "POST"])
    @admin_required
    def admin_warehouse_replenishment_detail(id):
        """Деталі замовлення на поповнення."""
        from models.warehouse import ReplenishmentOrder, ReplenishmentStatus
        
        order = ReplenishmentOrder.query.get_or_404(id)
        
        if request.method == "POST":
            action = request.form.get("action")
            
            if action == "approve":
                order.status = ReplenishmentStatus.APPROVED.value
                db.session.commit()
                flash("✅ Замовлення підтверджено", "success")
                
            elif action == "order":
                order.status = ReplenishmentStatus.ORDERED.value
                order.ordered_at = datetime.utcnow()
                db.session.commit()
                flash("📤 Замовлено у постачальника", "success")
                
            elif action == "shipped":
                order.status = ReplenishmentStatus.SHIPPED.value
                order.expected_at = datetime.utcnow()  # TODO: real expected date
                db.session.commit()
                flash("🚚 Позначено як відправлено", "success")
                
            elif action == "receive":
                order.mark_received()
                flash("✔️ Товар отримано, залишки оновлено!", "success")
                
            elif action == "cancel":
                order.status = ReplenishmentStatus.CANCELLED.value
                db.session.commit()
                flash("❌ Замовлення скасовано", "warning")
            
            elif action == "mark_paid":
                order.is_paid = True
                order.paid_at = datetime.utcnow()
                order.payment_method = request.form.get("payment_method", "")
                db.session.commit()
                flash("💰 Оплату зафіксовано", "success")
            
            return redirect(url_for("admin_warehouse_replenishment_detail", id=id))
        
        return render_template("admin/warehouse/replenishment_detail.html", order=order)
    
    @app.route("/admin/warehouse/expenses")
    @admin_required
    def admin_warehouse_expenses():
        """Витрати складу."""
        from models.warehouse import WarehouseExpense, ExpenseCategory
        
        page = request.args.get("page", 1, type=int)
        category_filter = request.args.get("category", "")
        date_from = request.args.get("date_from", "")
        date_to = request.args.get("date_to", "")
        per_page = 50
        
        query = WarehouseExpense.query
        
        if category_filter:
            query = query.filter(WarehouseExpense.category == category_filter)
        
        if date_from:
            query = query.filter(WarehouseExpense.expense_date >= date_from)
        
        if date_to:
            query = query.filter(WarehouseExpense.expense_date <= date_to)
        
        query = query.order_by(WarehouseExpense.expense_date.desc())
        
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        expenses = pagination.items
        
        # Статистика за місяць
        from datetime import date
        today = date.today()
        first_day = today.replace(day=1)
        
        monthly_stats = db.session.query(
            WarehouseExpense.category,
            db.func.sum(WarehouseExpense.amount)
        ).filter(
            WarehouseExpense.expense_date >= first_day
        ).group_by(WarehouseExpense.category).all()
        
        stats_by_category = {cat: amt for cat, amt in monthly_stats}
        total_monthly = sum(stats_by_category.values())
        
        return render_template(
            "admin/warehouse/expenses.html",
            expenses=expenses,
            pagination=pagination,
            stats_by_category=stats_by_category,
            total_monthly=total_monthly,
            category_filter=category_filter,
            date_from=date_from,
            date_to=date_to,
            page=page,
            total_pages=pagination.pages,
            expense_categories=ExpenseCategory,
        )
    
    @app.route("/admin/warehouse/expenses/add", methods=["GET", "POST"])
    @admin_required
    def admin_warehouse_expenses_add():
        """Додати витрату."""
        from models.warehouse import WarehouseExpense, ExpenseCategory
        from datetime import date
        
        if request.method == "POST":
            expense = WarehouseExpense(
                category=request.form.get("category", ExpenseCategory.OTHER.value),
                description=request.form.get("description", ""),
                amount=request.form.get("amount", 0, type=float),
                currency=request.form.get("currency", "UAH"),
                receipt_number=request.form.get("receipt_number", "") or None,
                notes=request.form.get("notes", "") or None,
                expense_date=date.fromisoformat(request.form.get("expense_date", str(date.today()))),
                created_by="admin",
            )
            db.session.add(expense)
            db.session.commit()
            
            flash("✅ Витрату додано", "success")
            return redirect(url_for("admin_warehouse_expenses"))
        
        return render_template(
            "admin/warehouse/expense_add.html",
            expense_categories=ExpenseCategory,
            today=date.today(),
        )
    
    @app.route("/admin/warehouse/reports")
    @admin_required
    def admin_warehouse_reports():
        """Звіти складу."""
        from models.warehouse import WarehouseTask, ReplenishmentOrder, WarehouseExpense, StockMovement
        from datetime import date, timedelta
        
        # Період
        period = request.args.get("period", "month")
        today = date.today()
        
        if period == "week":
            start_date = today - timedelta(days=7)
        elif period == "month":
            start_date = today.replace(day=1)
        elif period == "quarter":
            quarter_start = (today.month - 1) // 3 * 3 + 1
            start_date = today.replace(month=quarter_start, day=1)
        else:  # year
            start_date = today.replace(month=1, day=1)
        
        # Відправки
        shipments = {
            "total": WarehouseTask.query.filter(WarehouseTask.created_at >= start_date).count(),
            "shipped": WarehouseTask.query.filter(
                WarehouseTask.shipped_at >= start_date,
                WarehouseTask.shipped_at.isnot(None)
            ).count(),
            "delivered": WarehouseTask.query.filter(
                WarehouseTask.delivered_at >= start_date,
                WarehouseTask.delivered_at.isnot(None)
            ).count(),
        }
        
        # Поповнення
        replenishments = {
            "total": ReplenishmentOrder.query.filter(ReplenishmentOrder.created_at >= start_date).count(),
            "received": ReplenishmentOrder.query.filter(
                ReplenishmentOrder.received_at >= start_date,
                ReplenishmentOrder.received_at.isnot(None)
            ).count(),
            "total_cost": db.session.query(db.func.sum(ReplenishmentOrder.total)).filter(
                ReplenishmentOrder.received_at >= start_date,
                ReplenishmentOrder.received_at.isnot(None)
            ).scalar() or 0,
        }
        
        # Витрати
        expenses = {
            "total": db.session.query(db.func.sum(WarehouseExpense.amount)).filter(
                WarehouseExpense.expense_date >= start_date
            ).scalar() or 0,
        }
        
        # По категоріях
        expense_by_category = db.session.query(
            WarehouseExpense.category,
            db.func.sum(WarehouseExpense.amount)
        ).filter(
            WarehouseExpense.expense_date >= start_date
        ).group_by(WarehouseExpense.category).all()
        
        return render_template(
            "admin/warehouse/reports.html",
            period=period,
            start_date=start_date,
            shipments=shipments,
            replenishments=replenishments,
            expenses=expenses,
            expense_by_category=dict(expense_by_category),
        )
    
    # Автоматичне створення завдання після оплати
    @app.route("/webhook/payment-success", methods=["POST"])
    def webhook_payment_success():
        """Webhook для обробки успішної оплати - створює завдання для складу."""
        from models.warehouse import WarehouseTask
        
        data = request.get_json()
        order_id = data.get("order_id")
        
        if not order_id:
            return jsonify({"error": "order_id required"}), 400
        
        order = Order.query.get(order_id)
        if not order:
            return jsonify({"error": "order not found"}), 404
        
        # Перевіряємо чи не існує вже завдання
        existing_task = WarehouseTask.query.filter_by(order_id=order_id).first()
        if existing_task:
            return jsonify({"message": "task already exists", "task_id": existing_task.id})
        
        # Створюємо завдання
        task = WarehouseTask.create_from_order(
            order_id=order_id,
            priority=2 if order.is_b2b else 3,  # B2B - вищий пріоритет
            notes=order.notes,
        )
        
        return jsonify({"success": True, "task_id": task.id, "task_number": task.task_number})

    # Ініціалізація БД при старті
    init_db()
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="127.0.0.1", port=5000, debug=True)
