"""
Адреса доставки -> вибір тарифу перевізника -> Stripe Checkout -> сторінка
успіху/скасування -> webhook підтвердження оплати. Найчутливіший до
грошей розділ усього застосунку - реальний прийом оплат від клієнтів
магазину через Stripe Connect (destination charge).

Винесено з app.py ("ДОСТАВКА: АДРЕСА ТА ВИБІР ТАРИФУ" + "STRIPE CHECKOUT")
як частина Phase 2 плану (SWOT 2026-08-08) - останній, найризикованіший
кластер. Логіка перенесена без жодної зміни поведінки: жоден платіжний чи
безпековий чек (webhook-підпис, перевірка payment_status, store_id-скоуп)
не змінено, лише мінімальні правки для роботи як blueprint.
"""
from datetime import datetime

from flask import (
    Blueprint, current_app, g, jsonify, redirect, render_template, request,
    session, url_for, flash,
)
from flask_babel import gettext as _

from extensions import db, csrf
from models.settings import SiteSettings
from models.order import Order, OrderItem
from models.store import Store
from services.cart import get_cart, save_cart

try:
    import stripe
    STRIPE_AVAILABLE = True
except ImportError:
    STRIPE_AVAILABLE = False

checkout_bp = Blueprint("checkout", __name__)


def _cart_weight_kg():
    """Сумарна вага кошика (кг) для запиту тарифів. За відсутності
    ваги товару використовується дефолт 1.0 кг за одиницю."""
    from models.product import Product
    cart = get_cart()
    total_weight = 0.0
    for product_id_str, qty in cart.items():
        product = Product.query.filter_by(id=int(product_id_str), store_id=g.store.id).first()
        if product and product.is_active:
            total_weight += (product.weight_kg or 1.0) * qty
    return total_weight or 1.0


@checkout_bp.route("/checkout/address", methods=["GET", "POST"])
def checkout_address():
    """Форма адреси доставки - показується тільки якщо в магазині
    налаштовано хоча б одну службу доставки (інакше кнопка в кошику
    веде одразу на /checkout, як і раніше)."""
    settings = SiteSettings.get_or_create(g.store.id)
    cart = get_cart()
    if not cart:
        flash(_("Ваш кошик порожній."), "warning")
        return redirect(url_for("cart.cart_page"))

    if request.method == "POST":
        address = {
            "name": request.form.get("name", "").strip(),
            "phone": request.form.get("phone", "").strip(),
            "email": request.form.get("email", "").strip(),
            "street": request.form.get("street", "").strip(),
            "city": request.form.get("city", "").strip(),
            "postal_code": request.form.get("postal_code", "").strip(),
            "country_code": request.form.get("country_code", "").strip().upper(),
        }
        # Адреса потрібна лише для доставки перевізником - для самовивозу
        # обов'язкові тільки контактні дані, тому тут вимагаємо мінімум.
        missing = [k for k in ("name", "phone") if not address[k]]
        if missing:
            flash(_("Вкажіть ім'я та телефон."), "danger")
            return render_template("checkout_address.html", settings=settings, form=address)

        session["checkout_address"] = address
        return redirect(url_for(".checkout_shipping"))

    return render_template(
        "checkout_address.html",
        settings=settings,
        form=session.get("checkout_address", {}),
    )


