"""Offline duplicate postal gate/UI checks; footer fixtures are synthetic."""
from copy import deepcopy
import unittest
from unittest.mock import Mock, patch
from streamlit.testing.v1 import AppTest

from crm_campaign_content import render_campaign
from crm_campaign_send import production_checks
from crm_campaign_footer import DEFAULT_FOOTER
from crm_workspace_store import DEFAULTS
from tests.test_crm_campaigns_v1 import ready_document
from tests.test_crm_send_flow import CFG, LIVE


class PostalSettingRemovalTests(unittest.TestCase):
    def setUp(self):
        self.doc=ready_document()
        self.doc.update(content_mode='HTML',custom_html='<p>Synthetic campaign content</p>')
        self.footer=DEFAULT_FOOTER.replace('{{BUSINESS_ADDRESS}}',CFG['postal'])
        self.doc['html_sections']={'header':'<p>Sports Cave</p>','footer':self.footer}
        self.cfg={**CFG,'postal':'','postal_verified':False}

    def test_production_ready_without_postal_setting_or_attestation(self):
        checks=production_checks(self.doc,self.cfg,LIVE)
        self.assertNotIn('Business postal address configured',checks)
        self.assertNotIn('Business postal address configured and verified',checks)
        self.assertTrue(all(checks.values()),checks)
        for enabled in ('true','false',''):
            env={**LIVE,'CRM_BUSINESS_ADDRESS_VERIFIED':enabled}
            self.assertEqual(production_checks(self.doc,self.cfg,env),checks)

    def test_authored_footer_address_and_production_unsubscribe_are_unchanged(self):
        before=deepcopy(self.doc)
        url='https://example.test/customer-unsubscribe'
        result=render_campaign(self.doc,self.cfg,production=True,unsubscribe_url=url)
        self.assertIn(CFG['postal'],result['html'])
        self.assertIn(CFG['postal'],result['text'])
        self.assertIn('href="'+url+'"',result['html'])
        self.assertEqual(self.doc,before)
        self.assertNotIn('Business postal address not configured',result['html'])

    def test_legacy_token_footer_keeps_existing_configured_address(self):
        self.doc['html_sections']['footer']=DEFAULT_FOOTER
        result=render_campaign(self.doc,CFG,production=True,
                               unsubscribe_url='https://example.test/customer-unsubscribe')
        self.assertIn(CFG['postal'],result['html'])

    def test_missing_footer_unsubscribe_still_blocks_production(self):
        for footer in ('','<p>Business identity and address</p>',
                       '<p>{{UNSUBSCRIBE_URL}}</p>'):
            self.doc['html_sections']['footer']=footer
            checks=production_checks(self.doc,self.cfg,LIVE)
            self.assertFalse(checks['Visible unsubscribe footer / functional production link'])
            with self.assertRaises(ValueError):
                render_campaign(self.doc,self.cfg,production=True,
                                unsubscribe_url='https://example.test/customer-unsubscribe')

    def test_sender_contact_marketing_and_audience_gates_remain(self):
        checks=production_checks(self.doc,{**self.cfg,'contact':''},LIVE)
        self.assertFalse(checks['Business contact identity configured'])
        for key,label in (('CRM_MARKETING_ENABLED','Marketing delivery enabled'),
                          ('CRM_MARKETING_SEND_ENABLED','Marketing delivery enabled'),
                          ('RESEND_FROM_EMAIL','Sender configured'),
                          ('RESEND_REPLY_TO','Reply-To configured'),
                          ('RESEND_MARKETING_API_KEY','Resend marketing API configured')):
            checks=production_checks(self.doc,self.cfg,{**LIVE,key:''})
            self.assertFalse(checks[label],key)
        self.doc['counts']['eligible']=0
        self.doc['counts']['members']=0
        checks=production_checks(self.doc,self.cfg,LIVE)
        self.assertFalse(checks['Fresh complete eligible audience'])
        self.assertTrue(checks['Only SUBSCRIBED; suppression and duplicate checks enabled'])

    def test_settings_hides_postal_controls_and_preserves_legacy_values_on_save(self):
        script='''
from copy import deepcopy
from unittest.mock import Mock,patch
import streamlit as st
from crm_settings_page import compliance_page
from crm_workspace_store import DEFAULTS
from tests.test_crm import ADMIN
store=Mock()
values=deepcopy(DEFAULTS)
values['compliance'].update(postal='Retained synthetic address',postal_verified=True)
store.setting.side_effect=lambda key:{'value':values[key],'version':1}
with patch('streamlit.rerun'):
 compliance_page(store,ADMIN)
st.session_state['saved_values']=store.save_setting.call_args.args[2] if store.save_setting.called else None
'''
        app=AppTest.from_string(script).run()
        self.assertFalse(app.exception)
        self.assertNotIn('Business postal address',[t.label for t in app.text_input])
        self.assertNotIn('Nathan confirmed this business postal address',[c.label for c in app.checkbox])
        next(b for b in app.button if b.label=='Save compliance details').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['saved_values']['postal'],'Retained synthetic address')
        self.assertTrue(app.session_state['saved_values']['postal_verified'])


if __name__=='__main__':unittest.main()
