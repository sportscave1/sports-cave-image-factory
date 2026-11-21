"""Capacity refusals preserve mutation safety, allocation guards and visible review."""
from contextlib import ExitStack, redirect_stdout
import io
from unittest.mock import MagicMock, Mock, patch

import pytest
import requests
import shopify_sync as shopify
import supabase_backend as db
from tests.test_auto_editions_jobs import database

CONFIG = dict(store_domain='fixture.myshopify.com', api_version='2026-04', access_token='synthetic-token')
THROTTLED = {'errors': [{'message': 'Throttled', 'extensions': {'code': 'THROTTLED'}}]}


def response(payload, status=200, headers=None):
    result = Mock(status_code=status, headers=headers or {}, text='capacity refusal')
    result.json.return_value = payload
    if status >= 400:
        result.raise_for_status.side_effect = requests.HTTPError(response=result)
    return result


def request(post, query='query { shop { id } }'):
    return shopify.graphql_request(query, {'fixture': 1}, config=CONFIG, request_post=post)


def test_explicit_throttle_retries_identical_request_and_returns_version():
    payload = dict(THROTTLED, extensions={'cost': {'requestedQueryCost': 110,
        'throttleStatus': {'currentlyAvailable': 10, 'restoreRate': 50, 'maximumAvailable': 1000}}})
    post = Mock(side_effect=[response(payload), response({'data': {'ok': True}}, headers={'X-Shopify-API-Version': '2026-04'})])
    with patch.object(shopify.time, 'sleep') as sleep:
        assert request(post) == ({'ok': True}, '2026-04')
    sleep.assert_called_once_with(2.1)
    assert post.call_args_list[0] == post.call_args_list[1]


def test_http_429_honours_retry_after_even_for_falsey_requests_response():
    throttled = requests.Response()
    throttled.status_code = 429
    throttled._content = b'throttled'
    throttled.headers['Retry-After'] = '3'
    post = Mock(side_effect=[throttled, response({'data': {'ok': True}})])
    with patch.object(shopify.time, 'sleep') as sleep:
        assert request(post)[0] == {'ok': True}
    sleep.assert_called_once_with(3)


@pytest.mark.parametrize('payload', [
    dict(THROTTLED, data={'mutationResult': {'id': 'created'}}),
    dict(THROTTLED, errors=THROTTLED['errors'] + [{'message': 'Denied', 'extensions': {'code': 'ACCESS_DENIED'}}]),
    {'errors': [{'message': 'Invalid query'}]},
    {'errors': [{'message': 'Invalid metadata', 'extensions': 'unexpected'}]},
    {'data': None},
])
def test_partial_mixed_and_permanent_errors_are_never_replayed(payload):
    post = Mock(return_value=response(payload))
    with patch.object(shopify.time, 'sleep') as sleep, pytest.raises(shopify.ShopifyAPIError):
        request(post, 'mutation { fixtureWrite { id } }')
    post.assert_called_once()
    sleep.assert_not_called()


@pytest.mark.parametrize('failure', [requests.Timeout('uncertain execution'), response({}, 500), response({}, 401)])
def test_network_and_non_throttle_http_failures_are_not_replayed(failure):
    post = Mock(side_effect=failure) if isinstance(failure, Exception) else Mock(return_value=failure)
    with patch.object(shopify.time, 'sleep') as sleep, pytest.raises(shopify.ShopifyAPIError):
        request(post, 'mutation { fixtureWrite { id } }')
    post.assert_called_once()
    sleep.assert_not_called()


def test_persistent_throttle_is_bounded_and_remains_retryable_by_existing_queue():
    post = Mock(return_value=response(THROTTLED))
    with patch.object(shopify.time, 'sleep') as sleep, pytest.raises(shopify.ShopifyThrottleError):
        request(post)
    assert post.call_count == 3
    assert [call.args[0] for call in sleep.call_args_list] == [1, 2]


@pytest.mark.parametrize('retry_after', ['60', 'nan', '-1', 'unparseable'])
def test_unusable_or_long_retry_after_defers_without_early_retry(retry_after):
    post = Mock(return_value=response({}, 429, {'Retry-After': retry_after}))
    with patch.object(shopify.time, 'sleep') as sleep, pytest.raises(shopify.ShopifyAPIError):
        request(post)
    post.assert_called_once()
    sleep.assert_not_called()


def test_cost_larger_than_bucket_or_no_restoration_does_not_spin():
    for maximum, rate in [(50, 10), (1000, 0)]:
        payload = dict(THROTTLED, extensions={'cost': {'requestedQueryCost': 100,
            'throttleStatus': {'currentlyAvailable': 0, 'restoreRate': rate, 'maximumAvailable': maximum}}})
        post = Mock(return_value=response(payload))
        with patch.object(shopify.time, 'sleep') as sleep, pytest.raises(shopify.ShopifyAPIError):
            request(post)
        post.assert_called_once()
        sleep.assert_not_called()


class Refusal(Exception):
    sqlstate = 'P0001'


