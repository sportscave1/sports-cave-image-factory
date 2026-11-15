"""Embed the shared skin in isolated components. Run --check in validation."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from table_design import TABLE_CSS

HOSTS = {"crm_checkout_table": "checkout", "daily_planner": "planner",
         "files_window": "files", "files_chunk_uploader": "uploads"}


def expected(source, host):
    source = re.sub(r' data-sc-table-host="[^"]*"', '', source, count=1)
    source = source.replace('<html', f'<html data-sc-table-host="{host}"', 1)
    source = re.sub(r'<style id="sc-table-design-v3">.*?</style>\s*', '', source, flags=re.S)
    return source.replace('</head>', '<style id="sc-table-design-v3">' + TABLE_CSS + '</style>\n</head>', 1)


def main():
    bad = []
    for component, host in HOSTS.items():
        path = ROOT / 'components' / component / 'index.html'
        source = path.read_text(encoding='utf8')
        updated = expected(source, host)
        if source != updated:
            bad.append(component)
            if '--check' not in sys.argv:
                with path.open('w', encoding='utf8', newline='') as output:
                    output.write(updated)
    if '--check' in sys.argv and bad:
        raise SystemExit('Outdated table skins: ' + ', '.join(bad))
    print('Table skins verified' if '--check' in sys.argv else 'Table skins synchronized')


if __name__ == '__main__':
    main()
