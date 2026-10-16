"""Cancellation races on disposable PostgreSQL and isolated Companion workers."""
import asyncio
import json
import threading
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from auto_editions_cancellation import Cancellation
from auto_editions_reset import Reset, snapshot
import auto_editions_status as status
from tests.test_auto_editions_reset import design, selected, protected, discover, complete
from tests.test_auto_editions_discovery import database, store, pglite_database, PID
from tests.test_auto_editions_api import request, ADMIN


def gate(design):return Cancellation(design[0].connect)


def test_queued_cancel_then_exact_normal_reset(design,tmp_path):
    d,sql,_,_=design;before=protected(sql)
    sql.execute("UPDATE auto_edition_onboarding SET status='Awaiting preparation',preparation_hash=NULL WHERE product_gid=%s",(PID,))
    rid=str(uuid.uuid4())
    original=Reset.request
    with patch.object(Reset,'request',autospec=True,side_effect=original) as normal:
        assert gate(design).request(PID,rid,'admin')=='Discovering'
        assert gate(design).request(PID,rid,'admin')=='Discovering'
        assert normal.call_count==1
    assert d.queue.claim('host') is None
    assert protected(sql)==before
    assert discover(design)['stage']=='Queued'
    work=d.queue.claim('host')
    complete(design,work['lease_token'],tmp_path)
    assert status.batch(d.connect,[PID])['rows'][0]['status']=='Review'
    assert protected(sql)==before


def active(design):
    d,sql,_,_=design
    sql.execute("UPDATE auto_edition_onboarding SET status='Awaiting preparation',preparation_hash=NULL WHERE product_gid=%s",(PID,))
    return d.queue.claim('host')


def test_active_waits_even_after_expiry_and_repeated_clicks_join(design):
    d,sql,_,_=design;work=active(design);before=protected(sql)
    rid=str(uuid.uuid4());cancel=gate(design)
    with patch.object(Reset,'request',side_effect=AssertionError('Reset before safe stop')):
        assert cancel.request(PID,rid,'admin')=='Cancelling'
        assert cancel.request(PID,str(uuid.uuid4()),'other-admin')=='Cancelling'
        sql.execute("UPDATE auto_edition_onboarding SET lease_until=now()-interval '1 day' WHERE product_gid=%s",(PID,))
        cancel.resume()
        assert d.queue.claim('host') is None
        assert cancel.poll(PID,str(work['lease_token']),'host') is True
    value=status.batch(d.connect,[PID],writable=True)['rows'][0]
    assert value['status']=='Cancelling'+chr(8230) and not value['reset_allowed'] and not value['actions']
    assert 'offline' in value['reason'] and 'automatically' in value['reason']
    assert selected(sql)['replacement'] is None
    assert protected(sql)==before
    with pytest.raises(PermissionError):cancel.poll(PID,str(work['lease_token']),'unrelated-host',True)
    assert cancel.poll(PID,str(work['lease_token']),'host',True)
    assert selected(sql)['replacement']['id']==rid
    assert selected(sql)['replacement']['stage']=='Discovering'
    assert cancel.poll(PID,str(work['lease_token']),'host',True)
    sql.execute("SELECT count(*) n FROM auto_edition_onboarding_audit WHERE event='reset_requested' AND product_gid=%s",(PID,))
    assert sql.fetchone()['n']==1
    assert protected(sql)==before


def test_late_callbacks_recovery_and_checkpoint_cannot_change_design(design):
    d,sql,_,_=design;work=active(design);token=str(work['lease_token']);cancel=gate(design)
    cancel.request(PID,str(uuid.uuid4()),'admin')
    for after_ack in (False,True):
        if after_ack:cancel.poll(PID,token,'host',True)
        before=selected(sql)
        with pytest.raises(ValueError):d.queue.checkpoint(PID,token,'host','Cloud Ready','late result')
        with pytest.raises(ValueError):d.queue.heartbeat(PID,token,'host','Recovering')
        with pytest.raises(ValueError):d.queue.defer_owned(PID,token,'host')
        assert d.queue.completed_receipt(PID,token,'host') is None
        assert selected(sql)==before
    # A later reset cannot erase the old operation's terminal cancellation.
    sql.execute("UPDATE auto_edition_onboarding SET replacement=NULL WHERE product_gid=%s",(PID,))
    cancel.request(PID,str(uuid.uuid4()),'admin')
    assert cancel.poll(PID,token,'host') is True


def test_confirmation_persisted_before_restart_resumes_without_browser(design):
    d,sql,_,_=design;work=active(design);cancel=gate(design)
    rid=str(uuid.uuid4());cancel.request(PID,rid,'admin')
    with patch.object(Cancellation,'resume',side_effect=ConnectionError('server restart')):
        with pytest.raises(ConnectionError):cancel.poll(PID,str(work['lease_token']),'host',True)
    assert selected(sql)['reset_cancellation']['stage']=='Confirmed'
    assert d.queue.claim('host') is None
    Cancellation(d.connect).resume()
    assert selected(sql)['replacement']['id']==rid


