> **⚠️ Архівний документ.** Описаний тут v2.0 B2B+B2C функціонал (ролі,
> B2B-реєстрація, VAT/Handelsregister/WHOIS-верифікація, кабінети,
> мультитенантність) з того часу реалізовано повністю. Залишено як
> історичний контекст того, з чого починався продукт.

# 🚀 SmartShop B2B+B2C Platform - Roadmap

## 📊 Поточний стан (v1.0 - B2C Ready)

### ✅ Реалізовано:
- [x] Публічний магазин (каталог, товари, категорії)
- [x] Кошик та оформлення замовлення (Stripe)
- [x] AI чат-асистент (OpenAI)
- [x] Адмін-панель (товари, категорії, замовлення, контакти, налаштування)
- [x] Завантаження зображень товарів
- [x] PostgreSQL з підтримкою схем
- [x] Форма зворотного зв'язку

---

## 🎯 План розвитку (v2.0 - B2B+B2C Enterprise)

### Фаза 1: 👥 Система користувачів та B2B реєстрація
**Пріоритет: ВИСОКИЙ | Термін: 2 тижні**

#### 1.1 Базова система авторизації
- [ ] Модель `User` (email, password_hash, role, is_verified, created_at)
- [ ] Ролі: `customer` (B2C), `partner` (B2B), `manager`, `admin`
- [ ] Реєстрація B2C клієнтів (простий email + пароль)
- [ ] Логін/Логаут для всіх користувачів
- [ ] Відновлення пароля через email
- [ ] Email верифікація

#### 1.2 B2B Реєстрація (розширена)
- [ ] Модель `Company` (назва, VAT, адреса, країна, статус верифікації)
- [ ] Форма реєстрації B2B партнера:
  - Назва компанії
  - VAT номер (ПДВ)
  - Юридична адреса
  - Контактна особа
  - Телефон, email
  - Вебсайт (домен)
- [ ] Статуси: `pending`, `verified`, `rejected`, `suspended`

#### 1.3 Автоматична перевірка B2B партнерів
- [ ] **VAT перевірка** (VIES API для EU)
  - Автоматична перевірка VAT номера при реєстрації
  - Щоденна перевірка активних партнерів
  - Сповіщення при зміні статусу VAT
- [ ] **Handelsregister** (Німеччина)
  - API інтеграція з handelsregister.de
  - Перевірка юридичної особи
- [ ] **WHOIS перевірка домену**
  - Автоматичний WHOIS lookup
  - Збереження даних власника домену
  - Порівняння з даними реєстрації
- [ ] Щоденний cron-job для перевірки всіх партнерів
- [ ] Email/Telegram сповіщення про зміни

---

### Фаза 2: 🏢 Особисті кабінети

#### 2.1 Кабінет B2C клієнта
- [ ] Історія замовлень
- [ ] Статус поточних замовлень
- [ ] Збережені адреси доставки
- [ ] Список бажань (wishlist)
- [ ] Налаштування профілю

#### 2.2 Кабінет B2B партнера
- [ ] Dashboard з аналітикою:
  - Сума закупівель за період
  - Кількість замовлень
  - Графіки динаміки
- [ ] Історія всіх замовлень
- [ ] Відстеження статусу замовлень в реальному часі
- [ ] Документи (рахунки, накладні, акти)
- [ ] Спеціальні B2B ціни (оптові знижки)
- [ ] Кредитний ліміт та баланс
- [ ] Можливість оплати по інвойсу (відтермінування)
- [ ] Завантаження прайс-листа (Excel/CSV)
- [ ] Швидке повторне замовлення
- [ ] API ключі для інтеграції

---

### Фаза 3: 📦 Модуль "Склад"

#### 3.1 Управління складом
- [ ] Розділ `/admin/warehouse` 
- [ ] Dashboard складу:
  - Загальна кількість товарів
  - Товари з низьким залишком (alert)
  - Товари "немає в наявності"
  - Вартість складу
- [ ] Картка товару на складі:
  - Поточний залишок
  - Резерв (в замовленнях)
  - Доступно для продажу
  - Мінімальний залишок (для alert)
  - Історія руху
- [ ] Операції:
  - Прихід товару (закупівля)
  - Витрата (продаж, списання)
  - Інвентаризація
  - Переміщення (якщо кілька складів)

#### 3.2 Модель даних складу
```
StockMovement:
  - id
  - product_id
  - movement_type (in/out/adjustment)
  - quantity
  - unit_price (собівартість)
  - reference (order_id, purchase_id, etc.)
  - notes
  - created_by
  - created_at

PurchaseOrder:
  - id
  - supplier_id
  - status (draft/ordered/received/cancelled)
  - items[]
  - total_amount
  - created_at
  - received_at
```

#### 3.3 Автоматизація складу
- [ ] Автоматичне списання при продажі
- [ ] Автоматичне резервування при створенні замовлення
- [ ] Сповіщення при низькому залишку
- [ ] Звіти по руху товарів

---

### Фаза 4: 🚚 Інтеграція з доставкою

