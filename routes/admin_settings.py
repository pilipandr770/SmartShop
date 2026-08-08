"""
Налаштування магазину, що не вписуються в "загальні" admin/settings
(app.py): двофакторна автентифікація власника, власний домен магазину
(+ Traefik file-provider реєстрація), Stripe Connect (прийом оплат від
клієнтів магазину), самостійне видалення акаунту (GDPR "право на
забуття"), облікові записи перевізників (DHL/UPS) + самовивіз.

Об'єднані в один blueprint (а не 5 окремих), бо: (а) кожен розділ сам по
собі замалий, щоб виправдати окремий файл, (б) є реальна внутрішня
залежність - _delete_store_account (GDPR) викликає
_remove_custom_domain_router (Custom Domain), тож їм і так треба бути
в одному модулі. Сьомий крок Phase 2 плану (SWOT 2026-08-08).
"""
import os
import uuid
from datetime import datetime

from flask import (
    Blueprint, request, redirect, url_for, flash, render_template, g,
    current_app, abort,
)
from flask_babel import gettext as _
from flask_login import current_user, logout_user as flask_logout_user

from extensions import db
from models.settings import SiteSettings
from services.admin_auth import admin_required

try:
    import stripe
    STRIPE_AVAILABLE = True
except ImportError:
    STRIPE_AVAILABLE = False

settings_bp = Blueprint("settings", __name__)

BASE_DOMAIN = os.environ.get("BASE_DOMAIN", "").lower().strip().strip(".")


# =========================================================================
# 2FA (TOTP), опційно
# =========================================================================

@settings_bp.route("/admin/security/2fa", methods=["GET"])
@admin_required
def admin_2fa():
    return render_template("admin/security_2fa.html", user=current_user)


@settings_bp.route("/admin/security/2fa/setup", methods=["GET", "POST"])
@admin_required
def admin_2fa_setup():
    if current_user.totp_enabled:
        flash(_("2FA вже увімкнена."), "info")
        return redirect(url_for(".admin_2fa"))

    if request.method == "POST":
        code = request.form.get("code", "").strip()
        backup_codes = current_user.confirm_totp_setup(code)
        if backup_codes:
            db.session.commit()
            flash(_("Двофакторну автентифікацію увімкнено."), "success")
            return render_template("admin/security_2fa_backup_codes.html", backup_codes=backup_codes)
        flash(_("Невірний код. Перевірте, що годинник телефону синхронізований, і спробуйте ще раз."), "danger")

    # GET (або невдала спроба підтвердження) - показуємо QR-код для
    # поточного (можливо, щойно перегенерованого) непідтвердженого секрету.
    if not current_user.totp_secret:
        current_user.start_totp_setup()
        db.session.commit()

    qr_data_uri = _totp_qr_data_uri(current_user.get_totp_uri())
    return render_template(
        "admin/security_2fa_setup.html",
        qr_data_uri=qr_data_uri,
        secret=current_user.totp_secret,
    )


@settings_bp.route("/admin/security/2fa/restart", methods=["POST"])
@admin_required
def admin_2fa_restart():
    """Перегенерувати QR-код (напр. якщо попередній не відсканувався)."""
    current_user.start_totp_setup()
    db.session.commit()
    return redirect(url_for(".admin_2fa_setup"))


@settings_bp.route("/admin/security/2fa/disable", methods=["POST"])
@admin_required
def admin_2fa_disable():
    password = request.form.get("password", "")
    if not current_user.check_password(password):
        flash(_("Невірний пароль."), "danger")
        return redirect(url_for(".admin_2fa"))
    current_user.disable_totp()
    db.session.commit()
    flash(_("Двофакторну автентифікацію вимкнено."), "success")
    return redirect(url_for(".admin_2fa"))


