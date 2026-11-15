"""Exact review composition, optional import cache and isolated build leases."""
import ast
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch,Mock

import pytest
import auto_editions as ae
import auto_editions_bulk as bulk
from auto_editions_bulk_jobs import PreviewStore
from auto_editions_review_thumbnails import ReviewBuildStore,backfill,schedule_prepared
from tests.test_auto_editions_bulk import prepared,review,store,database,pglite_database,rebind
from tests.test_auto_editions_api import ADMIN
from tests.test_auto_editions_reset import design


def test_same_exact_review_bytes_and_source_unchanged(tmp_path):
    record,assets=prepared(tmp_path)
    tree=ast.parse(subprocess.check_output(['git','show','HEAD:auto_editions_bulk.py']).decode('utf-8'))
    old=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='ReviewCache')
    ns=dict(bulk.__dict__);exec(compile(ast.Module(body=[old],type_ignores=[]),'existing-renderer','exec'),ns)
    expected=ns['ReviewCache']().get(record,assets.fetch)
    hashes={p.name:ae.file_hash(p) for p in tmp_path.glob('*.png')}
    cache=bulk.ReviewCache();metrics={}
    assert cache.get(record,None,local_root=tmp_path,metrics=metrics)==expected
    assert metrics['cache']=='local-assets' and metrics['provider_bytes']==0
    assert hashes=={p.name:ae.file_hash(p) for p in tmp_path.glob('*.png')}
    assert bulk.ReviewCache.valid(cache.get(record,None,1200),1200)


def test_import_retains_local_files_and_persists_exact_receipt_key(review):
    db,sql,record,assets=review;cache=bulk.ReviewCache();builds=bulk.PreviewBuilds();store=ReviewBuildStore(db.connect)
    # The fixture keeps the generated files beside its copy callback.
    import inspect
    root=inspect.getclosurevars(assets.fetch.side_effect).nonlocals['root']
    with patch.object(bulk,'thumbnails',cache),patch.object(bulk,'preview_builds',builds),patch.object(bulk.runtime,'storage',side_effect=AssertionError('No provider transfer')):
        assert schedule_prepared(record,root,store)
        future=next(iter(builds.pending.values()))[0];future.result(timeout=5)
        key=ae.fingerprint(cache.key(record));data=store.get(key)
        assert data and data==bulk.ReviewCache().get(record,None,store=store)
    builds.pool.shutdown(wait=True)


def test_two_independent_processes_only_transfer_one_master_and_patch(review,tmp_path):
    db,sql,record,assets=review
    if not hasattr(db.connect,'test_url'):pytest.skip('Disposable loopback PGlite process test.')
    import inspect,os
    root=inspect.getclosurevars(assets.fetch.side_effect).nonlocals['root']
    export=tmp_path/'record.json';export.write_text(json.dumps(record));start=tmp_path/'start';transfers=tmp_path/'transfers.txt'
    command=[sys.executable,'tests/review_thumbnail_process.py',db.connect.test_url,str(export),str(root),str(start),str(transfers)]
    children=[subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0) for _ in range(2)]
    try:
        for child in children:assert child.stdout.readline().strip()=='ready'
        start.touch()
        for child in children:
            out,err=child.communicate(timeout=20);assert child.returncode==0,out+err
        assert sorted(transfers.read_text().splitlines())==['master.png','number-1.png']
        data=ReviewBuildStore(db.connect).get(ae.fingerprint(bulk.thumbnails.key(record)))
        assert bulk.ReviewCache.valid(data,300)
    finally:
        for child in children:
            if child.poll() is None:child.terminate();child.communicate(timeout=5)


def test_expired_build_owner_cannot_publish_or_release_new_owner(review):
    db,sql,record,assets=review;store=ReviewBuildStore(db.connect);identity=bulk.thumbnails.key(record)[0]
    first=store.claim(identity);assert first and store.claim(identity) is None
    sql.execute("UPDATE auto_edition_review_preview_builds SET lease_until=now()-interval '1 second'")
    second=store.claim(identity);assert second!=first and not store.renew(identity,first)
    data=bulk.ReviewCache().get(record,assets.fetch)
    assert not store.publish(identity,first,{ae.fingerprint((identity,300)):data})
    store.release(identity,first);assert store.renew(identity,second)
    assert store.publish(identity,second,{ae.fingerprint((identity,300)):data})


def test_backfill_bounded_resumable_missing_local_files_never_downloads(review,tmp_path):
    import inspect
    db,sql,record,assets=review;root=inspect.getclosurevars(assets.fetch.side_effect).nonlocals['root'];store=ReviewBuildStore(db.connect)
    other=deepcopy(record);other['receipts']['assets'][0]['revision']='local-second-receipt'
    items=[dict(record=record,root=str(root)),dict(record=other,root=str(tmp_path/'missing'))]
    state=tmp_path/'progress.json'
    with patch.object(bulk.runtime,'storage',side_effect=AssertionError('No backfill provider fallback')):
        result=backfill(items,store,state,limit=1);assert len(result['results'])==1 and result['pending']
        assert json.loads(state.read_text())['cursor']==1
        assert backfill(items,store,state,limit=1)['results'][0]['result']=='Pending'
        items[1]['root']=str(root)
        backfill(items,store,state,limit=2)
        assert not backfill(items,store,state,limit=2)['pending']
    # A missing/corrupt derived JPEG must become repairable even after checkpoint.
    key=ae.fingerprint(bulk.thumbnails.key(record));store.put(key,b'corrupt')
    backfill(items,store,state,limit=2);assert bulk.ReviewCache.valid(store.get(key),300)


