from copy import deepcopy
import json
import pytest
import requests
import prodigi_preparation as prep
import prodigi_dashboard_qa as qa
import prodigi_order_group as group
import prodigi_submission as submit
from test_prodigi_submission import ready
from test_prodigi_preparation import store
from test_auto_editions_jobs import database


@pytest.fixture
def pair(store,monkeypatch):
    monkeypatch.setattr(requests.sessions.Session,'request',lambda *a,**k:pytest.fail('Live network forbidden'))
    a,s,p,auth=ready();b=deepcopy(a);t=deepcopy(s)
    t.update(allocation_id=2,number=13);t['identity']['line_id']='457'
    b.update(allocation_id=2,item_id='89',snapshot=t,fingerprint=prep.digest(t),url_hash=prep.digest('https://fixture/art2'))
    item=deepcopy(p.data['items'][0]);item.update(id='89',merchantReference='457')
    item['assets'][0]['url']='https://fixture/art2';p.data['items'].append(item)
    pinned=qa.pinned_order(p.data);pinned['shippingMethod']=p.data.get('shippingMethod')
    for unit in (a,b):unit['dashboard_qa'].update(before=deepcopy(p.data),validated_order_hash=prep.digest(pinned))
    sources={1:s,2:t}
    monkeypatch.setattr(prep,'resolve',lambda aid:deepcopy(sources[aid]))
    monkeypatch.setattr(prep,'Client',lambda:p)
    with prep.connect() as c,c.cursor() as q:
        for unit in (a,b):prep.save(q,unit)
        q.execute('INSERT INTO app_settings(key,value) VALUES(%s,%s::jsonb)',(submit.SETTING,json.dumps(auth)))
    return a,b,p,auth


def test_group_waits_for_all_uploaded_numbered_items(pair):
    a,b,p,_=pair;b['browser']['verified']=False
    with prep.connect() as c,c.cursor() as q:prep.save(q,b)
    result=qa.enqueue(a,p,prep.resolve,lambda _:None)
    assert result['status']==qa.WAITING
    assert not p.submits


def test_immediate_upload_to_qa_still_waits_for_and_revalidates_siblings(pair):
    a,b,p,_=pair;b['browser']['verified']=False
    with prep.connect() as c,c.cursor() as q:prep.save(q,b)
    calls=[]
    def resolver(aid):
        calls.append(aid);return prep.resolve(aid)
    result=qa.enqueue(a,p,resolver,lambda _:None,verified_order=deepcopy(p.data))
    assert result['status']==qa.WAITING and calls==[2]
    assert not p.submits


def test_one_bad_sibling_cannot_be_hidden_by_passed_qa_on_first_item(pair):
    a,b,p,auth=pair;b['qa']['checks']['image_quality']=False
    with prep.connect() as c,c.cursor() as q:prep.save(q,b)
    with pytest.raises(ValueError,match='every automatic QA'):submit.checked(a,p,prep.resolve,auth)
    assert not p.submits


def test_waits_for_sibling_qa_and_does_not_create_submission_intent(pair):
    a,b,p,_=pair;b['status']=qa.ACTIVE
    with prep.connect() as c,c.cursor() as q:prep.save(q,b)
    submit.tick()
    assert prep.read(1)['status']=='Ready for manual payment'
    assert 'every numbered item' in prep.read(1)['message']
    assert not p.submits and not prep.read(1).get('submission')


def test_group_submits_once_and_marks_both_countdowns_without_certificates(pair,monkeypatch):
    a,b,p,_=pair
    submit.tick()
    assert p.submits==['99']
    assert prep.read(1)['status']==prep.read(2)['status']=='Submitted'
    assert prep.read(1)['submission']['items']==group.manifest(p.data)
    assert prep.read(2)['submission']['leader_allocation']==1
    # A lost response, next worker, or repeated alarm can only read back.
    with prep.connect() as c,c.cursor() as q:
        q.execute("UPDATE app_settings SET updated_at=now()-interval '1 minute' WHERE key LIKE 'prodigi_prepare:%%'")
    submit.tick();assert p.submits==['99']
    assert not prep.read(1).get('certificate_url') and not prep.read(2).get('certificate_url')


def test_finalisation_certifies_each_exact_item_and_rejects_sibling_changes(pair):
    a,b,p,_=pair;submit.tick();p.data['status']='in_production'
    certificates=[]
    def certificate(v):certificates.append(v['allocation_id']);return 'https://fixture/certificate.pdf'
    for aid in (1,2):
        v=prep.read(aid)
        assert submit.run(v,p,prep.resolve,lambda _:None,certificate)['status']=='Complete'
    assert certificates==[1,2] and p.submits==['99']
    p.data['items'][1]['assets'][0]['url']='https://fixture/wrong'
    v=prep.read(1)
    assert submit.run(v,p,prep.resolve,lambda _:None,lambda _:pytest.fail('No certificate on changed sibling'))['status']=='Submission uncertain'


