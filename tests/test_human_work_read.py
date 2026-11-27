"""Reader access, DST and transaction contracts without application startup."""
from datetime import date, timezone
from unittest.mock import MagicMock, patch

import pytest
import sports_cave_dashboard as dashboard
import supabase_backend as backend


OWNER = dict(id='owner', email='preview@example.invalid', role='admin', is_active=True,
             timezone='Australia/Sydney', page_permissions=['reporting'])


@pytest.mark.parametrize('day,hours', [('2026-10-04',23),('2026-04-05',25)])
def test_human_work_uses_whole_local_dst_day(day,hours):
    service=MagicMock()
    service.list_human_work_events.return_value=[]
    with patch.dict('os.environ',SPORTS_CAVE_ADMIN_EMAIL=OWNER['email']), patch.object(dashboard,'get_supabase_backend',return_value=service):
        result=dashboard.list_human_work_entries_page(day,day,user=OWNER)
    args=service.list_human_work_events.call_args.kwargs
    assert (args['end_at']-args['start_at']).total_seconds()==hours*3600
    assert args['start_at'].tzinfo==timezone.utc
    assert result['rows']==[] and not result['has_next']


def test_nonowner_admin_cannot_broaden_own_read_with_staff_filter():
    service=MagicMock()
    service.list_human_work_events.return_value=[]
    with patch.dict('os.environ',SPORTS_CAVE_ADMIN_EMAIL='other@example.invalid'), patch.object(dashboard,'get_supabase_backend',return_value=service):
        dashboard.list_human_work_entries_page(date(2026,11,26),date(2026,11,26),user=OWNER,staff_filter='Other')
    args=service.list_human_work_events.call_args.kwargs
    assert args['user_ids']==['owner'] and args['staff_filter']==''


def test_inactive_user_denied_before_backend():
    with patch.object(dashboard,'get_supabase_backend',side_effect=AssertionError('DB reached')):
        with pytest.raises(dashboard.DashboardStorageError):
            dashboard.list_human_work_entries_page('2026-11-26','2026-11-26',user=dict(OWNER,is_active=False))


def test_timeout_transaction_closes_and_next_read_recovers():
    conn=MagicMock()
    conn.transaction.return_value.__enter__.return_value=conn
    cursor=conn.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value=[]
    cursor.execute.side_effect=[None,TimeoutError('Synthetic query timeout'),None,None]
    with patch.object(backend,'ensure_dashboard_schema'), patch.object(backend,'connect',side_effect=AssertionError('New write transport')), patch.object(backend,'read_connection') as pooled:
        pooled.return_value.__enter__.return_value=conn
        with pytest.raises(TimeoutError):backend.list_human_work_events(limit=26)
        assert backend.list_human_work_events(limit=26)==[]
    assert conn.transaction.call_count==2
    assert conn.transaction.return_value.__exit__.call_count==2
    assert any('SET LOCAL statement_timeout' in str(call) for call in cursor.execute.call_args_list)
