"""
Базовий інтерфейс для служб доставки (DHL, UPS, ...).

Кожен провайдер реалізує get_rates() (тарифи для checkout) і
create_shipment() (створення відправлення + лейбл після оплати).
Обидва методи мають кидати ShippingProviderError при будь-якій помилці
(мережа, авторизація, невалідна адреса тощо) - виклики завжди обгортаються
викликаючим кодом у try/except, щоб збій перевізника ніколи не ламав
checkout чи підтвердження оплати.
"""
from dataclasses import dataclass, field


class ShippingProviderError(Exception):
    """Помилка при зверненні до API служби доставки."""
    pass


@dataclass
class RateOption:
    """Один варіант доставки, показаний покупцю в checkout."""
    service_code: str      # ідентифікатор перевізника для цього сервісу (напр. "P" для DHL Express)
    name: str               # людська назва ("DHL Express Worldwide")
    price: float
    currency: str
    eta_days: int = None    # орієнтовний термін доставки (днів), якщо перевізник повертає


@dataclass
class ShipmentResult:
    """Результат створення відправлення - те, що зберігаємо на WarehouseTask."""
    tracking_number: str
    label_url: str
    carrier_shipment_id: str = None


@dataclass
class Address:
    """Уніфікована адреса (відправник або отримувач) для запитів до перевізника."""
    name: str
    street: str
    city: str
    postal_code: str
    country_code: str  # ISO2
    phone: str = ""

    @staticmethod
    def from_dict(data):
        return Address(
            name=data.get("name", ""),
            street=data.get("street", ""),
            city=data.get("city", ""),
            postal_code=data.get("postal_code", ""),
            country_code=(data.get("country_code") or "").upper(),
            phone=data.get("phone", ""),
        )


class ShippingProvider:
    """Абстрактний інтерфейс провайдера доставки."""

    def __init__(self, credentials: dict, is_sandbox: bool = True):
        self.credentials = credentials or {}
        self.is_sandbox = is_sandbox

    def get_rates(self, origin: Address, destination: Address, weight_kg: float) -> list:
        """Повертає список RateOption для цієї пари адрес і ваги."""
        raise NotImplementedError

    def create_shipment(self, origin: Address, destination: Address, weight_kg: float,
                         service_code: str, reference: str) -> ShipmentResult:
        """Створює відправлення в перевізника, повертає трек-номер і лейбл."""
        raise NotImplementedError