def test_http_pending_is_202_not_completed(design):
    d,sql,_,_=design;active(design)
    with patch.object(status,'actor',return_value=ADMIN),patch('supabase_backend.connect',d.connect):
        response=asyncio.run(status.reset_action(request('POST',body=dict(product_gid=PID,request_id=str(uuid.uuid4())))))
    assert response.status_code==202 and json.loads(response.body)==dict(ok=False,stage='Cancelling')


def test_companion_waits_for_safe_boundary_and_preserves_files(tmp_path):
    import sys
    sys.path.insert(0,str(Path(__file__).parents[1]/'scripts/studio'))
    import auto_editions_local as local
    row=dict(context=dict(automatic=True,product_gid=PID,lease_token='synthetic'),folder=tmp_path,status='Working')
    source=tmp_path/'input.psd';source.write_bytes(b'source copy')
    archive=tmp_path/'prepared.zip';archive.write_bytes(b'generated package')
    entered=threading.Event();release=threading.Event();calls=[];cancelled=False
    def check(row,stopped=False,**kwargs):
        calls.append(stopped)
        if cancelled:row['cancel_requested']=True
        return cancelled
    @local.cancellable
    def operation(key):
        entered.set();release.wait(5)
        local.boundary(row)
        raise AssertionError('Cancelled operation proceeded to upload')
    with patch.object(local,'JOBS',{'job':row}),patch.object(local,'cancellation_check',side_effect=check):
        worker=threading.Thread(target=operation,args=('job',));worker.start();assert entered.wait(5)
        cancelled=True
        assert True not in calls
        release.set();worker.join(5);assert not worker.is_alive()
    assert row['status']=='Cancelled' and calls[-1] is True
    assert source.read_bytes()==b'source copy' and archive.read_bytes()==b'generated package'


def test_nested_worker_never_acknowledges_while_outer_operation_runs(tmp_path):
    import auto_editions_local as local
    row=dict(context=dict(automatic=True,product_gid=PID,lease_token='synthetic'),folder=tmp_path,status='Working')
    calls=[]
    def check(row,stopped=False,**kwargs):calls.append(stopped);return False
    @local.cancellable
    def inner(key):row['cancel_requested']=True;local.boundary(row)
    @local.cancellable
    def outer(key):
        inner(key)
        assert True not in calls
    with patch.object(local,'JOBS',{'job':row}),patch.object(local,'cancellation_check',side_effect=check):outer('job')
    assert calls[-1] is True and row['workers']==0


def test_pending_cancel_does_not_cancel_or_starve_another_design(design):
    d,sql,_,_=design;work=active(design)
    other='gid://shopify/Product/99999'
    sql.execute("INSERT INTO auto_edition_onboarding(product_gid,file_id,priority) VALUES(%s,'id:other',2)",(other,))
    cancel=gate(design);cancel.request(PID,str(uuid.uuid4()),'admin')
    unrelated=d.queue.claim('other-host')
    assert unrelated['product_gid']==other and not unrelated['reset_cancellation']
    assert not cancel.poll(other,str(unrelated['lease_token']),'other-host')
    with pytest.raises(ValueError):d.queue.retry(PID,'admin')
    assert selected(sql)['reset_cancellation']['stage']=='Cancelling'


def test_late_upload_after_cancellation_cannot_publish_checkpoint(design,tmp_path):
    from types import SimpleNamespace
    from starlette.requests import Request
    import auto_editions_setup_api as setup
    import auto_editions_onboarding_api as onboarding
    from auto_editions_store import Preparations
    d,sql,_,manifest=design;work=active(design);token=str(work['lease_token'])
    cancel=gate(design)
    ctx=dict(automatic=True,product_gid=PID,lease_token=token,source=manifest['source'],number=1,total=2)
    grant=dict(context=ctx,actor_id='host')
    published=[]
    def publish(*args):
        cancel.request(PID,str(uuid.uuid4()),'admin')
        # Upload has returned to the server; old operation is now fenced.
        published.append(True)
        return {}
    calls=0
    def context(req):
        nonlocal calls
        calls+=1
        if calls>1:
            assert selected(sql)['lease_token'] is None
            raise ValueError('Old preparation lease was cancelled.')
        return grant
    async def receive():return dict(type='http.request',body=b'synthetic upload',more_body=False)
    req=Request(dict(type='http',method='POST',path='/',headers=[],query_string=b''),receive)
    registry=Preparations(d.connect)
    with patch.object(setup,'grant_context',side_effect=context),patch.object(setup,'unpack',return_value=(manifest,[])),patch.object(setup.runtime,'storage',return_value=SimpleNamespace(publish_preparation=publish)),patch.object(setup.runtime,'stores',return_value=(registry,None)),patch.object(onboarding,'queue',return_value=d.queue),patch.object(registry,'save') as save:
        result=asyncio.run(setup.package(req))
    assert result.status_code==409 and published==[True]
    save.assert_not_called()
    assert selected(sql)['reset_cancellation']['stage']=='Cancelling'
    assert selected(sql)['replacement'] is None