@settings_bp.route("/admin/security/2fa/backup-codes/regenerate", methods=["POST"])
@admin_required
def admin_2fa_regenerate_backup_codes():
    password = request.form.get("password", "")
    if not current_user.check_password(password):
        flash(_("Невірний пароль."), "danger")
        return redirect(url_for(".admin_2fa"))
    if not current_user.totp_enabled:
        return redirect(url_for(".admin_2fa"))
    backup_codes = current_user.regenerate_backup_codes()
    db.session.commit()
    flash(_("Нові резервні коди згенеровано. Старі коди більше не діють."), "success")
    return render_template("admin/security_2fa_backup_codes.html", backup_codes=backup_codes)


def _totp_qr_data_uri(uri):
    if not uri:
        return None
    import io
    import base64
    import qrcode
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


# =========================================================================
# Власний домен магазину
# =========================================================================

TRAEFIK_DYNAMIC_DIR = os.environ.get("TRAEFIK_DYNAMIC_DIR", "/app/traefik-dynamic")


def _custom_domain_router_path(store_id):
    return os.path.join(TRAEFIK_DYNAMIC_DIR, f"custom-{store_id}.yml")


def _write_custom_domain_router(store):
    """Реєструє власний домен магазину в Traefik через файловий провайдер -
    Traefik стежить за цією директорією (--providers.file.watch=true) і
    підхоплює новий роутер за кілька секунд, без перезапуску контейнера.
    Сертифікат для цього домену Traefik запитає автоматично при першому
    HTTPS-запиті (HTTP-01, оскільки чужий домен не в нашій DNS-зоні)."""
    if not os.path.isdir(TRAEFIK_DYNAMIC_DIR):
        current_app.logger.warning(f"TRAEFIK_DYNAMIC_DIR {TRAEFIK_DYNAMIC_DIR} не існує - пропускаю реєстрацію домену в Traefik")
        return
    router_name = f"custom-{store.id}"
    content = f"""http:
  routers:
    {router_name}:
      rule: "Host(`{store.custom_domain}`)"
      service: "smartshop@docker"
      entryPoints:
        - websecure
      tls:
        certResolver: letsencrypt
"""
    with open(_custom_domain_router_path(store.id), "w", encoding="utf-8") as f:
        f.write(content)


def _remove_custom_domain_router(store_id):
    path = _custom_domain_router_path(store_id)
    if os.path.exists(path):
        os.remove(path)


@settings_bp.route("/admin/settings/domain", methods=["GET", "POST"])
@admin_required
def admin_domain_settings():
    """Прив'язка власного домену клієнта (напр. myshop.com) до магазину."""
    store = g.store
    platform_ip = os.environ.get("PLATFORM_IP", "").strip()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "save":
            new_domain = request.form.get("custom_domain", "").strip().lower()
            for prefix in ("https://", "http://"):
                if new_domain.startswith(prefix):
                    new_domain = new_domain[len(prefix):]
            new_domain = new_domain.rstrip("/") or None

            if new_domain != store.custom_domain:
                if store.custom_domain:
                    _remove_custom_domain_router(store.id)
                store.custom_domain = new_domain
                store.custom_domain_verified = False
                store.custom_domain_verified_at = None
                db.session.commit()
                if new_domain:
                    flash(_("Домен збережено. Тепер налаштуйте DNS і натисніть «Перевірити»."), "info")
                else:
                    flash(_("Власний домен видалено."), "info")
            return redirect(url_for(".admin_domain_settings"))

        elif action == "verify":
            if not store.custom_domain:
                flash(_("Спочатку вкажіть домен."), "danger")
                return redirect(url_for(".admin_domain_settings"))

            if not platform_ip:
                flash(_("Платформа ще не налаштувала перевірку доменів. Зверніться до підтримки."), "danger")
                return redirect(url_for(".admin_domain_settings"))

            import socket
            try:
                resolved_ips = {info[4][0] for info in socket.getaddrinfo(store.custom_domain, None)}
            except Exception as e:
                resolved_ips = set()
                current_app.logger.info(f"Custom domain DNS lookup failed for {store.custom_domain}: {e}")

            if platform_ip in resolved_ips:
                store.custom_domain_verified = True
                store.custom_domain_verified_at = datetime.utcnow()
                db.session.commit()
                _write_custom_domain_router(store)
                flash(_("✅ Домен %(domain)s підтверджено і активовано! Може знадобитись кілька хвилин, щоб з'явився сертифікат.") % {"domain": store.custom_domain}, "success")
            else:
                store.custom_domain_verified = False
                db.session.commit()
                resolved_display = ", ".join(resolved_ips) if resolved_ips else "не резолвиться взагалі"
                flash(
                    _("Домен ще не вказує на платформу (зараз резолвиться: %(resolved)s). "
                      "Перевірте DNS-налаштування (A-запис на %(ip)s) і спробуйте ще раз за кілька хвилин.")
                    % {"resolved": resolved_display, "ip": platform_ip},
                    "warning",
                )
            return redirect(url_for(".admin_domain_settings"))

    return render_template("admin/domain_settings.html", store=store, platform_ip=platform_ip)


