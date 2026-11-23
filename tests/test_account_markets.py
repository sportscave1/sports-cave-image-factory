import uuid
from unittest.mock import patch
import collector_vault as vault
from tests.test_collector_vault import _frame_environment, SECRET

def test_country_is_pinned_in_signed_cart_handoff(monkeypatch):
    monkeypatch.setenv('COLLECTOR_VAULT_ASSET_SIGNING_SECRET',SECRET)
    for country in ('AU','US','GB','CA','NZ','IE','FR','DE'):
        result=vault.frame_cart_response({'request_reference':uuid.uuid4()}, {}, 'gid://shopify/ProductVariant/42',country)
        token=result['cart_handoff_url'].split('sc_certificate_cart=')[1]
        payload=vault._verify_signed_token(token,expected_purpose='frame_cart')
        assert payload['country']==country and payload['variant_id'].endswith('/42')
        assert payload['destination']=='drawer'

def test_malformed_country_never_enters_signed_handoff(monkeypatch):
    monkeypatch.setenv('COLLECTOR_VAULT_ASSET_SIGNING_SECRET',SECRET)
    result=vault.frame_cart_response({'request_reference':uuid.uuid4()}, {}, 'gid://shopify/ProductVariant/42','US&attack')
    payload=vault._verify_signed_token(result['cart_handoff_url'].split('sc_certificate_cart=')[1],expected_purpose='frame_cart')
    assert payload['country']=='AU'


def test_frame_handoff_reuses_the_warmed_bounded_catalogue(monkeypatch):
    from tests.test_collector_vault import _frame_product_payload, FRAME_VARIANT_ID
    with patch.dict(vault.os.environ, _frame_environment(), clear=True), \
         patch.object(vault, '_FRAME_PRODUCT_CACHE', {}), \
         patch.object(vault.shopify_sync, 'graphql_request', return_value=(_frame_product_payload(), '2026-04')) as read:
        vault.get_frame_product()  # Account bootstrap warms the existing cache.
        assert vault._frame_variant_sku(FRAME_VARIANT_ID) == 'SC-FCC-A4-BLK'
        assert vault._frame_variant_sku(FRAME_VARIANT_ID) == 'SC-FCC-A4-BLK'
        assert read.call_count == 1
        with patch.object(vault.time, 'time', return_value=vault.time.time() + vault.FRAME_PRODUCT_CACHE_TTL_SECONDS + 1):
            vault._frame_variant_sku(FRAME_VARIANT_ID)
        assert read.call_count == 2  # Cache expiry still refreshes availability.


def test_cached_unavailable_frames_still_reject_before_cart_request_database(monkeypatch):
    import pytest
    from tests.test_collector_vault import _certificate_row, CUSTOMER_A
    with patch.object(vault, '_resolve_certificate_reference', return_value=_certificate_row()), \
         patch.object(vault, 'get_frame_product', return_value={'available':False}) as product, \
         patch.object(vault.supabase_backend, 'connect') as database:
        with pytest.raises(vault.CollectorVaultUnavailableError):
            vault.create_frame_request(CUSTOMER_A, certificate_reference='fixture', frame_variant_id='gid://shopify/ProductVariant/42',idempotency_key='fixture-42')
        product.assert_called_once_with()
        database.assert_not_called()

def test_launch_uses_only_shopify_localization_without_replacing_cart(monkeypatch):
    from starlette.testclient import TestClient
    from starlette.applications import Starlette
    from starlette.routing import Route
    import collector_vault_api as api
    monkeypatch.setenv('COLLECTOR_VAULT_ASSET_SIGNING_SECRET',SECRET)
    token=vault._signed_token({'purpose':'frame_cart','country':'US','request_reference':str(uuid.uuid4()),'variant_id':'gid://shopify/ProductVariant/42'},ttl_seconds=60)
    app=Starlette(routes=[Route('/launch',api.collector_vault_cart_launch)])
    response=TestClient(app).get('/launch',params={'sc_certificate_cart':token},follow_redirects=False)
    assert response.status_code==303
    assert response.headers['location']==('https://www.sportscaveshop.com/?country=US&sc_certificate_cart='+token)
    assert '/cart/clear' not in response.headers['location']
    assert response.headers['cache-control']=='no-store'
    assert TestClient(app).get('/launch',params={'sc_certificate_cart':'invalid'},follow_redirects=False).status_code in (401,403)

def test_owned_purchase_review_does_not_require_carrier_delivery(monkeypatch):
    from tests.test_collector_vault import _certificate_row,CUSTOMER_A
    monkeypatch.setenv('COLLECTOR_VAULT_ASSET_SIGNING_SECRET',SECRET)
    row=_certificate_row()
    with patch.object(vault,'_judgeme_configured',return_value=True), patch.object(vault,'_reviewed_keys',return_value=set()), patch.object(vault,'delivery_statuses',return_value={}), patch.object(vault,'lookup_judgeme_product',return_value={'id':'judge-product'}), patch.object(vault,'_resolve_certificate_reference',return_value=row):
        assert vault.review_prompt([row],CUSTOMER_A) is None
        prompt=vault.review_prompt([row],CUSTOMER_A,allow_purchased=True)
        assert prompt and vault._resolve_review_reference(prompt['reference'],CUSTOMER_A)==row
