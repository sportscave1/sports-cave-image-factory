"""Export credential-free HTML fixtures for visual QA. Starts no server or worker."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import marketplace as core
import marketplace_views as views

OUT = ROOT / '.tmp-marketplace-static'
OUT.mkdir(exist_ok=True)
rows = []
for index, (title, price, category) in enumerate((('Collector jersey', 20000, 'jerseys'), ('Graded trading card', 45000, 'cards'), ('Numbered sporting edition', 70000, 'memorabilia'))):
    rows.append({'id': f'00000000-0000-4000-8000-{index + 1:012d}', 'title': title,
        'category': category, 'sport': 'NRL', 'team': 'Test collection', 'condition': 'Excellent',
        'price_cents': price, 'shipping_cents': 1500, 'location': 'Sydney, NSW',
        'seller_name': 'Synthetic collector', 'seller_type': 'Private collector',
        'description': 'Synthetic item for local layout verification only.', 'provenance': '',
        'photo_count': 2, 'status': 'published', 'published_at': '2026-11-20T00:00:00+00:00'})

documents = {'home.html': views.home(core.deployed_site(), [], {}),
             'browse.html': views.home(core.deployed_site(), rows, {}, browse=True),
             'sell.html': views.sell(core.deployed_site()), 'item.html': views.item(rows[0])}
assets = ROOT / 'static' / 'marketplace'
for name, document in documents.items():
    for asset in ('marketplace.css', 'marketplace-home.css', 'marketplace.js', 'collector-room-1600.webp', 'collector-room-800.webp'):
        document = document.replace(core.BASE_PATH + '/assets/' + asset, (assets / asset).as_uri())
    document = document.replace(core.BASE_PATH + '/assets/logo.webp', (assets / 'logo-320.webp').as_uri())
    for row in rows:
        for index in range(2):
            document = document.replace(core.BASE_PATH + f'/images/{row["id"]}/{index}.webp', (assets / 'collector-room-800.webp').as_uri())
    document = document.replace('action="' + core.BASE_PATH + '/browse"', 'action="' + (OUT / 'browse.html').as_uri() + '"')
    document = document.replace('href="' + core.BASE_PATH + '/browse', 'href="' + (OUT / 'browse.html').as_uri())
    document = document.replace('href="' + core.BASE_PATH + '/sell"', 'href="' + (OUT / 'sell.html').as_uri() + '"')
    document = document.replace('href="' + core.BASE_PATH + '"', 'href="' + (OUT / 'home.html').as_uri() + '"')
    # Fixtures are view-only, with all form submission intercepted before the
    # site's JS handlers. Public production endpoints are never called.
    document = document.replace('</head>', '<script>document.addEventListener("submit",function(e){e.preventDefault();e.stopImmediatePropagation();},true);</script></head>')
    (OUT / name).write_text(document, encoding='utf-8')
print((OUT / 'home.html').as_uri())
