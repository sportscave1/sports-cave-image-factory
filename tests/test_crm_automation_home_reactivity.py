"""Home critical path and scoped publication reads; no external I/O."""
import inspect
import unittest
from unittest.mock import Mock, patch
from crm_automation_home import accepted_publication, refresh_publications, home, status_region, table
from crm_automation_home_data import identities


class HomeReactivityTests(unittest.TestCase):
    def test_identity_query_is_bounded_and_independent(self):
        store=Mock();identities(store,search='needle',offset=12)
        sql,args=store.q.call_args.args
        self.assertIn('LIMIT %s OFFSET %s',sql)
        for term in ('JOIN','crm_delivery_events','crm_order_attribution','crm_automation_enrollments'):
            self.assertNotIn(term,sql)
        self.assertEqual(args[-1],12);store.q.assert_called_once()

    def test_acceptance_seeds_cold_home_without_claiming_live(self):
        state={}
        job={'id':'job','automation_id':'auto','revision':8,'publication_version':2,'state':'QUEUED',
             'snapshot':{'name':'Saved name','flow':{'trigger':'abandoned'}}}
        with patch('crm_automation_ui.home_state',return_value=state):accepted_publication(job)
        self.assertTrue(state['publication_reset_filters'])
        row=state['publish_handoff']
        self.assertEqual((row['id'],row['name'],row['trigger_type']),('auto','Saved name','abandoned'))
        self.assertEqual(row['publication']['state'],'PUBLISHING')
        self.assertEqual(row['publication']['revision'],8)

    def test_status_is_bounded_and_stops_database_polling_after_completion(self):
        for result in ('LIVE','FAILED'):
            state={};records=[{'id':'auto','publication':{'job_id':'job','state':'PUBLISHING'}}]
            store=Mock();store.q.return_value=[{'id':'auto','category':'Active','publication':{'job_id':'job','state':result}}]
            with patch('crm_automation_ui.home_state',return_value=state):
                refresh_publications(store,records,state)
                refresh_publications(store,records,state)
            store.q.assert_called_once()
            sql=store.q.call_args.args[0]
            self.assertNotIn('JOIN',sql);self.assertNotIn('crm_delivery_events',sql)
            self.assertEqual(records[0]['publication']['state'],result)

    def test_status_failure_retains_accepted_state(self):
        state={};records=[{'id':'auto','publication':{'job_id':'job','state':'PUBLISHING'}}]
        store=Mock();store.q.side_effect=TimeoutError('private connection')
        with patch('crm_automation_ui.home_state',return_value=state):refresh_publications(store,records,state)
        self.assertEqual(records[0]['publication']['state'],'PUBLISHING')

    def test_home_has_no_provider_labels_or_global_poll(self):
        source=inspect.getsource(home)
        self.assertNotIn('customer_batch',source)
        self.assertNotIn('arm_home_poll(',source)
        self.assertLess(source.index('table(shop'),source.index('kpis(store)'))
        source=inspect.getsource(status_region)
        for term in ('summary(', 'activity(', 'st.rerun(', 'rows('):self.assertNotIn(term,source)
        self.assertIn('data-auto-status',source)

    def test_list_handoff_is_independent_of_metrics_completion(self):
        source=inspect.getsource(table)
        self.assertLess(source.index("('identities'"),source.index("('table'"))
        self.assertIn("state.get('publish_handoff')",source)
        self.assertNotIn("if metrics is None",source)
