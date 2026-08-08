# SmartShop AI

Multi-tenant SaaS платформа для запуску онлайн-магазину: один codebase,
кожен клієнт отримує ізольований магазин на своєму піддомені
(`<slug>.shop.andrii-it.de`) або власному домені. Підписка та білінг —
через Stripe (starter/pro/business, 7-денний trial); прийом оплат
магазинами клієнтів — через Stripe Connect (destination charges).

## Що є в продукті

- **Storefront + AI-продавець**: каталог, кошик, checkout, вбудований
  чат-бот на OpenAI, що знає живий каталог, ціни й статус замовлень
  конкретного магазину (без витоку даних між орендарями).
- **B2B + B2C в одному продукті**: автоматична верифікація партнерів
  (VAT/VIES, Handelsregister, WHOIS), кредитні ліміти, окремі кабінети.
- **Доставка**: розрахунок вартості й створення етикетки через
  DHL/UPS (або самовивіз), автоматична задача на склад після оплати.
- **Автоматизація контенту**: AI-генерація блогу за розкладом
  (APScheduler).
- **Безпека**: CSRF, підписані Stripe webhooks, шифрування credentials
  перевізників (Fernet), rate limiting на Redis, email-верифікація,
  скидання пароля, опціональна TOTP 2FA з backup-кодами.
- **Локалізація**: uk/en/de — вітрина, адмінка, транзакційні листи
  (мова фіксується на замовленні), flash-повідомлення.
- **GDPR**: самостійне видалення акаунту, cookie-банер, Datenschutz/AGB/
  Impressum на кожному магазині.
- **SEO з коробки**: per-store `robots.txt`, `sitemap.xml` (+ окремо
  товари/блог), OG/Twitter meta-теги, JSON-LD для товарів.

## Швидкий старт (Docker — основний спосіб)

```bash
cp .env.docker.example .env.docker
# відредагуйте .env.docker: Stripe/OpenAI ключі, SECRET_KEY, CARRIER_CREDENTIALS_KEY тощо
docker compose up -d --build
```

Стек піднімає `web` (Flask + gunicorn), `db` (PostgreSQL) і `redis`
(спільне сховище для rate limiting). Міграції Alembic застосовуються
автоматично при старті контейнера `web`.

- сайт: http://127.0.0.1:5000/
- вхід в адмінку: http://127.0.0.1:5000/login

Деталі, ручні міграції, перенесення даних — [DOCKER.md](DOCKER.md).

## Розробка без Docker (тільки для швидких правок у шаблонах/статиці)

```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
# .env на основі .env.example; DATABASE_URL має вказувати на PostgreSQL
python app.py
```

## Тести

```bash
pip install -r requirements-dev.txt
pytest tests/ -v --cov=. --cov-config=.coveragerc
```

Ганяється автоматично в GitHub Actions на кожен push/PR
(`.github/workflows/`). Тести працюють проти окремої схеми
`smartshop_test` в тому ж Postgres-контейнері — не проти dev/production
даних.

## Експлуатація в production

- **Бекапи БД**: щоденний cron + `scripts/backup_db.sh`, деталі й
  процедура відновлення — [BACKUP_RESTORE.md](BACKUP_RESTORE.md).
- **Моніторинг помилок (Sentry)**: код готовий, потрібен лише
  `SENTRY_DSN` — [docs/SENTRY_SETUP.md](docs/SENTRY_SETUP.md).
- **Email (Flask-Mail)**: шаблони й локалізація готові, потрібен SMTP —
  [docs/EMAIL_SETUP.md](docs/EMAIL_SETUP.md).
- **Зображення**: БД / Cloudinary / локально —
  [docs/IMAGE_STORAGE.md](docs/IMAGE_STORAGE.md),
  [docs/CLOUDINARY_SETUP.md](docs/CLOUDINARY_SETUP.md).
- **SEO**: [docs/SEO_GUIDE.md](docs/SEO_GUIDE.md).
- **i18n деплой**: [DEPLOY_i18n.md](DEPLOY_i18n.md).

## Структура

```
app.py            # основна маршрутизація (комерція, admin, склад, CRM, блог, чат-бот)
routes/           # auth, cabinet (B2B/B2C), platform_admin, signup — виділені blueprints
models/           # Store, User, Product, Order, CarrierAccount, HomepageBlock, ...
services/         # shipping providers, SEO, email, crypto, theme presets
migrations/       # Alembic
templates/        # Jinja2 (storefront, admin, cabinet, email, legal)
translations/      # uk/en/de (Flask-Babel)
tests/            # pytest
scripts/          # операційні скрипти (backup_db.sh)
```
