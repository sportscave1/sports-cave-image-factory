"""Credential-free account, private-chat and invoice acceptance/security checks."""
import base64
from copy import deepcopy
import json
import smtplib
import time
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

import marketplace as core
import marketplace_api as api
import marketplace_account_api as customer_api
import marketplace_account_views as views
from marketplace_accounts import (Accounts, Provider, COOKIE, FLOW_COOKIE, SignInRequired,
                                  AuthUnavailable, digest, safe_next)
from marketplace_chat import ChatStore, amount, invoice_url
from marketplace_store import PREFIX, put
from tests.test_marketplace import FakeDatabase, sample, photograph

PAYPAL = 'https://www.paypal.com/invoice/p/#INV2-AB12-CD34-EF56-GH78'
SECRET = 'synthetic password for tests'


def payload(kind='text', **values):
    return {'kind': kind, 'request_id': str(uuid4()), 'text': 'Is the jersey still available?', **values}


class FakeProvider:
    """A separately verified identity service; no network, emails or real users."""
    def __init__(self, database):
        self.database = database
        self.users, self.tokens, self.calls = {}, {}, []
        self.recovery_tokens = None
    def add(self, address, name='Collector', confirmed=True):
        uid, sid = str(uuid4()), str(uuid4())
        user = {'id': uid, 'email': address, 'email_confirmed_at': '2026-01-01' if confirmed else None,
                'user_metadata': {'display_name': name, 'role': 'admin'}}
        self.users[address] = (user, sid)
        self.database.sessions[sid] = uid
        return user
    def signin(self, address, secret):
        if address not in self.users or secret != SECRET:
            raise SignInRequired('Check your email and password.')
        user, sid = self.users[address]
        claims = base64.urlsafe_b64encode(json.dumps({'sub': user['id'], 'session_id': sid}).encode()).decode().rstrip('=')
        token = 'synthetic.' + claims + '.verified-by-fake-provider'
        self.tokens[token] = user
        return {'access_token': token, 'refresh_token': 'refresh:' + address, 'expires_in': 3600}
    def user(self, token):
        self.calls.append(('user', token))
        user = self.tokens.get(token)
        if not user or not user.get('email_confirmed_at'):
            raise SignInRequired('Confirm your email before signing in.')
        return deepcopy(user)
    def refresh(self, token):
        self.calls.append(('refresh', token))
        return self.signin(token.removeprefix('refresh:'), SECRET)
    def signup(self, address, secret, name):
        self.calls.append(('signup', address))
    def logout(self, token):
        self.calls.append(('logout', token))
    def call(self, method, path, data=None, **options):
        self.calls.append((method, path, data, options))
        if path == 'token':
            return self.recovery_tokens
        if path == 'logout' and options.get('params', {}).get('scope') == 'global':
            self.database.sessions.clear()
        return {}


class Setup(unittest.TestCase):
    def setUp(self):
        self.db = FakeDatabase()
        self.store = ChatStore(self.db.connect, media_storage=self.db.media)
        self.provider = FakeProvider(self.db)
        self.accounts = Accounts(self.store, self.provider)
        self.buyer = self.provider.add('buyer@example.invalid', 'Buyer')
        self.seller = self.provider.add('seller@example.invalid', 'Seller')
        self.other = self.provider.add('other@example.invalid', 'Other buyer')
        self.bearer, self.buyer_profile = self.accounts.signin(self.buyer['email'], SECRET)
        self.seller_bearer, self.seller_profile = self.accounts.signin(self.seller['email'], SECRET)
        self.other_bearer, self.other_profile = self.accounts.signin(self.other['email'], SECRET)
        result = self.store.submit(core.submission(sample()), core.prepare_photos([photograph(), photograph()]))
        self.item = result['id']
        self.store.moderate(self.item, 'published', 1, 'synthetic-admin')
    def start(self, **values):
        return self.store.start(self.buyer['id'], self.item, payload(**values))['id']