def test_cancellation_column_inherits_private_queue_permissions(design):
    d,sql,_,_=design
    for role in ('anon','authenticated'):
        sql.execute("SELECT has_column_privilege(%s,'auto_edition_onboarding','reset_cancellation','SELECT') AS allowed",(role,))
        assert not sql.fetchone()['allowed']


def test_disconnected_companion_cannot_start_new_stage(tmp_path):
    import auto_editions_local as local
    row=dict(context=dict(automatic=True,product_gid=PID,lease_token='synthetic'),folder=tmp_path,status='Working')
    ran=[]
    @local.cancellable
    def work(key):ran.append(True)
    with patch.object(local,'JOBS',{'job':row}),patch.object(local,'HOST_FILE',tmp_path/'absent-host.dpapi'):
        work('job')
    assert not ran and row['status']=='Recovering'
    assert json.loads((tmp_path/'job-state.json').read_text())['status']=='Recovering'


def test_real_preparation_worker_stops_after_build_before_upload(tmp_path):
    import auto_editions_local as local
    ctx=dict(automatic=True,product_gid=PID,lease_token='synthetic',source={},number=1,total=2)
    row=dict(context=ctx,folder=tmp_path,grant={},status='Working')
    source=tmp_path/'input.psd';source.write_bytes(b'preserved source copy')
    lease=tmp_path/'processor.lock';lease.write_text('owned test lease')
    def build(*args,**kwargs):row['cancel_requested']=True
    def check(row,stopped=False,**kwargs):
        if stopped:assert not lease.exists()
        return row.get('cancel_requested',False)
    with patch.object(local,'JOBS',{'job':row}),patch.object(local,'cancellation_check',side_effect=check),patch.object(local,'context',return_value=ctx),patch.object(local,'processor_lease',return_value=lease),patch('scripts.prepare_auto_editions.prepare',side_effect=build),patch.object(local,'upload_prepared') as upload:
        local.prepare_worker('job',dict(number='Number',plaque='Plaque'))
    assert row['status']=='Cancelled' and not lease.exists()
    assert source.read_bytes()==b'preserved source copy'
    upload.assert_not_called()


def test_cancelled_journal_acknowledged_after_reconnection_without_recovery(tmp_path):
    import auto_editions_local as local
    folder=tmp_path/'retained';folder.mkdir()
    ctx=dict(automatic=True,product_gid=PID,lease_token='synthetic',source={})
    local.journal(dict(context=ctx,folder=folder,status='Cancelled'))
    with patch.object(local,'HOST_FILE',tmp_path/'host.dpapi'),patch.object(Path,'home',return_value=tmp_path),patch.object(local,'JOBS',{}),patch.object(local,'host_request',return_value={'cancelled':True}) as request,patch.object(local,'start') as start:
        assert not local.recover_retained({})
        assert request.call_count==2
        assert request.call_args.args[2]['stopped'] is True
        start.assert_not_called()
        data=json.loads((folder/'job-state.json').read_text())
        assert data['status']=='Cancelled' and data['cancellation_confirmed'] is True
        request.reset_mock();local.recover_retained({});request.assert_not_called()


def test_complete_clear_gate_preserves_add_state_and_numbering(design):
    from tests.test_auto_editions_reset_clear import protected as clear_protected
    d,sql,_,_=design;before=clear_protected(sql);cancel=gate(design);rid=str(uuid.uuid4())
    assert cancel.clear(PID,rid,'admin')=='Complete'
    assert cancel.clear(PID,rid,'admin')=='Complete'
    row=selected(sql);assert row['replacement']['manual_required'] and row['file_id']==''
    sql.execute('SELECT 1 FROM product_psd_mappings WHERE shopify_product_gid=%s',(PID,));assert sql.fetchone() is None
    after=clear_protected(sql)
    for key in ('edition_allocations','synthetic_certificates','next','deferred'):assert after[key]==before[key]
    sql.execute("SELECT count(*) n FROM auto_edition_onboarding_audit WHERE event='reset_cleared' AND product_gid=%s",(PID,));assert sql.fetchone()['n']==1


def test_active_complete_clear_waits_for_owner_then_returns_to_add(design):
    d,sql,_,_=design;work=active(design);cancel=gate(design);rid=str(uuid.uuid4())
    assert cancel.clear(PID,rid,'admin')=='Cancelling'
    sql.execute('SELECT 1 FROM product_psd_mappings WHERE shopify_product_gid=%s',(PID,));assert sql.fetchone()
    assert cancel.poll(PID,str(work['lease_token']),'host',True)
    row=selected(sql);assert row['replacement']['manual_required'] and row['replacement']['stage']=='Complete'
    assert row['reset_cancellation']['stage']=='Dispatched'
    sql.execute('SELECT 1 FROM product_psd_mappings WHERE shopify_product_gid=%s',(PID,));assert sql.fetchone() is None
    assert cancel.clear(PID,rid,'admin')=='Complete'
