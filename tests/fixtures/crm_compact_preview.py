"""Real Streamlit preview/toolbar, synthetic API and SQL facts, no delivery."""
import sys
import os,types
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
if os.environ.get('CRM_PREVIEW_BASELINE')=='1':
    for name,filename in [('crm_flow_preview','baseline-flow-preview.py'),('crm_local_preview','baseline-local-preview.py'),('crm_abandoned_checkout_ui','baseline-canvas.py')]:
        module=types.ModuleType(name);module.__file__=str(Path.cwd()/(name+'.py'));sys.modules[name]=module
        exec(compile((Path('.tmp-preview-performance')/filename).read_text(),module.__file__,'exec'),module.__dict__)
import streamlit as st
from copy import deepcopy
from datetime import timedelta
from unittest.mock import Mock
from threading import Lock
import time,json
import requests
requests.sessions.Session.request=lambda *a,**k:(_ for _ in ()).throw(AssertionError('External network disabled'))
from crm_logic import now
from crm_automation_store import AutomationStore
from crm_abandoned_checkout_ui import automation_canvas
from crm_campaign_sections import section_defaults
from crm_collector_resolver import ORDER,PRODUCTS,BESTSELLERS
from crm_lifecycle_shopify import ORDER_FACTS
from crm_middle_sections import commit_middle
from tests.test_crm_flow_customer_preview import preview_wire,document
from tests.test_crm_collector_personalisation import product
from tests.test_crm_send_flow import CFG
import crm_personalisation_data
crm_personalisation_data.allocation=lambda *a:None
crm_personalisation_data.metadata=lambda *a:{}