@pytest.mark.parametrize('exhausted', [True, False, None])
def test_atomic_refusal_requires_fresh_exhausted_run_and_never_commits(exhausted):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    cur = conn.cursor.return_value.__enter__.return_value
    error = Refusal('Edition run is disabled, archived or sold out\nCONTEXT: private@example.invalid')
    cur.execute.side_effect = [error, None]
    cur.fetchone.return_value = {'exhausted': exhausted}
    output = io.StringIO()
    with patch.object(db, 'require_atomic_edition_allocation_capability'), patch.object(db, 'connect', return_value=conn), redirect_stdout(output):
        with pytest.raises(ValueError if exhausted else Refusal) as raised:
            db.allocate_edition_line_units_atomic(order={'shopify_order_id': 'gid://shopify/Order/1'},
                line_item={'shopify_line_item_id': 'gid://shopify/LineItem/1'},
                product={'shopify_product_gid': 'gid://shopify/Product/1'}, quantity=1)
    assert ('Edition limit reached' in str(raised.value)) is bool(exhausted)
    assert ('atomic_edition_allocation_blocked' in output.getvalue()) is bool(exhausted)
    assert 'private@example.invalid' not in output.getvalue()
    conn.commit.assert_not_called()
    conn.rollback.assert_called_once()
    assert cur.execute.call_count == 2
    assert cur.execute.call_args.args[0].lstrip().startswith('SELECT')


def test_diagnostic_failure_preserves_original_allocator_error():
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value.execute.side_effect = RuntimeError('diagnostic down')
    assert db._atomic_refusal_is_sold_out(conn, Refusal('Edition run is disabled, archived or sold out'), 'gid://shopify/Product/1') is False
    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()
    conn.rollback.side_effect = RuntimeError('connection closed')
    assert db._atomic_refusal_is_sold_out(conn, Refusal('Edition run is disabled, archived or sold out'), 'gid://shopify/Product/1') is False


def test_real_postgres_capacity_classification_preserves_all_counters(database):
    jobs, sql = database
    sql.execute('''CREATE TEMP TABLE edition_products(shopify_product_gid text,
        active_edition_run_id int,edition_total int,sold_count int,remaining_count int,
        next_edition_number int,sold_out boolean,is_sold_out boolean)''')
    sql.execute('''CREATE TEMP TABLE edition_runs(id int,status text,edition_total int,next_edition_number int)''')
    sql.execute("INSERT INTO edition_products VALUES ('gid://shopify/Product/1',1,100,100,0,101,true,true)")
    sql.execute("INSERT INTO edition_runs VALUES (1,'sold_out',100,101)")
    error = Refusal('Edition run is disabled, archived or sold out')
    with jobs.connect() as conn:
        assert db._atomic_refusal_is_sold_out(conn, error, 'gid://shopify/Product/1') is True
        assert db._atomic_refusal_is_sold_out(conn, error, 'gid://shopify/Product/2') is False
    sql.execute('SELECT * FROM edition_products')
    before = sql.fetchall()
    for field, value in [('status', 'expired'), ('status', 'inactive'), ('status', 'active'),
                         ('next_edition_number', 99), ('edition_total', 99)]:
        sql.execute(f'UPDATE edition_runs SET {field}=%s WHERE id=1', (value,))
        with jobs.connect() as conn:
            assert db._atomic_refusal_is_sold_out(conn, error, 'gid://shopify/Product/1') is False
        sql.execute("UPDATE edition_runs SET status='sold_out',next_edition_number=101,edition_total=100")
    sql.execute('SELECT * FROM edition_products')
    assert sql.fetchall() == before


def test_confirmed_capacity_refusal_uses_existing_sold_out_ui_and_retry_workflow():
    order = {'shopify_order_id': 'gid://shopify/Order/1', 'financial_status': 'PAID',
             'line_items': [{'shopify_line_item_id': 'gid://shopify/LineItem/1', 'quantity': 1}]}
    product = {'handle': 'synthetic', 'shopify_product_id': 'gid://shopify/Product/1', 'active': True}
    with ExitStack() as stack:
        for name in ('_persist_order_snapshot', '_set_order_ingestion_outcome', '_sync_perf_log'):
            stack.enter_context(patch.object(db, name))
        stack.enter_context(patch.object(db, 'shopify_order_eligibility', return_value={'eligible': True}))
        stack.enter_context(patch.object(db, '_order_effective_datetime', return_value=None))
        stack.enter_context(patch.object(db, '_assignment_snapshot_covers_line', return_value=(False, {})))
        stack.enter_context(patch.object(db, 'resolve_edition_product_for_order_line', return_value={'product': product}))
        stack.enter_context(patch.object(db, 'connect', return_value=MagicMock()))
        status = stack.enter_context(patch.object(db, '_set_order_line_status'))
        allocator = stack.enter_context(patch.object(db, 'allocate_edition_line_units_atomic', side_effect=ValueError('Edition limit reached: sold out; review required')))
        result = db.process_paid_order(order, ensure_schema_first=False, generate_certificates=False, sync_product_metafields=False)
    assert status.call_args.args[2] == 'Sold Out'
    assert result['assignments_created'] == 0
    assert result['ingestion_status'] == 'retryable_error'
    assert result['errors']
    allocator.assert_called_once()
