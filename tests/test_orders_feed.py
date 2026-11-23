from copy import deepcopy
from types import SimpleNamespace
import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient
import orders_feed as feed
import orders_prodigi_grid as grid
from test_orders_prodigi_grid import screen


def saved(ids):
    raw=[dict(edition_order_id=i,shopify_order_id=str(i),shopify_line_item_id=str(i),order='#'+str(i)) for i in ids]
    rows=grid.payload_rows(raw,raw,{},allowed=False)
    return dict(raw=raw,rows=rows,version=feed.signature([(r['id'],r['revision']) for r in rows]))


@pytest.fixture
def state(monkeypatch):
    feed._cache.clear();feed._building.clear()
    monkeypatch.setattr(feed,'allowed',lambda actor:actor.get('admin',False))
    monkeypatch.setattr(feed,'marker',lambda:'same-marker')
    return dict(id='fixture',admin=True)


def test_delta_adds_changes_and_removes_exact_ids_without_resending_unchanged_rows():
    before=saved([1,2]);after=saved([3,2]);known={r['id']:r['revision'] for r in before['rows']}
    result=feed.delta(after,known)
    assert result['order']==['allocation:3','allocation:2']
    assert [r['id'] for r in result['rows']]==['allocation:3']
    assert result['removed']==['allocation:1']


def test_unchanged_marker_reuses_snapshot_but_expiry_rechecks_mapping_and_completion(state,monkeypatch):
    calls=[]
    monkeypatch.setattr(feed,'build',lambda *_:(calls.append(True) or saved([len(calls)])))
    first,_=feed.snapshot(state,'')
    assert feed.snapshot(state,'')[0]==first and len(calls)==1
    feed._cache[feed.key(state,'')]['at']-=31
    assert feed.snapshot(state,'')[0]!=first and len(calls)==2


def test_cached_views_are_isolated_by_actor_search_and_privileges(state,monkeypatch):
    monkeypatch.setattr(feed,'build',lambda *_:saved([1]))
    first,_=feed.snapshot(state,'#1')
    assert feed.recalled(state,'#1',first['version'])
    assert feed.recalled(dict(id='other',admin=True),'#1',first['version']) is None
    assert feed.recalled(dict(id='fixture',admin=False),'#1',first['version']) is None
    assert feed.recalled(state,'#2',first['version']) is None


def test_source_failure_keeps_previous_good_snapshot(state,monkeypatch):
    monkeypatch.setattr(feed,'build',lambda *_:saved([1]))
    old,_=feed.snapshot(state,'')
    monkeypatch.setattr(feed,'marker',lambda:'changed')
    def failed(*_):raise RuntimeError('Synthetic unavailable source')
    monkeypatch.setattr(feed,'build',failed)
    with pytest.raises(RuntimeError):feed.snapshot(state,'')
    assert feed.recalled(state,'',old['version'])==old and not feed._building


def test_same_view_builds_once_and_never_overwrites_newer_data(state,monkeypatch):
    monkeypatch.setattr(feed,'build',lambda *_:saved([1]))
    old,_=feed.snapshot(state,'');waiting=[]
    monkeypatch.setattr(feed,'marker',lambda:'changed')
    def build(*_):
        waiting.append(feed.snapshot(state,''))
        return saved([2])
    monkeypatch.setattr(feed,'build',build)
    new,delayed=feed.snapshot(state,'')
    assert waiting==[(old,True)] and not delayed and new['raw'][0]['edition_order_id']==2


@pytest.fixture
def client(state,monkeypatch):
    import files_upload_api
    def actor(request,required_page):
        assert required_page=='Orders'
        if request.headers.get('fixture-user')!='yes':raise PermissionError('Sign in')
        return state
    monkeypatch.setattr(files_upload_api,'_request_user',actor)
    monkeypatch.setattr(feed,'build',lambda *_:saved([1,2]))
    return TestClient(Starlette(routes=[Route('/feed',feed.feed,methods=['POST'])]))


