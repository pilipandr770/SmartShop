"""
Спільні fixtures для тестового набору SmartShop AI.

ВАЖЛИВО: env-змінні нижче мають бути виставлені ДО `from app import app`,
бо `app.py` виконує `app = create_app()` на рівні модуля (побічний ефект
імпорту - див. memory "diagnostic_script_gotcha"). Тому цей блок стоїть на
самому початку файлу, перед усіма іншими імпортами.

Тести працюють проти окремої PostgreSQL-схеми (`smartshop_test`) у тому ж
контейнері `db`, що й локальна розробка (docker-compose експонує 5432 на
хост) - НЕ проти dev-схеми `smartshop` і НЕ проти production. Схема
дропається й перестворюється на початку кожного запуску тестової сесії.
"""
import os
import secrets

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://smartshop:smartshop@127.0.0.1:5432/smartshop"
)
os.environ["DB_SCHEMA"] = "smartshop_test"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["CARRIER_CREDENTIALS_KEY"] = "zq03c3Iykha5hTw-_Ws8p73n2zC8NpACbanMeu9KTk8="
os.environ["STRIPE_SECRET_KEY"] = "sk_test_dummy_for_tests"
os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_test_dummy_signing_secret"
os.environ["OPENAI_API_KEY"] = ""
os.environ["MAIL_USERNAME"] = ""
os.environ["BASE_DOMAIN"] = ""
os.environ["DEMO_MODE"] = "false"
os.environ["DISABLE_SCHEDULER"] = "1"
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "admin123")

import psycopg2
import pytest


def _reset_test_schema():
    """Дропає й перестворює schema smartshop_test - чистий старт кожного запуску."""
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DROP SCHEMA IF EXISTS smartshop_test CASCADE")
        cur.execute("CREATE SCHEMA smartshop_test")
    conn.close()


_reset_test_schema()

from app import app as flask_app  # noqa: E402  (навмисно після env-налаштувань)
from extensions import db as _db  # noqa: E402
from flask_migrate import upgrade as _flask_db_upgrade  # noqa: E402
from models.store import Store  # noqa: E402

# init_db() (запущений при імпорті app вище) створює таблиці лише для
# моделей, імпортованих на момент виклику db.create_all() - деякі моделі
# (напр. CarrierAccount) імпортуються лише лениво всередині окремих
# маршрутів і тому НЕ потрапляють у create_all(). У проді ці таблиці
# з'являються через `flask db upgrade` (docker-entrypoint.sh) ДО старту
# застосунку - тут прикладаємо міграції одразу після імпорту, щоб тестова
# схема точно відповідала реальній продакшн-схемі.
with flask_app.app_context():
    _flask_db_upgrade()


@pytest.fixture(scope="session")
def app():
    flask_app.config["TESTING"] = True
    # Flask-Limiter кешує "enabled" всередині limiter.init_app() (у
    # create_app(), задовго до цієї fixture) - виставляти
    # RATELIMIT_ENABLED тут запізно, ліміти лишаються реально активними.
    # Це навмисно: тести залишаються під тими самими лімітами, що й прод
    # (15/хв на /login тощо) - жоден тест наразі не перевищує їх випадково,
    # а test_rate_limiting.py явно перевіряє саму роботу обмеження.
    flask_app.config["WTF_CSRF_ENABLED"] = False
    yield flask_app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture(scope="session")
def default_store(app):
    """Store, автоматично створений init_db() при першому старті на порожній схемі."""
    with app.app_context():
        store = Store.query.order_by(Store.id.asc()).first()
        assert store is not None, "init_db() мав створити дефолтний Store"
        return store


def unique_email(prefix="test"):
    return f"{prefix}-{secrets.token_hex(6)}@example.com"


def store_host(slug):
    """Host-заголовок для звернення до конкретного магазину за slug'ом
    (той самий `.localhost`-конвент, що використовувався для ручного
    тестування протягом усієї цієї сесії - BASE_DOMAIN не налаштований)."""
    return f"{slug}.localhost"


def login_as(client, user, host=None):
    """Ін'єкція user_id в сесію тест-клієнта - стандартний спосіб Flask-Login
    залогінити тестового користувача без проходження форми /login.

    `host` МАЄ збігатися з Host-заголовком наступного реального запиту -
    без SESSION_COOKIE_DOMAIN (BASE_DOMAIN не налаштовано в тестах) кука
    сесії прив'язується рівно до того хоста, для якого її встановили."""
    kwargs = {"headers": {"Host": host}} if host else {}
    with client.session_transaction(**kwargs) as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
