"""
Загальні налаштування сайту: дизайн вітрини, зображення (лого/фавікон/
банер/фото "Про нас"), контакти, соцмережі, SEO, аналітика, дані
юрособи власника, логін/пароль адміністратора, юридичні тексти.

Винесено з app.py ("АДМІНКА: НАЛАШТУВАННЯ САЙТУ") як частина Phase 2
плану (SWOT 2026-08-08).
"""
from flask import Blueprint, g, redirect, render_template, request, url_for, flash
from flask_babel import gettext as _
from werkzeug.security import generate_password_hash

from extensions import db
from models.settings import SiteSettings
from services.admin_auth import admin_required
from services.image_storage import delete_old_image
from services.theme_presets import (
    THEME_PRESETS, FONT_PRESETS, HOMEPAGE_LAYOUTS, FONT_SIZE_PRESETS,
    is_valid_hex_color,
)

site_settings_bp = Blueprint("site_settings", __name__)


@site_settings_bp.route("/admin/settings", methods=["GET", "POST"])
@admin_required
def admin_settings():
    """Глобальні налаштування сайту."""
    settings = SiteSettings.get_or_create(g.store.id)

    if request.method == "POST":
        # Основні
        settings.site_name = request.form.get("site_name") or None
        settings.site_tagline = request.form.get("site_tagline") or None

        # Дизайн вітрини - валідуємо проти фіксованого набору пресетів,
        # ніколи не приймаємо довільне значення від форми.
        posted_theme = request.form.get("theme_preset", "")
        if posted_theme in THEME_PRESETS:
            settings.theme_preset = posted_theme
        posted_font = request.form.get("font_preset", "")
        if posted_font in FONT_PRESETS:
            settings.font_preset = posted_font
        posted_layout = request.form.get("homepage_layout", "")
        if posted_layout in HOMEPAGE_LAYOUTS:
            settings.homepage_layout = posted_layout
        posted_font_size = request.form.get("font_size_preset", "")
        if posted_font_size in FONT_SIZE_PRESETS:
            settings.font_size_preset = posted_font_size
        # Довільний колір приймаємо лише якщо це строго hex-формат -
        # інакше значення потрапило б прямо у <style> в base.html.
        posted_accent = request.form.get("accent_color", "").strip()
        if not posted_accent:
            settings.accent_color = None
        elif is_valid_hex_color(posted_accent):
            settings.accent_color = posted_accent

        # Зображення (лого/фавікон/банер/фото "Про нас") - видаляємо старе
        # завантажене зображення з БД, якщо власник замінив його на нове.
        # Одна й та сама картинка теоретично може бути використана одразу
        # в кількох полях - не видаляємо її, поки хоч одне поле все ще
        # на неї посилається після збереження.
        image_fields = ("logo_url", "favicon_url", "hero_image_url", "about_image_url")
        new_image_values = {f: request.form.get(f, "").strip() or None for f in image_fields}
        for image_field in image_fields:
            new_url = new_image_values[image_field]
            old_url = getattr(settings, image_field)
            if new_url != old_url and old_url and old_url not in new_image_values.values():
                delete_old_image(old_url)
            setattr(settings, image_field, new_url)

        # Контакти
        settings.contact_email = request.form.get("contact_email") or None
        settings.contact_phone = request.form.get("contact_phone") or None
        settings.contact_address = request.form.get("contact_address") or None
        settings.working_hours = request.form.get("working_hours") or None
        settings.google_maps_url = request.form.get("google_maps_url") or None

        # Соцмережі
        settings.social_telegram = request.form.get("social_telegram") or None
        settings.social_whatsapp = request.form.get("social_whatsapp") or None
        settings.social_instagram = request.form.get("social_instagram") or None
        settings.social_facebook = request.form.get("social_facebook") or None
        settings.social_youtube = request.form.get("social_youtube") or None
        settings.social_tiktok = request.form.get("social_tiktok") or None

        # SEO
        settings.meta_title = request.form.get("meta_title") or None
        settings.meta_description = request.form.get("meta_description") or None
        settings.meta_keywords = request.form.get("meta_keywords") or None

        # Аналітика
        settings.google_analytics_id = request.form.get("google_analytics_id") or None
        settings.facebook_pixel_id = request.form.get("facebook_pixel_id") or None
        settings.custom_head_code = request.form.get("custom_head_code") or None

        # Магазин
        settings.default_currency = request.form.get("default_currency") or "EUR"
        try:
            settings.products_per_page = int(request.form.get("products_per_page", 12))
        except ValueError:
            settings.products_per_page = 12
        try:
            settings.min_order_amount = float(request.form.get("min_order_amount", 0))
        except ValueError:
            settings.min_order_amount = 0.0
        settings.shipping_info = request.form.get("shipping_info") or None

        # ========== АДМІНІСТРАТОР ==========
        # Логін
        new_username = request.form.get("admin_username", "").strip()
        if new_username and len(new_username) >= 3:
            settings.admin_username = new_username

        # Пароль (тільки якщо заповнено і співпадає)
        new_password = request.form.get("admin_password", "")
        confirm_password = request.form.get("admin_password_confirm", "")
        if new_password:
            if len(new_password) < 6:
                flash(_("Пароль має бути мінімум 6 символів."), "warning")
            elif new_password != confirm_password:
                flash(_("Паролі не співпадають."), "warning")
            else:
                settings.admin_password_hash = generate_password_hash(new_password)
                flash(_("Пароль адміністратора змінено."), "success")

        # Дані юрособи адміністратора
        settings.admin_company_name = request.form.get("admin_company_name") or None
        settings.admin_company_legal_name = request.form.get("admin_company_legal_name") or None
        settings.admin_vat_number = request.form.get("admin_vat_number") or None
        settings.admin_vat_country = request.form.get("admin_vat_country") or None
        settings.admin_company_address = request.form.get("admin_company_address") or None
        settings.admin_company_city = request.form.get("admin_company_city") or None
        settings.admin_company_postal_code = request.form.get("admin_company_postal_code") or None
        settings.admin_company_country = request.form.get("admin_company_country") or None
        settings.admin_company_country_code = (request.form.get("admin_company_country_code") or "").upper() or None
        settings.admin_handelsregister_id = request.form.get("admin_handelsregister_id") or None
        settings.admin_company_email = request.form.get("admin_company_email") or None
        settings.admin_company_phone = request.form.get("admin_company_phone") or None
        settings.admin_company_website = request.form.get("admin_company_website") or None

        # Юридичні тексти (Datenschutz/AGB) - порожнє поле повертає сторінку
        # до загального шаблонного тексту (не перезаписує його порожнечею).
        settings.privacy_policy_text = request.form.get("privacy_policy_text") or None
        settings.terms_text = request.form.get("terms_text") or None

        db.session.commit()
        flash(_("Налаштування сайту збережено."), "success")
        return redirect(url_for(".admin_settings"))

    return render_template(
        "admin/settings.html",
        settings=settings,
        theme_presets=THEME_PRESETS,
        font_presets=FONT_PRESETS,
        homepage_layouts=HOMEPAGE_LAYOUTS,
        font_size_presets=FONT_SIZE_PRESETS,
    )
