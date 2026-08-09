"""
Реальний вхід/реєстрація/вихід для всіх ролей (customer/B2B partner/store
owner) - єдина точка автентифікації в системі, включно з другим фактором
(TOTP 2FA) для власників магазину. Також підтвердження email і скидання
пароля за токеном.

НЕ плутати з routes/auth.py (blueprint "auth", url_prefix "/auth") - той
лишає лише /auth/check-vat (AJAX з форми B2B-реєстрації); його docstring
детально пояснює, чому колишній дублікат /auth/login був видалений
2026-08-08 (він обходив 2FA).

Винесено з app.py ("AUTH: ВХІД/РЕЄСТРАЦІЯ B2C/B2B") як частина Phase 2
плану (SWOT 2026-08-08) - найчутливіший до безпеки розділ з усіх, що
виносились цієї сесії, тому логіка перенесена без жодної зміни поведінки,
лише мінімальні правки для роботи як blueprint (url_for на самих себе
стали відносними ".назва", app.logger -> current_app.logger).
"""
from datetime import datetime

from flask import Blueprint, current_app, g, redirect, render_template, request, session, url_for, flash
from flask_babel import gettext as _, get_locale
from flask_login import current_user, login_required

from extensions import db, limiter
from models.settings import SiteSettings
from models.user import User, UserRole
from models.company import Company, CompanyStatus

user_auth_bp = Blueprint("user_auth", __name__)


def _send_verification_email_for(user, locale=None):
    from services.email_service import send_verification_email_for_user
    send_verification_email_for_user(user, locale=locale)


@user_auth_bp.route("/verify-email/<token>")
def verify_email(token):
    """Підтвердження email за токеном з листа."""
    from services.tokens import verify_token, EMAIL_VERIFY_SALT, EMAIL_VERIFY_MAX_AGE
    email = verify_token(token, EMAIL_VERIFY_SALT, EMAIL_VERIFY_MAX_AGE)
    if not email:
        flash(_("Посилання для підтвердження email недійсне або протерміноване. Запросіть нове нижче."), "danger")
        return redirect(url_for(".resend_verification"))

    user = User.get_by_email(email)
    if not user:
        flash(_("Користувача не знайдено."), "danger")
        return redirect(url_for(".user_login"))

    if not user.is_verified:
        user.is_verified = True
        db.session.commit()
    flash(_("✅ Email підтверджено!"), "success")
    return redirect(url_for("user_cabinet") if current_user.is_authenticated else url_for(".user_login"))


@user_auth_bp.route("/resend-verification", methods=["GET", "POST"])
@limiter.limit("5 per minute;15 per hour")
def resend_verification():
    """Повторне надсилання листа підтвердження email."""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.get_by_email(email)
        # Однакове повідомлення незалежно від того, чи існує акаунт -
        # щоб не давати змогу перебором дізнатись, які email зареєстровані.
        if user and not user.is_verified:
            _send_verification_email_for(user, locale=str(get_locale()))
        flash(_("Якщо цей email зареєстровано і ще не підтверджено, ми надіслали новий лист."), "info")
        return redirect(url_for(".user_login"))
    settings = SiteSettings.get_or_create(g.store.id)
    return render_template("auth/resend_verification.html", settings=settings)


@user_auth_bp.route("/reset-password", methods=["GET", "POST"])
@limiter.limit("5 per minute;15 per hour")
def reset_password_request():
    """Форма запиту скидання пароля - вводиться email."""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.get_by_email(email)
        if user:
            from services.tokens import generate_token, PASSWORD_RESET_SALT
            token = generate_token(user.email, PASSWORD_RESET_SALT)
            reset_url = url_for(".reset_password", token=token, _external=True)
            try:
                from services.email_service import send_password_reset_email
                send_password_reset_email(user.email, user.full_name, reset_url, locale=str(get_locale()))
            except Exception as e:
                current_app.logger.error(f'Failed to send password reset email: {str(e)}')
        # Однакове повідомлення незалежно від існування акаунта -
        # захист від User enumeration через цю форму.
        flash(_("Якщо цей email зареєстровано, ми надіслали посилання для скидання пароля."), "info")
        return redirect(url_for(".user_login"))
    settings = SiteSettings.get_or_create(g.store.id)
    return render_template("auth/reset_password_request.html", settings=settings)