class AccountTests(Setup):
    def test_verified_identity_creates_customer_without_staff_privileges(self):
        row = self.accounts.authenticate(self.bearer)
        self.assertEqual(row['id'], self.buyer['id'])
        self.assertNotIn('role', row)
        self.assertNotIn('password', row)
        self.assertFalse(any('os_account' in key for key in self.db.values))
    def test_unconfirmed_identity_cannot_create_account_or_session(self):
        user = self.provider.add('unconfirmed@example.invalid', confirmed=False)
        with self.assertRaises(SignInRequired):
            self.accounts.signin(user['email'], SECRET)
        self.assertNotIn(PREFIX + 'account:' + user['id'], self.db.values)
    def test_unknown_or_forged_bearers_fail(self):
        for bearer in (None, '', 'forged', 'x' * 1000):
            with self.assertRaises(SignInRequired):
                self.accounts.authenticate(bearer)
    def test_session_revocation_is_immediate_even_before_jwt_expiry(self):
        sid = self.provider.users[self.buyer['email']][1]
        del self.db.sessions[sid]
        with self.assertRaises(SignInRequired):
            self.accounts.authenticate(self.bearer)
    def test_blocked_account_cannot_reauthenticate_or_message(self):
        thread = self.start()
        self.store.set_account_status(self.buyer['id'], 'blocked', 'admin')
        with self.assertRaises(PermissionError):
            self.accounts.authenticate(self.bearer)
        with self.assertRaises(PermissionError):
            self.accounts.signin(self.buyer['email'], SECRET)
        with self.assertRaises(PermissionError):
            self.store.send(thread, self.seller['id'], payload())
    def test_logout_revokes_locally_during_provider_outage(self):
        with patch.object(self.provider, 'logout', side_effect=AuthUnavailable('offline')):
            self.accounts.logout(self.bearer)
        with self.assertRaises(SignInRequired):
            self.accounts.authenticate(self.bearer)
    def test_expired_tokens_refresh_only_with_verified_matching_identity(self):
        key = PREFIX + 'session:' + digest(self.bearer)
        self.db.values[key]['token_expires'] = time.time() - 1
        self.assertEqual(self.accounts.authenticate(self.bearer)['id'], self.buyer['id'])
        self.assertTrue(any(c[0] == 'refresh' for c in self.provider.calls))
    def test_expired_app_session_does_not_refresh(self):
        self.db.values[PREFIX + 'session:' + digest(self.bearer)]['expires'] = 0
        with self.assertRaises(SignInRequired):
            self.accounts.authenticate(self.bearer)
        self.assertFalse(any(c[0] == 'refresh' for c in self.provider.calls))
    def test_recreated_identity_cannot_take_existing_verified_email(self):
        self.provider.add(self.seller['email'], 'Replacement')
        with self.assertRaises(PermissionError):
            self.accounts.signin(self.seller['email'], SECRET)
    def test_invitation_is_private_pending_and_changes_to_joined_after_signup(self):
        address = 'new@example.invalid'
        self.store.invite(address, 'New collector', 'admin')
        self.assertEqual(len(self.store.accounts()), 3)
        self.provider.add(address)
        self.accounts.signin(address, SECRET)
        self.assertEqual(self.store.invitations()[0]['status'], 'joined')
    def test_recovery_uses_pkce_and_cannot_be_used_as_marketplace_session(self):
        flow = self.accounts.recover(self.buyer['email'])
        request = next(c for c in self.provider.calls if c[0:2] == ('POST', 'recover'))
        self.assertEqual(request[2]['code_challenge_method'], 's256')
        self.assertNotIn('verifier', request[2])
        with self.assertRaises(SignInRequired):
            self.accounts.authenticate(flow)
        self.provider.recovery_tokens = self.provider.signin(self.buyer['email'], SECRET)
        self.accounts.recovery_exchange(flow, 'synthetic-code')
        with self.assertRaises(ValueError):
            self.accounts.recovery_exchange(flow, 'synthetic-code')
        self.accounts.reset_password(flow, SECRET + '-new')
        with self.assertRaises(SignInRequired):
            self.accounts.authenticate(self.bearer)
        with self.assertRaises(SignInRequired):
            self.accounts.reset_password(flow, SECRET + '-new')
    def test_recovery_rejects_wrong_browser_expired_flow_and_changed_email(self):
        with self.assertRaises(ValueError):
            self.accounts.recovery_exchange('', 'code')
        flow = self.accounts.recover(self.buyer['email'])
        self.provider.recovery_tokens = self.provider.signin(self.other['email'], SECRET)
        with self.assertRaises(PermissionError):
            self.accounts.recovery_exchange(flow, 'code')
        self.db.values[PREFIX + 'recovery:' + digest(flow)]['expires'] = 0
        with self.assertRaises(ValueError):
            self.accounts.recovery_exchange(flow, 'code')
    def test_next_path_never_redirects_to_external_sites_or_auth_callbacks(self):
        for value in ('https://attacker.invalid', '//attacker.invalid', '/marketplace\\evil',
                      '/marketplace/auth/recovery?code=bad', '/app', 'https://[', '/marketplace/\nattack'):
            self.assertEqual(safe_next(value), '/marketplace/inbox')
        self.assertEqual(safe_next('/marketplace/contact/demo?intent=offer'), '/marketplace/contact/demo?intent=offer')

    def test_expired_sessions_are_removed_without_touching_messages_or_active_sessions(self):
        thread = self.start()
        expired = PREFIX + 'session:' + digest('expired-synthetic-session')
        self.db.values[expired] = {'expires': 0, 'access_token': 'obsolete'}
        self.accounts.signin(self.other['email'], SECRET)
        self.assertNotIn(expired, self.db.values)
        self.assertEqual(self.accounts.authenticate(self.bearer)['id'], self.buyer['id'])
        self.assertEqual(len(self.store.conversation(thread, self.buyer['id'])['messages']), 1)


