# 📧 Налаштування Email для SmartShop AI

> **Flask-Mail** - відправка email сповіщень для користувачів та адміністраторів.

---

## 🎯 Що відправляється

### B2C Клієнти:
- ✅ **Welcome email** після реєстрації
- 📦 **Order confirmation** після успішної оплати
- 📬 **Order status updates** (shipped, delivered, cancelled)

### B2B Партнери:
- ⏳ **Verification pending** - компанія на перевірці
- ✅ **Verification approved** - доступ до B2B кабінету
- ❌ **Verification rejected** - причина відхилення

### Адміністратори:
- 🔔 **CRM alerts** - критичні зміни у верифікації партнерів
- 📰 **Blog digest** - щотижнева розсилка (опціонально)

---

## 🚀 Швидкий старт (Gmail)

### 1. Створити App Password в Gmail

Google більше не дозволяє використовувати звичайний пароль для SMTP. Потрібен **App Password**.

**Кроки:**

1. Перейдіть на https://myaccount.google.com/security
2. Увімкніть **2-Step Verification** (якщо ще не ввімкнено)
3. Перейдіть на https://myaccount.google.com/apppasswords
4. Виберіть **Mail** та **Other (Custom name)**
5. Введіть назву: `SmartShop AI`
6. Натисніть **Generate**
7. Скопіюйте 16-символьний пароль (наприклад: `abcd efgh ijkl mnop`)

### 2. Додати в .env

```bash
# Gmail SMTP (рекомендовано для початку)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=abcd efgh ijkl mnop  # App Password з кроку 1
MAIL_DEFAULT_SENDER=noreply@smartshop.com
```

### 3. Додати в Render Environment Variables

1. Render Dashboard → Your Web Service → **Environment**
2. **Add Environment Variable**:
   ```
   MAIL_SERVER=smtp.gmail.com
   MAIL_PORT=587
   MAIL_USE_TLS=True
   MAIL_USERNAME=your-email@gmail.com
   MAIL_PASSWORD=your-app-password-here
   MAIL_DEFAULT_SENDER=noreply@smartshop.com
   ```
3. **Save Changes** (automatic redeploy)

### 4. Перезапустити додаток

```bash
# Локально
python app.py

# На Render
git push origin main
```

---

## 📨 Інші SMTP сервіси

### Mailgun (для production)

**Переваги:**
- ✅ 5,000 emails/month безкоштовно
- ✅ High deliverability rate
- ✅ Email analytics dashboard

**Налаштування:**
```bash
MAIL_SERVER=smtp.mailgun.org
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=postmaster@your-domain.mailgun.org
MAIL_PASSWORD=your-mailgun-smtp-password
MAIL_DEFAULT_SENDER=noreply@yourdomain.com
```

### SendGrid

**Переваги:**
- ✅ 100 emails/day безкоштовно
- ✅ Email templates UI
- ✅ Detailed analytics

**Налаштування:**
```bash
MAIL_SERVER=smtp.sendgrid.net
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=apikey
MAIL_PASSWORD=your-sendgrid-api-key
MAIL_DEFAULT_SENDER=noreply@yourdomain.com
```

### AWS SES (Amazon Simple Email Service)

**Переваги:**
- ✅ $0.10 за 1,000 emails
- ✅ Надійність AWS infrastructure
- ✅ Інтеграція з Lambda

**Налаштування:**
```bash
MAIL_SERVER=email-smtp.eu-central-1.amazonaws.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your-ses-smtp-username
MAIL_PASSWORD=your-ses-smtp-password
MAIL_DEFAULT_SENDER=verified@yourdomain.com
```

---

## 🧪 Тестування локально

### Метод 1: MailHog (fake SMTP server)

**Установка:**
```bash
# Windows (Chocolatey)
choco install mailhog

# macOS
brew install mailhog

# Linux
go install github.com/mailhog/MailHog@latest
```

**Запуск:**
```bash
mailhog
```

**Налаштування .env:**
```bash
MAIL_SERVER=localhost
MAIL_PORT=1025
MAIL_USE_TLS=False
MAIL_USERNAME=
MAIL_PASSWORD=
MAIL_DEFAULT_SENDER=noreply@smartshop.local
```

**Перегляд листів:**
- Відкрийте http://localhost:8025
- Всі листи перехоплюються MailHog (не відправляються насправді)

### Метод 2: Mailtrap

**Безкоштовний fake SMTP для testing.**

1. Зареєструйтеся на https://mailtrap.io
2. Створіть inbox
3. Скопіюйте SMTP credentials

**Налаштування .env:**
```bash
MAIL_SERVER=smtp.mailtrap.io
MAIL_PORT=2525
MAIL_USE_TLS=True
MAIL_USERNAME=your-mailtrap-username
MAIL_PASSWORD=your-mailtrap-password
MAIL_DEFAULT_SENDER=noreply@smartshop.local
```

---

## 🎨 Кастомізація email templates

Email templates знаходяться в `templates/email/`:

```
templates/email/
├── layout.html                      # Базовий шаблон
├── registration_welcome.html        # Welcome email
├── b2b_verification_pending.html    # B2B pending
├── b2b_verification_approved.html   # B2B approved
├── b2b_verification_rejected.html   # B2B rejected
├── order_confirmation.html          # Order confirmation
├── order_status_update.html         # Order status change
├── crm_alert.html                   # CRM alerts
└── blog_digest.html                 # Weekly digest
```

