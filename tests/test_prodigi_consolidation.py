"""Synthetic cross-order copy/QA/cancel tests. No live supplier/customer access."""
from copy import deepcopy
import json
from datetime import datetime,timezone,timedelta
import pytest
import requests
import prodigi_consolidation as merge
import prodigi_preparation as prep
import prodigi_dashboard_qa as qa
import prodigi_browser as browser
from test_auto_editions_jobs import database
from test_prodigi_preparation import store
from test_prodigi_dashboard_qa import fixture,options,inserts,address


@pytest.fixture(autouse=True)
def no_live_network(monkeypatch):
    monkeypatch.setattr(requests.sessions.Session,'request',lambda *a,**k:pytest.fail('Live network is forbidden in consolidation tests'))


def pair():
    source,snap,p,evidence=fixture();source['status']='Ready for manual payment'
    so=deepcopy(p.data);so.update(createdAt='2026-11-22T01:00:00Z',allowedActions=['update','cancel'])
    target=deepcopy(source);target.update(allocation_id=2,order_id='98',item_id='87',status='Submitted',submission=dict(intent_at=prep.now(),confirmed=True,supplier_status='paused'))
    ts=deepcopy(snap);ts.update(allocation_id=2,order_reference='#SC122',job_id='e'*64)
    ts['identity'].update(order_id='122',line_id='455');target.update(snapshot=ts,fingerprint=prep.digest(ts),url_hash=prep.digest('https://fixture/target'))
    to=deepcopy(so);to.update(id='98',merchantReference='#SC122',status='paused',createdAt='2026-11-21T01:00:00Z')
    to['items'][0].update(id='87',merchantReference='455',assets=[dict(url='https://fixture/target',printArea='default',status='complete')])
    snapshots={1:snap,2:ts};identities={'123':('7',merge.destination(address())),'122':('7',merge.destination(address()))}
    class Provider:
        def __init__(self):self.orders={'99':so,'98':to};self.cancels=[];self.ack=True
        def order(self,oid):return deepcopy(self.orders[str(oid)])
        def cancel_unpaid_duplicate(self,oid):
            self.cancels.append(oid)
            if self.ack:self.orders[oid]['status']='cancelled'
            else:raise ValueError('Lost cancellation acknowledgement')
    return source,target,Provider(),snapshots,identities


def test_same_customer_and_complete_address_are_both_required():
    s,t,p,snaps,ids=pair()
    assert merge.guard([s],[t],p.order('99'),p.order('98'),ids,snaps.get)==ids['123']
    for bad in [('8',ids['123'][1]),('7',('another recipient',)+ids['123'][1][1:])]:
        changed=deepcopy(ids);changed['122']=bad
        with pytest.raises(ValueError,match='Customer or complete'):merge.guard([s],[t],p.order('99'),p.order('98'),changed,snaps.get)
    assert not p.cancels


@pytest.mark.parametrize('field,value',[('line1','9 Fixture Street'),('line2','Apartment 2'),('townOrCity','Elsewhere'),('stateOrCounty','NSW'),('postalOrZipCode','3001'),('countryCode','NZ')])
def test_every_shipping_address_component_blocks_a_mismatch(field,value):
    a=address();b=deepcopy(a);b['address'][field]=value
    assert merge.destination(a)!=merge.destination(b)


def test_company_recipient_and_incomplete_addresses_are_not_combined():
    a=address();b=deepcopy(a);b['name']='Different Recipient'
    assert merge.destination(a)!=merge.destination(b)
    assert merge.destination(a,'Company A')!=merge.destination(a,'Company B')
    del a['address']['postalOrZipCode']
    with pytest.raises(ValueError):merge.destination(a)


@pytest.mark.parametrize('change',[{'status':'in_production'},{'status':'shipped'},{'charges':[{'amount':1}]},{'shipments':[{'id':'shipment'}]},{'statusHistory':[{'status':'in_production'}]}])
def test_paid_production_and_shipping_history_are_never_eligible(change):
    s,t,p,snaps,ids=pair();order=p.order('98');order.update(change)
    with pytest.raises(ValueError):merge.guard([s],[t],p.order('99'),order,ids,snaps.get)
    assert not p.cancels


