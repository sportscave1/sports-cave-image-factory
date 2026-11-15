"""Conclusive synthetic production fixtures only; no live credentials or files."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image, ImageCms
import pytest

import auto_editions as ae
import auto_editions_quality as quality
from auto_editions_cloud import DropboxAssets,confirmed_job,execute
from auto_editions_quality_store import Quality
from tests.test_auto_editions_discovery import database,store,pglite_database,register,tick,asset,PID


@pytest.fixture
def case(tmp_path):
    profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    m=dict(schema_version=1,strategy='photoshop_number_patches',
           source=dict(product_gid=PID,file_id='id:original',revision='a1',content_hash='a'*64),
           dimensions=[100,100],source_dimensions=[100,100],edition_total=3,
           number_region=[40,80,60,90],plaque_bounds=[30,70,70,95],source_modified=False,
           original_text='3 / 3',
           number_layer_name='number',plaque_layer_name='plaque',source_inspection={'layers':[
               dict(path=[{'name':'number'}],visible=True,editable=True,fonts=[{'installed':True}]),
               dict(path=[{'name':'plaque'}],visible=True)]})
    def create(name,size,colour):
        with Image.new('RGB',size,colour) as image:image.save(tmp_path/name,icc_profile=profile)
        return dict(name=name,sha256=ae.file_hash(tmp_path/name))
    m['master']=create('master.png',(100,100),'white')
    m['patches']={str(n):create(f'number-{n}.png',(20,10),(n*40,0,0)) for n in range(1,4)}
    digest=ae.fingerprint(m)
    receipts=[];metadata={}
    for a in [m['master'],*m['patches'].values()]:
        path=tmp_path/a['name'];fid='id:'+path.stem
        receipts.append(dict(name=a['name'],file_id=fid,revision='b1',bytes=path.stat().st_size))
        metadata[fid]=dict(id=fid,rev='b1',size=path.stat().st_size,content_hash=ae.file_hash(path,dropbox=True),
                           path_display=DropboxAssets.path(digest,a['name']))
    proofs=[dict(number=n,preparation_hash=digest,pixel_exact=True) for n in (1,3)]
    proofs.append(dict(preparation_hash=digest,outside_number_exact=True))
    record=dict(hash=digest,manifest=m,proofs=proofs,receipts=dict(preparation_hash=digest,assets=receipts))
    checkpoint=dict(product_gid=PID,file_id='id:original',preparation_hash=digest,source=m['source'],
                    edition_total=3,status='Blocked')
    standard=dict(id='synthetic-supplier-artwork-v1',actor_id='synthetic-owner',approved_at='2026-01-01T00:00:00Z',
                  human_visual_approved=True,supplier_requirements_verified=True,supplier_evidence='synthetic supplier fixture',
                  supplier_sku='SYNTHETIC-ONLY',variant_ids=['456'],preparation_hash=digest,source=m['source'],output=dict(
                      dimensions=[100,100],format='JPEG',mode='RGB',dpi=[300,300],quality=100,subsampling=0,
                      printable_mm=[8,8],bleed_mm=[0,0,0,0],safe_margins_mm=[0,0,0,0],
                      minimum_source_ppi=300,icc_sha256=hashlib.sha256(profile).hexdigest(),
                      geometry_includes_bleed=True,safe_area_visually_approved=True))
    c=SimpleNamespace(record=record,checkpoint=checkpoint,standard=standard,metadata=metadata,
                      source=asset(),mapping=dict(shopify_product_gid=PID,dropbox_file_id='id:original'),root=tmp_path)
    c.fetch=lambda digest,a,destination:shutil.copyfile(tmp_path/a['name'],destination)
    c.read=lambda fid:metadata.get(fid)
    c.assess=lambda records=None:quality.assess(record,c.mapping,checkpoint,c.source,c.read,c.fetch,
                                                [standard] if records is None else records)
    return c


def test_conclusive_auto_approval_and_rollback(case,monkeypatch):
    check=case.assess()
    assert check['status']=='Production Ready' and check['evidence']['receipts_verified']==4
    assert check['evidence']['fulfilment_authorized'] is False
    assert not quality.current_certificate(check,case.record['manifest'],[case.standard])
    monkeypatch.setenv('AUTO_EDITIONS_V16_AUTO_APPROVAL_ENABLED','true')
    assert quality.current_certificate(check,case.record['manifest'],[case.standard])
    assert not quality.current_certificate(check,case.record['manifest'],[{**case.standard,'revoked':True}])


@pytest.mark.parametrize('change',[
    'new_art','changed_source','changed_plaque','wrong_number','ambiguous','missing_standard',
    'incomplete_supplier','missing_bleed','wrong_receipt','missing_file','missing_bytes',
    'missing_proof','unbound_proof','fonts','profile','resolution','dimensions','filename',
    'conflicting','outside_source','stale','outside_plaque','missing_aesthetics'])
def test_inconclusive_or_altered_assets_are_never_certified(case,change):
    m=case.record['manifest'];s=case.standard
    if change=='new_art':m['source']={**m['source'],'product_gid':'gid://shopify/Product/999'}
    if change=='changed_source':case.source['rev']='a2'
    if change=='changed_plaque':m['plaque_bounds']=[0,0,5,5]
    if change=='wrong_number':m['patches']['2']['sha256']='f'*64
    if change=='ambiguous':case.checkpoint['conflicting_approval']=True
    if change=='missing_standard':s['preparation_hash']='f'*64
    if change=='incomplete_supplier':s['supplier_requirements_verified']=False
    if change=='missing_bleed':s['output']['bleed_mm']=None
    if change=='wrong_receipt':case.metadata['id:master']['rev']='b2'
    if change=='missing_file':case.record['receipts']['assets'].pop()
    if change=='missing_bytes':case.record['receipts']['assets'][0].pop('bytes')
    if change=='missing_proof':case.record['proofs'].pop()
    if change=='unbound_proof':case.record['proofs'][0]['preparation_hash']='f'*64
    if change=='fonts':m['source_inspection']['layers'][0]['fonts'][0]['installed']=False
    if change=='profile':s['output']['icc_sha256']='f'*64
    if change=='resolution':s['output']['printable_mm']=[100,100]
    if change=='dimensions':s['output']['dimensions']=[200,200]
    if change=='filename':m['master']['name']='unrelated.png'
    if change=='conflicting':case.checkpoint['conflicting_approval']=True
    if change=='outside_source':case.source['path_display']='/Prepared/Masters/fake.psd'
    if change=='stale':case.checkpoint['preparation_hash']='f'*64
    if change=='outside_plaque':m['number_region']=[40,10,60,20]
    if change=='missing_aesthetics':s['human_visual_approved']=False
    assert case.assess()['status']!='Production Ready'


def test_does_not_read_assets_without_a_standard(case):
    case.fetch=lambda *a:pytest.fail('No asset work for unapproved historical artwork')
    assert case.assess(records=[])['status']=='Needs Review'


def test_full_encoded_output_gate_and_immutable_archive(case,monkeypatch):
    monkeypatch.setenv('AUTO_EDITIONS_V16_AUTO_APPROVAL_ENABLED','true')
    check=case.assess()
    unit=dict(id=42,shopify_product_gid=PID,shopify_variant_id='456',edition_number=2,edition_total=3,
              allocation_valid=True,identity_enforced=True,status='assigned',allocation_index=1,
              shopify_order_id='synthetic-order',shopify_line_item_id='synthetic-line')
    prep=dict(manifest=case.record['manifest'],approval=dict(actor_id='policy',preparation_hash=case.record['hash'],
              visual_approved=True,pixel_exact=True),variant_ids=['456'],production=check)
    with patch.object(quality,'standards',return_value=[case.standard]):
        job=confirmed_job(unit,{**case.mapping,'verified':True,'state':'Linked'},case.source,prep)
        class Assets:
            fetch=staticmethod(case.fetch)
            def publish_output(self,j,path):return dict(sha256=ae.file_hash(path),path=DropboxAssets.output_path(j))
        output=execute(job,Assets())
    assert output['print_ready'] is True and output['test_only'] is False
    assert '/Production/' in output['output']['path'] and 'TEST' not in output['filename']
    legacy=deepcopy(job);legacy.pop('production');legacy['identity'].pop('production_policy')
    assert '/TEST/' in DropboxAssets.output_path(legacy)


def install(case,store):
    d,sql=store;register(store);tick(store,[asset()])
    sql.execute("UPDATE edition_products SET edition_total=3")
    r=case.record
    sql.execute('INSERT INTO auto_edition_preparations(hash,manifest,proofs,receipts,created_by) VALUES(%s,%s::jsonb,%s::jsonb,%s::jsonb,%s)',
                (r['hash'],json.dumps(r['manifest']),json.dumps(r['proofs']),json.dumps(r['receipts']),'synthetic-owner'))
    sql.execute("UPDATE auto_edition_onboarding SET status='Blocked',source=%s::jsonb,edition_total=3,preparation_hash=%s",
                (json.dumps(case.record['manifest']['source']),case.record['hash']))
    sql.execute((Path(__file__).parents[1]/'supabase/migrations/20261015022631_auto_editions_v16_quality.sql').read_text())
    return d,sql


def test_durable_reconciliation_restart_status_and_permissions(case,store,monkeypatch):
    from auto_editions_status import batch
    d,sql=install(case,store)
    sql.execute("""INSERT INTO auto_edition_onboarding(product_gid,file_id,priority)
        SELECT 'gid://shopify/Product/'||n,'id:deferred-'||n,0 FROM generate_series(1000,1166)n""")
    sql.execute("SELECT jsonb_agg(to_jsonb(q) ORDER BY product_gid) AS rows FROM auto_edition_onboarding q WHERE priority=0")
    deferred=sql.fetchone()['rows'];assert len(deferred)==167
    monkeypatch.setenv('AUTO_EDITIONS_V16_AUTO_APPROVAL_ENABLED','true')
    integration=SimpleNamespace(psd_open_metadata=lambda token,fid,**kw:case.source if fid=='id:original' else case.read(fid))
    assets=SimpleNamespace(integration=integration,token='synthetic',fetch=case.fetch)
    with patch.object(quality,'standards',return_value=[case.standard]):
        assert Quality(d.connect).run_one(assets)
        assert not Quality(d.connect).run_one(assets) # durable due state, even a new process
        sql.execute('SELECT assessment FROM auto_edition_quality_checks')
        saved=sql.fetchone()['assessment']
        assert batch(d.connect,[PID])['rows'][0]['status']=='Production Ready',saved
        unit=dict(shopify_product_gid=PID,shopify_variant_id='456')
        assert Quality(d.connect).for_unit(unit)['production']['status']=='Production Ready'
        assert Quality(d.connect).for_unit(dict(unit,shopify_variant_id='457')) is None
        assert Quality(d.connect).index()=={(PID,'456'):case.record['hash']}
        from auto_editions_store import Preparations
        assert Preparations(d.connect).index().hashes[(PID,'456')]==case.record['hash']
        sql.execute('SELECT count(*) n FROM auto_edition_quality_audit');assert sql.fetchone()['n']==1
        Quality(d.connect).recheck(PID,'synthetic-owner')
        assert Quality(d.connect).for_unit(unit) is None
        assert Quality(d.connect).run_one(assets)
        assert Quality(d.connect).for_unit(unit) is not None
        for table in ('auto_edition_quality_checks','auto_edition_quality_audit'):
            sql.execute("SELECT relrowsecurity AS rls FROM pg_class WHERE relname=%s",(table,));assert sql.fetchone()['rls']
            sql.execute("SELECT has_table_privilege('authenticated',%s,'SELECT') AS allowed",(table,));assert not sql.fetchone()['allowed']
            sql.execute("SELECT has_table_privilege('service_role',%s,'DELETE') AS allowed",(table,));assert not sql.fetchone()['allowed']
        sql.execute("SELECT has_table_privilege('service_role','auto_edition_quality_audit','UPDATE') AS allowed");assert not sql.fetchone()['allowed']
        sql.execute('SELECT number,owner FROM edition_allocations');assert sql.fetchone()==dict(number=36,owner='synthetic-owner')
        sql.execute('SELECT next_edition_number FROM edition_products');assert sql.fetchone()['next_edition_number']==37
        sql.execute("SELECT count(*) n FROM auto_edition_layouts");assert sql.fetchone()['n']==0
        sql.execute("SELECT jsonb_agg(to_jsonb(q) ORDER BY product_gid) AS rows FROM auto_edition_onboarding q WHERE priority=0")
        assert sql.fetchone()['rows']==deferred
        monkeypatch.delenv('AUTO_EDITIONS_V16_AUTO_APPROVAL_ENABLED')
        assert batch(d.connect,[PID])['rows'][0]['status']=='Review'
        assert Quality(d.connect).for_unit(unit) is None


@pytest.mark.parametrize('change',['source','approval','expired','limit','scope','policy'])
def test_existing_certificate_is_fenced_after_changes(case,store,monkeypatch,change):
    d,sql=install(case,store)
    monkeypatch.setenv('AUTO_EDITIONS_V16_AUTO_APPROVAL_ENABLED','true')
    integration=SimpleNamespace(psd_open_metadata=lambda token,fid,**kw:case.source if fid=='id:original' else case.read(fid))
    assets=SimpleNamespace(integration=integration,token='synthetic',fetch=case.fetch)
    with patch.object(quality,'standards',return_value=[case.standard]):
        Quality(d.connect).run_one(assets)
        if change=='source':sql.execute("UPDATE auto_edition_onboarding SET source=jsonb_set(source,'{revision}','\"a2\"')")
        if change=='expired':sql.execute("UPDATE auto_edition_quality_checks SET next_check_at=now()-interval '1 second'")
        if change=='limit':sql.execute('UPDATE edition_products SET edition_total=4')
        if change=='scope':case.standard['variant_ids']=['999']
        if change=='policy':case.standard['revoked']=True
        if change=='approval':
            r=case.record
            sql.execute("INSERT INTO auto_edition_preparations(hash,manifest,proofs,receipts,created_by) VALUES(%s,%s::jsonb,'[]','{}','owner')",('f'*64,json.dumps(r['manifest'])))
            sql.execute("INSERT INTO auto_edition_layouts(product_gid,variant_id,preparation_hash,approval) VALUES(%s,'999',%s,'{}')",(PID,'f'*64))
        assert Quality(d.connect).for_unit(dict(shopify_product_gid=PID,shopify_variant_id='456')) is None
        assert Quality(d.connect).index()=={}


def test_restart_after_verification_interruption(case,store,monkeypatch):
    d,sql=install(case,store)
    monkeypatch.setenv('AUTO_EDITIONS_V16_AUTO_APPROVAL_ENABLED','true')
    assets=SimpleNamespace(integration=SimpleNamespace(psd_open_metadata=lambda *a,**kw:case.source),token='synthetic',fetch=case.fetch)
    with patch.object(quality,'standards',return_value=[case.standard]),patch.object(quality,'assess',side_effect=KeyboardInterrupt):
        with pytest.raises(KeyboardInterrupt):Quality(d.connect).run_one(assets)
    sql.execute('SELECT count(*) n FROM auto_edition_quality_checks');assert sql.fetchone()['n']==0
    with patch.object(quality,'standards',return_value=[case.standard]),patch.object(quality,'assess',return_value=quality.result('Needs Review','Owner evidence required',case.record['manifest'])):
        assert Quality(d.connect).run_one(assets)


def test_334_product_quality_status_remains_one_local_batch(store,monkeypatch):
    import statistics,time,tracemalloc
    import auto_editions_status as status
    d,sql=store
    sql.execute((Path(__file__).parents[1]/'supabase/migrations/20261015022631_auto_editions_v16_quality.sql').read_text())
    sql.execute('DELETE FROM edition_products')
    sql.execute("""INSERT INTO edition_products SELECT 'gid://shopify/Product/'||n,n::text,
        'Synthetic Art '||n,'art-'||n,100,37,true,true FROM generate_series(1,334)n""")
    ids=['gid://shopify/Product/'+str(n) for n in range(1,335)]
    metrics={}
    for flag in ('false','true'):
        monkeypatch.setenv('AUTO_EDITIONS_V16_AUTO_APPROVAL_ENABLED',flag)
        times=[];tracemalloc.start()
        for _ in range(7):
            response=status.batch(d.connect,ids);times.append(response['duration_ms'])
            assert response['query_count']==1 and len(response['rows'])==334
        _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
        metrics['v16_on' if flag=='true' else 'v15_baseline']={
            'median_ms':round(statistics.median(times),2),'python_peak_bytes':peak,
            'queries_per_refresh':1,'response_bytes':len(json.dumps(response)),'dropbox_calls':0}
    path=Path(__file__).parents[1]/'output/v16/performance.json';path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(metrics,indent=2))


def test_certificate_payload_cannot_change_output_or_scope(case,monkeypatch):
    monkeypatch.setenv('AUTO_EDITIONS_V16_AUTO_APPROVAL_ENABLED','true')
    check=case.assess()
    assert quality.current_certificate(check,case.record['manifest'],[case.standard])
    for field,value in (('output',{}),('scope',['999']),('receipts_verified',1)):
        altered=deepcopy(check);altered['evidence'][field]=value
        assert not quality.current_certificate(altered,case.record['manifest'],[case.standard])


def test_missing_embedded_profile_fails_closed_even_with_reviewed_geometry(case):
    # Exact hashes and an explicit reviewed standard cannot replace actual ICC evidence.
    with Image.open(case.root/'master.png') as im:im.copy().save(case.root/'master.png',icc_profile=b'')
    m=case.record['manifest'];m['master']['sha256']=ae.file_hash(case.root/'master.png')
    digest=ae.fingerprint(m);case.record['hash']=digest;case.standard['preparation_hash']=digest
    case.checkpoint['preparation_hash']=digest;case.record['receipts']['preparation_hash']=digest
    for proof in case.record['proofs']:proof['preparation_hash']=digest
    for receipt in case.record['receipts']['assets']:
        path=case.root/receipt['name'];receipt['bytes']=path.stat().st_size
        case.metadata[receipt['file_id']].update(size=path.stat().st_size,content_hash=ae.file_hash(path,dropbox=True),
            path_display=DropboxAssets.path(digest,receipt['name']))
    assert case.assess()['status']!='Production Ready'
