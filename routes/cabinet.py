"""
Особистий кабінет покупця: B2C дашборд, B2B дашборд + замовлення +
профіль компанії, зміна пароля (спільна для всіх ролей).

До 2026-08-09 існувало ДВІ паралельні реалізації кабінету: ця блюпринт-
версія (з маршрутами dashboard/b2c_dashboard/orders/order_detail/profile,
що фільтрували Order за user_id/company_id) і робоча версія прямо в
app.py (/cabinet, /cabinet/b2b, /cabinet/b2b/orders, /cabinet/b2b/company,
що фільтрує за customer_email). Друга була фактично МЕРТВИМ кодом:
жоден шаблон і жоден внутрішній redirect на неї не посилався (єдиний
живий маршрут цього blueprint був change_password), а там, де вона теж
була б технічно досяжна за прямим URL, вона була ще й ЗЛАМАНА - ніде в
коді Order.user_id/Order.company_id не встановлюються під час checkout(),
тож ці фільтри завжди повертали порожній результат; order_detail()/
profile()/orders() (гілка B2C) до того ж рендерили шаблони, яких взагалі
не існує (cabinet/b2c/orders.html, cabinet/b2c/order_detail.html,
cabinet/b2b/order_detail.html, cabinet/*/profile.html) - впали б з 500
одразу після того, як фільтр повернув би хоч щось.

Консолідовано в один blueprint 2026-08-09: перенесено робочу логіку з
app.py (яка й лишається єдиним джерелом правди - фільтрація за
customer_email, встановленим у checkout_success()/stripe_webhook()),
додано перевірку крос-тенантності (company.store_id != g.store.id) з
мертвої версії - це була єдина цінна відсутня деталь. Мертві маршрути
видалено, а не "полагоджені", бо на них ніщо не посилалось.

Той самий перенесений код (ще з app.py) мав власний, теж мертвий/нікому
не потрібний рядок `order.status_display = {...}.get(...)` - Order вже
має ідентичну by-design властивість status_display (models/order.py) без
setter'а, тож це падало з AttributeError щойно з'являвся хоч один реальний
запис в recent_orders/orders (раніше не спрацьовувало непомітно, бо
/cabinet ніколи не тестувався з користувачем, що реально мав замовлення).
Видалено - шаблони й так звертаються до order.status_display напряму.
"""
from flask import Blueprint, g, redirect, render_template, request, url_for, flash
from flask_babel import gettext as _
from flask_login import current_user, login_required

from extensions import db
from models.order import Order
from models.settings import SiteSettings

cabinet_bp = Blueprint("cabinet", __name__, url_prefix="/cabinet")


@cabinet_bp.route("")
@login_required
def user_cabinet():
    """Особистий кабінет B2C клієнта."""
    if current_user.is_b2b:
        return redirect(url_for(".b2b_dashboard"))

    settings = SiteSettings.get_or_create(g.store.id)

    # Статистика (тільки замовлення в межах поточного магазину)
    total_orders = Order.query.filter_by(customer_email=current_user.email, store_id=g.store.id).count()
    recent_orders = Order.query.filter_by(customer_email=current_user.email, store_id=g.store.id)\
        .order_by(Order.created_at.desc()).limit(5).all()

    return render_template(
        "cabinet/b2c/dashboard.html",
        settings=settings,
        total_orders=total_orders,
        recent_orders=recent_orders,
    )


@cabinet_bp.route("/b2b")
@login_required
def b2b_dashboard():
    """Dashboard B2B партнера."""
    if not current_user.is_b2b:
        return redirect(url_for(".user_cabinet"))

    company = current_user.company

    # Компанія зареєстрована як B2B-партнер конкретного магазину - на
    # іншому піддомені кабінет не показуємо (немає доступу до чужого
    # store; інакше можна було б побачити дані/знижку "не своєї" компанії).
    if company and company.store_id and company.store_id != g.store.id:
        flash(_("Цей кабінет недоступний на цьому магазині."), "warning")
        return redirect(url_for("index"))

    settings = SiteSettings.get_or_create(g.store.id)

    # Статистика (в межах поточного магазину)
    total_orders = Order.query.filter_by(customer_email=current_user.email, store_id=g.store.id).count()
    pending_orders = Order.query.filter_by(customer_email=current_user.email, status="pending", store_id=g.store.id).count()
    total_spent = db.session.query(db.func.coalesce(db.func.sum(Order.amount), 0.0))\
        .filter_by(customer_email=current_user.email, status="paid", store_id=g.store.id).scalar()

    discount = company.discount_percent if company else 0

    recent_orders = Order.query.filter_by(customer_email=current_user.email, store_id=g.store.id)\
        .order_by(Order.created_at.desc()).limit(5).all()

    return render_template(
        "cabinet/b2b/dashboard.html",
        settings=settings,
        total_orders=total_orders,
        pending_orders=pending_orders,
        total_spent=total_spent,
        discount=discount,
        recent_orders=recent_orders,
        recent_documents=[],  # TODO: Документи
        chart_labels=None,
        chart_data=None,
    )


@cabinet_bp.route("/b2b/orders")
@login_required
def b2b_orders():
    """Замовлення B2B партнера."""
    if not current_user.is_b2b:
        return redirect(url_for(".user_cabinet"))

    settings = SiteSettings.get_or_create(g.store.id)

    orders = Order.query.filter_by(customer_email=current_user.email, store_id=g.store.id)\
        .order_by(Order.created_at.desc()).all()

    return render_template(
        "cabinet/b2b/orders.html",
        settings=settings,
        orders=orders,
    )


@cabinet_bp.route("/b2b/company", methods=["GET", "POST"])
@login_required
def b2b_company():
    """Профіль компанії B2B партнера."""
    if not current_user.is_b2b:
        return redirect(url_for(".user_cabinet"))

    settings = SiteSettings.get_or_create(g.store.id)
    company = current_user.company

    if request.method == "POST" and company:
        company.name = request.form.get("name", company.name)
        company.address = request.form.get("address", company.address)
        company.city = request.form.get("city", company.city)
        company.postal_code = request.form.get("postal_code", company.postal_code)
        company.country = request.form.get("country", company.country)
        company.website = request.form.get("website", company.website)
        company.contact_person = request.form.get("contact_person", company.contact_person)
        company.contact_phone = request.form.get("phone", company.contact_phone)

        db.session.commit()
        flash(_("Дані компанії оновлено!"), "success")
        return redirect(url_for(".b2b_company"))

    return render_template(
        "cabinet/b2b/company.html",
        settings=settings,
        company=company,
    )


@cabinet_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    """Зміна пароля."""
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not current_user.check_password(current_password):
            flash(_("Невірний поточний пароль."), "danger")
        elif len(new_password) < 6:
            flash(_("Новий пароль має бути не менше 6 символів."), "danger")
        elif new_password != confirm_password:
            flash(_("Паролі не співпадають."), "danger")
        else:
            current_user.set_password(new_password)
            db.session.commit()
            flash(_("Пароль успішно змінено."), "success")
            if current_user.is_platform_owner:
                return redirect(url_for("platform_admin.dashboard"))
            if current_user.is_b2b:
                return redirect(url_for(".b2b_dashboard"))
            return redirect(url_for(".user_cabinet"))

    return render_template("cabinet/change_password.html")
