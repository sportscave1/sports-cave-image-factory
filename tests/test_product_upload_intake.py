"""Real disposable PostgreSQL (PGlite), real application services; providers simulated."""
import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import struct
import time
import uuid
from unittest.mock import Mock, patch

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from product_upload_intake import Intakes, CHUNK, MAX_BYTES, inspect_chunk, public
from product_upload_services import Handoff, resolve_products, register_product, reconcile
from tests.test_auto_editions_jobs import database
from tests.test_auto_editions_api import ADMIN

ROOT = Path(__file__).resolve().parents[1]
PID = 'gid://shopify/Product/987'


def psd(size=128, depth=8, colour=3):
    header=struct.pack('>4sH6sHIIHH',b'8BPS',1,b'\0'*6,3,100,200,depth,colour)
    return header + struct.pack('>III',0,0,8) + b'\0'*8 + b'\0\0' + b'\0'*(size-48)


def digest(data):
    return hashlib.sha256(b''.join(hashlib.sha256(data[i:i+CHUNK]).digest() for i in range(0,len(data),CHUNK))).hexdigest()


class DiskDropbox:
    """Provider boundary double; files/offsets survive app service recreation."""
    def __init__(self, root):
        self.root=root; root.mkdir(exist_ok=True)
        self.files={};self.sessions={};self.calls=[];self.lose_append=False;self.lose_finish=False
    def destination(self,key):
        import psd_directory
        return psd_directory.ROOT+'/product-upload-'+key+'.psd'
    def start(self):
        sid=uuid.uuid4().hex;self.sessions[sid]=self.root/sid;self.sessions[sid].touch();return sid
    def append(self,sid,offset,data):
        path=self.sessions[sid];size=path.stat().st_size
        if offset!=size:
            error=RuntimeError('incorrect_offset');error.correct_offset=size;raise error
        with path.open('ab') as f:f.write(data)
        self.calls.append(('append',len(data)))
        if self.lose_append:
            self.lose_append=False;raise RuntimeError('acknowledgement lost')
    def finish(self,sid,size,path):
        import auto_editions as ae
        file=self.sessions[sid]
        meta=dict(id='id:'+sid,rev='a1',content_hash=ae.file_hash(file,dropbox=True),size=file.stat().st_size,name=path.rsplit('/',1)[1],path_display=path,**{'.tag':'file'})
        self.files[path]=meta;self.files[meta['id']]=meta;self.calls.append(('finish',size))
        if self.lose_finish:self.lose_finish=False;raise RuntimeError('finish response lost')
        return meta
    def metadata_if_present(self,key):return deepcopy(self.files.get(key))
    def mockups(self):return dict(id='id:mockups',path='/Sportscave Team Folder/04_OUTPUT/product-images')


@pytest.fixture
def env(database,tmp_path,monkeypatch):
    jobs,sql=database
    # Existing fixture executes genuine PostgreSQL SQL. Its outer context commits
    # at exit; canonical registration's explicit commit needs this adapter method.
    jobs.connect.commit=lambda self:None
    for name in ('scripts/sql/product_psd_mapping.sql','supabase/migrations/20261014053326_auto_editions_onboarding.sql',
                 'supabase/migrations/20261014234210_auto_editions_v15_discovery.sql','supabase/migrations/20261017010350_product_upload_intakes.sql'):
        sql.execute((ROOT/name).read_text())
    sql.execute('''CREATE TABLE edition_products(id bigserial PRIMARY KEY,shopify_product_id text,shopify_product_gid text,
       shopify_handle text UNIQUE,product_title text,edition_total int,next_edition_number int,last_assigned_edition int,
       sold_count int,remaining_count int,edition_status text,edition_name text,active bool,is_active bool,sold_out bool,
       is_sold_out bool,featured_image_url text,raw jsonb,metafields_sync_status text,last_metafield_error text,
       synced_at timestamptz,updated_at timestamptz,active_edition_run_id bigint);
       CREATE TABLE edition_runs(id bigserial PRIMARY KEY,edition_product_id bigint,shopify_product_id text,shopify_handle text,
       product_title text,edition_name text,edition_total int,next_edition_number int,status text,started_at timestamptz,updated_at timestamptz);
       CREATE TABLE edition_orders(shopify_product_id text,shopify_product_gid text,shopify_handle text,product_handle text);
       CREATE TABLE edition_allocation_tombstones(shopify_product_gid text);
       CREATE TABLE shopify_products(shopify_product_id text PRIMARY KEY,legacy_resource_id text,shopify_product_gid text,title text,
       handle text,status text,vendor text,product_type text,online_store_url text,admin_url text,image_url text,featured_image_url text,
       raw_json jsonb,raw jsonb,synced_at timestamptz,updated_at timestamptz);''')
    monkeypatch.setenv('PRODUCT_UPLOAD_AUTOMATIC_ENABLED','true')
    monkeypatch.setenv('AUTO_EDITIONS_TECHNICAL_FLOW_ENABLED','false')
    monkeypatch.setenv('AUTO_EDITIONS_V17_CONTINUOUS_ENABLED','false')
    monkeypatch.setenv('AUTO_EDITIONS_V15_ENABLED','false')
    import supabase_backend as db
    monkeypatch.setattr(db,'connect',jobs.connect)
    monkeypatch.setattr(db,'_mirror_pending_registered_product',lambda *a,**k:False)
    return Intakes(jobs.connect),sql,DiskDropbox(tmp_path/'dropbox')


