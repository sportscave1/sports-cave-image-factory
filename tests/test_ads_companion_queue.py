"""Offline New Ads queue contracts, using disposable PostgreSQL and fake providers."""
from copy import deepcopy
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

import ads_page
import ads_companion_queue as queue
import design_publish_ad as companion
import os_accounts
import product_upload_staff_queue as uploads
from test_product_upload_staff_queue import database, store


ROW = dict(shopify_product_id='123', product_title='Collector Tribute',
           product_handle='collector-tribute', collections=['Baseball Wall Art'])
URL = 'https://sportscave.com.au/products/collector-tribute'
USER = {'id': 'fixture', 'role': 'admin'}


@pytest.fixture(autouse=True)
def no_provider_network(monkeypatch):
    import requests
    def blocked(*args, **kwargs):
        raise AssertionError('Live provider calls are forbidden in queue tests')
    monkeypatch.setattr(requests.sessions.Session, 'request', blocked)


def brief():
    return ads_page.build_ads_result_record('Collector Tribute', 'Baseball', 'USA',
        'Instant Experience', product_id='123', product_url=URL, variation_token='fixed-fixture')


@pytest.fixture
def queued_store(store, monkeypatch):
    monkeypatch.setattr(companion, 'connect', store)
    monkeypatch.setattr(os_accounts, 'can_access_page', lambda *_: True)
    monkeypatch.setattr(os_accounts.DEFAULT_STORE, 'get_user', lambda _: USER)
    return store


def test_durable_deduplicated_brief_and_shared_pause(queued_store, monkeypatch):
    result = brief()
    first = queue.enqueue(USER, result, {'row': ROW})
    assert queue.enqueue(USER, deepcopy(result), {'row': ROW}) == first
    assert companion.dashboard()['jobs'][0]['title'] == ROW['product_title']
    with queued_store() as conn, conn.cursor() as cur:
        cur.execute('SELECT count(*) AS n FROM product_upload_staff_jobs')
        assert cur.fetchone()['n'] == 0  # No fake upload or re-publication.
        cur.execute('SELECT value FROM app_settings WHERE key=%s', (companion.PREFIX + first['id'],))
        assert cur.fetchone()['value']['result'] == result
    token = uploads.pair({'id': 'desktop'})
    companion.settings(False)
    assert companion.tick(token, {}) == {}
    assert companion.dashboard()['jobs'][0]['label'] == 'Ready · queue paused'
    monkeypatch.setattr(queue, 'prepare', lambda value: dict(stage='opening', prompt='brief'))
    companion.settings(True)
    job = companion.tick(token, {})['job']
    assert job['id'] == first['id'] and job['project'] == companion.PROJECT
    assert queue.enqueue(USER, result, {'row': ROW})['id'] == first['id']
    result['country'] = 'Canada'
    assert queue.enqueue(USER, result, {'row': ROW})['id'] != first['id']


def test_standalone_job_uses_existing_completion_and_failure_path(queued_store, monkeypatch):
    import meta_posting_jobs
    result = brief()
    first = queue.enqueue(USER, result, {'row': ROW})
    token = uploads.pair({'id': 'desktop'})
    monkeypatch.setattr(queue, 'prepare', lambda value: dict(stage='opening', prompt='brief'))
    calls = []
    request = SimpleNamespace(submission_id=companion._posting_id(first['id']))
    monkeypatch.setattr(companion, '_post_request', lambda value: request)
    def submit(value):
        calls.append(value)
        return value.submission_id
    monkeypatch.setattr(meta_posting_jobs, 'JOBS', SimpleNamespace(submit=submit,
        snapshot=lambda _: dict(status='COMPLETE')))
    monkeypatch.setattr(meta_posting_jobs, 'confirmed_ads', lambda _: (3, 3))
    companion.tick(token, {})
    companion.tick(token, {'id': first['id'], 'state': 'submitted'})
    companion.tick(token, {})
    assert len(calls) == 1
    assert companion.dashboard()['jobs'][0]['stage'] == 'complete'
    assert not queue.enqueue(USER, result, {'row': ROW})['active']

    other = brief()
    other['country'] = 'Canada'
    second = queue.enqueue(USER, other, {'row': ROW})
    companion.tick(token, {})
    companion.tick(token, {'id': second['id'], 'state': 'blocked', 'reason': 'Reference unavailable'})
    assert companion.dashboard()['jobs'][0]['detail'] == 'Reference unavailable'


def test_queue_rejects_wrong_format_identity_and_permission(queued_store, monkeypatch):
    for changes, row in [({'campaign_type': 'Carousel'}, ROW), ({'platform': 'google'}, ROW),
                          ({'product_url': URL + '-other'}, ROW), ({}, {})]:
        with pytest.raises(ValueError):
            queue.enqueue(USER, {**brief(), **changes}, {'row': row})
    monkeypatch.setattr(os_accounts, 'can_access_page', lambda *_: False)
    with pytest.raises(ValueError, match='access'):
        queue.enqueue(USER, brief(), {'row': ROW})


def test_new_ads_and_design_jobs_share_one_active_slot(queued_store, monkeypatch):
    design = uploads.enqueue(USER, {'id': 'id:fixture', 'rev': 'one'}, 'Design', 'Baseball', ad_country='USA')
    token = uploads.pair({'id': 'desktop'})
    uploads.desktop_tick(token)
    uploads.advance(design, 'desktop', 6, allowed=[1])
    first = queue.enqueue(USER, brief(), {'row': ROW})
    monkeypatch.setattr(companion, '_prepare', lambda *_: dict(stage='opening', prompt='brief'))
    assert companion.tick(token, {})['job']['id'] == str(design)
    assert companion.tick(token, {})['job']['id'] == str(design)
    assert len(companion.dashboard()['jobs']) == 2
    companion.tick(token, {'id': str(design), 'state': 'blocked', 'reason': 'Fixture blocked'})
    assert companion.tick(token, {})['job']['id'] == first['id']
    monkeypatch.setattr(os_accounts.DEFAULT_STORE, 'get_user', lambda _: None)
    companion.tick(token, {})
    jobs = {job['title']: job for job in companion.dashboard()['jobs']}
    assert jobs['Collector Tribute']['stage'] == 'failed'
    assert 'access' in jobs['Collector Tribute']['detail']


