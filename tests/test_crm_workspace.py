"""Campaigns-first safety tests. Synthetic authority and loopback database only."""
from copy import deepcopy
from datetime import timedelta
import base64
import json
import os
import time
import unittest
import uuid
from unittest.mock import Mock,patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from svix.webhooks import Webhook
from crm_audience import evaluate_profiles,selection_page
from crm_campaign_content import new_document,render_campaign,preflight,html_budget,validate_document
from crm_campaign_store import CampaignStore
from crm_email_blocks import block,starter,validate_blocks
from crm_logic import now,recipient_hash
from crm_navigation import SIDEBAR_ROUTES,DEFAULT_ROUTE,navigation_allowed
from crm_prompt_factory import generate,parse,proposals,apply
from crm_shopify import Shopify,gid
from crm_tracking import campaign_link,asset_url,public_https
from crm_attribution import association,refresh_page
from crm_webhooks import receive_resend,unsubscribe
from crm_onsite import config,validate_event,pixel_code
from crm_workspace_store import validate_setting
from crm_resend import Config
from tests.crm_db_fixture import connect
from tests.crm_fixtures import ShopifyFixture
from tests.test_crm import ADMIN,WORKER
from tests.test_crm_resend_marketing import ENV


def ready():
    doc=new_document();doc['blocks']=[block('heading',text='A collector moment'),block('text',text='Discover the collection.'),block('button',url='https://www.sportscaveshop.com/collections/all')]
    doc['content'].update(subject='The collector edit',preheader='A new perspective');doc['copy_reviewed']=True
    return doc


def profile(identity,address,state='SUBSCRIBED'):
    return {'id':gid(identity),'email':address,'emailMarketingConsent':{'marketingState':state},'numberOfOrders':'10'}


