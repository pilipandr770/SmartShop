"""Мінімальна перевірка, що застосунок піднімається проти тестової схеми
і базові сторінки віддають 200."""


def test_app_boots(app):
    assert app is not None


def test_default_store_created(default_store):
    assert default_store.slug
    assert default_store.is_active


def test_shop_page_loads(client, default_store):
    resp = client.get("/shop", headers={"Host": f"{default_store.slug}.localhost"})
    assert resp.status_code == 200


def test_login_page_loads(client, default_store):
    resp = client.get("/login", headers={"Host": f"{default_store.slug}.localhost"})
    assert resp.status_code == 200
