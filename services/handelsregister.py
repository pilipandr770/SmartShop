"""
Сервіс для перевірки німецьких компаній в Handelsregister
Handelsregister - офіційний торговий реєстр Німеччини
"""
import re
import requests
from datetime import datetime
from typing import Optional, Dict, Any, List
from bs4 import BeautifulSoup


class HandelsregisterChecker:
    """
    Перевірка німецьких компаній в Handelsregister.
    
    Handelsregister (HRB/HRA) - номер реєстрації:
    - HRA = Handelsregister Abteilung A (фізичні особи, товариства)
    - HRB = Handelsregister Abteilung B (юридичні особи: GmbH, AG, etc.)
    
    Формат: HRB 12345 або HRA 12345 + назва суду (Amtsgericht)
    Приклад: HRB 123456 B (Amtsgericht Berlin-Charlottenburg)
    """
    
    # Офіційний портал Handelsregister
    BASE_URL = "https://www.handelsregister.de"
    SEARCH_URL = f"{BASE_URL}/rp_web/mask.do"
    
    # Публічні джерела даних
    NORTH_DATA_API = "https://www.northdata.com/api/v0.1/company"
    COMPANY_HOUSE_API = "https://api.unternehmensregister.de"  # Потребує API ключ
    
    # Німецькі суди (Amtsgerichte) та їх коди
    COURTS = {
        "berlin": "Berlin (Charlottenburg)",
        "munich": "München",
        "hamburg": "Hamburg",
        "frankfurt": "Frankfurt am Main",
        "cologne": "Köln",
        "dusseldorf": "Düsseldorf",
        "stuttgart": "Stuttgart",
        "hannover": "Hannover",
        "leipzig": "Leipzig",
        "dresden": "Dresden",
        "nuremberg": "Nürnberg",
        "essen": "Essen",
        "dortmund": "Dortmund",
        "bremen": "Bremen",
        "bonn": "Bonn",
    }
    
    # Типи компаній
    COMPANY_TYPES = {
        "GmbH": "Gesellschaft mit beschränkter Haftung",
        "AG": "Aktiengesellschaft",
        "KG": "Kommanditgesellschaft",
        "OHG": "Offene Handelsgesellschaft",
        "UG": "Unternehmergesellschaft (haftungsbeschränkt)",
        "GmbH & Co. KG": "GmbH & Compagnie Kommanditgesellschaft",
        "e.K.": "eingetragener Kaufmann",
        "eG": "eingetragene Genossenschaft",
        "SE": "Societas Europaea",
    }
    
    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.last_check_result = None
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
        })
    
    @staticmethod
    def parse_hr_number(hr_input: str) -> Dict[str, str]:
        """
        Парсить Handelsregister номер.
        
        Args:
            hr_input: Вхідний рядок (напр. "HRB 123456 B" або "HRB123456")
            
        Returns:
            {"type": "HRB", "number": "123456", "suffix": "B", "valid": True}
        """
        result = {
            "type": None,
            "number": None,
            "suffix": None,
            "valid": False,
            "raw": hr_input,
        }
        
        if not hr_input:
            return result
        
        # Очищення
        hr = hr_input.upper().strip()
        hr = re.sub(r'\s+', ' ', hr)
        
        # Паттерни HRB/HRA номерів
        patterns = [
            r'^(HR[AB])\s*(\d+)\s*([A-Z])?$',           # HRB 12345 B
            r'^(HR[AB])(\d+)([A-Z])?$',                 # HRB12345B
            r'^(HR[AB])\s*(\d+)\s+([A-Z])\s*\(',        # HRB 12345 B (Court)
            r'^(\d+)\s*([A-Z])?$',                       # 12345 B (без типу)
        ]
        
        for pattern in patterns:
            match = re.match(pattern, hr)
            if match:
                groups = match.groups()
                if len(groups) >= 2:
                    if groups[0] in ["HRA", "HRB"]:
                        result["type"] = groups[0]
                        result["number"] = groups[1]
                        result["suffix"] = groups[2] if len(groups) > 2 else None
                    else:
                        result["type"] = "HRB"  # За замовчуванням
                        result["number"] = groups[0]
                        result["suffix"] = groups[1] if len(groups) > 1 else None
                    result["valid"] = True
                    break
        
        return result
    
    @staticmethod
    def detect_company_type(company_name: str) -> Optional[str]:
        """Визначає тип компанії за назвою."""
        name_upper = company_name.upper()
        
        for abbr, full in HandelsregisterChecker.COMPANY_TYPES.items():
            if abbr.upper() in name_upper:
                return abbr
        
        return None
    
    def search_company_online(self, company_name: str, hr_number: str = None) -> Dict[str, Any]:
        """
        Шукає компанію в публічних джерелах.
        
        Note: Офіційний Handelsregister.de не має публічного API,
        тому використовуємо альтернативні джерела або парсинг.
        """
        result = {
            "found": False,
            "company_name": company_name,
            "hr_number": hr_number,
            "data": None,
            "source": None,
            "error": None,
        }
        
        # Спроба через North Data (публічні дані)
        try:
            # North Data пошук
            search_url = f"https://www.northdata.com/_search?q={requests.utils.quote(company_name)}"
            response = self.session.get(search_url, timeout=self.timeout)
            
            if response.status_code == 200:
                # Парсимо сторінку пошуку
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Шукаємо результати
                results = soup.find_all('div', class_='result')
                
                if results:
                    result["found"] = True
                    result["source"] = "northdata"
                    result["data"] = {
                        "results_count": len(results),
                        "first_result": results[0].get_text(strip=True)[:200] if results else None
                    }
        except Exception as e:
            result["error"] = f"Помилка пошуку: {str(e)}"
        
        return result
    
    def verify_hr_number(self, hr_number: str, company_name: str = None, court: str = None) -> Dict[str, Any]:
        """
        Перевіряє Handelsregister номер.
        
        Args:
            hr_number: HR номер (напр. "HRB 123456")
            company_name: Назва компанії для верифікації
            court: Суд (Amtsgericht)
            
        Returns:
            {
                "valid": bool,
                "hr_number": str,
                "hr_type": str,
                "company_name": str | None,
                "court": str | None,
                "status": str,
                "registration_date": str | None,
                "company_type": str | None,
                "address": str | None,
                "representatives": list,
                "capital": str | None,
                "reliability_score": int,
                "warnings": list,
                "error": str | None,
                "checked_at": str
            }
        """
        result = {
            "valid": False,
            "hr_number": hr_number,
            "hr_type": None,
            "hr_parsed": None,
            "company_name": company_name,
            "court": court,
            "status": "unknown",
            "registration_date": None,
            "company_type": None,
            "address": None,
            "representatives": [],
            "capital": None,
            "reliability_score": 0,
            "warnings": [],
            "error": None,
            "checked_at": datetime.utcnow().isoformat(),
        }
        
        # Парсимо номер
        parsed = self.parse_hr_number(hr_number)
        result["hr_parsed"] = parsed
        
        if not parsed["valid"]:
            result["error"] = "Невірний формат Handelsregister номера"
            result["warnings"].append("Очікуваний формат: HRB 123456 або HRA 123456")
            return result
        
        result["hr_type"] = parsed["type"]
        result["hr_number"] = f"{parsed['type']} {parsed['number']}"
        if parsed["suffix"]:
            result["hr_number"] += f" {parsed['suffix']}"
        
        # Визначаємо тип компанії
        if company_name:
            result["company_type"] = self.detect_company_type(company_name)
        
        # Базова валідація на основі формату
        score = 0
        
        # Правильний формат (20 балів)
        score += 20
        
        # Тип HRB/HRA (10 балів)
        if parsed["type"] in ["HRB", "HRA"]:
            score += 10
        
        # Номер має достатню довжину (15 балів)
        if parsed["number"] and len(parsed["number"]) >= 4:
            score += 15
        else:
            result["warnings"].append("Короткий HR номер")
        
        # Є суфікс (5 балів)
        if parsed["suffix"]:
            score += 5
        
        # Вказаний суд (15 балів)
        if court:
            score += 15
            result["court"] = court
        else:
            result["warnings"].append("Не вказано суд реєстрації (Amtsgericht)")
        
        # Тип компанії визначено (15 балів)
        if result["company_type"]:
            score += 15
        else:
            result["warnings"].append("Тип компанії не визначено")
        
        # Пошук онлайн (до 20 балів)
        if company_name:
            online_result = self.search_company_online(company_name, hr_number)
            if online_result.get("found"):
                score += 20
                result["status"] = "found"
            else:
                result["warnings"].append("Компанію не знайдено в публічних джерелах")
        
        result["reliability_score"] = min(100, score)
        result["valid"] = score >= 30  # Мінімальний поріг
        
        if result["valid"]:
            result["status"] = "verified_format"
        
        self.last_check_result = result
        return result
    
    def check_company(
        self, 
        company_name: str, 
        hr_number: str = None,
        city: str = None,
        vat_number: str = None
    ) -> Dict[str, Any]:
        """
        Комплексна перевірка німецької компанії.
        
        Args:
            company_name: Назва компанії
            hr_number: Handelsregister номер (опційно)
            city: Місто (для визначення суду)
            vat_number: VAT номер для крос-верифікації
            
        Returns:
            Результат перевірки з reliability_score
        """
        result = {
            "valid": False,
            "company_name": company_name,
            "is_german": False,
            "hr_verification": None,
            "company_type": None,
            "reliability_score": 0,
            "recommendations": [],
            "checked_at": datetime.utcnow().isoformat(),
        }
        
        # Перевіряємо чи це німецька компанія
        if vat_number and vat_number.upper().startswith("DE"):
            result["is_german"] = True
        
        # Визначаємо тип компанії
        result["company_type"] = self.detect_company_type(company_name)
        if result["company_type"]:
            result["is_german"] = True  # Німецькі форми власності
        
        # Верифікуємо HR номер
        if hr_number:
            # Визначаємо суд за містом
            court = None
            if city:
                city_lower = city.lower()
                for key, court_name in self.COURTS.items():
                    if key in city_lower:
                        court = court_name
                        break
            
            hr_result = self.verify_hr_number(hr_number, company_name, court)
            result["hr_verification"] = hr_result
            result["reliability_score"] = hr_result.get("reliability_score", 0)
            result["valid"] = hr_result.get("valid", False)
        else:
            result["recommendations"].append(
                "Рекомендуємо надати Handelsregister номер для повної верифікації"
            )
            
            # Базовий скор без HR
            if result["is_german"]:
                result["reliability_score"] = 20
                result["recommendations"].append(
                    "Компанія ідентифікована як німецька, але HR не надано"
                )
        
        return result


# Глобальний екземпляр
handelsregister_checker = HandelsregisterChecker()


def verify_german_company(
    company_name: str, 
    hr_number: str = None,
    city: str = None
) -> Dict[str, Any]:
    """Зручна функція для перевірки німецької компанії."""
    return handelsregister_checker.check_company(company_name, hr_number, city)
