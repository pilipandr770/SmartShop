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
from threading import Thread


mail = Mail()


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

def send_registration_email(user_email, user_name):
    """
    Відправити email підтвердження реєстрації.
    
    Args:
        user_email: Email користувача
        user_name: Ім'я користувача
    """
    subject = '🎉 Вітаємо в SmartShop AI!'
    
    html_body = render_template(
        'email/registration_welcome.html',
        user_name=user_name
    )
    
    send_email(subject, user_email, html_body)


def send_b2b_verification_pending(user_email, company_name):
    """
    Email для B2B партнера - очікування верифікації.
    
    Args:
        user_email: Email користувача
        company_name: Назва компанії
    """
    subject = '⏳ Ваша компанія на перевірці - SmartShop AI'
    
    html_body = render_template(
        'email/b2b_verification_pending.html',
        company_name=company_name
    )
    
    send_email(subject, user_email, html_body)


def send_b2b_verification_approved(user_email, company_name, discount_percent=0):
    """
    Email для B2B партнера - верифікація успішна.
    
    Args:
        user_email: Email користувача
        company_name: Назва компанії
        discount_percent: Знижка партнера
    """
    subject = '✅ Вашу компанію верифіковано! - SmartShop AI'
    
    html_body = render_template(
        'email/b2b_verification_approved.html',
        company_name=company_name,
        discount_percent=discount_percent
    )
    
    send_email(subject, user_email, html_body)


def send_b2b_verification_rejected(user_email, company_name, reason=''):
    """
    Email для B2B партнера - верифікація відхилена.
    
    Args:
        user_email: Email користувача
        company_name: Назва компанії
        reason: Причина відхилення
    """
    subject = '❌ Верифікація відхилена - SmartShop AI'
    
    html_body = render_template(
        'email/b2b_verification_rejected.html',
        company_name=company_name,
        reason=reason
    )
    
    send_email(subject, user_email, html_body)


def send_order_confirmation(user_email, order):
    """
    Підтвердження замовлення.
    
    Args:
        user_email: Email користувача
        order: Order object
    """
    subject = f'✅ Замовлення #{order.id} підтверджено - SmartShop AI'
    
    html_body = render_template(
        'email/order_confirmation.html',
        order=order
    )
    
    send_email(subject, user_email, html_body)


def send_order_status_update(user_email, order, old_status, new_status):
    """
    Зміна статусу замовлення.
    
    Args:
        user_email: Email користувача
        order: Order object
        old_status: Попередній статус
        new_status: Новий статус
    """
    status_emoji = {
        'pending': '⏳',
        'processing': '🔄',
        'shipped': '📦',
        'delivered': '✅',
        'cancelled': '❌'
    }
    
    emoji = status_emoji.get(new_status, '📋')
    subject = f'{emoji} Замовлення #{order.id} - статус змінено - SmartShop AI'
    
    html_body = render_template(
        'email/order_status_update.html',
        order=order,
        old_status=old_status,
        new_status=new_status
    )
    
    send_email(subject, user_email, html_body)


def send_crm_alert_email(admin_email, alert):
    """
    CRM алерт для адміністратора.
    
    Args:
        admin_email: Email адміністратора
        alert: CRMAlert object
    """
    severity_emoji = {
        'critical': '🔴',
        'warning': '🟠',
        'info': '🔵'
    }
    
    emoji = severity_emoji.get(alert.severity, '📋')
    subject = f'{emoji} CRM Alert: {alert.title} - SmartShop AI'
    
    html_body = render_template(
        'email/crm_alert.html',
        alert=alert
    )
    
    send_email(subject, admin_email, html_body)


def send_blog_digest_email(subscriber_email, posts):
    """
    Щотижневий блог-дайджест.
    
    Args:
        subscriber_email: Email підписника
        posts: List of BlogPost objects (останні 5-7 днів)
    """
    subject = '📰 Нові статті в блозі SmartShop AI'
    
    html_body = render_template(
        'email/blog_digest.html',
        posts=posts
    )
    
    send_email(subject, subscriber_email, html_body)
