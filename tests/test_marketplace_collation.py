"""Offline regressions for the punctuation ordering observed in live Postgres."""
from unittest.mock import patch

from marketplace_accounts import digest, prune_expired
from marketplace_notifications import NotificationStore
from marketplace_store import PREFIX, put
from tests.test_marketplace_accounts import Setup, SECRET, payload


def linguistic_key(value):
    # A primary text weight ignores punctuation. In particular a trailing '~'
    # does not sort after a UUID, unlike Python/SQLite's default byte ordering.
    return (''.join(c for c in value if c.isalnum()), value)


class CollationTests(Setup):
    def setUp(self):
        super().setUp()
        self.db.collation = linguistic_key

    def test_accounts_exclude_email_mapping_records_in_the_same_index_range(self):
        self.assertEqual({r['id'] for r in self.store.accounts()},
                         {self.buyer['id'], self.seller['id'], self.other['id']})
        self.assertTrue(all('email' in row for row in self.store.accounts()))

    def test_chat_lists_and_messages_survive_linguistic_order_without_foreign_threads(self):
        thread = self.start()
        self.store.send(thread, self.seller['id'], payload(text='Demo reply'))
        other_thread = self.store.start(self.other['id'], self.item, payload())['id']
        self.assertEqual([t['id'] for t in self.store.admin_threads()].count(thread), 1)
        self.assertEqual([t['id'] for t in self.store.inbox(self.buyer['id'])], [thread])
        self.assertEqual([t['id'] for t in self.store.inbox(self.other['id'])], [other_thread])
        self.assertEqual([m['seq'] for m in self.store.conversation(thread, self.buyer['id'])['messages']], [1, 2])
        self.assertEqual([m['seq'] for m in self.store.conversation(thread, self.buyer['id'], after=1)['messages']], [2])

    def test_guest_seller_claim_uses_only_the_matching_verified_email(self):
        with self.store.db() as conn:
            listing = self.db.values[PREFIX + 'listing:' + self.item]
            listing['seller_email'] = 'not-joined@example.invalid'
            listing.pop('seller_user_id', None)
            put(conn, 'listing:' + self.item, listing)
        thread = self.start()
        guest = self.provider.add('not-joined@example.invalid', 'Guest seller')
        self.accounts.signin(guest['email'], SECRET)
        self.assertEqual([t['id'] for t in self.store.inbox(guest['id'])], [thread])
        self.assertEqual(self.store.inbox(self.other['id']), [])

    def test_expired_session_cleanup_keeps_active_sessions_and_other_namespaces(self):
        expired = PREFIX + 'session:' + digest('expired synthetic session')
        recovery = PREFIX + 'recovery:' + digest('expired synthetic recovery')
        self.db.values[expired] = {'expires': 0}
        self.db.values[recovery] = {'expires': 0}
        with self.store.db() as conn:
            prune_expired(conn, 'session:')
        self.assertNotIn(expired, self.db.values)
        self.assertIn(recovery, self.db.values)
        self.assertEqual(self.accounts.authenticate(self.bearer)['id'], self.buyer['id'])

    def test_notification_is_due_at_its_timestamp_under_linguistic_order(self):
        with patch('marketplace_notifications.time.time', return_value=1000):
            thread = self.start()
        queue = NotificationStore(self.db.connect, clock=lambda: 1012)
        self.assertEqual([r['thread_id'] for r in queue.due()], [thread])
