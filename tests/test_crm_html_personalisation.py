"""Synthetic recipient and mocked transport coverage for the shared renderer."""
from copy import deepcopy
from unittest import TestCase,skipUnless
from unittest.mock import Mock,patch
import os
import uuid
from crm_personalisation import render,present,wanted,html_values
from crm_middle_sections import commit_middle
from tests.test_crm_simple_editor import document
from tests.test_crm_send_flow import CFG,LIVE


def authored(source='<p>Hello {{first_name}}, your {{product_name}} awaits.</p>'):
    doc=document()
    commit_middle(doc,[dict(id='personal',type='html',visible=True,html_number=1,html=source)])
    return doc


class HtmlPersonalisationTests(TestCase):
    def test_same_engine_all_approved_fields_and_source_preservation(self):
        doc=authored('<table><tr><td style="color:#C6A044"><img alt="{{first_name}}" src="https://example.com/art.png"><a href="https://example.com/art">{{first_name}} / {{product_name}} / {{short_product_name}} / {{sport_category}} / {{edition_number}}</a></td></tr></table>')
        before=deepcopy(doc)
        facts=dict(first_name='Anne & Jo',product_name='<img src=x onerror=evil()>',short_product_name='A "quote"',sport_category='NBA',edition_number='#028/100')
        out=render(doc,facts,trigger='post_purchase')['custom_html']
        self.assertIn('Anne &amp; Jo',out);self.assertIn('&lt;img src=x onerror=evil()&gt;',out)
        self.assertIn('A &quot;quote&quot;',out);self.assertIn('style="color:#C6A044"',out)
        self.assertIn('href="https://example.com/art"',out);self.assertIn('src="https://example.com/art.png"',out)
        self.assertEqual(doc,before);self.assertTrue(present(doc))
        self.assertEqual(wanted(doc),set(facts))

    def test_missing_names_and_unsupported_tokens(self):
        for value in ('',None,'null','{{first_name}}','<script>bad</script>'):
            self.assertIn('Hello there,',render(authored(),{'first_name':value})['custom_html'])
        for token in ('{{frist_name}}','{{email}}','{{first_name | upcase}}','{{first_name','{% bad %}'):
            with self.subTest(token=token),self.assertRaisesRegex(ValueError,'Unresolved template variable'):
                render(authored('<p>'+token+'</p>'),{'first_name':'Ada'})
        self.assertIn('your selected artwork',render(authored(),{})['custom_html'])

    def test_subject_rules_unchanged_and_html_natural_fallback(self):
        doc=authored();doc['content'].update(subject='{{first_name}}, your artwork',preheader='Hello {{first_name}}')
        result=render(doc,{})
        self.assertEqual(result['content']['subject'],'Your artwork')
        self.assertEqual(result['content']['preheader'],'Explore your chosen artwork and current availability.')
        self.assertIn('Hello there,',result['custom_html'])

    def test_all_automation_live_paths_recipient_gate_and_no_reuse(self):
        from crm_automation_runtime import render as live
        doc=authored();original=deepcopy(doc)
        for kind in ('abandoned','welcome','post_purchase','fulfilled','win_back'):
            outputs=[]
            for identity,name in (('1','Ada'),('2','Grace'),('3','')):
                customer={'id':'gid://shopify/Customer/'+identity,'firstName':name}
                row={'id':str(uuid.uuid4()),'shopify_customer_id':customer['id']}
                context={'_customer':customer}
                content={'document':doc,'trigger':kind,'render_settings':CFG}
                with patch.dict('os.environ',LIVE),patch('crm_campaign_send.production_checks',return_value={'ready':True}):
                    message=live(content,row,'https://example.test/unsubscribe',context)
                    self.assertIn('Hello '+(name or 'there')+',',message['html']);self.assertNotIn('{{',message['html'])
                    with self.assertRaisesRegex(ValueError,'recipient context'):
                        live(content,{**row,'shopify_customer_id':'other'},'https://example.test/unsubscribe',context)
                    outputs.append(message['html'])
            self.assertNotIn('Grace',outputs[0]);self.assertNotIn('Ada',outputs[1]);self.assertEqual(doc,original)

    def test_campaign_preview_cache_keys_actual_customer_and_unknown_stays_error(self):
        from crm_local_preview import model
        store=Mock(email_mode='campaign');state={}
        store.q.side_effect=lambda sql,args,one:dict(profile=dict(id=args[0],firstName={'1':'Ada','2':'Grace'}[args[0]]))
        doc=authored();original=deepcopy(doc)
        with patch('streamlit.session_state',state):
            for cid,name in (('1','Ada'),('2','Grace'),('1','Ada')):
                state['_smart_preview_customer']=cid
                result=model(doc,CFG,store)
                self.assertEqual(result['errors'],{})
                self.assertIn('Hello '+name,result['resolved']['personal']['html'])
                self.assertEqual(result['personalisation']['first_name'],name)
            invalid=model(authored('<p>{{frist_name}}</p>'),CFG,store)
            self.assertIn('Unresolved template variable',invalid['errors']['personal'])
        self.assertEqual(doc,original)

    def test_checkout_preview_keeps_personalisation_with_legacy_cart(self):
        from crm_checkout_preview import document as preview
        from crm_abandoned_checkout import context
        from tests.test_crm_abandoned_checkout import checkout
        from tests.test_crm_checkout_preview_fallback import LEGACY
        data=context(checkout());data['personalisation']={'first_name':'Ada'}
        doc=authored('<p>Hello {{ first_name }}</p><img src="https://example.com/preserved.png" alt="For {{first_name}}">'+LEGACY)
        rendered,_=preview(doc,data)
        self.assertIn('Hello Ada',rendered['custom_html']);self.assertNotIn('{{',rendered['custom_html'])
        self.assertIn('https://example.com/preserved.png',rendered['custom_html']);self.assertIn('For Ada',rendered['custom_html'])

    def test_publication_validates_without_rewriting_the_authored_document(self):
        from crm_abandoned_checkout import publication_document
        from tests.test_crm_abandoned_checkout import native_document
        doc=native_document();doc['middle_sections'][0]['html']='<p>Hello {{first_name}}</p>'
        doc['custom_html']=doc['middle_sections'][0]['html'];original=deepcopy(doc)
        result=publication_document(doc,'abandoned')
        self.assertIn('Hello there',str(result));self.assertEqual(doc,original)


@skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable SQL required')
class CampaignPersonalisationTests(TestCase):
    def test_manual_campaign_test_uses_verified_recipient_and_preserves_saved_source(self):
        from tests.test_crm_send_flow import SendFlowTests
        from tests.crm_fixtures import TestRecipientShop
        from tests.test_crm_resend_marketing import ENV
        from tests.test_crm import ADMIN
        from crm_campaign_send import send_test
        case=SendFlowTests();case.setUp()
        try:
            editor=case.editor();editor['document']=authored('<p>Hello {{first_name}}</p>')
            source=deepcopy(editor['document']);shop=TestRecipientShop();lookup=shop.customers
            def named(**kw):
                result=lookup(**kw);result['nodes'][0]['firstName']='Test Ada';return result
            shop.customers=named
            with patch('crm_test_recipient.Shopify',return_value=shop):
                send_test(case.store,ADMIN,editor,'internal@example.test',str(uuid.uuid4()),env=ENV,session=case.provider)
            message=case.provider.post.call_args.kwargs['json']
            self.assertIn('Hello Test Ada',message['html']);self.assertNotIn('{{',message['html'])
            saved=case.store.draft(editor['id'])['document']
            self.assertEqual(saved['custom_html'],source['custom_html'])
        finally:case.doCleanups()

    def test_campaign_preparation_freezes_distinct_recipient_html_and_headers(self):
        from tests.test_crm_batch_dispatch import DispatchTests,dispatch
        from tests.test_crm_campaign_v2 import profile
        case=DispatchTests();case.setUp();doc=authored('<p>Hello {{first_name}}</p><a href="https://example.com/art">Explore</a>')
        doc['content'].update(subject='Hello {{first_name}}',preheader='For {{first_name}}')
        names=iter(['Ada','Grace'])
        def named(*args,**kwargs):return {**profile(*args,**kwargs),'firstName':next(names)}
        try:
            with patch('tests.test_crm_batch_dispatch.document',return_value=doc),patch('tests.test_crm_batch_dispatch.profile',side_effect=named):identity=case.queue(2)
            self.assertTrue(dispatch(case.engine))
            messages=case.transport.calls[-1][1]
            self.assertEqual({m['subject'] for m in messages},{'Hello Ada','Hello Grace'})
            for message in messages:
                name=message['subject'].split()[-1]
                self.assertIn('Hello '+name,message['html']);self.assertIn('For '+name,message['html'])
                self.assertNotIn('Grace' if name=='Ada' else 'Ada',message['html'])
                self.assertNotIn('{{',message['html'])
            self.assertIn('{{first_name}}',doc['custom_html'])
        finally:case.tearDown();case.doCleanups()
