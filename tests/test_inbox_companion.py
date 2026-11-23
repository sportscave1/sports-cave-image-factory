"""Synthetic inbox/order changes only. Never read a real mailbox or contact Prodigi."""
from copy import deepcopy
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace
import json
import pytest
import requests
import inbox_companion as inbox
import inbox_companion_policy as policy
REAL_SUPPLIER=inbox.supplier
from test_auto_editions_jobs import database
from test_prodigi_preparation import store

OLD=dict(name='Fixture Customer',email='fixture@example.test',phoneNumber='+61000000000',
         address=dict(line1='1 Old Street',line2='Unit 1',townOrCity='Sydney',stateOrCounty='NSW',postalOrZipCode='2000',countryCode='AU'))
ADDRESS='Please update my shipping address:\nAddress: 2 New Street\nCity: Mount Lawley\nState: WA\nPostcode: 6050\nCountry: Australia'

@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(requests.sessions.Session,'request',lambda *a,**kw:pytest.fail('Live network forbidden'))
    monkeypatch.delenv('SPORTS_CAVE_INBOX_COMPANION_ENABLED',raising=False)

@pytest.mark.parametrize('subject,body,kind',[
    ('Order SC123','When will my order arrive?','ignore'),
    ('Order SC123',ADDRESS,'address'),
    ('Change order','Please change my frame to black','hold'),
    ('Order cancellation','Please cancel my order','hold'),
    ('Order','Can I switch to the larger size?','hold'),
    ('Order',ADDRESS+'\nAlso change the frame.','hold'),
    ('Order','Please change my order','hold'),
    ('Thanks','Thank you\nOn Monday a customer wrote:\nPlease cancel my order','ignore'),
    ('Order','I need a refund','hold'),
    ('Order','Could you update me on my order?','ignore'),
    ('Order','Please confirm my order status','ignore'),
    ('Order',"Don't change my address\n"+ADDRESS,'hold'),
    ('Re: Change my address SC123','Thanks, all good now','ignore'),
    ('Order SC123','My new address is:\n2 New Street\nSydney NSW 2000\nAustralia','address'),
    ('Order SC123','Please ship to:\n2 New Street\nSydney NSW 2000\nAustralia','address'),
    ('Order SC123','Could I have a white frame?','hold'),
    ('Re: New address SC123','Thanks for sending to my new address','ignore'),
])
def test_request_scope(subject,body,kind):assert policy.classify(subject,body)['kind']==kind

def test_complete_address_preserves_contact_and_clears_old_unit():
    result=policy.address(ADDRESS,OLD)
    assert result['name']==OLD['name'] and result['email']==OLD['email'] and result['phoneNumber']==OLD['phoneNumber']
    assert result['address']['line1']=='2 New Street' and result['address']['line2']==''

@pytest.mark.parametrize('body',[
    ADDRESS.replace('Country: Australia','Country: United States'),
    ADDRESS.replace('Postcode: 6050',''),ADDRESS+'\nAddress: 3 Conflicting Street',
    ADDRESS.replace('Address: 2 New Street','Address: unknown'),ADDRESS.replace('Postcode: 6050','Postcode: 12345'),
    'Please update my address to 2 New Street',
])
def test_incomplete_conflicting_and_country_change_need_review(body):assert policy.address(body,OLD) is None

def test_common_au_block_does_not_split_multiword_suburb_or_state():
    result=policy.address('Please update my address\n2 New Street\nMount Lawley Western Australia 6050\nAustralia',OLD)
    assert result['address']['townOrCity']=='Mount Lawley'
    assert result['address']['stateOrCounty']=='Western Australia'

def header():return dict(uid='7',uidvalidity='1',folder='INBOX',subject='Order SC123',sender=dict(name='Fixture Customer',email='fixture@example.test'),
                         reply_to=[],message_id='<fixture@example.test>',references=[],in_reply_to=[],to=[],cc=[])
def matched():return dict(shopify_order_id='123',order_name='#SC123',customer_email='fixture@example.test',
                         created_at=datetime.now(timezone.utc).isoformat(),fulfillment_status=None)