# =========================================================================
# Stripe Connect (прийом оплат від клієнтів магазину)
# =========================================================================
# На відміну від stripe_customer_id/stripe_subscription_id (це підписка
# МАГАЗИНУ на платформу), тут йдеться про власний Stripe Express-акаунт
# магазину, підключений через Connect. Оплати клієнтів магазину проводяться
# destination charge (checkout() в app.py передає transfer_data.destination) -
# кошти йдуть напряму власнику магазину, платформа їх не утримує і не бере
# комісії.

STRIPE_CONNECT_COUNTRIES = [
    ("DE", "Німеччина"), ("AT", "Австрія"), ("FR", "Франція"),
    ("NL", "Нідерланди"), ("ES", "Іспанія"), ("IT", "Італія"),
    ("PL", "Польща"), ("GB", "Велика Британія"), ("US", "США"),
]


def _create_connect_account_link(store):
    return stripe.AccountLink.create(
        account=store.stripe_connect_account_id,
        refresh_url=url_for(".admin_payments_refresh", _external=True),
        return_url=url_for(".admin_payments_return", _external=True),
        type="account_onboarding",
    )


@settings_bp.route("/admin/settings/payments", methods=["GET"])
@admin_required
def admin_payments_settings():
    """Підключення Stripe Connect для прийому оплат від клієнтів магазину."""
    return render_template(
        "admin/payments_settings.html",
        store=g.store,
        countries=STRIPE_CONNECT_COUNTRIES,
        stripe_configured=STRIPE_AVAILABLE and bool(current_app.config["STRIPE_SECRET_KEY"]),
    )


@settings_bp.route("/admin/settings/payments/connect", methods=["POST"])
@admin_required
def admin_payments_connect():
    store = g.store
    if not STRIPE_AVAILABLE or not current_app.config["STRIPE_SECRET_KEY"]:
        flash(_("Stripe не налаштовано на платформі."), "danger")
        return redirect(url_for(".admin_payments_settings"))

    country = (request.form.get("country") or "DE").strip().upper()

    try:
        if not store.stripe_connect_account_id:
            account = stripe.Account.create(
                type="express",
                country=country,
                email=current_user.email,
                capabilities={"transfers": {"requested": True}},
                business_profile={"name": store.name} if store.name else None,
            )
            store.stripe_connect_account_id = account.id
            db.session.commit()

        account_link = _create_connect_account_link(store)
        return redirect(account_link.url)
    except stripe.error.StripeError as e:
        flash(_("Помилка Stripe Connect: %(error)s") % {"error": e}, "danger")
        return redirect(url_for(".admin_payments_settings"))


@settings_bp.route("/admin/settings/payments/refresh")
@admin_required
def admin_payments_refresh():
    """Stripe перенаправляє сюди, якщо посилання на онбординг застаріло."""
    store = g.store
    if not store.stripe_connect_account_id:
        return redirect(url_for(".admin_payments_settings"))
    try:
        account_link = _create_connect_account_link(store)
        return redirect(account_link.url)
    except stripe.error.StripeError as e:
        flash(_("Помилка Stripe Connect: %(error)s") % {"error": e}, "danger")
        return redirect(url_for(".admin_payments_settings"))


