# Docker: локальний запуск і деплой

SmartShop AI можна підняти повністю в контейнерах: Flask-додаток (Gunicorn) + PostgreSQL,
з окремими volume для бази, завантажених файлів і логів.

## Швидкий старт

```bash
cp .env.docker.example .env.docker
# відредагуйте .env.docker: SECRET_KEY, ADMIN_PASSWORD, POSTGRES_PASSWORD,
# і за потреби STRIPE_*/OPENAI_API_KEY

docker compose up -d --build
```

Сайт: http://localhost:5000/
Адмінка: http://localhost:5000/admin/
PostgreSQL проброшений на хост: `localhost:5432` (для підключення DBeaver/psql ззовні).

## Що відбувається під капотом

- `db` — контейнер `postgres:16-alpine` з persistent volume `smartshop_pgdata`.
- `web` — образ, зібраний з `Dockerfile` (Python 3.11-slim), запускається через
  `docker-entrypoint.sh`, який:
  1. чекає, поки Postgres прийме з'єднання;
  2. виконує `flask db upgrade` (Alembic-міграції, якщо вони є);
  3. запускає `gunicorn app:app` на порту 5000.
- Uploads (`static/uploads`) і логи (`logs/`) зберігаються в окремих named volumes,
  тож не губляться при перезбірці образу.
- Демо-дані (категорія + 4 товари) створюються один раз при першому старті
  (існуючий механізм `init_db()` в `app.py`, не зачіпали) — при рестарті контейнера
  дублювання не відбувається.

## Міграції (Flask-Migrate / Alembic)

Раніше в проєкті не було міграцій взагалі — тільки `db.create_all()` і купа
ручних `ALTER TABLE ADD COLUMN IF NOT EXISTS` прямо в `init_db()` (це і ставало
причиною розсинхронізації схеми, зокрема на локальній SQLite). Ці ручні патчі
залишені як є (вони ідемпотентні й нешкідливі), але тепер для **нових** змін
моделей використовуйте нормальні Alembic-міграції:

```bash
# після зміни моделі (models/*.py) на локальному Postgres:
export FLASK_APP=app.py
export DATABASE_URL=postgresql://smartshop:smartshop@localhost:5432/smartshop
flask db migrate -m "Опис зміни"
flask db upgrade
```

Згенерований файл у `migrations/versions/` комітьте в git — на проді/в Docker
`docker-entrypoint.sh` застосує його автоматично через `flask db upgrade`
при наступному деплої.

## Змінні середовища

- `.env` — для запуску **без Docker** (`python app.py`), використовує SQLite.
- `.env.docker` — для `docker compose` (сервіс `web` підхоплює його через `env_file`).
  Не комітиться (в `.gitignore`).
- `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` в `.env.docker` — це лише
  документація; сам сервіс `db` в `docker-compose.yml` бере ці значення через
  підстановку `${POSTGRES_USER:-smartshop}` зі змінних оточення хоста або дефолтів.
  Якщо хочете змінити пароль бази — або експортуйте змінні в шелл перед
  `docker compose up`, або запускайте з `docker compose --env-file .env.docker up -d`.

## Корисні команди

```bash
docker compose logs -f web        # логи додатку
docker compose exec db psql -U smartshop -d smartshop   # psql в контейнер БД
docker compose down                # зупинити (дані в volumes зберігаються)
docker compose down -v             # зупинити І видалити volumes (втрата даних БД!)
docker compose up -d --build web   # перезібрати тільки додаток після зміни коду
```

## Перенесення існуючих даних з Render/іншого Postgres

Якщо є продакшн-база на Render, яку треба перенести в контейнер:

```bash
# 1. Дамп з існуючої бази
pg_dump --no-owner --no-acl -Fc "postgresql://user:pass@render-host/db" -f backup.dump

# 2. Відновлення в контейнер (поки він запущений)
docker compose exec -T db pg_restore --no-owner --no-acl -U smartshop -d smartshop < backup.dump
```

Схема (`smartshop`) має бути створена заздалегідь — вона створюється автоматично
при першому старті `web` (`init_db()`).
