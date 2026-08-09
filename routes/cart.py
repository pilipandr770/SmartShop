"""
Кошик покупця (session-based, без БД) - перегляд, додавання, зміна
кількості, видалення, очищення.

Винесено з app.py ("ПУБЛІЧНІ: КОШИК") як частина Phase 2 плану
(SWOT 2026-08-08) - другий з трьох файлів останнього кластера.
"""
from flask import Blueprint, abort, g, redirect, render_template, request, url_for, flash
from flask_babel import gettext as _

from models.settings import SiteSettings
from models.product import Product
from services.cart import get_cart, save_cart

cart_bp = Blueprint("cart", __name__)


@cart_bp.route("/cart")
def cart_page():
    """Сторінка кошика."""
    settings = SiteSettings.get_or_create(g.store.id)
    cart = get_cart()
    items = []
    total = 0.0

    for product_id_str, qty in cart.items():
        product = Product.query.filter_by(id=int(product_id_str), store_id=g.store.id).first()
        if product and product.is_active:
            item_total = product.price * qty
            total += item_total
            items.append({
                "product": product,
                "quantity": qty,
                "item_total": item_total,
            })

    from services.shipping.registry import get_enabled_providers
    has_shipping_options = bool(get_enabled_providers(g.store.id)) or settings.pickup_enabled

    return render_template(
        "cart.html",
        settings=settings,
        items=items,
        total=total,
        has_shipping_carriers=has_shipping_options,
    )


@cart_bp.route("/cart/add/<int:product_id>", methods=["POST"])
def cart_add(product_id):
    """Додати товар у кошик."""
    product = Product.query.filter_by(id=product_id, store_id=g.store.id).first_or_404()
    if not product.is_active:
        abort(404)

    cart = get_cart()
    product_id_str = str(product_id)
    quantity = request.form.get("quantity", 1, type=int)

    if quantity < 1:
        quantity = 1

    if product_id_str in cart:
        cart[product_id_str] += quantity
    else:
        cart[product_id_str] = quantity

    save_cart(cart)
    flash(_("«%(name)s» додано в кошик.") % {"name": product.name}, "success")

    # Повернутись на попередню сторінку або на сторінку товару
    next_url = request.form.get("next") or url_for("storefront.product_page", product_id=product_id)
    return redirect(next_url)


@cart_bp.route("/cart/update/<int:product_id>", methods=["POST"])
def cart_update(product_id):
    """Оновити кількість товару в кошику."""
    cart = get_cart()
    product_id_str = str(product_id)
    quantity = request.form.get("quantity", 1, type=int)

    if product_id_str in cart:
        if quantity > 0:
            cart[product_id_str] = quantity
        else:
            del cart[product_id_str]
        save_cart(cart)

    return redirect(url_for(".cart_page"))


@cart_bp.route("/cart/remove/<int:product_id>", methods=["POST"])
def cart_remove(product_id):
    """Видалити товар з кошика."""
    cart = get_cart()
    product_id_str = str(product_id)

    if product_id_str in cart:
        del cart[product_id_str]
        save_cart(cart)
        flash(_("Товар видалено з кошика."), "info")

    return redirect(url_for(".cart_page"))


@cart_bp.route("/cart/clear", methods=["POST"])
def cart_clear():
    """Очистити весь кошик."""
    save_cart({})
    flash(_("Кошик очищено."), "info")
    return redirect(url_for(".cart_page"))
