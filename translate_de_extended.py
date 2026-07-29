#!/usr/bin/env python3
"""Extended German translations for remaining Ukrainian strings."""
import re
from pathlib import Path

TRANSLATIONS = {
    # Alerts & notifications
    "%(count)s критичних алертів!": "%(count)s kritische Warnungen!",
    "%(emoji)s CRM Alert: %(title)s - SmartShop AI": "%(emoji)s CRM-Benachrichtigung: %(title)s - SmartShop AI",
    "%(emoji)s Замовлення #%(order_id)s - статус змінено - SmartShop AI": "%(emoji)s Bestellung #%(order_id)s - Status geändert - SmartShop AI",

    # Admin/Settings
    "(IP платформи ще не налаштовано)": "(Plattform-IP noch nicht konfiguriert)",
    "(без категорії)": "(Keine Kategorie)",
    "...та ще %(count)s товарів": "...und %(count)s weitere Produkte",
    "0 = точний, 1 = креативний": "0 = Präzise, 1 = Kreativ",
    "1. Заголовок H1": "1. H1-Überschrift",
    "14 днів": "14 Tage",
    "2. Вступ": "2. Einleitung",
    "30 днів": "30 Tage",
    "3. Підзаголовки H2": "3. H2-Überschriften",
    "60 днів": "60 Tage",
    "7 днів": "7 Tage",

    # AI Settings
    "AI Assistant": "KI-Assistent",
    "AI Блогер": "KI-Blogger",
    "AI Блогер увімкнено": "KI-Blogger aktiviert",
    "AI Налаштування": "KI-Einstellungen",
    "AI Налаштування - Адмін панель": "KI-Einstellungen - Admin-Panel",
    "AI генерація": "KI-Generierung",
    "AI не налаштовано": "KI nicht konfiguriert",
    "AI не налаштовано. Додайте OPENAI_API_KEY": "KI nicht konfiguriert. Fügen Sie OPENAI_API_KEY hinzu",
    "AI-контент": "KI-Inhalt",
    "AI-продавець": "KI-Verkäufer",

    # Navigation & UI
    "About": "Über",
    "Add New": "Hinzufügen",
    "Add to cart": "In den Warenkorb",
    "Admin Panel": "Admin-Panel",
    "All Categories": "Alle Kategorien",
    "All Products": "Alle Produkte",
    "All rights reserved": "Alle Rechte vorbehalten",
    "Ask me anything...": "Frag mich alles...",
    "B2B Замовлення": "B2B-Bestellungen",
    "B2B Кабінет партнера": "B2B-Partnerkabinett",
    "B2B Партнер": "B2B-Partner",
    "B2B Партнерство": "B2B-Partnerschaft",
    "B2B Реєстрація": "B2B-Registrierung",
    "B2B налаштування": "B2B-Einstellungen",
    "B2B-кабінет": "B2B-Kabinett",
    "Blog": "Blog",
    "Cart": "Warenkorb",
    "Categories": "Kategorien",
    "Category": "Kategorie",
    "Contacts": "Kontakte",
    "Dashboard": "Dashboard",
    "Description": "Beschreibung",
    "Featured Products": "Ausgewählte Produkte",
    "Home": "Startseite",
    "How can I help you?": "Wie kann ich dir helfen?",
    "ID": "ID",
    "Latest from Blog": "Neueste aus dem Blog",
    "Learn more": "Mehr erfahren",
    "Login": "Anmelden",
    "Logout": "Abmelden",
    "Next": "Weiter",
    "No results found": "Keine Ergebnisse gefunden",
    "Orders": "Bestellungen",
    "Previous": "Zurück",
    "Products": "Produkte",
    "Quantity": "Menge",
    "Read more": "Mehr lesen",
    "Register": "Registrieren",
    "Related Products": "Verwandte Produkte",
    "Shop": "Shop",
    "Total": "Insgesamt",
    "View all": "Alle anzeigen",
    "Welcome to SmartShop AI": "Willkommen bei SmartShop AI",
    "Your intelligent shopping assistant": "Dein intelligenter Shopping-Assistent",

    # Order-related
    "B2B Замовлення": "B2B-Bestellungen",
    "ID Замовлення:": "Bestellnummer:",
    "ID замовлення": "Bestellnummer",
    "order not found": "Bestellung nicht gefunden",

    # Company/Email
    "Email компанії": "Unternehmens-E-Mail",
    "Email обов'язковий.": "E-Mail ist erforderlich.",
    "Email:": "E-Mail:",

    # SEO & Headers
    "SEO заголовок (до 60 символів)": "SEO-Titel (bis 60 Zeichen)",
    "SEO ключові слова...": "SEO-Schlüsselwörter...",
    "SEO налаштування": "SEO-Einstellungen",
    "SEO опис (до 160 символів)": "SEO-Beschreibung (bis 160 Zeichen)",
    "SEO інструкції": "SEO-Anweisungen",
    "SKU / Артикул": "SKU / Artikelnummer",
    "Hero-блок": "Hero-Block",

    # Domain & DNS
    "DNS-зміни можуть діяти від кількох хвилин до кількох годин. Після налаштування натисніть «Перевірити».": "DNS-Änderungen können einige Minuten bis Stunden dauern. Nach der Konfiguration klicken Sie auf \"Überprüfen\".",
    "WHOIS домену": "Domain WHOIS",
    "Sandbox / тестовий режим": "Sandbox / Testmodus",

    # Shipping/Delivery
    "DHL/UPS - тарифи в checkout і автоматичні лейбли": "DHL/UPS - Tarife bei Kasse und automatische Etiketten",
    "DHL/UPS з розрахунком тарифів та автоматичним створенням накладних — або безкоштовний самовивіз.": "DHL/UPS mit Tarifberechnung und automatischer Etikett-Erstellung - oder kostenlose Selbstabholung.",

    # VAT
    "VAT заповнено": "VAT ausgefüllt",
    "VAT не заповнено - запити до реєстрів можуть бути обмежені": "VAT nicht ausgefüllt - Registrierungsanfragen können eingeschränkt sein",
    "VAT номер": "Steuernummer",
    "VAT номер (ПДВ)": "Umsatzsteuer-ID",
    "VAT номер підтверджено": "Steuernummer bestätigt",
    "VAT перевірка (VIES)": "Steuernummer-Überprüfung (VIES)",

    # Financial
    "Net (дохід − витрати)": "Netto (Einnahmen − Ausgaben)",

    # Email/Contact
    "HTML/JS код, який буде вставлено перед": "HTML/JS-Code, der eingefügt wird vor",

    # Meta/Platform
    "Stripe ще не налаштовано на платформі. Зверніться до підтримки.": "Stripe ist auf der Plattform noch nicht konfiguriert. Wenden Sie sich an den Support.",
    "SmartShop AI - Ваш надійний онлайн-магазин": "SmartShop AI - Dein zuverlässiger Online-Shop",
    "SmartShop AI — SaaS-конструктор магазинів: зберіть вітрину за годину, підключіть склад, доставку, бухгалтерію, автоматичний блог та ІІ-продавця. Підписка від 19€/міс.": "SmartShop AI - SaaS-Shop-Builder: Baue einen Shop in einer Stunde, verbinde Lager, Versand, Buchhaltung, automatischen Blog und KI-Verkäufer. Abonnement ab 19€/Monat.",
    "SmartShop AI — конструктор інтернет-магазинів з ІІ-продавцем": "SmartShop AI - Online-Shop-Builder mit KI-Verkäufer",
}

def apply_extended_translations(po_file):
    """Apply extended German translations to PO file."""
    with open(po_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    output = []
    i = 0
    changed = 0

    while i < len(lines):
        line = lines[i]

        # Look for msgid lines (not the header msgid "")
        if line.startswith('msgid "') and i > 0:
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

    print(f"[OK] Applied {changed} extended German translations")
    return changed

if __name__ == '__main__':
    po_file = Path(__file__).parent / 'translations' / 'de' / 'LC_MESSAGES' / 'messages.po'
    apply_extended_translations(str(po_file))
