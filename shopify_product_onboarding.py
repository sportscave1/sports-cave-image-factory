"""Server-side consumers of existing product receipts and edition registration.

No allocator, companion dependency or schema side effects. All Shopify reads are
current; receipts and scan continuation live in the existing database ledger.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import time
import uuid

LOG = logging.getLogger(__name__)
CHECKPOINT = 'edition-product-onboarding-checkpoint'
REVISION = 'edition-product-onboarding-revision'
LEASE = "edition-product-onboarding-lease"

PRODUCT_PAGE = '''query EditionUpdatedProducts($first:Int!, $after:String, $query:String!) {
  products(first:$first, after:$after, query:$query, sortKey:UPDATED_AT) {
    nodes { id updatedAt }
    pageInfo { hasNextPage endCursor }
  }
}'''
ORDER_HISTORY = '''query EditionProductHistory($after:String, $query:String!) {
  orders(first:100, after:$after, query:$query, sortKey:CREATED_AT) {
    nodes { id lineItems(first:250) { nodes { product { id } } pageInfo { hasNextPage } } }
    pageInfo { hasNextPage endCursor }
  }
}'''


class PendingRegistration(RuntimeError):
    """Durable review/metadata wait, distinct from a transient job failure."""


def now():
    return datetime.now(timezone.utc)


def verify_new_product(product, config=None):
    """Only new identities need a verified limit and complete order history.

    Registration repeats local history/identity checks inside its transaction.
    A racing first order uses the existing allocator and database uniqueness.
    """
    import supabase_backend as db
    import shopify_sync as shopify
    from product_upload_mapping import edition_limit
    pid = product['shopify_product_id']
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT id FROM edition_products WHERE shopify_product_gid=%s OR shopify_product_id=ANY(%s)',
                    (pid, [pid, pid.rsplit('/', 1)[-1]]))
        if cur.fetchone():
            return product
        cur.execute('SELECT shopify_product_id FROM shopify_products WHERE handle=%s', (product.get('handle'),))
        cached = cur.fetchone()
        if cached and str(cached['shopify_product_id']) not in (pid, pid.rsplit('/', 1)[-1]):
            raise PendingRegistration(
                f"Catalogue handle belongs to another Shopify product ({cached['shopify_product_id']}); "
                "reconcile the previous identity/history before onboarding. No counters changed.")
    try:
        total = edition_limit(product)
    except ValueError as exc:
        raise PendingRegistration(str(exc)) from exc
    if total is None:
        raise PendingRegistration('Product registration pending: verified edition limit is missing.')
    warning = shopify.edition_registration_history_warning(product, confirmed_total=total)
    if warning:
        raise PendingRegistration(warning)
    created = str(product.get('created_at') or '')
    try:
        created_time = datetime.fromisoformat(created.replace('Z', '+00:00'))
        if created_time.tzinfo is None or created_time > now():
            raise ValueError()
    except ValueError:
        raise PendingRegistration('Product creation time unavailable; order history cannot be verified.') from None
    # Shopify normally exposes only 60 days of orders. Never mistake a truncated
    # historical window for proof of zero sales.
    if created_time < now() - timedelta(days=59):
        scopes, _ = shopify.graphql_request('{ currentAppInstallation { accessScopes { handle } } }', config=config)
        if 'read_all_orders' not in {s['handle'] for s in scopes['currentAppInstallation']['accessScopes']}:
            raise PendingRegistration('Older product requires complete order-history access or manual reconciliation.')
    after = None
    for _ in range(100):
        data, _ = shopify.graphql_request(ORDER_HISTORY, variables={'after': after, 'query': f"created_at:>='{created}'"}, config=config)
        connection = data.get('orders')
        if not isinstance(connection, dict) or 'nodes' not in connection or 'pageInfo' not in connection:
            raise RuntimeError('Order history unavailable; initialization refused.')
        for order in connection['nodes']:
            lines = order.get('lineItems') or {}
            if 'nodes' not in lines or (lines.get('pageInfo') or {}).get('hasNextPage', True):
                raise PendingRegistration('Order line history is incomplete; reconciliation required.')
            if any((line.get('product') or {}).get('id') == pid for line in lines['nodes']):
                raise PendingRegistration('Existing Shopify order history; automatic initialization refused.')
        page = connection['pageInfo']
        if page.get('hasNextPage') is False:
            return dict(product, _onboarding_verified=True, _onboarding_total=total)
        cursor = page.get('endCursor')
        if not cursor or cursor == after:
            raise PendingRegistration('Order history pagination incomplete.')
        after = cursor
    raise PendingRegistration('Order history exceeds bounded verification; reconciliation required.')


def process_receipt(row, db, config=None):
    payload = row['payload']
    if isinstance(payload, str):
        payload = json.loads(payload)
    try:
        result = db.process_product_create_webhook(payload, row['webhook_id'], row['topic'], claim_event=False, config=config)
    except PendingRegistration as exc:
        db._update_webhook_event_status(row['webhook_id'], 'pending', error_message=str(exc))
        return {'status': 'pending', 'reason': str(exc)}
    if result.get('errors'):
        message = '; '.join(result['errors'])
        # Classification warnings need metadata/review, not a stalled scan.
        if all(error.startswith('Sport classification review required:') for error in result['errors']):
            db._update_webhook_event_status(row['webhook_id'], 'pending', error_message=message)
            return dict(result, status='pending')
        db._update_webhook_event_status(row['webhook_id'], 'failed', error_message=message)
        raise RuntimeError(message)
    decisions = result.get('eligibility_results') or []
    # Drafts, absent classification and late metadata remain durable pending work.
    pending = result.get('action') == 'skipped' or any(not d.get('eligible') for d in decisions)
    if pending:
        db._update_webhook_event_status(row['webhook_id'], 'pending', error_message=result.get('reason') or '; '.join(d.get('reason', '') for d in decisions))
    if result.get('new_products_inserted') or result.get('existing_products_updated'):
        db.set_app_setting(REVISION, now().isoformat(), ensure_schema_first=False)
    return result


def drain(db, config=None, limit=10, renew=None):
    """Caller holds a durable expiring lease, compatible with transaction pools.

    Existing failed/processing receipts survive restart. Use the edition mirror
    retry schedule (30s exponential, capped at one hour), without a retry cutoff.
    """
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT webhook_id,topic,payload FROM webhook_events
            WHERE lower(replace(topic,'_','/')) IN ('products/create','products/update')
              AND status IN ('received','processing','failed','retry','pending')
              AND (processed_at IS NULL OR processed_at <= now() -
                   least(3600,30*power(2,least(COALESCE((payload->>'_onboarding_attempts')::int,0),7))) * interval '1 second')
            ORDER BY COALESCE(processed_at,received_at),webhook_id LIMIT %s""", (limit,))
        rows = list(cur.fetchall())
    for row in rows:
        if renew:
            renew()
        try:
            process_receipt(row, db, config)
        except Exception as exc:
            db._update_webhook_event_status(row['webhook_id'], 'failed', error_message=str(exc))
            LOG.warning('edition_product_retry webhook_id=%s error_type=%s', row['webhook_id'], type(exc).__name__)
        finally:
            with db.connect() as conn, conn.cursor() as cur:
                cur.execute("""UPDATE webhook_events SET processed_at=now(),payload=jsonb_set(payload,
                    '{_onboarding_attempts}',to_jsonb(LEAST(8,COALESCE((payload->>'_onboarding_attempts')::int,0)+1)))
                    WHERE webhook_id=%s AND status IN ('pending','failed')""", (row['webhook_id'],))
                conn.commit()
    return len(rows)


