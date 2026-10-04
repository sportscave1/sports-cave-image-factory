"""Persistence helpers for shopper-created See It On Your Wall previews."""

from __future__ import annotations

from datetime import datetime, timezone


VALID_STATUSES = ("new", "approved", "used", "archived")
DEFAULT_LIMIT = 36
MAX_LIMIT = 120


def schema_issues(cur):
    """Check the additive inbox schema before the main service opens its port."""
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='wall_previews'")
    columns = {row['column_name'] for row in cur.fetchall()}
    required = {'id', 'image_sha256', 'product_id', 'variant_id', 'product_handle',
                'product_title', 'product_url', 'frame_label', 'size_label',
                'measurement_unit', 'marketing_permission', 'status', 'dropbox_file_id',
                'dropbox_path', 'content_type', 'image_width', 'image_height', 'image_bytes',
                'save_count', 'received_at', 'last_saved_at', 'reviewed_by', 'reviewed_at', 'notes',
                'customer_email', 'customer_name', 'shopify_customer_id', 'identity_source',
                'email_marketing_state', 'customer_folder'}
    issues = ['wall_previews missing column: ' + name for name in sorted(required - columns)]
    cur.execute("SELECT indexname FROM pg_indexes WHERE schemaname='public' AND tablename='wall_previews'")
    indexes = {row['indexname'] for row in cur.fetchall()}
    for name in ('idx_wall_previews_customer_image', 'idx_wall_previews_customer_email_search',
                 'idx_wall_previews_customer_name_search', 'idx_wall_previews_status_received',
                 'idx_wall_previews_permission_received', 'idx_wall_previews_product_received'):
        if name not in indexes: issues.append('wall_previews missing index: ' + name)
    cur.execute("SELECT relrowsecurity FROM pg_class WHERE oid=to_regclass('public.wall_previews')")
    if not (cur.fetchone() or {}).get('relrowsecurity'):
        issues.append('wall_previews RLS is not enabled')
    return issues


class WallPreviewStoreError(RuntimeError):
    pass


def _backend():
    import supabase_backend

    return supabase_backend


def _clean(value, limit):
    return " ".join(str(value or "").split())[: int(limit)]


def find_preview(digest, *, customer_email=''):
    """Reuse the original archive on retries, including its original consent."""
    with _backend().connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout='4000ms'")
            cur.execute("SELECT * FROM public.wall_previews WHERE customer_email=%s AND image_sha256=%s", (customer_email, digest))
            row = cur.fetchone()
            return dict(row) if row else None


def summary(*, include_private=False):
    where = "" if include_private else "WHERE marketing_permission=TRUE"
    with _backend().connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout='4000ms'")
            cur.execute(f"""SELECT
                count(*) FILTER (WHERE status='new') AS new,
                count(*) FILTER (WHERE status='approved') AS approved,
                count(*) FILTER (WHERE status='used') AS used,
                count(*) FILTER (WHERE NOT marketing_permission) AS private
                FROM public.wall_previews {where}""")
            return dict(cur.fetchone() or {})


