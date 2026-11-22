"""Read the PSD repair journal for Orders; never enqueue from a status read."""
import re


def public_message(value):
    from auto_editions_status import reason
    return reason(value)


def projection(row):
    from auto_editions_repair import ACTIVE
    detail = row.get('repair_detail') or {}
    pending = row.get('replacement') or {}
    cancelled = (row.get('reset_cancellation') or {}).get('stage') in ('Cancelling', 'Confirmed')
    eligible = (row.get('status') == 'assigned' and row.get('allocation_valid') is True
                and row.get('identity_enforced') is True and not row.get('invalidated_at')
                and not row.get('cancelled_at') and row.get('duplicate_allocation_warning') in (None,'','false')
                and not cancelled and not pending.get('manual_required'))
    failed = row.get('preparation_status') in ('Blocked', 'Needs PSD Repair')
    active = eligible and detail.get('state') in ACTIVE
    repairable = eligible and not active and (failed or detail.get('state') == 'Needs help' and bool(detail.get('jpg_blocked')))
    message = detail.get('message') if active or detail.get('state') == 'Needs help' else ''
    cause = public_message(row.get('technical_reason') or row.get('reason'))
    return dict(product_gid=row['product_gid'], allocation_id=int(row['id']), active=bool(active),
                repairable=bool(repairable), state=detail.get('state'),
                message=public_message(message) or cause, cause=cause,
                updated_at=str(detail.get('changed_at') or row.get('preparation_updated_at') or ''),
                request_id=detail.get('request_id'))


def batch(connect, ids):
    ids = list(dict.fromkeys(int(i) for i in ids if re.fullmatch(r'[1-9][0-9]*', str(i))))
    if not ids:
        return {}
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT e.id,e.shopify_product_gid AS product_gid,e.status,
          e.allocation_valid,e.identity_enforced,e.invalidated_at,to_jsonb(e)->>'cancelled_at' AS cancelled_at,
          to_jsonb(e)->>'duplicate_allocation_warning' AS duplicate_allocation_warning,
          q.status AS preparation_status,q.reason,q.updated_at AS preparation_updated_at,
          to_jsonb(q)->'replacement' AS replacement,to_jsonb(q)->'reset_cancellation' AS reset_cancellation,
          (SELECT reason FROM auto_edition_technical_checks t WHERE t.product_gid=q.product_gid
            AND t.preparation_hash=q.preparation_hash AND t.checkpoint_at=q.updated_at LIMIT 1) AS technical_reason,
          (SELECT detail FROM auto_edition_onboarding_audit a WHERE a.product_gid=q.product_gid
            AND a.event='edition_repair_request' ORDER BY a.id DESC LIMIT 1) AS repair_detail
          FROM edition_orders e JOIN auto_edition_onboarding q ON q.product_gid=e.shopify_product_gid
          WHERE e.id=ANY(%s)""", (ids,))
        return {str(row['id']): projection(row) for row in cur.fetchall()}
