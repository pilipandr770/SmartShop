"""
Категорії (швидке створення зі списку + повний CRUD) і товари. Обидва
розділи однаково залежать одне від одного (товар посилається на
категорію, видалення категорії обнуляє category_id товарів), тому
об'єднані в один blueprint.

Винесено з app.py ("АДМІНКА: КАТЕГОРІЇ", "АДМІНКА: ТОВАРИ", "АДМІНКА:
КАТЕГОРІЇ (повний CRUD)") як частина Phase 2 плану (SWOT 2026-08-08).
"""
from flask import Blueprint, g, redirect, render_template, request, url_for, flash
from flask_babel import gettext as _

from extensions import db
from models.settings import SiteSettings
from models.product import Product, Category
from services.admin_auth import admin_required
from services.image_storage import delete_old_image

products_bp = Blueprint("products", __name__)


@products_bp.route("/admin/categories", methods=["GET", "POST"])
@admin_required
def admin_categories():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        slug = request.form.get("slug", "").strip()
        description = request.form.get("description", "").strip()

        # Multilingual fields
        name_en = request.form.get("name_en", "").strip()
        name_de = request.form.get("name_de", "").strip()
        description_en = request.form.get("description_en", "").strip()
        description_de = request.form.get("description_de", "").strip()

        if not name or not slug:
            flash(_("Назва і slug категорії обовʼязкові."), "danger")
        else:
            exists = Category.query.filter_by(slug=slug, store_id=g.store.id).first()
            if exists:
                flash(_("Категорія з таким slug уже існує."), "warning")
            else:
                category = Category(
                    store_id=g.store.id,
                    name=name,
                    slug=slug,
                    description=description or None,
                    name_en=name_en or None,
                    name_de=name_de or None,
                    description_en=description_en or None,
                    description_de=description_de or None,
                )
                db.session.add(category)
                db.session.commit()
                flash(_("Категорія створена."), "success")
        return redirect(url_for(".admin_categories"))

    categories = Category.query.filter_by(store_id=g.store.id).order_by(Category.name.asc()).all()
    return render_template("admin/categories.html", categories=categories)