@pytest.mark.parametrize('case',['different_sender','different_reply_to','automated','two_orders','two_numbers','old_order','fulfilled'])
def test_ambiguous_or_untrusted_message_never_matches(case):
    h=header();orders=[matched()]
    if case=='different_sender':h['sender']['email']='other@example.test'
    if case=='different_reply_to':h['reply_to']=[dict(email='other@example.test')]
    if case=='automated':h['automated']=True
    if case=='two_orders':h['subject']='My order';orders.append({**matched(),'shopify_order_id':'124','order_name':'#SC124'})
    if case=='two_numbers':h['subject']='SC123 and SC124'
    if case=='old_order':orders[0]['created_at']=(datetime.now(timezone.utc)-timedelta(days=15)).isoformat()
    if case=='fulfilled':orders[0]['fulfillment_status']='fulfilled'
    assert policy.match_order(h,ADDRESS,orders) is None

def test_exact_customer_order_match():assert policy.match_order(header(),ADDRESS,[matched()])['shopify_order_id']=='123'

def test_reply_with_retained_subject_does_not_replay_old_instructions():
    assert policy.classify('Change address SC123','Thank you',is_reply=True)['kind']=='ignore'

@pytest.mark.parametrize('results,trusted,expected',[
    ([],['mail.example.test'],False),
    (['mail.example.test; dmarc=pass header.from=example.test'],[],False),
    (['other.example.test; dmarc=pass header.from=example.test'],['mail.example.test'],False),
    (['mail.example.test; dmarc=fail header.from=example.test'],['mail.example.test'],False),
    (['mail.example.test; dmarc=pass header.from=other.test'],['mail.example.test'],False),
    (['mail.example.test; dmarc=pass header.from=example.test'],['mail.example.test'],True),
    (['mail.example.test; dkim=pass header.d=example.test'],['mail.example.test'],True),
    (['mail.example.test; dkim=pass header.d=other.test'],['mail.example.test'],False),
    (['mail.example.test; spf=pass smtp.mailfrom=fixture@example.test'],['mail.example.test'],False),
    (['mail.example.test; dkim=fail header.d=example.test'],['mail.example.test'],False),
    (['mail.example.test; dmarc=fail header.from=example.test; dkim=pass header.d=example.test'],['mail.example.test'],False),
    (['untrusted; dmarc=fail header.from=example.test','mail.example.test; dmarc=pass header.from=example.test'],['mail.example.test'],False),
])
def test_provider_authentication_not_just_a_matching_from_address(results,trusted,expected):
    from email.message import EmailMessage
    message=EmailMessage()
    message['Received']='from upstream.example.test by mail.example.test with ESMTPS'
    for result in results:message['Authentication-Results']=result
    assert policy.verified_sender(message,'fixture@example.test',trusted) is expected

def test_unverified_sender_cannot_trigger_supplier_changes(store,monkeypatch):
    job,_,_=fixture(monkeypatch);job['sender_verified']=False;persist(job)
    monkeypatch.setattr(inbox,'supplier',lambda *a:pytest.fail('No supplier action for an unverified sender'))
    assert inbox.plan(job) is None
    assert inbox.read(job['key'])['message']=='Customer request · sender verification required'

def test_passing_assertion_from_a_different_receiving_hop_is_not_trusted():
    from email.message import EmailMessage
    message=EmailMessage();message['Received']='from sender.example.test by actual.example.test with ESMTPS'
    message['Authentication-Results']='forged.example.test; dkim=pass header.d=example.test'
    assert not policy.verified_sender(message,'fixture@example.test',['forged.example.test'])

def test_activation_captures_cursor_before_enabling_the_desktop_alarm(store,monkeypatch):
    import os_accounts,support_email_provider
    monkeypatch.setenv('SPORTS_CAVE_INBOX_COMPANION_ENABLED','true')
    monkeypatch.setenv('SPORTS_CAVE_INBOX_AUTH_SERVERS','mail.example.test')
    monkeypatch.setattr(os_accounts,'can_access_page',lambda *a:True)
    def baseline(cursor):
        assert cursor is None and not inbox.read(inbox.SETTING).get('enabled')
        return dict(uidvalidity='1',last_uid=42)
    monkeypatch.setattr(support_email_provider,'ImapProvider',lambda *a,**kw:SimpleNamespace(notification_snapshot=baseline))
    inbox.configure({'id':'owner'},True)
    assert inbox.read(inbox.SETTING)['cursor']=={'uidvalidity':'1','last_uid':42}
    assert inbox.read(inbox.SETTING)['enabled'] is True

