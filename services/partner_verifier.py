"""
Єдиний сервіс верифікації B2B партнерів
Об'єднує: VAT (VIES), WHOIS, Handelsregister
Розраховує загальний reliability score та створює алерти
"""
import json
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum

from services.vat_checker import VATChecker, check_vat_number
from services.whois_checker import WHOISChecker, check_company_domain
from services.handelsregister import HandelsregisterChecker, verify_german_company


class VerificationType(str, Enum):
    """Типи верифікації."""
    VAT = "vat"
    WHOIS = "whois"
    HANDELSREGISTER = "handelsregister"
    FULL = "full"


class ReliabilityLevel(str, Enum):
    """Рівні надійності контрагента."""
    HIGH = "high"           # 80-100 - Повністю верифікований
    MEDIUM = "medium"       # 50-79 - Частково верифікований
    LOW = "low"             # 20-49 - Потребує перевірки
    CRITICAL = "critical"   # 0-19 - Ненадійний


class AlertType(str, Enum):
    """Типи алертів."""
    VAT_INVALID = "vat_invalid"
    VAT_CHANGED = "vat_changed"
    DOMAIN_EXPIRED = "domain_expired"
    DOMAIN_OWNER_CHANGED = "domain_owner_changed"
    DOMAIN_NEW = "domain_new"
    HR_NOT_FOUND = "hr_not_found"
    HR_STATUS_CHANGED = "hr_status_changed"
    RELIABILITY_DROPPED = "reliability_dropped"
    NEW_PARTNER = "new_partner"
    VERIFICATION_FAILED = "verification_failed"


