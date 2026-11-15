"""Order-only presentation events; no eligibility or delivery bypass."""
import unittest
from unittest.mock import patch
from crm_post_purchase_audience import selection,add_candidate


class OrdersPanelTests(unittest.TestCase):
    def test_header_deselect_clears_off_page_selection_and_replay_is_ignored(self):
        state={'orders-selected':['a','b','c']}
        event={'sequence':'clear-1','selected':[],'clear_selection':True}
        self.assertEqual(selection(state,'orders',{'a'},event),[])
        state['orders-selected']=['c']
        self.assertEqual(selection(state,'orders',{'a'},event),['c'])

    def test_callback_rejects_late_page_event_before_changing_selection(self):
        from crm_lifecycle_ui import order_event
        state={'orders-selected':['a'],'orders-visible':['b'],'orders-table-context':'page2',
               'orders-table':{'context':'page1','sequence':'late','selected':[],'clear_selection':True}}
        with patch('crm_lifecycle_ui.st.session_state',state):order_event('orders')
        self.assertEqual(state['orders-selected'],['a'])
        state['orders-table']={'context':'page2','sequence':'new','selected':['b']}
        with patch('crm_lifecycle_ui.st.session_state',state):order_event('orders')
        self.assertEqual(state['orders-selected'],['a','b'])

    def test_local_hint_requires_known_consent_and_excludes_existing_journeys(self):
        r=dict(customer_id='customer',consent='SUBSCRIBED',financial_status='PAID')
        self.assertTrue(add_candidate(r))
        for change in ({'consent':'UNVERIFIED'},{'consent':'UNSUBSCRIBED'}, {'suppressed':True},
                       {'cancelled_at':'today'},{'financial_status':'REFUNDED'},
                       {'enrollment_id':'existing'},{'customer_id':None},{'enrollment_request_state':'CHECKING'}):
            with self.subTest(change=change):self.assertFalse(add_candidate({**r,**change}))


if __name__=='__main__':unittest.main()
