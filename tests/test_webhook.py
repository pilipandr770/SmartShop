"""
Регресія на аудит безпеки: /webhook/stripe має ВІДМОВЛЯТИ будь-якому
запиту без коректного Stripe-підпису - раніше (до фіксу) відсутній
STRIPE_WEBHOOK_SECRET означав, що ендпоінт беззастережно довіряв будь-якому
JSON, надісланому напряму, без жодної участі Stripe.
"""
import hmac
import hashlib
import json
import time

from .conftest import store_host


def _sign(secret, payload_bytes, timestamp=None):
    timestamp = timestamp or int(time.time())
    signed_payload = f"{timestamp}.".encode() + payload_bytes
    signature = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={signature}"


def test_webhook_rejects_missing_signature(client, default_store):
    payload = json.dumps({"type": "checkout.session.completed"}).encode()
    resp = client.post(
        "/webhook/stripe",
        data=payload,
        content_type="application/json",
        headers={"Host": store_host(default_store.slug)},
    )
    assert resp.status_code == 400


def test_webhook_rejects_wrong_signature(client, default_store):
    payload = json.dumps({"type": "checkout.session.completed"}).encode()
    bad_sig = _sign("wrong-secret-entirely", payload)
    resp = client.post(
        "/webhook/stripe",
        data=payload,
        content_type="application/json",
        headers={"Host": store_host(default_store.slug), "Stripe-Signature": bad_sig},
    )
    assert resp.status_code == 400


def test_webhook_accepts_correctly_signed_event(app, client, default_store):
    payload = json.dumps({
        "id": "evt_test",
        "type": "customer.subscription.updated",
        "data": {"object": {"id": "sub_does_not_exist", "status": "active"}},
    }).encode()
    secret = app.config["STRIPE_WEBHOOK_SECRET"]
    good_sig = _sign(secret, payload)

    resp = client.post(
        "/webhook/stripe",
        data=payload,
        content_type="application/json",
        headers={"Host": store_host(default_store.slug), "Stripe-Signature": good_sig},
    )
    assert resp.status_code == 200


def test_webhook_rejects_when_secret_unset(app, client, default_store):
    """Якщо STRIPE_WEBHOOK_SECRET взагалі не налаштовано - ендпоінт має
    відповідати 503, а НЕ мовчки довіряти вхідному JSON (сам знайдений
    і виправлений під час аудиту дефект)."""
    original = app.config["STRIPE_WEBHOOK_SECRET"]
    app.config["STRIPE_WEBHOOK_SECRET"] = ""
    try:
        payload = json.dumps({"type": "checkout.session.completed"}).encode()
        resp = client.post(
            "/webhook/stripe",
            data=payload,
            content_type="application/json",
            headers={"Host": store_host(default_store.slug)},
        )
        assert resp.status_code == 503
    finally:
        app.config["STRIPE_WEBHOOK_SECRET"] = original


def test_dead_payment_success_endpoint_is_gone(client, default_store):
    resp = client.post(
        "/webhook/payment-success",
        json={"order_id": 1},
        headers={"Host": store_host(default_store.slug)},
    )
    assert resp.status_code == 404
