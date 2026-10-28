from copy import deepcopy
from pathlib import Path
import pytest
from auto_editions_onboarding import detect,preparation_scale,NeedsRepair
from auto_editions_onboarding_store import Queue
from tests.test_auto_editions_jobs import database


def inspection():
    return dict(document=dict(width_px=2835,height_px=2004),layers=[
        dict(path=[dict(name='001 / 100')],kind='text',text='001 / 100',visible=True,editable=True,
             fonts=[dict(installed=True)],layout=dict(font='ExactFont'),bounds_px=[420,1820,580,1850]),
        dict(path=[dict(name='limited-edition-plaque')],kind='smart_object',visible=True,
             bounds_px=[170,1730,680,1900])])


def test_own_position_and_style_preserved():
    result=detect(inspection(),100)
    assert result['plaque_bounds']==[170,1730,680,1900]
    assert result['number_layer']=='001 / 100' and result['font']=='ExactFont'
    assert preparation_scale(result['source_dimensions'])==4
    assert preparation_scale([11340,8016])==1
    assert preparation_scale([2004,2835])==4


@pytest.mark.parametrize('suffix', ['1', '2', '12'])
@pytest.mark.parametrize('kind', ['smart_object', 'raster'])
def test_download_copy_plaque_retains_exact_layer_identity(suffix,kind):
    data=inspection();name=f'limited-edition-plaque ({suffix})'
    data['layers'][1]['path'][0]['name']=name
    data['layers'][1]['kind']=kind
    original=deepcopy(data)
    result=detect(data,100)
    assert result['plaque_layer']==name
    assert result['plaque_bounds']==[170,1730,680,1900]
    assert result['source_dimensions']==[2835,2004]
    assert data==original


@pytest.mark.parametrize('case', ['duplicate', 'canonical_and_copy', 'nested', 'chain',
                                 'outside', 'text', 'arbitrary', 'trailing', 'zero'])
def test_download_copy_plaque_does_not_relax_role_safety(case):
    data=inspection();plaque=data['layers'][1]
    plaque['path'][0]['name']='limited-edition-plaque (1)'
    if case in ('duplicate','canonical_and_copy'):
        other=deepcopy(plaque)
        other['path'][0]['name']='limited-edition-plaque' if case=='canonical_and_copy' else 'limited-edition-plaque (2)'
        data['layers'].append(other)
    if case=='nested':plaque['path'].append(dict(name='nested'))
    if case=='chain':plaque['smart_object_chain']=[dict(name='parent')]
    if case=='outside':data['layers'][0]['bounds_px']=[800,1820,980,1850]
    if case=='text':plaque['kind']='text'
    if case=='arbitrary':plaque['path'][0]['name']='custom plaque (1)'
    if case=='trailing':plaque['path'][0]['name']+=' copy'
    if case=='zero':plaque['path'][0]['name']='limited-edition-plaque (0)'
    with pytest.raises(NeedsRepair):detect(data,100)


@pytest.mark.parametrize('kind',['duplicate','nested','font','locked','total','outside','narrow'])
def test_uncertain_layers_never_enabled(kind):
    data=inspection();n=data['layers'][0]
    if kind=='duplicate':data['layers'].append(deepcopy(n))
    if kind=='nested':n['path'].append(dict(name='Number'))
    if kind=='font':n['fonts'][0]['installed']=False
    if kind=='locked':n['locked']=True
    if kind=='total':n['text']='001 / 200'
    if kind=='outside':n['bounds_px']=[800,1820,980,1850]
    if kind=='narrow':n['text']='1 / 100'
    with pytest.raises(NeedsRepair):detect(data,100)


def setup_queue(database):
    jobs,sql=database
    schema=(Path(__file__).parents[1]/'supabase/migrations/20261014053326_auto_editions_onboarding.sql').read_text()
    for statement in schema.split(';'):
        if statement.strip():sql.execute(statement)
    sql.execute('CREATE TABLE product_psd_mappings(shopify_product_gid text PRIMARY KEY,dropbox_file_id text)')
    sql.execute("INSERT INTO product_psd_mappings VALUES('p','f')")
    return Queue(jobs.connect),sql


def test_durable_queue_reuses_success_and_fences_stale_workers(database):
    queue,sql=setup_queue(database)
    queue.enqueue('p','f','admin');queue.enqueue('p','f','admin')
    sql.execute('SELECT count(*) n FROM auto_edition_onboarding');assert sql.fetchone()['n']==1
    first=queue.claim('admin');assert first and queue.claim('admin') is None
    sql.execute("UPDATE auto_edition_onboarding SET lease_until=now()-interval '1 second'")
    second=queue.claim('admin');assert second['lease_token']!=first['lease_token']
    with pytest.raises(ValueError):queue.checkpoint('p',first['lease_token'],'admin','Cloud Ready')
    queue.checkpoint('p',second['lease_token'],'admin','Needs PSD Repair','Missing font')
    assert queue.claim('admin') is None
    queue.retry('p','admin');third=queue.claim('admin');assert third['attempts']==1
    queue.checkpoint('p',third['lease_token'],'admin','Blocked','Review required')
    queue.enqueue('p','f','admin');assert queue.claim('admin') is None