def test_metadata_contains_structured_fields_not_email_prose():
    result=policy.proposed_address(ADDRESS+'\nThis is private unrelated prose')
    assert result and 'private' not in json.dumps(result)
    assert result['name']==''

def persist(job):
    with inbox.prep.connect() as c,c.cursor() as q:
        inbox.save(q,job['key'],job);inbox.flag(q,job,'Paused customer request')

def fixture(monkeypatch):
    key=inbox.PREFIX+'a'*64
    job=dict(key=key,header=header(),shopify_order_id='123',order_name='#SC123',kind='address',sender_verified=True,
             proposed=policy.proposed_address(ADDRESS),targets={},actor='owner',state='pending')
    supplier=dict(id='99',merchantReference='123',status='paused',recipient=deepcopy(OLD),
                  items=[dict(id='88',sku='GLOBAL-CFP-A2',quantity=1),dict(id='89',sku='GLOBAL-CFP-A2',quantity=1)],charges=[])
    units=[dict(order_id='99',item_id=i,status='Submitted') for i in ('88','89')]
    monkeypatch.setattr(inbox,'preparations',lambda _:deepcopy(units))
    monkeypatch.setattr(inbox,'supplier',lambda *a:deepcopy(supplier))
    return job,supplier,units

def test_address_requires_one_use_permit_saved_readback_and_all_items_unchanged(store,monkeypatch):
    job,order,_=fixture(monkeypatch);persist(job)
    plan=inbox.plan(job)
    assert plan['action']=='address'
    assert inbox.permit(plan['key'],plan['token'],'99')['permitted']
    with pytest.raises(ValueError,match='already used'):inbox.permit(plan['key'],plan['token'],'99')
    order['recipient']=plan['recipient']
    confirmations=[];monkeypatch.setattr(inbox,'confirm',lambda j:confirmations.append(j))
    assert inbox.finish(plan['key'],plan['token'],'99',{'address_saved':True})['confirmed']
    assert len(confirmations)==1
    assert inbox.finish(plan['key'],plan['token'],'99',{'address_saved':True})['confirmed']
    assert len(confirmations)==1

@pytest.mark.parametrize('case',['changed_item','changed_contact','production','missing_permit','missing_evidence'])
def test_bad_readback_never_confirms_or_emails(store,monkeypatch,case):
    job,order,_=fixture(monkeypatch);persist(job);plan=inbox.plan(job)
    if case!='missing_permit':inbox.permit(plan['key'],plan['token'],'99')
    order['recipient']=plan['recipient']
    if case=='changed_item':order['items'][1]['sku']='WRONG'
    if case=='changed_contact':order['recipient']['email']='other@example.test'
    if case=='production':order['status']='in_production'
    monkeypatch.setattr(inbox,'confirm',lambda _:pytest.fail('No confirmation before complete verification'))
    assert not inbox.finish(plan['key'],plan['token'],'99',{} if case=='missing_evidence' else {'address_saved':True})['confirmed']
    assert inbox.read(job['key'])['state']=='review'

def test_uncertain_save_never_issues_another_browser_plan(store,monkeypatch):
    job,_,_=fixture(monkeypatch);persist(job);plan=inbox.plan(job)
    inbox.permit(plan['key'],plan['token'],'99')
    assert inbox.plan(inbox.read(job['key'])) is None
    assert inbox.read(job['key'])['state']=='review'

def test_draft_is_locally_blocked_without_changing_upload(store,monkeypatch):
    job,order,_=fixture(monkeypatch);order['status']='draft';persist(job)
    assert inbox.plan(job) is None
    assert inbox.read(inbox.FLAG+'123')['blocking']