class ConversationTests(Setup):
    def test_buyer_and_seller_can_chat_but_other_buyers_cannot_read_or_write(self):
        thread = self.start()
        self.store.send(thread, self.seller['id'], payload(text='Yes, here to help.'))
        result = self.store.conversation(thread, self.buyer['id'])
        self.assertEqual([r['sender'] for r in result['messages']], ['buyer', 'seller'])
        for operation in (lambda: self.store.conversation(thread, self.other['id']),
                          lambda: self.store.send(thread, self.other['id'], payload()),
                          lambda: self.store.safety(thread, self.other['id'], 'block')):
            with self.assertRaises(ValueError): operation()
        self.assertEqual(self.store.inbox(self.other['id']), [])
    def test_inbox_and_payload_do_not_expose_emails_tokens_or_storage_receipts(self):
        thread = self.start()
        data = json.dumps(self.store.conversation(thread, self.buyer['id'])) + json.dumps(self.store.inbox(self.seller['id']))
        for text in ('@example', 'access_token', 'refresh_token', 'seller_email_hash', 'dropbox', 'media_source', self.buyer['id']):
            self.assertNotIn(text, data)
    def test_seller_cannot_contact_their_own_listing(self):
        with self.assertRaises(ValueError):
            self.store.start(self.seller['id'], self.item, payload())
    def test_one_thread_per_buyer_and_listing_and_idempotent_send(self):
        data = payload()
        first = self.store.start(self.buyer['id'], self.item, data)
        second = self.store.start(self.buyer['id'], self.item, data)
        self.assertEqual(first, second)
        third = self.store.start(self.buyer['id'], self.item, payload(text='Another question'))
        self.assertEqual(first['id'], third['id'])
        self.assertEqual(len(self.store.conversation(first['id'], self.buyer['id'])['messages']), 2)
    def test_guest_seller_is_claimed_by_verified_email_only(self):
        address = 'guest-seller@example.invalid'
        row = {**core.submission(sample()), 'seller_email': address}
        item = self.store.submit(row, core.prepare_photos([photograph(), photograph()]))['id']
        self.store.moderate(item, 'published', 1, 'admin')
        thread = self.store.start(self.buyer['id'], item, payload())['id']
        self.assertFalse(self.store.conversation(thread, self.buyer['id'])['conversation']['seller_joined'])
        self.assertEqual(self.store.inbox(self.other['id']), [])
        user = self.provider.add(address, 'Guest seller')
        _, profile = self.accounts.signin(address, SECRET)
        inbox = self.store.inbox(profile['id'])
        self.assertEqual(inbox[0]['id'], thread)
        self.assertEqual(self.store.listing(item)['seller_user_id'], user['id'])
        self.assertTrue(self.store.conversation(thread, self.buyer['id'])['conversation']['seller_joined'])
    def test_offer_is_buyer_only_and_seller_response_is_once(self):
        thread = self.start()
        offer = self.store.send(thread, self.buyer['id'], payload('offer', amount='175.50'))
        for operation in (lambda: self.store.send(thread, self.seller['id'], payload('offer', amount='175')),
                          lambda: self.store.send(thread, self.buyer['id'], payload('offer_response', offer_seq=offer['seq'], choice='accepted'))):
            with self.assertRaises(PermissionError): operation()
        self.store.send(thread, self.seller['id'], payload('offer_response', offer_seq=offer['seq'], choice='accepted'))
        with self.assertRaises(ValueError):
            self.store.send(thread, self.seller['id'], payload('offer_response', offer_seq=offer['seq'], choice='declined'))
        messages = self.store.conversation(thread, self.buyer['id'])['messages']
        self.assertEqual(messages[1]['status'], 'accepted')
        self.assertNotIn('paid', json.dumps(messages))
        self.assertEqual(self.store.listing(self.item)['status'], 'published')
    def test_only_seller_can_share_genuine_paypal_invoice_with_explicit_amount(self):
        thread = self.start()
        with self.assertRaises(PermissionError):
            self.store.send(thread, self.buyer['id'], payload('invoice', amount='180', url=PAYPAL))
        self.store.send(thread, self.seller['id'], payload('invoice', amount='195.00', url=PAYPAL))
        row = self.store.conversation(thread, self.buyer['id'])['messages'][-1]
        self.assertEqual(row['amount_cents'], 19500)
        self.assertEqual(row['status'], 'shared')
        self.assertNotIn('paid', row)
        self.assertNotIn('fee_cents', row)
    def test_invalid_messages_rollback_without_partial_thread_or_offer(self):
        for data in (payload(text=''), payload(text='x' * 2001), payload('offer', amount='NaN'),
                     payload('invoice', amount='10', url='https://evil.invalid'), payload('paid'),
                     payload(request_id='not-a-uuid')):
            before = deepcopy(self.db.values)
            with self.assertRaises((ValueError, PermissionError)):
                self.store.start(self.buyer['id'], self.item, data)
            self.assertEqual(self.db.values, before)
    def test_withdrawal_stops_new_threads_offers_and_invoices_but_preserves_history(self):
        thread = self.start()
        self.store.moderate(self.item, 'withdrawn', 2, 'admin')
        self.assertEqual(len(self.store.conversation(thread, self.buyer['id'])['messages']), 1)
        for operation in (lambda: self.store.start(self.other['id'], self.item, payload()),
                          lambda: self.store.send(thread, self.buyer['id'], payload('offer', amount='100')),
                          lambda: self.store.send(thread, self.seller['id'], payload('invoice', amount='100', url=PAYPAL))):
            with self.assertRaises(ValueError): operation()
        self.store.send(thread, self.buyer['id'], payload(text='Can we resolve my existing purchase?'))
    def test_blocks_prevent_both_directions_and_only_owner_can_unblock(self):
        thread = self.start()
        self.store.safety(thread, self.buyer['id'], 'block')
        self.store.safety(thread, self.seller['id'], 'unblock')
        with self.assertRaises(PermissionError):
            self.store.send(thread, self.seller['id'], payload())
        self.store.safety(thread, self.buyer['id'], 'unblock')
        self.store.send(thread, self.seller['id'], payload())
    def test_report_is_private_and_admin_can_record_review(self):
        thread = self.start()
        self.store.safety(thread, self.buyer['id'], 'report', 'Suspicious payment request')
        self.assertNotIn('Suspicious', json.dumps(self.store.conversation(thread, self.seller['id'])))
        self.assertEqual(self.store.admin_threads()[0]['report']['status'], 'new')
        self.store.resolve_report(thread, 'admin')
        self.assertEqual(self.store.admin_threads()[0]['report']['status'], 'reviewed')
    def test_cursor_has_no_duplicates_and_reads_are_bounded(self):
        thread = self.start()
        # More than one page, without bypassing production anti-abuse controls.
        with patch.object(self.store, '_rate'):
            for n in range(55): self.store.send(thread, self.buyer['id'], payload(text=str(n)))
        first = self.store.conversation(thread, self.seller['id'])
        self.assertEqual(len(first['messages']), 50)
        self.assertTrue(first['has_more'])
        last = self.store.conversation(thread, self.seller['id'], 50)
        self.assertEqual([m['seq'] for m in last['messages']], list(range(51, 57)))
        self.assertFalse(last['has_more'])
        for cursor in (-1, 1000001, '1'):
            with self.assertRaises(ValueError): self.store.conversation(thread, self.seller['id'], cursor)
    def test_persistent_rate_limit_rejects_flooding_without_losing_prior_messages(self):
        thread = self.start()
        for n in range(19): self.store.send(thread, self.buyer['id'], payload())
        with self.assertRaises(ValueError): self.store.send(thread, self.buyer['id'], payload())
        self.assertEqual(len(self.store.conversation(thread, self.buyer['id'])['messages']), 20)


