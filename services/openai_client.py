"""
Спільний lazy-singleton клієнт OpenAI.

Раніше жив як closure всередині create_app() (get_openai_client() у
app.py, з nonlocal-кешем). Винесено сюди, щоб blueprints (AI-чат, блог)
могли використовувати той самий клієнт без циклічного імпорту з app.py.
Кеш - на рівні модуля (один процес gunicorn = один клієнт, поведінка не
відрізняється від попереднього closure-варіанту, там теж був один
екземпляр на процес).
"""
from flask import current_app

try:
    from openai import OpenAI
    import openai as _openai_module
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    _openai_module = None

_client = None


def get_openai_client():
    """Lazy-ініціалізація клієнта OpenAI з кастомним httpx-клієнтом (без proxy,
    щоб SDK не намагався використати HTTP_PROXY з середовища)."""
    global _client
    if _client is None and OPENAI_AVAILABLE and current_app.config.get("OPENAI_API_KEY"):
        try:
            import httpx

            custom_http_client = httpx.Client(
                timeout=60.0,
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            )
            _client = OpenAI(
                api_key=current_app.config["OPENAI_API_KEY"],
                http_client=custom_http_client,
            )
            sdk_version = getattr(_openai_module, "__version__", "unknown")
            current_app.logger.info(f"OpenAI client initialized (SDK {sdk_version})")
        except Exception as e:
            current_app.logger.error(f"Failed to initialize OpenAI client: {type(e).__name__}: {e}")
            _client = None
    return _client