@checkout_bp.route("/checkout/shipping", methods=["GET", "POST"])
def checkout_shipping():
    """Вибір тарифу доставки на основі адреси з попереднього кроку."""
    from services.shipping.registry import get_enabled_providers
    from services.shipping.base import Address, ShippingProviderError

    settings = SiteSettings.get_or_create(g.store.id)
    address = session.get("checkout_address")
    if not address:
        return redirect(url_for(".checkout_address"))

    if request.method == "POST":
        carrier = request.form.get("carrier", "")
        session["checkout_shipping"] = {
            "carrier": carrier,
            "service_code": request.form.get("service_code", ""),
            "name": request.form.get("name", ""),
            "price": request.form.get("price", 0.0, type=float),
            "is_pickup": carrier == "pickup",
        }
        return redirect(url_for(".checkout"))

    providers = get_enabled_providers(g.store.id)
    destination = Address.from_dict(address)
    weight_kg = _cart_weight_kg()

    options = []
    if settings.pickup_enabled:
        options.append({
            "carrier": "pickup",
            "carrier_label": "🏬 Самовивіз",
            "service_code": "",
            "name": settings.pickup_address or "Самовивіз з магазину",
            "price": 0.0,
            "currency": settings.default_currency or "EUR",
            "eta_days": None,
        })

    for account, provider in providers:
        try:
            rates = provider.get_rates(Address.from_dict(account.origin_address), destination, weight_kg)
            for rate in rates:
                options.append({
                    "carrier": account.carrier,
                    "carrier_label": account.carrier_label,
                    "service_code": rate.service_code,
                    "name": rate.name,
                    "price": rate.price,
                    "currency": rate.currency,
                    "eta_days": rate.eta_days,
                })
        except ShippingProviderError as e:
            current_app.logger.warning(f"Shipping rate lookup failed for {account.carrier}: {e}")

    if not options:
        # Жодна служба не відповіла (або жодної не налаштовано) -
        # продовжуємо без доставки, як і раніше.
        session["checkout_shipping"] = None
        return redirect(url_for(".checkout"))

    return render_template(
        "checkout_shipping.html",
        settings=settings,
        options=options,
        address=address,
    )


