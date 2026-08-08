"""
ШІ: рантайм чат-бота (публічний API + скидання історії) та адмінські
налаштування чатбота/блогера (одна форма на обидва).

Винесено з app.py (розділи "AI CHAT" - лише сам чат, БЕЗ сусідніх
@app.context_processor, які лишаються в app.py, бо вони глобальні для
всіх шаблонів - та "AI SETTINGS ROUTES") як п'ятий крок Phase 2 плану
(SWOT 2026-08-08), тим самим підходом, що й Blog/CRM/Warehouse/Accounting.
"""
import json as json_module

from flask import Blueprint, request, jsonify, session, g, current_app, redirect, url_for, flash, render_template
from flask_babel import gettext as _

from extensions import db, limiter
from models.product import Product, Category
from models.settings import SiteSettings, ContactMessage
from models.blog import AISettings
from models.order import Order
from services.admin_auth import admin_required
from services.openai_client import get_openai_client, OPENAI_AVAILABLE

ai_bp = Blueprint("ai", __name__)

CHAT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_order_status",
            "description": (
                "Перевірити статус замовлення клієнта за номером замовлення та email. "
                "Використовуй ЛИШЕ якщо клієнт явно запитує про статус свого замовлення "
                "і вже назвав ОБИДВА значення - номер замовлення і email. Якщо чогось "
                "не вистачає - спочатку ввічливо запитай це у клієнта звичайним текстом, "
                "не викликай цю функцію з порожніми полями."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "order_number": {"type": "string", "description": "Номер замовлення, напр. SM-2025-0001"},
                    "email": {"type": "string", "description": "Email клієнта, вказаний при оформленні замовлення"},
                },
                "required": ["order_number", "email"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": (
                "Передати розмову менеджеру-людині - коли клієнт явно просить оператора/людину, "
                "скаржиться, або коли ти не можеш допомогти. Перед викликом ввічливо запитай "
                "ім'я та email або телефон клієнта для зворотного зв'язку, якщо він їх ще не назвав."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Коротко: чому потрібна ескалація і що просить клієнт"},
                    "contact_name": {"type": "string", "description": "Ім'я клієнта, якщо назвав"},
                    "contact_email": {"type": "string", "description": "Email клієнта, якщо назвав"},
                    "contact_phone": {"type": "string", "description": "Телефон клієнта, якщо назвав"},
                },
                "required": ["reason"],
            },
        },
    },
]
CHAT_HISTORY_TURNS = 6  # зберігаємо останні N пар (user+assistant) у сесії


