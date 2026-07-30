"""
Email сервіс для SmartShop AI.

Надсилає email-сповіщення для:
- Підтвердження реєстрації
- Зміна статусу замовлення  
- CRM алерти для адміністраторів
- Блог-дайджести
- B2B верифікація
"""

import os
from flask import render_template, current_app
from flask_mail import Mail, Message
from flask_babel import force_locale, gettext as _
from threading import Thread


mail = Mail()

DEFAULT_LOCALE = "uk"


def _locale_or_default(locale):
    """Мова листа: явно передана (напр. order.locale) або дефолтна платформи."""
    return locale or DEFAULT_LOCALE


def init_mail(app):
    """
    Ініціалізує Flask-Mail.
    
    Args:
        app: Flask application instance
    """
    # Mail налаштування з .env
    app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
    app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
    app.config['MAIL_USE_SSL'] = os.environ.get('MAIL_USE_SSL', 'false').lower() == 'true'
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
    app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@smartshop.com')
    
    mail.init_app(app)
    
    # Перевірка чи налаштовано email
    if not app.config['MAIL_USERNAME']:
        app.logger.warning('MAIL_USERNAME not configured - email notifications disabled')
    else:
        app.logger.info('Flask-Mail initialized successfully', extra={
            'mail_server': app.config['MAIL_SERVER'],
            'mail_port': app.config['MAIL_PORT']
        })


def send_async_email(app, msg):
    """
    Відправка email в окремому потоці (не блокує request).
    
    Args:
        app: Flask app context
        msg: Flask-Mail Message object
    """
    with app.app_context():
        try:
            mail.send(msg)
            app.logger.info('Email sent successfully', extra={
                'subject': msg.subject,
                'recipients': msg.recipients
            })
        except Exception as e:
            app.logger.error(f'Failed to send email: {str(e)}', extra={
                'subject': msg.subject,
                'recipients': msg.recipients
            }, exc_info=True)


def send_email(subject, recipients, html_body, text_body=None):
    """
    Універсальна функція для відправки email.
    
    Args:
        subject: Тема листа
        recipients: List of email addresses
        html_body: HTML версія листа
        text_body: Plain text версія (опціонально)
    """
    if not current_app.config.get('MAIL_USERNAME'):
        current_app.logger.warning('Email not sent - MAIL_USERNAME not configured')
        return
    
    msg = Message(
        subject=subject,
        recipients=recipients if isinstance(recipients, list) else [recipients],
        html=html_body,
        body=text_body or html_body
    )
    
    # Відправка в окремому потоці
    Thread(target=send_async_email, args=(current_app._get_current_object(), msg)).start()


# ==========================================
# Specific email templates
# ==========================================

def send_registration_email(user_email, user_name, locale=None):
    """
    Відправити email підтвердження реєстрації.

    Args:
        user_email: Email користувача
        user_name: Ім'я користувача
        locale: Мова листа (uk/en/de), за замовчуванням DEFAULT_LOCALE
    """
    with force_locale(_locale_or_default(locale)):
        subject = _('🎉 Вітаємо в SmartShop AI!')
        html_body = render_template(
            'email/registration_welcome.html',
            user_name=user_name
        )

    send_email(subject, user_email, html_body)


def send_verification_email_for_user(user, locale=None):
    """
    Best-effort надсилання листа підтвердження email для User-об'єкта -
    генерує токен і формує посилання сам. Ніколи не блокує реєстрацію:
    якщо SMTP не налаштовано або сталася будь-яка помилка, лише пише
    попередження в лог.
    """
    try:
        from flask import url_for
        from services.tokens import generate_token, EMAIL_VERIFY_SALT
        token = generate_token(user.email, EMAIL_VERIFY_SALT)
        verify_url = url_for("verify_email", token=token, _external=True)
        send_verification_email(user.email, user.full_name, verify_url, locale=locale)
    except Exception as e:
        current_app.logger.error(f'Failed to send verification email: {str(e)}')


def send_verification_email(user_email, user_name, verify_url, locale=None):
    """
    Лист із посиланням для підтвердження email адреси.

    Args:
        user_email: Email користувача
        user_name: Ім'я користувача
        verify_url: Повне посилання /verify-email/<token>
        locale: Мова листа (uk/en/de)
    """
    with force_locale(_locale_or_default(locale)):
        subject = _('Підтвердіть вашу email адресу - SmartShop AI')
        html_body = render_template(
            'email/verify_email.html',
            user_name=user_name,
            verify_url=verify_url,
        )

    send_email(subject, user_email, html_body)


def send_password_reset_email(user_email, user_name, reset_url, locale=None):
    """
    Лист із посиланням для скидання пароля.

    Args:
        user_email: Email користувача
        user_name: Ім'я користувача
        reset_url: Повне посилання /reset-password/<token>
        locale: Мова листа (uk/en/de)
    """
    with force_locale(_locale_or_default(locale)):
        subject = _('Скидання пароля - SmartShop AI')
        html_body = render_template(
            'email/password_reset.html',
            user_name=user_name,
            reset_url=reset_url,
        )

    send_email(subject, user_email, html_body)


