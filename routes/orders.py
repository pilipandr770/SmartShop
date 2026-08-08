"""
Статистика (загальні цифри по замовленнях) + список/деталі/зміна статусу
замовлень. Об'єднані в один blueprint - stats це, по суті, зведення тих
самих Order-даних, що й список замовлень.

Винесено з app.py ("АДМІНКА: СТАТИСТИКА" + "АДМІНКА: ЗАМОВЛЕННЯ") як
частина Phase 2 плану (SWOT 2026-08-08).
"""
from flask import Blueprint, current_app, g, redirect, render_template, request, url_for, flash
from flask_babel import gettext as _

from extensions import db
from models.order import Order, OrderItem
from services.admin_auth import admin_required

orders_bp = Blueprint("orders", __name__)


@orders_bp.route("/admin/stats")
@admin_required
def admin_stats():
    total_orders = Order.query.filter_by(store_id=g.store.id).count()
    paid_orders = Order.query.filter_by(status="paid", store_id=g.store.id).count()
    total_revenue = (
        db.session.query(db.func.coalesce(db.func.sum(Order.amount), 0.0))
        .filter(Order.status == "paid", Order.store_id == g.store.id)
        .scalar()
    )
    latest_orders = (
        Order.query.filter_by(store_id=g.store.id).order_by(Order.created_at.desc()).limit(20).all()
    )

    return render_template(
        "admin/stats.html",
        total_orders=total_orders,
        paid_orders=paid_orders,
        total_revenue=total_revenue,
        latest_orders=latest_orders,
    )


@orders_bp.route("/admin/orders")
@admin_required
def admin_orders():
    """Список усіх замовлень з фільтрацією та пагінацією."""
    page = request.args.get("page", 1, type=int)
    per_page = 20
    status_filter = request.args.get("status", "").strip()

    query = Order.query.filter_by(store_id=g.store.id).order_by(Order.created_at.desc())

    if status_filter:
        query = query.filter(Order.status == status_filter)

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    orders = pagination.items

    stats = {
        "total": Order.query.filter_by(store_id=g.store.id).count(),
        "paid": Order.query.filter_by(status="paid", store_id=g.store.id).count(),
        "pending": Order.query.filter_by(status="pending", store_id=g.store.id).count(),
        "revenue": db.session.query(db.func.coalesce(db.func.sum(Order.amount), 0.0))
            .filter(Order.status == "paid", Order.store_id == g.store.id).scalar(),
    }

    return render_template(
        "admin/orders.html",
        orders=orders,
        pagination=pagination,
        stats=stats,
    )


@orders_bp.route("/admin/orders/<int:order_id>")
@admin_required
def admin_order_detail(order_id):
    """Деталі замовлення."""
    order = Order.query.filter_by(id=order_id, store_id=g.store.id).first_or_404()
    return render_template("admin/order_detail.html", order=order)


@orders_bp.route("/admin/orders/<int:order_id>/status", methods=["POST"])
@admin_required
def admin_order_update_status(order_id):
    """Оновити статус замовлення."""
    order = Order.query.filter_by(id=order_id, store_id=g.store.id).first_or_404()
    new_status = request.form.get("status", "").strip()
    old_status = order.status

    valid_statuses = ["created", "pending", "paid", "shipped", "delivered", "cancelled"]
    if new_status in valid_statuses:
        order.status = new_status
        db.session.commit()

        # Відправити email про зміну статусу
        if order.customer_email and old_status != new_status:
            try:
                from services.email_service import send_order_status_update
                send_order_status_update(order.customer_email, order, old_status, new_status)
                current_app.logger.info(f'Order status email sent to {order.customer_email}')
            except Exception as e:
                current_app.logger.error(f'Failed to send order status email: {str(e)}')

        # Якщо статус змінився на "paid" - створюємо завдання для складу
        if new_status == "paid" and old_status != "paid":
            try:
                from models.warehouse import WarehouseTask
                existing_task = WarehouseTask.query.filter_by(order_id=order.id).first()
                if not existing_task:
                    task = WarehouseTask.create_from_order(
                        order_id=order.id,
                        priority=2 if getattr(order, 'is_b2b', False) else 3,
                        notes=getattr(order, 'notes', '') or '',
                    )
                    flash(_("📦 Завдання для складу #%(task_number)s створено!") % {"task_number": task.task_number}, "info")
            except Exception as e:
                print(f"Error creating warehouse task: {e}")

        flash(_("Статус змінено на «%(status)s».") % {"status": new_status}, "success")
    else:
        flash(_("Невірний статус."), "danger")

    return redirect(url_for(".admin_order_detail", order_id=order_id))


@orders_bp.route("/admin/orders/<int:order_id>/notes", methods=["POST"])
@admin_required
def admin_order_update_notes(order_id):
    """Оновити нотатки замовлення."""
    order = Order.query.filter_by(id=order_id, store_id=g.store.id).first_or_404()
    order.notes = request.form.get("notes", "").strip() or None
    db.session.commit()
    flash(_("Нотатки збережено."), "success")
    return redirect(url_for(".admin_order_detail", order_id=order_id))


@orders_bp.route("/admin/orders/<int:order_id>/delete", methods=["POST"])
@admin_required
def admin_order_delete(order_id):
    """Видалити замовлення."""
    order = Order.query.filter_by(id=order_id, store_id=g.store.id).first_or_404()

    # WarehouseTask.order_id є NOT NULL - якщо не видалити задачу складу
    # явно, SQLAlchemy спробує занулити її при видаленні Order (через
    # backref "warehouse_task") і впаде на обмеженні БД.
    from models.warehouse import WarehouseTask
    WarehouseTask.query.filter_by(order_id=order_id, store_id=g.store.id).delete()

    OrderItem.query.filter_by(order_id=order_id, store_id=g.store.id).delete()
    db.session.delete(order)
    db.session.commit()
    flash(_("Замовлення видалено."), "info")
    return redirect(url_for(".admin_orders"))
