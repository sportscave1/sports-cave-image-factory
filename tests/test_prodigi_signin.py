"""Synthetic sign-in incidents: no supplier authentication or live credentials."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import json

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient
import prodigi_signin as signin
import prodigi_preparation as prep
import prodigi_browser as browser
import prodigi_product_browser as product
import prodigi_dashboard_qa as qa
import shared_credentials as credentials
from test_auto_editions_jobs import database
from test_prodigi_preparation import store
from test_prodigi_product_browser import blank
from test_prodigi_upload_recovery import waiting, handoff, offline
from test_prodigi_dashboard_qa import fixture as qa_fixture
from test_prodigi_order_group import pair, batch_plan

USER = {'id': 'synthetic-owner', 'role': 'admin', 'is_active': True}
PAIR = 'p' * 43
KEY = 'prodigi_prepare:1'


def write(value):
    with prep.connect() as conn, conn.cursor() as cur:
        prep.save(cur, value)


def pause(plan, kind):
    return signin.pause(USER, PAIR, dict(key=plan['key'], token=plan['token'], kind=kind,
        login_url=signin.login_url(prep.read(1))))['wait']


def resume(wait):
    return signin.resume(USER, PAIR, {k: wait[k] for k in ('key', 'kind', 'id')})


def test_product_signin_wait_survives_expiry_and_retires_old_select_token(blank, monkeypatch):
    plan = product.claim()
    wait = pause(plan, 'product')
    assert signin.pending(USER, PAIR)['waits'] == [wait]
    assert pause(plan, 'product')['id'] == wait['id']  # lost acknowledgement
    with pytest.raises(ValueError):
        product.permit(plan['key'], plan['token'], plan['sha256'])
    value = prep.read(1)
    value['product_browser']['claimed_at'] = (datetime.now(timezone.utc)-timedelta(days=1)).isoformat()
    write(value)
    assert resume(wait) == {'status': 'resumed'}
    saved = prep.read(1)
    assert saved['status'] == product.WAITING and not saved.get('signin_wait') and not saved.get('product_browser')
    replacement = product.claim()
    assert replacement['token'] != plan['token'] and replacement['order_id'] == plan['order_id']
    with pytest.raises(PermissionError):
        product.permit(plan['key'], plan['token'], plan['sha256'])
    assert product.permit(replacement['key'], replacement['token'], replacement['sha256'])['permitted']
    assert not blank.writes


@pytest.mark.parametrize('changed', ['address', 'source', 'product'])
def test_changed_product_is_visible_for_review_and_does_not_get_a_new_permit(blank, changed):
    plan = product.claim()
    wait = pause(plan, 'product')
    if changed == 'address': blank.data['recipient'] = {'name': 'Changed synthetic recipient'}
    if changed == 'product': blank.data['items'][0]['sku'] = 'GLOBAL-CFP-A1'
    if changed == 'source':
        value = prep.read(1); value['snapshot']['number'] += 1; write(value)
    assert resume(wait) == {'status': 'review'}
    saved = prep.read(1)
    assert saved['signin_wait']['state'] == 'review' and saved['status'] == 'Needs review'
    assert signin.pending(USER, PAIR)['waits'] == []
    assert saved['product_browser']['token_hash'] == prep.digest(plan['token']) and not blank.writes


def test_artwork_wait_resumes_same_numbered_jpg_without_authorising_another_save(waiting):
    _, provider, plan, _ = waiting
    wait = pause(plan, 'artwork')
    with pytest.raises(ValueError): browser.permit(KEY, plan['token'], plan['sha256'])
    assert resume(wait) == {'status': 'resumed'}
    saved = prep.read(1)
    assert saved['status'] == browser.WAITING and saved['snapshot']['output']['sha256'] == plan['sha256']
    assert not saved.get('browser') and not provider.writes


def test_normal_recovery_cannot_retire_a_handoff_while_signin_is_pending(waiting):
    _, provider, plan, _ = waiting
    wait = pause(plan, 'artwork')
    import prodigi_upload_recovery as recovery
    assert recovery.recover(USER) == 0 and recovery.recover_one(KEY) is False
    assert browser._recover_ready_editor(USER, KEY, page_supported=True, processing_supported=True) is False
    assert prep.read(1)['signin_wait']['id'] == wait['id'] and not provider.writes


def test_consumed_select_uses_readback_instead_of_retiring_the_permit(blank, monkeypatch):
    monkeypatch.setattr(prep, 'require_user', lambda _: None)
    plan = product.claim(); product.permit(plan['key'], plan['token'], plan['sha256'])
    wait = pause(plan, 'product')
    assert wait['mode'] == 'readback'
    assert resume(wait) == {'status': 'review'}
    saved = prep.read(1)
    assert saved['product_browser']['started'] is True and not saved.get('signin_wait')
    assert product.claim() is None and not blank.writes


@pytest.mark.parametrize('consumed', [False, True])
def test_qa_signin_rechecks_saved_artwork_and_shipping_before_fresh_full_qa(store, monkeypatch, consumed):
    value, snap, provider, _ = qa_fixture()
    monkeypatch.setattr(browser, 'context', lambda _: (provider, lambda _: snap, None, False))
    write(value)
    plan = qa.claim(exact_item_supported=True)
    if consumed:
        value = prep.read(1)
        value['dashboard_qa'].update(started=True, shipping={'target': 'standard'})
        write(value)
    wait = pause(plan, 'qa')
    if not consumed:
        with pytest.raises(ValueError): qa.permit(KEY, plan['token'], {})
    assert resume(wait) == {'status': 'resumed'}
    saved = prep.read(1)
    assert saved['browser']['verified'] and saved['status'] == qa.WAITING
    assert not saved.get('dashboard_qa') and not saved.get('signin_wait') and not provider.writes
    assert qa.claim(exact_item_supported=True)['token'] != plan['token']


def test_consumed_qa_with_unconfirmed_shipping_is_held_for_visible_review(store, monkeypatch):
    value, snap, provider, _ = qa_fixture()
    monkeypatch.setattr(browser, 'context', lambda _: (provider, lambda _: snap, None, False))
    write(value); plan = qa.claim(exact_item_supported=True)
    value = prep.read(1); value['dashboard_qa'].update(started=True, shipping={'target': 'express'}); write(value)
    wait = pause(plan, 'qa')
    assert resume(wait) == {'status': 'review'}
    assert prep.read(1)['dashboard_qa']['started'] and not provider.writes


@pytest.mark.parametrize('changed_sibling', [False, True])
def test_grouped_signin_retires_all_unused_qa_tokens_atomically_or_preserves_all_for_review(pair, monkeypatch, changed_sibling):
    plan, provider, _ = batch_plan(pair, monkeypatch)
    assert plan and len(plan['items']) == 2
    wait = pause(plan, 'qa')
    before = [prep.read(aid)['dashboard_qa']['token_hash'] for aid in (1, 2)]
    if changed_sibling: provider.data['items'][1]['quantity'] = 2
    assert resume(wait)['status'] == ('review' if changed_sibling else 'resumed')
    for aid in (1, 2):
        saved = prep.read(aid)
        if changed_sibling:
            assert saved['dashboard_qa']['token_hash'] == before[aid-1]
        else:
            assert saved['status'] == qa.WAITING and not saved.get('dashboard_qa') and saved['browser']['verified']
    assert not provider.submits


def test_saved_credentials_are_fresh_permission_checked_one_shot_and_never_persisted(blank, monkeypatch, caplog):
    plan = product.claim(); wait = pause(plan, 'product')
    current = dict(USER); reads = []; audits = []
    monkeypatch.setattr('os_accounts.DEFAULT_STORE', SimpleNamespace(get_user=lambda uid: (reads.append(uid), current)[1]))
    monkeypatch.setattr(credentials, 'record_credential_audit', lambda *args, **kw: audits.append((args, kw)))
    monkeypatch.setenv('PRODIGI_USERNAME', signin.EMAIL)
    monkeypatch.setenv('PRODIGI_PASSWORD', 'synthetic-password-only')
    data = {**{k: wait[k] for k in ('key', 'kind', 'id')}, 'login_url': wait['login_url']}
    result = signin.credentials(USER, PAIR, data)
    assert result == dict(available=True, username=signin.EMAIL, password='synthetic-password-only')
    assert reads == [USER['id'], USER['id']] and len(audits) == 2
    assert signin.pending(USER, PAIR)['automatic'] is False
    assert signin.credentials(USER, PAIR, data)['available'] is False
    current.update(role='staff', page_permissions=[])
    with pytest.raises(credentials.CredentialAccessDenied): signin.credentials(USER, PAIR, data)
    with prep.connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT value FROM app_settings'); records = json.dumps(cur.fetchall())
    for output in (records, repr(audits), caplog.text, json.dumps(signin.pending(USER, PAIR))):
        assert 'synthetic-password-only' not in output
    assert not blank.writes


@pytest.mark.parametrize('case', ['missing', 'wrong-account'])
def test_missing_or_different_saved_credentials_offer_manual_signin_without_a_retry_loop(blank, monkeypatch, case):
    wait = pause(product.claim(), 'product')
    monkeypatch.setattr('os_accounts.DEFAULT_STORE', SimpleNamespace(get_user=lambda _: USER))
    monkeypatch.setattr(credentials, 'record_credential_audit', lambda *a, **kw: None)
    monkeypatch.setenv('PRODIGI_USERNAME', signin.EMAIL if case == 'missing' else 'other@example.invalid')
    monkeypatch.setenv('PRODIGI_PASSWORD', '' if case == 'missing' else 'synthetic-password-only')
    assert signin.credentials(USER, PAIR, {**{k: wait[k] for k in ('key', 'kind', 'id')}, 'login_url': wait['login_url']})['available'] is False
    assert signin.pending(USER, PAIR)['automatic'] is False and not blank.writes


def test_wait_and_credential_destination_are_pinned_to_owner_pairing_and_exact_order(blank, monkeypatch):
    plan = product.claim(); wait = pause(plan, 'product')
    for target in [wait['login_url']+'&redirect=%2Forders%2Fother%2Fdetail',
                   wait['login_url'].replace('dashboard.prodigi.com', 'evil.example'), wait['login_url']+'#x',
                   wait['login_url'].replace('redirect=', 'next=')]:
        with pytest.raises(ValueError): signin.pause(USER, PAIR, dict(key=plan['key'], kind='product', token=plan['token'], login_url=target))
    with pytest.raises(PermissionError): signin.resume(USER, 'q'*43, {k: wait[k] for k in ('key', 'kind', 'id')})
    with pytest.raises(PermissionError): signin.resume({'id': 'other'}, PAIR, {k: wait[k] for k in ('key', 'kind', 'id')})
    assert signin.pending(USER, 'q'*43)['waits'] == []
    assert not blank.writes


def test_retired_wait_cannot_mutate_a_new_handoff_or_submission(blank):
    wait = pause(product.claim(), 'product')
    value = prep.read(1); value['product_browser']['token_hash'] = prep.digest('new-token'); value['submission'] = {'status': 'submitted'}; write(value)
    assert resume(wait) == {'status': 'retired'}
    saved = prep.read(1)
    assert saved['product_browser']['token_hash'] == prep.digest('new-token') and saved['submission'] and not saved.get('signin_wait')


def test_signin_api_rejects_unpaired_oversized_and_extra_fields_without_echoing_secrets(monkeypatch):
    import prodigi_preparation_api as api
    monkeypatch.setattr(api, 'desktop', lambda _: USER)
    client = TestClient(Starlette(routes=[Route('/signin', signin.endpoint, methods=['POST'])]))
    assert client.post('/signin', json={'action': 'pending'}).status_code == 403
    headers = {'Authorization': 'Bearer '+PAIR}
    for body in [{'action': 'pending', 'password': 'synthetic-password-only'}, {'action': ['pending']}, ['pending']]:
        response = client.post('/signin', json=body, headers=headers)
        assert response.status_code in (409, 503) and 'synthetic-password-only' not in response.text
        assert 'no-store' in response.headers['cache-control']
    assert client.post('/signin', content=b'x'*2049, headers=headers).status_code == 409


def test_signin_alert_is_visible_in_order_controls_without_reset_or_secret_values():
    from orders_prodigi_grid import action_state
    result = action_state({'order_id': '99', 'status': 'Browser uploading', 'signin_wait': {'state': 'waiting'}})
    assert result['label'] == 'Sign in to Prodigi' and result['action'] == ''
    assert result['url'] == 'https://dashboard.prodigi.com/orders/99/detail' and 'resume automatically' in result['detail']
    assert action_state({'order_id': '99', 'signin_wait': {'state': 'waiting'},
                         '_inbox': {'blocking': True, 'paused': True}})['label'] == 'Paused customer request'
