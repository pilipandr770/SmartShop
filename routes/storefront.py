"""
Публічні сторінки каталогу: список товарів, категорія, окремий товар.
Read-only - жодних сесій/платежів, тому окремо від кошика й checkout.

Винесено з app.py ("ПУБЛІЧНІ: МАГАЗИН") як частина Phase 2 плану
(SWOT 2026-08-08) - перший з трьох файлів останнього, найризикованішого
кластера (кошик/оплата - решта два).
"""
from flask import Blueprint, abort, g, render_template, request

from models.settings import SiteSettings
from models.product import Product, Category

storefront_bp = Blueprint("storefront", __name__)


@storefront_bp.route("/shop")
def shop():
    """Сторінка всіх товарів з пагінацією."""
    settings = SiteSettings.get_or_create(g.store.id)
    page = request.args.get("page", 1, type=int)
    per_page = 12

    products = (
        Product.query.filter_by(is_active=True, store_id=g.store.id)
        .order_by(Product.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )
    categories = Category.query.filter_by(store_id=g.store.id).order_by(Category.name.asc()).all()

    return render_template(
        "shop.html",
        settings=settings,
        products=products,
        categories=categories,
    )


@storefront_bp.route("/category/<slug>")
def category_page(slug):
    """Сторінка категорії з товарами."""
    settings = SiteSettings.get_or_create(g.store.id)
    category = Category.query.filter_by(slug=slug, store_id=g.store.id).first_or_404()
    page = request.args.get("page", 1, type=int)
    per_page = 12

    products = (
        Product.query.filter_by(is_active=True, category_id=category.id, store_id=g.store.id)
        .order_by(Product.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )
    categories = Category.query.filter_by(store_id=g.store.id).order_by(Category.name.asc()).all()

    return render_template(
        "category.html",
        settings=settings,
        category=category,
        products=products,
        categories=categories,
    )


@storefront_bp.route("/product/<int:product_id>")
def product_page(product_id):
    """Сторінка окремого товару."""
    settings = SiteSettings.get_or_create(g.store.id)
    product = Product.query.filter_by(id=product_id, store_id=g.store.id).first_or_404()

    if not product.is_active:
        abort(404)

    # Схожі товари з тієї ж категорії
    related = []
    if product.category_id:
        related = (
            Product.query.filter(
                Product.is_active == True,
                Product.category_id == product.category_id,
                Product.id != product.id,
                Product.store_id == g.store.id,
            )
            .limit(4)
            .all()
        )

    return render_template(
        "product.html",
        settings=settings,
        product=product,
        related=related,
    )
