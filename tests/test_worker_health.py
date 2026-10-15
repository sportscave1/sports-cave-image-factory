"""Worker Health contracts against synthetic, isolated SQL only."""
import asyncio,json
from copy import deepcopy
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import Mock,patch
import pytest
import worker_health as health
import worker_health_api as api
import worker_diagnostics as diagnostic
from auto_editions_onboarding_store import Queue
from tests.test_auto_editions_discovery import database,store,pglite_database,rows
from tests.test_auto_editions_v17 import continuous,prepared,mapping
from tests.test_auto_editions_api import request,ADMIN,VA

NOW=datetime(2026,10,16,tzinfo=timezone.utc)


@pytest.fixture
def telemetry(continuous,monkeypatch):
    d,sql=continuous
    sql.execute((Path(__file__).parents[1]/'supabase/migrations/20261015200847_worker_health_telemetry.sql').read_text())
    monkeypatch.setenv('WORKER_HEALTH_TELEMETRY_ENABLED','true')
    return d,sql


def test_pause_during_owned_upload_is_durable_and_never_resets_data(telemetry):
    d,sql=telemetry
    first,fid=mapping(sql,1000);d.queue.enqueue(first,fid,'fixture',newly_linked=False)
    second,fid=mapping(sql,1001);d.queue.enqueue(second,fid,'fixture',newly_linked=False)
    protected=lambda:(rows(sql,'edition_allocations'),rows(sql,'edition_products'),rows(sql,'product_psd_mappings'),rows(sql,'synthetic_certificates'))
    before=protected();active=d.queue.claim('host');lease=str(active['lease_token'])
    paused=health.set_pause(d.connect,True,'administrator');assert paused['state']=='Pausing'
    assert health.set_pause(d.connect,True,'administrator')['audit_id']==paused['audit_id']
    d.queue.heartbeat(first,lease,'host','Uploading')
    assert Queue(d.connect).claim('other-host') is None
    d.queue.checkpoint(first,lease,'host','Blocked','Synthetic connectionerror')
    assert health.set_pause(d.connect,True,'administrator')['state']=='Paused'
    assert Queue(d.connect).claim('after-restart') is None
    assert health.set_pause(d.connect,False,'administrator')['state']=='Resumed'
    assert Queue(d.connect).claim('host')['product_gid']==second
    assert protected()==before
    assert len([r for r in rows(sql,'auto_edition_onboarding_audit') if r['event']=='worker_paused'])==1


def test_expired_owned_lease_can_finish_while_fresh_claims_are_paused(telemetry):
    d,sql=telemetry;pid,fid=mapping(sql,1000);d.queue.enqueue(pid,fid,'fixture');job=d.queue.claim('host')
    sql.execute("UPDATE auto_edition_onboarding SET lease_until=now()-interval '1 second'")
    health.set_pause(d.connect,True,'admin');assert d.queue.claim('other') is None
    d.queue.heartbeat(pid,str(job['lease_token']),'host','Photoshop')
    d.queue.checkpoint(pid,str(job['lease_token']),'host','Blocked','Synthetic repair')
    assert health.set_pause(d.connect,True,'admin')['state']=='Paused'
    assert rows(sql,'auto_edition_onboarding')[0]['attempts']==1


def test_pause_serialises_with_inflight_claim(telemetry):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    d,sql=telemetry;pid,fid=mapping(sql,1000);d.queue.enqueue(pid,fid,'fixture');entered=Event()
    with ThreadPoolExecutor(max_workers=1) as pool:
        with d.connect() as conn,conn.cursor() as cur:
            cur.execute('LOCK TABLE auto_edition_onboarding IN SHARE ROW EXCLUSIVE MODE')
            Queue.audit(cur,health.CONTROL,'admin','worker_paused',{'paused':True})
            def claim():entered.set();return d.queue.claim('host')
            future=pool.submit(claim);assert entered.wait(2)
            assert not future.done()
        assert future.result(timeout=3) is None


