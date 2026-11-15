"""Local role/loading regression checks. All data and provider calls are synthetic."""
import time
from concurrent.futures import Future, ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch, Mock

import os_accounts
import dropbox_integration
import os_pages
import developer_studio_page


def test_owner_route_and_direct_page_fail_closed_for_staff():
    owner=dict(id='owner',email='owner@example.test',role='admin',is_active=True)
    staff={**owner,'id':'va','role':'worker','page_permissions':['orders','prodigi','files','developer_studio']}
    with patch.dict('os.environ',{'SPORTS_CAVE_REPORTING_OWNER_EMAIL':owner['email']}):
        assert os_accounts.can_access_page(owner,'Developer Studio')
        assert not os_accounts.can_access_page(staff,'Developer Studio')
        assert all(os_accounts.can_access_page(staff,page) for page in ('Orders','Prodigi','Files'))
        with patch.object(developer_studio_page,'panel_html') as assets,patch('streamlit.error'):
            developer_studio_page.render_page(staff)
            assets.assert_not_called()


def test_prodigi_pending_rerenders_submit_one_bounded_read():
    future=Future(); executor=Mock(); executor.submit.return_value=future
    state={}
    with patch.object(os_pages,'st',SimpleNamespace(session_state=state)),patch.object(os_pages,'_PRODIGI_LOAD_EXECUTOR',executor):
        started=time.perf_counter()
        for _ in range(100):
            os_pages._start_prodigi_dispatch_load('Last 7 Days','',50)
            assert os_pages._consume_prodigi_dispatch_load()=='loading'
        elapsed=time.perf_counter()-started
        assert executor.submit.call_count==1
        assert executor.submit.call_args.args[1:]==('Last 7 Days','',50)
        future.set_result([{'row_id':'synthetic'}])
        assert os_pages._consume_prodigi_dispatch_load()=='ready'
        assert state[os_pages.PRODIGI_DISPATCH_FUTURE_KEY] is None
        assert os_pages._consume_prodigi_dispatch_load()=='idle'
        print(f'PRODIGI_SYNTHETIC pending_renders=100 reads=1 elapsed_ms={elapsed*1000:.2f}')


def test_prodigi_timeout_keeps_display_and_explicit_retry_recovers():
    state={os_pages.PRODIGI_DISPATCH_ROWS_KEY:[{'row_id':'previous'}]}
    first=Future(); second=Future(); executor=Mock(); executor.submit.side_effect=[first,second]
    with patch.object(os_pages,'st',SimpleNamespace(session_state=state)),patch.object(os_pages,'_PRODIGI_LOAD_EXECUTOR',executor):
        os_pages._start_prodigi_dispatch_load('Last 7 Days')
        state[os_pages.PRODIGI_DISPATCH_STARTED_KEY]=time.monotonic()-9
        assert os_pages._consume_prodigi_dispatch_load()=='error'
        assert first.cancelled()
        assert state[os_pages.PRODIGI_DISPATCH_ROWS_KEY]==[{'row_id':'previous'}]
        assert os_pages._consume_prodigi_dispatch_load()=='idle'
        assert executor.submit.call_count==1  # no automatic retry loop
        os_pages._start_prodigi_dispatch_load('Last 7 Days',force=True)
        second.set_result([{'row_id':'recovered'}])
        assert os_pages._consume_prodigi_dispatch_load()=='ready'
        assert not state[os_pages.PRODIGI_DISPATCH_ERROR_KEY]


def test_prodigi_shell_does_not_wait_for_slow_database_for_either_role():
    from streamlit.testing.v1 import AppTest
    for role in ('admin','worker'):
        assert os_accounts.can_access_page(dict(id=role,role=role,page_permissions=['prodigi']), 'Prodigi')
        gate=__import__('threading').Event()
        def read(**kwargs):
            assert kwargs=={'limit':50,'search':'','days':7}
            assert gate.wait(5)
            return []
        with ThreadPoolExecutor(max_workers=1) as executor,patch.object(os_pages,'_PRODIGI_LOAD_EXECUTOR',executor),patch.object(os_pages.supabase_backend,'is_configured',return_value=True),patch.object(os_pages.supabase_backend,'list_prodigi_dispatch_rows',side_effect=read) as database,patch.object(os_pages,'_prodigi_prepare_entry_state'),patch.object(dropbox_integration,'get_file_response',side_effect=AssertionError('No asset download on Prodigi entry')):
            app=AppTest.from_string('import os_pages\nos_pages.render_prodigi_page()')
            try:
                started=time.perf_counter();app.run(timeout=4);elapsed=time.perf_counter()-started
                assert not app.exception
                assert len(app.title)==1
                assert database.call_count==1
                assert not app.session_state[os_pages.PRODIGI_DISPATCH_FUTURE_KEY].done()
                print(f'PRODIGI_SYNTHETIC role={role} shell_ms={elapsed*1000:.2f} db_pending=true reads=1 asset_downloads=0')
            finally:
                gate.set()
