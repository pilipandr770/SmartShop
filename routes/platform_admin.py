"""
Панель оператора SaaS-платформи: єдиний погляд на всі магазини (tenants),
їх підписки та користувачів - на відміну від /admin/*, який завжди
скоупований по g.store (конкретному магазину).
"""
import os
from functools import wraps

from flask import Blueprint, render_template, redirect, url_for, flash, request, session, current_app
from flask_babel import gettext as _
from flask_login import login_required, current_user, login_user

from extensions import db
from models.store import Store, StoreSubscriptionStatus
from models.user import User

try:
    import stripe
    STRIPE_AVAILABLE = True
except ImportError:
    STRIPE_AVAILABLE = False

platform_admin_bp = Blueprint("platform_admin", __name__, url_prefix="/platform-admin")


def _platform_admin_url(path=""):
    """Посилання на голий BASE_DOMAIN (де живе /platform-admin), незалежно
    від того, на піддомені якого магазину зараз виконується запит - потрібно
    для повернення з імперсонації власника назад на панель платформи."""
    base_domain = os.environ.get("BASE_DOMAIN", "").strip().strip(".")
    if not base_domain:
        return url_for("platform_admin.dashboard")
    return f"https://{base_domain}/platform-admin{path}"

# Орієнтовна щомісячна ціна плану (EUR) - ті самі цифри, що на лендингу /
# в /signup. Використовується лише для оцінки MRR на дашборді, не для
# реальних розрахунків з Stripe (там точні суми).
PLAN_PRICES_EUR = {"starter": 19, "pro": 49, "business": 99}


def platform_owner_required(fn):
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.is_platform_owner:
            flash(_("Доступ лише для оператора платформи."), "danger")
            return redirect(url_for("index"))
        return fn(*args, **kwargs)
    return wrapper


@platform_admin_bp.route("")
@platform_owner_required
def dashboard():
    """Огляд усіх магазинів платформи."""
    stores = Store.query.order_by(Store.created_at.desc()).all()

    total_users = User.query.count()
    active_count = sum(1 for s in stores if s.subscription_status == StoreSubscriptionStatus.ACTIVE)
    trialing_count = sum(1 for s in stores if s.subscription_status == StoreSubscriptionStatus.TRIALING)
    past_due_count = sum(1 for s in stores if s.subscription_status == StoreSubscriptionStatus.PAST_DUE)
    canceled_count = sum(1 for s in stores if s.subscription_status == StoreSubscriptionStatus.CANCELED)
    mrr_estimate = sum(
        PLAN_PRICES_EUR.get(s.plan, 0)
        for s in stores
        if s.subscription_status == StoreSubscriptionStatus.ACTIVE
    )

    return render_template(
        "platform_admin/dashboard.html",
        stores=stores,
        total_users=total_users,
        active_count=active_count,
        trialing_count=trialing_count,
        past_due_count=past_due_count,
        canceled_count=canceled_count,
        mrr_estimate=mrr_estimate,
    )


@platform_admin_bp.route("/store/<int:store_id>/toggle-active", methods=["POST"])
@platform_owner_required
def toggle_store_active(store_id):
    """Ручне блокування/розблокування магазину оператором платформи."""
    store = Store.query.get_or_404(store_id)
    store.is_active = not store.is_active
    db.session.commit()
    flash(
        (_("Магазин «%(name)s» активовано.") if store.is_active
         else _("Магазин «%(name)s» заблоковано.")) % {"name": store.name},
        "success",
    )
    return redirect(url_for("platform_admin.dashboard"))


@platform_admin_bp.route("/users")
@platform_owner_required
def users():
    """Список усіх користувачів платформи (усі магазини і ролі)."""
    role_filter = request.args.get("role", "").strip()
    query = User.query
    if role_filter:
        query = query.filter_by(role=role_filter)
    all_users = query.order_by(User.created_at.desc()).all()

    # Мапа user_id -> Store, яким він володіє (для власників магазинів)
    owned_by_user = {s.owner_user_id: s for s in Store.query.all()}
    # Мапа store_id -> Store (для покупців/менеджерів, прив'язаних через store_id)
    stores_by_id = {s.id: s for s in Store.query.all()}

    return render_template(
        "platform_admin/users.html",
        users=all_users,
        owned_by_user=owned_by_user,
        stores_by_id=stores_by_id,
        role_filter=role_filter,
    )


