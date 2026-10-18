"""Real disposable SQL: no production providers, files, Photoshop or uploads."""
from copy import deepcopy
from datetime import datetime,timezone,timedelta
import json
from pathlib import Path
from unittest.mock import patch
import pytest
import auto_editions_recovery as recovery
from tests.test_auto_editions_technical import flow
from tests.test_worker_health_queue import operations,telemetry,continuous,store,database,pglite_database,failed,rows

CONFIG=dict(policies=[],memberships=[],default_group='')


@pytest.fixture
def backlog(operations,monkeypatch):
    d,sql=operations
    sql.execute(Path('supabase/migrations/20261017001547_auto_editions_technical_completion.sql').read_text())
    monkeypatch.setenv('AUTO_EDITIONS_BACKLOG_RECOVERY_ENABLED','true')
    return d,sql


def source_job(d,sql,n=1000,reason='Download interrupted'):
    pid=failed(d,sql,n)
    source=dict(product_gid=pid,file_id='id:source'+str(n),revision='a1',content_hash='a'*64)
    sql.execute("UPDATE auto_edition_onboarding SET source=%s::jsonb,reason=%s WHERE product_gid=%s",(json.dumps(source),reason,pid))
    return pid,source


def metadata(fid):
    return dict(id=fid,rev='a1',content_hash='a'*64)


def test_full_backlog_duplicate_priority_and_atomic_journal(backlog):
    d,sql=backlog
    # More than a displayed page of deterministic failures must not hide work.
    for n in range(1000,1052):source_job(d,sql,n,'Exactly one visible, editable edition-number layer is required.')
    pid,source=source_job(d,sql,1052)
    before={t:deepcopy(rows(sql,t)) for t in ('edition_products','edition_allocations','synthetic_certificates','product_psd_mappings')}
    with patch('auto_editions_colour_store.configuration',return_value=CONFIG):
        assert recovery.scan(d.connect,metadata)==[pid]
        assert recovery.scan(d.connect,metadata)==[]
    q=next(r for r in rows(sql,'auto_edition_onboarding') if r['product_gid']==pid)
    assert q['status']=='Awaiting preparation' and q['priority']==8
    assert sum(r['event']==recovery.EVENT for r in rows(sql,'auto_edition_onboarding_audit'))==1
    assert {t:rows(sql,t) for t in before}==before
    assert not any(r['status']=='Cloud Ready' for r in rows(sql,'auto_edition_onboarding'))


def test_restart_backoff_and_retry_ceiling(backlog):
    d,sql=backlog;pid,source=source_job(d,sql)
    with patch('auto_editions_colour_store.configuration',return_value=CONFIG):
        for attempt in range(3):
            assert recovery.scan(d.connect,metadata)==[pid]
            sql.execute("UPDATE auto_edition_onboarding SET status='Blocked',reason='Download interrupted',source=%s::jsonb",(json.dumps(source),))
            assert recovery.scan(d.connect,metadata)==[]
            sql.execute("UPDATE auto_edition_onboarding_audit SET created_at=now()-interval '1 hour' WHERE event=%s",(recovery.EVENT,))
        assert recovery.scan(d.connect,metadata)==[]
    assert sum(r['event']==recovery.EVENT for r in rows(sql,'auto_edition_onboarding_audit'))==3


def test_owned_lease_pause_changed_source_and_peer_progress(backlog):
    d,sql=backlog;first,_=source_job(d,sql);second,_=source_job(d,sql,1001)
    sql.execute("UPDATE auto_edition_onboarding SET lease_until=now()+interval '1 hour' WHERE product_gid=%s",(first,))
    with patch('auto_editions_colour_store.configuration',return_value=CONFIG):
        assert recovery.scan(d.connect,metadata)==[second]
    assert next(r for r in rows(sql,'auto_edition_onboarding') if r['product_gid']==first)['status']=='Blocked'


def test_failed_admission_journal_prevents_starvation(backlog):
    d,sql=backlog;first,_=source_job(d,sql);second,_=source_job(d,sql,1001)
    def current(fid):
        if fid=='id:source1000':raise TimeoutError('synthetic provider timeout')
        return metadata(fid)
    with patch('auto_editions_colour_store.configuration',return_value=CONFIG):
        assert recovery.scan(d.connect,current,limit=1)==[]
        assert recovery.scan(d.connect,current,limit=1)==[second]
    assert any(r['detail'].get('accepted') is False for r in rows(sql,'auto_edition_onboarding_audit') if r['event']==recovery.EVENT)


def test_unknown_colour_and_ambiguous_artwork_fail_closed():
    base=dict(status='Needs PSD Repair',priority=8,source=dict(file_id='id:source',revision='a1',content_hash='a'*64),dropbox_file_id='id:source')
    for reason in ('Colour policy awaiting approval: missing source profile','A unique recognised collector plaque is required; manual role review needed.','Preparation failed: RuntimeError. Existing PSD and mapping are preserved.','Photoshop cleanup is unproven; processor lock retained'):
        assert recovery.classify({**base,'reason':reason},CONFIG)['action'] is None


