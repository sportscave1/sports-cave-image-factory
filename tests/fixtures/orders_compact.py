"""Orders UI with synthetic units and no production backend or action writes."""
import ast
from pathlib import Path
from html import escape
from types import SimpleNamespace
from unittest.mock import patch
import streamlit as st
import orders_page as orders

st.set_page_config(layout='wide')
# Exercise the actual shared styling without importing the running application.
tree=ast.parse(Path('app.py').read_text(encoding='utf-8'))
style=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='inject_styles')
exec(compile(ast.Module(body=[style],type_ignores=[]),'app.py','exec'),globals())
inject_styles()
st.html('<style>.fixture-nav{position:fixed;top:0;left:0;width:100%;height:64px;background:#111;color:white;z-index:10000;padding:18px 24px;box-sizing:border-box}header[data-testid="stHeader"]{display:none}</style><div class="fixture-nav">Sports Cave OS · Orders fixture</div>')
rows=[dict(order=f'#SC{3000+i}',shopify_order_id=str(3000+i),shopify_line_item_id=str(6000+i),
           allocation_index=u,edition_number=i+u,edition_total=100,customer=f'Collector {i}',
           product=f'Artwork {i}',variant='Black / 60 x 90 cm',shipping='Standard',
           processed_at='2026-10-08T10:00:00Z',prodigi_status='Complete' if i%3==0 else '',
           certificate_pdf_url='https://example.test/certificate.pdf')
      for i in range(50) for u in range(1,3 if i<12 else 2)]
def read(search='',limit=50):
    selected=orders._filter_rows(rows,search) if search else rows
    return {'rows':selected,'source':'fixture','order_count':50,'search':search}
def action(selected):
    st.session_state[orders.NOTICE_KEY]=f'Fixture action on {len(selected)} selected units'
    return True
backend=SimpleNamespace(orders_visibility_marker=lambda **kw:{'marker':'fixture-v1'})
with patch.object(orders,'_configured_supabase_backend',return_value=backend), patch.object(orders,'_read_orders_snapshot',side_effect=read), patch.object(orders,'_generate_selected_certificates',side_effect=action), patch.object(orders,'_generate_upload_selected_certificates',side_effect=action), patch.object(orders,'_open_prodigi_for_row',side_effect=lambda row:action([row])):
    orders.render_page()
st.html(f'<span id="orders-fixture-state" style="display:none" data-count="{len(st.session_state.get(orders.ROWS_KEY,[]))}" data-query="{escape(st.session_state.get(orders.LOADED_QUERY_KEY,""),quote=True)}"></span>')