class InvoiceValidationTests(unittest.TestCase):
    def test_invoice_url_rejects_spoofed_hosts_redirects_and_generic_payment_links(self):
        self.assertEqual(invoice_url(PAYPAL), PAYPAL)
        for link in ('https://paypal.com.attacker.invalid/invoice/p/#INV2-AB12-CD34-EF56-GH78',
                     'https://www.paypal.com@evil.invalid/invoice/p/', 'javascript:alert(1)',
                     PAYPAL.replace('https:', 'http:'), PAYPAL.replace('/p/', '/p/?redirect=https://evil.invalid'),
                     'https://paypal.me/someone/200', 'https://www.paypal.com/signin?returnUri=https://evil.invalid',
                     PAYPAL.replace('www.paypal.com', 'www.paypal.com:443'), PAYPAL + '\n',
                     'https://www.paypal.com/invoice/p/#anything'):
            with self.assertRaises(ValueError, msg=link): invoice_url(link)
    def test_amounts_are_finite_exact_cents_within_total_limit(self):
        self.assertEqual(amount('195.05'), 19505)
        self.assertEqual(amount('51000.00'), 5100000)
        for value in ('NaN', 'Infinity', '1e3', '-1', '0', '0.99', '100.001', '51000.01', '100000', True, None):
            with self.assertRaises(ValueError): amount(value)


