"""Local schedule amendments: frozen identities, atomic rollback and replay."""
import json
import uuid
from unittest.mock import patch
from tests.test_crm_campaign_v8 import DurableTests,timing
from tests.test_crm import ADMIN
from crm_campaign_schedule import change_pending

class ScheduleManagementTests(DurableTests):
    def test_recipient_local_distinct_due_times_and_original_lock(self):
        local={'mode':'schedule','policy_version':2,'time_basis':'recipient_local','date':'2099-10-10','time':'17:00'}
        from tests.test_crm_campaign_v2 import profile
        states=iter(('NSW','NT','WA'))
        with patch('tests.test_crm_campaign_v8.timing',return_value=local),patch('tests.test_crm_campaign_v8.profile',side_effect=lambda i:profile(i,'AU',next(states))):
            saved=self.queue()
        identity=saved['id']
        rows=self.store.q('SELECT * FROM crm_marketing_sends WHERE campaign_id=%s ORDER BY recipient_hash',(identity,))
        original=self.store.q('SELECT * FROM crm_campaigns WHERE id=%s',(identity,),True)
        proposed={'mode':'schedule','policy_version':2,'time_basis':'recipient_local','date':'2099-10-11','time':'17:00'}
        result=self.change(ADMIN,identity,proposed,str(uuid.uuid4()),confirmed=True)
        after=self.store.q('SELECT * FROM crm_marketing_sends WHERE campaign_id=%s ORDER BY recipient_hash',(identity,))
        self.assertEqual(len({r['due_at'] for r in after}),3)
        self.assertEqual([r['id'] for r in rows],[r['id'] for r in after])
        self.assertTrue(all(r['due_at']!=old['due_at'] for r,old in zip(after,rows)))
        self.assertEqual(self.store.q('SELECT scheduled_at FROM crm_campaigns WHERE id=%s',(identity,),True)['scheduled_at'],original['scheduled_at'])
        with self.assertRaisesRegex(RuntimeError,'locked'):
            self.store.q("UPDATE crm_campaigns SET scheduled_at=now() WHERE id=%s",(identity,))

    def test_initial_block_remains_blocked_with_identical_due(self):
        saved=self.queue();identity=saved['id']
        self.store.q("UPDATE crm_marketing_sends SET status='BLOCKED',error_code='local_suppression' WHERE id=(SELECT id FROM crm_marketing_sends WHERE campaign_id=%s LIMIT 1)",(identity,))
        blocked=self.store.q("SELECT * FROM crm_marketing_sends WHERE campaign_id=%s AND status='BLOCKED'",(identity,),True)
        self.change(ADMIN,identity,timing(day='2099-10-11'),str(uuid.uuid4()),confirmed=True)
        self.assertEqual(self.store.q('SELECT * FROM crm_marketing_sends WHERE id=%s',(blocked['id'],),True),blocked)

    def test_old_acknowledged_operation_replays_without_reverting(self):
        saved=self.queue();identity=saved['id'];op=str(uuid.uuid4())
        first=self.change(ADMIN,identity,timing(day='2099-10-11'),op,confirmed=True)
        latest=self.change(ADMIN,identity,timing(day='2099-10-12'),str(uuid.uuid4()),confirmed=True)
        self.assertEqual(change_pending(self.store,ADMIN,identity,timing(day='2099-10-11'),op,confirmed=True),first)
        self.assertEqual(self.store.state('campaign-timing:'+str(identity)),latest)

    def test_failed_audit_rolls_back_all_due_times_and_receipt(self):
        saved=self.queue();identity=saved['id'];op=str(uuid.uuid4())
        before=self.store.q('SELECT * FROM crm_marketing_sends WHERE campaign_id=%s ORDER BY id',(identity,))
        prior=self.store.state('campaign-timing:'+str(identity))
        with patch.object(self.store,'_history',side_effect=RuntimeError('audit failed')):
            with self.assertRaisesRegex(RuntimeError,'audit failed'):
                self.change(ADMIN,identity,timing(day='2099-10-11'),op,confirmed=True)
        self.assertEqual(self.store.q('SELECT * FROM crm_marketing_sends WHERE campaign_id=%s ORDER BY id',(identity,)),before)
        self.assertEqual(self.store.state('campaign-timing:'+str(identity)),prior)
        self.assertFalse(self.store.state('campaign-timing-operation:'+str(identity)+':'+op))

    def test_attempted_pending_and_outage_block_fail_closed(self):
        saved=self.queue();identity=saved['id']
        for sql in ("UPDATE crm_marketing_sends SET attempts=1 WHERE campaign_id=%s", "UPDATE crm_marketing_sends SET attempts=0,status='BLOCKED',error_code='schedule_missed' WHERE campaign_id=%s"):
            self.store.q(sql,(identity,))
            with self.assertRaisesRegex(ValueError,'locked'):
                self.change(ADMIN,identity,timing(day='2099-10-11'),str(uuid.uuid4()),confirmed=True)

    def test_send_now_worker_uses_existing_frozen_batch_and_outage_override(self):
        import os
        from types import SimpleNamespace
        from unittest.mock import Mock
        from tests.test_crm_batch_dispatch import Transport
        from tests.test_crm_send_flow import LIVE
        from crm_campaign_schedule import schedule_gate
        from crm_campaign_dispatch import dispatch
        from crm_engine import Engine
        from crm_logic import now
        from crm_resend import Config
        saved=self.queue();identity=saved['id'];op=str(uuid.uuid4())
        before=self.store.q('SELECT id FROM crm_marketing_sends WHERE campaign_id=%s ORDER BY id',(identity,))
        with patch.dict(os.environ,LIVE):receipt=self.change(ADMIN,identity,{'mode':'now'},op,confirmed=True)
        # Configuration changes after acknowledgement cannot lose the receipt.
        with patch.dict(os.environ,{'CRM_MARKETING_ENABLED':'false'}):
            self.assertEqual(change_pending(self.store,ADMIN,identity,{'mode':'now'},op,confirmed=True),receipt)
        schedule_gate(self.store,False,now())
        self.assertEqual(self.store.q("SELECT count(*) n FROM crm_marketing_sends WHERE campaign_id=%s AND status='PENDING'",(identity,),True)['n'],3)
        transport=Transport();shop=Mock();shop.customer.side_effect=AssertionError('No Shopify rebuild')
        engine=Engine(self.store,shop,SimpleNamespace(batch_transport=transport),Config(LIVE))
        dispatch(engine)
        self.assertEqual(self.store.q("SELECT count(*) n FROM crm_marketing_sends WHERE campaign_id=%s AND status='ACCEPTED'",(identity,),True)['n'],3)
        self.assertEqual(self.store.q('SELECT id FROM crm_marketing_sends WHERE campaign_id=%s ORDER BY id',(identity,)),before)
        shop.customer.assert_not_called()

    def test_fixed_timezone_cannot_be_relabelled_recipient_local(self):
        saved=self.queue();identity=saved['id']
        local={'mode':'schedule','policy_version':2,'time_basis':'recipient_local','date':'2099-10-11','time':'17:00'}
        with self.assertRaisesRegex(ValueError,'evidence'):
            self.change(ADMIN,identity,local,str(uuid.uuid4()),confirmed=True)

    def test_irreversible_states_reject_every_amendment(self):
        for status in ('CLAIMED','SUBMITTING','ACCEPTED','UNCERTAIN','FAILED'):
            saved=self.queue();identity=saved['id']
            self.store.q('UPDATE crm_marketing_sends SET status=%s WHERE campaign_id=%s',(status,identity))
            with self.subTest(status=status),self.assertRaisesRegex(ValueError,'locked'):
                self.change(ADMIN,identity,timing(day='2099-10-11'),str(uuid.uuid4()),confirmed=True)
        for status in ('SENDING','SENT'):
            saved=self.queue();identity=saved['id']
            self.store.q('UPDATE crm_campaigns SET status=%s WHERE id=%s',(status,identity))
            with self.subTest(status=status),self.assertRaisesRegex(ValueError,'untouched'):
                self.change(ADMIN,identity,timing(day='2099-10-11'),str(uuid.uuid4()),confirmed=True)

    def test_legacy_date_edit_preserves_reviewed_timezone_assignments(self):
        legacy={'mode':'schedule','date':'2099-10-10','time':'17:00'}
        with patch('tests.test_crm_campaign_v8.timing',return_value=legacy):saved=self.queue()
        identity=saved['id']
        campaign=self.store.q('SELECT * FROM crm_campaigns WHERE id=%s',(identity,),True)
        before=self.store.template(campaign['template_id'],campaign['template_version'])
        proposed={'mode':'schedule','policy_version':2,'time_basis':'recipient_local','date':'2099-10-11','time':'17:00'}
        self.change(ADMIN,identity,proposed,str(uuid.uuid4()),confirmed=True)
        self.assertEqual(self.store.template(campaign['template_id'],campaign['template_version']),before)
        from crm_campaign_schedule import due
        from crm_logic import date
        for row in self.store.q('SELECT * FROM crm_marketing_sends WHERE campaign_id=%s',(identity,)):
            zone=before['schedule'][row['recipient_hash']]['timezone']
            self.assertEqual(date(row['due_at']),due(proposed,zone))

    def test_worker_transition_uses_current_override_after_reload(self):
        from datetime import datetime,timezone
        from crm_campaign_schedule import activate_due
        saved=self.queue();identity=saved['id']
        self.change(ADMIN,identity,timing(day='2099-10-12'),str(uuid.uuid4()),confirmed=True)
        # Original reviewed 10 October is due in this simulated worker tick,
        # but the current authorised 12 October schedule must stay scheduled.
        activate_due(self.store,clock=lambda:datetime(2099,10,11,tzinfo=timezone.utc))
        self.assertEqual(self.store.q('SELECT status FROM crm_campaigns WHERE id=%s',(identity,),True)['status'],'SCHEDULED')
        activate_due(self.store,clock=lambda:datetime(2099,10,13,tzinfo=timezone.utc))
        self.assertEqual(self.store.q('SELECT status FROM crm_campaigns WHERE id=%s',(identity,),True)['status'],'SENDING')
