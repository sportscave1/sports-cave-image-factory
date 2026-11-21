from copy import deepcopy
import json
from companion_status_payload import payload


def fixture():
    job = dict(id='job', title='Synthetic', stage=2, state='running', percent=45,
        label='Generating', detail='Keep this diagnostic', updated_at='v1', chat_url='https://chatgpt.com/c/fixture',
        estimated=True, can_cancel=True, can_play=False, can_defer=True, control_action='', posting_id='posting',
        targeting={'geo_locations': {'custom_locations': [{'name':'Unused header target'}]*1000}},
        country='USA', sport='NFL', file_path='/synthetic/output.psd', created_at='v0', prompt='not a display field')
    return dict(online=True, display_state='ready', checked_at=1,
        jobs=[dict(job, dispatch_id='dispatch', storefront='https://fixture.invalid/product',
                   restartable=False, cancellable=True, stalled=False, ad=dict(label='Posting', detail='Keep ad diagnostic', posting_id='posting'))],
        queues={name:dict(enabled=True, online=True, waiting=2, display=True, jobs=[job]) for name in ('upload','design','ads')})


def test_projection_preserves_display_controls_identity_order_and_diagnostics():
    source = fixture(); before = deepcopy(source); result = payload(source)
    assert source == before
    assert result['schema_version'] == 1
    assert result['checked_at'] == source['checked_at'] and result['display_state'] == 'ready'
    for name, queue in result['queues'].items():
        assert queue['waiting'] == 2 and queue['enabled']
        assert queue['jobs'][0] == {k:v for k,v in source['queues'][name]['jobs'][0].items()
            if k not in ('targeting','country','sport','file_path','created_at','prompt')}
    assert result['jobs'][0]['ad'] == source['jobs'][0]['ad']
    assert result['jobs'][0]['dispatch_id'] == 'dispatch'
    assert result['jobs'][0]['storefront'] == 'https://fixture.invalid/product'
    assert len(json.dumps(result)) < len(json.dumps(source))/10


def test_display_route_checks_auth_scope_and_freshness_before_304(monkeypatch):
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    import files_upload_api
    import product_upload_staff_queue as queue
    user = dict(id='admin-a', role='admin', session_version=1)
    value = fixture(); calls=[]
    def authenticate(*args, **kwargs):
        calls.append(user['id']); return user
    monkeypatch.setattr(files_upload_api, '_request_user', authenticate)
    monkeypatch.setattr(queue, '_header_display', lambda _:deepcopy(value))
    client = TestClient(Starlette(routes=[Route('/status', queue.status_route)]))
    first = client.get('/status?display=1'); assert first.status_code == 200
    tag = first.headers['etag']; headers={'If-None-Match':tag}
    same = client.get('/status?display=1', headers=headers)
    assert same.status_code == 304 and same.content == b'' and len(calls) == 2
    assert same.headers['cache-control'] == 'private, no-store'
    for field, changed in [('session_version',2), ('page_permissions',['Design Studio'])]:
        old=user.get(field); user[field]=changed
        assert client.get('/status?display=1', headers=headers).headers['etag'] != tag
        if old is None: user.pop(field)
        else: user[field]=old
    for key, changed in [('display_state','stale'), ('checked_at',2)]:
        old=value[key]; value[key]=changed
        assert client.get('/status?display=1', headers=headers).status_code == 200
        value[key]=old
    user['id']='staff-b'; user['role']='worker'
    assert client.get('/status?display=1', headers=headers).headers['etag'] != tag
    def deny(*args, **kwargs): raise PermissionError('Unavailable')
    monkeypatch.setattr(queue, 'requested_status', deny)
    assert client.get('/status?display=1&job_id=private', headers=headers).status_code == 403
    monkeypatch.setattr(files_upload_api, '_request_user', deny)
    assert client.get('/status?display=1', headers=headers).status_code == 403


def test_no_queues_are_added_to_staff_projection():
    assert 'queues' not in payload(dict(jobs=[], online=False, display_state='loading', checked_at=None))