def test_telemetry_is_bounded_optional_and_not_public(telemetry,monkeypatch):
    d,sql=telemetry
    assert health.record_heartbeat(d.connect,'Render','fixture',dict(state='Live',stage='Discovery',revision='abcdef12'))
    assert len(rows(sql,'auto_edition_worker_heartbeats'))==1
    health.record_heartbeat(d.connect,'Render','fixture',dict(state='Degraded',stage='Discovery',revision='abcdef12'))
    assert len(rows(sql,'auto_edition_worker_heartbeats'))==1
    sql.execute("SELECT relrowsecurity AS rls,has_table_privilege('anon','auto_edition_worker_heartbeats','SELECT') AS public_read FROM pg_class WHERE relname='auto_edition_worker_heartbeats'")
    permissions=sql.fetchone();assert permissions['rls'] and not permissions['public_read']
    with pytest.raises(ValueError):health.record_heartbeat(d.connect,'Companion','fixture',{'token':'do-not-store'})
    monkeypatch.setenv('WORKER_HEALTH_TELEMETRY_ENABLED','false')
    assert health.record_heartbeat(d.connect,'Render','another',dict(state='Live')) is False
    assert len(rows(sql,'auto_edition_worker_heartbeats'))==1


def sample(state='Queued'):
    row=dict(product_gid='gid://shopify/Product/1000',product_title='Synthetic artwork',priority=1,eligible=True,
        status='Preparing' if state=='Preparing' else 'Awaiting preparation',attempts=1,updated_at=NOW,claimed_at=NOW-timedelta(seconds=30),reason='',lease_until=NOW+timedelta(minutes=45))
    states={row['product_gid']:dict(status=state,uploaded=state in ('Needs Review','Cloud Ready'),actions=[],reason='',checkpoint='Mapped')}
    beats=[dict(component=c,seen_at=NOW,payload=dict(state='Live',revision='abcdef12',code_hash=health.code_hash()) if c=='Companion' else dict(state='Live',revision='abcdef12')) for c in ('Render','Companion')]
    successes=[dict(product_gid=row['product_gid'],product_title='Last artwork',created_at=NOW-timedelta(minutes=i+1),duration_seconds=n) for i,n in enumerate((60,90,120))]
    return [row],states,beats,successes,dict(paused=False)


def test_progress_uses_verified_units_and_eta_uses_successful_durations():
    args=sample();args[0].append({**args[0][0],'product_gid':'gid://shopify/Product/1001'})
    args[1]['gid://shopify/Product/1001']=dict(status='Needs Review',uploaded=True)
    value=health.project(*args,now=NOW,expected_revision='abcdef12')
    assert value['counts']['eligible']==2 and value['counts']['completed']==1 and value['counts']['remaining']==1
    assert value['progress']['ratio']==.5 and value['progress']['current_job_ratio'] is None
    assert value['eta_seconds']==90 and value['counts']['review']==1
    assert 'AEDT' in value['updated_at'] and '11:00:00' in value['updated_at']
    args[3].clear();value=health.project(*args,now=NOW);assert value['eta_seconds'] is None and value['eta_label']=='Calculating'


def test_independent_stale_heartbeats_versions_and_no_output_are_visible():
    args=sample('Preparing');args[0][0]['status']='Preparing'
    args[2][1]['seen_at']=NOW-timedelta(minutes=12)
    value=health.project(*args,now=NOW,expected_revision='abcdef12')
    assert value['overall']=='Offline' and value['health'][1]['status']=='Offline'
    args=sample();args[2][0]['payload']['revision']='deadbeef'
    assert health.project(*args,now=NOW,expected_revision='abcdef12')['health'][0]['status']=='Degraded'
    args=sample();args[3][0]['created_at']=NOW-timedelta(minutes=46)
    value=health.project(*args,now=NOW,expected_revision='abcdef12')
    assert value['overall']=='Degraded' and value['eta_label']=='Unavailable' and '45 minutes' in value['warnings'][0]
    args=sample();args[0][0].update(status='Preparing',lease_until=NOW-timedelta(seconds=1));args[1][args[0][0]['product_gid']]['status']='Failed'
    assert health.project(*args,now=NOW)['health'][-1]['status']=='Degraded'


