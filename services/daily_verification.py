"""
Сервіс для запуску щоденної перевірки партнерів.
Може бути запущений через cron job або APScheduler.
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Налаштування логування
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DailyVerificationJob:
    """
    Щоденна перевірка всіх активних B2B партнерів.
    
    Виконує:
    1. VAT перевірку через VIES
    2. WHOIS перевірку домену
    3. Handelsregister перевірку (для DE)
    4. Порівняння з попередніми результатами
    5. Генерацію алертів при змінах
    """
    
    def __init__(self, app=None):
        self.app = app
        
    def run(self, app=None) -> Dict[str, Any]:
        """
        Запускає перевірку всіх партнерів.
        
        Returns:
            {
                "success": bool,
                "checked": int,
                "alerts_created": int,
                "errors": int,
                "duration_seconds": float,
                "details": [...]
            }
        """
        if app:
            self.app = app
        
        start_time = datetime.utcnow()
        result = {
            "success": True,
            "checked": 0,
            "alerts_created": 0,
            "errors": 0,
            "duration_seconds": 0,
            "details": [],
            "started_at": start_time.isoformat(),
        }
        
        logger.info(f"🔄 Запуск щоденної перевірки партнерів: {start_time}")
        
        with self.app.app_context():
            from app import db
            from models.company import Company, VerificationLog, AdminAlert
            from services.partner_verifier import partner_verifier
            
            # Отримуємо всіх активних партнерів
            companies = Company.query.filter(
                Company.status.in_(["verified", "pending"])
            ).all()
            
            logger.info(f"📋 Знайдено {len(companies)} партнерів для перевірки")
            
            for company in companies:
                company_result = {
                    "company_id": company.id,
                    "company_name": company.name,
                    "success": False,
                    "alerts": [],
                    "error": None,
                }
                
                try:
                    # Попередній результат для порівняння
                    previous_result = company.last_verification_data
                    
                    # Повна верифікація
                    verification = partner_verifier.full_verification(
                        company_name=company.name,
                        vat_number=company.full_vat_number,
                        domain=company.website or company.domain,
                        hr_number=company.handelsregister_id,
                        country_code=company.country_code,
                        city=company.city,
                        previous_result=previous_result,
                    )
                    
                    # Оновлюємо дані компанії
                    old_score = company.reliability_score
                    company.reliability_score = verification.get("reliability_score", 0)
                    company.reliability_level = verification.get("reliability_level", "critical")
                    company.last_verification_at = datetime.utcnow()
                    company.last_verification_data = verification
                    
                    # Оновлюємо статуси окремих перевірок
                    if verification.get("vat_result", {}).get("valid"):
                        company.vat_verified = True
                        company.vat_verified_at = datetime.utcnow()
                        company.vat_data = verification["vat_result"]
                    elif verification.get("vat_result"):
                        company.vat_verified = False
                    
                    if verification.get("whois_result", {}).get("valid"):
                        company.is_whois_verified = True
                        company.whois_checked_at = datetime.utcnow()
                        company.whois_data = verification["whois_result"]
                    elif verification.get("whois_result"):
                        company.is_whois_verified = False
                    
                    if verification.get("hr_result", {}).get("valid"):
                        company.is_hr_verified = True
                        company.hr_data = verification["hr_result"]
                    elif verification.get("hr_result"):
                        company.is_hr_verified = False
                    
                    # Логуємо перевірку
                    changes_detected = len(verification.get("changes", [])) > 0
                    VerificationLog.log_check(
                        company_id=company.id,
                        check_type="daily_auto",
                        status="success",
                        is_valid=verification.get("reliability_score", 0) >= 50,
                        response_data=verification,
                        changes_detected=changes_detected,
                        changes_description=str(verification.get("changes", [])) if changes_detected else None,
                    )
                    
                    # Створюємо алерти
                    for alert_data in verification.get("alerts", []):
                        AdminAlert.create_alert(
                            alert_type=alert_data.get("type"),
                            title=f"[Auto] {company.name}: {alert_data.get('message', 'Алерт')}",
                            message=alert_data.get("message"),
                            company_id=company.id,
                            severity=alert_data.get("severity", "info"),
                            data=verification,
                        )
                        result["alerts_created"] += 1
                        company_result["alerts"].append(alert_data.get("type"))
                    
                    # Алерт якщо score суттєво впав
                    if old_score and company.reliability_score < old_score - 20:
                        AdminAlert.create_alert(
                            alert_type="reliability_dropped",
                            title=f"[Auto] {company.name}: Надійність впала",
                            message=f"Score впав з {old_score} до {company.reliability_score}",
                            company_id=company.id,
                            severity="critical",
                        )
                        result["alerts_created"] += 1
                    
                    company_result["success"] = True
                    company_result["new_score"] = company.reliability_score
                    result["checked"] += 1
                    
                    logger.info(
                        f"✅ {company.name}: score={company.reliability_score}, "
                        f"alerts={len(verification.get('alerts', []))}"
                    )
                    
                except Exception as e:
                    company_result["error"] = str(e)
                    result["errors"] += 1
                    
                    # Логуємо помилку
                    VerificationLog.log_check(
                        company_id=company.id,
                        check_type="daily_auto",
                        status="error",
                        is_valid=False,
                        error_message=str(e),
                    )
                    
                    logger.error(f"❌ {company.name}: {str(e)}")
                
                result["details"].append(company_result)
            
            # Зберігаємо всі зміни
            db.session.commit()
        
        # Підсумок
        end_time = datetime.utcnow()
        result["duration_seconds"] = (end_time - start_time).total_seconds()
        result["finished_at"] = end_time.isoformat()
        
        logger.info(
            f"🏁 Перевірка завершена: {result['checked']} партнерів, "
            f"{result['alerts_created']} алертів, {result['errors']} помилок, "
            f"{result['duration_seconds']:.1f}с"
        )
        
        return result


def run_daily_verification(app):
    """
    Функція для запуску з APScheduler або cron.
    
    Приклад використання з APScheduler:
    
    from apscheduler.schedulers.background import BackgroundScheduler
    
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=lambda: run_daily_verification(app),
        trigger="cron",
        hour=3,  # Запуск о 3:00 ночі
        minute=0,
        id="daily_partner_verification",
        replace_existing=True,
    )
    scheduler.start()
    """
    job = DailyVerificationJob(app)
    return job.run()


# CLI команда для ручного запуску
if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    
    from app import create_app
    
    app = create_app()
    result = run_daily_verification(app)
    
    print("\n" + "=" * 50)
    print("📊 РЕЗУЛЬТАТ ЩОДЕННОЇ ПЕРЕВІРКИ")
    print("=" * 50)
    print(f"✅ Перевірено: {result['checked']}")
    print(f"🔔 Алертів: {result['alerts_created']}")
    print(f"❌ Помилок: {result['errors']}")
    print(f"⏱️ Час: {result['duration_seconds']:.1f}с")
    print("=" * 50)
