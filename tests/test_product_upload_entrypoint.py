"""Offline real-Streamlit startup regression; never launch the deployment server."""
from pathlib import Path
import os
import socket
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('mode', ['legacy', 'allowed', 'outputs', 'missing', 'expired', 'denied', 'recover', 'recover-map', 'retired-label', 'retired-key', 'retired-denied'])
def test_full_main_routes_product_upload_with_session_namespace(mode, tmp_path, monkeypatch, caplog):
    import dotenv
    from streamlit.testing.v1 import AppTest

    def blocked(*args, **kwargs):
        raise AssertionError('Network is forbidden in entrypoint regression')

    socket_connect = socket.socket.connect
    def local_only(sock, address):
        # Windows implements asyncio's self-pipe with a loopback socket pair.
        if isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1'):
            return socket_connect(sock, address)
        return blocked()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(dotenv, 'load_dotenv', lambda *a, **k: False)
    monkeypatch.setattr(socket.socket, 'connect', local_only)
    monkeypatch.setattr(socket, 'create_connection', blocked)
    # No inherited provider settings, credentials or source-tree .env fallback.
    with patch.dict(os.environ, {'PATH': os.environ.get('PATH', ''),
                                'SYSTEMROOT': os.environ.get('SYSTEMROOT', ''),
                                'USERPROFILE': str(tmp_path),
                                'TEMP': str(tmp_path), 'TMP': str(tmp_path),
                                'SPORTS_CAVE_TEMP_DIR': str(tmp_path)}, clear=True):
        test = AppTest.from_file(str(ROOT / 'tests/fixtures/product_upload_entrypoint.py'))
        test.session_state['test_mode'] = mode
        test.session_state['test_root'] = str(tmp_path)
        test.run(timeout=45)
    if mode == 'legacy':
        assert "module '__main__' has no attribute 'current_os_user'" in caplog.text
        assert test.error
        return
    assert not test.exception, [e.message for e in test.exception]
    assert not test.error, [e.value for e in test.error]
    if mode in ('missing', 'expired'):
        assert any(b.label == 'Sign in' for b in test.button)
        assert not test.get('component_instance')
    elif mode in ('denied', 'retired-denied'):
        assert any(t.value == 'Access not approved' for t in test.title)
    else:
        assert test.get('component_instance'), 'Product Upload component must render'
        if mode in ('recover','recover-map'):
            import json
            payload=json.loads(test.get('component_instance')[0].proto.json_args)
            assert payload['id']=='12345678-1234-4234-9234-123456789012' and payload['mode']=='DRAFT'
            if mode=='recover-map':assert test.query_params['upload']==['12345678-1234-4234-9234-123456789012']
        if mode == 'outputs':
            import json
            payloads = [json.loads(c.proto.json_args) for c in test.get('component_instance')]
            assert not any(p.get('section') == 'handoff' for p in payloads), 'Unsaved outputs must not mount the final component'
            gallery = next(p for p in payloads if p.get('mode') == 'gallery')
            assert len(gallery['items']) == 5
            assert all(i['preview'].startswith('data:image/webp;base64,') for i in gallery['items'])
            assert any(p.get('mode') == 'actions' and p.get('prompt') for p in payloads)
            from product_upload_lifestyle import AUTOMATIC_START, FINISHED_MOCKUPS
            copied = next(p['prompt'] for p in payloads if p.get('mode') == 'actions')
            assert copied.startswith(AUTOMATIC_START + '\n\n')
            assert copied.startswith(AUTOMATIC_START + '\n\n' + FINISHED_MOCKUPS + '\n\n')
            assert copied.count(FINISHED_MOCKUPS) == 4
            assert copied.count('AUTOMATIC START —') == 1
            assert copied.count('END AUTOMATIC START') == 1
            assert 'Generate each COMPLETE mockup in one image-generation call' in copied
            assert 'not guaranteed pixel-identical reproduction' in copied
            assert 'deterministic image compositing' not in copied
            assert 'source-preserving compositing' not in copied
            assert 'IMMUTABLE ASSET' not in copied
            assert 'Wait until Card 1 is approved' not in copied
            assert 'stop and wait' not in copied
            assert len(test.get('file_uploader')) == 3
            assert any(b.label == 'Save all' for b in test.button)
            assert not any('Edit master prompt' in b.label for b in test.button)

    if mode.startswith('retired-'):
        assert test.session_state['current_page'] == 'Product Uploads'
        assert test.query_params['page'] == ['product_uploads']