#### 4.1 Nova Poshta API
- [ ] Пошук відділень/поштоматів
- [ ] Створення ТТН (експрес-накладної)
- [ ] Відстеження статусу доставки
- [ ] Розрахунок вартості доставки
- [ ] Зворотна доставка (повернення)
- [ ] Webhook для оновлення статусів

#### 4.2 Інші служби доставки
- [ ] УкрПошта (опційно)
- [ ] Meest Express (опційно)
- [ ] DHL/UPS/FedEx для міжнародних (опційно)

#### 4.3 Інтерфейс доставки
- [ ] Вибір служби доставки при оформленні
- [ ] Пошук відділення на карті
- [ ] Відстеження в кабінеті клієнта
- [ ] Друк накладних в адмін-панелі

---

### Фаза 5: 📊 CRM - Управління контрагентами

#### 5.1 База контрагентів
- [ ] Модель `Contractor`:
  - Тип: постачальник / клієнт / партнер
  - Контактні дані
  - Історія взаємодій
  - Документи
  - Теги/категорії
  - Відповідальний менеджер
  - Кредитний ліміт
  - Умови оплати
- [ ] Картка контрагента з повною історією

#### 5.2 Автоматичний моніторинг
- [ ] Щоденна перевірка:
  - VAT статус (VIES)
  - Handelsregister статус
  - WHOIS зміни
- [ ] Історія перевірок
- [ ] Сповіщення про зміни:
  - Email менеджеру
  - Telegram бот
  - Dashboard alerts

#### 5.3 CRM функції
- [ ] Нотатки та коментарі
- [ ] Задачі (follow-up дзвінки, зустрічі)
- [ ] Файли та документи
- [ ] Історія комунікацій
- [ ] Сегментація клієнтів
- [ ] Аналітика по клієнтах

---

### Фаза 6: 💰 Модуль "Бухгалтерія"

#### 6.1 Облік операцій
- [ ] Розділ `/admin/accounting`
- [ ] Типи операцій:
  - Продаж (автоматично з замовлень)
  - Закупівля (з модуля склад)
  - Витрати (оренда, ЗП, реклама)
  - Інші доходи
- [ ] Прив'язка до контрагентів

#### 6.2 Фінансові звіти
- [ ] Прибутки та збитки (P&L)
- [ ] Рух грошових коштів (Cash Flow)
- [ ] Дебіторська заборгованість
- [ ] Кредиторська заборгованість
- [ ] Звіт по продажах (за період, по товарах, по клієнтах)
- [ ] Звіт по закупівлях
- [ ] Маржинальність товарів

#### 6.3 Документообіг
- [ ] Генерація рахунків (Invoice)
- [ ] Генерація накладних
- [ ] Акти виконаних робіт
- [ ] Експорт в PDF
- [ ] Відправка документів на email
- [ ] Нумерація документів

#### 6.4 Інтеграції (опційно)
- [ ] Експорт в 1С/BAS
- [ ] Експорт в Excel/CSV
- [ ] API для зовнішніх систем

---

### Фаза 7: 🔔 Сповіщення та автоматизація

#### 7.1 Email сповіщення
- [ ] Підтвердження замовлення
- [ ] Зміна статусу замовлення
- [ ] Документи (рахунки, накладні)
- [ ] Маркетингові розсилки
- [ ] Сповіщення для адміністратора

#### 7.2 Telegram бот
- [ ] Сповіщення про нові замовлення
- [ ] Зміни статусу VAT/Handelsregister
- [ ] Низький залишок на складі
- [ ] Важливі фінансові операції

#### 7.3 Автоматизація
- [ ] Celery для фонових задач
- [ ] Cron jobs:
  - Щоденна перевірка VAT
  - Щоденні звіти
  - Нагадування про заборгованість
- [ ] Webhooks для зовнішніх систем

---

## 🗂️ Нова структура бази даних

### Основні таблиці (нові):

```
users
├── id, email, password_hash, role
├── is_verified, is_active
├── first_name, last_name, phone
├── company_id (FK, nullable)
└── created_at, last_login

companies
├── id, name, legal_name
├── vat_number, vat_verified, vat_verified_at
├── handelsregister_id, hr_verified
├── domain, whois_data
├── address, city, country, postal_code
├── credit_limit, payment_terms
├── status (pending/verified/rejected/suspended)
└── created_at, verified_at

contractors (CRM)
├── id, type (supplier/customer/partner)
├── company_id (FK, nullable)
├── user_id (FK, nullable)
├── manager_id (FK to users)
├── tags, notes
├── credit_limit, balance
└── created_at

verification_logs
├── id, company_id
├── check_type (vat/handelsregister/whois)
├── status, response_data
├── checked_at
└── changes_detected

stock_movements
├── id, product_id
├── movement_type (in/out/adjustment/reserve)
├── quantity, unit_cost
├── reference_type, reference_id
├── notes, created_by
└── created_at

purchase_orders
├── id, supplier_id (contractor)
├── status, items[]
├── total_amount
├── ordered_at, received_at
└── created_by

invoices
├── id, type (sale/purchase)
├── number, date
├── contractor_id
├── order_id (nullable)
├── items[], total, tax
├── status (draft/sent/paid/cancelled)
├── due_date, paid_at
└── pdf_url

financial_transactions
├── id, type (income/expense)
├── category
├── amount, currency
├── contractor_id, invoice_id
├── description
└── transaction_date

b2b_prices
├── id, product_id
├── company_id (nullable = all B2B)
├── min_quantity
├── price, discount_percent
└── valid_from, valid_to
```

