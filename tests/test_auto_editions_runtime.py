from unittest.mock import Mock,patch
import auto_editions_runtime as runtime


def test_links_match_shopify_gid_and_numeric_representations_only_for_approved_variant():
    registry=Mock();registry.index.return_value={('gid://shopify/Product/123','gid://shopify/ProductVariant/456')}
    rows=[dict(edition_order_id=7,shopify_product_id=123,variant_id=456),
          dict(edition_order_id=8,shopify_product_id=123,variant_id=999)]
    with patch.object(runtime,'enabled',return_value=True),patch.object(runtime,'stores',return_value=(registry,None)):
        assert runtime.download_links(rows)=={'7':'/auto-editions/download?allocation_id=7#Download JPG'}


def test_changed_source_after_render_blocks_and_discards_unapproved_output():
    jobs=Mock();jobs.claim.return_value=dict(id='first',lease_token='lease',attempts=1,payload={'identity':{'allocation_id':7}})
    assets=Mock();resolver=Mock(side_effect=[({'id':'first','identity':{'allocation_id':7}},assets),({'id':'changed'},assets)])
    with patch.object(runtime,'execute',return_value={'output':{'file_id':'generated'}}):
        assert runtime.run_one(jobs,resolver)
    jobs.finish.assert_called_once_with('first','lease',error_code='source_changed')
    assets.discard_cache.assert_called_once_with('first',{'file_id':'generated'})


def test_scoped_rollout_links_only_verified_units():
    registry=Mock();registry.index.return_value={('gid://shopify/Product/123','gid://shopify/ProductVariant/456'):[7]}
    rows=[dict(edition_order_id=i,shopify_product_id=123,variant_id=456) for i in (7,8)]
    with patch.object(runtime,'enabled',return_value=True),patch.object(runtime,'stores',return_value=(registry,None)):
        assert set(runtime.download_links(rows))=={'7'}


def test_archived_order_listing_does_not_scan_dropbox():
    registry=Mock();registry.index.return_value={('gid://shopify/Product/123','456'):[7]}
    jobs=Mock();jobs.summaries.return_value={'7':{'id':'a'*64,'status':'Ready'}}
    with patch.object(runtime,'enabled',return_value=True),patch.object(runtime,'stores',return_value=(registry,jobs)),patch.object(runtime,'storage') as storage:
        links=runtime.download_links([dict(edition_order_id=7,shopify_product_id=123,variant_id=456)])
        assert links['7'].endswith('#Open')
        storage.assert_not_called()
