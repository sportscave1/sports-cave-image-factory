"""Offline marketplace acceptance: no app startup, credentials or provider writes."""
import base64
from copy import deepcopy
import io
import json
import sys
import threading
import types
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from PIL import Image
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

import marketplace as core
import marketplace_api as api
from marketplace_publish import publish_website
from marketplace_store import MarketplaceStore
from prompt_releases import ReleaseError
from tests.marketplace_storage_fakes import MemorySource


def sample():
    return {'title': 'Broncos collector jersey', 'category': 'jerseys', 'sport': 'NRL',
            'team': 'Brisbane Broncos', 'condition': 'Excellent', 'description': 'Size L. Actual item. Small mark on the back.',
            'seller_name': 'Test collector', 'seller_email': 'seller@example.invalid',
            'seller_type': 'Private collector', 'location': 'Brisbane, QLD', 'provenance': 'Retail jersey.',
            'price': '200.00', 'shipping': '15.00', 'consent': True}


def photograph():
    output = io.BytesIO()
    Image.new('RGB', (400, 500), '#42635f').save(output, format='JPEG')
    return base64.b64encode(output.getvalue()).decode()


class FakeConnection:
    """Transactional state-table fixture with rollback and independent connections."""
    def __init__(self, database):
        self.database = database
        self.rows = []
    def __enter__(self):
        self.database.mutex.acquire()
        self.before = deepcopy(self.database.values)
        return self
    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self.database.values = self.before
        self.database.mutex.release()
    def execute(self, sql, args=()):
        if 'pg_advisory_xact_lock' in sql:
            self.rows = []
        elif sql.lstrip().startswith('INSERT'):
            key, value = args
            if self.database.fail_photo and ':image:' in key:
                raise OSError('synthetic failure')
            if self.database.fail_listing and ':listing:' in key:
                raise OSError('synthetic index failure')
            self.database.values[key] = json.loads(value)
            self.rows = []
        elif 'WHERE key=%s' in sql:
            self.rows = [{'value': deepcopy(self.database.values[args[0]])}] if args[0] in self.database.values else []
        elif 'WHERE key LIKE %s' in sql:
            self.rows = [{'value': deepcopy(v)} for k, v in self.database.values.items() if k.startswith(args[0].removesuffix('%'))
                         and ("value->>'status'='published'" not in sql or v['status'] == 'published')]
        else:
            raise AssertionError('Unexpected query: ' + sql)
        return self
    def fetchone(self):
        return self.rows[0] if self.rows else None
    def fetchall(self):
        return self.rows


class FakeDatabase:
    def __init__(self):
        self.values = {}
        self.mutex = threading.RLock()
        self.fail_photo = False
        self.fail_listing = False
        self.media = MemorySource()
    def connect(self):
        return FakeConnection(self)


def memory_store():
    database = FakeDatabase()
    return MarketplaceStore(database.connect, media_storage=database.media)


class OutreachTests(unittest.TestCase):
    def test_retries_and_previous_days_are_excluded(self):
        from marketplace_outreach import OutreachStore, SYDNEY
        from datetime import datetime
        from marketplace_store import put
        store = OutreachStore(FakeDatabase().connect)
        row = {'seller': 'First seller', 'category': 'Cards', 'item': 'Card',
               'source_url': 'https://example.invalid/item', 'contact_url': 'https://example.invalid/message',
               'contact_basis': 'Invites dealer enquiries'}
        with store.db() as conn:
            put(conn, 'outreach:day:2020-01-01', {'date': '2020-01-01', 'sellers': [row]})
        new = dict(row, seller='New seller', source_url='https://new.invalid/item',
                   contact_url='https://new.invalid/message')
        edition = {'date': datetime.now(SYDNEY).date().isoformat(), 'sellers': [dict(row, seller='Alias'), new]}
        self.assertEqual(store.submit(edition)['sellers'], [new])
        self.assertEqual(store.submit(edition)['sellers'], [new])
        self.assertEqual(len(store.history_page(0)['sellers']), 2)
        with self.assertRaises(ValueError):
            store.submit(dict(edition, sellers=[dict(new, contact_url='javascript:bad')]))


