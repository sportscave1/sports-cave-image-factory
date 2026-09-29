"""Unsaved leave confirmation: isolated SQL and no external APIs."""
from copy import deepcopy
import os
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from tests.test_crm_ui import SCRIPT
from tests.crm_db_fixture import connect
from crm_campaign_store import CampaignStore

SCRIPT=SCRIPT.replace("render_page(st.session_state.get('route','CRM Customers'),user,shop=", "render_page(st.session_state.get('route','CRM Customers'),user,navigate=lambda target:st.session_state.update(route=target),shop=")
SCRIPT=SCRIPT.replace("    if st.session_state.get('profile'):","    if st.session_state.get('route')=='Orders':st.title('Orders')\n    elif st.session_state.get('profile'):")

@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Isolated SQL required')
class LeaveTests(unittest.TestCase):
    def app(self):
        at=AppTest.from_string(SCRIPT);at.session_state['route']='CRM Campaigns';at.run(timeout=20)
        next(w for w in at.text_input if w.label=='Campaign name').set_value('Saved original').run(timeout=20)
        at.session_state['campaign_editor']['name']='Unsaved revision'
        at.session_state['crm_requested_route']='Orders'
        return at
    def test_open_is_ui_only_and_no_bottom_warning(self):
        at=self.app()
        with patch.object(CampaignStore,'setting',side_effect=AssertionError('No settings fetch')),patch.object(CampaignStore,'render_settings',side_effect=AssertionError('No templates fetch')):
            at.run(timeout=20)
        self.assertFalse(at.exception)
        self.assertTrue(any(e.proto.dialog.title=='Save changes?' for e in at.get('dialog')))
        self.assertEqual(sum(b.label=='Discard and leave' for b in at.button),1)
        self.assertFalse(any('Save your changes first' in w.value or 'retry before switching' in w.value for w in at.warning))
        self.assertEqual(at.session_state['route'],'CRM Campaigns')
    def test_save_and_leave_persists_then_navigates(self):
        at=self.app();identity=at.session_state['campaign_editor']['id'];at.run(timeout=20)
        next(b for b in at.button if b.label=='Save draft and leave').click().run(timeout=20)
        self.assertFalse(at.exception);self.assertEqual(at.session_state['route'],'Orders')
        self.assertEqual(CampaignStore(connect).draft(identity)['name'],'Unsaved revision')
        self.assertFalse(any(b.label=='Discard and leave' for b in at.button))
    def test_discard_preserves_saved_row_then_navigates(self):
        at=self.app();identity=at.session_state['campaign_editor']['id'];before=deepcopy(CampaignStore(connect).draft(identity));at.run(timeout=20)
        next(b for b in at.button if b.label=='Discard and leave').click().run(timeout=20)
        self.assertFalse(at.exception);self.assertEqual(at.session_state['route'],'Orders')
        self.assertEqual(CampaignStore(connect).draft(identity),before)
        self.assertEqual(at.session_state['campaign_editor']['name'],'Saved original')
        self.assertFalse(any(b.label=='Discard and leave' for b in at.button))
    def test_cancel_keeps_editor_and_clears_target(self):
        at=self.app();at.run(timeout=20)
        next(b for b in at.button if b.label=='Cancel').click().run(timeout=20)
        self.assertFalse(at.exception);self.assertEqual(at.session_state['route'],'CRM Campaigns')
        self.assertEqual(at.session_state['campaign_editor']['name'],'Unsaved revision')
        self.assertNotIn('crm_requested_route',at.session_state)
        self.assertFalse(any(b.label=='Discard and leave' for b in at.button))
    def test_failed_save_stays_in_dialog(self):
        from crm_store import StoreUnavailable
        at=self.app();at.run(timeout=20)
        with patch('crm_campaign_recovery.save_checkpoint',side_effect=StoreUnavailable('Fixture save unavailable')):
            next(b for b in at.button if b.label=='Save draft and leave').click().run(timeout=20)
        self.assertEqual(at.session_state['route'],'CRM Campaigns')
        self.assertEqual(at.session_state['campaign_editor']['name'],'Unsaved revision')
        self.assertTrue(any('Fixture save unavailable' in e.value for e in at.error))
