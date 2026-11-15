"""Synthetic Reviews preview; provider/network transport is forbidden."""
from datetime import timedelta
from unittest.mock import Mock
import streamlit as st
from crm_logic import now
from reviews_page import render_page
from reviews_model import DEFAULT_DISPLAY
from tests.test_crm import ADMIN

st.set_page_config(layout='wide',page_title='Reviews · local fixture')
rows=[{'id':'00000000-0000-0000-0000-'+str(i+1).zfill(12),'source':'csv','status':'PUBLISHED' if i%3 else 'PENDING',
 'product_title':'63 Years Later: Ryan Fox Open Championship Wall Art','product_id':'gid://shopify/Product/55',
 'product_image':'','product_url':'https://fixture.example/products/fox','reviewer_name':'Fixture collector '+str(i+1),
 'rating':5 if i%3 else 2,'title':'A lasting collector edition','body':'Beautiful artwork and careful presentation. A genuine centrepiece for the room.',
 'created_at':now()-timedelta(days=i),'verified_purchase':False,'source_verified':False,'merchant_reply':'','order_id':None,'customer_id':None} for i in range(6)]
store=Mock();store.connect=None
store.summary.return_value={'total':6,'average':4.0,'recent':6,'five_rate':66.7,'attention':2}
store.rows.side_effect=lambda **kw:[r for r in rows if kw.get('status')!='PENDING' or r['status']=='PENDING']
store.settings.return_value=dict(DEFAULT_DISPLAY);store.imports.return_value=[];store.q.return_value=None
store.products.return_value=[{'shopify_product_id':'gid://shopify/Product/55','title':'Fixture product'}]
store.get_review.side_effect=lambda identity:next(r for r in rows if r['id']==identity)
render_page(ADMIN,store=store)
