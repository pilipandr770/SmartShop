"""
Сервіс для перевірки VAT номерів через VIES API (EU)
"""
import re
import requests
from datetime import datetime
from typing import Optional, Dict, Any


class VATChecker:
    """Перевірка VAT номерів через VIES (EU) API."""
    
    # VIES REST API endpoint
    VIES_API_URL = "https://ec.europa.eu/taxation_customs/vies/rest-api/ms/{country}/vat/{vat_number}"
    
    # Формати VAT для різних країн
    VAT_PATTERNS = {
        "AT": r"^ATU\d{8}$",           # Austria
        "BE": r"^BE0?\d{9,10}$",       # Belgium
        "BG": r"^BG\d{9,10}$",         # Bulgaria
        "CY": r"^CY\d{8}[A-Z]$",       # Cyprus
        "CZ": r"^CZ\d{8,10}$",         # Czech Republic
        "DE": r"^DE\d{9}$",            # Germany
        "DK": r"^DK\d{8}$",            # Denmark
        "EE": r"^EE\d{9}$",            # Estonia
        "EL": r"^EL\d{9}$",            # Greece
        "ES": r"^ES[A-Z0-9]\d{7}[A-Z0-9]$",  # Spain
        "FI": r"^FI\d{8}$",            # Finland
        "FR": r"^FR[A-Z0-9]{2}\d{9}$", # France
        "HR": r"^HR\d{11}$",           # Croatia
        "HU": r"^HU\d{8}$",            # Hungary
        "IE": r"^IE\d{7}[A-Z]{1,2}$",  # Ireland
        "IT": r"^IT\d{11}$",           # Italy
        "LT": r"^LT(\d{9}|\d{12})$",   # Lithuania
        "LU": r"^LU\d{8}$",            # Luxembourg
        "LV": r"^LV\d{11}$",           # Latvia
        "MT": r"^MT\d{8}$",            # Malta
        "NL": r"^NL\d{9}B\d{2}$",      # Netherlands
        "PL": r"^PL\d{10}$",           # Poland
        "PT": r"^PT\d{9}$",            # Portugal
        "RO": r"^RO\d{2,10}$",         # Romania
        "SE": r"^SE\d{12}$",           # Sweden
        "SI": r"^SI\d{8}$",            # Slovenia
        "SK": r"^SK\d{10}$",           # Slovakia
        "XI": r"^XI\d{9}$",            # Northern Ireland
    }
    
    EU_COUNTRIES = list(VAT_PATTERNS.keys())
    
    def __init__(self):
        self.last_check_result = None
    
    @staticmethod
    def parse_vat_number(vat_number: str) -> tuple[str, str]:
        """
        Розбирає VAT номер на код країни та номер.
        
        Args:
            vat_number: VAT номер (напр. "DE123456789" або "123456789")
            
        Returns:
            Tuple (country_code, vat_number_only)
        """
        vat = vat_number.upper().replace(" ", "").replace("-", "").replace(".", "")
        
        # Перевіряємо чи починається з коду країни
        for country in VATChecker.EU_COUNTRIES:
            if vat.startswith(country):
                return country, vat[len(country):]
        
        return "", vat
    
    @staticmethod
    def validate_format(country_code: str, vat_number: str) -> bool:
        """
        Перевіряє формат VAT номера для країни.
        
        Args:
            country_code: ISO код країни (2 символи)
            vat_number: VAT номер без коду країни
            
        Returns:
            True якщо формат правильний
        """
        if country_code not in VATChecker.VAT_PATTERNS:
            return False
        
        full_vat = f"{country_code}{vat_number}"
        pattern = VATChecker.VAT_PATTERNS[country_code]
        return bool(re.match(pattern, full_vat))
    
    def check_vat(self, country_code: str, vat_number: str) -> Dict[str, Any]:
        """
        Перевіряє VAT номер через VIES API.
        
        Args:
            country_code: ISO код країни (2 символи)
            vat_number: VAT номер без коду країни
            
        Returns:
            Dict з результатом перевірки:
            {
                "valid": bool,
                "country_code": str,
                "vat_number": str,
                "request_date": str,
                "name": str | None,
                "address": str | None,
                "error": str | None,
                "raw_response": dict | None
            }
        """
        result = {
            "valid": False,
            "country_code": country_code.upper(),
            "vat_number": vat_number,
            "request_date": datetime.utcnow().isoformat(),
            "name": None,
            "address": None,
            "error": None,
            "raw_response": None,
        }
        
        # Валідація коду країни
        country = country_code.upper()
        if country not in self.EU_COUNTRIES:
            result["error"] = f"Країна {country} не підтримується VIES"
            return result
        
        # Очищення номера
        vat = vat_number.replace(" ", "").replace("-", "").replace(".", "")
        
        # Якщо номер починається з коду країни - прибираємо
        if vat.upper().startswith(country):
            vat = vat[len(country):]
        
        try:
            # Запит до VIES API
            url = self.VIES_API_URL.format(country=country, vat_number=vat)
            response = requests.get(url, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                result["raw_response"] = data
                result["valid"] = data.get("isValid", False)
                result["name"] = data.get("name")
                result["address"] = data.get("address")
                
                if not result["valid"]:
                    result["error"] = "VAT номер недійсний"
                    
            elif response.status_code == 400:
                result["error"] = "Невірний формат VAT номера"
            elif response.status_code == 404:
                result["error"] = "VAT номер не знайдено"
            else:
                result["error"] = f"Помилка VIES API: {response.status_code}"
                
        except requests.exceptions.Timeout:
            result["error"] = "Таймаут запиту до VIES"
        except requests.exceptions.RequestException as e:
            result["error"] = f"Помилка з'єднання: {str(e)}"
        except Exception as e:
            result["error"] = f"Невідома помилка: {str(e)}"
        
        self.last_check_result = result
        return result
    
    def check_full_vat(self, full_vat_number: str) -> Dict[str, Any]:
        """
        Перевіряє повний VAT номер (з кодом країни).
        
        Args:
            full_vat_number: Повний VAT номер (напр. "DE123456789")
            
        Returns:
            Dict з результатом перевірки
        """
        country, vat = self.parse_vat_number(full_vat_number)
        
        if not country:
            return {
                "valid": False,
                "error": "Не вдалося визначити країну з VAT номера",
                "vat_number": full_vat_number,
                "request_date": datetime.utcnow().isoformat(),
            }
        
        return self.check_vat(country, vat)


# Глобальний екземпляр
vat_checker = VATChecker()


def check_vat_number(vat_number: str, country_code: str = None) -> Dict[str, Any]:
    """
    Зручна функція для перевірки VAT.
    
    Args:
        vat_number: VAT номер
        country_code: Опційний код країни
        
    Returns:
        Результат перевірки
    """
    if country_code:
        return vat_checker.check_vat(country_code, vat_number)
    return vat_checker.check_full_vat(vat_number)
