"""One-order repair. Import is inert. Caller owns transaction and fresh Shopify read.

Install the reviewed guards and application certificate check before applying.
Call apply inside a transaction; commit only on success. Then invoke the existing
sync_product_edition_metafields(HANDLE, ensure_schema_first=False) mirror and
verify Shopify's values. Never change Shopify financial/refund state.
"""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import uuid

ORDER = 'gid://shopify/Order/18945167196467'
LINE = 'gid://shopify/LineItem/50798859878707'
PRODUCT = 'gid://shopify/Product/15411172376883'
HANDLE = 'kostecki-hazelwood-final-lap-wall-art'
RUN = '8a601906-f380-479a-8326-f8d34d1c9d28'
REPAIR = 'sc3303-release-019-20261015'
REQUEST = str(uuid.uuid5(uuid.NAMESPACE_URL, REPAIR))
GUARDS = ('cancelled_edition_order_guard','cancelled_edition_line_guard',
          'cancelled_edition_allocation_guard','cancelled_edition_certificate_guard',
          'cancelled_edition_dispatch_guard')


def require(ok, reason):
    if not ok:
        raise ValueError('SC3303 correction stopped: ' + reason)


def validate_shopify(order, fetched_at, now=None):
    now = now or datetime.now(timezone.utc)
    require(0 <= (now-fetched_at).total_seconds() <= 120, 'Shopify evidence is stale')
    require(order.get('id') == ORDER and order.get('name') == '#SC3303', 'order identity mismatch')
    require(order.get('currentSubtotalLineItemsQuantity') == 0, 'order has current items')
    require(Decimal(order['currentTotalPriceSet']['shopMoney']['amount']) == 0, 'order has a current value')
    require(order.get('fulfillments') == [], 'fulfilment evidence exists')
    lines = order.get('lineItems') or {}
    require(lines.get('pageInfo', {}).get('hasNextPage') is False, 'incomplete line evidence')
    require(len(lines.get('nodes', [])) == 1, 'unexpected order lines')
    line = lines['nodes'][0]
    require(line.get('id') == LINE and line.get('currentQuantity') == 0
            and line.get('unfulfilledQuantity') == 0
            and (line.get('product') or {}).get('id') == PRODUCT, 'line identity or quantity changed')
    fulfillment = order.get('fulfillmentOrders') or {}
    require(fulfillment.get('pageInfo', {}).get('hasNextPage') is False, 'incomplete fulfilment evidence')
    require(all(f.get('status') in ('CLOSED','CANCELLED') and f.get('requestStatus') == 'UNSUBMITTED'
                for f in fulfillment.get('nodes', [])), 'fulfilment work is pending or was submitted')


def read_state(cur):
    cur.execute('SELECT * FROM edition_products WHERE shopify_handle=%s FOR UPDATE', (HANDLE,))
    product = cur.fetchone()
    cur.execute('SELECT * FROM edition_runs WHERE id=%s FOR UPDATE', (RUN,))
    run = cur.fetchone()
    cur.execute("SELECT * FROM shopify_orders WHERE regexp_replace(shopify_order_id,'^.*/','')=%s FOR UPDATE", (ORDER.rsplit('/',1)[-1],))
    orders = cur.fetchall()
    require(len(orders)==1 and orders[0]['shopify_order_id']==ORDER, 'missing or duplicate order identity')
    order = orders[0]
    cur.execute("""SELECT * FROM edition_orders WHERE shopify_product_gid=%s OR shopify_handle=%s
      OR regexp_replace(COALESCE(shopify_product_id,''),'^.*/','')=%s OR edition_run_id=%s
      OR regexp_replace(COALESCE(shopify_order_id,''),'^.*/','')=%s ORDER BY edition_number,id FOR UPDATE""",
      (PRODUCT,HANDLE,PRODUCT.rsplit('/',1)[-1],RUN,ORDER.rsplit('/',1)[-1]))
    allocations = cur.fetchall()
    cur.execute("SELECT * FROM shopify_order_lines WHERE regexp_replace(shopify_order_id,'^.*/','')=%s ORDER BY id FOR UPDATE", (ORDER.rsplit('/',1)[-1],))
    lines = cur.fetchall()
    cur.execute("""SELECT * FROM certificates WHERE edition_order_id='678'
      OR regexp_replace(COALESCE(shopify_order_id,''),'^.*/','')=%s
      OR shopify_order_name='#SC3303'
      OR ((shopify_handle=%s OR product_handle=%s OR regexp_replace(COALESCE(shopify_product_id,''),'^.*/','')=%s)
          AND edition_number>=19)""", (ORDER.rsplit('/',1)[-1],HANDLE,HANDLE,PRODUCT.rsplit('/',1)[-1]))
    certificates = cur.fetchall()
    cur.execute("""SELECT * FROM prodigi_dispatch_rows WHERE shopify_order_name='#SC3303'
      OR regexp_replace(COALESCE(shopify_order_id,''),'^.*/','')=%s
      OR regexp_replace(COALESCE(shopify_line_item_id,''),'^.*/','')=%s""",
      (ORDER.rsplit('/',1)[-1],LINE.rsplit('/',1)[-1]))
    dispatch = cur.fetchall()
    cur.execute("""SELECT * FROM auto_edition_jobs WHERE payload->>'edition_order_id'='678'
      OR payload->'identity'->>'allocation_id'='678'
      OR payload::text LIKE %s OR payload::text LIKE %s OR payload::text LIKE %s""",
      ('%SC3303%','%'+ORDER.rsplit('/',1)[-1]+'%','%'+HANDLE+'%'))
    jobs = cur.fetchall()
    cur.execute("""SELECT webhook_id,status FROM webhook_events
      WHERE (shopify_order_name='#SC3303' OR regexp_replace(COALESCE(shopify_order_id,''),'^.*/','')=%s
        OR payload->>'id'=%s) AND status NOT IN ('processed','completed','rejected','skipped')""",
      (ORDER.rsplit('/',1)[-1],ORDER.rsplit('/',1)[-1]))
    webhooks = cur.fetchall()
    cur.execute('SELECT * FROM edition_allocation_tombstones WHERE shopify_product_gid=%s', (PRODUCT,))
    tombstones = cur.fetchall()
    return dict(product=product,run=run,order=order,allocations=allocations,lines=lines,
                certificates=certificates,dispatch=dispatch,jobs=jobs,webhooks=webhooks,tombstones=tombstones)