class ContractTests(unittest.TestCase):
    def test_exact_fee_and_money(self):
        self.assertEqual(core.fee_quote(20000), {'fee_cents': 1000, 'payout_cents': 19000})
        self.assertEqual(core.fee_quote(1010)['fee_cents'], 51)
        self.assertEqual(core.money(20000), 'A$200')
    def test_rejects_invalid_money_and_consent(self):
        for value in ('NaN', 'Infinity', '-1', '9.99', '200.001', '50001'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                core.submission({**sample(), 'price': value})
        with self.assertRaises(ValueError):
            core.submission({**sample(), 'consent': False})
    def test_photo_processing_and_rejection(self):
        result = core.prepare_photos([photograph(), photograph()])
        with Image.open(io.BytesIO(base64.b64decode(result[0]))) as image:
            self.assertEqual(image.format, 'WEBP')
            self.assertEqual(image.size, (400, 500))
            self.assertFalse(image.getexif())
        for values in ([], [photograph()], ['not-a-photo', photograph()], ['A' * 2800001, photograph()]):
            with self.assertRaises(ValueError):
                core.prepare_photos(values)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.database = FakeDatabase()
        self.store = MarketplaceStore(self.database.connect, media_storage=self.database.media)
    def submit(self):
        return self.store.submit(core.submission(sample()), core.prepare_photos([photograph(), photograph()]))['id']
    def test_approval_gate_privacy_images_and_withdrawal(self):
        key = self.submit()
        self.assertIsNone(self.store.listing(key, public=True))
        self.assertIsNone(self.store.photo(key, 0))
        self.assertEqual(self.store.listings(public=True), [])
        self.store.moderate(key, 'published', 1, 'synthetic-admin')
        row = self.store.listing(key, public=True)
        self.assertNotIn('seller_email', row)
        self.assertNotIn('consented_at', row)
        self.assertNotIn('history', row)
        self.assertTrue(self.store.photo(key, 0))
        self.store.moderate(key, 'withdrawn', 2, 'synthetic-admin')
        self.assertIsNone(self.store.photo(key, 0))
        with self.assertRaises(ValueError):
            self.store.enquire(key, 'Buyer', 'buyer@example.invalid', 'Is this available?')
    def test_partial_source_upload_does_not_create_an_approval_record(self):
        self.database.media.backend.fail_upload = 'photo-2.webp'
        with self.assertRaises(Exception):
            self.submit()
        self.assertEqual(self.database.values, {})
    def test_stale_reviewer_cannot_override_another_decision(self):
        key = self.submit()
        self.store.moderate(key, 'declined', 1, 'reviewer-one')
        with self.assertRaises(ValueError):
            self.store.moderate(key, 'published', 1, 'reviewer-two')
        self.assertEqual(self.store.listing(key)['status'], 'declined')
    def test_enquiry_is_private_and_can_be_handled(self):
        key = self.submit()
        self.store.moderate(key, 'published', 1, 'admin')
        enquiry = self.store.enquire(key, 'Buyer', 'buyer@example.invalid', 'Can I see the tag?')
        self.assertEqual(self.store.enquiries()[0]['status'], 'new')
        self.store.resolve_enquiry(enquiry)
        self.assertEqual(self.store.enquiries()[0]['status'], 'handled')
        self.assertNotIn('buyer@example.invalid', json.dumps(self.store.listings(public=True)))
    def test_concurrent_website_edits_fail_closed(self):
        config = deepcopy(core.DEFAULT_SITE)
        self.store.save_draft(config, config, 0)
        with self.assertRaises(ValueError):
            self.store.save_draft({**config, 'headline': 'Stale headline'}, config, 0)

    def test_publish_attempt_survives_sessions_and_blocks_stale_edits(self):
        config = deepcopy(core.DEFAULT_SITE)
        self.store.save_draft({**config, 'headline': 'A new chapter.'}, config, 0)
        first = self.store.begin_publish(1)
        new_session = MarketplaceStore(self.database.connect, media_storage=self.database.media)
        second = new_session.begin_publish(1)
        self.assertEqual(first['release_id'], second['release_id'])
        with self.assertRaises(ValueError):
            self.store.save_draft(config, config, 1)
        new_session.receipt({'release_id': first['release_id'], 'commit': 'b' * 40})
        self.assertNotIn('attempt', self.store.draft(config))


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.database = FakeDatabase()
        self.store = MarketplaceStore(self.database.connect, media_storage=self.database.media)
        self.override = patch.object(api, 'MarketplaceStore', return_value=self.store)
        self.override.start()
        api._RATE.clear()
        self.client = TestClient(Starlette(routes=[Route(path, endpoint, methods=list(methods)) for path, endpoint, methods in api.ROUTES]),
                                 base_url=core.PUBLIC_ORIGIN)
        self.headers = {'Origin': core.PUBLIC_ORIGIN}
    def tearDown(self):
        self.override.stop()
        self.client.close()
    def submit(self):
        payload = {**sample(), 'photos': [photograph(), photograph()]}
        result = self.client.post('/marketplace/api/submissions', json=payload, headers=self.headers)
        self.assertEqual(result.status_code, 201, result.text)
        return result.json()['reference']
    def test_landing_is_server_rendered_small_and_has_schema(self):
        response = self.client.get('/marketplace')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Great collections keep moving.', response.text)
        self.assertIn('application/ld+json', response.text)
        self.assertIn('CollectionPage', response.text)
        self.assertLess(len(response.content), 15000)
        self.assertNotIn('streamlit', response.text)
        self.assertIn('nonce-', response.headers['content-security-policy'])
    def test_full_public_flow_and_no_private_data_in_pages(self):
        key = self.submit()
        self.assertEqual(self.client.get('/marketplace/item/' + key).status_code, 404)
        self.assertEqual(self.client.get('/marketplace/images/' + key + '/0.webp').status_code, 404)
        self.store.moderate(key, 'published', 1, 'admin')
        result = self.client.get('/marketplace/item/' + key)
        self.assertEqual(result.status_code, 200)
        self.assertIn('Product', result.text)
        self.assertIn('200.00', result.text)
        self.assertNotIn('seller@example.invalid', result.text)
        self.assertEqual(self.client.get('/marketplace/images/' + key + '/0.webp').headers['content-type'], 'image/webp')
        payload = {'listing_id': key, 'name': 'Buyer', 'email': 'buyer@example.invalid', 'message': 'Is this available?', 'consent': True}
        self.assertEqual(self.client.post('/marketplace/api/enquiries', json=payload, headers=self.headers).status_code, 201)
        self.assertEqual(len(self.store.enquiries()), 1)
        self.assertIn(key, self.client.get('/marketplace/sitemap.xml').text)
        self.store.moderate(key, 'withdrawn', 2, 'admin')
        self.assertNotIn(key, self.client.get('/marketplace/sitemap.xml').text)
    def test_search_and_category_filters_are_real(self):
        key = self.submit()
        self.store.moderate(key, 'published', 1, 'admin')
        self.assertIn('Broncos collector jersey', self.client.get('/marketplace?q=Broncos').text)
        self.assertNotIn('Broncos collector jersey', self.client.get('/marketplace?category=cards').text)
        self.assertNotIn('Broncos collector jersey', self.client.get('/marketplace?q=missing').text)
    def test_bad_input_origins_and_private_assets_fail_closed(self):
        for headers in ({}, {'Origin': 'https://attacker.invalid'}):
            self.assertEqual(self.client.post('/marketplace/api/submissions', json=sample(), headers=headers).status_code, 403)
        self.assertEqual(self.client.post('/marketplace/api/submissions', json={}, headers=self.headers).status_code, 400)
        self.assertEqual(self.client.get('/marketplace/assets/site.json').status_code, 404)
        self.assertEqual(self.client.get('/marketplace/assets/../../marketplace.py').status_code, 404)
        self.assertEqual(self.client.get('/marketplace/item/invalid').status_code, 404)
    def test_pause_and_storage_outage_are_honest(self):
        with patch.object(api.core, 'deployed_site', return_value={**core.DEFAULT_SITE, 'intake_open': False}):
            result = self.client.post('/marketplace/api/submissions', json=sample(), headers=self.headers)
            self.assertEqual(result.status_code, 503)
            self.assertIn('paused', result.json()['error'])
        with patch.object(self.store, 'listings', side_effect=OSError('synthetic')):
            result = self.client.get('/marketplace')
            self.assertIn('temporarily unavailable', result.text)
    def test_escaping_prevents_stored_script_execution(self):
        row = {**core.submission(sample()), 'id': str(uuid4()), 'photo_count': 2,
               'title': '<script>alert(1)</script>', 'status': 'published'}
        text = api.views.item(row)
        self.assertNotIn('<script>alert(1)</script>', text)
        self.assertIn('&lt;script&gt;', text)
        self.assertIn('\\u003cscript', text)
    def test_assets_have_validators_and_do_not_expose_source(self):
        response = self.client.get('/marketplace/assets/marketplace.css')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get('/marketplace/assets/marketplace.css', headers={'If-None-Match': response.headers['etag']}).status_code, 304)

    def test_home_keeps_responsive_hero_without_empty_catalogue_navigation(self):
        import re
        response = self.client.get('/marketplace')
        self.assertIn('class="hero-photo"', response.text)
        self.assertIn('fetchpriority="high"', response.text)
        self.assertIn('collector-room-800.webp 800w', response.text)
        self.assertNotIn('class="browse-menu"', response.text)
        self.assertNotIn('Browse by sport', response.text)
        self.assertNotIn('Popular collections', response.text)
        self.assertIn('href="#finds"', response.text)
        self.assertIn('/marketplace/buyer-protection', response.text)
        self.assertEqual(len(re.findall(r'<h1\b', response.text)), 1)
        graph = json.loads(re.search(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', response.text, re.S).group(1))
        website = next(row for row in graph['@graph'] if row['@type'] == 'WebSite')
        self.assertNotIn('potentialAction', website)
        self.assertNotIn('stillwhite', response.text.lower())
        self.assertNotIn('5 Star Reviews', response.text)

    def test_browse_has_its_own_canonical_and_functional_price_sort(self):
        for title, price in (('Higher price jersey', '500'), ('Lower price jersey', '20')):
            row = core.submission({**sample(), 'title': title, 'price': price})
            key = self.store.submit(row, [photograph(), photograph()])['id']
            self.store.moderate(key, 'published', 1, 'admin')
        low = self.client.get('/marketplace/browse?sort=price_low&sport=NRL')
        high = self.client.get('/marketplace/browse?sort=price_high&sport=NRL')
        self.assertEqual(low.status_code, 200)
        self.assertNotIn('class="hero-photo"', low.text)
        self.assertIn('href="' + core.PUBLIC_ORIGIN + '/marketplace/browse"', low.text)
        self.assertLess(low.text.index('<h3>Lower price jersey'), low.text.index('<h3>Higher price jersey'))
        self.assertLess(high.text.index('<h3>Higher price jersey'), high.text.index('<h3>Lower price jersey'))
        self.assertIn('name="sport" value="NRL"', low.text)
        self.assertIn('noindex,follow', low.text)

    def test_editorial_assets_have_small_payloads_and_keep_source_private(self):
        for asset, limit in (('collector-room-1600.webp', 75000), ('collector-room-800.webp', 25000), ('logo.webp', 8000)):
            response = self.client.get('/marketplace/assets/' + asset)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers['content-type'], 'image/webp')
            self.assertLess(len(response.content), limit)
        self.assertEqual(self.client.get('/marketplace/assets/marketplace-home.css').status_code, 200)
        self.assertEqual(self.client.get('/marketplace/assets/site.json').status_code, 404)
        self.assertEqual(self.client.get('/marketplace/assets/original.png').status_code, 404)

    def test_filtered_search_keeps_facets_and_escapes_query_markup(self):
        response = self.client.get('/marketplace/browse', params={'q': '<script>alert(1)</script>', 'category': 'cards', 'sport': 'NRL'})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('<script>alert(1)</script>', response.text)
        self.assertIn('&lt;script&gt;', response.text)
        self.assertIn('name="category" value="cards"', response.text)
        self.assertIn('/marketplace/browse', self.client.get('/marketplace/sitemap.xml').text)


class PublishTests(unittest.TestCase):
    def client(self):
        client = Mock()
        client.head.return_value = 'a' * 40
        client.read.return_value = (json.dumps(core.DEFAULT_SITE), 'blob-sha')
        client.request.return_value = {'commit': {'sha': 'b' * 40}}
        return client
    def draft(self):
        return {'base': deepcopy(core.DEFAULT_SITE), 'config': {**core.DEFAULT_SITE, 'headline': 'Pass the passion on.'}, 'release_id': str(uuid4())}
    def test_publish_updates_only_website_settings_on_main(self):
        client = self.client()
        result = publish_website(self.draft(), client)
        self.assertEqual(result['commit'], 'b' * 40)
        method, path, body = client.request.call_args.args
        self.assertEqual((method, path), ('PUT', 'contents/static/marketplace/site.json'))
        self.assertEqual(body['branch'], 'main')
        self.assertEqual(body['sha'], 'blob-sha')
        content = json.loads(base64.b64decode(body['content']))
        self.assertEqual(content['headline'], 'Pass the passion on.')
    def test_concurrent_changes_and_identical_content_do_not_publish(self):
        client = self.client()
        draft = self.draft()
        client.read.return_value = (json.dumps({**core.DEFAULT_SITE, 'headline': 'Another editor'}), 'different-sha')
        with self.assertRaises(ReleaseError):
            publish_website(draft, client)
        client.request.assert_not_called()
        client = self.client()
        draft['config'] = deepcopy(core.DEFAULT_SITE)
        with self.assertRaises(ValueError):
            publish_website(draft, client)
    def test_lost_response_is_reconciled_without_a_second_commit(self):
        client = self.client()
        draft = self.draft()
        client.read.return_value = (json.dumps({**draft['config'], 'release_id': draft['release_id']}), 'new-blob')
        result = publish_website(draft, client)
        self.assertEqual(result['release_id'], draft['release_id'])
        client.request.assert_not_called()


class AdminTests(unittest.TestCase):
    def test_real_registry_restricts_marketplace_to_active_administrators(self):
        import os_accounts
        self.assertTrue(os_accounts.can_access_page({'role': 'admin', 'is_active': True}, 'Marketplace'))
        self.assertFalse(os_accounts.can_access_page({'role': 'worker', 'is_active': True, 'page_permissions': ['marketplace']}, 'Marketplace'))
        self.assertFalse(os_accounts.can_access_page({'role': 'admin', 'is_active': False}, 'Marketplace'))

    def test_website_draft_controls_save_and_publish_through_mocked_git(self):
        from streamlit.testing.v1 import AppTest
        import marketplace_page
        store = memory_store()
        fake_git = Mock(token='synthetic', render_token='')
        result = {'release_id': 'synthetic-release', 'commit': 'c' * 40, 'published_at': core.now()}
        with patch.object(marketplace_page, 'MarketplaceStore', return_value=store), \
             patch.object(marketplace_page, 'GitStore', return_value=fake_git), \
             patch.object(marketplace_page, 'publish_website', return_value=result) as publish:
            page = AppTest.from_string('import streamlit as st\nfrom marketplace_page import render_website, MarketplaceStore\nrender_website(st, MarketplaceStore())').run()
            self.assertFalse(page.exception)
            self.assertTrue(next(b for b in page.button if b.label == 'Publish website').disabled)
            page.text_input[0].set_value('Pass the passion on.').run()
            next(b for b in page.button if b.label == 'Save website draft').click().run()
            self.assertFalse(page.exception)
            self.assertEqual(store.draft(core.DEFAULT_SITE)['config']['headline'], 'Pass the passion on.')
            next(b for b in page.button if b.label == 'Publish website').click().run()
            self.assertFalse(page.exception)
            publish.assert_called_once()
            self.assertEqual(store.receipt()['commit'], 'c' * 40)

    def test_admin_only_and_real_empty_workspace(self):
        from streamlit.testing.v1 import AppTest
        import marketplace_page
        accounts = types.ModuleType('os_accounts')
        accounts.is_admin = lambda user: user.get('role') == 'admin'
        store = memory_store()
        with patch.dict(sys.modules, {'os_accounts': accounts}), patch.object(marketplace_page, 'MarketplaceStore', return_value=store):
            page = AppTest.from_string("from marketplace_page import render_page\nrender_page({'id':'test','role':'admin'})").run()
            self.assertFalse(page.exception)
            self.assertIn('Marketplace', [t.value for t in page.title])
            self.assertEqual([t.label for t in page.tabs], ['Listings', 'Enquiries', 'Website & publish', 'Outreach'])
            page = AppTest.from_string("from marketplace_page import render_page\nrender_page({'id':'test','role':'worker'})").run()
            self.assertFalse(page.exception)
            self.assertTrue(page.error)


if __name__ == '__main__':
    unittest.main()
