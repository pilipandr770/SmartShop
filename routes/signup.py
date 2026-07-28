"""
SaaS-реєстрація: створення нового Store (магазину-орендаря) + підписка Stripe.
"""
import os
import re

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_user, current_user

from extensions import db
from models.user import User, UserRole
from models.store import Store, StoreSubscriptionStatus, PLAN_CHOICES, DEFAULT_PLAN

try:
    import stripe
    STRIPE_AVAILABLE = True
except ImportError:
    STRIPE_AVAILABLE = False

signup_bp = Blueprint("signup", __name__, url_prefix="/signup")

# Мапа plan -> ENV змінна з Stripe Price ID (одна ціна на план, EUR/міс).
PLAN_PRICE_ENV = {
    "starter": "STRIPE_PRICE_STARTER",
    "pro": "STRIPE_PRICE_PRO",
    "business": "STRIPE_PRICE_BUSINESS",
}


def _slugify(value):
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9-]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value[:63]


def _get_plan_price_id(plan):
    env_var = PLAN_PRICE_ENV.get(plan)
    return os.environ.get(env_var, "") if env_var else ""


@signup_bp.route("", methods=["GET", "POST"])
def new_store():
    """Форма створення нового магазину (SaaS-реєстрація власника)."""
    if current_user.is_authenticated and current_user.is_store_owner:
        flash("У вас вже є магазин. Керуйте ним з адмінки.", "info")
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        store_name = request.form.get("store_name", "").strip()
        slug = request.form.get("slug", "").strip() or _slugify(store_name)
        slug = _slugify(slug)
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")
        plan = request.form.get("plan", DEFAULT_PLAN)
        if plan not in PLAN_CHOICES:
            plan = DEFAULT_PLAN

        errors = []
        if not store_name:
            errors.append("Назва магазину обов'язкова.")
        if not slug or len(slug) < 3:
            errors.append("Адреса магазину (slug) має бути не менше 3 символів (лише латиниця, цифри, дефіс).")
        elif not Store.slug_is_available(slug):
            errors.append(f"Адреса «{slug}» вже зайнята. Оберіть іншу.")
        if not email:
            errors.append("Email обов'язковий.")
        elif User.get_by_email(email):
            errors.append("Користувач з таким email вже існує. Увійдіть у свій акаунт.")
        if not password or len(password) < 8:
            errors.append("Пароль має бути не менше 8 символів.")
        elif password != password_confirm:
            errors.append("Паролі не співпадають.")

        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("auth/signup.html", plans=PLAN_CHOICES, form=request.form)

        owner = User(
            email=email,
            role=UserRole.STORE_OWNER.value,
            first_name=request.form.get("owner_name", "").strip() or None,
            is_verified=True,
        )
        owner.set_password(password)
        db.session.add(owner)
        db.session.flush()

        store = Store(
            name=store_name,
            slug=slug,
            owner_user_id=owner.id,
            plan=plan,
            subscription_status=StoreSubscriptionStatus.TRIALING,
        )
        db.session.add(store)
        db.session.commit()

        login_user(owner)

        price_id = _get_plan_price_id(plan)
        if STRIPE_AVAILABLE and current_app.config.get("STRIPE_SECRET_KEY") and price_id:
            try:
                checkout_session = stripe.checkout.Session.create(
                    payment_method_types=["card"],
                    line_items=[{"price": price_id, "quantity": 1}],
                    mode="subscription",
                    customer_email=email,
                    success_url=url_for("signup.success", _external=True) + "?session_id={CHECKOUT_SESSION_ID}",
                    cancel_url=url_for("signup.new_store", _external=True),
                    metadata={"store_id": str(store.id)},
                    subscription_data={"metadata": {"store_id": str(store.id)}},
                )
                return redirect(checkout_session.url)
            except stripe.error.StripeError as e:
                flash(f"Магазин створено, але не вдалося відкрити оплату: {e}. Спробуйте пізніше в адмінці.", "warning")
                return redirect(url_for("admin_dashboard"))

        # Stripe не налаштовано (лише для локальної розробки/демо) - одразу
        # активуємо магазин без реальної оплати.
        store.subscription_status = StoreSubscriptionStatus.ACTIVE
        db.session.commit()
        flash(f"✅ Магазин «{store.name}» створено! (Stripe не налаштовано — підписка активована без оплати для розробки.)", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("auth/signup.html", plans=PLAN_CHOICES, form={})


@signup_bp.route("/success")
def success():
    """Сторінка після повернення з Stripe Checkout (підписка)."""
    session_id = request.args.get("session_id")
    store = None

    if session_id and STRIPE_AVAILABLE and current_app.config.get("STRIPE_SECRET_KEY"):
        try:
            checkout_session = stripe.checkout.Session.retrieve(session_id)
            store_id = (checkout_session.get("metadata") or {}).get("store_id")
            if store_id:
                store = Store.query.get(int(store_id))
                if store and checkout_session.get("subscription"):
                    store.stripe_customer_id = checkout_session.get("customer")
                    store.stripe_subscription_id = checkout_session.get("subscription")
                    store.subscription_status = StoreSubscriptionStatus.ACTIVE
                    db.session.commit()
        except Exception as e:
            current_app.logger.error(f"Signup success: failed to reconcile Stripe session: {e}")

    return render_template("auth/signup_success.html", store=store)
