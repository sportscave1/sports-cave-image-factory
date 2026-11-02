"""No generation or upload: load accepted assets, exercise actual Save all."""
import hashlib
import json
import sys
import types
from pathlib import Path
import streamlit as st
from recorder_save_preview import STATE
from product_upload_mockups_preview import STATE as UPLOAD
from tests.test_product_upload_intake import ADMIN, saved
from product_upload_sport import state_key
import product_upload_api
import product_upload_outputs_ui as outputs

ROOT = Path(__file__).resolve().parents[2]
st.set_page_config(page_title='Sports Cave recorder save test', layout='wide')
st.title('Sports Cave recorder save test')
st.caption('Local disk and disposable SQL only. Five synthetic base assets; three retained generated lifestyle images. No cloud writes.')
if 'save-test-app' not in st.session_state:
    module = types.ModuleType('recorder_save_fixture_app')
    module.__file__ = str(ROOT / 'app.py')
    sys.modules[module.__name__] = module
    from unittest.mock import patch
    with patch.object(st, 'set_page_config', lambda **kwargs: None), patch('app_branding.render_install_metadata', lambda *args: None):
        exec(compile((ROOT / 'app.py').read_text(encoding='utf-8').rsplit('main()', 1)[0], module.__file__, 'exec'), module.__dict__)
    st.session_state['save-test-app'] = module
app = st.session_state['save-test-app']
st.set_page_config(page_title='Sports Cave recorder save test', layout='wide')
disk = STATE['disk']
store, _, _ = UPLOAD['env']
product_upload_api.Dropbox = lambda: types.SimpleNamespace(api=disk, token='local-only')
app.dropbox_integration = disk
app._files_access_token = lambda: 'local-only'
app._files_team_root = lambda token: disk.root
app.current_os_user = lambda: ADMIN
app.record_activity_log = lambda *a, **k: None
app.os_accounts = types.SimpleNamespace(can_access_page=lambda *a: True)
if 'save-test-row' not in st.session_state:
    row = saved(UPLOAD['env'])
    result = app.load_run_metadata(STATE['source'])
    accepted = json.loads((STATE['source'] / 'recorder-upload-receipt.json').read_text())
    if not accepted['readiness']['complete'] or len(accepted['originals']) != 3:
        raise ValueError('Accepted eight-image run required')
    for original in accepted['originals'].values():
        if hashlib.sha256(Path(original['path']).read_bytes()).hexdigest() != original['sha256']:
            raise ValueError('Accepted original changed')
    result.update(_product_upload_intake=str(row['id']), _product_upload_actor_id=ADMIN['id'],
        _product_upload_source_hash=row['data']['source']['content_hash'],
        _product_upload_source=dict(row['data']['source']))
    st.session_state['_product_upload_active'] = str(row['id'])
    result = app.normalize_generation_result(result)
    if not result['product_image_readiness']['complete']:
        raise ValueError('Retained manifest is incomplete')
    app._set_mockups_result(result)
    st.session_state['save-test-row'] = row
row = st.session_state['save-test-row']
key = str(row['id'])
st.session_state['_product_upload_active'] = key
st.session_state[state_key(key) + '-resolved'] = dict(id='id:recorder-hockey', path=disk.base + '/Hockey', name='Hockey', sport='Hockey', root=disk.root)
result = app._mockups_result()
st.caption('Source run: ' + str(STATE['source']))
st.caption('Local destination: ' + str(disk.directory))
st.caption('8 of 8 accepted product images')
target = disk.directory / ('save-receipt-' + key + '.json')
st.caption('Local save receipt: ' + str(target))
from product_upload_jobs import JOBS
job = JOBS.snapshot(key, ADMIN['id'], 'save')
busy = bool(job and job['state'] in ('Queued', 'Running'))
if st.button('Inject one test-only save failure', disabled=busy):
    disk.fail_once = '*'
    st.caption('Next missing output will fail once; existing files stay unchanged.')
outputs.save_controls(app, result, row, ADMIN, 'Recorder Phase 7 ' + key[:8])
receipt = (app._mockups_result() or {}).get('product_upload_save_receipt')
completed = JOBS.snapshot(key, ADMIN['id'], 'save')
if receipt and completed and completed['state'] == 'Ready':
    if st.session_state.get('published-save-job') != completed['token']:
        temporary = target.with_suffix('.tmp')
        temporary.write_text(json.dumps(dict(receipt=receipt, calls=disk.calls, source_run=str(STATE['source']), synthetic_base=True, job_token=completed['token']), indent=2), encoding='utf-8')
        temporary.replace(target)
        st.session_state['published-save-job'] = completed['token']
    if not receipt.get('failures') and len(receipt.get('successes', [])) == 8:
        from product_upload_source import current_source
        from product_upload_prompt_copy import prepare, render_copy
        current = store.read(key, ADMIN['id'])
        version = current_source(current)['version']
        prompt = prepare(store, key, ADMIN['id'], current['mode'], version)
        (disk.directory / 'prepared-upload-prompt.txt').write_text(prompt, encoding='utf-8')
        st.warning('Test-only destination IDs. Inspect/copy only; do not submit this prompt to a connected store.')
        render_copy(app, current, ADMIN, version)