class CustomerApiTests(Setup):
    def setUp(self):
        super().setUp()
        self.patches = [patch.object(customer_api, 'ChatStore', return_value=self.store),
                        patch('marketplace_accounts.Provider', return_value=self.provider),
                        patch.object(api, 'MarketplaceStore', return_value=self.store)]
        for item in self.patches: item.start()
        api._RATE.clear()
        self.client = TestClient(Starlette(routes=[Route(path, endpoint, methods=list(methods)) for path, endpoint, methods in api.ROUTES]), base_url=core.PUBLIC_ORIGIN)
        self.origin = {'Origin': core.PUBLIC_ORIGIN}
    def tearDown(self):
        self.client.close()
        for item in reversed(self.patches): item.stop()
    def login_cookie(self, bearer):
        self.client.cookies.set(COOKIE, bearer, domain='sports-cave-image-factory.onrender.com', path='/marketplace')
    def test_product_has_two_account_gated_actions_and_no_guest_message_form(self):
        response = self.client.get('/marketplace/item/' + self.item)
        self.assertIn('Message seller', response.text)
        self.assertIn('Make offer', response.text)
        self.assertNotIn('enquiry-form', response.text)
        for intent in ('message', 'offer'):
            response = self.client.get('/marketplace/contact/' + self.item + '?intent=' + intent, follow_redirects=False)
            self.assertEqual(response.status_code, 303)
            self.assertIn('/marketplace/signup?next=', response.headers['location'])
        for endpoint, data in (('/api/conversations', payload(listing_id=self.item)), ('/api/enquiries', {'listing_id': self.item, 'message': 'Can I buy?'})):
            self.assertEqual(self.client.post('/marketplace' + endpoint, json=data, headers=self.origin).status_code, 401)
    def test_signin_cookie_is_opaque_secure_http_only_and_not_an_os_cookie(self):
        response = self.client.post('/marketplace/api/auth/signin', json={'email': self.buyer['email'], 'password': SECRET, 'next': '//evil.invalid'}, headers=self.origin)
        self.assertEqual(response.status_code, 200, response.text)
        cookie = response.headers['set-cookie']
        for required in ('HttpOnly', 'Secure', 'SameSite=lax', 'Path=/marketplace'): self.assertIn(required, cookie)
        for forbidden in ('access_token', 'refresh_token', 'sports_cave_auth', SECRET): self.assertNotIn(forbidden, response.text + cookie)
        self.assertEqual(response.json()['redirect'], '/marketplace/inbox')
        self.assertIn('Verified email', self.client.get('/marketplace/account').text)

    def test_signup_preserves_the_item_and_offer_intent_after_email_confirmation(self):
        next_path = '/marketplace/contact/' + self.item + '?intent=offer'
        result = self.client.post('/marketplace/api/auth/signup', json={'email': self.buyer['email'],
            'password': SECRET, 'name': 'Buyer', 'consent': True, 'next': next_path}, headers=self.origin)
        self.assertEqual(result.status_code, 200, result.text)
        page = self.client.get('/marketplace/account/confirmed')
        self.assertIn('%3Fintent%3Doffer', page.text)
        self.assertIn(self.item, page.text)
        signin = self.client.get('/marketplace/signin')
        self.assertIn('value="' + next_path + '"', signin.text)
    def test_cross_site_or_missing_origin_mutations_fail_including_login_and_signout(self):
        self.login_cookie(self.bearer)
        for endpoint in ('/api/auth/signin', '/api/auth/signout', '/api/conversations'):
            for headers in ({}, {'Origin': 'https://attacker.invalid'}, {**self.origin, 'Sec-Fetch-Site': 'cross-site'}):
                self.assertEqual(self.client.post('/marketplace' + endpoint, json={}, headers=headers).status_code, 403)
    def test_complete_message_offer_invoice_flow_is_private_and_uncached(self):
        self.login_cookie(self.bearer)
        response = self.client.post('/marketplace/api/conversations', json=payload(listing_id=self.item), headers=self.origin)
        self.assertEqual(response.status_code, 201, response.text)
        thread = response.json()['id']
        route = '/marketplace/api/conversations/' + thread + '/messages'
        self.login_cookie(self.seller_bearer)
        result = self.client.post(route, json=payload('invoice', amount='195', url=PAYPAL), headers=self.origin)
        self.assertEqual(result.status_code, 201, result.text)
        self.login_cookie(self.bearer)
        for path in ('/marketplace/inbox/' + thread, route + '?after=0', '/marketplace/account'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.headers['cache-control'], 'no-store')
            self.assertEqual(response.headers['vary'], 'Cookie')
            self.assertIn('noindex', response.headers['x-robots-tag'])
            self.assertNotIn('seller@example.invalid', response.text)
        self.login_cookie(self.other_bearer)
        self.assertNotEqual(self.client.get(route).status_code, 200)
        self.assertNotIn(PAYPAL, self.client.get('/marketplace/inbox/' + thread).text)
    def test_messaging_identity_is_not_taken_from_posted_customer_fields(self):
        self.login_cookie(self.bearer)
        result = self.client.post('/marketplace/api/enquiries', json={'listing_id': self.item,
            'email': self.other['email'], 'name': 'Imposter', 'message': 'Question'}, headers=self.origin)
        self.assertEqual(result.status_code, 201, result.text)
        row = self.store.admin_threads()[0]
        self.assertEqual(row['buyer_id'], self.buyer['id'])
        self.assertEqual(row['buyer_name'], 'Buyer')
    def test_demo_is_noindex_has_no_offer_schema_and_cannot_be_created_as_real_listing(self):
        before = deepcopy(self.db.values)
        response = self.client.get('/marketplace/demo')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn('DEMO LISTING · NOT FOR SALE', response.text)
        self.assertIn('noindex', response.text)
        self.assertNotIn('"@type": "Offer"', response.text)
        self.assertNotIn('/marketplace/demo', self.client.get('/marketplace/sitemap.xml').text)
        self.assertEqual(self.db.values, before)
        self.login_cookie(self.bearer)
        self.assertIn('DEMO · NO MESSAGES OR PAYMENTS', self.client.get('/marketplace/contact/demo').text)
        response = self.client.post('/marketplace/api/conversations', json=payload(listing_id='demo'), headers=self.origin)
        self.assertEqual(response.status_code, 400)
    def test_rendered_messages_escape_html_and_paypal_links_are_external_isolated(self):
        raw = '<img src=x onerror=alert(1)>'
        row = {'kind': 'text', 'seq': 1, 'text': raw, 'sender': 'seller', 'created_at': core.now()}
        html = views.message(row, 'buyer')
        self.assertNotIn(raw, html)
        self.assertIn('&lt;img', html)
        invoice = dict(row, kind='invoice', url=PAYPAL, amount_cents=100, status='shared')
        self.assertIn('rel="noopener noreferrer"', views.message(invoice, 'buyer'))
    def test_private_pages_and_demo_are_absent_from_sitemap_and_assets_are_bounded(self):
        for asset in ('marketplace-accounts.css', 'marketplace-accounts.js', 'demo-jersey.svg', 'demo-detail.svg'):
            response = self.client.get('/marketplace/assets/' + asset)
            self.assertEqual(response.status_code, 200)
            self.assertLess(len(response.content), 18000)
        self.assertEqual(self.client.get('/marketplace/assets/marketplace_auth_public.json').status_code, 404)
        sitemap = self.client.get('/marketplace/sitemap.xml').text
        for path in ('/inbox', '/account', '/contact/', '/demo'): self.assertNotIn('/marketplace' + path, sitemap)


