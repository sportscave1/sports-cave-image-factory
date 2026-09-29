"""Modular authoring, read-only facts, renderer and durable test snapshots."""
from copy import deepcopy
from contextlib import contextmanager
import json
import os
import unittest
import uuid
from unittest.mock import Mock, patch

from crm_catalogue import Catalogue, edition_for, catalogue_html, product_issues, refresh_catalogues, FACTS_QUERY
from crm_middle_sections import middle_sections, apply_event, commit_middle, validate_middle
from crm_campaign_content import render_campaign, validate_document, preflight, settings
from crm_preview_cache import preview
from tests.test_crm_campaign_sections import sectioned
from tests.test_crm_campaigns_v1 import ADMIN, ENV


def node(i=1):
    return {'id':f'gid://shopify/Product/{i}','handle':f'art-{i}','title':f'Artwork {i}','status':'ACTIVE',
            'onlineStoreUrl':f'https://www.sportscaveshop.com/products/art-{i}',
            'featuredMedia':{'image':{'url':'https://cdn.shopify.com/art.jpg','altText':'Art'}},
            'contextualPricing':{'minVariantPricing':{'price':{'amount':'85.00','currencyCode':'AUD'},
             'compareAtPrice':{'amount':'110.00','currencyCode':'AUD'}}}}


def edition(i=1):
    return {'shopify_product_id':str(i),'shopify_handle':f'art-{i}','edition_total':100,
            'next_edition_number':37,'sold_count':36,'remaining_count':64,'active':True,'status':'active'}


def service():
    wire=Mock()
    wire.query.side_effect=lambda query,variables,*a:{'nodes':[node(int(i.rsplit('/',1)[-1])) for i in variables['ids']]}
    reader=Mock(side_effect=lambda **kw:[edition(int(i.rsplit('/',1)[-1])) for i in kw['product_ids']])
    return Catalogue(wire,edition_reader=reader)


def event(doc,action,**kw):
    apply_event(doc,dict(type=action,base=[s['id'] for s in middle_sections(doc)],**kw))


def catalogue_doc():
    doc=sectioned();event(doc,'add',kind='catalogue')
    doc['middle_sections'][-1]['products']=service().resolve([node()['id'],node(2)['id']])
    return doc


