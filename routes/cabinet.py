"""
Маршрути особистого кабінету (B2C та B2B)
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from extensions import db
from models.order import Order, OrderStatus

cabinet_bp = Blueprint("cabinet", __name__, url_prefix="/cabinet")


@cabinet_bp.route("/")
@login_required
def dashboard():
    """Головна сторінка кабінету."""
    if current_user.is_b2b:
        return redirect(url_for("cabinet.b2b_dashboard"))
    return redirect(url_for("cabinet.b2c_dashboard"))


@cabinet_bp.route("/b2c")
@login_required
def b2c_dashboard():
    """Dashboard для B2C клієнта."""
    # Останні замовлення
    recent_orders = Order.query.filter_by(user_id=current_user.id)\
        .order_by(Order.created_at.desc())\
        .limit(5)\
        .all()
    
    # Статистика
    total_orders = Order.query.filter_by(user_id=current_user.id).count()
    
    return render_template(
        "cabinet/b2c/dashboard.html",
        recent_orders=recent_orders,
        total_orders=total_orders,
    )


@cabinet_bp.route("/b2b")
@login_required
def b2b_dashboard():
    """Dashboard для B2B партнера."""
    if not current_user.is_b2b:
        flash("Доступ лише для B2B партнерів.", "warning")
        return redirect(url_for("cabinet.b2c_dashboard"))
    
    company = current_user.company
    
    # Перевірка статусу компанії
    if not company.is_verified:
        return render_template(
            "cabinet/b2b/pending.html",
            company=company,
        )
    
    # Останні замовлення компанії
    recent_orders = Order.query.filter_by(company_id=company.id)\
        .order_by(Order.created_at.desc())\
        .limit(10)\
        .all()
    
    # Статистика
    total_orders = Order.query.filter_by(company_id=company.id).count()
    paid_orders = Order.query.filter_by(company_id=company.id, status=OrderStatus.PAID.value).count()
    total_spent = db.session.query(db.func.coalesce(db.func.sum(Order.amount), 0.0))\
        .filter(Order.company_id == company.id, Order.status == OrderStatus.PAID.value)\
        .scalar()
    
    return render_template(
        "cabinet/b2b/dashboard.html",
        company=company,
        recent_orders=recent_orders,
        total_orders=total_orders,
        paid_orders=paid_orders,
        total_spent=total_spent,
    )


@cabinet_bp.route("/orders")
@login_required
def orders():
    """Список замовлень."""
    page = request.args.get("page", 1, type=int)
    per_page = 20
    
    if current_user.is_b2b and current_user.company_id:
        query = Order.query.filter_by(company_id=current_user.company_id)
    else:
        query = Order.query.filter_by(user_id=current_user.id)
    
    pagination = query.order_by(Order.created_at.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)
    
    orders = pagination.items
    
    template = "cabinet/b2b/orders.html" if current_user.is_b2b else "cabinet/b2c/orders.html"
    return render_template(template, orders=orders, pagination=pagination)


@cabinet_bp.route("/orders/<int:order_id>")
@login_required
def order_detail(order_id):
    """Деталі замовлення."""
    if current_user.is_b2b and current_user.company_id:
        order = Order.query.filter_by(id=order_id, company_id=current_user.company_id).first_or_404()
    else:
        order = Order.query.filter_by(id=order_id, user_id=current_user.id).first_or_404()
    
    template = "cabinet/b2b/order_detail.html" if current_user.is_b2b else "cabinet/b2c/order_detail.html"
    return render_template(template, order=order)


@cabinet_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """Профіль користувача."""
    if request.method == "POST":
        current_user.first_name = request.form.get("first_name", "").strip() or None
        current_user.last_name = request.form.get("last_name", "").strip() or None
        current_user.phone = request.form.get("phone", "").strip() or None
        
        db.session.commit()
        flash("Профіль оновлено.", "success")
        return redirect(url_for("cabinet.profile"))
    
    template = "cabinet/b2b/profile.html" if current_user.is_b2b else "cabinet/b2c/profile.html"
    return render_template(template)


@cabinet_bp.route("/company", methods=["GET", "POST"])
@login_required
def company():
    """Налаштування компанії (тільки для B2B)."""
    if not current_user.is_b2b:
        flash("Доступ лише для B2B партнерів.", "warning")
        return redirect(url_for("cabinet.dashboard"))
    
    company = current_user.company
    
    if request.method == "POST":
        company.contact_person = request.form.get("contact_person", "").strip() or None
        company.contact_phone = request.form.get("contact_phone", "").strip() or None
        company.address = request.form.get("address", "").strip() or None
        company.city = request.form.get("city", "").strip() or None
        company.postal_code = request.form.get("postal_code", "").strip() or None
        
        db.session.commit()
        flash("Дані компанії оновлено.", "success")
        return redirect(url_for("cabinet.company"))
    
    return render_template("cabinet/b2b/company.html", company=company)


@cabinet_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    """Зміна пароля."""
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        
        if not current_user.check_password(current_password):
            flash("Невірний поточний пароль.", "danger")
        elif len(new_password) < 6:
            flash("Новий пароль має бути не менше 6 символів.", "danger")
        elif new_password != confirm_password:
            flash("Паролі не співпадають.", "danger")
        else:
            current_user.set_password(new_password)
            db.session.commit()
            flash("Пароль успішно змінено.", "success")
            return redirect(url_for("cabinet.profile"))
    
    return render_template("cabinet/change_password.html")