def validate_state(state):
    p,r,o = (state[k] for k in ('product','run','order'))
    require(p and r and o, 'required records are missing')
    require(p['id']==727 and p['shopify_product_gid']==PRODUCT and str(p['active_edition_run_id'])==RUN,
            'product or active run changed')
    require((p['next_edition_number'],p['sold_count'],p['remaining_count'],p['edition_total'],p['last_assigned_edition'])
            ==(20,19,81,100,19), 'product counters changed')
    require((r['next_edition_number'],r['sold_count'],r['last_allocated_number'],r['edition_total'],r['status'],r['allocation_baseline_sold_count'])
            ==(20,19,19,100,'active',0), 'run counters changed')
    require(p['active'] and p['is_active'] and not p['sold_out'] and not p['is_sold_out'], 'run disabled')
    require(not p.get('manual_override_id') and not r.get('manual_override_id'), 'new override exists')
    require(o['order_name']=='#SC3303' and o['fulfillment_status']=='UNFULFILLED', 'order state changed')
    units=state['allocations']
    require(len(units)==19 and sorted(u['edition_number'] for u in units)==list(range(1,20)), 'allocation history changed')
    require(all(u['allocation_valid'] and u['identity_enforced'] and u['status']=='assigned'
                and str(u['edition_run_id'])==RUN for u in units), 'invalid or other-run allocation exists')
    target=next(u for u in units if u['edition_number']==19)
    require(target['id']==678 and target['shopify_order_id']==ORDER and target['external_line_item_id']==LINE
            and target['unit_ordinal']==1 and target['quantity']==1, 'edition 019 ownership changed')
    require(target['certificate_status']=='Certificate Missing', 'certificate state changed')
    require(not any(target.get(k) for k in ('certificate_id','certificate_file_url','shopify_file_id',
            'certificate_r2_key','certificate_preview_r2_key')), 'certificate asset evidence exists')
    require(next(u for u in units if u['edition_number']==18)['shopify_order_name']=='#SC3302'
            and next(u for u in units if u['edition_number']==17)['shopify_order_name']=='#SC3301', 'protected orders changed')
    require(state['lines'] and all(l['shopify_line_item_id'].rsplit('/',1)[-1]==LINE.rsplit('/',1)[-1]
            and l['shopify_product_id'].rsplit('/',1)[-1]==PRODUCT.rsplit('/',1)[-1] for l in state['lines']), 'unexpected local lines')
    for key in ('certificates','dispatch','jobs','webhooks','tombstones'):
        require(not state[key], key+' conflict exists')


