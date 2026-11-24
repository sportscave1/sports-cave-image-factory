"""Public photo reuse: bounded cost, exact bytes, fresh access and failure recovery."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import threading
import time
import unittest
from unittest.mock import patch

from marketplace_photo_cache import PhotoCache
from tests.test_marketplace import memory_store, sample, photograph
import marketplace as core
from marketplace_store import MarketplaceStore


def reference(data=b'photo', revision='01', identifier='id:photo'):
    return dict(provider='dropbox', id=identifier, rev=revision, size=len(data), sha256=hashlib.sha256(data).hexdigest())


class CacheTests(unittest.TestCase):
    def test_receipt_and_listing_scope_prevent_stale_or_cross_listing_reuse(self):
        cache = PhotoCache()
        calls = []
        def read(key, ref, data):
            return cache.read(key, 0, ref, lambda: calls.append(ref) or data)
        self.assertEqual(read('one', reference(), b'photo'), b'photo')
        self.assertEqual(read('one', reference(), b'photo'), b'photo')
        self.assertEqual(len(calls), 1)
        read('two', reference(), b'photo')
        read('one', reference(b'new', '02'), b'new')
        read('one', reference(b'other', '02'), b'other')
        self.assertEqual(len(calls), 4)

    def test_invalid_receipts_and_corrupt_bytes_never_enter_cache(self):
        cache = PhotoCache()
        for ref in [dict(reference(), provider='other'), dict(reference(), size=450001), dict(reference(), rev='bad!')]:
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                cache.read('one', 0, ref, lambda: b'photo')
        for data in [b'wrong', b'truncated', 'photo']:
            with self.subTest(data=data), self.assertRaises(RuntimeError):
                cache.read('one', 0, reference(), lambda: data)
        self.assertEqual(cache._bytes, 0)
        self.assertEqual(cache._inflight, {})
        self.assertEqual(cache.read('one', 0, reference(), lambda: b'photo'), b'photo')

    def test_lru_bytes_entries_and_oversized_load_are_bounded(self):
        cache = PhotoCache(max_bytes=10, max_entries=2)
        for key in ['one', 'two', 'one', 'three']:
            cache.read(key, 0, reference(), lambda: b'photo')
        self.assertEqual([key[0] for key in cache._values], ['one', 'three'])
        self.assertEqual(cache._bytes, 10)
        cache.read('large', 0, reference(b'x'*11), lambda: b'x'*11)
        self.assertEqual(cache._bytes, 10)
        self.assertEqual(len(cache._values), 2)
        cache.clear()
        self.assertEqual(cache._bytes, 0)
        self.assertEqual(len(cache._values), 0)

    def test_concurrent_identical_loads_coalesce_and_distinct_loads_are_bounded(self):
        cache = PhotoCache(max_inflight=2)
        count, active, peak = 0, 0, 0
        mutex = threading.Lock()
        start = threading.Barrier(8)
        def load():
            nonlocal count, active, peak
            with mutex:
                count += 1
                active += 1
                peak = max(peak, active)
            time.sleep(.02)
            with mutex:
                active -= 1
            return b'photo'
        def read(key):
            start.wait(timeout=2)
            return cache.read(key, 0, reference(), load)
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(list(pool.map(read, ['same']*8)), [b'photo']*8)
        self.assertEqual(count, 1)
        start = threading.Barrier(8)
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(list(pool.map(read, [str(i) for i in range(8)])), [b'photo']*8)
        self.assertLessEqual(peak, 2)
        self.assertEqual(cache._inflight, {})

    def test_failed_owner_releases_slot_and_retry_works(self):
        cache = PhotoCache(max_inflight=1)
        def broken():
            raise OSError('synthetic provider failure')
        with self.assertRaises(OSError):
            cache.read('one', 0, reference(), broken)
        self.assertEqual(cache._inflight, {})
        self.assertEqual(cache.read('one', 0, reference(), lambda: b'photo'), b'photo')

    def test_failed_shared_download_releases_all_waiters_for_retry(self):
        cache = PhotoCache(max_inflight=1)
        entered, release = threading.Event(), threading.Event()
        def broken():
            entered.set()
            self.assertTrue(release.wait(timeout=2))
            raise OSError('synthetic timeout')
        with ThreadPoolExecutor(max_workers=4) as pool:
            owner = pool.submit(cache.read, 'one', 0, reference(), broken)
            self.assertTrue(entered.wait(timeout=2))
            others = [pool.submit(cache.read, 'one', 0, reference(), broken) for _ in range(3)]
            release.set()
            for future in [owner, *others]:
                with self.assertRaises(OSError):
                    future.result(timeout=2)
        self.assertEqual(cache._inflight, {})
        self.assertEqual(cache.read('one', 0, reference(), lambda: b'photo'), b'photo')

    def test_waiter_timeout_does_not_cancel_owner_and_full_admission_is_bounded(self):
        cache = PhotoCache(max_inflight=1, wait_seconds=.03)
        entered, release = threading.Event(), threading.Event()
        def held():
            entered.set()
            self.assertTrue(release.wait(timeout=2))
            return b'photo'
        with ThreadPoolExecutor(max_workers=1) as pool:
            owner = pool.submit(cache.read, 'one', 0, reference(), held)
            self.assertTrue(entered.wait(timeout=2))
            try:
                with self.assertRaises(TimeoutError):
                    cache.read('one', 0, reference(), lambda: b'photo')
                with self.assertRaises(TimeoutError):
                    cache.read('two', 0, reference(), lambda: b'photo')
                self.assertFalse(owner.done())
            finally:
                release.set()
            self.assertEqual(owner.result(timeout=2), b'photo')
        self.assertEqual(cache.read('one', 0, reference(), lambda: self.fail('must reuse')), b'photo')

    def test_public_reuse_preserves_private_moderation_and_live_approval(self):
        cache = PhotoCache()
        store = memory_store()
        key = store.submit(core.submission(sample()), core.prepare_photos([photograph(), photograph()]))['id']
        store.moderate(key, 'published', 1, 'synthetic-admin')
        with patch('marketplace_photo_cache.PHOTOS', cache), patch.object(store.media_storage, 'read', wraps=store.media_storage.read) as read:
            first = store.photo(key, 0)
            self.assertEqual(store.photo(key, 0), first)
            self.assertEqual(read.call_count, 1)
            self.assertEqual(store.photo(key, 0, public=False), first)
            self.assertEqual(read.call_count, 2)
            store.moderate(key, 'withdrawn', 2, 'synthetic-admin')
            self.assertIsNone(store.photo(key, 0))
            self.assertEqual(store.photo(key, 0, public=False), first)

    def test_default_public_reads_use_existing_pool_and_private_reads_use_transactions(self):
        fixture = memory_store()
        key = fixture.submit(core.submission(sample()), core.prepare_photos([photograph(), photograph()]))['id']
        fixture.moderate(key, 'published', 1, 'synthetic-admin')
        store = MarketplaceStore(media_storage=fixture.media_storage)
        with patch('supabase_backend.read_connection', side_effect=fixture.db) as pooled, \
             patch('supabase_backend.connect', side_effect=fixture.connect) as transactional, \
             patch('marketplace_photo_cache.PHOTOS', PhotoCache()):
            self.assertIsNotNone(store.listing(key, public=True))
            self.assertEqual(len(store.listings(public=True)), 1)
            first = store.photo(key, 0)
            self.assertEqual(store.photo(key, 0), first)
            self.assertEqual(pooled.call_count, 4)
            transactional.assert_not_called()
            self.assertIsNotNone(store.listing(key))
            self.assertEqual(store.photo(key, 0, public=False), first)
            self.assertEqual(transactional.call_count, 2)
            fixture.moderate(key, 'withdrawn', 2, 'synthetic-admin')
            self.assertIsNone(store.photo(key, 0))
            self.assertIsNone(store.listing(key, public=True))
            self.assertEqual(store.listings(public=True), [])

    def test_public_pool_failure_never_falls_back_to_cached_approval(self):
        store = MarketplaceStore()
        with patch('supabase_backend.read_connection', side_effect=TimeoutError('synthetic pool timeout')):
            with self.assertRaises(TimeoutError):
                store.listings(public=True)


if __name__ == '__main__':
    unittest.main()
