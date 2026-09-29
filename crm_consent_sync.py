"""Durable opt-out reconciliation; never subscribes or clears local suppression."""
import logging


def reconcile_opt_out(store,recipient_hash,writer=None,*,approved=False):
    if approved is not True:return 'NOT_ACTIVATED'
    # Atomic claim is also a five-minute retry backoff/crash lease. Concurrent
    # clicks/workers cannot race the external write. A crashed claim expires.
    row=store.q("""UPDATE crm_suppressions SET shopify_sync_attempts=shopify_sync_attempts+1,
        shopify_sync_checked_at=now() WHERE recipient_hash=%s AND active=true
        AND shopify_sync_state<>'SYNCED'
        AND (shopify_sync_checked_at IS NULL OR shopify_sync_checked_at<now()-interval '5 minutes')
        RETURNING *""",(recipient_hash,),True)
    if not row:
        current=store.q('SELECT shopify_sync_state FROM crm_suppressions WHERE recipient_hash=%s AND active=true',(recipient_hash,),True)
        return current['shopify_sync_state'] if current else 'NO_ACTIVE_SUPPRESSION'
    try:
        if writer is None:
            from crm_shopify import Shopify
            writer=Shopify()
        if writer.unsubscribe_only(customer_id=row.get('shopify_customer_id'),email=None) is not True:
            raise ValueError('Opt-out not acknowledged.')
    except Exception as exc:
        logging.getLogger(__name__).warning('crm_opt_out_sync_pending type=%s',type(exc).__name__)
        store.q("UPDATE crm_suppressions SET shopify_sync_state='PENDING',shopify_sync_error='writer_unavailable' WHERE recipient_hash=%s",(recipient_hash,))
        return 'PENDING'
    store.q("UPDATE crm_suppressions SET shopify_sync_state='SYNCED',shopify_sync_error=NULL WHERE recipient_hash=%s",(recipient_hash,))
    return 'SYNCED'


def reconcile_pending(store,writer=None):
    rows=store.q("""SELECT recipient_hash FROM crm_suppressions WHERE active=true
        AND reason IN ('unsubscribe','manual_unsubscribe','provider_unsubscribe')
        AND shopify_sync_state<>'SYNCED' AND shopify_customer_id IS NOT NULL
        AND (shopify_sync_checked_at IS NULL OR shopify_sync_checked_at<now()-interval '5 minutes')
        ORDER BY shopify_sync_checked_at NULLS FIRST LIMIT 5""")
    for row in rows:reconcile_opt_out(store,row['recipient_hash'],writer,approved=True)
