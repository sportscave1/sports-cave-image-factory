"""GET-only production transitions and independent certificate tracking."""
from copy import deepcopy
import pytest
import prodigi_preparation as prep
import prodigi_status_sync as sync
import prodigi_submission as submission
from test_prodigi_submission import ready
from test_prodigi_preparation import store
from test_auto_editions_jobs import database


def submitted():
    v,s,p,a=ready()
    v.update(status='Submitted',submission={'intent_at':prep.now()})
    p.data['status']='in_production'
    return v,p


def test_production_validates_then_defers_pdf_without_submit():
    v,p=submitted();saved=[]
    sync.refresh(v,p.data,lambda v:saved.append(deepcopy(v)))
    assert v['status']=='Certificate pending' and v['submission']['finalised']
    assert not p.submits and 'certificate_url' not in v


def test_completed_certificate_tracks_shipping_without_regeneration():
    v,p=submitted();v.update(status='Complete',certificate_url='https://cdn.shopify.com/certificate.pdf')
    p.data['status']='shipped'
    sync.refresh(v,p.data,lambda _:None)
    assert v['status']=='Complete' and v['submission']['supplier_status']=='shipped'
    assert v['certificate_url'].endswith('certificate.pdf') and not p.submits


@pytest.mark.parametrize('change',[{'id':'other'},{'merchantReference':'other'},{'status':'delivered-invented'}])
def test_unmatched_or_unknown_readback_cannot_complete(change):
    v,p=submitted();p.data.update(change)
    with pytest.raises(ValueError):sync.refresh(v,p.data,lambda _:None)
    assert v['status']=='Submitted' and not p.submits


def test_wrong_artwork_still_blocks_certificate():
    v,p=submitted();p.data['items'][0]['sku']='WRONG'
    sync.refresh(v,p.data,lambda _:None)
    assert v['status']=='Submission uncertain' and 'finalised' not in v['submission']


def test_one_get_per_supplier_order_and_durable_backoff(store,monkeypatch):
    v,p=submitted();v2=deepcopy(v);v2['allocation_id']=2
    # Both completed certificates can share tracking without sharing PDFs.
    for row in (v,v2):row.update(status='Complete',certificate_url='https://cdn.shopify.com/'+str(row['allocation_id'])+'.pdf')
    with prep.connect() as c,c.cursor() as q:
        for row in (v,v2):prep.save(q,row)
    calls=[]
    def order(oid):calls.append(oid);return p.data
    p.order=order
    monkeypatch.setattr(prep,'Client',lambda:p)
    monkeypatch.setattr(submission,'kick',lambda:None)
    sync.tick();sync.tick()
    assert calls==['99'] and prep.read(2)['submission']['supplier_status']=='in_production'
    assert prep.read(1)['certificate_url']!=prep.read(2)['certificate_url']


def test_outage_preserves_complete_certificate_and_last_status(store,monkeypatch):
    v,p=submitted();v.update(status='Complete',certificate_url='https://cdn.shopify.com/cert.pdf')
    v['submission']['supplier_status']='in_production'
    with prep.connect() as c,c.cursor() as q:prep.save(q,v)
    def fail(_):raise RuntimeError('network down')
    p.order=fail;monkeypatch.setattr(prep,'Client',lambda:p)
    monkeypatch.setattr(submission,'kick',lambda:None)
    sync.tick();row=prep.read(1)
    assert row['status']=='Complete' and row['submission']['supplier_status']=='in_production'
    assert row['supplier_sync']['delayed'] and row['certificate_url']==v['certificate_url']


def test_existing_certificate_not_uploaded_again():
    v,p=submitted();v['certificate_url']='https://cdn.shopify.com/cert.pdf'
    def upload(_):raise AssertionError('must not regenerate')
    submission.run(v,p,lambda _:None,lambda _:None,certificate=upload)
    assert v['status']=='Complete' and not p.submits


def test_active_submission_lease_is_never_read_or_overwritten(store,monkeypatch):
    v,p=submitted();v['submission']['lease_until']=sync.after(300)
    with prep.connect() as c,c.cursor() as q:prep.save(q,v)
    monkeypatch.setattr(prep,'Client',lambda:pytest.fail('Active job must not be touched'))
    monkeypatch.setattr(submission,'kick',lambda:None)
    sync.tick()
    assert prep.read(1)['status']=='Submitted' and 'supplier_sync' not in prep.read(1)


def test_terminal_supplier_status_stops_passive_polling(store,monkeypatch):
    v,p=submitted();v.update(status='Complete',certificate_url='https://cdn.shopify.com/cert.pdf')
    p.data['status']='completed'
    with prep.connect() as c,c.cursor() as q:prep.save(q,v)
    monkeypatch.setattr(prep,'Client',lambda:p)
    monkeypatch.setattr(submission,'kick',lambda:None)
    sync.tick()
    with prep.connect() as c,c.cursor() as q:
        q.execute("UPDATE app_settings SET value=jsonb_set(value,'{supplier_sync,next_at}','\"2020-01-01T00:00:00+00:00\"'::jsonb)")
    monkeypatch.setattr(prep,'Client',lambda:pytest.fail('Terminal order must not be polled'))
    sync.tick()
    assert prep.read(1)['submission']['supplier_status']=='completed'


def test_cancelled_order_does_not_attempt_a_certificate_or_resubmit():
    v,p=submitted();p.data['status']='cancelled'
    sync.refresh(v,p.data,lambda _:None)
    assert v['status']=='Needs review' and not p.submits and not v.get('certificate_url')


def test_one_status_clock_per_server_process(monkeypatch):
    created=[]
    class Clock:
        def __init__(self,**kwargs):created.append(kwargs)
        def is_alive(self):return True
        def start(self):pass
    monkeypatch.setattr(prep,'enabled',lambda:True)
    monkeypatch.setattr(sync,'_thread',None)
    monkeypatch.setattr(sync.threading,'Thread',Clock)
    sync.start_worker();sync.start_worker()
    assert len(created)==1 and created[0]['name']=='orders-status-clock'