st.set_page_config(layout='wide')
st.session_state['email_editor_mode']='automation'
kind=st.selectbox('Fixture flow',['post_purchase','welcome','win_back','fulfilled','abandoned'])
if st.button('Close/open editor'):st.session_state['fixture_closed']=not st.session_state.get('fixture_closed',False)
st.button('Fixture counters')
slot='fixture_'+kind
if slot not in st.session_state:
    store,shop,row,_,_=preview_wire(kind,age=180 if kind=='win_back' else 1)
    metrics={};lock=Lock()
    def count(key,_metrics=metrics,_lock=lock):
        with _lock:_metrics[key]=_metrics.get(key,0)+1
    profiles={};orders={};ledgers={};options=[]
    for i,name in enumerate(['Fixture Ada','Fixture Grace with a deliberately very long customer name to check truncation']):
        cid='gid://shopify/Customer/'+str(101+i);oid='gid://shopify/Order/'+str(10+i)
        c=deepcopy(shop.customer.return_value);c.update(id=cid,firstName=name,email='fixture'+str(i)+'@example.invalid')
        c['defaultEmailAddress']['emailAddress']=c['email'];profiles[cid]=c
        at=now()-timedelta(days=(180 if kind=='win_back' else 1)+i)
        o=deepcopy(shop.orders.return_value['nodes'][0] if shop.orders.return_value['nodes'] else __import__('tests.test_crm_collector_personalisation',fromlist=['order']).order())
        o.update(id=oid,customer={'id':cid},createdAt=at.isoformat(),displayFulfillmentStatus='FULFILLED')
        pid='gid://shopify/Product/'+str(1+i);line=o['lineItems']['nodes'][0];line.update(product={'id':pid},quantity=i+1,title='Fixture '+('Ada' if i==0 else 'Grace')+' Motorsport artwork',variant={'id':'gid://shopify/ProductVariant/'+str(i+1),'product':{'id':pid},'image':{'url':'https://cdn.shopify.com/fixture-'+str(i)+'.png'}})
        orders[cid]=[] if kind=='welcome' else [o]
        raw={**o,'lifecycleFacts':{'risk':{'recommendation':'ACCEPT'},'disputes':[],'returnStatus':'NO_RETURN','fulfillments':[{'status':'SUCCESS','createdAt':at.isoformat()}]}}
        record={'shopify_order_id':oid,'created_at':at.isoformat(),'financial_status':'PAID','fulfillment_status':'FULFILLED','raw_json':raw}
        ledgers[oid]=record
        options.append({'key':cid if kind=='welcome' else oid,'customer_id':cid,'name':name,'profile':c,'verified_at':now().isoformat(),'subscribed_at':now().isoformat(),'paid_at':at.isoformat(),'fulfilled_at':at.isoformat(),'order_record':record})
    def q(sql,args=(),*rest,_options=options,_ledgers=ledgers):
        count('sql')
        if 'crm_lifecycle_customers' in sql:return deepcopy(_options)
        if sql.startswith('SELECT * FROM shopify_orders'):return [deepcopy(_ledgers[i]) for i in args[0]]
        if sql.startswith('SELECT object_id,topic'):return [{'object_id':i,'topic':'orders/paid','occurred_at':_ledgers[i]['created_at']} for i in args[0]]
        if sql.startswith('SELECT shopify_product_id'):return [{'shopify_product_id':i,'image_url':'https://cdn.shopify.com/fixture-'+str(int(i.rsplit('/',1)[-1])-1)+'.png','online_store_url':product(i)['onlineStoreUrl']} for i in args[0]]
        return []
    def customer(identity,_profiles=profiles,**kwargs):count('customer');time.sleep(.04);return deepcopy(_profiles[identity])
    def order_history(identity,_orders=orders,**kwargs):count('orders');time.sleep(.04);return {'nodes':deepcopy(_orders[identity]),'pageInfo':{'hasNextPage':False}}
    def query(sql,variables,*rest,_orders=orders,_ledgers=ledgers):
        count('query');time.sleep(.04)
        if sql==ORDER:return {'order':deepcopy(next(o for h in _orders.values() for o in h if o['id']==variables['id']))}
        if sql==ORDER_FACTS:return {'nodes':[{'id':i,'risk':{'recommendation':'ACCEPT'},'disputes':[],'returnStatus':'NO_RETURN','fulfillments':[{'status':'SUCCESS','createdAt':_ledgers[i]['created_at']}]} for i in variables['ids']]}
        if sql==BESTSELLERS:return {'collection':{'id':variables['id'],'products':{'nodes':[{'id':'gid://shopify/Product/'+str(i)} for i in range(3,9)]}}}
        if sql==PRODUCTS:return {'nodes':[product(i) for i in variables['ids']]}
        return {'nodes':[]}
    store.q.side_effect=q;store.preview_document=lambda d,owner=store:AutomationStore.preview_document(owner,d)
    store.default_sections.return_value=section_defaults(CFG)
    shop.customer.side_effect=customer;shop.orders.side_effect=order_history;shop.query.side_effect=query
    shop.products.side_effect=lambda ids,**kw:[product(i,collections={'nodes':[{'id':'gid://shopify/Collection/1','title':'Motorsport','handle':'motorsport'}]}) for i in ids]
    doc=document()
    if kind=='welcome':commit_middle(doc,[dict(id='welcome-body',type='html',visible=True,html_number=1,html='<p>Fixture Welcome subscriber content</p>')])
    if kind=='abandoned':
        from tests.test_crm_abandoned_checkout import checkout,native_document
        from crm_abandoned_checkout import context as checkout_context
        from concurrent.futures import Future
        doc=native_document();f=Future();data=checkout_context(checkout(),edition_reader=lambda **_:[]);f.set_result(data)
        st.session_state['_automation_checkout_pin']={'future':f,'last_good':data,'namespace':'fixture','started':time.monotonic()}
    st.session_state[slot]=(store,doc,metrics)
store,doc,metrics=st.session_state[slot]
if st.session_state.get('fixture_closed'):
    st.caption('Editor closed')
else:
    def edit():
        parts=deepcopy(doc['middle_sections']);parts[0]['html']=st.session_state['fixture_html'];commit_middle(doc,parts)
    st.text_area('Fixture HTML',doc['middle_sections'][0].get('html',''),key='fixture_html',on_change=edit)
    st.session_state['automation_editor']={'id':'00000000-0000-0000-0000-000000000001','version':1,'document':doc}
    if st.button('Collection template'):
        from crm_post_purchase_templates import source
        parts=deepcopy(doc['middle_sections']);parts[0]['html']=source('collections');commit_middle(doc,parts)
    automation_canvas(doc,{**CFG,'email_defaults':section_defaults(CFG)},'fixture_'+kind+'_',store)
st.html('<pre id="fixture-metrics">'+json.dumps(metrics)+'</pre>')