def test_shipping_intent_must_agree_and_oldest_order_must_be_the_target():
    s,t,p,snaps,ids=pair();t['snapshot']['shipping']='Express'
    with pytest.raises(ValueError,match='Standard and Express'):merge.guard([s],[t],p.order('99'),p.order('98'),ids,snaps.get)
    t['snapshot']['shipping']='Standard';p.orders['98']['createdAt']='2026-11-23T00:00:00Z'
    with pytest.raises(ValueError,match='oldest'):merge.guard([s],[t],p.order('99'),p.order('98'),ids,snaps.get)


def test_customer_identity_uses_ids_not_email_or_customer_name():
    raw=dict(id=123,customer=dict(id='gid://shopify/Customer/7'),shipping_address=dict(name='Synthetic Customer',address1='1 Fixture Street',address2='Unit 1',city='Fixture',province='VIC',zip='3000',country_code='AU'))
    assert merge.customer_identity(raw,'123')[0]=='7'
    raw['customer']={'email':'same@example.invalid','name':'Synthetic Customer'}
    with pytest.raises(ValueError,match='Customer'):merge.customer_identity(raw,'123')
    with pytest.raises(ValueError):merge.customer_identity({'raw_payload':{**raw,'id':999}},'123')


def install(store,monkeypatch):
    s,t,p,snaps,ids=pair()
    monkeypatch.setattr(merge,'supported',lambda:True)
    monkeypatch.setattr(merge,'identities',lambda _:ids)
    monkeypatch.setattr(prep,'resolve',snaps.get);monkeypatch.setattr(prep,'Client',lambda:p)
    monkeypatch.setattr(browser,'Client',lambda:p)
    with prep.connect() as c,c.cursor() as q:prep.save(q,s);prep.save(q,t)
    key=merge.admit_pending();assert key
    plan=merge.claim();assert plan['kind']=='merge-add'
    merge.permit(plan['key'],plan['token'],plan['sha256'])
    p.orders['98']['items'].append(dict(id='new-copy',merchantReference=None,sku='GLOBAL-CFP-A2',quantity=1,attributes={'color':'natural'},assets=[]))
    merge.finish(plan['key'],plan['token'])
    return key,p,snaps


def prepare_combined_qa(key,p,snaps,monkeypatch,aid=1):
    # Existing upload verification is independently covered by browser tests.
    with prep.connect() as c,c.cursor() as q:
        copied=prep.read(aid);copied.update(browser=dict(verified=True,full_image_fit_verified=True),url_hash=prep.digest('https://fixture/copied/'+str(aid)))
        prep.save(q,copied)
    p.orders['98']['items'][-1]['assets']=[dict(url='https://fixture/copied/'+str(aid),printArea='default',status='complete')]
    merge.claim() # Moves all units into one full QA batch.
    plan=qa.claim(exact_item_supported=True,batch_supported=True)
    assert len(plan['items'])==len(p.orders['98']['items'])
    qa.permit(plan['key'],plan['token'],dict(options=options(),current=p.orders['98']['shippingMethod'].lower(),target='budget'))
    p.orders['98']['shippingMethod']='budget'
    monkeypatch.setattr(qa,'identity_proof',lambda _:True)
    evidence=dict(items=[dict(item_id=i['id'],sku=i['sku'],colour=i['attributes']['color'],quality='Excellent') for i in p.orders['98']['items']],
                  shipping=dict(options=options(),selected='budget'),inserts=inserts())
    result=qa.finish(plan['key'],plan['token'],evidence)
    assert result['status']=='Ready for manual payment'


