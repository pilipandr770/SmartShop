"""
Бухгалтерія: огляд доходу/витрат за період + CSV-експорти (замовлення,
витрати складу, дохід по країнах доставки - довідково для VAT/OSS).

Винесено з app.py (розділ "АДМІНКА: БУХГАЛТЕРІЯ", ~170 рядків) як
четвертий крок Phase 2 плану (SWOT 2026-08-08), тим самим підходом, що
й Blog/CRM/Warehouse.
"""
from datetime import datetime

from flask import Blueprint, request, render_template, g, Response
from extensions import db
from models.order import Order
from models.warehouse import WarehouseExpense
from services.admin_auth import admin_required

accounting_bp = Blueprint("accounting", __name__)


def _accounting_period():
    """Читає ?from=&to= з рядка запиту, за замовчуванням - поточний місяць."""
    from datetime import date
    today = date.today()
    default_from = today.replace(day=1)
    try:
        date_from = datetime.strptime(request.args.get("from", ""), "%Y-%m-%d").date()
    except ValueError:
        date_from = default_from
    try:
        date_to = datetime.strptime(request.args.get("to", ""), "%Y-%m-%d").date()
    except ValueError:
        date_to = today
    return date_from, date_to


def _csv_response(filename, header, rows):
    import csv
    from io import StringIO
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows(rows)
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@accounting_bp.route("/admin/accounting")
@admin_required
def admin_accounting():
    """Огляд для бухгалтерії: дохід/витрати за період + посилання на експорт CSV."""
    date_from, date_to = _accounting_period()

    paid_orders_q = Order.query.filter(
        Order.store_id == g.store.id,
        Order.status == "paid",
        db.func.date(Order.paid_at) >= date_from,
        db.func.date(Order.paid_at) <= date_to,
    )
    stats = {
        "orders_count": paid_orders_q.count(),
        "revenue": paid_orders_q.with_entities(db.func.coalesce(db.func.sum(Order.amount), 0.0)).scalar(),
        "subtotal": paid_orders_q.with_entities(db.func.coalesce(db.func.sum(Order.subtotal), 0.0)).scalar(),
        "shipping": paid_orders_q.with_entities(db.func.coalesce(db.func.sum(Order.shipping_cost), 0.0)).scalar(),
        "tax": paid_orders_q.with_entities(db.func.coalesce(db.func.sum(Order.tax), 0.0)).scalar(),
    }

    expenses_total = db.session.query(db.func.coalesce(db.func.sum(WarehouseExpense.amount), 0.0)).filter(
        WarehouseExpense.store_id == g.store.id,
        WarehouseExpense.expense_date >= date_from,
        WarehouseExpense.expense_date <= date_to,
    ).scalar()
    stats["expenses"] = expenses_total
    stats["net"] = stats["revenue"] - expenses_total

    return render_template(
        "admin/accounting.html",
        stats=stats,
        date_from=date_from,
        date_to=date_to,
    )


@accounting_bp.route("/admin/accounting/export/orders.csv")
@admin_required
def admin_accounting_export_orders():
    """CSV-експорт оплачених замовлень за період - основний звіт для бухгалтерії."""
    date_from, date_to = _accounting_period()
    orders = Order.query.filter(
        Order.store_id == g.store.id,
        Order.status.in_(["paid", "shipped", "delivered"]),
        db.func.date(Order.paid_at) >= date_from,
        db.func.date(Order.paid_at) <= date_to,
    ).order_by(Order.paid_at.asc()).all()

    rows = []
    for order in orders:
        company = order.company if order.company_id else None
        rows.append([
            order.order_number or order.id,
            order.paid_at.strftime("%Y-%m-%d %H:%M") if order.paid_at else "",
            order.customer_name or "",
            order.customer_email or "",
            company.name if company else "",
            company.full_vat_number if company else "",
            order.shipping_country or "",
            f"{order.subtotal or 0.0:.2f}",
            f"{order.discount or 0.0:.2f}",
            f"{order.shipping_cost or 0.0:.2f}",
            f"{order.tax or 0.0:.2f}",
            f"{order.amount or 0.0:.2f}",
            order.currency,
            order.payment_method or "",
            order.status,
        ])

    return _csv_response(
        f"orders_{date_from}_{date_to}.csv",
        ["Номер замовлення", "Дата оплати", "Клієнт", "Email", "Компанія (B2B)", "VAT номер",
         "Країна доставки", "Товари", "Знижка", "Доставка", "Податок", "Разом", "Валюта",
         "Спосіб оплати", "Статус"],
        rows,
    )


@accounting_bp.route("/admin/accounting/export/expenses.csv")
@admin_required
def admin_accounting_export_expenses():
    """CSV-експорт витрат складу за період."""
    date_from, date_to = _accounting_period()
    expenses = WarehouseExpense.query.filter(
        WarehouseExpense.store_id == g.store.id,
        WarehouseExpense.expense_date >= date_from,
        WarehouseExpense.expense_date <= date_to,
    ).order_by(WarehouseExpense.expense_date.asc()).all()

    rows = [
        [
            e.expense_date.strftime("%Y-%m-%d") if e.expense_date else "",
            e.category_display,
            e.description or "",
            f"{e.amount:.2f}",
            e.currency,
            e.receipt_number or "",
            e.created_by or "",
        ]
        for e in expenses
    ]

    return _csv_response(
        f"expenses_{date_from}_{date_to}.csv",
        ["Дата", "Категорія", "Опис", "Сума", "Валюта", "№ чека", "Ким додано"],
        rows,
    )


@accounting_bp.route("/admin/accounting/export/revenue-by-country.csv")
@admin_required
def admin_accounting_export_revenue_by_country():
    """
    CSV: дохід згруповано за країною доставки - довідково для VAT/OSS звітності.
    Це НЕ розрахунок ПДВ (в системі немає розбивки по ставках) - лише сума
    оплачених замовлень по країнах, з якою бухгалтер вже рахує податок сам.
    """
    date_from, date_to = _accounting_period()
    rows_query = db.session.query(
        Order.shipping_country,
        db.func.count(Order.id),
        db.func.sum(Order.subtotal),
        db.func.sum(Order.amount),
    ).filter(
        Order.store_id == g.store.id,
        Order.status.in_(["paid", "shipped", "delivered"]),
        db.func.date(Order.paid_at) >= date_from,
        db.func.date(Order.paid_at) <= date_to,
    ).group_by(Order.shipping_country).order_by(Order.shipping_country.asc()).all()

    rows = [
        [country or "(не вказано)", count, f"{subtotal:.2f}", f"{total:.2f}"]
        for country, count, subtotal, total in rows_query
    ]

    return _csv_response(
        f"revenue_by_country_{date_from}_{date_to}.csv",
        ["Країна доставки", "К-сть замовлень", "Сума товарів", "Разом (з доставкою)"],
        rows,
    )
