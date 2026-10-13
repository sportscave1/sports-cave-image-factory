"""Actual Campaign editor; fabricated Shopify and loopback PostgreSQL only."""
from pathlib import Path
import sys,os,json
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
os.environ.setdefault('CRM_FIXTURE_SQL_PORT','8873')
import streamlit as st
from tests.crm_db_fixture import connect
from tests.test_crm_lifecycle_publication import LifecyclePublicationTests
from tests.test_crm_smart_catalogue import fixture
from crm_lifecycle_audience import cache_customer
from crm_logic import now

@st.cache_resource
def seed_smart():
    LifecyclePublicationTests.setUpClass()
    with connect() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS shopify_products(shopify_product_id text PRIMARY KEY,
            title text,product_type text,status text,online_store_url text,handle text,image_url text,raw_json jsonb DEFAULT '{}')''')
        for i in (9,10):
            c.execute('''INSERT INTO shopify_products(shopify_product_id,title,product_type,status,online_store_url)
                VALUES(%s,%s,'Motorsport','ACTIVE',%s) ON CONFLICT DO NOTHING''',
                (str(i),'Motorsport artwork '+str(i),'https://www.sportscaveshop.com/products/art-'+str(i)))
    from crm_campaign_store import CampaignStore
    store=CampaignStore(connect)
    for i,title,seed in [(901,'Fixture Alice',1),(902,'Fixture Bob',8)]:
        customer={'id':f'gid://shopify/Customer/{i}','email':f'fixture-{i}@example.invalid',
            'firstName':title,'lastName':'','createdAt':now().isoformat(),'updatedAt':now().isoformat(),
            'emailMarketingConsent':{'marketingState':'SUBSCRIBED'},'defaultAddress':{'countryCodeV2':'AU'}}
        cache_customer(store,customer,now())
        order={'lineItems':{'nodes':[{'title':'Motorsport artwork','product':{'id':f'gid://shopify/Product/{seed}'}}]}}
        with connect() as c:
            c.execute('''INSERT INTO shopify_orders(shopify_order_id,shopify_customer_id,financial_status,created_at,raw_json)
                VALUES(%s,%s,'PAID',now(),%s::jsonb) ON CONFLICT DO NOTHING''',
                (f'gid://shopify/Order/{i}',customer['id'],json.dumps(order)))
    return True

seed_smart()
if st.query_params.get('offline')=='1':st.session_state['_fixture_offline']=True
source=Path('tests/fixtures/crm_collection_picker.py').read_text()
source=source.replace("st.set_page_config(layout='wide')",'')
source=source.replace('\ninject_styles()','\nstyle_file=__file__;__file__=str(ROOT/"app.py");inject_styles();__file__=style_file')
source=source.replace('campaign_workspace(shop,CampaignStore(connect),Mock(user=ADMIN))','''
cat,authority,_=fixture(size=12)
shop.query.side_effect=authority.query.side_effect
shop.storefront_query.side_effect=authority.storefront_query.side_effect
if st.session_state.get('_fixture_offline'):
    shop.namespace+='-offline'
    shop.storefront_query.side_effect=RuntimeError('Fixture Storefront unavailable')
import crm_smart_catalogue
crm_smart_catalogue.Catalogue=lambda *a,**k:cat
if st.button('Reopen saved editor fixture'):
    for field in ('campaign_editor','campaign_saved','campaign_edit_key'):st.session_state.pop(field,None)
offline='&amp;offline=1' if st.session_state.get('_fixture_offline') else ''
st.html('<a target="_self" href="?page=CRM+Campaigns&amp;campaign='+str(row['id'])+offline+'">Open Catalogue fixture</a>')
campaign_workspace(shop,CampaignStore(connect),Mock(user=ADMIN))
''')
st.set_page_config(layout='wide')
exec(compile(source,'collection-picker-fixture','exec'))
