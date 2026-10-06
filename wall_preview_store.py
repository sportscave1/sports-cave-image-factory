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
                'email_marketing_state', 'customer_folder', 'client_preview_id', 'session_id',
                'archive_sha256', 'confirmed_at', 'version', 'email_requested_at', 'email_sent_at', 'share_token',
                'share_revoked_at', 'purchased_at', 'order_id', 'order_number', 'attribution',
                'image_reuse_consent_at','image_reuse_consent_source','submitted_marketing_opt_in',
                'marketing_consent_at','marketing_consent_source','market_country_code','market_country_name',
                'marketing_consent_text','marketing_consent_version'}
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
    for table in ('wall_preview_events','wall_preview_email_jobs','wall_preview_customer_jobs','wall_preview_archive_jobs'):
        cur.execute("SELECT relrowsecurity FROM pg_class WHERE oid=to_regclass(%s)",('public.'+table,))
        if not (cur.fetchone() or {}).get('relrowsecurity'):
            issues.append(table+' RLS is not enabled')
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
            cur.execute("SELECT * FROM public.wall_previews WHERE customer_email=%s AND image_sha256=%s AND client_preview_id IS NULL", (customer_email, digest))
            row = cur.fetchone()
            return dict(row) if row else None


def summary(*, include_private=False):
    where = "WHERE NOT (COALESCE(attribution,'{}'::jsonb) ? 'inbox_deleted_at')" + ("" if include_private else " AND marketing_permission=TRUE")
    with _backend().connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout='4000ms'")
            cur.execute(f"""SELECT
                count(*) FILTER (WHERE status='new') AS new,
                count(*) FILTER (WHERE status='approved') AS approved,
                count(*) FILTER (WHERE status='used') AS used,
                count(*) FILTER (WHERE NOT marketing_permission) AS private
                ,count(*) AS total
                ,count(*) FILTER (WHERE confirmed_at IS NOT NULL) AS confirmed
                ,count(*) FILTER (WHERE email_requested_at IS NOT NULL) AS email_captured
                ,count(*) FILTER (WHERE purchased_at IS NOT NULL) AS purchased
                ,count(*) FILTER (WHERE EXISTS (SELECT 1 FROM public.wall_preview_events e
                    WHERE e.preview_id=wall_previews.id AND e.event_name='WallPreviewAddedToCart')) AS added_to_cart
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
                    ON CONFLICT (customer_email, image_sha256) WHERE client_preview_id IS NULL DO UPDATE SET
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


def list_previews(*, status="new", limit=DEFAULT_LIMIT, include_private=False, customer_search='', intent='all', start_date=None, end_date=None, product_id='', device_type='', capture_source='', cursor=None):
    clean_status = str(status or "new").strip().lower()
    if clean_status not in (*VALID_STATUSES, "all"):
        clean_status = "new"
    safe_limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    clauses = ["NOT (COALESCE(attribution,'{}'::jsonb) ? 'inbox_deleted_at')"]
    params = []
    for column, value, operator in (('received_at',start_date,'>='),('received_at',end_date,'<'),('product_id',product_id,'=')):
        if value:
            clauses.append(f"{column} {operator} %s")
            params.append(value)
    for column,value in (('device_type',device_type),('capture_source',capture_source)):
        if value:
            clauses.append(f"(SELECT filter_event.{column} FROM public.wall_preview_events filter_event WHERE (filter_event.preview_id=wall_previews.id OR filter_event.client_preview_id=wall_previews.client_preview_id) AND NULLIF(filter_event.{column},'') IS NOT NULL ORDER BY filter_event.occurred_at DESC,filter_event.id DESC LIMIT 1)=%s")
            params.append(value)
    if cursor:
        clauses.append('(received_at,id) < (%s::timestamptz,%s::uuid)')
        params.extend(cursor)
    if clean_status != "all":
        clauses.append("status = %s")
        params.append(clean_status)
    if not include_private:
        clauses.append("marketing_permission = TRUE")
    intent_clause = {'reuse_allowed':'marketing_permission=TRUE','confirmed':'confirmed_at IS NOT NULL','email_captured':'email_requested_at IS NOT NULL',
                     'purchased':'purchased_at IS NOT NULL',
                     'added_to_cart':"EXISTS (SELECT 1 FROM public.wall_preview_events e WHERE e.preview_id=wall_previews.id AND e.event_name='WallPreviewAddedToCart')"}
    if intent in intent_clause:
        clauses.append(intent_clause[intent])
    search = _clean(customer_search, 254).lower()
    if search:
        # Prefix filtering stays in SQL; customer-controlled wildcards are escaped.
        pattern = search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        clauses.append("(customer_email LIKE %s OR lower(customer_name) LIKE %s OR lower(product_title) LIKE %s)")
        params.extend((pattern, pattern, pattern))
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    params.append(safe_limit)
    with _backend().connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout='4000ms'")
            cur.execute(
                f"""
                SELECT *, (SELECT state FROM public.wall_preview_email_jobs j
                    WHERE j.preview_id=wall_previews.id AND j.kind='requested') AS email_job_state,
                EXISTS (SELECT 1 FROM public.wall_preview_events e
                    WHERE e.preview_id=wall_previews.id AND e.event_name='WallPreviewAddedToCart') AS added_to_cart
                FROM public.wall_previews
                {where}
                ORDER BY received_at DESC, id DESC
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


def get_preview(preview_id, *, include_private=False):
    with _backend().connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout='4000ms'")
            cur.execute("""SELECT * FROM public.wall_previews WHERE id=%s
                AND NOT (COALESCE(attribution,'{}'::jsonb) ? 'inbox_deleted_at')
                AND (%s OR marketing_permission)""", (preview_id, include_private))
            return dict(cur.fetchone() or {})


def delete_preview(preview_id, *, user, remove_asset):
    """Remove one image, retaining its analytics tombstone and exact-request identity.

    Shares the archive worker's parent-row lock. Provider failure leaves the inbox
    intact; a retry after a DB failure tolerates an already removed provider file.
    """
    import os_accounts
    import wall_preview_crm_store as crm
    import activity_log
    if not os_accounts.is_admin(user):
        raise PermissionError('Only an administrator can delete a preview.')
    with crm.transaction() as cur:
        cur.execute('SELECT * FROM public.wall_previews WHERE id=%s FOR UPDATE', (preview_id,))
        row = dict(cur.fetchone() or {})
        if not row or (row.get('attribution') or {}).get('inbox_deleted_at'):
            return False
        cur.execute("SELECT id FROM public.wall_preview_email_jobs WHERE preview_id=%s AND state='processing' LIMIT 1",(preview_id,))
        if cur.fetchone():
            raise WallPreviewStoreError('An image delivery is in progress. Retry deletion shortly.')
        if row.get('dropbox_path'):
            cur.execute("""SELECT id FROM public.wall_previews WHERE id<>%s
                AND ((dropbox_file_id<>'' AND dropbox_file_id=%s) OR dropbox_path=%s) LIMIT 1""",
                (preview_id,row['dropbox_file_id'],row['dropbox_path']))
            if cur.fetchone():
                raise WallPreviewStoreError('This asset is shared by another preview; deletion was stopped.')
            remove_asset(row)
        cur.execute("""UPDATE public.wall_previews SET
            attribution=COALESCE(attribution,'{}'::jsonb) || jsonb_build_object(
                'inbox_deleted_at',now(),'inbox_deleted_by',%s::text),
            share_revoked_at=now(),status='archived',dropbox_file_id='',dropbox_path='',updated_at=now()
            WHERE id=%s""", (str(user['id']),preview_id))
        cur.execute("""UPDATE public.wall_preview_archive_jobs SET state='failed',image=NULL,
            reason='admin_deleted',finished_at=now() WHERE preview_id=%s""", (preview_id,))
        cur.execute("""UPDATE public.wall_preview_email_jobs SET state='suppressed',reason='preview_deleted'
            WHERE preview_id=%s AND state='queued'""", (preview_id,))
    activity_log.record_activity_log('wall_preview_deleted','Social Media','Wall preview image deleted',
        entity_type='wall_preview',entity_id=str(preview_id),actor=str(user['id']),
        event_key='wall-preview-deleted:'+str(preview_id))
    return True