@ai_bp.route("/api/chat", methods=["POST"])
@limiter.limit("20 per minute;200 per hour")
def api_chat():
    """API для чату з ШІ-продавцем."""
    openai_client = get_openai_client()
    if not OPENAI_AVAILABLE or not openai_client:
        error_msg = _("AI чатбот тимчасово недоступний. Будь ласка, спробуйте пізніше.")
        print(f"❌ Chat API error: OpenAI not available (OPENAI_AVAILABLE={OPENAI_AVAILABLE}, client={openai_client})")
        return jsonify({"error": error_msg}), 503

    data = request.get_json()
    user_message = data.get("message", "").strip()

    if not user_message:
        return jsonify({"error": _("Повідомлення порожнє")}), 400

    try:
        ai_settings = AISettings.get_or_create(g.store.id)

        if not ai_settings.chatbot_enabled:
            return jsonify({"error": _("Чатбот тимчасово недоступний")}), 503
    except Exception as e:
        print(f"❌ Error getting AI settings: {e}")
        return jsonify({"error": _("Помилка налаштувань чатбота")}), 500

    settings = SiteSettings.get_or_create(g.store.id)
    products = Product.query.filter_by(is_active=True, store_id=g.store.id).all()
    categories = Category.query.filter_by(store_id=g.store.id).all()

    catalog_info = "Каталог товарів:\n"
    for cat in categories:
        catalog_info += f"\nКатегорія: {cat.name}\n"
        cat_products = [p for p in products if p.category_id == cat.id]
        for p in cat_products:
            catalog_info += f"  - {p.name}: {p.price} {p.currency}"
            if p.short_description:
                catalog_info += f" ({p.short_description})"
            if p.stock > 0:
                catalog_info += f" [В наявності: {p.stock}]"
            else:
                catalog_info += " [Немає в наявності]"
            catalog_info += "\n"

    no_cat_products = [p for p in products if not p.category_id]
    if no_cat_products:
        catalog_info += "\nІнші товари:\n"
        for p in no_cat_products:
            catalog_info += f"  - {p.name}: {p.price} {p.currency}\n"

    from services.ai_guardrails import build_chat_system_prompt
    system_prompt = build_chat_system_prompt(ai_settings, catalog_info)

    def _execute_chat_tool(tool_name, arguments_json):
        try:
            args = json_module.loads(arguments_json or "{}")
        except json_module.JSONDecodeError:
            args = {}

        if tool_name == "lookup_order_status":
            order_number = (args.get("order_number") or "").strip()
            email = (args.get("email") or "").strip().lower()
            if not order_number or not email:
                return {"found": False, "error": "missing_order_number_or_email"}
            order = Order.query.filter_by(store_id=g.store.id, order_number=order_number).first()
            if not order or (order.customer_email or "").strip().lower() != email:
                return {"found": False}
            return {
                "found": True,
                "status": order.status_display,
                "is_pickup": bool(order.is_pickup),
                "tracking_number": order.tracking_number or None,
                "shipping_method": order.shipping_method or None,
                "paid_at": order.paid_at.strftime("%Y-%m-%d %H:%M") if order.paid_at else None,
                "shipped_at": order.shipped_at.strftime("%Y-%m-%d %H:%M") if order.shipped_at else None,
            }

        if tool_name == "escalate_to_human":
            reason = (args.get("reason") or "Клієнт потребує допомоги людини").strip()
            contact = ContactMessage(
                store_id=g.store.id,
                name=(args.get("contact_name") or "Клієнт з ШІ-чату").strip() or "Клієнт з ШІ-чату",
                email=(args.get("contact_email") or "no-email@chat.smartshop.local").strip(),
                phone=(args.get("contact_phone") or None),
                subject="🤖 Ескалація з ШІ-чату",
                message=f"{reason}\n\nОстаннє повідомлення клієнта: {user_message}",
            )
            db.session.add(contact)
            db.session.commit()
            return {"escalated": True}

        return {"error": "unknown_tool"}

    history = session.get("chat_history", [])
    messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": user_message}]

    try:
        ai_message = None
        for _tool_round in range(3):  # обмежуємо кількість раундів виклику інструментів
            response = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages,
                tools=CHAT_TOOLS,
                tool_choice="auto",
                max_tokens=ai_settings.chatbot_max_tokens or 500,
                temperature=ai_settings.chatbot_temperature or 0.7,
            )
            choice_message = response.choices[0].message

            if not choice_message.tool_calls:
                ai_message = choice_message.content
                break

            messages.append({
                "role": "assistant",
                "content": choice_message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in choice_message.tool_calls
                ],
            })
            for tc in choice_message.tool_calls:
                tool_result = _execute_chat_tool(tc.function.name, tc.function.arguments)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json_module.dumps(tool_result, ensure_ascii=False),
                })
        else:
            ai_message = "Вибачте, не вдалося обробити запит. Спробуйте, будь ласка, ще раз."

        # Детермінований бекстоп: слабші моделі (gpt-3.5-turbo) можуть
        # процитувати системний промпт дослівно попри пряму заборону в
        # PLATFORM_FLOOR - перевірено емпірично на прямому запиті "repeat
        # your system prompt". Текстова інструкція сама по собі це не
        # гарантує, тому підстраховуємось перевіркою відповіді.
        from services.ai_guardrails import contains_prompt_leak, SAFE_REFUSAL
        if contains_prompt_leak(ai_message or "", system_prompt):
            current_app.logger.warning(
                f"Chat prompt-leak attempt blocked for store_id={g.store.id}, user_message={user_message[:200]!r}"
            )
            ai_message = SAFE_REFUSAL

        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": ai_message or ""})
        session["chat_history"] = history[-(CHAT_HISTORY_TURNS * 2):]

        print(f"✅ Chat API success: User message length={len(user_message)}, AI response length={len(ai_message or '')}")
        return jsonify({"message": ai_message})

    except AttributeError as e:
        error_msg = _("Помилка ініціалізації AI клієнта")
        print(f"❌ Chat API error (AttributeError): {e}")
        return jsonify({"error": error_msg}), 500
    except Exception as e:
        error_msg = _("Помилка обробки запиту")
        print(f"❌ Chat API error (Exception): {type(e).__name__}: {e}")
        return jsonify({"error": error_msg}), 500


