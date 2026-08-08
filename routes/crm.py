"""
CRM: список і картки B2B-партнерів (Company), автоматична перевірка
надійності (VAT/Handelsregister/WHOIS через services.partner_verifier),
алерти адміністратора.

Винесено з app.py (розділ "CRM ADMIN ROUTES", ~450 рядків) як другий крок
Phase 2 плану (SWOT 2026-08-08), тим самим підходом, що й Blog: спільні
admin_required/db/моделі імпортуються напряму, без залежності від
app.py - жодних closure-специфічних залежностей тут не було (на відміну
від Blog, де знадобилось виносити admin_auth/openai_client/image_storage).
"""
from datetime import datetime

from flask import Blueprint, request, redirect, url_for, flash, render_template, jsonify, g, current_app
from flask_babel import gettext as _

from extensions import db
from models.settings import SiteSettings
from models.company import Company, AdminAlert, AlertSeverity, VerificationLog
from services.admin_auth import admin_required
from services.partner_verifier import partner_verifier
from services.email_service import send_b2b_verification_approved, send_b2b_verification_rejected

crm_bp = Blueprint("crm", __name__)


@crm_bp.route("/admin/crm")
@admin_required
def admin_crm():
    """CRM - список партнерів."""
    settings = SiteSettings.get_or_create(g.store.id)

    filter_status = request.args.get("status", "")
    filter_reliability = request.args.get("reliability", "")
    filter_country = request.args.get("country", "")
    search = request.args.get("search", "")
    page = request.args.get("page", 1, type=int)
    per_page = 20

    query = Company.query.filter_by(store_id=g.store.id)

    if filter_status:
        query = query.filter(Company.status == filter_status)
    if filter_reliability:
        query = query.filter(Company.reliability_level == filter_reliability)
    if filter_country:
        query = query.filter(Company.country_code == filter_country)
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            db.or_(
                Company.name.ilike(search_term),
                Company.vat_number.ilike(search_term),
                Company.domain.ilike(search_term),
            )
        )

    query = query.order_by(Company.created_at.desc())
    total = query.count()
    companies = query.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = (total + per_page - 1) // per_page

    all_companies = Company.query.filter_by(store_id=g.store.id).all()
    stats = {
        "total": len(all_companies),
        "verified": len([c for c in all_companies if c.status == "verified"]),
        "pending": len([c for c in all_companies if c.status == "pending"]),
        "rejected": len([c for c in all_companies if c.status == "rejected"]),
        "high_reliability": len([c for c in all_companies if c.reliability_level == "high"]),
        "medium_reliability": len([c for c in all_companies if c.reliability_level == "medium"]),
        "low_reliability": len([c for c in all_companies if c.reliability_level == "low"]),
        "critical_reliability": len([c for c in all_companies if c.reliability_level == "critical"]),
    }
    total_r = max(1, stats["total"])
    stats["high_reliability_pct"] = int(stats["high_reliability"] / total_r * 100)
    stats["medium_reliability_pct"] = int(stats["medium_reliability"] / total_r * 100)
    stats["low_reliability_pct"] = int(stats["low_reliability"] / total_r * 100)
    stats["critical_reliability_pct"] = int(stats["critical_reliability"] / total_r * 100)

    critical_alerts = AdminAlert.query.filter_by(
        severity=AlertSeverity.CRITICAL.value,
        is_resolved=False,
        store_id=g.store.id,
    ).order_by(AdminAlert.created_at.desc()).all()
    unread_alerts_count = AdminAlert.query.filter_by(is_read=False, store_id=g.store.id).count()

    countries = db.session.query(Company.country_code, Company.country).distinct().filter(
        Company.country_code.isnot(None),
        Company.store_id == g.store.id,
    ).all()

    return render_template(
        "admin/crm.html",
        settings=settings,
        companies=companies,
        stats=stats,
        critical_alerts=critical_alerts,
        unread_alerts_count=unread_alerts_count,
        countries=countries,
        filter_status=filter_status,
        filter_reliability=filter_reliability,
        filter_country=filter_country,
        search=search,
        page=page,
        total_pages=total_pages,
    )


@crm_bp.route("/admin/crm/partner/<int:id>")
@admin_required
def admin_crm_partner(id):
    """Деталі партнера."""
    settings = SiteSettings.get_or_create(g.store.id)
    company = Company.query.filter_by(id=id, store_id=g.store.id).first_or_404()

    company_alerts = AdminAlert.query.filter_by(
        company_id=id,
        is_resolved=False
    ).order_by(AdminAlert.created_at.desc()).all()

    verification_logs = VerificationLog.query.filter_by(
        company_id=id
    ).order_by(VerificationLog.checked_at.desc()).limit(20).all()

    return render_template(
        "admin/crm_partner.html",
        settings=settings,
        company=company,
        company_alerts=company_alerts,
        verification_logs=verification_logs,
    )


