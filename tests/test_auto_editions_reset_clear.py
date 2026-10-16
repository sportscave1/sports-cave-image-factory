"""Complete reset on isolated SQL, synthetic mappings and edition allocations only."""
import json
from pathlib import Path
from unittest.mock import patch,Mock
import uuid
import pytest
import auto_editions_status as status
import psd_directory as psd
from psd_mapping_store import PostgresMappings
from auto_editions_onboarding_store import Queue
from tests.test_auto_editions_reset import design,selected
from tests.test_auto_editions_discovery import store,database,pglite_database,PID,asset,due,register
from tests.test_auto_editions_api import ADMIN


def key():return str(uuid.uuid4())


def protected(sql):
    result={}
    for table in ('product_psd_mappings','auto_edition_layouts','edition_products','edition_allocations','synthetic_certificates'):
        sql.execute('SELECT * FROM '+table);result[table]=sql.fetchall()
    sql.execute('SELECT next_edition_number FROM edition_products WHERE shopify_product_gid=%s',(PID,));result['next']=sql.fetchone()['next_edition_number']
    sql.execute('SELECT * FROM auto_edition_onboarding WHERE product_gid<>%s ORDER BY product_gid',(PID,));result['deferred']=sql.fetchall()
    return result


def test_complete_reset_preserves_numbering_history_and_invalidates_mapping_caches(design):
    d,sql,reset,old=design;cache=PostgresMappings(d.connect);mapping=cache.read();before=protected(sql)
    sql.execute('SELECT * FROM auto_edition_preparations');preparations=sql.fetchall()
    rid=key();assert reset.clear(PID,rid,'admin')=='Complete'
    row=selected(sql);assert row['file_id']=='' and row['source'] is None and row['preparation_hash'] is None
    assert row['status']=='Blocked' and row['lease_token'] is None and row['replacement']['manual_required']
    assert PID not in cache.read() and PID not in PostgresMappings(d.connect).read()
    assert psd.display_link({'shopify_product_gid':PID},cache.read(),missing='Add').endswith('#Add')
    sql.execute('SELECT * FROM auto_edition_layouts WHERE product_gid=%s',(PID,));assert sql.fetchall()==[]
    sql.execute('SELECT * FROM auto_edition_preparations');assert sql.fetchall()==preparations
    sql.execute("SELECT detail FROM auto_edition_onboarding_audit WHERE event='reset_cleared'");detail=sql.fetchone()['detail']
    assert detail['mapping_before']['dropbox_file_id']==mapping[PID]['dropbox_file_id'] and detail['layouts_before']
    after=protected(sql)
    for field in ['edition_products','edition_allocations','synthetic_certificates','next','deferred']:assert before[field]==after[field]
    assert reset.clear(PID,rid,'admin')=='Complete'
    sql.execute("SELECT count(*) AS n FROM auto_edition_onboarding_audit WHERE event='reset_cleared'");assert sql.fetchone()['n']==1
    projected=status.batch(d.connect,[PID],writable=True)['rows'][0]
    assert projected['status']=='Not Connected' and projected['mapping_file_id'] is None and projected['preparation_hash'] is None
    assert projected['checkpoint']=='Reset — manually Add PSD'


def test_discovery_backfill_refresh_and_old_worker_cannot_restore_reset_mapping(design):
    d,sql,reset,old=design;mapping=PostgresMappings(d.connect).read();due(sql);claim=d.claim()
    reset.clear(PID,key(),'admin')
    sql.execute('SELECT * FROM auto_edition_discovery WHERE product_gid=%s',(PID,));request=sql.fetchone()
    assert d.reconcile(claim['lease_token'],request,asset()) is None
    register((d,sql),'new-webhook-event')
    assert d.reconcile(claim['lease_token'],{**request,'event_id':'new-webhook-event'},asset()) is None
    assert PID not in PostgresMappings(d.connect).read()
    report=PostgresMappings(d.connect).backfill(mapping);assert report['insert']==[]
    assert d.queue.claim('synthetic-host') is None
    with pytest.raises(ValueError):d.queue.checkpoint(PID,key(),'stale-host','Blocked','old result',digest='a'*64)
    assert selected(sql)['preparation_hash'] is None
    with pytest.raises(ValueError):d.queue.retry(PID,'admin')
    with pytest.raises(ValueError):d.queue.prepare_now(PID,'admin')
    with pytest.raises(ValueError,match='Manually Add'):reset.request(PID,key(),'admin')
    # Even a stale priority update cannot bypass the reset marker at claim time.
    sql.execute("UPDATE auto_edition_onboarding SET status='Awaiting preparation',priority=10 WHERE product_gid=%s",(PID,))
    assert d.queue.claim('stale-host') is None


