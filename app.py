
import sys

# Windows-консоль за замовчуванням використовує cp1251/cp866, що не підтримує
# emoji (⚠️, 📁 тощо), які використовуються в print()/logger по всьому коду.
# Без цього процес падає з UnicodeEncodeError ще до старту Flask.
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

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
    g,
    Response,
)
from flask_login import login_required, current_user
from flask_babel import Babel, gettext as _, lazy_gettext as _l, get_locale

# Опціональні залежності
try:
    import stripe
    STRIPE_AVAILABLE = True
except ImportError:
    STRIPE_AVAILABLE = False

try:
    from openai import OpenAI
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    openai = None

# Cloudinary для зберігання зображень
try:
    import cloudinary
    import cloudinary.uploader
    import cloudinary.api
    CLOUDINARY_AVAILABLE = True
except ImportError:
    CLOUDINARY_AVAILABLE = False

# Ініціалізація SQLAlchemy та Flask-Login - імпортуємо з extensions для уникнення дублювання
from extensions import db, login_manager, migrate, csrf, limiter


def create_app():
    """
    Фабрика Flask-додатку SmartShop AI.
    Запускає сайт-магазин з адмінкою, товарами та базовою статистикою.
    """
    app = Flask(__name__)

    # Базові налаштування
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")

    # Сесійна кука має діяти на всіх піддоменах платформи (<slug>.BASE_DOMAIN),
    # інакше логін власника магазину, зроблений на голому BASE_DOMAIN (напр.
    # одразу після Stripe checkout), не переноситься на власний піддомен
    # магазину - адмінка вимагає повторного входу або (гірше) g.store
    # резолвиться у чужий фолбек-магазин голого домену.
    # Примітка: тільки для реального BASE_DOMAIN (напр. shop.andrii-it.de) -
    # такий кук-домен потребує щонайменше однієї крапки. Спроба зробити те
    # саме для "localhost" (Domain=.localhost) не працює - браузери й curl
    # відмовляються ділити куку по піддоменах для однослівного хосту без
    # крапок (захист від supercookie-атак), тому локальна розробка без
    # BASE_DOMAIN не може відтворити цю крос-піддоменну поведінку - для
    # цього є справжній сервер.
    _base_domain_for_cookie = os.environ.get("BASE_DOMAIN", "").lower().strip().strip(".")
    if _base_domain_for_cookie:
        app.config["SESSION_COOKIE_DOMAIN"] = f".{_base_domain_for_cookie}"

    # Налаштування логування та моніторингу (критично для production)
    from config.logging_config import setup_logging, setup_sentry, log_request, log_exceptions
    setup_logging(app)
    setup_sentry(app)
    log_request(app)
    log_exceptions(app)
    
    app.logger.info('SmartShop AI application starting...', extra={
        'environment': os.environ.get('FLASK_ENV', 'production'),
        'python_version': os.sys.version
    })
    
    # Ініціалізація email сервісу
    from services.email_service import init_mail
    init_mail(app)
    
    # Security Headers Middleware
    @app.after_request
    def set_security_headers(response):
        """Add comprehensive security headers to all responses"""
        # HSTS - Force HTTPS for 1 year, including subdomains
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
        
        # Prevent MIME sniffing
        response.headers['X-Content-Type-Options'] = 'nosniff'
        
        # Clickjacking protection
        response.headers['X-Frame-Options'] = 'DENY'
        
        # XSS Protection (legacy but still useful)
        response.headers['X-XSS-Protection'] = '1; mode=block'
        
        # Content Security Policy - XSS protection
        csp_policy = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://js.stripe.com https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
            "img-src 'self' data: https: blob:; "
            "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net; "
            "connect-src 'self' https://api.openai.com https://api.stripe.com; "
            "frame-src https://js.stripe.com https://hooks.stripe.com; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self' https://checkout.stripe.com; "
            "upgrade-insecure-requests;"
        )
        response.headers['Content-Security-Policy'] = csp_policy
        
        # Referrer Policy - Control referrer information
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        # Permissions Policy (formerly Feature Policy)
        response.headers['Permissions-Policy'] = (
            "geolocation=(), microphone=(), camera=(), payment=(self)"
        )
        
        # Hide server information
        response.headers['Server'] = 'SmartShop'
        if 'X-Powered-By' in response.headers:
            del response.headers['X-Powered-By']
        
        return response
    
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
    openai_client = None  # Will be initialized lazily

    def get_openai_client():
        """Lazy initialization of OpenAI client with custom httpx client (no proxy)."""
        nonlocal openai_client
        if openai_client is None and OPENAI_AVAILABLE and app.config["OPENAI_API_KEY"]:
            print("🔧 [BUILD 57e7f39] Initializing OpenAI with custom httpx client (no proxy)...")
            try:
                # Create custom httpx client with NO proxy support
                # This prevents OpenAI SDK from trying to use HTTP_PROXY env var
                import httpx
                
                # Create httpx client that explicitly ignores proxy
                custom_http_client = httpx.Client(
                    timeout=60.0,
                    limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
                    # Don't pass proxy at all - let it default to None
                )
                
                # Create OpenAI client with custom http_client
                openai_client = OpenAI(
                    api_key=app.config["OPENAI_API_KEY"],
                    http_client=custom_http_client
                )
                
                sdk_version = getattr(openai, '__version__', 'unknown')
                print(f"✅ OpenAI client initialized successfully with custom httpx client (SDK version: {sdk_version})")
                        
            except Exception as e:
                print(f"❌ Failed to initialize OpenAI client: {type(e).__name__}: {e}")
                import traceback
                print(f"Traceback: {traceback.format_exc()}")
                sdk_version = getattr(openai, '__version__', 'unknown')
                print(f"OpenAI SDK version: {sdk_version}")
                openai_client = None
        return openai_client

    # Cloudinary налаштування для постійного зберігання зображень
    app.config["CLOUDINARY_CLOUD_NAME"] = os.environ.get("CLOUDINARY_CLOUD_NAME", "")
    app.config["CLOUDINARY_API_KEY"] = os.environ.get("CLOUDINARY_API_KEY", "")
    app.config["CLOUDINARY_API_SECRET"] = os.environ.get("CLOUDINARY_API_SECRET", "")
    app.config["IMAGE_STORAGE"] = os.environ.get("IMAGE_STORAGE", "database")  # 'cloudinary', 'database', or 'local'
    
    if CLOUDINARY_AVAILABLE and app.config["IMAGE_STORAGE"] == "cloudinary":
        if all([app.config["CLOUDINARY_CLOUD_NAME"], 
                app.config["CLOUDINARY_API_KEY"], 
                app.config["CLOUDINARY_API_SECRET"]]):
            cloudinary.config(
                cloud_name=app.config["CLOUDINARY_CLOUD_NAME"],
                api_key=app.config["CLOUDINARY_API_KEY"],
                api_secret=app.config["CLOUDINARY_API_SECRET"],
                secure=True
            )
            print("✅ Cloudinary configured for image storage")
        else:
            print("⚠️ Cloudinary credentials missing, falling back to database storage")
            app.config["IMAGE_STORAGE"] = "database"
    elif app.config["IMAGE_STORAGE"] == "database":
        print("💾 Using PostgreSQL database for permanent image storage")
    else:
        print("📁 Using local storage for images (will be lost on Render redeployment)")

    # Налаштування для завантаження файлів з додатковою безпекою
    UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    ALLOWED_MIME_TYPES = {
        'image/png',
        'image/jpeg',
        'image/gif',
        'image/webp'
    }
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max
    
    # Створюємо папку uploads якщо не існує
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    
    def allowed_file(filename, content_type=None):
        """Validate file extension and optionally MIME type"""
        if not filename or '.' not in filename:
            return False
        
        # Secure the filename
        filename = secure_filename(filename)
        
        # Check extension
        ext = filename.rsplit('.', 1)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            return False
        
        # Check MIME type if provided
        if content_type and content_type not in ALLOWED_MIME_TYPES:
            return False
        
        return True

    # Flask-Babel налаштування для мультимовності
    app.config['BABEL_DEFAULT_LOCALE'] = 'uk'
    app.config['BABEL_SUPPORTED_LOCALES'] = ['uk', 'en', 'de']
    app.config['LANGUAGES'] = {
        'uk': '🇺🇦 Українська',
        'en': '🇬🇧 English',
        'de': '🇩🇪 Deutsch'
    }
    
    babel = Babel()
    
    def get_locale_selector():
        # 1. Перевіряємо параметр URL
        lang = request.args.get('lang')
        if lang in app.config['BABEL_SUPPORTED_LOCALES']:
            session['lang'] = lang
            return lang
        # 2. Перевіряємо сесію
        if 'lang' in session:
            return session['lang']
        # 3. Автоматичне визначення з браузера
        return request.accept_languages.best_match(app.config['BABEL_SUPPORTED_LOCALES'])
    
    babel.init_app(app, locale_selector=get_locale_selector)
    
    # Робимо функції доступними в шаблонах
    @app.context_processor
    def inject_locale():
        return {
            'get_locale': get_locale,
            'languages': app.config['LANGUAGES'],
        }

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)

    # Ініціалізація Flask-Login
    login_manager.init_app(app)
    # ВАЖЛИВО: "user_login" (маршрут /login у цьому файлі), а НЕ застаріле
    # "auth.login" (routes/auth.py) - той дублюючий маршрут не передає
    # `settings` у шаблон і не має повної логіки редіректу за роллю
    # (platform_owner/b2b), тому будь-який @login_required-редірект
    # (наприклад, анонімний візит на /cabinet) через нього падав з
    # UndefinedError: 'settings' is undefined.
    login_manager.login_view = "user_login"
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
    from models.blog import BlogPost, BlogPlan, AISettings, BlogPostStatus
    from models.store import Store

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
    # Blog
    app.BlogPost = BlogPost
    app.BlogPlan = BlogPlan
    app.AISettings = AISettings
    app.WarehouseExpense = WarehouseExpense
    app.LowStockAlert = LowStockAlert
    app.Store = Store

    # ----- MULTI-TENANCY: РЕЗОЛЮЦІЯ ПОТОЧНОГО МАГАЗИНУ (g.store) -----
    # SaaS-режим: кожен магазин (Store) відповідає за свій піддомен
    # <slug>.<BASE_DOMAIN>. Поки BASE_DOMAIN не налаштований (або запит прийшов
    # без піддомену - як зараз на проді без wildcard DNS) - використовується
    # перший/дефолтний Store, щоб існуючий однотенантний деплой не зламався.
    BASE_DOMAIN = os.environ.get("BASE_DOMAIN", "").lower().strip().strip(".")
    RESERVED_SUBDOMAINS = {"www", "api", "admin", "app"}
    # Шляхи, доступні навіть якщо жодного Store ще не існує в БД (порожня
    # інсталяція до першої реєстрації) - реєстрація, статика, healthcheck,
    # перемикач мови (глобальна утиліта, що лише пише сесію і не читає g.store).
    STORE_OPTIONAL_PATH_PREFIXES = ("/signup", "/static", "/webhook", "/health", "/set-language")

    def resolve_current_store():
        """Визначає поточний Store за піддоменом запиту (або дефолтний, якщо
        піддомену немає/BASE_DOMAIN не налаштований).

        Повертає (store, is_platform_root): is_platform_root=True означає,
        що запит прийшов БЕЗ розпізнаного піддомену конкретного магазину
        (голий домен платформи, або поки BASE_DOMAIN/wildcard DNS ще не
        налаштовано) - в такому разі "/" має показувати маркетинговий
        лендинг платформи, а не вітрину дефолтного магазину."""
        host = (request.host or "").split(":")[0].lower()
        subdomain = None

        if BASE_DOMAIN and host.endswith("." + BASE_DOMAIN):
            subdomain = host[: -(len(BASE_DOMAIN) + 1)]
            if "." in subdomain:
                subdomain = subdomain.split(".")[0]
        elif host.endswith(".localhost"):
            subdomain = host[: -len(".localhost")]

        store = None
        if subdomain and subdomain not in RESERVED_SUBDOMAINS:
            store = Store.get_by_slug(subdomain)

        if store is None:
            # Не піддомен платформи - можливо, це підтверджений власний домен
            # клієнта (напр. myshop.com), підключений через /admin/settings/domain.
            store = Store.get_by_custom_domain(host)

        is_platform_root = store is None
        if store is None:
            # Немає piддомену (або магазин не знайдено) - дефолтний магазин
            # (Store #1, тобто той, що існував до впровадження multi-tenancy).
            store = Store.query.filter_by(is_deleted=False).order_by(Store.id.asc()).first()

        return store, is_platform_root

    @app.before_request
    def load_current_store():
        g.store, g.is_platform_root = resolve_current_store()
        if g.store is None:
            # Немає жодного активного Store в базі (наприклад, єдиний магазин
            # видалено). Маркетинговий лендинг платформи ("/") і службові
            # шляхи мають лишатись доступними — інакше платформа стає
            # непридатною для нової реєстрації, щойно останній магазин зникає.
            path_is_store_optional = request.path == "/" or request.path.startswith(STORE_OPTIONAL_PATH_PREFIXES)
            if not path_is_store_optional:
                abort(404, description="Магазин не знайдено. Можливо, платформа ще не налаштована — почніть з /signup.")
        if (
            g.store is not None
            and not g.store.is_active
            and not g.is_platform_root
            and not request.path.startswith(("/platform-admin", "/static"))
        ):
            abort(503, description="Цей магазин тимчасово заблоковано адміністрацією платформи.")

    # ----- СЛУЖБОВІ ФУНКЦІЇ -----

    def init_db():
        """Створити схему, таблиці й дефолтні налаштування, якщо їх ще немає."""
        with app.app_context():
            # Імпортуємо всі моделі перед створенням таблиць
            from models.product import Image, Category, Product
            from models.user import User
            from models.blog import BlogPost
            from models.order import Order
            
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
            
            if app.config["IMAGE_STORAGE"] == "database":
                from models.product import Image
                try:
                    image_count = Image.query.count()
                    print(f"✅ Таблиця 'images' готова для зберігання зображень (зараз: {image_count} зображень)")
                except Exception:
                    db.session.rollback()  # схема ще не мігрована (store_id відсутній) - пропускаємо діагностику
            
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
                    # Мультимовність
                    ('name_en', 'VARCHAR(120)'),
                    ('name_de', 'VARCHAR(120)'),
                    ('description_en', 'TEXT'),
                    ('description_de', 'TEXT'),
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
                    # Мультимовність
                    ('name_en', 'VARCHAR(200)'),
                    ('name_de', 'VARCHAR(200)'),
                    ('short_description_en', 'VARCHAR(255)'),
                    ('short_description_de', 'VARCHAR(255)'),
                    ('long_description_en', 'TEXT'),
                    ('long_description_de', 'TEXT'),
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
                    ('customer_name', 'VARCHAR(200)'),
                    ('customer_phone', 'VARCHAR(50)'),
                    ('customer_email', 'VARCHAR(200)'),
                    ('shipping_address', 'TEXT'),
                    ('shipping_method', 'VARCHAR(100)'),
                    ('is_b2b', 'BOOLEAN DEFAULT FALSE'),
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
                
                # blog_posts колонки
                blog_post_columns = [
                    ('title', 'VARCHAR(255)'),
                    ('slug', 'VARCHAR(255)'),
                    ('excerpt', 'VARCHAR(500)'),
                    ('content', 'TEXT'),
                    ('featured_image', 'VARCHAR(500)'),
                    ('meta_title', 'VARCHAR(100)'),
                    ('meta_description', 'VARCHAR(200)'),
                    ('meta_keywords', 'VARCHAR(255)'),
                    ('tags', 'VARCHAR(255)'),
                    ('category', 'VARCHAR(100)'),
                    ('status', "VARCHAR(20) DEFAULT 'draft'"),
                    ('publish_date', 'TIMESTAMP'),
                    ('is_ai_generated', 'BOOLEAN DEFAULT FALSE'),
                    ('ai_topic', 'VARCHAR(255)'),
                    ('blog_plan_id', 'INTEGER'),
                    ('author', "VARCHAR(100) DEFAULT 'AI'"),
                    ('views', 'INTEGER DEFAULT 0'),
                    ('created_at', 'TIMESTAMP DEFAULT NOW()'),
                    ('updated_at', 'TIMESTAMP DEFAULT NOW()'),
                    # Мультимовність
                    ('title_en', 'VARCHAR(255)'),
                    ('title_de', 'VARCHAR(255)'),
                    ('excerpt_en', 'VARCHAR(500)'),
                    ('excerpt_de', 'VARCHAR(500)'),
                    ('content_en', 'TEXT'),
                    ('content_de', 'TEXT'),
                ]
                
                # blog_plans колонки
                blog_plan_columns = [
                    ('plan_date', 'DATE'),
                    ('topic', 'VARCHAR(255)'),
                    ('keywords', 'VARCHAR(255)'),
                    ('status', "VARCHAR(20) DEFAULT 'pending'"),
                    ('blog_post_id', 'INTEGER'),
                    ('additional_instructions', 'TEXT'),
                    ('target_audience', 'VARCHAR(255)'),
                    ('created_at', 'TIMESTAMP DEFAULT NOW()'),
                ]
                
                # ai_settings колонки
                ai_settings_columns = [
                    ('chatbot_enabled', 'BOOLEAN DEFAULT TRUE'),
                    ('chatbot_name', "VARCHAR(100) DEFAULT 'ІІ-продавець'"),
                    ('chatbot_system_prompt', 'TEXT'),
                    ('chatbot_custom_instructions', 'TEXT'),
                    ('chatbot_tone', "VARCHAR(50) DEFAULT 'friendly'"),
                    ('chatbot_max_tokens', 'INTEGER DEFAULT 500'),
                    ('chatbot_temperature', 'FLOAT DEFAULT 0.7'),
                    ('chatbot_forbidden_topics', 'TEXT'),
                    ('blogger_enabled', 'BOOLEAN DEFAULT TRUE'),
                    ('blogger_name', "VARCHAR(100) DEFAULT 'AI Блогер'"),
                    ('blogger_style', "VARCHAR(50) DEFAULT 'informative'"),
                    ('blogger_language', "VARCHAR(10) DEFAULT 'uk'"),
                    ('blogger_default_keywords', 'TEXT'),
                    ('blogger_seo_instructions', 'TEXT'),
                    ('blogger_article_structure', 'TEXT'),
                    ('blogger_min_words', 'INTEGER DEFAULT 500'),
                    ('blogger_max_words', 'INTEGER DEFAULT 1500'),
                    ('auto_publish', 'BOOLEAN DEFAULT FALSE'),
                    ('publish_time', "VARCHAR(5) DEFAULT '10:00'"),
                    ('generate_images', 'BOOLEAN DEFAULT TRUE'),
                    ('image_style', "VARCHAR(100) DEFAULT 'professional photography, realistic, high quality'"),
                    ('auto_translate', 'BOOLEAN DEFAULT TRUE'),
                    ('auto_translate_languages', "VARCHAR(50) DEFAULT 'en,de'"),
                    ('created_at', 'TIMESTAMP DEFAULT NOW()'),
                    ('updated_at', 'TIMESTAMP DEFAULT NOW()'),
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
                    # Blog
                    ('blog_posts', blog_post_columns),
                    ('blog_plans', blog_plan_columns),
                    ('ai_settings', ai_settings_columns),
                ]
                
                with db.engine.connect() as conn:
                    for table_name, columns in migrations:
                        for col_name, col_type in columns:
                            try:
                                conn.execute(text(f"ALTER TABLE {db_schema}.{table_name} ADD COLUMN IF NOT EXISTS {col_name} {col_type}"))
                            except Exception as e:
                                pass
                    conn.commit()
                
                # Перевіряємо стан зображень після міграцій
                from models.product import Image
                try:
                    image_count = Image.query.count()
                    print(f"✅ Міграції застосовані (images в БД: {image_count})")
                except Exception:
                    db.session.rollback()  # схема ще не мігрована (store_id відсутній) - пропускаємо діагностику
            
            # ----- MULTI-TENANCY BOOTSTRAP -----
            # init_db() виконується поза HTTP-запитом (при старті процесу), тому
            # g.store тут недоступний (before_request ще не відпрацював). Замість
            # цього тут гарантуємо існування дефолтного Store (для зворотної
            # сумісності з однотенантним режимом, що існував до multi-tenancy) і
            # заповнюємо store_id=NULL у вже існуючих рядках (перехід зі старої
            # схеми).
            #
            # ВАЖЛИВО: на існуючій (доміграційній) базі таблиці "stores" і
            # колонок "store_id" ще не існує в момент цього виклику - вони
            # з'являються лише після `flask db upgrade`. Але `flask db upgrade`
            # сам імпортує app.py, а це викликає init_db() ще ДО того, як
            # міграція встигла застосуватися. Тому весь цей блок обгорнутий у
            # try/except: якщо схема ще стара - тихо пропускаємо бутстрап
            # (наступний запуск процесу, вже після міграції, довиконає його).
            try:
                from models.store import Store, StoreSubscriptionStatus

                # is_deleted=False - інакше м'яко видалений старий Store (напр.
                # після self-service видалення акаунту) назавжди "займає" роль
                # бутстрап-магазину для будь-якого наступного запуску процесу,
                # заважаючи реальному новому магазину коли-небудь стати ним.
                default_store = Store.query.filter_by(is_deleted=False).order_by(Store.id.asc()).first()
                created_new_default_store = False
                if default_store is None:
                    owner = (
                        User.query.filter_by(role=UserRole.STORE_OWNER.value).first()
                        or User.query.filter_by(role=UserRole.ADMIN.value).first()
                    )
                    bootstrap_email = os.environ.get("ADMIN_USERNAME", "admin")
                    if "@" not in bootstrap_email:
                        bootstrap_email = f"{bootstrap_email}@smartshop.local"
                    if owner is None:
                        owner = User.get_by_email(bootstrap_email)
                    if owner is None:
                        owner = User(
                            email=bootstrap_email,
                            role=UserRole.STORE_OWNER.value,
                            first_name="Admin",
                            is_verified=True,
                        )
                        owner.set_password(os.environ.get("ADMIN_PASSWORD", "admin123"))
                        db.session.add(owner)
                        db.session.flush()
                    else:
                        owner.role = UserRole.STORE_OWNER.value

                    # Використовуємо назву з існуючих (дотенантних) site_settings, якщо є
                    legacy_settings = SiteSettings.query.filter_by(store_id=None).first()
                    default_store_name = (
                        os.environ.get("DEFAULT_STORE_NAME")
                        or (legacy_settings.site_name if legacy_settings else None)
                        or "SmartShop Demo"
                    )

                    default_store = Store(
                        name=default_store_name,
                        slug=os.environ.get("DEFAULT_STORE_SLUG", "default"),
                        owner_user_id=owner.id,
                        plan="starter",
                        subscription_status=StoreSubscriptionStatus.ACTIVE,
                    )
                    db.session.add(default_store)
                    db.session.flush()
                    db.session.commit()
                    created_new_default_store = True
                    print(f"✅ Створено дефолтний Store #{default_store.id} ('{default_store.slug}')")

                DEFAULT_STORE_ID = default_store.id

                # Заповнюємо store_id=NULL для рядків, що існували до multi-tenancy
                from models.company import VerificationLog, AdminAlert
                for model_cls in (
                    Category, Product, Order, OrderItem, BlogPost, BlogPlan,
                    SiteSettings, ContactMessage, Image, AISettings,
                    Company, VerificationLog, AdminAlert,
                    WarehouseTask, StockMovement, ReplenishmentOrder,
                    ReplenishmentItem, WarehouseExpense, LowStockAlert,
                ):
                    try:
                        model_cls.query.filter(model_cls.store_id.is_(None)).update(
                            {"store_id": DEFAULT_STORE_ID}, synchronize_session=False
                        )
                    except Exception:
                        pass
                db.session.commit()

                # Тепер безпечно працювати з моделями
                SiteSettings.get_or_create(DEFAULT_STORE_ID)

                # Тестові демо-товари створюємо ЛИШЕ одразу після створення
                # нового бутстрап-магазину (перший запуск на порожній БД) - а
                # НЕ будь-коли, коли у "першого по ID" магазину раптом 0
                # категорій. Інакше будь-який реальний клієнтський магазин, що
                # просто ще не додав жодного товару, ризикує отримати чужі
                # демо-товари (iPhone/MacBook/...) при наступному старті
                # процесу - це реально стався один раз через діагностичний
                # запуск, що випадково "усиновив" такий магазин як бутстрап.
                if created_new_default_store and Category.query.filter_by(store_id=DEFAULT_STORE_ID).count() == 0:
                    # Тестова категорія
                    test_category = Category(
                        store_id=DEFAULT_STORE_ID,
                        name="Електроніка",
                        slug="electronics",
                        description="Смартфони, ноутбуки, планшети та інша техніка"
                    )
                    db.session.add(test_category)
                    db.session.flush()  # Отримуємо ID категорії

                    # Тестовий товар
                    test_product = Product(
                        store_id=DEFAULT_STORE_ID,
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
                            store_id=DEFAULT_STORE_ID,
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
            except Exception as e:
                db.session.rollback()
                print(f"⚠️ Multi-tenancy bootstrap: схема ще не мігрована ({e}), пропускаю (застосується після flask db upgrade)")
            
            # Автопублікація scheduled постів блогу
            try:
                from models.blog import BlogPost, BlogPostStatus
                scheduled_posts = BlogPost.query.filter(
                    BlogPost.status == BlogPostStatus.SCHEDULED,
                    BlogPost.publish_date <= datetime.utcnow()
                ).all()
                
                if scheduled_posts:
                    for post in scheduled_posts:
                        post.status = BlogPostStatus.PUBLISHED
                        print(f"📰 Автопублікація: {post.title}")
                    db.session.commit()
                    print(f"✅ Опубліковано {len(scheduled_posts)} заплановані статті")
            except Exception as e:
                print(f"⚠️ Помилка автопублікації: {e}")

    # DEMO MODE: Авторизація вимкнена для демонстрації
    DEMO_MODE = os.environ.get("DEMO_MODE", "true").lower() == "true"
    print(f"🔧 DEMO_MODE = {DEMO_MODE}")

    def is_admin_logged_in() -> bool:
        """
        Legacy-назва збережена для сумісності з рештою коду, що її викликає.
        Тепер означає: залогінений через Flask-Login користувач, який керує
        поточним g.store (власник або staff), а не булевий session-прапорець.
        """
        if DEMO_MODE:
            return True  # В демо-режимі завжди авторизовано
        return current_user.is_authenticated and current_user.can_manage_store(g.get("store"))

    def admin_required(fn):
        """Декоратор для захисту адмін-маршрутів поточного магазину (g.store)."""
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if DEMO_MODE:
                return fn(*args, **kwargs)  # В демо-режимі пропускаємо перевірку
            if not current_user.is_authenticated:
                flash(_("Потрібен вхід в адмін-панель."), "warning")
                return redirect(url_for("user_login", next=request.path))
            if not current_user.can_manage_store(g.get("store")):
                abort(403)
            return fn(*args, **kwargs)
        return wrapper

    # ----- РЕЄСТРАЦІЯ BLUEPRINTS -----
    from routes.auth import auth_bp
    from routes.cabinet import cabinet_bp
    from routes.signup import signup_bp
    from routes.platform_admin import platform_admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(cabinet_bp)
    app.register_blueprint(signup_bp)
    app.register_blueprint(platform_admin_bp)

    # ----- ПЕРЕКЛЮЧЕННЯ МОВИ -----

    @app.route("/set-language/<lang>")
    def set_language(lang):
        """Змінити мову інтерфейсу."""
        if lang in app.config['BABEL_SUPPORTED_LOCALES']:
            session['lang'] = lang
        # Повернути на попередню сторінку
        return redirect(request.referrer or url_for('index'))

    # ----- ПУБЛІЧНІ СТОРІНКИ -----

    @app.route("/")
    def index():
        if g.is_platform_root:
            return render_template("pages/landing.html")

        settings = SiteSettings.get_or_create(g.store.id)
        products = Product.query.filter_by(is_active=True, store_id=g.store.id).limit(8).all()
        categories = Category.query.filter_by(store_id=g.store.id).all()

        total_products = Product.query.filter_by(store_id=g.store.id).count()
        total_orders = Order.query.filter_by(store_id=g.store.id).count()
        total_revenue = (
            db.session.query(db.func.coalesce(db.func.sum(Order.amount), 0.0))
            .filter(Order.status == "paid", Order.store_id == g.store.id)
            .scalar()
        )

        # Останні пости блогу для головної
        blog_posts = BlogPost.query.filter(
            BlogPost.store_id == g.store.id,
            BlogPost.status == BlogPostStatus.PUBLISHED,
            db.or_(
                BlogPost.publish_date.is_(None),
                BlogPost.publish_date <= datetime.utcnow()
            )
        ).order_by(BlogPost.publish_date.desc()).limit(3).all()

        return render_template(
            "index.html",
            settings=settings,
            products=products,
            categories=categories,
            total_products=total_products,
            total_orders=total_orders,
            total_revenue=total_revenue,
            blog_posts=blog_posts,
        )

    # ----- ПУБЛІЧНІ: СТАТИЧНІ СТОРІНКИ -----

    @app.route("/about")
    def about_page():
        """Сторінка Про компанію."""
        settings = SiteSettings.get_or_create(g.store.id)
        return render_template("pages/about.html", settings=settings)

    @app.route("/contacts")
    def contacts_page():
        """Сторінка Контакти."""
        settings = SiteSettings.get_or_create(g.store.id)
        return render_template("pages/contacts.html", settings=settings)

    @app.route("/datenschutz")
    def datenschutz_page():
        """Політика конфіденційності (Datenschutzerklärung)."""
        settings = SiteSettings.get_or_create(g.store.id)
        return render_template("pages/datenschutz.html", settings=settings)

    @app.route("/agb")
    def agb_page():
        """Умови використання (Allgemeine Geschäftsbedingungen)."""
        settings = SiteSettings.get_or_create(g.store.id)
        return render_template("pages/agb.html", settings=settings)

    @app.route("/impressum")
    def impressum_page():
        """Юридичні реквізити власника магазину (Impressum, §5 TMG)."""
        settings = SiteSettings.get_or_create(g.store.id)
        return render_template("pages/impressum.html", settings=settings)

    @app.route("/ai-assistant")
    def ai_assistant_page():
        """Сторінка ІІ-продавця."""
        settings = SiteSettings.get_or_create(g.store.id)
        products = Product.query.filter_by(is_active=True, store_id=g.store.id).all()
        categories = Category.query.filter_by(store_id=g.store.id).all()
        return render_template(
            "pages/ai_assistant.html",
            settings=settings,
            products=products,
            categories=categories,
        )

    # ----- SEO: ROBOTS.TXT & SITEMAPS -----

    @app.route("/favicon.ico")
    def favicon():
        """Serve favicon or return 204 if not found."""
        try:
            return send_from_directory(app.static_folder, 'favicon.ico', mimetype='image/x-icon')
        except:
            return '', 204

    @app.route("/robots.txt")
    def robots_txt():
        """Serve robots.txt for search engine crawlers."""
        return send_from_directory(app.static_folder, 'robots.txt', mimetype='text/plain')

    @app.route("/sitemap.xml")
    def sitemap():
        """Generate main XML sitemap."""
        from services.seo_service import SEOService
        xml_content = SEOService.generate_sitemap()
        return app.response_class(xml_content, mimetype='application/xml')

    @app.route("/sitemap-products.xml")
    def sitemap_products():
        """Generate products sitemap."""
        from services.seo_service import SEOService
        xml_content = SEOService.generate_products_sitemap()
        return app.response_class(xml_content, mimetype='application/xml')

    @app.route("/sitemap-blog.xml")
    def sitemap_blog():
        """Generate blog sitemap."""
        from services.seo_service import SEOService
        xml_content = SEOService.generate_blog_sitemap()
        return app.response_class(xml_content, mimetype='application/xml')

    # ----- ПУБЛІЧНІ: МАГАЗИН -----

    @app.route("/shop")
    def shop():
        """Сторінка всіх товарів з пагінацією."""
        settings = SiteSettings.get_or_create(g.store.id)
        page = request.args.get("page", 1, type=int)
        per_page = 12

        products = (
            Product.query.filter_by(is_active=True, store_id=g.store.id)
            .order_by(Product.created_at.desc())
            .paginate(page=page, per_page=per_page, error_out=False)
        )
        categories = Category.query.filter_by(store_id=g.store.id).order_by(Category.name.asc()).all()

        return render_template(
            "shop.html",
            settings=settings,
            products=products,
            categories=categories,
        )

    @app.route("/category/<slug>")
    def category_page(slug):
        """Сторінка категорії з товарами."""
        settings = SiteSettings.get_or_create(g.store.id)
        category = Category.query.filter_by(slug=slug, store_id=g.store.id).first_or_404()
        page = request.args.get("page", 1, type=int)
        per_page = 12

        products = (
            Product.query.filter_by(is_active=True, category_id=category.id, store_id=g.store.id)
            .order_by(Product.created_at.desc())
            .paginate(page=page, per_page=per_page, error_out=False)
        )
        categories = Category.query.filter_by(store_id=g.store.id).order_by(Category.name.asc()).all()

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
        settings = SiteSettings.get_or_create(g.store.id)
        product = Product.query.filter_by(id=product_id, store_id=g.store.id).first_or_404()

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
                    Product.store_id == g.store.id,
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
        settings = SiteSettings.get_or_create(g.store.id)
        cart = get_cart()
        items = []
        total = 0.0

        for product_id_str, qty in cart.items():
            product = Product.query.filter_by(id=int(product_id_str), store_id=g.store.id).first()
            if product and product.is_active:
                item_total = product.price * qty
                total += item_total
                items.append({
                    "product": product,
                    "quantity": qty,
                    "item_total": item_total,
                })

        from services.shipping.registry import get_enabled_providers
        has_shipping_options = bool(get_enabled_providers(g.store.id)) or settings.pickup_enabled

        return render_template(
            "cart.html",
            settings=settings,
            items=items,
            total=total,
            has_shipping_carriers=has_shipping_options,
        )

    @app.route("/cart/add/<int:product_id>", methods=["POST"])
    def cart_add(product_id):
        """Додати товар у кошик."""
        product = Product.query.filter_by(id=product_id, store_id=g.store.id).first_or_404()
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
        flash(_("«%(name)s» додано в кошик.") % {"name": product.name}, "success")

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
            flash(_("Товар видалено з кошика."), "info")

        return redirect(url_for("cart_page"))

    @app.route("/cart/clear", methods=["POST"])
    def cart_clear():
        """Очистити весь кошик."""
        save_cart({})
        flash(_("Кошик очищено."), "info")
        return redirect(url_for("cart_page"))

    # ----- ДОСТАВКА: АДРЕСА ТА ВИБІР ТАРИФУ -----

    def _cart_weight_kg():
        """Сумарна вага кошика (кг) для запиту тарифів. За відсутності
        ваги товару використовується дефолт 1.0 кг за одиницю."""
        cart = get_cart()
        total_weight = 0.0
        for product_id_str, qty in cart.items():
            product = Product.query.filter_by(id=int(product_id_str), store_id=g.store.id).first()
            if product and product.is_active:
                total_weight += (product.weight_kg or 1.0) * qty
        return total_weight or 1.0

    @app.route("/checkout/address", methods=["GET", "POST"])
    def checkout_address():
        """Форма адреси доставки - показується тільки якщо в магазині
        налаштовано хоча б одну службу доставки (інакше кнопка в кошику
        веде одразу на /checkout, як і раніше)."""
        settings = SiteSettings.get_or_create(g.store.id)
        cart = get_cart()
        if not cart:
            flash(_("Ваш кошик порожній."), "warning")
            return redirect(url_for("cart_page"))

        if request.method == "POST":
            address = {
                "name": request.form.get("name", "").strip(),
                "phone": request.form.get("phone", "").strip(),
                "email": request.form.get("email", "").strip(),
                "street": request.form.get("street", "").strip(),
                "city": request.form.get("city", "").strip(),
                "postal_code": request.form.get("postal_code", "").strip(),
                "country_code": request.form.get("country_code", "").strip().upper(),
            }
            # Адреса потрібна лише для доставки перевізником - для самовивозу
            # обов'язкові тільки контактні дані, тому тут вимагаємо мінімум.
            missing = [k for k in ("name", "phone") if not address[k]]
            if missing:
                flash(_("Вкажіть ім'я та телефон."), "danger")
                return render_template("checkout_address.html", settings=settings, form=address)

            session["checkout_address"] = address
            return redirect(url_for("checkout_shipping"))

        return render_template(
            "checkout_address.html",
            settings=settings,
            form=session.get("checkout_address", {}),
        )

    @app.route("/checkout/shipping", methods=["GET", "POST"])
    def checkout_shipping():
        """Вибір тарифу доставки на основі адреси з попереднього кроку."""
        from services.shipping.registry import get_enabled_providers
        from services.shipping.base import Address, ShippingProviderError

        settings = SiteSettings.get_or_create(g.store.id)
        address = session.get("checkout_address")
        if not address:
            return redirect(url_for("checkout_address"))

        if request.method == "POST":
            carrier = request.form.get("carrier", "")
            session["checkout_shipping"] = {
                "carrier": carrier,
                "service_code": request.form.get("service_code", ""),
                "name": request.form.get("name", ""),
                "price": request.form.get("price", 0.0, type=float),
                "is_pickup": carrier == "pickup",
            }
            return redirect(url_for("checkout"))

        providers = get_enabled_providers(g.store.id)
        destination = Address.from_dict(address)
        weight_kg = _cart_weight_kg()

        options = []
        if settings.pickup_enabled:
            options.append({
                "carrier": "pickup",
                "carrier_label": "🏬 Самовивіз",
                "service_code": "",
                "name": settings.pickup_address or "Самовивіз з магазину",
                "price": 0.0,
                "currency": settings.default_currency or "EUR",
                "eta_days": None,
            })

        for account, provider in providers:
            try:
                rates = provider.get_rates(Address.from_dict(account.origin_address), destination, weight_kg)
                for rate in rates:
                    options.append({
                        "carrier": account.carrier,
                        "carrier_label": account.carrier_label,
                        "service_code": rate.service_code,
                        "name": rate.name,
                        "price": rate.price,
                        "currency": rate.currency,
                        "eta_days": rate.eta_days,
                    })
            except ShippingProviderError as e:
                app.logger.warning(f"Shipping rate lookup failed for {account.carrier}: {e}")

        if not options:
            # Жодна служба не відповіла (або жодної не налаштовано) -
            # продовжуємо без доставки, як і раніше.
            session["checkout_shipping"] = None
            return redirect(url_for("checkout"))

        return render_template(
            "checkout_shipping.html",
            settings=settings,
            options=options,
            address=address,
        )

    # ----- STRIPE CHECKOUT -----

    @app.route("/checkout", methods=["GET", "POST"])
    def checkout():
        """Створити Stripe Checkout сесію."""
        if not STRIPE_AVAILABLE or not app.config["STRIPE_SECRET_KEY"]:
            flash(_("Stripe не налаштовано. Зверніться до адміністратора."), "danger")
            return redirect(url_for("cart_page"))

        if not g.store.can_accept_payments:
            flash(_("Цей магазин ще не підключив прийом оплат. Зверніться до продавця."), "danger")
            return redirect(url_for("cart_page"))

        cart = get_cart()
        if not cart:
            flash(_("Ваш кошик порожній."), "warning")
            return redirect(url_for("cart_page"))

        line_items = []
        order_items_data = []
        total = 0.0

        for product_id_str, qty in cart.items():
            product = Product.query.filter_by(id=int(product_id_str), store_id=g.store.id).first()
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
            flash(_("Не вдалося знайти товари в кошику."), "danger")
            return redirect(url_for("cart_page"))

        # Адреса й тариф доставки (опційно - якщо магазин не налаштував
        # службу доставки, обидва відсутні і поведінка лишається такою ж,
        # як до впровадження цієї фічі).
        checkout_address = session.pop("checkout_address", None)
        checkout_shipping = session.pop("checkout_shipping", None)
        shipping_price = float(checkout_shipping["price"]) if checkout_shipping else 0.0

        if shipping_price > 0:
            line_items.append({
                "price_data": {
                    "currency": "eur",
                    "product_data": {"name": f"Доставка: {checkout_shipping['name']}"},
                    "unit_amount": int(shipping_price * 100),
                },
                "quantity": 1,
            })

        try:
            # Створюємо замовлення в БД
            order = Order(
                store_id=g.store.id,
                status="pending",
                amount=total + shipping_price,
                subtotal=total,
                currency="EUR",
                shipping_cost=shipping_price,
                shipping_method=checkout_shipping["name"] if checkout_shipping else None,
                is_pickup=bool(checkout_shipping and checkout_shipping.get("is_pickup")),
                shipping_address=checkout_address["street"] if checkout_address else None,
                shipping_city=checkout_address["city"] if checkout_address else None,
                shipping_postal_code=checkout_address["postal_code"] if checkout_address else None,
                shipping_country=checkout_address["country_code"] if checkout_address else None,
                customer_name=checkout_address["name"] if checkout_address else None,
                customer_phone=checkout_address["phone"] if checkout_address else None,
                locale=session.get("lang", app.config["BABEL_DEFAULT_LOCALE"]),
            )
            db.session.add(order)
            db.session.flush()  # Отримуємо ID
            order.order_number = f"{'B2B' if order.is_b2b else 'SM'}-{datetime.utcnow().year}-{order.id:05d}"

            # Додаємо товари до замовлення
            for item_data in order_items_data:
                order_item = OrderItem(
                    store_id=g.store.id,
                    order_id=order.id,
                    product_id=item_data["product_id"],
                    product_name=item_data["product_name"],
                    price=item_data["price"],
                    quantity=item_data["quantity"],
                    currency=item_data["currency"],
                )
                db.session.add(order_item)

            # Створюємо Stripe Checkout сесію. Гроші клієнта йдуть напряму
            # власнику магазину через destination charge (transfer_data) -
            # платформа лишається лише посередником Checkout-сесії й не
            # утримує кошти на своєму рахунку та не бере комісії.
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=line_items,
                mode="payment",
                success_url=url_for("checkout_success", _external=True) + "?session_id={CHECKOUT_SESSION_ID}",
                cancel_url=url_for("checkout_cancel", _external=True),
                payment_intent_data={
                    "transfer_data": {"destination": g.store.stripe_connect_account_id},
                },
                metadata={
                    "order_id": str(order.id),
                    "store_id": str(g.store.id),
                    "shipping_carrier": checkout_shipping["carrier"] if checkout_shipping else "",
                    "shipping_service_code": checkout_shipping["service_code"] if checkout_shipping else "",
                },
            )

            order.stripe_session_id = checkout_session.id
            db.session.commit()

            return redirect(checkout_session.url)

        except stripe.error.StripeError as e:
            db.session.rollback()
            flash(_("Помилка Stripe: %(error)s") % {"error": str(e)}, "danger")
            return redirect(url_for("cart_page"))

    def _auto_create_shipment(order, task, carrier_code, service_code):
        """
        Автоматично створює відправлення в перевізника (лейбл + трек-номер)
        для щойно оплаченого замовлення, якщо для цього магазину налаштовано
        відповідний CarrierAccount. Ніколи не пробрасує виняток назовні -
        збій перевізника не повинен ламати підтвердження оплати; в такому
        разі WarehouseTask лишається з порожнім tracking_number, і адмін
        може ввести його вручну на сторінці завдання складу (як і раніше).
        """
        if not carrier_code or not task:
            return
        try:
            from services.shipping.registry import get_provider_for_carrier
            from services.shipping.base import Address, ShippingProviderError

            account, provider = get_provider_for_carrier(order.store_id, carrier_code)
            if not provider:
                return

            origin = Address.from_dict(account.origin_address)
            destination = Address(
                name=order.customer_name or "",
                street=order.shipping_address or "",
                city=order.shipping_city or "",
                postal_code=order.shipping_postal_code or "",
                country_code=order.shipping_country or "",
                phone=order.customer_phone or "",
            )
            weight_kg = sum(
                (item.product.weight_kg or 1.0) * item.quantity
                for item in order.items if item.product
            ) or 1.0

            result = provider.create_shipment(
                origin, destination, weight_kg, service_code,
                reference=order.order_number or str(order.id),
            )
            task.tracking_number = result.tracking_number
            task.carrier = account.carrier_label
            task.label_url = result.label_url
            db.session.commit()
        except ShippingProviderError as e:
            app.logger.warning(f"Automatic shipment creation failed for order #{order.id}: {e}")
        except Exception as e:
            app.logger.warning(f"Automatic shipment creation error for order #{order.id}: {e}")

    @app.route("/checkout/success")
    def checkout_success():
        """Сторінка успішної оплати."""
        settings = SiteSettings.get_or_create(g.store.id)
        session_id = request.args.get("session_id")
        
        order = None
        if session_id and STRIPE_AVAILABLE and app.config["STRIPE_SECRET_KEY"]:
            try:
                checkout_session = stripe.checkout.Session.retrieve(session_id)
                order = Order.query.filter_by(stripe_session_id=session_id, store_id=g.store.id).first()

                # КРИТИЧНО: успішний retrieve() лише означає, що session_id
                # існує - НЕ означає, що оплата відбулась. Без цієї перевірки
                # клієнт міг скасувати оплату на сторінці Stripe і вручну
                # перейти на /checkout/success?session_id=... - замовлення
                # позначилось б оплаченим без жодної реальної транзакції.
                if order and order.status == "pending" and checkout_session.payment_status == "paid":
                    order.status = "paid"
                    order.paid_at = datetime.utcnow()
                    order.customer_email = checkout_session.customer_details.email if checkout_session.customer_details else None
                    order.customer_name = checkout_session.customer_details.name if checkout_session.customer_details else None
                    order.stripe_payment_intent = checkout_session.payment_intent
                    db.session.commit()
                    
                    # Відправити email підтвердження замовлення
                    if order.email:
                        try:
                            from services.email_service import send_order_confirmation
                            send_order_confirmation(order.email, order)
                            app.logger.info(f'Order confirmation email sent to {order.email}')
                        except Exception as e:
                            app.logger.error(f'Failed to send order confirmation: {str(e)}')
                    
                    # Створюємо завдання для складу
                    try:
                        from models.warehouse import WarehouseTask
                        existing_task = WarehouseTask.query.filter_by(order_id=order.id).first()
                        if not existing_task:
                            task = WarehouseTask.create_from_order(
                                order_id=order.id,
                                priority=2 if getattr(order, 'is_b2b', False) else 3,
                                notes=getattr(order, 'notes', ''),
                            )
                            metadata = checkout_session.metadata or {}
                            _auto_create_shipment(
                                order, task,
                                metadata.get("shipping_carrier"),
                                metadata.get("shipping_service_code"),
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
        settings = SiteSettings.get_or_create(g.store.id)
        flash(_("Оплату скасовано. Ви можете спробувати ще раз."), "info")
        return redirect(url_for("cart_page"))

    @app.route("/webhook/stripe", methods=["POST"])
    @csrf.exempt
    def stripe_webhook():
        """Webhook для Stripe. CSRF-виняток: запит приходить від Stripe,
        не з браузера з session-кукою, і автентичність перевіряється
        підписом (stripe.Webhook.construct_event), а не CSRF-токеном."""
        if not STRIPE_AVAILABLE:
            return jsonify({"error": _("Stripe not available")}), 400

        payload = request.get_data()
        sig_header = request.headers.get("Stripe-Signature")
        webhook_secret = app.config["STRIPE_WEBHOOK_SECRET"]

        # КРИТИЧНО: без webhook_secret немає способу перевірити, що запит
        # справді прийшов від Stripe, а не від будь-кого, хто відправив
        # довільний JSON на цей публічний ендпоінт. Раніше тут був фолбек
        # на stripe.Event.construct_from(), який довіряв НЕПІДПИСАНОМУ
        # тілу запиту - це дозволяло будь-кому позначити чуже замовлення
        # оплаченим або активувати підписку магазину без жодної реальної
        # транзакції. Без секрету обробка події повинна відмовляти, а не
        # довіряти вхідним даним.
        if not webhook_secret:
            app.logger.warning(
                "Отримано запит на /webhook/stripe, але STRIPE_WEBHOOK_SECRET не налаштовано - "
                "подію відхилено без верифікації підпису."
            )
            return jsonify({"error": _("Webhook not configured")}), 503

        try:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        except ValueError:
            return jsonify({"error": _("Invalid payload")}), 400
        except stripe.error.SignatureVerificationError:
            return jsonify({"error": _("Invalid signature")}), 400

        # Обробка події
        if event["type"] == "checkout.session.completed":
            session_data = event["data"]["object"]
            session_id = session_data["id"]

            if session_data.get("mode") == "subscription":
                # SaaS-підписка нового/існуючого Store (не замовлення в магазині)
                store_id = (session_data.get("metadata") or {}).get("store_id")
                if store_id:
                    store = Store.query.get(int(store_id))
                    if store:
                        store.stripe_customer_id = session_data.get("customer")
                        store.stripe_subscription_id = session_data.get("subscription")
                        store.subscription_status = "active"
                        db.session.commit()
            else:
                order = Order.query.filter_by(stripe_session_id=session_id).first()
                if order:
                    order.status = "paid"
                    order.paid_at = datetime.utcnow()
                    order.customer_email = session_data.get("customer_details", {}).get("email")
                    order.customer_name = session_data.get("customer_details", {}).get("name")
                    order.stripe_payment_intent = session_data.get("payment_intent")
                    db.session.commit()

                    # Створюємо завдання для складу
                    try:
                        from models.warehouse import WarehouseTask
                        existing_task = WarehouseTask.query.filter_by(order_id=order.id).first()
                        if not existing_task:
                            task = WarehouseTask.create_from_order(
                                order_id=order.id,
                                priority=2 if getattr(order, 'is_b2b', False) else 3,
                                notes=getattr(order, 'notes', ''),
                            )
                            webhook_metadata = session_data.get("metadata") or {}
                            _auto_create_shipment(
                                order, task,
                                webhook_metadata.get("shipping_carrier"),
                                webhook_metadata.get("shipping_service_code"),
                            )
                    except Exception:
                        pass  # Якщо модуль складу не доступний

        elif event["type"] in ("customer.subscription.updated", "customer.subscription.deleted"):
            # Синхронізуємо статус підписки Store (оплата не пройшла, скасування тощо)
            subscription_data = event["data"]["object"]
            store = Store.query.filter_by(stripe_subscription_id=subscription_data["id"]).first()
            if store:
                stripe_status = subscription_data.get("status")
                if event["type"] == "customer.subscription.deleted" or stripe_status == "canceled":
                    store.subscription_status = "canceled"
                elif stripe_status in ("past_due", "unpaid", "incomplete_expired"):
                    store.subscription_status = "past_due"
                elif stripe_status in ("active", "trialing"):
                    store.subscription_status = stripe_status
                db.session.commit()

        return jsonify({"status": "success"}), 200

    # ----- AI CHAT -----

    CHAT_TOOLS = [
        {
            "type": "function",
            "function": {
                "name": "lookup_order_status",
                "description": (
                    "Перевірити статус замовлення клієнта за номером замовлення та email. "
                    "Використовуй ЛИШЕ якщо клієнт явно запитує про статус свого замовлення "
                    "і вже назвав ОБИДВА значення - номер замовлення і email. Якщо чогось "
                    "не вистачає - спочатку ввічливо запитай це у клієнта звичайним текстом, "
                    "не викликай цю функцію з порожніми полями."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "order_number": {"type": "string", "description": "Номер замовлення, напр. SM-2025-0001"},
                        "email": {"type": "string", "description": "Email клієнта, вказаний при оформленні замовлення"},
                    },
                    "required": ["order_number", "email"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "escalate_to_human",
                "description": (
                    "Передати розмову менеджеру-людині - коли клієнт явно просить оператора/людину, "
                    "скаржиться, або коли ти не можеш допомогти. Перед викликом ввічливо запитай "
                    "ім'я та email або телефон клієнта для зворотного зв'язку, якщо він їх ще не назвав."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {"type": "string", "description": "Коротко: чому потрібна ескалація і що просить клієнт"},
                        "contact_name": {"type": "string", "description": "Ім'я клієнта, якщо назвав"},
                        "contact_email": {"type": "string", "description": "Email клієнта, якщо назвав"},
                        "contact_phone": {"type": "string", "description": "Телефон клієнта, якщо назвав"},
                    },
                    "required": ["reason"],
                },
            },
        },
    ]
    CHAT_HISTORY_TURNS = 6  # зберігаємо останні N пар (user+assistant) у сесії

    @app.route("/api/chat", methods=["POST"])
    def api_chat():
        """API для чату з ІІ-продавцем."""
        import json as json_module

        openai_client = get_openai_client()
        if not OPENAI_AVAILABLE or not openai_client:
            error_msg = _("AI чатбот тимчасово недоступний. Будь ласка, спробуйте пізніше.")
            print(f"❌ Chat API error: OpenAI not available (OPENAI_AVAILABLE={OPENAI_AVAILABLE}, client={openai_client})")
            return jsonify({"error": error_msg}), 503

        data = request.get_json()
        user_message = data.get("message", "").strip()

        if not user_message:
            return jsonify({"error": _("Повідомлення порожнє")}), 400

        # Отримуємо налаштування AI
        try:
            ai_settings = AISettings.get_or_create(g.store.id)

            if not ai_settings.chatbot_enabled:
                return jsonify({"error": _("Чатбот тимчасово недоступний")}), 503
        except Exception as e:
            print(f"❌ Error getting AI settings: {e}")
            return jsonify({"error": _("Помилка налаштувань чатбота")}), 500

        # Отримуємо налаштування сайту та каталог (лише поточного магазину!)
        settings = SiteSettings.get_or_create(g.store.id)
        products = Product.query.filter_by(is_active=True, store_id=g.store.id).all()
        categories = Category.query.filter_by(store_id=g.store.id).all()

        # Формуємо контекст каталогу
        catalog_info = "Каталог товарів:\n"
        for cat in categories:
            catalog_info += f"\nКатегорія: {cat.name}\n"
            cat_products = [p for p in products if p.category_id == cat.id]
            for p in cat_products:
                catalog_info += f"  - {p.name}: {p.price} {p.currency}"
                if p.short_description:
                    catalog_info += f" ({p.short_description})"
                if p.stock > 0:
                    catalog_info += f" [В наявності: {p.stock}]"
                else:
                    catalog_info += " [Немає в наявності]"
                catalog_info += "\n"

        # Товари без категорії
        no_cat_products = [p for p in products if not p.category_id]
        if no_cat_products:
            catalog_info += "\nІнші товари:\n"
            for p in no_cat_products:
                catalog_info += f"  - {p.name}: {p.price} {p.currency}\n"

        # Формуємо системний промпт з кастомними інструкціями
        system_prompt = ai_settings.get_full_chatbot_prompt(catalog_info)

        # Додаємо базові правила якщо немає в налаштуваннях
        if not ai_settings.chatbot_system_prompt:
            system_prompt = f"""Ти — {ai_settings.chatbot_name or 'ІІ-продавець'} цього магазину.

{catalog_info}

Важливо:
- Відповідай тільки на питання про товари з каталогу
- Не вигадуй товарів, яких немає
- Пропонуй релевантні товари
- Будь ввічливим та корисним
- Відповідай українською мовою

{ai_settings.chatbot_custom_instructions or ''}
"""

        system_prompt += (
            "\n\nЯкщо клієнт запитує про статус свого замовлення - використай функцію "
            "lookup_order_status (потрібні номер замовлення і email). Якщо клієнт просить "
            "оператора/людину або ти не можеш допомогти - використай функцію escalate_to_human."
        )

        def _execute_chat_tool(tool_name, arguments_json):
            try:
                args = json_module.loads(arguments_json or "{}")
            except json_module.JSONDecodeError:
                args = {}

            if tool_name == "lookup_order_status":
                order_number = (args.get("order_number") or "").strip()
                email = (args.get("email") or "").strip().lower()
                if not order_number or not email:
                    return {"found": False, "error": "missing_order_number_or_email"}
                order = Order.query.filter_by(store_id=g.store.id, order_number=order_number).first()
                if not order or (order.customer_email or "").strip().lower() != email:
                    return {"found": False}
                return {
                    "found": True,
                    "status": order.status_display,
                    "is_pickup": bool(order.is_pickup),
                    "tracking_number": order.tracking_number or None,
                    "shipping_method": order.shipping_method or None,
                    "paid_at": order.paid_at.strftime("%Y-%m-%d %H:%M") if order.paid_at else None,
                    "shipped_at": order.shipped_at.strftime("%Y-%m-%d %H:%M") if order.shipped_at else None,
                }

            if tool_name == "escalate_to_human":
                reason = (args.get("reason") or "Клієнт потребує допомоги людини").strip()
                contact = ContactMessage(
                    store_id=g.store.id,
                    name=(args.get("contact_name") or "Клієнт з ІІ-чату").strip() or "Клієнт з ІІ-чату",
                    email=(args.get("contact_email") or "no-email@chat.smartshop.local").strip(),
                    phone=(args.get("contact_phone") or None),
                    subject="🤖 Ескалація з ІІ-чату",
                    message=f"{reason}\n\nОстаннє повідомлення клієнта: {user_message}",
                )
                db.session.add(contact)
                db.session.commit()
                return {"escalated": True}

            return {"error": "unknown_tool"}

        history = session.get("chat_history", [])
        messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": user_message}]

        try:
            ai_message = None
            for _ in range(3):  # обмежуємо кількість раундів виклику інструментів
                response = openai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=messages,
                    tools=CHAT_TOOLS,
                    tool_choice="auto",
                    max_tokens=ai_settings.chatbot_max_tokens or 500,
                    temperature=ai_settings.chatbot_temperature or 0.7,
                )
                choice_message = response.choices[0].message

                if not choice_message.tool_calls:
                    ai_message = choice_message.content
                    break

                messages.append({
                    "role": "assistant",
                    "content": choice_message.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in choice_message.tool_calls
                    ],
                })
                for tc in choice_message.tool_calls:
                    tool_result = _execute_chat_tool(tc.function.name, tc.function.arguments)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json_module.dumps(tool_result, ensure_ascii=False),
                    })
            else:
                ai_message = "Вибачте, не вдалося обробити запит. Спробуйте, будь ласка, ще раз."

            # Оновлюємо історію діалогу в сесії (лише user/assistant репліки, без system/tool)
            history.append({"role": "user", "content": user_message})
            history.append({"role": "assistant", "content": ai_message or ""})
            session["chat_history"] = history[-(CHAT_HISTORY_TURNS * 2):]

            print(f"✅ Chat API success: User message length={len(user_message)}, AI response length={len(ai_message or '')}")
            return jsonify({"message": ai_message})

        except AttributeError as e:
            # OpenAI client not properly initialized
            error_msg = _("Помилка ініціалізації AI клієнта")
            print(f"❌ Chat API error (AttributeError): {e}")
            return jsonify({"error": error_msg}), 500
        except Exception as e:
            error_msg = _("Помилка обробки запиту")
            print(f"❌ Chat API error (Exception): {type(e).__name__}: {e}")
            return jsonify({"error": error_msg}), 500

    @app.route("/api/chat/reset", methods=["POST"])
    def api_chat_reset():
        """Скидає історію діалогу з ІІ-продавцем у поточній сесії."""
        session.pop("chat_history", None)
        return jsonify({"success": True})

    @app.context_processor
    def cart_context():
        """Додає cart_count у всі шаблони."""
        cart = get_cart()
        cart_count = sum(cart.values()) if cart else 0
        return {"cart_count": cart_count}

    @app.context_processor
    def impersonation_context():
        """Прапорець для банера "ви імперсонуєте власника" в адмінці - показує
        оператору платформи, що поточна сесія тимчасова, і дає швидкий вихід."""
        return {
            "is_impersonating": "impersonator_id" in session,
            "impersonating_store_name": session.get("impersonating_store_name"),
        }
    
    @app.context_processor
    def currency_context():
        """Додає функцію для отримання символу валюти."""
        def get_currency_symbol(currency_code):
            symbols = {
                "EUR": "€",
                "USD": "$",
                "UAH": "₴",
                "GBP": "£",
                "PLN": "zł",
                "CZK": "Kč"
            }
            return symbols.get(currency_code, currency_code)
        return {"get_currency_symbol": get_currency_symbol}

    @app.context_processor
    def theme_context():
        """Дає шаблонам доступ до готових пресетів дизайну (кольори/шрифт/
        розкладка) поточного магазину - завжди беремо з фіксованого набору
        в services/theme_presets.py, ніколи не рендеримо довільний CSS/HTML
        від власника магазину."""
        from services.theme_presets import get_theme, get_font, get_layout
        current_settings = getattr(g, "store", None) and SiteSettings.get_or_create(g.store.id)
        theme = get_theme(current_settings.theme_preset if current_settings else None)
        font = get_font(current_settings.font_preset if current_settings else None)
        layout = get_layout(current_settings.homepage_layout if current_settings else None)
        return {"active_theme": theme, "active_font": font, "active_homepage_layout": layout}

    # ----- АДМІНКА: АВТОРИЗАЦІЯ -----

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        """
        Legacy URL, залишений для сумісності зі старими закладками/лінками.
        Реальний логін тепер один для всіх (customer/partner/store owner) —
        через Flask-Login у routes/auth.py, щоб адмінка могла бути прив'язана
        до конкретного current_user і, відповідно, до конкретного Store.
        """
        if DEMO_MODE:
            return redirect(url_for("admin_dashboard"))
        return redirect(url_for("user_login", next=url_for("admin_dashboard")))

    @app.route("/admin/logout")
    def admin_logout():
        return redirect(url_for("user_logout"))

    # ----- АДМІНКА: ДАШБОРД -----

    @app.route("/admin/")
    @admin_required
    def admin_dashboard():
        settings = SiteSettings.get_or_create(g.store.id)
        product_count = Product.query.filter_by(store_id=g.store.id).count()
        category_count = Category.query.filter_by(store_id=g.store.id).count()
        order_count = Order.query.filter_by(store_id=g.store.id).count()

        total_revenue = (
            db.session.query(db.func.coalesce(db.func.sum(Order.amount), 0.0))
            .filter(Order.status == "paid", Order.store_id == g.store.id)
            .scalar()
        )

        last_orders = (
            Order.query.filter_by(store_id=g.store.id).order_by(Order.created_at.desc()).limit(5).all()
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
        settings = SiteSettings.get_or_create(g.store.id)

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
            flash(_("Налаштування головної сторінки збережені."), "success")
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
            
            # Multilingual fields
            name_en = request.form.get("name_en", "").strip()
            name_de = request.form.get("name_de", "").strip()
            description_en = request.form.get("description_en", "").strip()
            description_de = request.form.get("description_de", "").strip()

            if not name or not slug:
                flash(_("Назва і slug категорії обовʼязкові."), "danger")
            else:
                exists = Category.query.filter_by(slug=slug, store_id=g.store.id).first()
                if exists:
                    flash(_("Категорія з таким slug уже існує."), "warning")
                else:
                    category = Category(
                        store_id=g.store.id,
                        name=name,
                        slug=slug,
                        description=description or None,
                        name_en=name_en or None,
                        name_de=name_de or None,
                        description_en=description_en or None,
                        description_de=description_de or None,
                    )
                    db.session.add(category)
                    db.session.commit()
                    flash(_("Категорія створена."), "success")
            return redirect(url_for("admin_categories"))

        categories = Category.query.filter_by(store_id=g.store.id).order_by(Category.name.asc()).all()
        return render_template("admin/categories.html", categories=categories)

    # ----- АДМІНКА: ЗАВАНТАЖЕННЯ ЗОБРАЖЕНЬ -----

    @app.route("/admin/upload", methods=["POST"])
    @admin_required
    def admin_upload():
        """Завантаження зображення в базу даних PostgreSQL."""
        if 'file' not in request.files:
            return jsonify({"error": _("Файл не обрано")}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": _("Файл не обрано")}), 400
        
        # Get MIME type from request
        content_type = file.content_type
        
        # Validate file with both extension and MIME type
        if file and allowed_file(file.filename, content_type):
            from models.product import Image
            
            # Secure the filename
            secured_name = secure_filename(file.filename)
            
            # Генеруємо унікальне ім'я файлу
            ext = secured_name.rsplit('.', 1)[1].lower()
            filename = f"{uuid.uuid4().hex}.{ext}"
            
            # Читаємо файл у пам'ять
            file_data = file.read()
            file_size = len(file_data)
            
            # Перевірка розміру (max 16 MB)
            max_size = app.config.get('MAX_CONTENT_LENGTH', 16 * 1024 * 1024)
            if file_size > max_size:
                return jsonify({"error": f"Файл занадто великий (max {max_size // 1024 // 1024} MB)"}), 400
            
            # Upload to Cloudinary if configured
            if app.config.get("IMAGE_STORAGE") == "cloudinary" and CLOUDINARY_AVAILABLE:
                if all([app.config.get("CLOUDINARY_CLOUD_NAME"), 
                       app.config.get("CLOUDINARY_API_KEY"), 
                       app.config.get("CLOUDINARY_API_SECRET")]):
                    try:
                        # Reset file pointer
                        file.seek(0)
                        # Upload to Cloudinary
                        upload_result = cloudinary.uploader.upload(
                            file,
                            folder="smartshop",
                            public_id=filename.rsplit('.', 1)[0],
                            resource_type="image",
                            allowed_formats=['png', 'jpg', 'jpeg', 'gif', 'webp']
                        )
                        
                        file_url = upload_result['secure_url']
                        
                        return jsonify({
                            "success": True,
                            "url": file_url,
                            "filename": filename,
                            "storage": "cloudinary"
                        })
                        
                    except Exception as e:
                        print(f"Cloudinary upload error: {e}")
                        # Fallback to database
            
            # Зберігаємо в базі даних
            try:
                # Перевіряємо, чи вже існує файл з таким іменем
                existing_image = Image.query.filter_by(filename=filename).first()
                if existing_image:
                    # Оновлюємо існуюче зображення
                    existing_image.data = file_data
                    existing_image.mime_type = content_type
                    existing_image.size = file_size
                    image = existing_image
                else:
                    # Створюємо нове зображення
                    image = Image(
                        store_id=g.store.id,
                        filename=filename,
                        data=file_data,
                        mime_type=content_type,
                        size=file_size
                    )
                    db.session.add(image)
                
                db.session.commit()
                
                # Повертаємо URL для отримання зображення
                file_url = url_for('serve_image', filename=filename, _external=True)
                
                return jsonify({
                    "success": True, 
                    "url": file_url,
                    "filename": filename,
                    "storage": "database",
                    "size": file_size
                })
                
            except Exception as e:
                db.session.rollback()
                print(f"Database save error: {e}")
                return jsonify({"error": f"Помилка збереження: {str(e)}"}), 500
        
        return jsonify({"error": _("Недозволений тип файлу. Дозволено: png, jpg, jpeg, gif, webp")}), 400
    
    # ----- СЕРВІС ЗОБРАЖЕНЬ З БД -----
    
    @app.route("/images/<filename>")
    def serve_image(filename):
        """Віддає зображення з бази даних."""
        from models.product import Image
        from flask import send_file
        import io
        
        try:
            image = Image.query.filter_by(filename=filename).first()
            
            if not image:
                app.logger.warning(f"❌ Image not found in database: {filename}")
                # Повертаємо placeholder замість 404
                return send_file(
                    io.BytesIO(b''),
                    mimetype='image/png',
                    as_attachment=False
                ), 404
            
            # Створюємо буфер з даними зображення
            image_io = io.BytesIO(image.data)
            image_io.seek(0)
            
            app.logger.debug(f"✅ Serving image from database: {filename} ({image.size} bytes)")
            
            return send_file(
                image_io,
                mimetype=image.mime_type,
                as_attachment=False,
                download_name=image.filename
            )
        except Exception as e:
            app.logger.error(f"❌ Error serving image {filename}: {type(e).__name__}: {e}")
            return send_file(
                io.BytesIO(b''),
                mimetype='image/png',
                as_attachment=False
            ), 500
    
    def delete_old_image(old_image_url):
        """Видаляє старе зображення з бази даних або файлової системи.

        old_image_url може бути як відносним шляхом ('/images/xxx.png'),
        так і повним URL ('http://host/images/xxx.png' - саме так їх
        повертає /admin/upload через url_for(..., _external=True)), тому
        порівнюємо лише шлях (без хоста/схеми), а не сирий рядок цілком.
        """
        if not old_image_url:
            return

        from models.product import Image
        from urllib.parse import urlparse

        path = urlparse(old_image_url).path

        try:
            # Перевіряємо, чи це зображення з бази даних
            if path.startswith('/images/'):
                filename = path.split('/images/')[-1]
                old_image = Image.query.filter_by(filename=filename).first()

                if old_image:
                    db.session.delete(old_image)
                    db.session.commit()
                    app.logger.info(f"🗑️ Deleted old image from database: {filename}")
                    return True

            # Якщо це локальний файл
            elif path.startswith('/static/uploads/'):
                filename = path.split('/static/uploads/')[-1]
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

                if os.path.exists(file_path):
                    os.remove(file_path)
                    app.logger.info(f"🗑️ Deleted old local file: {filename}")
                    return True

        except Exception as e:
            app.logger.warning(f"⚠️ Could not delete old image {old_image_url}: {e}")

        return False

    # ----- АДМІНКА: ТОВАРИ -----

    @app.route("/admin/products")
    @admin_required
    def admin_products():
        products = (
            Product.query.filter_by(store_id=g.store.id).order_by(Product.created_at.desc())
            .all()
        )
        categories = Category.query.filter_by(store_id=g.store.id).order_by(Category.name.asc()).all()
        settings = SiteSettings.get_or_create(g.store.id)
        return render_template(
            "admin/products.html", products=products, categories=categories, settings=settings
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
        
        # Мультимовні поля
        name_en = request.form.get("name_en", "").strip() or None
        name_de = request.form.get("name_de", "").strip() or None
        description_en = request.form.get("description_en", "").strip() or None
        description_de = request.form.get("description_de", "").strip() or None

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

        settings = SiteSettings.get_or_create(g.store.id)
        # category_id має належати поточному магазину - інакше ігноруємо
        safe_category_id = None
        if category_id:
            cat = Category.query.filter_by(id=int(category_id), store_id=g.store.id).first()
            safe_category_id = cat.id if cat else None
        product = Product(
            store_id=g.store.id,
            name=name,
            price=price_value,
            old_price=old_price_value,
            currency=settings.default_currency or "EUR",
            category_id=safe_category_id,
            short_description=description or None,
            image_url=image_url or None,
            stock=stock_value,
            is_active=is_active,
            # Мультимовність
            name_en=name_en,
            name_de=name_de,
            short_description_en=description_en,
            short_description_de=description_de,
        )
        db.session.add(product)
        db.session.commit()
        flash(_("Товар створено."), "success")
        return redirect(url_for("admin_products"))

    @app.route("/admin/products/<int:product_id>/toggle", methods=["POST"])
    @admin_required
    def admin_products_toggle(product_id):
        product = Product.query.filter_by(id=product_id, store_id=g.store.id).first_or_404()
        product.is_active = not product.is_active
        db.session.commit()
        flash(_("Статус товару оновлено."), "info")
        return redirect(url_for("admin_products"))

    @app.route("/admin/products/<int:product_id>/delete", methods=["POST"])
    @admin_required
    def admin_products_delete(product_id):
        product = Product.query.filter_by(id=product_id, store_id=g.store.id).first_or_404()

        # Видаляємо зображення перед видаленням товару
        if product.image_url:
            delete_old_image(product.image_url)
        
        db.session.delete(product)
        db.session.commit()
        flash(_("Товар видалено."), "info")
        return redirect(url_for("admin_products"))

    @app.route("/admin/products/<int:product_id>/edit", methods=["GET", "POST"])
    @admin_required
    def admin_products_edit(product_id):
        """Редагування товару."""
        product = Product.query.filter_by(id=product_id, store_id=g.store.id).first_or_404()
        categories = Category.query.filter_by(store_id=g.store.id).order_by(Category.name.asc()).all()

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
            safe_category_id = None
            if category_id:
                cat = Category.query.filter_by(id=int(category_id), store_id=g.store.id).first()
                safe_category_id = cat.id if cat else None
            product.category_id = safe_category_id
            product.short_description = request.form.get("short_description", "").strip() or None
            product.long_description = request.form.get("long_description", "").strip() or None
            
            # Оновлюємо image_url та видаляємо старе зображення
            new_image_url = request.form.get("image_url", "").strip() or None
            if new_image_url and new_image_url != product.image_url:
                # Видаляємо старе зображення з бази даних
                delete_old_image(product.image_url)
            product.image_url = new_image_url
            
            product.sku = request.form.get("sku", "").strip() or None
            product.is_active = request.form.get("is_active") == "on"

            weight_kg = request.form.get("weight_kg", "").strip()
            try:
                product.weight_kg = float(weight_kg) if weight_kg else None
            except ValueError:
                product.weight_kg = None

            db.session.commit()
            flash(_("Товар оновлено."), "success")
            return redirect(url_for("admin_products"))

        return render_template(
            "admin/product_edit.html",
            product=product,
            categories=categories,
            settings=SiteSettings.get_or_create(g.store.id),
        )

    # ----- АДМІНКА: КАТЕГОРІЇ (повний CRUD) -----

    @app.route("/admin/categories/<int:category_id>/edit", methods=["GET", "POST"])
    @admin_required
    def admin_categories_edit(category_id):
        """Редагування категорії."""
        category = Category.query.filter_by(id=category_id, store_id=g.store.id).first_or_404()

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            slug = request.form.get("slug", "").strip()
            description = request.form.get("description", "").strip()

            if not name or not slug:
                flash(_("Назва і slug категорії обовʼязкові."), "danger")
            else:
                # Перевіряємо, чи slug не зайнятий іншою категорією цього ж магазину
                exists = Category.query.filter(
                    Category.slug == slug,
                    Category.store_id == g.store.id,
                    Category.id != category_id
                ).first()
                if exists:
                    flash(_("Категорія з таким slug уже існує."), "warning")
                else:
                    category.name = name
                    category.slug = slug
                    category.description = description or None
                    db.session.commit()
                    flash(_("Категорія оновлена."), "success")
                    return redirect(url_for("admin_categories"))

        return render_template("admin/category_edit.html", category=category)

    @app.route("/admin/categories/<int:category_id>/delete", methods=["POST"])
    @admin_required
    def admin_categories_delete(category_id):
        """Видалення категорії."""
        category = Category.query.filter_by(id=category_id, store_id=g.store.id).first_or_404()

        # Видаляємо зображення категорії
        if category.image_url:
            delete_old_image(category.image_url)

        # Товари в цій категорії стануть без категорії
        Product.query.filter_by(category_id=category_id, store_id=g.store.id).update({"category_id": None})
        db.session.delete(category)
        db.session.commit()
        flash(_("Категорія видалена. Товари залишились без категорії."), "info")
        return redirect(url_for("admin_categories"))

    # ----- АДМІНКА: СТАТИСТИКА -----

    @app.route("/admin/stats")
    @admin_required
    def admin_stats():
        total_orders = Order.query.filter_by(store_id=g.store.id).count()
        paid_orders = Order.query.filter_by(status="paid", store_id=g.store.id).count()
        total_revenue = (
            db.session.query(db.func.coalesce(db.func.sum(Order.amount), 0.0))
            .filter(Order.status == "paid", Order.store_id == g.store.id)
            .scalar()
        )
        latest_orders = (
            Order.query.filter_by(store_id=g.store.id).order_by(Order.created_at.desc()).limit(20).all()
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

        query = Order.query.filter_by(store_id=g.store.id).order_by(Order.created_at.desc())

        if status_filter:
            query = query.filter(Order.status == status_filter)

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        orders = pagination.items

        # Статистика
        stats = {
            "total": Order.query.filter_by(store_id=g.store.id).count(),
            "paid": Order.query.filter_by(status="paid", store_id=g.store.id).count(),
            "pending": Order.query.filter_by(status="pending", store_id=g.store.id).count(),
            "revenue": db.session.query(db.func.coalesce(db.func.sum(Order.amount), 0.0))
                .filter(Order.status == "paid", Order.store_id == g.store.id).scalar(),
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
        order = Order.query.filter_by(id=order_id, store_id=g.store.id).first_or_404()
        return render_template("admin/order_detail.html", order=order)

    @app.route("/admin/orders/<int:order_id>/status", methods=["POST"])
    @admin_required
    def admin_order_update_status(order_id):
        """Оновити статус замовлення."""
        order = Order.query.filter_by(id=order_id, store_id=g.store.id).first_or_404()
        new_status = request.form.get("status", "").strip()
        old_status = order.status
        
        valid_statuses = ["created", "pending", "paid", "shipped", "delivered", "cancelled"]
        if new_status in valid_statuses:
            order.status = new_status
            db.session.commit()
            
            # Відправити email про зміну статусу
            if order.email and old_status != new_status:
                try:
                    from services.email_service import send_order_status_update
                    send_order_status_update(order.email, order, old_status, new_status)
                    app.logger.info(f'Order status email sent to {order.email}')
                except Exception as e:
                    app.logger.error(f'Failed to send order status email: {str(e)}')
            
            # Якщо статус змінився на "paid" - створюємо завдання для складу
            if new_status == "paid" and old_status != "paid":
                try:
                    from models.warehouse import WarehouseTask
                    existing_task = WarehouseTask.query.filter_by(order_id=order.id).first()
                    if not existing_task:
                        task = WarehouseTask.create_from_order(
                            order_id=order.id,
                            priority=2 if getattr(order, 'is_b2b', False) else 3,
                            notes=getattr(order, 'notes', '') or '',
                        )
                        flash(_("📦 Завдання для складу #%(task_number)s створено!") % {"task_number": task.task_number}, "info")
                except Exception as e:
                    print(f"Error creating warehouse task: {e}")
            
            flash(_("Статус змінено на «%(status)s».") % {"status": new_status}, "success")
        else:
            flash(_("Невірний статус."), "danger")
        
        return redirect(url_for("admin_order_detail", order_id=order_id))

    @app.route("/admin/orders/<int:order_id>/notes", methods=["POST"])
    @admin_required
    def admin_order_update_notes(order_id):
        """Оновити нотатки замовлення."""
        order = Order.query.filter_by(id=order_id, store_id=g.store.id).first_or_404()
        order.notes = request.form.get("notes", "").strip() or None
        db.session.commit()
        flash(_("Нотатки збережено."), "success")
        return redirect(url_for("admin_order_detail", order_id=order_id))

    @app.route("/admin/orders/<int:order_id>/delete", methods=["POST"])
    @admin_required
    def admin_order_delete(order_id):
        """Видалити замовлення."""
        order = Order.query.filter_by(id=order_id, store_id=g.store.id).first_or_404()
        # Видаляємо товари замовлення
        OrderItem.query.filter_by(order_id=order_id, store_id=g.store.id).delete()
        db.session.delete(order)
        db.session.commit()
        flash(_("Замовлення видалено."), "info")
        return redirect(url_for("admin_orders"))

    # ----- АДМІНКА: КОНТАКТИ -----

    @app.route("/admin/contacts")
    @admin_required
    def admin_contacts():
        """Список заявок з форми контактів."""
        page = request.args.get("page", 1, type=int)
        per_page = 20

        pagination = ContactMessage.query.filter_by(store_id=g.store.id).order_by(
            ContactMessage.is_read.asc(),
            ContactMessage.created_at.desc()
        ).paginate(page=page, per_page=per_page, error_out=False)

        contacts = pagination.items

        # Статистика
        today = datetime.utcnow().date()
        stats = {
            "total": ContactMessage.query.filter_by(store_id=g.store.id).count(),
            "unread": ContactMessage.query.filter_by(is_read=False, store_id=g.store.id).count(),
            "today": ContactMessage.query.filter(
                db.func.date(ContactMessage.created_at) == today,
                ContactMessage.store_id == g.store.id,
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
        contact = ContactMessage.query.filter_by(id=contact_id, store_id=g.store.id).first_or_404()
        contact.is_read = True
        db.session.commit()
        flash(_("Заявку позначено як прочитану."), "success")
        return redirect(url_for("admin_contacts"))

    @app.route("/admin/contacts/<int:contact_id>/delete", methods=["POST"])
    @admin_required
    def admin_contact_delete(contact_id):
        """Видалити заявку."""
        contact = ContactMessage.query.filter_by(id=contact_id, store_id=g.store.id).first_or_404()
        db.session.delete(contact)
        db.session.commit()
        flash(_("Заявку видалено."), "info")
        return redirect(url_for("admin_contacts"))

    @app.route("/admin/contacts/mark-all-read", methods=["POST"])
    @admin_required
    def admin_contacts_mark_all_read():
        """Позначити всі заявки як прочитані."""
        ContactMessage.query.filter_by(is_read=False, store_id=g.store.id).update({"is_read": True})
        db.session.commit()
        flash(_("Усі заявки позначено як прочитані."), "success")
        return redirect(url_for("admin_contacts"))

    @app.route("/admin/contacts/delete-read", methods=["POST"])
    @admin_required
    def admin_contacts_delete_read():
        """Видалити всі прочитані заявки."""
        ContactMessage.query.filter_by(is_read=True, store_id=g.store.id).delete()
        db.session.commit()
        flash(_("Прочитані заявки видалено."), "info")
        return redirect(url_for("admin_contacts"))

    # ----- АДМІНКА: НАЛАШТУВАННЯ САЙТУ -----

    @app.route("/admin/settings", methods=["GET", "POST"])
    @admin_required
    def admin_settings():
        """Глобальні налаштування сайту."""
        settings = SiteSettings.get_or_create(g.store.id)

        if request.method == "POST":
            # Основні
            settings.site_name = request.form.get("site_name") or None
            settings.site_tagline = request.form.get("site_tagline") or None

            # Дизайн вітрини - валідуємо проти фіксованого набору пресетів,
            # ніколи не приймаємо довільне значення від форми.
            from services.theme_presets import THEME_PRESETS, FONT_PRESETS, HOMEPAGE_LAYOUTS
            posted_theme = request.form.get("theme_preset", "")
            if posted_theme in THEME_PRESETS:
                settings.theme_preset = posted_theme
            posted_font = request.form.get("font_preset", "")
            if posted_font in FONT_PRESETS:
                settings.font_preset = posted_font
            posted_layout = request.form.get("homepage_layout", "")
            if posted_layout in HOMEPAGE_LAYOUTS:
                settings.homepage_layout = posted_layout

            # Зображення (лого/фавікон/банер/фото "Про нас") - видаляємо старе
            # завантажене зображення з БД, якщо власник замінив його на нове.
            # Одна й та сама картинка теоретично може бути використана одразу
            # в кількох полях - не видаляємо її, поки хоч одне поле все ще
            # на неї посилається після збереження.
            image_fields = ("logo_url", "favicon_url", "hero_image_url", "about_image_url")
            new_image_values = {f: request.form.get(f, "").strip() or None for f in image_fields}
            for image_field in image_fields:
                new_url = new_image_values[image_field]
                old_url = getattr(settings, image_field)
                if new_url != old_url and old_url and old_url not in new_image_values.values():
                    delete_old_image(old_url)
                setattr(settings, image_field, new_url)


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
                    flash(_("Пароль має бути мінімум 6 символів."), "warning")
                elif new_password != confirm_password:
                    flash(_("Паролі не співпадають."), "warning")
                else:
                    settings.admin_password_hash = generate_password_hash(new_password)
                    flash(_("Пароль адміністратора змінено."), "success")
            
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

            # Юридичні тексти (Datenschutz/AGB) - порожнє поле повертає сторінку
            # до загального шаблонного тексту (не перезаписує його порожнечею).
            settings.privacy_policy_text = request.form.get("privacy_policy_text") or None
            settings.terms_text = request.form.get("terms_text") or None

            db.session.commit()
            flash(_("Налаштування сайту збережено."), "success")
            return redirect(url_for("admin_settings"))

        from services.theme_presets import THEME_PRESETS, FONT_PRESETS, HOMEPAGE_LAYOUTS
        return render_template(
            "admin/settings.html",
            settings=settings,
            theme_presets=THEME_PRESETS,
            font_presets=FONT_PRESETS,
            homepage_layouts=HOMEPAGE_LAYOUTS,
        )

    # ----- АДМІНКА: ВЛАСНИЙ ДОМЕН МАГАЗИНУ -----

    TRAEFIK_DYNAMIC_DIR = os.environ.get("TRAEFIK_DYNAMIC_DIR", "/app/traefik-dynamic")

    def _custom_domain_router_path(store_id):
        return os.path.join(TRAEFIK_DYNAMIC_DIR, f"custom-{store_id}.yml")

    def _write_custom_domain_router(store):
        """Реєструє власний домен магазину в Traefik через файловий провайдер -
        Traefik стежить за цією директорією (--providers.file.watch=true) і
        підхоплює новий роутер за кілька секунд, без перезапуску контейнера.
        Сертифікат для цього домену Traefik запитає автоматично при першому
        HTTPS-запиті (HTTP-01, оскільки чужий домен не в нашій DNS-зоні)."""
        if not os.path.isdir(TRAEFIK_DYNAMIC_DIR):
            app.logger.warning(f"TRAEFIK_DYNAMIC_DIR {TRAEFIK_DYNAMIC_DIR} не існує - пропускаю реєстрацію домену в Traefik")
            return
        router_name = f"custom-{store.id}"
        content = f"""http:
  routers:
    {router_name}:
      rule: "Host(`{store.custom_domain}`)"
      service: "smartshop@docker"
      entryPoints:
        - websecure
      tls:
        certResolver: letsencrypt
"""
        with open(_custom_domain_router_path(store.id), "w", encoding="utf-8") as f:
            f.write(content)

    def _remove_custom_domain_router(store_id):
        path = _custom_domain_router_path(store_id)
        if os.path.exists(path):
            os.remove(path)

    @app.route("/admin/settings/domain", methods=["GET", "POST"])
    @admin_required
    def admin_domain_settings():
        """Прив'язка власного домену клієнта (напр. myshop.com) до магазину."""
        store = g.store
        platform_ip = os.environ.get("PLATFORM_IP", "").strip()

        if request.method == "POST":
            action = request.form.get("action")

            if action == "save":
                new_domain = request.form.get("custom_domain", "").strip().lower()
                for prefix in ("https://", "http://"):
                    if new_domain.startswith(prefix):
                        new_domain = new_domain[len(prefix):]
                new_domain = new_domain.rstrip("/") or None

                if new_domain != store.custom_domain:
                    if store.custom_domain:
                        _remove_custom_domain_router(store.id)
                    store.custom_domain = new_domain
                    store.custom_domain_verified = False
                    store.custom_domain_verified_at = None
                    db.session.commit()
                    if new_domain:
                        flash(_("Домен збережено. Тепер налаштуйте DNS і натисніть «Перевірити»."), "info")
                    else:
                        flash(_("Власний домен видалено."), "info")
                return redirect(url_for("admin_domain_settings"))

            elif action == "verify":
                if not store.custom_domain:
                    flash(_("Спочатку вкажіть домен."), "danger")
                    return redirect(url_for("admin_domain_settings"))

                if not platform_ip:
                    flash(_("Платформа ще не налаштувала перевірку доменів. Зверніться до підтримки."), "danger")
                    return redirect(url_for("admin_domain_settings"))

                import socket
                try:
                    resolved_ips = {info[4][0] for info in socket.getaddrinfo(store.custom_domain, None)}
                except Exception as e:
                    resolved_ips = set()
                    app.logger.info(f"Custom domain DNS lookup failed for {store.custom_domain}: {e}")

                if platform_ip in resolved_ips:
                    store.custom_domain_verified = True
                    store.custom_domain_verified_at = datetime.utcnow()
                    db.session.commit()
                    _write_custom_domain_router(store)
                    flash(_("✅ Домен %(domain)s підтверджено і активовано! Може знадобитись кілька хвилин, щоб з'явився сертифікат.") % {"domain": store.custom_domain}, "success")
                else:
                    store.custom_domain_verified = False
                    db.session.commit()
                    resolved_display = ", ".join(resolved_ips) if resolved_ips else "не резолвиться взагалі"
                    flash(
                        _("Домен ще не вказує на платформу (зараз резолвиться: %(resolved)s). "
                          "Перевірте DNS-налаштування (A-запис на %(ip)s) і спробуйте ще раз за кілька хвилин.")
                        % {"resolved": resolved_display, "ip": platform_ip},
                        "warning",
                    )
                return redirect(url_for("admin_domain_settings"))

        return render_template("admin/domain_settings.html", store=store, platform_ip=platform_ip)

    # ----- АДМІНКА: STRIPE CONNECT (ПРИЙОМ ОПЛАТ ВІД КЛІЄНТІВ МАГАЗИНУ) -----
    # На відміну від stripe_customer_id/stripe_subscription_id (це підписка
    # МАГАЗИНУ на платформу), тут йдеться про власний Stripe Express-акаунт
    # магазину, підключений через Connect. Оплати клієнтів магазину проводяться
    # destination charge (checkout() нижче передає transfer_data.destination) -
    # кошти йдуть напряму власнику магазину, платформа їх не утримує і не бере
    # комісії.

    STRIPE_CONNECT_COUNTRIES = [
        ("DE", "Німеччина"), ("AT", "Австрія"), ("FR", "Франція"),
        ("NL", "Нідерланди"), ("ES", "Іспанія"), ("IT", "Італія"),
        ("PL", "Польща"), ("GB", "Велика Британія"), ("US", "США"),
    ]

    def _create_connect_account_link(store):
        return stripe.AccountLink.create(
            account=store.stripe_connect_account_id,
            refresh_url=url_for("admin_payments_refresh", _external=True),
            return_url=url_for("admin_payments_return", _external=True),
            type="account_onboarding",
        )

    @app.route("/admin/settings/payments", methods=["GET"])
    @admin_required
    def admin_payments_settings():
        """Підключення Stripe Connect для прийому оплат від клієнтів магазину."""
        return render_template(
            "admin/payments_settings.html",
            store=g.store,
            countries=STRIPE_CONNECT_COUNTRIES,
            stripe_configured=STRIPE_AVAILABLE and bool(app.config["STRIPE_SECRET_KEY"]),
        )

    @app.route("/admin/settings/payments/connect", methods=["POST"])
    @admin_required
    def admin_payments_connect():
        store = g.store
        if not STRIPE_AVAILABLE or not app.config["STRIPE_SECRET_KEY"]:
            flash(_("Stripe не налаштовано на платформі."), "danger")
            return redirect(url_for("admin_payments_settings"))

        country = (request.form.get("country") or "DE").strip().upper()

        try:
            if not store.stripe_connect_account_id:
                account = stripe.Account.create(
                    type="express",
                    country=country,
                    email=current_user.email,
                    capabilities={"transfers": {"requested": True}},
                    business_profile={"name": store.name} if store.name else None,
                )
                store.stripe_connect_account_id = account.id
                db.session.commit()

            account_link = _create_connect_account_link(store)
            return redirect(account_link.url)
        except stripe.error.StripeError as e:
            flash(_("Помилка Stripe Connect: %(error)s") % {"error": e}, "danger")
            return redirect(url_for("admin_payments_settings"))

    @app.route("/admin/settings/payments/refresh")
    @admin_required
    def admin_payments_refresh():
        """Stripe перенаправляє сюди, якщо посилання на онбординг застаріло."""
        store = g.store
        if not store.stripe_connect_account_id:
            return redirect(url_for("admin_payments_settings"))
        try:
            account_link = _create_connect_account_link(store)
            return redirect(account_link.url)
        except stripe.error.StripeError as e:
            flash(_("Помилка Stripe Connect: %(error)s") % {"error": e}, "danger")
            return redirect(url_for("admin_payments_settings"))

    @app.route("/admin/settings/payments/return")
    @admin_required
    def admin_payments_return():
        """Stripe перенаправляє сюди після (спроби) завершення онбордингу."""
        store = g.store
        if store.stripe_connect_account_id and STRIPE_AVAILABLE and app.config["STRIPE_SECRET_KEY"]:
            try:
                account = stripe.Account.retrieve(store.stripe_connect_account_id)
                transfers_active = (account.get("capabilities") or {}).get("transfers") == "active"
                store.stripe_connect_charges_enabled = bool(transfers_active)
                if transfers_active and not store.stripe_connect_onboarded_at:
                    store.stripe_connect_onboarded_at = datetime.utcnow()
                db.session.commit()
                if transfers_active:
                    flash(_("✅ Stripe підключено! Тепер ви можете приймати оплати від клієнтів."), "success")
                else:
                    flash(_("Реєстрацію в Stripe ще не завершено. Заповніть усі необхідні дані та спробуйте ще раз."), "warning")
            except stripe.error.StripeError as e:
                flash(_("Не вдалося перевірити статус Stripe: %(error)s") % {"error": e}, "danger")
        return redirect(url_for("admin_payments_settings"))

    @app.route("/admin/settings/payments/reset", methods=["POST"])
    @admin_required
    def admin_payments_reset():
        """Відв'язати поточний Connect-акаунт від магазину (сам акаунт у Stripe не видаляється)."""
        store = g.store
        store.stripe_connect_account_id = None
        store.stripe_connect_charges_enabled = False
        store.stripe_connect_onboarded_at = None
        db.session.commit()
        flash(_("Stripe-акаунт відв'язано від магазину."), "info")
        return redirect(url_for("admin_payments_settings"))

    # ----- АДМІНКА: ВИДАЛЕННЯ АКАУНТУ (GDPR "право на забуття") -----
    # Магазин фізично НЕ видаляється з БД - фінансові записи (замовлення)
    # мають зберігатись знеособленими для податкової звітності (GDPR ст.17.3
    # прямо дозволяє цей виняток). Знеособлюємо персональні дані клієнтів і
    # власника, скасовуємо підписку, звільняємо slug/домен, ховаємо магазин
    # від резолюції (is_deleted) - фактично це остаточне й незворотне
    # відключення магазину від платформи.

    def _delete_store_account(store):
        from models.shipping import CarrierAccount
        from models.order import Order
        from models.company import Company
        from models.user import User
        from models.store import StoreSubscriptionStatus

        if store.stripe_subscription_id and STRIPE_AVAILABLE and app.config["STRIPE_SECRET_KEY"]:
            try:
                stripe.Subscription.delete(store.stripe_subscription_id)
            except stripe.error.StripeError as e:
                app.logger.warning(f"Не вдалося скасувати Stripe-підписку магазину #{store.id}: {e}")

        if store.custom_domain:
            _remove_custom_domain_router(store.id)

        # Знеособлюємо замовлення - суми/статуси/номери лишаються (податковий облік).
        Order.query.filter_by(store_id=store.id).update({
            Order.customer_name: None,
            Order.customer_email: None,
            Order.customer_phone: None,
            Order.shipping_address: None,
            Order.shipping_city: None,
            Order.shipping_postal_code: None,
        }, synchronize_session=False)

        # Знеособлюємо контактну особу B2B-партнерів - юрдані (VAT, назва) лишаються.
        Company.query.filter_by(store_id=store.id).update({
            Company.contact_person: None,
            Company.contact_email: None,
            Company.contact_phone: None,
            Company.address: None,
            Company.website: None,
            Company.domain: None,
            Company.whois_data: None,
        }, synchronize_session=False)

        # Облікові дані перевізників (API-ключі) - видаляємо повністю, це секрети.
        CarrierAccount.query.filter_by(store_id=store.id).delete(synchronize_session=False)

        # Знеособлюємо усіх користувачів магазину (власник + клієнти/менеджери).
        user_ids = {store.owner_user_id}
        user_ids.update(
            uid for (uid,) in db.session.query(User.id).filter_by(store_id=store.id).all()
        )
        for user in User.query.filter(User.id.in_(user_ids)).all():
            user.email = f"deleted-user-{user.id}@deleted.local"
            user.set_password(uuid.uuid4().hex)
            user.first_name = None
            user.last_name = None
            user.phone = None

        store.is_deleted = True
        store.deleted_at = datetime.utcnow()
        store.is_active = False
        store.name = f"Видалений магазин #{store.id}"
        store.slug = f"deleted-{store.id}-{uuid.uuid4().hex[:8]}"
        store.custom_domain = None
        store.custom_domain_verified = False
        store.custom_domain_verified_at = None
        store.stripe_customer_id = None
        store.stripe_subscription_id = None
        store.stripe_connect_account_id = None
        store.stripe_connect_charges_enabled = False
        store.subscription_status = StoreSubscriptionStatus.CANCELED

        db.session.commit()

    @app.route("/admin/settings/account", methods=["GET", "POST"])
    @admin_required
    def admin_delete_account():
        """Самостійне видалення акаунту-магазину власником (GDPR)."""
        store = g.store
        if current_user.id != store.owner_user_id:
            abort(403)

        if request.method == "POST":
            password = request.form.get("password", "")
            confirm = request.form.get("confirm") == "on"
            if not confirm:
                flash(_("Підтвердіть, що розумієте наслідки видалення."), "danger")
                return redirect(url_for("admin_delete_account"))
            if not current_user.check_password(password):
                flash(_("Невірний пароль."), "danger")
                return redirect(url_for("admin_delete_account"))

            _delete_store_account(store)

            from flask_login import logout_user as flask_logout_user
            flask_logout_user()
            flash(_("Ваш акаунт і магазин видалено. Дякуємо, що були з нами."), "info")

            # Перенаправляємо на корневий домен без піддомену, щоб уникнути 404
            # (поточний піддомен більше не дійсний, оскільки магазин видалено)
            if BASE_DOMAIN:
                return redirect(f"https://{BASE_DOMAIN}/")
            return redirect(url_for("index"))

        return render_template("admin/delete_account.html", store=store)

    # ----- АДМІНКА: НАЛАШТУВАННЯ ДОСТАВКИ (DHL/UPS) -----

    @app.route("/admin/settings/shipping", methods=["GET", "POST"])
    @admin_required
    def admin_shipping_settings():
        """Список налаштованих служб доставки магазину + самовивіз."""
        from models.shipping import CarrierAccount, Carrier
        settings = SiteSettings.get_or_create(g.store.id)

        if request.method == "POST":
            settings.pickup_enabled = request.form.get("pickup_enabled") == "on"
            settings.pickup_address = request.form.get("pickup_address", "").strip() or None
            settings.pickup_instructions = request.form.get("pickup_instructions", "").strip() or None
            db.session.commit()
            flash(_("Налаштування самовивозу збережено."), "success")
            return redirect(url_for("admin_shipping_settings"))

        accounts = CarrierAccount.query.filter_by(store_id=g.store.id).all()
        configured_carriers = {a.carrier for a in accounts}
        available_carriers = [c for c in Carrier.CHOICES if c not in configured_carriers]
        return render_template(
            "admin/shipping_settings.html",
            settings=settings,
            accounts=accounts,
            available_carriers=available_carriers,
            carrier_labels=Carrier.LABELS,
        )

    @app.route("/admin/settings/shipping/new", methods=["GET", "POST"])
    @admin_required
    def admin_shipping_account_new():
        """Додати обліковий запис перевізника (DHL/UPS)."""
        from models.shipping import CarrierAccount, Carrier

        carrier = request.args.get("carrier") or request.form.get("carrier", "")
        if carrier not in Carrier.CHOICES:
            flash(_("Невідома служба доставки."), "danger")
            return redirect(url_for("admin_shipping_settings"))

        if CarrierAccount.query.filter_by(store_id=g.store.id, carrier=carrier).first():
            flash(_("%(carrier)s вже налаштовано для цього магазину.") % {"carrier": Carrier.LABELS.get(carrier, carrier)}, "warning")
            return redirect(url_for("admin_shipping_settings"))

        if request.method == "POST":
            is_sandbox = request.form.get("is_sandbox") == "on"
            if carrier == Carrier.DHL:
                credentials = {
                    "api_key": request.form.get("api_key", "").strip(),
                    "api_secret": request.form.get("api_secret", "").strip(),
                    "account_number": request.form.get("account_number", "").strip(),
                }
            else:  # ups
                credentials = {
                    "client_id": request.form.get("client_id", "").strip(),
                    "client_secret": request.form.get("client_secret", "").strip(),
                    "account_number": request.form.get("account_number", "").strip(),
                }

            account = CarrierAccount(
                store_id=g.store.id,
                carrier=carrier,
                is_enabled=True,
                is_sandbox=is_sandbox,
                credentials=credentials,
                origin_name=request.form.get("origin_name", "").strip() or None,
                origin_phone=request.form.get("origin_phone", "").strip() or None,
                origin_street=request.form.get("origin_street", "").strip() or None,
                origin_city=request.form.get("origin_city", "").strip() or None,
                origin_postal_code=request.form.get("origin_postal_code", "").strip() or None,
                origin_country_code=(request.form.get("origin_country_code", "").strip() or None),
            )
            db.session.add(account)
            db.session.commit()
            flash(_("%(carrier)s налаштовано.") % {"carrier": account.carrier_label}, "success")
            return redirect(url_for("admin_shipping_settings"))

        return render_template("admin/shipping_account_form.html", carrier=carrier, carrier_label=Carrier.LABELS.get(carrier, carrier), account=None)

    @app.route("/admin/settings/shipping/<int:id>/edit", methods=["GET", "POST"])
    @admin_required
    def admin_shipping_account_edit(id):
        """Редагувати обліковий запис перевізника."""
        from models.shipping import CarrierAccount, Carrier
        account = CarrierAccount.query.filter_by(id=id, store_id=g.store.id).first_or_404()

        if request.method == "POST":
            account.is_enabled = request.form.get("is_enabled") == "on"
            account.is_sandbox = request.form.get("is_sandbox") == "on"
            if account.carrier == Carrier.DHL:
                account.credentials = {
                    "api_key": request.form.get("api_key", "").strip(),
                    "api_secret": request.form.get("api_secret", "").strip(),
                    "account_number": request.form.get("account_number", "").strip(),
                }
            else:
                account.credentials = {
                    "client_id": request.form.get("client_id", "").strip(),
                    "client_secret": request.form.get("client_secret", "").strip(),
                    "account_number": request.form.get("account_number", "").strip(),
                }
            account.origin_name = request.form.get("origin_name", "").strip() or None
            account.origin_phone = request.form.get("origin_phone", "").strip() or None
            account.origin_street = request.form.get("origin_street", "").strip() or None
            account.origin_city = request.form.get("origin_city", "").strip() or None
            account.origin_postal_code = request.form.get("origin_postal_code", "").strip() or None
            account.origin_country_code = request.form.get("origin_country_code", "").strip() or None
            db.session.commit()
            flash(_("%(carrier)s оновлено.") % {"carrier": account.carrier_label}, "success")
            return redirect(url_for("admin_shipping_settings"))

        return render_template("admin/shipping_account_form.html", carrier=account.carrier, carrier_label=account.carrier_label, account=account)

    @app.route("/admin/settings/shipping/<int:id>/delete", methods=["POST"])
    @admin_required
    def admin_shipping_account_delete(id):
        """Видалити обліковий запис перевізника."""
        from models.shipping import CarrierAccount
        account = CarrierAccount.query.filter_by(id=id, store_id=g.store.id).first_or_404()
        db.session.delete(account)
        db.session.commit()
        flash(_("Обліковий запис видалено."), "info")
        return redirect(url_for("admin_shipping_settings"))

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
                return jsonify({"error": _("Заповніть обов'язкові поля")}), 400
            flash(_("Заповніть обов'язкові поля: ім'я, email, повідомлення."), "danger")
            return redirect(url_for("contacts_page"))
        
        contact = ContactMessage(
            store_id=g.store.id,
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
        
        flash(_("Дякуємо! Ваше повідомлення надіслано."), "success")
        return redirect(url_for("contacts_page"))

    # ----- AUTH: ВХІД/РЕЄСТРАЦІЯ B2C/B2B -----

    def _send_verification_email_for(user, locale=None):
        from services.email_service import send_verification_email_for_user
        send_verification_email_for_user(user, locale=locale)

    @app.route("/verify-email/<token>")
    def verify_email(token):
        """Підтвердження email за токеном з листа."""
        from services.tokens import verify_token, EMAIL_VERIFY_SALT, EMAIL_VERIFY_MAX_AGE
        email = verify_token(token, EMAIL_VERIFY_SALT, EMAIL_VERIFY_MAX_AGE)
        if not email:
            flash(_("Посилання для підтвердження email недійсне або протерміноване. Запросіть нове нижче."), "danger")
            return redirect(url_for("resend_verification"))

        user = User.get_by_email(email)
        if not user:
            flash(_("Користувача не знайдено."), "danger")
            return redirect(url_for("user_login"))

        if not user.is_verified:
            user.is_verified = True
            db.session.commit()
        flash(_("✅ Email підтверджено!"), "success")
        return redirect(url_for("user_cabinet") if current_user.is_authenticated else url_for("user_login"))

    @app.route("/resend-verification", methods=["GET", "POST"])
    @limiter.limit("5 per minute;15 per hour")
    def resend_verification():
        """Повторне надсилання листа підтвердження email."""
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            user = User.get_by_email(email)
            # Однакове повідомлення незалежно від того, чи існує акаунт -
            # щоб не давати змогу перебором дізнатись, які email зареєстровані.
            if user and not user.is_verified:
                _send_verification_email_for(user, locale=str(get_locale()))
            flash(_("Якщо цей email зареєстровано і ще не підтверджено, ми надіслали новий лист."), "info")
            return redirect(url_for("user_login"))
        settings = SiteSettings.get_or_create(g.store.id)
        return render_template("auth/resend_verification.html", settings=settings)

    @app.route("/reset-password", methods=["GET", "POST"])
    @limiter.limit("5 per minute;15 per hour")
    def reset_password_request():
        """Форма запиту скидання пароля - вводиться email."""
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            user = User.get_by_email(email)
            if user:
                from services.tokens import generate_token, PASSWORD_RESET_SALT
                token = generate_token(user.email, PASSWORD_RESET_SALT)
                reset_url = url_for("reset_password", token=token, _external=True)
                try:
                    from services.email_service import send_password_reset_email
                    send_password_reset_email(user.email, user.full_name, reset_url, locale=str(get_locale()))
                except Exception as e:
                    app.logger.error(f'Failed to send password reset email: {str(e)}')
            # Однакове повідомлення незалежно від існування акаунта -
            # захист від User enumeration через цю форму.
            flash(_("Якщо цей email зареєстровано, ми надіслали посилання для скидання пароля."), "info")
            return redirect(url_for("user_login"))
        settings = SiteSettings.get_or_create(g.store.id)
        return render_template("auth/reset_password_request.html", settings=settings)

    @app.route("/reset-password/<token>", methods=["GET", "POST"])
    @limiter.limit("10 per minute;30 per hour")
    def reset_password(token):
        """Встановлення нового пароля за токеном з листа."""
        from services.tokens import verify_token, PASSWORD_RESET_SALT, PASSWORD_RESET_MAX_AGE
        email = verify_token(token, PASSWORD_RESET_SALT, PASSWORD_RESET_MAX_AGE)
        if not email:
            flash(_("Посилання для скидання пароля недійсне або протерміноване. Запросіть нове."), "danger")
            return redirect(url_for("reset_password_request"))

        user = User.get_by_email(email)
        if not user:
            flash(_("Користувача не знайдено."), "danger")
            return redirect(url_for("reset_password_request"))

        settings = SiteSettings.get_or_create(g.store.id)

        if request.method == "POST":
            password = request.form.get("password", "")
            password_confirm = request.form.get("password_confirm", "")
            if not password or len(password) < 6:
                flash(_("Пароль має бути не менше 6 символів"), "danger")
                return render_template("auth/reset_password.html", token=token, settings=settings)
            if password != password_confirm:
                flash(_("Паролі не співпадають"), "danger")
                return render_template("auth/reset_password.html", token=token, settings=settings)

            user.set_password(password)
            db.session.commit()
            flash(_("✅ Пароль оновлено! Тепер ви можете увійти."), "success")
            return redirect(url_for("user_login"))

        return render_template("auth/reset_password.html", token=token, settings=settings)

    @app.route("/login", methods=["GET", "POST"])
    @limiter.limit("15 per minute;50 per hour")
    def user_login():
        """Сторінка входу для користувачів."""
        if current_user.is_authenticated:
            if current_user.is_platform_owner:
                return redirect(url_for("platform_admin.dashboard"))
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
                    flash(_("Ваш акаунт деактивовано. Зверніться до підтримки."), "danger")
                    return render_template("auth/login.html")
                
                from flask_login import login_user as flask_login_user
                flask_login_user(user, remember=remember)
                user.update_last_login()
                
                flash(_("Вітаємо, %(name)s!") % {"name": user.full_name}, "success")
                
                next_page = request.args.get("next")
                if next_page:
                    return redirect(next_page)
                
                if user.is_platform_owner:
                    return redirect(url_for("platform_admin.dashboard"))
                elif user.is_admin or user.is_manager:
                    return redirect(url_for("admin_dashboard"))
                elif user.is_b2b:
                    return redirect(url_for("b2b_dashboard"))

                return redirect(url_for("user_cabinet"))
            
            flash(_("Невірний email або пароль."), "danger")
        
        settings = SiteSettings.get_or_create(g.store.id)
        return render_template("auth/login.html", settings=settings)

    @app.route("/logout")
    @login_required
    def user_logout():
        """Вихід з системи."""
        from flask_login import logout_user as flask_logout_user
        flask_logout_user()
        flash(_("Ви успішно вийшли з системи."), "info")
        return redirect(url_for("user_login"))

    @app.route("/register", methods=["GET", "POST"])
    @limiter.limit("10 per minute;30 per hour")
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
                errors.append(_("Email обов'язковий"))
            elif User.get_by_email(email):
                errors.append(_("Користувач з таким email вже існує"))
            
            if not password:
                errors.append(_("Пароль обов'язковий"))
            elif len(password) < 6:
                errors.append(_("Пароль має бути не менше 6 символів"))
            elif password != password_confirm:
                errors.append(_("Паролі не співпадають"))
            
            if errors:
                for error in errors:
                    flash(error, "danger")
                settings = SiteSettings.get_or_create(g.store.id)
                return render_template("auth/register.html", settings=settings)
            
            user = User.create_user(
                email=email,
                password=password,
                role=UserRole.CUSTOMER,
                first_name=first_name or None,
                last_name=last_name or None,
                phone=phone or None,
                store_id=g.store.id,
            )
            
            # Відправити welcome email
            try:
                from services.email_service import send_registration_email
                user_name = f"{first_name} {last_name}".strip() or "Клієнт"
                send_registration_email(email, user_name, locale=str(get_locale()))
                app.logger.info(f'Registration email sent to {email}')
            except Exception as e:
                app.logger.error(f'Failed to send registration email: {str(e)}')

            _send_verification_email_for(user, locale=str(get_locale()))

            from flask_login import login_user as flask_login_user
            flask_login_user(user)
            flash(_("Реєстрація успішна! Ласкаво просимо!"), "success")
            return redirect(url_for("user_cabinet"))
        
        settings = SiteSettings.get_or_create(g.store.id)
        return render_template("auth/register.html", settings=settings)

    @app.route("/register/b2b", methods=["GET", "POST"])
    @limiter.limit("10 per minute;30 per hour")
    def user_register_b2b():
        """Реєстрація B2B партнера."""
        if current_user.is_authenticated:
            return redirect(url_for("b2b_dashboard"))
        
        settings = SiteSettings.get_or_create(g.store.id)
        if not getattr(settings, 'b2b_registration_open', True):
            flash(_("B2B реєстрація тимчасово закрита."), "warning")
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
                errors.append(_("Email обов'язковий"))
            elif User.get_by_email(email):
                errors.append(_("Користувач з таким email вже існує"))
            
            if not password:
                errors.append(_("Пароль обов'язковий"))
            elif len(password) < 8:
                errors.append(_("Пароль має бути не менше 8 символів"))
            elif password != password_confirm:
                errors.append(_("Паролі не співпадають"))
            
            if not company_name:
                errors.append(_("Назва компанії обов'язкова"))
            
            if not first_name or not last_name:
                errors.append(_("Ім'я та прізвище контактної особи обов'язкові"))
            
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
                        flash(_("✅ VAT номер підтверджено!"), "success")
                    else:
                        flash(_("⚠️ VAT не підтверджено: %(error)s") % {"error": vat_result.get('error', '')}, "warning")
                except Exception as e:
                    flash(_("⚠️ Помилка перевірки VAT: %(error)s") % {"error": str(e)}, "warning")
            
            # Створення компанії
            company = Company(
                store_id=g.store.id,
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
                store_id=g.store.id,
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()

            # Відправити email залежно від статусу
            try:
                from services.email_service import send_b2b_verification_pending, send_b2b_verification_approved
                reg_locale = str(get_locale())
                if company.is_verified:
                    send_b2b_verification_approved(email, company_name, company.discount_percent or 0, locale=reg_locale)
                    app.logger.info(f'B2B approval email sent to {email}')
                else:
                    send_b2b_verification_pending(email, company_name, locale=reg_locale)
                    app.logger.info(f'B2B pending email sent to {email}')
            except Exception as e:
                app.logger.error(f'Failed to send B2B email: {str(e)}')

            _send_verification_email_for(user, reg_locale)

            from flask_login import login_user as flask_login_user
            flask_login_user(user)
            
            if company.is_verified:
                flash(_("✅ Реєстрація успішна! Ваша компанія верифікована."), "success")
            else:
                flash(_("📋 Реєстрація успішна! Ваша заявка на розгляді."), "info")
            
            return redirect(url_for("b2b_dashboard"))
        
        return render_template("auth/register_b2b.html", settings=settings)

    # ----- API: ПЕРЕВІРКА VAT -----

    @app.route("/api/verify-vat", methods=["POST"])
    def api_verify_vat():
        """AJAX перевірка VAT номера."""
        data = request.get_json() if request.is_json else request.form
        vat_number = data.get("vat_number", "").strip()
        
        if not vat_number:
            return jsonify({"error": _("VAT номер обов'язковий")}), 400
        
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
        
        settings = SiteSettings.get_or_create(g.store.id)
        
        # Статистика (тільки замовлення в межах поточного магазину)
        total_orders = Order.query.filter_by(customer_email=current_user.email, store_id=g.store.id).count()
        recent_orders = Order.query.filter_by(customer_email=current_user.email, store_id=g.store.id)\
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
        
        settings = SiteSettings.get_or_create(g.store.id)
        company = current_user.company
        
        # Статистика (в межах поточного магазину)
        total_orders = Order.query.filter_by(customer_email=current_user.email, store_id=g.store.id).count()
        pending_orders = Order.query.filter_by(customer_email=current_user.email, status="pending", store_id=g.store.id).count()
        total_spent = db.session.query(db.func.coalesce(db.func.sum(Order.amount), 0.0))\
            .filter_by(customer_email=current_user.email, status="paid", store_id=g.store.id).scalar()

        discount = company.discount_percent if company else 0

        recent_orders = Order.query.filter_by(customer_email=current_user.email, store_id=g.store.id)\
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
        
        settings = SiteSettings.get_or_create(g.store.id)
        
        orders = Order.query.filter_by(customer_email=current_user.email, store_id=g.store.id)\
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
        
        settings = SiteSettings.get_or_create(g.store.id)
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
            flash(_("Дані компанії оновлено!"), "success")
            return redirect(url_for("b2b_company"))
        
        return render_template(
            "cabinet/b2b/company.html",
            settings=settings,
            company=company,
        )

    # ========== CRM ADMIN ROUTES ==========
    # Company/AdminAlert тепер tenant-scoped (store_id), Phase 2 завершено.

    @app.route("/admin/crm")
    @admin_required
    def admin_crm():
        """CRM - список партнерів."""
        settings = SiteSettings.get_or_create(g.store.id)

        # Фільтри
        filter_status = request.args.get("status", "")
        filter_reliability = request.args.get("reliability", "")
        filter_country = request.args.get("country", "")
        search = request.args.get("search", "")
        page = request.args.get("page", 1, type=int)
        per_page = 20

        # Базовий запит (тільки компанії поточного магазину)
        query = Company.query.filter_by(store_id=g.store.id)

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
        all_companies = Company.query.filter_by(store_id=g.store.id).all()
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
            is_resolved=False,
            store_id=g.store.id,
        ).order_by(AdminAlert.created_at.desc()).all()
        unread_alerts_count = AdminAlert.query.filter_by(is_read=False, store_id=g.store.id).count()

        # Унікальні країни
        countries = db.session.query(Company.country_code, Company.country).distinct().filter(
            Company.country_code.isnot(None),
            Company.store_id == g.store.id,
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
        settings = SiteSettings.get_or_create(g.store.id)
        company = Company.query.filter_by(id=id, store_id=g.store.id).first_or_404()

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
        company = Company.query.filter_by(id=id, store_id=g.store.id).first_or_404()
        
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
        company = Company.query.filter_by(id=id, store_id=g.store.id).first_or_404()
        company.status = "verified"
        company.verified_at = datetime.utcnow()
        db.session.commit()
        
        # Відправити email про успішну верифікацію
        if company.contact_email:
            try:
                from services.email_service import send_b2b_verification_approved
                send_b2b_verification_approved(
                    company.contact_email, 
                    company.name,
                    company.discount_percent or 0
                )
                app.logger.info(f'B2B approval email sent to {company.contact_email}')
            except Exception as e:
                app.logger.error(f'Failed to send B2B approval email: {str(e)}')
        
        return jsonify({"success": True})
    
    @app.route("/admin/crm/partner/<int:id>/reject", methods=["POST"])
    @admin_required
    def admin_crm_partner_reject(id):
        """Відхилити партнера."""
        data = request.get_json() or {}
        company = Company.query.filter_by(id=id, store_id=g.store.id).first_or_404()
        company.status = "rejected"
        company.rejection_reason = data.get("reason", "")
        db.session.commit()
        
        # Відправити email про відхилення
        if company.contact_email:
            try:
                from services.email_service import send_b2b_verification_rejected
                send_b2b_verification_rejected(
                    company.contact_email,
                    company.name,
                    company.rejection_reason
                )
                app.logger.info(f'B2B rejection email sent to {company.contact_email}')
            except Exception as e:
                app.logger.error(f'Failed to send B2B rejection email: {str(e)}')
        
        return jsonify({"success": True})
    
    @app.route("/admin/crm/partner/<int:id>/suspend", methods=["POST"])
    @admin_required
    def admin_crm_partner_suspend(id):
        """Призупинити партнера."""
        data = request.get_json() or {}
        company = Company.query.filter_by(id=id, store_id=g.store.id).first_or_404()
        company.status = "suspended"
        company.rejection_reason = data.get("reason", "")
        db.session.commit()
        
        return jsonify({"success": True})
    
    @app.route("/admin/crm/partner/<int:id>/update", methods=["POST"])
    @admin_required
    def admin_crm_partner_update(id):
        """Оновити B2B налаштування партнера."""
        company = Company.query.filter_by(id=id, store_id=g.store.id).first_or_404()
        company.credit_limit = float(request.form.get("credit_limit", 0))
        company.payment_terms = int(request.form.get("payment_terms", 0))
        company.discount_percent = float(request.form.get("discount_percent", 0))
        db.session.commit()
        
        flash(_("Налаштування оновлено!"), "success")
        return redirect(url_for("admin_crm_partner", id=id))
    
    @app.route("/admin/crm/alerts")
    @admin_required
    def admin_crm_alerts():
        """Список алертів."""
        settings = SiteSettings.get_or_create(g.store.id)

        from models.company import AdminAlert

        filter_severity = request.args.get("severity", "")
        filter_status = request.args.get("status", "")
        page = request.args.get("page", 1, type=int)
        per_page = 30

        query = AdminAlert.query.filter_by(store_id=g.store.id)

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
        all_alerts = AdminAlert.query.filter_by(store_id=g.store.id).all()
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
        alert = AdminAlert.query.filter_by(id=id, store_id=g.store.id).first_or_404()
        alert.mark_read()
        
        return jsonify({"success": True})
    
    @app.route("/admin/crm/alert/<int:id>/resolve", methods=["POST"])
    @admin_required
    def admin_crm_alert_resolve(id):
        """Вирішити алерт."""
        from models.company import AdminAlert
        data = request.get_json() or {}
        alert = AdminAlert.query.filter_by(id=id, store_id=g.store.id).first_or_404()
        
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
        AdminAlert.query.filter_by(is_read=False, store_id=g.store.id).update({"is_read": True})
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
                Company.status.in_(["verified", "pending"]),
                Company.store_id == g.store.id,
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
    # warehouse_* моделі tenant-scoped (store_id), Phase 2 завершено.
    # =====================================================================

    @app.route("/admin/warehouse")
    @admin_required
    def admin_warehouse():
        """Головна сторінка складу - завдання на відправку."""
        from models.warehouse import WarehouseTask, ShipmentStatus
        
        page = request.args.get("page", 1, type=int)
        status_filter = request.args.get("status", "")
        per_page = 20
        
        query = WarehouseTask.query.filter_by(store_id=g.store.id)

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
            "pending": WarehouseTask.query.filter_by(status=ShipmentStatus.PENDING.value, store_id=g.store.id).count(),
            "processing": WarehouseTask.query.filter_by(status=ShipmentStatus.PROCESSING.value, store_id=g.store.id).count(),
            "packed": WarehouseTask.query.filter_by(status=ShipmentStatus.PACKED.value, store_id=g.store.id).count(),
            "shipped_today": WarehouseTask.query.filter(
                WarehouseTask.status == ShipmentStatus.SHIPPED.value,
                WarehouseTask.store_id == g.store.id,
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

        task = WarehouseTask.query.filter_by(id=id, store_id=g.store.id).first_or_404()
        
        if request.method == "POST":
            action = request.form.get("action")
            
            if action == "start_processing":
                task.status = ShipmentStatus.PROCESSING.value
                task.assigned_to = request.form.get("assigned_to", "")
                db.session.commit()
                flash(_("✅ Завдання взято в роботу"), "success")
                
            elif action == "mark_packed":
                task.mark_packed(
                    weight_kg=request.form.get("weight_kg", type=float),
                    dimensions=request.form.get("dimensions", "")
                )
                flash(_("📦 Замовлення запаковано"), "success")
                
            elif action == "mark_ready":
                task.status = ShipmentStatus.READY.value
                db.session.commit()
                flash(_("✅ Готово до відправки"), "success")
                
            elif action == "mark_shipped":
                task.mark_shipped(
                    tracking_number=request.form.get("tracking_number", ""),
                    carrier=request.form.get("carrier", "")
                )
                flash(_("🚚 Відправлено!"), "success")
                
            elif action == "mark_delivered":
                task.mark_delivered()
                flash(_("✔️ Доставлено!"), "success")
                
            elif action == "cancel":
                task.status = ShipmentStatus.CANCELLED.value
                task.admin_notes = request.form.get("cancel_reason", "")
                db.session.commit()
                flash(_("❌ Завдання скасовано"), "warning")
            
            elif action == "update_notes":
                task.admin_notes = request.form.get("admin_notes", "")
                db.session.commit()
                flash(_("💾 Нотатки збережено"), "success")
            
            return redirect(url_for("admin_warehouse_task", id=id))

        return render_template("admin/warehouse/task_detail.html", task=task)

    @app.route("/admin/warehouse/task/<int:id>/print")
    @admin_required
    def admin_warehouse_task_print(id):
        """
        Пакувальний лист / відгрузочна наклейка для друку через діалог
        браузера (Ctrl+P) - працює для БУДЬ-ЯКОГО завдання складу, незалежно
        від того, чи підключена служба доставки (DHL/UPS) чи трек-номер
        внесено вручну.
        """
        from models.warehouse import WarehouseTask
        from models.shipping import CarrierAccount

        task = WarehouseTask.query.filter_by(id=id, store_id=g.store.id).first_or_404()
        settings = SiteSettings.get_or_create(g.store.id)
        order = task.order

        # Адреса відправника: якщо для перевізника завдання є CarrierAccount
        # з заповненою адресою - беремо звідти, інакше контакти магазину.
        sender = None
        if task.carrier:
            account = CarrierAccount.query.filter(
                CarrierAccount.store_id == g.store.id,
                db.func.lower(CarrierAccount.carrier) == task.carrier.lower(),
            ).first()
            if account and account.origin_street:
                sender = account.origin_address
        if not sender:
            sender = {
                "name": settings.site_name or "",
                "phone": settings.contact_phone or "",
                "street": settings.contact_address or "",
                "city": "",
                "postal_code": "",
                "country_code": "",
            }

        return render_template(
            "admin/warehouse/print_label.html",
            task=task,
            order=order,
            settings=settings,
            sender=sender,
        )

    @app.route("/admin/warehouse/stock")
    @admin_required
    def admin_warehouse_stock():
        """Залишки товарів на складі."""
        from models.warehouse import LowStockAlert, StockMovement
        
        page = request.args.get("page", 1, type=int)
        show_low = request.args.get("low", "0") == "1"
        search = request.args.get("search", "")
        per_page = 50
        
        query = Product.query.filter_by(is_active=True, store_id=g.store.id)

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
            "total_products": Product.query.filter_by(is_active=True, store_id=g.store.id).count(),
            "out_of_stock": Product.query.filter_by(is_active=True, stock=0, store_id=g.store.id).count(),
            "low_stock": Product.query.filter(
                Product.is_active == True,
                Product.stock > 0,
                Product.stock <= Product.min_stock,
                Product.min_stock > 0,
                Product.store_id == g.store.id,
            ).count(),
            "unresolved_alerts": LowStockAlert.query.filter_by(is_resolved=False, store_id=g.store.id).count(),
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

        product = Product.query.filter_by(id=product_id, store_id=g.store.id).first_or_404()

        adjustment = request.form.get("adjustment", 0, type=int)
        reason = request.form.get("reason", "adjustment")
        notes = request.form.get("notes", "")

        if adjustment == 0:
            flash(_("Введіть кількість для коригування"), "warning")
            return redirect(url_for("admin_warehouse_stock"))

        try:
            StockMovement.record_movement(
                product_id=product_id,
                quantity=adjustment,
                movement_type="adjustment",
                reason=reason,
                notes=notes,
                performed_by="admin",
                store_id=g.store.id,
            )
            flash(_("✅ Залишок '%(name)s' скориговано на %(adjustment)+d") % {"name": product.name, "adjustment": adjustment}, "success")
        except ValueError as e:
            flash(_("❌ Помилка: %(error)s") % {"error": str(e)}, "danger")
        
        return redirect(url_for("admin_warehouse_stock"))
    
    @app.route("/admin/warehouse/stock/<int:product_id>/history")
    @admin_required
    def admin_warehouse_stock_history(product_id):
        """Історія руху товару."""
        from models.warehouse import StockMovement

        product = Product.query.filter_by(id=product_id, store_id=g.store.id).first_or_404()

        page = request.args.get("page", 1, type=int)
        per_page = 50

        query = StockMovement.query.filter_by(product_id=product_id, store_id=g.store.id)\
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
        
        query = ReplenishmentOrder.query.filter_by(store_id=g.store.id)

        if status_filter:
            query = query.filter(ReplenishmentOrder.status == status_filter)

        query = query.order_by(ReplenishmentOrder.created_at.desc())

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        orders = pagination.items

        # Статистика
        stats = {
            "draft": ReplenishmentOrder.query.filter_by(status=ReplenishmentStatus.DRAFT.value, store_id=g.store.id).count(),
            "pending": ReplenishmentOrder.query.filter_by(status=ReplenishmentStatus.PENDING.value, store_id=g.store.id).count(),
            "ordered": ReplenishmentOrder.query.filter_by(status=ReplenishmentStatus.ORDERED.value, store_id=g.store.id).count(),
            "shipped": ReplenishmentOrder.query.filter_by(status=ReplenishmentStatus.SHIPPED.value, store_id=g.store.id).count(),
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
                store_id=g.store.id,
                supplier_name=request.form.get("supplier_name", ""),
                supplier_contact=request.form.get("supplier_contact", ""),
                notes=request.form.get("notes", ""),
                status="draft",
                created_by="admin",
            )
            db.session.add(order)
            db.session.flush()
            order.generate_order_number()

            # Додаємо товари (тільки з поточного магазину)
            product_ids = request.form.getlist("product_ids")
            quantities = request.form.getlist("quantities")
            prices = request.form.getlist("prices")

            for i, product_id in enumerate(product_ids):
                if product_id:
                    product = Product.query.filter_by(id=int(product_id), store_id=g.store.id).first()
                    if product:
                        item = ReplenishmentItem(
                            store_id=g.store.id,
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

            flash(_("✅ Замовлення %(order_number)s створено") % {"order_number": order.order_number}, "success")
            return redirect(url_for("admin_warehouse_replenishment_detail", id=order.id))

        # Товари з низьким залишком для пропозиції
        low_stock_products = Product.query.filter(
            Product.is_active == True,
            Product.stock <= Product.min_stock,
            Product.min_stock > 0,
            Product.store_id == g.store.id,
        ).all()

        return render_template(
            "admin/warehouse/replenishment_new.html",
            low_stock_products=low_stock_products,
            products=Product.query.filter_by(is_active=True, store_id=g.store.id).order_by(Product.name).all(),
        )
    
    @app.route("/admin/warehouse/replenishment/<int:id>", methods=["GET", "POST"])
    @admin_required
    def admin_warehouse_replenishment_detail(id):
        """Деталі замовлення на поповнення."""
        from models.warehouse import ReplenishmentOrder, ReplenishmentStatus

        order = ReplenishmentOrder.query.filter_by(id=id, store_id=g.store.id).first_or_404()
        
        if request.method == "POST":
            action = request.form.get("action")
            
            if action == "approve":
                order.status = ReplenishmentStatus.APPROVED.value
                db.session.commit()
                flash(_("✅ Замовлення підтверджено"), "success")
                
            elif action == "order":
                order.status = ReplenishmentStatus.ORDERED.value
                order.ordered_at = datetime.utcnow()
                db.session.commit()
                flash(_("📤 Замовлено у постачальника"), "success")
                
            elif action == "shipped":
                order.status = ReplenishmentStatus.SHIPPED.value
                order.expected_at = datetime.utcnow()  # TODO: real expected date
                db.session.commit()
                flash(_("🚚 Позначено як відправлено"), "success")
                
            elif action == "receive":
                order.mark_received()
                flash(_("✔️ Товар отримано, залишки оновлено!"), "success")
                
            elif action == "cancel":
                order.status = ReplenishmentStatus.CANCELLED.value
                db.session.commit()
                flash(_("❌ Замовлення скасовано"), "warning")
            
            elif action == "mark_paid":
                order.is_paid = True
                order.paid_at = datetime.utcnow()
                order.payment_method = request.form.get("payment_method", "")
                db.session.commit()
                flash(_("💰 Оплату зафіксовано"), "success")
            
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
        
        query = WarehouseExpense.query.filter_by(store_id=g.store.id)

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
            WarehouseExpense.expense_date >= first_day,
            WarehouseExpense.store_id == g.store.id,
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
                store_id=g.store.id,
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
            
            flash(_("✅ Витрату додано"), "success")
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
            "total": WarehouseTask.query.filter(
                WarehouseTask.created_at >= start_date, WarehouseTask.store_id == g.store.id
            ).count(),
            "shipped": WarehouseTask.query.filter(
                WarehouseTask.shipped_at >= start_date,
                WarehouseTask.shipped_at.isnot(None),
                WarehouseTask.store_id == g.store.id,
            ).count(),
            "delivered": WarehouseTask.query.filter(
                WarehouseTask.delivered_at >= start_date,
                WarehouseTask.delivered_at.isnot(None),
                WarehouseTask.store_id == g.store.id,
            ).count(),
        }

        # Поповнення
        replenishments = {
            "total": ReplenishmentOrder.query.filter(
                ReplenishmentOrder.created_at >= start_date, ReplenishmentOrder.store_id == g.store.id
            ).count(),
            "received": ReplenishmentOrder.query.filter(
                ReplenishmentOrder.received_at >= start_date,
                ReplenishmentOrder.received_at.isnot(None),
                ReplenishmentOrder.store_id == g.store.id,
            ).count(),
            "total_cost": db.session.query(db.func.sum(ReplenishmentOrder.total)).filter(
                ReplenishmentOrder.received_at >= start_date,
                ReplenishmentOrder.received_at.isnot(None),
                ReplenishmentOrder.store_id == g.store.id,
            ).scalar() or 0,
        }

        # Витрати
        expenses = {
            "total": db.session.query(db.func.sum(WarehouseExpense.amount)).filter(
                WarehouseExpense.expense_date >= start_date, WarehouseExpense.store_id == g.store.id
            ).scalar() or 0,
        }

        # По категоріях
        expense_by_category = db.session.query(
            WarehouseExpense.category,
            db.func.sum(WarehouseExpense.amount)
        ).filter(
            WarehouseExpense.expense_date >= start_date, WarehouseExpense.store_id == g.store.id
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
    
    # ----- АДМІНКА: БУХГАЛТЕРІЯ (звіти та експорт CSV) -----

    def _accounting_period():
        """Читає ?from=&to= з рядка запиту, за замовчуванням - поточний місяць."""
        from datetime import date
        today = date.today()
        default_from = today.replace(day=1)
        try:
            date_from = datetime.strptime(request.args.get("from", ""), "%Y-%m-%d").date()
        except ValueError:
            date_from = default_from
        try:
            date_to = datetime.strptime(request.args.get("to", ""), "%Y-%m-%d").date()
        except ValueError:
            date_to = today
        return date_from, date_to

    def _csv_response(filename, header, rows):
        import csv
        from io import StringIO
        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow(header)
        writer.writerows(rows)
        return Response(
            buffer.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    @app.route("/admin/accounting")
    @admin_required
    def admin_accounting():
        """Огляд для бухгалтерії: дохід/витрати за період + посилання на експорт CSV."""
        date_from, date_to = _accounting_period()

        paid_orders_q = Order.query.filter(
            Order.store_id == g.store.id,
            Order.status == "paid",
            db.func.date(Order.paid_at) >= date_from,
            db.func.date(Order.paid_at) <= date_to,
        )
        stats = {
            "orders_count": paid_orders_q.count(),
            "revenue": paid_orders_q.with_entities(db.func.coalesce(db.func.sum(Order.amount), 0.0)).scalar(),
            "subtotal": paid_orders_q.with_entities(db.func.coalesce(db.func.sum(Order.subtotal), 0.0)).scalar(),
            "shipping": paid_orders_q.with_entities(db.func.coalesce(db.func.sum(Order.shipping_cost), 0.0)).scalar(),
            "tax": paid_orders_q.with_entities(db.func.coalesce(db.func.sum(Order.tax), 0.0)).scalar(),
        }

        from models.warehouse import WarehouseExpense
        expenses_total = db.session.query(db.func.coalesce(db.func.sum(WarehouseExpense.amount), 0.0)).filter(
            WarehouseExpense.store_id == g.store.id,
            WarehouseExpense.expense_date >= date_from,
            WarehouseExpense.expense_date <= date_to,
        ).scalar()
        stats["expenses"] = expenses_total
        stats["net"] = stats["revenue"] - expenses_total

        return render_template(
            "admin/accounting.html",
            stats=stats,
            date_from=date_from,
            date_to=date_to,
        )

    @app.route("/admin/accounting/export/orders.csv")
    @admin_required
    def admin_accounting_export_orders():
        """CSV-експорт оплачених замовлень за період - основний звіт для бухгалтерії."""
        date_from, date_to = _accounting_period()
        orders = Order.query.filter(
            Order.store_id == g.store.id,
            Order.status.in_(["paid", "shipped", "delivered"]),
            db.func.date(Order.paid_at) >= date_from,
            db.func.date(Order.paid_at) <= date_to,
        ).order_by(Order.paid_at.asc()).all()

        rows = []
        for order in orders:
            company = order.company if order.company_id else None
            rows.append([
                order.order_number or order.id,
                order.paid_at.strftime("%Y-%m-%d %H:%M") if order.paid_at else "",
                order.customer_name or "",
                order.customer_email or "",
                company.name if company else "",
                company.full_vat_number if company else "",
                order.shipping_country or "",
                f"{order.subtotal or 0.0:.2f}",
                f"{order.discount or 0.0:.2f}",
                f"{order.shipping_cost or 0.0:.2f}",
                f"{order.tax or 0.0:.2f}",
                f"{order.amount or 0.0:.2f}",
                order.currency,
                order.payment_method or "",
                order.status,
            ])

        return _csv_response(
            f"orders_{date_from}_{date_to}.csv",
            ["Номер замовлення", "Дата оплати", "Клієнт", "Email", "Компанія (B2B)", "VAT номер",
             "Країна доставки", "Товари", "Знижка", "Доставка", "Податок", "Разом", "Валюта",
             "Спосіб оплати", "Статус"],
            rows,
        )

    @app.route("/admin/accounting/export/expenses.csv")
    @admin_required
    def admin_accounting_export_expenses():
        """CSV-експорт витрат складу за період."""
        from models.warehouse import WarehouseExpense
        date_from, date_to = _accounting_period()
        expenses = WarehouseExpense.query.filter(
            WarehouseExpense.store_id == g.store.id,
            WarehouseExpense.expense_date >= date_from,
            WarehouseExpense.expense_date <= date_to,
        ).order_by(WarehouseExpense.expense_date.asc()).all()

        rows = [
            [
                e.expense_date.strftime("%Y-%m-%d") if e.expense_date else "",
                e.category_display,
                e.description or "",
                f"{e.amount:.2f}",
                e.currency,
                e.receipt_number or "",
                e.created_by or "",
            ]
            for e in expenses
        ]

        return _csv_response(
            f"expenses_{date_from}_{date_to}.csv",
            ["Дата", "Категорія", "Опис", "Сума", "Валюта", "№ чека", "Ким додано"],
            rows,
        )

    @app.route("/admin/accounting/export/revenue-by-country.csv")
    @admin_required
    def admin_accounting_export_revenue_by_country():
        """
        CSV: дохід згруповано за країною доставки - довідково для VAT/OSS звітності.
        Це НЕ розрахунок ПДВ (в системі немає розбивки по ставках) - лише сума
        оплачених замовлень по країнах, з якою бухгалтер вже рахує податок сам.
        """
        date_from, date_to = _accounting_period()
        rows_query = db.session.query(
            Order.shipping_country,
            db.func.count(Order.id),
            db.func.sum(Order.subtotal),
            db.func.sum(Order.amount),
        ).filter(
            Order.store_id == g.store.id,
            Order.status.in_(["paid", "shipped", "delivered"]),
            db.func.date(Order.paid_at) >= date_from,
            db.func.date(Order.paid_at) <= date_to,
        ).group_by(Order.shipping_country).order_by(Order.shipping_country.asc()).all()

        rows = [
            [country or "(не вказано)", count, f"{subtotal:.2f}", f"{total:.2f}"]
            for country, count, subtotal, total in rows_query
        ]

        return _csv_response(
            f"revenue_by_country_{date_from}_{date_to}.csv",
            ["Країна доставки", "К-сть замовлень", "Сума товарів", "Разом (з доставкою)"],
            rows,
        )

    # =====================================================================
    # AI SETTINGS ROUTES
    # =====================================================================
    
    @app.route("/admin/ai", methods=["GET", "POST"])
    @admin_required
    def admin_ai_settings():
        """Налаштування AI чатбота та блогера."""
        ai_settings = AISettings.get_or_create(g.store.id)
        
        if request.method == "POST":
            # Чатбот
            ai_settings.chatbot_enabled = request.form.get("chatbot_enabled") == "on"
            ai_settings.chatbot_name = request.form.get("chatbot_name", "")
            ai_settings.chatbot_tone = request.form.get("chatbot_tone", "friendly")
            ai_settings.chatbot_system_prompt = request.form.get("chatbot_system_prompt", "")
            ai_settings.chatbot_custom_instructions = request.form.get("chatbot_custom_instructions", "")
            ai_settings.chatbot_forbidden_topics = request.form.get("chatbot_forbidden_topics", "")
            
            try:
                ai_settings.chatbot_max_tokens = int(request.form.get("chatbot_max_tokens", 500))
            except ValueError:
                ai_settings.chatbot_max_tokens = 500
            
            try:
                ai_settings.chatbot_temperature = float(request.form.get("chatbot_temperature", 0.7))
            except ValueError:
                ai_settings.chatbot_temperature = 0.7
            
            # Блогер
            ai_settings.blogger_enabled = request.form.get("blogger_enabled") == "on"
            ai_settings.blogger_name = request.form.get("blogger_name", "")
            ai_settings.blogger_style = request.form.get("blogger_style", "informative")
            ai_settings.blogger_language = request.form.get("blogger_language", "uk")
            ai_settings.blogger_default_keywords = request.form.get("blogger_default_keywords", "")
            ai_settings.blogger_seo_instructions = request.form.get("blogger_seo_instructions", "")
            ai_settings.blogger_article_structure = request.form.get("blogger_article_structure", "")
            
            try:
                ai_settings.blogger_min_words = int(request.form.get("blogger_min_words", 500))
            except ValueError:
                ai_settings.blogger_min_words = 500
            
            try:
                ai_settings.blogger_max_words = int(request.form.get("blogger_max_words", 1500))
            except ValueError:
                ai_settings.blogger_max_words = 1500
            
            ai_settings.auto_publish = request.form.get("auto_publish") == "on"
            ai_settings.publish_time = request.form.get("publish_time", "10:00")
            ai_settings.blogger_auto_generate = request.form.get("blogger_auto_generate") == "on"
            
            # Генерація зображень
            ai_settings.generate_images = request.form.get("generate_images") == "on"
            ai_settings.image_style = request.form.get("image_style", "professional photography, realistic, high quality")
            
            # Автоматичний переклад
            ai_settings.auto_translate = request.form.get("auto_translate") == "on"
            translate_langs = []
            if request.form.get("translate_en") == "on":
                translate_langs.append("en")
            if request.form.get("translate_de") == "on":
                translate_langs.append("de")
            ai_settings.auto_translate_languages = ",".join(translate_langs) if translate_langs else "en,de"
            
            db.session.commit()
            flash(_("✅ AI налаштування збережено!"), "success")
            return redirect(url_for("admin_ai_settings"))
        
        return render_template("admin/ai_settings.html", ai_settings=ai_settings)
    
    # =====================================================================
    # BLOG ADMIN ROUTES
    # =====================================================================
    
    @app.route("/admin/blog")
    @admin_required
    def admin_blog():
        """Список статей блогу."""
        page = request.args.get("page", 1, type=int)
        status_filter = request.args.get("status", "")
        per_page = 20
        
        query = BlogPost.query.filter_by(store_id=g.store.id)

        if status_filter:
            query = query.filter(BlogPost.status == status_filter)

        query = query.order_by(BlogPost.created_at.desc())

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        posts = pagination.items

        # Статистика
        stats = {
            "total": BlogPost.query.filter_by(store_id=g.store.id).count(),
            "published": BlogPost.query.filter_by(status=BlogPostStatus.PUBLISHED, store_id=g.store.id).count(),
            "scheduled": BlogPost.query.filter_by(status=BlogPostStatus.SCHEDULED, store_id=g.store.id).count(),
            "draft": BlogPost.query.filter_by(status=BlogPostStatus.DRAFT, store_id=g.store.id).count(),
        }
        
        return render_template(
            "admin/blog.html",
            posts=posts,
            pagination=pagination,
            stats=stats,
            status_filter=status_filter,
            page=page,
            total_pages=pagination.pages,
        )
    
    @app.route("/admin/blog/new", methods=["GET", "POST"])
    @admin_required
    def admin_blog_new():
        """Створення нової статті."""
        if request.method == "POST":
            action = request.form.get("action", "save")
            
            title = request.form.get("title", "").strip()
            slug = request.form.get("slug", "").strip() or BlogPost.generate_slug(title)
            
            # Перевіряємо унікальність slug (в межах магазину)
            existing = BlogPost.get_by_slug(slug, store_id=g.store.id)
            if existing:
                slug = f"{slug}-{uuid.uuid4().hex[:6]}"

            post = BlogPost(
                store_id=g.store.id,
                title=title,
                slug=slug,
                excerpt=request.form.get("excerpt", "").strip() or None,
                content=request.form.get("content", "").strip() or None,
                featured_image=request.form.get("featured_image", "").strip() or None,
                meta_title=request.form.get("meta_title", "").strip() or None,
                meta_description=request.form.get("meta_description", "").strip() or None,
                meta_keywords=request.form.get("meta_keywords", "").strip() or None,
                tags=request.form.get("tags", "").strip() or None,
                category=request.form.get("category", "").strip() or None,
                author=request.form.get("author", "AI").strip(),
                ai_topic=request.form.get("ai_topic", "").strip() or None,
                # Multilingual fields
                title_en=request.form.get("title_en", "").strip() or None,
                title_de=request.form.get("title_de", "").strip() or None,
                excerpt_en=request.form.get("excerpt_en", "").strip() or None,
                excerpt_de=request.form.get("excerpt_de", "").strip() or None,
                content_en=request.form.get("content_en", "").strip() or None,
                content_de=request.form.get("content_de", "").strip() or None,
            )
            
            # Статус та дата публікації
            if action == "publish":
                post.status = BlogPostStatus.PUBLISHED
                post.publish_date = datetime.utcnow()
            else:
                post.status = request.form.get("status", BlogPostStatus.DRAFT)
                publish_date = request.form.get("publish_date", "")
                if publish_date:
                    try:
                        post.publish_date = datetime.fromisoformat(publish_date)
                    except ValueError:
                        pass
            
            db.session.add(post)
            db.session.commit()
            
            flash(_("✅ Статтю створено!"), "success")
            return redirect(url_for("admin_blog_edit", id=post.id))
        
        return render_template("admin/blog_edit.html", post=None)
    
    @app.route("/admin/blog/<int:id>", methods=["GET", "POST"])
    @admin_required
    def admin_blog_edit(id):
        """Редагування статті."""
        post = BlogPost.query.filter_by(id=id, store_id=g.store.id).first_or_404()
        
        if request.method == "POST":
            action = request.form.get("action", "save")
            
            post.title = request.form.get("title", "").strip()
            
            new_slug = request.form.get("slug", "").strip() or BlogPost.generate_slug(post.title)
            if new_slug != post.slug:
                existing = BlogPost.query.filter(
                    BlogPost.slug == new_slug, BlogPost.store_id == g.store.id, BlogPost.id != id
                ).first()
                if existing:
                    new_slug = f"{new_slug}-{uuid.uuid4().hex[:6]}"
                post.slug = new_slug
            
            post.excerpt = request.form.get("excerpt", "").strip() or None
            post.content = request.form.get("content", "").strip() or None
            
            # Оновлюємо featured_image та видаляємо старе зображення
            new_featured_image = request.form.get("featured_image", "").strip() or None
            if new_featured_image and new_featured_image != post.featured_image:
                # Видаляємо старе зображення з бази даних
                delete_old_image(post.featured_image)
            post.featured_image = new_featured_image
            
            post.meta_title = request.form.get("meta_title", "").strip() or None
            post.meta_description = request.form.get("meta_description", "").strip() or None
            post.meta_keywords = request.form.get("meta_keywords", "").strip() or None
            post.tags = request.form.get("tags", "").strip() or None
            post.category = request.form.get("category", "").strip() or None
            post.author = request.form.get("author", "AI").strip()
            post.ai_topic = request.form.get("ai_topic", "").strip() or None
            
            # Multilingual fields
            post.title_en = request.form.get("title_en", "").strip() or None
            post.title_de = request.form.get("title_de", "").strip() or None
            post.excerpt_en = request.form.get("excerpt_en", "").strip() or None
            post.excerpt_de = request.form.get("excerpt_de", "").strip() or None
            post.content_en = request.form.get("content_en", "").strip() or None
            post.content_de = request.form.get("content_de", "").strip() or None
            
            if action == "publish":
                post.status = BlogPostStatus.PUBLISHED
                if not post.publish_date:
                    post.publish_date = datetime.utcnow()
            else:
                post.status = request.form.get("status", BlogPostStatus.DRAFT)
                publish_date = request.form.get("publish_date", "")
                if publish_date:
                    try:
                        post.publish_date = datetime.fromisoformat(publish_date)
                    except ValueError:
                        pass
            
            db.session.commit()
            flash(_("✅ Статтю оновлено!"), "success")
            return redirect(url_for("admin_blog_edit", id=id))
        
        return render_template("admin/blog_edit.html", post=post)
    
    @app.route("/admin/blog/<int:id>/delete", methods=["POST"])
    @admin_required
    def admin_blog_delete(id):
        """Видалення статті."""
        post = BlogPost.query.filter_by(id=id, store_id=g.store.id).first_or_404()
        
        # Видаляємо зображення перед видаленням статті
        if post.featured_image:
            delete_old_image(post.featured_image)
        
        db.session.delete(post)
        db.session.commit()
        flash(_("Статтю видалено."), "info")
        return redirect(url_for("admin_blog"))
    
    @app.route("/admin/blog/<int:id>/publish", methods=["POST"])
    @admin_required
    def admin_blog_publish(id):
        """Швидка публікація статті."""
        post = BlogPost.query.filter_by(id=id, store_id=g.store.id).first_or_404()
        post.status = BlogPostStatus.PUBLISHED
        # Якщо дата публікації в майбутньому або відсутня - ставимо поточний час
        if not post.publish_date or post.publish_date > datetime.utcnow():
            post.publish_date = datetime.utcnow()
        db.session.commit()
        flash(_("✅ Статтю '%(title)s' опубліковано!") % {"title": post.title}, "success")
        return redirect(url_for("admin_blog"))
    
    @app.route("/admin/blog/plan", methods=["GET", "POST"])
    @admin_required
    def admin_blog_plan():
        """План публікацій на 7 днів."""
        from datetime import date, timedelta
        
        if request.method == "POST":
            # Збираємо теми з форми
            topics_list = []
            target_audience = request.form.get("target_audience", "")
            additional_instructions = request.form.get("additional_instructions", "")
            
            for i in range(7):
                topic = request.form.get(f"topic_{i}", "").strip()
                if topic:
                    topics_list.append({
                        "topic": topic,
                        "keywords": request.form.get(f"keywords_{i}", "").strip(),
                        "audience": target_audience,
                        "instructions": additional_instructions,
                    })
            
            if topics_list:
                BlogPlan.create_weekly_plan(topics_list, store_id=g.store.id)
                flash(_("✅ Створено план на %(count)s днів!") % {"count": len(topics_list)}, "success")
            else:
                flash(_("Введіть хоча б одну тему."), "warning")
            
            return redirect(url_for("admin_blog_plan"))
        
        # Поточний тиждень
        today = date.today()
        week_days = []
        day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]
        
        for i in range(7):
            current_date = today + timedelta(days=i)
            plan = BlogPlan.query.filter_by(plan_date=current_date, store_id=g.store.id).first()
            
            week_days.append({
                "date": current_date,
                "day_name": day_names[current_date.weekday()],
                "is_today": current_date == today,
                "is_past": current_date < today,
                "plan": plan,
            })
        
        # Всі плани
        all_plans = BlogPlan.query.filter_by(store_id=g.store.id).order_by(BlogPlan.plan_date.desc()).limit(30).all()
        
        return render_template(
            "admin/blog_plan.html",
            week_days=week_days,
            all_plans=all_plans,
        )
    
    # =====================================================================
    # BLOG API ROUTES (AI Generation)
    # =====================================================================
    
    @app.route("/api/blog/generate", methods=["POST"])
    @admin_required
    def api_blog_generate():
        """API генерації статті через AI."""
        openai_client = get_openai_client()
        if not OPENAI_AVAILABLE or not openai_client:
            return jsonify({"error": _("AI не налаштовано")}), 400
        
        data = request.get_json()
        topic = data.get("topic", "").strip()
        keywords = data.get("keywords", "").strip()
        
        if not topic:
            return jsonify({"error": _("Тема обов'язкова")}), 400
        
        ai_settings = AISettings.get_or_create(g.store.id)
        
        try:
            # Формуємо промпт
            prompt = ai_settings.get_blogger_prompt(topic, keywords)
            
            response = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": f"""Ти - досвідчений контент-райтер та SEO-спеціаліст.
Пиши мовою: {ai_settings.blogger_language}
Стиль: {ai_settings.blogger_style}
Обсяг: {ai_settings.blogger_min_words}-{ai_settings.blogger_max_words} слів

Результат у форматі JSON:
{{
  "title": "SEO-оптимізований заголовок",
  "excerpt": "Короткий опис до 200 символів",
  "content": "Повний текст статті з HTML форматуванням (h2, h3, p, ul, li)",
  "meta_title": "Meta title до 60 символів",
  "meta_description": "Meta description до 160 символів",
  "tags": "тег1, тег2, тег3"
}}"""},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=2000,
                temperature=0.7,
            )
            
            content = response.choices[0].message.content
            
            # Парсимо JSON
            import json
            try:
                # Видаляємо можливі markdown блоки
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                
                result = json.loads(content.strip())
                result["success"] = True
                return jsonify(result)
            except json.JSONDecodeError:
                # Якщо не вдалось розпарсити - повертаємо як є
                return jsonify({
                    "success": True,
                    "title": topic,
                    "content": content,
                    "excerpt": content[:200] if content else "",
                })
        
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    def _generate_post_from_plan(plan):
        """
        Генерує BlogPost з BlogPlan через OpenAI (текст + SEO meta + опційно
        зображення й автопереклад). Винесено з api_blog_generate_from_plan,
        щоб бути викликаною і з адмін-роута (клік адміна), і з фонового
        планувальника (services нижче) - працює виключно з plan.store_id,
        без залежності від g.store/request, тож придатна для виклику поза
        HTTP-запитом.
        """
        openai_client = get_openai_client()
        if not OPENAI_AVAILABLE or not openai_client:
            raise RuntimeError("AI не налаштовано")

        store_id = plan.store_id

        # Якщо план вже має пост - видаляємо старе зображення при перегенерації
        old_post = None
        if plan.blog_post_id:
            old_post = BlogPost.query.get(plan.blog_post_id)
            if old_post and old_post.featured_image:
                app.logger.info(f"🔄 Regenerating post, will delete old image: {old_post.featured_image}")

        if plan.status != "pending":
            raise ValueError("План вже оброблено")

        ai_settings = AISettings.get_or_create(store_id)

        # Формуємо промпт
        topic = plan.topic
        keywords = plan.keywords or ""

        if plan.additional_instructions:
            keywords += f"\n\nДодаткові інструкції: {plan.additional_instructions}"

        prompt = ai_settings.get_blogger_prompt(topic, keywords)

        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": f"""Ти - досвідчений контент-райтер та SEO-спеціаліст.
Пиши мовою: {ai_settings.blogger_language}
Стиль: {ai_settings.blogger_style}
Обсяг: {ai_settings.blogger_min_words}-{ai_settings.blogger_max_words} слів

Результат у форматі JSON:
{{
  "title": "SEO-оптимізований заголовок",
  "excerpt": "Короткий опис до 200 символів",
  "content": "Повний текст статті з HTML форматуванням (h2, h3, p, ul, li)",
  "meta_title": "Meta title до 60 символів",
  "meta_description": "Meta description до 160 символів",
  "tags": "тег1, тег2, тег3"
}}"""},
                {"role": "user", "content": prompt},
            ],
            max_tokens=2000,
            temperature=0.7,
        )

        content = response.choices[0].message.content

        # Парсимо JSON
        import json
        try:
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            result = json.loads(content.strip())
        except json.JSONDecodeError:
            result = {
                "title": topic,
                "content": content,
                "excerpt": content[:200] if content else "",
            }

        # Генеруємо зображення для статті через DALL-E (якщо увімкнено)
        featured_image_url = None
        if ai_settings.generate_images:
            try:
                # Отримуємо стиль зображення з налаштувань
                image_style = ai_settings.image_style or "professional photography, realistic, high quality"

                # Створюємо промпт для генерації зображення на основі статті
                image_prompt_response = openai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": f"""Ти - експерт з створення промптів для генерації зображень.
Створи короткий промпт (до 200 символів) англійською мовою для DALL-E, щоб згенерувати реалістичне фото для статті блогу.
Промпт має описувати:
- Головний об'єкт/сцену що відповідає темі
- Стиль: {image_style}
- Світло та композицію
Відповідай ТІЛЬКИ промптом, без додаткового тексту."""},
                        {"role": "user", "content": f"Тема статті: {result.get('title', topic)}\n\nКороткий опис: {result.get('excerpt', '')[:200]}"},
                    ],
                    max_tokens=100,
                    temperature=0.7,
                )

                image_prompt = image_prompt_response.choices[0].message.content.strip()
                print(f"🎨 Генерую зображення: {image_prompt[:80]}...")

                # Генеруємо зображення через DALL-E
                image_response = openai_client.images.generate(
                    model="dall-e-3",
                    prompt=image_prompt,
                    size="1792x1024",
                    quality="standard",
                    n=1,
                )

                # Завантажуємо зображення та зберігаємо в базі даних
                image_url = image_response.data[0].url

                import requests as req
                img_response = req.get(image_url, timeout=30)
                if img_response.status_code == 200:
                    from models.product import Image

                    # Створюємо унікальне ім'я файлу
                    image_filename = f"blog_{uuid.uuid4().hex}.png"

                    if app.config["IMAGE_STORAGE"] == "database":
                        # Зберігаємо в базу даних PostgreSQL (ПОСТІЙНЕ ЗБЕРІГАННЯ)
                        image_data = img_response.content

                        # Перевіряємо чи не існує таке зображення
                        existing_image = Image.query.filter_by(filename=image_filename).first()
                        if not existing_image:
                            new_image = Image(
                                store_id=store_id,
                                filename=image_filename,
                                data=image_data,
                                mime_type='image/png',
                                size=len(image_data)
                            )
                            db.session.add(new_image)
                            db.session.commit()
                            print(f"💾 Зображення збережено в БД: {image_filename} ({len(image_data)} bytes)")

                        featured_image_url = f"/images/{image_filename}"
                    else:
                        # Зберігаємо локально (ВТРАТИТЬСЯ ПРИ РЕДЕПЛОЇ!)
                        image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)

                        with open(image_path, 'wb') as f:
                            f.write(img_response.content)

                        featured_image_url = f"/static/uploads/{image_filename}"

                    print(f"✅ Зображення збережено: {featured_image_url}")

            except Exception as img_error:
                # Логуємо помилку, але продовжуємо без зображення
                print(f"⚠️ Помилка генерації зображення: {img_error}")

        # Створюємо пост
        slug = BlogPost.generate_slug(result.get("title", topic))
        existing = BlogPost.get_by_slug(slug, store_id=store_id)
        if existing:
            slug = f"{slug}-{uuid.uuid4().hex[:6]}"

        # Визначаємо дату публікації
        publish_datetime = datetime.combine(plan.plan_date, datetime.strptime(ai_settings.publish_time, "%H:%M").time())

        # Визначаємо статус: якщо auto_publish і час настав - публікуємо одразу
        if ai_settings.auto_publish:
            if publish_datetime <= datetime.utcnow():
                post_status = BlogPostStatus.PUBLISHED
            else:
                post_status = BlogPostStatus.SCHEDULED
        else:
            post_status = BlogPostStatus.DRAFT

        post = BlogPost(
            store_id=store_id,
            title=result.get("title", topic),
            slug=slug,
            excerpt=result.get("excerpt", ""),
            content=result.get("content", ""),
            featured_image=featured_image_url,
            meta_title=result.get("meta_title", ""),
            meta_description=result.get("meta_description", ""),
            tags=result.get("tags", ""),
            status=post_status,
            publish_date=publish_datetime,
            is_ai_generated=True,
            ai_topic=topic,
            blog_plan_id=plan.id,
            author=ai_settings.blogger_name or "AI",
        )
        db.session.add(post)
        db.session.flush()  # Отримуємо post.id перед прив'язкою до плану

        # Видаляємо старе зображення якщо це регенерація
        if old_post and old_post.featured_image and featured_image_url:
            delete_old_image(old_post.featured_image)

        # Оновлюємо план
        plan.status = "generated"
        plan.blog_post_id = post.id

        db.session.commit()

        # Автоматичний переклад якщо увімкнено
        if ai_settings.auto_translate:
            try:
                translate_languages = (ai_settings.auto_translate_languages or "en,de").split(",")
                for lang in translate_languages:
                    lang = lang.strip()
                    if lang not in ["en", "de"]:
                        continue

                    lang_name = "English" if lang == "en" else "German"

                    # Перекладаємо заголовок
                    title_resp = openai_client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[
                            {"role": "system", "content": f"Translate from Ukrainian to {lang_name}. Return ONLY translated text."},
                            {"role": "user", "content": post.title},
                        ],
                        max_tokens=200,
                        temperature=0.3,
                    )

                    # Перекладаємо excerpt
                    excerpt_resp = openai_client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[
                            {"role": "system", "content": f"Translate from Ukrainian to {lang_name}. Return ONLY translated text."},
                            {"role": "user", "content": post.excerpt or ""},
                        ],
                        max_tokens=300,
                        temperature=0.3,
                    )

                    # Перекладаємо контент
                    content_resp = openai_client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[
                            {"role": "system", "content": f"Translate this HTML content from Ukrainian to {lang_name}. Keep all HTML tags. Return ONLY translated HTML."},
                            {"role": "user", "content": post.content or ""},
                        ],
                        max_tokens=3000,
                        temperature=0.3,
                    )

                    if lang == "en":
                        post.title_en = title_resp.choices[0].message.content.strip()
                        post.excerpt_en = excerpt_resp.choices[0].message.content.strip()
                        post.content_en = content_resp.choices[0].message.content.strip()
                    elif lang == "de":
                        post.title_de = title_resp.choices[0].message.content.strip()
                        post.excerpt_de = excerpt_resp.choices[0].message.content.strip()
                        post.content_de = content_resp.choices[0].message.content.strip()

                db.session.commit()
            except Exception as translate_error:
                print(f"Auto-translate error: {translate_error}")

        return post

    @app.route("/api/blog/generate-from-plan/<int:plan_id>", methods=["POST"])
    @admin_required
    def api_blog_generate_from_plan(plan_id):
        """Генерація статті з плану (ручний запуск адміном)."""
        plan = BlogPlan.query.filter_by(id=plan_id, store_id=g.store.id).first_or_404()
        if plan.status != "pending":
            return jsonify({"error": _("План вже оброблено")}), 400
        try:
            post = _generate_post_from_plan(plan)
            return jsonify({"success": True, "post_id": post.id})
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 500

    @app.route("/api/blog/generate-all-pending", methods=["POST"])
    @admin_required
    def api_blog_generate_all_pending():
        """Генерація всіх pending статей."""
        pending_plans = BlogPlan.get_pending_for_date(store_id=g.store.id)
        generated = 0
        
        for plan in pending_plans:
            try:
                # Використовуємо той самий API
                with app.test_client() as client:
                    response = client.post(
                        f"/api/blog/generate-from-plan/{plan.id}",
                        headers={"Cookie": request.headers.get("Cookie", "")},
                    )
                    if response.status_code == 200:
                        generated += 1
            except Exception as e:
                print(f"Error generating plan {plan.id}: {e}")
                continue
        
        return jsonify({"success": True, "generated": generated})
    
    @app.route("/api/blog/auto-publish", methods=["POST"])
    @admin_required
    def api_blog_auto_publish():
        """Автоматична публікація scheduled постів, час яких настав."""
        try:
            scheduled_posts = BlogPost.query.filter(
                BlogPost.status == BlogPostStatus.SCHEDULED,
                BlogPost.publish_date <= datetime.utcnow(),
                BlogPost.store_id == g.store.id,
            ).all()
            
            published_count = 0
            for post in scheduled_posts:
                post.status = BlogPostStatus.PUBLISHED
                published_count += 1
                app.logger.info(f"📰 Auto-published: {post.title}")
            
            if published_count > 0:
                db.session.commit()
            
            return jsonify({
                "success": True,
                "published": published_count,
                "message": f"Опубліковано {published_count} статей"
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    @app.route("/api/blog/plan/<int:plan_id>", methods=["DELETE"])
    @admin_required
    def api_blog_plan_delete(plan_id):
        """Видалення плану."""
        plan = BlogPlan.query.filter_by(id=plan_id, store_id=g.store.id).first_or_404()
        db.session.delete(plan)
        db.session.commit()
        return jsonify({"success": True})
    
    @app.route("/api/blog/translate/<int:post_id>", methods=["POST"])
    @admin_required
    def api_blog_translate(post_id):
        """Автоматичний переклад статті на інші мови."""
        openai_client = get_openai_client()
        if not OPENAI_AVAILABLE or not openai_client:
            return jsonify({"error": _("AI не налаштовано. Додайте OPENAI_API_KEY")}), 400
        
        post = BlogPost.query.filter_by(id=post_id, store_id=g.store.id).first_or_404()
        data = request.get_json() or {}
        languages = data.get("languages", ["en", "de"])
        
        if not post.title or not post.content:
            return jsonify({"error": _("Стаття не має контенту для перекладу")}), 400
        
        translated = {}
        
        try:
            for lang in languages:
                if lang not in ["en", "de"]:
                    continue
                
                lang_name = "English" if lang == "en" else "German"
                
                # Перекладаємо заголовок
                title_response = openai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": f"You are a professional translator. Translate the following text from Ukrainian to {lang_name}. Keep the same style and tone. Return ONLY the translated text, nothing else."},
                        {"role": "user", "content": post.title},
                    ],
                    max_tokens=200,
                    temperature=0.3,
                )
                translated_title = title_response.choices[0].message.content.strip()
                
                # Перекладаємо excerpt якщо є
                translated_excerpt = None
                if post.excerpt:
                    excerpt_response = openai_client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[
                            {"role": "system", "content": f"You are a professional translator. Translate the following text from Ukrainian to {lang_name}. Keep the same style and tone. Return ONLY the translated text, nothing else."},
                            {"role": "user", "content": post.excerpt},
                        ],
                        max_tokens=300,
                        temperature=0.3,
                    )
                    translated_excerpt = excerpt_response.choices[0].message.content.strip()
                
                # Перекладаємо контент (може бути довгим, тому розбиваємо)
                content_response = openai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": f"You are a professional translator. Translate the following HTML content from Ukrainian to {lang_name}. Keep all HTML tags intact. Maintain the same formatting and structure. Return ONLY the translated HTML, nothing else."},
                        {"role": "user", "content": post.content},
                    ],
                    max_tokens=3000,
                    temperature=0.3,
                )
                translated_content = content_response.choices[0].message.content.strip()
                
                # Зберігаємо переклади
                if lang == "en":
                    post.title_en = translated_title
                    post.excerpt_en = translated_excerpt
                    post.content_en = translated_content
                elif lang == "de":
                    post.title_de = translated_title
                    post.excerpt_de = translated_excerpt
                    post.content_de = translated_content
                
                translated[lang] = {
                    "title": translated_title,
                    "excerpt": translated_excerpt,
                    "content_preview": translated_content[:200] + "..." if len(translated_content) > 200 else translated_content
                }
            
            db.session.commit()
            
            return jsonify({
                "success": True,
                "translated": translated,
                "message": f"Стаття перекладена на {len(translated)} мов(и)"
            })
        
        except Exception as e:
            return jsonify({"error": f"Помилка перекладу: {str(e)}"}), 500
    
    # =====================================================================
    # PUBLIC BLOG ROUTES
    # =====================================================================
    
    @app.route("/blog")
    def blog_page():
        """Публічна сторінка блогу."""
        settings = SiteSettings.get_or_create(g.store.id)
        page = request.args.get("page", 1, type=int)
        per_page = 9
        
        # Отримуємо опубліковані пости
        query = BlogPost.query.filter(
            BlogPost.status == BlogPostStatus.PUBLISHED,
            BlogPost.store_id == g.store.id,
            db.or_(
                BlogPost.publish_date.is_(None),
                BlogPost.publish_date <= datetime.utcnow()
            )
        ).order_by(BlogPost.publish_date.desc(), BlogPost.created_at.desc())
        
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        posts = pagination.items
        
        # Останній пост як featured
        featured_post = posts[0] if posts else None
        other_posts = posts[1:] if len(posts) > 1 else []
        
        return render_template(
            "pages/blog.html",
            settings=settings,
            featured_post=featured_post,
            posts=other_posts,
            pagination=pagination,
            page=page,
            total_pages=pagination.pages,
        )
    
    @app.route("/blog/<slug>")
    def blog_post_page(slug):
        """Сторінка окремого посту."""
        settings = SiteSettings.get_or_create(g.store.id)
        post = BlogPost.get_by_slug(slug, store_id=g.store.id)

        if not post or not post.is_published:
            abort(404)

        # Збільшуємо перегляди
        post.increment_views()

        # Схожі пости
        related = []
        if post.category:
            related = BlogPost.query.filter(
                BlogPost.status == BlogPostStatus.PUBLISHED,
                BlogPost.category == post.category,
                BlogPost.store_id == g.store.id,
                BlogPost.id != post.id,
            ).limit(3).all()

        if not related:
            related = BlogPost.query.filter(
                BlogPost.status == BlogPostStatus.PUBLISHED,
                BlogPost.store_id == g.store.id,
                BlogPost.id != post.id,
            ).order_by(BlogPost.views.desc()).limit(3).all()
        
        return render_template(
            "pages/blog_post.html",
            settings=settings,
            post=post,
            related=related,
        )

    def _run_blog_automation():
        """
        Фонова робота блогера: генерує статті з BlogPlan, дата яких настала
        (лише для магазинів з увімкненим AISettings.blogger_auto_generate),
        і публікує BlogPost зі статусом SCHEDULED, час яких настав. Раніше
        обидві дії робилися лише вручну через адмінку - тепер це реально
        відбувається саме, без кліку адміна.
        """
        from datetime import date as date_cls

        try:
            due_plans = BlogPlan.get_pending_for_date(target_date=date_cls.today())
            for plan in due_plans:
                try:
                    ai_settings = AISettings.get_or_create(plan.store_id)
                    if not ai_settings.blogger_auto_generate:
                        continue
                    post = _generate_post_from_plan(plan)
                    app.logger.info(f"🤖 Auto-generated blog post #{post.id} from plan #{plan.id} (store {plan.store_id})")
                except Exception as e:
                    db.session.rollback()
                    app.logger.warning(f"Blog auto-generation failed for plan #{plan.id}: {e}")
        except Exception as e:
            app.logger.error(f"Blog automation (generate) job failed: {e}")

        try:
            due_posts = BlogPost.query.filter(
                BlogPost.status == BlogPostStatus.SCHEDULED,
                BlogPost.publish_date <= datetime.utcnow(),
            ).all()
            published_count = 0
            for post in due_posts:
                post.status = BlogPostStatus.PUBLISHED
                published_count += 1
            if published_count:
                db.session.commit()
                app.logger.info(f"📰 Auto-published {published_count} scheduled blog post(s)")
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Blog automation (auto-publish) job failed: {e}")

    def _start_blog_scheduler():
        """
        Запускає фонове завдання блогера кожні 15 хв. Gunicorn піднімає
        декілька worker-процесів - кожен запустив би свій BackgroundScheduler,
        що призвело б до дублювання генерації/публікації. Тому кожен тік
        спершу бере Postgres advisory lock: лише той worker, що встиг його
        захопити, реально виконує роботу, інші миттєво виходять.
        """
        if DEMO_MODE or os.environ.get("DISABLE_SCHEDULER") == "1":
            return
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            import sqlalchemy as sa

            LOCK_KEY = 928374651  # довільне, але стабільне число для цього job'а

            def guarded_job():
                with app.app_context():
                    got_lock = True
                    is_postgres = db.engine.url.get_backend_name().startswith("postgres")
                    if is_postgres:
                        try:
                            got_lock = bool(db.session.execute(
                                sa.text("SELECT pg_try_advisory_lock(:key)"), {"key": LOCK_KEY}
                            ).scalar())
                        except Exception:
                            got_lock = True  # якщо lock-запит не вдався - все одно спробуємо виконати
                    if not got_lock:
                        return
                    try:
                        _run_blog_automation()
                    finally:
                        if is_postgres:
                            try:
                                db.session.execute(sa.text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_KEY})
                                db.session.commit()
                            except Exception:
                                db.session.rollback()

            scheduler = BackgroundScheduler(daemon=True)
            scheduler.add_job(
                func=guarded_job,
                trigger="interval",
                minutes=15,
                id="blog_automation",
                replace_existing=True,
                next_run_time=datetime.utcnow(),
            )
            scheduler.start()
            app.logger.info("📅 Blog automation scheduler started (every 15 min)")
        except Exception as e:
            app.logger.warning(f"Could not start blog scheduler: {e}")

    # Ініціалізація БД при старті
    init_db()
    _start_blog_scheduler()
    return app


# Create the app instance for gunicorn
app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
