"""
Дашборд адмінки + редагування блоків головної сторінки (hero/about/blog
picks + соцмережі + інструкції для ШІ-асистента) + сумісні редіректи зі
старих /admin/login, /admin/logout на реальний Flask-Login вхід.

Винесено з app.py ("АДМІНКА: АВТОРИЗАЦІЯ" + "АДМІНКА: ДАШБОРД" +
"АДМІНКА: НАЛАШТУВАННЯ БЛОКІВ + СОЦМЕРЕЖІ + ШІ") як частина Phase 2 плану
(SWOT 2026-08-08).
"""
from flask import Blueprint, abort, g, redirect, render_template, request, url_for, flash
from flask_babel import gettext as _

from extensions import db
from models.settings import SiteSettings
from models.product import Product, Category
from models.order import Order
from models.homepage_block import HomepageBlock, LINK_TYPE_CHOICES
from services.admin_auth import admin_required, DEMO_MODE

content_bp = Blueprint("dashboard", __name__)


@content_bp.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    """
    Legacy URL, залишений для сумісності зі старими закладками/лінками.
    Реальний логін тепер один для всіх (customer/partner/store owner) -
    через Flask-Login у routes/auth.py, щоб адмінка могла бути прив'язана
    до конкретного current_user і, відповідно, до конкретного Store.
    """
    if DEMO_MODE:
        return redirect(url_for(".admin_dashboard"))
    return redirect(url_for("user_login", next=url_for(".admin_dashboard")))


@content_bp.route("/admin/logout")
def admin_logout():
    return redirect(url_for("user_logout"))


@content_bp.route("/admin/")
@admin_required
def admin_dashboard():
    settings = SiteSettings.get_or_create(g.store.id)
    product_count = Product.query.filter_by(store_id=g.store.id).count()
    category_count = Category.query.filter_by(store_id=g.store.id).count()
    order_count = Order.query.filter_by(store_id=g.store.id).count()

    total_revenue = (
        db.session.query(db.func.coalesce(db.func.sum(Order.amount), 0.0))
        .filter(Order.status == "paid", Order.store_id == g.store.id)
        .scalar()
    )

    last_orders = (
        Order.query.filter_by(store_id=g.store.id).order_by(Order.created_at.desc()).limit(5).all()
    )

    return render_template(
        "admin/dashboard.html",
        settings=settings,
        product_count=product_count,
        category_count=category_count,
        order_count=order_count,
        total_revenue=total_revenue,
        last_orders=last_orders,
    )


@content_bp.route("/admin/blocks", methods=["GET", "POST"])
@admin_required
def admin_blocks():
    settings = SiteSettings.get_or_create(g.store.id)

    if request.method == "POST":
        settings.hero_subtitle = request.form.get("hero_subtitle") or ""
        settings.about_title = request.form.get("about_title") or ""
        settings.about_text = request.form.get("about_text") or ""
        settings.blog_title = request.form.get("blog_title") or ""
        settings.blog_excerpt = request.form.get("blog_excerpt") or ""

        settings.social_telegram = request.form.get("social_telegram") or ""
        settings.social_whatsapp = request.form.get("social_whatsapp") or ""

        settings.ai_instructions = request.form.get("ai_instructions") or ""

        db.session.commit()
        flash(_("Налаштування головної сторінки збережені."), "success")
        return redirect(url_for(".admin_blocks"))

    homepage_blocks = HomepageBlock.get_all_for_store(g.store.id)
    return render_template(
        "admin/blocks.html",
        settings=settings,
        homepage_blocks=homepage_blocks,
        link_type_choices=LINK_TYPE_CHOICES,
    )


def _get_own_block_or_404(block_id):
    block = HomepageBlock.query.filter_by(id=block_id, store_id=g.store.id).first()
    if not block:
        abort(404)
    return block


@content_bp.route("/admin/blocks/new", methods=["POST"])
@admin_required
def admin_blocks_new():
    max_order = (
        db.session.query(db.func.coalesce(db.func.max(HomepageBlock.sort_order), -1))
        .filter(HomepageBlock.store_id == g.store.id)
        .scalar()
    )
    block = HomepageBlock(
        store_id=g.store.id,
        title=_("Новий блок"),
        subtitle="",
        link_type="custom",
        link_value="#",
        sort_order=max_order + 1,
        is_active=True,
    )
    db.session.add(block)
    db.session.commit()
    flash(_("Блок додано. Заповніть його нижче."), "success")
    return redirect(url_for(".admin_blocks"))


@content_bp.route("/admin/blocks/<int:block_id>", methods=["POST"])
@admin_required
def admin_blocks_save(block_id):
    block = _get_own_block_or_404(block_id)

    block.title = request.form.get("title", "").strip() or _("Без назви")
    block.subtitle = request.form.get("subtitle", "").strip()
    block.image_url = request.form.get("image_url", "").strip() or None

    link_type = request.form.get("link_type", "custom")
    block.link_type = link_type if link_type in LINK_TYPE_CHOICES else "custom"
    block.link_value = request.form.get("link_value", "").strip() or None

    block.is_active = request.form.get("is_active") == "on"

    db.session.commit()
    flash(_("Блок «%(title)s» збережено.") % {"title": block.title}, "success")
    return redirect(url_for(".admin_blocks"))


@content_bp.route("/admin/blocks/<int:block_id>/delete", methods=["POST"])
@admin_required
def admin_blocks_delete(block_id):
    block = _get_own_block_or_404(block_id)
    db.session.delete(block)
    db.session.commit()
    flash(_("Блок видалено."), "success")
    return redirect(url_for(".admin_blocks"))


@content_bp.route("/admin/blocks/<int:block_id>/move", methods=["POST"])
@admin_required
def admin_blocks_move(block_id):
    block = _get_own_block_or_404(block_id)
    direction = request.form.get("direction")

    siblings = (
        HomepageBlock.query.filter_by(store_id=g.store.id)
        .order_by(HomepageBlock.sort_order)
        .all()
    )
    index = next((i for i, b in enumerate(siblings) if b.id == block.id), None)
    if index is None:
        return redirect(url_for(".admin_blocks"))

    swap_index = index - 1 if direction == "up" else index + 1
    if 0 <= swap_index < len(siblings):
        other = siblings[swap_index]
        block.sort_order, other.sort_order = other.sort_order, block.sort_order
        db.session.commit()

    return redirect(url_for(".admin_blocks"))