def saved(env,selected='DRAFT',data=None):
    store,sql,provider=env;data=psd() if data is None else data;key=str(uuid.uuid4())
    store.create(key,ADMIN['id'],selected,'Design.psd',len(data),provider,digest(data))
    for offset in range(0,len(data),CHUNK):store.chunk(key,ADMIN['id'],offset,data[offset:offset+CHUNK],provider)
    row=store.finish(key,ADMIN['id'],provider);store.copied(key,ADMIN['id'],selected)
    return store.read(key,ADMIN['id'])


def product(**changes):
    return {**dict(shopify_product_id=PID,legacy_resource_id='987',title='New Art',handle='new-art',status='DRAFT',
       vendor='Sports Cave',product_type='Framed Art',metafields=[],tags=[],online_store_url='',
       admin_url='https://store.myshopify.com/admin/products/987',_edition_registration_canonical=True),**changes}


def service(env,p=None):
    store,sql,provider=env;p=p or product();shop=Mock();shop.fetch_product_by_shopify_id.return_value=p
    return Handoff(store.connect,provider,lookup=lambda value:[p],shopify=shop)


@pytest.mark.parametrize('selected',['DRAFT','LIVE','UPDATE'])
def test_real_registration_mapping_queue_and_repeat(env,selected):
    row=saved(env,selected);store,sql,provider=env;p=product();p['status']='ACTIVE' if selected=='LIVE' else 'DRAFT';p['online_store_url']='https://store.myshopify.com/products/new-art'
    handoff=service(env,p)
    result=handoff.resolve(str(row['id']),ADMIN,'New Art')
    assert result['data']['state']=='Waiting for Companion'
    handoff.resolve(str(row['id']),ADMIN,'New Art')
    handoff.link(str(row['id']),ADMIN,PID)
    for table in ('edition_products','edition_runs','shopify_products','product_psd_mappings','auto_edition_onboarding'):
        sql.execute('SELECT count(*) AS n FROM '+table);assert sql.fetchone()['n']==1,table
    sql.execute('SELECT next_edition_number,raw FROM edition_products');assert sql.fetchone()['next_edition_number']==1
    sql.execute('SELECT count(*) AS n FROM edition_orders');assert sql.fetchone()['n']==0


def test_interrupted_append_finish_restart_and_duplicate_bytes(env):
    store,sql,provider=env;data=psd(CHUNK+73);key=str(uuid.uuid4());h=digest(data)
    store.create(key,'admin','DRAFT','Design.psd',len(data),provider,h)
    provider.lose_append=True
    with pytest.raises(RuntimeError):store.chunk(key,'admin',0,data[:CHUNK],provider)
    store=Intakes(store.connect)
    assert store.create(key,'admin','DRAFT','Design.psd',len(data),provider,h)['data']['offset']==0
    store.chunk(key,'admin',0,data[:CHUNK],provider)
    store.chunk(key,'admin',0,data[:CHUNK],provider)
    with pytest.raises(ValueError,match='differ'):store.chunk(key,'admin',0,b'x'*CHUNK,provider)
    with pytest.raises(ValueError,match='incomplete'):store.finish(key,'admin',provider)
    store.chunk(key,'admin',CHUNK,data[CHUNK:],provider);provider.lose_finish=True
    with pytest.raises(RuntimeError):store.finish(key,'admin',provider)
    row=Intakes(store.connect).finish(key,'admin',provider)
    assert row['data']['basic_validated'] and len(provider.files)==2
    assert sum(kind=='finish' for kind,_ in provider.calls)==1
    assert max(n for kind,n in provider.calls if kind=='append')==CHUNK


@pytest.mark.parametrize('data',[b'x'*128,psd(depth=16),psd(colour=4),psd()[:32],psd()[:34]+b'\xff'*4+psd()[38:]])
def test_invalid_structures_do_not_enter_mapping(env,data):
    with pytest.raises(ValueError):saved(env,data=data)
    env[1].execute('SELECT count(*) AS n FROM product_psd_mappings');assert env[1].fetchone()['n']==0


