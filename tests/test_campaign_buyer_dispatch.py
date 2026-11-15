"""Disposable SQL + mocked Shopify/Resend: real review, queue and dispatch."""
import os, unittest, uuid
from copy import deepcopy
from unittest.mock import patch
from tests import test_crm_batch_dispatch as batch_tests
from tests.test_crm_campaign_v2 import authority, profile
from tests.test_crm_simple_editor import document
from tests.test_crm_send_flow import LIVE, CFG
from tests.test_crm import ADMIN
from crm_campaign_send import review, queue_campaign
from crm_campaign_dispatch import dispatch
from crm_campaign_markets import audience
from crm_logic import recipient_hash

@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class BuyerDispatchTests(unittest.TestCase):
    setUp=batch_tests.DispatchTests.setUp
    tearDown=batch_tests.DispatchTests.tearDown
    sends=batch_tests.DispatchTests.sends
    states=batch_tests.DispatchTests.states

    def queue_buyers(self, scheduled=False):
        seed=uuid.uuid4().int%100000000000
        rows=[profile(seed+i,'NZ') for i in range(3)]
        self.shop=authority(rows);self.engine.shop=self.shop
        self.members={r['id'] for r in rows}
        self.shop.campaign_member_ids.side_effect=lambda q:set(self.members)
        segment='gid://shopify/Segment/123'
        self.shop.segment.return_value={'id':segment,'name':'Cricket Buyers','query':"products_purchased MATCHES (tag CONTAINS 'SC_SPORT_CRICKET')"}
        doc=document();doc.update(market='NZ',market_audience=True,audience=audience('NZ'),
            shopify_segment_ids=[segment],shopify_segment_store='fixture')
        if scheduled:
            doc['send_timing']={'mode':'schedule','policy_version':2,'time_basis':'campaign_timezone','date':'2099-10-11','time':'07:00','timezone':'Pacific/Auckland'}
        with patch.object(self.store,'render_settings',return_value=deepcopy(CFG)),patch.dict(os.environ,LIVE):
            editor=self.store.save(ADMIN,'Buyer fixture '+uuid.uuid4().hex,doc,env=LIVE)
            restored=self.store.draft(editor['id']);self.assertEqual(restored['document']['shopify_segment_ids'],[segment])
            verified=review(self.shop,self.store,editor,LIVE)
            self.assertFalse(verified['blockers'])
            result=queue_campaign(self.shop,self.store,ADMIN,editor,str(uuid.uuid4()),env=LIVE,snapshot_id=verified['snapshot_id'])
        self.ids.append(editor['id']);self.assertEqual(result['recipients'],3)
        self.store.q("UPDATE crm_marketing_sends SET due_at=now()-interval '1 second' WHERE campaign_id=%s",(editor['id'],))
        if scheduled:self.store.q("UPDATE crm_campaigns SET status='SENDING' WHERE id=%s",(editor['id'],))
        return editor['id'],rows

    def test_send_now_rechecks_membership_and_deduplicates(self):
        identity,rows=self.queue_buyers()
        self.members.remove(rows[0]['id'])
        self.assertTrue(dispatch(self.engine))
        sent=[m for _,batch in self.transport.calls for m in batch]
        self.assertEqual(len(sent),2)
        self.assertNotIn(rows[0]['email'],[m['to'][0] for m in sent])
        dispatch(self.engine)
        self.assertEqual(len(self.transport.calls),1)

    def test_scheduled_rechecks_current_membership(self):
        identity,rows=self.queue_buyers(scheduled=True)
        self.members.clear()
        dispatch(self.engine)
        self.assertEqual(self.transport.calls,[])
        self.assertEqual({r['status'] for r in self.sends(identity)},{'BLOCKED'})

    def test_deleted_segment_blocks_without_provider_call_then_recovers(self):
        identity,_=self.queue_buyers();definition=self.shop.segment.return_value
        self.shop.segment.return_value=None
        with self.assertRaisesRegex(ValueError,'unavailable'):dispatch(self.engine)
        self.assertEqual(self.transport.calls,[])
        self.shop.segment.return_value=definition
        dispatch(self.engine)
        self.assertEqual(sum(len(batch) for _,batch in self.transport.calls),3)

    def test_outage_fails_closed(self):
        self.queue_buyers();self.shop.campaign_member_ids.side_effect=TimeoutError('Shopify offline')
        with self.assertRaises(TimeoutError):dispatch(self.engine)
        self.assertEqual(self.transport.calls,[])

    def test_projection_sql_atomic_cache_and_rename(self):
        from crm_buyer_segments import synchronize,snapshot_key
        from unittest.mock import Mock
        shop=Mock(namespace='projection-'+uuid.uuid4().hex)
        shop.segments.return_value={'nodes':[{'id':'gid://shopify/Segment/321','name':'Cricket Buyers','query':'actual saved query'}],'pageInfo':{}}
        shop.campaign_member_ids.return_value={'gid://shopify/Customer/123'}
        first=synchronize(shop,self.store)
        self.assertEqual(synchronize(shop,self.store),first)
        self.assertEqual(shop.campaign_member_ids.call_count,1)
        cached=self.store.state(snapshot_key(shop));cached['timestamp']=0
        self.store.set_state(snapshot_key(shop),cached)
        shop.segments.return_value['nodes'][0]['name']='Renamed Cricket'
        second=synchronize(shop,self.store)
        self.assertEqual(second['segments']['gid://shopify/Segment/321']['name'],'Renamed Cricket')
        self.assertEqual(second['bindings']['Cricket Buyers'],'gid://shopify/Segment/321')
