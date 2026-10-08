"""Wall Inbox events and per-user receipts in the existing OS notification stores."""
import hashlib
import json
import uuid

import os_accounts
import social_media
from wall_preview_crm_store import transaction

EVENT = 'wall_inbox_image_received'


def record(cur, preview_id):
    """Called inside a successful NEW capture transaction, never by a poll/backfill."""
    identity = str(uuid.UUID(str(preview_id)))
    cur.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', ('wall-notification:'+identity,))
    payload = {'action_type': EVENT, 'page': social_media.WALL_PREVIEW_ROUTE,
               'message': 'New image received in Wall Inbox.'}
    cur.execute('''INSERT INTO audit_logs(event_type,entity_type,entity_id,new_value,reason,actor,source)
        SELECT %s,'wall_preview_notification',%s,%s::jsonb,%s,'sports_cave_os',%s
        WHERE NOT EXISTS (SELECT 1 FROM audit_logs WHERE event_type=%s AND entity_id=%s)''',
        (EVENT, identity, json.dumps(payload), payload['message'], social_media.WALL_PREVIEW_ROUTE, EVENT, identity))


def _prefix(user_id):
    if not str(user_id or '').strip():
        raise PermissionError('Sign in to view Wall Inbox notifications.')
    return 'wall_inbox_seen_v1:'+hashlib.sha256(str(user_id).encode()).hexdigest()+':'


def status(claims, *, count_only=False):
    if social_media.WALL_PREVIEW_ROUTE not in set(claims.get('allowed_routes') or ()):
        return {'unread_count': 0, 'notifications': []}
    prefix = _prefix(claims.get('sub'))
    with transaction() as cur:
        select = 'count(*) AS unread_count' if count_only else 'p.id,p.product_title,a.created_at,count(*) OVER() AS unread_count'
        tail = '' if count_only else ' ORDER BY a.created_at DESC,p.id DESC LIMIT 10'
        cur.execute('SELECT '+select+'''
            FROM audit_logs a JOIN public.wall_previews p ON a.entity_id=p.id::text
            WHERE a.event_type=%s AND a.entity_type='wall_preview_notification'
              AND NOT (p.attribution ? 'inbox_deleted_at' OR p.attribution ? 'inbox_deletion')
              AND (%s OR p.marketing_permission)
              AND NOT EXISTS (SELECT 1 FROM app_sync_state s WHERE s.key=%s || p.id::text)
            '''+tail,
            (EVENT, os_accounts.is_admin(claims), prefix))
        rows = [dict(row) for row in cur.fetchall()]
    return {'unread_count': int(rows[0]['unread_count']) if rows else 0,
            'notifications': [] if count_only else [{'title': 'New image received in Wall Inbox.',
                'subtitle': row['product_title'] or 'Wall Preview Inbox',
                'route_key': social_media.WALL_PREVIEW_PAGE_KEY, 'wall_preview_id': str(row['id']),
                'created_at': str(row['created_at'])} for row in rows]}


def mark_seen(preview_id, user):
    """Only the authenticated viewer calls this after its image load acknowledgement."""
    if not os_accounts.can_access_page(user, social_media.WALL_PREVIEW_ROUTE):
        raise PermissionError('Wall Inbox access is not approved.')
    identity = str(uuid.UUID(str(preview_id)))
    key = _prefix(user.get('id'))+identity
    with transaction() as cur:
        cur.execute('''INSERT INTO app_sync_state(key,value,cursor_value,status,updated_at)
            SELECT %s,'{"seen":true}'::jsonb,%s,'ready',now()
            FROM public.wall_previews p WHERE p.id=%s AND (%s OR p.marketing_permission)
              AND NOT (p.attribution ? 'inbox_deleted_at' OR p.attribution ? 'inbox_deletion')
              AND EXISTS (SELECT 1 FROM audit_logs WHERE event_type=%s AND entity_id=p.id::text)
            ON CONFLICT(key) DO NOTHING''', (key, identity, identity, os_accounts.is_admin(user), EVENT))
