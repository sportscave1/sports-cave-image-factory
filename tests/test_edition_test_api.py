"""Synthetic roles and identities; no database, Dropbox or production requests."""
import asyncio
import json
import threading
from types import SimpleNamespace
from unittest.mock import patch
import edition_test_api as api
import files_upload_api as files
from test_edition_test import context as fixture_context


def test_context_single_use_and_fresh_permission_revocation():
    actor = {'id': 'fixture', 'session_version': 1, 'role': 'admin'}
    record = SimpleNamespace(edition_test_actor=dict(actor), edition_test_claimed=False, access_token='TEST-ONLY')
    manager = SimpleNamespace(_lock=threading.RLock(), get=lambda *_: record)
    request = SimpleNamespace(query_params={'ticket': 'fixture'})
    ctx = fixture_context()
    metadata = {**ctx['metadata'], 'size': 10, 'name': 'fixture.psd'}
    with patch.object(files, 'NATIVE_TRANSFER_MANAGER', manager), patch.object(files, '_native_transfer_secret', return_value='TEST-ONLY'), patch.object(files.os_accounts.DEFAULT_STORE, 'get_user', return_value=actor), patch.object(files.os_accounts, 'can_access_page', return_value=True) as access, patch.object(api.case, 'confirmed_unit', return_value=ctx['unit']), patch.object(files.dropbox_integration, 'psd_open_metadata', return_value=metadata):
        assert asyncio.run(api.context(request)).status_code == 200
        assert asyncio.run(api.context(request)).status_code == 403
        request.query_params['verify'] = '1'
        assert asyncio.run(api.context(request)).status_code == 200
        access.return_value = False
        assert asyncio.run(api.context(request)).status_code == 403
        access.return_value = True
        actor['session_version'] = 2
        assert asyncio.run(api.context(request)).status_code == 403


def test_staff_and_inactive_admin_cannot_start_local_photoshop():
    request = SimpleNamespace(headers={'origin': 'https://os.test'})
    for actor in ({'id':'va','role':'worker'}, {'id':'owner','role':'admin','is_active':False}):
        with patch.object(files, '_same_origin', return_value=True), patch.object(files, '_request_user', return_value=actor), patch.object(api.case, 'confirmed_unit') as unit, patch.object(files, '_dropbox_context') as dropbox:
            assert asyncio.run(api.page(request)).status_code == 403
            assert asyncio.run(api.prepare(request)).status_code == 403
            unit.assert_not_called();dropbox.assert_not_called()


def test_preexisting_staff_pilot_grant_is_denied_before_asset_reads():
    actor={'id':'va','role':'worker','session_version':1}
    record=SimpleNamespace(edition_test_actor=actor,edition_test_claimed=False)
    manager=SimpleNamespace(_lock=threading.RLock(),get=lambda *_:record)
    request=SimpleNamespace(query_params={'ticket':'test'})
    with patch.object(files,'NATIVE_TRANSFER_MANAGER',manager),patch.object(files,'_native_transfer_secret',return_value='test'),patch.object(files.os_accounts.DEFAULT_STORE,'get_user',return_value=actor),patch.object(api.case,'confirmed_unit') as unit:
        assert asyncio.run(api.context(request)).status_code==403
        unit.assert_not_called()


def test_prepare_rejects_cross_origin_before_creating_grant():
    request = SimpleNamespace(headers={'origin': 'https://forged.test'})
    with patch.object(files, '_same_origin', return_value=False), patch.object(files, '_request_user') as user:
        response = asyncio.run(api.prepare(request))
        assert response.status_code == 403
        user.assert_not_called()


def test_unexpected_backend_errors_do_not_leak_secrets():
    request = SimpleNamespace(headers={'origin': 'https://os.test'})
    with patch.object(files, '_same_origin', return_value=True), patch.object(files, '_request_user', side_effect=RuntimeError('secret-access-token')):
        response = asyncio.run(api.prepare(request))
        assert response.status_code == 403
        assert b'secret-access-token' not in response.body
