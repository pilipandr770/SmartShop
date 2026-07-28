"""
UPS (Rating API + Shipping API) провайдер доставки.

Реалізовано за офіційною специфікацією UPS API
(https://developer.ups.com/api/reference) - OAuth2 client_credentials для
токена, потім Rating API (`/api/rating/{version}/Shop`) і Shipping API
(`/api/shipments/{version}/ship`). НЕ протестовано проти реального sandbox -
на момент написання в проєкті немає UPS API-ключів. Перед використанням у
production обов'язково прогнати смоук-тест з реальними sandbox-креденшелами
(developer.ups.com -> Add App, client_id/client_secret).
"""
import requests
from .base import ShippingProvider, RateOption, ShipmentResult, ShippingProviderError

SANDBOX_BASE_URL = "https://wwwcie.ups.com"
PRODUCTION_BASE_URL = "https://onlinetools.ups.com"

REQUEST_TIMEOUT = 15


class UPSProvider(ShippingProvider):
    def __init__(self, credentials: dict, is_sandbox: bool = True):
        super().__init__(credentials, is_sandbox)
        self.client_id = (credentials or {}).get("client_id", "")
        self.client_secret = (credentials or {}).get("client_secret", "")
        self.account_number = (credentials or {}).get("account_number", "")
        self.base_url = SANDBOX_BASE_URL if is_sandbox else PRODUCTION_BASE_URL
        self._access_token = None

    def _get_access_token(self):
        if self._access_token:
            return self._access_token
        try:
            response = requests.post(
                f"{self.base_url}/security/v1/oauth/token",
                data={"grant_type": "client_credentials"},
                auth=(self.client_id, self.client_secret),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            self._access_token = response.json().get("access_token")
        except requests.RequestException as e:
            raise ShippingProviderError(f"UPS OAuth token request failed: {e}") from e
        if not self._access_token:
            raise ShippingProviderError("UPS OAuth response did not include an access_token")
        return self._access_token

    def _headers(self):
        return {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Content-Type": "application/json",
        }

    def _address_payload(self, address):
        return {
            "Name": address.name or "N/A",
            "Phone": {"Number": address.phone} if address.phone else None,
            "Address": {
                "AddressLine": [address.street],
                "City": address.city,
                "PostalCode": address.postal_code,
                "CountryCode": address.country_code,
            },
        }

    def get_rates(self, origin, destination, weight_kg):
        weight_kg = weight_kg or 1.0
        payload = {
            "RateRequest": {
                "Shipment": {
                    "Shipper": {**self._address_payload(origin), "ShipperNumber": self.account_number},
                    "ShipTo": self._address_payload(destination),
                    "ShipFrom": self._address_payload(origin),
                    "Package": [{
                        "PackagingType": {"Code": "02"},
                        "PackageWeight": {
                            "UnitOfMeasurement": {"Code": "KGS"},
                            "Weight": str(weight_kg),
                        },
                    }],
                }
            }
        }
        try:
            response = requests.post(
                f"{self.base_url}/api/rating/v1/Shop",
                json=payload,
                headers=self._headers(),
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            raise ShippingProviderError(f"UPS rating request failed: {e}") from e
        except ValueError as e:
            raise ShippingProviderError(f"UPS rating response was not valid JSON: {e}") from e

        rated = data.get("RateResponse", {}).get("RatedShipment", [])
        if isinstance(rated, dict):
            rated = [rated]

        rates = []
        for shipment in rated:
            charges = shipment.get("TotalCharges", {})
            service = shipment.get("Service", {})
            rates.append(RateOption(
                service_code=service.get("Code", ""),
                name=self._service_name(service.get("Code", "")),
                price=float(charges.get("MonetaryValue", 0.0)),
                currency=charges.get("CurrencyCode", "EUR"),
            ))
        return rates

    @staticmethod
    def _service_name(code):
        return {
            "03": "UPS Ground",
            "02": "UPS 2nd Day Air",
            "01": "UPS Next Day Air",
            "11": "UPS Standard",
            "07": "UPS Worldwide Express",
            "08": "UPS Worldwide Expedited",
            "65": "UPS Worldwide Saver",
        }.get(code, f"UPS ({code})")

    def create_shipment(self, origin, destination, weight_kg, service_code, reference):
        weight_kg = weight_kg or 1.0
        payload = {
            "ShipmentRequest": {
                "Shipment": {
                    "Description": reference or "Order",
                    "Shipper": {**self._address_payload(origin), "ShipperNumber": self.account_number},
                    "ShipTo": self._address_payload(destination),
                    "ShipFrom": self._address_payload(origin),
                    "PaymentInformation": {
                        "ShipmentCharge": {
                            "Type": "01",
                            "BillShipper": {"AccountNumber": self.account_number},
                        }
                    },
                    "Service": {"Code": service_code or "11"},
                    "Package": [{
                        "PackagingType": {"Code": "02"},
                        "PackageWeight": {
                            "UnitOfMeasurement": {"Code": "KGS"},
                            "Weight": str(weight_kg),
                        },
                    }],
                },
                "LabelSpecification": {
                    "LabelImageFormat": {"Code": "PDF"},
                },
            }
        }
        try:
            response = requests.post(
                f"{self.base_url}/api/shipments/v1/ship",
                json=payload,
                headers=self._headers(),
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            raise ShippingProviderError(f"UPS shipment creation failed: {e}") from e
        except ValueError as e:
            raise ShippingProviderError(f"UPS shipment response was not valid JSON: {e}") from e

        results = data.get("ShipmentResponse", {}).get("ShipmentResults", {})
        package_results = results.get("PackageResults", [])
        if isinstance(package_results, dict):
            package_results = [package_results]

        tracking_number = package_results[0].get("TrackingNumber", "") if package_results else ""
        label_image = package_results[0].get("ShippingLabel", {}).get("GraphicImage", "") if package_results else ""

        if not tracking_number:
            raise ShippingProviderError("UPS response did not include a tracking number")

        return ShipmentResult(
            tracking_number=tracking_number,
            # GraphicImage - base64 PDF; для MVP зберігаємо як data-URI напряму
            label_url=f"data:application/pdf;base64,{label_image}" if label_image else "",
            carrier_shipment_id=results.get("ShipmentIdentificationNumber", tracking_number),
        )
