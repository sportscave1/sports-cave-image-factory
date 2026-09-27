"""Sparse, server-only VA bonus tracking; catalogue/orders remain their own truth."""
from datetime import date, datetime
from uuid import UUID


START_AT = "2026-09-01 00:00:00 Australia/Sydney"

# Match immutable product IDs, never titles. Include orders awaiting allocation.
# Invalid allocations, test orders and cancelled orders cannot qualify a bonus.
FIRST_ORDER_SQL = """
SELECT order_id, order_name, order_at FROM (
    SELECT o.shopify_order_id AS order_id,
           COALESCE(NULLIF(o.order_name,''), NULLIF(o.shopify_order_name,''),
                    NULLIF(o.order_number,''), o.shopify_order_id) AS order_name,
           COALESCE(o.created_at,o.processed_at) AS order_at
    FROM shopify_order_lines l JOIN shopify_orders o
      ON o.shopify_order_id=l.shopify_order_id
    WHERE l.shopify_product_id IN (NULLIF(p.shopify_product_gid,''),NULLIF(p.shopify_product_id,''),
          NULLIF(regexp_replace(p.shopify_product_id,'^gid://shopify/Product/',''),''))
      AND l.quantity > 0 AND o.cancelled_at IS NULL
      AND COALESCE(o.raw_json->>'test',o.raw->>'test','false') <> 'true'
    UNION ALL
    SELECT COALESCE(NULLIF(e.shopify_order_id,''),NULLIF(e.external_order_id,'')),
           COALESCE(NULLIF(e.shopify_order_name,''),NULLIF(e.external_order_id,'')),
           COALESCE(o.created_at,e.purchase_date,e.assigned_at)
    FROM edition_orders e LEFT JOIN shopify_orders o
      ON o.shopify_order_id=e.shopify_order_id
    WHERE (e.shopify_product_gid=NULLIF(p.shopify_product_gid,'')
           OR e.shopify_product_id IN (NULLIF(p.shopify_product_gid,''),NULLIF(p.shopify_product_id,''),
              NULLIF(regexp_replace(p.shopify_product_id,'^gid://shopify/Product/',''),'')))
      AND e.allocation_valid IS DISTINCT FROM false
      AND o.cancelled_at IS NULL
      AND COALESCE(o.raw_json->>'test',o.raw->>'test','false') <> 'true'
) orders
WHERE order_id IS NOT NULL AND order_name IS NOT NULL
ORDER BY order_at NULLS LAST, order_id
LIMIT 1
"""

LIST_SQL = """
SELECT p.id AS edition_product_id,p.product_title,
       COALESCE(t.paid_order_name,f.order_name,'') AS first_order,
       COALESCE(t.paid_order_id,f.order_id,'') AS first_order_id,
       COALESCE(t.designed_by,'') AS designed_by,t.bonus_paid_on,
       COALESCE(t.version,0) AS version
FROM edition_products p
LEFT JOIN edition_design_tracking t ON t.edition_product_id=p.id
LEFT JOIN LATERAL (""" + FIRST_ORDER_SQL + """) f ON true
WHERE p.created_at >= %s::timestamptz
ORDER BY p.created_at DESC,p.id DESC
"""


class TrackingConflict(ValueError):
    pass


def _paid_date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise ValueError("Bonus must be a valid paid date or left blank.") from None


def editor_changes(originals, edited):
    """Only editable fields travel back; row identity comes from the saved snapshot."""
    if len(originals) != len(edited):
        raise ValueError("Refresh the tracker before saving.")
    changes = []
    for old, new in zip(originals, edited):
        designer = str(new.get("designed_by") or "").strip()
        paid = _paid_date(new.get("bonus_paid_on"))
        if designer != old["designed_by"] or paid != _paid_date(old.get("bonus_paid_on")):
            changes.append({
                "edition_product_id": old["edition_product_id"],
                "version": old["version"], "designed_by": designer,
                "bonus_paid_on": paid, "first_order_id": old["first_order_id"],
            })
    return changes


