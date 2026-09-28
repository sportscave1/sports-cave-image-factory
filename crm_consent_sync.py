"""Future opt-out reconciliation contract. No Shopify write client is wired in V1."""


def reconcile_opt_out(store,recipient_hash,writer=None,*,approved=False):
    """Mockable future adapter. Suppression survives every failure and never clears.

    A future approved worker supplies a narrowly scoped unsubscribe-only writer.
    No caller, page or scheduler invokes this function in V1.
    """
    if approved is not True or writer is None:return 'NOT_ACTIVATED'
    row=store.q('SELECT * FROM crm_suppressions WHERE recipient_hash=%s AND active=true',(recipient_hash,),True)
    if not row:return 'NO_ACTIVE_SUPPRESSION'
    if row['shopify_sync_state']=='SYNCED':return 'SYNCED'
    store.q("UPDATE crm_suppressions SET shopify_sync_attempts=shopify_sync_attempts+1,shopify_sync_checked_at=now() WHERE recipient_hash=%s",(recipient_hash,))
    try:
        acknowledged=writer.unsubscribe_only(customer_id=row.get('shopify_customer_id'),email=row.get('email_for_provider'))
        if acknowledged is not True:raise ValueError('Opt-out not acknowledged.')
    except Exception:
        store.q("UPDATE crm_suppressions SET shopify_sync_state='PENDING',shopify_sync_error='writer_unavailable' WHERE recipient_hash=%s",(recipient_hash,))
        return 'PENDING'
    store.q("UPDATE crm_suppressions SET shopify_sync_state='SYNCED',shopify_sync_error=NULL WHERE recipient_hash=%s",(recipient_hash,))
    return 'SYNCED'