### Як змінити дизайн:

1. Відредагуйте `templates/email/layout.html` для global styles
2. Змініть logo/colors в `<style>` блоці
3. Додайте соціальні посилання в footer
4. Використовуйте inline CSS (для email сумісності)

**Приклад:**
```html
<!-- templates/email/layout.html -->
<style>
    .email-header {
        background: linear-gradient(135deg, #YOUR_COLOR 0%, #YOUR_COLOR_2 100%);
        /* Змінити градієнт */
    }
</style>
```

---

## 🔍 Відладка

### Перевірити чи налаштовано email:

Перегляньте логи при старті додатку:

```
[INFO] Flask-Mail initialized successfully
  mail_server: smtp.gmail.com
  mail_port: 587
```

Якщо бачите:
```
[WARNING] MAIL_USERNAME not configured - email notifications disabled
```

Значить, MAIL_USERNAME не встановлено в .env.

### Тестовий endpoint (для перевірки):

Додайте в `app.py` (тимчасово):

```python
@app.route('/test-email')
@admin_required
def test_email():
    """Тестова відправка email"""
    from services.email_service import send_email
    send_email(
        subject="🧪 Test Email - SmartShop AI",
        recipients=["your-email@example.com"],
        html_body="<h1>Email працює! ✅</h1><p>Якщо ви отримали цей лист, email налаштовано правильно.</p>"
    )
    return "Email sent! Check your inbox."
```

Відкрийте http://localhost:5000/test-email

**Не забудьте видалити цей endpoint після тестування!**

---

## ⚠️ Поширені помилки

### 1. `SMTPAuthenticationError: Username and Password not accepted`

**Причина:** Невірний пароль або не використовується App Password (для Gmail).

**Рішення:**
- Створіть App Password в Gmail (див. вище)
- Перевірте, що 2FA ввімкнено

### 2. `SMTPServerDisconnected: Connection unexpectedly closed`

**Причина:** Firewall або ISP блокує SMTP порт 587/465.

**Рішення:**
- Спробуйте інший SMTP сервіс (Mailgun, SendGrid)
- Використовуйте Mailtrap для тестування

### 3. Листи не приходять (але помилок немає)

**Причина:** Email потрапив в Spam.

**Рішення:**
- Перевірте Spam folder
- Налаштуйте SPF/DKIM records для вашого домену
- Використовуйте професійний SMTP (Mailgun, SendGrid)

### 4. `socket.timeout: timed out`

**Причина:** Повільне з'єднання з SMTP сервером.

**Рішення:**
- Email відправляються асинхронно (в Thread), не блокують request
- Якщо проблема повторюється, змініть SMTP сервіс

---

## 📊 Моніторинг email

### Логування

Всі email логуються в `logs/smartshop.log`:

```json
{
  "timestamp": "2024-12-06T10:30:00Z",
  "level": "INFO",
  "message": "Email sent successfully",
  "subject": "Welcome to SmartShop AI",
  "recipients": ["user@example.com"]
}
```

Якщо email не відправився:

```json
{
  "level": "ERROR",
  "message": "Failed to send email: SMTPAuthenticationError",
  "subject": "Welcome email"
}
```

### Sentry integration

Помилки email автоматично відстежуються в Sentry:

- `SMTPAuthenticationError`
- `SMTPServerDisconnected`
- `socket.timeout`

---

## ✅ Checklist

- [ ] Створив App Password в Gmail (або зареєструвався на Mailgun/SendGrid)
- [ ] Додав MAIL_* змінні в `.env` локально
- [ ] Додав MAIL_* в Render Environment Variables
- [ ] Перезапустив додаток
- [ ] Перевірив логи: `Flask-Mail initialized successfully`
- [ ] Протестував реєстрацію - отримав welcome email
- [ ] Протестував оформлення замовлення - отримав confirmation
- [ ] Перевірив Spam folder (якщо не приходять листи)
- [ ] Email templates виглядають добре (адаптивні, без ламаного CSS)

---

## 🚀 Production Best Practices

### 1. Використовувати професійний SMTP

Gmail - для testing, але для production краще:
- **Mailgun** (5,000 free/month)
- **SendGrid** (100/day free)
- **AWS SES** ($0.10/1,000 emails)

### 2. SPF/DKIM/DMARC records

Щоб листи не потрапляли в Spam, налаштуйте DNS records:

**SPF Record:**
```
v=spf1 include:_spf.mailgun.org ~all
```

**DKIM:** Генерується вашим email провайдером (Mailgun, SendGrid)

**DMARC:**
```
v=DMARC1; p=none; rua=mailto:postmaster@yourdomain.com
```

### 3. Email rate limiting

Додати rate limit, щоб уникнути spam:

```python
# В services/email_service.py
from flask_limiter import Limiter

limiter = Limiter(
    key_func=lambda: request.remote_addr,
    default_limits=["10 per hour"]
)

@limiter.limit("5 per hour")
def send_email(...):
    # existing code
```

### 4. Email queue (для великих обсягів)

Якщо відправляєте >1,000 emails/day, використовуйте Celery + Redis:

```python
from celery import Celery

celery = Celery('smartshop', broker='redis://localhost:6379/0')

@celery.task
def send_email_task(subject, recipients, html_body):
    # existing send_email logic
```

---

**Автор:** SmartShop AI Team  
**Дата:** 2024  
**Версія:** 1.0
