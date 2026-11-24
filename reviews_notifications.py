"""Small per-account unread counts; receipt batches only after review rows load."""
import hashlib
import time
import uuid

from reviews_store import ReviewsStore, require


def scope(actor):
    if not str(actor or '').strip():raise PermissionError('Sign in to view review notifications.')
    return hashlib.sha256(('review-notifications:'+str(actor)).encode()).hexdigest()[:24]


def status(claims, store=None):
    if 'Reviews' not in set(claims.get('allowed_routes') or ()):
        return {'unread_count':0,'checked_at':time.time()}
    actor=str(claims.get('sub') or '');scope(actor)
    store=store or ReviewsStore()
    row=store.q("""SELECT count(*) FILTER (WHERE NOT EXISTS(
      SELECT 1 FROM sc_review_seen s WHERE s.actor_id=%s AND s.review_id=r.id)) AS count,
      max(notification_received_at) AS latest_arrival FROM sc_reviews r
      WHERE r.notification_received_at IS NOT NULL AND r.status IN ('PENDING','PUBLISHED')
      """,(actor,),one=True)
    return {'unread_count':int(row['count']),'checked_at':time.time(),'latest_arrival':str(row.get('latest_arrival') or '')}


def mark_visible(user, identities, store=None):
    require(user);actor=str(user.get('id') or '');actor_scope=scope(actor)
    ids=list(dict.fromkeys(str(uuid.UUID(str(value))) for value in identities))
    if len(ids)>25:raise ValueError('Acknowledge only the displayed page of reviews.')
    store=store or ReviewsStore()
    with store.db() as conn:
        row=conn.execute("""WITH marked AS (
          INSERT INTO sc_review_seen(actor_id,review_id)
          SELECT %s,r.id FROM sc_reviews r WHERE r.id=ANY(%s::uuid[])
          AND r.notification_received_at IS NOT NULL AND r.status IN ('PENDING','PUBLISHED')
          ON CONFLICT DO NOTHING RETURNING 1) SELECT count(*) AS marked FROM marked""",(actor,ids)).fetchone()
    return {**status({'sub':actor,'allowed_routes':['Reviews']},store),
      'marked':int(row['marked']),'scope':actor_scope}
