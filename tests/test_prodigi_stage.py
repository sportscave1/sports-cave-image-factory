"""Offline transaction lifetime and concurrent Reset regression checks."""
from contextlib import contextmanager
from copy import deepcopy
import pytest

import prodigi_browser as browser
import prodigi_preparation as prep
import prodigi_stage as stages
import prodigi_dashboard_qa as qa
import prodigi_submission as submit
import prodigi_sandbox as sandbox
from test_auto_editions_jobs import database
from test_prodigi_preparation import store
from test_prodigi_browser import handoff,KEY,render_url,offline
from test_prodigi_order_group import pair


def track_connections(monkeypatch):
    factory=prep.connect
    active=[]
    @contextmanager
    def tracked():
        with factory() as conn:
            active.append(conn)
            try:yield conn
            finally:active.pop()
    monkeypatch.setattr(prep,'connect',tracked)
    return active


def test_browser_checks_and_original_download_hold_no_transaction(handoff,monkeypatch):
    _,provider,_=handoff
    active=track_connections(monkeypatch)
    old=provider.order;reads=[]
    def order(oid):
        assert not active
        reads.append(oid)
        return old(oid)
    monkeypatch.setattr(provider,'order',order)
    provider_context=browser.context(KEY)
    def artwork(_):
        assert not active
        return 'https://fixture.invalid/source','a'*32
    monkeypatch.setattr(browser,'context',lambda _: (*provider_context[:2],artwork,True))
    def verify(*_):
        assert not active
        return True
    monkeypatch.setattr(browser,'verify_file',verify)
    plan=browser.claim()
    browser.permit(KEY,plan['token'],plan['sha256'])
    provider.artwork('99','88',render_url(),'a'*32)
    assert browser.finish(KEY,plan['token'])['status']=='Needs QA'
    assert len(reads)==4 # Claim, permit, and independent pre/post-download reads.
    assert not active


@pytest.mark.parametrize('operation',['claim','permit','finish'])
def test_reset_during_external_read_cannot_be_overwritten(handoff,monkeypatch,operation):
    factory,provider,original=handoff
    plan=None
    if operation!='claim':plan=browser.claim()
    if operation=='finish':
        browser.permit(KEY,plan['token'],plan['sha256'])
        provider.artwork('99','88',render_url(),'a'*32)
        monkeypatch.setattr(browser,'verify_file',lambda *_:True)
    changed=[];old=provider.order
    def reset_during_read(oid):
        if not changed:
            current=sandbox.list_tests()[0]
            current.update(status='Needs repair',message='New reset owns this order')
            with factory() as conn,conn.cursor() as cur:sandbox.save(cur,current)
            changed.append(True)
        return old(oid)
    monkeypatch.setattr(provider,'order',reset_during_read)
    if operation=='claim':assert browser.claim() is None
    elif operation=='permit':
        with pytest.raises(stages.Changed):browser.permit(KEY,plan['token'],plan['sha256'])
    else:assert browser.finish(KEY,plan['token'])=={'status':'Handoff unavailable'}
    current=sandbox.list_tests()[0]
    assert current['status']=='Needs repair' and current['message']=='New reset owns this order'


def test_grouped_qa_rechecks_every_sibling_and_commits_nothing_on_reset(pair,monkeypatch):
    a,b,p,_=pair
    for unit in (a,b):
        unit.update(status=qa.WAITING)
        unit.pop('dashboard_qa',None)
        with prep.connect() as conn,conn.cursor() as cur:prep.save(cur,unit)
    active=track_connections(monkeypatch)
    original=prep.resolve;calls=[]
    def source(aid):
        assert not active
        calls.append(aid)
        if aid==2:
            changed=prep.read(2);changed.update(status='Needs repair')
            with prep.connect() as conn,conn.cursor() as cur:prep.save(cur,changed)
        return original(aid)
    monkeypatch.setattr(browser,'context',lambda _:(p,source,None,False))
    assert qa.claim(tax_supported=True,exact_item_supported=True,batch_supported=True,sequential_supported=True) is None
    assert calls==[1,2] # Repeated validations share just this phase's source reads.
    assert prep.read(1)['status']==qa.WAITING and not prep.read(1).get('dashboard_qa')
    assert prep.read(2)['status']=='Needs repair'


@pytest.mark.parametrize('reset',[False,True])
def test_submission_network_is_outside_transaction_and_reset_blocks_post(pair,monkeypatch,reset):
    _,_,p,_=pair
    active=track_connections(monkeypatch)
    old=p.order;reads=[]
    original=prep.resolve;sources=[]
    def source(aid):
        sources.append(aid)
        return original(aid)
    monkeypatch.setattr(prep,'resolve',source)
    def read(oid):
        assert not active
        if reset and not reads:
            changed=prep.read(2);changed.update(status='Needs repair')
            with prep.connect() as conn,conn.cursor() as cur:prep.save(cur,changed)
        reads.append(oid)
        return old(oid)
    monkeypatch.setattr(p,'order',read)
    submit.tick()
    assert p.submits==([] if reset else ['99'])
    if reset:
        assert prep.read(2)['status']=='Needs repair'
        assert not prep.read(1).get('submission')
    else:
        assert len(reads)==3 # One whole-order read per preflight, then acknowledgement.
        assert sources==[1,2,1,2] # Each independent preflight verifies both exact sources.
        assert prep.read(1)['status']==prep.read(2)['status']=='Submitted'


def test_source_read_batch_is_local_to_one_phase_and_copies_results():
    reads=[]
    def source(aid):
        order=stages.source_read('order','same-order',lambda:(reads.append('order') or {'version':len(reads)}))
        return dict(aid=aid,order=order)
    first=stages.resolver_once(source)
    a=first(1);a['order']['version']=999
    assert first(1)['order']['version']==first(2)['order']['version']==1
    assert reads==['order']
    assert stages.resolver_once(source)(1)['order']['version']==2


def test_concurrent_claim_returns_only_the_committed_token(handoff,monkeypatch):
    _,provider,_=handoff
    old=provider.order;winner=[];entered=[]
    def overlapping(oid):
        if not entered:
            entered.append(True)
            winner.append(browser.claim())
        return old(oid)
    monkeypatch.setattr(provider,'order',overlapping)
    assert browser.claim() is None
    assert winner[0] and browser.claim() is None
    assert browser.permit(KEY,winner[0]['token'],winner[0]['sha256'])=={'permitted':True}


def test_owner_pause_during_submission_preflight_blocks_intent(pair,monkeypatch):
    _,_,p,_=pair;old=p.order
    def pause(oid):
        submit.configure({'id':'owner'},False)
        return old(oid)
    monkeypatch.setattr(prep,'require_user',lambda _:None)
    monkeypatch.setattr(p,'order',pause)
    submit.tick()
    assert not p.submits and not prep.read(1).get('submission') and not prep.read(2).get('submission')