@checkout_bp.route("/checkout", methods=["GET", "POST"])
def checkout():
    """Створити Stripe Checkout сесію."""
    from models.product import Product

    if not STRIPE_AVAILABLE or not current_app.config["STRIPE_SECRET_KEY"]:
        flash(_("Stripe не налаштовано. Зверніться до адміністратора."), "danger")
        return redirect(url_for("cart.cart_page"))

    if not g.store.can_accept_payments:
        flash(_("Цей магазин ще не підключив прийом оплат. Зверніться до продавця."), "danger")
        return redirect(url_for("cart.cart_page"))

    cart = get_cart()
    if not cart:
        flash(_("Ваш кошик порожній."), "warning")
        return redirect(url_for("cart.cart_page"))

    line_items = []
    order_items_data = []
    total = 0.0

    for product_id_str, qty in cart.items():
        product = Product.query.filter_by(id=int(product_id_str), store_id=g.store.id).first()
        if product and product.is_active:
            product_data = {
                "name": product.name,
                "images": [product.image_url] if product.image_url else [],
            }
            # Stripe відхиляє порожній рядок для description (тільки
            # непорожнє значення або повна відсутність ключа) - товар без
            # short_description раніше ламав весь checkout.
            if product.short_description:
                product_data["description"] = product.short_description
            line_items.append({
                "price_data": {
                    "currency": product.currency.lower(),
                    "product_data": product_data,
                    "unit_amount": int(product.price * 100),  # Stripe працює з центами
                },
                "quantity": qty,
            })
            order_items_data.append({
                "product_id": product.id,
                "product_name": product.name,
                "price": product.price,
                "quantity": qty,
                "currency": product.currency,
            })
            total += product.price * qty

    if not line_items:
        flash(_("Не вдалося знайти товари в кошику."), "danger")
        return redirect(url_for("cart.cart_page"))

    # Адреса й тариф доставки (опційно - якщо магазин не налаштував
    # службу доставки, обидва відсутні і поведінка лишається такою ж,
    # як до впровадження цієї фічі).
    checkout_address = session.pop("checkout_address", None)
    checkout_shipping = session.pop("checkout_shipping", None)
    shipping_price = float(checkout_shipping["price"]) if checkout_shipping else 0.0

    if shipping_price > 0:
        line_items.append({
            "price_data": {
                "currency": "eur",
                "product_data": {"name": f"Доставка: {checkout_shipping['name']}"},
                "unit_amount": int(shipping_price * 100),
            },
            "quantity": 1,
        })

    try:
        # Створюємо замовлення в БД
        order = Order(
            store_id=g.store.id,
            status="pending",
            amount=total + shipping_price,
            subtotal=total,
            currency="EUR",
            shipping_cost=shipping_price,
            shipping_method=checkout_shipping["name"] if checkout_shipping else None,
            is_pickup=bool(checkout_shipping and checkout_shipping.get("is_pickup")),
            shipping_address=checkout_address["street"] if checkout_address else None,
            shipping_city=checkout_address["city"] if checkout_address else None,
            shipping_postal_code=checkout_address["postal_code"] if checkout_address else None,
            shipping_country=checkout_address["country_code"] if checkout_address else None,
            customer_name=checkout_address["name"] if checkout_address else None,
            customer_phone=checkout_address["phone"] if checkout_address else None,
            locale=session.get("lang", current_app.config["BABEL_DEFAULT_LOCALE"]),
        )
        db.session.add(order)
        db.session.flush()  # Отримуємо ID
        order.order_number = f"{'B2B' if order.is_b2b else 'SM'}-{datetime.utcnow().year}-{order.id:05d}"

        # Додаємо товари до замовлення
        for item_data in order_items_data:
            order_item = OrderItem(
                store_id=g.store.id,
                order_id=order.id,
                product_id=item_data["product_id"],
                product_name=item_data["product_name"],
                price=item_data["price"],
                quantity=item_data["quantity"],
                currency=item_data["currency"],
            )
            db.session.add(order_item)

        # Створюємо Stripe Checkout сесію. Гроші клієнта йдуть напряму
        # власнику магазину через destination charge (transfer_data) -
        # платформа лишається лише посередником Checkout-сесії й не
        # утримує кошти на своєму рахунку та не бере комісії.
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=line_items,
            mode="payment",
            success_url=url_for(".checkout_success", _external=True) + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=url_for(".checkout_cancel", _external=True),
            payment_intent_data={
                "transfer_data": {"destination": g.store.stripe_connect_account_id},
            },
            metadata={
                "order_id": str(order.id),
                "store_id": str(g.store.id),
                "shipping_carrier": checkout_shipping["carrier"] if checkout_shipping else "",
                "shipping_service_code": checkout_shipping["service_code"] if checkout_shipping else "",
            },
        )

        order.stripe_session_id = checkout_session.id
        db.session.commit()

        return redirect(checkout_session.url)

    except stripe.error.StripeError as e:
        db.session.rollback()
        # Клієнту не показуємо сирий текст помилки Stripe (може містити
        # деталі конфігурації акаунту продавця) - лише продавцю в логах.
        current_app.logger.error(f"Checkout Stripe error for store_id={g.store.id}: {e}")
        flash(_("Оплата тимчасово недоступна. Спробуйте пізніше або зверніться до продавця."), "danger")
        return redirect(url_for("cart.cart_page"))