def test_boundaries_authorization_mode_and_replacement(env):
    store,sql,provider=env
    for size in (0,39,MAX_BYTES+1):
        with pytest.raises(ValueError,match='size'):store.create(str(uuid.uuid4()),'admin','DRAFT','a.psd',size,provider,'a'*64)
    key=str(uuid.uuid4());assert store.create(key,'admin','DRAFT','large.psd',MAX_BYTES,provider,'a'*64)
    row=saved(env);key=str(row['id']);assert row['data']['copied']
    assert not store.change_mode(key,'admin','UPDATE')['data']['copied']
    assert store.read(key,'other-user') is None
    with pytest.raises(ValueError):store.copied(key,'other-user','UPDATE')
    second=saved(env);assert second['id']!=row['id'] and 'preparation_hash' not in second['data']
    assert 'session' not in public(second) and 'source' not in public(second)


def test_mapping_conflict_retains_passed_design(env):
    first=saved(env);service(env).resolve(str(first['id']),ADMIN,'New Art')
    sql=env[1];sql.execute("UPDATE edition_products SET next_edition_number=37")
    second=saved(env)
    with pytest.raises(ValueError,match='Reset'):service(env).resolve(str(second['id']),ADMIN,'New Art')
    sql.execute('SELECT next_edition_number FROM edition_products');assert sql.fetchone()['next_edition_number']==37
    sql.execute('SELECT dropbox_file_id FROM product_psd_mappings');assert sql.fetchone()['dropbox_file_id']==first['data']['source']['id']


def test_not_found_keeps_lookup_and_source(env):
    row=saved(env);s=service(env);s.lookup=lambda value:[]
    result=s.resolve(str(row['id']),ADMIN,'Not synced yet')
    assert result['data']['lookup']=='Not synced yet' and result['data']['source']
    assert 'not found' in result['data']['reason']


def test_handoff_failure_can_finish_missing_step(env):
    row=saved(env);s=service(env);original=s.queue.enqueue
    s.queue.enqueue=Mock(side_effect=RuntimeError('lost acknowledgement'))
    with pytest.raises(RuntimeError):s.resolve(str(row['id']),ADMIN,'New Art')
    s.queue.enqueue=original
    s.resolve(str(row['id']),ADMIN,'New Art')
    env[1].execute('SELECT count(*) AS n FROM product_psd_mappings');assert env[1].fetchone()['n']==1


@pytest.mark.parametrize('value',['new  ART','https://store.myshopify.com/admin/products/987','https://admin.shopify.com/store/store/products/987','https://store.myshopify.com/products/new-art'])
def test_exact_lookup_drafts_urls_and_duplicates(value):
    shop=Mock();shop.get_config.return_value={'store_domain':'store.myshopify.com'}
    shop.fetch_product_by_shopify_id.return_value=product()
    shop.fetch_catalog_page.return_value=dict(products=[product(),{**product(),'shopify_product_id':'gid://shopify/Product/988'},product(title='New Art Other',handle='other-art')],has_next_page=False)
    results=resolve_products(value,shop)
    assert results and all(p['title']=='New Art' for p in results)
    if not value.startswith('https:'):assert len(results)==2


def test_lookup_rejects_foreign_url_and_escapes_search():
    shop=Mock();shop.get_config.return_value={'store_domain':'store.myshopify.com'}
    with pytest.raises(ValueError,match='connected'):resolve_products('https://attacker.example/products/x',shop)
    shop.fetch_catalog_page.return_value=dict(products=[],has_next_page=False)
    resolve_products('A title " OR status:active',shop)
    assert shop.fetch_catalog_page.call_args.kwargs['search']=='title:"A title \\" OR status:active"'


def test_http_auth_chunk_and_disabled_manual_route(env,monkeypatch):
    import product_upload_api as api
    import files_upload_api as files
    monkeypatch.setattr(api,'connect',env[0].connect);monkeypatch.setattr(api,'Dropbox',lambda:env[2])
    monkeypatch.setattr(files,'_request_user',lambda request,**kwargs:ADMIN)
    app=Starlette(routes=[Route(p,e,methods=list(m)) for p,e,m in api.ROUTES])
    with TestClient(app) as client:
        assert client.get('/product-uploads').status_code==200
        assert client.post('/api/product-uploads/start',json={}).status_code==403
        key=str(uuid.uuid4());data=psd();headers={'Origin':'http://testserver'}
        response=client.post('/api/product-uploads/start',json=dict(id=key,mode='DRAFT',name='Design.psd',size=len(data),content_hash=digest(data)),headers=headers)
        assert response.status_code==200,response.text
        assert client.post('/api/product-uploads/chunk?id='+key+'&offset=0',content=data,headers=headers).status_code==200
        assert client.post('/api/product-uploads/finish',json=dict(id=key),headers=headers).json()['upload']['basic_validated']
        assert client.get('/api/product-uploads/state?id='+key).json()['upload']['copied'] is False
        monkeypatch.setenv('PRODUCT_UPLOAD_AUTOMATIC_ENABLED','false')
        assert client.get('/product-uploads').status_code==200
        assert client.get('/api/product-uploads/state').json()['enabled'] is False
        assert client.post('/api/product-uploads/start',json={},headers=headers).status_code==409