@platform_admin_bp.route("/payments")
@platform_owner_required
def payments():
    """Реальна історія оплат підписок магазинів платформі (з Stripe, не оцінка)."""
    invoices = []
    error = None

    if not STRIPE_AVAILABLE or not current_app.config.get("STRIPE_SECRET_KEY"):
        error = _("Stripe не налаштовано на платформі.")
    else:
        stores_by_customer = {
            s.stripe_customer_id: s
            for s in Store.query.filter(Store.stripe_customer_id.isnot(None)).all()
        }
        for customer_id, store in stores_by_customer.items():
            try:
                result = stripe.Invoice.list(customer=customer_id, limit=10)
                for inv in result.get("data", []):
                    invoices.append({
                        "store": store,
                        "amount": (inv.get("amount_paid") or inv.get("amount_due") or 0) / 100,
                        "currency": (inv.get("currency") or "eur").upper(),
                        "status": inv.get("status"),
                        "created": inv.get("created"),
                        "hosted_invoice_url": inv.get("hosted_invoice_url"),
                        "number": inv.get("number"),
                    })
            except Exception as e:
                current_app.logger.error(f"Platform payments: failed to fetch invoices for store {store.id}: {e}")

        invoices.sort(key=lambda i: i["created"] or 0, reverse=True)

    total_paid = sum(i["amount"] for i in invoices if i["status"] == "paid")

    return render_template(
        "platform_admin/payments.html",
        invoices=invoices,
        total_paid=total_paid,
        error=error,
    )


@platform_admin_bp.route("/store/<int:store_id>/impersonate", methods=["POST"])
@platform_owner_required
def impersonate(store_id):
    """Тимчасово увійти як власник магазину, щоб допомогти йому в адмінці
    (напр. налаштувати щось на прохання клієнта) - без пароля, без TeamViewer.
    Оригінальний акаунт оператора платформи зберігається в сесії і
    відновлюється через stop_impersonating()."""
    store = Store.query.get_or_404(store_id)
    owner = store.owner
    if not owner:
        flash(_("У магазину немає власника - неможливо увійти."), "danger")
        return redirect(url_for("platform_admin.dashboard"))

    current_app.logger.info(
        f"Platform owner {current_user.email} (id={current_user.id}) impersonating "
        f"store owner {owner.email} (id={owner.id}) of store '{store.slug}'"
    )
    session["impersonator_id"] = current_user.id
    session["impersonating_store_name"] = store.name
    login_user(owner)
    flash(_("Ви увійшли як власник магазину «%(name)s».") % {"name": store.name}, "info")

    base_domain = os.environ.get("BASE_DOMAIN", "").strip().strip(".")
    if base_domain:
        return redirect(f"https://{store.slug}.{base_domain}/admin/")
    return redirect(url_for("admin_dashboard"))


@platform_admin_bp.route("/stop-impersonating")
@login_required
def stop_impersonating():
    """Повернутися до власного акаунту оператора платформи після імперсонації.
    Доступний з будь-якого піддомену (без subdomain-обмеження на blueprint),
    тому власник магазину не застрягає без можливості вийти."""
    impersonator_id = session.pop("impersonator_id", None)
    session.pop("impersonating_store_name", None)
    if not impersonator_id:
        flash(_("Ви не в режимі імперсонації."), "warning")
        return redirect(url_for("index"))

    original = User.query.get(impersonator_id)
    if not original:
        flash(_("Не вдалося відновити оригінальний акаунт."), "danger")
        return redirect(url_for("index"))

    login_user(original)
    flash(_("Ви повернулися до панелі платформи."), "success")
    return redirect(_platform_admin_url())
