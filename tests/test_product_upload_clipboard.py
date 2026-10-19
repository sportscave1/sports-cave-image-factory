from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
import pytest
from product_upload_clipboard import ClipboardRequests


def test_first_copy_and_repeat_use_independent_single_use_grants():
    requests = ClipboardRequests()
    user = dict(id='owner')
    codes = []
    for _ in range(3):
        code = requests.create(user, 'upload', 'version', Mock())
        codes.append(code)
        assert requests.status(code, user)['state'] == 'Waiting'
        record = requests.claim(code)
        with pytest.raises(ValueError, match='already opened'): requests.claim(code)
        requests.finish(code, record['secret'], 8)
        requests.finish(code, record['secret'], 8)  # Ack retry is idempotent.
        assert requests.status(code, user) == dict(state='Complete', count=8, error='')
    assert len(set(codes)) == 3


def test_owner_and_completion_secret_required_and_partial_copy_fails():
    requests = ClipboardRequests(); user = dict(id='owner')
    code = requests.create(user, 'upload', 'version', Mock())
    with pytest.raises(PermissionError): requests.status(code, dict(id='other'))
    record = requests.claim(code)
    with pytest.raises(PermissionError): requests.finish(code, 'wrong', 8)
    requests.finish(code, record['secret'], 7)
    assert requests.status(code, user)['state'] == 'Failed'


def test_stale_package_cancel_and_expiry_revoke_native_downloads():
    requests = ClipboardRequests(); user = dict(id='owner'); validate = Mock()
    code = requests.create(user, 'upload', 'version', validate)
    record = requests.claim(code)
    validate.side_effect = ValueError('Package changed')
    with pytest.raises(ValueError, match='changed'): requests.active(code)
    with pytest.raises(ValueError, match='changed'): requests.finish(code, record['secret'], 8)
    validate.side_effect = None
    requests.status(code, user, cancel=True)
    with pytest.raises(ValueError, match='active'): requests.active(code)
    record['expires'] = 0
    with pytest.raises(ValueError, match='expired'): requests.claim(code)


def test_concurrent_claim_has_exactly_one_winner():
    requests = ClipboardRequests()
    code = requests.create(dict(id='owner'), 'upload', 'version', Mock())
    def claim(_):
        try: requests.claim(code); return True
        except ValueError: return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(claim, range(8))) == 1


def test_real_routes_launch_claim_complete_repeat_and_cancel(monkeypatch):
    from types import SimpleNamespace
    from urllib.parse import urlsplit
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    from tests.test_product_upload_package import saved_row
    import product_upload_api as api
    import product_upload_package as packages
    import product_upload_clipboard as clipboard
    import files_upload_api as files
    import os_accounts
    row = saved_row(); version = packages.package(row)['version']
    calls = []
    async def actor(request, **kwargs):
        calls.append(kwargs)
        return dict(id='owner')
    monkeypatch.setattr(api, 'actor', actor)
    monkeypatch.setattr(os_accounts, 'can_access_page', lambda *a: True)
    monkeypatch.setattr(api, 'Intakes', lambda *_: SimpleNamespace(read=lambda *_: row))
    monkeypatch.setattr(api, 'Dropbox', lambda: object())
    monkeypatch.setattr(files, '_dropbox_context', lambda: {})
    grant = SimpleNamespace(ticket='ticket', secret='transfer-secret')
    monkeypatch.setattr(packages, 'native_grant', Mock(return_value=grant))
    monkeypatch.setattr(clipboard, 'REQUESTS', ClipboardRequests())
    app = Starlette(routes=[Route(p, e, methods=list(m)) for p, e, m in api.ROUTES])
    with TestClient(app) as client:
        headers = {'Origin': 'http://testserver'}
        for _ in range(2):
            response = client.post('/api/product-uploads/clipboard-launch', json=dict(id=row['id'], version=version), headers=headers)
            assert response.status_code == 200
            launch = response.json(); code = launch['code']
            assert urlsplit(launch['url']).fragment == code
            assert 'transfer-secret' not in launch['url']
            assert client.post('/api/product-uploads/clipboard-claim', json=dict(code=code)).status_code == 403
            response = client.post('/api/product-uploads/clipboard-claim', json=dict(code=code), headers=headers)
            assert response.status_code == 200
            secret = response.json()['secret']
            assert client.post('/api/product-uploads/clipboard-claim', json=dict(code=code), headers=headers).status_code == 409
            assert client.post('/api/product-uploads/clipboard-complete', json=dict(code=code, secret=secret, count=8), headers=headers).status_code == 200
            result = client.post('/api/product-uploads/clipboard-status', json=dict(code=code), headers=headers).json()
            assert result == dict(state='Complete', count=8, error='')
        launch = client.post('/api/product-uploads/clipboard-launch', json=dict(id=row['id'], version=version), headers=headers).json()
        client.post('/api/product-uploads/clipboard-status', json=dict(code=launch['code'], cancel=True), headers=headers)
        assert client.post('/api/product-uploads/clipboard-claim', json=dict(code=launch['code']), headers=headers).status_code == 409
    assert all(c.get('write') is True for c in calls)
