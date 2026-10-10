"""Isolated real render functions with synthetic reads; no app/provider imports."""
import ast, html, json, sys, time
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import streamlit as st
from table_design import TABLE_ROW_HEIGHT,inject_table_styles
import importlib, page_presentation
importlib.reload(page_presentation)
from page_presentation import inject_compact_page
st.set_page_config(page_title='Sports Cave local UI audit',layout='wide')
phase=st.query_params.get('phase','after')
route=st.query_params.get('route','Prodigi')
source=ROOT/'tmp/appwide-ui-v1-os_pages.before.py' if phase=='before' else ROOT/'os_pages.py'
@st.cache_resource(show_spinner=False)
def extracted(path,names,modified):
 # Cache only compiled public source, never customer records or provider responses.
 tree=ast.parse(Path(path).read_text(encoding='utf-8-sig'))
 return tuple(compile(ast.Module(body=[n],type_ignores=[]),path,'exec') for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names)
names=('render_prodigi_page','render_webhook_events_page','render_sync_runs_page','render_app_errors_page','render_persistence_check_page','prodigi_reference_table_html','_render_prodigi_dispatch_result','_prodigi_clean')
for code in extracted(str(source),names,source.stat().st_mtime_ns):exec(code,globals())
# Real shared shell styling, no application startup.
for code in extracted(str(ROOT/'app.py'),('inject_styles',),(ROOT/'app.py').stat().st_mtime_ns):exec(code,globals())
inject_styles()
PRODIGI_DASHBOARD_URL='https://example.invalid/fulfilment'
PRODIGI_SUPPORT_EMAIL='support@example.invalid'
PRODIGI_DISPATCH_SEARCH_QUERY_KEY='prodigi_dispatch_submitted_search'
PRODIGI_DISPATCH_FUTURE_KEY='prodigi_dispatch_load_future'
PRODIGI_DISPATCH_REQUEST_KEY='prodigi_dispatch_load_request'
PRODIGI_DISPATCH_RESULT_KEY='prodigi_dispatch_loaded_request'
PRODIGI_DISPATCH_ROWS_KEY='prodigi_dispatch_loaded_rows'
PRODIGI_DISPATCH_ERROR_KEY='prodigi_dispatch_load_error'
_prodigi_log_timing=lambda *a,**k:None
_prodigi_prepare_entry_state=lambda **k:None
_async_prodigi_load_supported=lambda:False
prodigi_reference_rows=lambda:[{'Sports Cave Variant':'Black / XL','Sports Cave Frame':'Black','Sports Cave Size':'A1','Fulfilment Product':'Classic Frame','Fulfilment Code':'GLOBAL-CFP-A1','Fulfilment Frame Colour':'Black'}]
prodigi_find_order_rows_from_cache=lambda query:([],[])
def _prodigi_apply_order_lookup(query,**kwargs):
 st.session_state['prodigi_dispatch_last_query']=query
 st.session_state['fixture_lookup']=query
prodigi_dispatch_table_records=lambda rows:rows
records=[{'Order':f'#SC{3000+i}','Customer':f'Test Collector {i}','Product':'Cricket wall art','Edition':f'{i}/100','Status':'Submitted','Notes':'QA checked','updated_at':'2026-10-10 09:00'} for i in range(1,51)]
def prodigi_load_dispatch_rows(view,query,limit=50):
 st.session_state['fixture_read_count']=st.session_state.get('fixture_read_count',0)+1
 return [r for r in records if query.lower() in str(r).lower()][:limit]
supabase_backend=SimpleNamespace(is_configured=lambda:True,list_webhook_events=lambda **k:[{'ID':'event-001','Topic':'orders/create','Status':'Processed','Received':'2026-10-10 09:00'}],list_sync_runs=lambda **k:[{'ID':'sync-001','Type':'Orders','Status':'Complete','Rows':50}],list_app_errors=lambda **k:[{'ID':'error-001','Source':'Fixture','Message':'Synthetic example','Resolved':True}],persistence_counts=lambda:{'products':50,'orders':50,'assets':50})
start=time.perf_counter()
{'Prodigi':render_prodigi_page,'Webhook Events':render_webhook_events_page,'Sync Runs':render_sync_runs_page,'App Errors':render_app_errors_page,'Persistence Check':render_persistence_check_page}[route]()
st.html('<span id="fixture-evidence" data-render-ms="'+str((time.perf_counter()-start)*1000)+'" data-reads="'+str(st.session_state.get('fixture_read_count',0))+'" data-search="'+html.escape(str(st.session_state.get(PRODIGI_DISPATCH_SEARCH_QUERY_KEY,'')),quote=True)+'"></span>')