class ProviderContractTests(unittest.TestCase):
    def test_requests_use_publishable_key_bearer_timeout_and_no_redirects(self):
        transport = Mock()
        transport.request.return_value = Mock(status_code=200, content=b'{}', json=lambda: {})
        provider = Provider({'url': 'https://synthetic-project.supabase.co', 'key': 'sb_publishable_test'}, transport)
        provider.call('GET', 'user', token='synthetic-access')
        call = transport.request.call_args
        self.assertEqual(call.kwargs['headers']['apikey'], 'sb_publishable_test')
        self.assertEqual(call.kwargs['headers']['Authorization'], 'Bearer synthetic-access')
        self.assertFalse(call.kwargs['allow_redirects'])
        self.assertEqual(call.kwargs['timeout'], (5, 12))
    def test_unverified_provider_user_and_error_details_are_not_trusted(self):
        transport = Mock()
        transport.request.return_value = Mock(status_code=200, content=b'{}', json=lambda: {'id': str(uuid4()), 'email': 'fake@example.invalid'})
        provider = Provider({'url': 'https://synthetic-project.supabase.co', 'key': 'sb_publishable_test'}, transport)
        with self.assertRaises(SignInRequired): provider.user('token')
        transport.request.return_value.status_code = 400
        transport.request.return_value.json = lambda: {'error': 'sensitive provider detail'}
        with self.assertRaises(SignInRequired) as error: provider.call('POST', 'token')
        self.assertNotIn('sensitive', str(error.exception))


