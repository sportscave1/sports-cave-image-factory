"""Offline recovery protocol: one Send permit, preserved receipts, bounded repair."""
from copy import deepcopy
from uuid import uuid4
import pytest
import ads_attachment_repair as repair


def job():
    return dict(stage='generating', upload=str(uuid4()), artifacts={'ad_copy.csv': {'hash':'saved'}},
        response_ids={'ad_copy.csv':'original'}, chat_url='https://chatgpt.com/g/g-p-6a6bd98cd6f081918788b544dcdecfc2/c/'+str(uuid4()))


def test_restart_and_lost_claim_reply_never_grant_send_twice():
    value=job()
    assert not repair.advance(value, {'transfer_failed':True})
    first=deepcopy(value['attachment_repair'])
    assert 'ad_copy.csv' not in first['names']
    assert repair.advance(value, {'repair_claim':first['id']})
    # Persisted server state survives both browser and server restarts.
    value=deepcopy(value)
    for _ in range(4):
        assert not repair.advance(value, {'repair_claim':first['id'],'transfer_failed':True})
    assert value['attachment_repair']['id']==first['id']
    assert value['attachment_repair']['state']=='sending'
    assert not repair.advance(value, {'repair_seen':first['id'],'repair_id':first['id'],'transfer_failed':True})
    assert value['attachment_repair']['state']=='submitted'
    assert value['artifacts']['ad_copy.csv']['hash']=='saved'
    assert value['response_ids']=={'ad_copy.csv':'original'}


def test_bounded_repairs_ignore_stale_reports_and_stop_after_two():
    value=job()
    for attempt in (1,2):
        old=value.get('attachment_repair',{}).get('id')
        repair.advance(value, {'transfer_failed':True,'repair_id':old})
        current=value['attachment_repair']['id']
        assert value['attachment_repair']['attempt']==attempt
        assert repair.advance(value, {'repair_claim':current})
        repair.advance(value, {'repair_seen':current})
        repair.advance(value, {'transfer_failed':True,'repair_id':'stale'})
        assert value['attachment_repair']['id']==current
    with pytest.raises(ValueError,match='two automatic repairs'):
        repair.advance(value, {'transfer_failed':True,'repair_id':current})


def test_ambiguous_send_and_generation_timeout_do_not_resend(monkeypatch):
    clock=[1000.0]
    monkeypatch.setattr(repair.time,'time',lambda:clock[0])
    value=job();repair.advance(value,{'transfer_failed':True})
    rid=value['attachment_repair']['id']
    assert repair.advance(value,{'repair_claim':rid})
    clock[0]+=301
    with pytest.raises(ValueError,match='no duplicate repair'):
        repair.advance(value,{'repair_claim':rid})
    clock[0]=1000;repair.advance(value,{'repair_seen':rid})
    clock[0]+=1801
    with pytest.raises(ValueError,match='30 minutes'):
        repair.advance(value,{})


def test_complete_files_or_posting_never_request_repair():
    from ads_companion_transfer import FILES
    value=job();value['artifacts']={name:{} for name in FILES}
    assert not repair.advance(value,{'transfer_failed':True})
    assert 'attachment_repair' not in value


def test_repair_then_four_receipts_continues_same_posting_once(monkeypatch):
    import design_publish_ad as ads
    import ads_companion_controls
    import meta_posting_jobs
    from ads_companion_transfer import FILES
    from types import SimpleNamespace
    monkeypatch.setattr(ads_companion_controls,'stopped',lambda _:False)
    writes=[]
    monkeypatch.setattr(ads,'write',lambda k,v:writes.append(deepcopy(v)))
    value=job();key='key'
    request=SimpleNamespace(submission_id=ads._posting_id(value['upload']))
    monkeypatch.setattr(ads,'_post_request',lambda v:request if len(v['artifacts'])==4 else None)
    submitted=[]
    monkeypatch.setattr(meta_posting_jobs,'JOBS',SimpleNamespace(
        submit=lambda r:submitted.append(r.submission_id) or r.submission_id,
        snapshot=lambda _:dict(status='CREATING')))
    first=ads._step(key,value,{},dict(transfer_failed=True),0)
    rid=first['repair']['id']
    assert ads._step(key,value,{},dict(repair_claim=rid),0)['repair_send']
    assert writes[-1]['attachment_repair']['state']=='sending'
    assert not ads._step(key,value,{},dict(repair_claim=rid),0)['repair_send']
    delivery=ads._step(key,value,{},dict(repair_seen=rid),0)
    assert delivery['recover'] and delivery['repair']['state']=='submitted'
    assert delivery['missing']==[n for n in FILES if n!='ad_copy.csv']
    value['artifacts'].update({n:{} for n in FILES if n!='ad_copy.csv'})
    ads._step(key,value,{},dict(),0)
    ads._step(key,value,{},dict(transfer_failed=True,repair_claim=rid),0)
    assert value['stage']=='posting'
    assert submitted==[request.submission_id]
    value=job();value['posting_id']='existing-posting'
    assert not repair.advance(value,{'transfer_failed':True})
    assert 'attachment_repair' not in value