def test_prepare_verifies_existing_product_and_preserves_manual_brief(monkeypatch):
    import ads_product_catalog
    import product_upload_mapping
    import product_upload_services
    import shopify_sync

    product = dict(shopify_product_id='gid://shopify/Product/123', handle='collector-tribute',
                   status='ACTIVE', online_store_url=URL)
    black = dict(original_black_image_url='https://cdn.shopify.com/black.webp',
                 variant_id='456', variant_url=URL + '?variant=456')
    monkeypatch.setattr(product_upload_mapping, 'read_edition', lambda *_: {'id': 'edition'})
    monkeypatch.setattr(shopify_sync, 'fetch_product_by_shopify_id', lambda *_: product)
    monkeypatch.setattr(ads_product_catalog, 'verify_live_black_frame_variant', lambda *_: black)
    folders = []
    import dropbox_integration
    api = SimpleNamespace(join_upload_path=dropbox_integration.join_upload_path,
        normalize_dropbox_path=dropbox_integration.normalize_dropbox_path,
        sanitize_path_component=dropbox_integration.sanitize_path_component,
        path_is_within_root=dropbox_integration.path_is_within_root,
        ensure_folder_path=lambda *args, **kwargs: folders.append(args[1]))
    monkeypatch.setattr(product_upload_services, 'Dropbox', lambda: SimpleNamespace(
        context={'root_path': '/fixture'}, api=api, token='fixture'))
    value = dict(result=brief(), product_gid='gid://shopify/Product/123', handle='collector-tribute', upload='job')
    prepared = queue.prepare(value)
    assert value['result']['master_prompt'] in prepared['prompt']
    assert black['original_black_image_url'] in prepared['prompt']
    assert all(name in prepared['prompt'] for name in ('ad_copy.csv', *companion.COVERS.values()))
    assert len(folders) == 1
    black['original_black_image_url'] = ''
    with pytest.raises(ValueError, match='Black-frame'):
        queue.prepare(value)
    product['status'] = 'DRAFT'
    with pytest.raises(ValueError, match='active'):
        queue.prepare(value)
    monkeypatch.setattr(product_upload_mapping, 'read_edition', lambda *_: None)
    with pytest.raises(ValueError, match='Edition Ops'):
        queue.prepare(value)
    assert len(folders) == 1


def test_queue_only_button_preserves_validation_and_automation(monkeypatch):
    calls = []
    monkeypatch.setattr(queue, 'enqueue', lambda user, result, selection: calls.append(deepcopy(result)) or
                        dict(id='fixture', active=True))
    monkeypatch.setattr(ads_page, 'load_edition_ops_product_rows', lambda: [ROW])
    monkeypatch.setattr(ads_page, 'render_supported_result', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ads_page, 'record_ad_prompt_generated', lambda *_args, **_kwargs: None)
    app = AppTest.from_string('import ads_page; ads_page.render_page()')
    app.session_state['sports_cave_current_user'] = USER
    app.run()
    assert not app.exception
    assert 'Submit' not in [button.label for button in app.button]
    assert 'Campaign Moment (Optional)' not in [item.label for item in app.expander]
    app.button(key='ads-add-to-queue').click().run()
    assert not calls  # Incomplete inputs never queue.
    for label, value in [('Product name', 'Collector Tribute'), ('Category', 'Baseball'), ('Country', 'USA')]:
        next(widget for widget in app.selectbox if widget.label == label).select(value).run()
    next(widget for widget in app.text_input if widget.label == 'Product page URL *').set_value(URL).run()
    assert not calls and not app.exception
    app.button(key='ads-add-to-queue').click().run()
    assert len(calls) == 1 and not app.exception
    assert calls[0] == app.session_state[ads_page._ads_result_state_key()]
    from ads_generation_review import RULES
    assert RULES in calls[0]['master_prompt']
    assert any('Added to the companion' in item.value for item in app.success)
    next(widget for widget in app.selectbox if widget.label == 'Campaign type').select('Carousel').run()
    assert app.button(key='ads-add-to-queue').disabled


def test_dependency_outage_deadline_survives_poll_writes_and_releases_queue(queued_store, monkeypatch):
    import time
    first = queue.enqueue(USER, brief(), {'row': ROW})
    second = queue.enqueue(USER, {**brief(), 'country': 'Canada'}, {'row': ROW})
    token = uploads.pair({'id': 'desktop'})
    clock = [time.time()]
    monkeypatch.setattr(companion.time, 'time', lambda: clock[0])
    def offline(value):
        raise RuntimeError('synthetic dependency outage')
    monkeypatch.setattr(queue, 'prepare', offline)
    assert companion.tick(token, {}) == {'busy': True}
    clock[0] += 3600
    assert companion.tick(token, {}) == {'busy': True}
    clock[0] += 3601
    assert companion.tick(token, {}) == {}
    rows = {row['id']: row for row in companion.dashboard()['jobs']}
    assert rows[first['id']]['stage'] == 'failed'
    monkeypatch.setattr(queue, 'prepare', lambda _: dict(stage='opening', prompt='brief'))
    assert companion.tick(token, {})['job']['id'] == second['id']
