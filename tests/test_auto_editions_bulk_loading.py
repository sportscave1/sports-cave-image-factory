"""Bounded review reads; SQL fixtures contain no live records or credentials."""
import asyncio
import json
import time
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock,patch

import pytest
import auto_editions_bulk as bulk
from tests.test_auto_editions_bulk import review,store,database,pglite_database
from tests.test_auto_editions_api import ADMIN,request


def test_page_filter_precedes_status_and_full_record_reads(review):
    d,sql,record,assets=review
    with patch.object(bulk.statuses,'batch',wraps=bulk.statuses.batch) as states,patch.object(bulk,'records',wraps=bulk.records) as records:
        data=bulk.listing(d.connect,[record['manifest']['source']['product_gid']],ADMIN)
    assert data['page_size']==20 and data['next_cursor'] is None
    assert len(states.call_args.args[1])<=20 and len(records.call_args.args[1])<=20
    assert data['rows'][0]['eligible']


def test_completed_or_failed_candidates_do_not_stop_pagination(review):
    d,sql,record,assets=review
    # The existing authoritative status still excludes stale/malformed preparations.
    sql.execute("UPDATE auto_edition_onboarding SET status='Needs PSD Repair'")
    assert bulk.listing(d.connect,[record['manifest']['source']['product_gid']],ADMIN)['rows']==[]


def test_metadata_read_limits_do_not_leak_to_next_transaction(review):
    d,sql,record,assets=review
    with bulk.review_read(d.connect) as conn,conn.cursor() as cur:
        cur.execute('SHOW transaction_read_only');assert cur.fetchone()['transaction_read_only']=='on'
        cur.execute('SHOW statement_timeout');assert cur.fetchone()['statement_timeout']=='2500ms'
        cur.execute('SHOW lock_timeout');assert cur.fetchone()['lock_timeout']=='500ms'
    sql.execute('SHOW transaction_read_only');assert sql.fetchone()['transaction_read_only']=='off'


def test_read_gate_rejects_excess_work_without_opening_connections():
    connect=Mock(side_effect=AssertionError('No extra connections'))
    with patch.object(bulk,'READ_SLOTS') as slots:
        slots.acquire.return_value=False
        with pytest.raises(ValueError,match='busy'):
            with bulk.review_read(connect):pass
    connect.assert_not_called()


@pytest.mark.parametrize('active',[True,False])
def test_watchdog_only_cancels_its_own_active_lease(active):
    callbacks=[]
    class Timer:
        def __init__(self,seconds,callback):callbacks.append(callback)
        def start(self):pass
        def cancel(self):pass
    cursor=Mock();cursor.__enter__=Mock(return_value=cursor);cursor.__exit__=Mock(return_value=False)
    cancel=Mock();conn=SimpleNamespace(cursor=lambda:cursor,cancel_safe=cancel)
    @contextmanager
    def connect():yield conn
    with patch.object(bulk.threading,'Timer',Timer):
        with bulk.review_read(connect):
            if active:callbacks[0]()
        callbacks[0]()  # A late timer must never cancel another pool user's lease.
    assert cancel.call_count==int(active)
    if active:cancel.assert_called_once_with(timeout=1)


def test_list_deadline_returns_retryable_error_without_approving():
    async def run():
        import supabase_backend  # Exclude one-time module import from the request deadline probe.
        async def admin(*args,**kwargs):return ADMIN
        def delayed(*args):time.sleep(.15);return dict(rows=[],next_cursor=None,duration_ms=100)
        with patch.object(bulk,'actor',side_effect=admin),patch.object(bulk,'LIST_TIMEOUT_SECONDS',.02),patch.object(bulk,'listing',side_effect=delayed),patch.object(bulk,'approve_one',side_effect=AssertionError('Read only')):
            started=time.perf_counter();response=await bulk.list_api(request('POST',body=dict(product_gids=[])))
            assert time.perf_counter()-started<.12
            assert response.status_code==503 and 'Retry' in json.loads(response.body)['error']
    asyncio.run(run())


@pytest.mark.parametrize('cursor',[-1,True,'20',2])
def test_invalid_cursor_rejected_before_database_access(cursor):
    async def run():
        async def admin(*args,**kwargs):return ADMIN
        with patch.object(bulk,'actor',side_effect=admin),patch.object(bulk,'listing',side_effect=AssertionError('No read')):
            result=await bulk.list_api(request('POST',body=dict(product_gids=['gid://shopify/Product/1'],cursor=cursor)))
            assert result.status_code==409
    asyncio.run(run())