def test_full_merge_preserves_original_edition_and_certificate_identity(store,monkeypatch):
    key,p,snaps=install(store,monkeypatch)
    copied=prep.read(1)
    assert copied['order_id']=='98' and copied['item_id']=='new-copy'
    assert copied['snapshot']==snaps[1] and copied['snapshot']['order_reference']=='#SC123'
    assert p.orders['99']['status']=='draft' and not p.cancels
    prepare_combined_qa(key,p,snaps,monkeypatch)
    merge.commit_ready();merge.commit_ready()
    assert p.cancels==['99'] and p.orders['99']['status']=='cancelled'
    for aid in (1,2):
        v=prep.read(aid);assert v['status']=='Submitted' and v['order_id']=='98' and 'merge_pending' not in v
        assert v['snapshot']==snaps[aid] and len(v['submission']['items'])==2
    # Production confirmation still generates one certificate for EACH original allocation.
    import prodigi_submission as submission
    p.orders['98']['status']='in_production';certs=[]
    for aid in (1,2):
        def cert(v):certs.append(v['snapshot']['order_reference']);return 'https://cdn.shopify.com/'+str(v['allocation_id'])+'.pdf'
        submission.run(prep.read(aid),p,snaps.get,lambda _:None,certificate=cert)
    assert certs==['#SC123','#SC122']


def test_lost_cancellation_ack_is_read_back_without_a_second_post(store,monkeypatch):
    key,p,snaps=install(store,monkeypatch);prepare_combined_qa(key,p,snaps,monkeypatch)
    p.ack=False
    merge.commit_ready();merge.commit_ready()
    assert p.cancels==['99'] and p.orders['99']['status']=='draft'
    assert prep.read(1).get('merge_pending')==key
    p.orders['99']['status']='cancelled';merge.commit_ready()
    assert p.cancels==['99'] and prep.read(1)['status']=='Submitted'


def test_failed_combined_qa_never_cancels_the_original_order(store,monkeypatch):
    key,p,snaps=install(store,monkeypatch)
    with prep.connect() as c,c.cursor() as q:
        job=merge.read_job(q,key);job['phase']='QA';merge.save_job(q,key,job)
        v=prep.read(1);v['status']='Needs QA';prep.save(q,v)
    merge.commit_ready()
    assert not p.cancels and p.orders['99']['status']=='draft'


def test_binding_cannot_be_reused_for_a_different_address_product_or_allocation(store,monkeypatch):
    key,p,snaps=install(store,monkeypatch);value=prep.read(1)
    assert prep.validate_order(p.order('98'),snaps[1],'98','new-copy',binding=value['consolidation_binding'])['sku']=='GLOBAL-CFP-A2'
    wrong=deepcopy(snaps[1]);wrong['number']=99
    with pytest.raises(ValueError):prep.validate_order(p.order('98'),wrong,'98','new-copy',binding=value['consolidation_binding'])
    order=p.order('98');order['recipient']['address']['line2']='Different unit'
    with pytest.raises(ValueError):prep.validate_order(order,snaps[1],'98','new-copy',binding=value['consolidation_binding'])


def test_paid_destination_stops_at_the_last_write_guard_without_cancelling(store,monkeypatch):
    key,p,snaps=install(store,monkeypatch)
    p.orders['98']['charges']=[{'amount':10}]
    with pytest.raises(ValueError,match='unpaid'):merge.check_write(prep.read(1),p,snaps.get)
    assert not p.cancels


def test_active_status_read_lease_prevents_merger_admission(store,monkeypatch):
    s,t,p,snaps,ids=pair();t['submission']['lease_until']=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()
    monkeypatch.setattr(merge,'supported',lambda:True);monkeypatch.setattr(merge,'identities',lambda _:ids)
    monkeypatch.setattr(prep,'Client',lambda:p);monkeypatch.setattr(prep,'resolve',snaps.get)
    with prep.connect() as c,c.cursor() as q:prep.save(q,s);prep.save(q,t)
    assert merge.admit_pending() is False
    assert 'merge_pending' not in prep.read(1) and not p.cancels


