import pytest

@pytest.fixture(autouse=True)
def synchronous_display_controls(monkeypatch):
    monkeypatch.setattr('upload_companion_page.visible', lambda: True)
    # Exercise controls deterministically; background cache races have separate tests.
    monkeypatch.setattr('upload_companion_page.read_display', lambda name, loader: loader())

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
    monkeypatch.setattr(morning_design_queue, 'list_jobs', lambda **kwargs: [])
    monkeypatch.setattr(product_upload_staff_queue, 'desktop_online', lambda: True)
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
    monkeypatch.setattr(product_upload_staff_queue, 'list_jobs', lambda **kwargs: {'online': True, 'jobs': []})
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


def test_companion_reset_is_click_only_and_only_for_failed_uploads(monkeypatch):
    failed = dict(id='failed-fixture', title='Fixture art', stage=7, label='Needs attention',
                  percent=0, detail='Mockup failed', updated_at='2026-11-18T00:00:00+00:00')
    calls = []
    def restart(key, user, stamp):
        calls.append((key, user['id'], stamp))
        failed.update(stage=0, label='Restart requested')
    monkeypatch.setattr(product_upload_staff_queue, 'settings', lambda: {'enabled': True})
    monkeypatch.setattr(product_upload_staff_queue, 'list_jobs', lambda **kwargs: {'online': True, 'jobs': [dict(failed)]})
    monkeypatch.setattr(product_upload_staff_queue, 'restart', restart)
    app = AppTest.from_string("from upload_companion_page import render_queue\nrender_queue({'id':'admin'})").run()
    assert not app.exception and not calls
    app.run()
    assert not calls
    app.button(key='cq-upload-reset-failed-fixture').click().run()
    assert not app.exception
    assert calls == [('failed-fixture', 'admin', '2026-11-18T00:00:00+00:00')]
    assert not any(b.key == 'cq-upload-reset-failed-fixture' for b in app.button)


def test_restart_route_requires_same_origin_and_authenticated_request(monkeypatch):
    import files_upload_api
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    queue = product_upload_staff_queue
    calls = []
    monkeypatch.setattr(files_upload_api, '_request_user', lambda request, **kw: {'id': 'staff'})
    monkeypatch.setattr(queue, 'restart', lambda *args: calls.append(args) or {'stage': 0})
    client = TestClient(Starlette(routes=[Route(path, endpoint, methods=methods) for path, endpoint, methods in queue.ROUTES]))
    path = '/api/staff-product-uploads/restart'
    body = {'id': 'fixture', 'updated_at': 'now'}
    assert client.post(path, json=body).status_code == 403
    assert client.post(path, json=body, headers={'Origin': 'https://elsewhere.test'}).status_code == 403
    assert not calls
    assert client.post(path, json=body, headers={'Origin': 'http://testserver'}).json()['job']['stage'] == 0
    assert len(calls) == 1


def test_only_selected_companion_tab_runs(monkeypatch):
    import os_accounts
    import upload_companion_page as page
    calls = []
    monkeypatch.setattr(os_accounts, 'can_access_page', lambda *args: True)
    monkeypatch.setattr(page, 'render_design_queue', lambda user: calls.append('design'))
    monkeypatch.setattr(page, 'render_queue', lambda user: calls.append('upload'))
    monkeypatch.setattr(page, 'render_ad_queue', lambda: calls.append('ads'))
    app = AppTest.from_string("from upload_companion_page import render_page\nrender_page({'id': 'fixture'})").run()
    assert not app.exception
    assert calls == ['design']
    for label, expected in [('Upload queue', 'upload'), ('Ads queue', 'ads'), ('Design queue', 'design')]:
        calls.clear()
        app.session_state['companion-queue-tabs'] = label
        app.run()
        assert not app.exception
        assert calls == [expected]


def test_display_paths_request_read_only_jobs(monkeypatch):
    calls = []
    def designs(*, display_only=False):
        calls.append(('design', display_only))
        return []
    def uploads(*, display_only=False):
        calls.append(('upload', display_only))
        return {'online': True, 'jobs': []}
    monkeypatch.setattr(morning_design_queue, 'list_jobs', designs)
    monkeypatch.setattr(product_upload_staff_queue, 'list_jobs', uploads)
    monkeypatch.setattr(product_upload_staff_queue, 'desktop_online', lambda: True)
    monkeypatch.setattr(morning_design_queue, 'settings', lambda: {'enabled': True})
    monkeypatch.setattr(product_upload_staff_queue, 'settings', lambda: {'enabled': True})
    app = AppTest.from_string('from upload_companion_page import render_design_queue, render_queue\nrender_design_queue()\nrender_queue()').run()
    assert not app.exception
    assert calls == [('design', True), ('upload', True)]


def test_closed_ad_composer_does_not_load_catalog(monkeypatch):
    import ads_companion_quick_add as composer
    calls = []
    def catalog():
        calls.append('catalog')
        return {'products': []}
    monkeypatch.setattr(composer, 'catalog', catalog)
    app = AppTest.from_string('from ads_companion_quick_add import render\nrender()').run()
    assert not app.exception and not calls
    app.session_state['cq-ad-composer'] = True
    app.run()
    assert not app.exception and calls == ['catalog']
    app.session_state['cq-ad-composer'] = False
    app.run()
    assert not app.exception and calls == ['catalog']
