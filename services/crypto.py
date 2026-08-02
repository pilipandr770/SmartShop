"""
Спільна утиліта симетричного шифрування (Fernet) для чутливих полів
at-rest. Раніше цей ключ використовувався лише для креденшелів
перевізників (models/shipping.py) - назва env-змінної лишається
історичною (CARRIER_CREDENTIALS_KEY), щоб не вимагати нової змінної
оточення на вже задеплоєних серверах. Тепер тим самим ключем
шифруються й TOTP-секрети двофакторної автентифікації (models/user.py).
"""
import os
from cryptography.fernet import Fernet

_fernet = None


def get_fernet():
    """Лінива ініціалізація - ключ читається з env лише при першому
    реальному зверненні, щоб відсутність ключа не ламала запуск
    застосунку для магазинів/користувачів, які взагалі не користуються
    жодною з фіч, що потребують шифрування."""
    global _fernet
    if _fernet is None:
        key = os.environ.get("CARRIER_CREDENTIALS_KEY")
        if not key:
            raise RuntimeError(
                "CARRIER_CREDENTIALS_KEY не налаштовано - неможливо "
                "зашифрувати/розшифрувати чутливі дані."
            )
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def encrypt_str(value):
    if not value:
        return None
    return get_fernet().encrypt(value.encode()).decode()


def decrypt_str(value):
    if not value:
        return None
    return get_fernet().decrypt(value.encode()).decode()