def test_restart_combined_qa_preserves_all_uploaded_items_and_the_source(store,monkeypatch):
    key,p,snaps=install(store,monkeypatch);prepare_combined_qa(key,p,snaps,monkeypatch)
    with prep.connect() as c,c.cursor() as q:
        job=merge.read_job(q,key);job['phase']='Needs review';merge.save_job(q,key,job)
        v=prep.read(1);v['status']='Needs QA';prep.save(q,v)
    before=deepcopy(p.orders)
    assert merge.restart_qa({'id':'owner'},1)['status']=='Awaiting dashboard QA'
    assert p.orders==before and not p.cancels
    assert qa.claim(exact_item_supported=True,batch_supported=True)['items']


def test_stage_timings_survive_same_stage_saves_and_remain_bounded(monkeypatch):
    v={'status':'Queued'};monkeypatch.setattr(prep,'now',lambda:'2026-11-22T01:00:00+00:00');prep.measure_stage(v)
    monkeypatch.setattr(prep,'now',lambda:'2026-11-22T01:00:05+00:00');prep.measure_stage(v)
    assert v['stage_timing']['entered_at']=='2026-11-22T01:00:00+00:00'
    v['status']='Uploading';prep.measure_stage(v)
    assert v['stage_durations'][0]['elapsed_ms']==5000
    for n in range(40):v['status']='Stage '+str(n);prep.measure_stage(v)
    assert len(v['stage_durations'])==16


def test_a_third_purchase_can_join_the_same_oldest_paused_order(store,monkeypatch):
    key,p,snaps=install(store,monkeypatch);prepare_combined_qa(key,p,snaps,monkeypatch);merge.commit_ready()
    original,_,_,_,_=pair();third=deepcopy(original)
    third.update(allocation_id=3,order_id='97',item_id='86',url_hash=prep.digest('https://fixture/third'))
    third['snapshot'].update(allocation_id=3,order_reference='#SC124',job_id='d'*64,number=14,rendered_number=14)
    third['snapshot']['identity'].update(order_id='124',line_id='457');third['fingerprint']=prep.digest(third['snapshot'])
    snaps[3]=deepcopy(third['snapshot'])
    source=deepcopy(p.orders['99']);source.update(id='97',merchantReference='#SC124',status='draft',createdAt='2026-11-22T02:00:00Z')
    source['items'][0].update(id='86',merchantReference='457',assets=[dict(url='https://fixture/third',printArea='default',status='complete')]);p.orders['97']=source
    identity=('7',merge.destination(address()));monkeypatch.setattr(merge,'identities',lambda _:dict.fromkeys(('122','123','124'),identity))
    with prep.connect() as c,c.cursor() as q:prep.save(q,third)
    next_key=merge.admit_pending();assert next_key and next_key!=key
    plan=merge.claim();assert plan['order_id']=='98'
    merge.permit(plan['key'],plan['token'],plan['sha256'])
    p.orders['98']['items'].append(dict(id='third-copy',quantity=1,sku='GLOBAL-CFP-A2',merchantReference=None,attributes={'color':'natural'},assets=[]))
    merge.finish(plan['key'],plan['token']);prepare_combined_qa(next_key,p,snaps,monkeypatch,aid=3);merge.commit_ready()
    assert p.cancels==['99','97'] and len(p.orders['98']['items'])==3
    for aid,ref in ((1,'#SC123'),(2,'#SC122'),(3,'#SC124')):
        value=prep.read(aid);assert value['order_id']=='98' and value['snapshot']['order_reference']==ref
        assert value['status']=='Submitted' and len(value['submission']['items'])==3