def reconcile(db, config=None, max_pages=4, renew=None):
    """Bounded update-window scan; save page continuation only after processing.

    Pending metadata is durably retained in receipts. API/persistence failures
    retain the old page/checkpoint; replay goes through the same registration.
    """
    import shopify_sync as shopify
    state = db.get_app_setting(CHECKPOINT, {}, ensure_schema_first=False)
    end = state.get('until') or now().isoformat()
    baseline = datetime.fromisoformat(state['checkpoint']) if state.get('checkpoint') else now()-timedelta(days=1)
    start = state.get('since') or (baseline-timedelta(minutes=10)).isoformat()
    after = state.get('after')
    query = f"updated_at:>='{start}' updated_at:<='{end}'"
    for _ in range(max_pages):
        data, _ = shopify.graphql_request(PRODUCT_PAGE, variables={'first': 50, 'after': after, 'query': query}, config=config)
        connection = data.get('products')
        if not isinstance(connection, dict) or 'nodes' not in connection or 'pageInfo' not in connection:
            raise RuntimeError('Incomplete product reconciliation page.')
        for product in connection['nodes']:
            if renew:
                renew()
            pid = product['id'].rsplit('/', 1)[-1]
            event = 'edition-recovery-' + hashlib.sha256((product['id'] + product['updatedAt']).encode()).hexdigest()
            payload = {'id': pid}
            claim = db.claim_product_create_webhook_receipt(payload, event, 'products/update', shop_domain=(config or {}).get('store_domain', ''))
            if not claim['duplicate']:
                process_receipt({'payload': payload, 'webhook_id': event, 'topic': 'products/update'}, db, config)
            else:
                # A previous attempt may have failed after receipt persistence.
                # Never advance this page past a failed receipt.
                with db.connect() as conn, conn.cursor() as cur:
                    cur.execute('SELECT status FROM webhook_events WHERE webhook_id=%s', (event,))
                    receipt = cur.fetchone()
                if not receipt or receipt['status'] in ('received','processing','failed','retry'):
                    process_receipt({'payload': payload, 'webhook_id': event, 'topic': 'products/update'}, db, config)
        page = connection['pageInfo']
        if page.get('hasNextPage') is False:
            db.set_app_setting(CHECKPOINT, {'checkpoint': end}, ensure_schema_first=False)
            return
        cursor = page.get('endCursor')
        if not cursor or cursor == after:
            raise RuntimeError('Product reconciliation cursor did not advance.')
        after = cursor
        db.set_app_setting(CHECKPOINT, {'checkpoint': state.get('checkpoint'), 'since': start, 'until': end, 'after': after}, ensure_schema_first=False)


