"""Full app execution in a session namespace, with offline service boundaries.

The wrapper remains sys.modules['__main__'], as can happen when another
Streamlit script/session replaces that process-global entry. No fake app object
or extracted app functions: compile and execute the complete, unchanged app.py.
"""
import ast
from pathlib import Path
import sys
from unittest.mock import Mock, patch
from contextlib import ExitStack

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]


def configure(ns):
    mode = st.session_state['test_mode']
    user = dict(id='offline-user', username='offline', role='staff',
                is_active=True, account_status='active', session_version=1,
                page_permissions=['product_uploads', 'files'])
    if mode == 'denied':
        user['page_permissions'] = []
    if mode != 'missing':
        st.session_state.update(sports_cave_authenticated=True,
                                sports_cave_current_user=user,
                                sports_cave_auth_checked_at=0)
    stack.enter_context(patch.object(ns['os_accounts'].DEFAULT_STORE, 'get_user', return_value={} if mode == 'expired' else user))
    # Retain actual authentication, login form, access checks, router and page.
    ns['_account_system_status'] = lambda: {'available': True, 'admin': user}
    ns['current_auth_cookie'] = lambda: ''
    ns['get_current_page'] = lambda: 'Product Uploads'
    for name in ('inject_styles', 'render_sidebar', 'apply_global_search_context',
                 'set_activity_actor', 'clear_activity_actor', '_finish_navigation_transition'):
        ns[name] = Mock()
    stack.enter_context(patch.object(ns['session_recovery'], 'install'))
    for name in ('render_top_bar', 'render_planner_data_refresh_bridge', 'render_navigation_complete'):
        stack.enter_context(patch.object(ns['top_bar'], name))
    stack.enter_context(patch.object(ns['prompt_store'], 'load_prompt_records',
        lambda specs, **kw: {s['prompt_key']: {'text': s['default_text']} for s in specs}))

    # Fail explicitly if any extracted-module dependency is absent, including
    # callbacks not exercised by an empty page or disabled buttons.
    for filename in ('product_upload_mockups_ui.py', 'product_upload_outputs_ui.py', 'product_upload_sport.py'):
        tree = ast.parse((ROOT / filename).read_text(encoding='utf-8'))
        required = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
                    and isinstance(n.value, ast.Name) and n.value.id == 'app'}
        assert not required.difference(ns), required.difference(ns)

    if mode == 'recover':
        import product_upload_intake
        st.query_params['upload']='12345678-1234-4234-9234-123456789012'
        def saved_upload(self,key,actor):
            assert key=='12345678-1234-4234-9234-123456789012' and actor=='offline-user'
            return dict(id=key,mode='DRAFT',data={})
        stack.enter_context(patch.object(product_upload_intake.Intakes,'read',saved_upload))

    if mode == 'outputs':
        import product_upload_intake
        import product_upload_dropbox
        from PIL import Image
        from product_upload_lifestyle import FILENAMES
        factory = ns['get_image_factory']()
        ns['_files_access_token']=lambda:'synthetic'
        ns['_files_team_root']=lambda token:'/Team'
        stack.enter_context(patch.object(ns['dropbox_integration'],'list_folder_page',
            lambda *a,**kw:dict(entries=[{'.tag':'folder','id':'id:cricket','name':'Cricket Wall Art',
                'path_display':'/Team/04_OUTPUT/product-images/Cricket Wall Art'}],has_more=False)))
        root = factory.create_temp_run_parent() / 'synthetic-run'
        root.mkdir()
        assets = []
        for key in ('black', 'oak', 'white', 'unframed', 'size-guide'):
            path = root / (key + '.webp')
            Image.new('RGB', (90, 60), 'navy').save(path)
            assets.append(factory.build_asset_record(key=key, label=key,
                webp_path=path, jpg_path=None, asset_group='generated', zip_group='core'))
            assets[-1]['preview_path'] = path
        prompts = []
        for filename in FILENAMES:
            path = root / filename
            path.write_text('Synthetic lifestyle prompt', encoding='utf-8')
            prompts.append(path)
        result = dict(product_name='Synthetic Product', product_slug='synthetic-product',
            sport_category='Cricket', sport_slug='cricket', run_dir=root,
            assets=assets, prompt_paths=prompts, lifestyle_mockup_paths={},
            _product_upload_intake='offline-intake', _product_upload_source_hash='offline-hash')
        st.session_state['_product_upload_active'] = 'offline-intake'
        st.session_state['_product_upload_mockups_result'] = result
        row = dict(id='offline-intake', mode='DRAFT', data=dict(name='Synthetic Product.psd',
            basic_validated=True, workflow_version=3, server_artwork={'state': 'Ready'},
            source={'content_hash': 'offline-hash', 'id': 'offline-file', 'rev': 'one'}))
        stack.enter_context(patch.object(product_upload_intake.Intakes, 'read', lambda self, key, actor: row))
        stack.enter_context(patch.object(product_upload_dropbox, 'status', lambda row, connect: row))
        # Exercise a cold lazy module in the captured namespace as on a rerun.
        ns['image_factory'] = None


def trace(frame, event, arg):
    if event == 'call' and frame.f_code.co_filename == str(ROOT / 'app.py') and frame.f_code.co_name == 'main':
        sys.settrace(None)
        configure(frame.f_globals)
    return trace


namespace = {'__name__': '__main__', '__file__': str(ROOT / 'app.py')}
stack = ExitStack()
sys.settrace(trace)
try:
    source = (ROOT / 'app.py').read_text(encoding='utf-8')
    if st.session_state['test_mode'] == 'legacy':
        # Negative control: replay the released bridge, without editing app.py.
        source = source.replace('render_page(SimpleNamespace(**globals()))',
                                "render_page(__import__('sys').modules[__name__])")
    exec(compile(source, str(ROOT / 'app.py'), 'exec'), namespace)
finally:
    sys.settrace(None)
    stack.close()
