"""Durable acceptance and fenced preparation; disposable SQL and fake providers."""
from copy import deepcopy
import os
import unittest
import uuid
from unittest.mock import patch
from crm_campaign_preparation import accept,lookup,claim,tick
from tests.test_crm_campaign_v2 import profile,authority
from tests.test_crm_send_flow import CFG,LIVE
from tests.test_crm import ADMIN


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class PreparationTests(unittest.TestCase):
    def setUp(self):
        from crm_campaign_store import CampaignStore
        from tests.crm_db_fixture import connect
        self.store=CampaignStore(connect);self.store.db=connect;self.ids=[]
        p=patch('requests.sessions.Session.request',side_effect=AssertionError('No external provider'));p.start();self.addCleanup(p.stop)
        p=patch.object(self.store,'render_settings',return_value=CFG);p.start();self.addCleanup(p.stop)
    def tearDown(self):
        for identity in self.ids:
            self.store.q("UPDATE crm_campaigns SET status='PAUSED' WHERE id=%s AND status='SENDING'",(identity,))
            self.store.q("UPDATE crm_campaign_preparation SET status='FAILED',lease_token=NULL,lease_until=NULL WHERE campaign_id=%s AND status='PREPARING'",(identity,))
    def reviewed(self,count=3,schedule=False):
        from tests.test_crm_simple_editor import document
        from crm_campaign_markets import audience
        from crm_campaign_send import review
        doc=document();doc.update(market='AU',market_audience=True,audience=audience('AU'))
        doc['send_timing']={'mode':'schedule','policy_version':2,'time_basis':'recipient_local','date':'2099-10-10','time':'17:00'} if schedule else {'mode':'now'}
        seed=uuid.uuid4().int%1000000000
        rows=[profile(seed+i,state='NT' if i%2 else 'NSW') for i in range(count)]
        shop=authority(rows)
        editor=self.store.save(ADMIN,'Acceptance fixture '+uuid.uuid4().hex,doc,env=LIVE)
        self.ids.append(editor['id']);result=review(shop,self.store,editor,LIVE)
        self.assertFalse(result['blockers'])
        return editor,result,shop
    def accepted(self,editor,result,op=None):
        return accept(self.store,ADMIN,editor,op or str(uuid.uuid4()),snapshot_id=result['snapshot_id'],confirmed=True,env=LIVE)
    def test_worker_general_store_adapter_publishes_the_accepted_campaign(self):
        from crm_store import Store
        from crm_worker import _prepare_campaign
        from crm_campaign_store import CampaignStore
        editor,result,shop=self.reviewed();self.accepted(editor,result)
        with patch.object(CampaignStore,'render_settings',return_value=CFG):
            self.assertTrue(_prepare_campaign(Store(self.store.connect),shop,env=LIVE))
        self.assertEqual(lookup(self.store,ADMIN,editor['id'])['status'],'SENDING')
        self.assertEqual(self.store.q('SELECT count(*) AS n FROM crm_marketing_sends WHERE campaign_id=%s',(editor['id'],),True)['n'],3)
    def test_four_clicks_session_loss_and_reopen_share_one_operation_without_profiles(self):
        editor,result,shop=self.reviewed();op=str(uuid.uuid4())
        with patch('crm_campaign_send.validate_tracking',side_effect=AssertionError('No render on acceptance')):
            receipts=[self.accepted(editor,result,op) for _ in range(4)]
        self.assertEqual({r['operation_id'] for r in receipts},{op})
        recovered=lookup(self.store,ADMIN,editor['id']);self.assertEqual(recovered['status'],'PREPARING')
        self.assertEqual(self.accepted(editor,result)['operation_id'],op)
        self.assertFalse(self.store.q('SELECT 1 FROM crm_marketing_sends WHERE campaign_id=%s',(editor['id'],)))
        self.assertFalse(self.store.q('SELECT 1 FROM crm_campaigns WHERE id=%s',(editor['id'],)))
        from crm_campaign_home_data import rows,counts
        self.assertEqual(next(r for r in rows(self.store) if str(r['id'])==str(editor['id']))['status'],'PREPARING')
        self.assertGreater(counts(self.store)['active'],0)
        from crm_campaign_progress import read_progress
        progress=read_progress(self.store,[editor['id']])[str(editor['id'])]
        self.assertEqual(progress['total'],3);self.assertFalse(progress['attention']);self.assertFalse(progress['started'])
    def test_worker_prepares_original_identity_and_local_due_times_once(self):
        editor,result,shop=self.reviewed(schedule=True);r=self.accepted(editor,result)
        with patch.dict(os.environ,LIVE):self.assertTrue(tick(self.store,shop,env=LIVE))
        self.assertEqual(lookup(self.store,ADMIN,editor['id'])['status'],'SCHEDULED')
        jobs=self.store.q('SELECT * FROM crm_marketing_sends WHERE campaign_id=%s',(editor['id'],))
        self.assertEqual(len(jobs),3);self.assertEqual(len({j['due_at'] for j in jobs}),2)
        self.assertEqual(self.accepted(editor,result)['operation_id'],r['operation_id'])
        self.assertFalse(tick(self.store,shop,env=LIVE))
        self.assertEqual(self.store.draft(editor['id'])['document'],editor['document'])
    def test_expired_claim_restart_fences_old_worker(self):
        editor,result,shop=self.reviewed();self.accepted(editor,result)
        old=claim(self.store);self.assertIsNone(claim(self.store))
        self.store.q("UPDATE crm_campaign_preparation SET lease_until=now()-interval '1 second' WHERE campaign_id=%s",(editor['id'],))
        new=claim(self.store);self.assertNotEqual(old['lease_token'],new['lease_token'])
        from crm_campaign_send import queue_campaign
        with self.assertRaisesRegex(ValueError,'lease changed'):
            queue_campaign(shop,self.store,ADMIN,editor,str(old['operation_id']),env=LIVE,snapshot_id=result['snapshot_id'],preparation_token=str(old['lease_token']))
        self.assertFalse(self.store.q('SELECT 1 FROM crm_marketing_sends WHERE campaign_id=%s',(editor['id'],)))
        queue_campaign(shop,self.store,ADMIN,editor,str(new['operation_id']),env=LIVE,snapshot_id=result['snapshot_id'],preparation_token=str(new['lease_token']))
        self.assertEqual(lookup(self.store,ADMIN,editor['id'])['status'],'SENDING')
    def test_frozen_draft_and_request_and_failed_audit(self):
        editor,result,shop=self.reviewed()
        with patch.object(self.store,'_history',side_effect=ValueError('Audit failure')):
            with self.assertRaisesRegex(ValueError,'Audit failure'):self.accepted(editor,result)
        self.assertIsNone(lookup(self.store,ADMIN,editor['id']))
        self.accepted(editor,result)
        for sql in ["UPDATE crm_campaign_drafts SET version=version+1 WHERE id=%s",
                    "UPDATE crm_campaign_preparation SET snapshot_id=gen_random_uuid() WHERE campaign_id=%s"]:
            with self.assertRaisesRegex(Exception,'immutable'):self.store.q(sql,(editor['id'],))
        from crm_campaign_send import queue_campaign
        with self.assertRaisesRegex(ValueError,'already accepted'):queue_campaign(shop,self.store,ADMIN,editor,str(uuid.uuid4()),env=LIVE,snapshot_id=result['snapshot_id'])
    def test_permission_confirmation_and_stale_content_rejected(self):
        editor,result,shop=self.reviewed()
        with self.assertRaises(PermissionError):accept(self.store,{},editor,str(uuid.uuid4()),snapshot_id=result['snapshot_id'],confirmed=True,env=LIVE)
        with self.assertRaises(ValueError):accept(self.store,ADMIN,editor,str(uuid.uuid4()),snapshot_id=result['snapshot_id'],env=LIVE)
        changed=deepcopy(editor);changed['version']+=1
        with self.assertRaisesRegex(ValueError,'changed'):self.accepted(changed,result)
    def test_lost_commit_ack_recovers_without_replacement(self):
        editor,result,shop=self.reviewed();op=str(uuid.uuid4());original=self.store.db
        class LostAck:
            def __init__(self):self.inner=original()
            def __enter__(self):return self.inner.__enter__()
            def __exit__(self,typ,*args):
                self.inner.__exit__(typ,*args)
                if typ is None:raise TimeoutError('Lost post-commit acknowledgement')
        with patch.object(self.store,'db',LostAck):
            with self.assertRaises(TimeoutError):self.accepted(editor,result,op)
        self.assertEqual(lookup(self.store,ADMIN,editor['id'])['operation_id'],op)
        self.assertEqual(self.accepted(editor,result,op)['operation_id'],op)
        self.assertEqual(len(self.store.q('SELECT campaign_id FROM crm_campaign_preparation WHERE campaign_id=%s',(editor['id'],))),1)
    def test_expired_review_and_changed_settings_release_no_queue(self):
        editor,result,shop=self.reviewed()
        stale=self.store.q('''INSERT INTO crm_campaign_snapshots(campaign_id,campaign_version,document,render_settings,counts,recipients,schedule,created_at)
          SELECT campaign_id,campaign_version,document,render_settings,counts,recipients,schedule,now()-interval '10 minutes'
          FROM crm_campaign_snapshots WHERE id=%s RETURNING id''',(result['snapshot_id'],),True)
        with self.assertRaisesRegex(ValueError,'expired'):self.accepted(editor,{**result,'snapshot_id':stale['id']})
        self.accepted(editor,result)
        with patch.object(self.store,'render_settings',return_value={**CFG,'postal':'Changed address'}):tick(self.store,shop,env=LIVE)
        self.assertEqual(lookup(self.store,ADMIN,editor['id'])['status'],'FAILED')
        self.assertFalse(self.store.q('SELECT 1 FROM crm_marketing_sends WHERE campaign_id=%s',(editor['id'],)))
        self.store.archive(ADMIN,editor['id'],editor['version'])
        archived=self.store.draft(editor['id'])
        self.assertIsNotNone(archived['archived_at'])
        self.assertEqual(archived['document'],editor['document'])
        self.assertEqual(lookup(self.store,ADMIN,editor['id'])['status'],'FAILED')
    def test_two_application_sessions_resolve_same_accepted_identity(self):
        from concurrent.futures import ThreadPoolExecutor
        editor,result,shop=self.reviewed()
        with ThreadPoolExecutor(max_workers=2) as pool:
            requests=[pool.submit(self.accepted,deepcopy(editor),result,str(uuid.uuid4())) for _ in range(2)]
            replies=[f.result() for f in requests]
        self.assertEqual(len({r['operation_id'] for r in replies}),1)
        self.assertEqual(len(self.store.q('SELECT campaign_id FROM crm_campaign_preparation WHERE campaign_id=%s',(editor['id'],))),1)
        from crm_campaign_send import review
        with self.assertRaisesRegex(ValueError,'already accepted'):review(shop,self.store,editor,LIVE)
    def test_database_rejects_unfenced_or_changed_snapshot_publication(self):
        editor,result,shop=self.reviewed();self.accepted(editor,result);job=claim(self.store)
        from crm_campaign_send import queue_campaign
        kwargs={'env':LIVE,'snapshot_id':result['snapshot_id'],'preparation_token':str(job['lease_token'])}
        with patch('crm_campaign_preparation.fence',return_value=None):
            with self.assertRaisesRegex(Exception,'current preparation lease'):
                queue_campaign(shop,self.store,ADMIN,editor,str(job['operation_id']),**kwargs)
        from crm_campaign_snapshot import load
        bad=load(self.store,editor['id'],result['snapshot_id']);bad['document']['content']['subject']='Unreviewed subject'
        with patch('crm_campaign_snapshot.load',return_value=bad):
            with self.assertRaisesRegex(Exception,'preserve the confirmed snapshot'):
                queue_campaign(shop,self.store,ADMIN,editor,str(job['operation_id']),**kwargs)
        self.assertFalse(self.store.q('SELECT 1 FROM crm_campaigns WHERE id=%s',(editor['id'],)))
        self.assertFalse(self.store.q('SELECT 1 FROM crm_marketing_sends WHERE campaign_id=%s',(editor['id'],)))
    def test_consent_webhook_during_preparation_is_blocked_at_native_dispatch(self):
        editor,result,shop=self.reviewed();self.accepted(editor,result)
        original=shop.customer_batch.side_effect
        customer=shop.campaign_subscribers.return_value['nodes'][0]
        def changed_during_read(ids,**kwargs):
            rows=original(ids,**kwargs)
            self.store.q('''INSERT INTO crm_webhook_events(provider,event_id,topic,related_customer_id,occurred_at)
              VALUES('shopify',%s,'customers_email_marketing_consent/update',%s,now())''',(str(uuid.uuid4()),customer['id']))
            return rows
        shop.customer_batch.side_effect=changed_during_read
        tick(self.store,shop,env=LIVE)
        campaign=self.store.q('SELECT * FROM crm_campaigns WHERE id=%s',(editor['id'],),True)
        jobs=self.store.q('SELECT * FROM crm_marketing_sends WHERE campaign_id=%s',(editor['id'],))
        from crm_campaign_dispatch import stop_state
        from crm_logic import now
        with self.store.db() as conn:reasons=stop_state(conn,campaign,jobs,16,now())
        self.assertEqual(next(r['reason'] for r in reasons if r['id']==next(j['id'] for j in jobs if j['shopify_customer_id']==customer['id'])),'consent_changed_after_snapshot')
    def test_changed_recipient_timezone_is_blocked_without_rewriting_review(self):
        editor,result,shop=self.reviewed(schedule=True);self.accepted(editor,result)
        first=shop.campaign_subscribers.return_value['nodes'][0]
        first['defaultAddress']={'countryCodeV2':'AU','provinceCode':'QLD','zip':'4000'}
        tick(self.store,shop,env=LIVE)
        changed=self.store.q('SELECT status,error_code FROM crm_marketing_sends WHERE campaign_id=%s AND shopify_customer_id=%s',(editor['id'],first['id']),True)
        self.assertEqual(changed,{'status':'BLOCKED','error_code':'recipient_timezone_changed'})
        self.assertEqual(self.store.q('SELECT schedule FROM crm_campaign_snapshots WHERE id=%s',(result['snapshot_id'],),True)['schedule'],result['schedule'])
    def test_suppression_and_consent_changes_block_without_adding_members(self):
        editor,result,shop=self.reviewed();self.accepted(editor,result)
        customer=shop.campaign_subscribers.return_value['nodes'][0]
        customer['emailMarketingConsent']['marketingState']='UNSUBSCRIBED'
        from crm_logic import recipient_hash
        other=shop.campaign_subscribers.return_value['nodes'][1]
        self.store.q("INSERT INTO crm_suppressions(recipient_hash,shopify_customer_id,reason,source) VALUES(%s,%s,'unsubscribe','fixture')",(recipient_hash(other['email']),other['id']))
        tick(self.store,shop,env=LIVE)
        jobs=self.store.q('SELECT status FROM crm_marketing_sends WHERE campaign_id=%s',(editor['id'],))
        self.assertEqual(len(jobs),3);self.assertEqual(sum(j['status']=='BLOCKED' for j in jobs),2)
    def test_unavailable_checks_retry_bounded_and_marketing_off_never_claims(self):
        editor,result,shop=self.reviewed();self.accepted(editor,result)
        self.assertFalse(tick(self.store,shop,env={**LIVE,'CRM_MARKETING_ENABLED':'false'}))
        self.assertEqual(self.store.q('SELECT attempts FROM crm_campaign_preparation WHERE campaign_id=%s',(editor['id'],),True)['attempts'],0)
        shop.customer_batch.side_effect=TimeoutError('Fixture timeout')
        for _ in range(3):
            tick(self.store,shop,env=LIVE)
            self.store.q("UPDATE crm_campaign_preparation SET retry_at=now() WHERE campaign_id=%s",(editor['id'],))
        self.assertEqual(lookup(self.store,ADMIN,editor['id'])['status'],'FAILED')
        self.assertFalse(self.store.q('SELECT 1 FROM crm_marketing_sends WHERE campaign_id=%s',(editor['id'],)))