def test_manual_add_restarts_once_and_old_reset_retry_cannot_unlink_new_mapping(design):
    d,sql,reset,old=design;rid=key();reset.clear(PID,rid,'admin')
    mappings=PostgresMappings(d.connect);mappings.attach(PID,asset(),ADMIN)
    row=selected(sql);assert row['file_id']=='id:original' and row['status']=='Awaiting preparation'
    assert row['preparation_hash'] is None and row['replacement'] is None
    mappings.attach(PID,asset(),ADMIN,expected_file_id='id:original')
    assert reset.clear(PID,rid,'admin')=='Complete' and PID in mappings.read()
    claim=d.queue.claim('host');assert claim['product_gid']==PID
    assert d.queue.claim('host') is None
    with pytest.raises(ValueError,match='active or uncertain'):reset.clear(PID,key(),'admin')


@pytest.mark.parametrize('state',['Preparing','expired'])
def test_active_and_uncertain_companion_operations_block_reset(design,state):
    d,sql,reset,_=design;sql.execute("UPDATE auto_edition_onboarding SET status='Preparing',lease_token=%s,lease_until=now()-interval '1 minute' WHERE product_gid=%s",(key(),PID))
    before=protected(sql)
    with pytest.raises(ValueError,match='active or uncertain'):reset.clear(PID,key(),'admin')
    assert protected(sql)==before


@pytest.mark.parametrize('state',['Queued','Generating'])
def test_order_operations_block_selected_reset_without_job_mutation(design,state):
    d,sql,reset,_=design;payload=json.dumps(dict(identity=dict(source=dict(product_gid=PID))))
    sql.execute('INSERT INTO auto_edition_jobs(id,payload,actor_id,status) VALUES(%s,%s::jsonb,%s,%s)',('a'*64,payload,'synthetic-owner',state))
    before=protected(sql)
    with pytest.raises(ValueError,match='order artwork operation'):reset.clear(PID,key(),'admin')
    assert protected(sql)==before
    sql.execute('SELECT status FROM auto_edition_jobs');assert sql.fetchone()['status']==state


@pytest.mark.parametrize('state',['Pending','Processing'])
def test_review_jobs_cancel_only_pending_and_preserve_history(design,state):
    d,sql,reset,_=design;sql.execute(Path('supabase/migrations/20261016071758_auto_editions_bulk_operations.sql').read_text())
    sql.execute('INSERT INTO auto_edition_review_jobs(id,product_gid,preparation_hash,actor_id,state) VALUES(%s,%s,%s,%s,%s)',(key(),PID,'a'*64,'admin',state))
    if state=='Processing':
        with pytest.raises(ValueError,match='currently approving'):reset.clear(PID,key(),'admin')
        assert PID in PostgresMappings(d.connect).read()
    else:reset.clear(PID,key(),'admin')
    sql.execute('SELECT state FROM auto_edition_review_jobs');assert sql.fetchone()['state']==('Skipped' if state=='Pending' else state)


def test_reset_audit_failure_rolls_back_every_active_association(design):
    d,sql,reset,_=design;before=protected(sql);checkpoint=selected(sql)
    with patch.object(PostgresMappings,'_audit',side_effect=RuntimeError('audit unavailable')):
        with pytest.raises(RuntimeError):reset.clear(PID,key(),'admin')
    assert protected(sql)==before and selected(sql)==checkpoint
    sql.execute("SELECT 1 FROM auto_edition_onboarding_audit WHERE event='reset_cleared'");assert sql.fetchall()==[]


def test_other_design_active_job_is_untouched(design):
    d,sql,reset,_=design
    sql.execute("UPDATE auto_edition_onboarding SET status='Preparing',lease_token=%s,lease_until=now()+interval '1 hour' WHERE product_gid='gid://shopify/Product/1000'",(key(),))
    before=protected(sql);reset.clear(PID,key(),'admin');assert protected(sql)['deferred']==before['deferred']


def test_reset_permissions_migration_is_service_only_and_checksum_bound(design):
    d,sql,reset,_=design
    import hashlib,run_migrations
    name='20261016120000_auto_editions_reset_mapping_permissions.sql';source=Path('supabase/migrations')/name
    assert hashlib.sha256(source.read_bytes()).hexdigest()==run_migrations.REVIEWED_MIGRATION_SHA256[name]
    assert name in run_migrations.DEPLOYMENT_MIGRATIONS
    sql.execute(source.read_text())
    for table in ('product_psd_mappings','auto_edition_layouts'):
        sql.execute("SELECT has_table_privilege('service_role',%s,'DELETE') AS allowed",(table,));assert sql.fetchone()['allowed']
        for role in ('anon','authenticated'):
            sql.execute("SELECT has_table_privilege(%s,%s,'DELETE') AS allowed",(role,table));assert not sql.fetchone()['allowed']