def test_unknown_duplicate_or_wrong_sibling_artwork_fails_closed(pair):
    a,b,p,_=pair
    p.data['items'][1]['assets'][0]['url']='https://fixture/wrong'
    with pytest.raises(ValueError,match='sibling item artwork'):group.members(a,p.data)
    p.data['items'][1]['id']='unmapped'
    with pytest.raises(ValueError,match='outside'):group.members(a,p.data)


def test_multi_item_dashboard_evidence_must_name_the_exact_item(pair):
    from test_prodigi_dashboard_qa import inserts,options
    a,b,p,_=pair;a['dashboard_qa']['shipping']=dict(options=options(),current='standard',target='budget')
    evidence=dict(quality='Excellent',sku=a['snapshot']['mapping']['prodigi_code'],colour='natural',shipping=dict(options=options(),selected='budget'),inserts=inserts())
    with pytest.raises(ValueError,match='another supplier item'):qa.evaluate(a,a['snapshot'],p.data,p.data['items'][0],evidence,identity_verified=True)

def test_group_publish_never_claims_a_sibling_certificate_is_uploaded(pair):
    a,b,p,_=pair;submit.tick();v=prep.read(1)
    v.update(status='Complete',message='Supplier submission and customer certificate upload confirmed.')
    v['submission'].update(supplier_status='in_production',finalised=True)
    group.publish(v)
    assert prep.read(2)['status']=='Certificate pending'
    assert not prep.read(2).get('certificate_url')
    assert 'Awaiting this edition' in prep.read(2)['message']


def batch_plan(pair,monkeypatch):
    import prodigi_browser as browser
    a,b,p,auth=pair
    monkeypatch.setattr(browser,'context',lambda _:(p,prep.resolve,None,False))
    monkeypatch.setattr(qa,'identity_proof',lambda _:True)
    with prep.connect() as c,c.cursor() as q:
        for unit in (a,b):
            unit.pop('dashboard_qa',None);unit['status']=qa.WAITING;prep.save(q,unit)
    plan=qa.claim(tax_supported=True,exact_item_supported=True,batch_supported=True)
    return plan,p,auth


def test_real_grouped_server_plan_is_accepted_by_companion_with_lowercase_provider_colour(pair,monkeypatch):
    import subprocess
    from pathlib import Path
    plan,p,_=batch_plan(pair,monkeypatch)
    assert p.data['items'][0]['attributes']['color']=='natural'
    assert plan['colour']=='Natural' and all(row['colour']==plan['colour'] for row in plan['items'])
    script="""const fs=require('fs'),vm=require('vm');
const c=vm.createContext({chrome:{runtime:{onMessage:{addListener(){}}}},URL});
vm.runInContext(fs.readFileSync('windows-upload-companion/prodigi-browser.js','utf8'),c);
c.plan=JSON.parse(fs.readFileSync(0,'utf8'));
if(!vm.runInContext('prodigiPlanValid(plan)',c))process.exit(1);"""
    result=subprocess.run(['node','-e',script],input=json.dumps(plan),text=True,capture_output=True,
        cwd=Path(__file__).resolve().parent.parent,timeout=10)
    assert result.returncode==0,result.stderr


@pytest.mark.parametrize('case',['unchanged','used_permit','changed_asset','changed_currency','changed_address','exhausted','fixed_plan','recent_plan'])
def test_mixed_colour_plan_recovers_whole_group_only_before_any_permit(pair,monkeypatch,case):
    from datetime import datetime,timezone,timedelta
    plan,p,_=batch_plan(pair,monkeypatch)
    monkeypatch.setattr(prep,'require_user',lambda _:None)
    with prep.connect() as c,c.cursor() as q:
        for aid in (1,2):
            v=prep.read(aid);r=v['dashboard_qa']
            r.pop('colour_policy',None)
            r['claimed_at']=(datetime.now(timezone.utc)-timedelta(seconds=10 if case=='recent_plan' else 180)).isoformat()
            if case=='used_permit' and aid==2:r['started']=True
            if case=='exhausted':v['qa_colour_plan_recoveries']=1
            if case=='fixed_plan':r['colour_policy']='canonical-v1'
            prep.save(q,v)
    if case=='changed_asset':p.data['items'][1]['assets'][0]['url']='https://fixture/wrong'
    if case=='changed_currency':p.data['items'][1]['unitPrice']={'amount':'52','currency':'AUD'}
    if case=='changed_address':p.data['recipient']['address']['line1']='Changed'
    assert qa.recover_colour_plans({'id':'owner'})==(1 if case=='unchanged' else 0)
    assert not p.submits and not p.writes
    if case=='unchanged':
        assert prep.read(1)['status']==prep.read(2)['status']==qa.WAITING
        assert prep.read(1)['browser']['verified'] and prep.read(2)['browser']['verified']
        new=qa.claim(tax_supported=True,exact_item_supported=True,batch_supported=True)
        assert new['token']!=plan['token'] and new['colour']==new['items'][0]['colour']
        with pytest.raises(PermissionError):qa.permit(plan['key'],plan['token'],{})
        assert qa.recover_colour_plans({'id':'owner'})==0


