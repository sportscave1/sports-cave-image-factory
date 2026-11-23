import asyncio
import threading
from unittest.mock import patch
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.requests import Request
from starlette.testclient import TestClient
import collector_vault as vault
import collector_vault_api as api

OWNER = 'gid://shopify/Customer/101'

def test_fast_bootstrap_never_calls_optional_review_provider():
    with patch.object(vault, '_list_owned_certificates_with_capabilities', return_value=([], {'secure_assets': True, 'frame_requests': True})), \
         patch.object(vault, 'get_frame_product', return_value={'available': True}), \
         patch.object(vault, '_public_certificate_rows', return_value=[]), \
         patch.object(vault, 'review_prompt', side_effect=AssertionError('optional provider was called')):
        result = vault.build_vault_payload(OWNER, include_review=False)
    assert result['frame_product']['available'] is True
    assert result['review_prompt'] is None


def test_legacy_bootstrap_keeps_review_payload_by_default():
    with patch.object(vault, '_list_owned_certificates_with_capabilities', return_value=([], {'secure_assets': True})), \
         patch.object(vault, '_public_certificate_rows', return_value=[]), \
         patch.object(vault, 'review_prompt', return_value={'reference': 'fixture'}) as review:
        result = vault.build_vault_payload(OWNER)
    assert result['review_prompt']['reference'] == 'fixture'
    review.assert_called_once_with([], OWNER, allow_purchased=True)


def test_review_options_respect_secure_asset_capability():
    with patch.object(vault, '_list_owned_certificates_with_capabilities', return_value=([], {'secure_assets': False})), \
         patch.object(vault, 'review_prompt') as review:
        assert vault.build_review_prompt_payload(OWNER) == {'review_prompt': None}
    review.assert_not_called()


APP = Starlette(routes=[Route(path, handler, methods=methods) for path, handler, methods in api.COLLECTOR_VAULT_ROUTES])

def test_review_options_require_authentication_before_lookup():
    with patch.object(vault, 'build_review_prompt_payload') as load:
        assert TestClient(APP).get('/api/collector-vault/review-prompt').status_code == 401
    load.assert_not_called()


def test_review_options_use_session_owner_not_supplied_customer_id():
    with patch.object(vault, 'verify_shopify_session_token', return_value={'shopify_customer_id': OWNER}), \
         patch.object(vault, 'build_review_prompt_payload', return_value={'review_prompt': {'reference': 'owned'}}) as load:
        response = TestClient(APP).get('/api/collector-vault/review-prompt?customer_id=other', headers={'Authorization': 'Bearer fixture'})
    assert response.status_code == 200
    load.assert_called_once_with(OWNER)


def test_slow_optional_review_does_not_block_frame_bootstrap():
    gate, entered = threading.Event(), threading.Event()
    def optional(_owner):
        entered.set()
        gate.wait(3)
        return {'review_prompt': None}
    def request(path, query=b''):
        return Request({'type': 'http', 'method': 'GET', 'path': path, 'query_string': query, 'headers': []})
    async def exercise():
        review = asyncio.create_task(api.collector_vault_review_prompt(request('/api/collector-vault/review-prompt')))
        try:
            assert await asyncio.to_thread(entered.wait, 1)
            response = await asyncio.wait_for(api.collector_vault_bootstrap(request('/api/collector-vault/bootstrap', b'include_review=false')), timeout=1)
            assert response.status_code == 200
            assert not review.done()
        finally:
            gate.set()
            await review
    with patch.object(api, '_session', return_value={'shopify_customer_id': OWNER}), \
         patch.object(vault, 'build_review_prompt_payload', side_effect=optional), \
         patch.object(vault, 'build_vault_payload', return_value={'certificates': [], 'frame_product': {'available': True}}) as load:
        asyncio.run(exercise())
    load.assert_called_once_with(OWNER, include_review=False)

def test_compact_recommendation_response_preserves_rank_and_context_without_product_bloat():
    products = [{'id': str(i), 'title': 'private unused payload', 'variants': [{}] * 100} for i in range(10)]
    with patch.object(vault, 'verify_shopify_session_token', return_value={'shopify_customer_id': OWNER}), \
         patch('collector_collection_offers.recommendations', return_value=products) as recommend:
        response = TestClient(APP).get('/api/collector-vault/recommendations?fields=ids&country=US&product_id=seed', headers={'Authorization': 'Bearer fixture'})
    assert response.json()['products'] == [{'id': str(i)} for i in range(8)]
    recommend.assert_called_once_with(OWNER, country='US', seed_product_id='seed')


def test_legacy_recommendation_response_is_unchanged():
    products = [{'id': '1', 'title': 'Existing card'}]
    with patch.object(vault, 'verify_shopify_session_token', return_value={'shopify_customer_id': OWNER}), \
         patch('collector_collection_offers.recommendations', return_value=products):
        response = TestClient(APP).get('/api/collector-vault/recommendations', headers={'Authorization': 'Bearer fixture'})
    assert response.json()['products'] == products
