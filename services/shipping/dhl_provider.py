"""
DHL Express (MyDHL API) провайдер доставки.

Реалізовано за офіційною специфікацією MyDHL API (https://developer.dhl.com/
api-reference/dhl-express-mydhl-api). НЕ протестовано проти реального
sandbox - на момент написання в проєкті немає DHL API-ключів. Перед
використанням у production обов'язково прогнати смоук-тест з реальними
sandbox-креденшелами (developer.dhl.com -> My Apps & Keys).

Автентифікація: Basic Auth (api_key як username, api_secret як password) -
саме так MyDHL API видає доступ для тестового і продакшн середовища.
"""
import requests
from .base import ShippingProvider, RateOption, ShipmentResult, ShippingProviderError

SANDBOX_BASE_URL = "https://express.api.dhl.com/mydhlapi/test"
PRODUCTION_BASE_URL = "https://express.api.dhl.com/mydhlapi"

REQUEST_TIMEOUT = 15  # секунд


class DHLProvider(ShippingProvider):
    def __init__(self, credentials: dict, is_sandbox: bool = True):
        super().__init__(credentials, is_sandbox)
        self.api_key = (credentials or {}).get("api_key", "")
        self.api_secret = (credentials or {}).get("api_secret", "")
        self.account_number = (credentials or {}).get("account_number", "")
        self.base_url = SANDBOX_BASE_URL if is_sandbox else PRODUCTION_BASE_URL

    def _auth(self):
        return (self.api_key, self.api_secret)

    def _address_payload(self, address):
        return {
            "postalCode": address.postal_code,
            "cityName": address.city,
            "countryCode": address.country_code,
            "addressLine1": address.street,
        }

    def get_rates(self, origin, destination, weight_kg):
        weight_kg = weight_kg or 1.0
        payload = {
            "customerDetails": {
                "shipperDetails": self._address_payload(origin),
                "receiverDetails": self._address_payload(destination),
            },
            "accounts": [{"typeCode": "shipper", "number": self.account_number}] if self.account_number else [],
            "unitOfMeasurement": "metric",
            "isCustomsDeclarable": destination.country_code != origin.country_code,
            "packages": [{"weight": weight_kg, "dimensions": {"length": 20, "width": 20, "height": 10}}],
        }
        try:
            response = requests.get(
                f"{self.base_url}/rates",
                params=payload,
                auth=self._auth(),
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            raise ShippingProviderError(f"DHL rates request failed: {e}") from e
        except ValueError as e:
            raise ShippingProviderError(f"DHL rates response was not valid JSON: {e}") from e

        rates = []
        for product in data.get("products", []):
            price_info = (product.get("totalPrice") or [{}])[0]
            rates.append(RateOption(
                service_code=product.get("productCode", "P"),
                name=product.get("productName", "DHL Express"),
                price=float(price_info.get("price", 0.0)),
                currency=price_info.get("priceCurrency", "EUR"),
                eta_days=None,
            ))
        return rates

    def create_shipment(self, origin, destination, weight_kg, service_code, reference):
        weight_kg = weight_kg or 1.0
        payload = {
            "plannedShippingDateAndTime": None,
            "productCode": service_code or "P",
            "accounts": [{"typeCode": "shipper", "number": self.account_number}] if self.account_number else [],
            "customerReferences": [{"value": reference}] if reference else [],
            "customerDetails": {
                "shipperDetails": {**self._address_payload(origin), "companyName": origin.name, "phone": origin.phone},
                "receiverDetails": {**self._address_payload(destination), "companyName": destination.name, "phone": destination.phone},
            },
            "content": {
                "packages": [{"weight": weight_kg, "dimensions": {"length": 20, "width": 20, "height": 10}}],
                "isCustomsDeclarable": destination.country_code != origin.country_code,
                "unitOfMeasurement": "metric",
            },
        }
        try:
            response = requests.post(
                f"{self.base_url}/shipments",
                json=payload,
                auth=self._auth(),
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            raise ShippingProviderError(f"DHL shipment creation failed: {e}") from e
        except ValueError as e:
            raise ShippingProviderError(f"DHL shipment response was not valid JSON: {e}") from e

        tracking_number = data.get("shipmentTrackingNumber", "")
        documents = data.get("documents", [])
        label_url = ""
        for doc in documents:
            if doc.get("typeCode") == "label":
                # MyDHL API повертає base64-контент документа, а не URL;
                # для MVP зберігаємо посилання на власний ендпоінт, що віддає
                # збережений label (див. WarehouseTask.label_url).
                label_url = doc.get("url", "")
                break

        if not tracking_number:
            raise ShippingProviderError("DHL response did not include a tracking number")

        return ShipmentResult(
            tracking_number=tracking_number,
            label_url=label_url,
            carrier_shipment_id=tracking_number,
        )
