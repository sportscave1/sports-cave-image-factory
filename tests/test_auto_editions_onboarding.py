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
