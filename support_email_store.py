"""Optional workflow metadata and read-only access to existing synced orders.

No method accepts a customer message, message body, HTML or attachment bytes.
Schema provisioning is an explicit migration, never a page-render side effect.
"""
from contextlib import contextmanager
import logging
import re

import os_accounts
from support_email_logic import STATUSES

LOGGER = logging.getLogger(__name__)


class SupportStorageError(RuntimeError):
    pass


@contextmanager
def cursor(write=False):
    try:
        import supabase_backend
        with supabase_backend.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout='4000ms'")
                if not write:
                    cur.execute("SET TRANSACTION READ ONLY")
                yield cur
            if write:
                conn.commit()
    except SupportStorageError:
        raise
    except Exception as error:
        LOGGER.warning("Support metadata unavailable (%s)", type(error).__name__)
        raise SupportStorageError("Support metadata is unavailable. The live mailbox is still available.") from None


def load_metadata(mailbox, keys):
    if not keys:
        return {}
    with cursor() as cur:
        cur.execute("SELECT * FROM customer_support_threads WHERE mailbox=%s AND thread_key=ANY(%s)",
                    (mailbox.casefold(), list(keys)))
        return {row["thread_key"]: dict(row) for row in cur.fetchall()}


def load_assignees():
    with cursor() as cur:
        cur.execute("""SELECT u.id, u.display_name, u.username, u.role, u.is_active, u.account_status,
                     ARRAY(SELECT page_key FROM os_user_page_permissions p
                           WHERE p.user_id=u.id AND p.can_access) AS page_permissions
                       FROM os_users u WHERE u.is_active AND u.account_status='active'
                       ORDER BY u.display_name, u.username LIMIT 101""")
        users = cur.fetchall()
        return [dict(u) for u in users if os_accounts.can_access_page(u, "Email")]


def load_orders(emails=(), numbers=(), ids=()):
    """One bounded lookup across the existing order ledger. No Shopify calls or writes."""
    if not emails and not numbers and not ids:
        return []
    with cursor() as cur:
        cur.execute("""SELECT o.shopify_order_id, o.order_name, o.customer_name,
                       COALESCE(NULLIF(o.customer_email,''), o.email) AS customer_email,
                       o.created_at, o.fulfillment_status, o.admin_url, o.synced_at,
                       o.raw_json->'fulfillments' AS fulfillments,
                       o.raw_json->'tracking' AS tracking
                       FROM shopify_orders o
                       WHERE lower(trim(COALESCE(NULLIF(o.customer_email,''),o.email)))=ANY(%s)
                          OR upper(ltrim(COALESCE(o.order_name,o.shopify_order_name),'#'))=ANY(%s)
                          OR o.shopify_order_id=ANY(%s)
                       ORDER BY o.created_at DESC NULLS LAST LIMIT 1001""",
                    (list(emails), list(numbers), list(ids)))
        orders = [dict(o) for o in cur.fetchall()]
        if len(orders) > 1000:
            raise SupportStorageError("Too many matching orders. Narrow the inbox window before matching.")
        order_ids = [o["shopify_order_id"] for o in orders]
        if not order_ids:
            return []
        cur.execute("""SELECT shopify_order_id, product_title, variant_title, shopify_handle
                       FROM shopify_order_lines WHERE shopify_order_id=ANY(%s) LIMIT 5001""", (order_ids,))
        lines = cur.fetchall()
        cur.execute("""SELECT id, shopify_order_id, product_title, variant_title, shopify_handle,
                       edition_number, edition_total, certificate_status
                       FROM edition_orders WHERE shopify_order_id=ANY(%s) LIMIT 5001""", (order_ids,))
        editions = cur.fetchall()
        if len(lines) > 5000 or len(editions) > 5000:
            raise SupportStorageError("Order detail limit reached. Matching is unavailable for this window.")
        for order in orders:
            order["lines"] = [dict(l) for l in lines if l["shopify_order_id"] == order["shopify_order_id"]]
            order["editions"] = [dict(e) for e in editions if e["shopify_order_id"] == order["shopify_order_id"]]
        return orders


def audit(action, thread_key="", *, actor=""):
    # Fixed messages; never serialize the email object or note text into the existing audit log.
    descriptions = {
        "email_inbox_refreshed": "Email inbox refreshed from VentraIP IMAP",
        "support_status_changed": "Support status changed",
        "support_assignment_changed": "Conversation assigned",
        "support_note_changed": "Internal support note updated",
        "support_approval_changed": "Support approval requirement changed",
    }
    if action not in descriptions:
        return
    from activity_log import record_activity_log
    record_activity_log(action, "Email", descriptions[action], entity_type="customer_support_thread",
                        entity_id=thread_key, actor=actor)


def save_workflow(mailbox, thread_key, *, actor, support_status, assigned_user_id=None,
                  internal_notes="", needs_approval=False, previous=None):
    if not os_accounts.can_access_page(actor, "Email") or not actor.get("id"):
        raise SupportStorageError("Email access is required to update support metadata.")
    if support_status not in STATUSES or not re.fullmatch(r"[0-9a-f]{64}", thread_key):
        raise SupportStorageError("Invalid support metadata.")
    if not isinstance(internal_notes, str) or len(internal_notes) > 8000:
        raise SupportStorageError("Internal notes must be 8,000 characters or fewer.")
    if assigned_user_id and str(assigned_user_id) not in {str(u["id"]) for u in load_assignees()}:
        raise SupportStorageError("Choose an active OS account with Email access.")
    previous = previous or {}
    with cursor(True) as cur:
        cur.execute("""INSERT INTO customer_support_threads
            (mailbox,thread_key,support_status,assigned_user_id,internal_notes,needs_approval,last_handled_by,last_handled_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,now())
            ON CONFLICT (mailbox,thread_key) DO UPDATE SET
                support_status=EXCLUDED.support_status, assigned_user_id=EXCLUDED.assigned_user_id,
                internal_notes=EXCLUDED.internal_notes, needs_approval=EXCLUDED.needs_approval,
                last_handled_by=EXCLUDED.last_handled_by, last_handled_at=now(),updated_at=now()
            WHERE customer_support_threads.updated_at=%s::timestamptz
            RETURNING *""",
            (mailbox.casefold(), thread_key, support_status, assigned_user_id or None, internal_notes,
             bool(needs_approval), str(actor["id"]), previous.get("updated_at")))
        saved = cur.fetchone()
        if not saved:
            raise SupportStorageError("Another user changed this conversation. Refresh Inbox before saving.")
    changed = {"support_status": (support_status, "support_status_changed"),
               "assigned_user_id": (assigned_user_id or None, "support_assignment_changed"),
               "internal_notes": (internal_notes, "support_note_changed"),
               "needs_approval": (bool(needs_approval), "support_approval_changed")}
    for field, (value, action) in changed.items():
        if str(previous.get(field) or "") != str(value or ""):
            audit(action, thread_key, actor=os_accounts.safe_account_label(actor))
    return dict(saved)