def _auto_create_shipment(order, task, carrier_code, service_code):
    """
    Автоматично створює відправлення в перевізника (лейбл + трек-номер)
    для щойно оплаченого замовлення, якщо для цього магазину налаштовано
    відповідний CarrierAccount. Ніколи не пробрасує виняток назовні -
    збій перевізника не повинен ламати підтвердження оплати; в такому
    разі WarehouseTask лишається з порожнім tracking_number, і адмін
    може ввести його вручну на сторінці завдання складу (як і раніше).
    """
    if not carrier_code or not task:
        return
    try:
        from services.shipping.registry import get_provider_for_carrier
        from services.shipping.base import Address, ShippingProviderError

        account, provider = get_provider_for_carrier(order.store_id, carrier_code)
        if not provider:
            return

        origin = Address.from_dict(account.origin_address)
        destination = Address(
            name=order.customer_name or "",
            street=order.shipping_address or "",
            city=order.shipping_city or "",
            postal_code=order.shipping_postal_code or "",
            country_code=order.shipping_country or "",
            phone=order.customer_phone or "",
        )
        weight_kg = sum(
            (item.product.weight_kg or 1.0) * item.quantity
            for item in order.items if item.product
        ) or 1.0

        result = provider.create_shipment(
            origin, destination, weight_kg, service_code,
            reference=order.order_number or str(order.id),
        )
        task.tracking_number = result.tracking_number
        task.carrier = account.carrier_label
        task.label_url = result.label_url
        db.session.commit()
    except ShippingProviderError as e:
        current_app.logger.warning(f"Automatic shipment creation failed for order #{order.id}: {e}")
    except Exception as e:
        current_app.logger.warning(f"Automatic shipment creation error for order #{order.id}: {e}")


@checkout_bp.route("/checkout/success")
def checkout_success():
    """Сторінка успішної оплати."""
    settings = SiteSettings.get_or_create(g.store.id)
    session_id = request.args.get("session_id")

    order = None
    if session_id and STRIPE_AVAILABLE and current_app.config["STRIPE_SECRET_KEY"]:
        try:
            checkout_session = stripe.checkout.Session.retrieve(session_id)
            order = Order.query.filter_by(stripe_session_id=session_id, store_id=g.store.id).first()

            # КРИТИЧНО: успішний retrieve() лише означає, що session_id
            # існує - НЕ означає, що оплата відбулась. Без цієї перевірки
            # клієнт міг скасувати оплату на сторінці Stripe і вручну
            # перейти на /checkout/success?session_id=... - замовлення
            # позначилось б оплаченим без жодної реальної транзакції.
            if order and order.status == "pending" and checkout_session.payment_status == "paid":
                order.status = "paid"
                order.paid_at = datetime.utcnow()
                order.customer_email = checkout_session.customer_details.email if checkout_session.customer_details else None
                order.customer_name = checkout_session.customer_details.name if checkout_session.customer_details else None
                order.stripe_payment_intent = checkout_session.payment_intent
                db.session.commit()

                # Відправити email підтвердження замовлення
                if order.customer_email:
                    try:
                        from services.email_service import send_order_confirmation
                        send_order_confirmation(order.customer_email, order)
                        current_app.logger.info(f'Order confirmation email sent to {order.customer_email}')
                    except Exception as e:
                        current_app.logger.error(f'Failed to send order confirmation: {str(e)}')

                # Створюємо завдання для складу
                try:
                    from models.warehouse import WarehouseTask
                    existing_task = WarehouseTask.query.filter_by(order_id=order.id).first()
                    if not existing_task:
                        task = WarehouseTask.create_from_order(
                            order_id=order.id,
                            priority=2 if getattr(order, 'is_b2b', False) else 3,
                            notes=getattr(order, 'notes', ''),
                        )
                        metadata = checkout_session.metadata or {}
                        _auto_create_shipment(
                            order, task,
                            metadata.get("shipping_carrier"),
                            metadata.get("shipping_service_code"),
                        )
                except Exception:
                    pass  # Якщо модуль складу не доступний

                # Очищаємо кошик
                save_cart({})
        except Exception:
            pass

    return render_template("checkout_success.html", settings=settings, order=order)


@checkout_bp.route("/checkout/cancel")
def checkout_cancel():
    """Сторінка скасованої оплати."""
    SiteSettings.get_or_create(g.store.id)
    flash(_("Оплату скасовано. Ви можете спробувати ще раз."), "info")
    return redirect(url_for("cart.cart_page"))


