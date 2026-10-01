"""Renderer-only collector styling and canonical-link regressions; no network I/O."""
from copy import deepcopy
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit
import unittest

from crm_catalogue import catalogue_html, canonical_product_url, product_issues
from crm_campaign_content import render_campaign
from crm_campaign_html import import_html
from tests.test_crm_modular_catalogue import catalogue_doc


class Markup(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.anchors, self.images, self.tags = [], [], []
        self.anchor = None
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append((tag, attrs))
        if tag == 'a':
            self.anchor = attrs
            self.anchors.append(attrs)
        if tag == 'img':
            self.images.append((attrs, self.anchor))

    def handle_endtag(self, tag):
        if tag == 'a':
            self.anchor = None


class CataloguePresentationTests(unittest.TestCase):
    def setUp(self):
        self.doc = catalogue_doc()
        self.section = self.doc['middle_sections'][-1]
        self.section['products'] = self.section['products'][:1]
        self.p = self.section['products'][0]
        self.p.update(url='https://www.sportscaveshop.com/products/example',
                      image='https://cdn.shopify.com/example.webp')

    def test_image_src_is_cdn_but_image_title_and_cta_open_same_product_in_new_tab(self):
        raw = Markup(catalogue_html(self.section))
        self.assertEqual(raw.images[0][0]['src'], self.p['image'])
        self.assertEqual(raw.images[0][1]['href'], self.p['url'])
        self.assertNotEqual(raw.images[0][0]['src'], raw.images[0][1]['href'])
        self.assertEqual([a['href'] for a in raw.anchors], [self.p['url']] * 3)
        for a in raw.anchors:
            self.assertEqual(a['target'], '_blank')
            self.assertEqual(a['rel'], 'noopener noreferrer')

    def test_sanitized_output_retains_safe_new_tab_links_and_image(self):
        html, text, checks = import_html(catalogue_html(self.section))
        markup = Markup(html)
        self.assertTrue(all(checks.values()))
        self.assertEqual(markup.images[0][0]['src'], self.p['image'] + '?format=png')
        self.assertIn(self.p['url'], text)
        self.assertTrue(all(a.get('target') == '_blank' and a.get('rel') == 'noopener noreferrer' for a in markup.anchors))

    def test_final_render_tracks_once_per_product_identically_in_all_links_and_plaintext(self):
        before = deepcopy(self.doc)
        rendered = render_campaign(self.doc)
        links = [a['href'] for a in Markup(rendered['html']).anchors if '/products/example' in a.get('href', '')]
        self.assertEqual(len(links), 3)
        self.assertEqual(len(set(links)), 1)
        self.assertEqual(urlsplit(links[0]).scheme, 'https')
        self.assertEqual(parse_qs(urlsplit(links[0]).query)['utm_content'], ['product_1'])
        self.assertEqual(parse_qs(urlsplit(links[0]).query)['sc_test'], ['1'])
        self.assertIn(links[0], rendered['text'])
        self.assertEqual(self.doc, before)  # URL, edition values and snapshot facts untouched.

    def test_invalid_or_nonproduct_urls_do_not_create_broken_anchors(self):
        for url in ('', '/products/example', 'http://example.com/products/example', 'javascript:alert(1)',
                    'https://cdn.shopify.com/example.webp', 'https://admin.shopify.com/store/test/products/1',
                    'https://example.com/products/example?preview_theme_id=1',
                    'https://example.com/products/example?signature=secret'):
            with self.subTest(url=url):
                self.p['url'] = url
                self.assertEqual(canonical_product_url(self.p), '')
                self.assertTrue(product_issues(self.p, self.section['settings']))
                self.assertEqual(Markup(catalogue_html(self.section)).anchors, [])

    def test_valid_locale_and_query_survive_escaping_without_rebuilding_destination(self):
        self.p['url'] = 'https://www.sportscaveshop.com/en-au/products/example?variant=1&locale=en'
        self.assertEqual(canonical_product_url(self.p), self.p['url'])
        self.assertEqual([a['href'] for a in Markup(catalogue_html(self.section)).anchors], [self.p['url']] * 3)

    def test_compact_styles_survive_renderer_without_distorting_images(self):
        result = render_campaign(self.doc)['html']
        for style in ('width:100%', 'height:auto', 'font-size:21px', 'padding:12px 18px', 'background:#111111', 'color:#faf6eb'):
            self.assertIn(style, result)
        self.assertNotIn('object-fit', result)
        self.assertNotIn('text-transform:uppercase">Artwork', result)

    def test_layouts_share_renderer_and_preserve_responsive_hook(self):
        for columns in (1,2):
            self.section['settings']['columns']=columns
            html=render_campaign(self.doc)['html']
            self.assertNotIn('class="sc-stack"',html)
            self.assertIn('width="552"',html)
            self.assertNotIn('max-height:300px',html)
            self.assertIn('@media only screen and (max-width:480px)',html)

    def test_missing_editions_and_display_toggles_keep_valid_customer_output(self):
        self.p['edition'] = None
        html = catalogue_html(self.section)
        self.assertNotIn('Edition data not connected', html)
        self.assertNotIn('NEXT AVAILABLE', html)
        self.assertEqual(len(Markup(html).anchors), 3)
        self.section['settings']['display'].update(image=False, title=False, cta=False)
        self.assertEqual(Markup(catalogue_html(self.section)).anchors, [])

    def test_custom_cta_and_price_values_are_not_rewritten(self):
        self.section['settings']['cta'] = 'Explore this artwork'
        self.p.update(price='69.95', compare_at='79.50')
        html = catalogue_html(self.section)
        for text in ('Explore this artwork', 'A$69.95', 'A$79.50'):
            self.assertIn(text, html)

    def test_edition_wording_and_values_are_accurate_without_allocation_claim(self):
        html = catalogue_html(self.section)
        for text in ('LIMITED TO 100 WORLDWIDE', '#037 / 100', 'NEXT AVAILABLE · 64 REMAINING'):
            self.assertIn(text, html)
        self.assertNotIn('Your edition', html)
        self.p['edition'].update(remaining=0, next=101, sold=100)
        html = catalogue_html(self.section)
        self.assertIn('SOLD OUT', html)
        self.assertNotIn('NEXT AVAILABLE', html)


if __name__ == '__main__':
    unittest.main()
