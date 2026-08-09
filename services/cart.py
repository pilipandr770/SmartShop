"""
Кошик зберігається в сесії (session["cart"] = {product_id_str: quantity}).

Раніше жили як closures всередині create_app() (app.py) - винесено сюди,
щоб routes/cart.py і routes/checkout.py могли їх імпортувати без
циклічного імпорту з app.py, а app.py власний context_processor
cart_context() (лишається в app.py - він глобальний, як і три інші поруч)
міг далі рахувати cart_count тим самим кодом.
"""
from flask import session


def get_cart():
    """Отримати кошик з сесії."""
    return session.get("cart", {})


def save_cart(cart):
    """Зберегти кошик у сесію."""
    session["cart"] = cart
    session.modified = True
