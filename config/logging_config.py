"""
Конфігурація системи логування для SmartShop AI.

Підтримує:
- Structured logging з JSON форматом
- Ротація файлів логів
- Різні рівні логування для dev/prod
- Інтеграція з Sentry для error tracking
"""

import os
import logging
from logging.handlers import RotatingFileHandler
from pythonjsonlogger import jsonlogger


def setup_logging(app):
    """
    Налаштовує систему логування для Flask додатку.
    
    Args:
        app: Flask application instance
    """
    # Створюємо директорію для логів якщо не існує
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # Визначаємо рівень логування
    log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
    app.logger.setLevel(getattr(logging, log_level))
    
    # Structured JSON logging для production
    if app.config.get('ENV') == 'production':
        # JSON formatter
        json_formatter = jsonlogger.JsonFormatter(
            '%(timestamp)s %(level)s %(name)s %(message)s %(pathname)s %(lineno)d',
            timestamp=True
        )
        
        # File handler з ротацією (max 10MB, keep 10 files)
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, 'smartshop.log'),
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=10
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(json_formatter)
        app.logger.addHandler(file_handler)
        
        # Error file handler (окремий файл для помилок)
        error_handler = RotatingFileHandler(
            os.path.join(log_dir, 'errors.log'),
            maxBytes=10 * 1024 * 1024,
            backupCount=10
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(json_formatter)
        app.logger.addHandler(error_handler)
        
    else:
        # Readable format для development
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
        )
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(formatter)
        app.logger.addHandler(console_handler)
        
        # File handler для dev
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, 'dev.log'),
            maxBytes=5 * 1024 * 1024,
            backupCount=3
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        app.logger.addHandler(file_handler)
    
    app.logger.info('Logging configured successfully', extra={
        'environment': app.config.get('ENV'),
        'log_level': log_level
    })


def setup_sentry(app):
    """
    Налаштовує Sentry для error tracking в production.
    
    Args:
        app: Flask application instance
    """
    sentry_dsn = os.environ.get('SENTRY_DSN')
    
    if not sentry_dsn:
        app.logger.warning('SENTRY_DSN not configured - error tracking disabled')
        return
    
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        
        environment = os.environ.get('SENTRY_ENVIRONMENT', app.config.get('ENV', 'development'))
        
        sentry_sdk.init(
            dsn=sentry_dsn,
            integrations=[
                FlaskIntegration(),
                SqlalchemyIntegration(),
            ],
            # Відсоток транзакцій для performance monitoring
            traces_sample_rate=float(os.environ.get('SENTRY_TRACES_SAMPLE_RATE', '0.1')),
            
            # Відсоток сесій для profiling
            profiles_sample_rate=float(os.environ.get('SENTRY_PROFILES_SAMPLE_RATE', '0.1')),
            
            environment=environment,
            
            # Релізна версія (git commit або версія з package.json)
            release=os.environ.get('SENTRY_RELEASE', 'smartshop-ai@1.0.0'),
            
            # Не відправляти PII (personally identifiable information)
            send_default_pii=False,
            
            # Фільтрація sensitive даних
            before_send=filter_sensitive_data,
        )
        
        app.logger.info('Sentry initialized successfully', extra={
            'environment': environment,
            'traces_sample_rate': float(os.environ.get('SENTRY_TRACES_SAMPLE_RATE', '0.1'))
        })
        
    except ImportError:
        app.logger.error('sentry-sdk not installed - run: pip install sentry-sdk[flask]')
    except Exception as e:
        app.logger.error(f'Failed to initialize Sentry: {str(e)}')


def filter_sensitive_data(event, hint):
    """
    Фільтрує чутливі дані перед відправкою в Sentry.
    
    Args:
        event: Sentry event dict
        hint: Additional context
        
    Returns:
        Modified event dict or None to drop event
    """
    # Видаляємо паролі, токени, API ключі
    sensitive_keys = [
        'password', 'token', 'api_key', 'secret', 'authorization',
        'stripe_secret', 'openai_api_key', 'mail_password'
    ]
    
    if 'request' in event:
        # Фільтруємо query params
        if 'query_string' in event['request']:
            event['request']['query_string'] = '[FILTERED]'
        
        # Фільтруємо headers
        if 'headers' in event['request']:
            for key in list(event['request']['headers'].keys()):
                if any(sensitive in key.lower() for sensitive in sensitive_keys):
                    event['request']['headers'][key] = '[FILTERED]'
        
        # Фільтруємо cookies
        if 'cookies' in event['request']:
            event['request']['cookies'] = '[FILTERED]'
    
    # Фільтруємо environment variables
    if 'extra' in event and 'sys.argv' in event['extra']:
        del event['extra']['sys.argv']
    
    return event


def log_request(app):
    """
    Middleware для логування HTTP запитів.
    
    Args:
        app: Flask application instance
    """
    @app.before_request
    def log_request_info():
        from flask import request
        
        app.logger.info('Request started', extra={
            'method': request.method,
            'path': request.path,
            'remote_addr': request.remote_addr,
            'user_agent': str(request.user_agent)
        })
    
    @app.after_request
    def log_response_info(response):
        from flask import request
        
        app.logger.info('Request completed', extra={
            'method': request.method,
            'path': request.path,
            'status_code': response.status_code,
            'response_size': len(response.get_data())
        })
        
        return response


def log_exceptions(app):
    """
    Обробник для логування необроблених винятків.
    
    Args:
        app: Flask application instance
    """
    @app.errorhandler(Exception)
    def handle_exception(e):
        from flask import request
        
        app.logger.error('Unhandled exception', extra={
            'exception_type': type(e).__name__,
            'exception_message': str(e),
            'method': request.method,
            'path': request.path,
            'remote_addr': request.remote_addr
        }, exc_info=True)
        
        # Пропускаємо далі для стандартної обробки Flask
        raise e
