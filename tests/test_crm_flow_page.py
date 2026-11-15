from copy import deepcopy
from datetime import timedelta
import json,os,uuid,unittest
from unittest.mock import patch
from crm_flow_thumbnail import InertEmail,miniature
from crm_flow_page import rate,snippet,delay_origin,step_performance
from crm_automation_home_data import step_metrics
from crm_checkout_analytics import report,window
from crm_logic import now
from tests import test_crm_native_automations as native
from tests.test_crm import ADMIN
from tests.test_crm_send_flow import CFG
from tests.test_crm_simple_editor import document

class PresentationTests(unittest.TestCase):
    def test_delay_anchor_skips_disabled_steps_after_reordering(self):
        from crm_automation_definition import email_step,new_flow
        from crm_flow_builder import edit_sequence
        flow=new_flow();flow['emails']=[email_step(delay_seconds=60),email_step(delay_seconds=120),email_step(delay_seconds=180)]
        flow['emails'][0]['enabled']=False
        self.assertEqual(delay_origin(flow['emails'],1),' after trigger')
        self.assertEqual(delay_origin(flow['emails'],2),' after the previous enabled email')
        moved=edit_sequence(flow,flow['emails'][2]['step_id'],'up')
        self.assertEqual(delay_origin(moved['emails'],1),' after trigger')
        self.assertEqual(moved['emails'][1],flow['emails'][2])

    def test_metrics_error_and_recovery_use_owning_fragment_slots(self):
        from unittest.mock import Mock
        # A nested fragment wrapper would detach these writes from the sequence.
        self.assertFalse(hasattr(step_performance,'__wrapped__'))
        slots={'original':Mock(),'second':Mock()};details={k:Mock() for k in slots}
        values=[dict(step_id='original',sent=32,opened=11,clicked=1,orders=0,delivered=32,queued=0,failed=0,skipped=0,bounced=0)]
        with patch('crm_flow_page.st') as ui,patch('crm_flow_page.read') as read,patch('crm_flow_page.arm') as arm:
            ui.session_state={};ui.button.return_value=False
            for phase,data in [('LOADING',None),('ERROR',None),('READY',values),('REFRESHING',values),('TIMED_OUT',values)]:
                read.return_value=(data,phase)
                step_performance(Mock(),'flow',slots,details)
                self.assertIn('sc-flow-metrics',slots['original'].html.call_args.args[0])
            self.assertIn('32',slots['original'].html.call_args.args[0])
            self.assertNotIn('32',slots['second'].html.call_args.args[0])
            ui.rerun.assert_not_called()
            ui.caption.assert_called_with('Step analytics unavailable.')
            arm.assert_called_with('flow-steps',1)
            with patch('crm_flow_page.refresh_reads') as refresh:
                ui.button.side_effect=lambda label,**kwargs:label=='Retry step analytics'
                step_performance(Mock(),'flow',slots,details)
                refresh.assert_called_once()
                ui.rerun.assert_called_once_with(scope='fragment')

    def test_thumbnail_is_inert_and_bounds_remote_images(self):
        parser=InertEmail();parser.feed('<script>secret()</script><style>@import "https://private";</style><p onclick="secret()" style="color:red;background-image:url(https://private)">Real heading</p><img src="https://cdn.shopify.com/a.jpg?width=4000"><img src="https://tracker.test/pixel"><a href="https://checkout.test/private-token">CTA</a>')
        output=''.join(parser.out)
        self.assertIn('Real heading',output);self.assertIn('color:red',output)
        self.assertIn('width=80',output)
        for token in ('secret','private','tracker','onclick','href','background-image'):self.assertNotIn(token,output)

    def test_thumbnail_content_cache_changes_only_with_document_or_settings(self):
        doc=document();original=deepcopy(doc);miniature.cache_clear()
        first=miniature(json.dumps(doc,sort_keys=True),json.dumps(CFG,sort_keys=True))
        self.assertIn('A collector moment',first)
        self.assertEqual(first,miniature(json.dumps(doc,sort_keys=True),json.dumps(CFG,sort_keys=True)))
        self.assertEqual(miniature.cache_info().hits,1)
        doc['custom_html']='<p>Changed artwork heading</p>';doc['content_mode']='HTML';doc.pop('middle_sections',None)
        self.assertIn('Changed artwork heading',miniature(json.dumps(doc,sort_keys=True),json.dumps(CFG,sort_keys=True)))
        self.assertNotIn('Changed artwork heading',original.get('custom_html',''))

    def test_rates_and_snippets_do_not_invent_values(self):
        self.assertEqual(rate(11,32),'34.4%');self.assertEqual(rate(0,0),'—')
        self.assertEqual(snippet({'custom_html':'<style>private css</style><p>Actual &amp; saved</p>'}),'Actual & saved')

    def test_refresh_fences_pending_reads_and_retains_last_good_data(self):
        from concurrent.futures import Future
        from types import SimpleNamespace
        from crm_flow_page import refresh_reads
        token=(None,('analytics-report','flow-1','All time'));other=(None,('analytics-report','flow-2','All time'))
        pending=Future();untouched=Future()
        cache={'campaign_home_cache':{token:(0,pending),other:(0,untouched)},'campaign_home_resolved':{token:[{'sent':32}]},'automation_read_terminal':{token:'ERROR'},'automation_read_started':{token:0}}
        with patch('crm_flow_page.state',return_value=cache):refresh_reads(SimpleNamespace(connect=None),'flow-1')
        self.assertTrue(pending.cancelled());self.assertFalse(untouched.cancelled())
        self.assertNotIn(token,cache['automation_read_terminal']);self.assertNotIn(token,cache['automation_read_started'])
        self.assertEqual(cache['campaign_home_resolved'][token],[{'sent':32}])

