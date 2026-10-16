"""Offline collection display contracts; no delivery, Shopify writes or reads."""
from copy import deepcopy
from html import escape
import unittest
from unittest.mock import patch

from crm_catalogue import catalogue_html, collection_display_title
from crm_campaign_content import render_campaign
from crm_middle_sections import render_middle
from tests.test_crm_modular_catalogue import catalogue_doc
from tests.test_crm_send_flow import CFG


CASES = (
    ('Peter Brock Tribute Wall Art', 'Peter Brock Tribute'),
    ('Allan Moffat Wall Art', 'Allan Moffat'),
    ('Dick Johnson Crash – Bathurst 1980 Collector’s Wall Art',
     'Dick Johnson Crash – Bathurst 1980 Collector’s'),
    ('Peter wAlL ArT Brock', 'Peter Brock'),
    ('  Peter  WALL\t \nART   Tribute  ', 'Peter Tribute'),
    ('Wall Art – Peter Brock', 'Peter Brock'),
    ('Peter Brock | Wall Art', 'Peter Brock'),
    ('Wall Art: Peter Wall Art Brock — WALL ART', 'Peter Brock'),
    ('Peter Brock – Collector’s Edition!', 'Peter Brock – Collector’s Edition!'),
    ('  Original  spacing – Tribute  ', '  Original  spacing – Tribute  '),
    ('Wall Artist / Sidewall Art', 'Wall Artist / Sidewall Art'),
    ('Wall Art', 'Wall Art'),
    ('  wALL\tART  ', '  wALL\tART  '),
    ('Wall Art –', 'Wall Art –'),
    ('<Brock & Moffat> Wall Art', '<Brock & Moffat>'),
)


class CollectionDisplayTitleTests(unittest.TestCase):
    def document(self, title):
        doc = catalogue_doc()
        doc['middle_sections'][-1]['products'][0]['title'] = title
        return doc

    def test_formatting(self):
        for original, expected in CASES:
            with self.subTest(original=original):
                self.assertEqual(collection_display_title(original), expected)

    def test_collection_preview_test_and_production_rendering_preserve_facts(self):
        from crm_preview_cache import preview
        for original, expected in CASES:
            with self.subTest(original=original):
                doc = self.document(original)
                before = deepcopy(doc)
                section = doc['middle_sections'][-1]
                with patch('crm_catalogue.collection_display_title', side_effect=lambda value: value):
                    original_html = catalogue_html(section)
                self.assertEqual(catalogue_html(section), original_html.replace(
                    '>'+escape(original, quote=True)+'</a>', '>'+escape(expected, quote=True)+'</a>'))
                with (patch('requests.sessions.Session.request', side_effect=AssertionError('No network')),
                      patch('crm_catalogue.Catalogue.resolve', side_effect=AssertionError('No product reads'))):
                    variants = [catalogue_html(section), render_middle(doc)[0],
                                preview({}, doc, CFG)['html'], render_campaign(doc, CFG)['html'],
                                render_campaign(doc, CFG, production=True,
                                                unsubscribe_url='https://example.test/unsubscribe')['html']]
                for html in variants:
                    self.assertIn('>'+escape(expected, quote=True)+'</a>', html)
                    self.assertIn('#037 / 100', html)
                    self.assertIn('64 REMAINING', html)
                self.assertEqual(doc, before)

    def test_browser_model_carries_formatted_titles_without_changing_selection(self):
        from crm_local_preview import model
        doc = self.document('Peter Brock Wall Art')
        before = deepcopy(doc)
        with patch('streamlit.session_state', {}):
            result = model(doc, CFG)
        self.assertEqual(result['catalogue_titles']['Peter Brock Wall Art'], 'Peter Brock')
        self.assertEqual(doc, before)
        self.assertEqual(result['resolved'][doc['middle_sections'][-1]['id']]['section']['products'][0]['title'],
                         'Peter Brock Wall Art')

    def test_every_flow_series_email_uses_shared_renderer(self):
        from crm_automation_definition import new_flow, email_step
        from crm_flow_tests import prepare
        flow = new_flow('welcome')
        flow['emails'] = [email_step(self.document(title), i*3600)
                          for i, (title, _) in enumerate(CASES[:3])]
        before = deepcopy(flow)
        cfg = {**CFG, 'test_unsubscribe_url': 'https://example.test/unsubscribe'}
        messages = prepare(flow, cfg)
        self.assertEqual(len(messages), 3)
        for (_, _, message), (_, expected) in zip(messages, CASES):
            self.assertIn('>'+expected+'</a>', message['html'])
            self.assertIn(expected, message['text'])
        self.assertEqual(flow, before)

    def test_smart_collection_hydration_uses_same_title_helper(self):
        from crm_smart_catalogue import hydrate
        from tests.test_crm_smart_catalogue import fixture
        doc = self.document('Stored manual Wall Art')
        doc['middle_sections'][-1]['settings']['smart'] = True
        cat, shop, store = fixture()
        resolve = cat.resolve
        def products(*args, **kwargs):
            rows = resolve(*args, **kwargs)
            for row in rows:
                row['title'] = 'Peter Brock Wall Art'
            return rows
        cat.resolve = products
        hydrated = hydrate(doc, store, shop, {'id':'gid://shopify/Customer/1'},
                           orders=[], catalogue=cat)
        before = deepcopy(hydrated)
        with (patch('streamlit.session_state', {}),
              patch('crm_smart_catalogue.preview', return_value=hydrated)):
            from crm_local_preview import model
            result = model(doc, CFG, hydrated_document=hydrated)
        self.assertEqual(result['catalogue_titles']['Peter Brock Wall Art'], 'Peter Brock')
        for production in (False, True):
            message = render_campaign(hydrated, CFG, production=production,
                                      unsubscribe_url='https://example.test/unsubscribe')
            self.assertIn('>Peter Brock</a>', message['html'])
        self.assertEqual(hydrated, before)


if __name__ == '__main__':
    unittest.main()