def tick(scan=False, db=None, config=None):
    if db is None:
        import supabase_backend as db
    if not db.is_configured():
        return
    # Session advisory locks are unsafe through transaction-mode poolers. Claim
    # and renew an expiring lease in short committed transactions instead.
    owner = str(uuid.uuid4())
    def lease(release=False):
        with db.connect() as conn, conn.cursor() as cur:
            cur.execute("""UPDATE app_settings SET value=jsonb_build_object(
                'owner',%s::text,'expires_at',now()+%s * interval '1 second'),updated_at=now()
                WHERE key=%s AND value->>'owner'=%s RETURNING key""",
                (owner, 0 if release else 600, LEASE, owner))
            owned = cur.fetchone()
            conn.commit()
            if not owned and not release:
                raise RuntimeError('Product onboarding lease was lost; retry later.')
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO app_settings(key,value,updated_at)
            VALUES(%s,jsonb_build_object('owner',%s::text,'expires_at',now()+interval '10 minutes'),now())
            ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=now()
            WHERE (app_settings.value->>'expires_at')::timestamptz <= now()
            RETURNING key""", (LEASE, owner))
        acquired = cur.fetchone()
        conn.commit()
    if not acquired:
        return
    try:
        drain(db, config, renew=lease)
        if scan:
            reconcile(db, config, renew=lease)
    finally:
        lease(release=True)


def inspect_subscriptions():
    """Read the OS app's subscriptions only; never create/delete them."""
    import shopify_sync as shopify
    config = shopify.get_config()
    for suffix in ('create', 'update'):
        result = getattr(shopify, f'list_products_{suffix}_webhook_subscriptions')(config=config)
        callbacks = [shopify._webhook_callback_url(row).split('?')[0]
                     for row in result.get('subscriptions', [])]
        LOG.warning('edition_product_subscriptions topic=products/%s callbacks=%s visibility=os_app_only', suffix, callbacks)


def run(stop):
    try:
        inspect_subscriptions()
    except Exception as exc:
        LOG.warning('edition_product_subscription_inspection_failed error_type=%s', type(exc).__name__)
    next_scan = 0
    while not stop.is_set():
        scan = time.monotonic() >= next_scan
        try:
            tick(scan=scan)
        except Exception:
            LOG.exception('edition_product_onboarding_failed')
        if scan:
            next_scan = time.monotonic() + 300
        stop.wait(5)
