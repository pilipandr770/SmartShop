#!/usr/bin/env python3
"""Auto-translate de catalog using Google Translate API."""
import re
import sys
from pathlib import Path

try:
    from google.cloud import translate_v2 as translate
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False
    print("WARNING: google-cloud-translate not available, using free API fallback")

# Fallback: use free API via urllib
def translate_text_free(text, target_lang='de'):
    """Translate text using Google Translate free API (no auth needed)."""
    try:
        import urllib.parse
        import urllib.request
        import json

        # Use Mymemory free translation API (no key required)
        url = f"https://api.mymemory.translated.net/get?q={urllib.parse.quote(text)}&langpair=uk|{target_lang}"

        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                data = json.loads(response.read())
                if data['responseStatus'] == 200:
                    return data['responseData']['translatedText']
        except:
            pass

        return None
    except Exception as e:
        print(f"Translation error: {e}")
        return None

def translate_catalog(po_file, target_lang='de'):
    """Translate PO file msgstrs using Google Translate."""
    with open(po_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Pattern: msgid "text"\nmsgstr ""
    pattern = r'(msgid "([^"]+)")\nmsgstr ""'

    def replace_msgstr(match):
        msgid_line = match.group(1)
        text = match.group(2)

        # Skip if text is empty or already translated
        if not text or text.strip() in ['', 'msgid']:
            return match.group(0)

        # Translate
        print(f"Translating: {text[:60]}...", end=" → ")
        translated = translate_text_free(text, target_lang)

        if translated:
            print(f"OK ({translated[:40]}...)" if len(translated) > 40 else f"OK ({translated})")
            return f'{msgid_line}\nmsgstr "{translated}"'
        else:
            print("FAILED (keeping empty)")
            return match.group(0)

    new_content = re.sub(pattern, replace_msgstr, content)

    # Write back
    with open(po_file, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print(f"\n✅ Translated {po_file}")

if __name__ == '__main__':
    po_file = Path(__file__).parent / 'translations' / 'de' / 'LC_MESSAGES' / 'messages.po'

    if not po_file.exists():
        print(f"❌ File not found: {po_file}")
        sys.exit(1)

    print(f"Translating {po_file} to German...\n")
    translate_catalog(str(po_file), 'de')
    print("\nDone! Run: pybabel compile -d translations")
