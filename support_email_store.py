"""Optional workflow metadata and read-only access to existing synced orders.

No method accepts a customer message, message body or attachment bytes.
The settings API accepts administrator-authored signature HTML only.
Schema provisioning is an explicit migration, never a page-render side effect.
"""
from contextlib import contextmanager
import hashlib
import logging
import json
import re
import uuid

import os_accounts
from support_email_db_guard import METADATA_DB
from support_email_logic import STATUSES

LOGGER = logging.getLogger(__name__)


class SupportStorageError(RuntimeError):
    pass


@contextmanager
def cursor(write=False):
    if not METADATA_DB.ready():
        raise SupportStorageError("Support metadata is temporarily unavailable.")
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
        METADATA_DB.failed(error, 'support_metadata')
        raise SupportStorageError("Support metadata is unavailable. The live mailbox is still available.") from None


def load_metadata(mailbox, keys):
    if not keys:
        return {}
    with cursor() as cur:
        cur.execute("SELECT * FROM customer_support_threads WHERE mailbox=%s AND thread_key=ANY(%s)",
                    (mailbox.casefold(), list(keys)))
        return {row["thread_key"]: dict(row) for row in cur.fetchall()}


def load_companion_receipts(mailbox, message_ids):
    """One bounded, indexed lookup of confirmed automatic sends, without MIME reads.

    Include visible messages' In-Reply-To IDs so a Sent reply can find its
    original request. A reference alone never labels a later customer message.
    Both existing Companion producers use deterministic private request keys.
    """
    mailbox = mailbox.casefold()
    candidates = []
    for message_id in dict.fromkeys(message_ids):
        if not isinstance(message_id, str) or not message_id or len(message_id) > 998:
            continue
        digest = hashlib.sha256(json.dumps([mailbox, message_id], sort_keys=True).encode()).hexdigest()
        certificate_key = 'inbox_certificate_reply:' + digest
        address_key = 'inbox_companion_request:' + digest
        candidates.append(dict(source_id=message_id, certificate_key=certificate_key, address_key=address_key,
            certificate_operation=str(uuid.uuid5(uuid.NAMESPACE_URL, 'sports-cave-certificate-reply:' + certificate_key)),
            address_operation=str(uuid.uuid5(uuid.NAMESPACE_URL, 'sports-cave-inbox:' + address_key))))
        if len(candidates) == 2000:
            break
    if not candidates:
        return {}
    with cursor() as cur:
        cur.execute("""WITH candidates AS (
          SELECT * FROM jsonb_to_recordset(%s::jsonb) AS c(
            source_id text, certificate_key text, address_key text,
            certificate_operation uuid, address_operation uuid)
        ), requests AS (
          SELECT c.source_id, c.certificate_operation AS operation_id
          FROM candidates c JOIN app_settings a ON a.key=c.certificate_key
          WHERE a.value->>'message_id'=c.source_id
            AND a.value->>'operation_id'=c.certificate_operation::text
          UNION ALL
          SELECT c.source_id, c.address_operation AS operation_id
          FROM candidates c JOIN app_settings a ON a.key=c.address_key
          WHERE a.value->>'kind'='address' AND a.value->'header'->>'message_id'=c.source_id
        )
        SELECT r.source_id, o.message_id, o.accepted_at
        FROM requests r JOIN support_email_outbox o ON o.operation_id=r.operation_id
        WHERE o.mailbox=%s AND o.status='accepted' AND o.accepted_at IS NOT NULL
        ORDER BY o.accepted_at""", (json.dumps(candidates), mailbox))
        receipts = {}
        for row in cur.fetchall():
            receipt = {'status': 'sent', 'accepted_at': row['accepted_at']}
            receipts[row['source_id']] = receipt
            receipts[row['message_id']] = receipt
        return receipts


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
        "email_sent": "Email accepted by the mail server",
        "email_reply_sent": "Reply accepted by the mail server",
        "email_forward_sent": "Forward accepted by the mail server",
        "email_archived": "Email moved to Archive",
        "email_trashed": "Email moved to Trash",
        "email_permanently_deleted": "Email permanently deleted from Trash",
        "email_junked": "Email moved to Junk",
        "email_copied": "Email copied; original retained",
        "email_mark_read": "Email marked read",
        "email_mark_unread": "Email marked unread",
        "email_flag_changed": "Email flag changed",
        "email_draft_saved": "Draft saved in the real mailbox",
        "email_draft_discarded": "Draft moved to Trash",
        "email_settings_updated": "Email settings updated",
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
    if previous.get("needs_approval") and not needs_approval and not os_accounts.is_admin(actor):
        raise SupportStorageError("Only Nathan or another OS administrator can clear an approval requirement.")
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