@settings_bp.route("/admin/settings/payments/return")
@admin_required
def admin_payments_return():
    """Stripe перенаправляє сюди після (спроби) завершення онбордингу."""
    store = g.store
    if store.stripe_connect_account_id and STRIPE_AVAILABLE and current_app.config["STRIPE_SECRET_KEY"]:
        try:
            account = stripe.Account.retrieve(store.stripe_connect_account_id)
            transfers_active = (account.get("capabilities") or {}).get("transfers") == "active"
            store.stripe_connect_charges_enabled = bool(transfers_active)
            if transfers_active and not store.stripe_connect_onboarded_at:
                store.stripe_connect_onboarded_at = datetime.utcnow()
            db.session.commit()
            if transfers_active:
                flash(_("✅ Stripe підключено! Тепер ви можете приймати оплати від клієнтів."), "success")
            else:
                flash(_("Реєстрацію в Stripe ще не завершено. Заповніть усі необхідні дані та спробуйте ще раз."), "warning")
        except stripe.error.StripeError as e:
            flash(_("Не вдалося перевірити статус Stripe: %(error)s") % {"error": e}, "danger")
    return redirect(url_for(".admin_payments_settings"))


@settings_bp.route("/admin/settings/payments/reset", methods=["POST"])
@admin_required
def admin_payments_reset():
    """Відв'язати поточний Connect-акаунт від магазину (сам акаунт у Stripe не видаляється)."""
    store = g.store
    store.stripe_connect_account_id = None
    store.stripe_connect_charges_enabled = False
    store.stripe_connect_onboarded_at = None
    db.session.commit()
    flash(_("Stripe-акаунт відв'язано від магазину."), "info")
    return redirect(url_for(".admin_payments_settings"))


# =========================================================================
# Видалення акаунту (GDPR "право на забуття")
# =========================================================================
# Магазин фізично НЕ видаляється з БД - фінансові записи (замовлення)
# мають зберігатись знеособленими для податкової звітності (GDPR ст.17.3
# прямо дозволяє цей виняток). Знеособлюємо персональні дані клієнтів і
# власника, скасовуємо підписку, звільняємо slug/домен, ховаємо магазин
# від резолюції (is_deleted) - фактично це остаточне й незворотне
# відключення магазину від платформи.

def _delete_store_account(store):
    from models.shipping import CarrierAccount
    from models.order import Order
    from models.company import Company
    from models.user import User
    from models.store import StoreSubscriptionStatus

    if store.stripe_subscription_id and STRIPE_AVAILABLE and current_app.config["STRIPE_SECRET_KEY"]:
        try:
            stripe.Subscription.delete(store.stripe_subscription_id)
        except stripe.error.StripeError as e:
            current_app.logger.warning(f"Не вдалося скасувати Stripe-підписку магазину #{store.id}: {e}")

    if store.custom_domain:
        _remove_custom_domain_router(store.id)

    # Знеособлюємо замовлення - суми/статуси/номери лишаються (податковий облік).
    Order.query.filter_by(store_id=store.id).update({
        Order.customer_name: None,
        Order.customer_email: None,
        Order.customer_phone: None,
        Order.shipping_address: None,
        Order.shipping_city: None,
        Order.shipping_postal_code: None,
    }, synchronize_session=False)

    # Знеособлюємо контактну особу B2B-партнерів - юрдані (VAT, назва) лишаються.
    Company.query.filter_by(store_id=store.id).update({
        Company.contact_person: None,
        Company.contact_email: None,
        Company.contact_phone: None,
        Company.address: None,
        Company.website: None,
        Company.domain: None,
        Company.whois_data: None,
    }, synchronize_session=False)

    # Облікові дані перевізників (API-ключі) - видаляємо повністю, це секрети.
    CarrierAccount.query.filter_by(store_id=store.id).delete(synchronize_session=False)

    # Знеособлюємо усіх користувачів магазину (власник + клієнти/менеджери).
    user_ids = {store.owner_user_id}
    user_ids.update(
        uid for (uid,) in db.session.query(User.id).filter_by(store_id=store.id).all()
    )
    for user in User.query.filter(User.id.in_(user_ids)).all():
        user.email = f"deleted-user-{user.id}@deleted.local"
        user.set_password(uuid.uuid4().hex)
        user.first_name = None
        user.last_name = None
        user.phone = None

    store.is_deleted = True
    store.deleted_at = datetime.utcnow()
    store.is_active = False
    store.name = f"Видалений магазин #{store.id}"
    store.slug = f"deleted-{store.id}-{uuid.uuid4().hex[:8]}"
    store.custom_domain = None
    store.custom_domain_verified = False
    store.custom_domain_verified_at = None
    store.stripe_customer_id = None
    store.stripe_subscription_id = None
    store.stripe_connect_account_id = None
    store.stripe_connect_charges_enabled = False
    store.subscription_status = StoreSubscriptionStatus.CANCELED

    db.session.commit()