def test_incomplete_address_becomes_hold_not_a_guessed_edit(store,monkeypatch):
    job,_,_=fixture(monkeypatch);job['proposed']=None;persist(job)
    plan=inbox.plan(job)
    assert plan['action']=='hold' and plan['recipient'] is None

def test_other_change_pauses_whole_supplier_order_preserving_identical_items(store,monkeypatch):
    job,_,_=fixture(monkeypatch);job['kind']='hold';persist(job);plan=inbox.plan(job)
    inbox.permit(plan['key'],plan['token'],'99')
    assert inbox.finish(plan['key'],plan['token'],'99',{'indefinite_hold':True})['confirmed']
    assert inbox.read(inbox.FLAG+'123')['blocking']
    assert inbox.read(job['key'])['message']=='Paused customer request · review required'

def test_newer_customer_message_retires_old_permit(store,monkeypatch):
    job,_,_=fixture(monkeypatch);persist(job);plan=inbox.plan(job)
    newer={**job,'key':inbox.PREFIX+'b'*64,'header':{**header(),'uid':'8'}};persist(newer)
    with pytest.raises(ValueError,match='newer'):inbox.permit(plan['key'],plan['token'],'99')

def test_existing_order_submission_has_zero_extra_reads_when_disabled(monkeypatch):
    monkeypatch.setattr(inbox,'read',lambda _:pytest.fail('No extra Orders I/O with feature off'))
    inbox.submission_guard({'snapshot':{'identity':{'order_id':'123'}}})

def test_flag_fences_new_submission_when_enabled(store,monkeypatch):
    monkeypatch.setenv('SPORTS_CAVE_INBOX_COMPANION_ENABLED','true')
    job,_,_=fixture(monkeypatch);persist(job)
    with pytest.raises(ValueError,match='Paused customer request'):inbox.submission_guard({'snapshot':{'identity':{'order_id':'123'}}})
    with pytest.raises(ValueError,match='Paused customer request'):inbox.submission_guard({'snapshot':{'identity':{'order_id':'gid://shopify/Order/123'}}})

def test_full_shopify_gid_and_numeric_order_id_find_the_same_preparations(store):
    with store() as c,c.cursor() as q:
        inbox.save(q,'prodigi_prepare:1',dict(snapshot={'identity':{'order_id':'gid://shopify/Order/123'}},allocation_id=1))
        inbox.save(q,'prodigi_prepare:2',dict(snapshot={'identity':{'order_id':'123'}},allocation_id=2))
        inbox.save(q,'prodigi_prepare:3',dict(snapshot={'identity':{'order_id':'124'}},allocation_id=3))
    assert {v['allocation_id'] for v in inbox.preparations('123')}=={1,2}
    assert {v['allocation_id'] for v in inbox.preparations('gid://shopify/Order/123')}=={1,2}
    assert inbox.preparations('gid://shopify/LineItem/123')==[]

def test_supplier_reference_accepts_the_existing_hashless_order_name_convention(monkeypatch):
    import prodigi_client
    job=dict(shopify_order_id='123',header=header())
    units=[dict(order_id='99',item_id='88',snapshot={'order_reference':'#SC123','identity':{'order_id':'gid://shopify/Order/123'}})]
    order=dict(id='99',merchantReference='SC123',recipient=deepcopy(OLD),items=[dict(id='88')])
    monkeypatch.setattr(inbox,'preparations',lambda _:units)
    monkeypatch.setattr(prodigi_client,'Client',lambda:SimpleNamespace(order=lambda _:order))
    assert REAL_SUPPLIER(job,'99')['merchantReference']=='SC123'

def test_uid_baseline_does_not_replay_old_mail(store,monkeypatch):
    config={'enabled':True,'actor':'owner','cursor':None}
    imap=SimpleNamespace(notification_snapshot=lambda _:dict(uidvalidity='1',last_uid=40,messages=[]))
    inbox.scan(config,imap,lambda **k:pytest.fail('Do not replay historical orders'))
    assert inbox.read(inbox.SETTING)['cursor']=={'uidvalidity':'1','last_uid':40}

