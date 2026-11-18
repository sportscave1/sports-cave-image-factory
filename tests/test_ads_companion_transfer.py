import io
import json
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PIL import Image

import ads_page
import design_publish_ad as ads
import ads_companion_transfer as transfer
import product_upload_staff_queue as uploads
from test_product_upload_staff_queue import database, store
from tests.test_ads_posting_handoff import completed_ad


@pytest.fixture
def batch(store, monkeypatch):
    import os_accounts
    import product_upload_services
    monkeypatch.setattr(ads, 'connect', store)
    monkeypatch.setattr(os_accounts.DEFAULT_STORE, 'get_user', lambda key: {'id':key})
    monkeypatch.setattr(ads, 'check_request', lambda *args: None)
    monkeypatch.setattr(uploads, 'can_control_queues', lambda user: user.get('id')=='admin')
    token=uploads.pair({'id':'admin'})
    result,workflow=completed_ad('Instant Experience')
    job=str(uuid4())
    chat=ads.PROJECT.removesuffix('/project')+'/c/'+str(uuid4())
    value=dict(upload=job,stage='generating',requester='staff',sport='NFL',country='USA',
               result=result,folder='/ads/fixture',chat_url=chat)
    with store() as conn,conn.cursor() as cur:
        cur.execute('INSERT INTO app_settings(key,value) VALUES(%s,%s::jsonb)',(ads.PREFIX+job,json.dumps(value)))
    files={'ad_copy.csv':ads_page.build_instant_experience_copy_csv(result,workflow)}
    for index,name in enumerate(ads.COVERS.values()):
        out=io.BytesIO()
        Image.new('RGB',(512,512),(index*50,100,150)).save(out,format='JPEG')
        files[name]=out.getvalue()
    remote={}
    calls=[]
    def upload(token,path,data):
        calls.append(path)
        remote[path]=dict(path_display=path,size=len(data),content_hash=transfer.content_hash(data),id='id:'+path,rev='r1')
        return remote[path]
    monkeypatch.setattr(product_upload_services,'Dropbox',lambda:SimpleNamespace(
        token='fake',context={'root_path':'/ads'},metadata_if_present=remote.get,
        api=SimpleNamespace(path_is_within_root=lambda path,root:path.startswith(root+'/'),upload_file=upload)))
    def read():
        with store() as conn,conn.cursor() as cur:
            cur.execute('SELECT value FROM app_settings WHERE key=%s',(ads.PREFIX+job,))
            return cur.fetchone()['value']
    return SimpleNamespace(token=token,job=job,chat=chat,files=files,remote=remote,calls=calls,read=read,value=value)


def send(batch,name,**overrides):
    args=dict(token=batch.token,job_id=batch.job,name=name,chat_url=batch.chat,response_id='response-1',data=batch.files[name])
    args.update(overrides)
    return transfer.receive(**args)


def test_four_receipts_survive_retries_and_resume_without_regeneration(batch):
    assert not send(batch,'ad_copy.csv')['ready']
    assert not send(batch,'ad_copy.csv')['ready']
    assert len(batch.calls)==1
    for index,name in enumerate(ads.COVERS.values()):
        receipt=send(batch,name,response_id='image-response-'+str(index))
        assert receipt['ready']==(index==2)
    assert transfer.delivery(batch.read())['missing']==[]
    assert batch.read()['detail']=='3 of 3 images collected · CSV ready'
    failed=batch.read();failed['stage']='failed'
    ads.write(ads.PREFIX+batch.job,failed)
    transfer.resume(batch.job,{'id':'admin'})
    resumed=batch.read()
    assert resumed['collect_only'] and resumed['stage']=='generating'
    assert resumed['artifacts']==failed['artifacts']
    assert resumed['chat_url']==batch.chat
    assert len(batch.calls)==4


def test_reject_wrong_token_chat_response_invalid_files_and_preserve_conflicts(batch):
    with pytest.raises(PermissionError):send(batch,'ad_copy.csv',token='x'*43)
    with pytest.raises(ValueError,match='conversation'):send(batch,'ad_copy.csv',chat_url=batch.chat[:-36]+str(uuid4()))
    send(batch,'ad_copy.csv')
    with pytest.raises(ValueError,match='response'):send(batch,'ad_copy.csv',response_id='different')
    with pytest.raises(ValueError):send(batch,'man-cave.jpg',data=b'not an image')
    path=batch.value['folder']+'/man-cave.jpg'
    batch.remote[path]=dict(path_display=path,size=123,content_hash='different',id='id:original',rev='old')
    before=deepcopy(batch.remote)
    with pytest.raises(ValueError,match='preserved'):send(batch,'man-cave.jpg')
    assert batch.remote==before
    assert 'man-cave.jpg' in transfer.delivery(batch.read())['missing']


def test_submitted_job_cannot_receive_or_restart(batch):
    value=batch.read();value.update(stage='failed',posting_id='existing-post')
    ads.write(ads.PREFIX+batch.job,value)
    with pytest.raises(ValueError,match='accepting'):send(batch,'ad_copy.csv')
    with pytest.raises(ValueError,match='Posting receipt'):transfer.resume(batch.job,{'id':'admin'})
    with pytest.raises(PermissionError):transfer.resume(batch.job,{'id':'other'})
    assert not batch.calls