def test_relevant_fix_and_policy_changes_reassess_without_unrelated_revision(monkeypatch):
    row=dict(source={'file_id':'id:x'},preparation_hash=None)
    decision=dict(category='Colour/provenance')
    first=recovery.key(row,decision,CONFIG)
    monkeypatch.setenv('RENDER_GIT_COMMIT','unrelated')
    assert recovery.key(row,decision,CONFIG)==first
    # An unrelated membership never replenishes this source's retry budget.
    assert recovery.key(row,decision,{**CONFIG,'memberships':[{'receipt_hash':'changed'}]})==first
    with patch('auto_editions_colour_policy.resolve',return_value=(b'icc',{'approval_hash':'new-approved-policy'})):
        assert recovery.key(row,decision,CONFIG)!=first
    now=datetime.now(timezone.utc)
    assert recovery.budget([dict(created_at=now)],3,now)=='Waiting for capped retry backoff.'
    assert recovery.budget([dict(created_at=now-timedelta(hours=1))]*3,3,now).startswith('Retry limit')


def test_tagged_retained_export_repair_preserves_original_package(flow,monkeypatch):
    from auto_editions_technical import Technical
    d,sql,record,assets,root=flow
    sql.execute(Path('supabase/migrations/20261015024929_auto_editions_reset_design.sql').read_text())
    monkeypatch.setenv('AUTO_EDITIONS_BACKLOG_RECOVERY_ENABLED','true')
    service=Technical(d.connect);service.seed();job=service.claim()
    service.fail(job,'Embedded ICC profile required.',False)
    before=deepcopy(rows(sql,'auto_edition_preparations'))
    with patch('auto_editions_colour_store.configuration',return_value=CONFIG):
        result=recovery.scan(d.connect,lambda fid:dict(id=fid,rev='a1',content_hash='a'*64))
        assert result==[job['product_gid']], [r['detail'] for r in rows(sql,'auto_edition_onboarding_audit') if r['event']==recovery.EVENT]
    assert rows(sql,'auto_edition_preparations')==before
    q=rows(sql,'auto_edition_onboarding')[0]
    assert q['preparation_hash']==record['hash'] and q['replacement']['stage']=='Discovering'
    assert q['priority']==2
    assert recovery.scan(d.connect,metadata)==[]


def test_pause_and_disabled_scanner_never_mutate(backlog,monkeypatch):
    from worker_health import set_pause
    d,sql=backlog;source_job(d,sql)
    monkeypatch.delenv('AUTO_EDITIONS_BACKLOG_RECOVERY_ENABLED')
    assert recovery.scan(d.connect,lambda _:pytest.fail('Disabled scanner called provider'))==[]
    monkeypatch.setenv('AUTO_EDITIONS_BACKLOG_RECOVERY_ENABLED','true')
    set_pause(d.connect,True,'owner')
    with patch('auto_editions_colour_store.configuration',return_value=CONFIG):
        assert recovery.scan(d.connect,metadata)==[]
    assert rows(sql,'auto_edition_onboarding')[0]['status']=='Blocked'


def test_source_revision_reassessment_requires_changed_bytes():
    from tests.test_auto_editions_discovery import asset
    base=dict(product_gid='gid://shopify/Product/987',status='Needs PSD Repair',priority=8,
        reason='A unique recognised collector plaque is required; manual role review needed.',
        source=dict(product_gid='gid://shopify/Product/987',file_id='id:original',revision='a1',content_hash='a'*64),
        dropbox_file_id='id:original')
    assert recovery.classify({**base,'inventory_metadata':asset(rev='a2')},CONFIG)['action'] is None
    revised={**base,'inventory_metadata':asset(rev='a2',content_hash='b'*64)}
    assert recovery.classify(revised,CONFIG)['action']=='retry'
    assert recovery.key(revised,dict(category='Stale/source'),CONFIG)!=recovery.key(base,dict(category='Stale/source'),CONFIG)


def test_recovery_health_has_wait_reason_and_review_resolution(backlog,monkeypatch):
    import worker_health as health
    d,sql=backlog;pid,_=source_job(d,sql,reason='A unique recognised collector plaque is required; manual role review needed.')
    with patch('auto_editions_colour_store.configuration',return_value=CONFIG):
        assert recovery.scan(d.connect,metadata)==[]
    result=health.Health(d.connect).snapshot()
    assert result['recovery']['needs_review']==1
    assert result['recovery']['runnable']==0 and result['recovery']['verified']==0
    assert next(j for j in result['jobs'] if j['id']==pid)['category']=='Needs Review'
    state=next(h for h in result['health'] if h['component']=='Recovery')
    assert state['status']=='Waiting' and 'No eligible failures' in state['reason']