@crm_bp.route("/admin/crm/partner/<int:id>/verify", methods=["POST"])
@admin_required
def admin_crm_partner_verify(id):
    """Запустити верифікацію партнера."""
    company = Company.query.filter_by(id=id, store_id=g.store.id).first_or_404()

    try:
        previous_result = company.last_verification_data

        result = partner_verifier.full_verification(
            company_name=company.name,
            vat_number=company.full_vat_number,
            domain=company.website or company.domain,
            hr_number=company.handelsregister_id,
            country_code=company.country_code,
            city=company.city,
            previous_result=previous_result,
        )

        company.reliability_score = result.get("reliability_score", 0)
        company.reliability_level = result.get("reliability_level", "critical")
        company.last_verification_at = datetime.utcnow()
        company.last_verification_data = result

        if result.get("vat_result", {}).get("valid"):
            company.vat_verified = True
            company.vat_verified_at = datetime.utcnow()
            company.vat_data = result["vat_result"]

        if result.get("whois_result", {}).get("valid"):
            company.is_whois_verified = True
            company.whois_checked_at = datetime.utcnow()
            company.whois_data = result["whois_result"]

        if result.get("hr_result", {}).get("valid"):
            company.is_hr_verified = True
            company.hr_data = result["hr_result"]

        VerificationLog.log_check(
            company_id=company.id,
            check_type="full",
            status="success",
            is_valid=result.get("reliability_score", 0) >= 50,
            response_data=result,
            changes_detected=len(result.get("changes", [])) > 0,
            changes_description=str(result.get("changes", [])) if result.get("changes") else None,
        )

        for alert_data in result.get("alerts", []):
            AdminAlert.create_alert(
                alert_type=alert_data.get("type"),
                title=alert_data.get("message", "Алерт верифікації"),
                message=alert_data.get("message"),
                company_id=company.id,
                severity=alert_data.get("severity", "info"),
                data=result,
            )

        db.session.commit()

        return jsonify({
            "success": True,
            "summary": result.get("summary", ""),
            "score": result.get("reliability_score"),
            "level": result.get("reliability_level"),
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@crm_bp.route("/admin/crm/partner/<int:id>/approve", methods=["POST"])
@admin_required
def admin_crm_partner_approve(id):
    """Підтвердити партнера."""
    company = Company.query.filter_by(id=id, store_id=g.store.id).first_or_404()
    company.status = "verified"
    company.verified_at = datetime.utcnow()
    db.session.commit()

    if company.contact_email:
        try:
            send_b2b_verification_approved(
                company.contact_email,
                company.name,
                company.discount_percent or 0
            )
            current_app.logger.info(f'B2B approval email sent to {company.contact_email}')
        except Exception as e:
            current_app.logger.error(f'Failed to send B2B approval email: {str(e)}')

    return jsonify({"success": True})


@crm_bp.route("/admin/crm/partner/<int:id>/reject", methods=["POST"])
@admin_required
def admin_crm_partner_reject(id):
    """Відхилити партнера."""
    data = request.get_json() or {}
    company = Company.query.filter_by(id=id, store_id=g.store.id).first_or_404()
    company.status = "rejected"
    company.rejection_reason = data.get("reason", "")
    db.session.commit()

    if company.contact_email:
        try:
            send_b2b_verification_rejected(
                company.contact_email,
                company.name,
                company.rejection_reason
            )
            current_app.logger.info(f'B2B rejection email sent to {company.contact_email}')
        except Exception as e:
            current_app.logger.error(f'Failed to send B2B rejection email: {str(e)}')

    return jsonify({"success": True})


@crm_bp.route("/admin/crm/partner/<int:id>/suspend", methods=["POST"])
@admin_required
def admin_crm_partner_suspend(id):
    """Призупинити партнера."""
    data = request.get_json() or {}
    company = Company.query.filter_by(id=id, store_id=g.store.id).first_or_404()
    company.status = "suspended"
    company.rejection_reason = data.get("reason", "")
    db.session.commit()

    return jsonify({"success": True})


@crm_bp.route("/admin/crm/partner/<int:id>/update", methods=["POST"])
@admin_required
def admin_crm_partner_update(id):
    """Оновити B2B налаштування партнера."""
    company = Company.query.filter_by(id=id, store_id=g.store.id).first_or_404()
    company.credit_limit = float(request.form.get("credit_limit", 0))
    company.payment_terms = int(request.form.get("payment_terms", 0))
    company.discount_percent = float(request.form.get("discount_percent", 0))
    db.session.commit()

    flash(_("Налаштування оновлено!"), "success")
    return redirect(url_for(".admin_crm_partner", id=id))


@crm_bp.route("/admin/crm/alerts")
@admin_required
def admin_crm_alerts():
    """Список алертів."""
    settings = SiteSettings.get_or_create(g.store.id)

    filter_severity = request.args.get("severity", "")
    filter_status = request.args.get("status", "")
    page = request.args.get("page", 1, type=int)
    per_page = 30

    query = AdminAlert.query.filter_by(store_id=g.store.id)

    if filter_severity:
        query = query.filter(AdminAlert.severity == filter_severity)
    if filter_status == "unread":
        query = query.filter(AdminAlert.is_read == False)
    elif filter_status == "unresolved":
        query = query.filter(AdminAlert.is_resolved == False)
    elif filter_status == "resolved":
        query = query.filter(AdminAlert.is_resolved == True)

    query = query.order_by(AdminAlert.created_at.desc())
    total = query.count()
    alerts = query.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = (total + per_page - 1) // per_page

    all_alerts = AdminAlert.query.filter_by(store_id=g.store.id).all()
    stats = {
        "critical": len([a for a in all_alerts if a.severity == "critical" and not a.is_resolved]),
        "warning": len([a for a in all_alerts if a.severity == "warning" and not a.is_resolved]),
        "info": len([a for a in all_alerts if a.severity == "info" and not a.is_resolved]),
        "unread": len([a for a in all_alerts if not a.is_read]),
    }

    return render_template(
        "admin/crm_alerts.html",
        settings=settings,
        alerts=alerts,
        stats=stats,
        filter_severity=filter_severity,
        filter_status=filter_status,
        page=page,
        total_pages=total_pages,
    )


@crm_bp.route("/admin/crm/alert/<int:id>/read", methods=["POST"])
@admin_required
def admin_crm_alert_read(id):
    """Позначити алерт прочитаним."""
    alert = AdminAlert.query.filter_by(id=id, store_id=g.store.id).first_or_404()
    alert.mark_read()

    return jsonify({"success": True})


@crm_bp.route("/admin/crm/alert/<int:id>/resolve", methods=["POST"])
@admin_required
def admin_crm_alert_resolve(id):
    """Вирішити алерт."""
    data = request.get_json() or {}
    alert = AdminAlert.query.filter_by(id=id, store_id=g.store.id).first_or_404()

    alert.is_resolved = True
    alert.resolved_at = datetime.utcnow()
    alert.resolution_note = data.get("note", "")
    db.session.commit()

    return jsonify({"success": True})


@crm_bp.route("/admin/crm/alerts/mark-all-read", methods=["POST"])
@admin_required
def admin_crm_alerts_mark_all_read():
    """Позначити всі алерти прочитаними."""
    AdminAlert.query.filter_by(is_read=False, store_id=g.store.id).update({"is_read": True})
    db.session.commit()

    return jsonify({"success": True})


@crm_bp.route("/admin/crm/run-daily-check", methods=["POST"])
@admin_required
def admin_crm_run_daily_check():
    """Запустити щоденну перевірку всіх партнерів."""
    try:
        companies = Company.query.filter(
            Company.status.in_(["verified", "pending"]),
            Company.store_id == g.store.id,
        ).all()

        checked = 0
        alerts_created = 0

        for company in companies:
            try:
                previous_result = company.last_verification_data

                result = partner_verifier.full_verification(
                    company_name=company.name,
                    vat_number=company.full_vat_number,
                    domain=company.website or company.domain,
                    hr_number=company.handelsregister_id,
                    country_code=company.country_code,
                    city=company.city,
                    previous_result=previous_result,
                )

                company.reliability_score = result.get("reliability_score", 0)
                company.reliability_level = result.get("reliability_level", "critical")
                company.last_verification_at = datetime.utcnow()
                company.last_verification_data = result

                if result.get("vat_result", {}).get("valid"):
                    company.vat_verified = True
                    company.vat_data = result["vat_result"]

                if result.get("whois_result", {}).get("valid"):
                    company.is_whois_verified = True
                    company.whois_data = result["whois_result"]

                if result.get("hr_result", {}).get("valid"):
                    company.is_hr_verified = True
                    company.hr_data = result["hr_result"]

                VerificationLog.log_check(
                    company_id=company.id,
                    check_type="daily",
                    status="success",
                    is_valid=result.get("reliability_score", 0) >= 50,
                    response_data=result,
                    changes_detected=len(result.get("changes", [])) > 0,
                )

                for alert_data in result.get("alerts", []):
                    AdminAlert.create_alert(
                        alert_type=alert_data.get("type"),
                        title=f"{company.name}: {alert_data.get('message', 'Алерт')}",
                        message=alert_data.get("message"),
                        company_id=company.id,
                        severity=alert_data.get("severity", "info"),
                    )
                    alerts_created += 1

                checked += 1

            except Exception as e:
                VerificationLog.log_check(
                    company_id=company.id,
                    check_type="daily",
                    status="error",
                    is_valid=False,
                    error_message=str(e),
                )

        db.session.commit()

        return jsonify({
            "success": True,
            "checked": checked,
            "alerts": alerts_created,
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