@user_auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
@limiter.limit("10 per minute;30 per hour")
def reset_password(token):
    """Встановлення нового пароля за токеном з листа."""
    from services.tokens import verify_token, PASSWORD_RESET_SALT, PASSWORD_RESET_MAX_AGE
    email = verify_token(token, PASSWORD_RESET_SALT, PASSWORD_RESET_MAX_AGE)
    if not email:
        flash(_("Посилання для скидання пароля недійсне або протерміноване. Запросіть нове."), "danger")
        return redirect(url_for(".reset_password_request"))

    user = User.get_by_email(email)
    if not user:
        flash(_("Користувача не знайдено."), "danger")
        return redirect(url_for(".reset_password_request"))

    settings = SiteSettings.get_or_create(g.store.id)

    if request.method == "POST":
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")
        if not password or len(password) < 6:
            flash(_("Пароль має бути не менше 6 символів"), "danger")
            return render_template("auth/reset_password.html", token=token, settings=settings)
        if password != password_confirm:
            flash(_("Паролі не співпадають"), "danger")
            return render_template("auth/reset_password.html", token=token, settings=settings)

        user.set_password(password)
        db.session.commit()
        flash(_("✅ Пароль оновлено! Тепер ви можете увійти."), "success")
        return redirect(url_for(".user_login"))

    return render_template("auth/reset_password.html", token=token, settings=settings)