def test_unknown_diagnostic_never_invents_a_cause_or_exposes_secrets(telemetry):
    d,sql=telemetry;pid,fid=mapping(sql,1000);d.queue.enqueue(pid,fid,'fixture');job=d.queue.claim('host')
    d.queue.checkpoint(pid,str(job['lease_token']),'host','Blocked','RuntimeError C:/private/secret.psd https://secret.test?token=secret')
    logs=health.Health(d.connect).logs(search='undetermined')
    assert len(logs['rows'])==1
    item=logs['rows'][0];assert item['description']=='Cause not yet determined.' and item['trace'].startswith('AE-')
    assert 'secret' not in json.dumps(logs) and 'private' not in json.dumps(logs)
    assert health.Health(d.connect).logs(component='Dropbox')['rows']==[]
    assert diagnostic.explain('ICC profile does not match')['code']=='ICC_MISMATCH'
    assert diagnostic.explain('upload/checkpoint failed')['code']=='UPLOAD_INTERRUPTED'


def test_snapshot_uses_current_receipts_and_bounded_reads(telemetry):
    d,sql=telemetry;pid,fid=mapping(sql,1000);d.queue.enqueue(pid,fid,'fixture')
    value=health.Health(d.connect).snapshot()
    assert value['counts']['eligible']==1 and value['counts']['queued']==1 and value['counts']['completed']==0
    assert value['cost']['queries']==5 and value['cost']['dropbox_calls']==0
    assert value['overall']=='Degraded' # no independent heartbeats yet
    assert 'lease_token' not in json.dumps(value)


def test_health_admin_controls_require_auth_and_origin_and_strict_body():
    with patch('files_upload_api._request_user',return_value=VA),patch.object(api,'store') as forbidden:
        assert asyncio.run(api.pause(request('POST',body={'paused':True}))).status_code==403
        assert asyncio.run(api.page(request('GET'))).status_code==403
        forbidden.assert_not_called()
    with patch('files_upload_api._request_user',return_value=ADMIN),patch.object(api,'store') as forbidden:
        assert asyncio.run(api.pause(request('POST',origin='https://untrusted.test',body={'paused':True}))).status_code==403
        assert asyncio.run(api.pause(request('POST',body={'paused':True,'kill_photoshop':True}))).status_code==409
        forbidden.assert_not_called()


def test_api_unavailable_does_not_false_report_disconnected():
    with patch('files_upload_api._request_user',return_value=ADMIN),patch.object(api,'store',side_effect=RuntimeError('private database credentials')):
        response=asyncio.run(api.snapshot(request('GET')))
    assert response.status_code==503 and b'Authoritative worker status unavailable' in response.body and b'credentials' not in response.body


def test_heartbeat_diagnostics_are_persistent_sanitised_and_transition_only(telemetry):
    d,sql=telemetry
    value=dict(state='Recovering',stage='Uploading',revision='abcdef12',recovery_failures=1,retry_at=NOW.timestamp()+60,
        diagnostic=dict(code='UPLOAD_INTERRUPTED',stage='Uploading'))
    assert health.record_heartbeat(d.connect,'Companion','fixture',value)
    assert health.record_heartbeat(d.connect,'Companion','fixture',value)
    assert len(health.Health(d.connect).logs()['rows'])==1
    health.record_heartbeat(d.connect,'Companion','fixture',dict(state='Idle',stage='Recovery',revision='abcdef12',recovery_failures=0))
    logs=health.Health(d.connect).logs()
    assert len(logs['rows'])==2 and logs['rows'][0]['recovery_result']=='Recovered'
    assert logs['rows'][1]['component']=='Dropbox' and logs['rows'][1]['next_retry_at']
    with pytest.raises(ValueError):health.validate_heartbeat(dict(protocol=float('nan')))
    with pytest.raises(ValueError):health.validate_heartbeat(dict(diagnostic=dict(code='ICC_MISMATCH',secret='never')))