def test_orders_pairing_heartbeat_does_not_update_the_shared_desktop_row(store,monkeypatch):
    import prodigi_preparation_api as api,product_upload_staff_queue as pairing,os_accounts
    from types import SimpleNamespace
    token='synthetic-pairing'
    with prep.connect() as c,c.cursor() as q:
        q.execute('CREATE TABLE product_upload_desktop(singleton bool,token_hash text,actor_id text,seen_at timestamptz)')
        q.execute("INSERT INTO product_upload_desktop VALUES(true,%s,'owner','2026-01-01T00:00:00Z')",(pairing.digest(token),))
    monkeypatch.setattr(os_accounts,'DEFAULT_STORE',SimpleNamespace(get_user=lambda aid:{'id':aid}))
    monkeypatch.setattr(os_accounts,'can_access_page',lambda *_:True)
    assert api.desktop(token)=={'id':'owner'}
    with prep.connect() as c,c.cursor() as q:
        q.execute('SELECT seen_at FROM product_upload_desktop');seen=q.fetchone()['seen_at']
        assert str(seen).startswith('2026-01-01')
        q.execute("SELECT value FROM app_settings WHERE key='orders_companion_seen'");assert q.fetchone()
    with pytest.raises(PermissionError):api.desktop('revoked-token')


def test_already_submitted_duplicate_is_held_before_any_destination_add(store,monkeypatch):
    s,t,p,snaps,ids=pair();s.update(status='Submitted',submission=dict(intent_at=prep.now(),confirmed=True,supplier_status='paused'))
    p.orders['99']['status']='paused'
    monkeypatch.setattr(merge,'supported',lambda:True);monkeypatch.setattr(merge,'identities',lambda _:ids)
    monkeypatch.setattr(prep,'Client',lambda:p);monkeypatch.setattr(prep,'resolve',snaps.get)
    with prep.connect() as c,c.cursor() as q:prep.save(q,s);prep.save(q,t)
    before=deepcopy(p.orders['98']);key=merge.admit_pending();plan=merge.claim()
    assert plan['kind']=='merge-hold' and plan['order_id']=='99'
    permission=merge.permit(plan['key'],plan['token'],plan['sha256'])
    assert permission['order_id']=='99' and permission['operation']=='hold-duplicate'
    assert p.orders['98']==before and not p.cancels
    merge.finish(plan['key'],plan['token'],stage='merge-hold-confirmed')
    with prep.connect() as c,c.cursor() as q:assert merge.read_job(q,key)['hold']['confirmed']
    add=merge.claim();assert add['kind']=='merge-add' and add['order_id']=='98'
    assert p.orders['98']==before # Original countdown has no read/modify API operation.


def test_an_unconfirmed_duplicate_hold_never_adds_or_cancels(store,monkeypatch):
    s,t,p,snaps,ids=pair();s.update(status='Submitted',submission=dict(intent_at=prep.now(),confirmed=True));p.orders['99']['status']='paused'
    monkeypatch.setattr(merge,'supported',lambda:True);monkeypatch.setattr(merge,'identities',lambda _:ids)
    monkeypatch.setattr(prep,'Client',lambda:p);monkeypatch.setattr(prep,'resolve',snaps.get)
    with prep.connect() as c,c.cursor() as q:prep.save(q,s);prep.save(q,t)
    key=merge.admit_pending();plan=merge.claim();merge.permit(plan['key'],plan['token'],plan['sha256'])
    merge.finish(plan['key'],plan['token'],stage='merge-hold')
    assert prep.read(1)['status']=='Needs review' and len(p.orders['98']['items'])==1 and not p.cancels


def test_cancel_adapter_rejects_paid_or_wrong_order_readbacks_without_a_post(monkeypatch):
    from prodigi_client import Client
    monkeypatch.setattr(merge,'supported',lambda:True)
    s,t,p,_,_=pair();calls=[]
    class Transport:
        def request(self,*a,**k):calls.append(a);raise AssertionError('Cancellation must not be posted')
    client=Client(key='fixture',transport=Transport())
    paid=p.order('99');paid['charges']=[{'amount':1}]
    monkeypatch.setattr(client,'order',lambda _:paid)
    with pytest.raises(ValueError):client.cancel_unpaid_duplicate('99')
    wrong=p.order('99');wrong['id']='98';monkeypatch.setattr(client,'order',lambda _:wrong)
    with pytest.raises(ValueError):client.cancel_unpaid_duplicate('99')
    assert not calls
