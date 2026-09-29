"""One editable footer; local fixture and mocked delivery only."""
from tests.crm_fixtures import TEST_UNSUBSCRIBE_URL
from copy import deepcopy
import os
import unittest
import uuid
from unittest.mock import Mock, patch

from crm_campaign_content import render_campaign, preflight, settings
from crm_campaign_footer import (DEFAULT_FOOTER, DISCLOSURE, prepare_footer, render_footer,
                                 has_unsubscribe_link, UNSUBSCRIBE_REQUIRED)
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

    def test_removal_stays_removed_and_only_live_footer_check_blocks(self):
        raw=DEFAULT_FOOTER.replace('<a href="{{UNSUBSCRIBE_URL}}" style="color:#dfc986">Unsubscribe</a>','')
        self.assertEqual(prepare_footer(raw),raw)
        self.assertEqual(section_source('footer',raw),raw)
        doc=sectioned();doc['html_sections']['footer']=raw
        checks=preflight(doc,ENV)
        self.assertTrue(checks['test_ready'])
        self.assertFalse(checks['live'][UNSUBSCRIBE_REQUIRED])
        self.assertFalse(checks['live_ready'])
        self.assertNotIn('Unsubscribe',render_campaign(doc,settings(ENV))['html'])
        with self.assertRaises(ValueError) as error:
            render_campaign(doc,settings(ENV),unsubscribe_url='https://example.test/unsubscribe?token=signed')
        self.assertEqual(str(error.exception),UNSUBSCRIBE_REQUIRED)
        self.assertEqual(doc['html_sections']['footer'],raw)

    def test_custom_footer_is_authoritative_even_with_all_business_settings(self):
        raw='<table bgcolor="#111111"><tr><td style="color:#ffffff;padding:12px"><p>Made for collectors.</p><a href="https://example.test/custom">My link</a></td></tr></table>'
        cfg={**settings(ENV),'business':'Injected company','postal':'Injected address',
             'contact':'injected@example.test','website':'https://example.test/injected',
             'privacy':'https://example.test/privacy','social_links':['https://example.test/social']}
        self.assertEqual(prepare_footer(raw),raw)
        self.assertEqual(section_source('footer',raw),raw)
        self.assertEqual(render_footer(raw,cfg)[0],raw)
        doc=sectioned();doc['html_sections']={'header':'<p>My header</p>','footer':raw}
        output=render_campaign(doc,cfg)
        self.assertEqual(output['html'].count(raw),1)
        for forbidden in ('Sports Cave','injected@example.test','Website',DISCLOSURE,'Injected company',
                          'Injected address','https://example.test/injected','Privacy','Unsubscribe',
                          'background:#f4f1e9','SYSTEM_FOOTER','Business postal address not configured'):
            self.assertNotIn(forbidden,str(output))

    def test_legacy_token_is_inline_once_and_render_compatible(self):
        doc=sectioned();doc['html_sections']['footer']='<div style="background-color:#171717;color:white"><p>My footer</p>{{SYSTEM_FOOTER}}{{SYSTEM_FOOTER}}</div>'
        converted=prepare_footer(doc['html_sections']['footer'])
        self.assertNotIn('SYSTEM_FOOTER',converted)
        self.assertEqual(converted.count('<div'),1)
        result=render_campaign(doc,settings(ENV))
        doc['html_sections']['footer']=converted
        self.assertEqual(render_campaign(doc,settings(ENV)),result)
        self.assertEqual(result['html'].count(DISCLOSURE),0)
        self.assertEqual(result['html'].count('My footer'),1)
        self.assertEqual(prepare_footer('{{SYSTEM_FOOTER}}'),'')
        self.assertEqual(prepare_footer(DEFAULT_FOOTER+'{{SYSTEM_FOOTER}}'),DEFAULT_FOOTER)

    def test_missing_hidden_unlinked_or_comment_tokens_block_only_live(self):
        for footer in ('<div style="display:none">'+DEFAULT_FOOTER+'</div>',
                       '<div style="font-size:0.0px">'+DEFAULT_FOOTER+'</div>',
                       '<!--<a href="{{UNSUBSCRIBE_URL}}">Unsubscribe</a>-->',
                       '{{UNSUBSCRIBE_URL}}', '<p>Custom footer</p>', '',
                       '<a href="https://example.test/not-a-recipient-link">Unsubscribe</a>',
                       DEFAULT_FOOTER.replace('>Unsubscribe</a>','></a>')):
            with self.subTest(footer=footer):
                doc=sectioned();doc['html_sections']['footer']=footer
                self.assertTrue(preflight(doc,ENV)['test_ready'])
                self.assertFalse(preflight(doc,ENV)['live'][UNSUBSCRIBE_REQUIRED])
                self.assertFalse(has_unsubscribe_link(footer))
                self.assertEqual(section_source('footer',footer),footer)
                self.assertEqual(doc['html_sections']['footer'],footer)

    def test_authored_unsubscribe_label_style_and_stored_token_unchanged(self):
        raw='<p><a href="{{UNSUBSCRIBE_URL}}" style="color:#c9a33f" title="Preferences">Stop these updates</a></p>'
        self.assertTrue(has_unsubscribe_link(raw))
        self.assertEqual(section_source('footer',raw),raw)
        preview=render_footer(raw,settings(ENV))[0]
        self.assertEqual(preview,'<p><span style="color:#c9a33f" title="Preferences">Stop these updates</span></p>')
        url='https://example.test/unsubscribe?recipient=abc&signature=xyz'
        resolved=render_footer(raw,settings(ENV),unsubscribe_url=url)[0]
        self.assertEqual(resolved,raw.replace('{{UNSUBSCRIBE_URL}}',url.replace('&','&amp;')))
        self.assertEqual(resolved.count('Stop these updates'),1)
        self.assertNotIn('utm_',resolved)
        doc=sectioned();doc['html_sections']['footer']=raw
        self.assertTrue(preflight(doc,ENV)['live'][UNSUBSCRIBE_REQUIRED])
        self.assertFalse(preflight(doc,ENV)['live_ready'])
        self.assertIn(resolved,render_campaign(doc,settings(ENV),unsubscribe_url=url)['html'])

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
        from tests.crm_fixtures import TestRecipientShop
        customer_patch=patch('crm_test_recipient.Shopify',return_value=TestRecipientShop())
        customer_patch.start();self.addCleanup(customer_patch.stop)
        from crm_campaign_store import CampaignStore
        from tests.crm_db_fixture import connect
        self.store=CampaignStore(connect)
    def test_internal_test_uses_global_footer_production_render_and_never_resends(self):
        doc=sectioned();doc['html_sections']['footer']='<p>Only my footer</p>'
        row=self.store.save(ADMIN,'Author footer test',doc,env=ENV)
        sending=self.store.setting('sending')
        self.store.save_setting(ADMIN,'sending',{'internal_recipients':['manual@example.test'],'smart_hours':16},sending['version'])
        wire=Mock();wire.post.return_value=Mock(status_code=200,json=lambda:{'id':str(uuid.uuid4())})
        operation=str(uuid.uuid4())
        preview=render_campaign(row['document'],self.store.render_settings(ENV),production=True,unsubscribe_url=TEST_UNSUBSCRIBE_URL)
        with patch('requests.sessions.Session.request',side_effect=AssertionError('No external network')),patch('crm_resend_marketing._audit',return_value=True):
            for _ in range(2):
                self.store.test_campaign(ADMIN,row['id'],row['version'],recipient='manual@example.test',confirmed=True,operation_id=operation,env=ENV,session=wire)
        wire.post.assert_called_once()
        payload=wire.post.call_args.kwargs['json']
        self.assertEqual(payload['html'],preview['html'])
        self.assertEqual(payload['text'],preview['text'])
        self.assertEqual(payload['to'],['manual@example.test'])
        self.assertFalse(preflight(doc,ENV)['marketing_enabled'])
        self.assertFalse(preflight(doc,ENV)['live'][UNSUBSCRIBE_REQUIRED])


if __name__=='__main__':unittest.main()
