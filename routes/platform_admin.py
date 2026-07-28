"""
Панель оператора SaaS-платформи: єдиний погляд на всі магазини (tenants),
їх підписки та користувачів - на відміну від /admin/*, який завжди
скоупований по g.store (конкретному магазину).
"""
from functools import wraps

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from extensions import db
from models.store import Store, StoreSubscriptionStatus
from models.user import User

platform_admin_bp = Blueprint("platform_admin", __name__, url_prefix="/platform-admin")

# Орієнтовна щомісячна ціна плану (EUR) - ті самі цифри, що на лендингу /
# в /signup. Використовується лише для оцінки MRR на дашборді, не для
# реальних розрахунків з Stripe (там точні суми).
PLAN_PRICES_EUR = {"starter": 19, "pro": 49, "business": 99}


def platform_owner_required(fn):
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.is_platform_owner:
            flash("Доступ лише для оператора платформи.", "danger")
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
        f"Магазин «{store.name}» {'активовано' if store.is_active else 'заблоковано'}.",
        "success",
    )
    return redirect(url_for("platform_admin.dashboard"))