@products_bp.route("/admin/categories/<int:category_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_categories_edit(category_id):
    """Редагування категорії."""
    category = Category.query.filter_by(id=category_id, store_id=g.store.id).first_or_404()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        slug = request.form.get("slug", "").strip()
        description = request.form.get("description", "").strip()

        if not name or not slug:
            flash(_("Назва і slug категорії обовʼязкові."), "danger")
        else:
            exists = Category.query.filter(
                Category.slug == slug,
                Category.store_id == g.store.id,
                Category.id != category_id
            ).first()
            if exists:
                flash(_("Категорія з таким slug уже існує."), "warning")
            else:
                category.name = name
                category.slug = slug
                category.description = description or None
                db.session.commit()
                flash(_("Категорія оновлена."), "success")
                return redirect(url_for(".admin_categories"))

    return render_template("admin/category_edit.html", category=category)


@products_bp.route("/admin/categories/<int:category_id>/delete", methods=["POST"])
@admin_required
def admin_categories_delete(category_id):
    """Видалення категорії."""
    category = Category.query.filter_by(id=category_id, store_id=g.store.id).first_or_404()

    if category.image_url:
        delete_old_image(category.image_url)

    # Товари в цій категорії стануть без категорії
    Product.query.filter_by(category_id=category_id, store_id=g.store.id).update({"category_id": None})
    db.session.delete(category)
    db.session.commit()
    flash(_("Категорія видалена. Товари залишились без категорії."), "info")
    return redirect(url_for(".admin_categories"))


@products_bp.route("/admin/products")
@admin_required
def admin_products():
    products = (
        Product.query.filter_by(store_id=g.store.id).order_by(Product.created_at.desc())
        .all()
    )
    categories = Category.query.filter_by(store_id=g.store.id).order_by(Category.name.asc()).all()
    settings = SiteSettings.get_or_create(g.store.id)
    return render_template(
        "admin/products.html", products=products, categories=categories, settings=settings
    )


@products_bp.route("/admin/products/new", methods=["POST"])
@admin_required
def admin_products_new():
    name = request.form.get("name", "").strip()
    price = request.form.get("price", "0").replace(",", ".").strip()
    old_price = request.form.get("old_price", "").replace(",", ".").strip()
    category_id = request.form.get("category_id") or None
    description = request.form.get("description", "").strip()
    image_url = request.form.get("image_url", "").strip()
    stock = request.form.get("stock", "0").strip()
    is_active = request.form.get("is_active") == "on"

    # Мультимовні поля
    name_en = request.form.get("name_en", "").strip() or None
    name_de = request.form.get("name_de", "").strip() or None
    description_en = request.form.get("description_en", "").strip() or None
    description_de = request.form.get("description_de", "").strip() or None

    try:
        price_value = float(price)
    except ValueError:
        price_value = 0.0

    try:
        old_price_value = float(old_price) if old_price else None
    except ValueError:
        old_price_value = None

    try:
        stock_value = int(stock)
    except ValueError:
        stock_value = 0

    settings = SiteSettings.get_or_create(g.store.id)
    # category_id має належати поточному магазину - інакше ігноруємо
    safe_category_id = None
    if category_id:
        cat = Category.query.filter_by(id=int(category_id), store_id=g.store.id).first()
        safe_category_id = cat.id if cat else None
    product = Product(
        store_id=g.store.id,
        name=name,
        price=price_value,
        old_price=old_price_value,
        currency=settings.default_currency or "EUR",
        category_id=safe_category_id,
        short_description=description or None,
        image_url=image_url or None,
        stock=stock_value,
        is_active=is_active,
        # Мультимовність
        name_en=name_en,
        name_de=name_de,
        short_description_en=description_en,
        short_description_de=description_de,
    )
    db.session.add(product)
    db.session.commit()
    flash(_("Товар створено."), "success")
    return redirect(url_for(".admin_products"))


@products_bp.route("/admin/products/<int:product_id>/toggle", methods=["POST"])
@admin_required
def admin_products_toggle(product_id):
    product = Product.query.filter_by(id=product_id, store_id=g.store.id).first_or_404()
    product.is_active = not product.is_active
    db.session.commit()
    flash(_("Статус товару оновлено."), "info")
    return redirect(url_for(".admin_products"))


@products_bp.route("/admin/products/<int:product_id>/delete", methods=["POST"])
@admin_required
def admin_products_delete(product_id):
    product = Product.query.filter_by(id=product_id, store_id=g.store.id).first_or_404()

    if product.image_url:
        delete_old_image(product.image_url)

    db.session.delete(product)
    db.session.commit()
    flash(_("Товар видалено."), "info")
    return redirect(url_for(".admin_products"))


@products_bp.route("/admin/products/<int:product_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_products_edit(product_id):
    """Редагування товару."""
    product = Product.query.filter_by(id=product_id, store_id=g.store.id).first_or_404()
    categories = Category.query.filter_by(store_id=g.store.id).order_by(Category.name.asc()).all()

    if request.method == "POST":
        product.name = request.form.get("name", "").strip()
        price = request.form.get("price", "0").replace(",", ".").strip()
        old_price = request.form.get("old_price", "").replace(",", ".").strip()
        stock = request.form.get("stock", "0").strip()

        try:
            product.price = float(price)
        except ValueError:
            product.price = 0.0

        try:
            product.old_price = float(old_price) if old_price else None
        except ValueError:
            product.old_price = None

        try:
            product.stock = int(stock)
        except ValueError:
            product.stock = 0

        category_id = request.form.get("category_id")
        safe_category_id = None
        if category_id:
            cat = Category.query.filter_by(id=int(category_id), store_id=g.store.id).first()
            safe_category_id = cat.id if cat else None
        product.category_id = safe_category_id
        product.short_description = request.form.get("short_description", "").strip() or None
        product.long_description = request.form.get("long_description", "").strip() or None

        # Оновлюємо image_url та видаляємо старе зображення
        new_image_url = request.form.get("image_url", "").strip() or None
        if new_image_url and new_image_url != product.image_url:
            delete_old_image(product.image_url)
        product.image_url = new_image_url

        product.sku = request.form.get("sku", "").strip() or None
        product.is_active = request.form.get("is_active") == "on"

        weight_kg = request.form.get("weight_kg", "").strip()
        try:
            product.weight_kg = float(weight_kg) if weight_kg else None
        except ValueError:
            product.weight_kg = None

        db.session.commit()
        flash(_("Товар оновлено."), "success")
        return redirect(url_for(".admin_products"))

    return render_template(
        "admin/product_edit.html",
        product=product,
        categories=categories,
        settings=SiteSettings.get_or_create(g.store.id),
    )