def load_email_settings(mailbox, user_id):
    from support_email_compose import default_settings, normalized_signatures
    settings = default_settings()
    with cursor() as cur:
        cur.execute("SELECT sender_name,signatures,folder_mapping,sent_policy FROM customer_support_email_settings WHERE mailbox=%s",
                    (mailbox.casefold(),))
        row = cur.fetchone()
        if row:
            settings.update(dict(row))
        cur.execute("SELECT signature_key FROM customer_support_email_preferences WHERE mailbox=%s AND user_id=%s",
                    (mailbox.casefold(), str(user_id)))
        pref = cur.fetchone()
    settings["signatures"] = normalized_signatures(settings.get("signatures"))
    return settings, (pref or {}).get("signature_key")


def save_email_settings(mailbox, *, actor, sender_name, signatures, folder_mapping, sent_policy, discovered_names):
    from support_email_compose import normalized_signatures
    if not os_accounts.is_admin(actor) or not os_accounts.can_access_page(actor, "Email"):
        raise SupportStorageError("Only an OS administrator can change mailbox settings.")
    sender_name = str(sender_name).strip()
    if not sender_name or len(sender_name) > 120 or any(c in sender_name for c in "\r\n\x00"):
        raise SupportStorageError("Use a valid sender display name.")
    if sent_policy not in {"verify", "server", "append"}:
        raise SupportStorageError("Invalid Sent storage policy.")
    mapping = {role: str(name) for role, name in dict(folder_mapping).items()
               if role in {"sent", "drafts", "archive", "junk", "trash"} and name}
    if any(name not in discovered_names or name.casefold() == "inbox" for name in mapping.values()):
        raise SupportStorageError("Map folders from the discovered mailbox list.")
    if len(set(mapping.values())) != len(mapping):
        raise SupportStorageError("Each mailbox role must use a different folder.")
    clean = normalized_signatures({key: {"version": 2, "html": value.get("html", "")}
                                  for key, value in signatures.items() if key in {"company", "nathan", "reina"}})
    with cursor(True) as cur:
        cur.execute("""INSERT INTO customer_support_email_settings (mailbox,sender_name,signatures,folder_mapping,sent_policy)
            VALUES (%s,%s,%s::jsonb,%s::jsonb,%s) ON CONFLICT(mailbox) DO UPDATE SET sender_name=EXCLUDED.sender_name,
            signatures=EXCLUDED.signatures,folder_mapping=EXCLUDED.folder_mapping,sent_policy=EXCLUDED.sent_policy,updated_at=now()""",
            (mailbox.casefold(), sender_name, json.dumps(clean), json.dumps(mapping), sent_policy))
    audit("email_settings_updated", actor=os_accounts.safe_account_label(actor))


def save_email_preference(mailbox, *, actor, signature_key):
    from support_email_compose import SIGNATURE_KEYS
    if not os_accounts.can_access_page(actor, "Email") or signature_key not in SIGNATURE_KEYS:
        raise SupportStorageError("Invalid Email preference.")
    with cursor(True) as cur:
        cur.execute("""INSERT INTO customer_support_email_preferences(mailbox,user_id,signature_key) VALUES (%s,%s,%s)
            ON CONFLICT(mailbox,user_id) DO UPDATE SET signature_key=EXCLUDED.signature_key,updated_at=now()""",
            (mailbox.casefold(), str(actor["id"]), signature_key))


def search_contacts(actor, term):
    """Read only already-synced customer addresses; CRM permission is mandatory."""
    if not os_accounts.can_access_page(actor, 'Email') or not os_accounts.can_access_page(actor, 'CRM Customers'):
        raise PermissionError('CRM Customers permission required.')
    term = str(term).strip()
    if not 2 <= len(term) <= 80 or any(ord(c)<32 for c in term):return []
    # Literal substring match, not wildcard or raw SQL input. Small fixed result.
    with cursor() as cur:
        cur.execute("""SELECT customer_name AS name,
            COALESCE(NULLIF(customer_email,''),email) AS email, shopify_order_id
            FROM shopify_orders
            WHERE position(lower(%s) in lower(COALESCE(customer_name,'') || ' ' ||
                COALESCE(NULLIF(customer_email,''),email,''))) > 0
            ORDER BY created_at DESC NULLS LAST LIMIT 8""", (term,))
        return [dict(name=r['name'] or '',email=r['email'] or '',source='Synced customer record') for r in cur.fetchall()]