class ResendTests(unittest.TestCase):
    def test_reuses_existing_sender_and_matching_key_without_exposing_key(self):
        from marketplace_mail import smtp_plan, check_smtp
        env = {'RESEND_MARKETING_API_KEY': 'synthetic-marketing-key', 'RESEND_FROM_EMAIL': 'hello@example.invalid',
               'RESEND_API_KEY': 'synthetic-reporting-key', 'ACTIVITY_DIGEST_FROM': 'Reports <reports@example.invalid>'}
        connection = Mock()
        factory = Mock(return_value=connection)
        plan = check_smtp(env, factory)
        self.assertEqual(plan, smtp_plan(env))
        self.assertEqual(plan['sender_email'], 'hello@example.invalid')
        connection.login.assert_called_once_with('resend', 'synthetic-marketing-key')
        self.assertEqual(factory.call_args.args, ('smtp.resend.com', 465))
        self.assertTrue(factory.call_args.kwargs['context'].check_hostname)
        connection.sendmail.assert_not_called()
        connection.send_message.assert_not_called()
        connection.mail.assert_not_called()
        for secret in ('synthetic-marketing-key', 'synthetic-reporting-key'):
            self.assertNotIn(secret, json.dumps(plan))

    def test_reporting_fallback_keeps_sender_and_key_together(self):
        from marketplace_mail import smtp_plan
        plan = smtp_plan({'RESEND_FROM_EMAIL': 'marketing@example.invalid',
                          'RESEND_API_KEY': 'reporting-key', 'ACTIVITY_DIGEST_FROM': 'Reports <reports@example.invalid>'})
        self.assertEqual(plan['sender_email'], 'reports@example.invalid')
        self.assertEqual(plan['key_variable'], 'RESEND_API_KEY')

    def test_smtp_failures_are_redacted_and_missing_config_never_connects(self):
        from marketplace_mail import check_smtp
        factory = Mock()
        with self.assertRaises(ValueError): check_smtp({}, factory)
        factory.assert_not_called()
        factory.side_effect = smtplib.SMTPAuthenticationError(535, b'synthetic-secret-should-not-escape')
        with self.assertRaises(ValueError) as caught:
            check_smtp({'RESEND_API_KEY': 'key', 'ACTIVITY_DIGEST_FROM': 'a@example.invalid'}, factory)
        self.assertNotIn('synthetic-secret', str(caught.exception))


