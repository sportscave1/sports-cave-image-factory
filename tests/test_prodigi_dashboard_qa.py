from copy import deepcopy
import json
from types import SimpleNamespace
import pytest
import prodigi_dashboard_qa as qa
import prodigi_preparation as prep
import prodigi_browser as browser
from test_auto_editions_jobs import database
from test_prodigi_preparation import store,snapshot,order,Provider


def options():return [dict(service='budget',cents=500,currency='$'),dict(service='standard',cents=700,currency='$'),dict(service='express',cents=1200,currency='$')]
def inserts():
    rows=[dict(name='Round packaging sticker',asset='sticker-id'),dict(name='Packing slip (colour)',asset='slip-id')]
    return dict(set_name=qa.SET,saved=rows,expected=deepcopy(rows),available=True)
def address():return dict(name='Synthetic Customer',address=dict(line1='1 Fixture Street',line2='',townOrCity='Fixture',stateOrCounty='VIC',postalOrZipCode='3000',countryCode='AU'))
def fixture():
    snap=snapshot();snap['recipient']=address()
    provider=Provider();provider.mode='live';provider.data.update(recipient=address(),shippingMethod='Standard')
    provider.data['items'][0]['assets']=[dict(url='https://fixture/art',printArea='default',status='complete')]
    value=dict(allocation_id=1,order_id='99',item_id='88',snapshot=snap,fingerprint=prep.digest(snap),url_hash=prep.digest('https://fixture/art'),
        browser=dict(verified=True,full_image_fit_verified=True),status=qa.WAITING,checks={},history=[])
    evidence=dict(quality='Excellent',sku=snap['mapping']['prodigi_code'],colour='natural',shipping=dict(options=options(),selected='budget'),inserts=inserts())
    return value,snap,provider,evidence

@pytest.mark.parametrize('case',['unchanged','old_policy','started','changed_address','changed_shipping','changed_asset','exhausted'])
@pytest.mark.parametrize('message',['QA shipping: The exact draft or shipping quotes changed before QA.','QA inserts: The expected Prodigi control did not finish loading.',
    'Interrupted QA; recheck the saved order without repeating an upload.','QA open: Receiving end does not exist'])
def test_prepermit_connection_failure_recovers_only_unchanged_verified_work(store,monkeypatch,case,message):
    value,snap,p,_=fixture()
    monkeypatch.setattr(prep,'require_user',lambda _:None)
    monkeypatch.setattr(browser,'context',lambda _:(p,lambda _:snap,None,False))
    with prep.connect() as c,c.cursor() as q:prep.save(q,value)
    plan=qa.claim(exact_item_supported=True)
    qa.finish(plan['key'],plan['token'],None,error=message)
    value=prep.read(1)
    if case=='started':value['dashboard_qa']['started']=True
    if case=='exhausted':value.update(qa_prepermit_recoveries=2,qa_prepermit_recovery_policy=qa.RECOVERY_POLICY)
    if case=='old_policy':value.update(qa_prepermit_recoveries=2,qa_prepermit_recovery_policy='before-lock-fix')
    if case in ('started','exhausted','old_policy'):
        with prep.connect() as c,c.cursor() as q:prep.save(q,value)
    if case=='changed_address':p.data['recipient']['address']['line1']='Changed'
    if case=='changed_shipping':p.data['shippingMethod']='Express'
    if case=='changed_asset':p.data['items'][0]['assets'][0]['url']='https://fixture/other'
    assert qa.recover_waiting_item_qa({'id':'fixture'},page_supported=True)==(1 if case in ('unchanged','old_policy') else 0)
    saved=prep.read(1)
    assert saved['browser']['verified'] and not p.writes
    if case in ('unchanged','old_policy'):assert saved['qa_prepermit_recoveries']==1 and saved['status']==qa.WAITING and saved['qa_prepermit_recovery_policy']==qa.RECOVERY_POLICY


def test_verified_upload_enters_qa_immediately_without_repeating_provider_or_source_reads():
    value,snap,p,_=fixture();readback=deepcopy(p.data)
    p.order=lambda _:pytest.fail('Upload already independently read back this order')
    resolver=lambda _:pytest.fail('Upload already verified this exact source')
    saved=[]
    assert qa.enqueue(value,p,resolver,saved.append,verified_order=readback)['status']==qa.WAITING
    assert len(saved)==1 and not p.writes
    readback['items'][0]['assets'][0]['url']='https://fixture/wrong'
    with pytest.raises(ValueError,match='artwork changed'):
        qa.enqueue(value,p,resolver,saved.append,verified_order=readback)