def send_b2b_verification_pending(user_email, company_name, locale=None):
    """
    Email для B2B партнера - очікування верифікації.

    Args:
        user_email: Email користувача
        company_name: Назва компанії
        locale: Мова листа (uk/en/de), за замовчуванням DEFAULT_LOCALE
    """
    with force_locale(_locale_or_default(locale)):
        subject = _('⏳ Ваша компанія на перевірці - SmartShop AI')
        html_body = render_template(
            'email/b2b_verification_pending.html',
            company_name=company_name
        )

    send_email(subject, user_email, html_body)


def send_b2b_verification_approved(user_email, company_name, discount_percent=0, locale=None):
    """
    Email для B2B партнера - верифікація успішна.

    Args:
        user_email: Email користувача
        company_name: Назва компанії
        discount_percent: Знижка партнера
        locale: Мова листа (uk/en/de), за замовчуванням DEFAULT_LOCALE
    """
    with force_locale(_locale_or_default(locale)):
        subject = _('✅ Вашу компанію верифіковано! - SmartShop AI')
        html_body = render_template(
            'email/b2b_verification_approved.html',
            company_name=company_name,
            discount_percent=discount_percent
        )

    send_email(subject, user_email, html_body)


def send_b2b_verification_rejected(user_email, company_name, reason='', locale=None):
    """
    Email для B2B партнера - верифікація відхилена.

    Args:
        user_email: Email користувача
        company_name: Назва компанії
        reason: Причина відхилення
        locale: Мова листа (uk/en/de), за замовчуванням DEFAULT_LOCALE
    """
    with force_locale(_locale_or_default(locale)):
        subject = _('❌ Верифікація відхилена - SmartShop AI')
        html_body = render_template(
            'email/b2b_verification_rejected.html',
            company_name=company_name,
            reason=reason
        )

    send_email(subject, user_email, html_body)


def send_order_confirmation(user_email, order, locale=None):
    """
    Підтвердження замовлення.

    Args:
        user_email: Email користувача
        order: Order object
        locale: Мова листа (uk/en/de) - типово беремо з order.locale,
            тобто мову, яку клієнт обрав на сайті під час оформлення.
    """
    with force_locale(_locale_or_default(locale or getattr(order, "locale", None))):
        subject = _('✅ Замовлення #%(order_id)s підтверджено - SmartShop AI') % {"order_id": order.id}
        html_body = render_template(
            'email/order_confirmation.html',
            order=order
        )

    send_email(subject, user_email, html_body)


def send_order_status_update(user_email, order, old_status, new_status, locale=None):
    """
    Зміна статусу замовлення.

    Args:
        user_email: Email користувача
        order: Order object
        old_status: Попередній статус
        new_status: Новий статус
        locale: Мова листа (uk/en/de) - типово беремо з order.locale.
    """
    status_emoji = {
        'pending': '⏳',
        'processing': '🔄',
        'shipped': '📦',
        'delivered': '✅',
        'cancelled': '❌'
    }
    emoji = status_emoji.get(new_status, '📋')

    with force_locale(_locale_or_default(locale or getattr(order, "locale", None))):
        subject = _('%(emoji)s Замовлення #%(order_id)s - статус змінено - SmartShop AI') % {
            "emoji": emoji, "order_id": order.id,
        }
        html_body = render_template(
            'email/order_status_update.html',
            order=order,
            old_status=old_status,
            new_status=new_status
        )

    send_email(subject, user_email, html_body)


def send_crm_alert_email(admin_email, alert, locale=None):
    """
    CRM алерт для адміністратора.

    Args:
        admin_email: Email адміністратора
        alert: CRMAlert object
        locale: Мова листа (uk/en/de), за замовчуванням DEFAULT_LOCALE
    """
    severity_emoji = {
        'critical': '🔴',
        'warning': '🟠',
        'info': '🔵'
    }
    emoji = severity_emoji.get(alert.severity, '📋')

    with force_locale(_locale_or_default(locale)):
        subject = _('%(emoji)s CRM Alert: %(title)s - SmartShop AI') % {
            "emoji": emoji, "title": alert.title,
        }
        html_body = render_template(
            'email/crm_alert.html',
            alert=alert
        )

    send_email(subject, admin_email, html_body)


def send_blog_digest_email(subscriber_email, posts, locale=None):
    """
    Щотижневий блог-дайджест.

    Args:
        subscriber_email: Email підписника
        posts: List of BlogPost objects (останні 5-7 днів)
        locale: Мова листа (uk/en/de), за замовчуванням DEFAULT_LOCALE
    """
    with force_locale(_locale_or_default(locale)):
        subject = _('📰 Нові статті в блозі SmartShop AI')
        html_body = render_template(
            'email/blog_digest.html',
            posts=posts
        )

    send_email(subject, subscriber_email, html_body)
