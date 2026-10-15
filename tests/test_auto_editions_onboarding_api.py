import asyncio
import hashlib
import json
from unittest.mock import patch
import pytest
import auto_editions_onboarding_api as onboarding
import auto_editions_api as api
import files_upload_api as files
from tests.test_auto_editions_api import request, ADMIN, VA
from tests.test_auto_editions_onboarding import setup_queue
from tests.test_auto_editions_jobs import database


def host_request(token,origin=''):
    req=request('POST',origin=origin)
    req.scope['headers'].append((b'x-sports-cave-preparation-host',token.encode()))
    return req


def test_staff_and_cross_origin_cannot_register_host_or_claim():
    async def check():
        with patch.object(api.runtime,'enabled',return_value=True),patch.object(files,'_request_user',return_value=VA):
            assert (await onboarding.register_host(request('POST',body={'confirm_preparation_host':True}))).status_code==403
            assert (await onboarding.claim(request('POST'))).status_code==403
        with patch.object(api.runtime,'enabled',return_value=True),patch.object(files,'_request_user',return_value=ADMIN):
            for origin in ('','https://untrusted.test'):
                assert (await onboarding.register_host(request('POST',origin=origin))).status_code==403
    asyncio.run(check())


def test_host_capability_is_hashed_revocable_and_session_bound(database):
    queue,sql=setup_queue(database)
    admin={**ADMIN,'session_version':7}
    async def check():
        with patch.object(onboarding,'queue',return_value=queue),patch.object(api.runtime,'enabled',return_value=True),patch.object(files,'_request_user',return_value=admin),patch.object(files.os_accounts.DEFAULT_STORE,'get_user',return_value=admin):
            response=await onboarding.register_host(request('POST',body={'confirm_preparation_host':True}))
            assert response.status_code==200
            token=json.loads(response.body)['token'];assert len(token)==43
            sql.execute('SELECT * FROM auto_edition_preparation_hosts');row=sql.fetchone()
            assert row['token_hash']==hashlib.sha256(token.encode()).hexdigest()
            # PostgreSQL timestamps are datetime values; inspect their printable
            # form too when checking that only the capability hash was stored.
            assert token not in json.dumps(row, default=str)
            assert (await onboarding.preparation_actor(host_request(token)))['id']=='admin'
            with pytest.raises(PermissionError):await onboarding.preparation_actor(host_request(token,'https://os.test'))
            with patch.object(files.os_accounts.DEFAULT_STORE,'get_user',return_value={**admin,'session_version':8}):
                with pytest.raises(PermissionError):await onboarding.preparation_actor(host_request(token))
            assert (await onboarding.revoke_hosts(request('POST'))).status_code==200
            with pytest.raises(PermissionError):await onboarding.preparation_actor(host_request(token))
            assert (await onboarding.claim(host_request(token))).status_code==403
    asyncio.run(check())


def test_legacy_host_is_bound_to_existing_server_signing_configuration():
    import sc_auth
    legacy={**ADMIN,'id':'legacy-master-admin'}
    with patch.object(sc_auth,'_signing_key',return_value=b'synthetic-first'):
        row={'actor_id':legacy['id'],'session_version':onboarding.host_session_version(legacy)}
        assert onboarding.host_account(row)['id']==legacy['id']
    with patch.object(sc_auth,'_signing_key',return_value=b'synthetic-rotated'):
        with pytest.raises(PermissionError):onboarding.host_account(row)