class OsCustomerControlsTests(Setup):
    def test_admin_can_prepare_invitation_and_block_customer_without_creating_staff(self):
        from streamlit.testing.v1 import AppTest
        import marketplace_chat
        with patch.object(marketplace_chat, 'ChatStore', return_value=self.store):
            page = AppTest.from_string("import streamlit as st\nfrom marketplace_accounts_page import render_accounts\nfrom marketplace_chat import ChatStore\nrender_accounts(st,ChatStore(),{'id':'synthetic-admin'})").run()
            self.assertFalse(page.exception)
            next(t for t in page.text_input if t.label == 'Customer display name').set_value('Invited buyer')
            next(t for t in page.text_input if t.label == 'Customer email').set_value('invited@example.invalid')
            next(b for b in page.button if b.label == 'Save invitation').click().run()
            self.assertFalse(page.exception)
            self.assertEqual(self.store.invitations()[0]['status'], 'awaiting signup')
            chosen = page.selectbox[0].value
            next(b for b in page.button if b.label == 'Block marketplace access').click().run()
            self.assertFalse(page.exception)
            row = next(r for r in self.store.accounts() if r['id'] == chosen)
            self.assertEqual(row['status'], 'blocked')
            self.assertNotIn('role', row)

    def test_report_and_latest_messages_are_reviewable_in_os(self):
        from streamlit.testing.v1 import AppTest
        import marketplace_chat
        thread = self.start()
        self.store.safety(thread, self.buyer['id'], 'report', 'Please review this conversation')
        with patch.object(marketplace_chat, 'ChatStore', return_value=self.store):
            page = AppTest.from_string("import streamlit as st\nfrom marketplace_accounts_page import render_conversations\nfrom marketplace_chat import ChatStore\nrender_conversations(st,ChatStore(),{'id':'synthetic-admin'})").run()
            self.assertFalse(page.exception)
            self.assertIn('Is the jersey still available?', [t.value for t in page.text])
            next(b for b in page.button if b.label == 'Mark report reviewed').click().run()
            self.assertFalse(page.exception)
            self.assertEqual(self.store.admin_threads()[0]['report']['status'], 'reviewed')
