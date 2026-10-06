"""Timing presentation uses persisted clocks without modifying checkout state."""
import copy
import unittest
from datetime import datetime, timedelta, timezone
from crm_checkout_timing_ui import time_to_send


class TimingLabels(unittest.TestCase):
    def setUp(self):
        self.at = datetime(2026, 10, 6, tzinfo=timezone.utc)
        self.row = dict(enrollment_id='fixture', flow_status='ACTIVE', current_step=0,
                        steps=[{}, {'delay_seconds':3600}], sends=[])

    def label(self, **changes):
        row = dict(self.row, **changes)
        before = copy.deepcopy(row)
        result = time_to_send(row, self.at)
        self.assertEqual(row, before)
        return result

    def test_remaining_and_due(self):
        for seconds, expected in [(720,'12m remaining'), (4680,'1h 18m remaining'),
                                  (187200,'2d 4h remaining'), (1,'1m remaining'), (0,'Due now'), (-60,'Due now')]:
            with self.subTest(seconds=seconds):
                self.assertEqual(self.label(next_due_at=self.at+timedelta(seconds=seconds)),expected)

    def test_not_enrolled_and_blocked(self):
        self.assertEqual(self.label(enrollment_id=None),'—')
        for result in ('Suppressed','Unsubscribed','Missing email','Invalid email','Not eligible'):
            self.assertEqual(self.label(enrollment_id=None,evaluation={'result':result}),result)
        self.assertEqual(self.label(flow_status='STOPPED',stop_reason='consent_unsubscribed'),'Unsubscribed')

    def test_hold_states(self):
        self.assertEqual(self.label(automation_status='PAUSED'),'Paused')
        self.assertEqual(self.label(archived_at=self.at),'Archived')
        self.assertEqual(self.label(order_id='shopify-order'),'Recovered')
        self.assertEqual(self.label(),'Awaiting schedule')

    def test_provider_states_are_not_sent(self):
        for status, expected in [('PENDING','Awaiting schedule'),('CLAIMED','Processing'),('SUBMITTING','Processing'),
                                 ('FAILED','Send failed'),('UNCERTAIN','Awaiting confirmation'),('BLOCKED','Suppressed')]:
            self.assertEqual(self.label(sends=[{'enrollment_id':'fixture','step':0,'status':status,'error':'local_suppression'}]),expected)

    def test_accepted_step_uses_existing_worker_clock(self):
        receipt = {'enrollment_id':'fixture','step':0,'status':'ACCEPTED','provider_id':'fixture','updated_at':self.at}
        self.assertEqual(self.label(sends=[receipt], next_due_at=self.at-timedelta(days=2)), 'Awaiting schedule')
        self.assertEqual(self.label(sends=[receipt], steps=[{}]),'Sent')
        self.assertEqual(self.label(sends=[receipt], flow_status='COMPLETED'),'Sent')

    def test_other_enrollment_receipt_cannot_replace_current_schedule(self):
        receipt = {'enrollment_id':'other','step':0,'status':'ACCEPTED','provider_id':'fixture','updated_at':self.at}
        self.assertEqual(self.label(sends=[receipt],next_due_at=self.at+timedelta(minutes=12)), '12m remaining')


if __name__ == '__main__':
    unittest.main()
