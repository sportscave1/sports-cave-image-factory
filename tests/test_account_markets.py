import uuid
from unittest.mock import patch
import collector_vault as vault
from tests.test_collector_vault import _frame_environment, SECRET

def test_country_is_pinned_in_signed_cart_handoff(monkeypatch):
    monkeypatch.setenv('COLLECTOR_VAULT_ASSET_SIGNING_SECRET',SECRET)
    for country in ('AU','US','GB','CA','NZ','DE'):
        result=vault.frame_cart_response({'request_reference':uuid.uuid4()}, {}, 'gid://shopify/ProductVariant/42',country)
        token=result['cart_handoff_url'].split('sc_certificate_cart=')[1]
        payload=vault._verify_signed_token(token,expected_purpose='frame_cart')
        assert payload['country']==country and payload['variant_id'].endswith('/42')

def test_malformed_country_never_enters_signed_handoff(monkeypatch):
    monkeypatch.setenv('COLLECTOR_VAULT_ASSET_SIGNING_SECRET',SECRET)
    result=vault.frame_cart_response({'request_reference':uuid.uuid4()}, {}, 'gid://shopify/ProductVariant/42','US&attack')
    payload=vault._verify_signed_token(result['cart_handoff_url'].split('sc_certificate_cart=')[1],expected_purpose='frame_cart')
    assert payload['country']=='AU'