def test_cheapest_and_express_rules_do_not_confuse_price_ties():
    rows=options()
    assert qa.shipping_choice(rows,'standard','standard')=='budget'
    rows[1]['cents']=500
    assert qa.shipping_choice(rows,'standard','standard')=='standard'
    assert qa.shipping_choice(rows,'express','budget')=='express'
    with pytest.raises(ValueError,match='unavailable'):qa.shipping_choice(rows[:2],'express','standard')
    rows[0]['currency']='€'
    with pytest.raises(ValueError,match='currencies'):qa.shipping_choice(rows,'standard','standard')


def test_inserts_record_presence_without_matching_templates_assets_or_availability():
    proof=inserts();assert qa.insert_checks(proof)==(True,True)
    proof.update(set_name='New seasonal branding',available=False,expected=[])
    proof['saved'][1].update(name='Seasonal packing slip',asset=None)
    assert qa.insert_checks(proof)==(True,True)
    assert qa.observed_inserts(proof)==['Round packaging sticker','Seasonal packing slip']
    proof['saved']=[dict(name='New flyer',asset=None)]
    assert qa.insert_checks(proof)==(True,True)
    for missing in ([],None,[{}],[dict(name='   ')]):
        proof['saved']=missing
        assert qa.insert_checks(proof)==(False,False)


def test_presence_only_inserts_do_not_block_final_qa_but_missing_inserts_do():
    value,snap,p,evidence=fixture();p.data['shippingMethod']='Budget'
    value['dashboard_qa']={'shipping':dict(options=options(),current='standard',target='budget')}
    evidence['inserts'].update(set_name='New set',expected=[],available=False)
    evidence['inserts']['saved']=[dict(name='Current flyer',asset=None),dict(name='Current sticker',asset=None)]
    result=qa.evaluate(value,snap,p.data,p.data['items'][0],evidence,identity_verified=True)
    assert all(result['checks'].values()) and not result['blockers']
    assert result['inserts']==dict(names=['Current flyer','Current sticker'],supplier_available=False)
    evidence['inserts']['saved']=[]
    result=qa.evaluate(value,snap,p.data,p.data['items'][0],evidence,identity_verified=True)
    assert not result['checks']['final_check'] and not result['checks']['packing_slip']


def test_live_full_qa_queues_a_dashboard_check_without_creating_a_certificate(monkeypatch):
    import prodigi_full_qa as full
    value,snap,p,evidence=fixture();value['status']='Checking QA'
    monkeypatch.setattr(full,'live_enabled',lambda:True)
    monkeypatch.setattr(full,'approve',lambda *_:pytest.fail('No legacy native-PPI quality gate'))
    monkeypatch.setattr('prodigi_documents.create',lambda *_:pytest.fail('No certificate upload'))
    result=full.run(value,p,lambda _:snap,lambda _:None)
    assert result['status']==qa.WAITING and not p.writes and 'document' not in value


def test_dashboard_qa_uses_excellent_but_never_ignores_address_or_asset_identity():
    value,snap,p,evidence=fixture();p.data['shippingMethod']='Budget'
    value['dashboard_qa']={'shipping':dict(options=options(),current='standard',target='budget')}
    # Superseded native-source warnings must not impersonate a failed supplier rating.
    value['print_approval']={'print_ready':False,'source_ppi':[121,121]}
    result=qa.evaluate(value,snap,p.data,p.data['items'][0],evidence,identity_verified=True)
    assert all(result['checks'].values()) and result['policy']==qa.POLICY
    evidence['quality']='Good'
    assert not qa.evaluate(value,snap,p.data,p.data['items'][0],evidence,identity_verified=True)['checks']['image_quality']
    evidence['quality']='Excellent';p.data['recipient']['address']['line1']='Another address'
    assert not qa.evaluate(value,snap,p.data,p.data['items'][0],evidence,identity_verified=True)['checks']['customer_address']
    assert not qa.evaluate(value,snap,p.data,p.data['items'][0],evidence,identity_verified=False)['checks']['edition_number']


def test_durable_qa_permit_is_single_use_and_changes_only_shipping(store,monkeypatch):
    value,snap,p,evidence=fixture();key=prep.PREFIX+'1'
    monkeypatch.setattr(browser,'context',lambda _:(p,lambda _:snap,None,False))
    monkeypatch.setattr(qa,'identity_proof',lambda _:True)
    with store() as c,c.cursor() as q:prep.save(q,value)
    plan=qa.claim();assert plan['kind']=='qa' and 'artwork_url' not in plan
    assert qa.claim() is None
    with pytest.raises(ValueError,match='differs'):qa.permit(key,plan['token'],dict(options=options(),current='standard',target='standard'))
    assert qa.permit(key,plan['token'],dict(options=options(),current='standard',target='budget'))=={'permitted':True,'tax_declaration':True}
    with pytest.raises(ValueError,match='used'):qa.permit(key,plan['token'],dict(options=options(),current='standard',target='budget'))
    p.data['shippingMethod']='Budget'
    assert qa.finish(key,plan['token'],evidence)['status']=='Ready for manual payment'
    assert qa.finish(key,plan['token'],None)['status']=='Ready for manual payment'
    assert not p.writes and p.data['status']=='draft' and not p.data.get('charges')
    assert all(prep.read(1)['checks'].values())