def test_replaced_mapping_invalidates_old_preparation_lease(database):
    queue,sql=setup_queue(database);queue.enqueue('p','f','admin');first=queue.claim('admin')
    sql.execute("UPDATE product_psd_mappings SET dropbox_file_id='new'")
    with pytest.raises(ValueError):queue.enqueue('p','f','admin')
    queue.enqueue('p','new','admin')
    with pytest.raises(ValueError):queue.checkpoint('p',first['lease_token'],'admin','Cloud Ready')


def test_manual_attachment_is_durable_and_reconnect_retry_keeps_one_job(database):
    from psd_mapping_store import PostgresMappings
    import psd_directory as psd
    jobs,sql=database;root=Path(__file__).parents[1]
    sql.execute((root/'supabase/migrations/20261014053326_auto_editions_onboarding.sql').read_text())
    sql.execute((root/'scripts/sql/product_psd_mapping.sql').read_text())
    sql.execute('CREATE TABLE edition_products(shopify_product_gid text,shopify_product_id text,product_title text,shopify_handle text,edition_total int,next_edition_number int)')
    pid='gid://shopify/Product/1'
    sql.execute("INSERT INTO edition_products VALUES(%s,%s,'Fixture','fixture',100,50)",(pid,pid))
    meta={'.tag':'file','id':'id:fixture','name':'Fixture.psd','path_display':psd.ROOT+'/Fixture.psd'}
    actor=dict(id='admin',role='admin',is_active=True)
    store=PostgresMappings(jobs.connect);queue=Queue(jobs.connect)
    store.attach(pid,meta,actor)
    # No Companion is running: the same persisted checkpoint remains queued.
    sql.execute('SELECT status FROM auto_edition_onboarding');assert sql.fetchone()['status']=='Awaiting preparation'
    store.attach(pid,meta,actor,expected_file_id=meta['id'])
    assert PostgresMappings(jobs.connect).read()[pid]['dropbox_file_id']==meta['id']
    first=queue.claim('admin');assert first['file_id']==meta['id'] and queue.claim('admin') is None
    sql.execute("UPDATE auto_edition_onboarding SET lease_until=now()-interval '1 second'")
    resumed=queue.claim('admin');assert resumed['lease_token']!=first['lease_token']
    with pytest.raises(ValueError):queue.checkpoint(pid,first['lease_token'],'admin','Cloud Ready')
    queue.checkpoint(pid,resumed['lease_token'],'admin','Needs PSD Repair','Fixture role repair')
    queue.retry(pid,'admin')
    with pytest.raises(ValueError):queue.retry(pid,'admin')
    assert queue.claim('admin')['file_id']==meta['id']
    for table in ('auto_edition_onboarding','product_psd_mappings','product_psd_mapping_audit'):
        sql.execute('SELECT count(*) AS n FROM '+table);assert sql.fetchone()['n']==1
    sql.execute('SELECT next_edition_number FROM edition_products');assert sql.fetchone()['next_edition_number']==50
    sql.execute('SELECT count(*) AS n FROM auto_edition_jobs');assert sql.fetchone()['n']==0


def test_preparation_metrics_commit_with_checkpoint_or_not_at_all(database):
    from unittest.mock import patch
    queue,sql=setup_queue(database);queue.enqueue('p','f','admin');row=queue.claim('admin')
    sql.execute("INSERT INTO auto_edition_preparations(hash,manifest,proofs,receipts,created_by) VALUES(%s,'{}','[]','{}','admin')",('a'*64,))
    original=queue.audit
    def fail_metrics(cur,pid,actor,event,detail=None):
        if event=='preparation_metrics':raise RuntimeError('receipt failed')
        return original(cur,pid,actor,event,detail)
    with patch.object(queue,'audit',side_effect=fail_metrics):
        with pytest.raises(RuntimeError):
            queue.checkpoint('p',row['lease_token'],'admin','Blocked','Review',digest='a'*64,metrics={'validation_seconds':4})
    sql.execute("SELECT status FROM auto_edition_onboarding WHERE product_gid='p'")
    assert sql.fetchone()['status']=='Preparing'
    queue.checkpoint('p',row['lease_token'],'admin','Blocked','Review',digest='a'*64,metrics={'validation_seconds':4})
    sql.execute("SELECT detail FROM auto_edition_onboarding_audit WHERE event='preparation_metrics'")
    receipt=sql.fetchone()['detail']
    assert receipt['validation_seconds']==4 and receipt['preparation_hash']=='a'*64


def test_completed_receipt_fences_actor_lease_and_mapping(database):
    queue,sql=setup_queue(database);queue.enqueue('p','f','admin');row=queue.claim('admin')
    sql.execute("INSERT INTO auto_edition_preparations(hash,manifest,proofs,receipts,created_by) VALUES(%s,%s::jsonb,'[]','{}','admin')",
                ('b'*64,'{"source":{"product_gid":"p","file_id":"f","revision":"r1"}}'))
    queue.checkpoint('p',row['lease_token'],'admin','Blocked','Review',digest='b'*64,metrics={'validation_seconds':7})
    found=queue.completed_receipt('p',row['lease_token'],'admin')
    assert found['preparation_hash']=='b'*64 and found['timings']['validation_seconds']==7
    assert queue.completed_receipt('p',row['lease_token'],'other') is None
    assert queue.completed_receipt('p','00000000-0000-0000-0000-000000000000','admin') is None
    sql.execute("UPDATE product_psd_mappings SET dropbox_file_id='changed'")
    assert queue.completed_receipt('p',row['lease_token'],'admin') is None