def test_feed_authenticates_even_for_unchanged_client_revisions(client):
    body=dict(query='',known={})
    assert client.post('/feed',json=body).status_code==403
    first=client.post('/feed',json=body,headers={'fixture-user':'yes'})
    assert first.status_code==200 and 'no-store' in first.headers['cache-control']
    body['known']={r['id']:r['revision'] for r in first.json()['rows']}
    assert client.post('/feed',json=body).status_code==403
    assert client.post('/feed',json=body,headers={'fixture-user':'yes'}).json()['rows']==[]


@pytest.mark.parametrize('body',[dict(query='',known={},action='send'),dict(query='x'*201,known={}),dict(query='',known={'allocation:1':'wrong'}),dict(query='',known=[]),dict(query='',known={'../outside':'a'*64})])
def test_feed_cannot_accept_job_instructions_or_invalid_revisions(client,body):
    assert client.post('/feed',json=body,headers={'fixture-user':'yes'}).status_code==409


def test_new_row_selection_adopts_server_cached_rows_without_whole_page_reload(screen,monkeypatch):
    session,calls,view,reply=screen
    actor=dict(id='staff');initial=[dict(edition_order_id=1)]
    grid.render(initial,[{}],grid_key='selection',selected=[],actor=actor,statuses={})
    scope=view['feed']['scope'];fresh=saved([2,1])
    monkeypatch.setattr(feed,'recalled',lambda *_:deepcopy(fresh))
    reply['event']=dict(event='new-selection',type='select',ids=['allocation:2'],scope=scope,version=fresh['version'])
    grid.render(initial,[{}],grid_key='selection',selected=[],actor=actor,statuses={})
    assert session['orders-grid-selected-ids']==['allocation:2']
    assert [r['edition_order_id'] for r in session['orders_allocation_rows']]==[2,1]
    assert calls==[('rerun',{'scope':'fragment'})]
    grid.render(initial,[{}],grid_key='selection',selected=[],actor=actor,statuses={})
    assert [r['id'] for r in view['rows']]==['allocation:2','allocation:1']
    assert view['selected']==['allocation:2']


def test_old_search_response_cannot_replace_current_view(screen,monkeypatch):
    session,calls,view,reply=screen
    monkeypatch.setattr(feed,'recalled',lambda *_:pytest.fail('Wrong scope must not read cached customer rows'))
    reply['event']=dict(event='old-search',type='feed',scope='old',version='a'*64)
    grid.render([dict(edition_order_id=1)],[{}],grid_key='selection',selected=[],actor=dict(id='staff'),statuses={})
    assert not calls and 'orders-grid-feed' not in session


def test_component_feed_disables_legacy_whole_page_live_reload(monkeypatch):
    import orders_page
    monkeypatch.setattr(orders_page,'st',SimpleNamespace(session_state={'orders-grid-feed-active':True},fragment=lambda **_:pytest.fail('No parallel whole-page marker loop')))
    orders_page._render_orders_supabase_live_refresh()


def test_presenter_build_is_batched_read_only_and_does_not_contact_providers(state,monkeypatch):
    import order_allocator,orders_display_reads,psd_directory,requests
    reads=[]
    rows=[dict(edition_order_id=1,shopify_order_id='1',shopify_line_item_id='10',shopify_product_id='100',
               order='#SC1',product='Synthetic print',edition_number=1,edition_total=100,variant='Black / L')]
    def mirror(**kw):reads.append(('mirror',kw));return dict(rows=rows)
    monkeypatch.setattr(order_allocator,'load_hybrid_orders_snapshot',mirror)
    monkeypatch.setattr(psd_directory,'page_directory',lambda:{})
    monkeypatch.setattr(orders_display_reads,'download_links',lambda r:(reads.append(('jpg',len(r))) or {}))
    monkeypatch.setattr(grid,'batch_status',lambda ids:(reads.append(('status',ids)) or {}))
    monkeypatch.setattr(requests.sessions.Session,'request',lambda *_a,**_k:pytest.fail('The row feed cannot contact a provider'))
    result=feed.build(state,'#SC1')
    assert result['rows'][0]['id']=='allocation:1'
    assert result['rows'][0]['cells']['edition']=='#001/100'
    assert reads==[('mirror',dict(limit=75,search='#SC1')),('jpg',1),('status',['1'])]
