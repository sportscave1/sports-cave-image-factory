"""Real upload cards with synthetic base assets, no cloud operations."""
import hashlib
import json
from pathlib import Path
import tempfile
import types
import sys

import streamlit as st
from product_upload_mockups_preview import STATE
from tests.test_product_upload_intake import ADMIN, saved
from PIL import Image
import image_factory
import product_upload_outputs_ui as outputs

ROOT = Path(__file__).resolve().parents[2]
if 'recorder-upload-app' not in st.session_state:
    module = types.ModuleType('recorder_upload_fixture_app')
    module.__file__ = str(ROOT / 'app.py')
    sys.modules[module.__name__] = module
    exec(compile((ROOT / 'app.py').read_text(encoding='utf-8').rsplit('main()', 1)[0],
                 module.__file__, 'exec'), module.__dict__)
    st.session_state['recorder-upload-app'] = module
app = st.session_state['recorder-upload-app']

st.set_page_config(page_title='Sports Cave OS', layout='wide')
st.title('Sports Cave recorder upload test')
st.caption('Isolated test: five synthetic base images; real retained lifestyle uploads. No external saves.')
store, _, provider = STATE['env']
app.current_os_user = lambda: ADMIN
app.record_activity_log = lambda *a, **k: None
if st.button('Reset isolated upload run'):
    # Retain old evidence/files; a new run gets distinct uploader widget keys.
    st.session_state.pop('recorder-upload-row', None)
    st.session_state.pop('recorder-upload-result', None)
    st.rerun()
if 'recorder-upload-row' not in st.session_state:
    row = saved(STATE['env'])
    base = Path(tempfile.mkdtemp(prefix='recorder-upload-'))
    templates = base / 'templates'
    templates.mkdir()
    for name in ('black-frame-template.jpg', 'oak-frame-template.jpg', 'white-frame-template.jpg',
                 'unframed-template.jpg', 'size-guide-template.jpg'):
        Image.new('RGB', (1000, 1000), (230, 226, 218)).save(templates / name)
    source = base / 'synthetic-artwork.png'
    Image.new('RGB', (120, 80), (20, 40, 80)).save(source)
    result = image_factory.generate_product_images('Isolated recorder test', 'Hockey', source,
        base_dir=base, output_root=image_factory.create_temp_run_parent(), export_jpg=False)
    from product_upload_lifestyle import FILENAMES
    prompt_dir = Path(result['run_dir']) / 'prompts'
    prompt_dir.mkdir(exist_ok=True)
    result['prompt_paths'] = []
    for filename in FILENAMES:
        prompt = prompt_dir / filename
        prompt.write_text('Isolated upload test. Do not submit generation.', encoding='utf-8')
        result['prompt_paths'].append(prompt)
    result.update(_product_upload_intake=str(row['id']), _product_upload_actor_id=ADMIN['id'],
                  _product_upload_source_hash=row['data']['source']['content_hash'])
    st.session_state['recorder-upload-row'] = row
    st.session_state['recorder-upload-result'] = result
    st.session_state['_product_upload_active'] = str(row['id'])
    app._set_mockups_result(result)
row = st.session_state['recorder-upload-row']
st.session_state['_product_upload_active'] = str(row['id'])
result = app._mockups_result() or st.session_state['recorder-upload-result']

def defaults(specs, **kwargs):
    return {spec['prompt_key']: dict(text=spec['default_text']) for spec in specs}

def local_save_boundary(*args):
    st.caption('Save all is unavailable in this upload-only test.')
    # Runs after every fragment update, including file-picker acceptance.
    latest = app._mockups_result()
    receipt = dict(intake=str(row['id']), synthetic_base=True, originals={})
    for name, entry in (latest.get('product_upload_originals') or {}).items():
        path = Path(entry['path'])
        receipt['originals'][name] = dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    receipt['readiness'] = latest['product_image_readiness']
    target = Path(latest['run_dir'], 'recorder-upload-receipt.json')
    target.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    st.caption('Local receipt: ' + str(target))

app.prompt_store.load_prompt_records = defaults
app.prompt_store.get_prompt = lambda key, default='', **kw: default
# Fragment-only reruns also remain inside this boundary.
outputs.save_controls = local_save_boundary
outputs.render_outputs(app, result, row, ADMIN, 'Isolated recorder test')

