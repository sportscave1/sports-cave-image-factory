from copy import deepcopy
from datetime import timedelta
import io
from contextlib import redirect_stdout
from unittest import TestCase
from unittest.mock import Mock,patch
from crm_logic import now,date
from crm_automation_capabilities import verify,require,refresh_due,TOPICS,CONNECTION
from tests import test_crm_shopify_automation_triggers as trigger_tests

ENV={'SPORTS_CAVE_WEBHOOK_BASE_URL':'https://fixture.example','SHOPIFY_WEBHOOK_SECRET':'fixture-secret'}


class DiagnosticTests(TestCase):
    def report(self,*,scopes=None,hooks=None,env=None,identity=None):
        shop=trigger_tests.CapabilitiesTests().shop()
        response=shop.query(CONNECTION,{})
        if scopes is not None:response['currentAppInstallation']['accessScopes']=[{'handle':s} for s in scopes]
        if identity:response['currentAppInstallation']['app']['apiKey']=identity
        shop.query.side_effect=lambda *a:response
        if hooks is None:hooks=self.hooks()
        with patch('crm_tracking_health.subscriptions',return_value=hooks):
            result=verify(shop,Mock(),ENV if env is None else env)
        return result

    def hooks(self):
        return [{'topic':topic,'apiVersion':{'handle':'2026-04'},'endpoint':{'callbackUrl':'https://fixture.example/webhooks/shopify/crm'}} for topic in sorted({t for ts in TOPICS.values() for t in ts})]

    def test_each_server_requirement_fails_closed_with_exact_reason(self):
        for scope in ('read_customers','read_orders'):
            result=self.report(scopes=[s for s in ('read_customers','read_orders') if s!=scope])
            self.assertEqual(result['triggers']['abandoned'],'UNAVAILABLE')
            self.assertIn(scope+': MISSING',result['reasons']['abandoned'])
        for topic in TOPICS['abandoned']:
            for fault in ('missing','callback','version'):
                hooks=self.hooks()
                if fault=='missing':hooks=[h for h in hooks if h['topic']!=topic]
                else:
                    row=next(h for h in hooks if h['topic']==topic)
                    if fault=='callback':row['endpoint']['callbackUrl']='https://wrong.example/hook'
                    else:row['apiVersion']['handle']='2025-10'
                result=self.report(hooks=hooks)
                self.assertEqual(result['triggers']['abandoned'],'UNAVAILABLE')
                self.assertIn(topic,result['reasons']['abandoned'][0])
                self.assertIn({'missing':'MISSING','callback':'CALLBACK MISMATCH','version':'API VERSION MISMATCH'}[fault],result['reasons']['abandoned'][0])

    def test_hmac_identity_and_https_configuration(self):
        for env in ({'SPORTS_CAVE_WEBHOOK_BASE_URL':'https://fixture.example'},dict(ENV,SHOPIFY_WEBHOOK_SECRET='shpat_secret')):
            result=self.report(env=env);self.assertFalse(result['webhook_hmac_configured'])
            self.assertEqual(result['triggers']['abandoned'],'UNAVAILABLE')
            self.assertNotIn('shpat_secret',str(result))
        self.assertIn('App identity: MISMATCH',self.report(identity='another-app')['reasons']['abandoned'])
        self.assertIn('Callback configuration',str(self.report(env=dict(ENV,SPORTS_CAVE_WEBHOOK_BASE_URL='http://localhost'))['reasons']['abandoned']))

    def test_paid_callback_and_pixel_independence(self):
        hooks=self.hooks();next(h for h in hooks if h['topic']=='ORDERS_PAID')['endpoint']['callbackUrl']='https://fixture.example/webhooks/shopify/orders-paid'
        result=self.report(hooks=hooks,scopes=['read_customers','read_orders'])
        self.assertEqual(result['pixel'],'UNVERIFIED');self.assertEqual(result['triggers']['abandoned'],'AVAILABLE')
        store=Mock();store.state.return_value=result;require(store,'abandoned')

    def test_worker_skips_optional_pixel_but_explicit_diagnostic_checks_it(self):
        from crm_automation_capabilities import PIXEL
        shop=trigger_tests.CapabilitiesTests().shop();store=Mock()
        store.state.return_value={'pixel':'NOT VERIFIED','pixel_checked_at':'2026-10-01T00:00:00Z'}
        with patch('crm_tracking_health.subscriptions',return_value=self.hooks()):
            result=verify(shop,store,ENV,include_pixel=False)
            self.assertFalse(any(call.args[0]==PIXEL for call in shop.query.call_args_list))
            self.assertEqual(result['triggers']['abandoned'],'AVAILABLE')
            self.assertEqual(result['pixel_checked_at'],'2026-10-01T00:00:00Z')
            verify(shop,store,ENV)
            self.assertTrue(any(call.args[0]==PIXEL for call in shop.query.call_args_list))

    def test_missing_stale_and_failed_reports_block_but_valid_report_passes(self):
        for result,text in [({},'Diagnostic missing'),({'checked_at':(now()-timedelta(minutes=11)).isoformat(),'triggers':{'abandoned':'AVAILABLE'}},'Diagnostic expired'),(self.report(scopes=['read_customers']),'read_orders: MISSING')]:
            store=Mock();store.state.return_value=result
            with self.assertRaisesRegex(ValueError,text):require(store,'abandoned')
        store=Mock();store.state.return_value=self.report(scopes=['read_customers','read_orders']);require(store,'abandoned')

    def test_failure_is_safe_and_inspection_does_not_persist(self):
        shop=Mock();shop.query.side_effect=RuntimeError('private-token');store=Mock()
        with patch('crm_tracking_health.subscriptions',side_effect=RuntimeError('private-token')):
            result=verify(shop,store,ENV,persist=False)
        self.assertNotIn('private-token',str(result));store.set_state.assert_not_called()
        self.assertIn('UNAVAILABLE',result['checks']['Shopify API']);self.assertEqual(result['triggers']['abandoned'],'UNVERIFIED')

    def test_worker_schedule_remains_fresh_over_twenty_minutes(self):
        from crm_engine import Engine
        clock=now();store=Mock();store.lease.return_value=True;store.q.return_value=[]
        state={'checked_at':clock.isoformat()};store.state.side_effect=lambda key:state if key=='shopify_automation_capabilities' else {}
        config=Mock(enabled=False,api_key='');engine=Engine(store,Mock(),config=config,clock=lambda:clock)
        engine.send_one=Mock(return_value=False)
        stamps=[]
        def verified(*a,**kwargs):
            self.assertFalse(kwargs['include_pixel'])
            state['checked_at']=clock.isoformat();stamps.append(clock)
        with patch('crm_automation_capabilities.verify',side_effect=verified),patch('crm_campaign_schedule.schedule_gate'),patch('crm_campaign_dispatch.dispatch'),patch('crm_campaign_attribution.reconcile'),patch('crm_consent_sync.reconcile_pending'):
            for minute in range(21):
                if minute:clock+=timedelta(minutes=1)
                engine.tick('fixture-worker')
                self.assertLess(clock-date(state['checked_at']),timedelta(minutes=5))
        self.assertEqual(len(stamps),4)
        self.assertTrue(refresh_due({},clock))

    def test_admin_control_is_explicit_does_not_publish_or_fetch_on_render(self):
        import crm_automation_diagnostic_ui as ui
        store=Mock();store.state.return_value=self.report(scopes=['read_customers'])
        with patch('os_accounts.is_admin',return_value=False),patch.object(ui,'verify') as diagnostic:
            with self.assertRaises(PermissionError):ui.run_diagnostic(Mock(),store,{})
            diagnostic.assert_not_called()
        st=Mock();st.expander.return_value.__enter__=Mock();st.expander.return_value.__exit__=Mock(return_value=False)
        st.button.return_value=False
        with patch('os_accounts.is_admin',return_value=True),patch.object(ui,'st',st),patch.object(ui,'verify') as diagnostic:
            ui.control.__wrapped__(Mock(),store,{},'abandoned','fixture')
            diagnostic.assert_not_called();self.assertIn('read_orders: MISSING',str(st.caption.call_args_list))
            st.button.return_value=True;diagnostic.return_value=self.report(scopes=['read_customers','read_orders'])
            ui.control.__wrapped__(Mock(),store,{},'abandoned','fixture')
            diagnostic.assert_called_once();store.publish.assert_not_called()

    def test_script_reports_readiness_and_reasons(self):
        from scripts.shopify_automation_diagnostics import main
        with patch('crm_shopify.Shopify'),patch('crm_store.Store'),patch('crm_automation_capabilities.verify',return_value=self.report(scopes=['read_customers'])) as diagnostic,redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['--inspect-only']),0)
        self.assertIn('ABANDONED CHECKOUT: NOT READY',output.getvalue());self.assertIn('read_orders: MISSING',output.getvalue())
        self.assertFalse(diagnostic.call_args.kwargs['persist'])

    def test_admin_streamlit_button_updates_stored_report_without_publication(self):
        from streamlit.testing.v1 import AppTest
        script='''
import streamlit as st
from unittest.mock import Mock,patch
from crm_logic import now
from crm_automation_diagnostic_ui import control
if 'report' not in st.session_state:
 st.session_state.report={}
 st.session_state.runs=0
store=Mock();store.state.side_effect=lambda key:st.session_state.report
def verify(shop,store):
 st.session_state.runs+=1
 st.session_state.report={'checked_at':now().isoformat(),'triggers':{'abandoned':'AVAILABLE'},'checks':{'App identity':'VERIFIED','read_customers':'VERIFIED','read_orders':'VERIFIED'}}
 return st.session_state.report
with patch('os_accounts.is_admin',return_value=True),patch('crm_automation_diagnostic_ui.verify',side_effect=verify):
 control(Mock(),store,{},'abandoned','fixture_')
'''
        app=AppTest.from_string(script).run()
        self.assertFalse(app.exception);self.assertEqual(app.session_state['runs'],0)
        self.assertTrue(any('Diagnostic missing' in caption.value for caption in app.caption))
        next(b for b in app.button if b.label=='Run diagnostic').click().run()
        self.assertFalse(app.exception);self.assertEqual(app.session_state['runs'],1)
        self.assertTrue(any(c.value=='Abandoned checkout trigger · READY' for c in app.caption))

    def test_future_timestamp_is_not_accepted_and_non_leader_does_not_refresh(self):
        from crm_engine import Engine
        store=Mock();store.state.return_value={'checked_at':(now()+timedelta(days=1)).isoformat(),'triggers':{'abandoned':'AVAILABLE'}}
        with self.assertRaisesRegex(ValueError,'timestamp is invalid'):require(store,'abandoned')
        self.assertTrue(refresh_due(store.state.return_value,now()))
        store.lease.return_value=False
        with patch('crm_automation_capabilities.verify') as diagnostic:
            self.assertEqual(Engine(store,Mock()).tick('other-worker'),{'leader':False})
            diagnostic.assert_not_called()