def record_preview(payload):
    payload = dict(payload or {})
    sha256 = _clean(payload.get("image_sha256"), 64).lower()
    dropbox_path = str(payload.get("dropbox_path") or "").strip()
    if len(sha256) != 64 or not dropbox_path:
        raise WallPreviewStoreError("Wall preview identity is incomplete.")

    with _backend().connect() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout='5000ms'")
                cur.execute(
                    """
                    INSERT INTO public.wall_previews (
                        image_sha256,
                        product_id,
                        variant_id,
                        product_handle,
                        product_title,
                        product_url,
                        frame_label,
                        size_label,
                        measurement_unit,
                        marketing_permission,
                        dropbox_file_id,
                        dropbox_path,
                        content_type,
                        image_width,
                        image_height,
                        image_bytes,
                        customer_email, customer_name, shopify_customer_id,
                        identity_source, email_marketing_state, customer_folder
                    )
                    VALUES (
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                        %s,%s,%s,%s,%s,%s
                    )
                    ON CONFLICT (customer_email, image_sha256) DO UPDATE SET
                        save_count = public.wall_previews.save_count + 1,
                        last_saved_at = now()
                    RETURNING *,
                        (xmax <> 0) AS duplicate
                    """,
                    (
                        sha256,
                        _clean(payload.get("product_id"), 80),
                        _clean(payload.get("variant_id"), 80),
                        _clean(payload.get("product_handle"), 255),
                        _clean(payload.get("product_title"), 500),
                        _clean(payload.get("product_url"), 1200),
                        _clean(payload.get("frame_label"), 120),
                        _clean(payload.get("size_label"), 160),
                        _clean(payload.get("measurement_unit"), 2),
                        bool(payload.get("marketing_permission")),
                        _clean(payload.get("dropbox_file_id"), 500),
                        dropbox_path[:1500],
                        _clean(payload.get("content_type") or "image/jpeg", 40),
                        int(payload.get("image_width") or 0),
                        int(payload.get("image_height") or 0),
                        int(payload.get("image_bytes") or 0),
                        _clean(payload.get('customer_email'), 254).lower(),
                        _clean(payload.get('customer_name'), 200),
                        _clean(payload.get('shopify_customer_id'), 100),
                        _clean(payload.get('identity_source'), 16),
                        _clean(payload.get('email_marketing_state') or 'UNKNOWN', 32),
                        _clean(payload.get('customer_folder'), 1500),
                    ),
                )
                row = dict(cur.fetchone() or {})
            conn.commit()
            return row
        except Exception:
            conn.rollback()
            raise


def list_previews(*, status="new", limit=DEFAULT_LIMIT, include_private=False, customer_search=''):
    clean_status = str(status or "new").strip().lower()
    if clean_status not in (*VALID_STATUSES, "all"):
        clean_status = "new"
    safe_limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    clauses = []
    params = []
    if clean_status != "all":
        clauses.append("status = %s")
        params.append(clean_status)
    if not include_private:
        clauses.append("marketing_permission = TRUE")
    search = _clean(customer_search, 254).lower()
    if search:
        # Prefix searches use the dedicated pattern indexes; no all-history scan
        # or wildcard injection from customer-controlled strings.
        pattern = search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        clauses.append("(customer_email LIKE %s OR lower(customer_name) LIKE %s)")
        params.extend((pattern, pattern))
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    params.append(safe_limit)
    with _backend().connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout='4000ms'")
            cur.execute(
                f"""
                SELECT *
                FROM public.wall_previews
                {where}
                ORDER BY received_at DESC
                LIMIT %s
                """,
                tuple(params),
            )
            return [dict(row or {}) for row in cur.fetchall() or ()]


def update_status(preview_id, status, *, actor_user_id=None, include_private=False):
    clean_status = str(status or "").strip().lower()
    if clean_status not in VALID_STATUSES:
        raise WallPreviewStoreError("Choose a valid wall preview status.")
    preview_id = str(preview_id or "").strip()
    if not preview_id:
        raise WallPreviewStoreError("Wall preview is required.")

    with _backend().connect() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout='4000ms'")
                if clean_status in {"approved", "used"} or not include_private:
                    cur.execute(
                        """
                        SELECT marketing_permission
                        FROM public.wall_previews
                        WHERE id = %s
                        FOR UPDATE
                        """,
                        (preview_id,),
                    )
                    existing = dict(cur.fetchone() or {})
                    if not existing:
                        raise WallPreviewStoreError("Wall preview was not found.")
                    if not bool(existing.get("marketing_permission")):
                        raise WallPreviewStoreError(
                            "This preview has not been approved by the shopper for social use."
                        )
                cur.execute(
                    """
                    UPDATE public.wall_previews
                    SET status = %s,
                        reviewed_by = %s,
                        reviewed_at = %s
                    WHERE id = %s
                    RETURNING *
                    """,
                    (
                        clean_status,
                        str(actor_user_id or "") or None,
                        datetime.now(timezone.utc),
                        preview_id,
                    ),
                )
                row = dict(cur.fetchone() or {})
                if not row:
                    raise WallPreviewStoreError("Wall preview was not found.")
            conn.commit()
            return row
        except Exception:
            conn.rollback()
            raise
