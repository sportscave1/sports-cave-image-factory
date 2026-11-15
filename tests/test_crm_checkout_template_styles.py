from copy import deepcopy
from html.parser import HTMLParser
import os
import unittest
from unittest.mock import Mock
from crm_abandoned_checkout import apply_template,block_html,hydrate,context,dynamic,publication_document
from crm_checkout_styles import CLASSES,MARKER,default_html
from crm_checkout_template import validate,load,save,use,KEY
from crm_campaign_content import render_campaign
from crm_checkout_preview import document as preview_document
from tests.test_crm_abandoned_checkout import checkout
from tests.test_crm_simple_editor import document
from tests.test_crm_send_flow import CFG


def styled(html=None):
    doc=document();apply_template(doc,html);doc['copy_reviewed']=True;return doc


def attrs(source,name):
    class Find(HTMLParser):
        def handle_starttag(self,tag,attributes):
            attributes=dict(attributes)
            if attributes.get('class')==name:self.results.append(attributes)
    parser=Find();parser.results=[];parser.feed(source);return parser.results


class TemplateStyleTests(unittest.TestCase):
    def test_data_markup_has_contract_but_no_visual_theme(self):
        html=block_html(context(checkout(items=2)))
        for name in CLASSES-{'sc-cart-label','sc-cart-dimensions'}:self.assertTrue(attrs(html,name),name)
        for forbidden in ('color:','background:','font-size:','font-weight:','opacity:','padding:'):
            self.assertNotIn(forbidden,html)

    def test_variant_title_button_and_image_width_follow_authored_css(self):
        html=default_html().replace('.sc-cart-variant { color:#b79335;', '.sc-cart-variant { color:#d1a938 !important;').replace('.sc-cart-title { color:#ffffff;', '.sc-cart-title { color:#ff0000 !important;').replace('background:#d1a938;', 'background:#c59b2d !important;').replace('max-width:480px;', 'max-width:320px;')
        doc=styled(html);original=deepcopy(doc)
        message=render_campaign(hydrate(doc,context(checkout())),CFG)
        self.assertIn('color:#d1a938',attrs(message['html'],'sc-cart-variant')[0]['style'])
        self.assertIn('color:#ff0000',attrs(message['html'],'sc-cart-title')[0]['style'])
        self.assertIn('background:#c59b2d',attrs(message['html'],'sc-cart-button')[0]['style'])
        self.assertIn('max-width:320px',attrs(message['html'],'sc-cart-image')[0]['style'])
        self.assertNotIn('<style>',str(hydrate(doc,context(checkout()))))
        self.assertEqual(doc,original)

    def test_preview_test_and_live_compilation_match_theme(self):
        doc=styled(default_html().replace('.sc-cart-variant { color:#b79335;', '.sc-cart-variant { color:#d1a938;'))
        data=context(checkout())
        preview=preview_document(doc,data)[0];test=preview_document(doc,data,test=True)[0];live=hydrate(doc,data)
        for rendered in (preview,test,live):
            self.assertIn('color:#d1a938',attrs(render_campaign(rendered,CFG)['html'],'sc-cart-variant')[0]['style'])
        self.assertNotIn(data['recovery_url'],str(test));self.assertIn(data['recovery_url'],str(live))

    def test_marker_pipeline_preserves_surrounding_copy_and_protection(self):
        doc=document();doc.update(content_mode='HTML',custom_html=default_html());doc.pop('middle_sections',None)
        self.assertTrue(dynamic(doc));rendered=hydrate(doc,context(checkout()))
        self.assertNotIn(MARKER,str(rendered));self.assertIn('YOUR COLLECTION AWAITS',str(rendered))
        self.assertIn('Just reply',str(rendered));self.assertFalse(dynamic(publication_document(doc,'abandoned')))
        with self.assertRaises(ValueError):publication_document(doc,'welcome')

    def test_validation_accepts_visual_changes_rejects_unsafe_or_broken_contract(self):
        validate(default_html())
        # Class presence and fixed checkout positions are no longer design rules.
        validate(default_html().replace('.sc-cart-variant {','.arbitrary {'))
        validate(default_html()+'<a class="sc-cart-button" href="https://example.test">More information</a>')
        for bad in (default_html().replace(MARKER,''),default_html()+MARKER,
                    default_html()+'{{ item.product_title }}',default_html()+'<script>alert(1)</script>',
                    default_html().replace('color:#ffffff;','color:expression(alert(1));'),
                    default_html()+'<a href="http://unsafe.test">Unsafe</a>'):
            with self.subTest(bad=bad[-60:]),self.assertRaises(ValueError):validate(bad)

    def test_publication_rejects_duplicate_native_blocks(self):
        doc=styled();doc['middle_sections'].append({'id':'duplicate','type':'abandoned_checkout_products','visible':True})
        with self.assertRaises(ValueError):publication_document(doc,'abandoned')

    def test_legacy_typed_block_without_css_gets_template_file_fallback(self):
        doc=styled();doc['middle_sections'][0]['html']='<p>Existing authored copy</p>';doc['custom_html']=doc['middle_sections'][0]['html']
        rendered=render_campaign(hydrate(doc,context(checkout())),CFG)
        self.assertIn('color:#b79335',attrs(rendered['html'],'sc-cart-variant')[0]['style'])
        self.assertIn('Existing authored copy',rendered['html'])

    def test_general_html_css_boundary_remains_closed(self):
        from crm_campaign_html import import_html
        html,_,_=import_html('<style>.bad{color:red}</style><p class="arbitrary">Content</p>')
        self.assertNotIn('<style',html);self.assertNotIn('class=',html)


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class MasterPersistenceTests(unittest.TestCase):
    def test_saved_master_use_independence_revision_and_reset(self):
        from crm_automation_store import AutomationStore
        from tests.crm_db_fixture import connect
        from tests.test_crm import ADMIN
        store=AutomationStore(connect);previous=store.state(KEY)
        try:
            old=load(store);draft=styled();before=deepcopy(draft)
            changed=old['html'].replace('.sc-cart-variant { color:#b79335;', '.sc-cart-variant { color:#d1a938;')
            row=save(store,ADMIN,changed,old['revision'])
            self.assertEqual(load(store)['html'],changed);self.assertEqual(draft,before)
            use(store,draft);self.assertIn('color:#d1a938',draft['middle_sections'][0]['html'])
            with self.assertRaises(ValueError):save(store,ADMIN,default_html(),old['revision'])
            reset=save(store,ADMIN,default_html(),row['revision']);self.assertEqual(reset['html'],default_html())
        finally:
            if previous:store.set_state(KEY,previous)
            else:store.q('DELETE FROM crm_runtime_state WHERE key=%s',(KEY,))
