"""Offline sizing, advisory assets, review/queue/delivery and compact UI checks."""
from copy import deepcopy
from concurrent.futures import Future
from pathlib import Path
import unittest
from unittest.mock import Mock,patch
from streamlit.testing.v1 import AppTest

import crm_email_size as size
from crm_campaign_send import production_checks,queue_campaign,review
from crm_campaign_content import render_campaign
from tests import test_crm_postal_setting_removal as postal_fixture
from tests.test_crm_send_flow import LIVE,CFG
from tests.test_crm import ADMIN
from tests.test_crm_campaign_loading import SCRIPT

IDENTITY='00000000-0000-0000-0000-000000000123'


class EmailSizeTests(unittest.TestCase):
    def setUp(self):
        fixture=postal_fixture.PostalSettingRemovalTests();fixture.setUp()
        self.doc=fixture.doc;self.cfg=fixture.cfg

    def oversized(self):
        # Source fits the existing compose cap; production tracking pushes the
        # actual outgoing HTML over the send budget.
        self.doc['custom_html']='<p>'+('x'*60000)+'</p>'+('<a href="https://www.sportscaveshop.com/collection">View</a>'*200)
        return self.doc

    def test_exact_unicode_utf8_and_separate_plain_text(self):
        report=size.analyze_rendered_email('<p>é🏆</p>','收藏')
        self.assertEqual(report['html_bytes'],len('<p>é🏆</p>'.encode('utf-8')))
        self.assertEqual(report['text_bytes'],6)
        self.assertEqual(report['html_kb'],report['html_bytes']/1024)

    def test_all_threshold_edges_and_clamping(self):
        for amount,status in ((0,'SAFE'),(size.SAFE_BYTES,'SAFE'),(size.SAFE_BYTES+1,'NEAR LIMIT'),
                              (size.LIMIT_BYTES,'NEAR LIMIT'),(size.LIMIT_BYTES+1,'TOO LARGE')):
            report=size.analyze_rendered_email('x'*amount,'')
            self.assertEqual(report['status'],status)
            self.assertEqual(report['percent'],min(100,amount/size.LIMIT_BYTES*100))
        self.assertIn('width:100.00%',size.meter_html(report))
        self.assertIn('aria-label="Email size',size.meter_html(report))

    def test_same_production_renderer_with_footer_tracking_and_unsubscribe(self):
        from crm_tracking import send_identity
        with patch('requests.sessions.Session.request',side_effect=AssertionError('No I/O')):
            expected=render_campaign(self.doc,self.cfg,production=True,
                unsubscribe_url=size.REPRESENTATIVE_UNSUBSCRIBE,campaign_id=IDENTITY,send_id=send_identity(IDENTITY))
            actual=size.render_production(self.doc,self.cfg,IDENTITY)
            report=size.campaign_size(self.doc,self.cfg,IDENTITY)
        self.assertEqual(actual,expected)
        self.assertEqual(report['production_html_bytes'],len(actual['html'].encode('utf-8')))
        self.assertIn('sc_campaign_id=',actual['html'])
        self.assertIn(CFG['postal'],actual['html'])
        self.assertIn(size.REPRESENTATIVE_UNSUBSCRIBE,actual['html'])
        self.doc['html_sections']['footer']+='<p>Extra footer text</p>'
        self.assertGreater(size.campaign_size(self.doc,self.cfg,IDENTITY)['html_bytes'],report['html_bytes'])

    def test_actual_unsubscribe_length_changes_measured_message(self):
        short=size.render_production(self.doc,self.cfg,IDENTITY,'https://example.test/unsubscribe')
        long=size.render_production(self.doc,self.cfg,IDENTITY,size.REPRESENTATIVE_UNSUBSCRIBE)
        self.assertGreater(len(long['html'].encode()),len(short['html'].encode()))

    def test_remote_assets_deduplicate_and_do_not_inflate_clipping_size(self):
        url='https://cdn.shopify.com/image.jpg'
        html=f'<img src="{url}"><img src="{url}"><div style="background-image:url({url})"></div>'
        report=size.analyze_rendered_email(html,'',{url:2*1024*1024})
        self.assertEqual(report['asset_urls'],[url])
        self.assertEqual(report['html_bytes'],len(html.encode()))
        self.assertEqual(report['status'],'SAFE')
        self.assertEqual(report['large_asset_count'],1)
        self.assertEqual(report['remote_asset_bytes'],2*1024*1024)
        self.assertIn('1 large image',size.meter_html(report))

    def test_unknown_assets_and_unsafe_hosts_never_crash_or_request(self):
        from crm_email_asset_size import head_size
        report=size.analyze_rendered_email('<img src="https://example.test/image.jpg">','')
        self.assertEqual(report['unknown_asset_count'],1)
        with patch('requests.head',side_effect=AssertionError('No unsafe requests')):
            for url in ('http://cdn.shopify.com/a','https://127.0.0.1/a','https://cdn.shopify.com.evil.test/a'):
                self.assertIsNone(head_size(url))

    def test_head_is_short_no_redirects_and_unknown_length_is_allowed(self):
        from crm_email_asset_size import head_size
        response=Mock(status_code=200,headers={'Content-Length':'1234'})
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        with patch('requests.head',return_value=response) as head:
            self.assertEqual(head_size('https://cdn.shopify.com/a.jpg'),1234)
            self.assertEqual(head.call_args.kwargs,{'timeout':(1,1),'allow_redirects':False})
            response.headers={};self.assertIsNone(head_size('https://cdn.shopify.com/a.jpg'))

    def test_asset_future_cache_never_waits_and_deduplicates(self):
        import crm_email_asset_size as assets
        future=Future();url='https://cdn.shopify.com/a.jpg'
        with patch.object(assets,'_CACHE',{}),patch.object(assets._POOL,'submit',return_value=future) as submit:
            self.assertEqual(assets.metadata([url],start=False),{url:None})
            submit.assert_not_called()
            self.assertEqual(assets.metadata([url,url],start=True),{url:None})
            submit.assert_called_once()
            future.set_result(321)
            self.assertEqual(assets.metadata([url],start=True),{url:321})
            submit.assert_called_once()

    def test_validator_blocks_oversize_and_accepts_exact_limit(self):
        size.validate_rendered_email({'html':'x'*size.LIMIT_BYTES,'text':'test'})
        with self.assertRaisesRegex(ValueError,'Email is too large for safe delivery'):
            size.validate_rendered_email({'html':'x'*(size.LIMIT_BYTES+1),'text':''})
        with self.assertRaisesRegex(ValueError,'attachment transport sizing'):
            size.validate_rendered_email({'html':'x','text':'','attachments':[{}]})

    def test_transport_is_separate_from_html_budget(self):
        with patch.object(size,'TRANSPORT_BYTES',100):
            with self.assertRaisesRegex(ValueError,'40 MB transport'):
                size.validate_rendered_email({'html':'<p>Small</p>','text':'Small'})

    def test_production_checks_block_final_html(self):
        checks=production_checks(self.oversized(),self.cfg,LIVE)
        self.assertFalse(checks[size.SIZE_ERROR])

    def test_queue_and_schedule_cannot_bypass_size_guard(self):
        doc=self.oversized()
        editor={'id':IDENTITY,'version':1,'document':doc,'archived_at':None}
        store=Mock();store.q.return_value=None;store.draft.return_value=editor
        store.render_settings.return_value=self.cfg
        for scheduled in (False,True):
            snapshot={'campaign_version':1,'document':doc,'recipients':[],
                      'render_settings':self.cfg,'schedule':{'fixture':{}} if scheduled else {}}
            with patch('crm_campaign_snapshot.load',return_value=snapshot),patch('requests.sessions.Session.request',side_effect=AssertionError('No network')):
                with self.assertRaisesRegex(ValueError,'Email is too large for safe delivery'):
                    queue_campaign(Mock(),store,ADMIN,editor,IDENTITY,env=LIVE,snapshot_id=IDENTITY)
        store.db.assert_not_called()

    def test_review_checks_size_before_snapshot(self):
        doc=self.oversized();editor={'id':IDENTITY,'document':doc,'name':'Fixture','version':1}
        state={'members':1,'eligible':1,'excluded':{},'complete':True,'checked_at':doc['counts']['checked_at'],'recipients':[]}
        store=Mock();store.render_settings.return_value=self.cfg
        with patch('crm_campaign_send.final_audience',return_value=state),patch('crm_campaign_snapshot.create') as create:
            result=review(Mock(),store,editor,LIVE)
        self.assertIn(size.SIZE_ERROR,result['blockers'])
        self.assertEqual(result['email_size']['status'],'TOO LARGE')
        self.assertIsNone(result['snapshot_id']);create.assert_not_called()
        self.assertIn('TOO LARGE',size.size_line(result['email_size']))

    def test_worker_checks_actual_render_before_submission(self):
        from crm_engine import Engine
        from crm_resend import Config
        from crm_logic import recipient_hash
        store=Mock();provider=Mock();provider.suppressed.return_value=False
        row={'test_send':False,'enrollment_id':None,'template_id':'fixture','template_version':1,
             'campaign_id':IDENTITY,'recipient_hash':recipient_hash('fixture@example.test'),'shopify_customer_id':'fixture'}
        store.claim_send.return_value=row;store.suppressed.return_value=False
        store.template.return_value={'format':'campaign_delivery_v1','document':self.doc,'render_settings':self.cfg}
        store.q.return_value={'campaign_send_id':IDENTITY}
        engine=Engine(store,Mock(),provider=provider,config=Config(LIVE))
        with patch.object(engine,'validate',return_value=({'email':'fixture@example.test'}, {},'')),patch('crm_campaign_schedule.overdue_reason',return_value=None),patch('crm_native_unsubscribe.native_unsubscribe_url',return_value='https://example.test/unsubscribe'),patch('crm_campaign_send.production_checks',return_value={'ready':True}),patch('crm_campaign_content.render_campaign',return_value={'html':'x'*(size.LIMIT_BYTES+1),'text':''}):
            engine.send_one()
        store.finish_send.assert_called_once_with(row,'BLOCKED','email_size_limit')
        store.begin_send.assert_not_called();provider.send.assert_not_called()

    def test_meter_is_in_action_row_without_new_card_and_first_paint_does_no_head(self):
        with patch('requests.head',side_effect=AssertionError('No first-paint HEAD')):
            app=AppTest.from_string(SCRIPT).run()
        self.assertFalse(app.exception)
        markup='\n'.join(h.proto.body for h in app.get('html'))
        self.assertIn('class="sc-email-size"',markup)
        self.assertIn('height:6px',markup)
        self.assertNotIn('sc-email-loading',markup)
        self.assertFalse(app.metric)
        source=Path(__file__).resolve().parents[1].joinpath('crm_campaign_page.py').read_text(encoding='utf-8')
        action=source[source.index("with toolbar.container"):source.index('new_requested=False')]
        self.assertLess(action.index('size_meter('),action.index("st.button('Save draft'"))

    def test_fragment_updates_unsaved_content_locally(self):
        script='''
from unittest.mock import patch
import streamlit as st
from crm_email_size_ui import size_meter
from tests.test_crm_postal_setting_removal import PostalSettingRemovalTests
fixture=PostalSettingRemovalTests();fixture.setUp()
doc=fixture.doc
doc['custom_html']='<p>'+st.session_state.get('content','Short')+'</p>'+('<a href="https://www.sportscaveshop.com/collection">View</a>'*200)
editor={'id':None,'document':doc}
st.session_state['campaign_editor']=editor
with patch('crm_email_asset_size.metadata',return_value={}):size_meter(editor,'fixture',fixture.cfg)
'''
        app=AppTest.from_string(script).run();self.assertFalse(app.exception)
        first='\n'.join(h.proto.body for h in app.get('html'))
        app.session_state['content']='x'*60000;app.run()
        self.assertFalse(app.exception)
        second='\n'.join(h.proto.body for h in app.get('html'))
        self.assertIn('SAFE',first);self.assertIn('TOO LARGE',second)

    def test_review_modal_size_line_and_red_confirmation_disabled(self):
        script='''
from concurrent.futures import Future
from unittest.mock import Mock,patch
import streamlit as st
from crm_campaign_send_ui import review_finalization
from crm_campaign_review import identity
from crm_email_size import analyze_rendered_email,SIZE_ERROR,LIMIT_BYTES
from tests.test_crm_simple_editor import document
editor={'id':'00000000-0000-0000-0000-000000000123','name':'Fixture','document':document(),'version':1}
report=analyze_rendered_email('x'*(LIMIT_BYTES+1),'')
job=Mock(closed=False,applied=True,identity=identity(editor))
job.future=Future();job.future.set_result({'counts':{'eligible':1,'excluded':{}},'blockers':[SIZE_ERROR],'snapshot_id':None,'tracking_ok':True,'email_size':report})
with patch('crm_campaign_send_ui.queue_campaign',side_effect=AssertionError('No sends')):
 review_finalization(None,None,{},editor,'fixture',job,{'marketing_enabled':True})
'''
        app=AppTest.from_string(script).run()
        self.assertFalse(app.exception)
        self.assertTrue(any('Email size' in c.value and 'TOO LARGE' in c.value for c in app.caption))
        self.assertTrue(next(b for b in app.button if b.key=='confirm_send' or str(b.key).endswith('confirm_send')).disabled)

    def test_ui_unknown_state_has_no_payload_or_exception_logging(self):
        script='''
from unittest.mock import patch
import streamlit as st
from crm_email_size_ui import size_meter
editor={'id':None,'document':{}}
with patch('crm_email_size_ui.render_production',side_effect=ValueError('private@example.test token=secret')):
 size_meter(editor,'fixture',{})
'''
        app=AppTest.from_string(script).run()
        self.assertFalse(app.exception)
        html='\n'.join(h.proto.body for h in app.get('html'))
        self.assertIn('Unknown',html)
        self.assertNotIn('private@example.test',html);self.assertNotIn('token=secret',html)


if __name__=='__main__':unittest.main()