@user_auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("15 per minute;50 per hour")
def user_login():
    """Сторінка входу для користувачів."""
    if current_user.is_authenticated:
        if current_user.is_platform_owner:
            return redirect(url_for("platform_admin.dashboard"))
        if current_user.is_b2b:
            return redirect(url_for("b2b_dashboard"))
        return redirect(url_for("user_cabinet"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        remember = request.form.get("remember") == "on"

        user = User.get_by_email(email)

        if user and user.check_password(password):
            if not user.is_active:
                flash(_("Ваш акаунт деактивовано. Зверніться до підтримки."), "danger")
                return render_template("auth/login.html")

            if user.totp_enabled:
                # Пароль правильний, але потрібен ще другий фактор - НЕ
                # логінимо користувача одразу, а лишаємо "відкладений" вхід
                # у сесії до підтвердження коду на окремій сторінці.
                session["2fa_pending_user_id"] = user.id
                session["2fa_remember"] = remember
                session["2fa_next"] = request.args.get("next") or ""
                return redirect(url_for(".login_2fa"))

            from flask_login import login_user as flask_login_user
            flask_login_user(user, remember=remember)
            user.update_last_login()

            flash(_("Вітаємо, %(name)s!") % {"name": user.full_name}, "success")

            next_page = request.args.get("next")
            if next_page:
                return redirect(next_page)

            if user.is_platform_owner:
                return redirect(url_for("platform_admin.dashboard"))
            elif user.is_admin or user.is_manager:
                return redirect(url_for("dashboard.admin_dashboard"))
            elif user.is_b2b:
                return redirect(url_for("b2b_dashboard"))

            return redirect(url_for("user_cabinet"))

        flash(_("Невірний email або пароль."), "danger")

    settings = SiteSettings.get_or_create(g.store.id)
    return render_template("auth/login.html", settings=settings)


@user_auth_bp.route("/login/2fa", methods=["GET", "POST"])
@limiter.limit("10 per minute;30 per hour")
def login_2fa():
    """Другий крок входу для користувачів з увімкненою 2FA - доступний
    лише одразу після успішної перевірки пароля (позначено в сесії
    user_login()), не є самостійною точкою входу."""
    pending_user_id = session.get("2fa_pending_user_id")
    if not pending_user_id:
        return redirect(url_for(".user_login"))

    user = User.query.get(pending_user_id)
    if not user:
        session.pop("2fa_pending_user_id", None)
        return redirect(url_for(".user_login"))

    if request.method == "POST":
        code = request.form.get("code", "").strip()
        use_backup = request.form.get("use_backup") == "on"

        verified = user.verify_backup_code(code) if use_backup else user.verify_totp_code(code)
        if verified:
            if use_backup:
                db.session.commit()  # позначити резервний код використаним

            remember = session.pop("2fa_remember", False)
            next_page = session.pop("2fa_next", "") or None
            session.pop("2fa_pending_user_id", None)

            from flask_login import login_user as flask_login_user
            flask_login_user(user, remember=remember)
            user.update_last_login()

            flash(_("Вітаємо, %(name)s!") % {"name": user.full_name}, "success")

            if next_page:
                return redirect(next_page)
            if user.is_platform_owner:
                return redirect(url_for("platform_admin.dashboard"))
            elif user.is_admin or user.is_manager:
                return redirect(url_for("dashboard.admin_dashboard"))
            elif user.is_b2b:
                return redirect(url_for("b2b_dashboard"))
            return redirect(url_for("user_cabinet"))

        flash(_("Невірний код. Спробуйте ще раз."), "danger")

    return render_template("auth/login_2fa.html")


@user_auth_bp.route("/logout")
@login_required
def user_logout():
    """Вихід з системи."""
    from flask_login import logout_user as flask_logout_user
    flask_logout_user()
    flash(_("Ви успішно вийшли з системи."), "info")
    return redirect(url_for(".user_login"))


@user_auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per minute;30 per hour")
def user_register():
    """Реєстрація B2C клієнта."""
    if current_user.is_authenticated:
        return redirect(url_for("user_cabinet"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        phone = request.form.get("phone", "").strip()

        errors = []

        if not email:
            errors.append(_("Email обов'язковий"))
        elif User.get_by_email(email):
            errors.append(_("Користувач з таким email вже існує"))

        if not password:
            errors.append(_("Пароль обов'язковий"))
        elif len(password) < 6:
            errors.append(_("Пароль має бути не менше 6 символів"))
        elif password != password_confirm:
            errors.append(_("Паролі не співпадають"))

        if errors:
            for error in errors:
                flash(error, "danger")
            settings = SiteSettings.get_or_create(g.store.id)
            return render_template("auth/register.html", settings=settings)

        user = User.create_user(
            email=email,
            password=password,
            role=UserRole.CUSTOMER,
            first_name=first_name or None,
            last_name=last_name or None,
            phone=phone or None,
            store_id=g.store.id,
        )

        # Відправити welcome email
        try:
            from services.email_service import send_registration_email
            user_name = f"{first_name} {last_name}".strip() or "Клієнт"
            send_registration_email(email, user_name, locale=str(get_locale()))
            current_app.logger.info(f'Registration email sent to {email}')
        except Exception as e:
            current_app.logger.error(f'Failed to send registration email: {str(e)}')

        _send_verification_email_for(user, locale=str(get_locale()))

        from flask_login import login_user as flask_login_user
        flask_login_user(user)
        flash(_("Реєстрація успішна! Ласкаво просимо!"), "success")
        return redirect(url_for("user_cabinet"))

    settings = SiteSettings.get_or_create(g.store.id)
    return render_template("auth/register.html", settings=settings)


@user_auth_bp.route("/register/b2b", methods=["GET", "POST"])
@limiter.limit("10 per minute;30 per hour")
def user_register_b2b():
    """Реєстрація B2B партнера."""
    if current_user.is_authenticated:
        return redirect(url_for("b2b_dashboard"))

    settings = SiteSettings.get_or_create(g.store.id)
    if not getattr(settings, 'b2b_registration_open', True):
        flash(_("B2B реєстрація тимчасово закрита."), "warning")
        return redirect(url_for(".user_login"))

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
        vat_number = request.form.get("vat_number", "").strip()
        country = request.form.get("country", "").strip()
        address = request.form.get("address", "").strip()
        city = request.form.get("city", "").strip()
        website = request.form.get("website", "").strip()

        # Валідація
        errors = []

        if not email:
            errors.append(_("Email обов'язковий"))
        elif User.get_by_email(email):
            errors.append(_("Користувач з таким email вже існує"))

        if not password:
            errors.append(_("Пароль обов'язковий"))
        elif len(password) < 8:
            errors.append(_("Пароль має бути не менше 8 символів"))
        elif password != password_confirm:
            errors.append(_("Паролі не співпадають"))

        if not company_name:
            errors.append(_("Назва компанії обов'язкова"))

        if not first_name or not last_name:
            errors.append(_("Ім'я та прізвище контактної особи обов'язкові"))

        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("auth/register_b2b.html", settings=settings)

        # Перевірка VAT (опціонально)
        vat_verified = False
        vat_data = None
        if vat_number:
            try:
                from services.vat_checker import VATChecker
                checker = VATChecker()
                vat_result = checker.check_vat(vat_number)
                vat_verified = vat_result.get("valid", False)
                vat_data = vat_result
                if vat_verified:
                    flash(_("✅ VAT номер підтверджено!"), "success")
                else:
                    flash(_("⚠️ VAT не підтверджено: %(error)s") % {"error": vat_result.get('error', '')}, "warning")
            except Exception as e:
                flash(_("⚠️ Помилка перевірки VAT: %(error)s") % {"error": str(e)}, "warning")

        # Створення компанії
        company = Company(
            store_id=g.store.id,
            name=company_name,
            vat_number=vat_number or None,
            vat_country=country[:2].upper() if country else None,
            vat_verified=vat_verified,
            vat_verified_at=datetime.utcnow() if vat_verified else None,
            vat_data=vat_data,
            address=address or None,
            city=city or None,
            country=country or None,
            website=website or None,
            contact_person=f"{first_name} {last_name}",
            contact_email=email,
            contact_phone=phone or None,
            status=CompanyStatus.VERIFIED.value if (getattr(settings, 'b2b_auto_approve', False) and vat_verified) else CompanyStatus.PENDING.value,
        )
        db.session.add(company)
        db.session.flush()

        # Створення користувача
        user = User(
            email=email,
            role=UserRole.PARTNER.value,
            first_name=first_name,
            last_name=last_name,
            phone=phone or None,
            company_id=company.id,
            store_id=g.store.id,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        # Відправити email залежно від статусу
        reg_locale = str(get_locale())
        try:
            from services.email_service import send_b2b_verification_pending, send_b2b_verification_approved
            if company.is_verified:
                send_b2b_verification_approved(email, company_name, company.discount_percent or 0, locale=reg_locale)
                current_app.logger.info(f'B2B approval email sent to {email}')
            else:
                send_b2b_verification_pending(email, company_name, locale=reg_locale)
                current_app.logger.info(f'B2B pending email sent to {email}')
        except Exception as e:
            current_app.logger.error(f'Failed to send B2B email: {str(e)}')

        _send_verification_email_for(user, reg_locale)

        from flask_login import login_user as flask_login_user
        flask_login_user(user)

        if company.is_verified:
            flash(_("✅ Реєстрація успішна! Ваша компанія верифікована."), "success")
        else:
            flash(_("📋 Реєстрація успішна! Ваша заявка на розгляді."), "info")

        return redirect(url_for("b2b_dashboard"))

    return render_template("auth/register_b2b.html", settings=settings)