@settings_bp.route("/admin/settings/account", methods=["GET", "POST"])
@admin_required
def admin_delete_account():
    """Самостійне видалення акаунту-магазину власником (GDPR)."""
    store = g.store
    if current_user.id != store.owner_user_id:
        abort(403)

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm") == "on"
        if not confirm:
            flash(_("Підтвердіть, що розумієте наслідки видалення."), "danger")
            return redirect(url_for(".admin_delete_account"))
        if not current_user.check_password(password):
            flash(_("Невірний пароль."), "danger")
            return redirect(url_for(".admin_delete_account"))

        _delete_store_account(store)

        flask_logout_user()
        flash(_("Ваш акаунт і магазин видалено. Дякуємо, що були з нами."), "info")

        # Перенаправляємо на корневий домен без піддомену, щоб уникнути 404
        # (поточний піддомен більше не дійсний, оскільки магазин видалено)
        if BASE_DOMAIN:
            return redirect(f"https://{BASE_DOMAIN}/")
        return redirect(url_for("index"))

    return render_template("admin/delete_account.html", store=store)


# =========================================================================
# Налаштування доставки (DHL/UPS) + самовивіз
# =========================================================================

@settings_bp.route("/admin/settings/shipping", methods=["GET", "POST"])
@admin_required
def admin_shipping_settings():
    """Список налаштованих служб доставки магазину + самовивіз."""
    from models.shipping import CarrierAccount, Carrier
    settings = SiteSettings.get_or_create(g.store.id)

    if request.method == "POST":
        settings.pickup_enabled = request.form.get("pickup_enabled") == "on"
        settings.pickup_address = request.form.get("pickup_address", "").strip() or None
        settings.pickup_instructions = request.form.get("pickup_instructions", "").strip() or None
        db.session.commit()
        flash(_("Налаштування самовивозу збережено."), "success")
        return redirect(url_for(".admin_shipping_settings"))

    accounts = CarrierAccount.query.filter_by(store_id=g.store.id).all()
    configured_carriers = {a.carrier for a in accounts}
    available_carriers = [c for c in Carrier.CHOICES if c not in configured_carriers]
    return render_template(
        "admin/shipping_settings.html",
        settings=settings,
        accounts=accounts,
        available_carriers=available_carriers,
        carrier_labels=Carrier.LABELS,
    )