@checkout_bp.route("/webhook/stripe", methods=["POST"])
@csrf.exempt
def stripe_webhook():
    """Webhook для Stripe. CSRF-виняток: запит приходить від Stripe,
    не з браузера з session-кукою, і автентичність перевіряється
    підписом (stripe.Webhook.construct_event), а не CSRF-токеном."""
    if not STRIPE_AVAILABLE:
        return jsonify({"error": _("Stripe not available")}), 400

    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature")
    webhook_secret = current_app.config["STRIPE_WEBHOOK_SECRET"]

    # КРИТИЧНО: без webhook_secret немає способу перевірити, що запит
    # справді прийшов від Stripe, а не від будь-кого, хто відправив
    # довільний JSON на цей публічний ендпоінт. Раніше тут був фолбек
    # на stripe.Event.construct_from(), який довіряв НЕПІДПИСАНОМУ
    # тілу запиту - це дозволяло будь-кому позначити чуже замовлення
    # оплаченим або активувати підписку магазину без жодної реальної
    # транзакції. Без секрету обробка події повинна відмовляти, а не
    # довіряти вхідним даним.
    if not webhook_secret:
        current_app.logger.warning(
            "Отримано запит на /webhook/stripe, але STRIPE_WEBHOOK_SECRET не налаштовано - "
            "подію відхилено без верифікації підпису."
        )
        return jsonify({"error": _("Webhook not configured")}), 503

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except ValueError:
        return jsonify({"error": _("Invalid payload")}), 400
    except stripe.error.SignatureVerificationError:
        return jsonify({"error": _("Invalid signature")}), 400

    # Обробка події
    if event["type"] == "checkout.session.completed":
        session_data = event["data"]["object"]
        session_id = session_data["id"]

        if session_data.get("mode") == "subscription":
            # SaaS-підписка нового/існуючого Store (не замовлення в магазині)
            store_id = (session_data.get("metadata") or {}).get("store_id")
            if store_id:
                store = Store.query.get(int(store_id))
                if store:
                    store.stripe_customer_id = session_data.get("customer")
                    store.stripe_subscription_id = session_data.get("subscription")
                    store.subscription_status = "active"
                    db.session.commit()
        else:
            order = Order.query.filter_by(stripe_session_id=session_id).first()
            if order:
                order.status = "paid"
                order.paid_at = datetime.utcnow()
                order.customer_email = session_data.get("customer_details", {}).get("email")
                order.customer_name = session_data.get("customer_details", {}).get("name")
                order.stripe_payment_intent = session_data.get("payment_intent")
                db.session.commit()

                # Створюємо завдання для складу
                try:
                    from models.warehouse import WarehouseTask
                    existing_task = WarehouseTask.query.filter_by(order_id=order.id).first()
                    if not existing_task:
                        task = WarehouseTask.create_from_order(
                            order_id=order.id,
                            priority=2 if getattr(order, 'is_b2b', False) else 3,
                            notes=getattr(order, 'notes', ''),
                        )
                        webhook_metadata = session_data.get("metadata") or {}
                        _auto_create_shipment(
                            order, task,
                            webhook_metadata.get("shipping_carrier"),
                            webhook_metadata.get("shipping_service_code"),
                        )
                except Exception:
                    pass  # Якщо модуль складу не доступний

    elif event["type"] in ("customer.subscription.updated", "customer.subscription.deleted"):
        # Синхронізуємо статус підписки Store (оплата не пройшла, скасування тощо)
        subscription_data = event["data"]["object"]
        store = Store.query.filter_by(stripe_subscription_id=subscription_data["id"]).first()
        if store:
            stripe_status = subscription_data.get("status")
            if event["type"] == "customer.subscription.deleted" or stripe_status == "canceled":
                store.subscription_status = "canceled"
            elif stripe_status in ("past_due", "unpaid", "incomplete_expired"):
                store.subscription_status = "past_due"
            elif stripe_status in ("active", "trialing"):
                store.subscription_status = stripe_status
            db.session.commit()

    return jsonify({"status": "success"}), 200
