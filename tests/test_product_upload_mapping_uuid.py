"""Production UUID run IDs with real local PostgreSQL; all provider writes mocked."""
from copy import deepcopy
import uuid
import pytest
from tests.test_product_upload_mapping import database, env, setup, ADMIN, PID, count
from product_upload_mapping import read_edition


def uuid_run(env, service):
    sql=env[1]
    sql.execute("ALTER TABLE edition_runs ALTER COLUMN id DROP DEFAULT")
    sql.execute("ALTER TABLE edition_runs ALTER COLUMN id TYPE uuid USING ('00000000-0000-0000-0000-' || lpad(id::text,12,'0'))::uuid")
    sql.execute("ALTER TABLE edition_products ALTER COLUMN active_edition_run_id TYPE uuid USING ('00000000-0000-0000-0000-' || lpad(active_edition_run_id::text,12,'0'))::uuid")
    original=service.connect
    def adapt(row):
        if row is None:return None
        row=dict(row)
        # PGlite's HTTP fixture returns strings. Psycopg returns native UUIDs.
        for k,v in row.items():
            if isinstance(v,str) and len(v)==36:
                try:row[k]=uuid.UUID(v)
                except ValueError:pass
        return row
    class Connection:
        def __init__(self):self.base=original()
        def __enter__(self):self.base.__enter__();return self
        def __exit__(self,*args):return self.base.__exit__(*args)
        def cursor(self):
            cur=self.base.cursor()
            class Cursor:
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def execute(self,*args):return cur.execute(*args)
                def fetchone(self):return adapt(cur.fetchone())
                def fetchall(self):return [adapt(r) for r in cur.fetchall()]
            return Cursor()
    service.connect=Connection
    service.store.connect=Connection
    service.mappings._connect=Connection
    return Connection


@pytest.mark.parametrize('failure',[None,'unavailable','move_ack','link'])
def test_uuid_run_finalisation_and_retry(env,failure):
    service,key,meta,p=setup(env)
    connect=uuid_run(env,service)
    before=deepcopy(read_edition(connect,PID))
    original_move=env[2].api.move_path.side_effect
    original_link=service.mappings.attach
    if failure=='unavailable':env[2].api.move_path.side_effect=ConnectionError('simulated Dropbox outage')
    if failure=='move_ack':
        def lost(*a,**kw):original_move(*a,**kw);raise ConnectionError('simulated lost response')
        env[2].api.move_path.side_effect=lost
    if failure=='link':service.mappings.attach=lambda *a,**kw:(_ for _ in ()).throw(ConnectionError('simulated database outage'))
    result=service.map(key,ADMIN)
    if failure:
        assert result['state']=='Mapping failed',result
        assert 'Moving PSD' in result['reason'] or 'Saving mapping' in result['reason']
        assert count(env[1],'product_psd_mappings')==0
        env[2].api.move_path.side_effect=original_move
        service.mappings.attach=original_link
        result=service.map(key,ADMIN)
    assert result['state']=='Mapped',result
    assert result['run_id']==str(before['run_id'])
    assert service.map(key,ADMIN)['state']=='Mapped'
    assert service.status(key,ADMIN)['state']=='Mapped'
    assert env[2].api.move_path.call_count==(2 if failure=='unavailable' else 1)
    assert count(env[1],'product_psd_mappings')==1
    assert read_edition(connect,PID)==before
    assert not service.shopify.method_calls
    service.onboard.assert_not_called()


def test_earlier_hold_offers_original_attempt_without_taking_over(env):
    from product_upload_mapping_hold import acquire
    from product_upload_dropbox import select
    service,key,meta,p=setup(env)
    acquire(service.connect,key,ADMIN['id'],PID,meta['id'])
    with pytest.raises(ValueError,match='Another upload') as other_account:
        acquire(service.connect,str(uuid.uuid4()),'another-account',PID,meta['id'])
    assert not hasattr(other_account.value,'resume_upload_id')
    new_key=str(uuid.uuid4())
    select(service.connect,env[2],new_key,ADMIN['id'],'LIVE',meta['id'],meta['rev'])
    old=service.store.read(key,ADMIN['id'])
    with service.store.locked(new_key,ADMIN['id']) as (row,cur):
        row['data'].update(mockups_exported=True,mockup_saves=deepcopy(old['data']['mockup_saves']))
        row['data']['upload_operation'].update(product_id=PID,output=deepcopy(old['data']['upload_operation']['output']))
    result=service.map(new_key,ADMIN)
    assert result['state']=='Mapping failed' and result['resume_upload_id']==key
    assert not env[2].api.move_path.called
    assert count(env[1],'product_upload_mapping_holds')==1
    assert service.map(key,ADMIN)['state']=='Mapped'
    assert service.map(key,ADMIN)['state']=='Mapped'
    assert env[2].api.move_path.call_count==1
