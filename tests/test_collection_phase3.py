"""Synthetic recommendation caching; all database/Shopify reads are substituted."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from crm_cache import DisplayCache
from collector_preview_cache import ByteCache
import collector_recommendation_cache as ranked
import collector_collection_offers as offers
import collector_vault as vault


OWNER = 'gid://shopify/Customer/101'
SEED, OTHER, SPORT, SUBJECT, SPARE = [f'gid://shopify/Product/{i}' for i in range(55, 60)]


@pytest.fixture(autouse=True)
def isolated_candidates(monkeypatch):
    value = ByteCache(max_bytes=200_000, max_entries=16, ttl=120, max_pending=8)
    monkeypatch.setattr(ranked, 'CANDIDATES', value)
    return value


def shop_context(namespace='fixture-shop'):
    return SimpleNamespace(namespace=namespace, cache=DisplayCache())


def test_cache_keys_cover_owner_owned_set_seed_country_shop_and_generation():
    shop = shop_context()
    load = Mock(return_value={'candidates': [SUBJECT], 'groups': [[SUBJECT]]})
    def get(owner=OWNER, owned=None, seed=SEED, country='AU', context=None):
        return ranked.ranked_candidates(context or shop, owner, owned or {SEED}, seed, country, load)
    assert get() == get()
    assert load.call_count == 1
    get(owner='other-owner')
    get(owned={SEED, SPORT})
    get(seed=SPORT)
    get(country='US')
    get(context=shop_context('different-shop'))
    shop.cache.invalidate()
    get()
    assert load.call_count == 7


def test_existing_display_invalidation_has_monotonic_generation():
    c = DisplayCache()
    assert c.generation == 0
    c.invalidate('revision-1')
    assert c.generation == 1
    c.invalidate('revision-1')
    assert c.generation == 1
    c.invalidate()
    assert c.generation == 2


def test_failed_load_is_retried_and_caller_mutation_cannot_poison_cache():
    load = Mock(side_effect=[RuntimeError('temporary'), {'candidates': [SUBJECT], 'groups': [[SUBJECT]]}])
    shop = shop_context()
    def get():
        return ranked.ranked_candidates(shop, OWNER, {SEED}, SEED, 'AU', load)
    with pytest.raises(RuntimeError):
        get()
    value = get()
    value['candidates'].append('untrusted')
    value['groups'][0].clear()
    assert get() == {'candidates': [SUBJECT], 'groups': [[SUBJECT]]}
    assert load.call_count == 2


def test_rank_ttl_and_byte_limits(monkeypatch):
    clock = [0]
    c = ByteCache(max_bytes=200, max_entries=2, ttl=120, now=lambda: clock[0])
    monkeypatch.setattr(ranked, 'CANDIDATES', c)
    shop = shop_context()
    load = Mock(return_value={'candidates': [SUBJECT], 'groups': []})
    def get(country='AU'):
        return ranked.ranked_candidates(shop, OWNER, {SEED}, SEED, country, load)
    get(); get()
    assert load.call_count == 1
    clock[0] = 120
    get()
    assert load.call_count == 2
    get('US'); get('NZ')
    assert c.stats()['entries'] <= 2 and c.stats()['bytes'] <= 200


def test_inflight_rank_is_shared_and_old_generation_never_becomes_a_current_hit():
    shop, entered, release, joined = shop_context(), threading.Event(), threading.Event(), threading.Event()
    calls = []
    def load():
        calls.append(1)
        entered.set()
        assert release.wait(3)
        return {'candidates': [SUBJECT], 'groups': []}
    def get():
        return ranked.ranked_candidates(shop, OWNER, {SEED}, SEED, 'AU', load)
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(get)
        assert entered.wait(3)
        future = next(iter(ranked.CANDIDATES._pending.values()))
        result = future.result
        def follower(**kwargs):
            joined.set()
            return result(**kwargs)
        with patch.object(future, 'result', side_effect=follower):
            second = pool.submit(get)
            try:
                assert joined.wait(3)
                shop.cache.invalidate()
            finally:
                release.set()
        assert first.result() == second.result()
    assert len(calls) == 1
    get()
    assert len(calls) == 2


@pytest.fixture
def sources():
    shop = shop_context()
    shop.query = Mock(return_value={'nodes': [
        {'id': SEED, 'tags': ['SC_SUBJECT_A', 'SC_SPORT_BASEBALL']},
        {'id': SPORT, 'tags': ['SC_SPORT_BASEBALL']},
        {'id': SUBJECT, 'tags': ['SC_SUBJECT_A']},
        {'id': SPARE, 'tags': ['SC_SPORT_BASEBALL']},
    ]})
    ledger = Mock(return_value={OWNER: [{'products': [{'product_id': 55}, {'product_id': 56}]}]})
    certificates = Mock(return_value=[])
    catalogue = Mock()
    catalogue.resolve.side_effect = lambda ids, *a, **k: [dict(id=i, edition={'status': 'available'}) for i in ids]
    members, products = Mock(return_value=[{'id': 'baseball'}]), Mock(return_value=[SEED, OTHER, SPORT, SUBJECT, SPARE])
    signals = Mock(return_value={})
    with ExitStack() as stack:
        for target, value in [
            ('crm_smart_catalogue.histories', ledger),
            ('collector_vault.list_owned_certificates', certificates),
            ('crm_collector_transport.bounded', Mock(return_value=shop)),
            ('crm_shopify.Shopify', Mock(return_value=shop)),
            ('crm_catalogue.Catalogue', Mock(return_value=catalogue)),
            ('crm_smart_candidates.memberships', members),
            ('crm_smart_candidates.collection_products', products),
            ('crm_catalogue.edition_available', lambda edition: edition['status'] != 'sold_out'),
            ('crm_catalogue.product_issues', Mock(return_value=[])),
            ('website_recommendation_analytics._ranking_snapshot', signals),
        ]:
            stack.enter_context(patch(target, value))
        yield SimpleNamespace(shop=shop, ledger=ledger, certificates=certificates, catalogue=catalogue, members=members, products=products, signals=signals)


def test_warm_rank_avoids_memberships_tags_and_ranking_but_rechecks_ownership_and_eligibility(sources):
    first = offers.recommendations(OWNER, 'AU', SEED)
    second = offers.recommendations(OWNER, 'AU', SEED)
    assert first == second
    assert first[0]['id'] == SUBJECT
    assert sources.members.call_count == sources.products.call_count == sources.shop.query.call_count == 1
    assert sources.signals.call_count == 1
    assert sources.ledger.call_count == sources.certificates.call_count == sources.catalogue.resolve.call_count == 2


def test_new_purchase_changes_fingerprint_and_never_reappears_in_pairs(sources):
    assert offers.recommendations(OWNER, 'AU', SEED)[0]['id'] == SUBJECT
    sources.certificates.return_value = [{'shopify_product_id': SUBJECT}]
    result = offers.recommendations(OWNER, 'AU', SEED)
    assert SUBJECT not in [p['id'] for p in result]
    assert sources.members.call_count == 2


def test_warm_candidates_still_exclude_newly_sold_out_products(sources):
    offers.recommendations(OWNER, 'AU', SEED)
    sources.catalogue.resolve.side_effect = lambda ids, *a, **k: [dict(id=i, edition={'status': 'sold_out' if i == SUBJECT else 'available'}) for i in ids]
    result = offers.recommendations(OWNER, 'AU', SEED)
    assert SUBJECT not in [p['id'] for p in result]
    assert sources.members.call_count == 1
    assert sources.catalogue.resolve.call_count == 2


def test_missing_ownership_or_history_failure_never_serves_a_warm_rank(sources):
    offers.recommendations(OWNER, 'AU', SEED)
    sources.ledger.side_effect = RuntimeError('history unavailable')
    with pytest.raises(RuntimeError):
        offers.recommendations(OWNER, 'AU', SEED)
    assert sources.catalogue.resolve.call_count == 1
    sources.ledger.side_effect = None
    sources.ledger.return_value = {OWNER: [{'products': [{'product_id': 56}]}]}
    with pytest.raises(vault.CollectorVaultError, match='owned edition'):
        offers.recommendations(OWNER, 'AU', SEED)
    sources.ledger.return_value = {}
    assert offers.recommendations(OWNER, 'AU', SEED) == []
    assert sources.catalogue.resolve.call_count == 1


def test_query_candidate_cache_contains_no_customer_records_prices_or_credentials(sources):
    offers.recommendations(OWNER, 'AU', SEED)
    entries = ranked.CANDIDATES._entries
    assert len(entries) == 1
    key, (content, _) = next(iter(entries.items()))
    assert OWNER not in key and len(key) == 64
    assert OWNER.encode() not in content
    assert b'price' not in content and b'customer' not in content and b'token' not in content


def test_recommendation_api_reauthenticates_warm_hits_and_ignores_supplied_customer(sources):
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    import collector_vault_api as api
    client = TestClient(Starlette(routes=[Route(path, handler, methods=methods) for path, handler, methods in api.COLLECTOR_VAULT_ROUTES]))
    url = '/api/collector-vault/recommendations?fields=ids&country=AU&product_id='+SEED+'&customer_id=other'
    with patch.object(vault, 'verify_shopify_session_token', return_value={'shopify_customer_id': OWNER}) as auth:
        for _ in range(2):
            response = client.get(url, headers={'Authorization': 'Bearer synthetic'})
            assert response.status_code == 200
            assert response.json()['products'][0] == {'id': SUBJECT}
        assert auth.call_count == 2
    assert sources.ledger.call_count == 2 and sources.members.call_count == 1
    assert client.get(url).status_code == 401
    assert sources.ledger.call_count == 2


def test_saturated_rank_cache_returns_retryable_service_error(monkeypatch):
    from collector_preview_cache import PreviewBusyError
    monkeypatch.setattr(ranked, 'CANDIDATES', Mock(get_or_load=Mock(side_effect=PreviewBusyError())))
    with pytest.raises(vault.CollectorVaultUnavailableError) as raised:
        ranked.ranked_candidates(shop_context(), OWNER, {SEED}, SEED, 'AU', lambda: {})
    assert raised.value.status_code == 503


def test_legacy_unseeded_recommendations_keep_collection_balancing(sources):
    sources.members.return_value = [{'id': 'baseball'}, {'id': 'basketball'}]
    sources.products.side_effect = lambda shop, group: [SEED, SPORT] if group == 'baseball' else [OTHER, SUBJECT, SPARE]
    for _ in range(2):
        result = offers.recommendations(OWNER, 'AU')
        assert [product['id'] for product in result] == [SPORT, SUBJECT, SPARE]
    assert sources.members.call_count == 1 and sources.products.call_count == 2
    assert sources.shop.query.call_count == 0
    assert sources.catalogue.resolve.call_count == 2


def test_cold_recommendations_batch_lightweight_affinity_and_stop_after_eight_eligible(sources):
    candidates = [f"gid://shopify/Product/{i}" for i in range(1000, 1120)]
    sources.products.return_value = [SEED, *candidates]
    sources.shop.query.return_value = {'nodes': [{'id': i, 'tags': ['SC_SPORT_BASEBALL']} for i in [SEED, *candidates]]}
    result = offers.recommendations(OWNER, 'AU', SEED)
    assert sources.shop.query.call_count == 1
    assert len(sources.shop.query.call_args.args[1]['ids']) == 121
    assert sources.catalogue.resolve.call_count == 1
    assert len(sources.catalogue.resolve.call_args.args[0]) == 8
    assert [p['id'] for p in result] == candidates[:8]


def test_small_fact_batches_still_find_eight_eligible_in_smart_order(sources):
    candidates = [f"gid://shopify/Product/{i}" for i in range(1000, 1020)]
    sources.products.return_value = [SEED, *candidates]
    sources.shop.query.return_value = {'nodes': [{'id': i, 'tags': ['SC_SPORT_BASEBALL']} for i in [SEED, *candidates]]}
    sources.catalogue.resolve.side_effect = lambda ids, *a, **k: [dict(id=i, edition={'status': 'sold_out' if i in candidates[:4] else 'available'}) for i in ids]
    result = offers.recommendations(OWNER, 'AU', SEED)
    assert [p['id'] for p in result] == candidates[4:12]
    assert sources.catalogue.resolve.call_count == 2