@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable SQL required')
class FlowMetricsTests(unittest.TestCase):
    setUp=native.NativeAutomationTests.setUp
    published=native.NativeAutomationTests.published

    def test_32_original_sends_are_independent_after_reordering_and_new_step(self):
        row=self.published(delays=(0,86400));first,second=[s['step_id'] for s in row['steps']]
        step=row['steps'][0]
        self.store.q('''INSERT INTO crm_automation_enrollments(automation_id,shopify_customer_id,trigger_shopify_id,trigger_key,trigger_at,steps,next_due_at)
          SELECT %s,'fixture-'||i,'fixture-'||i,'fixture-'||i,now(),%s::jsonb,now() FROM generate_series(1,32) i''',(row['id'],json.dumps(row['steps'])))
        self.store.q('''INSERT INTO crm_marketing_sends(idempotency_key,shopify_customer_id,recipient_hash,template_id,template_version,enrollment_id,step_index,status,provider_email_id,first_submitted_at)
          SELECT 'history:'||id,shopify_customer_id,'fixture',%s,%s,id,0,'ACCEPTED','fixture-'||id,now() FROM crm_automation_enrollments WHERE automation_id=%s''',(step['template_id'],step['template_version'],row['id']))
        sends=self.store.q('SELECT s.* FROM crm_marketing_sends s JOIN crm_automation_enrollments j ON j.id=s.enrollment_id WHERE j.automation_id=%s',(row['id'],))
        for i,send in enumerate(sends):
            for event in ['email.delivered']+(['email.opened','email.opened'] if i<11 else [])+(['email.clicked'] if i==0 else []):
                self.store.q('INSERT INTO crm_delivery_events(event_id,provider_id,event_type,occurred_at,send_id) VALUES(%s,%s,%s,now(),%s)',(str(uuid.uuid4()),send['provider_email_id'],event,send['id']))
        before_enrollments=self.store.q('SELECT * FROM crm_automation_enrollments WHERE automation_id=%s ORDER BY id',(row['id'],))
        draft=deepcopy(row['config']['draft']);draft['emails'].reverse()
        self.store.save_flow(ADMIN,row['id'],row['name'],draft,row['config']['revision'])
        persisted=self.store.flow(row['id'])
        self.assertEqual(persisted['config']['draft']['emails'],draft['emails'])
        self.assertEqual(persisted['steps'],row['steps'])
        self.assertEqual(persisted['config']['published_version'],row['config']['published_version'])
        self.assertEqual(persisted['status'],row['status'])
        self.assertEqual(self.store.q('SELECT * FROM crm_automation_enrollments WHERE automation_id=%s ORDER BY id',(row['id'],)),before_enrollments)
        self.assertEqual(self.store.q('SELECT s.* FROM crm_marketing_sends s JOIN crm_automation_enrollments j ON j.id=s.enrollment_id WHERE j.automation_id=%s',(row['id'],)),sends)
        metrics={r['step_id']:r for r in step_metrics(self.store,row['id'],window('All time'))}
        self.assertEqual((metrics[first]['sent'],metrics[first]['opened'],metrics[first]['clicked']),(32,11,1))
        self.assertNotIn(second,metrics)
        overall=report(self.store,row['id'],window('All time'))
        self.assertEqual((overall['entered'],overall['sent'],overall['opened']),(32,32,11))
        step=row['steps'][1];send=sends[0]
        self.store.q('''INSERT INTO crm_marketing_sends(idempotency_key,shopify_customer_id,recipient_hash,template_id,template_version,enrollment_id,step_index,status,first_submitted_at)
          VALUES(%s,%s,'fixture',%s,%s,%s,1,'ACCEPTED',now())''',(str(uuid.uuid4()),send['shopify_customer_id'],step['template_id'],step['template_version'],send['enrollment_id']))
        updated=report(self.store,row['id'],window('All time'))
        self.assertEqual((updated['entered'],updated['sent']),(32,33))
        metrics={r['step_id']:r for r in step_metrics(self.store,row['id'])}
        self.assertEqual((metrics[first]['sent'],metrics[second]['sent']),(32,1))
        for sid,currency,amount,eligible in [(first,'AUD',10,True),(second,'NZD',20,True),(second,'AUD',999,False)]:
            self.store.q('''INSERT INTO crm_order_attribution(shopify_order_id,customer_id,order_created_at,visit_at,amount,currency,eligible,evidence)
              VALUES(%s,'fixture',now(),now(),%s,%s,%s,%s::jsonb)''',(str(uuid.uuid4()),amount,currency,eligible,json.dumps({'automation_id':str(row['id']),'step_id':sid})))
        metrics={r['step_id']:r for r in step_metrics(self.store,row['id'])}
        self.assertEqual(metrics[first]['revenue'],{'AUD':10});self.assertEqual(metrics[second]['revenue'],{'NZD':20})
        self.assertEqual((metrics[first]['orders'],metrics[second]['orders']),(1,1))
        self.assertEqual(step_metrics(self.store,row['id'],(now()+timedelta(days=1),now()+timedelta(days=2))),[])
        self.provider.send.assert_not_called()
