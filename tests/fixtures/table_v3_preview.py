"""Loopback-only synthetic native grid fixture: no app credentials or providers."""
import ast
import html
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import streamlit as st
from table_design import TABLE_ROW_HEIGHT, inject_table_styles

st.set_page_config(page_title='Table V3 local verification', layout='wide')
before = os.environ.get('TABLE_V3_PHASE') == 'before'
source_root = ROOT / 'tmp/table-v3-baseline' if before else ROOT

# Use the application's real shell CSS, without executing startup/API calls.
tree = ast.parse((source_root / 'app.py').read_text(encoding='utf8'))
style = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'inject_styles')
exec(compile(ast.Module(body=[style], type_ignores=[]), 'app.py', 'exec'), globals())
inject_styles()
st.title('Sports Cave OS · Table verification')
modules = ['Orders', 'Edition Ops', 'Meta Review', 'Email', 'Reporting', 'Social Media',
           'Analytics', 'SEO', 'Reviews', 'Design Tracking', 'Creative Refresh', 'Posting',
           'Marketing Factory', 'Product Uploads', 'Accounts & Access', 'Fulfilment']
module = st.selectbox('Module presentation', modules)
count = st.selectbox('Records', [50, 250, 500, 1000])
query = st.text_input('Search fixture records')
rows = [{'Record': f'KEY-{i:04}', 'Customer': f'Collector {i:04}', 'Amount': 120.5+i,
         'Units': i % 5 + 1, 'Status': ['Completed', 'Pending', 'Failed'][i % 3]}
        for i in range(count)]
rows = [row for row in rows if query.casefold() in (row['Record'] + row['Customer']).casefold()]
density = {'row_height': TABLE_ROW_HEIGHT} if not before else {}
st.caption('Synthetic data · local interaction checks')
start = time.perf_counter()
event = st.dataframe(rows, key='table-v3-selection', on_select='rerun',
                     selection_mode='single-row', hide_index=True, height=340,
                     column_config={'Amount': st.column_config.NumberColumn(format='$%.2f')}, **density)
elapsed = (time.perf_counter()-start)*1000
selected = event.selection.rows
st.caption('Selected: ' + (rows[selected[0]]['Record'] if selected else 'none'))

@st.dialog('Record details')
def details():
    st.dataframe([rows[selected[0]]], hide_index=True, **density)

if st.button('Open selected record', disabled=not selected):
    details()
def saved():
    st.session_state['fixture-saves'] = st.session_state.get('fixture-saves', 0) + 1
edited = st.data_editor(rows[:5], key='table-v3-editor', hide_index=True,
                        width='content', column_config={
                            'Record': st.column_config.TextColumn(width=160),
                            'Customer': st.column_config.TextColumn(width=200),
                            'Amount': st.column_config.NumberColumn(width=140),
                            'Units': st.column_config.NumberColumn(width=100),
                            'Status': st.column_config.TextColumn(width=160)},
                        disabled=['Record', 'Customer', 'Status'], on_change=saved, **density)
st.caption('Local saves: ' + str(st.session_state.get('fixture-saves', 0)))
st.caption('Edited units: ' + str(edited[0]['Units'] if edited else 'empty'))
st.caption('Edited amount: ' + str(edited[0]['Amount'] if edited else 'empty'))
st.table([{'Detail': 'Source', 'Value': 'Local fixture'}, {'Detail': 'Module', 'Value': module}])
st.html('<span id="table-v3-state" data-count="'+str(len(rows))+'" data-render-ms="'+str(elapsed)+'"></span>')

# Exercise actual custom Python HTML generators with synthetic inputs.
for file, function, data in [
    ('app.py', '_activity_table_html', [{'Time':'10 Oct 09:00', 'User':'Operator', 'Action':'Reviewed',
                                      'Details':'Table presentation fixture', 'Result/Status':'Complete'}]),
    ('os_pages.py', 'prodigi_reference_table_html', [{'Sports Cave Variant':'Black / 60 x 90 cm',
       'Sports Cave Frame':'Black', 'Sports Cave Size':'60 x 90 cm', 'Fulfilment Product':'Framed print',
       'Fulfilment Code':'EXAMPLE-6090', 'Fulfilment Frame Colour':'Black'}])]:
    tree=ast.parse((source_root/file).read_text(encoding='utf8'))
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==function)
    exec(compile(ast.Module(body=[node],type_ignores=[]),file,'exec'),globals())
    st.markdown(globals()[function](data), unsafe_allow_html=True)
