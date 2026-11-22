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
    assert result['status']=='Checking QA' and 'all numbered' in result['message']
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
