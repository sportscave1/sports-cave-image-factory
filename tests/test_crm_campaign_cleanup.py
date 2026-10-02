"""Disposable SQL and mocked UI only; no production connections or sends."""
import os
import unittest
import uuid
from concurrent.futures import Future
from unittest.mock import Mock,patch
from crm_campaign_delete import delete_campaign,remove_cached_row
from crm_campaign_home_data import counts,rows,delivery_summary,reporting_window
from crm_campaign_home import kpis
from tests.test_crm import ADMIN


class CacheTests(unittest.TestCase):
    def test_trash_is_visible_only_for_canonical_eligibility(self):
        from streamlit.testing.v1 import AppTest
        from tests.test_crm_campaign_home import SCRIPT
        for status,deletable,archived in (('DRAFT',True,False),('ARCHIVED',True,True),('SENT',True,False),('SENT',False,False)):
            code=SCRIPT.replace('else:f.set_result([record()])',
                "else:\n  row=record();row.update(status="+repr(status)+",deletable="+repr(deletable)+",archived_at="+repr('2026-10-01' if archived else None)+");f.set_result([row])")
            app=AppTest.from_string(code).run()
            self.assertFalse(app.exception)
            self.assertEqual(sum(b.label=='Delete campaign' for b in app.button),int(deletable))

    def test_archived_cache_counts_decrement_without_touching_delivery(self):
        store=Mock(connect=None)
        totals=dict(all_count=3,drafts=1,archived=2,active=0,sent=0)
        state={'campaign_home_resolved':{(None,('counts',)):totals},'campaign_home_cache':{}}
        remove_cached_row(state,store,dict(id='archived',archived_at='2026-10-01',delivery_status=None))
        self.assertEqual(state['campaign_home_counts']['all_count'],2)
        self.assertEqual(state['campaign_home_counts']['archived'],1)
        self.assertEqual(state['campaign_home_counts']['drafts'],1)

    def test_delete_detaches_stale_reads_and_retains_kpis(self):
        store=Mock(connect=None);state={'campaign_home_cache':{},'campaign_home_resolved':{}}
        for name,value in [('counts',dict(all_count=3,drafts=2,archived=1,sent=0,active=0)),
                           ('delivery',dict(sent_emails=4,bounce_rate=25,click_rate=50)),
                           ('attribution',dict(orders=2)),('table',[{'id':'delete'},{'id':'keep'}])]:
            identity=(None,(name,));f=Future();f.set_result(value)
            state['campaign_home_cache'][identity]=(0,f);state['campaign_home_resolved'][identity]=value
        delivery=state['campaign_home_cache'][(None,('delivery',))]
        remove_cached_row(state,store,dict(id='delete',archived_at=None,delivery_status=None))
        self.assertIs(state['campaign_home_cache'][(None,('delivery',))],delivery)
        self.assertEqual(state['campaign_home_counts']['all_count'],2)
        self.assertEqual(state['campaign_home_counts']['drafts'],1)
        self.assertEqual(state['campaign_home_resolved'][(None,('table',))],[{'id':'keep'}])
        self.assertNotIn((None,('table',)),state['campaign_home_cache'])
        self.assertEqual(state['campaign_home_resolved'][(None,('attribution',))],{'orders':2})

    def test_bounce_unknown_and_known_zero_are_distinct(self):
        self.assertIn('<strong>—</strong>',kpis({'bounce_rate':None}))
        self.assertIn('<strong>0.0%</strong>',kpis({'bounce_rate':0}))
        self.assertNotIn('Revenue',kpis({'revenue':{'NZD':999}}))


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable local SQL required')
class DeletionSQLTests(unittest.TestCase):
    def setUp(self):
        from crm_campaign_store import CampaignStore
        from tests.crm_db_fixture import connect
        from tests.test_crm_simple_editor import document
        from tests.test_crm_resend_marketing import ENV
        from crm_campaign_content import settings
        self.store=CampaignStore(connect);self.store.seed()
        self.patch=patch.object(self.store,'render_settings',return_value=settings(ENV));self.patch.start();self.addCleanup(self.patch.stop)
        self.doc=document();self.env=ENV

    def draft(self):
        return self.store.save(ADMIN,'Cleanup fixture '+uuid.uuid4().hex,self.doc,env=self.env)

    def campaign(self,row,status='SENT'):
        self.store.q('''INSERT INTO crm_campaigns(id,name,segment_definition_id,template_id,template_version,status,sent_at)
          SELECT %s,%s,(SELECT id FROM crm_segment_definitions LIMIT 1),id,version,%s,now()
          FROM crm_templates LIMIT 1''',(row['id'],row['name'],status))

    def receipt(self,row,status='ACCEPTED',days=0,test=False):
        return self.store.q('''INSERT INTO crm_marketing_sends(campaign_id,idempotency_key,template_id,template_version,
          status,provider_email_id,first_submitted_at,test_send)
          SELECT %s,%s,template_id,template_version,%s,%s,now()-(%s*interval '1 day'),%s
          FROM crm_campaigns WHERE id=%s RETURNING id''',
          (row['id'],str(uuid.uuid4()),status,str(uuid.uuid4()) if status=='ACCEPTED' else None,days,test,row['id']),True)['id']

    def test_draft_archived_and_empty_sent_tombstones_preserve_rows_and_audit(self):
        for mode in ('draft','archived','empty'):
            row=self.draft()
            if mode=='archived':
                self.store.archive(ADMIN,row['id'],row['version']);row=self.store.draft(row['id'])
            if mode=='empty':self.campaign(row);self.receipt(row,'FAILED')
            before=counts(self.store)
            self.assertTrue(rows(self.store,search=row['name'])[0]['deletable'])
            delete_campaign(self.store,ADMIN,row['id'],row['version'],confirmed=True)
            self.assertFalse(rows(self.store,search=row['name']))
            self.assertEqual(counts(self.store)['all_count'],before['all_count']-1)
            self.assertEqual(self.store.draft(row['id'])['name'],row['name'])
            self.assertEqual(self.store.history(row['id'])[0]['action'],'campaign_deleted')
            if mode=='empty':self.assertEqual(self.store.q('SELECT count(*) n FROM crm_marketing_sends WHERE campaign_id=%s',(row['id'],),True)['n'],1)

    def test_all_unsent_draft_authoring_states_are_deletable(self):
        for status in ('DRAFT','NEEDS_REVIEW','TEST_READY'):
            row=self.draft()
            self.store.q('UPDATE crm_campaign_drafts SET status=%s WHERE id=%s',(status,row['id']))
            self.assertTrue(rows(self.store,search=row['name'])[0]['deletable'])
            delete_campaign(self.store,ADMIN,row['id'],row['version'],confirmed=True)
            self.assertFalse(rows(self.store,search=row['name']))

    def test_real_receipts_active_sends_events_and_orders_fail_closed(self):
        for mode in ('accepted','uncertain','sending','event','order'):
            row=self.draft();self.campaign(row,'SENDING' if mode=='sending' else 'SENT')
            if mode in ('accepted','uncertain','event'):
                send=self.receipt(row,'UNCERTAIN' if mode=='uncertain' else 'ACCEPTED' if mode=='accepted' else 'FAILED')
                if mode=='event':self.store.q("INSERT INTO crm_delivery_events(event_id,provider_id,event_type,occurred_at,send_id) VALUES(%s,%s,'email.clicked',now(),%s)",(str(uuid.uuid4()),str(uuid.uuid4()),send))
            if mode=='order':self.store.q("INSERT INTO crm_order_attribution(shopify_order_id,campaign_id,campaign_key,order_created_at,visit_at,amount,currency,eligible) VALUES(%s,%s,%s,now(),now(),10,'NZD',true)",(str(uuid.uuid4()),row['id'],row['document']['campaign_key']))
            self.assertFalse(rows(self.store,search=row['name'])[0]['deletable'])
            with self.assertRaises(ValueError):delete_campaign(self.store,ADMIN,row['id'],row['version'],confirmed=True)
            self.assertTrue(rows(self.store,search=row['name']))

    def test_cancel_permission_and_version_do_not_mutate(self):
        row=self.draft()
        for user,version,confirmed,error in ((ADMIN,row['version'],False,ValueError),(ADMIN,999,True,ValueError),({'is_active':False},row['version'],True,PermissionError)):
            with self.assertRaises(error):delete_campaign(self.store,user,row['id'],version,confirmed=confirmed)
        self.assertEqual(self.store.draft(row['id'])['version'],row['version'])

    def test_reviewed_cleanup_preserves_two_receipts_and_tombstones_history(self):
        from scripts.cleanup_campaign_home import cleanup,inventory
        keep=[self.draft(),self.draft()];draft=self.draft();archived=self.draft()
        for row in (*keep,archived): self.campaign(row);self.receipt(row)
        self.store.archive(ADMIN,archived['id'],archived['version']);archived=self.store.draft(archived['id'])
        ids={str(r['id']) for r in (*keep,draft,archived)}
        # Limit this test's inventory to its own fabricated namespace; the real
        # operator command always requires coverage of the entire visible DB.
        def isolated(conn):return [r for r in inventory(conn) if str(r['id']) in ids]
        plan={'keep':[str(r['id']) for r in keep], 'remove':[{'id':str(r['id']),'version':r['version']} for r in (draft,archived)]}
        receipts=self.store.q('SELECT count(*) n FROM crm_marketing_sends',one=True)['n']
        with patch('scripts.cleanup_campaign_home.inventory',side_effect=isolated):
            preview=cleanup(self.store,plan)
            self.assertFalse(preview['applied']);self.assertEqual(len(preview['before']),4)
            self.assertFalse(preview['tombstoned'])
            result=cleanup(self.store,plan,apply=True,actor=ADMIN['id'])
        self.assertEqual(len(result['after']),2)
        self.assertEqual(set(result['preserved']),set(plan['keep']))
        self.assertEqual(self.store.q('SELECT count(*) n FROM crm_marketing_sends',one=True)['n'],receipts)
        self.assertEqual(self.store.draft(archived['id'])['name'],archived['name'])
        self.assertEqual(self.store.history(archived['id'])[0]['action'],'campaign_deleted')

    def test_cleanup_rejects_title_guess_partial_inventory_and_nonarchived_success(self):
        from scripts.cleanup_campaign_home import cleanup,inventory
        rows_=[self.draft() for _ in range(3)]
        for row in rows_:self.campaign(row);self.receipt(row)
        ids={str(r['id']) for r in rows_}
        def isolated(conn):return [r for r in inventory(conn) if str(r['id']) in ids]
        with patch('scripts.cleanup_campaign_home.inventory',side_effect=isolated):
            for plan in ({'keep':[str(r['id']) for r in rows_[:2]],'remove':[]},
                         {'keep':[str(r['id']) for r in rows_[:2]],'remove':[{'id':str(rows_[2]['id']),'version':rows_[2]['version']}]}):
                with self.assertRaises(ValueError):cleanup(self.store,plan,apply=True,actor=ADMIN['id'])
        for row in rows_:self.assertTrue(rows(self.store,search=row['name']))

    def test_bounce_cohort_deduplicates_verified_events_excludes_tests_and_old_sends(self):
        row=self.draft();self.campaign(row)
        for status,days,test,bounce in [('ACCEPTED',0,False,True),('ACCEPTED',0,False,False),('ACCEPTED',40,False,True),('ACCEPTED',0,True,True),('FAILED',0,False,True)]:
            send=self.receipt(row,status,days,test)
            if bounce:
                for _ in range(2):self.store.q("INSERT INTO crm_delivery_events(event_id,provider_id,event_type,occurred_at,send_id) VALUES(%s,%s,'email.bounced',now(),%s)",(str(uuid.uuid4()),str(uuid.uuid4()),send))
        before=delivery_summary(self.store,reporting_window())
        # Isolate this fixture cohort using a future window: zero denominator stays unknown.
        from datetime import datetime,timedelta,timezone
        now=datetime.now(timezone.utc)
        self.assertIsNone(delivery_summary(self.store,(now+timedelta(days=1),now+timedelta(days=31)))['bounce_rate'])
        total=self.store.q("SELECT count(*) n FROM crm_marketing_sends WHERE NOT test_send AND status='ACCEPTED' AND first_submitted_at>=now()-interval '30 days'",one=True)['n']
        bounced=self.store.q("SELECT count(*) n FROM crm_marketing_sends s WHERE NOT test_send AND status='ACCEPTED' AND first_submitted_at>=now()-interval '30 days' AND EXISTS(SELECT 1 FROM crm_delivery_events e WHERE e.send_id=s.id AND e.event_type='email.bounced')",one=True)['n']
        self.assertAlmostEqual(float(before['bounce_rate']),100*bounced/total)
