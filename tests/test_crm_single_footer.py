"""One editable footer; local fixture and mocked delivery only."""
from copy import deepcopy
import os
import unittest
import uuid
from unittest.mock import Mock

from crm_campaign_content import render_campaign, preflight, settings
from crm_campaign_footer import DEFAULT_FOOTER, DISCLOSURE, prepare_footer, render_footer
from crm_brand_templates import section_source
from tests.test_crm_campaign_sections import sectioned
from tests.test_crm_resend_marketing import ENV
from tests.test_crm import ADMIN


class FooterTests(unittest.TestCase):
    def test_single_footer_and_no_diagnostics_inside_design(self):
        doc=sectioned();before=deepcopy(doc)
        cfg=settings(ENV);cfg['postal']=''
        result=render_campaign(doc,cfg)
        self.assertEqual(result['html'].count(DISCLOSURE),1)
        self.assertEqual(result['text'].count(DISCLOSURE),1)
        self.assertEqual(result['html'].count('Unsubscribe'),1)
        self.assertNotIn('background:#f4f1e9',result['html'])
        self.assertNotIn('Business postal address not configured',str(result))
        self.assertNotIn('{{',result['html'])
        self.assertEqual(doc,before)
        self.assertFalse(preflight(doc,ENV)['live_ready'])
        self.assertFalse(preflight(doc,ENV)['marketing_enabled'])
        self.assertFalse(preflight(doc,ENV)['live']['Business postal address configured and verified'])

    def test_removal_restores_inline_not_second_styled_footer(self):
        raw=DEFAULT_FOOTER.replace('<a href="{{UNSUBSCRIBE_URL}}" style="color:#dfc986">Unsubscribe</a>','')
        fixed=prepare_footer(raw)
        self.assertIn('{{UNSUBSCRIBE_URL}}',fixed)
        self.assertEqual(fixed.count('<table'),1)
        self.assertEqual(prepare_footer(fixed),fixed)
        self.assertLess(fixed.index('Unsubscribe'),fixed.index('</td>'))
        self.assertEqual(section_source('footer',raw),fixed)

    def test_legacy_token_is_inline_once_and_render_compatible(self):
        doc=sectioned();doc['html_sections']['footer']='<div style="background-color:#171717;color:white"><p>My footer</p>{{SYSTEM_FOOTER}}{{SYSTEM_FOOTER}}</div>'
        converted=prepare_footer(doc['html_sections']['footer'])
        self.assertNotIn('SYSTEM_FOOTER',converted)
        self.assertEqual(converted.count('<div'),1)
        result=render_campaign(doc,settings(ENV))
        doc['html_sections']['footer']=converted
        self.assertEqual(render_campaign(doc,settings(ENV)),result)
        self.assertEqual(result['html'].count(DISCLOSURE),1)
        self.assertEqual(prepare_footer(DEFAULT_FOOTER+'{{SYSTEM_FOOTER}}'),DEFAULT_FOOTER)

    def test_hidden_or_comment_only_compliance_cannot_pass_test_preflight(self):
        for footer in ('<div style="display:none">'+DEFAULT_FOOTER+'</div>',
                       '<div style="font-size:0.0px">'+DEFAULT_FOOTER+'</div>',
                       DEFAULT_FOOTER.replace('{{MARKETING_DISCLOSURE}}','<!--{{MARKETING_DISCLOSURE}}-->'),
                       DEFAULT_FOOTER.replace('>Unsubscribe</a>','></a>')):
            with self.subTest(footer=footer):
                doc=sectioned();doc['html_sections']['footer']=footer
                self.assertFalse(preflight(doc,ENV)['test_ready'])
                with self.assertRaises(ValueError):section_source('footer',footer)

    def test_configured_identity_address_contact_privacy_and_real_unsubscribe(self):
        cfg={**settings(ENV),'postal':'Configured business premises','privacy':'https://example.test/privacy'}
        output=render_footer(DEFAULT_FOOTER,cfg,unsubscribe_url='https://example.test/unsubscribe?id=abc&key=123')[0]
        self.assertIn('Configured business premises',output)
        self.assertIn('href="mailto:'+cfg['contact']+'"',output)
        self.assertIn('https://example.test/unsubscribe?id=abc&amp;key=123',output)
        self.assertNotIn('utm_',output)
        self.assertIn('Privacy',output)
        with self.assertRaises(ValueError):render_footer(DEFAULT_FOOTER,cfg,unsubscribe_url='javascript:alert(1)')

    def test_body_header_unchanged_and_no_unsafe_markup(self):
        from crm_campaign_html import import_html
        attempted=import_html('<a href="javascript:bad">Bad</a>',template_links={'javascript:bad'})
        self.assertNotIn('javascript:',attempted[0])
        self.assertFalse(attempted[2]['CTA label and HTTPS URL valid'])
        doc=sectioned();header=doc['html_sections']['header'];body=doc['custom_html']
        doc['html_sections']['footer']=DEFAULT_FOOTER+'<script>evil()</script><img onerror="bad()" src="javascript:bad">'
        output=render_campaign(doc,settings(ENV))
        self.assertNotIn('<script',output['html']);self.assertNotIn('onerror',output['html'])
        self.assertFalse(preflight(doc,ENV)['test_ready'])
        self.assertEqual(doc['html_sections']['header'],header);self.assertEqual(doc['custom_html'],body)


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Requires disposable SQL fixture')
class FooterStorageTests(unittest.TestCase):
    def setUp(self):
        from crm_campaign_store import CampaignStore
        from tests.crm_db_fixture import connect
        self.store=CampaignStore(connect)
        self.store.set_section_default(ADMIN,'footer','builtin_footer')

    def test_default_selected_edit_preview_and_draft_save(self):
        from streamlit.testing.v1 import AppTest
        from tests.test_crm_ui import SCRIPT
        at=AppTest.from_string(SCRIPT.replace("'role':'worker'","'role':'admin'"))
        at.session_state['route']='CRM Campaigns';at.run(timeout=20)
        picker=next(s for s in at.selectbox if s.label=='Footer template')
        self.assertEqual(picker.value,'builtin_footer')
        self.assertIn('Sports Cave Default Footer',str(picker.options))
        source=next(t for t in at.text_area if t.label=='Footer HTML')
        self.assertFalse(source.proto.disabled)
        source.set_value(source.value.replace('<strong>','<strong>Collector footer ')).run()
        self.assertTrue(any('Collector footer' in e.proto.srcdoc for e in at.get('iframe')))
        source=next(t for t in at.text_area if t.label=='Footer HTML')
        source.set_value(source.value.replace('{{UNSUBSCRIBE_URL}}','https://example.test/wrong')).run()
        self.assertTrue(any('Required compliance content restored' in w.value for w in at.warning))
        self.assertIn('{{UNSUBSCRIBE_URL}}',next(t for t in at.text_area if t.label=='Footer HTML').value)
        next(b for b in at.button if b.label=='Save draft').click().run(timeout=20)
        self.assertFalse(at.exception)
        row=self.store.draft(at.session_state['campaign_editor']['id'])
        self.assertIn('Collector footer',row['document']['html_sections']['footer'])
        self.assertEqual(row['document']['custom_html'],'')

    def test_legacy_save_snapshot_and_reusable_footer(self):
        doc=sectioned();doc['html_sections']['footer']='<p>Old custom</p>{{SYSTEM_FOOTER}}'
        row=self.store.save(ADMIN,'Legacy footer',doc,env=ENV)
        self.assertNotIn('SYSTEM_FOOTER',row['document']['html_sections']['footer'])
        self.assertEqual(render_campaign(doc,settings(ENV)),render_campaign(row['document'],settings(ENV)))
        template=self.store.save_section_template(ADMIN,'footer','Footer '+uuid.uuid4().hex,row['document']['html_sections']['footer'],make_default=True)
        self.assertEqual(self.store.default_sections(settings(ENV))['footer'],row['document']['html_sections']['footer'])
        self.store.save_section_template(ADMIN,'footer',template['name'],DEFAULT_FOOTER,identity=template['id'],version=template['version'],confirmed=True)
        self.assertEqual(self.store.draft(row['id'])['document'],row['document'])
        self.store.set_section_default(ADMIN,'footer','builtin_footer')

    def test_hidden_footer_never_reaches_test_transport(self):
        doc=sectioned();doc['html_sections']['footer']='<div style="display:none">'+DEFAULT_FOOTER+'</div>'
        row=self.store.save(ADMIN,'Hidden footer blocked',doc,env=ENV)
        sending=self.store.setting('sending')
        self.store.save_setting(ADMIN,'sending',{'internal_recipients':['manual@example.test'],'smart_hours':16},sending['version'])
        wire=Mock()
        with self.assertRaisesRegex(ValueError,'preflight'):
            self.store.test_campaign(ADMIN,row['id'],row['version'],recipient='manual@example.test',confirmed=True,operation_id=str(uuid.uuid4()),env=ENV,session=wire)
        wire.post.assert_not_called()


if __name__=='__main__':unittest.main()
