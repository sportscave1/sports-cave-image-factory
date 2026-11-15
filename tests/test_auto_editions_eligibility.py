import json
from copy import deepcopy
from unittest.mock import patch
import pytest
import auto_editions as ae
from auto_editions_store import Preparations
from tests.test_auto_editions_jobs import database,eligibility_tables
from test_auto_editions import package


def ready(database,tmp_path):
    jobs,sql=database
    manifest=package(tmp_path);digest=ae.fingerprint(manifest)
    eligibility_tables(sql,manifest)
    registry=Preparations(jobs.connect)
    registry.save(manifest,[dict(preparation_hash=digest,pixel_exact=True,outside_number_exact=True)],{},'admin')
    unit=dict(id=42,shopify_product_gid=manifest['source']['product_gid'],shopify_variant_id='gid://shopify/ProductVariant/456')
    registry.approve(digest,unit,'admin',allocation_ids=[42])
    sql.execute("INSERT INTO auto_edition_onboarding VALUES(%s,'Cloud Ready',%s::jsonb,%s)",(unit['shopify_product_gid'],json.dumps(manifest['source']),digest))
    return registry,sql,unit,manifest


def test_cloud_ready_product_inherits_existing_and_future_units_without_mutation(database,tmp_path):
    registry,sql,unit,manifest=ready(database,tmp_path)
    for allocation,variant in ((42,'456'),(43,'gid://shopify/ProductVariant/456'),(999,'new-variant')):
        assert registry.for_unit(dict(unit,id=allocation,shopify_variant_id=variant))['manifest']==manifest
    assert registry.index()[(unit['shopify_product_gid'],'*')] is None
    sql.execute('SELECT approval FROM auto_edition_layouts')
    assert sql.fetchone()['approval']['allocation_ids']==[42] # history retained
    sql.execute('SELECT count(*) n FROM auto_edition_layouts');assert sql.fetchone()['n']==1
    with pytest.raises(ValueError):registry.for_unit(dict(unit,shopify_product_gid='other-product'))


@pytest.mark.parametrize('change',['mapping','source','master','unapproved','not_ready'])
def test_stale_or_unverified_product_never_gains_shared_layout(database,tmp_path,change):
    registry,sql,unit,manifest=ready(database,tmp_path)
    if change=='mapping':sql.execute("UPDATE product_psd_mappings SET dropbox_file_id='id:replacement'")
    if change=='source':
        source=dict(manifest['source'],revision='changed')
        sql.execute('UPDATE auto_edition_onboarding SET source=%s::jsonb',(json.dumps(source),))
    if change=='master':sql.execute("UPDATE auto_edition_onboarding SET preparation_hash=%s",('b'*64,))
    if change=='unapproved':sql.execute("UPDATE auto_edition_layouts SET approval=approval-'visual_approved'")
    if change=='not_ready':sql.execute("UPDATE auto_edition_onboarding SET status='Preparing'")
    with pytest.raises(ValueError):registry.for_unit(dict(unit,id=999,shopify_variant_id='new'))
    assert (unit['shopify_product_gid'],'*') not in registry.index()


def test_multiple_layouts_keep_exact_variant_approval_and_reject_unknown(database,tmp_path):
    registry,sql,unit,manifest=ready(database,tmp_path)
    other=deepcopy(manifest);other['number_region']=[1,1,2,2]
    # Different stored layout must prevent an inferred wildcard, even when invalid.
    sql.execute("INSERT INTO auto_edition_preparations(hash,manifest,proofs,receipts,created_by) VALUES(%s,%s::jsonb,'[]','{}','admin')",('b'*64,json.dumps(other)))
    sql.execute("INSERT INTO auto_edition_layouts(product_gid,variant_id,preparation_hash,approval) VALUES(%s,'different',%s,'{}')",(unit['shopify_product_gid'],'b'*64))
    assert registry.for_unit(unit)['manifest']==manifest
    assert registry.for_unit(dict(unit,id=43))['manifest']==manifest
    with pytest.raises(ValueError):registry.for_unit(dict(unit,id=43,shopify_variant_id='unknown'))


def test_listing_and_generation_share_policy_and_archive_master_fence(database,tmp_path):
    import auto_editions_runtime as runtime
    from unittest.mock import Mock
    registry,sql,unit,manifest=ready(database,tmp_path)
    jobs=Mock();jobs.summaries.return_value={'43':dict(id='a'*64,status='Ready',preparation_hash=ae.fingerprint(manifest))}
    rows=[dict(edition_order_id=43,shopify_product_gid=unit['shopify_product_gid'],shopify_variant_id='new'),
          dict(edition_order_id=44,shopify_product_gid='gid://shopify/Product/999',shopify_variant_id='new')]
    with patch.object(runtime,'enabled',return_value=True),patch.object(runtime,'stores',return_value=(registry,jobs)):
        assert runtime.download_links(rows)=={'43':'/auto-editions/open?allocation_id=43&job_id='+'a'*64+'#Open'}
        jobs.summaries.return_value['43']['preparation_hash']='b'*64
        assert runtime.download_links(rows)['43'].endswith('#Download JPG')
        sql.execute("UPDATE product_psd_mappings SET dropbox_file_id='id:changed'")
        blocked=runtime.download_links(rows)['43']
        assert blocked.startswith('/auto-editions/status?') and 'job_id=' not in blocked
        with pytest.raises(ValueError):registry.for_unit(unit)