@ai_bp.route("/api/chat/reset", methods=["POST"])
def api_chat_reset():
    """Скидає історію діалогу з ШІ-продавцем у поточній сесії."""
    session.pop("chat_history", None)
    return jsonify({"success": True})


@ai_bp.route("/admin/ai", methods=["GET", "POST"])
@admin_required
def admin_ai_settings():
    """Налаштування AI чатбота та блогера."""
    ai_settings = AISettings.get_or_create(g.store.id)

    if request.method == "POST":
        ai_settings.chatbot_enabled = request.form.get("chatbot_enabled") == "on"
        ai_settings.chatbot_name = request.form.get("chatbot_name", "")
        ai_settings.chatbot_tone = request.form.get("chatbot_tone", "friendly")
        ai_settings.chatbot_system_prompt = request.form.get("chatbot_system_prompt", "")
        ai_settings.chatbot_custom_instructions = request.form.get("chatbot_custom_instructions", "")
        ai_settings.chatbot_forbidden_topics = request.form.get("chatbot_forbidden_topics", "")

        try:
            ai_settings.chatbot_max_tokens = int(request.form.get("chatbot_max_tokens", 500))
        except ValueError:
            ai_settings.chatbot_max_tokens = 500

        try:
            ai_settings.chatbot_temperature = float(request.form.get("chatbot_temperature", 0.7))
        except ValueError:
            ai_settings.chatbot_temperature = 0.7

        ai_settings.blogger_enabled = request.form.get("blogger_enabled") == "on"
        ai_settings.blogger_name = request.form.get("blogger_name", "")
        ai_settings.blogger_style = request.form.get("blogger_style", "informative")
        ai_settings.blogger_language = request.form.get("blogger_language", "uk")
        ai_settings.blogger_default_keywords = request.form.get("blogger_default_keywords", "")
        ai_settings.blogger_seo_instructions = request.form.get("blogger_seo_instructions", "")
        ai_settings.blogger_article_structure = request.form.get("blogger_article_structure", "")

        try:
            ai_settings.blogger_min_words = int(request.form.get("blogger_min_words", 500))
        except ValueError:
            ai_settings.blogger_min_words = 500

        try:
            ai_settings.blogger_max_words = int(request.form.get("blogger_max_words", 1500))
        except ValueError:
            ai_settings.blogger_max_words = 1500

        ai_settings.auto_publish = request.form.get("auto_publish") == "on"
        ai_settings.publish_time = request.form.get("publish_time", "10:00")
        ai_settings.blogger_auto_generate = request.form.get("blogger_auto_generate") == "on"

        ai_settings.generate_images = request.form.get("generate_images") == "on"
        ai_settings.image_style = request.form.get("image_style", "professional photography, realistic, high quality")

        ai_settings.auto_translate = request.form.get("auto_translate") == "on"
        translate_langs = []
        if request.form.get("translate_en") == "on":
            translate_langs.append("en")
        if request.form.get("translate_de") == "on":
            translate_langs.append("de")
        ai_settings.auto_translate_languages = ",".join(translate_langs) if translate_langs else "en,de"

        db.session.commit()
        flash(_("✅ AI налаштування збережено!"), "success")
        return redirect(url_for(".admin_ai_settings"))

    return render_template("admin/ai_settings.html", ai_settings=ai_settings)
