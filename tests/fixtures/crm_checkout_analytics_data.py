"""Synthetic browser data only, persisted to loopback SQL; never sends email."""
from copy import deepcopy
from datetime import timedelta
import uuid,os
import streamlit as st
from crm_logic import now
from crm_shopify_automation_events import facts,persist
from crm_checkout_analytics import details
from tests.test_crm import ADMIN
from tests.test_crm_send_flow import LIVE

@st.cache_resource
def setup(_store,identity):
    store=_store
    row=store.flow(identity);store.publish(ADMIN,identity,row['config']['revision'],env=LIVE)
    at=now();objects={};customers={}
    for index in range(70):
        days=1 if index<40 else 20 if index<50 else 60 if index<60 else 400
        stamp=at-timedelta(days=days);token='browser_'+uuid.uuid4().hex
        customer={'id':'gid://shopify/Customer/'+str(900000+index),'firstName':'Local','lastName':'Collector '+str(index),
          'email':'local'+str(index)+'@example.test','emailMarketingConsent':{'marketingState':'SUBSCRIBED'},'validEmailAddress':True}
        checkout={'id':'gid://shopify/AbandonedCheckout/'+str(800000+index),'createdAt':stamp.isoformat(),'updatedAt':stamp.isoformat(),
          'completedAt':None,'customer':customer,'abandonedCheckoutUrl':'https://fixture.myshopify.com/checkouts/'+token+'/recover',
          'shippingAddress':{'countryCodeV2':'AU'},'totalPriceSet':{'shopMoney':{'amount':'199.50','currencyCode':'AUD'}}}
        payload={'token':token,'customer':{'id':customer['id']},'created_at':stamp.isoformat(),'updated_at':stamp.isoformat()}
        persist(store,'browser-'+str(uuid.uuid4()),'checkouts/create','checkout-fixture',customer['id'],stamp,facts('checkouts/create',payload,'fixture.myshopify.com',stamp))
        details(store,checkout);objects[checkout['id']]=checkout;customers[customer['id']]=customer
    prefix='browser-large-'+str(identity)+'-'
    store.q("""INSERT INTO crm_shopify_checkouts(checkout_key,shop,source_event_id,created_at,activity_at,status)
      SELECT %s||i::text,'fixture.myshopify.com','synthetic-browser-large',now()-interval '400 days',now()-interval '400 days','OPEN'
      FROM generate_series(1,5000) i ON CONFLICT DO NOTHING""",(prefix,))
    return objects,customers

def configure(store,shop,identity):
    os.environ['SHOPIFY_STORE_DOMAIN']='fixture.myshopify.com'
    objects,customers=setup(store,identity)
    shop.checkout.side_effect=lambda identity,**_:deepcopy(objects.get(identity))
    shop.customer.side_effect=lambda identity,**_:deepcopy(customers.get(identity))
    # Merely opening/filtering analytics must not issue Shopify list calls.
    shop.query.side_effect=AssertionError('Unexpected Shopify analytics read')
