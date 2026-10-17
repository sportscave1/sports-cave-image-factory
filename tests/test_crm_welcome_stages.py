"""Shared, read-only Welcome stage projection and persisted identity lookup."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
import json,os,unittest,uuid
from unittest.mock import Mock,patch
from crm_flow_recipient_adapters import LIFECYCLE,project
from crm_lifecycle_definition import expanded_flow

AT=datetime(2026,10,17,0,tzinfo=timezone.utc)
def display(value):
    from crm_logic import date
    return date(value).astimezone(ZoneInfo('Australia/Sydney')).strftime('%d %b %Y %H:%M %Z')

def fixture(count=3):
    flow=expanded_flow('welcome')
    while len(flow['emails'])<count:
        step=deepcopy(flow['emails'][-1]);step['step_id']=str(uuid.uuid4());flow['emails'].append(step)
    flow['emails']=flow['emails'][:count]
    row=dict(status='ACTIVE',trigger_type='welcome',config={'draft':deepcopy(flow),'published_flow':flow})
    record=dict(key='customer',customer_id='customer',name='Stage fixture',email='stage@example.test',
        consent='SUBSCRIBED',suppressed=False,flow_state='ACTIVE',enrollment_id='journey',
        current_step=0,steps=deepcopy(flow['emails']),sends=[],next_due_at=AT+timedelta(hours=1),
        audience_at=AT,order_count=0,source='Signup')
    return row,record

def projected(row,record):return project(LIFECYCLE['welcome'],row,[record],display,AT)
def stages(row,record):return projected(row,record)[1][0]['cells'][5:]

class WelcomeStages(unittest.TestCase):
    def test_dynamic_columns_and_event_anchors_do_not_accumulate_days(self):
        for count in (1,2,3,5):
            row,record=fixture(count);before=deepcopy(row)
            columns,_=projected(row,record)
            self.assertEqual(len([c for c in columns if 'id' in c]),count)
            self.assertEqual([c['label'] for c in columns if c.get('visible',True)],['Flow','Purchased']+['Email '+str(i+1) for i in range(count)])
            self.assertEqual(row,before)
        self.assertEqual([c['timing'] for c in columns if 'id' in c][:3],
            ['Instant after confirmed subscription','3 days after confirmed subscription','7 days after confirmed subscription'])
        for s in row['config']['published_flow']['emails']:s.pop('anchor')
        self.assertIn('previous enabled email',[c for c in projected(row,record)[0] if 'id' in c][2]['timing'])
        row['config']['published_flow']['emails'][0]['delay_seconds']=30
        self.assertIn('30 seconds',[c for c in projected(row,record)[0] if 'id' in c][0]['timing'])

    def test_no_enrollment_never_invents_deadlines(self):
        row,record=fixture();record['enrollment_id']=None
        self.assertEqual([c['label'] for c in stages(row,record)],['Not enrolled']*3)
        self.assertTrue(all(not c.get('due_at') and not c.get('detail') for c in stages(row,record)))

    def test_scheduled_waiting_queued_sending_and_acceptance(self):
        row,record=fixture()
        values=stages(row,record)
        self.assertEqual([v['label'] for v in values],['Scheduled','Waiting','Waiting'])
        self.assertEqual(values[0]['detail'],'Scheduled 17 Oct 2026 12:00 AEDT')
        record['next_due_at']=AT-timedelta(minutes=2)
        send=dict(enrollment_id='journey',step=0,status='PENDING',due_at=AT-timedelta(minutes=1))
        record['sends']=[send]
        self.assertEqual(stages(row,record)[0]['label'],'Queued')
        for state in ('CLAIMED','SUBMITTING'):
            send['status']=state;self.assertEqual(stages(row,record)[0]['label'],'Sending')
        send.update(status='ACCEPTED',submitted_at=AT.isoformat())
        self.assertNotIn('Sent',stages(row,record)[0]['label'])
        send['provider_id']='provider-receipt'
        self.assertEqual(stages(row,record)[0]['label'],'Sent ✓')
        self.assertEqual(stages(row,record)[0]['detail'],'Sent 17 Oct 2026 11:00 AEDT')
        send['enrollment_id']='other-flow'
        self.assertNotIn('Sent',stages(row,record)[0]['label'])

    def test_failures_blocking_drafts_and_disabled_parent(self):
        row,record=fixture()
        for state,label in [('FAILED','Failed'),('BLOCKED','Suppressed'),('UNCERTAIN','Confirming')]:
            record['sends']=[dict(enrollment_id='journey',step=0,status=state,error='consent_unsubscribed')]
            value=stages(row,record)[0];self.assertEqual(value['label'],label)
            if state!='UNCERTAIN':self.assertEqual(value['reason'],'consent_unsubscribed')
        record['sends']=[];row['status']='DRAFT'
        self.assertEqual(stages(row,record)[0]['label'],'Paused')
        self.assertIn('Held',stages(row,record)[0]['detail'])
        row['config']['published_flow']['emails'][1]['enabled']=False
        self.assertEqual(stages(row,record)[1]['label'],'Disabled')
        extra=deepcopy(row['config']['draft']['emails'][0]);extra['step_id']='draft-only'
        row['config']['draft']['emails'].append(extra)
        self.assertEqual(stages(row,record)[-1]['label'],'Not published')
        self.assertIn('Draft',projected(row,record)[0][-1]['timing'])

@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class PersistedWelcomeLookup(unittest.TestCase):
    def test_hash_matched_journey_is_not_false_not_enrolled_and_one_batched_read(self):
        from tests.test_crm_lifecycle_expansion import DatabaseTests,CUSTOMER
        from tests.crm_db_fixture import connect
        from tests.test_crm import ADMIN
        from tests.test_crm_send_flow import CFG
        from crm_automation_store import AutomationStore
        from crm_lifecycle_audience import cache_customer,listing
        from crm_logic import recipient_hash
        DatabaseTests.setUpClass();store=AutomationStore(connect)
        customer=deepcopy(CUSTOMER);customer['id']='gid://shopify/Customer/'+str(uuid.uuid4().int%10**12)
        customer['email']=str(uuid.uuid4())+'@example.test';cache_customer(store,customer,AT)
        with patch.object(store,'render_settings',return_value=CFG):row=store.create(ADMIN,'welcome',lifecycle=True)
        steps=deepcopy(row['config']['draft']['emails']);steps[0]['recipient_hash']=recipient_hash(customer['email'])
        journey=store.q('''INSERT INTO crm_automation_enrollments(automation_id,shopify_customer_id,trigger_shopify_id,trigger_key,trigger_at,steps,next_due_at)
          VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s) RETURNING id''',
          (row['id'],'old-customer-id','signup',str(uuid.uuid4()),AT,json.dumps(steps),AT+timedelta(days=3)),True)
        before=store.flow(row['id']);original=store.q
        with patch.object(store,'q',wraps=original) as query:
            records=listing(store,row,search=customer['id'])
            self.assertEqual(query.call_count,1)
        self.assertEqual(len(records),1);self.assertEqual(records[0]['enrollment_id'],journey['id'])
        self.assertEqual(records[0]['flow_state'],'ACTIVE');self.assertEqual(store.flow(row['id']),before)
        self.assertEqual(listing(store,row,search=customer['id'],filter_by='New'),[])
        template=store.q("INSERT INTO crm_templates(name,kind,content) VALUES('Local receipt fixture','Automation','{}') RETURNING id,version",one=True)
        store.q("INSERT INTO crm_template_versions(template_id,version,content) VALUES(%s,1,'{}')",(template['id'],))
        send=store.enqueue(str(uuid.uuid4()),customer['id'],recipient_hash(customer['email']),template,
            enrollment_id=journey['id'],step_index=0)
        due=AT-timedelta(minutes=1)
        store.q('UPDATE crm_automation_enrollments SET next_due_at=%s WHERE id=%s',(due,journey['id']))
        # Projection-only active view; no automation is activated by this test.
        view=deepcopy(row);view['status']='ACTIVE';view['config']['published_flow']=deepcopy(row['config']['draft'])
        for state,label in [('PENDING','Queued'),('CLAIMED','Sending'),('FAILED','Failed'),('BLOCKED','Suppressed'),('ACCEPTED','Sent ✓')]:
            store.q('UPDATE crm_marketing_sends SET status=%s,due_at=%s,first_submitted_at=%s,provider_email_id=%s,error_code=%s WHERE id=%s',
                (state,due,AT,'local-receipt-'+str(send['id']) if state=='ACCEPTED' else None,'local_fixture_reason',send['id']))
            records=listing(store,row,search=customer['id'])
            value=stages(view,records[0])[0];self.assertEqual(value['label'],label)
            if state=='ACCEPTED':self.assertEqual(value['detail'],'Sent 17 Oct 2026 11:00 AEDT')
            if state in ('FAILED','BLOCKED'):self.assertEqual(value['reason'],'local_fixture_reason')
        self.assertEqual(store.flow(row['id']),before)

if __name__=='__main__':unittest.main()