def test_one_batch_checks_every_item_then_submits_order_only_once(pair,monkeypatch):
    from test_prodigi_dashboard_qa import options,inserts
    plan,p,auth=batch_plan(pair,monkeypatch)
    assert [r['item_id'] for r in plan['items']]==['88','89']
    assert prep.read(1)['dashboard_qa']['batch']==prep.read(2)['dashboard_qa']['batch']==[1,2]
    assert prep.read(1)['status']==prep.read(2)['status']==qa.ACTIVE
    qa.permit(plan['key'],plan['token'],dict(options=options(),current='standard',target='budget'))
    assert prep.read(2)['dashboard_qa']['started'] is True
    p.data['shippingMethod']='Budget'
    evidence=dict(items=[dict(**row,quality='Excellent') for row in plan['items']],tax_collected=None,
        shipping=dict(options=options(),selected='budget'),inserts=inserts())
    assert qa.finish(plan['key'],plan['token'],evidence)['status']=='Ready for manual payment'
    assert prep.read(1)['dashboard_qa']['checked_at']==prep.read(2)['dashboard_qa']['checked_at']
    assert all(prep.read(1)['checks'].values()) and all(prep.read(2)['checks'].values())
    submit.tick();assert p.submits==['99']
    assert prep.read(1)['status']==prep.read(2)['status']=='Submitted'


@pytest.mark.parametrize('failure',['missing','duplicate','quality','wrong_id','changed_order'])
def test_batch_cannot_hide_a_missing_wrong_or_failed_item(pair,monkeypatch,failure):
    from test_prodigi_dashboard_qa import options,inserts
    plan,p,auth=batch_plan(pair,monkeypatch)
    qa.permit(plan['key'],plan['token'],dict(options=options(),current='standard',target='budget'))
    p.data['shippingMethod']='Budget'
    evidence=dict(items=[dict(**row,quality='Excellent') for row in plan['items']],tax_collected=None,
        shipping=dict(options=options(),selected='budget'),inserts=inserts())
    if failure=='missing':evidence['items'].pop()
    if failure=='duplicate':evidence['items'][1]['item_id']='88'
    if failure=='wrong_id':evidence['items'][1]['item_id']='unrelated'
    if failure=='quality':evidence['items'][1]['quality']='Poor'
    if failure=='changed_order':p.data['recipient']['address']['line1']='Other destination'
    qa.finish(plan['key'],plan['token'],evidence)
    submit.tick();assert not p.submits
    assert not prep.read(1).get('submission') and not prep.read(2).get('submission')


