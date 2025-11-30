"""
Сервіс для перевірки домену компанії через WHOIS
Перевіряє: реєстрацію домену, власника, дату створення, термін дії
"""
import socket
import re
from datetime import datetime
from typing import Optional, Dict, Any
from urllib.parse import urlparse


class WHOISChecker:
    """Перевірка домену компанії через WHOIS."""
    
    # WHOIS сервери для різних TLD
    WHOIS_SERVERS = {
        "com": "whois.verisign-grs.com",
        "net": "whois.verisign-grs.com",
        "org": "whois.pir.org",
        "info": "whois.afilias.net",
        "biz": "whois.biz",
        "de": "whois.denic.de",
        "uk": "whois.nic.uk",
        "co.uk": "whois.nic.uk",
        "eu": "whois.eu",
        "nl": "whois.domain-registry.nl",
        "fr": "whois.nic.fr",
        "it": "whois.nic.it",
        "es": "whois.nic.es",
        "pl": "whois.dns.pl",
        "cz": "whois.nic.cz",
        "at": "whois.nic.at",
        "ch": "whois.nic.ch",
        "be": "whois.dns.be",
        "ua": "whois.ua",
        "ru": "whois.tcinet.ru",
        "io": "whois.nic.io",
        "co": "whois.nic.co",
        "ai": "whois.nic.ai",
    }
    
    # Паттерни для парсингу WHOIS
    PATTERNS = {
        "creation_date": [
            r"Creation Date:\s*(.+)",
            r"Created:\s*(.+)",
            r"Created On:\s*(.+)",
            r"Registration Date:\s*(.+)",
            r"Registered:\s*(.+)",
            r"created:\s*(.+)",
            r"Domain Registration Date:\s*(.+)",
        ],
        "expiration_date": [
            r"Expir[a-z]+ Date:\s*(.+)",
            r"Expiry Date:\s*(.+)",
            r"Expires:\s*(.+)",
            r"Expires On:\s*(.+)",
            r"paid-till:\s*(.+)",
            r"Registry Expiry Date:\s*(.+)",
        ],
        "registrar": [
            r"Registrar:\s*(.+)",
            r"Registrar Name:\s*(.+)",
            r"Sponsoring Registrar:\s*(.+)",
        ],
        "registrant_name": [
            r"Registrant Name:\s*(.+)",
            r"Registrant:\s*(.+)",
            r"Owner:\s*(.+)",
            r"holder:\s*(.+)",
        ],
        "registrant_org": [
            r"Registrant Organization:\s*(.+)",
            r"Registrant Organisation:\s*(.+)",
            r"Organization:\s*(.+)",
            r"organisation:\s*(.+)",
        ],
        "registrant_country": [
            r"Registrant Country:\s*(.+)",
            r"Registrant State/Province:\s*(.+)",
            r"country:\s*(.+)",
        ],
        "status": [
            r"Domain Status:\s*(.+)",
            r"Status:\s*(.+)",
            r"state:\s*(.+)",
        ],
        "name_servers": [
            r"Name Server:\s*(.+)",
            r"nserver:\s*(.+)",
            r"Nameserver:\s*(.+)",
        ],
    }
    
    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.last_check_result = None
    
    @staticmethod
    def extract_domain(url_or_domain: str) -> str:
        """
        Витягує домен з URL або повертає сам домен.
        
        Args:
            url_or_domain: URL (https://example.com/page) або домен (example.com)
            
        Returns:
            Чистий домен без www (example.com)
        """
        # Якщо це URL - парсимо
        if "://" in url_or_domain:
            parsed = urlparse(url_or_domain)
            domain = parsed.netloc
        else:
            domain = url_or_domain
        
        # Прибираємо www
        domain = domain.lower().strip()
        if domain.startswith("www."):
            domain = domain[4:]
        
        # Прибираємо порт якщо є
        if ":" in domain:
            domain = domain.split(":")[0]
        
        return domain
    
    @staticmethod
    def get_tld(domain: str) -> str:
        """Повертає TLD домену."""
        parts = domain.split(".")
        if len(parts) >= 2:
            # Перевіряємо складні TLD (co.uk, com.ua)
            if len(parts) >= 3 and parts[-2] in ["co", "com", "org", "net", "gov"]:
                return f"{parts[-2]}.{parts[-1]}"
            return parts[-1]
        return ""
    
    def get_whois_server(self, domain: str) -> Optional[str]:
        """Повертає WHOIS сервер для домену."""
        tld = self.get_tld(domain)
        return self.WHOIS_SERVERS.get(tld)
    
    def query_whois(self, domain: str, server: str) -> Optional[str]:
        """
        Робить WHOIS запит до сервера.
        
        Args:
            domain: Домен для запиту
            server: WHOIS сервер
            
        Returns:
            Відповідь WHOIS або None
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            sock.connect((server, 43))
            
            # Деякі сервери потребують особливого формату
            if server == "whois.verisign-grs.com":
                query = f"={domain}\r\n"
            elif server == "whois.denic.de":
                query = f"-T dn {domain}\r\n"
            else:
                query = f"{domain}\r\n"
            
            sock.send(query.encode("utf-8"))
            
            response = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response += chunk
            
            sock.close()
            
            # Спроба декодування
            for encoding in ["utf-8", "latin-1", "cp1251"]:
                try:
                    return response.decode(encoding)
                except UnicodeDecodeError:
                    continue
            
            return response.decode("utf-8", errors="ignore")
            
        except socket.timeout:
            return None
        except socket.error:
            return None
        except Exception:
            return None
    
    def parse_whois(self, raw_data: str) -> Dict[str, Any]:
        """Парсить WHOIS відповідь."""
        result = {
            "creation_date": None,
            "expiration_date": None,
            "registrar": None,
            "registrant_name": None,
            "registrant_org": None,
            "registrant_country": None,
            "status": [],
            "name_servers": [],
        }
        
        for field, patterns in self.PATTERNS.items():
            for pattern in patterns:
                matches = re.findall(pattern, raw_data, re.IGNORECASE | re.MULTILINE)
                if matches:
                    if field in ["status", "name_servers"]:
                        result[field] = [m.strip() for m in matches]
                    else:
                        result[field] = matches[0].strip()
                    break
        
        return result
    
    def parse_date(self, date_str: str) -> Optional[datetime]:
        """Парсить дату з різних форматів."""
        if not date_str:
            return None
        
        date_formats = [
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%d-%b-%Y",
            "%d.%m.%Y",
            "%Y.%m.%d",
            "%d/%m/%Y",
            "%m/%d/%Y",
        ]
        
        # Очищуємо дату від зайвого
        date_str = date_str.split()[0] if " " in date_str else date_str
        date_str = date_str.replace("T", " ").split(" ")[0]
        
        for fmt in date_formats:
            try:
                return datetime.strptime(date_str[:len(fmt.replace("%", "").replace("-", "").replace("/", "").replace(".", "").replace("Y", "0000").replace("m", "00").replace("d", "00").replace("H", "00").replace("M", "00").replace("S", "00").replace("b", "000"))], fmt)
            except (ValueError, IndexError):
                continue
        
        return None
    
    def check_domain(self, domain_or_url: str) -> Dict[str, Any]:
        """
        Перевіряє домен через WHOIS.
        
        Args:
            domain_or_url: Домен або URL
            
        Returns:
            Dict з результатом:
            {
                "valid": bool,
                "domain": str,
                "tld": str,
                "creation_date": str | None,
                "expiration_date": str | None,
                "age_days": int | None,
                "registrar": str | None,
                "registrant_name": str | None,
                "registrant_org": str | None,
                "registrant_country": str | None,
                "status": list,
                "name_servers": list,
                "is_active": bool,
                "is_expired": bool,
                "reliability_score": int,  # 0-100
                "warnings": list,
                "error": str | None,
                "raw_data": str | None,
                "checked_at": str
            }
        """
        domain = self.extract_domain(domain_or_url)
        
        result = {
            "valid": False,
            "domain": domain,
            "tld": self.get_tld(domain),
            "creation_date": None,
            "expiration_date": None,
            "age_days": None,
            "registrar": None,
            "registrant_name": None,
            "registrant_org": None,
            "registrant_country": None,
            "status": [],
            "name_servers": [],
            "is_active": False,
            "is_expired": False,
            "reliability_score": 0,
            "warnings": [],
            "error": None,
            "raw_data": None,
            "checked_at": datetime.utcnow().isoformat(),
        }
        
        if not domain or "." not in domain:
            result["error"] = "Невірний формат домену"
            return result
        
        # Знаходимо WHOIS сервер
        whois_server = self.get_whois_server(domain)
        if not whois_server:
            result["error"] = f"WHOIS сервер для TLD .{result['tld']} не знайдено"
            result["warnings"].append("Використовується невідомий TLD")
            return result
        
        # Робимо запит
        raw_data = self.query_whois(domain, whois_server)
        if not raw_data:
            result["error"] = "Не вдалося отримати WHOIS дані"
            return result
        
        result["raw_data"] = raw_data
        
        # Перевіряємо чи домен існує
        not_found_patterns = [
            "No match for",
            "NOT FOUND",
            "No Data Found",
            "Domain not found",
            "No entries found",
            "Status: free",
            "Status: available",
        ]
        
        for pattern in not_found_patterns:
            if pattern.lower() in raw_data.lower():
                result["error"] = "Домен не зареєстрований"
                result["warnings"].append("Домен не існує")
                return result
        
        # Парсимо дані
        parsed = self.parse_whois(raw_data)
        
        result["registrar"] = parsed.get("registrar")
        result["registrant_name"] = parsed.get("registrant_name")
        result["registrant_org"] = parsed.get("registrant_org")
        result["registrant_country"] = parsed.get("registrant_country")
        result["status"] = parsed.get("status", [])
        result["name_servers"] = parsed.get("name_servers", [])
        
        # Парсимо дати
        if parsed.get("creation_date"):
            creation_dt = self.parse_date(parsed["creation_date"])
            if creation_dt:
                result["creation_date"] = creation_dt.isoformat()
                result["age_days"] = (datetime.utcnow() - creation_dt).days
        
        if parsed.get("expiration_date"):
            expiry_dt = self.parse_date(parsed["expiration_date"])
            if expiry_dt:
                result["expiration_date"] = expiry_dt.isoformat()
                result["is_expired"] = expiry_dt < datetime.utcnow()
        
        # Перевіряємо активність
        active_statuses = ["active", "ok", "clienttransferprohibited"]
        result["is_active"] = any(
            any(s in status.lower() for s in active_statuses)
            for status in result["status"]
        )
        
        # Якщо є name servers - домен активний
        if result["name_servers"]:
            result["is_active"] = True
        
        result["valid"] = True
        
        # Розраховуємо reliability score
        score = 0
        warnings = []
        
        # Вік домену (до 40 балів)
        if result["age_days"]:
            if result["age_days"] > 365 * 5:  # > 5 років
                score += 40
            elif result["age_days"] > 365 * 2:  # > 2 роки
                score += 30
            elif result["age_days"] > 365:  # > 1 рік
                score += 20
            elif result["age_days"] > 180:  # > 6 місяців
                score += 10
            else:
                warnings.append(f"Домен молодий ({result['age_days']} днів)")
        else:
            warnings.append("Не вдалося визначити вік домену")
        
        # Активність (до 20 балів)
        if result["is_active"]:
            score += 20
        else:
            warnings.append("Домен неактивний")
        
        # Не прострочений (до 15 балів)
        if not result["is_expired"]:
            score += 15
        else:
            warnings.append("Домен прострочений!")
        
        # Є реєстрант (до 15 балів)
        if result["registrant_org"] or result["registrant_name"]:
            score += 15
        else:
            warnings.append("Дані власника приховані")
        
        # Name servers (до 10 балів)
        if len(result["name_servers"]) >= 2:
            score += 10
        elif len(result["name_servers"]) >= 1:
            score += 5
            warnings.append("Тільки один NS сервер")
        
        result["reliability_score"] = min(100, score)
        result["warnings"] = warnings
        
        self.last_check_result = result
        return result
    
    def compare_registrant_with_company(
        self, 
        whois_data: Dict[str, Any], 
        company_name: str,
        country_code: str = None
    ) -> Dict[str, Any]:
        """
        Порівнює дані WHOIS з даними компанії.
        
        Returns:
            {
                "matches": bool,
                "name_match": bool,
                "country_match": bool,
                "confidence": int,  # 0-100
                "details": str
            }
        """
        result = {
            "matches": False,
            "name_match": False,
            "country_match": False,
            "confidence": 0,
            "details": "",
        }
        
        if not whois_data.get("valid"):
            result["details"] = "WHOIS дані недійсні"
            return result
        
        registrant = (
            whois_data.get("registrant_org") or 
            whois_data.get("registrant_name") or 
            ""
        ).lower()
        
        # Порівнюємо назви
        company_lower = company_name.lower()
        
        # Пряме співпадіння
        if company_lower in registrant or registrant in company_lower:
            result["name_match"] = True
            result["confidence"] += 50
        else:
            # Часткове співпадіння (перші слова)
            company_words = set(company_lower.split()[:3])
            registrant_words = set(registrant.split()[:3])
            common = company_words & registrant_words
            if len(common) >= 1:
                result["name_match"] = True
                result["confidence"] += 30
        
        # Порівнюємо країну
        if country_code and whois_data.get("registrant_country"):
            whois_country = whois_data["registrant_country"].upper()[:2]
            if country_code.upper() == whois_country:
                result["country_match"] = True
                result["confidence"] += 30
        
        # Додаткові бали за вік
        if whois_data.get("age_days", 0) > 365:
            result["confidence"] += 20
        
        result["matches"] = result["name_match"] or result["country_match"]
        result["confidence"] = min(100, result["confidence"])
        
        if result["matches"]:
            result["details"] = "Дані WHOIS відповідають компанії"
        else:
            result["details"] = "Дані WHOIS не співпадають з даними компанії"
        
        return result


# Глобальний екземпляр
whois_checker = WHOISChecker()


def check_company_domain(domain: str) -> Dict[str, Any]:
    """Зручна функція для перевірки домену."""
    return whois_checker.check_domain(domain)
