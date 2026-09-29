"""Footer URL integration checks: synthetic identities and mocked HTTP only."""
import os
import unittest
import uuid
from unittest.mock import Mock, patch

from crm_campaign_content import settings, render_campaign, fingerprint
from crm_campaign_footer import has_unsubscribe_link, render_footer
from crm_campaign_sections import section_defaults
from crm_resend import Config, MarketingDisabled, Resend
from tests.test_crm_simple_editor import document

ENV = {'CRM_MARKETING_ENABLED': 'false', 'CRM_PUBLIC_BASE_URL': 'https://hooks.example.test',
       'CRM_UNSUBSCRIBE_SECRET': 'synthetic-render-fixture-only-' * 2,
       'RESEND_MARKETING_API_KEY': 'fixture', 'RESEND_FROM_NAME': 'Sports Cave',
       'RESEND_FROM_EMAIL': 'sender@example.test', 'RESEND_REPLY_TO': 'reply@example.test'}
FOOTER = '<p>Sports Cave</p><a href="{{UNSUBSCRIBE_URL}}" style="color:#BFBFBF;text-decoration:underline;">Unsubscribe</a>'

class FooterURLTests(unittest.TestCase):
    def setUp(self):
        self.cfg = settings(ENV)
        self.doc = document()
        self.doc['html_sections'] = section_defaults(self.cfg)
        self.doc['html_sections']['footer'] = FOOTER

    def test_explicit_test_configuration_reaches_footer_without_process_environment(self):
        with patch.dict(os.environ, {}, clear=True):
            result = render_campaign(self.doc, self.cfg)
        self.assertIn('href="https://hooks.example.test/crm/unsubscribe/test"', result['html'])
        self.assertNotIn('?token=', result['html'])
        self.assertNotIn('{{UNSUBSCRIBE_URL}}', result['html'])
        self.assertTrue(has_unsubscribe_link(FOOTER))
        self.assertFalse(Config(ENV).enabled)

    def test_production_recipients_and_style_preservation(self):
        cfg = Config(ENV)
        urls = [cfg.unsubscribe_url(str(uuid.uuid4())) for _ in range(2)]
        self.assertNotEqual(*urls)
        test_markup = render_footer(FOOTER, self.cfg)[0]
        for url in urls:
            markup = render_footer(FOOTER, self.cfg, unsubscribe_url=url)[0]
            self.assertEqual(markup, test_markup.replace(cfg.test_unsubscribe_url(), url))
            result = render_campaign(self.doc, self.cfg, unsubscribe_url=url, production=True)
            self.assertIn('href="' + url + '"', result['html'])
            self.assertNotIn('{{UNSUBSCRIBE_URL}}', result['html'])
            self.assertIn('color:#BFBFBF;text-decoration:underline', result['html'])
        self.assertEqual(self.doc['html_sections']['footer'], FOOTER)

    def test_generation_and_render_fail_closed(self):
        for overrides in [{'CRM_PUBLIC_BASE_URL': ''}, {'CRM_PUBLIC_BASE_URL': 'http://unsafe.test'},
                          {'CRM_UNSUBSCRIBE_SECRET': ''}]:
            with self.assertRaises(MarketingDisabled):
                Config({**ENV, **overrides}).unsubscribe_url(str(uuid.uuid4()))
        for url in [None, '', '#', '{{UNSUBSCRIBE_URL}}']:
            with self.assertRaises(ValueError):
                render_campaign(self.doc, self.cfg, unsubscribe_url=url, production=True)

    def test_render_cache_identity_changes_with_public_base(self):
        other = settings({**ENV, 'CRM_PUBLIC_BASE_URL': 'https://other.example.test'})
        self.assertNotEqual(fingerprint(self.doc, self.cfg), fingerprint(self.doc, other))
        self.assertNotIn(ENV['CRM_UNSUBSCRIBE_SECRET'], str(self.cfg))

    def test_legacy_settings_still_resolve_runtime_test_route(self):
        legacy = dict(self.cfg)
        legacy.pop('test_unsubscribe_url')
        with patch.dict(os.environ, ENV, clear=True):
            self.assertIn(Config(ENV).test_unsubscribe_url(), render_footer(FOOTER, legacy)[0])

    def test_provider_headers_match_visible_link_without_delivery(self):
        cfg = Config(ENV)
        url = cfg.unsubscribe_url(str(uuid.uuid4()))
        message = render_campaign(self.doc, self.cfg, unsubscribe_url=url, production=True)
        message['unsubscribe_url'] = url
        session = Mock()
        session.post.return_value.status_code = 200
        session.post.return_value.json.return_value = {'id': 'mock-only'}
        # Exercise payload construction only; the real marketing gate remains OFF.
        with patch.object(cfg, 'require_send'), patch('crm_resend.pace'):
            Resend(cfg, session).send('synthetic@example.test', message, 'fixture-key')
        payload = session.post.call_args.kwargs['json']
        self.assertEqual(payload['headers']['List-Unsubscribe'], '<' + url + '>')
        self.assertEqual(payload['headers']['List-Unsubscribe-Post'], 'List-Unsubscribe=One-Click')
        self.assertIn('href="' + url + '"', payload['html'])
        self.assertFalse(cfg.enabled)