def test_companion_health_uses_owned_state_and_never_paths_or_grants(tmp_path,monkeypatch):
    import sys
    sys.path.insert(0,str(Path(__file__).parents[1]/'scripts/studio'))
    import auto_editions_local as local
    monkeypatch.setattr(Path,'home',lambda:tmp_path)
    monkeypatch.setattr(local.transfer,'ROOT',tmp_path)
    monkeypatch.setattr(local,'HOST_FAILURES',0);monkeypatch.setattr(local,'HOST_RETRY_AT',0);monkeypatch.setattr(local,'HOST_LAST_DIAGNOSTIC',None)
    row=dict(status='Working',phase='Uploading',context={'product_gid':'gid://shopify/Product/1000','lease_token':'NEVER'},grant={'secret':'NEVER'},folder='C:/private/NEVER')
    monkeypatch.setattr(local,'JOBS',{'fixture':row})
    value=local.health_payload();assert value['state']=='Live' and value['stage']=='Uploading'
    assert 'NEVER' not in json.dumps(value) and health.validate_heartbeat(value)
    row.update(status='Recovering',checkpoint_pending=True,retry_at=NOW.timestamp()+60,recovery_failures=2)
    value=local.health_payload();assert value['state']=='Recovering' and value['checkpoint_pending'] and value['recovery_failures']==2


def test_334_job_snapshot_is_bounded_read_only_and_timed(telemetry):
    import statistics,time
    d,sql=telemetry
    for n in range(1000,1334):
        pid,fid=mapping(sql,n);d.queue.enqueue(pid,fid,'synthetic-owner')
    protected=lambda:tuple(rows(sql,t) for t in ('auto_edition_onboarding','edition_products','edition_allocations','product_psd_mappings','synthetic_certificates','auto_edition_onboarding_audit'))
    before=protected();times=[]
    for _ in range(5):
        start=time.perf_counter();value=health.Health(d.connect).snapshot();times.append((time.perf_counter()-start)*1000)
        assert len(value['jobs'])==334 and value['counts']['eligible']==334 and value['counts']['queued']==334
        assert value['cost']['queries']==5 and value['cost']['dropbox_calls']==0
    assert before==protected()
    print('334-job local snapshot median_ms=',round(statistics.median(times),2),'max_ms=',round(max(times),2),'response_bytes=',len(json.dumps(value)))


def test_no_initial_output_and_unmeasurable_stalled_stage_do_not_claim_health():
    args=sample('Preparing');args[0][0].update(status='Preparing',claimed_at=NOW-timedelta(minutes=46));args[3].clear()
    value=health.project(*args,now=NOW,expected_revision='abcdef12')
    assert value['overall']=='Degraded' and '45 minutes' in ' '.join(value['warnings'])
    args=sample('Preparing');args[2][1]['payload'].update(product_gid=args[0][0]['product_gid'],last_progress_at=(NOW-timedelta(minutes=16)).timestamp())
    value=health.project(*args,now=NOW,expected_revision='abcdef12')
    assert value['overall']=='Degraded' and value['eta_seconds'] is None and 'stage change' in ' '.join(value['warnings'])


def test_pending_quality_validation_is_not_an_active_photoshop_job():
    args=sample('Preparing');args[0][0]['status']='Blocked'
    value=health.project(*args,now=NOW,expected_revision='abcdef12')
    assert value['current'] is None and value['jobs'][0]['stage']=='Verifying' and value['jobs'][0]['status']=='Queued'
    assert value['eta_seconds'] is None


def test_pause_also_prevents_new_quality_validation_without_provider_io(telemetry,monkeypatch):
    from auto_editions_quality_store import Quality
    d,sql=telemetry;monkeypatch.setenv('AUTO_EDITIONS_V16_AUTO_APPROVAL_ENABLED','true')
    health.set_pause(d.connect,True,'admin');assets=Mock()
    assert Quality(d.connect).run_one(assets,records=[]) is False
    assets.integration.psd_open_metadata.assert_not_called();assets.fetch.assert_not_called()