def test_saved_nathan_signature_is_used_in_confirmation(store,monkeypatch):
    import support_email_store,support_email_provider,support_email_durable
    from support_email_compose import default_settings
    job,_,_=fixture(monkeypatch)
    job['targets']={'99':{'state':'confirmed'}};persist(job)
    settings=default_settings();settings['signatures']['nathan']['html']='<p>Existing Nathan signature</p>'
    monkeypatch.setattr(support_email_provider,'load_configuration',lambda:SimpleNamespace(address='hello@example.test'))
    monkeypatch.setattr(support_email_store,'load_email_settings',lambda *a:(settings,None))
    prepared=[]
    monkeypatch.setattr(support_email_durable.REGISTRY.store,'prepare',lambda *a,**kw:prepared.append((a,kw)))
    inbox.confirm(job)
    assert len(prepared)==1 and prepared[0][1]['policy']=='append'
    mime=prepared[0][0][2]
    assert mime['recipients']==['fixture@example.test']
    from email.parser import BytesParser
    from email.policy import default
    assert 'Existing Nathan signature' in BytesParser(policy=default).parsebytes(mime['bytes']).get_body(preferencelist=('plain',)).get_content()
    assert inbox.read(inbox.FLAG+'123')['blocking'] is False

def test_saved_flags_are_visible_in_orders_without_changing_item_checks():
    from orders_prodigi_grid import action_state
    result=action_state({'order_id':'99','status':'Submitted','_inbox':{'blocking':True,'paused':True,'label':'Paused customer request'}})
    assert result['label']=='Paused customer request' and result['action']==''

@pytest.mark.parametrize('case',['good','extra_item','other_email','other_reference','other_supplier','missing_sibling'])
def test_real_supplier_scope_covers_every_numbered_item_and_customer(monkeypatch,case):
    import prodigi_client
    job=dict(shopify_order_id='123',header=header())
    units=[dict(order_id='99',item_id=i,snapshot={'order_reference':'#SC123'}) for i in ('88','89')]
    order=dict(id='99',merchantReference='123',recipient=deepcopy(OLD),items=[dict(id='88'),dict(id='89')])
    if case=='extra_item':order['items'].append(dict(id='90'))
    if case=='other_email':order['recipient']['email']='other@example.test'
    if case=='other_reference':order['merchantReference']='124'
    if case=='other_supplier':order['id']='100'
    if case=='missing_sibling':units.pop()
    monkeypatch.setattr(inbox,'preparations',lambda _:units)
    monkeypatch.setattr(prodigi_client,'Client',lambda:SimpleNamespace(order=lambda _:order))
    if case=='good':assert REAL_SUPPLIER(job,'99')['id']=='99'
    else:
        with pytest.raises(ValueError):REAL_SUPPLIER(job,'99')

def test_new_message_id_is_deduplicated_across_copies_and_body_is_not_persisted(store):
    config=dict(enabled=True,actor='owner',changed_at='activation',cursor=dict(uidvalidity='1',last_uid=6))
    with inbox.prep.connect() as c,c.cursor() as q:inbox.save(q,inbox.SETTING,config)
    h1=header();h2={**header(),'uid':'8'};reads=[]
    imap=SimpleNamespace(configuration=SimpleNamespace(address='hello@example.test'),
       notification_snapshot=lambda _:dict(uidvalidity='1',last_uid=8,messages=[h1,h2]),
       notification_target=lambda validity,uid,message_id:dict(h1 if uid=='7' else h2),
       read_message=lambda h,**kw:(reads.append(h['uid']) or dict(text=ADDRESS+'\nPrivate unrelated prose',warnings=[])))
    inbox.scan(config,imap,lambda **kw:[matched()])
    jobs=inbox.pending()
    assert len(jobs)==1 and reads==['7']
    assert 'Private unrelated prose' not in json.dumps(jobs) and 'text' not in jobs[0]
    assert inbox.read(inbox.SETTING)['cursor']['last_uid']==8

