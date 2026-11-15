"""Loopback-only REAL app/Orders renderer, synthetic read boundaries.

Browser timings from this harness isolate Streamlit/render lifecycle effects;
they are not production end-to-end timings. Source delays are explicit inputs,
using measured production medians. Auth uses a signed disposable local cookie
and the actual authentication/permission functions. No production data/secrets.
Run: python tests/orders_v20_preview.py --serve ROOT PORT [before|after]
"""
from pathlib import Path
import os
import sys

if '--serve' in sys.argv:
    root, port, variant = sys.argv[2:]
    sys.argv[:] = [sys.argv[0]]
    os.environ.update(OV20_ROOT=root, OV20_VARIANT=variant,
                     SPORTS_CAVE_AUTH_SECRET='ov20-local-only')
    sys.path.insert(0, root)
    import sc_auth
    import uvicorn
    from streamlit.web.server.starlette import App
    from starlette.middleware import Middleware
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse
    from starlette.routing import Route
    token = sc_auth.create_user_auth_token('00000000-0000-0000-0000-000000000020',
                                        extra_secret=os.environ['SPORTS_CAVE_AUTH_SECRET'])
    class LocalCookie(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            response = await call_next(request)
            if request.url.path == '/':
                response.set_cookie(sc_auth.AUTH_COOKIE_NAME, token, samesite='lax')
            return response
    async def status(request):
        return JSONResponse(dict(ok=True, items=[], notifications=[], results=[],
                                 timer={}, action_required_count=0, unread_count=0))
    import top_bar_api
    paths = (top_bar_api.EMAIL_STATUS_PATH, top_bar_api.ORDER_STATUS_PATH,
             top_bar_api.NOTIFICATIONS_PATH, top_bar_api.DAILY_PLANNER_STATUS_PATH,
             top_bar_api.REPAIR_REQUESTS_PATH)
    uvicorn.run(App(str(Path(__file__).resolve()), routes=[Route(p, status) for p in paths],
                    middleware=[Middleware(LocalCookie)]), host='127.0.0.1', port=int(port))
else:
    import ast
    import time
    from copy import deepcopy
    from types import SimpleNamespace
    from unittest.mock import Mock
    root = Path(os.environ['OV20_ROOT'])
    sys.path.insert(0, str(root))
    # Refuse ALL external DB/API calls, including accidental writer paths.
    for key in list(os.environ):
        if any(part in key.upper() for part in ('DATABASE_URL', 'SUPABASE', 'SHOPIFY', 'DROPBOX', 'RESEND')):
            os.environ.pop(key, None)
    import requests
    import psycopg
    def forbidden(*args, **kwargs):
        raise AssertionError('External I/O forbidden in Orders V20 local preview')
    requests.sessions.Session.request = forbidden
    psycopg.connect = forbidden
    import streamlit as st
    import orders_page as orders
    import os_accounts
    import supabase_backend as db
    import psd_directory
    import auto_editions_runtime as runtime
    st.set_page_config(page_title='Sports Cave OS · local V20 verification', layout='wide', initial_sidebar_state='expanded')
    before = os.environ['OV20_VARIANT'] == 'before'
    user = dict(id='00000000-0000-0000-0000-000000000020', role='admin',
                username='synthetic', display_name='Local validation',
                email='fixture@sportscave.test', is_active=True, account_status='active',
                session_version=1, page_permissions=['orders'], timezone='Australia/Sydney')
    def account(identity):
        time.sleep(.14)
        return deepcopy(user) if identity == user['id'] else {}
    os_accounts.DEFAULT_STORE = SimpleNamespace(get_user=account)
    db.connect = forbidden
    db.is_configured = lambda: True
    db.orders_badge_summary = lambda **kwargs: {'action_required_count': 0}
    db.orders_visibility_marker = lambda **kwargs: {'marker': 'synthetic-stable'}
    db.database_status = lambda **kwargs: {'configured': True, 'connected': True}
    rows = []
    for i in range(50):
        for line in range(2 if i < 13 else 1):
            for unit in range(2 if i == 0 and line == 0 else 1):
                rows.append(dict(order=f'#TEST{3400-i}', shopify_order_id=str(3400-i),
                    shopify_line_item_id=str(10000+i*2+line), shopify_product_gid=f'gid://shopify/Product/{100+i}',
                    allocation_index=unit+1, edition_order_id=str(700+i*3+line+unit),
                    edition_number=i+unit+1, edition_total=100, customer=f'Synthetic collector {i:02}',
                    product=f'Synthetic artwork {i:02}', variant='Black / 60 x 90 cm', shipping='Standard',
                    processed_at='2026-10-16T01:00:00Z', prodigi_status='',
                    _orders_refund={'status': 'Refund Pending' if i == 1 else 'Refunded' if i == 2 else '',
                                    'blocked': i in (1,2), 'closed': i == 2}))
    assert len(rows) == 64
    def read(search='', limit=50):
        # Identical 560-order fixture scope, selected 50 orders / 64 units.
        corpus = rows + [dict(rows[-1], order=f'#TEST{3000-i}',
                              shopify_order_id=str(3000-i)) for i in range(510)]
        selected = orders._filter_rows(corpus, search) if search else deepcopy(rows)
        time.sleep((.869 if before else .309) if search else (1.705 if before else .960))
        return {'rows': selected, 'source': 'synthetic-560-order-ledger',
                'order_count': len({r['shopify_order_id'] for r in selected}), 'search': search}
    orders._read_orders_snapshot = read
    def mapping():
        time.sleep(.143)
        return {f'gid://shopify/Product/{100+i}': dict(verified=True, state='Linked',
            dropbox_file_id=f'id:synthetic{i}', path=psd_directory.ROOT+f'/Synthetic artwork {i:02}.psd',
            url='https://www.dropbox.com/preview/synthetic.psd') for i in range(288)}
    psd_directory.directory = lambda *args: mapping()
    def links(rows):
        time.sleep(1.252 if before else .390)
        return {str(r['edition_order_id']): '/auto-editions/open?allocation_id='+str(r['edition_order_id'])+'&job_id=synthetic#Open' for r in rows}
    runtime.download_links = links
    if not before:
        import orders_display_reads
        orders_display_reads.download_links = links
    os.environ['SPORTS_CAVE_AUTO_EDITIONS_V6'] = 'true'
    # Execute actual app definitions and main; skip top-level dotenv/main calls.
    tree = ast.parse((root/'app.py').read_text(encoding='utf-8'))
    nodes = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom,
             ast.FunctionDef, ast.ClassDef, ast.Assign, ast.AnnAssign))]
    namespace = {'__file__': str(root/'app.py'), '__name__': 'orders_v20_local'}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(root/'app.py'), 'exec'), namespace)
    namespace['get_orders_page'] = lambda: orders
    if not hasattr(orders, '_ov20_original_render'):
        orders._ov20_original_render = orders.render_page
        def render():
            orders._ov20_original_render()
            import html
            st.session_state['ov20_orders_runs'] = st.session_state.get('ov20_orders_runs', 0)+1
            query = str(st.session_state.get(orders.LOADED_QUERY_KEY) or '')
            if st.session_state.get(orders.LOAD_FUTURE_KEY) is None:
                st.html('<div id="ov20-ready" data-query="'+html.escape(query, quote=True)
                        +'" data-rows="'+str(len(st.session_state.get(orders.ROWS_KEY) or []))
                        +'" data-run="'+str(st.session_state['ov20_orders_runs'])
                        +'" data-full-run="'+str(st.session_state.get('ov20_full_runs', 0))+'"></div>')
        orders.render_page = render
    # Dashboard is only a navigation origin; its backend is unrelated to Orders.
    namespace['render_lightweight_dashboard_page'] = lambda: st.title('Home')
    st.session_state.setdefault('current_page', 'Orders')
    st.session_state.setdefault('selected_page', 'Orders')
    st.session_state['ov20_full_runs'] = st.session_state.get('ov20_full_runs', 0)+1
    namespace['main']()
    st.html('<div id="ov20-full-run" data-count="'+str(st.session_state['ov20_full_runs'])+'"></div>')
