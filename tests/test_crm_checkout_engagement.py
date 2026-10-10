"""Status evidence projection and persisted webhook integration (local fixtures only)."""
from copy import deepcopy
from datetime import timedelta
import uuid
from crm_checkout_progress import progress, columns
from crm_webhooks import receive_resend, receive_shopify
from tests import test_crm_checkout_progress as base


class Engagement(base.Projection):
    def test_progression_and_click_without_open(self):
        self.accepted()
        receipt=self.row['sends'][0]
        for evidence,label in (({},'Sent'),({'opened':True},'Opened'),({'clicked':True},'Clicked')):
            receipt.update(evidence)
            self.assertEqual(self.labels()[0],label+' ✓')
            self.assertEqual(progress(self.row,self.schema)[0]['tone'],'green')
        receipt.pop('opened')
        self.assertEqual(self.labels()[0],'Clicked ✓')
        self.row['order_id']='verified-order'
        self.assertEqual(self.labels()[0],'Recovered ✓')

    def test_latest_sent_recovery_without_engagement_and_reordered_columns(self):
        for index in range(3):self.accepted(index)
        self.row['sends'][0]['opened']=True
        self.row['sends'][1]['clicked']=True
        self.row['completion_verified']=True
        self.assertEqual(self.labels(),['Opened ✓','Clicked ✓','Recovered ✓'])
        self.assertEqual(self.labels(schema=list(reversed(self.schema))),['Recovered ✓','Clicked ✓','Opened ✓'])
        self.row['sends'][2]['status']='BLOCKED'
        self.assertEqual(self.labels(),['Opened ✓','Recovered ✓','Purchased'])

    def test_latest_receipt_time_and_strict_evidence(self):
        for index in range(2):self.accepted(index)
        self.row['sends'][0]['submitted_at']=self.at
        self.row['sends'][1]['submitted_at']=self.at-timedelta(hours=1)
        self.row['order_id']='verified-order'
        self.assertEqual(self.labels(),['Recovered ✓','Sent ✓','Purchased'])
        self.row.pop('order_id');self.row['flow_status']='RECOVERED'
        self.assertEqual(self.labels(),['Sent ✓','Sent ✓','Purchased'])

    def test_unsent_other_journey_and_step_never_inherit_engagement(self):
        self.accepted();self.row['sends'][0].update(opened=True,clicked=True)
        for change in ({'provider_id':None},{'status':'PENDING'},{'enrollment_id':'other'},{'step_id':'other'}):
            row=deepcopy(self.row);row['sends'][0].update(change)
            self.assertNotIn(self.labels(row)[0],['Opened ✓','Clicked ✓','Recovered ✓'])
        self.row['sends']=[];self.row['order_id']='order'
        self.assertEqual(self.labels(),['Purchased']*3)

    def test_completed_historical_extra_column_stays_not_applicable(self):
        self.accepted();self.row['flow_status']='COMPLETED'
        schema=columns(self.steps+[{'step_id':'new'}])
        self.assertEqual(self.labels(schema=schema)[-1],'Not applicable')


class PersistedEngagement(base.PersistedProgress):
    def test_webhook_duplicate_delayed_reload_and_signed_order_recovery(self):
        from crm_automation_runtime import reconcile,advance
        a,key,c,_=self.automatic();reconcile(self.engine,a)
        row=self.read(a,key)
        j=self.store.q('SELECT * FROM crm_automation_enrollments WHERE id=%s',(row['enrollment_id'],),True)
        advance(self.engine,j);advance(self.engine,j);self.engine.send_one();self.engine.send_one()
        receipt=self.read(a,key)['sends'][0]
        def label():
            row=self.read(a,key)
            return progress(row,columns(row['published_steps']))[0]['label']
        def event(kind,event_id=None,offset=0):
            return receive_resend(self.store,event_id or uuid.uuid4().hex,{
                'type':'email.'+kind,'created_at':(self.at+timedelta(seconds=offset)).isoformat(),
                'data':{'email_id':receipt['provider_id'],'click':{'link':'https://example.test/products/frame'}}})
        from crm_logic import now
        self.at=now()
        event('delivered');self.assertEqual(label(),'Sent ✓')
        event('opened');self.assertEqual(label(),'Opened ✓')
        eid=uuid.uuid4().hex
        self.assertTrue(event('clicked',eid));self.assertFalse(event('clicked',eid))
        event('opened',offset=-10);event('delivered',offset=-20)
        self.assertEqual(label(),'Clicked ✓')
        # Exact shop-scoped checkout token, not a customer-wide order guess.
        from urllib.parse import urlsplit
        token=urlsplit(c['abandonedCheckoutUrl']).path.split('/')[2]
        receive_shopify(self.store,'orders/create',uuid.uuid4().hex,{
            'id':12345,'checkout_token':token,'customer':{'id':1},
            'created_at':self.at.isoformat(),'updated_at':self.at.isoformat()},self.at.isoformat())
        self.assertEqual(label(),'Recovered ✓')
        event('opened',offset=-30);self.assertEqual(label(),'Recovered ✓')
        self.provider.send.assert_called_once()
