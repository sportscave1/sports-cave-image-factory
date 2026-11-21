"""Complete light recommendation rendering; fixtures only, no remote calls."""
from copy import deepcopy
from unittest import TestCase
from urllib.parse import urlsplit,parse_qs
from crm_catalogue import catalogue_html
from crm_campaign_content import render_campaign
from tests.test_crm_modular_catalogue import catalogue_doc
from tests.test_crm_catalogue_presentation import Markup


class LightCatalogueTests(TestCase):
    def test_light_cards_keep_facts_and_all_product_destinations(self):
        doc=catalogue_doc();section=doc['middle_sections'][-1]
        section['products']=section['products'][:1]
        section['products'][0]['title']='A memory #111111 Wall Art'
        before=deepcopy(section)
        html=catalogue_html(section,theme='light')
        parsed=Markup(html)
        self.assertIn('A memory #111111',html)
        self.assertIn('bgcolor="#FFFFFF"',html)
        self.assertNotIn('bgcolor="#151515"',html)
        self.assertIn('color:#222222',html)
        button=next(a for a in parsed.anchors if 'font-weight:700' in a.get('style',''))
        self.assertIn('color:#FFFFFF',button['style'])
        self.assertIn('font-size:16px',button['style'])
        self.assertIn('line-height:24px',button['style'])
        self.assertIn('padding:12px',button['style'])
        self.assertEqual(len(set(a['href'] for a in parsed.anchors)),1)
        self.assertEqual(section,before)

    def test_light_document_keeps_tracked_links_plain_text_and_escaping(self):
        doc=catalogue_doc();doc['tags'].append('email-light-v1')
        doc['middle_sections'][-1]['products'][0]['title']='<script>Fan & sport</script>'
        before=deepcopy(doc)
        message=render_campaign(doc)
        self.assertNotIn('<script>',message['html'])
        self.assertIn('bgcolor="#FFFFFF"',message['html'])
        links=[a['href'] for a in Markup(message['html']).anchors if '/products/' in a.get('href','')]
        self.assertTrue(links)
        self.assertTrue(all(parse_qs(urlsplit(link).query)['sc_test']==['1'] for link in links))
        self.assertIn('Fan & sport',message['text'])
        self.assertEqual(doc,before)

    def test_untagged_documents_retain_the_existing_dark_cards(self):
        doc=catalogue_doc()
        self.assertIn('bgcolor="#151515"',render_campaign(doc)['html'])
        self.assertEqual(catalogue_html(doc['middle_sections'][-1]),
                         catalogue_html(doc['middle_sections'][-1],theme='dark'))
