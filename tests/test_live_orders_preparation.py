import pytest
import prodigi_preparation as prep
import prodigi_browser as browser
from test_prodigi_preparation import store,snapshot
from test_auto_editions_jobs import database


def test_live_preflight_failure_is_recorded_before_any_supplier_upload(store,monkeypatch):
    monkeypatch.setattr(prep,'require_user',lambda _:None)
    monkeypatch.setattr(prep,'enabled',lambda:True)
    monkeypatch.setattr(prep,'resolve',lambda _:snapshot())
    monkeypatch.setattr(prep,'Client',lambda:object())
    monkeypatch.setattr('prodigi_full_qa.live_enabled',lambda:True)
    def reject(*_):raise ValueError('Higher-resolution master required')
    monkeypatch.setattr('prodigi_full_qa.native_gate',reject)
    result=prep.request({'id':'staff'},1)
    saved=prep.read(1)
    assert result['status']=='Needs QA' and saved['last_failure']['stage']=='preflight'
    assert saved['last_failure']['message']=='Higher-resolution master required'
    assert not saved.get('browser') and not saved.get('write_intent')


def test_source_failure_is_saved_even_before_a_preparation_can_be_created(store,monkeypatch):
    monkeypatch.setattr(prep,'require_user',lambda _:None)
    monkeypatch.setattr(prep,'enabled',lambda:True)
    def reject(*_):raise ValueError('Source profile requires review')
    monkeypatch.setattr(prep,'_request',reject)
    with pytest.raises(ValueError):prep.request({'id':'staff'},1)
    with pytest.raises(ValueError):prep.request({'id':'staff'},1)
    assert prep.read(1) is None
    failure=prep.request_failure(1)
    assert len(failure['history'])==2
    assert failure['last_failure']['stage']=='request' and failure['message']=='Source profile requires review'
    from orders_prodigi_grid import batch_status
    assert batch_status([1])['1']['status']=='Needs review'
    monkeypatch.setattr(prep,'_request',lambda *_:{'status':'Queued'})
    assert prep.request({'id':'staff'},1)['status']=='Queued'
    assert prep.request_failure(1) is None


def test_disabled_test_handoff_cannot_reach_a_provider(monkeypatch):
    monkeypatch.delenv('SPORTS_CAVE_PRODIGI_SANDBOX_ENABLED',raising=False)
    with pytest.raises(ValueError,match='disabled'):browser.context('prodigi_sandbox_test:00000000-0000-4000-8000-000000000001')


@pytest.mark.parametrize('prefix',['','document:'])
def test_stale_test_receipts_are_acknowledged_without_blocking_live_worker(monkeypatch,prefix):
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    import prodigi_preparation_api as api
    monkeypatch.delenv('SPORTS_CAVE_PRODIGI_SANDBOX_ENABLED',raising=False)
    monkeypatch.setattr(api,'desktop',lambda _:None)
    monkeypatch.setattr(browser,'context',lambda _:pytest.fail('Stopped receipts must not reach supplier'))
    client=TestClient(Starlette(routes=[Route('/finish',api.browser_action,methods=['POST'])]))
    response=client.post('/finish',headers={'Authorization':'Bearer '+'a'*43},json={'key':prefix+'prodigi_sandbox_test:00000000-0000-4000-8000-000000000001','token':'b'*43})
    assert response.status_code==200 and response.json()=={'status':'Stopped'}