def apply(cur, shopify_order, fetched_at, actor_id):
    """All checks and DB edits are in the caller's single transaction. No commit."""
    validate_shopify(shopify_order,fetched_at)
    cur.execute("SET LOCAL lock_timeout='10s'")
    cur.execute("SET LOCAL statement_timeout='45s'")
    cur.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', (PRODUCT,))
    cur.execute("SELECT tgname FROM pg_trigger WHERE tgname=ANY(%s) AND tgenabled='O'", (list(GUARDS),))
    require({r['tgname'] for r in cur.fetchall()}==set(GUARDS), 'deploy cancellation guards first')
    cur.execute('SELECT applied_at FROM edition_repair_audits WHERE repair_key=%s', (REPAIR,))
    require(not cur.fetchone(), 'repair already recorded; verify it, never decrement twice')
    state=read_state(cur)
    validate_state(state)
    # Prevent new queued jobs or certificates between the checks and commit.
    # Existing writers finish first; repeat checks under these short table locks.
    cur.execute('LOCK TABLE auto_edition_jobs,webhook_events,certificates,prodigi_dispatch_rows IN SHARE ROW EXCLUSIVE MODE')
    state=read_state(cur)
    validate_state(state)
    before=json.dumps({**state,'shopify_evidence':shopify_order,'shopify_checked_at':fetched_at},default=str,sort_keys=True)
    cur.execute("""INSERT INTO edition_repair_audits(repair_key,product_gid,mode,snapshot_sha256,report,actor)
      VALUES(%s,%s,'apply',%s,%s::jsonb,%s)""",
      (REPAIR,PRODUCT,hashlib.sha256(before.encode()).hexdigest(),before,'user-authorized SC3303 correction; '+str(actor_id)))
    cur.execute("""INSERT INTO edition_repair_archive(repair_key,edition_order_id,row_snapshot)
      SELECT %s,id::text,to_jsonb(e) FROM edition_orders e WHERE id=678""", (REPAIR,))
    cur.execute("SELECT set_config('sports_cave.edition_repair_key',%s,true)", (REPAIR,))
    for key in ('id:'+ORDER.rsplit('/',1)[-1],'name:#SC3303'):
        cur.execute("""INSERT INTO edition_order_sync_locks(canonical_order_key,shopify_order_id,shopify_order_name,status,reason)
          VALUES(%s,%s,'#SC3303','cancelled',%s) ON CONFLICT(canonical_order_key) DO UPDATE
          SET status='cancelled',reason=EXCLUDED.reason,updated_at=now()""", (key,ORDER,REPAIR))
    cur.execute("""INSERT INTO edition_allocation_tombstones(source_channel,external_order_id,external_line_item_id,
      unit_ordinal,shopify_product_gid,former_edition_number,repair_key,reason,edition_run_id)
      VALUES('shopify',%s,%s,1,%s,19,%s,'Cancelled before issue; number released by explicit cursor override',%s)""",
      (ORDER,LINE,PRODUCT,REPAIR,RUN))
    cur.execute("""UPDATE edition_orders SET status='cancelled',allocation_valid=false,invalidated_at=now(),
      invalidation_reason=%s,certificate_status='Cancelled',updated_at=now() WHERE id=678""", (REPAIR,))
    cur.execute("UPDATE shopify_orders SET cancelled_at=now(),fulfillment_status='CANCELLED',total_price='0.00',updated_at=now() WHERE shopify_order_id=%s", (ORDER,))
    cur.execute("UPDATE shopify_order_lines SET quantity=0,assignment_status='Cancelled',updated_at=now() WHERE shopify_order_id=%s", (ORDER,))
    cur.execute("""UPDATE edition_products SET sold_count=18,remaining_count=82,last_assigned_edition=18,
      edition_display_text='Next Available Edition #019/100',updated_at=now() WHERE id=727""")
    cur.execute('SELECT override_edition_cursor(%s,%s::uuid,20,19,%s::uuid,%s::uuid,100,100)', (HANDLE,RUN,REQUEST,str(actor_id)))
    cur.execute('SELECT next_edition_number,sold_count,remaining_count,last_assigned_edition FROM edition_products WHERE id=727')
    require(cur.fetchone()==dict(next_edition_number=19,sold_count=18,remaining_count=82,last_assigned_edition=18), 'unexpected final counters')
    cur.execute('SELECT * FROM edition_orders WHERE shopify_product_gid=%s AND id<>678 ORDER BY edition_number,id', (PRODUCT,))
    require(cur.fetchall()==[u for u in state['allocations'] if u['id']!=678], 'earlier allocations changed')
    cur.execute('UPDATE edition_repair_audits SET applied_at=now() WHERE repair_key=%s', (REPAIR,))
    return dict(order='#SC3303',status='CANCELLED',released=19,next=19,sold=18,remaining=82,shopify_sync='Pending')
