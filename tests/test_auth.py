"""
Тести на auth-флоу, побудовані в межах щойно завершеного аудиту безпеки:
CSRF, реєстрація/логін, email-верифікація, скидання пароля.
"""
from models.user import User

from .conftest import unique_email, store_host


def test_csrf_rejects_post_without_token(app, client, default_store):
    """CSRF вимикається глобально для зручності інших тестів (conftest) -
    тут явно вмикаємо назад лише для цього одного тесту, щоб підтвердити,
    що захист справді працює, а не просто вимкнений усюди."""
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        resp = client.post(
            "/login",
            data={"email": "x@example.com", "password": "whatever"},
            headers={"Host": store_host(default_store.slug)},
        )
        assert resp.status_code == 400
    finally:
        app.config["WTF_CSRF_ENABLED"] = False


def test_register_creates_unverified_user(app, client, default_store):
    email = unique_email("newcustomer")
    resp = client.post(
        "/register",
        data={
            "email": email,
            "password": "TestPass123!",
            "password_confirm": "TestPass123!",
            "first_name": "Тест",
            "last_name": "Клієнт",
        },
        headers={"Host": store_host(default_store.slug)},
        follow_redirects=False,
    )
    assert resp.status_code == 302

    with app.app_context():
        user = User.get_by_email(email)
        assert user is not None
        assert user.is_verified is False
        assert user.store_id == default_store.id


def test_register_rejects_duplicate_email(client, default_store):
    email = unique_email("dupe")
    payload = {
        "email": email,
        "password": "TestPass123!",
        "password_confirm": "TestPass123!",
        "first_name": "A",
        "last_name": "B",
    }
    headers = {"Host": store_host(default_store.slug)}
    first = client.post("/register", data=payload, headers=headers)
    assert first.status_code == 302
    # /register автоматично логінить щойно зареєстрованого - без явного
    # логауту другий POST одразу редіректить у кабінет ще ДО перевірки email,
    # бо user_register() перевіряє current_user.is_authenticated найпершим.
    client.get("/logout", headers=headers)

    second = client.post("/register", data=payload, headers=headers)
    assert second.status_code == 200  # повертає форму з помилкою, не редіректить
    assert "вже існує" in second.get_data(as_text=True)


def test_login_wrong_password_stays_on_page(client, default_store):
    email = unique_email("loginwrong")
    headers = {"Host": store_host(default_store.slug)}
    client.post(
        "/register",
        data={
            "email": email,
            "password": "CorrectPass123!",
            "password_confirm": "CorrectPass123!",
            "first_name": "A",
            "last_name": "B",
        },
        headers=headers,
    )
    client.get("/logout", headers=headers)  # register() авто-логінить - вийти перед спробою логіну

    resp = client.post(
        "/login",
        data={"email": email, "password": "WrongPass"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.request.path == "/login"


def test_email_verification_round_trip(app, client, default_store):
    from services.tokens import generate_token, EMAIL_VERIFY_SALT

    email = unique_email("verifyme")
    client.post(
        "/register",
        data={
            "email": email,
            "password": "TestPass123!",
            "password_confirm": "TestPass123!",
            "first_name": "A",
            "last_name": "B",
        },
        headers={"Host": store_host(default_store.slug)},
    )
    with app.app_context():
        user = User.get_by_email(email)
        assert user.is_verified is False
        token = generate_token(user.email, EMAIL_VERIFY_SALT)

    resp = client.get(f"/verify-email/{token}", headers={"Host": store_host(default_store.slug)})
    assert resp.status_code == 302

    with app.app_context():
        user = User.get_by_email(email)
        assert user.is_verified is True


def test_email_verification_rejects_tampered_token(client, default_store):
    resp = client.get(
        "/verify-email/not-a-real-token",
        headers={"Host": store_host(default_store.slug)},
    )
    assert resp.status_code == 302  # graceful redirect, не 500


def test_password_reset_round_trip(app, client, default_store):
    from services.tokens import generate_token, PASSWORD_RESET_SALT

    email = unique_email("resetme")
    client.post(
        "/register",
        data={
            "email": email,
            "password": "OldPass123!",
            "password_confirm": "OldPass123!",
            "first_name": "A",
            "last_name": "B",
        },
        headers={"Host": store_host(default_store.slug)},
    )

    with app.app_context():
        token = generate_token(email, PASSWORD_RESET_SALT)

    resp = client.post(
        f"/reset-password/{token}",
        data={"password": "BrandNewPass456!", "password_confirm": "BrandNewPass456!"},
        headers={"Host": store_host(default_store.slug)},
    )
    assert resp.status_code == 302

    with app.app_context():
        user = User.get_by_email(email)
        assert user.check_password("OldPass123!") is False
        assert user.check_password("BrandNewPass456!") is True


def test_password_reset_rejects_mismatched_confirmation(app, client, default_store):
    from services.tokens import generate_token, PASSWORD_RESET_SALT

    email = unique_email("resetmismatch")
    client.post(
        "/register",
        data={
            "email": email,
            "password": "OldPass123!",
            "password_confirm": "OldPass123!",
            "first_name": "A",
            "last_name": "B",
        },
        headers={"Host": store_host(default_store.slug)},
    )

    with app.app_context():
        token = generate_token(email, PASSWORD_RESET_SALT)

    resp = client.post(
        f"/reset-password/{token}",
        data={"password": "NewPass1!", "password_confirm": "DoesNotMatch"},
        headers={"Host": store_host(default_store.slug)},
    )
    assert resp.status_code == 200

    with app.app_context():
        user = User.get_by_email(email)
        assert user.check_password("OldPass123!") is True
