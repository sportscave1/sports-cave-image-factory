from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
import pytest
from product_upload_clipboard import ClipboardRequests


def prepared():
    service=ClipboardRequests();user=dict(id='owner');validate=Mock()
    code=service.create(user,'upload','v1',validate);record=service.claim(code)
    service.native(code,record['secret'],'ready',count=8)
    return service,user,code,record,validate


def test_preparation_never_copies_repeat_clicks_require_new_command():
    service,user,code,record,_=prepared()
    for sequence in range(1,4):
        assert service.native(code,record['secret'],'poll')['command']=='wait'
        service.status(code,user,copy=True)
        assert service.native(code,record['secret'],'heartbeat')['command']=='wait'
        assert service.native(code,record['secret'],'poll')==dict(command='copy',sequence=sequence)
        assert service.native(code,record['secret'],'poll')['command']=='wait'
        service.native(code,record['secret'],'complete',count=8,sequence=sequence,copy_ms=42)
        assert service.status(code,user)['state']=='Complete'
        assert service.status(code,user)['copy_ms']==42


def test_duplicate_click_only_one_command_and_no_partial_success():
    service,user,code,record,_=prepared()
    def click(_):
        try:service.status(code,user,copy=True);return True
        except ValueError:return False
    with ThreadPoolExecutor(max_workers=8) as pool:assert sum(pool.map(click,range(8)))==1
    service.native(code,record['secret'],'poll')
    service.native(code,record['secret'],'complete',count=7,sequence=1)
    assert service.status(code,user)['state']=='Failed'


def test_owner_secret_staleness_disconnect_and_cancel():
    service,user,code,record,validate=prepared()
    with pytest.raises(PermissionError):service.status(code,dict(id='other'),copy=True)
    with pytest.raises(PermissionError):service.native(code,'wrong','poll')
    validate.side_effect=ValueError('changed')
    with pytest.raises(ValueError,match='changed'):service.active(code)
    validate.side_effect=None
    record['heartbeat']-=15
    with pytest.raises(ValueError,match='disconnected'):service.status(code,user,copy=True)
    service.status(code,user,cancel=True)
    with pytest.raises(ValueError,match='active'):service.active(code)


def test_new_product_revokes_old_copy_and_late_completion():
    service,user,code,record,_=prepared()
    service.status(code,user,copy=True)
    service.native(code,record['secret'],'poll')
    service.create(user,'new-upload','v2',Mock())
    with pytest.raises(ValueError,match='active'):service.active(code)
    with pytest.raises(ValueError,match='active'):service.native(code,record['secret'],'complete',count=8,sequence=1)


def test_routes_prepare_request_copy_acknowledge_and_repeat(monkeypatch):
    from types import SimpleNamespace
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    from tests.test_product_upload_package import saved_row
    import product_upload_api as api, product_upload_package as packages, product_upload_clipboard as clipboard
    import files_upload_api as files, os_accounts
    row=saved_row();version=packages.package(row)['version']
    async def actor(*a,**k):return dict(id='owner')
    monkeypatch.setattr(api,'actor',actor);monkeypatch.setattr(os_accounts,'can_access_page',lambda *a:True)
    monkeypatch.setattr(api,'Intakes',lambda *_:SimpleNamespace(read=lambda *_:row))
    monkeypatch.setattr(api,'Dropbox',lambda:object());monkeypatch.setattr(files,'_dropbox_context',lambda:{})
    monkeypatch.setattr(packages,'native_grant',Mock(return_value=SimpleNamespace(ticket='ticket',secret='transfer-secret')))
    monkeypatch.setattr(clipboard,'REQUESTS',ClipboardRequests())
    with TestClient(Starlette(routes=[Route(p,e,methods=list(m)) for p,e,m in api.ROUTES])) as client:
        def post(action,**body):return client.post('/api/product-uploads/clipboard-'+action,json=body,headers={'Origin':'http://testserver'})
        code=post('launch',id=row['id'],version=version).json()['code']
        assert client.post('/api/product-uploads/clipboard-claim',json=dict(code=code)).status_code==403
        secret=post('claim',code=code).json()['secret']
        assert post('claim',code=code).status_code==409
        assert post('status',code=code,copy=True).status_code==409
        assert post('complete',code=code,secret=secret,event='ready',count=8).status_code==200
        for sequence in (1,2,3):
            assert post('status',code=code,copy=True).status_code==200
            assert post('complete',code=code,secret=secret,event='poll').json()['command']=='copy'
            assert post('complete',code=code,secret=secret,event='complete',count=8,sequence=sequence).status_code==200
            assert post('status',code=code).json()['state']=='Complete'
        post('status',code=code,cancel=True)
        assert post('complete',code=code,secret=secret,event='poll').status_code==409