class Store:
    def __init__(self, connect=None):
        if connect is None:
            from supabase_backend import connect
        self.connect = connect

    @staticmethod
    def _authorize(conn, actor):
        # Identity is passed by the authenticated server session, never editor data.
        try:
            actor_id = str(UUID(str((actor or {}).get("id") or "")))
        except ValueError:
            raise PermissionError("Sign in with your personal Edition Ops account.") from None
        user = conn.execute("""
            SELECT id,role,is_active,account_status,removed_at,session_version
            FROM os_users WHERE id=%s FOR SHARE
        """, (actor_id,)).fetchone()
        if (not user or not user["is_active"] or user["account_status"] != "active"
                or user["removed_at"] or int(user["session_version"]) != int(actor.get("session_version",1))):
            raise PermissionError("Your session is no longer active. Please sign in again.")
        admin = user["role"] == "admin"
        if not admin:
            permission = conn.execute("""
                SELECT 1 FROM os_user_page_permissions
                WHERE user_id=%s AND page_key='edition_ops' AND can_access=true FOR SHARE
            """, (actor_id,)).fetchone()
            if not permission:
                raise PermissionError("Edition Ops access is required.")
        return actor_id, admin

    def list_rows(self, actor):
        with self.connect() as conn:
            self._authorize(conn, actor)
            return conn.execute(LIST_SQL, (START_AT,)).fetchall()

    def save(self, actor, changes):
        if not changes:
            return 0
        if len({int(c["edition_product_id"]) for c in changes}) != len(changes):
            raise ValueError("Duplicate product rows. Refresh before saving.")
        with self.connect() as conn:
            actor_id, admin = self._authorize(conn, actor)
            for change in sorted(changes, key=lambda c: int(c["edition_product_id"])):
                self._save_row(conn, actor_id, admin, change)
        return len(changes)

    @staticmethod
    def _save_row(conn, actor_id, admin, change):
        product_id = int(change["edition_product_id"])
        designer = str(change.get("designed_by") or "").strip()
        if len(designer) > 120:
            raise ValueError("Designed by must be 120 characters or fewer.")
        paid = _paid_date(change.get("bonus_paid_on"))
        # Lock the parent too: two first-time edits must not race to insert a row.
        product = conn.execute("""
            SELECT id FROM edition_products WHERE id=%s AND created_at >= %s::timestamptz
            FOR UPDATE
        """, (product_id, START_AT)).fetchone()
        if not product:
            raise ValueError("This product is outside the design tracking period.")
        old = conn.execute("SELECT * FROM edition_design_tracking WHERE edition_product_id=%s FOR UPDATE",
                           (product_id,)).fetchone() or {}
        if int(change["version"]) != int(old.get("version",0)):
            raise TrackingConflict("Someone updated this design. Refresh and reapply your changes.")
        bonus_changed = paid != old.get("bonus_paid_on")
        if bonus_changed and not admin:
            raise PermissionError("Only an admin can change the Bonus paid date.")
        order_id, order_name = old.get("paid_order_id"), old.get("paid_order_name")
        paid_by = old.get("bonus_paid_by")
        if bonus_changed:
            paid_by = actor_id if paid else None
            if paid:
                if not order_id:
                    first = conn.execute("SELECT f.* FROM edition_products p CROSS JOIN LATERAL ("
                                         + FIRST_ORDER_SQL + ") f WHERE p.id=%s", (product_id,)).fetchone()
                    if not first:
                        raise ValueError("A recorded first order is required before marking a bonus paid.")
                    order_id, order_name = first["order_id"], first["order_name"]
                if str(change.get("first_order_id") or "") != str(order_id):
                    raise TrackingConflict("The first order changed. Refresh before marking the bonus paid.")
            else:
                order_id = order_name = None
        if designer == old.get("designed_by", "") and not bonus_changed:
            return
        conn.execute("""
            INSERT INTO edition_design_tracking
              (edition_product_id,designed_by,bonus_paid_on,paid_order_id,paid_order_name,
               bonus_paid_by,updated_by,version)
            VALUES (%s,%s,%s,%s,%s,%s,%s,1)
            ON CONFLICT (edition_product_id) DO UPDATE SET
              designed_by=excluded.designed_by,bonus_paid_on=excluded.bonus_paid_on,
              paid_order_id=excluded.paid_order_id,paid_order_name=excluded.paid_order_name,
              bonus_paid_by=excluded.bonus_paid_by,updated_by=excluded.updated_by,
              version=edition_design_tracking.version+1,updated_at=now()
        """, (product_id,designer,paid,order_id,order_name,paid_by,actor_id))
