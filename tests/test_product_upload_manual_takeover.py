"""Manual hold recovery against disposable PostgreSQL; no production/provider writes."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import uuid
from unittest.mock import patch

import pytest
from tests.test_product_upload_mapping import database, env, setup, ADMIN, PID, count, restore_provider_boundaries
from product_upload_mapping import read_edition
from product_upload_mapping_hold import acquire
from psd_mapping_store import MappingConflict, PostgresMappings
import psd_directory as psd

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / 'supabase/migrations/20261020121849_product_upload_manual_mapping_takeover.sql'


def inactive(env, *, moved=False, lost_ack=False):
    service,key,source,_ = setup(env)
    env[1].execute(MIGRATION.read_text())
    acquire(service.connect,key,ADMIN['id'],PID,source['id'])
    # Model a completed external move, resolving its current location by ID.
    current = dict(source,path_display=psd.ROOT+'/Different artwork.psd',name='Different artwork.psd',rev='b2')
    env[2].files[source['id']] = current
    with env[0].locked(key,ADMIN['id']) as (row,cur):
        op = row['data']['upload_operation'];op['product_id'] = PID
        task = op.setdefault('sync_map',{})
        task.update(state='Mapping failed',lease='old-worker',lease_until=None,
                    error='Retained failure',completed=['Finding product','Moving PSD'] if moved else ['Finding product'])
        if moved or lost_ack:task['move_intent'] = dict(source=source,to=current['path_display'])
        if moved:task['moved'] = deepcopy(current)
    return service,key,source,current


def save(service,key,meta,**kw):
    return service.mappings.attach(PID,meta,ADMIN,confirm_mismatch=True,manual_takeover_operation=key,**kw)


@pytest.mark.parametrize('mismatch',[False,True])
def test_ordinary_manual_attach_and_confirmed_mismatch_keep_existing_behaviour(env,mismatch):
    service,key,meta,_=setup(env)
    env[1].execute(MIGRATION.read_text())
    name='Different artwork.psd' if mismatch else 'New Art.psd'
    current=dict(meta,name=name,path_display=psd.ROOT+'/'+name)
    if mismatch:
        with pytest.raises(ValueError,match='Filename differs'):
            service.mappings.attach(PID,current,ADMIN)
    saved=service.mappings.attach(PID,current,ADMIN,confirm_mismatch=mismatch)
    assert saved['verified'] and saved['file_path']==current['path_display']
    assert count(env[1],'auto_edition_onboarding')==1
    assert count(env[1],'product_upload_mapping_holds')==0
    assert not env[0].read(key,ADMIN['id'])['data']['upload_operation'].get('sync_map')


@pytest.mark.parametrize('moved,lost_ack',[(False,False),(True,False),(False,True)])
def test_explicit_takeover_preserves_progress_and_persists_verified_manual_link(env,moved,lost_ack):
    service,key,source,current=inactive(env,moved=moved,lost_ack=lost_ack)
    before=deepcopy(env[0].read(key,ADMIN['id']))
    edition=read_edition(service.connect,PID)
    with pytest.raises(MappingConflict,match='Confirm manual takeover') as prompt:
        service.mappings.attach(PID,current,ADMIN,confirm_mismatch=True)
    assert prompt.value.manual_takeover_operation==key
    assert env[0].read(key,ADMIN['id'])==before
    with pytest.raises(MappingConflict):save(service,str(uuid.uuid4()),current)
    result=save(service,key,current)
    assert result['verified'] and result['dropbox_file_id']==source['id']
    fresh=PostgresMappings(service.connect).read_one(PID)
    assert fresh['verified'] and fresh['file_path']==current['path_display']
    task=env[0].read(key,ADMIN['id'])['data']['upload_operation']['sync_map']
    assert task['state']=='Manually mapped' and task['lease'] is None
    assert task['manual_takeover']['edition_id']==edition['id']
    assert task['manual_takeover']['source']==current
    old=before['data']['upload_operation']['sync_map']
    for field in ('moved','move_intent','completed','error'):
        assert task.get(field)==old.get(field)
    assert read_edition(service.connect,PID)==edition
    assert count(env[1],'product_upload_mapping_holds')==1  # retained, never deleted
    assert count(env[1],'product_psd_mappings')==1
    assert count(env[1],'auto_edition_onboarding')==1  # ordinary Save admission
    assert not env[2].api.move_path.called and not service.shopify.method_calls
    # Reopening the saved selection does not duplicate either link or audit.
    n=count(env[1],'product_psd_mapping_audit')
    assert save(service,key,current,expected_file_id=source['id'])['verified']
    assert count(env[1],'product_psd_mapping_audit')==n


@pytest.mark.parametrize('kind',['lease','expired_inflight','preparing','rendering','changed_content','other_owner','stale_selection'])
def test_takeover_refuses_active_or_conflicting_work_without_releasing_hold(env,kind):
    service,key,source,current=inactive(env)
    if kind=='lease':
        with env[0].locked(key,ADMIN['id']) as (row,cur):
            row['data']['upload_operation']['sync_map']['lease_until']=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()
    if kind=='preparing':
        # Simulate unexpected retained work admitted before the hold was acquired.
        env[1].execute('ALTER TABLE auto_edition_onboarding DISABLE TRIGGER upload_hold_onboarding')
        env[1].execute("INSERT INTO auto_edition_onboarding(product_gid,file_id,status) VALUES(%s,%s,'Preparing')",(PID,source['id']))
    if kind=='rendering':
        env[1].execute('ALTER TABLE auto_edition_jobs DISABLE TRIGGER upload_hold_render')
        env[1].execute("INSERT INTO auto_edition_jobs(id,actor_id,payload,status) VALUES(%s,'fixture',%s::jsonb,'Generating')",('a'*64,json.dumps({'identity':{'source':{'product_gid':PID,'file_id':source['id']}}})))
    if kind=='changed_content':current['content_hash']='b'*64
    if kind=='other_owner':env[1].execute("UPDATE product_upload_mapping_holds SET product_gid='gid://shopify/Product/999'")
    before=env[0].read(key,ADMIN['id'])
    if kind=='expired_inflight':
        # PGlite serialises transactions; emulate psycopg's NOWAIT result. Real
        # multi-connection lock contention is a separate integration limitation.
        class Locked(Exception):sqlstate='55P03'
        original=service.mappings.connect
        class Connection:
            def __enter__(self):self.base=original();self.base.__enter__();return self
            def __exit__(self,*a):return self.base.__exit__(*a)
            def cursor(self):
                cur=self.base.cursor()
                class Cursor:
                    def __enter__(self):return self
                    def __exit__(self,*a):pass
                    def execute(self,sql,args=()):
                        if 'FOR UPDATE NOWAIT' in sql:raise Locked()
                        return cur.execute(sql,args)
                    def fetchone(self):return cur.fetchone()
                    def fetchall(self):return cur.fetchall()
                return Cursor()
        with patch.object(service.mappings,'connect',Connection):
            with pytest.raises(MappingConflict,match='worker is active'):save(service,key,current)
    else:
        with pytest.raises((MappingConflict,ValueError)):
            save(service,key,current,expected_file_id='id:stale' if kind=='stale_selection' else '')
    assert env[0].read(key,ADMIN['id'])==before
    assert count(env[1],'product_psd_mappings')==0
    assert count(env[1],'product_upload_mapping_holds')==1


def test_retire_sibling_attempts_and_database_fence_old_code_retries(env):
    service,key,source,current=inactive(env,moved=True)
    sibling=str(uuid.uuid4())
    original=deepcopy(env[0].read(key,ADMIN['id']))
    original['data']['upload_operation']['id']=sibling
    env[1].execute('INSERT INTO product_upload_intakes(id,actor_id,mode,data) VALUES(%s,%s,%s,%s::jsonb)',
                   (sibling,ADMIN['id'],original['mode'],json.dumps(original['data'])))
    save(service,key,current)
    expected=service.mappings.read_one(PID)
    for attempt in (key,sibling):
        with pytest.raises(ValueError,match='retired'):service.map(attempt,ADMIN)
        with pytest.raises(ValueError,match='retired'):
            with service._guard(attempt,ADMIN,'old-worker'):pass
        # Simulate an older deployed process that doesn't know the new app check.
        with pytest.raises(Exception,match='retired'):
            with env[0].locked(attempt,ADMIN['id']) as (row,cur):
                row['data']['upload_operation']['sync_map'].update(state='Mappingâ€¦',lease='late-worker')
        with pytest.raises(Exception,match='retired'):
            with service.connect() as conn,conn.cursor() as cur:
                cur.execute('DELETE FROM product_upload_intakes WHERE id=%s',(attempt,))
    assert service.mappings.read_one(PID)==expected
    assert count(env[1],'product_psd_mappings')==1 and not env[2].api.move_path.called


def test_schema_absent_fails_closed_for_held_save_but_not_ordinary_mapping(env):
    service,key,source,_=setup(env)
    acquire(service.connect,key,ADMIN['id'],PID,source['id'])
    current=dict(source,name='Art.psd',path_display=psd.ROOT+'/Art.psd')
    with pytest.raises(MappingConflict,match='migration is required'):save(service,key,current)
    assert count(env[1],'product_psd_mappings')==0


def test_actual_save_endpoint_offers_then_commits_the_exact_takeover(env):
    import asyncio
    from unittest.mock import patch
    import files_upload_api as api
    import psd_mapping_store
    from tests.test_psd_picker_api import request
    service,key,source,current=inactive(env)
    payload=dict(product_gid=PID,file_id=source['id'],confirm_mismatch=True)
    with patch.object(api,'_psd_attach_user',return_value=ADMIN), \
         patch.object(api,'_dropbox_context',return_value={'access_token':'local-fixture'}), \
         patch.object(api.dropbox_integration,'psd_open_metadata',return_value=current) as metadata, \
         patch.object(psd_mapping_store,'STORE',service.mappings):
        prompt=asyncio.run(api.attach_product_psd(request('POST',payload)))
        assert prompt.status_code==409
        assert json.loads(prompt.body)['manual_takeover_operation']==key
        assert count(env[1],'product_psd_mappings')==0
        payload['manual_takeover_operation']=key
        result=asyncio.run(api.attach_product_psd(request('POST',payload)))
        assert result.status_code==200, result.body
        assert json.loads(result.body)['mapping']['verified']
        metadata.assert_called_with('local-fixture',source['id'],include_preview=False)
    assert service.mappings.read_one(PID)['file_path']==current['path_display']


def test_takeover_migration_keeps_hold_immutable_and_does_not_grant_browser_access(env):
    service,key,source,current=inactive(env)
    sql=env[1]
    for role in ('anon','authenticated'):
        sql.execute("SELECT has_function_privilege(%s,'public.guard_upload_manual_takeover()','EXECUTE') AS allowed",(role,))
        assert not sql.fetchone()['allowed']
    for privilege in ('UPDATE','DELETE'):
        sql.execute("SELECT has_table_privilege('service_role','public.product_upload_mapping_holds',%s) AS allowed",(privilege,))
        assert not sql.fetchone()['allowed']
    sql.execute('ALTER TABLE product_upload_intakes DISABLE TRIGGER upload_manual_takeover_terminal')
    with pytest.raises(MappingConflict,match='retry guard'):save(service,key,current)
    assert count(sql,'product_psd_mappings')==0
