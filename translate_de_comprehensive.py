#!/usr/bin/env python3
"""Comprehensive manual German translations for SmartShop."""
import re
from pathlib import Path

TRANSLATIONS = {
    # Auth & account
    "Невірний email або пароль.": "Ungültige E-Mail oder Passwort.",
    "Ви успішно вийшли з системи.": "Sie wurden erfolgreich abgemeldet.",
    "Email обов'язковий": "E-Mail erforderlich",
    "Користувач з таким email вже існує": "Ein Benutzer mit dieser E-Mail existiert bereits",
    "Пароль обов'язковий": "Passwort erforderlich",
    "Пароль має бути не менше 6 символів": "Passwort muss mindestens 6 Zeichen lang sein",
    "Пароль має бути не менше 8 символів": "Passwort muss mindestens 8 Zeichen lang sein",
    "Паролі не співпадають": "Passwörter stimmen nicht überein",
    "Реєстрація успішна! Ласкаво просимо!": "Registrierung erfolgreich! Willkommen!",
    "Вітаємо, %(name)s!": "Willkommen, %(name)s!",
    "Невірний пароль.": "Falsches Passwort.",
    "Підтвердіть, що розумієте наслідки видалення.": "Bestätigen Sie, dass Sie die Folgen des Löschens verstehen.",
    "Ваш акаунт і магазин видалено. Дякуємо, що були з нами.": "Ihr Konto und Shop wurden gelöscht. Danke, dass Sie bei uns waren.",

    # B2B registration
    "B2B реєстрація тимчасово закрита.": "B2B-Registrierung ist vorübergehend geschlossen.",
    "Назва компанії обов'язкова": "Unternehmensname erforderlich",
    "Ім'я та прізвище контактної особи обов'язкові": "Name und Nachname des Kontakts erforderlich",
    "VAT номер обов'язковий": "VAT-Nummer erforderlich",
    "VAT номер підтверджено!": "VAT-Nummer bestätigt!",
    "VAT не підтверджено: %(error)s": "VAT nicht bestätigt: %(error)s",
    "Помилка перевірки VAT: %(error)s": "Fehler bei der VAT-Überprüfung: %(error)s",
    "Реєстрація успішна! Ваша компанія верифікована.": "Registrierung erfolgreich! Ihr Unternehmen ist verifiziert.",
    "Реєстрація успішна! Ваша заявка на розгляді.": "Registrierung erfolgreich! Ihre Bewerbung wird überprüft.",
    "Дані компанії оновлено!": "Unternehmensdaten aktualisiert!",

    # Shipping/Delivery
    "Налаштування самовивозу збережено.": "Selbstabholungseinstellungen gespeichert.",
    "Невідома служба доставки.": "Unbekannter Lieferdienst.",
    "%(carrier)s вже налаштовано для цього магазину.": "%(carrier)s ist bereits für diesen Shop konfiguriert.",
    "%(carrier)s налаштовано.": "%(carrier)s ist konfiguriert.",
    "%(carrier)s оновлено.": "%(carrier)s wurde aktualisiert.",
    "Обліковий запис видалено.": "Konto gelöscht.",

    # Form validation
    "Заповніть обов'язкові поля": "Füllen Sie die erforderlichen Felder aus",
    "Заповніть обов'язкові поля: ім'я, email, повідомлення.": "Füllen Sie die erforderlichen Felder aus: Name, E-Mail, Nachricht.",

    # Contact form
    "Дякуємо! Ваше повідомлення надіслано.": "Danke! Ihre Nachricht wurde gesendet.",

    # Account status
    "Ваш акаунт деактивовано. Зверніться до підтримки.": "Ihr Konto wurde deaktiviert. Wenden Sie sich an den Support.",

    # Domain verification
    "Платформа ще не налаштувала перевірку доменів. Зверніться до підтримки.": "Plattform hat die Domänenüberprüfung noch nicht konfiguriert. Wenden Sie sich an den Support.",
    "Домен %(domain)s підтверджено і активовано! Може знадобитись кілька хвилин, щоб з'явився сертифікат.": "Domain %(domain)s bestätigt und aktiviert! Es kann einige Minuten dauern, bis das Zertifikat angezeigt wird.",
    "Домен ще не вказує на платформу (зараз резолвиться: %(resolved)s). Перевірте DNS-налаштування (A-запис на %(ip)s) і спробуйте ще раз за кілька хвилин.": "Domain verweist noch nicht auf die Plattform (wird zu %(resolved)s aufgelöst). Überprüfen Sie die DNS-Einstellungen (A-Datensatz für %(ip)s) und versuchen Sie es in einigen Minuten erneut.",
    "Stripe не налаштовано на платформі.": "Stripe ist auf der Plattform nicht konfiguriert.",
    "Помилка Stripe Connect: %(error)s": "Stripe Connect-Fehler: %(error)s",
    "Stripe підключено! Тепер ви можете приймати оплати від клієнтів.": "Stripe verbunden! Sie können jetzt Zahlungen von Kunden erhalten.",
    "Реєстрацію в Stripe ще не завершено. Заповніть усі необхідні дані та спробуйте ще раз.": "Stripe-Registrierung noch nicht abgeschlossen. Füllen Sie alle erforderlichen Daten aus und versuchen Sie es erneut.",
    "Не вдалося перевірити статус Stripe: %(error)s": "Konnte Stripe-Status nicht überprüfen: %(error)s",
    "Stripe-акаунт відв'язано від магазину.": "Stripe-Konto vom Shop getrennt.",

    # Warehouse/Tasks
    "Завдання взято в роботу": "Aufgabe übernommen",
    "Замовлення запаковано": "Bestellung verpackt",
    "Готово до відправки": "Versandbereit",
    "Завдання виконано": "Aufgabe abgeschlossen",
    "Замовлення відправлено": "Bestellung versandt",

    # Stripe payment errors
    "Stripe not available": "Stripe nicht verfügbar",
    "Invalid payload": "Ungültige Nutzlast",
    "Invalid signature": "Ungültige Signatur",

    # Settings
    "Налаштування оновлено!": "Einstellungen aktualisiert!",

    # Common UI strings
    "Додати": "Hinzufügen",
    "Видалити": "Löschen",
    "Редагувати": "Bearbeiten",
    "Зберегти": "Speichern",
    "Скасувати": "Abbrechen",
    "Назад": "Zurück",
    "Вперед": "Weiter",
    "Вихід": "Logout",
    "Профіль": "Profil",
    "Параметри": "Einstellungen",
    "Допомога": "Hilfe",
    "Про нас": "Über uns",
    "Контакти": "Kontakte",
    "Кошик": "Warenkorb",
    "Товари": "Produkte",
    "Замовлення": "Bestellungen",
    "Статус": "Status",
    "Ціна": "Preis",
    "Кількість": "Menge",
    "Разом": "Insgesamt",
    "Завантажити": "Herunterladen",
    "Завантаження": "Wird geladen...",
    "Помилка": "Fehler",
    "Успіх": "Erfolg",
    "Попередження": "Warnung",
    "Інформація": "Information",
    "Підтвердити": "Bestätigen",
    "Закрити": "Schließen",
    "Пошук": "Suche",
    "Фільтр": "Filter",
    "Сортування": "Sortierung",
    "Завжди": "Immer",
    "Невідомо": "Unbekannt",
    "Недоступно": "Nicht verfügbar",

    # Admin panel common
    "Панель адміністратора": "Admin-Panel",
    "Головна": "Startseite",
    "Магазин": "Shop",
    "Блог": "Blog",
    "Про": "Über",
    "Контакти": "Kontakte",
    "Вихід": "Abmelden",
}

def apply_comprehensive_translations(po_file):
    """Apply comprehensive German translations to PO file."""
    with open(po_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    output = []
    i = 0
    changed = 0

    while i < len(lines):
        line = lines[i]

        # Look for msgid lines (not the header msgid "")
        if line.startswith('msgid "') and i > 0 and lines[i-1].strip() != "":
            # Extract msgid text
            match = re.match(r'msgid "(.+)"', line)
            if match:
                msgid_text = match.group(1)

                # Check if we have a translation
                if msgid_text in TRANSLATIONS:
                    output.append(line)  # Keep msgid line
                    i += 1

                    # Skip comment lines and other metadata
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
    apply_comprehensive_translations(str(po_file))
