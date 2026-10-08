"""Single-delay contract against the disposable local PostgreSQL fixture."""
import os
import unittest
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from crm_logic import date,now
from crm_automation_timing import single_delay,scheduled_at,delay_controls
from crm_automation_runtime import advance
from tests import test_crm_native_automations as native

class TimingContract(unittest.TestCase):
    def test_legacy_30_plus_1_is_31_and_idempotent(self):
        old={'trigger':'abandoned','abandonment_seconds':1800,'emails':[{'delay_seconds':60},{'delay_seconds':7200}]}
        original=deepcopy(old);new=single_delay(old)
        self.assertEqual([s['delay_seconds'] for s in new['emails']],[1860,7200])
        self.assertEqual(single_delay(new),new);self.assertEqual(old,original)
        self.assertNotIn('abandonment_seconds',new)
    def test_one_pm_plus_thirty_minutes(self):
        self.assertEqual(scheduled_at('2026-10-06T13:00:00Z',1800).isoformat(),'2026-10-06T13:30:00+00:00')
    def test_delay_units(self):
        self.assertEqual(delay_controls(1800),(30,'Minutes'))
        self.assertEqual(delay_controls(7200),(2,'Hours'))
        self.assertEqual(delay_controls(172800),(2,'Days'))
    def test_analytics_has_no_live_timer(self):
        source=Path('crm_automation_analytics_ui.py').read_text(encoding='utf-8')
        self.assertIn('time_to_send(c,at=timing_now)',source)
        self.assertNotIn('run_every=',source)

@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable database required')
class PersistedTiming(unittest.TestCase):
    setUp=native.NativeAutomationTests.setUp
    published=native.NativeAutomationTests.published
    enroll=native.NativeAutomationTests.enroll
    due=native.NativeAutomationTests.due
    def test_before_due_no_queue_then_due_survives_new_store(self):
        a=self.published(delays=(1800,));j=self.enroll(a)
        self.assertEqual(date(j['next_due_at']),date(j['trigger_at'])+timedelta(minutes=30))
        advance(self.engine,j);self.provider.send.assert_not_called()
        self.assertFalse(self.store.q('SELECT id FROM crm_marketing_sends WHERE enrollment_id=%s',(j['id'],)))
        from crm_automation_store import AutomationStore
        from tests.crm_db_fixture import connect
        self.engine.store=AutomationStore(connect)
        advance(self.engine,self.due(j));advance(self.engine,self.due(j))
        jobs=self.store.q('SELECT * FROM crm_marketing_sends WHERE enrollment_id=%s',(j['id'],))
        self.assertEqual(len(jobs),1)
        self.assertEqual(date(jobs[0]['due_at']),date(self.store.q('SELECT next_due_at FROM crm_automation_enrollments WHERE id=%s',(j['id'],),True)['next_due_at']).replace(microsecond=date(jobs[0]['due_at']).microsecond))
    def test_missing_schedule_backfill_preserves_existing_deadline(self):
        a=self.published(delays=(1800,));j=self.enroll(a);original=date(j['next_due_at'])
        sql=Path('migrations/20261006033000_crm_single_delay.sql').read_text()
        update=sql[sql.index('UPDATE crm_automation_enrollments'):sql.index('COMMIT;')].strip().rstrip(';')
        self.store.q(update)
        self.assertEqual(date(self.store.q('SELECT next_due_at FROM crm_automation_enrollments WHERE id=%s',(j['id'],),True)['next_due_at']),original)
        # Simulate an older nullable schema only inside this rolled-back transaction.
        with self.store.db() as conn:
            conn.execute('ALTER TABLE crm_automation_enrollments ALTER COLUMN next_due_at DROP NOT NULL')
            conn.execute('UPDATE crm_automation_enrollments SET next_due_at=NULL WHERE id=%s',(j['id'],))
            conn.execute(update)
            conn.execute('ALTER TABLE crm_automation_enrollments ALTER COLUMN next_due_at SET NOT NULL')
        self.store.q(update);self.store.q(update)
        self.assertEqual(date(self.store.q('SELECT next_due_at FROM crm_automation_enrollments WHERE id=%s',(j['id'],),True)['next_due_at']),original)
        self.provider.send.assert_not_called()
    def test_two_worker_claims_share_one_persistent_job(self):
        from concurrent.futures import ThreadPoolExecutor
        from crm_automation_store import AutomationStore
        from tests.crm_db_fixture import connect
        a=self.published();j=self.due(self.enroll(a));advance(self.engine,j)
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows=list(pool.map(lambda _:AutomationStore(connect).claim_send(),range(2)))
        claimed=[r for r in rows if r and str(r.get('enrollment_id'))==str(j['id'])]
        self.assertEqual(len(claimed),1)
        self.provider.send.assert_not_called()

    def test_legacy_published_new_entry_freezes_combined_delay(self):
        a=self.published('abandoned',delays=(60,))
        self.store.q("UPDATE crm_automations SET config=jsonb_set(config,'{published}',((config->'published')-'timing_version') || '{\"abandonment_seconds\":1800}'::jsonb) WHERE id=%s",(a['id'],))
        j=self.enroll(self.store.flow(a['id']))
        self.assertEqual(j['steps'][0]['delay_seconds'],1860)
        self.assertEqual(date(j['next_due_at'])-date(j['trigger_at']),timedelta(minutes=31))
