"""
Склад: завдання на відправку (WarehouseTask), залишки товарів, поповнення
запасів (ReplenishmentOrder), витрати складу, звіти.

Винесено з app.py (розділ "СКЛАД (WAREHOUSE) ROUTES", ~585 рядків) як
третій крок Phase 2 плану (SWOT 2026-08-08), тим самим підходом, що й
Blog/CRM: спільні admin_required/db/моделі імпортуються напряму. Жодних
closure-специфічних залежностей тут немає (як і в CRM).
"""
from datetime import datetime, date, timedelta

from flask import Blueprint, request, redirect, url_for, flash, render_template, g
from flask_babel import gettext as _

from extensions import db
from models.product import Product
from models.settings import SiteSettings
from models.shipping import CarrierAccount
from models.warehouse import (
    WarehouseTask, ShipmentStatus, LowStockAlert, StockMovement,
    ReplenishmentOrder, ReplenishmentStatus, ReplenishmentItem,
    WarehouseExpense, ExpenseCategory,
)
from services.admin_auth import admin_required

warehouse_bp = Blueprint("warehouse", __name__)


@warehouse_bp.route("/admin/warehouse")
@admin_required
def admin_warehouse():
    """Головна сторінка складу - завдання на відправку."""
    page = request.args.get("page", 1, type=int)
    status_filter = request.args.get("status", "")
    per_page = 20

    query = WarehouseTask.query.filter_by(store_id=g.store.id)

    if status_filter:
        query = query.filter(WarehouseTask.status == status_filter)

    if not status_filter:
        active_statuses = [
            ShipmentStatus.PENDING.value,
            ShipmentStatus.PROCESSING.value,
            ShipmentStatus.PACKED.value,
            ShipmentStatus.READY.value,
        ]
        query = query.filter(WarehouseTask.status.in_(active_statuses))

    query = query.order_by(WarehouseTask.priority.asc(), WarehouseTask.created_at.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    tasks = pagination.items

    stats = {
        "pending": WarehouseTask.query.filter_by(status=ShipmentStatus.PENDING.value, store_id=g.store.id).count(),
        "processing": WarehouseTask.query.filter_by(status=ShipmentStatus.PROCESSING.value, store_id=g.store.id).count(),
        "packed": WarehouseTask.query.filter_by(status=ShipmentStatus.PACKED.value, store_id=g.store.id).count(),
        "shipped_today": WarehouseTask.query.filter(
            WarehouseTask.status == ShipmentStatus.SHIPPED.value,
            WarehouseTask.store_id == g.store.id,
            db.func.date(WarehouseTask.shipped_at) == db.func.current_date()
        ).count(),
    }

    return render_template(
        "admin/warehouse/tasks.html",
        tasks=tasks,
        pagination=pagination,
        stats=stats,
        status_filter=status_filter,
        page=page,
        total_pages=pagination.pages,
    )


@warehouse_bp.route("/admin/warehouse/task/<int:id>", methods=["GET", "POST"])
@admin_required
def admin_warehouse_task(id):
    """Деталі завдання складу."""
    task = WarehouseTask.query.filter_by(id=id, store_id=g.store.id).first_or_404()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "start_processing":
            task.status = ShipmentStatus.PROCESSING.value
            task.assigned_to = request.form.get("assigned_to", "")
            db.session.commit()
            flash(_("✅ Завдання взято в роботу"), "success")

        elif action == "mark_packed":
            task.mark_packed(
                weight_kg=request.form.get("weight_kg", type=float),
                dimensions=request.form.get("dimensions", "")
            )
            flash(_("📦 Замовлення запаковано"), "success")

        elif action == "mark_ready":
            task.status = ShipmentStatus.READY.value
            db.session.commit()
            flash(_("✅ Готово до відправки"), "success")

        elif action == "mark_shipped":
            task.mark_shipped(
                tracking_number=request.form.get("tracking_number", ""),
                carrier=request.form.get("carrier", "")
            )
            flash(_("🚚 Відправлено!"), "success")

        elif action == "mark_delivered":
            task.mark_delivered()
            flash(_("✔️ Доставлено!"), "success")

        elif action == "cancel":
            task.status = ShipmentStatus.CANCELLED.value
            task.admin_notes = request.form.get("cancel_reason", "")
            db.session.commit()
            flash(_("❌ Завдання скасовано"), "warning")

        elif action == "update_notes":
            task.admin_notes = request.form.get("admin_notes", "")
            db.session.commit()
            flash(_("💾 Нотатки збережено"), "success")

        return redirect(url_for(".admin_warehouse_task", id=id))

    return render_template("admin/warehouse/task_detail.html", task=task)


@warehouse_bp.route("/admin/warehouse/task/<int:id>/print")
@admin_required
def admin_warehouse_task_print(id):
    """
    Пакувальний лист / відгрузочна наклейка для друку через діалог
    браузера (Ctrl+P) - працює для БУДЬ-ЯКОГО завдання складу, незалежно
    від того, чи підключена служба доставки (DHL/UPS) чи трек-номер
    внесено вручну.
    """
    task = WarehouseTask.query.filter_by(id=id, store_id=g.store.id).first_or_404()
    settings = SiteSettings.get_or_create(g.store.id)
    order = task.order

    sender = None
    if task.carrier:
        account = CarrierAccount.query.filter(
            CarrierAccount.store_id == g.store.id,
            db.func.lower(CarrierAccount.carrier) == task.carrier.lower(),
        ).first()
        if account and account.origin_street:
            sender = account.origin_address
    if not sender:
        sender = {
            "name": settings.site_name or "",
            "phone": settings.contact_phone or "",
            "street": settings.contact_address or "",
            "city": "",
            "postal_code": "",
            "country_code": "",
        }

    return render_template(
        "admin/warehouse/print_label.html",
        task=task,
        order=order,
        settings=settings,
        sender=sender,
    )


@warehouse_bp.route("/admin/warehouse/stock")
@admin_required
def admin_warehouse_stock():
    """Залишки товарів на складі."""
    page = request.args.get("page", 1, type=int)
    show_low = request.args.get("low", "0") == "1"
    search = request.args.get("search", "")
    per_page = 50

    query = Product.query.filter_by(is_active=True, store_id=g.store.id)

    if show_low:
        query = query.filter(
            Product.stock <= Product.min_stock,
            Product.min_stock > 0
        )

    if search:
        query = query.filter(
            db.or_(
                Product.name.ilike(f"%{search}%"),
                Product.sku.ilike(f"%{search}%")
            )
        )

    query = query.order_by(Product.stock.asc(), Product.name.asc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    products = pagination.items

    stats = {
        "total_products": Product.query.filter_by(is_active=True, store_id=g.store.id).count(),
        "out_of_stock": Product.query.filter_by(is_active=True, stock=0, store_id=g.store.id).count(),
        "low_stock": Product.query.filter(
            Product.is_active == True,
            Product.stock > 0,
            Product.stock <= Product.min_stock,
            Product.min_stock > 0,
            Product.store_id == g.store.id,
        ).count(),
        "unresolved_alerts": LowStockAlert.query.filter_by(is_resolved=False, store_id=g.store.id).count(),
    }

    return render_template(
        "admin/warehouse/stock.html",
        products=products,
        pagination=pagination,
        stats=stats,
        show_low=show_low,
        search=search,
        page=page,
        total_pages=pagination.pages,
    )


@warehouse_bp.route("/admin/warehouse/stock/<int:product_id>/adjust", methods=["POST"])
@admin_required
def admin_warehouse_stock_adjust(product_id):
    """Коригування залишку товару."""
    product = Product.query.filter_by(id=product_id, store_id=g.store.id).first_or_404()

    adjustment = request.form.get("adjustment", 0, type=int)
    reason = request.form.get("reason", "adjustment")
    notes = request.form.get("notes", "")

    if adjustment == 0:
        flash(_("Введіть кількість для коригування"), "warning")
        return redirect(url_for(".admin_warehouse_stock"))

    try:
        StockMovement.record_movement(
            product_id=product_id,
            quantity=adjustment,
            movement_type="adjustment",
            reason=reason,
            notes=notes,
            performed_by="admin",
            store_id=g.store.id,
        )
        flash(_("✅ Залишок '%(name)s' скориговано на %(adjustment)+d") % {"name": product.name, "adjustment": adjustment}, "success")
    except ValueError as e:
        flash(_("❌ Помилка: %(error)s") % {"error": str(e)}, "danger")

    return redirect(url_for(".admin_warehouse_stock"))


@warehouse_bp.route("/admin/warehouse/stock/<int:product_id>/history")
@admin_required
def admin_warehouse_stock_history(product_id):
    """Історія руху товару."""
    product = Product.query.filter_by(id=product_id, store_id=g.store.id).first_or_404()

    page = request.args.get("page", 1, type=int)
    per_page = 50

    query = StockMovement.query.filter_by(product_id=product_id, store_id=g.store.id)\
        .order_by(StockMovement.created_at.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    movements = pagination.items

    return render_template(
        "admin/warehouse/stock_history.html",
        product=product,
        movements=movements,
        pagination=pagination,
    )


@warehouse_bp.route("/admin/warehouse/replenishment")
@admin_required
def admin_warehouse_replenishment():
    """Замовлення на поповнення."""
    page = request.args.get("page", 1, type=int)
    status_filter = request.args.get("status", "")
    per_page = 20

    query = ReplenishmentOrder.query.filter_by(store_id=g.store.id)

    if status_filter:
        query = query.filter(ReplenishmentOrder.status == status_filter)

    query = query.order_by(ReplenishmentOrder.created_at.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    orders = pagination.items

    stats = {
        "draft": ReplenishmentOrder.query.filter_by(status=ReplenishmentStatus.DRAFT.value, store_id=g.store.id).count(),
        "pending": ReplenishmentOrder.query.filter_by(status=ReplenishmentStatus.PENDING.value, store_id=g.store.id).count(),
        "ordered": ReplenishmentOrder.query.filter_by(status=ReplenishmentStatus.ORDERED.value, store_id=g.store.id).count(),
        "shipped": ReplenishmentOrder.query.filter_by(status=ReplenishmentStatus.SHIPPED.value, store_id=g.store.id).count(),
    }

    return render_template(
        "admin/warehouse/replenishment.html",
        orders=orders,
        pagination=pagination,
        stats=stats,
        status_filter=status_filter,
        page=page,
        total_pages=pagination.pages,
    )


@warehouse_bp.route("/admin/warehouse/replenishment/new", methods=["GET", "POST"])
@admin_required
def admin_warehouse_replenishment_new():
    """Нове замовлення на поповнення."""
    if request.method == "POST":
        order = ReplenishmentOrder(
            store_id=g.store.id,
            supplier_name=request.form.get("supplier_name", ""),
            supplier_contact=request.form.get("supplier_contact", ""),
            notes=request.form.get("notes", ""),
            status="draft",
            created_by="admin",
        )
        db.session.add(order)
        db.session.flush()
        order.generate_order_number()

        product_ids = request.form.getlist("product_ids")
        quantities = request.form.getlist("quantities")
        prices = request.form.getlist("prices")

        for i, product_id in enumerate(product_ids):
            if product_id:
                product = Product.query.filter_by(id=int(product_id), store_id=g.store.id).first()
                if product:
                    item = ReplenishmentItem(
                        store_id=g.store.id,
                        replenishment_id=order.id,
                        product_id=product.id,
                        product_name=product.name,
                        product_sku=product.sku,
                        quantity=int(quantities[i]) if i < len(quantities) and quantities[i] else 1,
                        unit_price=float(prices[i]) if i < len(prices) and prices[i] else 0.0,
                    )
                    db.session.add(item)

        order.calculate_totals()
        db.session.commit()

        flash(_("✅ Замовлення %(order_number)s створено") % {"order_number": order.order_number}, "success")
        return redirect(url_for(".admin_warehouse_replenishment_detail", id=order.id))

    low_stock_products = Product.query.filter(
        Product.is_active == True,
        Product.stock <= Product.min_stock,
        Product.min_stock > 0,
        Product.store_id == g.store.id,
    ).all()

    return render_template(
        "admin/warehouse/replenishment_new.html",
        low_stock_products=low_stock_products,
        products=Product.query.filter_by(is_active=True, store_id=g.store.id).order_by(Product.name).all(),
    )


@warehouse_bp.route("/admin/warehouse/replenishment/<int:id>", methods=["GET", "POST"])
@admin_required
def admin_warehouse_replenishment_detail(id):
    """Деталі замовлення на поповнення."""
    order = ReplenishmentOrder.query.filter_by(id=id, store_id=g.store.id).first_or_404()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "approve":
            order.status = ReplenishmentStatus.APPROVED.value
            db.session.commit()
            flash(_("✅ Замовлення підтверджено"), "success")

        elif action == "order":
            order.status = ReplenishmentStatus.ORDERED.value
            order.ordered_at = datetime.utcnow()
            db.session.commit()
            flash(_("📤 Замовлено у постачальника"), "success")

        elif action == "shipped":
            order.status = ReplenishmentStatus.SHIPPED.value
            order.expected_at = datetime.utcnow()  # TODO: real expected date
            db.session.commit()
            flash(_("🚚 Позначено як відправлено"), "success")

        elif action == "receive":
            order.mark_received()
            flash(_("✔️ Товар отримано, залишки оновлено!"), "success")

        elif action == "cancel":
            order.status = ReplenishmentStatus.CANCELLED.value
            db.session.commit()
            flash(_("❌ Замовлення скасовано"), "warning")

        elif action == "mark_paid":
            order.is_paid = True
            order.paid_at = datetime.utcnow()
            order.payment_method = request.form.get("payment_method", "")
            db.session.commit()
            flash(_("💰 Оплату зафіксовано"), "success")

        return redirect(url_for(".admin_warehouse_replenishment_detail", id=id))

    return render_template("admin/warehouse/replenishment_detail.html", order=order)


@warehouse_bp.route("/admin/warehouse/expenses")
@admin_required
def admin_warehouse_expenses():
    """Витрати складу."""
    page = request.args.get("page", 1, type=int)
    category_filter = request.args.get("category", "")
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")
    per_page = 50

    query = WarehouseExpense.query.filter_by(store_id=g.store.id)

    if category_filter:
        query = query.filter(WarehouseExpense.category == category_filter)

    if date_from:
        query = query.filter(WarehouseExpense.expense_date >= date_from)

    if date_to:
        query = query.filter(WarehouseExpense.expense_date <= date_to)

    query = query.order_by(WarehouseExpense.expense_date.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    expenses = pagination.items

    today = date.today()
    first_day = today.replace(day=1)

    monthly_stats = db.session.query(
        WarehouseExpense.category,
        db.func.sum(WarehouseExpense.amount)
    ).filter(
        WarehouseExpense.expense_date >= first_day,
        WarehouseExpense.store_id == g.store.id,
    ).group_by(WarehouseExpense.category).all()

    stats_by_category = {cat: amt for cat, amt in monthly_stats}
    total_monthly = sum(stats_by_category.values())

    return render_template(
        "admin/warehouse/expenses.html",
        expenses=expenses,
        pagination=pagination,
        stats_by_category=stats_by_category,
        total_monthly=total_monthly,
        category_filter=category_filter,
        date_from=date_from,
        date_to=date_to,
        page=page,
        total_pages=pagination.pages,
        expense_categories=ExpenseCategory,
    )


@warehouse_bp.route("/admin/warehouse/expenses/add", methods=["GET", "POST"])
@admin_required
def admin_warehouse_expenses_add():
    """Додати витрату."""
    if request.method == "POST":
        expense = WarehouseExpense(
            store_id=g.store.id,
            category=request.form.get("category", ExpenseCategory.OTHER.value),
            description=request.form.get("description", ""),
            amount=request.form.get("amount", 0, type=float),
            currency=request.form.get("currency", "UAH"),
            receipt_number=request.form.get("receipt_number", "") or None,
            notes=request.form.get("notes", "") or None,
            expense_date=date.fromisoformat(request.form.get("expense_date", str(date.today()))),
            created_by="admin",
        )
        db.session.add(expense)
        db.session.commit()

        flash(_("✅ Витрату додано"), "success")
        return redirect(url_for(".admin_warehouse_expenses"))

    return render_template(
        "admin/warehouse/expense_add.html",
        expense_categories=ExpenseCategory,
        today=date.today(),
    )


@warehouse_bp.route("/admin/warehouse/reports")
@admin_required
def admin_warehouse_reports():
    """Звіти складу."""
    period = request.args.get("period", "month")
    today = date.today()

    if period == "week":
        start_date = today - timedelta(days=7)
    elif period == "month":
        start_date = today.replace(day=1)
    elif period == "quarter":
        quarter_start = (today.month - 1) // 3 * 3 + 1
        start_date = today.replace(month=quarter_start, day=1)
    else:  # year
        start_date = today.replace(month=1, day=1)

    shipments = {
        "total": WarehouseTask.query.filter(
            WarehouseTask.created_at >= start_date, WarehouseTask.store_id == g.store.id
        ).count(),
        "shipped": WarehouseTask.query.filter(
            WarehouseTask.shipped_at >= start_date,
            WarehouseTask.shipped_at.isnot(None),
            WarehouseTask.store_id == g.store.id,
        ).count(),
        "delivered": WarehouseTask.query.filter(
            WarehouseTask.delivered_at >= start_date,
            WarehouseTask.delivered_at.isnot(None),
            WarehouseTask.store_id == g.store.id,
        ).count(),
    }

    replenishments = {
        "total": ReplenishmentOrder.query.filter(
            ReplenishmentOrder.created_at >= start_date, ReplenishmentOrder.store_id == g.store.id
        ).count(),
        "received": ReplenishmentOrder.query.filter(
            ReplenishmentOrder.received_at >= start_date,
            ReplenishmentOrder.received_at.isnot(None),
            ReplenishmentOrder.store_id == g.store.id,
        ).count(),
        "total_cost": db.session.query(db.func.sum(ReplenishmentOrder.total)).filter(
            ReplenishmentOrder.received_at >= start_date,
            ReplenishmentOrder.received_at.isnot(None),
            ReplenishmentOrder.store_id == g.store.id,
        ).scalar() or 0,
    }

    expenses = {
        "total": db.session.query(db.func.sum(WarehouseExpense.amount)).filter(
            WarehouseExpense.expense_date >= start_date, WarehouseExpense.store_id == g.store.id
        ).scalar() or 0,
    }

    expense_by_category = db.session.query(
        WarehouseExpense.category,
        db.func.sum(WarehouseExpense.amount)
    ).filter(
        WarehouseExpense.expense_date >= start_date, WarehouseExpense.store_id == g.store.id
    ).group_by(WarehouseExpense.category).all()

    return render_template(
        "admin/warehouse/reports.html",
        period=period,
        start_date=start_date,
        shipments=shipments,
        replenishments=replenishments,
        expenses=expenses,
        expense_by_category=dict(expense_by_category),
    )
