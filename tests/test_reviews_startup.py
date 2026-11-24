"""Startup boundaries: synthetic state only; no provider transport."""
import ast
import subprocess
import inspect
import os
import uuid
from concurrent.futures import Future
from unittest.mock import Mock,patch
import pytest
import reviews_page as page
from reviews_cache import settle_initial
from reviews_store import ReviewsStore


def test_layout_and_row_markup_unchanged_from_published_layout():
    baseline=subprocess.check_output(['git','show','82dbd17df3bb2fa10c18a7f626ad9a9f982b6980:reviews_page.py'],text=True,encoding='utf-8')
    def nodes(source):
        tree=ast.parse(source)
        return [ast.dump(n,include_attributes=False) for n in tree.body if
          (isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='STYLE_REVIEW' for t in n.targets)) or
          (isinstance(n,ast.FunctionDef) and n.name=='row_html')]
    assert nodes(baseline)==nodes(open('reviews_page.py',encoding='utf-8').read())


def test_initial_completion_window_is_capped_and_cached_refresh_never_waits():
    future=Future();key=('table',)
    state={'reviews_cache':{key:{'future':future}}}
    with patch('reviews_cache.wait') as wait:
        settle_initial(state,[key],timeout=30)
        wait.assert_called_once_with([future],timeout=.5)
        state['reviews_good']={key:[]};wait.reset_mock()
        settle_initial(state,[key]);wait.assert_not_called()
    future.set_result([])
    with patch('reviews_cache.wait') as wait:
        settle_initial(state,[key]);wait.assert_not_called()


def test_prefetch_requires_permission_before_queueing_and_skips_other_tabs():
    with patch.object(page,'require',side_effect=PermissionError),patch.object(page,'read') as read:
        with pytest.raises(PermissionError):page.prefetch_overview({})
        read.assert_not_called()
    with patch.object(page,'require'),patch.object(page.st,'session_state',{'reviews-tabs':'Import & connections'}),patch.object(page,'read') as read:
        page.prefetch_overview({},Mock());read.assert_not_called()


def test_prefetch_uses_current_filter_and_page_keys():
    signature=('PENDING','fixture','',4,'csv',30)
    state={'reviews-status':'Pending','rv_search':'fixture','rv_rating':4,'rv_source':'csv','rv_period':30,
      'reviews_state':{'filters':signature,'offset':25}}
    with patch.object(page,'require'),patch.object(page.st,'session_state',state),patch.object(page,'read') as read:
        keys=page.prefetch_overview({},Mock())
        assert keys==(('table',signature,25),('summary',))
        assert [c.args[1] for c in read.call_args_list]==list(keys)


def test_legacy_reviews_do_not_start_receipt_jobs():
    with patch.object(page,'load') as load:
        page.acknowledge_visible(Mock(),{},[{'id':'fixture','status':'PUBLISHED','notification_received_at':None}])
        load.assert_not_called()


def test_visible_new_arrivals_still_acknowledge_only_active_reviews():
    rows=[{'id':'new','status':'PENDING','notification_received_at':'2026-11-24'},
      {'id':'archived','status':'ARCHIVED','notification_received_at':'2026-11-24'},
      {'id':'legacy','status':'PUBLISHED','notification_received_at':None}]
    with patch.object(page,'load',return_value=(None,'LOADING')) as load:
        page.acknowledge_visible(Mock(),{'id':'synthetic-account'},rows)
        assert load.call_args.args[0][2]==('new',)


def test_private_read_pool_adapter_and_single_summary_query():
    store=ReviewsStore();cursor=Mock();cursor.fetchone.return_value={'totals':{},'n':0}
    def run(operation,select,deadline_seconds):
        assert deadline_seconds==4
        return select(cursor),{}
    with patch('supabase_backend._run_read_operation',side_effect=run) as pool:
        result=store.summary()
        assert result['total']==0
        assert pool.call_count==1
        assert pool.call_args.args[0]=='reviews.summary'
        cursor.execute.assert_called_once()
    with patch.object(store,'q',return_value=[]) as q,patch('supabase_backend._run_read_operation') as pool:
        store.rows(public=True);q.assert_called_once();pool.assert_not_called()


def test_fragment_rechecks_access_before_any_read_and_clears_the_table():
    authorize=Mock(return_value={})
    with patch.object(page,'require',side_effect=PermissionError),patch.object(page,'read') as read,patch.object(page.st,'warning') as warning:
        inspect.unwrap(page.overview)(Mock(),{'id':'old-account'},authorize)
        authorize.assert_called_once();read.assert_not_called();warning.assert_called_once()


def test_pagination_callback_updates_before_render_and_clamps_previous():
    session={'reviews_state':{'offset':25}}
    with patch.object(page.st,'session_state',session):
        page.move_page(25);assert session['reviews_state']['offset']==50
        page.move_page(-75);assert session['reviews_state']['offset']==0


@pytest.mark.skipif(os.getenv('CRM_TEST_POSTGRES')!='1',reason='Disposable PostgreSQL required')
def test_compact_projection_keeps_identical_markup_and_full_editor_record():
    from tests.crm_db_fixture import connect
    store=ReviewsStore(connect);identity=str(uuid.uuid4())
    try:
        store.q("INSERT INTO sc_reviews(id,source,reviewer_name,rating,dedupe_key,title,body,source_metadata) VALUES(%s,'csv',%s,4,%s,'Synthetic title',%s,jsonb_build_object('large_provider_payload',repeat('private',2000),'date_known',false))",(identity,identity,identity,'Synthetic review text '+('🏏'*400)))
        full=store.get_review(identity)
        compact=next(r for r in store.rows(overview=True,search=identity) if str(r['id'])==identity)
        assert page.row_html(full)==page.row_html(compact)
        assert len(compact['body'])==161
        assert compact['source_metadata']=={'date_known':False}
        assert 'email' not in compact and 'dedupe_key' not in compact
        assert len(full['body'])>161 and 'large_provider_payload' in full['source_metadata']
        for metadata in ("jsonb_build_object('date_known',null)","'{}'::jsonb"):
            store.q('UPDATE sc_reviews SET source_metadata='+metadata+' WHERE id=%s',(identity,))
            full=store.get_review(identity)
            compact=next(r for r in store.rows(overview=True,search=identity) if str(r['id'])==identity)
            assert page.row_html(full)==page.row_html(compact)
            assert compact['source_metadata']==full['source_metadata']
    finally:store.q('DELETE FROM sc_reviews WHERE id=%s',(identity,))
