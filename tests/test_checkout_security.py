"""
Регресійні тести на найдорожчий клас багів - оплату:
1. checkout_success() не повинен позначати замовлення оплаченим, якщо
   Stripe каже payment_status != "paid" (сам аудит безпеки).
2. Побічно виявлений під час написання цих тестів баг: код звертався до
   неіснуючого order.email (мало бути order.customer_email) - AttributeError
   мовчки ковтався try/except, тому email підтвердження, завдання складу і
   очищення кошика НІКОЛИ не виконувались для жодного реального оплаченого
   замовлення. Тест нижче ловить точно цей регрес.
"""
from unittest.mock import patch, MagicMock

from extensions import db
from models.order import Order

from .conftest import store_host


def _make_pending_order(store_id, session_id):
    order = Order(
        store_id=store_id,
        stripe_session_id=session_id,
        status="pending",
        subtotal=100.0,
        amount=100.0,
        currency="EUR",
    )
    db.session.add(order)
    db.session.commit()
    return order.id


class _FakeCustomerDetails:
    email = "buyer@example.com"
    name = "Buyer Name"


def _fake_session(payment_status):
    fake = MagicMock()
    fake.payment_status = payment_status
    fake.customer_details = _FakeCustomerDetails()
    fake.payment_intent = "pi_test_123"
    fake.metadata = {}
    return fake


def test_checkout_success_ignores_unpaid_session(app, client, default_store):
    """Клієнт скасував оплату на Stripe і вручну відкрив success-URL зі
    старим session_id - замовлення НЕ повинно позначитись оплаченим."""
    with app.app_context():
        order_id = _make_pending_order(default_store.id, "cs_test_unpaid_001")

    with patch("stripe.checkout.Session.retrieve", return_value=_fake_session("unpaid")):
        resp = client.get(
            "/checkout/success",
            query_string={"session_id": "cs_test_unpaid_001"},
            headers={"Host": store_host(default_store.slug)},
        )
    assert resp.status_code == 200

    with app.app_context():
        order = db.session.get(Order, order_id)
        assert order.status == "pending"


def test_checkout_success_marks_paid_and_sets_customer_email(app, client, default_store):
    """Регресійний тест на знайдений під час написання тестів баг:
    раніше код падав на неіснуючому order.email (AttributeError, мовчки
    проковтнутий try/except), і повністю пропускав встановлення
    customer_email/paid_at попри те, що order.status все ж ставало "paid"."""
    with app.app_context():
        order_id = _make_pending_order(default_store.id, "cs_test_paid_001")

    with patch("stripe.checkout.Session.retrieve", return_value=_fake_session("paid")):
        resp = client.get(
            "/checkout/success",
            query_string={"session_id": "cs_test_paid_001"},
            headers={"Host": store_host(default_store.slug)},
        )
    assert resp.status_code == 200

    with app.app_context():
        order = db.session.get(Order, order_id)
        assert order.status == "paid"
        assert order.customer_email == "buyer@example.com"
        assert order.paid_at is not None


def test_checkout_success_does_not_touch_other_stores_order(app, client, default_store):
    """store_id-фільтр у запиті замовлення - той самий session_id не має
    зачепити замовлення іншого магазину."""
    from models.store import Store, StoreSubscriptionStatus
    from models.user import User, UserRole
    from .conftest import unique_email

    with app.app_context():
        owner = User(email=unique_email("other-owner"), role=UserRole.STORE_OWNER.value, is_verified=True)
        owner.set_password("Pass123!")
        db.session.add(owner)
        db.session.flush()
        other_store = Store(
            name="Other Store", slug=f"other-{unique_email('')[:6]}",
            owner_user_id=owner.id, plan="starter",
            subscription_status=StoreSubscriptionStatus.ACTIVE,
        )
        db.session.add(other_store)
        db.session.commit()
        other_store_id = other_store.id
        order_id = _make_pending_order(other_store_id, "cs_test_cross_store")

    # Запит іде на default_store (інший магазин, ніж той, кому належить order)
    with patch("stripe.checkout.Session.retrieve", return_value=_fake_session("paid")):
        client.get(
            "/checkout/success",
            query_string={"session_id": "cs_test_cross_store"},
            headers={"Host": store_host(default_store.slug)},
        )

    with app.app_context():
        order = db.session.get(Order, order_id)
        assert order.status == "pending"  # НЕ зачепило чуже замовлення