def test_large_arrival_batch_keeps_unprocessed_messages_behind_cursor(store):
    config=dict(enabled=True,actor='owner',changed_at='activation',cursor=dict(uidvalidity='1',last_uid=6))
    with inbox.prep.connect() as c,c.cursor() as q:inbox.save(q,inbox.SETTING,config)
    messages=[{**header(),'uid':str(i),'message_id':f'<fixture{i}@example.test>'} for i in range(7,17)]
    imap=SimpleNamespace(configuration=SimpleNamespace(address='hello@example.test'),
        notification_snapshot=lambda _:dict(uidvalidity='1',last_uid=16,messages=messages),
        notification_target=lambda validity,uid,message_id:next(h for h in messages if h['uid']==uid),
        read_message=lambda h,**kw:dict(text='When will my order arrive?',warnings=[]))
    inbox.scan(config,imap,lambda **kw:pytest.fail('A status question is not a change request'))
    assert inbox.read(inbox.SETTING)['cursor']['last_uid']==11

def test_all_split_supplier_orders_must_finish_before_reply(store,monkeypatch):
    import support_email_provider
    job,_,units=fixture(monkeypatch);persist(job)
    units.append(dict(order_id='100',item_id='90',status='Submitted'))
    job['targets']={'99':{'state':'confirmed'}}
    monkeypatch.setattr(support_email_provider,'load_configuration',lambda:pytest.fail('No reply until all supplier orders confirm'))
    inbox.confirm(job)
    assert inbox.read(inbox.FLAG+'123')['blocking']

def test_split_orders_all_preflight_before_the_first_address_write(store,monkeypatch):
    job,order,units=fixture(monkeypatch);persist(job)
    units.append(dict(order_id='100',item_id='90',status='Submitted'))
    second={**deepcopy(order),'id':'100','status':'in_production'}
    monkeypatch.setattr(inbox,'supplier',lambda _,supplier_id:deepcopy(order if supplier_id=='99' else second))
    assert inbox.plan(job) is None
    assert inbox.read(job['key'])['targets']=={}

def test_split_countries_are_held_consistently_before_any_address_edit(store,monkeypatch):
    job,order,units=fixture(monkeypatch);persist(job)
    units.append(dict(order_id='100',item_id='90',status='Submitted'))
    second={**deepcopy(order),'id':'100'};second['recipient']['address']['countryCode']='US'
    monkeypatch.setattr(inbox,'supplier',lambda _,supplier_id:deepcopy(order if supplier_id=='99' else second))
    assert inbox.plan(job)['action']=='hold'
    assert inbox.read(job['key'])['kind']=='hold'

def test_mailbox_reconnect_and_one_supplier_failure_do_not_starve_other_requests(monkeypatch):
    import os_accounts,support_email_provider
    from prodigi_client import ProdigiError
    monkeypatch.setattr(inbox.prep,'require_user',lambda _:None)
    monkeypatch.setattr(os_accounts,'can_access_page',lambda *a:True)
    monkeypatch.setattr(inbox,'available',lambda:True)
    monkeypatch.setattr(inbox,'read',lambda _:dict(enabled=True,actor='owner'))
    monkeypatch.setattr(support_email_provider,'ImapProvider',lambda *a,**kw:object())
    monkeypatch.setattr(inbox,'scan',lambda *a:(_ for _ in ()).throw(support_email_provider.MailboxError('Synthetic outage')))
    monkeypatch.setattr(inbox,'pending',lambda:['unavailable','ready'])
    def plan(job):
        if job=='unavailable':raise ProdigiError('Synthetic supplier outage')
        return {'order_id':'99'}
    monkeypatch.setattr(inbox,'plan',plan)
    assert inbox.tick({'id':'owner'})['browser']=={'order_id':'99'}

def test_mailbox_generation_rotation_allows_a_new_flag_with_lower_uid(store):
    old=dict(key=inbox.PREFIX+'a'*64,shopify_order_id='123',header={**header(),'uid':'900'},kind='hold',state='done')
    persist(old)
    new={**old,'key':inbox.PREFIX+'b'*64,'header':{**header(),'uidvalidity':'2','uid':'1'},'state':'pending'}
    persist(new)
    assert inbox.read(inbox.FLAG+'123')['request']==new['key']