def test_hash_or_receipt_change_cannot_reuse_thumbnail(review):
    db,sql,record,assets=review;cache=bulk.ReviewCache();store=ReviewBuildStore(db.connect)
    original=cache.get(record,assets.fetch,store=store)
    other=deepcopy(record);other['receipts']['assets'][0]['revision']='new-receipt'
    assert cache.key(other)!=cache.key(record)
    assert store.get(ae.fingerprint(cache.key(other))) is None
    other=deepcopy(record);other['manifest']['original_text']='2 / 2';rebind(other)
    assert cache.key(other)!=cache.key(record)
    assert original


def test_reset_invalidates_unexpired_actor_metadata_without_deleting_audit_cache(review):
    db,sql,record,assets=review;pid=record['manifest']['source']['product_gid']
    store=PreviewStore(db.connect);data=bulk.ReviewCache().get(record,assets.fetch,store=store)
    bulk.snapshots[(str(ADMIN['id']),pid,record['hash'])]=(time.monotonic()+900,record)
    assert bulk.preview_entries(ADMIN,[dict(product_gid=pid,hash=record['hash'])],db.connect)[0]
    sql.execute('DELETE FROM product_psd_mappings WHERE shopify_product_gid=%s',(pid,))
    sql.execute('UPDATE auto_edition_onboarding SET preparation_hash=NULL WHERE product_gid=%s',(pid,))
    entries,failed=bulk.preview_entries(ADMIN,[dict(product_gid=pid,hash=record['hash'])],db.connect)
    assert not entries and failed[0]['state']=='Unavailable'
    assert store.get(ae.fingerprint(bulk.thumbnails.key(record)))==data


def test_prefetch_miss_never_starts_cold_builder(review):
    db,sql,record,assets=review
    with patch.object(bulk,'thumbnails',bulk.ReviewCache()),patch.object(bulk.preview_builds,'read',side_effect=AssertionError('No speculative cold build')):
        rows=bulk.cached_previews([(record['manifest']['source']['product_gid'],record['hash'],record)],PreviewStore(db.connect),True,True)
    assert not rows[0]['jpeg']


def test_background_does_not_wait_on_paid_render_budget(review):
    import inspect,threading
    db,sql,record,assets=review;root=inspect.getclosurevars(assets.fetch.side_effect).nonlocals['root']
    builds=bulk.PreviewBuilds();ae._RENDER_LOCK.acquire()
    try:
        with patch.object(bulk,'preview_builds',builds):
            assert schedule_prepared(record,root,ReviewBuildStore(db.connect))
            assert next(iter(builds.pending.values()))[0].result(timeout=1) is None
    finally:ae._RENDER_LOCK.release();builds.pool.shutdown(wait=True)


def test_optional_thumbnail_failure_does_not_fail_valid_preparation(design,tmp_path):
    from tests.test_auto_editions_reset import test_existing_import_upload_and_checkpoint_path_is_reused
    with patch('auto_editions_review_thumbnails.schedule_prepared',side_effect=RuntimeError('disposable thumbnail failure')) as thumbnail:
        test_existing_import_upload_and_checkpoint_path_is_reused(design,tmp_path,'success')
    thumbnail.assert_called_once()


def test_build_lease_table_is_private(review):
    db,sql,_,_=review
    for role in ('anon','authenticated'):
        sql.execute("SELECT has_table_privilege(%s,'auto_edition_review_preview_builds','SELECT') AS allowed",(role,))
        assert not sql.fetchone()['allowed']


@pytest.mark.parametrize('broken',['missing_icc','wrong_size','changed_bytes'])
def test_local_pregeneration_preserves_asset_validation(tmp_path,broken):
    from PIL import Image
    record,_=prepared(tmp_path)
    if broken=='changed_bytes':(tmp_path/'master.png').write_bytes(b'changed')
    else:
        with Image.open(tmp_path/'master.png') as image:
            with image.resize((201,100) if broken=='wrong_size' else image.size) as updated:
                if broken=='missing_icc':updated.info.pop('icc_profile',None)
                updated.save(tmp_path/'new.png',**({} if broken=='missing_icc' else {'icc_profile':image.info['icc_profile']}))
        (tmp_path/'new.png').replace(tmp_path/'master.png')
        record['manifest']['master']['sha256']=ae.file_hash(tmp_path/'master.png')
        record['receipts']['assets'][0]['bytes']=(tmp_path/'master.png').stat().st_size;rebind(record)
    with pytest.raises(ValueError):bulk.ReviewCache().get(record,None,local_root=tmp_path)


def test_backfill_duplicate_inputs_and_changed_export_do_not_fake_completion(review,tmp_path):
    import inspect
    db,sql,record,assets=review;root=inspect.getclosurevars(assets.fetch.side_effect).nonlocals['root'];store=ReviewBuildStore(db.connect)
    state=tmp_path/'cursor.json';item=dict(record=record,root=str(root))
    assert not backfill([item,item],store,state,limit=1)['pending']
    other=deepcopy(record);other['receipts']['assets'][0]['revision']='different-receipt'
    assert backfill([dict(record=other,root=str(tmp_path/'absent'))],store,state,limit=1)['pending']


def test_foreground_and_backfill_share_decoder_budget(tmp_path):
    record,_=prepared(tmp_path);first=bulk.ReviewCache();second=bulk.ReviewCache()
    assert first.decoders is second.decoders
    first.decoders.acquire();first.decoders.acquire()
    try:assert second.get(record,None,local_root=tmp_path,background=True) is None
    finally:first.decoders.release();first.decoders.release()
