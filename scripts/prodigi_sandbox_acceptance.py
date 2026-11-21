"""Real sandbox-only transport acceptance. No login/shared-resource operations.

Uses SC_PRODIGI_SANDBOX_KEY, loaded separately from the sandbox dashboard.
Creates one idempotent, synthetic two-item draft; never submits or pays it.
All outputs are test IDs, state and assertions; no keys or provider URLs logged.
"""
import hashlib
import json
import os
import time
import requests

BASE = 'https://api.prodigi.com/v5'
SAMPLE = 'https://pwintyimages.blob.core.windows.net/samples/stars/test-sample-grey.png'
REFERENCE = 'SC-COMPANION-SANDBOX-20261121'
LIVE_ORDER_READ_ONLY = '75236408630055936'


def run():
    key = os.environ.get('SC_PRODIGI_SANDBOX_KEY', '')
    if not key or key.startswith('live_') or key == os.environ.get('PRODIGI_API_KEY'):
        raise ValueError('A separate sandbox credential is required; production keys are rejected.')
    key = key if key.startswith('sandbox_') else 'sandbox_' + key
    session = requests.Session()
    headers = {'X-API-Key': key}
    # Verify that the known live order is outside this environment before writes.
    isolated = session.get(BASE + '/orders/' + LIVE_ORDER_READ_ONLY, headers=headers, timeout=20, allow_redirects=False)
    if isolated.status_code != 404:
        raise ValueError('Sandbox isolation was not proven; no test order was created.')
    print('PASS: known live order is inaccessible through sandbox key', flush=True)
    payload = {'merchantReference': REFERENCE, 'submit': False, 'shippingMethod': 'Standard',
        'recipient': {'name': 'Sports Cave Synthetic Acceptance', 'address': {
            'line1': '1 Example Test Street', 'townOrCity': 'Sydney', 'stateOrCounty': 'NSW',
            'postalOrZipCode': '2000', 'countryCode': 'AU'}},
        'items': [{'merchantReference': 'sandbox-line-' + str(n), 'sku': 'GLOBAL-CFP-A2',
            'quantity': 1, 'sizing': 'fitPrintArea', 'attributes': {'color': colour}}
            for n, colour in [(1, 'black'), (2, 'natural')]]}
    token = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    response = session.post(BASE + '/orders', headers={**headers, 'Idempotency-Key': token},
                            json=payload, timeout=20, allow_redirects=False)
    if response.status_code not in (200, 201, 202):
        print('create_status', response.status_code, flush=True)
        # Error details for synthetic fields only; never a provider order body.
        print('validation', response.json().get('issues', []), flush=True)
        raise ValueError('Sandbox draft creation failed.')
    order_id = str(response.json()['data']['id'])
    print('sandbox_order_id', order_id, flush=True)
    def read():
        result = session.get(BASE + '/orders/' + order_id, headers=headers, timeout=20, allow_redirects=False)
        if result.status_code != 200:
            return None
        return result.json()['data']
    order = None
    for _ in range(8):
        order = read()
        if order: break
        time.sleep(1)
    if not order or order['status'] != 'draft' or len(order.get('items', [])) != 2 or order.get('charges'):
        raise ValueError('An unpaid, two-item sandbox draft was not verified.')
    # Existing exact item IDs are updated; no add/remove/replacement operations.
    items = []
    for item in order['items']:
        url = SAMPLE + '?sc-sandbox-unit=' + item['merchantReference']
        changed = session.patch(BASE + '/orders/' + order_id + '/items/' + str(item['id']),
            headers=headers, json={'assets': [{'printArea': 'default', 'url': url}]},
            timeout=20, allow_redirects=False)
        if changed.status_code != 200:
            raise ValueError('Sandbox item artwork edit was rejected: HTTP ' + str(changed.status_code))
        current = read()
        if not current or current['status'] != 'draft' or current.get('charges'):
            raise ValueError('Sandbox edit did not retain an unpaid draft.')
        actual = next(i for i in current['items'] if i['id'] == item['id'])
        if actual.get('sku') != item.get('sku') or actual.get('attributes') != item.get('attributes'):
            raise ValueError('Sandbox artwork PATCH did not preserve the selected product/frame. Use browser upload.')
        if actual['merchantReference'] != item['merchantReference'] or actual['quantity'] != 1:
            raise ValueError('Sandbox item identity changed.')
        if not any(a.get('url') == url for a in actual.get('assets', [])):
            raise ValueError('The exact sandbox artwork was not returned.')
        items.append({'item_id': item['id'], 'line': actual['merchantReference'],
                      'asset_status': [a.get('status') for a in actual.get('assets', [])]})
    final = read()
    receipt = {'environment': 'sandbox', 'order_id': order_id, 'status': final['status'],
        'charged': bool(final.get('charges')), 'items': items, 'submitted': False,
        'live_order_modified': False, 'fixture': 'synthetic API draft, imported-order identity checked separately read-only'}
    print(json.dumps(receipt, sort_keys=True), flush=True)
    return receipt


if __name__ == '__main__':
    run()
