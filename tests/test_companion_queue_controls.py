from streamlit.testing.v1 import AppTest
import morning_design_queue
import product_upload_staff_queue


def test_play_pause_buttons_and_waiting_status(monkeypatch):
    state = {'enabled': True}
    changes = []
    def settings(enabled=None):
        if enabled is not None:
            state['enabled'] = enabled
            changes.append(enabled)
        return dict(state)
    monkeypatch.setattr(morning_design_queue, 'settings', settings)
    monkeypatch.setattr(morning_design_queue, 'list_jobs', lambda: [])
    monkeypatch.setattr(product_upload_staff_queue, 'list_jobs', lambda: {'online': True})
    app = AppTest.from_string('from upload_companion_page import render_design_queue\nrender_design_queue()').run()
    assert not app.exception
    assert app.button(key='cq-design-play').disabled
    app.button(key='cq-design-pause').click().run()
    assert not app.exception
    assert changes == [False]
    assert app.button(key='cq-design-pause').disabled
    assert not app.button(key='cq-design-play').disabled
    assert any('Queue paused. Press Play' in item.value for item in app.markdown)
    app.button(key='cq-design-play').click().run()
    assert not app.exception
    assert changes == [False, True]
    assert app.button(key='cq-design-play').disabled


def test_upload_play_pause_buttons_and_waiting_status(monkeypatch):
    state = {'enabled': True}
    changes = []
    def settings(enabled=None):
        if enabled is not None:
            state['enabled'] = enabled
            changes.append(enabled)
        return dict(state)
    monkeypatch.setattr(product_upload_staff_queue, 'settings', settings)
    monkeypatch.setattr(product_upload_staff_queue, 'list_jobs', lambda: {'online': True, 'jobs': []})
    app = AppTest.from_string('from upload_companion_page import render_queue\nrender_queue()').run()
    assert not app.exception
    assert app.button(key='cq-upload-play').disabled
    app.button(key='cq-upload-pause').click().run()
    assert not app.exception
    assert changes == [False]
    assert app.button(key='cq-upload-pause').disabled
    assert not app.button(key='cq-upload-play').disabled
    assert any('Queue paused. Press Play' in item.value for item in app.markdown)
    app.button(key='cq-upload-play').click().run()
    assert not app.exception
    assert changes == [False, True]
    assert app.button(key='cq-upload-play').disabled


def test_header_controls_require_admin_and_same_origin(monkeypatch):
    import files_upload_api
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient

    queue = product_upload_staff_queue
    client = TestClient(Starlette(routes=[
        Route(path, endpoint, methods=methods) for path, endpoint, methods in queue.ROUTES
    ]))
    user = {'id': 'fixture-user', 'role': 'worker', 'is_active': True}
    monkeypatch.setattr(files_upload_api, '_request_user', lambda request, **kwargs: user)
    monkeypatch.setattr(queue, 'list_jobs', lambda actor: {'jobs': [], 'online': False})
    monkeypatch.setattr(queue, 'header_queue_status', lambda: {'design': {'waiting': 4, 'enabled': True}})
    calls = []

    def set_enabled(name, enabled):
        calls.append((name, enabled))
        return {'enabled': enabled}

    monkeypatch.setattr(queue, 'settings', lambda enabled: set_enabled('upload', enabled))
    monkeypatch.setattr(morning_design_queue, 'settings', lambda enabled: set_enabled('design', enabled))
    path = '/api/staff-product-uploads'
    origin = {'Origin': 'http://testserver'}
    action = {'queue': 'design', 'enabled': False}
    assert 'queues' not in client.get(path + '/status').json()
    assert client.post(path + '/queue-control', json=action, headers=origin).status_code == 403
    user['role'] = 'admin'
    assert client.get(path + '/status').json()['queues']['design']['waiting'] == 4
    assert client.post(path + '/queue-control', json=action, headers={'Origin': 'https://elsewhere.test'}).status_code == 403
    assert client.post(path + '/queue-control', json={**action, 'enabled': 'false'}, headers=origin).status_code == 409
    assert not calls
    assert client.post(path + '/queue-control', json=action, headers=origin).json() == {'enabled': False}
    assert client.post(path + '/queue-control', json={'queue': 'upload', 'enabled': True}, headers=origin).json() == {'enabled': True}
    assert calls == [('design', False), ('upload', True)]