class WorkspaceUnitTests(unittest.TestCase):
    def test_navigation_alias_permissions(self):
        import os_accounts
        self.assertEqual(SIDEBAR_ROUTES,('CRM Campaigns','CRM Automations','CRM Settings'));self.assertEqual(DEFAULT_ROUTE,'CRM Campaigns')
        self.assertTrue(os_accounts.can_access_page(WORKER,'CRM Customers'));self.assertTrue(os_accounts.can_access_page(WORKER,'CRM Settings'))
        self.assertFalse(os_accounts.can_access_page(WORKER,'CRM Campaigns'))

    def test_unsaved_navigation_does_not_discard_draft(self):
        state={'campaign_saved':{'name':'Saved','document':ready()}}
        state['campaign_editor']=deepcopy(state['campaign_saved'])
        self.assertTrue(navigation_allowed(state,'CRM Campaigns','CRM Settings'))
        state['campaign_editor']['name']='Pending edit'
        self.assertFalse(navigation_allowed(state,'CRM Campaigns','CRM Settings'))
        self.assertEqual(state['crm_requested_route'],'CRM Settings')
        self.assertEqual(state['campaign_editor']['name'],'Pending edit')

    def test_market_currency_never_falls_back_to_australian_price(self):
        shop=Shopify(Mock());shop.query=Mock(return_value={'productVariant':{'contextualPricing':{'price':{'amount':'179','currencyCode':'AUD'}}}})
        self.assertIsNone(shop.campaign_price(gid(1,'ProductVariant'),'US'))
        self.assertEqual(shop.campaign_price(gid(1,'ProductVariant'),'AU')['amount'],'179')
        shop.query.reset_mock();self.assertIsNone(shop.campaign_price(gid(1,'ProductVariant'),'Global'));shop.query.assert_not_called()

    def test_shopify_derivative_is_public_email_safe_and_proportional(self):
        derivative='https://cdn.shopify.com/art.avif?width=1000&format=jpg'
        image=Shopify.email_image({'url':'https://cdn.shopify.com/art.avif','emailUrl':derivative})
        self.assertEqual(image['url'],derivative);self.assertTrue(asset_url(image['url']))
        self.assertFalse(asset_url('https://example.test/art.avif?format=jpg'))
        from crm_shopify import CAMPAIGN_IMAGES
        self.assertIn('maxWidth:1000,preferredContentType:JPG',CAMPAIGN_IMAGES);self.assertNotIn('crop:',CAMPAIGN_IMAGES)

    def test_connection_status_is_explicit_read_only_and_redacted(self):
        wire=Mock(return_value={'shop':{'id':gid(1,'Shop')},'currentAppInstallation':{'accessScopes':[{'handle':'read_products'}]}})
        shop=Shopify(wire);wire.assert_not_called()
        self.assertEqual(shop.campaign_connection(),{'connected':True,'scopes':['read_products']})
        wire.assert_called_once();self.assertNotIn('mutation',wire.call_args.args[0])

    def test_email_brand_presets_keep_readable_footer_and_plain_text(self):
        from crm_campaign_content import settings
        from crm_workspace_store import DEFAULTS
        value={**deepcopy(DEFAULTS['branding']),'font':'Georgia','button_style':'Outlined black'}
        validate_setting('branding',value)
        rendered=render_campaign(ready(),{**settings(ENV),**value})
        self.assertIn('Georgia,Times,serif',rendered['html']);self.assertIn('bgcolor="#fff"',rendered['html'])
        self.assertIn('Unsubscribe',rendered['html']);self.assertIn('Unsubscribe',rendered['text'])
        with self.assertRaises(ValueError):validate_setting('branding',{**value,'button_style':'javascript:alert(1)'})

    def test_conflicting_duplicate_consent_excluded_and_totals_exclusive(self):
        rows=[profile(1,'a@example.test'),profile(2,'A@example.test','UNSUBSCRIBED'),profile(3,'b@example.test'),profile(4,'b@example.test'),profile(5,'c@example.test')]
        r=evaluate_profiles(rows,set(),set(),set(),set(),{recipient_hash('c@example.test')})
        self.assertEqual(r['eligible'],1);self.assertEqual(r['excluded'],{'conflicting_consent':2,'duplicate':1,'smart_sending':1})
        self.assertEqual(r['members'],r['eligible']+sum(r['excluded'].values()))
        r=evaluate_profiles(rows,set(),{recipient_hash('a@example.test')},set(),set(),set())
        self.assertEqual(r['excluded']['excluded_segment'],2)

    def test_multi_segment_union_exclusions_and_global_conflict_pass(self):
        wire=ShopifyFixture(4);wire.customers=[profile(1,'one@example.test'),profile(2,'one@example.test','PENDING'),profile(3,'three@example.test'),profile(4,'four@example.test')]
        shop=Mock();shop.members.side_effect=lambda identity,**kw:{'nodes':[wire.customers[0],wire.customers[2]] if identity.endswith('/1') else [wire.customers[2]],'pageInfo':{'hasNextPage':False}}
        shop.customers.return_value={'nodes':wire.customers,'pageInfo':{'hasNextPage':False}}
        store=Mock();store.active_suppression_hashes.return_value=(set(),set());store.recent_marketing_hashes.return_value=set()
        source=lambda i:{'kind':'Shopify','id':gid(i,'Segment'),'name':str(i)}
        audience={'kind':'Selection','name':'union','include':[source(1),source(2)],'exclude':[source(2)]}
        state=None
        for _ in range(4):state=selection_page(shop,store,audience,state)
        self.assertTrue(state['complete']);self.assertEqual(state['members'],2);self.assertEqual(state['eligible'],0)
        self.assertEqual(state['excluded'],{'excluded_segment':1,'conflicting_consent':1})

    def test_incomplete_shopify_and_history_unavailable_fail_closed(self):
        shop=Mock();shop.members.return_value={'nodes':[],'pageInfo':{},'complete':False}
        audience={'kind':'Selection','name':'x','include':[{'kind':'Shopify','id':gid(1,'Segment'),'name':'x'}],'exclude':[]}
        with self.assertRaisesRegex(ValueError,'incomplete'):selection_page(shop,Mock(),audience)
        shop.members.return_value={'nodes':[profile(1,'x@example.test')],'pageInfo':{}}
        state=selection_page(shop,Mock(),audience);self.assertFalse(state['complete'])
        shop.customers.return_value={'nodes':[],'pageInfo':{}}
        with self.assertRaisesRegex(ValueError,'could not be verified'):selection_page(shop,Mock(),audience,state)

    def test_block_renderer_footer_mobile_plain_text_no_script(self):
        doc=ready();doc['blocks'].insert(1,block('text',text='<script>alert(1)</script>'))
        products=[{'id':gid(i,'Product'),'title':'Art '+str(i),'url':'https://example.test/p/'+str(i),'image':'https://cdn.shopify.com/art.png','alt':'Art','market':'AU'} for i in (1,2)]
        doc['blocks'].append(block('product_grid',products=products))
        rendered=render_campaign(doc)
        self.assertNotIn('<script',rendered['html']);self.assertIn('sc-stack',rendered['html']);self.assertIn('max-width:600px',rendered['html']);self.assertIn('16px',rendered['html'])
        self.assertIn('Unsubscribe',rendered['html']);self.assertIn('Unsubscribe',rendered['text']);self.assertIn('Art 1',rendered['text'])
        self.assertNotIn('<img',render_campaign(doc,images_off=True)['html'])
        doc['blocks'].append({'id':'b_footer','type':'footer','text':'remove'})
        with self.assertRaises(ValueError):render_campaign(doc)

    def test_placeholders_alt_price_and_payload_size_block_tests(self):
        doc=ready();self.assertTrue(preflight(doc,ENV)['test_ready']);self.assertFalse(preflight(doc,ENV)['live_ready'])
        doc['blocks']=starter('New Editions');self.assertFalse(preflight(doc,ENV)['test_ready'])
        doc=ready();doc['blocks'].append(block('image',url='https://example.test/a.jpg'));self.assertFalse(preflight(doc,ENV)['test_ready'])
        self.assertTrue(html_budget('x'*96000)['review_required']);self.assertTrue(html_budget('x'*85000)['warning'])

    def test_urls_and_utm_are_safe_stable_and_contextual(self):
        key='sc_'+uuid.uuid4().hex
        url='https://sportscaveshop.com/products/art?variant=4#details'
        result=campaign_link(url,key,'b_one');self.assertIn('variant=4',result);self.assertTrue(result.endswith('#details'))
        self.assertEqual(campaign_link(result,key,'b_one'),result);self.assertIn('sc_test=1',result)
        for url in ('https://example.test/checkouts/x?key=secret','https://example.test/x?signature=abc','https://example.test/privacy','mailto:a@example.test'):
            self.assertEqual(campaign_link(url,key,'b_one'),url)
        for value in ('https://127.0.0.1/x.jpg','https://localhost/x.jpg','https://example.local/x.png','data:abc','http://a.com/a.png','https://a.com/x.svg','https://a.com/x.jpg?X-Amz-Signature=abc','https://user:pass@a.com/a.jpg'):
            self.assertFalse(asset_url(value))

    def test_versioned_prompt_proposals_only_apply_selected_copy(self):
        doc=ready();brief=generate(doc);self.assertIn('Unknown facts must be omitted',brief);self.assertNotIn('customer_id',brief)
        data={'schema_version':1,'subject_options':['One','Two','Three'],'preheader_options':['A','B','C'],'recommended':{'subject':'One','preheader':'A'},'copy':{k:'' for k in ('headline','intro','body','cta_label','closing','image_brief','alt')},'blocks':[{'id':doc['blocks'][0]['id'],'text':'New headline'}]}
        result=parse(json.dumps(data),doc);updated=apply(doc,result,['subject',doc['blocks'][0]['id']])
        self.assertEqual(updated['content']['subject'],'One');self.assertEqual(updated['content']['preheader'],doc['content']['preheader'])
        self.assertEqual(updated['audience'],doc['audience']);self.assertEqual(updated['blocks'][-1]['url'],doc['blocks'][-1]['url'])
        for key,value in (('footer','bad'),('sender','evil'),('mode','live'),('audience',[])):
            with self.assertRaises(ValueError):parse(json.dumps({**data,key:value}),doc)
        data['blocks'][0]['text']='<b>HTML</b>'
        with self.assertRaises(ValueError):parse(json.dumps(data),doc)

    def test_settings_no_secrets_and_admin_boundary(self):
        for val in ({'api_key':'secret'},{'CRM_MARKETING_ENABLED':True}):
            with self.assertRaises(ValueError):validate_setting('sending',val)
        with self.assertRaises(PermissionError):CampaignStore(Mock()).save_setting(WORKER,'prompts',{'default':'x'},0)

    def test_attribution_only_canonical_paid_order_and_last_utm(self):
        key='sc_'+uuid.uuid4().hex
        order={'id':gid(1,'Order'),'createdAt':now().isoformat(),'fullyPaid':True,'test':False,'cancelledAt':None,'netPaymentSet':{'shopMoney':{'amount':'249.00','currencyCode':'AUD'}},'customerJourneySummary':{'ready':True,'lastVisit':{'occurredAt':(now()-timedelta(hours=1)).isoformat(),'landingPage':'https://example.test/products/x','utmParameters':{'source':'sports_cave','medium':'email','campaign':key}}}}
        result,reason=association(order,key);self.assertTrue(result['eligible']);self.assertEqual(result['amount'],'249.00')
        order['cancelledAt']=now().isoformat();self.assertFalse(association(order,key)[0]['eligible'])
        order['customerJourneySummary']['lastVisit']['landingPage']+='?sc_test=1';self.assertEqual(association(order,key),(None,'internal_test'))
        order['customerJourneySummary']['ready']=False;self.assertEqual(association(order,key),(None,'journey_unavailable'))

    def test_pixel_config_default_off_and_no_pii_schema(self):
        cfg=config({'CRM_PUBLIC_BASE_URL':'https://hooks.example.test','CRM_WEBSITE_PIXEL_ID':'public_fixture_12345','CRM_WEBSITE_ALLOWED_ORIGINS':'https://shop.example.test'})
        self.assertFalse(cfg['enabled']);source=pixel_code(cfg);self.assertIn('"enabled": false',source);self.assertNotIn('window.top',source)
        payload={'pixel_id':cfg['pixel_id'],'event_id':'event-1','event_type':'page_viewed','session_ref':str(uuid.uuid4()),'campaign_key':'','product_ref':'','occurred_at':now().isoformat(),'test_context':True,'analytics_allowed':True,'marketing_allowed':True}
        validate_event(payload,cfg)
        for key,value in (('email','private@example.test'),('checkout',{'payment':'x'})):
            with self.assertRaises(ValueError):validate_event({**payload,key:value},cfg)
        with self.assertRaises(ValueError):validate_event({**payload,'analytics_allowed':False},cfg)


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Requires local fixture.')
class WorkspacePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.store=CampaignStore(connect)
        row=self.store.setting('sending');self.store.save_setting(ADMIN,'sending',{'internal_recipients':['internal@example.test'],'smart_hours':16},row['version'])
        self.campaign=self.store.save(ADMIN,'Workspace '+uuid.uuid4().hex[:8],ready(),env=ENV)
        self.provider_id=str(uuid.uuid4());self.wire=Mock();self.wire.post.return_value=Mock(status_code=200,json=lambda:{'id':self.provider_id})
        self.audit=patch('crm_resend_marketing._audit',return_value=True);self.audit.start();self.addCleanup(self.audit.stop)
        self.network=patch('requests.sessions.Session.request',side_effect=AssertionError('No real HTTP'));self.network.start();self.addCleanup(self.network.stop)

    def send(self,operation=None,recipient='internal@example.test'):
        return self.store.test_campaign(ADMIN,self.campaign['id'],self.campaign['version'],recipient=recipient,confirmed=True,operation_id=operation or str(uuid.uuid4()),env=ENV,session=self.wire)

    def test_allowlist_fail_closed_and_no_lists(self):
        for value in ('customer@example.test',['internal@example.test'],{'segment':'1'},'internal@example.test,second@example.test'):
            with self.assertRaises((ValueError,RuntimeError)):self.send(recipient=value)
        self.wire.post.assert_not_called()
        row=self.store.setting('sending');self.store.save_setting(ADMIN,'sending',{'internal_recipients':[],'smart_hours':16},row['version'])
        with self.assertRaises(ValueError):self.send()

    def test_durable_idempotency_and_test_not_frequency_history(self):
        operation=str(uuid.uuid4());first=self.send(operation);second=self.send(operation)
        self.wire.post.assert_called_once();self.assertEqual(first['message_id'],second['message_id'])
        self.assertNotIn(recipient_hash('internal@example.test'),self.store.recent_marketing_hashes())
        report=self.store.delivery_report(self.campaign['id']);self.assertEqual(report['counts']['total'],1);self.assertEqual(report['counts']['accepted'],1);self.assertEqual(report['events'],{})

    def marketing_receipt(self,*,test=False):
        template=self.store.save_design(ADMIN,'Receipt fixture',ready())
        address=uuid.uuid4().hex+'@example.test';hashed=recipient_hash(address)
        row=self.store.enqueue('workspace-'+uuid.uuid4().hex,gid(909),hashed,template,test_recipient=address if test else None)
        provider=str(uuid.uuid4())
        self.store.q("UPDATE crm_marketing_sends SET status='ACCEPTED',provider_email_id=%s,first_submitted_at=now() WHERE id=%s",(provider,row['id']))
        return row,provider,hashed

    def test_smart_sending_uses_actual_marketing_receipts_and_window(self):
        row,provider,hashed=self.marketing_receipt()
        self.assertIn(hashed,self.store.recent_marketing_hashes());self.assertTrue(self.store.frequency_blocked(hashed))
        self.store.q("UPDATE crm_marketing_sends SET first_submitted_at=now()-interval '17 hours' WHERE id=%s",(row['id'],))
        self.assertNotIn(hashed,self.store.recent_marketing_hashes());self.assertFalse(self.store.frequency_blocked(hashed))
        row,provider,hashed=self.marketing_receipt(test=True)
        self.assertNotIn(hashed,self.store.recent_marketing_hashes());self.assertFalse(self.store.frequency_blocked(hashed))

    def test_only_verified_permanent_bounce_suppresses_and_sync_failure_keeps_it(self):
        from crm_consent_sync import reconcile_opt_out
        row,provider,hashed=self.marketing_receipt()
        def bounce(kind):
            receive_resend(self.store,'evt_'+uuid.uuid4().hex,{'type':'email.bounced','created_at':now().isoformat(),'data':{'email_id':provider,'bounce':{'type':kind}}})
        bounce('Transient');self.assertFalse(self.store.suppressed(None,hashed))
        bounce('Permanent');self.assertTrue(self.store.suppressed(None,hashed))
        writer=Mock();writer.unsubscribe_only.side_effect=RuntimeError('secret')
        self.assertEqual(reconcile_opt_out(self.store,hashed,writer),'NOT_ACTIVATED');writer.unsubscribe_only.assert_not_called()
        self.assertEqual(reconcile_opt_out(self.store,hashed,writer,approved=True),'PENDING')
        self.assertTrue(self.store.suppressed(None,hashed))
        writer.unsubscribe_only.side_effect=None;writer.unsubscribe_only.return_value=False
        self.assertEqual(reconcile_opt_out(self.store,hashed,writer,approved=True),'PENDING')
        writer.unsubscribe_only.return_value=True
        self.assertEqual(reconcile_opt_out(self.store,hashed,writer,approved=True),'SYNCED')
        self.store.suppress(hashed,None,'manual_unsubscribe','fixture')
        self.assertEqual(self.store.q('SELECT shopify_sync_state FROM crm_suppressions WHERE recipient_hash=%s',(hashed,),True)['shopify_sync_state'],'PENDING')

    def test_internal_test_token_cannot_opt_out_customer(self):
        from tests.test_crm import config as send_config
        row,provider,hashed=self.marketing_receipt(test=True);cfg=send_config()
        token=cfg.unsubscribe_url(row['id']).split('token=',1)[1]
        with self.assertRaises(ValueError):unsubscribe(self.store,cfg,token)
        self.assertFalse(self.store.suppressed(None,hashed))

    def test_attribution_idempotent_refunds_unrelated_orders_and_separate_currencies(self):
        key=self.campaign['document']['campaign_key'];prefix=int(uuid.uuid4().int%1000000000)
        def order(i,currency,amount):
            return {'id':gid(prefix+i,'Order'),'createdAt':now().isoformat(),'fullyPaid':True,'test':False,'cancelledAt':None,'netPaymentSet':{'shopMoney':{'amount':amount,'currencyCode':currency}},'customerJourneySummary':{'ready':True,'lastVisit':{'occurredAt':(now()-timedelta(hours=1)).isoformat(),'landingPage':'https://example.test/products/a','utmParameters':{'source':'sports_cave','medium':'email','campaign':key}}}}
        rows=[order(1,'AUD','100'),order(2,'USD','50'),order(3,'AUD','900')]
        rows[-1]['customerJourneySummary']['lastVisit']['utmParameters']['source']='unrelated'
        shop=Mock();shop.campaign_orders.return_value={'nodes':rows,'pageInfo':{}}
        for _ in range(2):self.assertTrue(refresh_page(self.store,shop,self.campaign,'2026-01-01','2026-12-31')['complete'])
        rows[0]['netPaymentSet']['shopMoney']['amount']='75'
        refresh_page(self.store,shop,self.campaign,'2026-01-01','2026-12-31')
        result=self.store.q('SELECT currency,sum(amount) AS amount,count(*) AS n FROM crm_order_attribution WHERE campaign_id=%s AND eligible=true GROUP BY currency',(self.campaign['id'],))
        self.assertEqual({r['currency']:float(r['amount']) for r in result},{'AUD':75,'USD':50});self.assertTrue(all(r['n']==1 for r in result))
        rows[0]['cancelledAt']=now().isoformat();refresh_page(self.store,shop,self.campaign,'2026-01-01','2026-12-31')
        self.assertEqual(len(self.store.q('SELECT * FROM crm_order_attribution WHERE campaign_id=%s AND eligible=true',(self.campaign['id'],))),1)

    def test_uncertain_send_never_automatically_retried(self):
        self.wire.post.side_effect=TimeoutError('secret should never escape');operation=str(uuid.uuid4())
        with self.assertRaises(RuntimeError) as caught:self.send(operation)
        self.assertNotIn('secret',str(caught.exception))
        with self.assertRaisesRegex(ValueError,'already attempted'):self.send(operation)
        self.wire.post.assert_called_once();self.assertEqual(self.store.test_history(self.campaign['id'])[0]['status'],'UNCERTAIN')

    def test_template_snapshot_optimistic_settings_and_recoverable_archive(self):
        template=self.store.save_design(ADMIN,'Template',self.campaign['document'])
        doc=self.store.template_document(template);doc['blocks'][0]['text']='Changed'
        self.store.save_design(ADMIN,'Template',doc,template['id'],template['version'])
        self.assertEqual(self.store.draft(self.campaign['id'])['document']['blocks'][0]['text'],'A collector moment')
        with self.assertRaises(ValueError):self.store.save_design(ADMIN,'Stale',doc,template['id'],template['version'])
        self.store.archive(ADMIN,self.campaign['id'],1);self.store.restore(ADMIN,self.campaign['id'],2)
        self.assertEqual(self.store.draft(self.campaign['id'])['status'],'DRAFT')
        setting=self.store.setting('prompts');self.store.save_setting(ADMIN,'prompts',{'default':'Fresh'},setting['version'])
        with self.assertRaises(ValueError):self.store.save_setting(ADMIN,'prompts',{'default':'Stale'},setting['version'])

    def test_early_verified_event_reconciled_and_duplicates_out_of_order(self):
        payload={'type':'email.delivered','created_at':now().isoformat(),'data':{'email_id':self.provider_id,'campaign_id':str(uuid.uuid4()),'to':['private@example.test']}}
        event='early_'+uuid.uuid4().hex;receive_resend(self.store,event,payload);receive_resend(self.store,event,payload)
        self.assertEqual(self.store.delivery_report(self.campaign['id'])['events'],{})
        self.send();receive_resend(self.store,'sent_'+uuid.uuid4().hex,{**payload,'type':'email.sent'})
        self.assertEqual(self.store.delivery_report(self.campaign['id'])['events']['email.delivered'],1)
        rows=self.store.q('SELECT * FROM crm_delivery_events WHERE event_id=%s',(event,));self.assertEqual(len(rows),1);self.assertNotIn('private',str(rows))

    def test_test_and_unrelated_bounces_cannot_suppress_customers(self):
        self.send()
        for provider in (self.provider_id,str(uuid.uuid4())):
            receive_resend(self.store,'bounce_'+uuid.uuid4().hex,{'type':'email.bounced','created_at':now().isoformat(),'data':{'email_id':provider,'to':['unique-protected@example.test'],'bounce':{'type':'Permanent'}}})
        self.assertFalse(self.store.suppressed(None,recipient_hash('unique-protected@example.test')))

    def test_rls_no_public_read_or_write(self):
        for table in ('crm_workspace_settings','crm_settings_history','crm_internal_tests','crm_delivery_events','crm_website_events','crm_order_attribution'):
            row=self.store.q("SELECT relrowsecurity FROM pg_class WHERE relname=%s",(table,),True);self.assertTrue(row['relrowsecurity'])
            self.assertFalse(self.store.q("SELECT has_table_privilege('anon',%s,'SELECT,INSERT,UPDATE,DELETE') AS allowed",(table,),True)['allowed'])

    def test_signed_webhook_endpoint_durable_and_raw_body(self):
        from crm_http import router
        app=FastAPI();app.include_router(router);client=TestClient(app)
        secret='whsec_'+base64.b64encode(b'fixture-signing-key-32-bytes-long!').decode()
        raw=json.dumps({'type':'email.delivered','created_at':now().isoformat(),'data':{'email_id':self.provider_id}})
        stamp=now();event='evt_'+uuid.uuid4().hex
        headers={'svix-id':event,'svix-timestamp':str(int(stamp.timestamp())),'svix-signature':Webhook(secret).sign(event,stamp,raw)}
        with patch.dict(os.environ,{'CRM_RESEND_WEBHOOK_SECRET':secret}),patch('crm_store.Store',return_value=self.store):
            self.assertEqual(client.post('/webhooks/resend/crm',content=raw,headers=headers).status_code,200)
            self.assertEqual(client.post('/webhooks/resend/crm',content=raw+' ',headers=headers).status_code,401)
            headers['svix-timestamp']=str(int(stamp.timestamp())-600)
            self.assertEqual(client.post('/webhooks/resend/crm',content=raw,headers=headers).status_code,401)

    def test_pixel_endpoint_default_off_cors_and_durable_dedupe(self):
        from crm_http import router
        app=FastAPI();app.include_router(router);client=TestClient(app)
        env={'CRM_WEBSITE_TRACKING_ENABLED':'true','CRM_WEBSITE_PIXEL_ID':'fixture_pixel_12345','CRM_WEBSITE_ALLOWED_ORIGINS':'https://shop.example.test'}
        body={'pixel_id':env['CRM_WEBSITE_PIXEL_ID'],'event_id':'event_'+uuid.uuid4().hex,'event_type':'checkout_completed','session_ref':str(uuid.uuid4()),'campaign_key':'','product_ref':'','occurred_at':now().isoformat(),'test_context':True,'analytics_allowed':True,'marketing_allowed':True}
        with patch.dict(os.environ,{},clear=True):self.assertEqual(client.post('/crm/tracking/events',json=body).status_code,404)
        with patch.dict(os.environ,env),patch('crm_store.Store',return_value=self.store):
            self.assertEqual(client.post('/crm/tracking/events',json=body,headers={'origin':'https://evil.example.test'}).status_code,403)
            headers={'origin':'https://shop.example.test'}
            self.assertEqual(client.options('/crm/tracking/events',headers=headers).status_code,204)
            self.assertEqual(client.post('/crm/tracking/events',json={**body,'marketing_allowed':False},headers=headers).status_code,400)
            response=client.post('/crm/tracking/events',json=body,headers=headers);self.assertEqual(response.status_code,202)
            self.assertEqual(client.post('/crm/tracking/events',json=body,headers=headers).status_code,202)
            self.assertEqual(len(self.store.q('SELECT * FROM crm_website_events WHERE event_id=%s',(body['event_id'],))),1)
        self.wire.post.assert_not_called()


if __name__=='__main__':unittest.main()
