#!/usr/bin/env python3
"""Manual German translation mapping for common UI strings."""
import re
from pathlib import Path

# Manual German translations for key UI strings
TRANSLATIONS = {
    "Потрібен вхід в адмін-панель.": "Anmeldung im Admin-Panel erforderlich.",
    "«%(name)s» додано в кошик.": "«%(name)s» zum Warenkorb hinzugefügt.",
    "Товар видалено з кошика.": "Artikel aus dem Warenkorb entfernt.",
    "Кошик очищено.": "Warenkorb geleert.",
    "Ваш кошик порожній.": "Ihr Warenkorb ist leer.",
    "Вкажіть ім'я та телефон.": "Bitte geben Sie Name und Telefon an.",
    "Stripe не налаштовано. Зверніться до адміністратора.": "Stripe ist nicht konfiguriert. Wenden Sie sich an den Administrator.",
    "Цей магазин ще не підключив прийом оплат. Зверніться до продавця.": "Dieser Shop hat noch keine Zahlungsabwicklung aktiviert. Wenden Sie sich an den Verkäufer.",
    "Не вдалося знайти товари в кошику.": "Artikel im Warenkorb konnten nicht gefunden werden.",
    "Помилка Stripe: %(error)s": "Stripe-Fehler: %(error)s",
    "Оплату скасовано. Ви можете спробувати ще раз.": "Zahlung storniert. Sie können es später versuchen.",
    "AI чатбот тимчасово недоступний. Будь ласка, спробуйте пізніше.": "AI-Chatbot ist vorübergehend nicht verfügbar. Bitte versuchen Sie es später erneut.",
    "Повідомлення порожнє": "Nachricht ist leer",
    "Чатбот тимчасово недоступний": "Chatbot ist vorübergehend nicht verfügbar",
    "Помилка налаштувань чатбота": "Fehler in der Chatbot-Konfiguration",
    "Помилка ініціалізації AI клієнта": "Fehler bei der Initialisierung des KI-Clients",
    "Помилка обробки запиту": "Fehler bei der Anfrageverarbeitung",
    "Налаштування головної сторінки збережені.": "Einstellungen der Startseite gespeichert.",
    "Назва і slug категорії обовʼязкові.": "Name und Kategorie-Slug sind erforderlich.",
    "Категорія з таким slug уже існує.": "Eine Kategorie mit diesem Slug existiert bereits.",
    "Категорія створена.": "Kategorie erstellt.",
    "Файл не обрано": "Datei nicht ausgewählt",
    "Недозволений тип файлу. Дозволено: png, jpg, jpeg, gif, webp": "Dateityp nicht zulässig. Erlaubt: png, jpg, jpeg, gif, webp",
    "Товар створено.": "Artikel erstellt.",
    "Статус товару оновлено.": "Artikelstatus aktualisiert.",
    "Товар видалено.": "Artikel gelöscht.",
    "Товар оновлено.": "Artikel aktualisiert.",
    "Категорія оновлена.": "Kategorie aktualisiert.",
    "Категорія видалена. Товари залишились без категорії.": "Kategorie gelöscht. Artikel sind nun ohne Kategorie.",
    "📦 Завдання для складу #%(task_number)s створено!": "📦 Lagertask #%(task_number)s erstellt!",
    "Статус змінено на «%(status)s».": "Status auf «%(status)s» geändert.",
    "Невірний статус.": "Ungültiger Status.",
    "Нотатки збережено.": "Notizen gespeichert.",
    "Замовлення видалено.": "Bestellung gelöscht.",
    "Заявку позначено як прочитану.": "Anfrage als gelesen markiert.",
    "Заявку видалено.": "Anfrage gelöscht.",
    "Усі заявки позначено як прочитані.": "Alle Anfragen als gelesen markiert.",
    "Прочитані заявки видалено.": "Gelesene Anfragen gelöscht.",
    "Пароль має бути мінімум 6 символів.": "Passwort muss mindestens 6 Zeichen lang sein.",
    "Паролі не співпадають.": "Passwörter stimmen nicht überein.",
    "Пароль адміністратора змінено.": "Admin-Passwort geändert.",
    "Налаштування сайту збережено.": "Website-Einstellungen gespeichert.",
    "Домен збережено. Тепер налаштуйте DNS і натисніть «Перевірити».": "Domain gespeichert. Jetzt konfigurieren Sie DNS und klicken Sie auf \"Überprüfen\".",
    "Власний домен видалено.": "Benutzerdefinierte Domain entfernt.",
    "Спочатку вкажіть домен.": "Bitte geben Sie zuerst die Domain an.",
    # Add more translations as needed
}

def apply_translations(po_file):
    """Apply manual translations to PO file."""
    with open(po_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    output = []
    i = 0
    changed = 0

    while i < len(lines):
        line = lines[i]

        # Look for msgid lines
        if line.startswith('msgid "') and not line.startswith('msgid ""'):
            # Extract msgid text
            match = re.match(r'msgid "(.+)"', line)
            if match:
                msgid_text = match.group(1)

                # Check if we have a translation
                if msgid_text in TRANSLATIONS:
                    output.append(line)  # Keep msgid line
                    i += 1

                    # Skip to msgstr line
                    while i < len(lines) and not lines[i].startswith('msgstr'):
                        output.append(lines[i])
                        i += 1

                    if i < len(lines) and lines[i].startswith('msgstr ""'):
                        # Replace empty msgstr with translation
                        translation = TRANSLATIONS[msgid_text]
                        output.append(f'msgstr "{translation}"\n')
                        changed += 1
                        i += 1
                    else:
                        output.append(lines[i])
                        i += 1
                else:
                    output.append(line)
                    i += 1
            else:
                output.append(line)
                i += 1
        else:
            output.append(line)
            i += 1

    # Write back
    with open(po_file, 'w', encoding='utf-8') as f:
        f.writelines(output)

    print(f"[OK] Applied {changed} German translations to {po_file}")
    return changed

if __name__ == '__main__':
    po_file = Path(__file__).parent / 'translations' / 'de' / 'LC_MESSAGES' / 'messages.po'
    apply_translations(str(po_file))