def test_product_change_during_qa_cannot_be_approved(store,monkeypatch):
    value,snap,p,evidence=fixture();key=prep.PREFIX+'1'
    monkeypatch.setattr(browser,'context',lambda _:(p,lambda _:snap,None,False))
    monkeypatch.setattr(qa,'identity_proof',lambda _:True)
    with store() as c,c.cursor() as q:prep.save(q,value)
    plan=qa.claim();qa.permit(key,plan['token'],dict(options=options(),current='standard',target='budget'))
    p.data['items'][0]['attributes']['color']='black'
    assert qa.finish(key,plan['token'],evidence)['status']=='Needs review'
    assert not prep.read(1)['dashboard_qa'].get('verified') and not p.writes


def test_existing_unused_certificate_failure_rechecks_only_dashboard(store,monkeypatch):
    value,snap,p,evidence=fixture();value.update(status='Needs review',document_browser={'started':False})
    monkeypatch.setattr('prodigi_full_qa.live_enabled',lambda:True)
    monkeypatch.setattr(prep,'require_user',lambda _:None)
    monkeypatch.setattr('prodigi_document_browser.resume_unstarted',lambda *_:pytest.fail('Certificate upload is retired'))
    with store() as c,c.cursor() as q:prep.save(q,value)
    assert prep.reconcile({'id':'staff'},1)['status']=='Checking QA'


def test_browser_receipts_are_bound_to_the_paired_desktop(monkeypatch):
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    import prodigi_preparation_api as api
    calls=[]
    monkeypatch.setattr(api,'desktop',lambda _,**kw:calls.append('authenticated'))
    monkeypatch.setattr(qa,'finish',lambda *args:{'status':'Needs QA'})
    client=TestClient(Starlette(routes=[Route('/qa/finish',api.dashboard_qa_action,methods=['POST'])]))
    assert client.post('/qa/finish',json={}).status_code!=200 and not calls
    response=client.post('/qa/finish',headers={'Authorization':'Bearer '+'a'*43},json=dict(key='prodigi_prepare:1',token='b'*43,evidence={},error='Incomplete'))
    assert response.status_code==200 and calls==['authenticated']


def test_shipping_intent_reads_only_the_service_not_the_appended_recipient():
    assert qa.intent('Standard Tracked Shipping | Synthetic Recipient | Fixture')=='standard'
    assert qa.intent('Express Shipping | Synthetic Recipient')=='express'
    assert qa.intent('Standard | Express Street')=='standard'
    with pytest.raises(ValueError):qa.intent('Unknown service | Express Street')


def test_country_prefixed_standard_and_extended_quotes_preserve_the_lowest_tied_service():
    assert qa.intent('US Standard Tracked Shipping')=='standard'
    assert qa.intent('UK Standard Shipping | Express Street')=='standard'
    assert qa.intent('International Standard Shipping')=='standard'
    with pytest.raises(ValueError):qa.intent('Unknown service | US Standard Tracked Shipping')
    rows=[dict(service=service,cents=cents,currency='$') for service,cents in [('budget',2730),('standard',2730),('express',3810),('overnight',5430),('standardplus',3000)]]
    assert qa.shipping_choice(rows,'standard','standard')=='standard'
    assert qa.shipping_choice(rows,'express','standard')=='express'
    rows[-1]['cents']=2000
    assert qa.shipping_choice(rows,'standard','standard')=='standardplus'


def test_us_declaration_is_hidden_but_required_before_accepting_the_receipt(store,monkeypatch):
    value,snap,p,evidence=fixture();snap['recipient']['address']['countryCode']='US';p.data['recipient']['address']['countryCode']='US'
    monkeypatch.setattr(browser,'context',lambda _:(p,lambda _:snap,None,False));monkeypatch.setattr(qa,'identity_proof',lambda _:True)
    with store() as c,c.cursor() as q:prep.save(q,value)
    assert qa.claim() is None # Previous companions cannot take a US tax handoff.
    plan=qa.claim(tax_supported=True);assert plan['tax_declaration'] and plan['tax_required']
    qa.permit(prep.PREFIX+'1',plan['token'],dict(options=options(),current='standard',target='budget'));p.data['shippingMethod']='Budget'
    assert qa.finish(prep.PREFIX+'1',plan['token'],evidence)['status']=='Needs review'
    assert 'sales-tax' in prep.read(1)['message'] and not prep.read(1)['dashboard_qa'].get('verified')


