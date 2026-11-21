from copy import deepcopy
import json
from types import SimpleNamespace
import pytest
import prodigi_document_browser as docs
import prodigi_browser as browser
import prodigi_preparation as prep
from test_auto_editions_jobs import database
from test_prodigi_preparation import store,snapshot,order


@pytest.fixture
def handoff(store,monkeypatch):
    snap=snapshot();supplier=order();supplier['items'][0]['assets']=[{'url':'https://fixture/art'}]
    key=prep.PREFIX+'1';v=dict(allocation_id=1,snapshot=snap,order_id='99',item_id='88',
        status=docs.WAITING,browser={'verified':True},url_hash=prep.digest('https://fixture/art'),
        document={'url':'https://sports-cave-image-factory.onrender.com/api/prodigi-document/'+'a'*43,
            'output':{'sha256':'a'*64,'bytes':5}})
    with store() as c,c.cursor() as q:q.execute('INSERT INTO app_settings(key,value) VALUES(%s,%s::jsonb)',(key,json.dumps(v)))
    provider=SimpleNamespace(mode='live')
    monkeypatch.setattr(browser,'context',lambda _:(provider,lambda _:snap,None,False))
    monkeypatch.setattr(docs,'current',lambda *_:(snap,deepcopy(supplier),deepcopy(supplier['items'][0])))
    return key,v,supplier,store


def test_certificate_permit_is_single_use_and_bound_to_exact_bytes(handoff):
    key,v,supplier,store=handoff;plan=docs.claim()
    assert plan['kind']=='certificate' and plan['key']=='document:'+key
    assert docs.claim() is None
    with pytest.raises(ValueError,match='checksum'):docs.permit(plan['key'],plan['token'],'b'*64)
    assert docs.permit(plan['key'],plan['token'],'a'*64)=={'permitted':True}
    with pytest.raises(ValueError,match='already used'):docs.permit(plan['key'],plan['token'],'a'*64)
    with pytest.raises(PermissionError):docs.permit(plan['key'],'wrong','a'*64)


def test_existing_slip_never_gets_a_certificate_upload(handoff):
    key,v,supplier,store=handoff;supplier['packingSlip']={'url':'https://fixture/existing'}
    assert docs.claim() is None
    with store() as c,c.cursor() as q:
        q.execute('SELECT value FROM app_settings WHERE key=%s',(key,));saved=q.fetchone()['value']
    assert saved['status']=='Needs review' and not saved.get('document_browser')


def test_uncertain_certificate_upload_is_read_back_and_never_claimed_again(handoff):
    key,v,supplier,store=handoff;plan=docs.claim()
    docs.permit(plan['key'],plan['token'],'a'*64)
    result=docs.finish(plan['key'],plan['token'],'save')
    assert result['status']=='Needs review' and docs.claim() is None
    assert docs.finish(plan['key'],'wrong')['status']=='Handoff unavailable'
    with store() as c,c.cursor() as q:
        q.execute('SELECT value FROM app_settings WHERE key=%s',(key,));saved=q.fetchone()['value']
    assert saved['document_browser']['started'] and not saved['document_browser'].get('verified')


def test_staff_can_rearm_only_a_stopped_unused_certificate_permit(handoff,monkeypatch):
    key,v,supplier,store=handoff;plan=docs.claim()
    monkeypatch.setattr(prep,'require_user',lambda _:None)
    assert docs.finish(plan['key'],plan['token'],'row')['status']=='Needs review'
    assert docs.resume_unstarted({'id':'admin'},key)['status']==docs.WAITING
    with pytest.raises(PermissionError):docs.permit(plan['key'],plan['token'],'a'*64)
    fresh=docs.claim();assert fresh['token']!=plan['token']
    docs.permit(fresh['key'],fresh['token'],'a'*64)
    docs.finish(fresh['key'],fresh['token'],'save')
    with pytest.raises(ValueError,match='unused'):docs.resume_unstarted({'id':'admin'},key)


def test_certificate_readback_binds_asset_identity_and_reports_unavailable_raw_bytes(monkeypatch):
    v={'document_browser':{'started':True,'companion_sha256':'a'*64,'filename':'SC-1-certificate-'+'a'*16+'.pdf'},
       'document':{'output':{'sha256':'a'*64,'bytes':5}}}
    url='https://live-services.pwinty.com/image-library/transform/exact/image?token=fixture'
    asset={'id':'99','name':v['document_browser']['filename'],'sizeBytes':5,'mimeType':'application/pdf','url':'https://fixture/original'}
    p=SimpleNamespace(assets=lambda:[asset],asset=lambda _:{'url':url})
    monkeypatch.setattr(browser,'verify_file',lambda *_:False)
    proof=docs.verify(p,v,{'packingSlip':{'url':url}})
    assert proof['verified'] and proof['sha256']=='a'*64 and proof['supplier_original_bytes_verified'] is False
    asset['sizeBytes']=6
    with pytest.raises(ValueError,match='metadata'):docs.verify(p,v,{'packingSlip':{'url':url}})
    asset['sizeBytes']=5
    with pytest.raises(ValueError,match='one exact'):docs.verify(p,v,{'packingSlip':{'url':url.replace('/exact/','/other/')}})
    v['document_browser']['started']=False
    with pytest.raises(ValueError,match='permit'):docs.verify(p,v,{'packingSlip':{'url':url}})
