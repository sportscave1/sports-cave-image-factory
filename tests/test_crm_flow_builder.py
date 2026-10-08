"""Pure sequence editing and simulation; no external services."""
from copy import deepcopy
from datetime import datetime,timezone
import unittest
from crm_automation_definition import new_flow,email_step,validate
from crm_flow_builder import edit_sequence,simulate,display_name


class FlowBuilderTests(unittest.TestCase):
    def test_reorder_duplicate_disable_delete_keep_stable_identity(self):
        flow=new_flow();flow['emails'].append(email_step(delay_seconds=3600));original=deepcopy(flow)
        first,second=[s['step_id'] for s in flow['emails']]
        moved=edit_sequence(flow,second,'up')
        self.assertEqual([s['step_id'] for s in moved['emails']],[second,first])
        copied=edit_sequence(moved,second,'duplicate')
        self.assertNotEqual(copied['emails'][1]['step_id'],second)
        disabled=edit_sequence(copied,second,'toggle');self.assertFalse(disabled['emails'][0]['enabled'])
        removed=edit_sequence(disabled,second,'delete');self.assertEqual(len(removed['emails']),2)
        self.assertEqual(flow,original)

    def test_simulation_delays_disabled_steps_and_exits_no_mutation(self):
        flow=new_flow('abandoned');flow['emails']=[email_step(delay_seconds=s) for s in (7200,86400,172800)]
        flow['emails'][1]['enabled']=False;original=deepcopy(flow)
        rows=simulate(flow,datetime(2026,10,8,tzinfo=timezone.utc))
        self.assertTrue(rows[0]['Planned time (UTC)'].startswith('2026-10-08T02:00'))
        self.assertEqual(rows[1]['Outcome'],'Disabled')
        self.assertTrue(rows[2]['Planned time (UTC)'].startswith('2026-10-10T02:00'))
        self.assertEqual(simulate(flow,purchased=True)[0]['Planned time (UTC)'],'—')
        self.assertEqual(simulate(flow,subscribed=False)[0]['Planned time (UTC)'],'—')
        self.assertEqual(original,flow)

    def test_checkout_display_alias_is_not_a_record_migration(self):
        self.assertEqual(display_name('Abandoned Checkout — Reminder 1'),'Abandoned Checkout Recovery')
        self.assertEqual(display_name('My own recovery flow'),'My own recovery flow')

    def test_simulation_checks_entry_rules_and_exit_between_emails(self):
        flow=new_flow();flow['emails'].append(email_step(delay_seconds=3600))
        flow['rules']=[{'field':'customer_country','condition':'is','value':'NZ'}]
        self.assertEqual(simulate(flow)[0]['Outcome'],'Entry rules not matched')
        result=simulate(flow,customer={'defaultAddress':{'countryCodeV2':'NZ'}},exit_after=1)
        self.assertNotEqual(result[0]['Planned time (UTC)'],'—')
        self.assertEqual(result[1]['Planned time (UTC)'],'—')

    def test_validation_fails_closed_and_has_no_step_limit(self):
        flow=new_flow();flow['emails']=[email_step() for _ in range(100)]
        validate(flow)
        flow['emails'][0]['enabled']='false'
        with self.assertRaises(ValueError):validate(flow)
        flow=new_flow('abandoned');flow['exit_on_purchase']=False
        with self.assertRaises(ValueError):validate(flow)
        flow=new_flow('win_back');flow['inactive_days']=0
        with self.assertRaises(ValueError):validate(flow)


if __name__=='__main__':unittest.main()
