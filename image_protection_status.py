"""Explicit public check, called only by the admin settings-page button."""
from datetime import datetime, timezone
from html.parser import HTMLParser
import re
import requests
from image_protection import PUBLIC_ORIGIN


def verify_dev():
    checked=datetime.now(timezone.utc).isoformat(timespec='seconds')
    try:
        with requests.Session() as session:
            page=session.get('https://www.sportscaveshop.com/?preview_theme_id=189335863603',timeout=(3,8))
            page.raise_for_status()
            theme=re.search(r'Shopify\.theme\s*=\s*\{[^}]*["\']id["\']\s*:\s*189335863603\b',page.text)
            class Scripts(HTMLParser):
                def __init__(self):
                    super().__init__();self.sources=[]
                def handle_starttag(self,tag,attrs):
                    if tag=='script': self.sources.append(dict(attrs).get('src',''))
            parser=Scripts();parser.feed(page.text)
            if not theme:
                return f'Unable to verify DEV theme identity · Checked {checked}'
            if PUBLIC_ORIGIN+'/storefront-protection.js' not in parser.sources:
                return f'Not detected on DEV · Checked {checked}'
            config=session.get(PUBLIC_ORIGIN+'/api/storefront-protection/config',timeout=(3,8))
            config.raise_for_status()
            return f'Script installed on Shopify DEV · Config reachable · Checked {checked}'
    except Exception:
        return f'Unable to verify · Checked {checked}'
