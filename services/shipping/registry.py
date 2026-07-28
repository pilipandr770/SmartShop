"""
Фабрика провайдерів доставки: бере активні CarrierAccount магазину і
повертає готові до використання екземпляри ShippingProvider.

Магазин, що не налаштував жодного перевізника, отримує порожній список -
це навмисний "opt-in" фолбек: checkout для такого магазину продовжує
працювати так само, як і до впровадження цієї фічі (без кроку вибору
доставки, shipping_cost=0).
"""
from models.shipping import CarrierAccount, Carrier
from .test_provider import TestShippingProvider
from .dhl_provider import DHLProvider
from .ups_provider import UPSProvider

_PROVIDER_CLASSES = {
    Carrier.DHL: DHLProvider,
    Carrier.UPS: UPSProvider,
}


def build_provider(account: CarrierAccount):
    """Створює ShippingProvider для одного CarrierAccount."""
    if account.is_test_mode:
        return TestShippingProvider(account.credentials, account.is_sandbox, carrier_name=account.carrier)

    provider_cls = _PROVIDER_CLASSES.get(account.carrier)
    if provider_cls is None:
        return None
    return provider_cls(account.credentials, account.is_sandbox)


def get_enabled_providers(store_id):
    """Повертає [(CarrierAccount, ShippingProvider), ...] для активних акаунтів магазину."""
    accounts = CarrierAccount.get_enabled_for_store(store_id)
    result = []
    for account in accounts:
        provider = build_provider(account)
        if provider is not None:
            result.append((account, provider))
    return result


def get_provider_for_carrier(store_id, carrier_code):
    """Повертає (CarrierAccount, ShippingProvider) для конкретного carrier магазину, або (None, None)."""
    account = CarrierAccount.query.filter_by(store_id=store_id, carrier=carrier_code, is_enabled=True).first()
    if account is None:
        return None, None
    return account, build_provider(account)
