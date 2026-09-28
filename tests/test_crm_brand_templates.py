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

@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Requires disposable SQL fixture')
class BrandTemplateTests(unittest.TestCase):
    def setUp(self):
        from tests.crm_db_fixture import connect
        self.store=CampaignStore(connect);self.cfg=self.store.render_settings(ENV)
        self.store.set_section_default(ADMIN,'header','builtin_header')
        self.store.set_section_default(ADMIN,'footer','builtin_footer')

    def save(self,kind,source=None,**kw):
        return self.store.save_section_template(ADMIN,kind,'Fixture '+uuid.uuid4().hex[:8],source if source is not None else HEADER if kind=='header' else '<p>Footer note</p>',**kw)

    def tearDown(self):
        for kind in ('header','footer'):self.store.set_section_default(ADMIN,kind,'builtin_'+kind)

    def test_defaults_blank_body_and_no_write_on_page_load(self):
        from streamlit.testing.v1 import AppTest
        from tests.test_crm_ui import SCRIPT
        header=self.save('header',make_default=True);footer=self.save('footer',make_default=True)
        before=self.store.q('SELECT count(*) AS n FROM crm_campaign_drafts',one=True)['n']
        at=AppTest.from_string(SCRIPT);at.session_state['route']='CRM Campaigns';at.run(timeout=20)
        self.assertFalse(at.exception)
        doc=at.session_state['campaign_editor']['document']
        self.assertEqual(doc['custom_html'],'')

        self.assertEqual(doc['html_sections'],{'header':header['content']['html'],'footer':footer['content']['html']})
        self.assertEqual(before,self.store.q('SELECT count(*) AS n FROM crm_campaign_drafts',one=True)['n'])
        # Both selectors apply independently in the same editor.
        other=self.save('header','<p>Other header</p>');other_footer=self.save('footer','<p>Other footer</p>')
        at.run()
        next(s for s in at.selectbox if s.label=='Header template').set_value(str(other['id'])).run()
        next(s for s in at.selectbox if s.label=='Footer template').set_value(str(other_footer['id'])).run()
        doc=at.session_state['campaign_editor']['document']
        self.assertEqual(doc['html_sections']['header'],other['content']['html'])
        self.assertEqual(doc['html_sections']['footer'],other_footer['content']['html'])
        self.assertEqual(doc['custom_html'],'')

    def test_changed_default_does_not_relabel_or_overwrite_selected_source(self):
        from streamlit.testing.v1 import AppTest
        from tests.test_crm_ui import SCRIPT
        at=AppTest.from_string(SCRIPT);at.session_state['route']='CRM Campaigns';at.run(timeout=20)
        before=deepcopy(at.session_state['campaign_editor']['document'])
        labels=next(s for s in at.selectbox if s.label=='Header template').options
        self.save('header','<p>New global default</p>',make_default=True)
        at.run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state['campaign_editor']['document'],before)
        self.assertEqual(next(s for s in at.selectbox if s.label=='Header template').options[:2],labels[:2])

    def test_snapshots_versions_default_changes_and_exact_footer(self):
        header=self.save('header',make_default=True);footer=self.save('footer',make_default=True)
        doc=sectioned();doc['html_sections']=self.store.default_sections(self.cfg)
        campaign=self.store.save(ADMIN,'Snapshot test',doc,env=ENV)
        for row in (header,footer):
            kind=row['content']['section']
            edited=self.store.save_section_template(ADMIN,kind,row['name'],'<p>Changed '+kind+'</p>',identity=row['id'],version=row['version'],confirmed=True)
            self.assertEqual(edited['version'],2)
            self.assertEqual(edited['content']['created_by'],str(ADMIN['id']))
            self.assertNotEqual(self.store.default_sections(self.cfg)[kind],doc['html_sections'][kind])
            with self.assertRaises(ValueError):self.store.delete_section_template(ADMIN,edited['id'],2,confirmed=True)
        self.assertEqual(self.store.draft(campaign['id'])['document'],campaign['document'])
        self.assertNotIn(FOOTER_TOKEN,footer['content']['html'])
        self.assertEqual(footer['content']['html'],'<p>Footer note</p>')
        output=render_campaign(doc,self.cfg)['html']
        self.assertEqual(output.count('Unsubscribe'),0)
        self.assertEqual(output.count('You’re receiving this marketing email'),0)

    def test_permissions_overwrite_delete_and_type_boundaries(self):
        row=self.save('header')
        with self.assertRaises(ValueError):self.store.save_section_template(ADMIN,'header',row['name'].upper(),HEADER)
        with self.assertRaises(ValueError):self.store.save_section_template(ADMIN,'header',row['name'],HEADER,identity=row['id'],version=1)
        with self.assertRaises(ValueError):self.store.save_section_template(ADMIN,'footer',row['name'],HEADER,identity=row['id'],version=1,confirmed=True)
        with self.assertRaises(PermissionError):self.store.set_section_default(WORKER,'header',str(row['id']))
        with self.assertRaises(ValueError):self.store.delete_section_template(ADMIN,row['id'],1)
        self.store.delete_section_template(ADMIN,row['id'],1,confirmed=True)
        self.assertNotIn(str(row['id']),[str(r['id']) for r in self.store.section_templates('header',self.cfg)])
        with self.assertRaises(ValueError):self.store.set_section_default(ADMIN,'header',str(row['id']))
        with self.assertRaises(ValueError):self.store.delete_section_template(ADMIN,'builtin_header',0,confirmed=True)
        self.assertNotIn(row['id'],[r['id'] for r in self.store.templates(True)])
        self.assertNotIn(row['id'],[r['id'] for r in self.store.list('templates')])

    def test_fidelity_preview_matches_mocked_test_payload(self):
        doc=sectioned();doc['html_sections']['header']=HEADER+'<img src="'+LOGO+'" alt="Sports Cave logo">'
        row=self.store.save(ADMIN,'Fidelity test',doc,env=ENV)
        setting=self.store.setting('sending');self.store.save_setting(ADMIN,'sending',{'internal_recipients':['manual@example.test'],'smart_hours':16},setting['version'])
        wire=Mock();wire.post.return_value=Mock(status_code=200,json=lambda:{'id':str(uuid.uuid4())})
        with patch('requests.sessions.Session.request',side_effect=AssertionError('No network')),patch('crm_resend_marketing._audit',return_value=True):
            self.store.test_campaign(ADMIN,row['id'],row['version'],recipient='manual@example.test',confirmed=True,operation_id=str(uuid.uuid4()),env=ENV,session=wire)
        self.assertEqual(wire.post.call_args.kwargs['json']['html'],render_campaign(row['document'],self.store.render_settings(ENV))['html'])

    def test_ui_save_section_templates_and_edit_shared_default(self):
        from streamlit.testing.v1 import AppTest
        from tests.test_crm_ui import SCRIPT
        at=AppTest.from_string(SCRIPT.replace("'role':'worker'","'role':'admin'"))
        at.session_state['route']='CRM Campaigns';at.run(timeout=20)
        for kind in ('header','footer'):
            label='UI '+kind+' '+uuid.uuid4().hex[:8]
            next(t for t in at.text_area if t.label==kind.title()+' HTML').set_value(HEADER if kind=='header' else '<p>Shared footer</p>')
            next(t for t in at.text_input if (t.key or '').endswith(kind+'_template_name')).set_value(label)
            next(c for c in at.checkbox if (c.key or '').endswith(kind+'_make_default')).check()
            next(b for b in at.button if b.label=='Save '+kind+' template').click().run(timeout=20)
            self.assertFalse(at.exception)
            self.assertEqual(next(r['name'] for r in self.store.section_templates(kind,self.cfg) if r['is_default']),label)
            self.assertEqual(at.session_state['campaign_editor']['document']['custom_html'],'')
        next(b for b in at.button if b.key=='campaign_settings_toggle').click().run(timeout=20)
        next(s for s in at.selectbox if s.label=='Campaign Settings').select('Email brand templates').run(timeout=20)
        next(b for b in at.button if b.key=='header_edit').click().run(timeout=20)
        self.assertFalse(at.exception)
        next(t for t in at.text_area if t.label=='Header template HTML').set_value('<p>Reviewed shared header</p>')
        self.assertTrue(next(b for b in at.button if b.label=='Save shared template').disabled)
        next(c for c in at.checkbox if c.label=='Confirm overwriting this shared template').check().run(timeout=20)
        next(b for b in at.button if b.label=='Save shared template').click().run(timeout=20)
        self.assertFalse(at.exception)
        self.assertEqual(self.store.default_sections(self.cfg)['header'],'<p>Reviewed shared header</p>')
