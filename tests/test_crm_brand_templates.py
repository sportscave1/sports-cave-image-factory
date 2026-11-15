"""Email-safe fidelity and reusable section templates; mocked mail / isolated SQL."""
from copy import deepcopy
from pathlib import Path
import os
import unittest
import uuid
from unittest.mock import Mock,patch
from crm_campaign_html import import_html,email_image_url
from crm_campaign_sections import FOOTER_TOKEN
from crm_campaign_content import render_campaign,settings
from crm_campaign_store import CampaignStore
from tests.test_crm_campaign_sections import sectioned
from tests.test_crm import ADMIN,WORKER
from tests.test_crm_resend_marketing import ENV

HEADER=Path('tests/fixtures/campaign_header_fidelity.html').read_text(encoding='utf-8')
LOGO='https://cdn.shopify.com/s/files/1/0722/2332/6515/files/sports-cave-logo-landscape-gold-transparent-optimised_1.webp?v=1779715351'

class FidelityTests(unittest.TestCase):
    def test_exact_fixture_preserves_header_presentation(self):
        output,_,checks=import_html(HEADER)
        for expected in ('bgcolor="#111111"','color="#FFFFFF"','color="#C9A33F"','bgcolor="#C9A33F"','height="3"','padding:26px 20px 22px 20px','padding-top:6px','font-size:0','line-height:3px','role="presentation"','cellspacing="0"','cellpadding="0"','border="0"','align="center"','face="Arial, Helvetica, sans-serif"'):
            self.assertIn(expected,output)
        self.assertTrue(all(checks.values()))

    def test_inline_email_styles_and_attributes(self):
        css='background:#111111;background-color:#111111;color:#ffffff;margin:0 auto;margin-top:4px;margin-right:2px;margin-bottom:1px;margin-left:3px;padding:4px;min-width:10px;max-width:600px;width:100%;height:auto;max-height:800px;border:0;border-top:3px solid #C9A33F;border-radius:2px;border-collapse:collapse;font-family:Arial;font-size:20px;font-weight:700;font-style:italic;line-height:1.5;letter-spacing:1px;text-transform:uppercase;text-align:center;text-decoration:none;display:block;vertical-align:top'
        output,_,_=import_html('<table><tr><td valign="top" style="'+css+'">Text</td></tr></table>')
        for declaration in css.split(';'):self.assertIn(declaration,output)

    def test_images_links_and_shopify_query_preserved_with_png_delivery(self):
        for url in ('https://cdn.shopify.com/s/files/logo.png?v=123','https://example.com/logo.jpg'):
            output,_,checks=import_html('<a href="https://example.com" target="_blank" title="Shop"><img src="'+url+'" alt="Logo" width="200" height="60" border="0" style="display:block"></a>')
            self.assertIn(url,output);self.assertTrue(all(v for k,v in checks.items() if k!='HTML content present'))
            self.assertIn('rel="noopener noreferrer"',output)
        self.assertEqual(email_image_url(LOGO),LOGO+'&format=png')
        output,_,checks=import_html('<img src="'+LOGO+'" alt="Sports Cave">')
        self.assertIn('v=1779715351&amp;format=png',output)
        self.assertTrue(checks['Images use durable public JPEG/PNG URLs'])
        for bad in ('javascript:alert(1)','data:image/svg+xml,bad','http://cdn.shopify.com/logo.png',LOGO+'&token=secret'):
            self.assertFalse(email_image_url(bad))

    def test_dangerous_content_stays_blocked(self):
        source='<script>evil()</script><object>evil()</object><embed src="x"><iframe src="https://evil.test">evil()</iframe><img src="javascript:bad" onerror="evil()" alt="x"><a href="javascript:bad" onclick="evil()">Link</a><p style="background:url(https://evil.test);color:expression(evil());width:calc(100%);margin:0;@import:bad">Good</p>'
        output,_,checks=import_html(source)
        for bad in ('script','object','embed','iframe','javascript:','onerror','onclick','expression','url(','@import','evil()'):self.assertNotIn(bad,output)
        self.assertIn('margin:0',output);self.assertFalse(checks['HTML contains only safe email markup'])
