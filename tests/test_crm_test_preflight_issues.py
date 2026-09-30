"""Outgoing-document validation: no provider/network or business writes."""
from copy import deepcopy
import unittest
from unittest.mock import Mock, patch
from crm_campaign_content import preflight, settings, render_campaign
from crm_catalogue import verify_catalogues
from crm_campaign_issues import document_issues
from tests.test_crm_modular_catalogue import catalogue_doc, event, service
from tests.test_crm_image_sections import HTML
from tests.test_crm_resend_marketing import ENV


class TestPreflightIssues(unittest.TestCase):
    def setUp(self):
        self.network = patch('requests.sessions.Session.request', side_effect=AssertionError('No external I/O'))
        self.network.start(); self.addCleanup(self.network.stop)
        self.doc = catalogue_doc(); self.cfg = settings(ENV)

    def checks(self): return preflight(self.doc, ENV, self.cfg)

    def image(self, source):
        event(self.doc, 'add', kind='image')
        section = self.doc['middle_sections'][-1]
        event(self.doc, 'html', id=section['id'], html=source)
        return section

    def test_hidden_catalogue_bad_facts_and_empty_image_are_ignored(self):
        cat=self.doc['middle_sections'][-1]
        cat['visible']=False
        for products in ([], cat['products']):
            cat['products']=products
            if products: products[0]['image']='data:image/png;base64,SECRET'; products[0]['status']='DRAFT'
            self.image('')
            checks=self.checks()
            self.assertTrue(checks['test']['Images use durable public JPEG/PNG URLs'])
            self.assertTrue(checks['test']['Image alt text complete'])
            self.assertNotIn('Catalogue product facts valid', checks['test'])
            self.assertFalse(checks['issues'])
        reader=Mock(); verify_catalogues(self.doc, reader); reader.resolve.assert_not_called()

    def test_visible_empty_catalogue_names_section(self):
        cat=self.doc['middle_sections'][-1]; cat['products']=[]
        checks=self.checks()
        self.assertFalse(checks['test']['Catalogue product facts valid'])
        self.assertIn(cat['id'], checks['issues'][0])
        self.assertIn('No products selected',checks['issues'][0])

    def test_incomplete_image_markup_is_not_an_empty_placeholder(self):
        self.image('<img src="https://example.test/art.png"')
        self.assertFalse(self.checks()['test']['HTML contains only safe email markup'])

    def test_bad_images_name_section_and_never_expose_tokens(self):
        image=self.image('<img src="https://cdn.shopify.com/private.svg?token=SECRET">')
        checks=self.checks()
        self.assertFalse(checks['test']['Images use durable public JPEG/PNG URLs'])
        self.assertFalse(checks['test']['Image alt text complete'])
        self.assertTrue(all(image['id'] in issue for issue in checks['issues']))
        self.assertNotIn('SECRET',str(checks['issues']))
        self.assertEqual(len(checks['issues']),2)
        event(self.doc,'visible',id=image['id'],visible=False)
        self.assertTrue(self.checks()['test']['Image alt text complete'])
        self.assertFalse(self.checks()['issues'])

    def test_rasters_and_shopify_webp_pass_complete_preview_and_test_pipeline(self):
        for suffix in ('jpg','png','webp'):
            with self.subTest(suffix=suffix):
                section=self.image(HTML.replace('artwork.jpg','artwork.'+suffix))
                self.assertTrue(self.checks()['test']['Images use durable public JPEG/PNG URLs'])
                preview=render_campaign(self.doc,self.cfg)['html']
                sent=render_campaign(self.doc,self.cfg,production=True,test_tracking=True,unsubscribe_url='https://example.test/unsubscribe')['html']
                needle='artwork.'+suffix+('?format=png' if suffix=='webp' else '')
                self.assertIn(needle,preview); self.assertIn(needle,sent)
                event(self.doc,'remove',id=section['id'],confirmed=True)

    def test_pending_edits_visibility_reorder_and_removed_content_deterministic(self):
        section=self.image('<img src="data:image/png;base64,AAA">')
        cat=self.doc['middle_sections'][1];cat['products']=[]
        event(self.doc,'visible',id=cat['id'],visible=False,edits={section['id']:HTML})
        event(self.doc,'order',ids=list(reversed([s['id'] for s in self.doc['middle_sections']])))
        before=deepcopy(self.doc)
        self.assertEqual(self.checks(),self.checks()); self.assertEqual(self.doc,before)
        self.assertFalse(self.checks()['issues'])
        event(self.doc,'remove',id=section['id'],confirmed=True)
        self.assertFalse(self.checks()['issues'])

    def test_locked_assets_have_attribution_not_body_misattribution(self):
        self.assertFalse(document_issues(self.doc,self.cfg))
        self.cfg['email_defaults']={'header':'<img src="https://example.test/logo.svg">','footer':self.doc['html_sections']['footer']}
        issues=self.checks()['issues']
        self.assertEqual(len(issues),2)
        self.assertTrue(all('Header [locked system section]' in i for i in issues))

    def test_fresh_catalogue_comparison_blocks_changed_facts_without_mutating_draft(self):
        before=deepcopy(self.doc); reader=service()
        verify_catalogues(self.doc,reader)
        self.assertTrue(reader.shop.query.call_args.args[-1])
        changed=service();old=changed.resolve
        def resolve(*a,**kw):
            products=old(*a,**kw);products[0]['price']='99.00';return products
        changed.resolve=resolve
        with self.assertRaises(ValueError) as failure:
            verify_catalogues(self.doc,changed)
        self.assertIn('Artwork 1',failure.exception.checks['section_issues'][0]['message'])
        self.assertEqual(self.doc,before)


if __name__=='__main__': unittest.main()