def test_us_declaration_accepts_checked_receipt_but_not_explicit_unsaved_api_value(store,monkeypatch):
    value,snap,p,evidence=fixture();snap['recipient']['address']['countryCode']='US';p.data['recipient']['address']['countryCode']='US'
    monkeypatch.setattr(browser,'context',lambda _:(p,lambda _:snap,None,False));monkeypatch.setattr(qa,'identity_proof',lambda _:True)
    with store() as c,c.cursor() as q:prep.save(q,value)
    plan=qa.claim(tax_supported=True);qa.permit(prep.PREFIX+'1',plan['token'],dict(options=options(),current='standard',target='budget'))
    p.data.update(shippingMethod='Budget',usSalesTaxAlreadyCollected=False);evidence['tax_collected']=True
    assert qa.finish(prep.PREFIX+'1',plan['token'],evidence)['status']=='Needs review'
    p.data['usSalesTaxAlreadyCollected']=True
    assert qa.finish(prep.PREFIX+'1',plan['token'],evidence)['status']=='Ready for manual payment'
    saved=prep.read(1);assert saved['dashboard_qa']['tax_collected'] is True and all(saved['checks'].values())


@pytest.mark.parametrize('case',['saved','omitted','unchecked','changed_shipping','changed_asset','charged','exhausted','wrong_policy'])
def test_tax_timeout_recovery_requires_independent_saved_tax_and_unchanged_draft(store,monkeypatch,case):
    value,snap,p,_=fixture()
    monkeypatch.setattr(prep,'require_user',lambda _:None)
    monkeypatch.setattr(browser,'context',lambda _:(p,lambda _:snap,None,False))
    with prep.connect() as c,c.cursor() as q:prep.save(q,value)
    plan=qa.claim(exact_item_supported=True,tax_supported=True)
    qa.permit(plan['key'],plan['token'],dict(options=options(),current='standard',target='budget'))
    p.data.update(shippingMethod='Budget',usSalesTaxAlreadyCollected=True)
    qa.finish(plan['key'],plan['token'],None,error='QA tax-declaration: The expected Prodigi control did not finish loading.')
    value=prep.read(1)
    if case=='exhausted':value['qa_tax_readback_recoveries']=1
    if case=='wrong_policy':value['dashboard_qa']['tax_policy']='unconfirmed'
    with prep.connect() as c,c.cursor() as q:prep.save(q,value)
    if case=='omitted':p.data.pop('usSalesTaxAlreadyCollected')
    if case=='unchecked':p.data['usSalesTaxAlreadyCollected']=False
    if case=='changed_shipping':p.data['shippingMethod']='Express'
    if case=='changed_asset':p.data['items'][0]['assets'][0]['url']='https://fixture/changed'
    if case=='charged':p.data['charges']=[{'id':'fixture-charge'}]
    assert qa.recover_waiting_item_qa({'id':'fixture'})==(1 if case in ('saved','omitted') else 0)
    saved=prep.read(1)
    assert saved['browser']['verified'] and not p.writes
    if case in ('saved','omitted'):
        assert saved['status']==qa.WAITING and saved['qa_tax_readback_recoveries']==1
        assert 'dashboard_qa' not in saved
        # Recovery is admission only: fresh DOM evidence and permit still required.
        next_plan=qa.claim(exact_item_supported=True,tax_supported=True)
        assert next_plan and next_plan['token']!=plan['token']
        assert prep.read(1)['dashboard_qa']['started'] is False



def test_page_wait_recovery_requires_fixed_page_ready_companion(store,monkeypatch):
    v,s,p,_=fixture()
    monkeypatch.setattr(prep,'require_user',lambda _:None)
    monkeypatch.setattr(browser,'context',lambda _:(p,lambda _:s,None,False))
    with prep.connect() as c,c.cursor() as q:prep.save(q,v)
    plan=qa.claim(exact_item_supported=True,tax_supported=True)
    qa.finish(plan['key'],plan['token'],None,error='Interrupted QA; recheck the saved order without repeating an upload.')
    assert qa.recover_waiting_item_qa({'id':'fixture'})==0
    assert qa.recover_waiting_item_qa({'id':'fixture'},page_supported=True)==1
    assert prep.read(1)['browser']['verified'] and not p.writes
