# 📊 Налаштування Sentry для SmartShop AI

> **Sentry** - це сервіс для моніторингу помилок та performance у реальному часі. Критично важливий для production.

---

## 🎯 Чому Sentry?

### Проблема без Sentry:
- ❌ Користувачі бачать помилки, але ви про них не знаєте
- ❌ Важко відтворити баги у production
- ❌ Немає інформації про performance bottlenecks
- ❌ Логи розкидані по файлах, важко аналізувати

### Переваги з Sentry:
- ✅ **Real-time alerts** - отримуєте email/Slack при кожній помилці
- ✅ **Stack traces** - повний traceback з контекстом
- ✅ **User context** - email, IP, browser користувача
- ✅ **Performance monitoring** - slow queries, endpoints
- ✅ **Release tracking** - порівнюйте помилки між версіями
- ✅ **Search & filters** - знайдіть конкретні помилки за секунди

---

## 🚀 Швидкий старт

### 1. Створити безкоштовний Sentry аккаунт

1. Перейдіть на https://sentry.io/signup/
2. Виберіть "Create a new organization"
3. Назвіть організацію (наприклад: "smartshop-ai")
4. Виберіть **Flask** як platform

### 2. Отримати DSN

Після створення проекту, Sentry покаже вам **DSN** (Data Source Name):

```
https://examplePublicKey@o0.ingest.sentry.io/0123456
```

Це публічний ключ для відправки помилок.

### 3. Додати DSN в .env

```bash
# .env
SENTRY_DSN=https://your-public-key@o0.ingest.sentry.io/your-project-id
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1  # 10% запитів для performance
SENTRY_RELEASE=smartshop-ai@1.0.0
```

### 4. Встановити залежності

```bash
pip install sentry-sdk[flask]==1.40.0
```

Вже додано в `requirements.txt` ✅

### 5. Перезапустити додаток

```bash
# Локально
python app.py

# На Render - просто push в GitHub
git add .
git commit -m "Add Sentry monitoring"
git push
```

---

## 🔧 Конфігурація (вже зроблено в app.py)

Sentry автоматично ініціалізується в `app.py`:

```python
from config.logging_config import setup_sentry

setup_sentry(app)  # Викликається при старті додатку
```

**Що відстежується:**
- ✅ Необроблені винятки (500 errors)
- ✅ Database errors (SQLAlchemy)
- ✅ HTTP запити (performance)
- ✅ Breadcrumbs (логи перед помилкою)
- ✅ User context (якщо залогінений)

**Що НЕ відправляється (privacy):**
- ❌ Паролі
- ❌ API ключі
- ❌ Токени
- ❌ Cookies
- ❌ Query strings з sensitive data

Фільтрація налаштована в `config/logging_config.py` → `filter_sensitive_data()`

---

## 📈 Використання Sentry Dashboard

### Перегляд помилок

1. **Issues** - всі помилки згруповані
2. Клікніть на помилку щоб побачити:
   - Stack trace
   - Request URL
   - User info (email, IP)
   - Browser/OS
   - Breadcrumbs (що користувач робив до помилки)

### Performance Monitoring

1. **Performance** tab
2. Побачите:
   - Slow endpoints (які запити найповільніші)
   - Database queries
   - Transactions timeline

### Alerts

1. **Alerts** → **Create Alert**
2. Налаштуйте:
   - Email notification при кожній новій помилці
   - Slack integration
   - Threshold alerts (якщо >10 помилок за годину)

---

## 🎨 Приклади використання

### Ручне логування помилки

```python
import sentry_sdk

try:
    process_payment(order_id)
except PaymentError as e:
    sentry_sdk.capture_exception(e)
    app.logger.error(f"Payment failed for order {order_id}")
```

### Додати контекст до помилки

```python
with sentry_sdk.configure_scope() as scope:
    scope.set_tag("order_id", order.id)
    scope.set_user({"email": current_user.email})
    scope.set_context("order", {
        "total": order.total,
        "items": len(order.items)
    })
    
    # Тепер будь-яка помилка буде мати цей контекст
    process_order(order)
```

### Performance tracking

```python
import sentry_sdk

with sentry_sdk.start_transaction(op="task", name="generate_blog_post"):
    with sentry_sdk.start_span(op="ai", description="OpenAI API call"):
        result = openai_client.chat.completions.create(...)
    
    with sentry_sdk.start_span(op="db", description="Save to database"):
        db.session.add(post)
        db.session.commit()
```

---

## 🆓 Безкоштовний план

Sentry має **Developer plan (Free forever)**:
- ✅ 5,000 errors/month
- ✅ 10,000 performance events/month
- ✅ 1 GB crash reports
- ✅ Unlimited projects
- ✅ 7 days history

Для початку більше ніж достатньо!

---

## 📊 Приклад Sentry алерту

**Email notification:**

```
🔴 New Issue: ZeroDivisionError in checkout

Project: smartshop-ai (production)
URL: /checkout
User: user@example.com
Browser: Chrome 120 on Windows

Stack trace:
  File "app.py", line 1105, in checkout
    price_per_item = total / quantity
ZeroDivisionError: division by zero

Breadcrumbs:
  [12:30:15] User logged in
  [12:30:45] Added product #123 to cart
  [12:31:00] Clicked "Proceed to checkout"
  [12:31:02] ❌ Error occurred

View in Sentry →
```

---

## 🚨 Важливо для Render.com

### Додати Environment Variables на Render

1. Перейдіть в Render Dashboard → Your Web Service
2. **Environment** → **Add Environment Variable**
3. Додайте:
   ```
   SENTRY_DSN=your-dsn-here
   SENTRY_ENVIRONMENT=production
   SENTRY_RELEASE=smartshop-ai@1.0.0
   LOG_LEVEL=INFO
   ```
4. **Save Changes** - автоматичний redeploy

---

## 🔍 Тестування локально

### Викликати тестову помилку:

```python
# app.py (додайте тимчасовий endpoint)

@app.route('/sentry-test')
def sentry_test():
    """Тестовий endpoint для перевірки Sentry"""
    1 / 0  # Викличе ZeroDivisionError
```

Відкрийте http://localhost:5000/sentry-test

Через 1-2 секунди помилка з'явиться в Sentry Dashboard.

**Не забудьте видалити цей endpoint після тестування!**

---

## 📚 Додаткові ресурси

- 📖 [Sentry Flask Documentation](https://docs.sentry.io/platforms/python/guides/flask/)
- 🎥 [Sentry Quickstart Video](https://sentry.io/welcome/)
- 💬 [Sentry Discord Community](https://discord.gg/sentry)
- 🐛 [GitHub Issues](https://github.com/getsentry/sentry-python/issues)

---

## ✅ Checklist

- [ ] Створив Sentry аккаунт
- [ ] Отримав DSN з Sentry dashboard
- [ ] Додав SENTRY_DSN в .env (локально)
- [ ] Додав SENTRY_DSN в Render Environment Variables
- [ ] Встановив sentry-sdk: `pip install -r requirements.txt`
- [ ] Перезапустив додаток
- [ ] Протестував з `/sentry-test` endpoint
- [ ] Налаштував email alerts в Sentry
- [ ] Видалив тестовий endpoint

---

**Автор:** SmartShop AI Team  
**Дата:** 2024  
**Версія:** 1.0
