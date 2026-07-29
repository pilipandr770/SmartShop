#!/usr/bin/env python3
"""Auto-wrap Ukrainian text in remaining admin templates with _() calls."""
import re
import sys
from pathlib import Path

# Files to process (remaining unwrapped ones)
FILES = [
    'templates/admin/order_detail.html',
    'templates/admin/product_edit.html',
    'templates/admin/products.html',
    'templates/admin/shipping_account_form.html',
    'templates/admin/stats.html',
    'templates/platform_admin/dashboard.html',
    'templates/admin/warehouse/print_label.html',
    'templates/admin/warehouse/reports.html',
    'templates/admin/warehouse/stock.html',
    'templates/admin/warehouse/stock_history.html',
    'templates/admin/warehouse/task_detail.html',
    'templates/admin/warehouse/tasks.html',
]

# Cyrillic pattern (Ukrainian)
CYRILLIC = r'[А-Яа-яЁёІіЇїЄєҐґ]'

def is_already_wrapped(text):
    """Check if text is already inside {{ _(...) }}"""
    return '_(' in text or "_('" in text or '_("' in text

def wrap_text_node(text):
    """Wrap standalone Ukrainian text nodes in {{ _('...') }}"""
    if not text or not text.strip():
        return text

    # Skip if already wrapped
    if is_already_wrapped(text):
        return text

    # Check if text contains Ukrainian
    if not re.search(CYRILLIC, text):
        return text

    # Don't wrap pure HTML/whitespace
    stripped = text.strip()
    if not stripped or stripped.startswith('<') or stripped.startswith('{'):
        return text

    # Escape single quotes in the text
    escaped = stripped.replace("'", "\\'")
    return f"{{{{ _('{escaped}') }}}}"

def process_file(filepath):
    """Process a single template file and wrap Ukrainian strings."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"[ERROR] {filepath}: {e}")
        return False

    original = content

    # Pattern 1: <label>.....</label> (wrap label text)
    content = re.sub(
        r'(<label[^>]*>)([^<]*' + CYRILLIC + r'[^<]*)(<\/label>)',
        lambda m: m.group(1) + wrap_text_node(m.group(2)) + m.group(3),
        content
    )

    # Pattern 2: <h1>.....</h1>, <h2>....</h2>, <h3>....</h3>
    for tag in ['h1', 'h2', 'h3']:
        content = re.sub(
            rf'(<{tag}[^>]*>)([^<]*{CYRILLIC}[^<]*)(<\/{tag}>)',
            lambda m: m.group(1) + wrap_text_node(m.group(2)) + m.group(3),
            content
        )

    # Pattern 3: <th>.....</th> (table headers)
    content = re.sub(
        r'(<th[^>]*>)([^<]*' + CYRILLIC + r'[^<]*)(<\/th>)',
        lambda m: m.group(1) + wrap_text_node(m.group(2)) + m.group(3),
        content
    )

    # Pattern 4: <option>.....</option>
    content = re.sub(
        r'(<option[^>]*>)([^<]*' + CYRILLIC + r'[^<]*)(<\/option>)',
        lambda m: m.group(1) + wrap_text_node(m.group(2)) + m.group(3),
        content
    )

    # Pattern 5: Text inside <span>, <div>, <p> that don't have {{ inside
    content = re.sub(
        r'(>)([^<{}]*' + CYRILLIC + r'[^<{}]*)(<)',
        lambda m: m.group(1) + wrap_text_node(m.group(2)) + m.group(3),
        content
    )

    if content == original:
        print(f"[SKIP] {filepath}: no changes")
        return True

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"[OK] {filepath}: wrapped")
        return True
    except Exception as e:
        print(f"[ERROR] {filepath}: write failed: {e}")
        return False

if __name__ == '__main__':
    root = Path(__file__).parent
    success = 0

    for filepath_rel in FILES:
        filepath = root / filepath_rel
        if filepath.exists():
            if process_file(filepath):
                success += 1
        else:
            print(f"⊘ {filepath_rel}: not found")

    print(f"\n{success}/{len(FILES)} files processed")