@settings_bp.route("/admin/settings/shipping/new", methods=["GET", "POST"])
@admin_required
def admin_shipping_account_new():
    """Додати обліковий запис перевізника (DHL/UPS)."""
    from models.shipping import CarrierAccount, Carrier

    carrier = request.args.get("carrier") or request.form.get("carrier", "")
    if carrier not in Carrier.CHOICES:
        flash(_("Невідома служба доставки."), "danger")
        return redirect(url_for(".admin_shipping_settings"))

    if CarrierAccount.query.filter_by(store_id=g.store.id, carrier=carrier).first():
        flash(_("%(carrier)s вже налаштовано для цього магазину.") % {"carrier": Carrier.LABELS.get(carrier, carrier)}, "warning")
        return redirect(url_for(".admin_shipping_settings"))

    if request.method == "POST":
        is_sandbox = request.form.get("is_sandbox") == "on"
        if carrier == Carrier.DHL:
            credentials = {
                "api_key": request.form.get("api_key", "").strip(),
                "api_secret": request.form.get("api_secret", "").strip(),
                "account_number": request.form.get("account_number", "").strip(),
            }
        else:  # ups
            credentials = {
                "client_id": request.form.get("client_id", "").strip(),
                "client_secret": request.form.get("client_secret", "").strip(),
                "account_number": request.form.get("account_number", "").strip(),
            }

        account = CarrierAccount(
            store_id=g.store.id,
            carrier=carrier,
            is_enabled=True,
            is_sandbox=is_sandbox,
            credentials=credentials,
            origin_name=request.form.get("origin_name", "").strip() or None,
            origin_phone=request.form.get("origin_phone", "").strip() or None,
            origin_street=request.form.get("origin_street", "").strip() or None,
            origin_city=request.form.get("origin_city", "").strip() or None,
            origin_postal_code=request.form.get("origin_postal_code", "").strip() or None,
            origin_country_code=(request.form.get("origin_country_code", "").strip() or None),
        )
        db.session.add(account)
        db.session.commit()
        flash(_("%(carrier)s налаштовано.") % {"carrier": account.carrier_label}, "success")
        return redirect(url_for(".admin_shipping_settings"))

    return render_template("admin/shipping_account_form.html", carrier=carrier, carrier_label=Carrier.LABELS.get(carrier, carrier), account=None)


@settings_bp.route("/admin/settings/shipping/<int:id>/edit", methods=["GET", "POST"])
@admin_required
def admin_shipping_account_edit(id):
    """Редагувати обліковий запис перевізника."""
    from models.shipping import CarrierAccount, Carrier
    account = CarrierAccount.query.filter_by(id=id, store_id=g.store.id).first_or_404()

    if request.method == "POST":
        account.is_enabled = request.form.get("is_enabled") == "on"
        account.is_sandbox = request.form.get("is_sandbox") == "on"
        if account.carrier == Carrier.DHL:
            account.credentials = {
                "api_key": request.form.get("api_key", "").strip(),
                "api_secret": request.form.get("api_secret", "").strip(),
                "account_number": request.form.get("account_number", "").strip(),
            }
        else:
            account.credentials = {
                "client_id": request.form.get("client_id", "").strip(),
                "client_secret": request.form.get("client_secret", "").strip(),
                "account_number": request.form.get("account_number", "").strip(),
            }
        account.origin_name = request.form.get("origin_name", "").strip() or None
        account.origin_phone = request.form.get("origin_phone", "").strip() or None
        account.origin_street = request.form.get("origin_street", "").strip() or None
        account.origin_city = request.form.get("origin_city", "").strip() or None
        account.origin_postal_code = request.form.get("origin_postal_code", "").strip() or None
        account.origin_country_code = request.form.get("origin_country_code", "").strip() or None
        db.session.commit()
        flash(_("%(carrier)s оновлено.") % {"carrier": account.carrier_label}, "success")
        return redirect(url_for(".admin_shipping_settings"))

    return render_template("admin/shipping_account_form.html", carrier=account.carrier, carrier_label=account.carrier_label, account=account)


@settings_bp.route("/admin/settings/shipping/<int:id>/delete", methods=["POST"])
@admin_required
def admin_shipping_account_delete(id):
    """Видалити обліковий запис перевізника."""
    from models.shipping import CarrierAccount
    account = CarrierAccount.query.filter_by(id=id, store_id=g.store.id).first_or_404()
    db.session.delete(account)
    db.session.commit()
    flash(_("Обліковий запис видалено."), "info")
    return redirect(url_for(".admin_shipping_settings"))
