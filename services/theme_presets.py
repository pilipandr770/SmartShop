"""
Готові пресети дизайну вітрини: кольорові теми, шрифти, розкладки головної
сторінки. Власник магазину обирає з цього фіксованого набору (не довільний
CSS/HTML) - просто і безпечно, без ризику зламати верстку чи внести XSS.
"""
from flask_babel import lazy_gettext as _l

# lazy_gettext (не gettext) - ці словники обчислюються ОДИН РАЗ при імпорті
# модуля, до появи будь-якого запиту/локалі. Звичайний _() зафіксував би
# переклад назавжди в тій локалі, що була активна при старті процесу.
# LazyString відкладає переклад до фактичного рендеру (коли рядок
# перетворюється на str() всередині шаблону чи f-рядка) - саме тоді вже
# є активний контекст запиту з правильною мовою.

THEME_PRESETS = {
    "emerald_dark": {
        "label": _l("Смарагдова темна (за замовчуванням)"),
        "is_dark": True,
        "bg_main": "#050816",
        "bg_card": "#0b1020",
        "bg_card_hover": "#101731",
        "accent": "#10b981",
        "accent_soft": "rgba(16, 185, 129, 0.12)",
        "text_main": "#f9fafb",
        "text_muted": "#9ca3af",
        "border_soft": "rgba(148, 163, 184, 0.25)",
        "body_gradient": "radial-gradient(circle at top, #0f172a 0, #020617 45%, #000 100%)",
    },
    "slate_light": {
        "label": _l("Світла графітова"),
        "is_dark": False,
        "bg_main": "#f8fafc",
        "bg_card": "#ffffff",
        "bg_card_hover": "#f1f5f9",
        "accent": "#0891b2",
        "accent_soft": "rgba(8, 145, 178, 0.1)",
        "text_main": "#0f172a",
        "text_muted": "#64748b",
        "border_soft": "rgba(15, 23, 42, 0.12)",
        "body_gradient": "radial-gradient(circle at top, #ffffff 0, #eef2f7 60%, #e2e8f0 100%)",
    },
    "sunset_warm": {
        "label": _l("Теплий захід сонця"),
        "is_dark": True,
        "bg_main": "#1c1207",
        "bg_card": "#2b1c0f",
        "bg_card_hover": "#3a2615",
        "accent": "#f97316",
        "accent_soft": "rgba(249, 115, 22, 0.15)",
        "text_main": "#fef3e2",
        "text_muted": "#d6b896",
        "border_soft": "rgba(214, 184, 150, 0.25)",
        "body_gradient": "radial-gradient(circle at top, #2b1c0f 0, #1c1207 45%, #000 100%)",
    },
    "ocean_blue": {
        "label": _l("Океанський синій"),
        "is_dark": False,
        "bg_main": "#f0f9ff",
        "bg_card": "#ffffff",
        "bg_card_hover": "#e0f2fe",
        "accent": "#2563eb",
        "accent_soft": "rgba(37, 99, 235, 0.1)",
        "text_main": "#0c2340",
        "text_muted": "#4b6584",
        "border_soft": "rgba(37, 99, 235, 0.18)",
        "body_gradient": "radial-gradient(circle at top, #ffffff 0, #e0f2fe 100%)",
    },
    "monochrome_dark": {
        "label": _l("Монохромна темна"),
        "is_dark": True,
        "bg_main": "#0a0a0a",
        "bg_card": "#171717",
        "bg_card_hover": "#262626",
        "accent": "#e5e5e5",
        "accent_soft": "rgba(229, 229, 229, 0.12)",
        "text_main": "#fafafa",
        "text_muted": "#a3a3a3",
        "border_soft": "rgba(163, 163, 163, 0.25)",
        "body_gradient": "radial-gradient(circle at top, #171717 0, #0a0a0a 45%, #000 100%)",
    },
    "rose_light": {
        "label": _l("Ніжна рожева"),
        "is_dark": False,
        "bg_main": "#fff1f2",
        "bg_card": "#ffffff",
        "bg_card_hover": "#ffe4e6",
        "accent": "#e11d48",
        "accent_soft": "rgba(225, 29, 72, 0.1)",
        "text_main": "#1f2937",
        "text_muted": "#6b7280",
        "border_soft": "rgba(225, 29, 72, 0.15)",
        "body_gradient": "radial-gradient(circle at top, #ffffff 0, #ffe4e6 100%)",
    },
}

DEFAULT_THEME_PRESET = "emerald_dark"

FONT_PRESETS = {
    "system_sans": {
        "label": _l("Системний (за замовчуванням)"),
        "family": "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        "google_font_url": None,
    },
    "modern_serif": {
        "label": _l("Сучасний серіф"),
        "family": "'Merriweather', Georgia, serif",
        "google_font_url": "https://fonts.googleapis.com/css2?family=Merriweather:wght@400;700&display=swap",
    },
    "rounded_friendly": {
        "label": _l("Округлий дружній"),
        "family": "'Quicksand', system-ui, sans-serif",
        "google_font_url": "https://fonts.googleapis.com/css2?family=Quicksand:wght@400;600;700&display=swap",
    },
    "elegant_display": {
        "label": _l("Елегантний"),
        "family": "'Playfair Display', Georgia, serif",
        "google_font_url": "https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700&display=swap",
    },
    "techno_grotesk": {
        "label": _l("Технологічний"),
        "family": "'Space Grotesk', system-ui, sans-serif",
        "google_font_url": "https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&display=swap",
    },
}

DEFAULT_FONT_PRESET = "system_sans"

HOMEPAGE_LAYOUTS = {
    "hero_grid": {
        "label": _l("Товари сіткою (за замовчуванням)"),
        "description": _l("Великий hero-блок, 4 картки розділів, потім товари сіткою."),
    },
    "categories_first": {
        "label": _l("Спочатку категорії"),
        "description": _l("Компактний заголовок і одразу категорії з товарами - для магазинів з великим каталогом."),
    },
}

DEFAULT_HOMEPAGE_LAYOUT = "hero_grid"


def get_theme(preset_key):
    return THEME_PRESETS.get(preset_key) or THEME_PRESETS[DEFAULT_THEME_PRESET]


def get_font(preset_key):
    return FONT_PRESETS.get(preset_key) or FONT_PRESETS[DEFAULT_FONT_PRESET]


def get_layout(preset_key):
    return preset_key if preset_key in HOMEPAGE_LAYOUTS else DEFAULT_HOMEPAGE_LAYOUT
