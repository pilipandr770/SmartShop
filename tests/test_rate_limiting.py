"""
Регресія: /login має реально обмежувати кількість спроб на IP - без цього
брутфорс/credential-stuffing нічим не стримується. Ліміт для /login -
15/хв - б'ємо 20 разів і очікуємо хоча б один 429 у відповідях.

Примітка: Flask-Limiter кешує self.enabled при limiter.init_app() всередині
create_app(), тому app.config["RATELIMIT_ENABLED"] = False (виставлений для
зручності решти тестів) на цей момент вже НЕ впливає - ліміти реально активні,
що й дозволяє перевірити їх тут без додаткових маніпуляцій з конфігом.
"""
from .conftest import store_host


def test_login_rate_limit_triggers(client, default_store):
    """Власна фейкова IP-адреса (не 127.0.0.1/testclient за замовчуванням) -
    інакше цей тест назавжди вичерпав би ліміт /login для всіх ІНШИХ тестів
    у тій самій pytest-сесії (in-memory сховище Flask-Limiter спільне для
    всього процесу й рахує за remote_addr, не за тестовим клієнтом)."""
    headers = {"Host": store_host(default_store.slug)}
    statuses = []
    for _ in range(20):
        resp = client.post(
            "/login",
            data={"email": "nobody@example.com", "password": "wrong"},
            headers=headers,
            environ_overrides={"REMOTE_ADDR": "203.0.113.55"},
        )
        statuses.append(resp.status_code)

    assert 429 in statuses, f"очікували хоча б один 429 серед {statuses}"


def test_ai_chat_rate_limit_triggers(client, default_store):
    """/api/chat раніше не мав жодного ліміту - lookup_order_status приймає
    order_number+email від клієнта, тобто без throttling це brute-force
    оракул для підбору чужих замовлень. Ліміт - 20/хв."""
    headers = {"Host": store_host(default_store.slug)}
    statuses = []
    for _ in range(25):
        resp = client.post(
            "/api/chat",
            json={"message": "hello"},
            headers=headers,
            environ_overrides={"REMOTE_ADDR": "203.0.113.77"},
        )
        statuses.append(resp.status_code)

    assert 429 in statuses, f"очікували хоча б один 429 серед {statuses}"
