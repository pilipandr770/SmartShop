"""
Ізоляція між орендарями (Store) - найдорожчий клас багів у мультитенантному
застосунку: один пропущений store_id-фільтр може показати чи дозволити
редагувати чужі дані. Перевіряємо і публічну вітрину, і адмінські IDOR-шляхи.
"""
import pytest

from extensions import db
from models.store import Store, StoreSubscriptionStatus
from models.user import User, UserRole
from models.product import Category, Product

from .conftest import unique_email, store_host, login_as


@pytest.fixture()
def two_stores(app):
    """Два незалежні магазини, кожен зі своїм власником, категорією й товаром."""
    with app.app_context():
        stores = []
        for label in ("alpha", "beta"):
            owner = User(
                email=unique_email(f"owner-{label}"),
                role=UserRole.STORE_OWNER.value,
                first_name=label.capitalize(),
                is_verified=True,
            )
            owner.set_password("TestPass123!")
            db.session.add(owner)
            db.session.flush()

            store = Store(
                name=f"Store {label.capitalize()}",
                slug=f"tenant-{label}-{unique_email('')[:6]}",
                owner_user_id=owner.id,
                plan="starter",
                subscription_status=StoreSubscriptionStatus.ACTIVE,
            )
            db.session.add(store)
            db.session.flush()

            category = Category(store_id=store.id, name=f"Category {label}", slug=f"cat-{label}")
            db.session.add(category)
            db.session.flush()

            product = Product(
                store_id=store.id,
                category_id=category.id,
                name=f"UniqueProduct-{label.upper()}-9f3k",
                sku=f"SKU-{label}",
                price=99.0,
                stock=10,
                is_active=True,
            )
            db.session.add(product)
            db.session.commit()

            stores.append({"store": store, "owner": owner, "category": category, "product": product})

        db.session.commit()
        yield stores


def test_storefront_only_shows_own_products(client, two_stores):
    alpha, beta = two_stores
    resp = client.get("/shop", headers={"Host": store_host(alpha["store"].slug)})
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert alpha["product"].name in body
    assert beta["product"].name not in body


def test_admin_cannot_edit_other_stores_product(client, two_stores):
    """IDOR-перевірка: власник alpha не повинен мати доступ до товару beta
    навіть якщо вгадає його числовий ID."""
    alpha, beta = two_stores
    login_as(client, alpha["owner"], host=store_host(alpha["store"].slug))

    resp = client.get(
        f"/admin/products/{beta['product'].id}/edit",
        headers={"Host": store_host(alpha["store"].slug)},
    )
    assert resp.status_code == 404


def test_admin_can_edit_own_store_product(client, two_stores):
    alpha, _beta = two_stores
    login_as(client, alpha["owner"], host=store_host(alpha["store"].slug))

    resp = client.get(
        f"/admin/products/{alpha['product'].id}/edit",
        headers={"Host": store_host(alpha["store"].slug)},
    )
    assert resp.status_code == 200


def test_other_stores_owner_gets_403_not_404_on_admin_dashboard(client, two_stores):
    """На відміну від конкретного товару (де ID належить іншому магазину і
    404 приховує сам факт існування), /admin/ завжди існує для будь-якого
    магазину - тому власнику чужого магазину має повертатися 403, а не 404."""
    alpha, beta = two_stores
    # Логін під хостом alpha, щоб імітувати те, що в проді дає спільна
    # SESSION_COOKIE_DOMAIN=.<BASE_DOMAIN> - власник beta, вже залогінений
    # десь на платформі, переходить на піддомен чужого магазину alpha.
    login_as(client, beta["owner"], host=store_host(alpha["store"].slug))

    resp = client.get("/admin/", headers={"Host": store_host(alpha["store"].slug)})
    assert resp.status_code == 403