class ModularTests(unittest.TestCase):
    def test_legacy_body_is_exact_first_html_no_catalogue_no_render_change(self):
        doc=sectioned();doc['custom_html']='\r\n<table><tr><td>Original body</td></tr></table>\n '
        before=render_campaign(doc)
        items=middle_sections(doc)
        self.assertEqual(len(items),1);self.assertEqual(items[0]['html'],doc['custom_html'])
        self.assertEqual(items[0]['html_number'],1)
        self.assertNotIn('middle_sections',doc)
        commit_middle(doc,items)
        self.assertEqual(render_campaign(doc),before)

    def test_middle_order_visibility_and_identity_keep_header_footer_fixed(self):
        doc=sectioned();headerfooter=deepcopy(doc['html_sections'])
        event(doc,'add',kind='catalogue');event(doc,'add',kind='html');event(doc,'add',kind='catalogue')
        sections=doc['middle_sections'];self.assertEqual([s.get('html_number') for s in sections],[1,None,2,None])
        event(doc,'html',id=sections[2]['id'],html='<p>Second section</p>')
        event(doc,'visible',id=sections[0]['id'],visible=False)
        ids=[s['id'] for s in doc['middle_sections']]
        event(doc,'order',ids=ids[::-1])
        self.assertEqual(doc['html_sections'],headerfooter)
        rendered=render_campaign(doc)
        self.assertNotIn('A collector moment',rendered['html']);self.assertIn('Second section',rendered['html'])
        event(doc,'visible',id='html-1',visible=True)
        self.assertIn('A collector moment',render_campaign(doc)['html'])
        for action in ({'type':'order','ids':['header',*ids,'footer']},{'type':'visible','id':'footer','visible':False},
                       {'type':'remove','id':'html-1','confirmed':True},{'type':'add','kind':'footer'}):
            with self.assertRaises(ValueError):apply_event(doc,{'base':[s['id'] for s in doc['middle_sections']],**action})

    def test_existing_large_html_budget_is_not_halved_by_compatibility_mirror(self):
        doc=sectioned();doc['custom_html']='<p>'+'Collector artwork. '*3600+'</p>'
        validate_document(doc);commit_middle(doc,middle_sections(doc));validate_document(doc)
        doc['custom_html']='different'
        with self.assertRaisesRegex(ValueError,'compatibility source'):validate_document(doc)

    def test_remove_requires_confirmation_and_numbering_does_not_count_catalogues(self):
        doc=sectioned();event(doc,'add',kind='catalogue');event(doc,'add',kind='html');event(doc,'add',kind='html')
        second=doc['middle_sections'][2]['id']
        with self.assertRaises(ValueError):event(doc,'remove',id=second)
        event(doc,'remove',id=second,confirmed=True);event(doc,'add',kind='html')
        self.assertEqual([s.get('html_number') for s in doc['middle_sections']],[1,None,3,4])

    def test_catalogue_visibility_product_order_and_removal(self):
        doc=catalogue_doc();s=doc['middle_sections'][-1];identity=s['id'];ids=[p['id'] for p in s['products']]
        event(doc,'product_order',id=identity,ids=ids[::-1])
        output=render_campaign(doc)['html'];self.assertLess(output.index('Artwork 2'),output.index('Artwork 1'))
        event(doc,'visible',id=identity,visible=False)
        self.assertNotIn('Artwork 2',render_campaign(doc)['html']);self.assertEqual(len(doc['middle_sections'][-1]['products']),2)
        event(doc,'visible',id=identity,visible=True);event(doc,'product_remove',id=identity,product_id=ids[0])
        self.assertEqual([p['id'] for p in doc['middle_sections'][-1]['products']],[ids[1]])

    def test_catalogue_render_facts_plaintext_responsive_safe_and_not_allocated(self):
        doc=catalogue_doc();output=render_campaign(doc)
        for text in ('Artwork 1','100 WORLDWIDE','#037 / 100','Only 64 remaining','A$85.00','A$110.00','View the Edition'):
            self.assertIn(text,output['html']);self.assertIn(text,output['text'])
        self.assertNotIn('Your edition',output['html'])
        self.assertIn('class="sc-stack"',output['html']);self.assertIn('@media only screen',output['html'])
        self.assertIn('width="50%"',output['html'])
        doc['middle_sections'][-1]['settings']['columns']=1
        self.assertIn('width="100%"',catalogue_html(doc['middle_sections'][-1]))

    def test_untrusted_fields_unsafe_assets_and_missing_editions(self):
        doc=catalogue_doc();p=doc['middle_sections'][-1]['products'][0]
        p.update(title='<script>alert(1)</script>',edition=None)
        output=render_campaign(doc)
        self.assertNotIn('<script>',output['html']);self.assertIn('&lt;script&gt;',output['html'])
        self.assertNotIn('Edition data not connected',output['html'])
        p['image']='javascript:alert(1)'
        self.assertTrue(product_issues(p,doc['middle_sections'][-1]['settings']))
        self.assertFalse(preflight(doc,ENV)['test_ready'])
        for source in ('http://unsafe.example/p','javascript:evil'):
            p['url']=source;self.assertNotIn(source,render_campaign(doc)['html'])

    def test_render_cache_changes_for_order_visibility_html_templates_and_facts(self):
        doc=catalogue_doc();state={}
        with patch('crm_preview_cache.render_campaign',wraps=render_campaign) as render:
            preview(state,doc,settings(ENV));preview(state,doc,settings(ENV))
            self.assertEqual(render.call_count,1)
            event(doc,'html',id='html-1',html='<p>New HTML</p>');preview(state,doc,settings(ENV))
            event(doc,'visible',id='html-1',visible=False);preview(state,doc,settings(ENV))
            doc['middle_sections'][-1]['products'][0]['edition']['next']=38;preview(state,doc,settings(ENV))
            self.assertEqual(render.call_count,4)

    def test_index_queries_are_paginated_readonly_and_parameterized(self):
        cur=Mock();cur.__enter__=Mock(return_value=cur);cur.__exit__=Mock(return_value=False)
        cur.fetchall.return_value=[dict(shopify_product_id=str(i),handle='art',title='Art',status='ACTIVE',image_url='https://cdn.shopify.com/a.jpg') for i in range(1,14)]
        conn=Mock();conn.__enter__=Mock(return_value=conn);conn.__exit__=Mock(return_value=False);conn.cursor.return_value=cur
        shop=Mock();reader=Catalogue(shop,connect=lambda:conn)
        result=reader.search("Brock'",12)
        self.assertTrue(result['more']);self.assertEqual(len(result['rows']),12)
        statements=cur.execute.call_args_list
        self.assertEqual(statements[0].args[0],'SET TRANSACTION READ ONLY')
        self.assertIn('LIMIT 13 OFFSET %s',statements[-1].args[0]);self.assertEqual(statements[-1].args[1],("Brock'",True,12))
        shop.query.assert_not_called()

    def test_live_resolution_uses_canonical_ids_and_edition_ledger_not_metafields(self):
        svc=service();p=svc.resolve([node()['id']])[0]
        self.assertEqual((p['price'],p['compare_at'],p['edition']['next'],p['edition']['remaining']),('85.00','110.00',37,64))
        self.assertEqual(svc.edition_reader.call_args.kwargs['handles'],['art-1'])
        self.assertEqual(edition_for(p,[{**edition(), 'shopify_product_id':''}]),p['edition'])
        for rows in ([],[edition(99)], [edition(),edition()], [{**edition(),'allocation_blocked':True}], [{**edition(),'next_edition_number':None}]):
            self.assertIsNone(edition_for(p,rows))
        self.assertNotIn('metafield',FACTS_QUERY)

    def test_fresh_resolution_missing_editions_market_and_secret_url(self):
        svc=service();n=node();n['onlineStoreUrl']='https://example.com/p?token=PRIVATE'
        svc.shop.query.side_effect=None;svc.shop.query.return_value={'nodes':[n]}
        svc.edition_reader.side_effect=RuntimeError('PRIVATE')
        p=svc.resolve([n['id']],'US',fresh=True)[0]
        self.assertEqual(svc.shop.query.call_args.args[1]['country'],'US')
        self.assertEqual(p['url'],'');self.assertIsNone(p['edition']);self.assertNotIn('PRIVATE',json.dumps(p))

    def test_refresh_is_copy_and_hidden_catalogue_does_not_fetch(self):
        doc=catalogue_doc();before=deepcopy(doc);svc=service()
        refreshed=refresh_catalogues(doc,svc);self.assertEqual(doc,before);self.assertIsNot(refreshed,doc)
        event(doc,'visible',id=doc['middle_sections'][-1]['id'],visible=False);svc.shop.reset_mock()
        refresh_catalogues(doc,svc);svc.shop.query.assert_not_called()

    def test_canonical_edition_read_filters_ids_handles_without_schema_or_writes(self):
        import supabase_backend as backend
        cur=Mock();cur.fetchall.return_value=[]
        def read(operation,fn):return fn(cur),{'recovered':False}
        with patch.object(backend,'_run_read_operation',side_effect=read),patch.object(backend,'ensure_schema',side_effect=AssertionError('No schema writes')):
            backend.list_edition_products_read_only(product_ids=[node()['id']],handles=['art-1'])
        sql,args=cur.execute.call_args.args
        self.assertIn('= ANY(%s)',sql);self.assertEqual(args[:2],(['1'],['art-1']))
        self.assertNotRegex(sql.upper(),r'\b(UPDATE|INSERT|DELETE|CREATE|ALTER)\b')

    def test_brand_new_page_does_not_load_product_index_or_facts(self):
        from streamlit.testing.v1 import AppTest
        from tests.test_crm_ui import SCRIPT
        if os.getenv('CRM_TEST_POSTGRES')!='1':self.skipTest('Disposable SQL required')
        with patch.object(Catalogue,'search',side_effect=AssertionError('Index must be lazy')),patch.object(Catalogue,'resolve',side_effect=AssertionError('Facts must be lazy')):
            at=AppTest.from_string(SCRIPT);at.session_state['route']='CRM Campaigns';at.run(timeout=20)
            self.assertFalse(at.exception)
            self.assertNotIn('middle_sections',at.session_state['campaign_editor']['document'])

    def test_product_picker_selection_and_cancel_use_local_basket(self):
        from streamlit.testing.v1 import AppTest
        script='''
import streamlit as st
from tests.test_crm_modular_catalogue import catalogue_doc,service
from crm_section_ui import product_picker
doc=st.session_state.setdefault('doc',catalogue_doc())
st.session_state.setdefault('pick_generation','fixture')
svc=service()
svc.search=lambda *a:{'rows':svc.resolve(['gid://shopify/Product/1','gid://shopify/Product/2']),'more':False}
if st.button('Pick'):st.session_state['open']=True
if st.session_state.get('open'):product_picker(doc,doc['middle_sections'][-1]['id'],svc,'pick_')
'''
        at=AppTest.from_string(script).run()
        next(b for b in at.button if b.label=='Pick').click().run()
        self.assertFalse(at.exception)
        next(c for c in at.checkbox if c.label=='Select Artwork 2').uncheck().run()
        next(b for b in at.button if b.label=='Cancel').click().run()
        self.assertEqual(len(at.session_state['doc']['middle_sections'][-1]['products']),2)
        next(b for b in at.button if b.label=='Pick').click().run()
        next(c for c in at.checkbox if c.label=='Select Artwork 2').uncheck().run()
        next(b for b in at.button if b.label=='Add selected').click().run()
        self.assertFalse(at.exception)
        self.assertEqual([p['id'] for p in at.session_state['doc']['middle_sections'][-1]['products']],[node()['id']])


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Requires disposable SQL fixture')
class ModularPersistenceTests(unittest.TestCase):
    def setUp(self):
        from crm_campaign_store import CampaignStore
        from tests.crm_db_fixture import connect
        self.store=CampaignStore(connect)

    def test_json_order_hidden_settings_snapshots_history_duplicate_and_template(self):
        doc=catalogue_doc();event(doc,'add',kind='html');event(doc,'visible',id='html-1',visible=False)
        ids=[s['id'] for s in doc['middle_sections']];event(doc,'order',ids=ids[::-1])
        row=self.store.save(ADMIN,'Modular persistence',doc,env=ENV)
        self.assertEqual(self.store.draft(row['id'])['document'],doc)
        duplicate=self.store.duplicate(ADMIN,row['id']);self.assertEqual(duplicate['document']['middle_sections'],doc['middle_sections'])
        template=self.store.save_design(ADMIN,'Modular template',doc)
        self.assertEqual(self.store.template_document(template)['middle_sections'],doc['middle_sections'])

    def test_outbound_snapshot_before_transport_and_duplicate_attempt_never_resends(self):
        doc=catalogue_doc();row=self.store.save(ADMIN,'Modular test',doc,env=ENV)
        setting=self.store.setting('sending')
        self.store.save_setting(ADMIN,'sending',{'internal_recipients':['manual@example.test'],'smart_hours':16},setting['version'])
        operation=str(uuid.uuid4());wire=Mock()
        def sent(*a,**kw):
            history=self.store.q("SELECT after_value FROM crm_campaign_history WHERE campaign_id=%s AND action='campaign_test_snapshot'",(row['id'],))
            self.assertEqual(history[-1]['after_value']['outbound_snapshot']['rendered']['html'],kw['json']['html'])
            return Mock(status_code=200,json=lambda:{'id':str(uuid.uuid4())})
        wire.post.side_effect=sent
        facts=service()
        with patch('crm_catalogue.Catalogue',return_value=facts),patch('crm_resend_marketing._audit',return_value=True),patch('requests.sessions.Session.request',side_effect=AssertionError('No external I/O')):
            self.store.test_campaign(ADMIN,row['id'],row['version'],recipient='manual@example.test',confirmed=True,operation_id=operation,env=ENV,session=wire)
            # Tomorrow's edition cursor must neither mutate history nor make an
            # already accepted operation send again.
            facts.edition_reader.side_effect=lambda **kw:[{**edition(),'next_edition_number':42}]
            self.store.test_campaign(ADMIN,row['id'],row['version'],recipient='manual@example.test',confirmed=True,operation_id=operation,env=ENV,session=wire)
        wire.post.assert_called_once();self.assertEqual(facts.shop.query.call_count,1)
        history=self.store.q("SELECT after_value FROM crm_campaign_history WHERE campaign_id=%s AND action='campaign_test_snapshot'",(row['id'],))
        self.assertEqual(history[-1]['after_value']['outbound_snapshot']['sections'][-1]['products'][0]['edition']['next'],37)

    def test_changed_current_facts_block_test_until_review_no_writes_to_editions(self):
        doc=catalogue_doc();row=self.store.save(ADMIN,'Changed facts',doc,env=ENV)
        setting=self.store.setting('sending');self.store.save_setting(ADMIN,'sending',{'internal_recipients':['manual@example.test'],'smart_hours':16},setting['version'])
        current=deepcopy(doc);current['middle_sections'][-1]['products'][0]['edition']['next']=42
        with patch('crm_catalogue.refresh_catalogues',return_value=current),patch('crm_resend_marketing._send_admin_email') as send:
            with self.assertRaisesRegex(ValueError,'facts changed'):
                self.store.test_campaign(ADMIN,row['id'],row['version'],recipient='manual@example.test',confirmed=True,operation_id=str(uuid.uuid4()),env=ENV)
            send.assert_not_called()
        self.assertEqual(self.store.draft(row['id'])['document'],doc)

    def test_fact_lookup_failure_blocks_send_without_sensitive_exception(self):
        doc=catalogue_doc();row=self.store.save(ADMIN,'Unavailable facts',doc,env=ENV)
        setting=self.store.setting('sending');self.store.save_setting(ADMIN,'sending',{'internal_recipients':['manual@example.test'],'smart_hours':16},setting['version'])
        with patch('crm_catalogue.refresh_catalogues',side_effect=RuntimeError('private-token')),patch('crm_resend_marketing._send_admin_email') as send:
            with self.assertRaisesRegex(ValueError,'cannot be verified') as failure:
                self.store.test_campaign(ADMIN,row['id'],row['version'],recipient='manual@example.test',confirmed=True,operation_id=str(uuid.uuid4()),env=ENV)
            self.assertNotIn('private-token',str(failure.exception));send.assert_not_called()