def test_expired_session_and_backend_content_mismatch_do_not_accept_upload(env):
    store,sql,provider=env;data=psd();key=str(uuid.uuid4())
    store.create(key,'admin','DRAFT','a.psd',len(data),provider,digest(data))
    with store.locked(key,'admin') as (row,cur):row['data']['expires']='2000-01-01T00:00:00+00:00'
    with pytest.raises(ValueError,match='expired'):store.chunk(key,'admin',0,data,provider)
    assert not provider.calls
    key=str(uuid.uuid4());store.create(key,'admin','DRAFT','a.psd',len(data),provider,digest(data));store.chunk(key,'admin',0,data,provider)
    original=provider.metadata_if_present
    def wrong(key):
        result=original(key)
        if result:result['content_hash']='0'*64
        return result
    provider.metadata_if_present=wrong
    with pytest.raises(ValueError,match='verification failed'):store.finish(key,'admin',provider)
    assert not store.read(key,'admin')['data'].get('basic_validated')


def test_duplicate_titles_require_choice_and_colon_long_title_is_lookup_data(env):
    title='Art: '+('A long exact product title '*5)
    first=product(title=title);second=product(title=title,shopify_product_id='gid://shopify/Product/988',handle='other-art')
    shop=Mock();shop.get_config.return_value=dict(store_domain='store.myshopify.com')
    shop.fetch_catalog_page.return_value=dict(products=[first,second],has_next_page=False)
    assert len(resolve_products(title,shop))==2
    row=saved(env);handoff=service(env,first);handoff.lookup=lambda value:[first,second]
    result=handoff.resolve(str(row['id']),ADMIN,title)
    assert len(result['data']['choices'])==2 and not result['data'].get('product_gid')
    with pytest.raises(ValueError,match='Choose a product'):handoff.link(str(row['id']),ADMIN,'gid://shopify/Product/999')
    handoff.link(str(row['id']),ADMIN,PID)
    env[1].execute('SELECT product_title FROM edition_products');assert env[1].fetchone()['product_title']==title


def test_normal_sync_already_discovered_product_and_concurrent_clicks(env):
    from concurrent.futures import ThreadPoolExecutor
    p=product();register_product(p)  # Existing canonical sync wins the first race.
    row=saved(env);handoff=service(env,p)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(handoff.resolve,str(row['id']),ADMIN,'New Art') for _ in range(2)]
        for f in futures:assert f.result()['data']['product_gid']==PID
    for table in ('edition_products','edition_runs','product_psd_mappings','auto_edition_onboarding'):
        env[1].execute('SELECT count(*) AS n FROM '+table);assert env[1].fetchone()['n']==1


def test_prompt_only_account_keeps_access_and_expired_session_is_rejected(monkeypatch):
    import product_upload_api as api,files_upload_api as files,sc_auth,prompt_store
    user=dict(id='prompt-user',role='worker',is_active=True,session_version=1,page_permissions=['product_uploads'])
    monkeypatch.setenv('PRODUCT_UPLOAD_AUTOMATIC_ENABLED','true')
    monkeypatch.setenv('SPORTS_CAVE_AUTH_SECRET','synthetic-secret')
    monkeypatch.setattr(sc_auth,'DEFAULT_APP_PASSWORD','synthetic-password')
    monkeypatch.setattr(files.os_accounts.DEFAULT_STORE,'get_user',lambda key:user)
    monkeypatch.setattr(prompt_store,'get_prompt',lambda key,default,**kw:default)
    token=sc_auth.create_user_auth_token(user['id'],password='synthetic-password',extra_secret='synthetic-secret')
    client=TestClient(Starlette(routes=[Route(p,e,methods=list(m)) for p,e,m in api.ROUTES]))
    client.cookies.set(sc_auth.AUTH_COOKIE_NAME,token)
    assert client.get('/product-uploads').status_code==200
    assert client.get('/api/product-uploads/state').json()==dict(enabled=False,upload=None)
    headers={'Origin':'http://testserver'}
    assert client.post('/api/product-uploads/prompt',json={'mode':'DRAFT'},headers=headers).status_code==200
    assert client.post('/api/product-uploads/start',json={},headers=headers).status_code==403
    assert client.post('/api/product-uploads/mockups',json={},headers=headers).status_code==403
    user['session_version']=2
    assert client.get('/product-uploads').status_code==403
