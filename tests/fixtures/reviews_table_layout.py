"""Offline responsive/latency fixture. Synthetic data; all providers blocked."""
from copy import deepcopy
from datetime import timedelta
from time import sleep
from unittest.mock import Mock,patch
import streamlit as st
from crm_logic import now
from reviews_page import render_page
from reviews_page import changed
from tests.test_crm import ADMIN

st.set_page_config(layout='wide',page_title='Reviews table · synthetic local test')
with st.sidebar:st.title('Sports Cave OS');st.caption('Synthetic offline fixture')
if 'layout_rows' not in st.session_state:
    st.session_state.layout_rows=[dict(id='00000000-0000-0000-0000-'+str(i+1).zfill(12),source='csv',review_type='PRODUCT',
      status='PUBLISHED',product_title='The Seventh Nolan Ryan Black Framed Limited Edition Baseball Wall Art — Championship Collectors Edition',
      product_id='gid://shopify/Product/55',product_image='https://cdn.shopify.com/s/files/1/fixture.jpg',product_url='',
      reviewer_name='Synthetic collector '+str(i+1),rating=4,title='A collector edition',body='Beautiful artwork and careful presentation. A genuine centrepiece for the room.',
      created_at=now()-timedelta(days=i),updated_at='original',verified_purchase=False,source_verified=False,merchant_reply='',order_id=None,customer_id=None) for i in range(52)]
rows=st.session_state.layout_rows
calls=st.session_state.setdefault('layout_calls',{'table':0,'summary':0,'edits':0})
slow=st.session_state.get('simulate_slow');failure=st.session_state.get('simulate_failure')
def table(**kw):
    calls['table']+=1
    if slow:sleep(1)
    if failure:raise RuntimeError('Synthetic storage outage')
    filtered=[r for r in rows if str(kw.get('search','')).lower() in (r['reviewer_name']+' '+r['body']).lower() and (not kw.get('rating') or r['rating']==kw['rating'])]
    start=kw.get('offset',0);return deepcopy(filtered[start:start+26])
def summary():
    calls['summary']+=1
    return dict(total=52,average=4,recent=30,five_rate=0,attention=52)
store=Mock();store.connect=None;store.rows.side_effect=table;store.summary.side_effect=summary
store.get_review.side_effect=lambda identity:deepcopy(next(r for r in rows if r['id']==identity));store.media.return_value=[]
store.q.return_value=[]
store.products.return_value=[]
def edit(user,identity,**values):
    row=next(r for r in rows if r['id']==identity)
    if values['expected_updated_at']!=row['updated_at']:raise ValueError('Synthetic conflict')
    row.update(title=values['title'],body=values['body'],updated_at='edited');calls['edits']+=1
store.edit_text.side_effect=edit
with patch('reviews_page.acknowledge_visible'),patch('requests.sessions.Session.request',side_effect=AssertionError('Provider transport forbidden')):
    render_page(ADMIN,store=store)
with st.container(key='fixture-controls'):
    st.checkbox('Simulate slow storage',key='simulate_slow')
    st.checkbox('Simulate storage failure',key='simulate_failure')
    if st.button('Refresh fixture'):changed('table');st.rerun()
    st.caption('SQL/provider calls simulated; no live access')
    st.code(str(calls))
    st.caption('Offset: '+str(st.session_state.get('reviews_state',{}).get('offset')))
