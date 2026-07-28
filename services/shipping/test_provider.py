"""
Тестовий провайдер доставки - без мережевих викликів, детерміновані тарифи
й лейбли. Використовується, коли CarrierAccount.is_test_mode == True
(sandbox + креденшели-заглушки "test"), щоб можна було перевірити весь
checkout-флоу без реальних ключів DHL/UPS.
"""
import uuid
from .base import ShippingProvider, RateOption, ShipmentResult


class TestShippingProvider(ShippingProvider):
    """Синтетичні тарифи/лейбли - без мережі, для розробки й перевірки flow."""

    def __init__(self, credentials=None, is_sandbox=True, carrier_name="test"):
        super().__init__(credentials, is_sandbox)
        self.carrier_name = carrier_name

    def get_rates(self, origin, destination, weight_kg):
        weight_kg = weight_kg or 1.0
        base = 4.5 if self.carrier_name == "dhl" else 5.0
        return [
            RateOption(
                service_code="STANDARD",
                name=f"{self.carrier_name.upper()} Standard (test)",
                price=round(base + weight_kg * 1.2, 2),
                currency="EUR",
                eta_days=4,
            ),
            RateOption(
                service_code="EXPRESS",
                name=f"{self.carrier_name.upper()} Express (test)",
                price=round(base * 2.5 + weight_kg * 1.8, 2),
                currency="EUR",
                eta_days=1,
            ),
        ]

    def create_shipment(self, origin, destination, weight_kg, service_code, reference):
        fake_tracking = f"TEST{uuid.uuid4().hex[:10].upper()}"
        return ShipmentResult(
            tracking_number=fake_tracking,
            label_url=f"/static/test-labels/{fake_tracking}.txt",
            carrier_shipment_id=fake_tracking,
        )
