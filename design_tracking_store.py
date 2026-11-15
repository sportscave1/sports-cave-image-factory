"""Server-only editable design tracker with manual orders and protected bonuses."""
from datetime import date, datetime
from uuid import UUID

START_AT = "2026-09-01 00:00:00 Australia/Sydney"
EDITABLE_FIELDS = ("product_title", "date_created", "first_order", "designed_by", "bonus_paid_on")
ROW_COLUMNS = "id,edition_product_id,product_title,date_created,first_order,designed_by,bonus_paid_on,version"
DISCOVER_SQL = """
INSERT INTO edition_design_tracking (edition_product_id,product_title,date_created,first_order,created_at)
SELECT p.id,p.product_title,(p.created_at AT TIME ZONE 'Australia/Sydney')::date,'',p.created_at
FROM edition_products p
WHERE p.created_at >= %s::timestamptz
  AND NOT EXISTS (SELECT 1 FROM edition_design_tracking t
                  WHERE t.edition_product_id=p.id AND t.product_title IS NOT NULL
                    AND t.date_created IS NOT NULL AND t.first_order IS NOT NULL)
ON CONFLICT (edition_product_id) DO UPDATE SET
    product_title=COALESCE(edition_design_tracking.product_title,excluded.product_title),
    date_created=COALESCE(edition_design_tracking.date_created,excluded.date_created),
    first_order=COALESCE(edition_design_tracking.first_order,'')
WHERE edition_design_tracking.product_title IS NULL
   OR edition_design_tracking.date_created IS NULL OR edition_design_tracking.first_order IS NULL
"""
LIST_SQL = """
SELECT t.id,t.edition_product_id,COALESCE(t.product_title,p.product_title,'') AS product_title,
       COALESCE(t.date_created,(p.created_at AT TIME ZONE 'Australia/Sydney')::date) AS date_created,
       COALESCE(t.first_order,'') AS first_order,t.designed_by,t.bonus_paid_on,t.version
FROM edition_design_tracking t LEFT JOIN edition_products p ON p.id=t.edition_product_id
ORDER BY t.created_at DESC,t.id
"""


class TrackingConflict(ValueError):
    pass


def _date(value, label):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise ValueError(f"{label} must be a valid date.") from None


def _value(field, value):
    if field in ("date_created", "bonus_paid_on"):
        return _date(value, "Date created" if field == "date_created" else "Bonus")
    return str(value or "").strip()


def _row(row):
    result = {key: row[key] for key in ("id", "edition_product_id", *EDITABLE_FIELDS, "version")}
    result["id"] = str(result["id"])
    return result


def editor_changes(originals, edited):
    """Editable patches only; identities and prior values come from server state."""
    if len(originals) != len(edited):
        raise ValueError("Use Add product to add a row. Existing rows cannot be deleted.")
    changes = []
    for old, new in zip(originals, edited):
        values = {key: _value(key, new.get(key)) for key in EDITABLE_FIELDS
                  if _value(key, new.get(key)) != _value(key, old.get(key))}
        if values:
            changes.append({"id": old["id"], "values": values,
                            "original": {key: old.get(key) for key in values}})
    return changes


class Store:
    def __init__(self, connect=None):
        if connect is None:
            from supabase_backend import connect
        self.connect = connect

    @staticmethod
    def _authorize(conn, actor):
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
            # Webhooks have no human identity: never credit the person viewing a row.
            conn.execute(DISCOVER_SQL, (START_AT,))
            return [_row(row) for row in conn.execute(LIST_SQL).fetchall()]

    def create(self, actor, *, row_id, product_title, date_created):
        row_id = str(UUID(str(row_id)))
        title = str(product_title or "").strip()
        created = _date(date_created, "Date created")
        if not title or len(title) > 500 or created is None:
            raise ValueError("Enter a product name (up to 500 characters) and Date created.")
        with self.connect() as conn:
            actor_id, _ = self._authorize(conn, actor)
            creator = conn.execute("SELECT display_name,username FROM os_users WHERE id=%s", (actor_id,)).fetchone()
            designer = str(creator.get("display_name") or creator.get("username") or "").strip()[:120]
            # Stable request ID makes retry after a lost response safe.
            conn.execute("""
                INSERT INTO edition_design_tracking
                    (id,product_title,date_created,first_order,designed_by,added_by,updated_by)
                VALUES (%s,%s,%s,'',%s,%s,%s) ON CONFLICT (id) DO NOTHING
            """, (row_id,title,created,designer,actor_id,actor_id))
            row = conn.execute("SELECT " + ROW_COLUMNS + " FROM edition_design_tracking WHERE id=%s AND added_by=%s",
                               (row_id,actor_id)).fetchone()
            if not row:
                raise TrackingConflict("This add-product request has already been used. Refresh and try again.")
            return _row(row)

    def save(self, actor, changes):
        if not changes:
            return []
        if len({str(c["id"]) for c in changes}) != len(changes):
            raise ValueError("Duplicate rows. Refresh before saving.")
        with self.connect() as conn:
            actor_id, admin = self._authorize(conn, actor)
            # Stable lock order and one atomic transaction for a multi-cell paste.
            return [self._save_row(conn,actor_id,admin,c) for c in sorted(changes,key=lambda c:str(c["id"]))]

    @staticmethod
    def _save_row(conn, actor_id, admin, change):
        row_id = str(UUID(str(change["id"])))
        values = change.get("values") or {}
        if set(values) - set(EDITABLE_FIELDS):
            raise ValueError("Only spreadsheet fields can be changed.")
        old = conn.execute("SELECT * FROM edition_design_tracking WHERE id=%s FOR UPDATE", (row_id,)).fetchone()
        if not old:
            raise TrackingConflict("This design could not be found. Your edits have been kept.")
        merged = dict(old)
        changed = {}
        for field, value in values.items():
            value = _value(field, value)
            current = _value(field, old.get(field))
            if value == current:
                continue
            if field == "bonus_paid_on" and not admin:
                raise PermissionError("Only an admin can change the Bonus paid date.")
            if current != _value(field, change["original"].get(field)):
                raise TrackingConflict("Someone changed the same cell. Your draft is kept; reload saved values before replacing it.")
            changed[field] = value
            merged[field] = value
        if not changed:
            return _row(old)
        if not merged.get("product_title") or len(merged["product_title"]) > 500:
            raise ValueError("Product must contain 1–500 characters.")
        if merged.get("date_created") is None:
            raise ValueError("Date created is required.")
        if len(merged.get("designed_by") or "") > 120 or len(merged.get("first_order") or "") > 120:
            raise ValueError("Designed by and First order must be 120 characters or fewer.")
        if "bonus_paid_on" in changed:
            paid = merged["bonus_paid_on"]
            if paid and not merged.get("first_order"):
                raise ValueError("Enter First order before marking its bonus paid.")
            # Non-bonus edits preserve the historical payment receipt unchanged.
            changed.update(paid_order_id=("manual:" + merged["first_order"]) if paid else None,
                           paid_order_name=merged["first_order"] if paid else None,
                           bonus_paid_by=actor_id if paid else None)
        # Columns come only from the allowlist and the fixed receipt keys above.
        setters = ",".join(key + "=%s" for key in changed)
        result = conn.execute("UPDATE edition_design_tracking SET " + setters +
            ",updated_by=%s,updated_at=now(),version=version+1 WHERE id=%s RETURNING " + ROW_COLUMNS,
            (*changed.values(),actor_id,row_id)).fetchone()
        return _row(result)