---

## 📁 Нова структура файлів

```
smartshop_ai/
├── app.py                    # Основний файл (рефакторинг)
├── config.py                 # Конфігурація
├── extensions.py             # Flask extensions (db, mail, celery)
│
├── models/                   # Моделі бази даних
│   ├── __init__.py
│   ├── user.py              # User, Role
│   ├── company.py           # Company, VerificationLog
│   ├── product.py           # Product, Category
│   ├── order.py             # Order, OrderItem
│   ├── stock.py             # StockMovement, PurchaseOrder
│   ├── crm.py               # Contractor, Interaction
│   ├── accounting.py        # Invoice, Transaction
│   └── settings.py          # SiteSettings
│
├── routes/                   # Маршрути (blueprints)
│   ├── __init__.py
│   ├── auth.py              # Логін, реєстрація
│   ├── shop.py              # Публічний магазин
│   ├── b2c_cabinet.py       # Кабінет B2C
│   ├── b2b_cabinet.py       # Кабінет B2B
│   ├── admin/
│   │   ├── __init__.py
│   │   ├── dashboard.py
│   │   ├── products.py
│   │   ├── orders.py
│   │   ├── warehouse.py     # NEW
│   │   ├── crm.py           # NEW
│   │   ├── accounting.py    # NEW
│   │   └── settings.py
│   └── api/
│       ├── __init__.py
│       ├── chat.py
│       ├── cart.py
│       ├── delivery.py      # NEW (Nova Poshta)
│       └── b2b.py           # NEW (B2B API)
│
├── services/                 # Бізнес-логіка
│   ├── __init__.py
│   ├── vat_checker.py       # VIES API
│   ├── handelsregister.py   # Handelsregister API
│   ├── whois_checker.py     # WHOIS lookup
│   ├── nova_poshta.py       # Nova Poshta API
│   ├── stock_manager.py     # Логіка складу
│   ├── invoice_generator.py # Генерація PDF
│   └── notifications.py     # Email, Telegram
│
├── tasks/                    # Celery tasks
│   ├── __init__.py
│   ├── verification.py      # Щоденна перевірка
│   └── reports.py           # Звіти
│
├── templates/
│   ├── auth/                # Логін, реєстрація
│   ├── cabinet/             # Особистий кабінет
│   │   ├── b2c/
│   │   └── b2b/
│   ├── admin/
│   │   ├── warehouse/       # NEW
│   │   ├── crm/             # NEW
│   │   └── accounting/      # NEW
│   └── emails/              # Email шаблони
│
├── static/
│   ├── css/
│   ├── js/
│   └── uploads/
│
├── migrations/              # Flask-Migrate
├── tests/                   # Тести
├── requirements.txt
├── .env
├── .env.example
└── README.md
```

---

## ⏱️ Орієнтовний графік

| Фаза | Назва | Термін | Статус |
|------|-------|--------|--------|
| 1 | Система користувачів + B2B реєстрація | 2 тижні | 🔴 |
| 2 | Особисті кабінети | 1.5 тижні | 🔴 |
| 3 | Модуль "Склад" | 1.5 тижні | 🔴 |
| 4 | Інтеграція з доставкою | 1 тиждень | 🔴 |
| 5 | CRM | 2 тижні | 🔴 |
| 6 | Бухгалтерія | 2 тижні | 🔴 |
| 7 | Сповіщення та автоматизація | 1 тиждень | 🔴 |

**Загальний термін: ~11 тижнів (2.5-3 місяці)**

---

## 🔧 Технології для нових модулів

### Backend:
- **Flask-Login** - авторизація
- **Flask-Mail** - відправка email
- **Flask-Migrate** - міграції БД
- **Celery + Redis** - фонові задачі
- **WeasyPrint/ReportLab** - генерація PDF
- **python-whois** - WHOIS lookup
- **zeep** - SOAP для VIES API

### APIs:
- **VIES** (VAT Information Exchange System) - безкоштовний
- **Handelsregister.de** - платний або scraping
- **Nova Poshta API** - безкоштовний
- **Telegram Bot API** - безкоштовний

---

## 🚦 З чого почати?

**Рекомендую почати з Фази 1:**
1. Створити систему авторизації (User model)
2. Додати B2B реєстрацію
3. Інтегрувати VAT перевірку (VIES)
4. Базовий кабінет партнера

Це дасть основу для всіх інших модулів.

---

## 📝 Примітки

- Кожна фаза може бути реалізована окремо
- Фази 3-6 можна виконувати паралельно
- Для production потрібен Redis (для Celery)
- Рекомендую Docker для деплою
- Тести критично важливі для фінансових модулів

---

*Документ створено: 30.11.2025*
*Автор: SmartShop AI Development Team*
