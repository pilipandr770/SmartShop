"""
Маршрути авторизації.

Реальні login/register/logout живуть у app.py (/login, /register,
/register/b2b) - там же й повна логіка редіректу за роллю та перевірка
TOTP 2FA. Цей blueprint раніше мав власні ПОВНІ дублікати цих маршрутів
під /auth/* "для зворотної сумісності зі старими закладками" - вони були
видалені 2026-08-08: дублікат /auth/login НЕ перевіряв 2FA, тобто був
робочим способом обійти двофакторну автентифікацію для будь-якого
акаунта. Жоден шаблон і жоден внутрішній redirect на них не посилався.

Єдине, що тут лишається - /auth/check-vat, яке реально викликається AJAX
з templates/auth/register_b2b.html.
"""
from flask import Blueprint, request, jsonify
from services.vat_checker import check_vat_number

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/check-vat", methods=["POST"])
def check_vat():
    """AJAX перевірка VAT номера (викликається з форми реєстрації B2B)."""
    vat_number = request.form.get("vat_number", "").strip()
    vat_country = request.form.get("vat_country", "").strip().upper()

    if not vat_number:
        return jsonify({"error": "VAT номер обов'язковий"}), 400

    result = check_vat_number(vat_number, vat_country if vat_country else None)
    return jsonify(result)
