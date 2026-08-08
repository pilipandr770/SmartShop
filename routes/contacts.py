"""
Форма контактів: публічне надсилання повідомлення + адмінська модерація
(список, позначення прочитаним, видалення).

Винесено з app.py (розділи "АДМІНКА: КОНТАКТИ" + "ПУБЛІЧНИЙ: ФОРМА
КОНТАКТІВ") як шостий крок Phase 2 плану (SWOT 2026-08-08), тим самим
підходом, що й попередні модулі.
"""
from datetime import datetime

from flask import Blueprint, request, redirect, url_for, flash, render_template, jsonify, g
from flask_babel import gettext as _

from extensions import db
from models.settings import ContactMessage
from services.admin_auth import admin_required

contacts_bp = Blueprint("contacts", __name__)


@contacts_bp.route("/admin/contacts")
@admin_required
def admin_contacts():
    """Список заявок з форми контактів."""
    page = request.args.get("page", 1, type=int)
    per_page = 20

    pagination = ContactMessage.query.filter_by(store_id=g.store.id).order_by(
        ContactMessage.is_read.asc(),
        ContactMessage.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    contacts = pagination.items

    today = datetime.utcnow().date()
    stats = {
        "total": ContactMessage.query.filter_by(store_id=g.store.id).count(),
        "unread": ContactMessage.query.filter_by(is_read=False, store_id=g.store.id).count(),
        "today": ContactMessage.query.filter(
            db.func.date(ContactMessage.created_at) == today,
            ContactMessage.store_id == g.store.id,
        ).count(),
    }

    return render_template(
        "admin/contacts.html",
        contacts=contacts,
        pagination=pagination,
        stats=stats,
    )


@contacts_bp.route("/admin/contacts/<int:contact_id>/read", methods=["POST"])
@admin_required
def admin_contact_mark_read(contact_id):
    """Позначити заявку як прочитану."""
    contact = ContactMessage.query.filter_by(id=contact_id, store_id=g.store.id).first_or_404()
    contact.is_read = True
    db.session.commit()
    flash(_("Заявку позначено як прочитану."), "success")
    return redirect(url_for(".admin_contacts"))


@contacts_bp.route("/admin/contacts/<int:contact_id>/delete", methods=["POST"])
@admin_required
def admin_contact_delete(contact_id):
    """Видалити заявку."""
    contact = ContactMessage.query.filter_by(id=contact_id, store_id=g.store.id).first_or_404()
    db.session.delete(contact)
    db.session.commit()
    flash(_("Заявку видалено."), "info")
    return redirect(url_for(".admin_contacts"))


@contacts_bp.route("/admin/contacts/mark-all-read", methods=["POST"])
@admin_required
def admin_contacts_mark_all_read():
    """Позначити всі заявки як прочитані."""
    ContactMessage.query.filter_by(is_read=False, store_id=g.store.id).update({"is_read": True})
    db.session.commit()
    flash(_("Усі заявки позначено як прочитані."), "success")
    return redirect(url_for(".admin_contacts"))


@contacts_bp.route("/admin/contacts/delete-read", methods=["POST"])
@admin_required
def admin_contacts_delete_read():
    """Видалити всі прочитані заявки."""
    ContactMessage.query.filter_by(is_read=True, store_id=g.store.id).delete()
    db.session.commit()
    flash(_("Прочитані заявки видалено."), "info")
    return redirect(url_for(".admin_contacts"))


@contacts_bp.route("/api/contact", methods=["POST"])
def api_contact():
    """API для збереження повідомлень з форми контактів."""
    data = request.get_json() if request.is_json else request.form

    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    phone = data.get("phone", "").strip()
    subject = data.get("subject", "").strip()
    message = data.get("message", "").strip()

    if not name or not email or not message:
        if request.is_json:
            return jsonify({"error": _("Заповніть обов'язкові поля")}), 400
        flash(_("Заповніть обов'язкові поля: ім'я, email, повідомлення."), "danger")
        return redirect(url_for("contacts_page"))

    contact = ContactMessage(
        store_id=g.store.id,
        name=name,
        email=email,
        phone=phone or None,
        subject=subject or None,
        message=message,
    )
    db.session.add(contact)
    db.session.commit()

    if request.is_json:
        return jsonify({"success": True, "message": "Дякуємо за ваше повідомлення!"})

    flash(_("Дякуємо! Ваше повідомлення надіслано."), "success")
    return redirect(url_for("contacts_page"))