def test_receipt_endpoints_require_pairing_email_access_and_server_owned_instructions(monkeypatch):
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    import inbox_companion_api as api
    import prodigi_preparation_api,os_accounts
    calls=[]
    monkeypatch.setattr(prodigi_preparation_api,'desktop',lambda *a,**kw:{'id':'owner'})
    monkeypatch.setattr(os_accounts,'can_access_page',lambda *a:True)
    monkeypatch.setattr(inbox,'tick',lambda actor,**kw:(calls.append(kw) or {'enabled':True}))
    client=TestClient(Starlette(routes=[Route(path,handler,methods=list(methods)) for path,handler,methods in api.ROUTES]))
    base='/api/inbox-companion/'
    headers={'Authorization':'Bearer '+'a'*43}
    assert client.post(base+'tick',json={}).status_code!=200
    assert client.post(base+'tick',headers=headers,json={'recipient':OLD}).status_code!=200
    assert calls==[]
    assert client.post(base+'tick',headers={**headers,'X-Inbox-Scan-Only':'1'},json={}).status_code==200
    assert calls==[{'scan_only':True}]
    monkeypatch.setattr(os_accounts,'can_access_page',lambda *a:False)
    assert client.post(base+'tick',headers=headers,json={}).status_code!=200

def test_header_sender_verification_and_auto_response_detection_use_actual_imap_parser(monkeypatch):
    from support_email_provider import parse_headers
    monkeypatch.setenv('SPORTS_CAVE_INBOX_AUTH_SERVERS','mail.example.test')
    raw=b'From: Fixture <fixture@example.test>\r\nReceived: from upstream.example.test by mail.example.test with ESMTPS\r\nAuthentication-Results: mail.example.test; dmarc=pass header.from=example.test\r\nAuto-Submitted: auto-replied\r\n\r\n'
    value=parse_headers(raw,uid='1',uidvalidity='1')
    assert value['sender_verified'] is True and value['automated'] is True

def test_flag_display_does_not_leak_across_orders_without_allocations(store,monkeypatch):
    from orders_prodigi_grid import payload_rows
    monkeypatch.setenv('SPORTS_CAVE_INBOX_COMPANION_ENABLED','true')
    job,_,_=fixture(monkeypatch);persist(job)
    rows=[{'shopify_order_id':'123','edition_order_id':None},{'shopify_order_id':'124','edition_order_id':None}]
    result=payload_rows(rows,[{},{}],{},allowed=True)
    assert result[0]['state']['label']=='Customer request · review'
    assert result[1]['state']['label']=='—'

def test_reply_intent_uses_real_durable_outbox_deduplication(store,monkeypatch):
    from support_email_durable import MailStore
    from support_email_compose import new_draft,build_mime,default_settings
    from pathlib import Path
    sql=Path('migrations/20261006063028_support_email_durable_delivery.sql').read_text()
    # Execute only the real outbox DDL inside the disposable local PostgreSQL engine.
    start=sql.index('CREATE TABLE IF NOT EXISTS public.support_email_outbox')
    ddl=sql[start:sql.index(';',start)+1]
    with store() as c,c.cursor() as q:q.execute(ddl)
    settings=default_settings();draft=new_draft('hello@example.test',mode='reply',header=header(),signature='nathan')
    draft['html']='<p>Address updated</p>'
    first=build_mime(draft,'hello@example.test',settings['sender_name'],settings['signatures'])
    second=build_mime(draft,'hello@example.test',settings['sender_name'],settings['signatures'])
    # The fixture commits on context exit, while psycopg also exposes commit().
    monkeypatch.setattr(store,'commit',lambda self:None,raising=False)
    delivery=MailStore(connect=store)
    delivery.prepare('hello@example.test',draft['operation_id'],first,actor='owner')
    delivery.prepare('hello@example.test',draft['operation_id'],second,actor='owner')
    with store() as c,c.cursor() as q:
        q.execute('SELECT count(*) AS count FROM support_email_outbox');assert q.fetchone()['count']==1