class PartnerVerifier:
    """
    Головний сервіс верифікації партнерів.
    
    Виконує комплексну перевірку:
    1. VAT через VIES API (для ЄС)
    2. WHOIS домену компанії
    3. Handelsregister (для німецьких компаній)
    
    Розраховує reliability_score (0-100) та генерує алерти.
    """
    
    # Ваги для розрахунку загального score
    WEIGHTS = {
        "vat": 40,          # VAT - 40% ваги
        "whois": 30,        # WHOIS - 30% ваги
        "handelsregister": 30,  # HR - 30% (тільки для DE)
    }
    
    # Пороги reliability
    THRESHOLDS = {
        ReliabilityLevel.HIGH: 80,
        ReliabilityLevel.MEDIUM: 50,
        ReliabilityLevel.LOW: 20,
    }
    
    def __init__(self):
        self.vat_checker = VATChecker()
        self.whois_checker = WHOISChecker()
        self.hr_checker = HandelsregisterChecker()
    
    def get_reliability_level(self, score: int) -> ReliabilityLevel:
        """Визначає рівень надійності за score."""
        if score >= self.THRESHOLDS[ReliabilityLevel.HIGH]:
            return ReliabilityLevel.HIGH
        elif score >= self.THRESHOLDS[ReliabilityLevel.MEDIUM]:
            return ReliabilityLevel.MEDIUM
        elif score >= self.THRESHOLDS[ReliabilityLevel.LOW]:
            return ReliabilityLevel.LOW
        return ReliabilityLevel.CRITICAL
    
    def verify_vat(self, vat_number: str) -> Dict[str, Any]:
        """Перевіряє VAT номер."""
        return self.vat_checker.check_full_vat(vat_number)
    
    def verify_domain(self, domain: str) -> Dict[str, Any]:
        """Перевіряє домен компанії."""
        return self.whois_checker.check_domain(domain)
    
    def verify_handelsregister(
        self, 
        company_name: str, 
        hr_number: str = None,
        city: str = None
    ) -> Dict[str, Any]:
        """Перевіряє німецьку компанію в Handelsregister."""
        return self.hr_checker.check_company(company_name, hr_number, city)
    
    def full_verification(
        self,
        company_name: str,
        vat_number: str = None,
        domain: str = None,
        hr_number: str = None,
        country_code: str = None,
        city: str = None,
        previous_result: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Повна верифікація партнера.
        
        Args:
            company_name: Назва компанії
            vat_number: VAT номер
            domain: Веб-сайт/домен компанії
            hr_number: Handelsregister номер (для DE)
            country_code: Код країни (напр. "DE")
            city: Місто (для HR перевірки)
            previous_result: Попередній результат для порівняння
            
        Returns:
            {
                "company_name": str,
                "verified_at": str,
                "reliability_score": int,
                "reliability_level": str,
                "vat_result": {...} | None,
                "whois_result": {...} | None,
                "hr_result": {...} | None,
                "is_german": bool,
                "alerts": [...],
                "changes": [...],
                "summary": str,
                "recommendations": [...]
            }
        """
        result = {
            "company_name": company_name,
            "verified_at": datetime.utcnow().isoformat(),
            "reliability_score": 0,
            "reliability_level": ReliabilityLevel.CRITICAL.value,
            "vat_result": None,
            "whois_result": None,
            "hr_result": None,
            "is_german": False,
            "alerts": [],
            "changes": [],
            "summary": "",
            "recommendations": [],
        }
        
        scores = {}
        weights_used = {}
        
        # Визначаємо чи це німецька компанія
        is_german = False
        if country_code and country_code.upper() == "DE":
            is_german = True
        elif vat_number and vat_number.upper().startswith("DE"):
            is_german = True
        
        result["is_german"] = is_german
        
        # === VAT верифікація ===
        if vat_number:
            try:
                vat_result = self.verify_vat(vat_number)
                result["vat_result"] = vat_result
                
                if vat_result.get("valid"):
                    scores["vat"] = 100
                    
                    # Порівнюємо з попередньою перевіркою
                    if previous_result and previous_result.get("vat_result"):
                        prev_vat = previous_result["vat_result"]
                        if prev_vat.get("name") != vat_result.get("name"):
                            result["changes"].append({
                                "type": "vat_name_changed",
                                "old": prev_vat.get("name"),
                                "new": vat_result.get("name"),
                            })
                            result["alerts"].append({
                                "type": AlertType.VAT_CHANGED.value,
                                "message": f"Назва компанії в VAT змінилась",
                                "severity": "warning",
                            })
                else:
                    scores["vat"] = 0
                    result["alerts"].append({
                        "type": AlertType.VAT_INVALID.value,
                        "message": f"VAT номер недійсний: {vat_result.get('error')}",
                        "severity": "critical",
                    })
                    result["recommendations"].append("Перевірте VAT номер")
                
                weights_used["vat"] = self.WEIGHTS["vat"]
                
            except Exception as e:
                result["alerts"].append({
                    "type": AlertType.VERIFICATION_FAILED.value,
                    "message": f"Помилка VAT перевірки: {str(e)}",
                    "severity": "warning",
                })
        else:
            result["recommendations"].append("Рекомендуємо надати VAT номер")
        
        # === WHOIS верифікація ===
        if domain:
            try:
                whois_result = self.verify_domain(domain)
                result["whois_result"] = whois_result
                
                if whois_result.get("valid"):
                    scores["whois"] = whois_result.get("reliability_score", 50)
                    
                    # Перевірка на критичні проблеми
                    if whois_result.get("is_expired"):
                        result["alerts"].append({
                            "type": AlertType.DOMAIN_EXPIRED.value,
                            "message": "Домен компанії прострочений!",
                            "severity": "critical",
                        })
                        scores["whois"] = max(0, scores["whois"] - 30)
                    
                    if whois_result.get("age_days") and whois_result["age_days"] < 90:
                        result["alerts"].append({
                            "type": AlertType.DOMAIN_NEW.value,
                            "message": f"Домен новий (< 90 днів)",
                            "severity": "warning",
                        })
                    
                    # Порівняння з попереднім
                    if previous_result and previous_result.get("whois_result"):
                        prev_whois = previous_result["whois_result"]
                        prev_org = prev_whois.get("registrant_org") or prev_whois.get("registrant_name")
                        curr_org = whois_result.get("registrant_org") or whois_result.get("registrant_name")
                        
                        if prev_org and curr_org and prev_org != curr_org:
                            result["changes"].append({
                                "type": "whois_owner_changed",
                                "old": prev_org,
                                "new": curr_org,
                            })
                            result["alerts"].append({
                                "type": AlertType.DOMAIN_OWNER_CHANGED.value,
                                "message": "Власник домену змінився!",
                                "severity": "critical",
                            })
                else:
                    scores["whois"] = 0
                    result["recommendations"].append("Перевірте домен компанії")
                
                weights_used["whois"] = self.WEIGHTS["whois"]
                
            except Exception as e:
                result["alerts"].append({
                    "type": AlertType.VERIFICATION_FAILED.value,
                    "message": f"Помилка WHOIS перевірки: {str(e)}",
                    "severity": "warning",
                })
        else:
            result["recommendations"].append("Рекомендуємо надати веб-сайт компанії")
        
        # === Handelsregister (тільки для Німеччини) ===
        if is_german:
            try:
                hr_result = self.verify_handelsregister(
                    company_name, 
                    hr_number, 
                    city
                )
                result["hr_result"] = hr_result
                
                if hr_result.get("valid"):
                    scores["handelsregister"] = hr_result.get("reliability_score", 50)
                else:
                    scores["handelsregister"] = 0
                    if hr_number:
                        result["alerts"].append({
                            "type": AlertType.HR_NOT_FOUND.value,
                            "message": "Handelsregister номер не підтверджено",
                            "severity": "warning",
                        })
                    else:
                        result["recommendations"].append(
                            "Для німецьких компаній рекомендуємо надати HR номер"
                        )
                
                weights_used["handelsregister"] = self.WEIGHTS["handelsregister"]
                
            except Exception as e:
                result["alerts"].append({
                    "type": AlertType.VERIFICATION_FAILED.value,
                    "message": f"Помилка HR перевірки: {str(e)}",
                    "severity": "warning",
                })
        
        # === Розрахунок загального score ===
        if scores and weights_used:
            total_weight = sum(weights_used.values())
            weighted_sum = sum(
                scores.get(key, 0) * weight 
                for key, weight in weights_used.items()
            )
            result["reliability_score"] = int(weighted_sum / total_weight)
        
        result["reliability_level"] = self.get_reliability_level(
            result["reliability_score"]
        ).value
        
        # === Порівняння з попереднім score ===
        if previous_result:
            prev_score = previous_result.get("reliability_score", 0)
            if result["reliability_score"] < prev_score - 20:
                result["alerts"].append({
                    "type": AlertType.RELIABILITY_DROPPED.value,
                    "message": f"Надійність впала з {prev_score} до {result['reliability_score']}",
                    "severity": "critical",
                })
        
        # === Формування summary ===
        result["summary"] = self._generate_summary(result)
        
        return result
    
    def _generate_summary(self, result: Dict[str, Any]) -> str:
        """Генерує текстовий summary результату."""
        level = result["reliability_level"]
        score = result["reliability_score"]
        
        level_texts = {
            "high": "✅ Високий рівень надійності",
            "medium": "⚠️ Середній рівень надійності",
            "low": "🔶 Низький рівень надійності",
            "critical": "❌ Критичний рівень надійності",
        }
        
        parts = [f"{level_texts.get(level, '')} ({score}/100)"]
        
        # VAT
        if result.get("vat_result"):
            if result["vat_result"].get("valid"):
                parts.append("VAT: ✓")
            else:
                parts.append("VAT: ✗")
        
        # WHOIS
        if result.get("whois_result"):
            if result["whois_result"].get("valid"):
                age = result["whois_result"].get("age_days")
                parts.append(f"Домен: ✓ ({age} днів)" if age else "Домен: ✓")
            else:
                parts.append("Домен: ✗")
        
        # HR
        if result.get("is_german") and result.get("hr_result"):
            if result["hr_result"].get("valid"):
                parts.append("HR: ✓")
            else:
                parts.append("HR: ✗")
        
        # Алерти
        critical_alerts = [a for a in result.get("alerts", []) if a.get("severity") == "critical"]
        if critical_alerts:
            parts.append(f"⚠️ {len(critical_alerts)} критичних алертів")
        
        return " | ".join(parts)
    
    def quick_check(self, vat_number: str) -> Dict[str, Any]:
        """
        Швидка перевірка лише за VAT номером.
        Використовується при реєстрації партнера.
        """
        return self.verify_vat(vat_number)
    
    def generate_alerts_for_db(
        self, 
        company_id: int, 
        verification_result: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Генерує алерти для збереження в БД.
        
        Returns:
            Список алертів для AdminAlert моделі
        """
        alerts = []
        
        for alert in verification_result.get("alerts", []):
            alerts.append({
                "company_id": company_id,
                "alert_type": alert.get("type"),
                "message": alert.get("message"),
                "severity": alert.get("severity", "info"),
                "verification_data": json.dumps(verification_result),
                "created_at": datetime.utcnow(),
                "is_resolved": False,
            })
        
        # Додаємо алерт про зміни
        for change in verification_result.get("changes", []):
            alerts.append({
                "company_id": company_id,
                "alert_type": f"change_{change.get('type')}",
                "message": f"{change.get('type')}: {change.get('old')} → {change.get('new')}",
                "severity": "warning",
                "verification_data": json.dumps(change),
                "created_at": datetime.utcnow(),
                "is_resolved": False,
            })
        
        return alerts


# Глобальний екземпляр
partner_verifier = PartnerVerifier()


def verify_partner(
    company_name: str,
    vat_number: str = None,
    domain: str = None,
    hr_number: str = None,
    country_code: str = None,
    city: str = None
) -> Dict[str, Any]:
    """Зручна функція для верифікації партнера."""
    return partner_verifier.full_verification(
        company_name=company_name,
        vat_number=vat_number,
        domain=domain,
        hr_number=hr_number,
        country_code=country_code,
        city=city
    )
