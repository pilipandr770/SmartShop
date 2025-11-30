"""
Маршрути авторизації: login, logout, register (B2C та B2B)
"""
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from extensions import db
from models.user import User, UserRole
from models.company import Company, CompanyStatus, VerificationLog
from services.vat_checker import check_vat_number

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Сторінка входу."""
    if current_user.is_authenticated:
        return redirect(url_for("cabinet.dashboard"))
    
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        remember = request.form.get("remember") == "on"
        
        user = User.get_by_email(email)
        
        if user and user.check_password(password):
            if not user.is_active:
                flash("Ваш акаунт деактивовано. Зверніться до підтримки.", "danger")
                return render_template("auth/login.html")
            
            login_user(user, remember=remember)
            user.update_last_login()
            
            flash(f"Вітаємо, {user.full_name}!", "success")
            
            # Редірект залежно від ролі
            next_page = request.args.get("next")
            if next_page:
                return redirect(next_page)
            
            if user.is_admin or user.is_manager:
                return redirect(url_for("admin_dashboard"))
            
            return redirect(url_for("cabinet.dashboard"))
        
        flash("Невірний email або пароль.", "danger")
    
    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    """Вихід з системи."""
    logout_user()
    flash("Ви успішно вийшли з системи.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Реєстрація B2C клієнта."""
    if current_user.is_authenticated:
        return redirect(url_for("cabinet.dashboard"))
    
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        phone = request.form.get("phone", "").strip()
        
        # Валідація
        errors = []
        
        if not email:
            errors.append("Email обов'язковий")
        elif User.get_by_email(email):
            errors.append("Користувач з таким email вже існує")
        
        if not password:
            errors.append("Пароль обов'язковий")
        elif len(password) < 6:
            errors.append("Пароль має бути не менше 6 символів")
        elif password != password_confirm:
            errors.append("Паролі не співпадають")
        
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("auth/register.html")
        
        # Створення користувача
        user = User.create_user(
            email=email,
            password=password,
            role=UserRole.CUSTOMER,
            first_name=first_name or None,
            last_name=last_name or None,
            phone=phone or None,
        )
        
        login_user(user)
        flash("Реєстрація успішна! Ласкаво просимо!", "success")
        return redirect(url_for("cabinet.dashboard"))
    
    return render_template("auth/register.html")


@auth_bp.route("/register/b2b", methods=["GET", "POST"])
def register_b2b():
    """Реєстрація B2B партнера."""
    if current_user.is_authenticated:
        return redirect(url_for("cabinet.dashboard"))
    
    # Перевіряємо чи відкрита B2B реєстрація
    from models.settings import SiteSettings
    settings = SiteSettings.get_or_create()
    if not settings.b2b_registration_open:
        flash("B2B реєстрація тимчасово закрита.", "warning")
        return redirect(url_for("auth.login"))
    
    vat_result = None
    
    if request.method == "POST":
        # Дані користувача
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        phone = request.form.get("phone", "").strip()
        
        # Дані компанії
        company_name = request.form.get("company_name", "").strip()
        legal_name = request.form.get("legal_name", "").strip()
        vat_number = request.form.get("vat_number", "").strip()
        vat_country = request.form.get("vat_country", "").strip().upper()
        
        address = request.form.get("address", "").strip()
        city = request.form.get("city", "").strip()
        postal_code = request.form.get("postal_code", "").strip()
        country = request.form.get("country", "").strip()
        
        website = request.form.get("website", "").strip()
        
        # Валідація
        errors = []
        
        if not email:
            errors.append("Email обов'язковий")
        elif User.get_by_email(email):
            errors.append("Користувач з таким email вже існує")
        
        if not password:
            errors.append("Пароль обов'язковий")
        elif len(password) < 8:
            errors.append("Пароль має бути не менше 8 символів")
        elif password != password_confirm:
            errors.append("Паролі не співпадають")
        
        if not company_name:
            errors.append("Назва компанії обов'язкова")
        
        if not first_name or not last_name:
            errors.append("Ім'я та прізвище контактної особи обов'язкові")
        
        # Перевірка VAT якщо вказано
        vat_verified = False
        if vat_number:
            if not vat_country:
                # Спробуємо визначити з номера
                from services.vat_checker import VATChecker
                vat_country, _ = VATChecker.parse_vat_number(vat_number)
            
            if vat_country:
                vat_result = check_vat_number(vat_number, vat_country)
                vat_verified = vat_result.get("valid", False)
                
                if vat_verified:
                    flash(f"✅ VAT номер підтверджено: {vat_result.get('name', company_name)}", "success")
                    # Оновлюємо дані з VIES якщо є
                    if vat_result.get("name") and not legal_name:
                        legal_name = vat_result.get("name")
                    if vat_result.get("address") and not address:
                        address = vat_result.get("address")
                else:
                    flash(f"⚠️ VAT номер не підтверджено: {vat_result.get('error', 'невідома помилка')}", "warning")
        
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("auth/register_b2b.html", vat_result=vat_result)
        
        # Створення компанії
        company = Company(
            name=company_name,
            legal_name=legal_name or company_name,
            vat_number=vat_number or None,
            vat_country=vat_country or None,
            vat_verified=vat_verified,
            vat_verified_at=datetime.utcnow() if vat_verified else None,
            vat_data=vat_result if vat_result else None,
            address=address or None,
            city=city or None,
            postal_code=postal_code or None,
            country=country or None,
            website=website or None,
            contact_person=f"{first_name} {last_name}",
            contact_email=email,
            contact_phone=phone or None,
            status=CompanyStatus.VERIFIED.value if (settings.b2b_auto_approve and vat_verified) else CompanyStatus.PENDING.value,
        )
        
        # Витягуємо домен з website
        if website:
            import re
            domain_match = re.search(r'(?:https?://)?(?:www\.)?([^/]+)', website)
            if domain_match:
                company.domain = domain_match.group(1)
        
        db.session.add(company)
        db.session.flush()  # Отримуємо ID
        
        # Логуємо перевірку VAT
        if vat_result:
            VerificationLog.log_check(
                company_id=company.id,
                check_type="vat",
                status="success" if vat_verified else "failed",
                is_valid=vat_verified,
                request_data={"vat_number": vat_number, "country": vat_country},
                response_data=vat_result,
                error_message=vat_result.get("error") if not vat_verified else None,
            )
        
        # Створення користувача
        user = User(
            email=email,
            role=UserRole.PARTNER.value,
            first_name=first_name,
            last_name=last_name,
            phone=phone or None,
            company_id=company.id,
            is_verified=vat_verified,  # Якщо VAT підтверджено - верифікуємо і юзера
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        # Логін
        login_user(user)
        
        if company.is_verified:
            flash("✅ Реєстрація успішна! Ваша компанія верифікована, ви можете робити замовлення.", "success")
        else:
            flash("📋 Реєстрація успішна! Ваша заявка на розгляді. Ми повідомимо вас після верифікації.", "info")
        
        return redirect(url_for("cabinet.dashboard"))
    
    return render_template("auth/register_b2b.html", vat_result=vat_result)


@auth_bp.route("/check-vat", methods=["POST"])
def check_vat():
    """AJAX перевірка VAT номера."""
    from flask import jsonify
    
    vat_number = request.form.get("vat_number", "").strip()
    vat_country = request.form.get("vat_country", "").strip().upper()
    
    if not vat_number:
        return jsonify({"error": "VAT номер обов'язковий"}), 400
    
    result = check_vat_number(vat_number, vat_country if vat_country else None)
    return jsonify(result)