def test_each_edition_finishes_qa_before_sibling_then_final_batch_submits_once(pair,monkeypatch):
    import prodigi_browser as browser
    from test_prodigi_dashboard_qa import options,inserts
    a,b,p,auth=pair
    monkeypatch.setattr(browser,'context',lambda _:(p,prep.resolve,None,False))
    monkeypatch.setattr(qa,'identity_proof',lambda _:True)
    a.pop('dashboard_qa',None);a['status']=qa.WAITING
    b.pop('dashboard_qa',None);b.update(status='Awaiting product selection',browser={})
    p.data['items'][1].update(sku=None,attributes={},assets=[])
    with prep.connect() as c,c.cursor() as q:
        prep.save(q,a);prep.save(q,b)
    # An old companion cannot silently claim an incomplete grouped batch.
    assert qa.claim(exact_item_supported=True,batch_supported=True) is None
    assert qa.claim(exact_item_supported=True,batch_supported=True,sequential_supported=True) is None
    first=qa.claim(exact_item_supported=True,batch_supported=True,sequential_supported=True,item_qa_supported=True)
    assert first['item_id']=='88' and 'items' not in first and first['item_only'] is True
    with pytest.raises(ValueError,match='Item QA cannot change'):
        qa.permit(first['key'],first['token'],dict(options=options(),current='standard',target='budget'))
    evidence=dict(item_id='88',quality='Excellent',sku=a['snapshot']['mapping']['prodigi_code'],colour='natural')
    assert qa.finish(first['key'],first['token'],evidence)['status']=='Waiting for order'
    assert prep.read(1)['checks']['image_quality'] is True and prep.read(1)['checks']['final_check'] is False
    assert 'shipping' not in prep.read(1)['checks'] and 'packing_slip' not in prep.read(1)['checks']
    submit.tick();assert not p.submits and not prep.read(1).get('submission')
    # The next item's variant/upload occurs after the first QA, on the same order.
    p.data['items'][1].update(sku=b['snapshot']['mapping']['prodigi_code'],attributes={'color':'natural'},
        assets=[dict(url='https://fixture/art2',printArea='default',status='complete')])
    b['browser']=dict(verified=True,full_image_fit_verified=True);b['status']=qa.WAITING
    with prep.connect() as c,c.cursor() as q:prep.save(q,b)
    final=qa.claim(exact_item_supported=True,batch_supported=True,sequential_supported=True,item_qa_supported=True)
    assert {i['item_id'] for i in final['items']}=={'88','89'}
    qa.permit(final['key'],final['token'],dict(options=options(),current='standard',target='budget'))
    p.data['shippingMethod']='Budget'
    combined=dict(items=[dict(**r,quality='Excellent') for r in final['items']],
        shipping=dict(options=options(),selected='budget'),inserts=inserts())
    assert qa.finish(final['key'],final['token'],combined)['status']=='Ready for manual payment'
    submit.tick();assert p.submits==['99']
    assert prep.read(1)['status']==prep.read(2)['status']=='Submitted'


@pytest.mark.parametrize('change',['poor','wrong_item','extra_shared','address','artwork'])
def test_item_qa_cannot_bypass_identity_quality_or_submission_checks(pair,monkeypatch,change):
    import prodigi_browser as browser
    a,b,p,_=pair
    monkeypatch.setattr(browser,'context',lambda _:(p,prep.resolve,None,False))
    monkeypatch.setattr(qa,'identity_proof',lambda _:True)
    a.pop('dashboard_qa',None);a['status']=qa.WAITING
    b.update(status='Awaiting product selection',browser={})
    with prep.connect() as c,c.cursor() as q:prep.save(q,a);prep.save(q,b)
    plan=qa.claim(exact_item_supported=True,batch_supported=True,sequential_supported=True,item_qa_supported=True)
    evidence=dict(item_id='88',sku=a['snapshot']['mapping']['prodigi_code'],colour='natural',quality='Excellent')
    if change=='poor':evidence['quality']='Poor'
    if change=='wrong_item':evidence['item_id']='89'
    if change=='extra_shared':evidence['shipping']={}
    if change=='address':p.data['recipient']['address']['line1']='Different'
    if change=='artwork':p.data['items'][0]['assets'][0]['url']='https://fixture/other'
    result=qa.finish(plan['key'],plan['token'],evidence)
    assert result['status'] in ('Needs QA','Needs review')
    submit.tick();assert not p.submits and not prep.read(1).get('submission')


@pytest.mark.parametrize('changed',[False,True])
@pytest.mark.parametrize('message',['QA inserts: The expected QA control did not finish loading.','QA product-row: Close the existing order editor before QA.'])
def test_known_item_inserts_wait_recovers_saved_artwork_without_upload(pair,monkeypatch,changed,message):
    import prodigi_browser as browser
    a,b,p,_=pair
    monkeypatch.setattr(prep,'require_user',lambda _:None)
    monkeypatch.setattr(browser,'context',lambda _:(p,prep.resolve,None,False))
    monkeypatch.setattr(qa,'identity_proof',lambda _:True)
    a.pop('dashboard_qa',None);a['status']=qa.WAITING
    b.update(status='Awaiting product selection',browser={})
    with prep.connect() as c,c.cursor() as q:prep.save(q,a);prep.save(q,b)
    plan=qa.claim(exact_item_supported=True,batch_supported=True,sequential_supported=True,item_qa_supported=True)
    qa.finish(plan['key'],plan['token'],None,error=message)
    if changed:p.data['recipient']['address']['line1']='Different'
    assert qa.recover_waiting_item_qa({'id':'fixture'})==(0 if changed else 1)
    assert prep.read(1)['status']==('Needs review' if changed else qa.WAITING)
    assert prep.read(1)['browser']['verified'] is True and not p.submits
