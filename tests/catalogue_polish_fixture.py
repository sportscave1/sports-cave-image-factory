"""Public storefront images/links; fabricated prices/editions. No service calls.

Titles, handles and filenames observed read-only on /collections/all, 29 Sep 2026.
Never use this fixture as current price, edition or inventory truth.
"""
import json
from pathlib import Path
from tests.test_crm_modular_catalogue import catalogue_doc, service


def products():
    cards = json.loads((Path(__file__).parent / 'fixtures/catalogue_public_cards.json').read_text(encoding='utf-8'))
    facts = service().resolve(['gid://shopify/Product/' + str(i) for i in range(1, 8)])
    for i, (p, card) in enumerate(zip(facts, cards)):
        p.update(title=card['title'], handle=card['handle'],
            url='https://www.sportscaveshop.com/products/' + card['handle'],
            image='https://cdn.shopify.com/s/files/1/0722/2332/6515/files/' + card['file'] + '?format=png',
            price='69.00', compare_at='79.00')
        p['edition'].update(next=i + 2, sold=i + 1, remaining=99 - i)
    facts[-1]['edition'] = None  # Exercise the editor-only mapping warning.
    return facts


def document():
    doc = catalogue_doc()
    doc['custom_html'] = doc['middle_sections'][0]['html'] = ''
    doc['middle_sections'][-1]['products'] = products()
    doc['campaign_key'] = 'local_polish_fixture'
    return doc
