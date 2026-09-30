"""Presentation changes retain native controls and timing values."""
import os
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest


class TimingPresentationTests(unittest.TestCase):
    def test_segmented_radio_preserves_schedule_roundtrip(self):
        at = AppTest.from_string('''
import streamlit as st
from crm_campaign_controls import timing_control
doc = st.session_state.setdefault('document', {'send_timing': {'mode': 'now'}})
timing_control(doc, 'fixture')
''').run()
        self.assertEqual(at.radio[0].options, ['Send now', 'Schedule'])
        at.radio[0].set_value('Schedule').run()
        self.assertEqual(at.session_state['document']['send_timing']['mode'], 'schedule')
        self.assertEqual(len(at.date_input), 1)
        self.assertEqual(len(at.time_input), 1)
        at.radio[0].set_value('Send now').run()
        self.assertEqual(at.session_state['document']['send_timing'], {'mode': 'now'})
        self.assertFalse(at.exception)

    @unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES') == '1', 'Disposable SQL required')
    def test_actions_and_enabled_status_presentation(self):
        from tests.test_crm_ui import SCRIPT
        # Mock only the displayed status; no delivery configuration is changed.
        with patch('crm_campaign_page.get_resend_marketing_config_status', return_value={'marketing_enabled': True}):
            at = AppTest.from_string(SCRIPT)
            at.session_state['route'] = 'CRM Campaigns'
            at.run(timeout=20)
        self.assertFalse(at.exception)
        self.assertEqual([t.label for t in at.tabs], ['Settings', 'Editor', 'Templates', 'Drafts', 'Sent'])
        self.assertFalse(any('Marketing delivery ON' in c.value for c in at.caption))
        self.assertEqual(next(b for b in at.button if b.label == 'Save draft').proto.type, 'secondary')
        self.assertEqual(next(b for b in at.button if b.label == 'Send now').proto.type, 'primary')
