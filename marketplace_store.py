"""Marketplace records in the existing private OS runtime-state table.

No migrations, application startup, credentials or network calls at import time.
Every write is transaction-scoped; photographs and contact details stay private.
"""
from copy import deepcopy
import json
from uuid import uuid4

from crm_store import Store
from marketplace import now, identifier, public_listing

PREFIX = 'marketplace:v1:'


def read(conn, name, default=None):
    row = conn.execute('SELECT value FROM crm_runtime_state WHERE key=%s', (PREFIX + name,)).fetchone()
    return deepcopy(row['value']) if row else deepcopy(default)


def put(conn, name, value):
    conn.execute('''INSERT INTO crm_runtime_state(key,value) VALUES(%s,%s::jsonb)
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=now()''',
                 (PREFIX + name, json.dumps(value)))


def lock(conn, name):
    conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', (PREFIX + name,))


class MarketplaceStore(Store):
    def listing(self, listing_id, *, public=False):
        with self.db() as conn:
            row = read(conn, 'listing:' + identifier(listing_id))
        if row is None or public and row.get('status') != 'published':
            return None
        return public_listing(row) if public else row

    def listings(self, *, public=False):
        query = "SELECT value FROM crm_runtime_state WHERE key LIKE %s"
        if public:
            query += " AND value->>'status'='published'"
        query += ' ORDER BY updated_at DESC LIMIT 600'
        with self.db() as conn:
            rows = [r['value'] for r in conn.execute(query, (PREFIX + 'listing:%',)).fetchall()]
        return [public_listing(row) for row in rows] if public else rows

    def submit(self, row, photos, video=None, video_storage=None):
        listing_id = str(uuid4())
        metadata = None
        if video:
            from marketplace_media import VideoStorage
            video_storage = video_storage or VideoStorage()
            metadata = video_storage.save(listing_id, video)
        record = {**row, 'id': listing_id, 'status': 'pending', 'revision': 1,
                  'photo_count': len(photos), 'submitted_at': now(), 'history': [],
                  'has_video': bool(metadata), 'video_seconds': metadata['seconds'] if metadata else 0}
        if metadata:
            record['video'] = metadata
        try:
            with self.db() as conn:
                # One transaction includes all photographs and the private video reference.
                put(conn, 'listing:' + listing_id, record)
                for index, data in enumerate(photos):
                    put(conn, f'image:{listing_id}:{index}', {'webp': data})
        except Exception:
            if metadata:
                try:
                    # A failed commit acknowledgement must not delete a committed object's video.
                    if self.listing(listing_id) is None:
                        video_storage.discard(listing_id, metadata)
                except Exception:
                    pass  # Leave an unreferenced private object rather than risk a valid listing.
            raise
        return {'id': listing_id, 'status': 'pending'}

    def video(self, listing_id, *, public=True):
        row = self.listing(listing_id)
        if not row or public and row.get('status') != 'published':
            return None
        return deepcopy(row.get('video'))

    def photo(self, listing_id, index, *, public=True):
        listing_id = identifier(listing_id)
        if not isinstance(index, int) or not 0 <= index < 4:
            return None
        with self.db() as conn:
            row = read(conn, 'listing:' + listing_id)
            if not row or public and row.get('status') != 'published' or index >= row['photo_count']:
                return None
            image = read(conn, f'image:{listing_id}:{index}')
        return image['webp'] if image else None

    def moderate(self, listing_id, action, revision, actor):
        if action not in ('published', 'declined', 'withdrawn'):
            raise ValueError('Choose publish, decline or withdraw.')
        listing_id = identifier(listing_id)
        with self.db() as conn:
            lock(conn, 'listing:' + listing_id)
            row = read(conn, 'listing:' + listing_id)
            if not row or row['revision'] != revision:
                raise ValueError('This item changed. Reload the review queue.')
            if action == 'published' and row['status'] not in ('pending', 'withdrawn'):
                raise ValueError('Only a pending or withdrawn item can be published.')
            if action == 'published' and (row.get('photo_count', 0) < 2 or not row.get('seller_email')):
                raise ValueError('Review the item photographs and seller details before publishing.')
            row['history'].append({'from': row['status'], 'to': action, 'at': now(), 'actor': str(actor)})
            row.update(status=action, revision=revision + 1)
            if action == 'published':
                row['published_at'] = now()
            put(conn, 'listing:' + listing_id, row)
        return row

    def enquire(self, listing_id, name, address, message):
        listing_id = identifier(listing_id)
        with self.db() as conn:
            lock(conn, 'listing:' + listing_id)
            row = read(conn, 'listing:' + listing_id)
            if not row or row['status'] != 'published':
                raise ValueError('This item is no longer available for enquiries.')
            enquiry_id = str(uuid4())
            put(conn, 'enquiry:' + enquiry_id, {'id': enquiry_id, 'listing_id': listing_id,
                'item_title': row['title'], 'name': name, 'email': address, 'message': message,
                'created_at': now(), 'status': 'new'})
        return enquiry_id

    def enquiries(self):
        with self.db() as conn:
            return [r['value'] for r in conn.execute('''SELECT value FROM crm_runtime_state
                WHERE key LIKE %s ORDER BY updated_at DESC LIMIT 300''', (PREFIX + 'enquiry:%',)).fetchall()]

    def resolve_enquiry(self, enquiry_id):
        with self.db() as conn:
            key = 'enquiry:' + identifier(enquiry_id)
            lock(conn, key)
            row = read(conn, key)
            if row:
                put(conn, key, {**row, 'status': 'handled', 'handled_at': now()})

    def draft(self, deployed):
        with self.db() as conn:
            return read(conn, 'site-draft', {'revision': 0, 'base': deployed, 'config': deployed})

    def save_draft(self, config, base, revision):
        with self.db() as conn:
            lock(conn, 'site-draft')
            previous = read(conn, 'site-draft', {'revision': 0})
            if previous['revision'] != revision:
                raise ValueError('Another editor saved this website. Reload before saving.')
            if previous.get('attempt'):
                raise ValueError('Reconcile the interrupted publication before editing this draft.')
            row = {'revision': revision + 1, 'base': base, 'config': config}
            put(conn, 'site-draft', row)
        return row

    def begin_publish(self, revision):
        with self.db() as conn:
            lock(conn, 'site-draft')
            draft = read(conn, 'site-draft')
            if not draft or draft['revision'] != revision:
                raise ValueError('This draft changed. Reload before publishing.')
            if not draft.get('attempt'):
                draft['attempt'] = {'release_id': str(uuid4())}
                put(conn, 'site-draft', draft)
            return {**draft, **draft['attempt']}

    def cancel_publish(self, release_id):
        with self.db() as conn:
            lock(conn, 'site-draft')
            draft = read(conn, 'site-draft')
            if draft and draft.get('attempt', {}).get('release_id') == release_id:
                draft.pop('attempt')
                put(conn, 'site-draft', draft)

    def receipt(self, result=None):
        with self.db() as conn:
            if result is not None:
                put(conn, 'release', result)
                lock(conn, 'site-draft')
                draft = read(conn, 'site-draft')
                if draft and draft.get('attempt', {}).get('release_id') == result['release_id']:
                    draft.pop('attempt')
                    put(conn, 'site-draft', draft)
            return read(conn, 'release')
