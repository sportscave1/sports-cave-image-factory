import csv
import gc
import io
import json
import os
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import shopify_sync
from certificate_service import certificate_id, generate_certificate_pdf, generate_certificate_preview_png
from services import r2_storage


BASE_DIR = Path(__file__).resolve().parent
CERTIFICATE_OUTPUT_DIR = BASE_DIR / "output" / "certificates"
PSD_MASTER_FOLDER_SETTING_KEY = "psd_master_folder_url"
LAST_SUCCESSFUL_ORDER_SYNC_KEY = "last_successful_order_sync_at"
LAST_ATTEMPTED_ORDER_SYNC_KEY = "last_attempted_order_sync_at"
LAST_SUCCESSFUL_ORDER_FETCH_KEY = "last_successful_order_fetch_at"
LAST_ORDER_FETCH_STATUS_KEY = "last_order_fetch_status"
LAST_ORDER_FETCH_DURATION_KEY = "last_order_fetch_duration_ms"
LAST_ORDERS_IMPORTED_COUNT_KEY = "last_orders_imported_count"
LAST_ASSIGNMENTS_CREATED_COUNT_KEY = "last_assignments_created_count"
EDITION_TRACKING_START_KEY = "edition_tracking_start_at"
LAST_SUCCESSFUL_PRODUCT_SYNC_KEY = "last_successful_product_sync_at"
LAST_ATTEMPTED_PRODUCT_SYNC_KEY = "last_attempted_product_sync_at"
SYNC_LOOKBACK_BUFFER_KEY = "sync_lookback_buffer_minutes"
DEFAULT_SYNC_LOOKBACK_BUFFER_MINUTES = 10
DEFAULT_INITIAL_ORDER_BOOTSTRAP_DAYS = 30
DEFAULT_INITIAL_ORDER_ASSIGNMENT_WINDOW_DAYS = 7
DEFAULT_INCREMENTAL_ORDER_FETCH_LIMIT = 100
DEFAULT_LATEST_PAID_ORDER_FETCH_LIMIT = 50
DEFAULT_LATEST_PAID_ORDER_LOOKBACK_DAYS = 14
DEFAULT_CURSORLESS_ORDER_LOOKBACK_HOURS = 48
DATETIME_MAX_UTC = datetime.max.replace(tzinfo=timezone.utc)
DEFAULT_PSD_MASTER_FOLDER_SETTING = {
    "url": "https://drive.google.com/drive/folders/1UCs_EsyjVXZUNclAfnmO7y2x7rKutwhH",
    "name": "Sports Cave PSD Master Folder",
}
HISTORICAL_ORDER_STATUS = "Historical Order"
REPAIRABLE_ORDER_LINE_STATUSES = ("Error", "Product Not Found", "Needs Edition Setup")
MISSING_EDITION_REPAIRABLE_STATUSES = REPAIRABLE_ORDER_LINE_STATUSES + ("Needs Edition", "Historical Order")
HISTORICAL_ORDER_NOTE = (
    "Paid before edition tracking started. Run Historical Order Backfill if this order should receive editions."
)
DATABASE_URL_ENV_KEYS = (
    "DATABASE_URL",
    "SUPABASE_DATABASE_URL",
    "SUPABASE_DB_URL",
    "POSTGRES_URL",
    "POSTGRES_PRISMA_URL",
    "POSTGRES_URL_NON_POOLING",
    "DATABASE_PRIVATE_URL",
    "DATABASE_PUBLIC_URL",
    "RENDER_DATABASE_URL",
)
REQUIRED_DATABASE_ENV_VARS = ("DATABASE_URL",)
_SCHEMA_READY = False
_ORDER_READ_SCHEMA_READY = False
_SCHEMA_LOCK = threading.Lock()
_LAST_DATABASE_STATUS = {}
DEFAULT_EDITION_NAME = "Original Edition"
ACTIVE_RUN_STATUS = "active"
SOLD_OUT_RUN_STATUS = "sold_out"
ARCHIVED_RUN_STATUS = "archived"
INACTIVE_RUN_STATUS = "inactive"
EDITION_RUN_STATUSES = {
    ACTIVE_RUN_STATUS,
    SOLD_OUT_RUN_STATUS,
    ARCHIVED_RUN_STATUS,
    INACTIVE_RUN_STATUS,
}
PROMISED_EDITION_NUMBER_KEYS = {
    "edition",
    "edition_number",
    "edition number",
    "edition no",
    "edition no.",
    "edition_number_promised",
    "edition number promised",
    "promised_edition_number",
    "promised edition number",
    "sports_cave_edition_number",
    "sports cave edition number",
    "customer_promised_edition_number",
    "customer promised edition number",
}
PROMISED_EDITION_TOTAL_KEYS = {
    "edition_total",
    "edition total",
    "edition_limit",
    "edition limit",
    "sports_cave_edition_total",
    "sports cave edition total",
}
KNOWN_MISSING_EDITION_REPAIRS = (
    {
        "order_name": "#SC2848",
        "customer_name": "Paul Grubb",
        "product_title": "Legends Never Die Messi vs Ronaldo Wall Art",
        "edition_number": 42,
        "edition_total": 100,
    },
    {
        "order_name": "#SC2849",
        "customer_name": "Elle Hosking",
        "product_title": "Greg Murphy Lap of the Gods Wall Art",
        "edition_number": 17,
        "edition_total": 100,
    },
    {
        "order_name": "#SC2849",
        "customer_name": "Elle Hosking",
        "product_title": "Peter Brock Tribute Wall Art",
        "edition_number": 67,
        "edition_total": 100,
    },
    {
        "order_name": "#SC2850",
        "customer_name": "Daniel Brearley",
        "product_title": "Lionel Messi The Final Crown Wall Art",
        "edition_number": 30,
        "edition_total": 100,
    },
    {
        "order_name": "#SC2851",
        "customer_name": "Scott Tasler",
        "product_title": "Legends Never Die Messi vs Ronaldo Wall Art",
        "edition_number": 43,
        "edition_total": 100,
    },
    {
        "order_name": "#SC2852",
        "customer_name": "Marco Da Cruz",
        "product_title": "Legends Never Die Messi vs Ronaldo Wall Art",
        "edition_number": 44,
        "edition_total": 100,
    },
    {
        "order_name": "#SC2853",
        "customer_name": "Angelo Hiotis",
        "product_title": "Legends Never Die Messi vs Ronaldo Wall Art",
        "edition_number": 45,
        "edition_total": 100,
    },
)

ASSET_TYPES = (
    "google_drive_folder",
    "psd_master_file",
    "certificate_template",
    "black_frame_image",
    "oak_frame_image",
    "white_frame_image",
    "unframed_image",
    "lifestyle_image",
    "shopify_cdn_file",
    "prodigi_link",
)

ASSET_LABELS = {
    "google_drive_folder": "Google Drive Folder",
    "psd_master_file": "PSD Master File",
    "certificate_template": "Certificate Template",
    "black_frame_image": "Black Frame Image",
    "oak_frame_image": "Oak Frame Image",
    "white_frame_image": "White Frame Image",
    "unframed_image": "Unframed Image",
    "lifestyle_image": "Lifestyle Image",
    "shopify_cdn_file": "Shopify CDN File",
    "prodigi_link": "Prodigi",
}


class SupabaseNotConfigured(RuntimeError):
    pass


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def utc_now_datetime():
    return datetime.now(timezone.utc).replace(microsecond=0)


def _parse_datetime(value):
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _datetime_to_setting(value):
    parsed = _parse_datetime(value) or utc_now_datetime()
    return parsed.isoformat(timespec="seconds").replace("+00:00", "Z")


def _datetime_to_shopify_query(value):
    parsed = _parse_datetime(value) or utc_now_datetime()
    return parsed.isoformat(timespec="seconds").replace("+00:00", "Z")


def _order_effective_datetime(order):
    return (
        _parse_datetime(order.get("processed_at"))
        or _parse_datetime(order.get("paid_at"))
        or _parse_datetime(order.get("created_at"))
    )


def _allocation_datetime_sort_value(value):
    return _parse_datetime(value) or DATETIME_MAX_UTC


def _numeric_sort_value(value):
    digits = re.findall(r"\d+", str(value or ""))
    return int(digits[-1]) if digits else 0


def _line_item_position(line_item, fallback):
    for key in ("position", "line_item_position", "current_position", "index"):
        try:
            value = int(line_item.get(key) or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value
    return fallback


def _line_item_sort_identity(line_item):
    return str(
        line_item.get("shopify_line_item_id")
        or line_item.get("line_item_id")
        or line_item.get("id")
        or ""
    )


def order_allocation_sort_key(order):
    """Stable oldest-first key for edition allocation, independent of API/display order."""
    line_items = order.get("line_items") or [{}]
    line_keys = []
    for fallback_position, line_item in enumerate(line_items, start=1):
        if not isinstance(line_item, dict):
            line_item = {}
        quantity = max(_int_value(line_item.get("quantity"), 1), 1)
        for quantity_index in range(1, quantity + 1):
            line_keys.append(
                (
                    _line_item_position(line_item, fallback_position),
                    _line_item_sort_identity(line_item),
                    quantity_index,
                )
            )
    line_key = min(line_keys or [(1, "", 1)])
    return (
        _allocation_datetime_sort_value(order.get("created_at") or order.get("createdAt")),
        _allocation_datetime_sort_value(order.get("processed_at") or order.get("processedAt") or order.get("paid_at")),
        _numeric_sort_value(order.get("order_number") or order.get("shopify_order_number") or order.get("order_name")),
        str(order.get("shopify_order_id") or order.get("id") or ""),
        *line_key,
    )


def get_database_url_source():
    for key in DATABASE_URL_ENV_KEYS:
        if os.getenv(key, "").strip():
            return key
    return ""


def get_database_url():
    for key in DATABASE_URL_ENV_KEYS:
        value = os.getenv(key, "").strip()
        if value:
            return value
    return ""


def is_configured():
    return bool(get_database_url())


def database_mode_diagnostic():
    """Return safe database mode details without exposing connection strings."""
    source = get_database_url_source()
    if source:
        return {
            "mode": "Supabase/Postgres configured",
            "configured": True,
            "url_source": source,
            "required_env_vars": REQUIRED_DATABASE_ENV_VARS,
            "accepted_env_vars": DATABASE_URL_ENV_KEYS,
            "host_reference": safe_database_reference(),
            "warning": "",
        }
    return {
        "mode": "Local/fallback only",
        "configured": False,
        "url_source": "",
        "required_env_vars": REQUIRED_DATABASE_ENV_VARS,
        "accepted_env_vars": DATABASE_URL_ENV_KEYS,
        "host_reference": "Local/fallback only",
        "warning": "DATABASE_URL missing. Set DATABASE_URL for the durable Supabase/Postgres ledger.",
    }


def safe_database_reference():
    url = get_database_url()
    if not url:
        return "Local SQLite fallback"
    parsed = urlparse(url)
    return parsed.hostname or "Configured Postgres host"


def _safe_error_type(error):
    return error.__class__.__name__ if error else ""


def _database_url_with_ssl():
    url = get_database_url()
    if not url:
        raise SupabaseNotConfigured(
            "No Supabase/Postgres database URL is configured. Set DATABASE_URL, "
            "SUPABASE_DATABASE_URL, or POSTGRES_URL in Render."
        )
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.setdefault("sslmode", "require")
    query.setdefault("connect_timeout", "8")
    return urlunparse(parsed._replace(query=urlencode(query)))


def connect():
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as error:
        raise RuntimeError(
            "Postgres support is not installed. Add psycopg[binary] to requirements.txt."
        ) from error
    database_url = _database_url_with_ssl()
    return psycopg.connect(
        database_url,
        row_factory=dict_row,
        connect_timeout=8,
        prepare_threshold=None,
        options="-c statement_timeout=8000 -c idle_in_transaction_session_timeout=8000",
    )


def database_status(run_schema_check=True):
    """Return safe database diagnostics without exposing DATABASE_URL credentials."""
    global _LAST_DATABASE_STATUS
    checked_at = utc_now()
    mode = database_mode_diagnostic()
    if not is_configured():
        status = {
            "mode": mode["mode"],
            "configured": False,
            "connected": False,
            "tables_ready": False,
            "host_reference": mode["host_reference"],
            "url_source": "",
            "required_env_vars": mode["required_env_vars"],
            "accepted_env_vars": mode["accepted_env_vars"],
            "checked_at": checked_at,
            "connect_time_seconds": 0.0,
            "migration_time_seconds": 0.0,
            "error_type": "",
            "warning": mode["warning"],
        }
        _LAST_DATABASE_STATUS = status
        return status

    connected = False
    tables_ready = False
    connect_time = 0.0
    migration_time = 0.0
    error_type = ""
    try:
        started = time.perf_counter()
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 AS ok")
                connected = bool((cur.fetchone() or {}).get("ok"))
        connect_time = time.perf_counter() - started
        if run_schema_check:
            migration_started = time.perf_counter()
            ensure_schema()
            migration_time = time.perf_counter() - migration_started
            tables_ready = True
        else:
            tables_ready = _SCHEMA_READY
    except Exception as error:
        error_type = _safe_error_type(error)
    print(
        "PERF DB "
        f"mode=postgres connected={str(connected).lower()} "
        f"connect_time={connect_time:.3f}s migration_time={migration_time:.3f}s",
        flush=True,
    )
    status = {
        "mode": mode["mode"],
        "configured": True,
        "connected": connected,
        "tables_ready": tables_ready,
        "host_reference": safe_database_reference(),
        "url_source": get_database_url_source(),
        "required_env_vars": mode["required_env_vars"],
        "accepted_env_vars": mode["accepted_env_vars"],
        "checked_at": checked_at,
        "connect_time_seconds": round(connect_time, 3),
        "migration_time_seconds": round(migration_time, 3),
        "error_type": error_type,
        "warning": "",
    }
    _LAST_DATABASE_STATUS = status
    return status


def json_dumps(value):
    return json.dumps(value or {}, ensure_ascii=True, default=str)


def table_exists(cur, table_name):
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = %s
        ) AS exists
        """,
        (table_name,),
    )
    return bool((cur.fetchone() or {}).get("exists"))


def column_exists(cur, table_name, column_name):
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema='public'
              AND table_name=%s
              AND column_name=%s
        ) AS exists
        """,
        (table_name, column_name),
    )
    return bool((cur.fetchone() or {}).get("exists"))


def _safe_create_index(cur, sql, index_name):
    try:
        cur.execute("SAVEPOINT sports_cave_index")
        cur.execute(sql)
        cur.execute("RELEASE SAVEPOINT sports_cave_index")
    except Exception as error:
        cur.execute("ROLLBACK TO SAVEPOINT sports_cave_index")
        cur.execute("RELEASE SAVEPOINT sports_cave_index")
        print(
            f"WARN DB index skipped index={index_name} error_type={_safe_error_type(error)}",
            flush=True,
        )


def _ensure_schema_uncached():
    if not is_configured():
        raise SupabaseNotConfigured(
            "No Supabase/Postgres database URL is configured. Set DATABASE_URL, "
            "SUPABASE_DATABASE_URL, or POSTGRES_URL in Render."
        )
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS shopify_products (
                    shopify_product_id TEXT PRIMARY KEY,
                    legacy_resource_id TEXT,
                    title TEXT,
                    handle TEXT UNIQUE,
                    status TEXT,
                    vendor TEXT,
                    product_type TEXT,
                    online_store_url TEXT,
                    admin_url TEXT,
                    image_url TEXT,
                    raw_json JSONB DEFAULT '{}'::jsonb,
                    synced_at TIMESTAMPTZ DEFAULT now(),
                    updated_at TIMESTAMPTZ DEFAULT now()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS shopify_variants (
                    shopify_variant_id TEXT PRIMARY KEY,
                    shopify_product_id TEXT,
                    legacy_resource_id TEXT,
                    title TEXT,
                    sku TEXT,
                    price TEXT,
                    raw_json JSONB DEFAULT '{}'::jsonb,
                    synced_at TIMESTAMPTZ DEFAULT now()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS edition_products (
                    id BIGSERIAL PRIMARY KEY,
                    shopify_product_id TEXT,
                    shopify_handle TEXT UNIQUE NOT NULL,
                    product_title TEXT,
                    edition_total INTEGER DEFAULT 100,
                    next_edition_number INTEGER DEFAULT 1,
                    active BOOLEAN DEFAULT TRUE,
                    sold_out BOOLEAN DEFAULT FALSE,
                    updated_at TIMESTAMPTZ DEFAULT now()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS shopify_customers (
                    shopify_customer_id TEXT PRIMARY KEY,
                    customer_name TEXT,
                    email TEXT,
                    raw_json JSONB DEFAULT '{}'::jsonb,
                    updated_at TIMESTAMPTZ DEFAULT now()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS shopify_orders (
                    shopify_order_id TEXT PRIMARY KEY,
                    legacy_resource_id TEXT,
                    order_name TEXT,
                    order_number TEXT,
                    admin_url TEXT,
                    customer_id TEXT,
                    customer_name TEXT,
                    customer_email TEXT,
                    financial_status TEXT,
                    fulfillment_status TEXT,
                    total_price TEXT,
                    currency TEXT,
                    created_at TIMESTAMPTZ,
                    remote_updated_at TIMESTAMPTZ,
                    processed_at TIMESTAMPTZ,
                    cancelled_at TIMESTAMPTZ,
                    raw_json JSONB DEFAULT '{}'::jsonb,
                    synced_at TIMESTAMPTZ DEFAULT now()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS shopify_order_lines (
                    id BIGSERIAL PRIMARY KEY,
                    shopify_line_item_id TEXT UNIQUE,
                    shopify_order_id TEXT,
                    shopify_product_id TEXT,
                    shopify_handle TEXT,
                    product_title TEXT,
                    variant_title TEXT,
                    sku TEXT,
                    quantity INTEGER DEFAULT 1,
                    assignment_status TEXT DEFAULT 'Needs Edition',
                    last_error TEXT DEFAULT '',
                    raw_json JSONB DEFAULT '{}'::jsonb,
                    synced_at TIMESTAMPTZ DEFAULT now(),
                    updated_at TIMESTAMPTZ DEFAULT now()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS edition_orders (
                    id BIGSERIAL PRIMARY KEY,
                    shopify_customer_id TEXT,
                    shopify_order_id TEXT,
                    shopify_order_name TEXT,
                    shopify_line_item_id TEXT,
                    shopify_product_id TEXT,
                    shopify_variant_id TEXT,
                    shopify_handle TEXT,
                    product_handle TEXT,
                    product_title TEXT,
                    variant_title TEXT,
                    sku TEXT,
                    customer_name TEXT,
                    customer_email TEXT,
                    edition_number INTEGER,
                    edition_total INTEGER,
                    edition_display TEXT,
                    allocation_index INTEGER DEFAULT 1,
                    assigned_at TIMESTAMPTZ DEFAULT now(),
                    certificate_status TEXT DEFAULT 'Certificate Missing',
                    certificate_id TEXT,
                    shopify_file_id TEXT,
                    shopify_file_status TEXT,
                    certificate_file_url TEXT,
                    purchase_date TIMESTAMPTZ,
                    source TEXT DEFAULT 'sports_cave_os',
                    manual_override BOOLEAN DEFAULT FALSE,
                    override_old_edition_number INTEGER,
                    override_new_edition_number INTEGER,
                    override_timestamp TIMESTAMPTZ,
                    override_reason TEXT,
                    created_at TIMESTAMPTZ DEFAULT now(),
                    updated_at TIMESTAMPTZ DEFAULT now(),
                    UNIQUE (shopify_line_item_id, allocation_index)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS certificates (
                    id BIGSERIAL PRIMARY KEY,
                    edition_order_id TEXT UNIQUE,
                    related_edition_order_id uuid NULL,
                    shopify_customer_id TEXT,
                    customer_email TEXT,
                    customer_name TEXT,
                    shopify_order_id TEXT,
                    shopify_order_name TEXT,
                    shopify_line_item_id TEXT,
                    shopify_handle TEXT,
                    product_handle TEXT,
                    shopify_product_id TEXT,
                    shopify_variant_id TEXT,
                    product_title TEXT,
                    variant_title TEXT,
                    certificate_id TEXT,
                    edition_number INTEGER,
                    edition_total INTEGER,
                    edition_limit INTEGER,
                    edition_display TEXT,
                    display_edition TEXT,
                    line_item_unit_index INTEGER DEFAULT 1,
                    pdf_filename TEXT,
                    local_file_path TEXT,
                    shopify_file_id TEXT,
                    shopify_file_status TEXT,
                    shopify_file_url TEXT,
                    certificate_file_url TEXT,
                    certificate_pdf_url TEXT,
                    certificate_print_jpg_url TEXT,
                    certificate_preview_image_url TEXT,
                    shopify_pdf_file_id TEXT,
                    shopify_print_jpg_file_id TEXT,
                    shopify_preview_file_id TEXT,
                    asset_sync_status TEXT DEFAULT 'pending',
                    asset_sync_error TEXT,
                    certificate_shopify_file_id TEXT,
                    certificate_status TEXT DEFAULT 'Processing',
                    sync_status TEXT DEFAULT 'pending',
                    last_sync_error TEXT,
                    purchase_date TIMESTAMPTZ,
                    source TEXT DEFAULT 'sports_cave_os',
                    generated_at TIMESTAMPTZ DEFAULT now(),
                    status TEXT DEFAULT 'Local PDF',
                    created_at TIMESTAMPTZ DEFAULT now(),
                    updated_at TIMESTAMPTZ DEFAULT now()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS product_assets (
                    id BIGSERIAL PRIMARY KEY,
                    shopify_handle TEXT,
                    asset_type TEXT,
                    asset_name TEXT,
                    asset_url TEXT,
                    google_drive_file_id TEXT,
                    google_drive_file_url TEXT,
                    notes TEXT,
                    is_primary BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMPTZ DEFAULT now(),
                    updated_at TIMESTAMPTZ DEFAULT now(),
                    UNIQUE (shopify_handle, asset_type)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS prodigi_dispatch_rows (
                    row_id TEXT PRIMARY KEY,
                    shopify_order_id TEXT,
                    shopify_order_name TEXT,
                    shopify_order_number TEXT,
                    shopify_line_item_id TEXT,
                    customer_name TEXT,
                    product_title TEXT,
                    shopify_variant_title TEXT,
                    edition_number INTEGER,
                    sports_cave_frame TEXT,
                    sports_cave_size TEXT,
                    prodigi_product_name TEXT,
                    prodigi_product_code TEXT,
                    prodigi_frame_colour TEXT,
                    prodigi_status TEXT,
                    date_sent_to_prodigi TEXT,
                    submitted_at TIMESTAMPTZ,
                    qa_confirmed BOOLEAN DEFAULT FALSE,
                    qa_notes TEXT,
                    notes TEXT,
                    source TEXT DEFAULT 'prodigi_dispatch_log',
                    row_json JSONB DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ DEFAULT now(),
                    updated_at TIMESTAMPTZ DEFAULT now()
                )
                """
            )
            cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
            cur.execute(
                """
                SELECT data_type
                FROM information_schema.columns
                WHERE table_schema='public'
                  AND table_name='edition_products'
                  AND column_name='id'
                """
            )
            edition_product_id_type = (cur.fetchone() or {}).get("data_type")
            if edition_product_id_type == "uuid":
                edition_product_fk_type = "UUID"
            elif edition_product_id_type == "integer":
                edition_product_fk_type = "INTEGER"
            elif edition_product_id_type == "bigint":
                edition_product_fk_type = "BIGINT"
            else:
                edition_product_fk_type = "TEXT"
            edition_product_fk = (
                " REFERENCES edition_products(id) ON DELETE SET NULL"
                if edition_product_fk_type != "TEXT"
                else ""
            )
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS edition_runs (
                    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                    edition_product_id {edition_product_fk_type}{edition_product_fk},
                    shopify_product_id TEXT,
                    shopify_handle TEXT NOT NULL,
                    product_title TEXT,
                    edition_name TEXT DEFAULT '{DEFAULT_EDITION_NAME}',
                    edition_total INTEGER DEFAULT 100,
                    next_edition_number INTEGER DEFAULT 1,
                    status TEXT DEFAULT '{ACTIVE_RUN_STATUS}',
                    started_at TIMESTAMPTZ DEFAULT now(),
                    archived_at TIMESTAMPTZ NULL,
                    notes TEXT,
                    created_at TIMESTAMPTZ DEFAULT now(),
                    updated_at TIMESTAMPTZ DEFAULT now()
                )
                """
            )
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS edition_adjustments (
                    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                    edition_product_id {edition_product_fk_type}{edition_product_fk},
                    edition_run_id uuid NULL REFERENCES edition_runs(id) ON DELETE SET NULL,
                    shopify_product_id TEXT,
                    shopify_handle TEXT,
                    old_next_edition_number INTEGER,
                    new_next_edition_number INTEGER,
                    old_edition_total INTEGER,
                    new_edition_total INTEGER,
                    reason TEXT,
                    source TEXT DEFAULT 'manual_app',
                    created_at TIMESTAMPTZ DEFAULT now()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS file_assets (
                    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                    asset_type TEXT NOT NULL,
                    bucket TEXT NOT NULL,
                    object_key TEXT NOT NULL,
                    filename TEXT,
                    mime_type TEXT,
                    size_bytes BIGINT,
                    related_shopify_product_id TEXT,
                    related_shopify_order_id TEXT,
                    related_shopify_handle TEXT,
                    related_edition_order_id uuid NULL,
                    source TEXT DEFAULT 'r2',
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMPTZ DEFAULT now(),
                    updated_at TIMESTAMPTZ DEFAULT now(),
                    UNIQUE (bucket, object_key)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value JSONB DEFAULT '{}'::jsonb,
                    updated_at TIMESTAMPTZ DEFAULT now()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS app_sync_state (
                    key TEXT PRIMARY KEY,
                    value JSONB DEFAULT '{}'::jsonb,
                    cursor_value TEXT,
                    last_success_at TIMESTAMPTZ,
                    last_attempt_at TIMESTAMPTZ,
                    status TEXT DEFAULT 'idle',
                    error_message TEXT,
                    updated_at TIMESTAMPTZ DEFAULT now()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id BIGSERIAL PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    entity_type TEXT,
                    entity_id TEXT,
                    shopify_order_id TEXT,
                    shopify_line_item_id TEXT,
                    shopify_handle TEXT,
                    old_value JSONB DEFAULT '{}'::jsonb,
                    new_value JSONB DEFAULT '{}'::jsonb,
                    reason TEXT,
                    actor TEXT DEFAULT 'sports_cave_os',
                    source TEXT DEFAULT 'sports_cave_os',
                    created_at TIMESTAMPTZ DEFAULT now()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS webhook_events (
                    webhook_id TEXT PRIMARY KEY,
                    topic TEXT,
                    status TEXT,
                    received_at TIMESTAMPTZ DEFAULT now(),
                    payload JSONB DEFAULT '{}'::jsonb,
                    error_message TEXT
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS sync_runs (
                    id BIGSERIAL PRIMARY KEY,
                    sync_type TEXT,
                    status TEXT,
                    started_at TIMESTAMPTZ DEFAULT now(),
                    completed_at TIMESTAMPTZ,
                    records_seen INTEGER DEFAULT 0,
                    records_processed INTEGER DEFAULT 0,
                    error_message TEXT
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS app_errors (
                    id BIGSERIAL PRIMARY KEY,
                    error_type TEXT,
                    message TEXT,
                    context JSONB DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ DEFAULT now()
                )
                """
            )

            additive_columns = {
                "shopify_products": (
                    ("shopify_product_gid", "TEXT"),
                    ("legacy_resource_id", "TEXT"),
                    ("title", "TEXT"),
                    ("handle", "TEXT"),
                    ("status", "TEXT"),
                    ("vendor", "TEXT"),
                    ("product_type", "TEXT"),
                    ("online_store_url", "TEXT"),
                    ("admin_url", "TEXT"),
                    ("image_url", "TEXT"),
                    ("featured_image_url", "TEXT"),
                    ("raw_json", "JSONB DEFAULT '{}'::jsonb"),
                    ("raw", "JSONB DEFAULT '{}'::jsonb"),
                    ("synced_at", "TIMESTAMPTZ DEFAULT now()"),
                    ("updated_at", "TIMESTAMPTZ DEFAULT now()"),
                ),
                "shopify_variants": (
                    ("shopify_product_id", "TEXT"),
                    ("legacy_resource_id", "TEXT"),
                    ("title", "TEXT"),
                    ("sku", "TEXT"),
                    ("price", "TEXT"),
                    ("raw_json", "JSONB DEFAULT '{}'::jsonb"),
                    ("synced_at", "TIMESTAMPTZ DEFAULT now()"),
                ),
                "edition_products": (
                    ("shopify_product_id", "TEXT"),
                    ("shopify_product_gid", "TEXT"),
                    ("shopify_handle", "TEXT"),
                    ("product_title", "TEXT"),
                    ("edition_total", "INTEGER DEFAULT 100"),
                    ("next_edition_number", "INTEGER DEFAULT 1"),
                    ("last_assigned_edition", "INTEGER DEFAULT 0"),
                    ("sold_count", "INTEGER DEFAULT 0"),
                    ("remaining_count", "INTEGER DEFAULT 100"),
                    ("edition_status", "TEXT DEFAULT 'limited_release'"),
                    ("edition_display_text", "TEXT"),
                    ("active_edition_run_id", "UUID"),
                    ("edition_name", f"TEXT DEFAULT '{DEFAULT_EDITION_NAME}'"),
                    ("allow_counter_history_override", "BOOLEAN DEFAULT FALSE"),
                    ("metafields_synced_at", "TIMESTAMPTZ"),
                    ("metafields_sync_status", "TEXT DEFAULT 'Never Synced'"),
                    ("last_metafield_error", "TEXT"),
                    ("active", "BOOLEAN DEFAULT TRUE"),
                    ("is_active", "BOOLEAN DEFAULT TRUE"),
                    ("sold_out", "BOOLEAN DEFAULT FALSE"),
                    ("is_sold_out", "BOOLEAN DEFAULT FALSE"),
                    ("featured_image_url", "TEXT"),
                    ("raw", "JSONB DEFAULT '{}'::jsonb"),
                    ("synced_at", "TIMESTAMPTZ DEFAULT now()"),
                    ("updated_at", "TIMESTAMPTZ DEFAULT now()"),
                ),
                "shopify_customers": (
                    ("customer_name", "TEXT"),
                    ("email", "TEXT"),
                    ("first_name", "TEXT"),
                    ("last_name", "TEXT"),
                    ("raw_json", "JSONB DEFAULT '{}'::jsonb"),
                    ("raw", "JSONB DEFAULT '{}'::jsonb"),
                    ("updated_at", "TIMESTAMPTZ DEFAULT now()"),
                ),
                "shopify_orders": (
                    ("legacy_resource_id", "TEXT"),
                    ("order_name", "TEXT"),
                    ("shopify_order_name", "TEXT"),
                    ("order_number", "TEXT"),
                    ("shopify_order_number", "TEXT"),
                    ("admin_url", "TEXT"),
                    ("customer_id", "TEXT"),
                    ("shopify_customer_id", "TEXT"),
                    ("customer_name", "TEXT"),
                    ("customer_email", "TEXT"),
                    ("email", "TEXT"),
                    ("financial_status", "TEXT"),
                    ("fulfillment_status", "TEXT"),
                    ("total_price", "TEXT"),
                    ("currency", "TEXT"),
                    ("created_at", "TIMESTAMPTZ"),
                    ("remote_updated_at", "TIMESTAMPTZ"),
                    ("processed_at", "TIMESTAMPTZ"),
                    ("cancelled_at", "TIMESTAMPTZ"),
                    ("raw_json", "JSONB DEFAULT '{}'::jsonb"),
                    ("raw", "JSONB DEFAULT '{}'::jsonb"),
                    ("synced_at", "TIMESTAMPTZ DEFAULT now()"),
                    ("updated_at", "TIMESTAMPTZ DEFAULT now()"),
                ),
                "shopify_order_lines": (
                    ("shopify_order_id", "TEXT"),
                    ("shopify_product_id", "TEXT"),
                    ("shopify_handle", "TEXT"),
                    ("product_title", "TEXT"),
                    ("variant_title", "TEXT"),
                    ("sku", "TEXT"),
                    ("quantity", "INTEGER DEFAULT 1"),
                    ("assignment_status", "TEXT DEFAULT 'Needs Edition'"),
                    ("last_error", "TEXT DEFAULT ''"),
                    ("raw_json", "JSONB DEFAULT '{}'::jsonb"),
                    ("synced_at", "TIMESTAMPTZ DEFAULT now()"),
                    ("updated_at", "TIMESTAMPTZ DEFAULT now()"),
                ),
                "edition_orders": (
                    ("shopify_customer_id", "TEXT"),
                    ("shopify_order_id", "TEXT"),
                    ("shopify_order_name", "TEXT"),
                    ("shopify_line_item_id", "TEXT"),
                    ("shopify_product_id", "TEXT"),
                    ("shopify_variant_id", "TEXT"),
                    ("shopify_handle", "TEXT"),
                    ("product_handle", "TEXT"),
                    ("product_title", "TEXT"),
                    ("variant_title", "TEXT"),
                    ("sku", "TEXT"),
                    ("customer_name", "TEXT"),
                    ("customer_email", "TEXT"),
                    ("shopify_customer_name", "TEXT"),
                    ("shopify_customer_email", "TEXT"),
                    ("edition_number", "INTEGER"),
                    ("edition_total", "INTEGER"),
                    ("edition_display", "TEXT"),
                    ("allocation_index", "INTEGER DEFAULT 1"),
                    ("quantity", "INTEGER DEFAULT 1"),
                    ("status", "TEXT DEFAULT 'assigned'"),
                    ("assigned_at", "TIMESTAMPTZ DEFAULT now()"),
                    ("certificate_status", "TEXT DEFAULT 'Certificate Missing'"),
                    ("certificate_id", "TEXT"),
                    ("shopify_file_id", "TEXT"),
                    ("shopify_file_status", "TEXT"),
                    ("certificate_file_url", "TEXT"),
                    ("purchase_date", "TIMESTAMPTZ"),
                    ("source", "TEXT DEFAULT 'sports_cave_os'"),
                    ("manual_override", "BOOLEAN DEFAULT FALSE"),
                    ("override_old_edition_number", "INTEGER"),
                    ("override_new_edition_number", "INTEGER"),
                    ("override_timestamp", "TIMESTAMPTZ"),
                    ("override_reason", "TEXT"),
                    ("created_at", "TIMESTAMPTZ DEFAULT now()"),
                    ("edition_run_id", "UUID"),
                    ("edition_name", "TEXT"),
                    ("certificate_r2_bucket", "TEXT"),
                    ("certificate_r2_key", "TEXT"),
                    ("certificate_preview_r2_bucket", "TEXT"),
                    ("certificate_preview_r2_key", "TEXT"),
                    ("updated_at", "TIMESTAMPTZ DEFAULT now()"),
                ),
                "certificates": (
                    ("edition_order_id", "TEXT"),
                    ("related_edition_order_id", "uuid NULL"),
                    ("shopify_customer_id", "TEXT"),
                    ("customer_email", "TEXT"),
                    ("customer_name", "TEXT"),
                    ("shopify_order_id", "TEXT"),
                    ("shopify_order_name", "TEXT"),
                    ("shopify_line_item_id", "TEXT"),
                    ("shopify_handle", "TEXT"),
                    ("product_handle", "TEXT"),
                    ("shopify_product_id", "TEXT"),
                    ("shopify_variant_id", "TEXT"),
                    ("product_title", "TEXT"),
                    ("variant_title", "TEXT"),
                    ("certificate_id", "TEXT"),
                    ("edition_number", "INTEGER"),
                    ("edition_total", "INTEGER"),
                    ("edition_limit", "INTEGER"),
                    ("edition_display", "TEXT"),
                    ("display_edition", "TEXT"),
                    ("line_item_unit_index", "INTEGER DEFAULT 1"),
                    ("local_file_path", "TEXT"),
                    ("shopify_file_id", "TEXT"),
                    ("shopify_file_status", "TEXT"),
                    ("shopify_file_url", "TEXT"),
                    ("certificate_file_url", "TEXT"),
                    ("certificate_pdf_url", "TEXT"),
                    ("certificate_print_jpg_url", "TEXT"),
                    ("certificate_preview_image_url", "TEXT"),
                    ("shopify_pdf_file_id", "TEXT"),
                    ("shopify_print_jpg_file_id", "TEXT"),
                    ("shopify_preview_file_id", "TEXT"),
                    ("asset_sync_status", "TEXT DEFAULT 'pending'"),
                    ("asset_sync_error", "TEXT"),
                    ("certificate_shopify_file_id", "TEXT"),
                    ("certificate_status", "TEXT DEFAULT 'Processing'"),
                    ("sync_status", "TEXT DEFAULT 'pending'"),
                    ("last_sync_error", "TEXT"),
                    ("purchase_date", "TIMESTAMPTZ"),
                    ("source", "TEXT DEFAULT 'sports_cave_os'"),
                    ("created_at", "TIMESTAMPTZ DEFAULT now()"),
                    ("updated_at", "TIMESTAMPTZ DEFAULT now()"),
                    ("generated_at", "TIMESTAMPTZ DEFAULT now()"),
                    ("status", "TEXT DEFAULT 'Local PDF'"),
                ),
                "product_assets": (
                    ("shopify_handle", "TEXT"),
                    ("asset_type", "TEXT"),
                    ("asset_name", "TEXT"),
                    ("asset_url", "TEXT"),
                    ("google_drive_file_id", "TEXT"),
                    ("google_drive_file_url", "TEXT"),
                    ("notes", "TEXT"),
                    ("is_primary", "BOOLEAN DEFAULT TRUE"),
                    ("created_at", "TIMESTAMPTZ DEFAULT now()"),
                    ("updated_at", "TIMESTAMPTZ DEFAULT now()"),
                ),
                "prodigi_dispatch_rows": (
                    ("row_id", "TEXT"),
                    ("shopify_order_id", "TEXT"),
                    ("shopify_order_name", "TEXT"),
                    ("shopify_order_number", "TEXT"),
                    ("shopify_line_item_id", "TEXT"),
                    ("customer_name", "TEXT"),
                    ("product_title", "TEXT"),
                    ("shopify_variant_title", "TEXT"),
                    ("edition_number", "INTEGER"),
                    ("sports_cave_frame", "TEXT"),
                    ("sports_cave_size", "TEXT"),
                    ("prodigi_product_name", "TEXT"),
                    ("prodigi_product_code", "TEXT"),
                    ("prodigi_frame_colour", "TEXT"),
                    ("prodigi_status", "TEXT"),
                    ("date_sent_to_prodigi", "TEXT"),
                    ("submitted_at", "TIMESTAMPTZ"),
                    ("qa_confirmed", "BOOLEAN DEFAULT FALSE"),
                    ("qa_notes", "TEXT"),
                    ("notes", "TEXT"),
                    ("source", "TEXT DEFAULT 'prodigi_dispatch_log'"),
                    ("row_json", "JSONB DEFAULT '{}'::jsonb"),
                    ("created_at", "TIMESTAMPTZ DEFAULT now()"),
                    ("updated_at", "TIMESTAMPTZ DEFAULT now()"),
                ),
                "certificates": (
                    ("edition_order_id", "TEXT"),
                    ("related_edition_order_id", "uuid NULL"),
                    ("shopify_customer_id", "TEXT"),
                    ("customer_email", "TEXT"),
                    ("customer_name", "TEXT"),
                    ("shopify_order_id", "TEXT"),
                    ("shopify_order_name", "TEXT"),
                    ("shopify_line_item_id", "TEXT"),
                    ("shopify_handle", "TEXT"),
                    ("product_handle", "TEXT"),
                    ("shopify_product_id", "TEXT"),
                    ("shopify_variant_id", "TEXT"),
                    ("product_title", "TEXT"),
                    ("variant_title", "TEXT"),
                    ("certificate_id", "TEXT"),
                    ("edition_number", "INTEGER"),
                    ("edition_total", "INTEGER"),
                    ("edition_limit", "INTEGER"),
                    ("edition_display", "TEXT"),
                    ("display_edition", "TEXT"),
                    ("line_item_unit_index", "INTEGER DEFAULT 1"),
                    ("pdf_filename", "TEXT"),
                    ("local_file_path", "TEXT"),
                    ("shopify_file_id", "TEXT"),
                    ("shopify_file_status", "TEXT"),
                    ("shopify_file_url", "TEXT"),
                    ("certificate_file_url", "TEXT"),
                    ("certificate_pdf_url", "TEXT"),
                    ("certificate_print_jpg_url", "TEXT"),
                    ("certificate_preview_image_url", "TEXT"),
                    ("shopify_pdf_file_id", "TEXT"),
                    ("shopify_print_jpg_file_id", "TEXT"),
                    ("shopify_preview_file_id", "TEXT"),
                    ("asset_sync_status", "TEXT DEFAULT 'pending'"),
                    ("asset_sync_error", "TEXT"),
                    ("certificate_shopify_file_id", "TEXT"),
                    ("certificate_status", "TEXT DEFAULT 'Processing'"),
                    ("order_metafields_synced_at", "TIMESTAMPTZ"),
                    ("order_metafields_sync_status", "TEXT DEFAULT 'Never Synced'"),
                    ("order_metafields_error", "TEXT"),
                    ("sync_status", "TEXT DEFAULT 'pending'"),
                    ("last_sync_error", "TEXT"),
                    ("purchase_date", "TIMESTAMPTZ"),
                    ("source", "TEXT DEFAULT 'sports_cave_os'"),
                    ("created_at", "TIMESTAMPTZ DEFAULT now()"),
                    ("updated_at", "TIMESTAMPTZ DEFAULT now()"),
                    ("certificate_r2_bucket", "TEXT"),
                    ("certificate_r2_key", "TEXT"),
                    ("certificate_preview_r2_bucket", "TEXT"),
                    ("certificate_preview_r2_key", "TEXT"),
                    ("status", "TEXT DEFAULT 'Local PDF'"),
                    ("generated_at", "TIMESTAMPTZ DEFAULT now()"),
                ),
                "file_assets": (
                    ("asset_type", "TEXT"),
                    ("bucket", "TEXT"),
                    ("object_key", "TEXT"),
                    ("filename", "TEXT"),
                    ("mime_type", "TEXT"),
                    ("size_bytes", "BIGINT"),
                    ("related_shopify_product_id", "TEXT"),
                    ("related_shopify_order_id", "TEXT"),
                    ("related_shopify_handle", "TEXT"),
                    ("related_edition_order_id", "uuid NULL"),
                    ("source", "TEXT DEFAULT 'r2'"),
                    ("status", "TEXT DEFAULT 'active'"),
                    ("created_at", "TIMESTAMPTZ DEFAULT now()"),
                    ("updated_at", "TIMESTAMPTZ DEFAULT now()"),
                ),
                "edition_runs": (
                    ("edition_product_id", f"{edition_product_fk_type}{edition_product_fk}"),
                    ("shopify_product_id", "TEXT"),
                    ("shopify_handle", "TEXT"),
                    ("product_title", "TEXT"),
                    ("edition_name", f"TEXT DEFAULT '{DEFAULT_EDITION_NAME}'"),
                    ("edition_total", "INTEGER DEFAULT 100"),
                    ("next_edition_number", "INTEGER DEFAULT 1"),
                    ("status", f"TEXT DEFAULT '{ACTIVE_RUN_STATUS}'"),
                    ("started_at", "TIMESTAMPTZ DEFAULT now()"),
                    ("archived_at", "TIMESTAMPTZ"),
                    ("notes", "TEXT"),
                    ("created_at", "TIMESTAMPTZ DEFAULT now()"),
                    ("updated_at", "TIMESTAMPTZ DEFAULT now()"),
                ),
                "edition_adjustments": (
                    ("edition_product_id", f"{edition_product_fk_type}{edition_product_fk}"),
                    ("edition_run_id", "UUID"),
                    ("shopify_product_id", "TEXT"),
                    ("shopify_handle", "TEXT"),
                    ("old_next_edition_number", "INTEGER"),
                    ("new_next_edition_number", "INTEGER"),
                    ("old_edition_total", "INTEGER"),
                    ("new_edition_total", "INTEGER"),
                    ("reason", "TEXT"),
                    ("source", "TEXT DEFAULT 'manual_app'"),
                    ("created_at", "TIMESTAMPTZ DEFAULT now()"),
                ),
                "webhook_events": (
                    ("topic", "TEXT"),
                    ("status", "TEXT"),
                    ("received_at", "TIMESTAMPTZ DEFAULT now()"),
                    ("payload", "JSONB DEFAULT '{}'::jsonb"),
                    ("error_message", "TEXT"),
                ),
                "sync_runs": (
                    ("sync_type", "TEXT"),
                    ("status", "TEXT"),
                    ("started_at", "TIMESTAMPTZ DEFAULT now()"),
                    ("completed_at", "TIMESTAMPTZ"),
                    ("records_seen", "INTEGER DEFAULT 0"),
                    ("records_processed", "INTEGER DEFAULT 0"),
                    ("error_message", "TEXT"),
                ),
                "app_errors": (
                    ("source", "TEXT DEFAULT 'sports_cave_os'"),
                    ("severity", "TEXT DEFAULT 'error'"),
                    ("error_type", "TEXT"),
                    ("message", "TEXT"),
                    ("context", "JSONB DEFAULT '{}'::jsonb"),
                    ("created_at", "TIMESTAMPTZ DEFAULT now()"),
                ),
                "app_settings": (
                    ("key", "TEXT"),
                    ("value", "JSONB DEFAULT '{}'::jsonb"),
                    ("updated_at", "TIMESTAMPTZ DEFAULT now()"),
                ),
                "app_sync_state": (
                    ("key", "TEXT"),
                    ("value", "JSONB DEFAULT '{}'::jsonb"),
                    ("cursor_value", "TEXT"),
                    ("last_success_at", "TIMESTAMPTZ"),
                    ("last_attempt_at", "TIMESTAMPTZ"),
                    ("status", "TEXT DEFAULT 'idle'"),
                    ("error_message", "TEXT"),
                    ("updated_at", "TIMESTAMPTZ DEFAULT now()"),
                ),
                "audit_logs": (
                    ("event_type", "TEXT"),
                    ("entity_type", "TEXT"),
                    ("entity_id", "TEXT"),
                    ("shopify_order_id", "TEXT"),
                    ("shopify_line_item_id", "TEXT"),
                    ("shopify_handle", "TEXT"),
                    ("old_value", "JSONB DEFAULT '{}'::jsonb"),
                    ("new_value", "JSONB DEFAULT '{}'::jsonb"),
                    ("reason", "TEXT"),
                    ("actor", "TEXT DEFAULT 'sports_cave_os'"),
                    ("source", "TEXT DEFAULT 'sports_cave_os'"),
                    ("created_at", "TIMESTAMPTZ DEFAULT now()"),
                ),
            }
            for table_name, columns in additive_columns.items():
                if not table_exists(cur, table_name):
                    continue
                for column_name, column_type in columns:
                    cur.execute(
                        f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} {column_type}"
                    )

            if table_exists(cur, "certificates"):
                # The legacy certificate key is text because older deployments stored
                # stringified assignment ids there. Do not attach a foreign key to it:
                # some Supabase databases use uuid ids for edition_orders, which makes
                # certificates.edition_order_id -> edition_orders.id incompatible.
                # related_edition_order_id is the nullable uuid-safe link for newer rows.
                cur.execute("ALTER TABLE certificates DROP CONSTRAINT IF EXISTS certificates_edition_order_id_fkey")
                cur.execute("ALTER TABLE certificates DROP CONSTRAINT IF EXISTS certificates_related_edition_order_id_fkey")
                cur.execute("ALTER TABLE certificates ADD COLUMN IF NOT EXISTS related_edition_order_id uuid NULL")
                cur.execute(
                    """
                    SELECT data_type
                    FROM information_schema.columns
                    WHERE table_schema='public'
                      AND table_name='edition_orders'
                      AND column_name='id'
                    """
                )
                edition_order_id_type = (cur.fetchone() or {}).get("data_type")
                if edition_order_id_type == "uuid":
                    cur.execute(
                        """
                        UPDATE certificates
                        SET related_edition_order_id = CASE
                            WHEN edition_order_id::text ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                            THEN edition_order_id::uuid
                            ELSE NULL
                        END
                        WHERE related_edition_order_id IS NULL
                          AND edition_order_id::text ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                          AND EXISTS (
                              SELECT 1
                              FROM edition_orders eo
                              WHERE eo.id = CASE
                                  WHEN certificates.edition_order_id::text ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                                  THEN certificates.edition_order_id::uuid
                                  ELSE NULL
                              END
                          )
                        """
                    )
                    cur.execute(
                        """
                        UPDATE certificates
                        SET related_edition_order_id = NULL
                        WHERE related_edition_order_id IS NOT NULL
                          AND NOT EXISTS (
                              SELECT 1
                              FROM edition_orders eo
                              WHERE eo.id = certificates.related_edition_order_id
                          )
                        """
                    )

            if table_exists(cur, "app_errors"):
                if column_exists(cur, "app_errors", "source"):
                    cur.execute(
                        "ALTER TABLE app_errors ALTER COLUMN source SET DEFAULT 'sports_cave_os'"
                    )
                    cur.execute(
                        "UPDATE app_errors SET source='sports_cave_os' WHERE source IS NULL"
                    )
                if column_exists(cur, "app_errors", "severity"):
                    cur.execute(
                        "ALTER TABLE app_errors ALTER COLUMN severity SET DEFAULT 'error'"
                    )
                    cur.execute("UPDATE app_errors SET severity='error' WHERE severity IS NULL")

            uuid_id_tables = (
                "shopify_products",
                "shopify_variants",
                "edition_products",
                "shopify_customers",
                "shopify_orders",
                "shopify_order_lines",
                "edition_orders",
                "edition_runs",
                "edition_adjustments",
                "certificates",
                "product_assets",
                "file_assets",
                "sync_runs",
                "app_errors",
                "audit_logs",
            )
            pgcrypto_ready = False
            for table_name in uuid_id_tables:
                if not table_exists(cur, table_name):
                    continue
                cur.execute(
                    """
                    SELECT data_type, column_default
                    FROM information_schema.columns
                    WHERE table_schema='public'
                      AND table_name=%s
                      AND column_name='id'
                    """,
                    (table_name,),
                )
                id_column = cur.fetchone() or {}
                if id_column.get("data_type") == "uuid" and not id_column.get("column_default"):
                    if not pgcrypto_ready:
                        cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
                        pgcrypto_ready = True
                    cur.execute(
                        f"ALTER TABLE {table_name} ALTER COLUMN id SET DEFAULT gen_random_uuid()"
                    )

            _safe_create_index(cur, "CREATE UNIQUE INDEX IF NOT EXISTS idx_shopify_products_id_unique ON shopify_products(shopify_product_id)", "idx_shopify_products_id_unique")
            _safe_create_index(cur, "CREATE UNIQUE INDEX IF NOT EXISTS idx_shopify_products_handle_unique ON shopify_products(handle)", "idx_shopify_products_handle_unique")
            _safe_create_index(cur, "CREATE UNIQUE INDEX IF NOT EXISTS idx_shopify_variants_id_unique ON shopify_variants(shopify_variant_id)", "idx_shopify_variants_id_unique")
            _safe_create_index(cur, "CREATE UNIQUE INDEX IF NOT EXISTS idx_edition_products_handle_unique ON edition_products(shopify_handle)", "idx_edition_products_handle_unique")
            _safe_create_index(cur, "CREATE UNIQUE INDEX IF NOT EXISTS idx_shopify_customers_id_unique ON shopify_customers(shopify_customer_id)", "idx_shopify_customers_id_unique")
            _safe_create_index(cur, "CREATE UNIQUE INDEX IF NOT EXISTS idx_shopify_orders_id_unique ON shopify_orders(shopify_order_id)", "idx_shopify_orders_id_unique")
            _safe_create_index(cur, "CREATE UNIQUE INDEX IF NOT EXISTS idx_shopify_order_lines_line_id_unique ON shopify_order_lines(shopify_line_item_id)", "idx_shopify_order_lines_line_id_unique")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_shopify_order_lines_order_id ON shopify_order_lines(shopify_order_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_shopify_order_lines_handle ON shopify_order_lines(shopify_handle)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_shopify_order_lines_product_id ON shopify_order_lines(shopify_product_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_shopify_order_lines_sku ON shopify_order_lines(sku)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_shopify_variants_product_id ON shopify_variants(shopify_product_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_shopify_variants_sku ON shopify_variants(sku)")
            cur.execute("ALTER TABLE edition_orders DROP CONSTRAINT IF EXISTS edition_orders_shopify_handle_edition_number_key")
            cur.execute("DROP INDEX IF EXISTS idx_edition_orders_handle_number_unique")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_edition_orders_handle_number ON edition_orders(shopify_handle, edition_number)")
            _safe_create_index(cur, "CREATE UNIQUE INDEX IF NOT EXISTS idx_edition_orders_line_allocation_unique ON edition_orders(shopify_line_item_id, allocation_index)", "idx_edition_orders_line_allocation_unique")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_edition_orders_run_id ON edition_orders(edition_run_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_edition_orders_line_item_id ON edition_orders(shopify_line_item_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_edition_orders_product_id ON edition_orders(shopify_product_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_edition_orders_assigned_at ON edition_orders(assigned_at DESC)")
            cur.execute("DROP INDEX IF EXISTS idx_edition_orders_run_number_unique")
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_edition_orders_run_number
                ON edition_orders(edition_run_id, edition_number)
                WHERE edition_run_id IS NOT NULL AND edition_number IS NOT NULL
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_edition_runs_handle_status ON edition_runs(shopify_handle, status)")
            _safe_create_index(
                cur,
                f"""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_edition_runs_one_active_per_handle
                ON edition_runs(shopify_handle)
                WHERE status='{ACTIVE_RUN_STATUS}'
                """,
                "idx_edition_runs_one_active_per_handle",
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_edition_adjustments_handle ON edition_adjustments(shopify_handle, created_at DESC)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_edition_adjustments_run ON edition_adjustments(edition_run_id, created_at DESC)")
            _safe_create_index(cur, "CREATE UNIQUE INDEX IF NOT EXISTS idx_certificates_edition_order_unique ON certificates(edition_order_id)", "idx_certificates_edition_order_unique")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_certificates_related_edition_order ON certificates(related_edition_order_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_certificates_certificate_id ON certificates(certificate_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_certificates_shopify_order_id ON certificates(shopify_order_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_certificates_line_unit ON certificates(shopify_line_item_id, line_item_unit_index)")
            _safe_create_index(cur, "CREATE UNIQUE INDEX IF NOT EXISTS idx_product_assets_handle_type_unique ON product_assets(shopify_handle, asset_type)", "idx_product_assets_handle_type_unique")
            _safe_create_index(cur, "CREATE UNIQUE INDEX IF NOT EXISTS idx_product_assets_handle_type_name_unique ON product_assets(shopify_handle, asset_type, asset_name)", "idx_product_assets_handle_type_name_unique")
            _safe_create_index(cur, "CREATE UNIQUE INDEX IF NOT EXISTS idx_prodigi_dispatch_rows_row_id_unique ON prodigi_dispatch_rows(row_id)", "idx_prodigi_dispatch_rows_row_id_unique")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_prodigi_dispatch_rows_order ON prodigi_dispatch_rows(shopify_order_name)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_prodigi_dispatch_rows_status ON prodigi_dispatch_rows(prodigi_status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_prodigi_dispatch_rows_updated_at ON prodigi_dispatch_rows(updated_at DESC)")
            _safe_create_index(cur, "CREATE UNIQUE INDEX IF NOT EXISTS idx_file_assets_bucket_key_unique ON file_assets(bucket, object_key)", "idx_file_assets_bucket_key_unique")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_file_assets_handle ON file_assets(related_shopify_handle)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_file_assets_order ON file_assets(related_shopify_order_id)")
            _safe_create_index(cur, "CREATE UNIQUE INDEX IF NOT EXISTS idx_app_settings_key_unique ON app_settings(key)", "idx_app_settings_key_unique")
            _safe_create_index(cur, "CREATE UNIQUE INDEX IF NOT EXISTS idx_app_sync_state_key_unique ON app_sync_state(key)", "idx_app_sync_state_key_unique")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_app_sync_state_updated_at ON app_sync_state(updated_at DESC)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at DESC)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_entity ON audit_logs(entity_type, entity_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_order_line ON audit_logs(shopify_order_id, shopify_line_item_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_handle ON audit_logs(shopify_handle)")
            _safe_create_index(cur, "CREATE UNIQUE INDEX IF NOT EXISTS idx_webhook_events_id_unique ON webhook_events(webhook_id)", "idx_webhook_events_id_unique")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_shopify_products_title ON shopify_products(title)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_shopify_products_updated_at ON shopify_products(updated_at DESC)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_shopify_products_product_type ON shopify_products(product_type)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_shopify_orders_created_at ON shopify_orders(created_at DESC)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_shopify_orders_updated_at ON shopify_orders(remote_updated_at DESC)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_shopify_orders_financial_fulfillment ON shopify_orders(financial_status, fulfillment_status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_shopify_orders_financial_status ON shopify_orders(financial_status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_shopify_orders_fulfillment_status ON shopify_orders(fulfillment_status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_shopify_orders_customer ON shopify_orders(customer_name)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_shopify_orders_customer_email ON shopify_orders(customer_email)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_shopify_orders_order_name ON shopify_orders(order_name)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_edition_orders_order_id ON edition_orders(shopify_order_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_edition_orders_handle ON edition_orders(shopify_handle)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_edition_orders_edition_number ON edition_orders(edition_number)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_shopify_order_lines_assignment_status ON shopify_order_lines(assignment_status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_edition_products_product_id ON edition_products(shopify_product_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_edition_products_title ON edition_products(product_title)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_edition_products_edition_status ON edition_products(edition_status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_edition_products_updated_at ON edition_products(updated_at DESC)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_product_assets_handle ON product_assets(shopify_handle)")
            cur.execute(
                f"""
                INSERT INTO edition_runs(
                    edition_product_id, shopify_product_id, shopify_handle, product_title,
                    edition_name, edition_total, next_edition_number, status, started_at, updated_at
                )
                SELECT ep.id,
                       ep.shopify_product_id,
                       ep.shopify_handle,
                       ep.product_title,
                       COALESCE(NULLIF(ep.edition_name, ''), '{DEFAULT_EDITION_NAME}'),
                       COALESCE(ep.edition_total, 100),
                       GREATEST(COALESCE(ep.next_edition_number, 1), 1),
                       CASE
                           WHEN COALESCE(ep.sold_out, ep.is_sold_out, FALSE) THEN '{SOLD_OUT_RUN_STATUS}'
                           WHEN COALESCE(ep.active, ep.is_active, TRUE) THEN '{ACTIVE_RUN_STATUS}'
                           ELSE '{INACTIVE_RUN_STATUS}'
                       END,
                       now(),
                       now()
                FROM edition_products ep
                WHERE ep.shopify_handle IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM edition_runs er
                      WHERE er.shopify_handle = ep.shopify_handle
                        AND er.status IN ('{ACTIVE_RUN_STATUS}', '{SOLD_OUT_RUN_STATUS}', '{INACTIVE_RUN_STATUS}')
                  )
                """
            )
            cur.execute(
                f"""
                UPDATE edition_products ep
                SET active_edition_run_id=er.id,
                    edition_name=er.edition_name,
                    updated_at=now()
                FROM edition_runs er
                WHERE er.shopify_handle=ep.shopify_handle
                  AND er.id = (
                      SELECT er2.id
                      FROM edition_runs er2
                      WHERE er2.shopify_handle=ep.shopify_handle
                        AND er2.status IN ('{ACTIVE_RUN_STATUS}', '{SOLD_OUT_RUN_STATUS}', '{INACTIVE_RUN_STATUS}')
                      ORDER BY CASE
                          WHEN er2.status='{ACTIVE_RUN_STATUS}' THEN 0
                          WHEN er2.status='{SOLD_OUT_RUN_STATUS}' THEN 1
                          ELSE 2
                      END,
                      er2.started_at DESC NULLS LAST,
                      er2.created_at DESC NULLS LAST
                      LIMIT 1
                  )
                  AND (ep.active_edition_run_id IS NULL OR ep.active_edition_run_id <> er.id)
                """
            )
        conn.commit()


def reset_schema_cache():
    global _SCHEMA_READY, _ORDER_READ_SCHEMA_READY
    with _SCHEMA_LOCK:
        _SCHEMA_READY = False
        _ORDER_READ_SCHEMA_READY = False


def ensure_schema():
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return
        started = time.perf_counter()
        _ensure_schema_uncached()
        elapsed = time.perf_counter() - started
        print(f"PERF DB migration time={elapsed:.3f}s", flush=True)
        _SCHEMA_READY = True


def ensure_order_read_schema():
    """Keep Orders readable even if a later full-schema migration needs attention."""
    global _ORDER_READ_SCHEMA_READY
    if _SCHEMA_READY or _ORDER_READ_SCHEMA_READY:
        return
    if not is_configured():
        raise SupabaseNotConfigured(
            "No Supabase/Postgres database URL is configured. Set DATABASE_URL, "
            "SUPABASE_DATABASE_URL, or POSTGRES_URL in Render."
        )
    with _SCHEMA_LOCK:
        if _SCHEMA_READY or _ORDER_READ_SCHEMA_READY:
            return
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS shopify_orders (
                        shopify_order_id TEXT PRIMARY KEY,
                        order_name TEXT,
                        order_number TEXT,
                        admin_url TEXT,
                        customer_name TEXT,
                        customer_email TEXT,
                        financial_status TEXT,
                        fulfillment_status TEXT,
                        total_price TEXT,
                        currency TEXT,
                        created_at TIMESTAMPTZ,
                        remote_updated_at TIMESTAMPTZ,
                        processed_at TIMESTAMPTZ,
                        cancelled_at TIMESTAMPTZ,
                        raw_json JSONB DEFAULT '{}'::jsonb,
                        synced_at TIMESTAMPTZ DEFAULT now()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS shopify_order_lines (
                        id BIGSERIAL PRIMARY KEY,
                        shopify_line_item_id TEXT UNIQUE,
                        shopify_order_id TEXT,
                        shopify_product_id TEXT,
                        shopify_handle TEXT,
                        product_title TEXT,
                        variant_title TEXT,
                        sku TEXT,
                        quantity INTEGER DEFAULT 1,
                        assignment_status TEXT DEFAULT 'Needs Edition',
                        last_error TEXT DEFAULT '',
                        raw_json JSONB DEFAULT '{}'::jsonb,
                        synced_at TIMESTAMPTZ DEFAULT now(),
                        updated_at TIMESTAMPTZ DEFAULT now()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS edition_orders (
                        id BIGSERIAL PRIMARY KEY,
                        shopify_customer_id TEXT,
                        shopify_order_id TEXT,
                        shopify_order_name TEXT,
                        shopify_line_item_id TEXT,
                        shopify_product_id TEXT,
                        shopify_variant_id TEXT,
                        shopify_handle TEXT,
                        product_handle TEXT,
                        product_title TEXT,
                        variant_title TEXT,
                        sku TEXT,
                        customer_name TEXT,
                        customer_email TEXT,
                        edition_number INTEGER,
                        edition_total INTEGER,
                        edition_display TEXT,
                        allocation_index INTEGER DEFAULT 1,
                        assigned_at TIMESTAMPTZ DEFAULT now(),
                        certificate_status TEXT DEFAULT 'Certificate Missing',
                        certificate_id TEXT,
                        shopify_file_id TEXT,
                        shopify_file_status TEXT,
                        certificate_file_url TEXT,
                        purchase_date TIMESTAMPTZ,
                        source TEXT DEFAULT 'sports_cave_os',
                        manual_override BOOLEAN DEFAULT FALSE,
                        override_old_edition_number INTEGER,
                        override_new_edition_number INTEGER,
                        override_timestamp TIMESTAMPTZ,
                        override_reason TEXT,
                        created_at TIMESTAMPTZ DEFAULT now(),
                        updated_at TIMESTAMPTZ DEFAULT now()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS certificates (
                        id BIGSERIAL PRIMARY KEY,
                        edition_order_id TEXT UNIQUE,
                        related_edition_order_id uuid NULL,
                        shopify_customer_id TEXT,
                        customer_email TEXT,
                        customer_name TEXT,
                        shopify_order_id TEXT,
                        shopify_order_name TEXT,
                        shopify_line_item_id TEXT,
                        shopify_handle TEXT,
                        product_handle TEXT,
                        shopify_product_id TEXT,
                        shopify_variant_id TEXT,
                        product_title TEXT,
                        variant_title TEXT,
                        certificate_id TEXT,
                        edition_number INTEGER,
                        edition_total INTEGER,
                        edition_display TEXT,
                        line_item_unit_index INTEGER DEFAULT 1,
                        pdf_filename TEXT,
                        local_file_path TEXT,
                        shopify_file_id TEXT,
                        shopify_file_status TEXT,
                        shopify_file_url TEXT,
                        certificate_file_url TEXT,
                        certificate_pdf_url TEXT,
                        certificate_print_jpg_url TEXT,
                        certificate_preview_image_url TEXT,
                        shopify_pdf_file_id TEXT,
                        shopify_print_jpg_file_id TEXT,
                        shopify_preview_file_id TEXT,
                        asset_sync_status TEXT DEFAULT 'pending',
                        asset_sync_error TEXT,
                        certificate_shopify_file_id TEXT,
                        certificate_status TEXT DEFAULT 'Processing',
                        purchase_date TIMESTAMPTZ,
                        source TEXT DEFAULT 'sports_cave_os',
                        generated_at TIMESTAMPTZ DEFAULT now(),
                        status TEXT DEFAULT 'Local PDF',
                        created_at TIMESTAMPTZ DEFAULT now(),
                        updated_at TIMESTAMPTZ DEFAULT now()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS edition_products (
                        id BIGSERIAL PRIMARY KEY,
                        shopify_handle TEXT UNIQUE,
                        product_title TEXT,
                        featured_image_url TEXT
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS shopify_products (
                        shopify_product_id TEXT PRIMARY KEY,
                        handle TEXT UNIQUE,
                        title TEXT,
                        image_url TEXT,
                        featured_image_url TEXT
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS product_assets (
                        id BIGSERIAL PRIMARY KEY,
                        shopify_handle TEXT,
                        asset_type TEXT,
                        asset_url TEXT,
                        google_drive_file_url TEXT,
                        is_primary BOOLEAN DEFAULT TRUE
                    )
                    """
                )

                read_columns = {
                    "shopify_orders": (
                        ("order_name", "TEXT"),
                        ("order_number", "TEXT"),
                        ("admin_url", "TEXT"),
                        ("customer_name", "TEXT"),
                        ("customer_email", "TEXT"),
                        ("financial_status", "TEXT"),
                        ("fulfillment_status", "TEXT"),
                        ("total_price", "TEXT"),
                        ("currency", "TEXT"),
                        ("created_at", "TIMESTAMPTZ"),
                        ("remote_updated_at", "TIMESTAMPTZ"),
                        ("processed_at", "TIMESTAMPTZ"),
                        ("cancelled_at", "TIMESTAMPTZ"),
                        ("raw_json", "JSONB DEFAULT '{}'::jsonb"),
                        ("synced_at", "TIMESTAMPTZ DEFAULT now()"),
                    ),
                    "shopify_order_lines": (
                        ("shopify_line_item_id", "TEXT"),
                        ("shopify_order_id", "TEXT"),
                        ("shopify_product_id", "TEXT"),
                        ("shopify_handle", "TEXT"),
                        ("product_title", "TEXT"),
                        ("variant_title", "TEXT"),
                        ("sku", "TEXT"),
                        ("quantity", "INTEGER DEFAULT 1"),
                        ("assignment_status", "TEXT DEFAULT 'Needs Edition'"),
                        ("last_error", "TEXT DEFAULT ''"),
                        ("raw_json", "JSONB DEFAULT '{}'::jsonb"),
                        ("synced_at", "TIMESTAMPTZ DEFAULT now()"),
                        ("updated_at", "TIMESTAMPTZ DEFAULT now()"),
                    ),
                    "edition_orders": (
                        ("shopify_customer_id", "TEXT"),
                        ("shopify_order_id", "TEXT"),
                        ("shopify_order_name", "TEXT"),
                        ("shopify_line_item_id", "TEXT"),
                        ("shopify_product_id", "TEXT"),
                        ("shopify_variant_id", "TEXT"),
                        ("shopify_handle", "TEXT"),
                        ("product_handle", "TEXT"),
                        ("product_title", "TEXT"),
                        ("variant_title", "TEXT"),
                        ("sku", "TEXT"),
                        ("customer_name", "TEXT"),
                        ("customer_email", "TEXT"),
                        ("edition_number", "INTEGER"),
                        ("edition_total", "INTEGER"),
                        ("edition_display", "TEXT"),
                        ("allocation_index", "INTEGER DEFAULT 1"),
                        ("assigned_at", "TIMESTAMPTZ DEFAULT now()"),
                        ("certificate_status", "TEXT DEFAULT 'Certificate Missing'"),
                        ("certificate_id", "TEXT"),
                        ("shopify_file_id", "TEXT"),
                        ("shopify_file_status", "TEXT"),
                        ("certificate_file_url", "TEXT"),
                        ("purchase_date", "TIMESTAMPTZ"),
                        ("source", "TEXT DEFAULT 'sports_cave_os'"),
                        ("manual_override", "BOOLEAN DEFAULT FALSE"),
                        ("override_old_edition_number", "INTEGER"),
                        ("override_new_edition_number", "INTEGER"),
                        ("override_timestamp", "TIMESTAMPTZ"),
                        ("override_reason", "TEXT"),
                        ("created_at", "TIMESTAMPTZ DEFAULT now()"),
                        ("updated_at", "TIMESTAMPTZ DEFAULT now()"),
                        ("status", "TEXT DEFAULT 'assigned'"),
                    ),
                    "certificates": (
                        ("edition_order_id", "TEXT"),
                        ("related_edition_order_id", "uuid NULL"),
                        ("shopify_customer_id", "TEXT"),
                        ("customer_email", "TEXT"),
                        ("customer_name", "TEXT"),
                        ("shopify_order_id", "TEXT"),
                        ("shopify_order_name", "TEXT"),
                        ("shopify_line_item_id", "TEXT"),
                        ("shopify_handle", "TEXT"),
                        ("product_handle", "TEXT"),
                        ("shopify_product_id", "TEXT"),
                        ("shopify_variant_id", "TEXT"),
                        ("product_title", "TEXT"),
                        ("variant_title", "TEXT"),
                        ("certificate_id", "TEXT"),
                        ("edition_number", "INTEGER"),
                        ("edition_total", "INTEGER"),
                        ("edition_display", "TEXT"),
                        ("line_item_unit_index", "INTEGER DEFAULT 1"),
                        ("pdf_filename", "TEXT"),
                        ("local_file_path", "TEXT"),
                        ("shopify_file_id", "TEXT"),
                        ("shopify_file_status", "TEXT"),
                        ("shopify_file_url", "TEXT"),
                        ("certificate_file_url", "TEXT"),
                        ("certificate_pdf_url", "TEXT"),
                        ("certificate_print_jpg_url", "TEXT"),
                        ("certificate_preview_image_url", "TEXT"),
                        ("shopify_pdf_file_id", "TEXT"),
                        ("shopify_print_jpg_file_id", "TEXT"),
                        ("shopify_preview_file_id", "TEXT"),
                        ("asset_sync_status", "TEXT DEFAULT 'pending'"),
                        ("asset_sync_error", "TEXT"),
                        ("certificate_shopify_file_id", "TEXT"),
                        ("certificate_status", "TEXT DEFAULT 'Processing'"),
                        ("purchase_date", "TIMESTAMPTZ"),
                        ("source", "TEXT DEFAULT 'sports_cave_os'"),
                        ("status", "TEXT DEFAULT 'Local PDF'"),
                        ("generated_at", "TIMESTAMPTZ DEFAULT now()"),
                        ("created_at", "TIMESTAMPTZ DEFAULT now()"),
                        ("updated_at", "TIMESTAMPTZ DEFAULT now()"),
                        ("certificate_r2_bucket", "TEXT"),
                        ("certificate_r2_key", "TEXT"),
                        ("certificate_preview_r2_bucket", "TEXT"),
                        ("certificate_preview_r2_key", "TEXT"),
                    ),
                    "edition_products": (
                        ("shopify_handle", "TEXT"),
                        ("product_title", "TEXT"),
                        ("featured_image_url", "TEXT"),
                    ),
                    "shopify_products": (
                        ("handle", "TEXT"),
                        ("title", "TEXT"),
                        ("image_url", "TEXT"),
                        ("featured_image_url", "TEXT"),
                    ),
                    "product_assets": (
                        ("shopify_handle", "TEXT"),
                        ("asset_type", "TEXT"),
                        ("asset_url", "TEXT"),
                        ("google_drive_file_url", "TEXT"),
                        ("is_primary", "BOOLEAN DEFAULT TRUE"),
                    ),
                }
                for table_name, columns in read_columns.items():
                    if not table_exists(cur, table_name):
                        continue
                    for column_name, column_type in columns:
                        cur.execute(
                            f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} {column_type}"
                        )
                if table_exists(cur, "certificates"):
                    cur.execute("ALTER TABLE certificates DROP CONSTRAINT IF EXISTS certificates_edition_order_id_fkey")
                    cur.execute("ALTER TABLE certificates DROP CONSTRAINT IF EXISTS certificates_related_edition_order_id_fkey")
            conn.commit()
        _ORDER_READ_SCHEMA_READY = True


def test_connection():
    ensure_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT now() AS server_time")
            row = cur.fetchone() or {}
    return {
        "connected": True,
        "server_time": row.get("server_time"),
        "url_source": get_database_url_source(),
    }


def log_app_error(error_type, message, context=None):
    if not is_configured():
        return
    try:
        ensure_schema()
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO app_errors(source, severity, error_type, message, context)
                    VALUES ('sports_cave_os', 'error', %s, %s, %s::jsonb)
                    """,
                    (str(error_type or "error"), str(message or ""), json_dumps(context)),
                )
            conn.commit()
    except Exception:
        pass


def _insert_audit_log(
    cur,
    *,
    event_type,
    entity_type="",
    entity_id="",
    shopify_order_id="",
    shopify_line_item_id="",
    shopify_handle="",
    old_value=None,
    new_value=None,
    reason="",
    actor="sports_cave_os",
    source="sports_cave_os",
):
    cur.execute(
        """
        INSERT INTO audit_logs(
            event_type, entity_type, entity_id,
            shopify_order_id, shopify_line_item_id, shopify_handle,
            old_value, new_value, reason, actor, source
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s)
        """,
        (
            str(event_type or "").strip() or "unknown_event",
            str(entity_type or "").strip(),
            str(entity_id or "").strip(),
            str(shopify_order_id or "").strip(),
            str(shopify_line_item_id or "").strip(),
            str(shopify_handle or "").strip(),
            json_dumps(old_value or {}),
            json_dumps(new_value or {}),
            str(reason or "").strip(),
            str(actor or "").strip() or "sports_cave_os",
            str(source or "").strip() or "sports_cave_os",
        ),
    )


def start_sync_run(sync_type):
    ensure_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO sync_runs(sync_type, status)
                VALUES (%s, 'Running')
                RETURNING id
                """,
                (sync_type,),
            )
            run_id = cur.fetchone()["id"]
        conn.commit()
    return run_id


def finish_sync_run(run_id, status, records_seen=0, records_processed=0, error_message=""):
    if not run_id:
        return
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE sync_runs
                SET status=%s,
                    completed_at=now(),
                    records_seen=%s,
                    records_processed=%s,
                    error_message=%s
                WHERE id=%s
                """,
                (status, records_seen, records_processed, error_message, run_id),
            )
        conn.commit()


def _first_image_url(product):
    images = product.get("images") or []
    if images:
        return images[0].get("url") or ""
    return ""


def upsert_products(products):
    ensure_schema()
    processed = 0
    with connect() as conn:
        with conn.cursor() as cur:
            for product in products:
                handle = product.get("handle") or ""
                if not handle:
                    continue
                product_id = product.get("shopify_product_id")
                image_url = _first_image_url(product)
                raw_json = json_dumps(product)
                is_active = str(product.get("status") or "").upper() == "ACTIVE"
                cur.execute(
                    """
                    INSERT INTO shopify_products(
                        shopify_product_id, legacy_resource_id, shopify_product_gid, title, handle, status, vendor,
                        product_type, online_store_url, admin_url, image_url, featured_image_url,
                        raw_json, raw, synced_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, now(), now())
                    ON CONFLICT (shopify_product_id) DO UPDATE SET
                        legacy_resource_id=EXCLUDED.legacy_resource_id,
                        shopify_product_gid=EXCLUDED.shopify_product_gid,
                        title=EXCLUDED.title,
                        handle=EXCLUDED.handle,
                        status=EXCLUDED.status,
                        vendor=EXCLUDED.vendor,
                        product_type=EXCLUDED.product_type,
                        online_store_url=EXCLUDED.online_store_url,
                        admin_url=EXCLUDED.admin_url,
                        image_url=EXCLUDED.image_url,
                        featured_image_url=EXCLUDED.featured_image_url,
                        raw_json=EXCLUDED.raw_json,
                        raw=EXCLUDED.raw,
                        synced_at=now(),
                        updated_at=now()
                    """,
                    (
                        product_id,
                        product.get("legacy_resource_id"),
                        product_id,
                        product.get("title"),
                        handle,
                        product.get("status"),
                        product.get("vendor"),
                        product.get("product_type"),
                        product.get("online_store_url"),
                        product.get("admin_url"),
                        image_url,
                        image_url,
                        raw_json,
                        raw_json,
                    ),
                )
                for variant in product.get("variants") or []:
                    variant_id = variant.get("id") or variant.get("shopify_variant_id")
                    if not variant_id:
                        continue
                    cur.execute(
                        """
                        INSERT INTO shopify_variants(
                            shopify_variant_id, shopify_product_id, legacy_resource_id, title,
                            sku, price, raw_json, synced_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, now())
                        ON CONFLICT (shopify_variant_id) DO UPDATE SET
                            shopify_product_id=EXCLUDED.shopify_product_id,
                            legacy_resource_id=EXCLUDED.legacy_resource_id,
                            title=EXCLUDED.title,
                            sku=EXCLUDED.sku,
                            price=EXCLUDED.price,
                            raw_json=EXCLUDED.raw_json,
                            synced_at=now()
                        """,
                        (
                            variant_id,
                            product.get("shopify_product_id"),
                            variant.get("legacy_resource_id"),
                            variant.get("title"),
                            variant.get("sku"),
                            variant.get("price"),
                            json_dumps(variant),
                        ),
                    )
                cur.execute(
                    """
                    INSERT INTO edition_products(
                        shopify_product_id, shopify_product_gid, shopify_handle, product_title,
                        edition_total, next_edition_number, active, is_active, sold_out, is_sold_out,
                        featured_image_url, raw, synced_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, 100, 1, %s, %s, FALSE, FALSE, %s, %s::jsonb, now(), now())
                    ON CONFLICT (shopify_handle) DO UPDATE SET
                        shopify_product_id=EXCLUDED.shopify_product_id,
                        shopify_product_gid=EXCLUDED.shopify_product_gid,
                        product_title=EXCLUDED.product_title,
                        active=EXCLUDED.active,
                        is_active=EXCLUDED.is_active,
                        featured_image_url=EXCLUDED.featured_image_url,
                        raw=EXCLUDED.raw,
                        synced_at=now(),
                        updated_at=now()
                    """,
                    (
                        product_id,
                        product_id,
                        handle,
                        product.get("title"),
                        is_active,
                        is_active,
                        image_url,
                        raw_json,
                    ),
                )
                processed += 1
            _ensure_active_edition_runs_for_products(cur)
        conn.commit()
    return processed


def sync_shopify_products_to_supabase(config=None, progress_callback=None, *, mode="incremental"):
    ensure_schema()
    config = config or shopify_sync.get_config()
    requested_full_sync = str(mode or "").lower() in {"full", "initial_full", "initial"}
    bootstrap_full_sync = False
    if not requested_full_sync:
        state = get_sync_state()
        last_success = _parse_datetime(state.get("last_successful_product_sync_at"))
        if not last_success and count_shopify_products() == 0:
            bootstrap_full_sync = True
    full_sync = requested_full_sync or bootstrap_full_sync
    sync_type = "shopify_products_full" if full_sync else "shopify_products_incremental"
    run_id = start_sync_run(sync_type)
    seen = 0
    processed = 0
    handles_seen = []
    metafield_result = {"attempted": 0, "synced": 0, "skipped": 0, "errors": []}
    sync_from = None
    try:
        _set_sync_attempt(LAST_ATTEMPTED_PRODUCT_SYNC_KEY)
        sync_config = dict(config)
        sync_config["max_products"] = max(int(sync_config.get("max_products") or 0), 1000)
        search = "status:active"
        if not full_sync:
            state = get_sync_state()
            last_success = _parse_datetime(state.get("last_successful_product_sync_at"))
            if not last_success:
                last_success = utc_now_datetime()
            sync_from = last_success - timedelta(minutes=state.get("sync_lookback_buffer_minutes") or DEFAULT_SYNC_LOOKBACK_BUFFER_MINUTES)
            search = f"status:active updated_at:>='{_datetime_to_shopify_query(sync_from)}'"

        for page in shopify_sync.iter_catalog_pages(search=search, page_size=50, config=sync_config):
            seen += len(page["products"])
            processed += upsert_products(page["products"])
            handles_seen.extend(product.get("handle") for product in page["products"] if product.get("handle"))
            if progress_callback:
                progress_callback(seen)
            del page
            gc.collect()
        if handles_seen:
            try:
                metafield_result = sync_product_edition_metafields_for_handles(
                    handles_seen,
                    config=config,
                )
            except Exception as metafield_error:
                metafield_result = {
                    "attempted": len(set(handles_seen)),
                    "synced": 0,
                    "skipped": len(set(handles_seen)),
                    "errors": [str(metafield_error)],
                }
        _set_sync_success(LAST_SUCCESSFUL_PRODUCT_SYNC_KEY)
        finish_sync_run(run_id, "Complete", seen, processed)
        return {
            "products_seen": seen,
            "products_processed": processed,
            "metafields_attempted": metafield_result.get("attempted", 0),
            "metafields_synced": metafield_result.get("synced", 0),
            "metafield_errors": metafield_result.get("errors", []),
            "sync_from": _datetime_to_setting(sync_from) if sync_from else "",
            "mode": "full" if full_sync else "incremental",
            "bootstrap_full_sync": bootstrap_full_sync,
        }
    except Exception as error:
        finish_sync_run(run_id, "Failed", seen, processed, "Shopify product sync failed.")
        log_app_error("shopify_product_sync_failed", str(error), {"records_seen": seen})
        raise


def _int_value(value, default=0):
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _clean_edition_run_status(status, *, active=True, sold_out=False):
    normalized = str(status or "").strip().lower().replace(" ", "_").replace("-", "_")
    if normalized in {"soldout", "sold_out", "sold"}:
        return SOLD_OUT_RUN_STATUS
    if normalized in {"inactive", "disabled", "paused"}:
        return INACTIVE_RUN_STATUS
    if normalized in {"archived", "archive", "legacy", "historical"}:
        return ARCHIVED_RUN_STATUS
    if normalized in {"active", "available", "live", "open"}:
        return ACTIVE_RUN_STATUS
    if sold_out:
        return SOLD_OUT_RUN_STATUS
    return ACTIVE_RUN_STATUS if active else INACTIVE_RUN_STATUS


def _status_flags_from_run(status):
    normalized = _clean_edition_run_status(status)
    return {
        "active": normalized == ACTIVE_RUN_STATUS,
        "sold_out": normalized == SOLD_OUT_RUN_STATUS,
    }


def _ensure_active_edition_runs_for_products(cur):
    cur.execute(
        f"""
        INSERT INTO edition_runs(
            edition_product_id, shopify_product_id, shopify_handle, product_title,
            edition_name, edition_total, next_edition_number, status, started_at, updated_at
        )
        SELECT ep.id,
               ep.shopify_product_id,
               ep.shopify_handle,
               ep.product_title,
               COALESCE(NULLIF(ep.edition_name, ''), '{DEFAULT_EDITION_NAME}'),
               COALESCE(ep.edition_total, 100),
               GREATEST(COALESCE(ep.next_edition_number, 1), 1),
               CASE
                   WHEN COALESCE(ep.sold_out, ep.is_sold_out, FALSE) THEN '{SOLD_OUT_RUN_STATUS}'
                   WHEN COALESCE(ep.active, ep.is_active, TRUE) THEN '{ACTIVE_RUN_STATUS}'
                   ELSE '{INACTIVE_RUN_STATUS}'
               END,
               now(),
               now()
        FROM edition_products ep
        WHERE ep.shopify_handle IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM edition_runs er
              WHERE er.shopify_handle = ep.shopify_handle
                AND er.status IN ('{ACTIVE_RUN_STATUS}', '{SOLD_OUT_RUN_STATUS}', '{INACTIVE_RUN_STATUS}')
          )
        """
    )
    cur.execute(
        f"""
        UPDATE edition_products ep
        SET active_edition_run_id=er.id,
            edition_name=er.edition_name,
            edition_total=COALESCE(er.edition_total, ep.edition_total, 100),
            next_edition_number=GREATEST(COALESCE(er.next_edition_number, ep.next_edition_number, 1), 1),
            active=(er.status='{ACTIVE_RUN_STATUS}'),
            is_active=(er.status='{ACTIVE_RUN_STATUS}'),
            sold_out=(er.status='{SOLD_OUT_RUN_STATUS}'),
            is_sold_out=(er.status='{SOLD_OUT_RUN_STATUS}'),
            updated_at=now()
        FROM edition_runs er
        WHERE er.shopify_handle=ep.shopify_handle
          AND er.id = (
              SELECT er2.id
              FROM edition_runs er2
              WHERE er2.shopify_handle=ep.shopify_handle
                AND er2.status IN ('{ACTIVE_RUN_STATUS}', '{SOLD_OUT_RUN_STATUS}', '{INACTIVE_RUN_STATUS}')
              ORDER BY CASE
                  WHEN er2.id = ep.active_edition_run_id THEN 0
                  WHEN er2.status='{ACTIVE_RUN_STATUS}' THEN 1
                  WHEN er2.status='{SOLD_OUT_RUN_STATUS}' THEN 2
                  ELSE 3
              END,
              er2.started_at DESC NULLS LAST,
              er2.created_at DESC NULLS LAST
              LIMIT 1
          )
        """
    )


def _active_run_lateral_sql():
    return f"""
        LEFT JOIN LATERAL (
            SELECT er.*
            FROM edition_runs er
            WHERE er.shopify_handle=ep.shopify_handle
              AND (
                  er.id=ep.active_edition_run_id
                  OR (
                      ep.active_edition_run_id IS NULL
                      AND er.status IN ('{ACTIVE_RUN_STATUS}', '{SOLD_OUT_RUN_STATUS}', '{INACTIVE_RUN_STATUS}')
                  )
              )
            ORDER BY CASE
                WHEN er.id=ep.active_edition_run_id THEN 0
                WHEN er.status='{ACTIVE_RUN_STATUS}' THEN 1
                WHEN er.status='{SOLD_OUT_RUN_STATUS}' THEN 2
                ELSE 3
            END,
            er.started_at DESC NULLS LAST,
            er.created_at DESC NULLS LAST
            LIMIT 1
        ) er ON TRUE
    """


def _normalize_edition_product_row(row):
    normalized = dict(row or {})
    run_id = normalized.get("edition_run_id") or normalized.get("active_edition_run_id")
    run_status = _clean_edition_run_status(
        normalized.get("run_status") or normalized.get("status"),
        active=bool(normalized.get("active")),
        sold_out=bool(normalized.get("sold_out")),
    )
    edition_total = max(
        _int_value(normalized.get("run_edition_total"), _int_value(normalized.get("edition_total"), 100)),
        1,
    )
    next_number = max(
        _int_value(
            normalized.get("run_next_edition_number"),
            _int_value(normalized.get("next_edition_number"), 1),
        ),
        1,
    )
    latest_sent = max(next_number - 1, 0)
    active_run_max = _int_value(normalized.get("active_run_max_assigned"), 0)
    historical_max = max(active_run_max, _int_value(normalized.get("last_assigned_edition"), 0))
    remaining = max(edition_total - latest_sent, 0)
    normalized.update(
        {
            "active_edition_run_id": run_id,
            "edition_run_id": run_id,
            "edition_name": normalized.get("run_edition_name")
            or normalized.get("edition_name")
            or DEFAULT_EDITION_NAME,
            "edition_total": edition_total,
            "next_edition_number": next_number,
            "latest_sent": latest_sent,
            "last_assigned_edition": latest_sent,
            "historical_max_assigned_edition": historical_max,
            "active_run_max_assigned": active_run_max,
            "remaining_count": remaining,
            "remaining_editions": remaining,
            "status": run_status,
            "active": run_status == ACTIVE_RUN_STATUS,
            "sold_out": run_status == SOLD_OUT_RUN_STATUS,
            "updated_at": normalized.get("run_updated_at") or normalized.get("updated_at"),
        }
    )
    return normalized


def _normalize_edition_product_rows(rows):
    return [_normalize_edition_product_row(row) for row in rows or []]


def _get_active_edition_run_for_handle(cur, shopify_handle, *, lock=False, create_missing=True):
    handle = str(shopify_handle or "").strip()
    if not handle:
        return None, None
    lock_sql = " FOR UPDATE" if lock else ""
    cur.execute(
        f"""
        SELECT *
        FROM edition_products
        WHERE shopify_handle=%s
        {lock_sql}
        """,
        (handle,),
    )
    product = cur.fetchone()
    if not product:
        return None, None

    active_run_id = product.get("active_edition_run_id")
    cur.execute(
        f"""
        SELECT *
        FROM edition_runs
        WHERE shopify_handle=%s
          AND (
              id=%s
              OR (
                  %s IS NULL
                  AND status IN ('{ACTIVE_RUN_STATUS}', '{SOLD_OUT_RUN_STATUS}', '{INACTIVE_RUN_STATUS}')
              )
          )
        ORDER BY CASE
            WHEN id=%s THEN 0
            WHEN status='{ACTIVE_RUN_STATUS}' THEN 1
            WHEN status='{SOLD_OUT_RUN_STATUS}' THEN 2
            ELSE 3
        END,
        started_at DESC NULLS LAST,
        created_at DESC NULLS LAST
        LIMIT 1
        {lock_sql}
        """,
        (handle, active_run_id, active_run_id, active_run_id),
    )
    run = cur.fetchone()
    if not run and create_missing:
        status = _clean_edition_run_status(
            "",
            active=bool(product.get("active") if product.get("active") is not None else True),
            sold_out=bool(product.get("sold_out")),
        )
        cur.execute(
            f"""
            INSERT INTO edition_runs(
                edition_product_id, shopify_product_id, shopify_handle, product_title,
                edition_name, edition_total, next_edition_number, status, started_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now(), now())
            RETURNING *
            """,
            (
                product.get("id"),
                product.get("shopify_product_id") or product.get("shopify_product_gid"),
                handle,
                product.get("product_title"),
                product.get("edition_name") or DEFAULT_EDITION_NAME,
                max(_int_value(product.get("edition_total"), 100), 1),
                max(_int_value(product.get("next_edition_number"), 1), 1),
                status,
            ),
        )
        run = cur.fetchone()

    if run and product.get("active_edition_run_id") != run.get("id"):
        cur.execute(
            """
            UPDATE edition_products
            SET active_edition_run_id=%s,
                edition_name=%s,
                updated_at=now()
            WHERE shopify_handle=%s
            """,
            (run.get("id"), run.get("edition_name") or DEFAULT_EDITION_NAME, handle),
        )
    return product, run


def _insert_edition_adjustment_with_cursor(
    cur,
    *,
    product,
    run,
    old_next,
    new_next,
    old_total,
    new_total,
    reason="",
    source="manual_app",
):
    if _int_value(old_next, 1) == _int_value(new_next, 1) and _int_value(old_total, 100) == _int_value(new_total, 100):
        return
    cur.execute(
        """
        INSERT INTO edition_adjustments(
            edition_product_id, edition_run_id, shopify_product_id, shopify_handle,
            old_next_edition_number, new_next_edition_number,
            old_edition_total, new_edition_total, reason, source
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            (product or {}).get("id"),
            (run or {}).get("id"),
            (run or {}).get("shopify_product_id") or (product or {}).get("shopify_product_id"),
            (run or {}).get("shopify_handle") or (product or {}).get("shopify_handle"),
            _int_value(old_next, 1),
            _int_value(new_next, 1),
            _int_value(old_total, 100),
            _int_value(new_total, 100),
            str(reason or "Manual edition adjustment"),
            str(source or "manual_app"),
        ),
    )


def list_edition_products(search="", limit=500, offset=0):
    ensure_schema()
    search_value = f"%{search.strip().lower()}%" if search.strip() else None
    limit_value = max(min(int(limit or 500), 5000), 1)
    offset_value = max(int(offset or 0), 0)
    with connect() as conn:
        with conn.cursor() as cur:
            _ensure_active_edition_runs_for_products(cur)
            active_run_join = _active_run_lateral_sql()
            if search_value:
                cur.execute(
                    f"""
                    SELECT ep.*, sp.admin_url, sp.online_store_url,
                           er.id AS edition_run_id,
                           er.edition_name AS run_edition_name,
                           er.edition_total AS run_edition_total,
                           er.next_edition_number AS run_next_edition_number,
                           er.status AS run_status,
                           er.updated_at AS run_updated_at,
                           COALESCE((
                               SELECT MAX(eo.edition_number)
                               FROM edition_orders eo
                               WHERE eo.edition_run_id = er.id
                           ), 0) AS active_run_max_assigned,
                           COALESCE(NULLIF(ep.featured_image_url, ''), NULLIF(sp.featured_image_url, ''), NULLIF(sp.image_url, '')) AS display_image_url,
                           CASE
                               WHEN COALESCE(ep.allow_counter_history_override, FALSE) THEN GREATEST(
                                   COALESCE(ep.last_assigned_edition, 0),
                                   GREATEST(COALESCE(ep.next_edition_number, 1) - 1, 0)
                               )
                               ELSE GREATEST(
                                   COALESCE(ep.last_assigned_edition, 0),
                                   COALESCE((
                                       SELECT MAX(eo.edition_number)
                                       FROM edition_orders eo
                                       WHERE eo.shopify_handle = ep.shopify_handle
                                   ), 0),
                                   GREATEST(COALESCE(ep.next_edition_number, 1) - 1, 0)
                               )
                           END AS last_assigned_edition,
                           (
                               SELECT COUNT(*)
                               FROM edition_orders eo
                               WHERE eo.shopify_handle = ep.shopify_handle
                           ) AS sold_count,
                           GREATEST(COALESCE(ep.edition_total, 100) - CASE
                               WHEN COALESCE(ep.allow_counter_history_override, FALSE) THEN GREATEST(
                                   COALESCE(ep.last_assigned_edition, 0),
                                   GREATEST(COALESCE(ep.next_edition_number, 1) - 1, 0)
                               )
                               ELSE GREATEST(
                                   COALESCE(ep.last_assigned_edition, 0),
                                   COALESCE((
                                       SELECT MAX(eo.edition_number)
                                       FROM edition_orders eo
                                       WHERE eo.shopify_handle = ep.shopify_handle
                                   ), 0),
                                   GREATEST(COALESCE(ep.next_edition_number, 1) - 1, 0)
                               )
                           END, 0) AS remaining_count,
                           GREATEST(COALESCE(ep.edition_total, 100) - COALESCE(ep.next_edition_number, 1) + 1, 0) AS remaining_editions
                    FROM edition_products ep
                    {active_run_join}
                    LEFT JOIN shopify_products sp ON sp.handle = ep.shopify_handle
                    WHERE LOWER(COALESCE(ep.product_title, '')) LIKE %s
                       OR LOWER(COALESCE(ep.shopify_handle, '')) LIKE %s
                       OR EXISTS (
                           SELECT 1
                           FROM shopify_variants sv
                           WHERE sv.shopify_product_id = ep.shopify_product_id
                             AND LOWER(COALESCE(sv.sku, '')) LIKE %s
                       )
                    ORDER BY ep.product_title NULLS LAST, ep.shopify_handle
                    LIMIT %s OFFSET %s
                    """,
                    (search_value, search_value, search_value, limit_value, offset_value),
                )
            else:
                cur.execute(
                    f"""
                    SELECT ep.*, sp.admin_url, sp.online_store_url,
                           er.id AS edition_run_id,
                           er.edition_name AS run_edition_name,
                           er.edition_total AS run_edition_total,
                           er.next_edition_number AS run_next_edition_number,
                           er.status AS run_status,
                           er.updated_at AS run_updated_at,
                           COALESCE((
                               SELECT MAX(eo.edition_number)
                               FROM edition_orders eo
                               WHERE eo.edition_run_id = er.id
                           ), 0) AS active_run_max_assigned,
                           COALESCE(NULLIF(ep.featured_image_url, ''), NULLIF(sp.featured_image_url, ''), NULLIF(sp.image_url, '')) AS display_image_url,
                           CASE
                               WHEN COALESCE(ep.allow_counter_history_override, FALSE) THEN GREATEST(
                                   COALESCE(ep.last_assigned_edition, 0),
                                   GREATEST(COALESCE(ep.next_edition_number, 1) - 1, 0)
                               )
                               ELSE GREATEST(
                                   COALESCE(ep.last_assigned_edition, 0),
                                   COALESCE((
                                       SELECT MAX(eo.edition_number)
                                       FROM edition_orders eo
                                       WHERE eo.shopify_handle = ep.shopify_handle
                                   ), 0),
                                   GREATEST(COALESCE(ep.next_edition_number, 1) - 1, 0)
                               )
                           END AS last_assigned_edition,
                           (
                               SELECT COUNT(*)
                               FROM edition_orders eo
                               WHERE eo.shopify_handle = ep.shopify_handle
                           ) AS sold_count,
                           GREATEST(COALESCE(ep.edition_total, 100) - CASE
                               WHEN COALESCE(ep.allow_counter_history_override, FALSE) THEN GREATEST(
                                   COALESCE(ep.last_assigned_edition, 0),
                                   GREATEST(COALESCE(ep.next_edition_number, 1) - 1, 0)
                               )
                               ELSE GREATEST(
                                   COALESCE(ep.last_assigned_edition, 0),
                                   COALESCE((
                                       SELECT MAX(eo.edition_number)
                                       FROM edition_orders eo
                                       WHERE eo.shopify_handle = ep.shopify_handle
                                   ), 0),
                                   GREATEST(COALESCE(ep.next_edition_number, 1) - 1, 0)
                               )
                           END, 0) AS remaining_count,
                           GREATEST(COALESCE(ep.edition_total, 100) - COALESCE(ep.next_edition_number, 1) + 1, 0) AS remaining_editions
                    FROM edition_products ep
                    {active_run_join}
                    LEFT JOIN shopify_products sp ON sp.handle = ep.shopify_handle
                    ORDER BY ep.product_title NULLS LAST, ep.shopify_handle
                    LIMIT %s OFFSET %s
                    """,
                    (limit_value, offset_value),
                )
            return _normalize_edition_product_rows(cur.fetchall())


def list_edition_products_read_only(search="", limit=500, offset=0):
    search_value = f"%{search.strip().lower()}%" if search.strip() else None
    limit_value = max(min(int(limit or 500), 5000), 1)
    offset_value = max(int(offset or 0), 0)
    started = time.perf_counter()
    with connect() as conn:
        with conn.cursor() as cur:
            active_run_join = _active_run_lateral_sql()
            if search_value:
                cur.execute(
                    f"""
                    SELECT ep.*, sp.admin_url, sp.online_store_url,
                           er.id AS edition_run_id,
                           er.edition_name AS run_edition_name,
                           er.edition_total AS run_edition_total,
                           er.next_edition_number AS run_next_edition_number,
                           er.status AS run_status,
                           er.updated_at AS run_updated_at,
                           COALESCE((
                               SELECT MAX(eo.edition_number)
                               FROM edition_orders eo
                               WHERE eo.edition_run_id = er.id
                           ), 0) AS active_run_max_assigned,
                           COALESCE(NULLIF(ep.featured_image_url, ''), NULLIF(sp.featured_image_url, ''), NULLIF(sp.image_url, '')) AS display_image_url,
                           CASE
                               WHEN COALESCE(ep.allow_counter_history_override, FALSE) THEN GREATEST(
                                   COALESCE(ep.last_assigned_edition, 0),
                                   GREATEST(COALESCE(ep.next_edition_number, 1) - 1, 0)
                               )
                               ELSE GREATEST(
                                   COALESCE(ep.last_assigned_edition, 0),
                                   COALESCE((
                                       SELECT MAX(eo.edition_number)
                                       FROM edition_orders eo
                                       WHERE eo.shopify_handle = ep.shopify_handle
                                   ), 0),
                                   GREATEST(COALESCE(ep.next_edition_number, 1) - 1, 0)
                               )
                           END AS last_assigned_edition,
                           (
                               SELECT COUNT(*)
                               FROM edition_orders eo
                               WHERE eo.shopify_handle = ep.shopify_handle
                           ) AS sold_count,
                           GREATEST(COALESCE(ep.edition_total, 100) - CASE
                               WHEN COALESCE(ep.allow_counter_history_override, FALSE) THEN GREATEST(
                                   COALESCE(ep.last_assigned_edition, 0),
                                   GREATEST(COALESCE(ep.next_edition_number, 1) - 1, 0)
                               )
                               ELSE GREATEST(
                                   COALESCE(ep.last_assigned_edition, 0),
                                   COALESCE((
                                       SELECT MAX(eo.edition_number)
                                       FROM edition_orders eo
                                       WHERE eo.shopify_handle = ep.shopify_handle
                                   ), 0),
                                   GREATEST(COALESCE(ep.next_edition_number, 1) - 1, 0)
                               )
                           END, 0) AS remaining_count,
                           GREATEST(COALESCE(ep.edition_total, 100) - COALESCE(ep.next_edition_number, 1) + 1, 0) AS remaining_editions
                    FROM edition_products ep
                    {active_run_join}
                    LEFT JOIN shopify_products sp ON sp.handle = ep.shopify_handle
                    WHERE LOWER(COALESCE(ep.product_title, '')) LIKE %s
                       OR LOWER(COALESCE(ep.shopify_handle, '')) LIKE %s
                       OR EXISTS (
                           SELECT 1
                           FROM shopify_variants sv
                           WHERE sv.shopify_product_id = ep.shopify_product_id
                             AND LOWER(COALESCE(sv.sku, '')) LIKE %s
                       )
                    ORDER BY ep.product_title NULLS LAST, ep.shopify_handle
                    LIMIT %s OFFSET %s
                    """,
                    (search_value, search_value, search_value, limit_value, offset_value),
                )
            else:
                cur.execute(
                    f"""
                    SELECT ep.*, sp.admin_url, sp.online_store_url,
                           er.id AS edition_run_id,
                           er.edition_name AS run_edition_name,
                           er.edition_total AS run_edition_total,
                           er.next_edition_number AS run_next_edition_number,
                           er.status AS run_status,
                           er.updated_at AS run_updated_at,
                           COALESCE((
                               SELECT MAX(eo.edition_number)
                               FROM edition_orders eo
                               WHERE eo.edition_run_id = er.id
                           ), 0) AS active_run_max_assigned,
                           COALESCE(NULLIF(ep.featured_image_url, ''), NULLIF(sp.featured_image_url, ''), NULLIF(sp.image_url, '')) AS display_image_url,
                           CASE
                               WHEN COALESCE(ep.allow_counter_history_override, FALSE) THEN GREATEST(
                                   COALESCE(ep.last_assigned_edition, 0),
                                   GREATEST(COALESCE(ep.next_edition_number, 1) - 1, 0)
                               )
                               ELSE GREATEST(
                                   COALESCE(ep.last_assigned_edition, 0),
                                   COALESCE((
                                       SELECT MAX(eo.edition_number)
                                       FROM edition_orders eo
                                       WHERE eo.shopify_handle = ep.shopify_handle
                                   ), 0),
                                   GREATEST(COALESCE(ep.next_edition_number, 1) - 1, 0)
                               )
                           END AS last_assigned_edition,
                           (
                               SELECT COUNT(*)
                               FROM edition_orders eo
                               WHERE eo.shopify_handle = ep.shopify_handle
                           ) AS sold_count,
                           GREATEST(COALESCE(ep.edition_total, 100) - CASE
                               WHEN COALESCE(ep.allow_counter_history_override, FALSE) THEN GREATEST(
                                   COALESCE(ep.last_assigned_edition, 0),
                                   GREATEST(COALESCE(ep.next_edition_number, 1) - 1, 0)
                               )
                               ELSE GREATEST(
                                   COALESCE(ep.last_assigned_edition, 0),
                                   COALESCE((
                                       SELECT MAX(eo.edition_number)
                                       FROM edition_orders eo
                                       WHERE eo.shopify_handle = ep.shopify_handle
                                   ), 0),
                                   GREATEST(COALESCE(ep.next_edition_number, 1) - 1, 0)
                               )
                           END, 0) AS remaining_count,
                           GREATEST(COALESCE(ep.edition_total, 100) - COALESCE(ep.next_edition_number, 1) + 1, 0) AS remaining_editions
                    FROM edition_products ep
                    {active_run_join}
                    LEFT JOIN shopify_products sp ON sp.handle = ep.shopify_handle
                    ORDER BY ep.product_title NULLS LAST, ep.shopify_handle
                    LIMIT %s OFFSET %s
                    """,
                    (limit_value, offset_value),
                )
            rows = _normalize_edition_product_rows(cur.fetchall())
    print(f"PERF Edition Ops read-only products {(time.perf_counter() - started):.3f}s rows={len(rows)}", flush=True)
    return rows


def run_db_health_repair():
    started = time.perf_counter()
    ensure_schema()
    repaired = 0
    with connect() as conn:
        with conn.cursor() as cur:
            before = conn.info.transaction_status if hasattr(conn, "info") else None
            _ = before
            _ensure_active_edition_runs_for_products(cur)
            repaired = cur.rowcount if getattr(cur, "rowcount", -1) and cur.rowcount > 0 else 0
        conn.commit()
    return {
        "ok": True,
        "active_run_rows_touched": repaired,
        "duration_ms": int((time.perf_counter() - started) * 1000),
    }


def get_edition_counter_state(shopify_handle):
    ensure_schema()
    handle = str(shopify_handle or "").strip()
    if not handle:
        raise ValueError("Shopify handle is required.")
    with connect() as conn:
        with conn.cursor() as cur:
            product, run = _get_active_edition_run_for_handle(cur, handle, create_missing=True)
            if not product:
                raise ValueError(f"No edition product found for {handle}.")
            cur.execute(
                """
                SELECT COALESCE(MAX(edition_number), 0) AS max_assigned
                FROM edition_orders
                WHERE edition_run_id=%s
                """,
                (run.get("id") if run else None,),
            )
            active_run_max = _int_value((cur.fetchone() or {}).get("max_assigned"), 0)
            cur.execute(
                """
                SELECT ep.*,
                       er.id AS edition_run_id,
                       er.edition_name AS run_edition_name,
                       er.edition_total AS run_edition_total,
                       er.next_edition_number AS run_next_edition_number,
                       er.status AS run_status,
                       er.updated_at AS run_updated_at,
                       %s AS active_run_max_assigned,
                       ep.shopify_handle,
                       ep.product_title,
                       COALESCE(ep.active, ep.is_active, TRUE) AS active,
                       COALESCE(ep.sold_out, ep.is_sold_out, FALSE) AS sold_out,
                       COALESCE(ep.allow_counter_history_override, FALSE) AS allow_counter_history_override,
                       COALESCE(ep.last_assigned_edition, 0) AS stored_last_assigned_edition,
                       COALESCE((
                           SELECT MAX(eo.edition_number)
                           FROM edition_orders eo
                           WHERE eo.shopify_handle = ep.shopify_handle
                       ), 0) AS max_assigned_edition
                FROM edition_products ep
                LEFT JOIN edition_runs er ON er.id=%s
                WHERE ep.shopify_handle=%s
                """,
                (active_run_max, run.get("id") if run else None, handle),
            )
            row = cur.fetchone()
    if not row:
        raise ValueError(f"No edition product found for {handle}.")
    normalized = _normalize_edition_product_row(row)
    normalized["max_assigned_edition"] = max(
        _int_value(row.get("max_assigned_edition"), 0),
        _int_value(normalized.get("active_run_max_assigned"), 0),
    )
    return normalized


def update_edition_product(
    shopify_handle,
    *,
    edition_name=None,
    edition_total=None,
    next_edition_number=None,
    active=None,
    sold_out=None,
    status=None,
    current_edition=None,
    allow_history_override=False,
    reason="Manual edition edit",
):
    ensure_schema()
    handle = str(shopify_handle or "").strip()
    if not handle:
        raise ValueError("Shopify handle is required.")
    with connect() as conn:
        with conn.cursor() as cur:
            _update_edition_product_with_cursor(
                cur,
                handle,
                edition_name=edition_name,
                edition_total=edition_total,
                next_edition_number=next_edition_number,
                active=active,
                sold_out=sold_out,
                status=status,
                current_edition=current_edition,
                allow_history_override=allow_history_override,
                reason=reason,
            )
        conn.commit()
    return get_edition_counter_state(handle)


def _update_edition_product_with_cursor(
    cur,
    shopify_handle,
    *,
    edition_name=None,
    edition_total=None,
    next_edition_number=None,
    active=None,
    sold_out=None,
    status=None,
    current_edition=None,
    allow_history_override=False,
    reason="Manual edition edit",
):
    handle = str(shopify_handle or "").strip()
    if not handle:
        raise ValueError("Shopify handle is required.")
    product, run = _get_active_edition_run_for_handle(cur, handle, lock=True, create_missing=True)
    if not product or not run:
        raise ValueError(f"No edition product found for {handle}.")

    old_next = max(_int_value(run.get("next_edition_number"), 1), 1)
    old_total = max(_int_value(run.get("edition_total"), 100), 1)
    new_total = max(_int_value(edition_total, old_total), 1)
    if current_edition is not None:
        current = _int_value(current_edition, 0)
        if current < 0:
            raise ValueError("Latest sent cannot be below 0.")
        proposed_next = current + 1
    elif next_edition_number is not None:
        proposed_next = _int_value(next_edition_number, old_next)
    else:
        proposed_next = old_next

    cur.execute(
        """
        SELECT COALESCE(MAX(edition_number), 0) AS max_assigned
        FROM edition_orders
        WHERE shopify_handle = %s
        """,
        (handle,),
    )
    max_assigned = _int_value((cur.fetchone() or {}).get("max_assigned"), 0)
    if not allow_history_override:
        proposed_next = max(proposed_next, max_assigned + 1 if max_assigned > 0 else 1)

    if proposed_next < 1:
        raise ValueError("Next edition number must be at least 1.")
    if new_total < 1:
        raise ValueError("Edition total must be at least 1.")

    requested_status = _clean_edition_run_status(
        status,
        active=bool(active if active is not None else run.get("status") == ACTIVE_RUN_STATUS),
        sold_out=bool(sold_out if sold_out is not None else run.get("status") == SOLD_OUT_RUN_STATUS),
    )
    if sold_out is True or proposed_next > new_total:
        requested_status = SOLD_OUT_RUN_STATUS
    elif active is False and status is None:
        requested_status = INACTIVE_RUN_STATUS
    elif active is True and sold_out is False and status is None:
        requested_status = ACTIVE_RUN_STATUS

    latest_sent = proposed_next - 1
    remaining = new_total - latest_sent

    new_name = str(edition_name or run.get("edition_name") or DEFAULT_EDITION_NAME).strip() or DEFAULT_EDITION_NAME
    cur.execute(
        """
        UPDATE edition_runs
        SET edition_name=%s,
            edition_total=%s,
            next_edition_number=%s,
            status=%s,
            archived_at=CASE WHEN %s = 'archived' THEN COALESCE(archived_at, now()) ELSE archived_at END,
            updated_at=now()
        WHERE id=%s
        RETURNING *
        """,
        (
            new_name,
            new_total,
            proposed_next,
            requested_status,
            requested_status,
            run.get("id"),
        ),
    )
    updated_run = cur.fetchone() or run
    flags = _status_flags_from_run(requested_status)
    cur.execute(
        """
        UPDATE edition_products
        SET active_edition_run_id=%s,
            edition_name=%s,
            edition_total=%s,
            next_edition_number=%s,
            last_assigned_edition=%s,
            remaining_count=%s,
            active=%s,
            is_active=%s,
            sold_out=%s,
            is_sold_out=%s,
            allow_counter_history_override=%s,
            updated_at=now()
        WHERE shopify_handle=%s
        """,
        (
            updated_run.get("id"),
            new_name,
            new_total,
            proposed_next,
            latest_sent,
            max(remaining, 0),
            flags["active"],
            flags["active"],
            flags["sold_out"],
            flags["sold_out"],
            bool(allow_history_override),
            handle,
        ),
    )
    _insert_edition_adjustment_with_cursor(
        cur,
        product=product,
        run=updated_run,
        old_next=old_next,
        new_next=proposed_next,
        old_total=old_total,
        new_total=new_total,
        reason=reason,
        source="manual_app",
    )
    return {"handle": handle, "next_edition_number": proposed_next, "edition_total": new_total}


def update_edition_products_batch(rows, reason="Manual edition edit"):
    ensure_schema()
    results = []
    with connect() as conn:
        with conn.cursor() as cur:
            for row in rows or []:
                handle = str((row or {}).get("handle") or (row or {}).get("shopify_handle") or "").strip()
                key = str((row or {}).get("edition_product_id") or handle or "")
                cur.execute("SAVEPOINT edition_ops_batch_row")
                try:
                    _update_edition_product_with_cursor(
                        cur,
                        handle,
                        edition_name=(row or {}).get("edition_name"),
                        edition_total=(row or {}).get("edition_total"),
                        next_edition_number=(row or {}).get("next_edition_number"),
                        active=(row or {}).get("active"),
                        sold_out=(row or {}).get("sold_out"),
                        allow_history_override=bool((row or {}).get("allow_history_override")),
                        reason=reason,
                    )
                    results.append({"ok": True, "handle": handle, "key": key})
                    cur.execute("RELEASE SAVEPOINT edition_ops_batch_row")
                except Exception as error:
                    cur.execute("ROLLBACK TO SAVEPOINT edition_ops_batch_row")
                    results.append({"ok": False, "handle": handle, "key": key, "message": str(error)})
        conn.commit()
    return results


def start_new_edition_run(shopify_handle, *, edition_name="", edition_total=100, notes="", reason="Start new edition run"):
    ensure_schema()
    handle = str(shopify_handle or "").strip()
    if not handle:
        raise ValueError("Shopify handle is required.")
    new_name = str(edition_name or DEFAULT_EDITION_NAME).strip() or DEFAULT_EDITION_NAME
    new_total = max(_int_value(edition_total, 100), 1)
    with connect() as conn:
        with conn.cursor() as cur:
            product, current_run = _get_active_edition_run_for_handle(cur, handle, lock=True, create_missing=True)
            if not product:
                raise ValueError(f"No edition product found for {handle}.")
            old_next = _int_value((current_run or {}).get("next_edition_number"), _int_value(product.get("next_edition_number"), 1))
            old_total = _int_value((current_run or {}).get("edition_total"), _int_value(product.get("edition_total"), 100))
            if current_run:
                cur.execute(
                    """
                    UPDATE edition_runs
                    SET status=%s,
                        archived_at=COALESCE(archived_at, now()),
                        updated_at=now()
                    WHERE id=%s
                    """,
                    (ARCHIVED_RUN_STATUS, current_run.get("id")),
                )
            cur.execute(
                """
                INSERT INTO edition_runs(
                    edition_product_id, shopify_product_id, shopify_handle, product_title,
                    edition_name, edition_total, next_edition_number, status, notes, started_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, 1, %s, %s, now(), now())
                RETURNING *
                """,
                (
                    product.get("id"),
                    product.get("shopify_product_id") or product.get("shopify_product_gid"),
                    handle,
                    product.get("product_title"),
                    new_name,
                    new_total,
                    ACTIVE_RUN_STATUS,
                    str(notes or ""),
                ),
            )
            new_run = cur.fetchone()
            cur.execute(
                """
                UPDATE edition_products
                SET active_edition_run_id=%s,
                    edition_name=%s,
                    edition_total=%s,
                    next_edition_number=1,
                    last_assigned_edition=0,
                    remaining_count=%s,
                    active=TRUE,
                    is_active=TRUE,
                    sold_out=FALSE,
                    is_sold_out=FALSE,
                    allow_counter_history_override=FALSE,
                    updated_at=now()
                WHERE shopify_handle=%s
                """,
                (new_run.get("id"), new_name, new_total, new_total, handle),
            )
            _insert_edition_adjustment_with_cursor(
                cur,
                product=product,
                run=new_run,
                old_next=old_next,
                new_next=1,
                old_total=old_total,
                new_total=new_total,
                reason=reason or f"Started new edition run: {new_name}",
                source="manual_app",
            )
        conn.commit()
    return get_edition_counter_state(handle)


def list_edition_adjustments(search="", limit=100):
    ensure_schema()
    search_value = f"%{search.strip().lower()}%" if search.strip() else None
    with connect() as conn:
        with conn.cursor() as cur:
            if search_value:
                cur.execute(
                    """
                    SELECT ea.*, er.edition_name, er.product_title
                    FROM edition_adjustments ea
                    LEFT JOIN edition_runs er ON er.id=ea.edition_run_id
                    WHERE LOWER(COALESCE(ea.shopify_handle, '')) LIKE %s
                       OR LOWER(COALESCE(er.product_title, '')) LIKE %s
                       OR LOWER(COALESCE(er.edition_name, '')) LIKE %s
                    ORDER BY ea.created_at DESC
                    LIMIT %s
                    """,
                    (search_value, search_value, search_value, limit),
                )
            else:
                cur.execute(
                    """
                    SELECT ea.*, er.edition_name, er.product_title
                    FROM edition_adjustments ea
                    LEFT JOIN edition_runs er ON er.id=ea.edition_run_id
                    ORDER BY ea.created_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
            return cur.fetchall()


def reset_active_edition_counters_to_zero_sold(reason="Developer reset all active edition counters to 0 sold"):
    ensure_schema()
    reset_rows = []
    with connect() as conn:
        with conn.cursor() as cur:
            _ensure_active_edition_runs_for_products(cur)
            cur.execute(
                f"""
                SELECT ep.id AS edition_product_id,
                       er.id AS edition_run_id,
                       er.shopify_product_id,
                       er.shopify_handle,
                       COALESCE(er.next_edition_number, ep.next_edition_number, 1) AS old_next_edition_number,
                       COALESCE(er.edition_total, ep.edition_total, 100) AS edition_total
                FROM edition_runs er
                JOIN edition_products ep ON ep.shopify_handle=er.shopify_handle
                WHERE er.status=%s
                  AND COALESCE(ep.active, ep.is_active, TRUE) = TRUE
                ORDER BY er.shopify_handle
                """,
                (ACTIVE_RUN_STATUS,),
            )
            reset_rows = cur.fetchall()
            for row in reset_rows:
                edition_total = max(_int_value(row.get("edition_total"), 100), 1)
                edition_display_text = f"Next Available Edition {format_edition_display_number(1, edition_total)}"
                cur.execute(
                    """
                    UPDATE edition_runs
                    SET next_edition_number=1,
                        updated_at=now()
                    WHERE id=%s
                    """,
                    (row.get("edition_run_id"),),
                )
                cur.execute(
                    """
                    UPDATE edition_products
                    SET active_edition_run_id=%s,
                        next_edition_number=1,
                        last_assigned_edition=0,
                        sold_count=0,
                        remaining_count=%s,
                        edition_status='limited_release',
                        edition_display_text=%s,
                        sold_out=FALSE,
                        is_sold_out=FALSE,
                        updated_at=now()
                    WHERE shopify_handle=%s
                    """,
                    (
                        row.get("edition_run_id"),
                        edition_total,
                        edition_display_text,
                        row.get("shopify_handle"),
                    ),
                )
                _insert_edition_adjustment_with_cursor(
                    cur,
                    product={"id": row.get("edition_product_id"), "shopify_handle": row.get("shopify_handle")},
                    run={
                        "id": row.get("edition_run_id"),
                        "shopify_product_id": row.get("shopify_product_id"),
                        "shopify_handle": row.get("shopify_handle"),
                    },
                    old_next=row.get("old_next_edition_number"),
                    new_next=1,
                    old_total=edition_total,
                    new_total=edition_total,
                    reason=reason,
                    source="developer_reset",
                )
            cur.execute(
                """
                INSERT INTO app_errors(source, severity, error_type, message, context)
                VALUES ('sports_cave_os', 'info', 'edition_counters_reset_to_zero_sold', %s, %s::jsonb)
                """,
                (
                    reason,
                    json_dumps(
                        {
                            "active_runs_reset": len(reset_rows),
                            "next_edition_number": 1,
                        }
                    ),
                ),
            )
        conn.commit()
    return {"active_runs_reset": len(reset_rows)}


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def format_edition_display_number(edition_number, edition_total):
    number = _safe_int(edition_number, 0)
    total = _safe_int(edition_total, 100)
    if number <= 0:
        return f"Numbered Edition of {total}"
    return f"#{number:03d}/{total}"


def calculate_product_edition_metafield_values(row):
    edition_total = max(_safe_int(row.get("edition_total"), 100), 1)
    next_number = max(_safe_int(row.get("next_edition_number"), 1), 1)
    last_assigned = max(next_number - 1, 0)
    sold_count = last_assigned
    remaining_count = max(edition_total - last_assigned, 0)
    is_sold_out = bool(row.get("sold_out")) or next_number > edition_total or remaining_count <= 0
    if is_sold_out:
        edition_status = "sold_out"
        edition_display_text = "Sold Out Archive"
    elif remaining_count <= 5:
        edition_status = "final_editions"
        edition_display_text = f"Final Editions — Only {remaining_count} Remaining"
    elif remaining_count <= 12:
        edition_status = "selling_quickly"
        edition_display_text = f"Next Available Edition {format_edition_display_number(next_number, edition_total)}"
    else:
        edition_status = "limited_release"
        edition_display_text = f"Next Available Edition {format_edition_display_number(next_number, edition_total)}"
    return {
        "edition_total": edition_total,
        "next_edition_number": next_number,
        "last_assigned_edition": last_assigned,
        "sold_count": sold_count,
        "remaining_count": remaining_count,
        "is_sold_out": is_sold_out,
        "edition_status": edition_status,
        "edition_display_text": edition_display_text,
    }


def get_product_edition_metafield_payload(shopify_handle):
    ensure_schema()
    handle = str(shopify_handle or "").strip()
    if not handle:
        raise ValueError("Shopify handle is required.")
    with connect() as conn:
        with conn.cursor() as cur:
            _get_active_edition_run_for_handle(cur, handle, create_missing=True)
            active_run_join = _active_run_lateral_sql()
            cur.execute(
                f"""
                SELECT ep.*, sp.shopify_product_id AS synced_shopify_product_id,
                       sp.shopify_product_gid AS synced_shopify_product_gid,
                       sp.admin_url, sp.online_store_url,
                       er.id AS edition_run_id,
                       er.edition_name AS run_edition_name,
                       er.edition_total AS run_edition_total,
                       er.next_edition_number AS run_next_edition_number,
                       er.status AS run_status,
                       er.updated_at AS run_updated_at,
                       COALESCE((
                           SELECT MAX(eo.edition_number)
                           FROM edition_orders eo
                           WHERE eo.edition_run_id = er.id
                       ), 0) AS active_run_max_assigned,
                       CASE
                           WHEN COALESCE(ep.allow_counter_history_override, FALSE) THEN GREATEST(
                               COALESCE(ep.last_assigned_edition, 0),
                               GREATEST(COALESCE(ep.next_edition_number, 1) - 1, 0)
                           )
                           ELSE GREATEST(
                               COALESCE(ep.last_assigned_edition, 0),
                               COALESCE((
                                   SELECT MAX(eo.edition_number)
                                   FROM edition_orders eo
                                   WHERE eo.shopify_handle = ep.shopify_handle
                               ), 0),
                               GREATEST(COALESCE(ep.next_edition_number, 1) - 1, 0)
                           )
                       END AS last_assigned_edition,
                       (
                           SELECT COUNT(*)
                           FROM edition_orders eo
                           WHERE eo.shopify_handle = ep.shopify_handle
                       ) AS sold_count
                FROM edition_products ep
                {active_run_join}
                LEFT JOIN shopify_products sp ON sp.handle = ep.shopify_handle
                WHERE ep.shopify_handle=%s
                """,
                (handle,),
            )
            row = cur.fetchone()
    if not row:
        raise ValueError(f"No edition product found for {handle}.")
    row = _normalize_edition_product_row(row)
    owner_gid = (
        row.get("shopify_product_gid")
        or row.get("shopify_product_id")
        or row.get("synced_shopify_product_gid")
        or row.get("synced_shopify_product_id")
        or ""
    )
    if not owner_gid:
        raise ValueError(f"{handle} does not have a Shopify product ID yet. Run Sync Products first.")
    values = calculate_product_edition_metafield_values(row)
    return {
        **row,
        **values,
        "shopify_product_id": owner_gid,
        "shopify_product_gid": owner_gid,
        "shopify_handle": handle,
    }


def _mark_product_metafields_sync(shopify_handle, payload, status, error_message=""):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE edition_products
                SET last_assigned_edition=%s,
                    sold_count=%s,
                    remaining_count=%s,
                    edition_status=%s,
                    edition_display_text=%s,
                    metafields_synced_at=CASE WHEN %s = 'Synced' THEN now() ELSE metafields_synced_at END,
                    metafields_sync_status=%s,
                    last_metafield_error=%s,
                    sold_out=%s,
                    is_sold_out=%s,
                    updated_at=now()
                WHERE shopify_handle=%s
                """,
                (
                    payload.get("last_assigned_edition") or 0,
                    payload.get("sold_count") or 0,
                    payload.get("remaining_count") or 0,
                    payload.get("edition_status") or "",
                    payload.get("edition_display_text") or "",
                    status,
                    status,
                    str(error_message or "")[:1000],
                    bool(payload.get("is_sold_out")),
                    bool(payload.get("is_sold_out")),
                    shopify_handle,
                ),
            )
        conn.commit()


def sync_product_edition_metafields(shopify_handle, config=None, request_post=None):
    payload = get_product_edition_metafield_payload(shopify_handle)
    try:
        result = shopify_sync.sync_limited_edition_metafields_for_products(
            [
                {
                    "shopify_product_id": payload.get("shopify_product_id"),
                    "handle": payload.get("shopify_handle") or shopify_handle,
                    "title": payload.get("product_title") or payload.get("title") or shopify_handle,
                    "edition_enabled": not bool(payload.get("is_archived")),
                    "edition_total": payload.get("edition_total"),
                    "edition_next_number": payload.get("next_edition_number"),
                    "edition_sold_count": payload.get("sold_count"),
                    "edition_remaining": payload.get("remaining_count"),
                    "edition_status": payload.get("edition_status"),
                }
            ],
            config=config,
            request_post=request_post,
            raise_on_failure=True,
        )
        try:
            shopify_sync.sync_product_edition_metafields(
                payload,
                config=config,
                request_post=request_post,
            )
        except Exception as legacy_error:
            log_app_error(
                "legacy_product_metafield_sync_failed",
                str(legacy_error),
                {"shopify_handle": shopify_handle},
            )
        _mark_product_metafields_sync(shopify_handle, payload, "Synced", "")
        return {"shopify_handle": shopify_handle, "payload": payload, **result}
    except Exception as error:
        _mark_product_metafields_sync(shopify_handle, payload, "Failed", str(error))
        log_app_error(
            "product_metafield_sync_failed",
            str(error),
            {"shopify_handle": shopify_handle},
        )
        raise


def sync_product_edition_metafields_for_handles(handles, config=None, progress_callback=None):
    ensure_schema()
    unique_handles = []
    seen_handles = set()
    for handle in handles or []:
        clean_handle = str(handle or "").strip()
        if clean_handle and clean_handle not in seen_handles:
            unique_handles.append(clean_handle)
            seen_handles.add(clean_handle)
    run_id = start_sync_run("shopify_product_metafields")
    synced = 0
    skipped = 0
    errors = []
    try:
        for index, handle in enumerate(unique_handles, start=1):
            try:
                sync_product_edition_metafields(handle, config=config)
                synced += 1
            except Exception as error:
                skipped += 1
                errors.append(f"{handle}: {error}")
            if progress_callback:
                progress_callback(index, len(unique_handles), handle)
        finish_sync_run(
            run_id,
            "Complete" if not errors else "Complete With Warnings",
            len(unique_handles),
            synced,
            "; ".join(errors[:3]),
        )
        return {
            "attempted": len(unique_handles),
            "synced": synced,
            "skipped": skipped,
            "errors": errors[:10],
        }
    except Exception as error:
        finish_sync_run(run_id, "Failed", len(unique_handles), synced, str(error))
        log_app_error("product_metafield_bulk_sync_failed", str(error), {})
        raise


def sync_all_product_edition_metafields(config=None, search="", limit=1000, progress_callback=None):
    products = list_edition_products(search=search, limit=limit)
    return sync_product_edition_metafields_for_handles(
        [product.get("shopify_handle") for product in products],
        config=config,
        progress_callback=progress_callback,
    )


def _certificate_rows_for_order(shopify_order_id):
    ensure_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.id AS certificate_row_id, c.certificate_id, c.edition_number,
                       c.edition_total,
                       COALESCE(NULLIF(c.shopify_file_url, ''), NULLIF(c.certificate_file_url, '')) AS shopify_file_url,
                       c.certificate_pdf_url, c.certificate_print_jpg_url, c.certificate_preview_image_url,
                       c.shopify_file_id, c.shopify_pdf_file_id, c.shopify_print_jpg_file_id, c.shopify_preview_file_id,
                       c.shopify_file_status, c.certificate_status,
                       c.shopify_customer_id, c.customer_email, c.customer_name,
                       c.shopify_order_name, c.shopify_line_item_id, c.shopify_product_id,
                       c.shopify_variant_id, c.product_title AS certificate_product_title,
                       c.product_handle, c.variant_title AS certificate_variant_title,
                       c.line_item_unit_index, c.purchase_date, c.created_at, c.generated_at,
                       eo.product_title, eo.shopify_handle, eo.variant_title,
                       eo.customer_name AS edition_customer_name,
                       eo.customer_email AS edition_customer_email,
                       o.shopify_order_id, o.customer_id, o.order_name
                FROM certificates c
                LEFT JOIN edition_orders eo ON eo.id::text=COALESCE(c.related_edition_order_id::text, c.edition_order_id::text)
                LEFT JOIN shopify_orders o ON o.shopify_order_id=c.shopify_order_id
                WHERE c.shopify_order_id=%s
                ORDER BY c.generated_at ASC, c.id ASC
                """,
                (shopify_order_id,),
            )
            return cur.fetchall()


def sync_order_certificate_metafields(shopify_order_id, config=None, request_post=None):
    order_id = str(shopify_order_id or "").strip()
    if not order_id:
        return {"count": 0, "skipped": True, "reason": "Missing Shopify order ID."}
    rows = _certificate_rows_for_order(order_id)
    if not rows:
        return {"count": 0, "skipped": True, "reason": "No certificates for this order."}
    certificates = []
    for row in rows:
        certificates.append(
            {
                "shopify_customer_id": row.get("shopify_customer_id") or row.get("customer_id") or "",
                "customer_email": row.get("customer_email") or row.get("edition_customer_email") or "",
                "customer_name": row.get("customer_name") or row.get("edition_customer_name") or "",
                "shopify_order_id": row.get("shopify_order_id") or order_id,
                "shopify_order_name": row.get("shopify_order_name") or row.get("order_name") or "",
                "shopify_line_item_id": row.get("shopify_line_item_id") or "",
                "shopify_product_id": row.get("shopify_product_id") or "",
                "shopify_variant_id": row.get("shopify_variant_id") or "",
                "product_title": row.get("certificate_product_title") or row.get("product_title") or "",
                "shopify_handle": row.get("product_handle") or row.get("shopify_handle") or "",
                "product_handle": row.get("product_handle") or row.get("shopify_handle") or "",
                "variant_title": row.get("certificate_variant_title") or row.get("variant_title") or "",
                "edition_number": row.get("edition_number") or 0,
                "edition_total": row.get("edition_total") or 100,
                "edition_display": format_edition_display_number(
                    row.get("edition_number"),
                    row.get("edition_total") or 100,
                ),
                "certificate_id": row.get("certificate_id") or "",
                "shopify_file_id": row.get("shopify_file_id") or "",
                "pdf_shopify_file_id": row.get("shopify_pdf_file_id") or row.get("shopify_file_id") or "",
                "shopify_pdf_file_id": row.get("shopify_pdf_file_id") or row.get("shopify_file_id") or "",
                "shopify_print_jpg_file_id": row.get("shopify_print_jpg_file_id") or "",
                "shopify_preview_file_id": row.get("shopify_preview_file_id") or "",
                "shopify_file_status": row.get("shopify_file_status") or "",
                "certificate_url": row.get("shopify_file_url") or row.get("certificate_pdf_url") or "",
                "certificate_file_url": row.get("shopify_file_url") or row.get("certificate_pdf_url") or "",
                "certificate_pdf_url": row.get("certificate_pdf_url") or row.get("shopify_file_url") or "",
                "certificate_print_jpg_url": row.get("certificate_print_jpg_url") or "",
                "certificate_preview_image_url": row.get("certificate_preview_image_url") or "",
                "line_item_unit_index": row.get("line_item_unit_index") or 1,
                "certificate_status": row.get("certificate_status") or "",
                "purchase_date": str(row.get("purchase_date") or ""),
                "created_at": str(row.get("created_at") or row.get("generated_at") or ""),
                "generated_at": str(row.get("generated_at") or ""),
            }
        )
    try:
        result = shopify_sync.sync_order_certificate_metafields(
            order_id,
            certificates,
            config=config,
            request_post=request_post,
        )
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE certificates
                    SET order_metafields_synced_at=now(),
                        order_metafields_sync_status='Synced',
                        order_metafields_error='',
                        sync_status='synced',
                        last_sync_error=''
                    WHERE shopify_order_id=%s
                    """,
                    (order_id,),
                )
            conn.commit()
        return {"certificates": certificates, **result}
    except Exception as error:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE certificates
                    SET order_metafields_sync_status='Failed',
                        order_metafields_error=%s,
                        sync_status='failed',
                        last_sync_error=%s
                    WHERE shopify_order_id=%s
                    """,
                    (str(error)[:1000], str(error)[:1000], order_id),
                )
            conn.commit()
        log_app_error(
            "order_certificate_metafield_sync_failed",
            str(error),
            {"shopify_order_id": order_id},
        )
        return {
            "count": 0,
            "failed": True,
            "error": str(error),
            "certificates": certificates,
        }


def backfill_ready_certificate_order_metafields(config=None, request_post=None, limit=100, only_unsynced=False):
    if not is_configured():
        return {"attempted": 0, "synced": 0, "failed": 0, "skipped": True, "reason": "Supabase is not configured."}
    ensure_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT shopify_order_id
                FROM certificates
                WHERE shopify_order_id IS NOT NULL
                  AND shopify_order_id <> ''
                  AND COALESCE(NULLIF(certificate_pdf_url, ''), NULLIF(shopify_file_url, ''), NULLIF(certificate_file_url, '')) IS NOT NULL
                  AND COALESCE(NULLIF(certificate_pdf_url, ''), NULLIF(shopify_file_url, ''), NULLIF(certificate_file_url, '')) <> ''
                  AND (
                    %s = FALSE
                    OR COALESCE(order_metafields_sync_status, '') <> 'Synced'
                    OR COALESCE(sync_status, '') <> 'synced'
                  )
                ORDER BY shopify_order_id
                LIMIT %s
                """,
                (bool(only_unsynced), max(int(limit or 100), 1)),
            )
            order_ids = [row.get("shopify_order_id") for row in cur.fetchall() if row.get("shopify_order_id")]
    attempted = 0
    synced = 0
    failed = 0
    errors = []
    for order_id in order_ids:
        attempted += 1
        result = sync_order_certificate_metafields(order_id, config=config, request_post=request_post)
        if result.get("failed"):
            failed += 1
            errors.append(result.get("error") or f"Failed for {order_id}")
        else:
            synced += 1
    return {
        "attempted": attempted,
        "synced": synced,
        "failed": failed,
        "errors": errors[:10],
    }


def sync_certificate_to_shopify(identifier, config=None, request_post=None):
    cleaned = str(identifier or "").strip()
    if not cleaned:
        return {"attempted": 0, "synced": 0, "failed": 0, "skipped": True, "reason": "Enter an order ID, order name, or certificate ID."}
    if not is_configured():
        return {"attempted": 0, "synced": 0, "failed": 0, "skipped": True, "reason": "Supabase is not configured."}
    ensure_schema()
    order_ids = []
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT shopify_order_id
                FROM certificates
                WHERE shopify_order_id IS NOT NULL
                  AND shopify_order_id <> ''
                  AND (
                    shopify_order_id=%s
                    OR shopify_order_name=%s
                    OR certificate_id=%s
                  )
                ORDER BY shopify_order_id
                LIMIT 20
                """,
                (cleaned, cleaned, cleaned),
            )
            order_ids = [row.get("shopify_order_id") for row in cur.fetchall() if row.get("shopify_order_id")]
    if not order_ids:
        return {"attempted": 0, "synced": 0, "failed": 0, "skipped": True, "reason": "No certificate record matched that order or certificate ID."}

    attempted = 0
    synced = 0
    failed = 0
    errors = []
    for order_id in order_ids:
        attempted += 1
        result = sync_order_certificate_metafields(order_id, config=config, request_post=request_post)
        if result.get("failed"):
            failed += 1
            errors.append(result.get("error") or f"Failed for {order_id}")
        else:
            synced += 1
    return {
        "attempted": attempted,
        "synced": synced,
        "failed": failed,
        "errors": errors[:10],
    }


def certificate_vault_diagnostics():
    diagnostics = {
        "configured": is_configured(),
        "certificates_generated_count": 0,
        "certificates_synced_to_shopify_count": 0,
        "unsynced_certificate_count": 0,
        "pdf_ready_count": 0,
        "print_jpg_ready_count": 0,
        "preview_ready_count": 0,
        "missing_print_jpg_count": 0,
        "missing_preview_count": 0,
        "last_shopify_order_metafield_sync_status": "",
        "last_sync_error": "",
    }
    if not is_configured():
        return diagnostics
    ensure_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS count FROM certificates")
            diagnostics["certificates_generated_count"] = int((cur.fetchone() or {}).get("count") or 0)
            cur.execute(
                """
                SELECT COUNT(*) AS count
                FROM certificates
                WHERE COALESCE(order_metafields_sync_status, '') = 'Synced'
                   OR COALESCE(sync_status, '') = 'synced'
                """
            )
            diagnostics["certificates_synced_to_shopify_count"] = int((cur.fetchone() or {}).get("count") or 0)
            cur.execute(
                """
                SELECT COUNT(*) AS count
                FROM certificates
                WHERE NOT (
                    COALESCE(order_metafields_sync_status, '') = 'Synced'
                    OR COALESCE(sync_status, '') = 'synced'
                )
                """
            )
            diagnostics["unsynced_certificate_count"] = int((cur.fetchone() or {}).get("count") or 0)
            cur.execute(
                """
                SELECT
                    COUNT(*) FILTER (
                        WHERE COALESCE(
                            NULLIF(certificate_pdf_url, ''),
                            NULLIF(shopify_file_url, ''),
                            NULLIF(certificate_file_url, ''),
                            ''
                        ) <> ''
                    ) AS pdf_ready,
                    COUNT(*) FILTER (WHERE COALESCE(certificate_print_jpg_url, '') <> '') AS print_ready,
                    COUNT(*) FILTER (WHERE COALESCE(certificate_preview_image_url, '') <> '') AS preview_ready,
                    COUNT(*) FILTER (
                        WHERE COALESCE(
                            NULLIF(certificate_pdf_url, ''),
                            NULLIF(shopify_file_url, ''),
                            NULLIF(certificate_file_url, ''),
                            ''
                        ) <> ''
                          AND COALESCE(certificate_print_jpg_url, '') = ''
                    ) AS missing_print,
                    COUNT(*) FILTER (
                        WHERE COALESCE(
                            NULLIF(certificate_pdf_url, ''),
                            NULLIF(shopify_file_url, ''),
                            NULLIF(certificate_file_url, ''),
                            ''
                        ) <> ''
                          AND COALESCE(certificate_preview_image_url, '') = ''
                    ) AS missing_preview
                FROM certificates
                """
            )
            asset_counts = cur.fetchone() or {}
            diagnostics["pdf_ready_count"] = int(asset_counts.get("pdf_ready") or 0)
            diagnostics["print_jpg_ready_count"] = int(asset_counts.get("print_ready") or 0)
            diagnostics["preview_ready_count"] = int(asset_counts.get("preview_ready") or 0)
            diagnostics["missing_print_jpg_count"] = int(asset_counts.get("missing_print") or 0)
            diagnostics["missing_preview_count"] = int(asset_counts.get("missing_preview") or 0)
            cur.execute(
                """
                SELECT
                    COALESCE(order_metafields_sync_status, sync_status, '') AS status,
                    COALESCE(order_metafields_error, last_sync_error, '') AS error
                FROM certificates
                ORDER BY COALESCE(order_metafields_synced_at, updated_at, created_at) DESC NULLS LAST, id DESC
                LIMIT 1
                """
            )
            latest = cur.fetchone() or {}
            diagnostics["last_shopify_order_metafield_sync_status"] = latest.get("status") or ""
            diagnostics["last_sync_error"] = latest.get("error") or ""
    return diagnostics


def persistence_counts():
    ensure_schema()
    tables = (
        "edition_products",
        "edition_orders",
        "shopify_order_lines",
        "product_assets",
        "certificates",
        "shopify_products",
        "shopify_orders",
        "audit_logs",
    )
    counts = {}
    with connect() as conn:
        with conn.cursor() as cur:
            for table_name in tables:
                cur.execute(f"SELECT COUNT(*) AS count FROM {table_name}")
                counts[table_name] = int((cur.fetchone() or {}).get("count") or 0)
    return counts


def count_shopify_products():
    ensure_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS count FROM shopify_products")
            return int((cur.fetchone() or {}).get("count") or 0)


def count_shopify_orders():
    ensure_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS count FROM shopify_orders")
            return int((cur.fetchone() or {}).get("count") or 0)


def list_existing_shopify_order_ids(order_ids):
    ensure_schema()
    values = [str(order_id or "").strip() for order_id in (order_ids or []) if str(order_id or "").strip()]
    if not values:
        return set()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT shopify_order_id FROM shopify_orders WHERE shopify_order_id = ANY(%s)",
                (values,),
            )
            return {str(row.get("shopify_order_id") or "").strip() for row in cur.fetchall() if row.get("shopify_order_id")}


def list_existing_shopify_line_item_ids(line_item_ids):
    ensure_schema()
    values = [str(line_item_id or "").strip() for line_item_id in (line_item_ids or []) if str(line_item_id or "").strip()]
    if not values:
        return set()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT shopify_line_item_id FROM shopify_order_lines WHERE shopify_line_item_id = ANY(%s)",
                (values,),
            )
            return {
                str(row.get("shopify_line_item_id") or "").strip()
                for row in cur.fetchall()
                if row.get("shopify_line_item_id")
            }


def get_order_line_assignment_snapshot(line_item_ids):
    ensure_order_read_schema()
    values = [str(line_item_id or "").strip() for line_item_id in (line_item_ids or []) if str(line_item_id or "").strip()]
    if not values:
        return {}
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    li.shopify_line_item_id,
                    COALESCE(li.assignment_status, '') AS assignment_status,
                    COALESCE(li.last_error, '') AS last_error,
                    COALESCE(
                        json_agg(
                            json_build_object(
                                'id', eo.id,
                                'edition_order_id', eo.id,
                                'edition_number', eo.edition_number,
                                'allocation_index', eo.allocation_index,
                                'shopify_handle', eo.shopify_handle,
                                'product_title', eo.product_title,
                                'certificate_status', COALESCE(c.status, eo.certificate_status, '')
                            )
                            ORDER BY eo.allocation_index
                        ) FILTER (WHERE eo.id IS NOT NULL),
                        '[]'::json
                    ) AS assignments
                FROM shopify_order_lines li
                LEFT JOIN edition_orders eo ON eo.shopify_line_item_id = li.shopify_line_item_id
                LEFT JOIN certificates c ON COALESCE(c.related_edition_order_id::text, c.edition_order_id::text) = eo.id::text
                WHERE li.shopify_line_item_id = ANY(%s)
                GROUP BY li.shopify_line_item_id, li.assignment_status, li.last_error
                """,
                (values,),
            )
            rows = cur.fetchall()
    return {
        str(row.get("shopify_line_item_id") or "").strip(): {
            "assignment_status": str(row.get("assignment_status") or "").strip(),
            "last_error": str(row.get("last_error") or "").strip(),
            "assignments": row.get("assignments") or [],
        }
        for row in rows
        if str(row.get("shopify_line_item_id") or "").strip()
    }


def _prodigi_int_value(value, default=0):
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def _prodigi_bool_value(value):
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() in {"1", "true", "yes", "y", "checked"}


def _prodigi_dispatch_time_sql():
    return """
        COALESCE(
            submitted_at,
            CASE
                WHEN COALESCE(date_sent_to_prodigi, '') ~ '^\\d{4}-\\d{2}-\\d{2}'
                    THEN date_sent_to_prodigi::timestamptz
                ELSE NULL
            END,
            updated_at,
            created_at
        )
    """


def _prodigi_payload_from_db_row(row):
    payload = row.get("row_json") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError):
            payload = {}
    if not isinstance(payload, dict):
        payload = {}
    for key in (
        "row_id",
        "shopify_order_id",
        "shopify_order_name",
        "shopify_order_number",
        "shopify_line_item_id",
        "customer_name",
        "product_title",
        "shopify_variant_title",
        "edition_number",
        "sports_cave_frame",
        "sports_cave_size",
        "prodigi_product_name",
        "prodigi_product_code",
        "prodigi_frame_colour",
        "prodigi_status",
        "date_sent_to_prodigi",
        "submitted_at",
        "qa_confirmed",
        "qa_notes",
        "notes",
        "source",
    ):
        value = row.get(key)
        if value is not None and not payload.get(key):
            payload[key] = value
    if row.get("updated_at") and not payload.get("updated_at"):
        payload["updated_at"] = str(row.get("updated_at"))
    if row.get("created_at") and not payload.get("created_at"):
        payload["created_at"] = str(row.get("created_at"))
    return payload


def list_prodigi_dispatch_rows(status=None, days=None, older_than_days=None, limit=1000, search=""):
    limit_value = max(min(int(limit or 1000), 5000), 1)
    where_clauses = []
    params = []
    clean_status = str(status or "").strip()
    if clean_status == "Submitted":
        where_clauses.append("prodigi_status IN ('Submitted', 'Submitted to Prodigi')")
    elif clean_status == "Needs Review":
        where_clauses.append("prodigi_status = 'Needs Review'")
    elif clean_status:
        where_clauses.append("prodigi_status = %s")
        params.append(clean_status)
    if days:
        where_clauses.append(f"{_prodigi_dispatch_time_sql()} >= now() - (%s * interval '1 day')")
        params.append(int(days))
    if older_than_days:
        where_clauses.append(f"{_prodigi_dispatch_time_sql()} < now() - (%s * interval '1 day')")
        params.append(int(older_than_days))
    search_value = str(search or "").strip().lower()
    if search_value:
        where_clauses.append(
            """
            LOWER(
                COALESCE(shopify_order_name, '') || ' ' ||
                COALESCE(shopify_order_number, '') || ' ' ||
                COALESCE(customer_name, '') || ' ' ||
                COALESCE(product_title, '') || ' ' ||
                COALESCE(shopify_variant_title, '') || ' ' ||
                COALESCE(prodigi_product_code, '') || ' ' ||
                COALESCE(prodigi_product_name, '') || ' ' ||
                COALESCE(notes, '') || ' ' ||
                COALESCE(qa_notes, '')
            ) LIKE %s
            """
        )
        params.append(f"%{search_value}%")
    where_sql = f"WHERE {' AND '.join(f'({clause})' for clause in where_clauses)}" if where_clauses else ""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    row_id, shopify_order_id, shopify_order_name, shopify_order_number,
                    shopify_line_item_id, customer_name, product_title, shopify_variant_title,
                    edition_number, sports_cave_frame, sports_cave_size, prodigi_product_name,
                    prodigi_product_code, prodigi_frame_colour, prodigi_status,
                    date_sent_to_prodigi, submitted_at, qa_confirmed, qa_notes,
                    notes, source, row_json, created_at, updated_at
                FROM prodigi_dispatch_rows
                {where_sql}
                ORDER BY {_prodigi_dispatch_time_sql()} DESC NULLS LAST, shopify_order_name DESC NULLS LAST
                LIMIT %s
                """,
                (*params, limit_value),
            )
            rows = cur.fetchall()
    return [_prodigi_payload_from_db_row(row) for row in rows]


def get_prodigi_dispatch_summary():
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS rows_saved, MAX(updated_at) AS last_saved_at
                FROM prodigi_dispatch_rows
                """
            )
            row = cur.fetchone() or {}
    return {
        "rows_saved": _prodigi_int_value(row.get("rows_saved"), 0),
        "last_saved_at": str(row.get("last_saved_at") or ""),
    }


def upsert_prodigi_dispatch_row(row):
    return upsert_prodigi_dispatch_rows([row])


def upsert_prodigi_dispatch_rows(rows):
    ensure_schema()
    count = 0
    with connect() as conn:
        with conn.cursor() as cur:
            for raw in rows or []:
                row = dict(raw or {})
                row_id = str(row.get("row_id") or "").strip()
                if not row_id:
                    continue
                cur.execute(
                    """
                    INSERT INTO prodigi_dispatch_rows(
                        row_id, shopify_order_id, shopify_order_name, shopify_line_item_id,
                        shopify_order_number, customer_name, product_title, shopify_variant_title,
                        edition_number, sports_cave_frame, sports_cave_size, prodigi_product_name,
                        prodigi_product_code, prodigi_frame_colour, prodigi_status,
                        date_sent_to_prodigi, submitted_at, qa_confirmed, qa_notes,
                        notes, source, row_json, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, now())
                    ON CONFLICT (row_id) DO UPDATE SET
                        shopify_order_id=EXCLUDED.shopify_order_id,
                        shopify_order_name=EXCLUDED.shopify_order_name,
                        shopify_line_item_id=EXCLUDED.shopify_line_item_id,
                        shopify_order_number=EXCLUDED.shopify_order_number,
                        customer_name=EXCLUDED.customer_name,
                        product_title=EXCLUDED.product_title,
                        shopify_variant_title=EXCLUDED.shopify_variant_title,
                        edition_number=EXCLUDED.edition_number,
                        sports_cave_frame=EXCLUDED.sports_cave_frame,
                        sports_cave_size=EXCLUDED.sports_cave_size,
                        prodigi_product_name=EXCLUDED.prodigi_product_name,
                        prodigi_product_code=EXCLUDED.prodigi_product_code,
                        prodigi_frame_colour=EXCLUDED.prodigi_frame_colour,
                        prodigi_status=EXCLUDED.prodigi_status,
                        date_sent_to_prodigi=EXCLUDED.date_sent_to_prodigi,
                        submitted_at=COALESCE(prodigi_dispatch_rows.submitted_at, EXCLUDED.submitted_at),
                        qa_confirmed=EXCLUDED.qa_confirmed,
                        qa_notes=EXCLUDED.qa_notes,
                        notes=EXCLUDED.notes,
                        source=EXCLUDED.source,
                        row_json=EXCLUDED.row_json,
                        updated_at=now()
                    """,
                    (
                        row_id,
                        str(row.get("shopify_order_id") or ""),
                        str(row.get("shopify_order_name") or ""),
                        str(row.get("shopify_line_item_id") or row.get("linked_order_line_id") or ""),
                        str(row.get("shopify_order_number") or row.get("shopify_order_name") or ""),
                        str(row.get("customer_name") or ""),
                        str(row.get("product_title") or ""),
                        str(row.get("shopify_variant_title") or row.get("variant_title") or ""),
                        _prodigi_int_value(row.get("edition_number"), 0) or None,
                        str(row.get("sports_cave_frame") or row.get("frame") or ""),
                        str(row.get("sports_cave_size") or row.get("size") or ""),
                        str(row.get("prodigi_product_name") or ""),
                        str(row.get("prodigi_product_code") or row.get("prodigi_code") or ""),
                        str(row.get("prodigi_frame_colour") or row.get("prodigi_frame") or ""),
                        str(row.get("prodigi_status") or ""),
                        str(row.get("date_sent_to_prodigi") or ""),
                        str(row.get("submitted_at") or "") or None,
                        _prodigi_bool_value(row.get("qa_confirmed")),
                        str(row.get("qa_notes") or ""),
                        str(row.get("notes") or row.get("issue_reason") or ""),
                        str(row.get("source") or "prodigi_dispatch_log"),
                        json_dumps(row),
                    ),
                )
                count += 1
        conn.commit()
    return {"upserted": count}


def get_app_setting(key, default=None):
    ensure_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM app_settings WHERE key=%s", (key,))
            row = cur.fetchone()
    if not row:
        return default
    return row.get("value") or default


def set_app_setting(key, value):
    ensure_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO app_settings(key, value, updated_at)
                VALUES (%s, %s::jsonb, now())
                ON CONFLICT (key) DO UPDATE SET
                    value=EXCLUDED.value,
                    updated_at=now()
                """,
                (key, json_dumps(value)),
            )
        conn.commit()


def get_sync_setting(key, default=""):
    value = get_app_setting(key, default)
    if isinstance(value, dict):
        return value.get("value", default)
    if value is None:
        return default
    return value


def get_sync_setting_int(key, default=0):
    return _int_value(get_sync_setting(key, default), default)


def _sync_lookback_minutes():
    raw = get_sync_setting(SYNC_LOOKBACK_BUFFER_KEY, DEFAULT_SYNC_LOOKBACK_BUFFER_MINUTES)
    try:
        minutes = int(raw)
    except (TypeError, ValueError):
        minutes = DEFAULT_SYNC_LOOKBACK_BUFFER_MINUTES
    if minutes <= 0:
        minutes = DEFAULT_SYNC_LOOKBACK_BUFFER_MINUTES
    return min(minutes, 120)


def ensure_sync_defaults():
    if get_app_setting(SYNC_LOOKBACK_BUFFER_KEY) is None:
        set_app_setting(SYNC_LOOKBACK_BUFFER_KEY, DEFAULT_SYNC_LOOKBACK_BUFFER_MINUTES)


def ensure_edition_tracking_start():
    ensure_sync_defaults()
    existing = get_sync_setting(EDITION_TRACKING_START_KEY, "")
    parsed = _parse_datetime(existing)
    if parsed:
        return parsed
    started_at = utc_now_datetime()
    set_app_setting(EDITION_TRACKING_START_KEY, _datetime_to_setting(started_at))
    return started_at


def get_sync_state():
    ensure_sync_defaults()
    return {
        "last_successful_order_sync_at": get_sync_setting(LAST_SUCCESSFUL_ORDER_SYNC_KEY, ""),
        "last_attempted_order_sync_at": get_sync_setting(LAST_ATTEMPTED_ORDER_SYNC_KEY, ""),
        "last_successful_order_fetch_at": get_sync_setting(LAST_SUCCESSFUL_ORDER_FETCH_KEY, ""),
        "last_order_fetch_status": get_sync_setting(LAST_ORDER_FETCH_STATUS_KEY, ""),
        "last_order_fetch_duration_ms": get_sync_setting_int(LAST_ORDER_FETCH_DURATION_KEY, 0),
        "last_orders_imported_count": get_sync_setting_int(LAST_ORDERS_IMPORTED_COUNT_KEY, 0),
        "last_assignments_created_count": get_sync_setting_int(LAST_ASSIGNMENTS_CREATED_COUNT_KEY, 0),
        "edition_tracking_start_at": get_sync_setting(EDITION_TRACKING_START_KEY, ""),
        "last_successful_product_sync_at": get_sync_setting(LAST_SUCCESSFUL_PRODUCT_SYNC_KEY, ""),
        "last_attempted_product_sync_at": get_sync_setting(LAST_ATTEMPTED_PRODUCT_SYNC_KEY, ""),
        "sync_lookback_buffer_minutes": _sync_lookback_minutes(),
    }


def get_sync_state_read_only():
    keys = (
        LAST_SUCCESSFUL_ORDER_SYNC_KEY,
        LAST_ATTEMPTED_ORDER_SYNC_KEY,
        LAST_SUCCESSFUL_ORDER_FETCH_KEY,
        LAST_ORDER_FETCH_STATUS_KEY,
        LAST_ORDER_FETCH_DURATION_KEY,
        LAST_ORDERS_IMPORTED_COUNT_KEY,
        LAST_ASSIGNMENTS_CREATED_COUNT_KEY,
        EDITION_TRACKING_START_KEY,
        LAST_SUCCESSFUL_PRODUCT_SYNC_KEY,
        LAST_ATTEMPTED_PRODUCT_SYNC_KEY,
        SYNC_LOOKBACK_BUFFER_KEY,
    )
    values = {}
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT key, value FROM app_settings WHERE key = ANY(%s)", (list(keys),))
            for row in cur.fetchall():
                raw_value = row.get("value")
                if isinstance(raw_value, dict):
                    raw_value = raw_value.get("value", "")
                values[row.get("key")] = raw_value
    return {
        "last_successful_order_sync_at": values.get(LAST_SUCCESSFUL_ORDER_SYNC_KEY, ""),
        "last_attempted_order_sync_at": values.get(LAST_ATTEMPTED_ORDER_SYNC_KEY, ""),
        "last_successful_order_fetch_at": values.get(LAST_SUCCESSFUL_ORDER_FETCH_KEY, ""),
        "last_order_fetch_status": values.get(LAST_ORDER_FETCH_STATUS_KEY, ""),
        "last_order_fetch_duration_ms": _int_value(values.get(LAST_ORDER_FETCH_DURATION_KEY), 0),
        "last_orders_imported_count": _int_value(values.get(LAST_ORDERS_IMPORTED_COUNT_KEY), 0),
        "last_assignments_created_count": _int_value(values.get(LAST_ASSIGNMENTS_CREATED_COUNT_KEY), 0),
        "edition_tracking_start_at": values.get(EDITION_TRACKING_START_KEY, ""),
        "last_successful_product_sync_at": values.get(LAST_SUCCESSFUL_PRODUCT_SYNC_KEY, ""),
        "last_attempted_product_sync_at": values.get(LAST_ATTEMPTED_PRODUCT_SYNC_KEY, ""),
        "sync_lookback_buffer_minutes": _int_value(values.get(SYNC_LOOKBACK_BUFFER_KEY), DEFAULT_SYNC_LOOKBACK_BUFFER_MINUTES),
    }


def _set_sync_attempt(key):
    timestamp = _datetime_to_setting(utc_now_datetime())
    set_app_setting(key, timestamp)
    return timestamp


def _set_sync_success(key):
    timestamp = _datetime_to_setting(utc_now_datetime())
    set_app_setting(key, timestamp)
    return timestamp


def _set_sync_success_at(key, value):
    timestamp = _datetime_to_setting(value)
    set_app_setting(key, timestamp)
    return timestamp


def _record_order_fetch_metrics(
    *,
    status,
    duration_ms=0,
    imported_count=0,
    assignments_created=0,
    success_timestamp="",
):
    set_app_setting(LAST_ORDER_FETCH_STATUS_KEY, str(status or "Unknown"))
    set_app_setting(LAST_ORDER_FETCH_DURATION_KEY, int(duration_ms or 0))
    set_app_setting(LAST_ORDERS_IMPORTED_COUNT_KEY, int(imported_count or 0))
    set_app_setting(LAST_ASSIGNMENTS_CREATED_COUNT_KEY, int(assignments_created or 0))
    if success_timestamp:
        set_app_setting(LAST_SUCCESSFUL_ORDER_FETCH_KEY, str(success_timestamp))


def _sync_perf_log(label, started=None, **fields):
    parts = [f"PERF Sync Orders: {label}"]
    if started is not None:
        parts.append(f"elapsed_ms={int((time.perf_counter() - started) * 1000)}")
    for key, value in fields.items():
        if value is None:
            continue
        parts.append(f"{key}={value}")
    print(" ".join(parts), flush=True)


def _sync_order_line_count(orders):
    return sum(len(order.get("line_items") or []) for order in orders or [])


def _sync_order_metafield_count(orders):
    return sum(len(order.get("metafields") or []) for order in orders or [])


def _shopify_order_cursor_datetime(order):
    return (
        _parse_datetime(order.get("remote_updated_at"))
        or _parse_datetime(order.get("updated_at"))
        or _parse_datetime(order.get("processed_at"))
        or _parse_datetime(order.get("created_at"))
    )


def _newest_shopify_order_cursor(orders):
    cursors = [
        cursor
        for cursor in (_shopify_order_cursor_datetime(order) for order in orders or [])
        if cursor is not None
    ]
    return max(cursors) if cursors else None


def _latest_paid_sync_cursor(state, *, backfill_latest_paid=False):
    if backfill_latest_paid:
        return {
            "cursor_raw": "",
            "cursor_source": "backfill",
            "cursor_datetime": None,
            "cursor_used": "",
            "cursor_timezone": "UTC",
            "cursor_warning": "",
            "cursor_ignored": False,
            "query_mode": "latest_paid_backfill",
        }

    raw_cursor = ""
    source = ""
    for key in ("last_successful_order_fetch_at", "last_successful_order_sync_at"):
        candidate = state.get(key)
        parsed = _parse_datetime(candidate)
        if parsed:
            raw_cursor = str(candidate or "")
            source = key
            break

    now = utc_now_datetime()
    if raw_cursor and parsed > now:
        sync_from = now - timedelta(hours=DEFAULT_CURSORLESS_ORDER_LOOKBACK_HOURS)
        return {
            "cursor_raw": raw_cursor,
            "cursor_source": source,
            "cursor_datetime": parsed,
            "cursor_used": _datetime_to_setting(sync_from),
            "cursor_timezone": "UTC",
            "cursor_warning": (
                f"Stored order sync cursor {raw_cursor} is in the future. "
                "Ignored it and used the safe recent-orders window instead."
            ),
            "cursor_ignored": True,
            "query_mode": "safe_window_future_cursor_ignored",
        }

    if raw_cursor:
        sync_from = parsed - timedelta(
            minutes=state.get("sync_lookback_buffer_minutes") or DEFAULT_SYNC_LOOKBACK_BUFFER_MINUTES
        )
        return {
            "cursor_raw": raw_cursor,
            "cursor_source": source,
            "cursor_datetime": parsed,
            "cursor_used": _datetime_to_setting(sync_from),
            "cursor_timezone": "UTC",
            "cursor_warning": "",
            "cursor_ignored": False,
            "query_mode": "cursor",
        }

    sync_from = now - timedelta(hours=DEFAULT_CURSORLESS_ORDER_LOOKBACK_HOURS)
    return {
        "cursor_raw": "",
        "cursor_source": "none",
        "cursor_datetime": None,
        "cursor_used": _datetime_to_setting(sync_from),
        "cursor_timezone": "UTC",
        "cursor_warning": "",
        "cursor_ignored": False,
        "query_mode": "safe_window",
    }


def _latest_paid_empty_fetch_reason(payload):
    if payload.get("backfill_latest_paid"):
        return "Shopify API returned empty for latest paid orders in backfill mode."
    if payload.get("cursor_warning"):
        return (
            f"{payload.get('cursor_warning')} Shopify API returned empty for paid orders "
            f"after {payload.get('sync_from') or 'the safe window'}."
        )
    if payload.get("sync_from"):
        return (
            f"No paid orders after cursor {payload.get('sync_from')}. "
            "Backfill not enabled. Shopify API returned empty."
        )
    return "Shopify API returned empty for paid orders. Backfill not enabled."


def _paid_order_skip_counts(orders):
    skipped_orders = 0
    skipped_lines = 0
    for order in orders or []:
        financial_status = str(order.get("financial_status") or "").upper()
        cancelled = bool(str(order.get("cancelled_at") or "").strip())
        unpaid_or_refunded = financial_status and financial_status not in {"PAID", "PARTIALLY_PAID"}
        if cancelled or unpaid_or_refunded:
            skipped_orders += 1
            skipped_lines += len(order.get("line_items") or [])
    return skipped_orders, skipped_lines


def _log_order_fetch_timing(*, total_ms, shopify_ms, pages, orders, db_load_ms, assign_ms, db_write_ms):
    db_ms = int((db_load_ms or 0) + (db_write_ms or 0))
    _sync_perf_log(
        "total sync time",
        None,
        total_ms=int(total_ms),
        shopify_ms=int(shopify_ms),
        pages=int(pages),
        orders=int(orders),
        supabase_ms=db_ms,
        edition_allocation_ms=int(assign_ms),
    )
    print(
        "ORDER_FETCH "
        f"total={int(total_ms)}ms "
        f"shopify={int(shopify_ms)}ms "
        f"pages={int(pages)} "
        f"orders={int(orders)} "
        f"db_load={int(db_load_ms)}ms "
        f"assign={int(assign_ms)}ms "
        f"db_write={int(db_write_ms)}ms"
    )
    print(
        "FETCH_NEW_ORDERS "
        f"total={int(total_ms)}ms "
        f"shopify={int(shopify_ms)}ms "
        f"db={db_ms}ms "
        f"assign={int(assign_ms)}ms"
    )


def reset_incremental_sync_timestamps():
    ensure_sync_defaults()
    for key in (
        LAST_SUCCESSFUL_ORDER_SYNC_KEY,
        LAST_ATTEMPTED_ORDER_SYNC_KEY,
        LAST_SUCCESSFUL_ORDER_FETCH_KEY,
        LAST_SUCCESSFUL_PRODUCT_SYNC_KEY,
        LAST_ATTEMPTED_PRODUCT_SYNC_KEY,
    ):
        set_app_setting(key, "")
    _record_order_fetch_metrics(
        status="Never",
        duration_ms=0,
        imported_count=0,
        assignments_created=0,
        success_timestamp="",
    )
    set_app_setting(EDITION_TRACKING_START_KEY, _datetime_to_setting(utc_now_datetime()))
    return get_sync_state()


def ensure_psd_master_folder_setting():
    existing = get_app_setting(PSD_MASTER_FOLDER_SETTING_KEY)
    if existing:
        return existing
    set_app_setting(PSD_MASTER_FOLDER_SETTING_KEY, DEFAULT_PSD_MASTER_FOLDER_SETTING)
    return DEFAULT_PSD_MASTER_FOLDER_SETTING


def get_psd_master_folder_setting():
    return get_app_setting(PSD_MASTER_FOLDER_SETTING_KEY, DEFAULT_PSD_MASTER_FOLDER_SETTING)


def _normalize_handle(value):
    cleaned = re.sub(r"\.psd$", "", str(value or "").strip().lower(), flags=re.IGNORECASE)
    cleaned = re.sub(r"[^a-z0-9]+", "-", cleaned)
    return cleaned.strip("-")


def _parse_int(value, default=None):
    raw = str(value or "").strip()
    if not raw:
        return default
    match = re.search(r"\d+", raw.replace(",", ""))
    if not match:
        return default
    return int(match.group(0))


def _parse_edition_number(value):
    raw = str(value or "").strip()
    if not raw or raw in {"-", "N/A", "n/a"}:
        return None, None
    numbers = re.findall(r"\d+", raw)
    if not numbers:
        return None, None
    edition_number = int(numbers[0])
    edition_total = int(numbers[1]) if len(numbers) > 1 else None
    return edition_number, edition_total


def _normalized_attribute_key(value):
    text = str(value or "").strip().casefold()
    text = text.replace("_", " ").replace("-", " ")
    text = re.sub(r"\s+", " ", text)
    return text


def _attribute_pairs_from_value(value):
    if isinstance(value, dict):
        return list(value.items())
    if isinstance(value, list):
        pairs = []
        for item in value:
            if isinstance(item, dict):
                key = item.get("key") or item.get("name") or item.get("attribute") or item.get("property")
                if key is not None:
                    pairs.append((key, item.get("value")))
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                pairs.append((item[0], item[1]))
        return pairs
    return []


def _edition_hint_from_attributes(attributes):
    edition_number = None
    edition_total = None
    for key, value in _attribute_pairs_from_value(attributes):
        normalized_key = _normalized_attribute_key(key)
        if normalized_key in PROMISED_EDITION_NUMBER_KEYS:
            number, total = _parse_edition_number(value)
            edition_number = edition_number or number
            edition_total = edition_total or total
        elif normalized_key in PROMISED_EDITION_TOTAL_KEYS:
            _, total = _parse_edition_number(value)
            edition_total = edition_total or total or _int_value(value, 0) or None
    if edition_number:
        return {"edition_number": edition_number, "edition_total": edition_total, "source": "shopify_attribute"}
    return {}


def _edition_hint_from_allocation(order, line_item, allocation_index):
    try:
        import order_allocator
    except Exception:
        return {}
    payload = order_allocator.allocation_payload_from_metafields(order.get("metafields") or [])
    line_items = payload.get("line_items") or {}
    line_id = order_allocator.line_item_gid(line_item.get("shopify_line_item_id") or line_item.get("id") or "")
    allocation = line_items.get(line_id) or line_items.get(str(line_item.get("shopify_line_item_id") or "")) or {}
    if not isinstance(allocation, dict):
        return {}
    edition_total = _int_value(allocation.get("edition_total"), 0) or None
    unit_allocations = allocation.get("unit_allocations")
    if isinstance(unit_allocations, list):
        for unit in unit_allocations:
            if not isinstance(unit, dict):
                continue
            unit_index = _int_value(
                unit.get("line_item_unit_index") or unit.get("quantity_index") or unit.get("allocation_index"),
                0,
            )
            if unit_index and unit_index != int(allocation_index or 1):
                continue
            number, total = _parse_edition_number(
                unit.get("edition_number") or unit.get("edition") or unit.get("edition_display")
            )
            if number:
                return {
                    "edition_number": number,
                    "edition_total": total or edition_total,
                    "source": "shopify_order_metafield",
                }
    numbers = allocation.get("edition_numbers")
    if isinstance(numbers, list) and len(numbers) >= int(allocation_index or 1):
        number, total = _parse_edition_number(numbers[int(allocation_index or 1) - 1])
        if number:
            return {
                "edition_number": number,
                "edition_total": total or edition_total,
                "source": "shopify_order_metafield",
            }
    number, total = _parse_edition_number(
        allocation.get("edition_number") or allocation.get("edition") or allocation.get("edition_display")
    )
    if number and int(allocation_index or 1) == 1:
        return {"edition_number": number, "edition_total": total or edition_total, "source": "shopify_order_metafield"}
    return {}


def promised_edition_hint_for_order_line(order, line_item, allocation_index=1):
    hint = _edition_hint_from_allocation(order, line_item, allocation_index)
    if hint:
        return hint
    for source in (
        line_item.get("custom_attributes"),
        line_item.get("properties"),
        line_item.get("note_attributes"),
        line_item.get("raw_json", {}).get("custom_attributes") if isinstance(line_item.get("raw_json"), dict) else None,
        order.get("custom_attributes"),
        order.get("note_attributes"),
    ):
        hint = _edition_hint_from_attributes(source)
        if hint:
            hint["source"] = "shopify_line_or_order_attribute"
            return hint
    for source in (line_item, order):
        if not isinstance(source, dict):
            continue
        for key in ("edition_number", "edition", "edition_display", "promised_edition_number", "sports_cave_edition_number"):
            number, total = _parse_edition_number(source.get(key))
            if number:
                return {
                    "edition_number": number,
                    "edition_total": total or _int_value(source.get("edition_total"), 0) or None,
                    "source": "shopify_raw_snapshot",
                }
    return {}


def _csv_value(row, *names):
    lowered = {str(key or "").strip().lower(): value for key, value in (row or {}).items()}
    for name in names:
        value = lowered.get(str(name).strip().lower())
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return ""


def _normalize_product_title_key(value):
    text = str(value or "").strip()
    if not text:
        return ""
    replacements = {
        "\u2019": "'",
        "\u2018": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    text = re.sub(r"[^\w\s'&/+.-]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.casefold()


def _shopify_identifier_candidates(resource_type, value):
    raw = str(value or "").strip()
    if not raw:
        return []
    candidates = {raw}
    prefix = f"gid://shopify/{resource_type}/"
    if raw.startswith(prefix):
        legacy_id = raw.removeprefix(prefix).strip()
        if legacy_id:
            candidates.add(legacy_id)
    else:
        candidates.add(f"{prefix}{raw}")
    return [candidate for candidate in candidates if candidate]


def _edition_product_row_for_output(row, *, match_method="", reason=""):
    if not row:
        return {}
    active_value = row.get("active")
    is_active_value = row.get("is_active")
    active = True
    if active_value is not None:
        active = bool(active_value)
    if is_active_value is not None:
        active = active and bool(is_active_value)
    return {
        **dict(row),
        "edition_product_id": row.get("id"),
        "shopify_product_id": row.get("shopify_product_id") or row.get("shopify_product_gid") or "",
        "handle": row.get("shopify_handle") or "",
        "title": row.get("product_title") or "",
        "active": active,
        "is_active": active,
        "match_method": match_method,
        "match_reason": reason,
    }


def _unique_edition_product_match(rows, *, match_method, missing_reason, ambiguous_reason):
    clean_rows = [row for row in (rows or []) if row]
    if len(clean_rows) == 1:
        return {
            "product": _edition_product_row_for_output(
                clean_rows[0],
                match_method=match_method,
                reason=f"Matched Edition Ops product by {match_method}.",
            ),
            "status": "matched",
            "reason": f"Matched Edition Ops product by {match_method}.",
            "candidates": [],
        }
    if len(clean_rows) > 1:
        return {
            "product": {},
            "status": "ambiguous",
            "reason": ambiguous_reason,
            "candidates": [
                {
                    "shopify_handle": row.get("shopify_handle") or "",
                    "product_title": row.get("product_title") or "",
                    "shopify_product_id": row.get("shopify_product_id") or row.get("shopify_product_gid") or "",
                }
                for row in clean_rows[:5]
            ],
        }
    return {"product": {}, "status": "missing", "reason": missing_reason, "candidates": []}


def _resolve_edition_product_for_order_line_with_cursor(cur, line_item, *, lock=False):
    line_item = line_item or {}
    product_ids = _shopify_identifier_candidates(
        "Product",
        line_item.get("shopify_product_id") or line_item.get("product_id") or line_item.get("product_gid"),
    )
    variant_ids = _shopify_identifier_candidates(
        "ProductVariant",
        line_item.get("shopify_variant_id") or line_item.get("variant_id") or line_item.get("variant_gid"),
    )
    handle = _normalize_handle(
        line_item.get("product_handle")
        or line_item.get("shopify_handle")
        or line_item.get("handle")
    )
    title = str(line_item.get("product_title") or line_item.get("title") or "").strip()
    title_key = _normalize_product_title_key(title)
    lock_sql = " FOR UPDATE" if lock else ""

    if product_ids:
        cur.execute(
            f"""
            SELECT ep.*
            FROM edition_products ep
            WHERE ep.shopify_product_id = ANY(%s)
               OR ep.shopify_product_gid = ANY(%s)
            ORDER BY ep.updated_at DESC NULLS LAST, ep.id DESC
            {lock_sql}
            """,
            (product_ids, product_ids),
        )
        result = _unique_edition_product_match(
            cur.fetchall() or [],
            match_method="shopify_product_id",
            missing_reason="No Edition Ops product matched the Shopify product ID.",
            ambiguous_reason="Multiple Edition Ops products matched the Shopify product ID.",
        )
        if result["status"] != "missing":
            return result

    if variant_ids:
        cur.execute(
            f"""
            SELECT ep.*
            FROM shopify_variants sv
            JOIN edition_products ep
              ON ep.shopify_product_id = sv.shopify_product_id
              OR ep.shopify_product_gid = sv.shopify_product_id
            WHERE sv.shopify_variant_id = ANY(%s)
               OR sv.legacy_resource_id = ANY(%s)
            ORDER BY ep.updated_at DESC NULLS LAST, ep.id DESC
            {lock_sql}
            """,
            (variant_ids, variant_ids),
        )
        result = _unique_edition_product_match(
            cur.fetchall() or [],
            match_method="shopify_variant_id",
            missing_reason="No Edition Ops product matched the Shopify variant ID.",
            ambiguous_reason="Multiple Edition Ops products matched the Shopify variant ID.",
        )
        if result["status"] != "missing":
            return result

    if handle:
        cur.execute(
            f"""
            SELECT ep.*
            FROM edition_products ep
            WHERE ep.shopify_handle=%s
            ORDER BY ep.updated_at DESC NULLS LAST, ep.id DESC
            {lock_sql}
            """,
            (handle,),
        )
        result = _unique_edition_product_match(
            cur.fetchall() or [],
            match_method="shopify_handle",
            missing_reason="No Edition Ops product matched the Shopify handle.",
            ambiguous_reason="Multiple Edition Ops products matched the Shopify handle.",
        )
        if result["status"] != "missing":
            return result

    if title_key:
        cur.execute(
            f"""
            SELECT ep.*
            FROM edition_products ep
            WHERE COALESCE(ep.product_title, '') <> ''
            ORDER BY ep.updated_at DESC NULLS LAST, ep.id DESC
            {lock_sql}
            """,
        )
        rows = [
            row
            for row in (cur.fetchall() or [])
            if _normalize_product_title_key(row.get("product_title")) == title_key
        ]
        result = _unique_edition_product_match(
            rows,
            match_method="normalized_product_title",
            missing_reason="No Edition Ops product matched the normalized product title.",
            ambiguous_reason="Multiple Edition Ops products matched the normalized product title.",
        )
        if result["status"] != "missing":
            return result

    return {
        "product": {},
        "status": "missing",
        "reason": "No Edition Ops product matched by product ID, variant ID, handle, or normalized title.",
        "candidates": [],
    }


def resolve_edition_product_for_order_line(line_item, *, fetch_missing_products=True):
    ensure_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            result = _resolve_edition_product_for_order_line_with_cursor(cur, line_item)
    if result.get("product") or not fetch_missing_products or not line_item.get("shopify_product_id"):
        return result
    fetched = shopify_sync.fetch_product_by_shopify_id(line_item["shopify_product_id"])
    upsert_products([fetched])
    with connect() as conn:
        with conn.cursor() as cur:
            return _resolve_edition_product_for_order_line_with_cursor(cur, line_item)


def _match_product_handle(cur, *, handle="", shopify_product_id="", product_title=""):
    matched = _resolve_edition_product_for_order_line_with_cursor(
        cur,
        {
            "product_handle": handle,
            "shopify_product_id": shopify_product_id,
            "product_title": product_title,
        },
    )
    matched_product = matched.get("product") or {}
    if matched_product.get("handle"):
        return matched_product["handle"]

    normalized_handle = _normalize_handle(handle)
    if normalized_handle:
        cur.execute(
            """
            SELECT shopify_handle
            FROM edition_products
            WHERE shopify_handle=%s
            UNION
            SELECT handle AS shopify_handle
            FROM shopify_products
            WHERE handle=%s
            LIMIT 1
            """,
            (normalized_handle, normalized_handle),
        )
        row = cur.fetchone()
        if row and row.get("shopify_handle"):
            return row["shopify_handle"]

    if shopify_product_id:
        cur.execute(
            """
            SELECT shopify_handle
            FROM edition_products
            WHERE shopify_product_id=%s
            UNION
            SELECT handle AS shopify_handle
            FROM shopify_products
            WHERE shopify_product_id=%s OR legacy_resource_id=%s
            LIMIT 1
            """,
            (shopify_product_id, shopify_product_id, shopify_product_id),
        )
        row = cur.fetchone()
        if row and row.get("shopify_handle"):
            return row["shopify_handle"]

    return normalized_handle


def _find_import_product(cur, *, shopify_product_id="", handle=""):
    product_id = str(shopify_product_id or "").strip()
    normalized_handle = _normalize_handle(handle)
    if product_id:
        cur.execute(
            """
            SELECT ep.*, TRUE AS edition_product_exists,
                   sp.admin_url, sp.online_store_url
            FROM edition_products ep
            LEFT JOIN shopify_products sp ON sp.handle=ep.shopify_handle
            WHERE ep.shopify_product_id=%s OR ep.shopify_product_gid=%s
            LIMIT 1
            """,
            (product_id, product_id),
        )
        row = cur.fetchone()
        if row:
            return row
        cur.execute(
            """
            SELECT NULL AS id,
                   sp.shopify_product_id,
                   sp.shopify_product_gid,
                   sp.handle AS shopify_handle,
                   sp.title AS product_title,
                   FALSE AS edition_product_exists,
                   TRUE AS shopify_product_exists,
                   sp.admin_url,
                   sp.online_store_url
            FROM shopify_products sp
            WHERE sp.shopify_product_id=%s OR sp.shopify_product_gid=%s OR sp.legacy_resource_id=%s
            LIMIT 1
            """,
            (product_id, product_id, product_id),
        )
        row = cur.fetchone()
        if row:
            return row
    if normalized_handle:
        cur.execute(
            """
            SELECT ep.*, TRUE AS edition_product_exists,
                   sp.admin_url, sp.online_store_url
            FROM edition_products ep
            LEFT JOIN shopify_products sp ON sp.handle=ep.shopify_handle
            WHERE ep.shopify_handle=%s
            LIMIT 1
            """,
            (normalized_handle,),
        )
        row = cur.fetchone()
        if row:
            return row
        cur.execute(
            """
            SELECT NULL AS id,
                   sp.shopify_product_id,
                   sp.shopify_product_gid,
                   sp.handle AS shopify_handle,
                   sp.title AS product_title,
                   FALSE AS edition_product_exists,
                   TRUE AS shopify_product_exists,
                   sp.admin_url,
                   sp.online_store_url
            FROM shopify_products sp
            WHERE sp.handle=%s
            LIMIT 1
            """,
            (normalized_handle,),
        )
        row = cur.fetchone()
        if row:
            return row
    return None


def _limited_edition_import_values(row):
    edition_number, edition_total_from_number = _parse_edition_number(
        _csv_value(row, "Edition No.", "Edition No", "Edition Number", "edition_number")
    )
    latest_sent = _parse_int(
        _csv_value(row, "latest_sent", "Latest Sent", "Current Number", "current_number", "Current Edition"),
        None,
    )
    if latest_sent is None and edition_number is not None:
        latest_sent = edition_number
    next_number = _parse_int(
        _csv_value(
            row,
            "next_edition_number",
            "Next Edition Number",
            "Next Edition",
        ),
        None,
    )
    if next_number is None and latest_sent is not None:
        next_number = latest_sent + 1
    edition_total = (
        _parse_int(
            _csv_value(
                row,
                "edition_total",
                "Edition Total",
                "Total Editions",
                "total_editions",
                "edition_limit",
                "Total",
            ),
            None,
        )
        or edition_total_from_number
    )
    status = _clean_edition_run_status(
        _csv_value(row, "status", "Status", "Active"),
        active=True,
        sold_out=False,
    )
    return {
        "shopify_product_id": _csv_value(row, "shopify_product_id", "Shopify Product ID", "Product ID"),
        "shopify_handle": _normalize_handle(_csv_value(row, "handle", "shopify_handle", "Shopify Handle")),
        "product_title": _csv_value(row, "product_title", "Product Title", "Product", "Title"),
        "edition_name": _csv_value(row, "edition_name", "Edition Name") or DEFAULT_EDITION_NAME,
        "latest_sent": latest_sent,
        "next_edition_number": next_number,
        "edition_total": edition_total,
        "status": status,
        "psd_link": _csv_value(row, "psd link", "psd_link", "psd_file_url", "PSD"),
        "prodigi_link": _csv_value(row, "prodigi link", "prodigi_link", "prodigi_url", "Prodigi"),
    }


def preview_limited_edition_import_rows(rows):
    ensure_schema()
    result = {
        "rows_read": 0,
        "matched": [],
        "createable": [],
        "unmatched": [],
        "changes": [],
        "errors": [],
    }
    with connect() as conn:
        with conn.cursor() as cur:
            _ensure_active_edition_runs_for_products(cur)
            conn.commit()
            for line_number, row in enumerate(rows or [], start=2):
                result["rows_read"] += 1
                parsed = _limited_edition_import_values(row)
                matched = _find_import_product(
                    cur,
                    shopify_product_id=parsed["shopify_product_id"],
                    handle=parsed["shopify_handle"],
                )
                if not matched:
                    result["unmatched"].append(
                        {
                            "line": line_number,
                            "product_title": parsed["product_title"],
                            "shopify_handle": parsed["shopify_handle"],
                            "shopify_product_id": parsed["shopify_product_id"],
                            "reason": "No Shopify product ID or handle match. Title-only matching is disabled.",
                        }
                    )
                    continue

                handle = matched.get("shopify_handle") or parsed["shopify_handle"]
                if not matched.get("edition_product_exists"):
                    result["createable"].append(
                        {
                            "line": line_number,
                            "product_title": matched.get("product_title") or parsed["product_title"],
                            "shopify_handle": handle,
                            "shopify_product_id": matched.get("shopify_product_id") or parsed["shopify_product_id"],
                            "next_edition_number": parsed["next_edition_number"] or 1,
                            "edition_total": parsed["edition_total"] or 100,
                            "status": parsed["status"],
                        }
                    )
                    continue

                state = get_edition_counter_state(handle)
                proposed_next = parsed["next_edition_number"] or state.get("next_edition_number") or 1
                proposed_total = parsed["edition_total"] or state.get("edition_total") or 100
                proposed_name = parsed["edition_name"] or state.get("edition_name") or DEFAULT_EDITION_NAME
                proposed_status = parsed["status"] or state.get("status") or ACTIVE_RUN_STATUS
                row_changes = []
                comparisons = (
                    ("edition_name", state.get("edition_name"), proposed_name),
                    ("next_edition_number", state.get("next_edition_number"), proposed_next),
                    ("edition_total", state.get("edition_total"), proposed_total),
                    ("status", state.get("status"), proposed_status),
                )
                for field, old_value, new_value in comparisons:
                    if str(old_value or "") != str(new_value or ""):
                        row_changes.append({"field": field, "old": old_value, "new": new_value})
                preview_row = {
                    "line": line_number,
                    "product_title": state.get("product_title") or parsed["product_title"],
                    "shopify_handle": handle,
                    "shopify_product_id": state.get("shopify_product_id") or parsed["shopify_product_id"],
                    "current_edition_name": state.get("edition_name"),
                    "new_edition_name": proposed_name,
                    "current_next": state.get("next_edition_number"),
                    "new_next": proposed_next,
                    "current_total": state.get("edition_total"),
                    "new_total": proposed_total,
                    "current_status": state.get("status"),
                    "new_status": proposed_status,
                    "changes": row_changes,
                }
                result["matched"].append(preview_row)
                if row_changes:
                    result["changes"].append(preview_row)
    return result


def apply_limited_edition_import_rows(rows, *, create_missing_from_shopify=False, reason="Google Sheet CSV import"):
    ensure_schema()
    result = {
        "rows_read": 0,
        "rows_matched": 0,
        "rows_created": 0,
        "rows_updated": 0,
        "rows_skipped": 0,
        "errors": [],
    }
    run_id = start_sync_run("limited_edition_csv_import")
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                _ensure_active_edition_runs_for_products(cur)
                conn.commit()
                for line_number, row in enumerate(rows or [], start=2):
                    result["rows_read"] += 1
                    parsed = _limited_edition_import_values(row)
                    matched = _find_import_product(
                        cur,
                        shopify_product_id=parsed["shopify_product_id"],
                        handle=parsed["shopify_handle"],
                    )
                    if not matched:
                        result["rows_skipped"] += 1
                        result["errors"].append(f"Line {line_number}: no Shopify product ID or handle match.")
                        continue
                    handle = matched.get("shopify_handle") or parsed["shopify_handle"]
                    if not matched.get("edition_product_exists"):
                        if not create_missing_from_shopify:
                            result["rows_skipped"] += 1
                            result["errors"].append(
                                f"Line {line_number}: {handle} exists in Shopify sync but not edition_products."
                            )
                            continue
                        cur.execute(
                            """
                            INSERT INTO edition_products(
                                shopify_product_id, shopify_product_gid, shopify_handle, product_title,
                                edition_name, edition_total, next_edition_number,
                                active, is_active, sold_out, is_sold_out, updated_at
                            )
                            VALUES (%s, %s, %s, %s, %s, 100, 1, TRUE, TRUE, FALSE, FALSE, now())
                            ON CONFLICT (shopify_handle) DO NOTHING
                            """,
                            (
                                matched.get("shopify_product_id") or parsed["shopify_product_id"],
                                matched.get("shopify_product_gid") or matched.get("shopify_product_id") or parsed["shopify_product_id"],
                                handle,
                                matched.get("product_title") or parsed["product_title"],
                                parsed["edition_name"] or DEFAULT_EDITION_NAME,
                            ),
                        )
                        conn.commit()
                        result["rows_created"] += 1
                    result["rows_matched"] += 1
                    state = get_edition_counter_state(handle)
                    proposed_next = parsed["next_edition_number"] or state.get("next_edition_number") or 1
                    proposed_total = parsed["edition_total"] or state.get("edition_total") or 100
                    proposed_name = parsed["edition_name"] or state.get("edition_name") or DEFAULT_EDITION_NAME
                    proposed_status = parsed["status"] or state.get("status") or ACTIVE_RUN_STATUS
                    update_edition_product(
                        handle,
                        edition_name=proposed_name,
                        edition_total=proposed_total,
                        next_edition_number=proposed_next,
                        status=proposed_status,
                        reason=f"{reason} line {line_number}",
                    )
                    if parsed["psd_link"]:
                        upsert_product_asset(
                            handle,
                            "psd_master_file",
                            parsed["psd_link"],
                            asset_name="PSD Master File",
                            notes="Imported from Limited Edition CSV",
                        )
                    if parsed["prodigi_link"]:
                        upsert_product_asset(
                            handle,
                            "prodigi_link",
                            parsed["prodigi_link"],
                            asset_name="Prodigi",
                            notes="Imported from Limited Edition CSV",
                        )
                    result["rows_updated"] += 1
            conn.commit()
        finish_sync_run(
            run_id,
            "Complete",
            records_seen=result["rows_read"],
            records_processed=result["rows_updated"] + result["rows_created"],
        )
        return result
    except Exception as error:
        finish_sync_run(
            run_id,
            "Failed",
            records_seen=result["rows_read"],
            records_processed=result["rows_updated"] + result["rows_created"],
            error_message="Limited edition CSV import failed.",
        )
        log_app_error("limited_edition_csv_import_failed", str(error), result)
        raise


def import_limited_edition_rows(
    rows,
    *,
    overwrite_existing_orders=False,
    allow_next_number_override=False,
):
    ensure_schema()
    run_id = start_sync_run("limited_edition_csv_import")
    result = {
        "rows_read": 0,
        "rows_matched": 0,
        "rows_inserted": 0,
        "rows_updated": 0,
        "rows_skipped": 0,
        "errors": [],
    }
    touched_handles = set()
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                for line_number, row in enumerate(rows or [], start=2):
                    result["rows_read"] += 1
                    shopify_product_id = _csv_value(row, "shopify_product_id", "Shopify Product ID")
                    handle = _csv_value(row, "handle", "shopify_handle", "Shopify Handle")
                    product_title = _csv_value(row, "product_title", "Product Title", "Edition Name", "Product")
                    matched_handle = _match_product_handle(
                        cur,
                        handle=handle,
                        shopify_product_id=shopify_product_id,
                        product_title=product_title,
                    )
                    if not matched_handle:
                        result["rows_skipped"] += 1
                        result["errors"].append(f"Line {line_number}: no product handle could be matched.")
                        continue

                    result["rows_matched"] += 1
                    edition_number, edition_total_from_no = _parse_edition_number(
                        _csv_value(row, "Edition No.", "Edition No", "Edition Number", "edition_number")
                    )
                    edition_total = (
                        _parse_int(_csv_value(row, "edition_total", "Edition Total", "edition_limit"), None)
                        or edition_total_from_no
                        or 100
                    )
                    next_number = _parse_int(
                        _csv_value(row, "next_edition_number", "next_available_edition", "Next Edition"),
                        None,
                    )
                    override_next_number = bool(allow_next_number_override and next_number)
                    active_raw = _csv_value(row, "active", "Active")
                    active = False if active_raw.lower() in {"false", "no", "0", "inactive"} else True

                    cur.execute(
                        """
                        INSERT INTO edition_products(
                            shopify_product_id, shopify_product_gid, shopify_handle, product_title,
                            edition_total, next_edition_number, active, is_active,
                            allow_counter_history_override, sold_out, is_sold_out, updated_at
                        )
                        VALUES (%s, %s, %s, %s, %s, COALESCE(%s, 1), %s, %s, %s, FALSE, FALSE, now())
                        ON CONFLICT (shopify_handle) DO UPDATE SET
                            shopify_product_id=COALESCE(EXCLUDED.shopify_product_id, edition_products.shopify_product_id),
                            shopify_product_gid=COALESCE(EXCLUDED.shopify_product_gid, edition_products.shopify_product_gid),
                            product_title=COALESCE(NULLIF(EXCLUDED.product_title, ''), edition_products.product_title),
                            edition_total=EXCLUDED.edition_total,
                            next_edition_number=CASE
                                WHEN %s THEN COALESCE(EXCLUDED.next_edition_number, 1)
                                ELSE GREATEST(edition_products.next_edition_number, EXCLUDED.next_edition_number)
                            END,
                            allow_counter_history_override=CASE
                                WHEN %s THEN TRUE
                                ELSE COALESCE(edition_products.allow_counter_history_override, FALSE)
                            END,
                            active=EXCLUDED.active,
                            is_active=EXCLUDED.is_active,
                            sold_out=CASE
                                WHEN %s THEN COALESCE(EXCLUDED.next_edition_number, 1)
                                ELSE GREATEST(edition_products.next_edition_number, EXCLUDED.next_edition_number)
                            END > EXCLUDED.edition_total,
                            is_sold_out=CASE
                                WHEN %s THEN COALESCE(EXCLUDED.next_edition_number, 1)
                                ELSE GREATEST(edition_products.next_edition_number, EXCLUDED.next_edition_number)
                            END > EXCLUDED.edition_total,
                            updated_at=now()
                        RETURNING (xmax = 0) AS inserted
                        """,
                        (
                            shopify_product_id or None,
                            shopify_product_id or None,
                            matched_handle,
                            product_title,
                            int(edition_total),
                            int(next_number) if next_number else None,
                            bool(active),
                            bool(active),
                            override_next_number,
                            override_next_number,
                            override_next_number,
                            override_next_number,
                            override_next_number,
                        ),
                    )
                    inserted_product = bool((cur.fetchone() or {}).get("inserted"))
                    if inserted_product:
                        result["rows_inserted"] += 1
                    else:
                        result["rows_updated"] += 1
                    touched_handles.add(matched_handle)

                    if edition_number:
                        order_name = _csv_value(row, "Shopify Order #", "Order", "order_name", "shopify_order_id")
                        customer_name = _csv_value(row, "Customer Name", "customer_name")
                        variant_title = " / ".join(
                            part
                            for part in (
                                _csv_value(row, "Frame"),
                                _csv_value(row, "Size"),
                            )
                            if part
                        )
                        synthetic_order_id = f"csv-import:{matched_handle}:{order_name or 'order'}:{edition_number}"
                        synthetic_line_id = f"{synthetic_order_id}:line:1"
                        if overwrite_existing_orders:
                            cur.execute(
                                """
                                INSERT INTO edition_orders(
                                    shopify_order_id, shopify_line_item_id, shopify_product_id,
                                    shopify_handle, product_title, variant_title, customer_name,
                                    edition_number, edition_total, allocation_index, assigned_at, certificate_status
                                )
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1, now(), 'Certificate Missing')
                                ON CONFLICT (shopify_line_item_id, allocation_index) DO UPDATE SET
                                    product_title=EXCLUDED.product_title,
                                    variant_title=EXCLUDED.variant_title,
                                    customer_name=EXCLUDED.customer_name,
                                    edition_total=EXCLUDED.edition_total
                                """,
                                (
                                    synthetic_order_id,
                                    synthetic_line_id,
                                    shopify_product_id,
                                    matched_handle,
                                    product_title,
                                    variant_title,
                                    customer_name,
                                    int(edition_number),
                                    int(edition_total),
                                ),
                            )
                        else:
                            cur.execute(
                                """
                                INSERT INTO edition_orders(
                                    shopify_order_id, shopify_line_item_id, shopify_product_id,
                                    shopify_handle, product_title, variant_title, customer_name,
                                    edition_number, edition_total, allocation_index, assigned_at, certificate_status
                                )
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1, now(), 'Certificate Missing')
                                ON CONFLICT DO NOTHING
                                """,
                                (
                                    synthetic_order_id,
                                    synthetic_line_id,
                                    shopify_product_id,
                                    matched_handle,
                                    product_title,
                                    variant_title,
                                    customer_name,
                                    int(edition_number),
                                    int(edition_total),
                                ),
                            )

                for handle in touched_handles:
                    cur.execute(
                        """
                        UPDATE edition_products ep
                        SET next_edition_number = GREATEST(
                                COALESCE(ep.next_edition_number, 1),
                                COALESCE((
                                    SELECT MAX(eo.edition_number) + 1
                                    FROM edition_orders eo
                                    WHERE eo.shopify_handle = ep.shopify_handle
                                ), 1)
                            ),
                            sold_out = GREATEST(
                                COALESCE(ep.next_edition_number, 1),
                                COALESCE((
                                    SELECT MAX(eo.edition_number) + 1
                                    FROM edition_orders eo
                                    WHERE eo.shopify_handle = ep.shopify_handle
                                ), 1)
                            ) > COALESCE(ep.edition_total, 100),
                            updated_at = now()
                        WHERE ep.shopify_handle = %s
                          AND COALESCE(ep.allow_counter_history_override, FALSE) = FALSE
                        """,
                        (handle,),
                    )
            conn.commit()
        finish_sync_run(
            run_id,
            "Complete",
            records_seen=result["rows_read"],
            records_processed=result["rows_inserted"] + result["rows_updated"],
        )
        return result
    except Exception as error:
        finish_sync_run(
            run_id,
            "Failed",
            records_seen=result["rows_read"],
            records_processed=result["rows_inserted"] + result["rows_updated"],
            error_message="Limited edition CSV import failed.",
        )
        log_app_error("limited_edition_csv_import_failed", str(error), result)
        raise


def get_product_asset_map(handles=None):
    ensure_schema()
    handle_values = [str(handle or "").strip() for handle in (handles or []) if str(handle or "").strip()]
    where = ""
    params = []
    if handle_values:
        where = "AND shopify_handle = ANY(%s)"
        params.append(handle_values)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT shopify_handle, asset_type,
                       COALESCE(NULLIF(asset_url, ''), NULLIF(google_drive_file_url, '')) AS asset_url
                FROM product_assets
                WHERE is_primary IS DISTINCT FROM FALSE
                  {where}
                """,
                tuple(params),
            )
            rows = cur.fetchall()
    result = {}
    for row in rows:
        result.setdefault(row["shopify_handle"], {})[row["asset_type"]] = row.get("asset_url") or ""
    return result


def extract_google_drive_file_id(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    query_id = dict(parse_qsl(parsed.query or "")).get("id")
    if query_id:
        return query_id.strip()
    match = re.search(r"/(?:file/d|folders)/([^/?#]+)", parsed.path or raw)
    if match:
        return match.group(1).strip()
    match = re.search(r"[?&]id=([^&#]+)", raw)
    if match:
        return match.group(1).strip()
    return ""


def get_primary_psd_assets(handles=None):
    ensure_schema()
    handle_values = [str(handle or "").strip() for handle in (handles or []) if str(handle or "").strip()]
    where = ""
    params = []
    if handle_values:
        where = "AND shopify_handle = ANY(%s)"
        params.append(handle_values)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT shopify_handle, asset_type, asset_name, asset_url,
                       google_drive_file_id, google_drive_file_url, notes,
                       is_primary, created_at, updated_at
                FROM product_assets
                WHERE asset_type='psd_master_file'
                  AND is_primary IS DISTINCT FROM FALSE
                  AND COALESCE(NULLIF(asset_url, ''), NULLIF(google_drive_file_url, '')) <> ''
                  {where}
                ORDER BY shopify_handle, updated_at DESC NULLS LAST
                """,
                tuple(params),
            )
            rows = cur.fetchall()
    assets = {}
    for row in rows:
        handle = row.get("shopify_handle")
        if handle and handle not in assets:
            assets[handle] = row
    return assets


def get_psd_link_stats():
    ensure_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH products AS (
                    SELECT shopify_handle, product_title FROM edition_products WHERE shopify_handle IS NOT NULL
                    UNION
                    SELECT handle AS shopify_handle, title AS product_title FROM shopify_products WHERE handle IS NOT NULL
                ),
                psd AS (
                    SELECT DISTINCT shopify_handle
                    FROM product_assets
                    WHERE asset_type='psd_master_file'
                      AND is_primary IS DISTINCT FROM FALSE
                      AND COALESCE(NULLIF(asset_url, ''), NULLIF(google_drive_file_url, '')) <> ''
                )
                SELECT
                    (SELECT COUNT(*) FROM product_assets) AS product_assets_count,
                    (SELECT COUNT(*) FROM product_assets WHERE asset_type='psd_master_file') AS psd_master_file_count,
                    (SELECT COUNT(*) FROM products) AS products_count,
                    (SELECT COUNT(*) FROM products p JOIN psd ON psd.shopify_handle=p.shopify_handle) AS matched_psd_count,
                    (SELECT COUNT(*) FROM products p LEFT JOIN psd ON psd.shopify_handle=p.shopify_handle WHERE psd.shopify_handle IS NULL) AS missing_psd_count
                """
            )
            return cur.fetchone() or {}


def list_missing_psd_products(limit=500):
    ensure_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH products AS (
                    SELECT ep.shopify_handle, ep.product_title, sp.admin_url, sp.online_store_url
                    FROM edition_products ep
                    LEFT JOIN shopify_products sp ON sp.handle=ep.shopify_handle
                    WHERE ep.shopify_handle IS NOT NULL
                    UNION
                    SELECT sp.handle AS shopify_handle, sp.title AS product_title, sp.admin_url, sp.online_store_url
                    FROM shopify_products sp
                    WHERE sp.handle IS NOT NULL
                )
                SELECT p.*
                FROM products p
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM product_assets pa
                    WHERE pa.shopify_handle=p.shopify_handle
                      AND pa.asset_type='psd_master_file'
                      AND pa.is_primary IS DISTINCT FROM FALSE
                      AND COALESCE(NULLIF(pa.asset_url, ''), NULLIF(pa.google_drive_file_url, '')) <> ''
                )
                ORDER BY p.product_title NULLS LAST, p.shopify_handle
                LIMIT %s
                """,
                (limit,),
            )
            return cur.fetchall()


def list_product_assets(search=""):
    ensure_schema()
    search_value = f"%{search.strip().lower()}%" if search.strip() else None
    with connect() as conn:
        with conn.cursor() as cur:
            if search_value:
                cur.execute(
                    """
                    SELECT ep.shopify_handle, ep.product_title, ep.active, ep.sold_out,
                           pa.asset_type, pa.asset_name, pa.asset_url, pa.google_drive_file_id,
                           pa.google_drive_file_url,
                           pa.notes, pa.is_primary, pa.created_at, pa.updated_at
                    FROM edition_products ep
                    LEFT JOIN product_assets pa ON pa.shopify_handle = ep.shopify_handle
                    WHERE LOWER(COALESCE(ep.product_title, '')) LIKE %s
                       OR LOWER(COALESCE(ep.shopify_handle, '')) LIKE %s
                    ORDER BY ep.product_title NULLS LAST, pa.asset_type
                    """,
                    (search_value, search_value),
                )
            else:
                cur.execute(
                    """
                    SELECT ep.shopify_handle, ep.product_title, ep.active, ep.sold_out,
                           pa.asset_type, pa.asset_name, pa.asset_url, pa.google_drive_file_id,
                           pa.google_drive_file_url,
                           pa.notes, pa.is_primary, pa.created_at, pa.updated_at
                    FROM edition_products ep
                    LEFT JOIN product_assets pa ON pa.shopify_handle = ep.shopify_handle
                    ORDER BY ep.product_title NULLS LAST, pa.asset_type
                    """
                )
            return cur.fetchall()


def list_known_product_handles(search=""):
    ensure_schema()
    search_value = f"%{search.strip().lower()}%" if search.strip() else None
    with connect() as conn:
        with conn.cursor() as cur:
            if search_value:
                cur.execute(
                    """
                    SELECT shopify_handle, product_title
                    FROM edition_products
                    WHERE LOWER(COALESCE(product_title, '')) LIKE %s
                       OR LOWER(COALESCE(shopify_handle, '')) LIKE %s
                    UNION
                    SELECT handle AS shopify_handle, title AS product_title
                    FROM shopify_products
                    WHERE LOWER(COALESCE(title, '')) LIKE %s
                       OR LOWER(COALESCE(handle, '')) LIKE %s
                    ORDER BY product_title NULLS LAST, shopify_handle
                    """,
                    (search_value, search_value, search_value, search_value),
                )
            else:
                cur.execute(
                    """
                    SELECT shopify_handle, product_title
                    FROM edition_products
                    UNION
                    SELECT handle AS shopify_handle, title AS product_title
                    FROM shopify_products
                    ORDER BY product_title NULLS LAST, shopify_handle
                    """
                )
            return [row for row in cur.fetchall() if row.get("shopify_handle")]


def upsert_product_asset(
    shopify_handle,
    asset_type,
    asset_url,
    notes="",
    *,
    asset_name="",
    google_drive_file_id="",
    is_primary=None,
):
    ensure_schema()
    if asset_type not in ASSET_TYPES:
        raise ValueError("Unsupported asset type.")
    shopify_handle = _normalize_handle(shopify_handle)
    asset_url = str(asset_url or "").strip()
    google_drive_file_id = str(google_drive_file_id or "").strip() or extract_google_drive_file_id(asset_url)
    primary_value = asset_type == "psd_master_file" if is_primary is None else bool(is_primary)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO product_assets(
                    shopify_handle, asset_type, asset_name, asset_url,
                    google_drive_file_id, google_drive_file_url, notes, is_primary, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now(), now())
                ON CONFLICT (shopify_handle, asset_type) DO UPDATE SET
                    asset_name=EXCLUDED.asset_name,
                    asset_url=EXCLUDED.asset_url,
                    google_drive_file_id=EXCLUDED.google_drive_file_id,
                    google_drive_file_url=EXCLUDED.google_drive_file_url,
                    notes=EXCLUDED.notes,
                    is_primary=EXCLUDED.is_primary,
                    updated_at=now()
                """,
                (
                    shopify_handle,
                    asset_type,
                    asset_name,
                    asset_url,
                    google_drive_file_id,
                    asset_url,
                    notes,
                    primary_value,
                ),
            )
        conn.commit()


def remove_product_asset(shopify_handle, asset_type="psd_master_file"):
    ensure_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM product_assets
                WHERE shopify_handle=%s AND asset_type=%s
                """,
                (_normalize_handle(shopify_handle), asset_type),
            )
        conn.commit()


def _shopify_gid(resource_type, value):
    raw = str(value or "").strip()
    if raw.startswith("gid://"):
        return raw
    if not raw:
        return ""
    return f"gid://shopify/{resource_type}/{raw}"


def _usable_customer_name(value):
    name = str(value or "").strip()
    if name.lower() in {"", "customer not shown", "not shown", "unknown customer"}:
        return ""
    return name


def _customer_name_for_storage(order):
    return _usable_customer_name(order.get("customer_name")) or str(
        order.get("customer_email") or order.get("email") or ""
    ).strip()


def _customer_from_order(order):
    customer_email = order.get("customer_email") or order.get("email") or ""
    customer_name = _customer_name_for_storage(order) or "Customer not shown"
    customer_id = order.get("shopify_customer_id") or order.get("customer_id") or customer_email or order.get("shopify_order_id")
    return {
        "shopify_customer_id": str(customer_id or ""),
        "customer_name": customer_name,
        "email": customer_email,
        "raw_json": order.get("customer_raw") or {},
    }


def _upsert_customer(cur, customer):
    if not customer.get("shopify_customer_id"):
        return
    raw_customer = customer.get("raw_json") or {}
    first_name = raw_customer.get("firstName") or raw_customer.get("first_name") or ""
    last_name = raw_customer.get("lastName") or raw_customer.get("last_name") or ""
    cur.execute(
        """
        INSERT INTO shopify_customers(
            shopify_customer_id, customer_name, email, first_name, last_name, raw_json, raw, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, now())
        ON CONFLICT (shopify_customer_id) DO UPDATE SET
            customer_name=EXCLUDED.customer_name,
            email=EXCLUDED.email,
            first_name=EXCLUDED.first_name,
            last_name=EXCLUDED.last_name,
            raw_json=EXCLUDED.raw_json,
            raw=EXCLUDED.raw,
            updated_at=now()
        """,
        (
            customer["shopify_customer_id"],
            customer.get("customer_name"),
            customer.get("email"),
            first_name,
            last_name,
            json_dumps(customer.get("raw_json")),
            json_dumps(customer.get("raw_json")),
        ),
    )


def _upsert_order(cur, order):
    customer_name = _customer_name_for_storage(order) or "Customer not shown"
    customer_email = str(order.get("customer_email") or order.get("email") or "").strip()
    order_name = order.get("order_name")
    order_number = order.get("order_number")
    customer_id = order.get("customer_id") or order.get("shopify_customer_id") or ""
    raw_json = json_dumps(order)
    cur.execute(
        """
        INSERT INTO shopify_orders(
            shopify_order_id, legacy_resource_id, order_name, shopify_order_name,
            order_number, shopify_order_number, admin_url,
            customer_id, shopify_customer_id, customer_name, customer_email, email,
            financial_status, fulfillment_status,
            total_price, currency, created_at, remote_updated_at, processed_at, cancelled_at,
            raw_json, raw, synced_at, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                NULLIF(%s, '')::timestamptz, NULLIF(%s, '')::timestamptz,
                NULLIF(%s, '')::timestamptz, NULLIF(%s, '')::timestamptz,
                %s::jsonb, %s::jsonb, now(), now())
        ON CONFLICT (shopify_order_id) DO UPDATE SET
            legacy_resource_id=EXCLUDED.legacy_resource_id,
            order_name=EXCLUDED.order_name,
            shopify_order_name=EXCLUDED.shopify_order_name,
            order_number=EXCLUDED.order_number,
            shopify_order_number=EXCLUDED.shopify_order_number,
            admin_url=EXCLUDED.admin_url,
            customer_id=EXCLUDED.customer_id,
            shopify_customer_id=EXCLUDED.shopify_customer_id,
            customer_name=EXCLUDED.customer_name,
            customer_email=EXCLUDED.customer_email,
            email=EXCLUDED.email,
            financial_status=EXCLUDED.financial_status,
            fulfillment_status=EXCLUDED.fulfillment_status,
            total_price=EXCLUDED.total_price,
            currency=EXCLUDED.currency,
            created_at=EXCLUDED.created_at,
            remote_updated_at=EXCLUDED.remote_updated_at,
            processed_at=EXCLUDED.processed_at,
            cancelled_at=EXCLUDED.cancelled_at,
            raw_json=EXCLUDED.raw_json,
            raw=EXCLUDED.raw,
            synced_at=now(),
            updated_at=now()
        """,
        (
            order.get("shopify_order_id"),
            order.get("legacy_resource_id"),
            order_name,
            order_name,
            order_number,
            order_number,
            order.get("admin_url"),
            customer_id,
            customer_id,
            customer_name,
            customer_email,
            customer_email,
            order.get("financial_status"),
            order.get("fulfillment_status"),
            order.get("total_price"),
            order.get("currency"),
            order.get("created_at") or "",
            order.get("remote_updated_at") or "",
            order.get("processed_at") or "",
            order.get("cancelled_at") or "",
            raw_json,
            raw_json,
        ),
    )


def _upsert_order_lines(cur, order):
    has_line_variant_id = column_exists(cur, "shopify_order_lines", "shopify_variant_id")
    variant_column = ", shopify_variant_id" if has_line_variant_id else ""
    variant_value = ", %s" if has_line_variant_id else ""
    variant_update = (
        "\n                shopify_variant_id=COALESCE(NULLIF(EXCLUDED.shopify_variant_id, ''), shopify_order_lines.shopify_variant_id),"
        if has_line_variant_id
        else ""
    )
    for line_index, line_item in enumerate(order.get("line_items") or [], start=1):
        line_item_id = str(
            line_item.get("shopify_line_item_id")
            or f"{order.get('shopify_order_id') or 'order'}:line:{line_index}"
        ).strip()
        if not line_item_id:
            continue
        shopify_product_id = str(line_item.get("shopify_product_id") or "").strip()
        shopify_variant_id = str(
            line_item.get("shopify_variant_id")
            or line_item.get("variant_id")
            or ""
        ).strip()
        product_title = str(line_item.get("product_title") or "").strip()
        matched_handle = _match_product_handle(
            cur,
            handle=line_item.get("product_handle") or "",
            shopify_product_id=shopify_product_id,
            product_title=product_title,
        )
        cur.execute(
            f"""
            INSERT INTO shopify_order_lines(
                shopify_line_item_id, shopify_order_id, shopify_product_id{variant_column}, shopify_handle,
                product_title, variant_title, sku, quantity, assignment_status, last_error,
                raw_json, synced_at, updated_at
            )
            VALUES (%s, %s, %s{variant_value}, %s, %s, %s, %s, %s, 'Needs Edition', '', %s::jsonb, now(), now())
            ON CONFLICT (shopify_line_item_id) DO UPDATE SET
                shopify_order_id=EXCLUDED.shopify_order_id,
                shopify_product_id=COALESCE(NULLIF(EXCLUDED.shopify_product_id, ''), shopify_order_lines.shopify_product_id),{variant_update}
                shopify_handle=COALESCE(NULLIF(EXCLUDED.shopify_handle, ''), shopify_order_lines.shopify_handle),
                product_title=COALESCE(NULLIF(EXCLUDED.product_title, ''), shopify_order_lines.product_title),
                variant_title=COALESCE(NULLIF(EXCLUDED.variant_title, ''), shopify_order_lines.variant_title),
                sku=COALESCE(NULLIF(EXCLUDED.sku, ''), shopify_order_lines.sku),
                quantity=EXCLUDED.quantity,
                raw_json=EXCLUDED.raw_json,
                synced_at=now(),
                updated_at=now()
            """,
            tuple(
                value
                for value in (
                line_item_id,
                order.get("shopify_order_id") or "",
                shopify_product_id,
                shopify_variant_id if has_line_variant_id else None,
                matched_handle,
                product_title,
                line_item.get("variant_title") or "",
                line_item.get("sku") or "",
                max(1, int(line_item.get("quantity") or 1)),
                json_dumps(line_item),
                )
                if value is not None
            ),
        )


def _persist_order_snapshot(order):
    with connect() as conn:
        try:
            with conn.cursor() as cur:
                customer_started = time.perf_counter()
                customer = _customer_from_order(order)
                _upsert_customer(cur, customer)
                _sync_perf_log("Supabase customer upsert time", customer_started)
                order_started = time.perf_counter()
                _upsert_order(cur, order)
                _sync_perf_log("Supabase order upsert time", order_started, lines=len(order.get("line_items") or []))
                lines_started = time.perf_counter()
                _upsert_order_lines(cur, order)
                _sync_perf_log("Supabase line item upsert time", lines_started, lines=len(order.get("line_items") or []))
                backfill_started = time.perf_counter()
                _backfill_edition_customer_details(cur, order)
                _sync_perf_log("Supabase edition customer backfill time", backfill_started)
                commit_started = time.perf_counter()
                conn.commit()
                _sync_perf_log("Supabase order snapshot commit time", commit_started)
        except Exception:
            conn.rollback()
            raise


def _set_order_line_status(
    cur,
    shopify_line_item_id,
    assignment_status,
    *,
    shopify_product_id="",
    shopify_variant_id="",
    shopify_handle="",
    product_title="",
    variant_title="",
    sku="",
    last_error="",
):
    has_line_variant_id = column_exists(cur, "shopify_order_lines", "shopify_variant_id")
    variant_update_sql = (
        """
            shopify_variant_id=CASE
                WHEN %s <> '' THEN %s
                ELSE shopify_variant_id
            END,
        """
        if has_line_variant_id
        else ""
    )
    variant_params = (
        str(shopify_variant_id or ""),
        str(shopify_variant_id or ""),
    ) if has_line_variant_id else ()
    cur.execute(
        f"""
        UPDATE shopify_order_lines
        SET assignment_status=%s,
            last_error=%s,
            shopify_product_id=CASE
                WHEN %s <> '' THEN %s
                ELSE shopify_product_id
            END,
            {variant_update_sql}
            shopify_handle=CASE
                WHEN %s <> '' THEN %s
                ELSE shopify_handle
            END,
            product_title=CASE
                WHEN %s <> '' THEN %s
                ELSE product_title
            END,
            variant_title=CASE
                WHEN %s <> '' THEN %s
                ELSE variant_title
            END,
            sku=CASE
                WHEN %s <> '' THEN %s
                ELSE sku
            END,
            synced_at=now(),
            updated_at=now()
        WHERE shopify_line_item_id=%s
        """,
        (
            str(assignment_status or "Needs Edition"),
            str(last_error or ""),
            str(shopify_product_id or ""),
            str(shopify_product_id or ""),
            *variant_params,
            str(shopify_handle or ""),
            str(shopify_handle or ""),
            str(product_title or ""),
            str(product_title or ""),
            str(variant_title or ""),
            str(variant_title or ""),
            str(sku or ""),
            str(sku or ""),
            shopify_line_item_id,
        ),
    )


def _mark_order_lines_historical(shopify_order_id, reason=HISTORICAL_ORDER_NOTE):
    if not shopify_order_id:
        return 0
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE shopify_order_lines li
                SET assignment_status=%s,
                    last_error=%s,
                    synced_at=now(),
                    updated_at=now()
                WHERE li.shopify_order_id=%s
                  AND COALESCE(li.assignment_status, '') <> 'Assigned'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM edition_orders eo
                      WHERE eo.shopify_line_item_id=li.shopify_line_item_id
                  )
                """,
                (
                    HISTORICAL_ORDER_STATUS,
                    str(reason or HISTORICAL_ORDER_NOTE),
                    shopify_order_id,
                ),
            )
            updated = cur.rowcount
        conn.commit()
    return updated


def _backfill_edition_customer_details(cur, order):
    customer_name = _customer_name_for_storage(order)
    customer_email = str(order.get("customer_email") or order.get("email") or "").strip()
    if not order.get("shopify_order_id") or not (customer_name or customer_email):
        return 0
    cur.execute(
        """
        UPDATE edition_orders
        SET customer_name = CASE
                WHEN %s <> ''
                 AND LOWER(COALESCE(customer_name, '')) IN ('', 'customer not shown', 'not shown', 'unknown customer')
                THEN %s
                ELSE customer_name
            END,
            shopify_customer_name = CASE
                WHEN %s <> ''
                 AND LOWER(COALESCE(shopify_customer_name, '')) IN ('', 'customer not shown', 'not shown', 'unknown customer')
                THEN %s
                ELSE shopify_customer_name
            END,
            customer_email = CASE
                WHEN %s <> ''
                 AND COALESCE(customer_email, '') = ''
                THEN %s
                ELSE customer_email
            END,
            shopify_customer_email = CASE
                WHEN %s <> ''
                 AND COALESCE(shopify_customer_email, '') = ''
                THEN %s
                ELSE shopify_customer_email
            END
        WHERE shopify_order_id=%s
          AND (
              LOWER(COALESCE(customer_name, '')) IN ('', 'customer not shown', 'not shown', 'unknown customer')
              OR LOWER(COALESCE(shopify_customer_name, '')) IN ('', 'customer not shown', 'not shown', 'unknown customer')
              OR COALESCE(customer_email, '') = ''
              OR COALESCE(shopify_customer_email, '') = ''
          )
        """,
        (
            customer_name,
            customer_name,
            customer_name,
            customer_name,
            customer_email,
            customer_email,
            customer_email,
            customer_email,
            order.get("shopify_order_id"),
        ),
    )
    return cur.rowcount


def _lookup_product_by_handle_or_id(cur, line_item):
    matched = _resolve_edition_product_for_order_line_with_cursor(cur, line_item)
    matched_product = matched.get("product") or {}
    if matched_product:
        return matched_product

    handle = line_item.get("product_handle") or ""
    product_id = line_item.get("shopify_product_id") or ""
    variant_id = line_item.get("shopify_variant_id") or line_item.get("variant_id") or ""
    title = str(line_item.get("product_title") or "").strip()
    normalized_title = _normalize_product_title_key(title)
    if variant_id:
        cur.execute(
            """
            SELECT
                COALESCE(sp.shopify_product_id, sv.shopify_product_id) AS shopify_product_id,
                COALESCE(sp.handle, ep.shopify_handle) AS handle,
                COALESCE(sp.title, ep.product_title, sv.title) AS title
            FROM shopify_variants sv
            LEFT JOIN shopify_products sp ON sp.shopify_product_id = sv.shopify_product_id
            LEFT JOIN edition_products ep ON ep.shopify_product_id = sv.shopify_product_id
            WHERE sv.shopify_variant_id=%s
            LIMIT 1
            """,
            (variant_id,),
        )
        row = cur.fetchone()
        if row and row.get("handle"):
            return row
    if product_id:
        cur.execute(
            """
            SELECT sp.shopify_product_id, sp.handle, sp.title
            FROM shopify_products sp
            WHERE sp.shopify_product_id=%s OR sp.legacy_resource_id=%s
            """,
            (product_id, product_id),
        )
        row = cur.fetchone()
        if row:
            return row
        cur.execute(
            """
            SELECT ep.shopify_product_id, ep.shopify_handle AS handle, ep.product_title AS title
            FROM edition_products ep
            WHERE ep.shopify_product_id=%s
            """,
            (product_id,),
        )
        row = cur.fetchone()
        if row:
            return row
    if handle:
        cur.execute(
            """
            SELECT sp.shopify_product_id, sp.handle, sp.title
            FROM shopify_products sp
            WHERE sp.handle=%s
            """,
            (handle,),
        )
        row = cur.fetchone()
        if row:
            return row
        cur.execute(
            """
            SELECT ep.shopify_product_id, ep.shopify_handle AS handle, ep.product_title AS title
            FROM edition_products ep
            WHERE ep.shopify_handle=%s
            """,
            (handle,),
        )
        row = cur.fetchone()
        if row:
            return row
    if normalized_title:
        cur.execute(
            """
            SELECT sp.shopify_product_id, sp.handle, sp.title
            FROM shopify_products sp
            WHERE COALESCE(sp.title, '') <> ''
            """,
        )
        rows = [
            row
            for row in (cur.fetchall() or [])
            if _normalize_product_title_key(row.get("title")) == normalized_title
        ]
        if len(rows) == 1:
            return rows[0]
        if len(rows) > 1:
            return None
        cur.execute(
            """
            SELECT ep.shopify_product_id, ep.shopify_handle AS handle, ep.product_title AS title
            FROM edition_products ep
            WHERE COALESCE(ep.product_title, '') <> ''
            """,
        )
        rows = [
            row
            for row in (cur.fetchall() or [])
            if _normalize_product_title_key(row.get("title")) == normalized_title
        ]
        if len(rows) == 1:
            return rows[0]
    return None


def _insert_product_if_fetched(cur, product):
    upsert_products([product])
    cur.execute(
        """
        SELECT shopify_product_id, handle, title
        FROM shopify_products
        WHERE shopify_product_id=%s
        """,
        (product.get("shopify_product_id"),),
    )
    return cur.fetchone()


UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _coerce_uuid_or_none(value):
    cleaned = str(value or "").strip()
    return cleaned if UUID_RE.match(cleaned) else None


def _none_if_blank(value):
    cleaned = str(value or "").strip()
    return cleaned or None


def _int_or_none(value):
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def upsert_certificate_metadata(metadata):
    if not is_configured():
        return {"ok": False, "skipped": True, "reason": "Supabase DATABASE_URL is not configured."}
    metadata = dict(metadata or {})
    account_record = shopify_sync.order_certificate_account_record(metadata)
    now_value = datetime.now(timezone.utc).isoformat(timespec="seconds")
    certificate_url = account_record.get("certificate_file_url") or ""
    print_jpg_url = account_record.get("certificate_print_jpg_url") or ""
    preview_image_url = account_record.get("certificate_preview_image_url") or ""
    line_item_unit_index = _int_or_none(
        metadata.get("line_item_unit_index") or metadata.get("allocation_index")
    ) or 1
    row = {
        "edition_order_id": _none_if_blank(metadata.get("edition_order_id")),
        "related_edition_order_id": _coerce_uuid_or_none(metadata.get("related_edition_order_id") or metadata.get("edition_order_id")),
        "shopify_customer_id": _none_if_blank(account_record.get("shopify_customer_id")),
        "customer_email": _none_if_blank(account_record.get("customer_email")),
        "customer_name": _none_if_blank(account_record.get("customer_name")),
        "shopify_order_id": _none_if_blank(account_record.get("shopify_order_id")),
        "shopify_order_name": _none_if_blank(account_record.get("shopify_order_name")),
        "shopify_line_item_id": _none_if_blank(account_record.get("shopify_line_item_id")),
        "shopify_handle": _none_if_blank(account_record.get("product_handle")),
        "product_handle": _none_if_blank(account_record.get("product_handle")),
        "shopify_product_id": _none_if_blank(account_record.get("shopify_product_id")),
        "shopify_variant_id": _none_if_blank(account_record.get("shopify_variant_id")),
        "product_title": _none_if_blank(account_record.get("product_title")),
        "variant_title": _none_if_blank(account_record.get("variant_title")),
        "certificate_id": _none_if_blank(account_record.get("certificate_id")),
        "edition_number": _int_or_none(account_record.get("edition_number")),
        "edition_total": _int_or_none(account_record.get("edition_total")) or 100,
        "edition_limit": _int_or_none(account_record.get("edition_limit") or account_record.get("edition_total")) or 100,
        "edition_display": _none_if_blank(account_record.get("edition_display")),
        "display_edition": _none_if_blank(account_record.get("display_edition") or account_record.get("edition_display")),
        "line_item_unit_index": line_item_unit_index,
        "pdf_filename": _none_if_blank(metadata.get("pdf_filename") or Path(str(metadata.get("local_pdf_path") or "")).name),
        "local_file_path": _none_if_blank(metadata.get("local_pdf_path")),
        "shopify_file_id": _none_if_blank(account_record.get("shopify_file_id")),
        "shopify_file_status": _none_if_blank(account_record.get("shopify_file_status")),
        "shopify_file_url": _none_if_blank(certificate_url),
        "certificate_file_url": _none_if_blank(certificate_url),
        "certificate_pdf_url": _none_if_blank(certificate_url),
        "certificate_print_jpg_url": _none_if_blank(print_jpg_url),
        "certificate_preview_image_url": _none_if_blank(preview_image_url),
        "shopify_pdf_file_id": _none_if_blank(account_record.get("shopify_pdf_file_id") or account_record.get("shopify_file_id")),
        "shopify_print_jpg_file_id": _none_if_blank(account_record.get("shopify_print_jpg_file_id")),
        "shopify_preview_file_id": _none_if_blank(account_record.get("shopify_preview_file_id")),
        "asset_sync_status": _none_if_blank(metadata.get("asset_sync_status")) or (
            "ready" if print_jpg_url and preview_image_url else "pdf_ready"
        ),
        "asset_sync_error": _none_if_blank(metadata.get("asset_sync_error")),
        "certificate_shopify_file_id": _none_if_blank(account_record.get("shopify_file_id")),
        "certificate_status": _none_if_blank(account_record.get("certificate_status")) or "Processing",
        "sync_status": _none_if_blank(metadata.get("sync_status")) or "pending",
        "last_sync_error": _none_if_blank(metadata.get("last_sync_error") or metadata.get("sync_error")),
        "purchase_date": _none_if_blank(account_record.get("purchase_date")),
        "source": "sports_cave_os",
        "generated_at": _none_if_blank(metadata.get("generated_at") or account_record.get("created_at")),
        "status": _none_if_blank(metadata.get("status") or account_record.get("certificate_status")) or "Processing",
        "created_at": _none_if_blank(metadata.get("created_at") or account_record.get("created_at")) or now_value,
        "updated_at": _none_if_blank(metadata.get("updated_at")) or now_value,
    }
    if not row["certificate_id"] and not (row["shopify_order_id"] and row["shopify_line_item_id"] and row["edition_number"]):
        return {"ok": False, "skipped": True, "reason": "Certificate metadata is missing stable identity fields."}

    columns = tuple(row.keys())
    assignments = ", ".join(f"{column}=%s" for column in columns)
    insert_columns = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    ensure_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id
                FROM certificates
                WHERE (%s <> '' AND certificate_id=%s)
                   OR (
                        shopify_order_id=%s
                    AND shopify_line_item_id=%s
                    AND line_item_unit_index=%s
                    AND edition_number=%s
                   )
                ORDER BY updated_at DESC NULLS LAST, id DESC
                LIMIT 1
                """,
                (
                    row["certificate_id"] or "",
                    row["certificate_id"] or "",
                    row["shopify_order_id"],
                    row["shopify_line_item_id"],
                    row["line_item_unit_index"],
                    row["edition_number"],
                ),
            )
            existing = cur.fetchone() or {}
            if existing.get("id"):
                cur.execute(
                    f"UPDATE certificates SET {assignments} WHERE id=%s",
                    tuple(row[column] for column in columns) + (existing["id"],),
                )
                certificate_row_id = existing["id"]
                action = "updated"
            else:
                cur.execute(
                    f"INSERT INTO certificates ({insert_columns}) VALUES ({placeholders}) RETURNING id",
                    tuple(row[column] for column in columns),
                )
                certificate_row_id = (cur.fetchone() or {}).get("id")
                action = "inserted"
            cur.execute(
                """
                UPDATE edition_orders
                SET shopify_customer_id=%s,
                    shopify_order_name=%s,
                    shopify_variant_id=%s,
                    product_handle=%s,
                    edition_display=%s,
                    certificate_status=%s,
                    certificate_id=%s,
                    shopify_file_id=%s,
                    shopify_file_status=%s,
                    certificate_file_url=%s,
                    purchase_date=%s,
                    updated_at=now()
                WHERE shopify_line_item_id=%s
                  AND allocation_index=%s
                """,
                (
                    row["shopify_customer_id"],
                    row["shopify_order_name"],
                    row["shopify_variant_id"],
                    row["product_handle"],
                    row["edition_display"],
                    row["certificate_status"],
                    row["certificate_id"],
                    row["shopify_file_id"],
                    row["shopify_file_status"],
                    row["certificate_file_url"],
                    row["purchase_date"],
                    row["shopify_line_item_id"],
                    row["line_item_unit_index"],
                ),
            )
        conn.commit()
    return {"ok": True, "action": action, "id": certificate_row_id, "certificate_id": row["certificate_id"]}


def _upsert_file_asset_with_cursor(cur, metadata):
    if not table_exists(cur, "file_assets"):
        return {"ok": False, "warning": "R2 file uploaded, but file_assets metadata table is missing."}
    bucket = str(metadata.get("bucket") or "").strip()
    object_key = str(metadata.get("object_key") or "").strip()
    asset_type = str(metadata.get("asset_type") or "").strip()
    if not bucket or not object_key or not asset_type:
        return {"ok": False, "warning": "R2 file uploaded, but required file metadata was incomplete."}
    cur.execute(
        """
        INSERT INTO file_assets (
            asset_type, bucket, object_key, filename, mime_type, size_bytes,
            related_shopify_product_id, related_shopify_order_id, related_shopify_handle,
            related_edition_order_id, source, status, created_at, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s, 'r2'), COALESCE(%s, 'active'), now(), now())
        ON CONFLICT (bucket, object_key) DO UPDATE SET
            asset_type=EXCLUDED.asset_type,
            filename=EXCLUDED.filename,
            mime_type=EXCLUDED.mime_type,
            size_bytes=EXCLUDED.size_bytes,
            related_shopify_product_id=EXCLUDED.related_shopify_product_id,
            related_shopify_order_id=EXCLUDED.related_shopify_order_id,
            related_shopify_handle=EXCLUDED.related_shopify_handle,
            related_edition_order_id=EXCLUDED.related_edition_order_id,
            source=EXCLUDED.source,
            status=EXCLUDED.status,
            updated_at=now()
        RETURNING id
        """,
        (
            asset_type,
            bucket,
            object_key,
            metadata.get("filename"),
            metadata.get("mime_type"),
            metadata.get("size_bytes"),
            metadata.get("related_shopify_product_id"),
            metadata.get("related_shopify_order_id"),
            metadata.get("related_shopify_handle"),
            _coerce_uuid_or_none(metadata.get("related_edition_order_id")),
            metadata.get("source") or "r2",
            metadata.get("status") or "active",
        ),
    )
    row = cur.fetchone() or {}
    return {"ok": True, "id": row.get("id"), "bucket": bucket, "object_key": object_key}


def upsert_file_asset(metadata):
    if not is_configured():
        return {"ok": False, "warning": "R2 file uploaded, but Supabase DATABASE_URL is not configured."}
    try:
        ensure_schema()
        with connect() as conn:
            with conn.cursor() as cur:
                result = _upsert_file_asset_with_cursor(cur, metadata or {})
            conn.commit()
        return result
    except Exception as error:
        return {"ok": False, "warning": f"R2 file uploaded, but metadata was not saved: {error}"}


def _log_app_error_with_cursor(cur, error_type, message, context=None):
    if not table_exists(cur, "app_errors"):
        return
    cur.execute(
        """
        INSERT INTO app_errors(error_type, message, context, source, severity, created_at)
        VALUES (%s, %s, %s::jsonb, 'sports_cave_os', 'warning', now())
        """,
        (error_type, str(message), json_dumps(context or {})),
    )


def _record_r2_file_asset(cur, *, asset_type, upload_result, local_path, assignment, mime_type):
    if not upload_result.get("ok"):
        return upload_result
    path = Path(local_path)
    return _upsert_file_asset_with_cursor(
        cur,
        {
            "asset_type": asset_type,
            "bucket": upload_result.get("bucket"),
            "object_key": upload_result.get("key"),
            "filename": path.name,
            "mime_type": mime_type,
            "size_bytes": upload_result.get("size_bytes") or (path.stat().st_size if path.exists() else None),
            "related_shopify_product_id": assignment.get("shopify_product_id"),
            "related_shopify_order_id": assignment.get("shopify_order_id"),
            "related_shopify_handle": assignment.get("shopify_handle"),
            "related_edition_order_id": assignment.get("id"),
            "source": "r2",
            "status": "active",
        },
    )


def _upload_certificate_outputs_to_r2(cur, assignment, pdf_path, preview_path=""):
    if not r2_storage.safe_r2_enabled():
        return {}
    bucket = r2_storage.get_bucket_name("certificates")
    if not bucket:
        return {"warning": "R2 certificates bucket is not configured."}

    order_name = assignment.get("order_name") or assignment.get("shopify_order_name") or assignment.get("shopify_order_id")
    pdf_key = r2_storage.certificate_pdf_key(
        assignment.get("shopify_handle"),
        order_name,
        assignment.get("edition_number"),
    )
    pdf_upload = r2_storage.upload_file(bucket, pdf_key, pdf_path, content_type="application/pdf")
    if not pdf_upload.get("ok"):
        _log_app_error_with_cursor(
            cur,
            "r2_certificate_pdf_upload_failed",
            pdf_upload.get("error") or "Certificate PDF upload failed.",
            {"edition_order_id": assignment.get("id"), "bucket": bucket, "object_key": pdf_key},
        )
        return {"pdf": pdf_upload}

    metadata_result = _record_r2_file_asset(
        cur,
        asset_type="certificate_pdf",
        upload_result=pdf_upload,
        local_path=pdf_path,
        assignment=assignment,
        mime_type="application/pdf",
    )
    if not metadata_result.get("ok"):
        _log_app_error_with_cursor(
            cur,
            "r2_certificate_metadata_failed",
            metadata_result.get("warning") or "Certificate PDF metadata was not saved.",
            {"edition_order_id": assignment.get("id"), "bucket": bucket, "object_key": pdf_key},
        )

    preview_upload = {}
    preview_key = ""
    if preview_path:
        preview_key = r2_storage.certificate_preview_key(
            assignment.get("shopify_handle"),
            order_name,
            assignment.get("edition_number"),
        )
        preview_upload = r2_storage.upload_file(bucket, preview_key, preview_path, content_type="image/png")
        if preview_upload.get("ok"):
            preview_metadata = _record_r2_file_asset(
                cur,
                asset_type="certificate_preview_png",
                upload_result=preview_upload,
                local_path=preview_path,
                assignment=assignment,
                mime_type="image/png",
            )
            if not preview_metadata.get("ok"):
                _log_app_error_with_cursor(
                    cur,
                    "r2_certificate_preview_metadata_failed",
                    preview_metadata.get("warning") or "Certificate preview metadata was not saved.",
                    {"edition_order_id": assignment.get("id"), "bucket": bucket, "object_key": preview_key},
                )
        else:
            _log_app_error_with_cursor(
                cur,
                "r2_certificate_preview_upload_failed",
                preview_upload.get("error") or "Certificate preview upload failed.",
                {"edition_order_id": assignment.get("id"), "bucket": bucket, "object_key": preview_key},
            )

    certificate_update = {
        "certificate_r2_bucket": bucket,
        "certificate_r2_key": pdf_key,
        "certificate_preview_r2_bucket": bucket if preview_upload.get("ok") else "",
        "certificate_preview_r2_key": preview_key if preview_upload.get("ok") else "",
    }
    cur.execute(
        """
        UPDATE certificates
        SET certificate_r2_bucket=%s,
            certificate_r2_key=%s,
            certificate_preview_r2_bucket=%s,
            certificate_preview_r2_key=%s
        WHERE COALESCE(related_edition_order_id::text, edition_order_id::text)=%s
        """,
        (
            certificate_update["certificate_r2_bucket"],
            certificate_update["certificate_r2_key"],
            certificate_update["certificate_preview_r2_bucket"],
            certificate_update["certificate_preview_r2_key"],
            str(assignment.get("id")),
        ),
    )
    cur.execute(
        """
        UPDATE edition_orders
        SET certificate_r2_bucket=%s,
            certificate_r2_key=%s,
            certificate_preview_r2_bucket=%s,
            certificate_preview_r2_key=%s
        WHERE id::text=%s
        """,
        (
            certificate_update["certificate_r2_bucket"],
            certificate_update["certificate_r2_key"],
            certificate_update["certificate_preview_r2_bucket"],
            certificate_update["certificate_preview_r2_key"],
            str(assignment.get("id")),
        ),
    )
    return {"pdf": pdf_upload, "preview": preview_upload, **certificate_update}


def resolve_product_for_line(line_item, *, fetch_missing_products=True):
    ensure_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            product = _lookup_product_by_handle_or_id(cur, line_item)
    if product or not fetch_missing_products or not line_item.get("shopify_product_id"):
        return product
    fetched = shopify_sync.fetch_product_by_shopify_id(line_item["shopify_product_id"])
    upsert_products([fetched])
    with connect() as conn:
        with conn.cursor() as cur:
            return _lookup_product_by_handle_or_id(cur, line_item)


def _generate_certificate_for_assignment(cur, assignment, *, force=False):
    local_file_path = ""
    local_preview_path = ""
    try:
        cur.execute(
            """
            SELECT local_file_path,
                   COALESCE(NULLIF(shopify_file_url, ''), NULLIF(certificate_file_url, '')) AS shopify_file_url,
                   certificate_r2_bucket, certificate_r2_key
            FROM certificates
            WHERE COALESCE(related_edition_order_id::text, edition_order_id::text)=%s
            """,
            (str(assignment["id"]),),
        )
        existing_certificate = cur.fetchone()
        if not force and existing_certificate and (
            existing_certificate.get("shopify_file_url")
            or existing_certificate.get("local_file_path")
            or (existing_certificate.get("certificate_r2_bucket") and existing_certificate.get("certificate_r2_key"))
        ):
            cur.execute(
                "UPDATE edition_orders SET certificate_status='Certificate Ready' WHERE id::text=%s",
                (str(assignment["id"]),),
            )
            return (
                existing_certificate.get("local_file_path")
                or existing_certificate.get("shopify_file_url")
                or existing_certificate.get("certificate_r2_key")
            )

        local_file_path = generate_certificate_pdf(
            CERTIFICATE_OUTPUT_DIR,
            product_title=assignment.get("product_title"),
            edition_number=assignment.get("edition_number"),
            edition_total=assignment.get("edition_total"),
            order_name=assignment.get("order_name"),
            customer_name=assignment.get("customer_name"),
            assigned_at=assignment.get("assigned_at"),
            shopify_handle=assignment.get("shopify_handle") or "",
        )
        try:
            local_preview_path = generate_certificate_preview_png(
                CERTIFICATE_OUTPUT_DIR,
                product_title=assignment.get("product_title"),
                edition_number=assignment.get("edition_number"),
                edition_total=assignment.get("edition_total"),
                order_name=assignment.get("order_name"),
                shopify_handle=assignment.get("shopify_handle") or "",
            )
        except Exception as preview_error:
            _log_app_error_with_cursor(
                cur,
                "certificate_preview_generation_failed",
                str(preview_error),
                {"edition_order_id": assignment.get("id")},
            )
        generated_certificate_id = certificate_id(
            assignment.get("order_name") or assignment.get("shopify_order_id"),
            assignment.get("edition_number"),
        )
        cur.execute(
            """
            INSERT INTO certificates(
                edition_order_id, related_edition_order_id, shopify_customer_id, customer_email, customer_name,
                shopify_order_id, shopify_order_name, shopify_line_item_id, shopify_handle, product_handle,
                shopify_product_id, shopify_variant_id, product_title, variant_title,
                certificate_id, edition_number, edition_total, edition_display, line_item_unit_index,
                pdf_filename, local_file_path, certificate_status, status, purchase_date, source,
                generated_at, created_at, updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, 'Processing', 'Local PDF', %s, 'sports_cave_os',
                now(), now(), now()
            )
            ON CONFLICT (edition_order_id) DO UPDATE SET
                related_edition_order_id=EXCLUDED.related_edition_order_id,
                shopify_customer_id=EXCLUDED.shopify_customer_id,
                customer_email=EXCLUDED.customer_email,
                customer_name=EXCLUDED.customer_name,
                shopify_order_name=EXCLUDED.shopify_order_name,
                shopify_line_item_id=EXCLUDED.shopify_line_item_id,
                product_handle=EXCLUDED.product_handle,
                shopify_product_id=EXCLUDED.shopify_product_id,
                shopify_variant_id=EXCLUDED.shopify_variant_id,
                product_title=EXCLUDED.product_title,
                variant_title=EXCLUDED.variant_title,
                certificate_id=EXCLUDED.certificate_id,
                edition_display=EXCLUDED.edition_display,
                line_item_unit_index=EXCLUDED.line_item_unit_index,
                pdf_filename=EXCLUDED.pdf_filename,
                local_file_path=EXCLUDED.local_file_path,
                generated_at=now(),
                status='Local PDF',
                updated_at=now()
            """,
            (
                str(assignment["id"]),
                _coerce_uuid_or_none(assignment.get("id")),
                assignment.get("shopify_customer_id") or assignment.get("customer_id"),
                assignment.get("customer_email"),
                assignment.get("customer_name"),
                assignment.get("shopify_order_id"),
                assignment.get("order_name") or assignment.get("shopify_order_name"),
                assignment.get("shopify_line_item_id"),
                assignment.get("shopify_handle"),
                assignment.get("product_handle") or assignment.get("shopify_handle"),
                assignment.get("shopify_product_id"),
                assignment.get("shopify_variant_id"),
                assignment.get("product_title"),
                assignment.get("variant_title"),
                generated_certificate_id,
                assignment.get("edition_number"),
                assignment.get("edition_total"),
                format_edition_display_number(assignment.get("edition_number"), assignment.get("edition_total") or 100),
                assignment.get("allocation_index") or 1,
                Path(local_file_path).name,
                local_file_path,
                assignment.get("assigned_at"),
            ),
        )
        _upload_certificate_outputs_to_r2(cur, assignment, local_file_path, local_preview_path)
        cur.execute(
            "UPDATE edition_orders SET certificate_status='Certificate Ready' WHERE id::text=%s",
            (str(assignment["id"]),),
        )
    except Exception as error:
        cur.execute(
            "UPDATE edition_orders SET certificate_status='Certificate Missing' WHERE id::text=%s",
            (str(assignment["id"]),),
        )
        raise error
    return local_file_path


def _resolve_next_edition_number_state(next_number, should_be_next, allow_counter_override):
    if next_number < should_be_next:
        if allow_counter_override:
            return {"next_number": next_number, "mode": "manual_override_active"}
        return {"next_number": should_be_next, "mode": "auto_correct"}
    if next_number > should_be_next:
        return {"next_number": next_number, "mode": "respect_manual_counter"}
    return {"next_number": next_number, "mode": "matched"}


def allocate_edition_for_order_line(
    *,
    shopify_order_id,
    shopify_order_name,
    shopify_line_item_id,
    allocation_index,
    shopify_handle,
    product_title,
    variant_title="",
    sku="",
    shopify_product_id="",
    customer_name="",
    customer_email="",
    allocation_status="assigned",
    promised_edition_number=None,
    promised_edition_total=None,
    assignment_source="supabase_sequential_allocation",
):
    ensure_schema()
    if not shopify_handle:
        raise ValueError("Shopify handle is required for edition allocation.")
    if not shopify_order_id:
        raise ValueError("Shopify order ID is required for edition allocation.")
    if not shopify_line_item_id:
        raise ValueError("Shopify line item ID is required for edition allocation.")

    with connect() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT eo.*, o.order_name
                    FROM edition_orders eo
                    LEFT JOIN shopify_orders o ON o.shopify_order_id=eo.shopify_order_id
                    WHERE eo.shopify_order_id=%s
                      AND eo.shopify_line_item_id=%s
                      AND eo.allocation_index=%s
                    """,
                    (shopify_order_id, shopify_line_item_id, allocation_index),
                )
                existing = cur.fetchone()
                if existing:
                    target_existing_number = _int_value(promised_edition_number, 0)
                    existing_number = _int_value(existing.get("edition_number"), 0)
                    if target_existing_number and existing_number and existing_number != target_existing_number:
                        message = (
                            f"Existing edition #{existing_number} for {shopify_order_name or shopify_order_id} "
                            f"does not match promised edition #{target_existing_number}."
                        )
                        cur.execute(
                            """
                            INSERT INTO app_errors(error_type, message, context)
                            VALUES ('promised_edition_existing_mismatch', %s, %s::jsonb)
                            """,
                            (
                                message,
                                json_dumps(
                                    {
                                        "shopify_order_id": shopify_order_id,
                                        "shopify_line_item_id": shopify_line_item_id,
                                        "allocation_index": allocation_index,
                                        "shopify_handle": shopify_handle,
                                        "existing_edition_number": existing_number,
                                        "promised_edition_number": target_existing_number,
                                    }
                                ),
                            ),
                        )
                        conn.commit()
                        return {"created": False, "assignment": None, "sold_out": False, "error": message}
                    if customer_name or customer_email:
                        cur.execute(
                            """
                            UPDATE edition_orders
                            SET customer_name = CASE
                                    WHEN %s <> ''
                                     AND LOWER(COALESCE(customer_name, '')) IN ('', 'customer not shown', 'not shown', 'unknown customer')
                                    THEN %s
                                    ELSE customer_name
                                END,
                                shopify_customer_name = CASE
                                    WHEN %s <> ''
                                     AND LOWER(COALESCE(shopify_customer_name, '')) IN ('', 'customer not shown', 'not shown', 'unknown customer')
                                    THEN %s
                                    ELSE shopify_customer_name
                                END,
                                customer_email = CASE
                                    WHEN %s <> ''
                                     AND COALESCE(customer_email, '') = ''
                                    THEN %s
                                    ELSE customer_email
                                END,
                                shopify_customer_email = CASE
                                    WHEN %s <> ''
                                     AND COALESCE(shopify_customer_email, '') = ''
                                    THEN %s
                                    ELSE shopify_customer_email
                                END
                            WHERE shopify_order_id=%s
                              AND shopify_line_item_id=%s
                              AND allocation_index=%s
                            RETURNING *
                            """,
                            (
                                _usable_customer_name(customer_name),
                                _usable_customer_name(customer_name),
                                _usable_customer_name(customer_name),
                                _usable_customer_name(customer_name),
                                str(customer_email or "").strip(),
                                str(customer_email or "").strip(),
                                str(customer_email or "").strip(),
                                str(customer_email or "").strip(),
                                shopify_order_id,
                                shopify_line_item_id,
                                allocation_index,
                            ),
                        )
                        updated_existing = cur.fetchone()
                        if updated_existing:
                            existing = updated_existing
                    conn.commit()
                    return {"created": False, "assignment": existing, "sold_out": False, "error": ""}

                cur.execute(
                    """
                    INSERT INTO edition_products(
                        shopify_product_id, shopify_product_gid, shopify_handle, product_title,
                        edition_total, next_edition_number, active, is_active, sold_out, is_sold_out, updated_at
                    )
                    VALUES (%s, %s, %s, %s, 100, 1, TRUE, TRUE, FALSE, FALSE, now())
                    ON CONFLICT (shopify_handle) DO UPDATE SET
                        shopify_product_id=COALESCE(EXCLUDED.shopify_product_id, edition_products.shopify_product_id),
                        shopify_product_gid=COALESCE(EXCLUDED.shopify_product_gid, edition_products.shopify_product_gid),
                        product_title=COALESCE(EXCLUDED.product_title, edition_products.product_title),
                        updated_at=now()
                    """,
                    (shopify_product_id, shopify_product_id, shopify_handle, product_title),
                )
                cur.execute(
                    """
                    SELECT *
                    FROM edition_products
                    WHERE shopify_handle=%s
                    FOR UPDATE
                    """,
                    (shopify_handle,),
                )
                edition_product = cur.fetchone()
                _, edition_run = _get_active_edition_run_for_handle(
                    cur,
                    shopify_handle,
                    lock=True,
                    create_missing=True,
                )
                if not edition_run:
                    raise ValueError(f"No active edition run found for {shopify_handle}.")
                next_number = int(edition_run.get("next_edition_number") or edition_product.get("next_edition_number") or 1)
                edition_total = int(edition_run.get("edition_total") or edition_product.get("edition_total") or 100)
                edition_name = edition_run.get("edition_name") or DEFAULT_EDITION_NAME
                run_status = _clean_edition_run_status(edition_run.get("status"))
                cur.execute(
                    """
                    SELECT COALESCE(MAX(edition_number), 0) AS max_assigned
                    FROM edition_orders
                    WHERE shopify_handle=%s
                    """,
                    (shopify_handle,),
                )
                max_assigned = int((cur.fetchone() or {}).get("max_assigned") or 0)
                safe_floor = max(max_assigned + 1, 1)
                if next_number < 1:
                    cur.execute(
                        """
                        UPDATE edition_runs
                        SET next_edition_number=1, updated_at=now()
                        WHERE id=%s
                        """,
                        (edition_run.get("id"),),
                    )
                    cur.execute(
                        """
                        UPDATE edition_products
                        SET next_edition_number=1, updated_at=now()
                        WHERE shopify_handle=%s
                        """,
                        (shopify_handle,),
                    )
                    cur.execute(
                        """
                        INSERT INTO app_errors(error_type, message, context)
                        VALUES ('edition_counter_zero_blocked', %s, %s::jsonb)
                        """,
                        (
                            f"Edition counter for {shopify_handle} was below 1 and was corrected before allocation.",
                            json_dumps(
                                {
                                    "shopify_handle": shopify_handle,
                                    "previous_next_edition_number": next_number,
                                    "corrected_next_edition_number": 1,
                                }
                            ),
                        ),
                    )
                    next_number = 1
                if next_number < safe_floor:
                    previous_next_number = next_number
                    cur.execute(
                        """
                        UPDATE edition_runs
                        SET next_edition_number=%s, updated_at=now()
                        WHERE id=%s
                        """,
                        (safe_floor, edition_run.get("id")),
                    )
                    cur.execute(
                        """
                        UPDATE edition_products
                        SET next_edition_number=%s,
                            last_assigned_edition=%s,
                            updated_at=now()
                        WHERE shopify_handle=%s
                        """,
                        (safe_floor, max_assigned, shopify_handle),
                    )
                    audit_started = time.perf_counter()
                    _insert_audit_log(
                        cur,
                        event_type="edition_counter_auto_corrected",
                        entity_type="edition_product",
                        entity_id=str(edition_product.get("id") or ""),
                        shopify_handle=shopify_handle,
                        old_value={
                            "next_edition_number": previous_next_number,
                            "last_assigned_edition": edition_product.get("last_assigned_edition"),
                        },
                        new_value={
                            "next_edition_number": safe_floor,
                            "last_assigned_edition": max_assigned,
                        },
                        reason="Raised next edition number to the current ledger floor before auto allocation.",
                        actor="sports_cave_os_sync",
                        source="supabase_ledger",
                    )
                    _sync_perf_log("audit log write time", audit_started, event="edition_counter_auto_corrected")
                    next_number = safe_floor

                if run_status == SOLD_OUT_RUN_STATUS or next_number > edition_total:
                    cur.execute(
                        """
                        UPDATE edition_runs
                        SET status=%s, updated_at=now()
                        WHERE id=%s
                        """,
                        (SOLD_OUT_RUN_STATUS, edition_run.get("id")),
                    )
                    cur.execute(
                        """
                        UPDATE edition_products
                        SET sold_out=TRUE, is_sold_out=TRUE, updated_at=now()
                        WHERE shopify_handle=%s
                        """,
                        (shopify_handle,),
                    )
                    message = (
                        f"{shopify_handle} is sold out. Could not allocate edition "
                        f"{next_number}/{edition_total}."
                    )
                    cur.execute(
                        """
                        INSERT INTO app_errors(error_type, message, context)
                        VALUES ('sold_out_allocation_blocked', %s, %s::jsonb)
                        """,
                        (
                            message,
                            json_dumps(
                                {
                                    "shopify_order_id": shopify_order_id,
                                    "shopify_line_item_id": shopify_line_item_id,
                                    "allocation_index": allocation_index,
                                    "shopify_handle": shopify_handle,
                                }
                            ),
                        ),
                    )
                    conn.commit()
                    return {"created": False, "assignment": None, "sold_out": True, "error": message}

                target_number = _int_value(promised_edition_number, 0)
                if target_number:
                    if target_number < 1 or target_number > edition_total:
                        message = (
                            f"Promised edition #{target_number}/{edition_total} is outside the edition range "
                            f"for {shopify_handle}."
                        )
                        cur.execute(
                            """
                            INSERT INTO app_errors(error_type, message, context)
                            VALUES ('promised_edition_out_of_range', %s, %s::jsonb)
                            """,
                            (
                                message,
                                json_dumps(
                                    {
                                        "shopify_order_id": shopify_order_id,
                                        "shopify_line_item_id": shopify_line_item_id,
                                        "allocation_index": allocation_index,
                                        "shopify_handle": shopify_handle,
                                        "edition_number": target_number,
                                        "edition_total": edition_total,
                                    }
                                ),
                            ),
                        )
                        conn.commit()
                        return {"created": False, "assignment": None, "sold_out": False, "error": message}
                    cur.execute(
                        """
                        SELECT id, shopify_order_id, shopify_order_name, shopify_line_item_id,
                               allocation_index, product_title, shopify_handle, edition_number
                        FROM edition_orders
                        WHERE edition_number=%s
                          AND COALESCE(shopify_handle, product_handle, '')=%s
                          AND NOT (
                              shopify_order_id=%s
                              AND shopify_line_item_id=%s
                              AND COALESCE(allocation_index, 1)=%s
                          )
                        LIMIT 1
                        """,
                        (
                            target_number,
                            shopify_handle,
                            shopify_order_id,
                            shopify_line_item_id,
                            allocation_index,
                        ),
                    )
                    conflict = cur.fetchone()
                    if conflict:
                        message = (
                            f"Promised edition conflict for {shopify_handle} "
                            f"#{target_number}/{edition_total}; already used by "
                            f"{conflict.get('shopify_order_name') or conflict.get('shopify_order_id')}."
                        )
                        cur.execute(
                            """
                            INSERT INTO app_errors(error_type, message, context)
                            VALUES ('promised_edition_conflict', %s, %s::jsonb)
                            """,
                            (
                                message,
                                json_dumps(
                                    {
                                        "shopify_order_id": shopify_order_id,
                                        "shopify_line_item_id": shopify_line_item_id,
                                        "allocation_index": allocation_index,
                                        "shopify_handle": shopify_handle,
                                        "edition_number": target_number,
                                        "conflict": conflict,
                                    }
                                ),
                            ),
                        )
                        conn.commit()
                        return {"created": False, "assignment": None, "sold_out": False, "error": message}
                else:
                    target_number = next_number

                cur.execute(
                    """
                    INSERT INTO edition_orders(
                        shopify_order_id, shopify_order_name, shopify_line_item_id, shopify_product_id,
                        shopify_handle, product_title, edition_run_id, edition_name, variant_title, sku,
                        customer_name, customer_email, shopify_customer_name, shopify_customer_email,
                        edition_number, edition_total, allocation_index, quantity,
                        assigned_at, certificate_status, status, source, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1,
                            now(), 'Certificate Missing', %s, %s, now())
                    ON CONFLICT DO NOTHING
                    RETURNING id, shopify_order_id, shopify_line_item_id, shopify_product_id,
                              shopify_handle, product_title, edition_run_id, edition_name, variant_title, sku, customer_name,
                              customer_email, edition_number, edition_total, allocation_index,
                              assigned_at, certificate_status
                    """,
                    (
                        shopify_order_id,
                        shopify_order_name,
                        shopify_line_item_id,
                        shopify_product_id,
                        shopify_handle,
                        product_title,
                        edition_run.get("id"),
                        edition_name,
                        variant_title,
                        sku,
                        customer_name,
                        customer_email,
                        customer_name,
                        customer_email,
                        target_number,
                        _int_value(promised_edition_total, 0) or edition_total,
                        allocation_index,
                        allocation_status or "assigned",
                        assignment_source or ("shopify_purchase_snapshot" if promised_edition_number else "supabase_sequential_allocation"),
                    ),
                )
                inserted = cur.fetchone()
                if not inserted:
                    cur.execute(
                        """
                        SELECT eo.*, o.order_name
                        FROM edition_orders eo
                        LEFT JOIN shopify_orders o ON o.shopify_order_id=eo.shopify_order_id
                        WHERE eo.shopify_order_id=%s
                          AND eo.shopify_line_item_id=%s
                          AND eo.allocation_index=%s
                        """,
                        (shopify_order_id, shopify_line_item_id, allocation_index),
                    )
                    existing_after_conflict = cur.fetchone()
                    if existing_after_conflict:
                        conn.commit()
                        return {
                            "created": False,
                            "assignment": existing_after_conflict,
                            "sold_out": False,
                            "error": "",
                        }
                    message = (
                        f"Edition allocation conflict for {shopify_handle} "
                        f"#{target_number}/{edition_total}."
                    )
                    cur.execute(
                        """
                        INSERT INTO app_errors(error_type, message, context)
                        VALUES ('edition_allocation_conflict', %s, %s::jsonb)
                        """,
                        (
                            message,
                            json_dumps(
                                {
                                    "shopify_order_id": shopify_order_id,
                                    "shopify_line_item_id": shopify_line_item_id,
                                    "allocation_index": allocation_index,
                                    "shopify_handle": shopify_handle,
                                    "edition_number": target_number,
                                }
                            ),
                        ),
                    )
                    conn.commit()
                    return {"created": False, "assignment": None, "sold_out": False, "error": message}

                incremented_next = max(next_number, target_number + 1)
                last_assigned_for_counter = max(incremented_next - 1, target_number)
                cur.execute(
                    """
                    UPDATE edition_runs
                    SET next_edition_number=%s,
                        status=%s,
                        updated_at=now()
                    WHERE id=%s
                    """,
                    (
                        incremented_next,
                        SOLD_OUT_RUN_STATUS if incremented_next > edition_total else ACTIVE_RUN_STATUS,
                        edition_run.get("id"),
                    ),
                )
                cur.execute(
                    """
                    UPDATE edition_products
                    SET next_edition_number=%s,
                        edition_name=%s,
                        last_assigned_edition=%s,
                        remaining_count=%s,
                        sold_out=%s,
                        is_sold_out=%s,
                        updated_at=now()
                    WHERE shopify_handle=%s
                    """,
                    (
                        incremented_next,
                        edition_name,
                        last_assigned_for_counter,
                        max(edition_total - last_assigned_for_counter, 0),
                        incremented_next > edition_total,
                        incremented_next > edition_total,
                        shopify_handle,
                    ),
                )
                inserted["order_name"] = shopify_order_name
                audit_started = time.perf_counter()
                _insert_audit_log(
                    cur,
                    event_type="edition_order_purchase_snapshot_allocation" if promised_edition_number else "edition_order_auto_allocation",
                    entity_type="edition_order",
                    entity_id=str(inserted.get("id") or ""),
                    shopify_order_id=shopify_order_id,
                    shopify_line_item_id=shopify_line_item_id,
                    shopify_handle=shopify_handle,
                    old_value={},
                    new_value={
                        "edition_number": target_number,
                        "edition_total": edition_total,
                        "allocation_index": allocation_index,
                        "shopify_order_name": shopify_order_name,
                        "variant_title": variant_title or "",
                        "sku": sku or "",
                    },
                    reason=(
                        "Purchase-time Shopify edition snapshot applied during order sync."
                        if promised_edition_number
                        else "Auto allocation during Shopify order sync."
                    ),
                    actor="sports_cave_os_sync",
                    source="supabase_ledger",
                )
                _sync_perf_log("audit log write time", audit_started, event="edition_order_allocation")
                conn.commit()
                return {"created": True, "assignment": inserted, "sold_out": False, "error": ""}
        except Exception:
            conn.rollback()
            raise


def process_paid_order(
    order,
    *,
    fetch_missing_products=True,
    allocation_status="assigned",
    generate_certificates=True,
    sync_product_metafields=True,
    assign_editions=True,
    allocation_skip_reason="",
):
    ensure_schema()
    if not order.get("shopify_order_id"):
        raise ValueError("Shopify order ID is missing.")
    assignments_created = 0
    existing_assignments_skipped = 0
    missing_mapping_skipped = 0
    changed_handles = set()
    generated_certificates = 0
    errors = []
    _persist_order_snapshot(order)

    financial_status = str(order.get("financial_status") or "").upper()
    if financial_status and financial_status not in {"PAID", "PARTIALLY_PAID"}:
        return {
            "assignments_created": 0,
            "existing_assignments_skipped": 0,
            "missing_mapping_skipped": 0,
            "generated_certificates": 0,
            "historical_lines_marked": 0,
            "changed_handles": [],
            "errors": [],
        }
    if not assign_editions:
        return {
            "assignments_created": 0,
            "existing_assignments_skipped": 0,
            "missing_mapping_skipped": 0,
            "generated_certificates": 0,
            "historical_lines_marked": _mark_order_lines_historical(
                order.get("shopify_order_id"),
                allocation_skip_reason or HISTORICAL_ORDER_NOTE,
            ),
            "changed_handles": [],
            "errors": [],
        }

    order_customer_name = _customer_name_for_storage(order)
    order_customer_email = str(order.get("customer_email") or order.get("email") or "").strip()
    new_assignments = []
    product_cache = {}
    product_match_ms = 0.0
    allocation_ms = 0.0
    line_status_ms = 0.0
    line_items_for_allocation = sorted(
        enumerate(order.get("line_items") or [], start=1),
        key=lambda item: (
            _line_item_position(item[1] if isinstance(item[1], dict) else {}, item[0]),
            _line_item_sort_identity(item[1] if isinstance(item[1], dict) else {}),
            item[0],
        ),
    )
    for line_index, line_item in line_items_for_allocation:
        if not isinstance(line_item, dict):
            line_item = {}
        quantity = max(1, int(line_item.get("quantity") or 1))
        line_item_id = str(
            line_item.get("shopify_line_item_id")
            or f"{order['shopify_order_id']}:line:{line_index}"
        )
        line_cache_keys = [
            str(line_item.get("shopify_product_id") or "").strip(),
            str(line_item.get("shopify_variant_id") or line_item.get("variant_id") or "").strip(),
            str(line_item.get("product_handle") or "").strip().lower(),
            str(line_item.get("product_title") or "").strip().lower(),
            _normalize_product_title_key(line_item.get("product_title")),
        ]
        cached_product = next((product_cache[key] for key in line_cache_keys if key and key in product_cache), None)
        match_result = {}
        try:
            if cached_product is not None:
                product = cached_product
                match_result = {"product": product, "status": "matched", "reason": "Matched from order sync product cache."}
            else:
                product_match_started = time.perf_counter()
                match_result = resolve_edition_product_for_order_line(
                    line_item,
                    fetch_missing_products=fetch_missing_products,
                )
                product_match_ms += (time.perf_counter() - product_match_started) * 1000
                product = match_result.get("product") or {}
        except Exception as error:
            product = None
            errors.append(f"Product fetch failed for {line_item.get('product_title')}: {error}")
            line_status_started = time.perf_counter()
            with connect() as conn:
                with conn.cursor() as cur:
                    _set_order_line_status(
                        cur,
                        line_item_id,
                        "Error",
                        shopify_product_id=line_item.get("shopify_product_id") or "",
                        shopify_variant_id=line_item.get("shopify_variant_id") or line_item.get("variant_id") or "",
                        shopify_handle=line_item.get("product_handle") or "",
                        product_title=line_item.get("product_title") or "",
                        variant_title=line_item.get("variant_title") or "",
                        sku=line_item.get("sku") or "",
                        last_error=str(error),
                    )
                conn.commit()
            line_status_ms += (time.perf_counter() - line_status_started) * 1000
            continue

        if product:
            for cache_key in (
                str(product.get("shopify_product_id") or "").strip(),
                str(line_item.get("shopify_variant_id") or line_item.get("variant_id") or "").strip(),
                str(product.get("handle") or "").strip().lower(),
                str(product.get("title") or "").strip().lower(),
                _normalize_product_title_key(product.get("title")),
                *line_cache_keys,
            ):
                if cache_key:
                    product_cache[cache_key] = product

        handle = (product or {}).get("handle") or ""
        if not handle:
            missing_mapping_skipped += quantity
            mapping_reason = (match_result or {}).get("reason") or "Could not confidently match the line to an Edition Ops product."
            errors.append(f"Missing product mapping for line item {line_item_id}: {mapping_reason}")
            line_status_started = time.perf_counter()
            with connect() as conn:
                with conn.cursor() as cur:
                    _set_order_line_status(
                        cur,
                        line_item_id,
                        "Product Not Found",
                        shopify_product_id=(product or {}).get("shopify_product_id") or line_item.get("shopify_product_id") or "",
                        shopify_variant_id=line_item.get("shopify_variant_id") or line_item.get("variant_id") or "",
                        product_title=(product or {}).get("title") or line_item.get("product_title") or "",
                        variant_title=line_item.get("variant_title") or "",
                        sku=line_item.get("sku") or "",
                        last_error=mapping_reason,
                    )
                conn.commit()
            line_status_ms += (time.perf_counter() - line_status_started) * 1000
            continue
        if product and not bool(product.get("active", True)):
            missing_mapping_skipped += quantity
            setup_reason = "Matched Edition Ops product is disabled."
            errors.append(f"Edition setup disabled for line item {line_item_id}: {handle}.")
            line_status_started = time.perf_counter()
            with connect() as conn:
                with conn.cursor() as cur:
                    _set_order_line_status(
                        cur,
                        line_item_id,
                        "Needs Edition Setup",
                        shopify_product_id=product.get("shopify_product_id") or line_item.get("shopify_product_id") or "",
                        shopify_variant_id=line_item.get("shopify_variant_id") or line_item.get("variant_id") or "",
                        shopify_handle=handle,
                        product_title=product.get("title") or line_item.get("product_title") or "",
                        variant_title=line_item.get("variant_title") or "",
                        sku=line_item.get("sku") or "",
                        last_error=setup_reason,
                    )
                conn.commit()
            line_status_ms += (time.perf_counter() - line_status_started) * 1000
            continue
        product_title = (product or {}).get("title") or line_item.get("product_title") or "Sports Cave Artwork"
        product_id = (product or {}).get("shopify_product_id") or line_item.get("shopify_product_id") or ""
        line_created = 0
        line_existing = 0
        line_sold_out = False
        line_errors = []

        for allocation_index in range(1, quantity + 1):
            promised_hint = promised_edition_hint_for_order_line(order, line_item, allocation_index)
            allocation_started = time.perf_counter()
            result = allocate_edition_for_order_line(
                shopify_order_id=order.get("shopify_order_id"),
                shopify_order_name=order.get("order_name"),
                shopify_line_item_id=line_item_id,
                allocation_index=allocation_index,
                shopify_handle=handle,
                shopify_product_id=product_id,
                product_title=product_title,
                variant_title=line_item.get("variant_title") or "",
                sku=line_item.get("sku") or "",
                customer_name=order_customer_name or order_customer_email,
                customer_email=order_customer_email,
                allocation_status=allocation_status,
                promised_edition_number=promised_hint.get("edition_number"),
                promised_edition_total=promised_hint.get("edition_total"),
                assignment_source=promised_hint.get("source") or "supabase_sequential_allocation",
            )
            allocation_ms += (time.perf_counter() - allocation_started) * 1000
            if result.get("error"):
                line_errors.append(result["error"])
                errors.append(result["error"])
            assignment = result.get("assignment")
            if result.get("created") and assignment:
                assignments_created += 1
                line_created += 1
                changed_handles.add(handle)
                new_assignments.append(assignment)
            elif assignment:
                existing_assignments_skipped += 1
                line_existing += 1
            if result.get("sold_out"):
                line_sold_out = True

        line_status = "Needs Edition"
        line_error = line_errors[0] if line_errors else ""
        if line_created + line_existing >= quantity:
            line_status = "Assigned"
            line_error = ""
        elif line_sold_out:
            line_status = "Sold Out"
        elif line_errors:
            line_status = "Error"
        line_status_started = time.perf_counter()
        with connect() as conn:
            with conn.cursor() as cur:
                _set_order_line_status(
                    cur,
                    line_item_id,
                    line_status,
                    shopify_product_id=product_id,
                    shopify_variant_id=line_item.get("shopify_variant_id") or line_item.get("variant_id") or "",
                    shopify_handle=handle,
                    product_title=product_title,
                    variant_title=line_item.get("variant_title") or "",
                    sku=line_item.get("sku") or "",
                    last_error=line_error,
                )
            conn.commit()
        line_status_ms += (time.perf_counter() - line_status_started) * 1000

    if generate_certificates:
        certificate_started = time.perf_counter()
        for assignment in new_assignments:
            try:
                generate_certificate_for_edition_order(assignment["id"])
                generated_certificates += 1
            except Exception as error:
                errors.append(
                    f"Certificate generation failed for {assignment.get('shopify_handle')} "
                    f"#{assignment.get('edition_number')}: {error}"
                )
                log_app_error(
                    "certificate_generation_failed",
                    str(error),
                    {"edition_order_id": assignment.get("id"), "shopify_handle": assignment.get("shopify_handle")},
                )
        _sync_perf_log("certificate generation time", certificate_started, generated=generated_certificates)
    else:
        _sync_perf_log("certificate generation time", None, elapsed_ms=0, skipped=True)

    if sync_product_metafields:
        metafield_started = time.perf_counter()
        for handle in sorted(changed_handles):
            try:
                sync_product_edition_metafields(handle)
            except Exception as error:
                errors.append(f"Shopify metafield sync failed for {handle}: {error}")
        _sync_perf_log("Shopify metafield mirror/update time", metafield_started, handles=len(changed_handles))
    else:
        _sync_perf_log("Shopify metafield mirror/update time", None, elapsed_ms=0, deferred_handles=len(changed_handles))

    audit_error_started = time.perf_counter()
    for message in errors:
        log_app_error("order_processing_warning", message, {"shopify_order_id": order.get("shopify_order_id")})
    _sync_perf_log("audit log write time", audit_error_started, warnings=len(errors))
    _sync_perf_log(
        "order processing detail",
        None,
        product_match_ms=int(product_match_ms),
        edition_allocation_ms=int(allocation_ms),
        line_status_ms=int(line_status_ms),
        assignments=assignments_created,
        existing_assignments=existing_assignments_skipped,
        missing_mapping=missing_mapping_skipped,
    )
    return {
        "assignments_created": assignments_created,
        "existing_assignments_skipped": existing_assignments_skipped,
        "missing_mapping_skipped": missing_mapping_skipped,
        "generated_certificates": generated_certificates,
        "historical_lines_marked": 0,
        "changed_handles": sorted(changed_handles),
        "errors": errors,
    }


def process_shopify_order_for_editions(
    order_payload,
    *,
    fetch_missing_products=True,
    allocation_status="assigned",
    generate_certificates=False,
    sync_product_metafields=True,
    assign_editions=True,
    allocation_skip_reason="",
):
    """Persist one Shopify order, assign editions, and sync product widget metafields."""
    order = dict(order_payload or {})
    if not order.get("shopify_order_id") and order.get("id") and isinstance(order.get("line_items"), list):
        order = normalize_rest_order(order)
    return process_paid_order(
        order,
        fetch_missing_products=fetch_missing_products,
        allocation_status=allocation_status,
        generate_certificates=generate_certificates,
        sync_product_metafields=sync_product_metafields,
        assign_editions=assign_editions,
        allocation_skip_reason=allocation_skip_reason,
    )


def _preview_product_counter_state(cur, line_item, cache):
    product_result = _resolve_edition_product_for_order_line_with_cursor(cur, line_item)
    product = product_result.get("product") or {}
    handle = str(product.get("handle") or "").strip()
    if not handle:
        return {}
    if not bool(product.get("active", True)):
        return {}
    cached = cache.get(handle)
    if cached is not None:
        return cached
    cur.execute(
        """
        SELECT
            ep.shopify_product_id,
            ep.shopify_handle,
            ep.product_title,
            COALESCE(NULLIF(er.next_edition_number, 0), NULLIF(ep.next_edition_number, 0), 1) AS next_edition_number,
            COALESCE(NULLIF(er.edition_total, 0), NULLIF(ep.edition_total, 0), 100) AS edition_total,
            COALESCE(er.status, %s) AS run_status,
            COALESCE(ep.sold_out, FALSE) AS sold_out
        FROM edition_products ep
        LEFT JOIN edition_runs er
          ON er.shopify_handle = ep.shopify_handle
         AND er.status IN (%s, %s)
        WHERE ep.shopify_handle=%s
        ORDER BY CASE WHEN er.status=%s THEN 0 ELSE 1 END, er.updated_at DESC NULLS LAST
        LIMIT 1
        """,
        (
            ACTIVE_RUN_STATUS,
            ACTIVE_RUN_STATUS,
            SOLD_OUT_RUN_STATUS,
            handle,
            ACTIVE_RUN_STATUS,
        ),
    )
    row = cur.fetchone() or {}
    if not row:
        cache[handle] = {}
        return {}
    state = {
        "shopify_product_id": str(row.get("shopify_product_id") or product.get("shopify_product_id") or line_item.get("shopify_product_id") or ""),
        "handle": handle,
        "title": str(row.get("product_title") or product.get("title") or line_item.get("product_title") or ""),
        "next_edition_number": max(int(row.get("next_edition_number") or 1), 1),
        "edition_total": max(int(row.get("edition_total") or 100), 1),
        "sold_out": bool(row.get("sold_out")),
        "run_status": _clean_edition_run_status(row.get("run_status")),
    }
    cur.execute(
        """
        SELECT COALESCE(MAX(edition_number), 0) AS max_assigned
        FROM edition_orders
        WHERE shopify_handle=%s
        """,
        (handle,),
    )
    max_assigned = int((cur.fetchone() or {}).get("max_assigned") or 0)
    state["next_edition_number"] = max(state["next_edition_number"], max_assigned + 1)
    cache[handle] = state
    return state


def _latest_paid_orders_payload(
    config=None,
    *,
    limit=DEFAULT_LATEST_PAID_ORDER_FETCH_LIMIT,
    lookback_days=DEFAULT_LATEST_PAID_ORDER_LOOKBACK_DAYS,
    backfill_latest_paid=False,
):
    config = config or shopify_sync.get_config()
    state = get_sync_state()
    sync_from = None
    query = ""
    sort_key = "CREATED_AT"
    reverse = True
    query_mode = "latest_paid_backfill" if backfill_latest_paid else "cursor"
    cursor = _latest_paid_sync_cursor(state, backfill_latest_paid=backfill_latest_paid)
    if backfill_latest_paid:
        query = "financial_status:paid"
        sort_key = "CREATED_AT"
    else:
        sync_from = _parse_datetime(cursor.get("cursor_used"))
        query = f"financial_status:paid updated_at:>='{_datetime_to_shopify_query(sync_from)}'"
        sort_key = "UPDATED_AT"
        reverse = False
        query_mode = cursor.get("query_mode") or "cursor"
    query_parameters = {
        "status": "any",
        "financial_status": "paid",
        "fulfillment_status": "",
        "updated_at_min": _datetime_to_shopify_query(sync_from) if sync_from else "",
        "created_at_min": "",
        "limit": int(limit or DEFAULT_LATEST_PAID_ORDER_FETCH_LIMIT),
        "sort": sort_key,
        "order": "desc" if reverse else "asc",
    }
    fetch_started = time.perf_counter()
    _sync_perf_log(
        "cursor query build",
        None,
        mode=query_mode,
        cursor=bool(sync_from),
        cursor_source=cursor.get("cursor_source"),
        cursor_used=_datetime_to_setting(sync_from) if sync_from else "",
        cursor_ignored=cursor.get("cursor_ignored"),
        lookback_hours="" if cursor.get("cursor_raw") or backfill_latest_paid else DEFAULT_CURSORLESS_ORDER_LOOKBACK_HOURS,
    )
    _sync_perf_log(
        "Shopify query parameters",
        None,
        status=query_parameters["status"],
        financial_status=query_parameters["financial_status"],
        fulfillment_status=query_parameters["fulfillment_status"] or "none",
        updated_at_min=query_parameters["updated_at_min"] or "none",
        created_at_min=query_parameters["created_at_min"] or "none",
        limit=query_parameters["limit"],
        sort=query_parameters["sort"],
        order=query_parameters["order"],
    )
    _sync_perf_log("Shopify fetch start", None, mode=query_mode, limit=limit, cursor=bool(sync_from))
    fetched = shopify_sync.fetch_latest_paid_orders(
        limit=limit,
        lookback_days=lookback_days,
        query=query or None,
        sort_key=sort_key,
        reverse=reverse,
        lightweight=True,
        config=config,
    )
    orders = fetched.get("orders") or []
    _sync_perf_log(
        "Shopify fetch end",
        fetch_started,
        pages=fetched.get("pages_fetched") or (1 if orders else 0),
        orders=len(orders),
        line_items=fetched.get("line_items_fetched") or _sync_order_line_count(orders),
        metafields=fetched.get("metafields_fetched") or _sync_order_metafield_count(orders),
        query_mode=query_mode,
    )
    return {
        "orders": orders,
        "query": str(fetched.get("query") or ""),
        "query_parameters": query_parameters,
        "limit": int(fetched.get("limit") or limit or DEFAULT_LATEST_PAID_ORDER_FETCH_LIMIT),
        "lookback_days": int(fetched.get("lookback_days") or lookback_days or DEFAULT_LATEST_PAID_ORDER_LOOKBACK_DAYS),
        "sync_from": _datetime_to_setting(sync_from) if sync_from else "",
        "query_mode": query_mode,
        "cursor_raw": cursor.get("cursor_raw") or "",
        "cursor_source": cursor.get("cursor_source") or "",
        "cursor_timezone": cursor.get("cursor_timezone") or "UTC",
        "cursor_warning": cursor.get("cursor_warning") or "",
        "cursor_ignored": bool(cursor.get("cursor_ignored")),
        "backfill_latest_paid": bool(backfill_latest_paid),
        "pages_fetched": int(fetched.get("pages_fetched") or (1 if orders else 0)),
        "line_items_fetched": int(fetched.get("line_items_fetched") or _sync_order_line_count(orders)),
        "metafields_fetched": int(fetched.get("metafields_fetched") or _sync_order_metafield_count(orders)),
        "empty_fetch_reason": _latest_paid_empty_fetch_reason(
            {
                "backfill_latest_paid": bool(backfill_latest_paid),
                "cursor_warning": cursor.get("cursor_warning") or "",
                "sync_from": _datetime_to_setting(sync_from) if sync_from else "",
            }
        )
        if not orders
        else "",
    }


def list_existing_shopify_order_states(order_ids):
    ensure_schema()
    values = [str(order_id or "").strip() for order_id in (order_ids or []) if str(order_id or "").strip()]
    if not values:
        return {}
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT shopify_order_id, remote_updated_at, created_at, synced_at
                FROM shopify_orders
                WHERE shopify_order_id = ANY(%s)
                """,
                (values,),
            )
            rows = cur.fetchall()
    return {
        str(row.get("shopify_order_id") or "").strip(): {
            "remote_updated_at": row.get("remote_updated_at"),
            "created_at": row.get("created_at"),
            "synced_at": row.get("synced_at"),
        }
        for row in rows
        if row.get("shopify_order_id")
    }


def _latest_paid_order_needs_sync(order, existing_order_ids, existing_line_item_ids, existing_order_states):
    order_id = str(order.get("shopify_order_id") or "").strip()
    if not order_id:
        return False
    if order_id not in existing_order_ids:
        return True
    for line_item in order.get("line_items") or []:
        line_item_id = str(line_item.get("shopify_line_item_id") or "").strip()
        if line_item_id and line_item_id not in existing_line_item_ids:
            return True
    existing = existing_order_states.get(order_id) or {}
    incoming_updated = _parse_datetime(
        order.get("remote_updated_at")
        or order.get("updated_at")
        or order.get("processed_at")
        or order.get("created_at")
    )
    stored_updated = _parse_datetime(
        existing.get("remote_updated_at")
        or existing.get("created_at")
        or existing.get("synced_at")
    )
    if incoming_updated and not stored_updated:
        return True
    if not incoming_updated:
        return False
    return incoming_updated > stored_updated


def _analyze_fetched_orders_for_preview(
    fetched_orders,
    *,
    tracking_start,
    mode_label="dry_run",
    respect_tracking_start=True,
):
    seen = len(fetched_orders)
    imported_orders = 0
    new_lines_imported = 0
    existing_lines_preserved = 0
    assignments = 0
    existing_assignments_preserved = 0
    missing_mapping_skipped = 0
    historical_orders_skipped = 0
    historical_lines_skipped = 0
    sold_out_skipped = 0
    preview_rows = []

    order_ids = [order.get("shopify_order_id") for order in fetched_orders]
    line_item_ids = []
    for order in fetched_orders:
        for line_item in order.get("line_items") or []:
            line_id = str(line_item.get("shopify_line_item_id") or "").strip()
            if line_id:
                line_item_ids.append(line_id)
    existing_order_ids = list_existing_shopify_order_ids(order_ids)
    existing_line_ids = list_existing_shopify_line_item_ids(line_item_ids)
    assignment_snapshot = get_order_line_assignment_snapshot(line_item_ids)
    imported_orders = sum(
        1 for order in fetched_orders if str(order.get("shopify_order_id") or "").strip() not in existing_order_ids
    )
    new_lines_imported = sum(1 for line_id in line_item_ids if line_id not in existing_line_ids)
    existing_lines_preserved = max(len(line_item_ids) - new_lines_imported, 0)

    product_state_cache = {}
    with connect() as conn:
        with conn.cursor() as cur:
            for order in sorted(fetched_orders, key=order_allocation_sort_key):
                should_assign_editions = True
                order_datetime = _order_effective_datetime(order)
                if respect_tracking_start and order_datetime and tracking_start and order_datetime < tracking_start:
                    should_assign_editions = False
                    historical_orders_skipped += 1
                order_missing_mapping = False
                order_would_allocate = 0
                for line_index, line_item in enumerate(order.get("line_items") or [], start=1):
                    if not isinstance(line_item, dict):
                        line_item = {}
                    quantity = max(1, int(line_item.get("quantity") or 1))
                    line_item_id = str(
                        line_item.get("shopify_line_item_id")
                        or f"{order.get('shopify_order_id') or 'order'}:line:{line_index}"
                    )
                    snapshot = assignment_snapshot.get(line_item_id) or {}
                    existing_indexes = {
                        int(item.get("allocation_index") or 0)
                        for item in (snapshot.get("assignments") or [])
                        if int(item.get("allocation_index") or 0) > 0
                    }
                    if not should_assign_editions:
                        historical_lines_skipped += max(quantity - len(existing_indexes), 0)
                        existing_assignments_preserved += len(existing_indexes)
                        continue
                    product_state = _preview_product_counter_state(cur, line_item, product_state_cache)
                    handle = str(product_state.get("handle") or line_item.get("product_handle") or "").strip()
                    if not handle:
                        missing_mapping_skipped += max(quantity - len(existing_indexes), 0)
                        existing_assignments_preserved += len(existing_indexes)
                        order_missing_mapping = True
                        continue
                    for allocation_index in range(1, quantity + 1):
                        if allocation_index in existing_indexes:
                            existing_assignments_preserved += 1
                            continue
                        next_number = int(product_state.get("next_edition_number") or 1)
                        edition_total = int(product_state.get("edition_total") or 100)
                        is_sold_out = (
                            product_state.get("run_status") == SOLD_OUT_RUN_STATUS
                            or bool(product_state.get("sold_out"))
                            or next_number > edition_total
                        )
                        if is_sold_out:
                            sold_out_skipped += 1
                            continue
                        assignments += 1
                        order_would_allocate += 1
                        product_state["next_edition_number"] = next_number + 1
                preview_rows.append(
                    {
                        "order_name": str(order.get("order_name") or ""),
                        "date": str(order.get("processed_at") or order.get("created_at") or "")[:10],
                        "customer_name": str(order.get("customer_name") or order.get("customer_email") or ""),
                        "financial_status": str(order.get("financial_status") or ""),
                        "fulfillment_status": str(order.get("fulfillment_status") or ""),
                        "line_item_count": len(order.get("line_items") or []),
                        "already_exists": str(order.get("shopify_order_id") or "").strip() in existing_order_ids,
                        "would_insert": str(order.get("shopify_order_id") or "").strip() not in existing_order_ids,
                        "missing_mapping": order_missing_mapping,
                        "would_allocate": order_would_allocate,
                        "shopify_order_id": str(order.get("shopify_order_id") or ""),
                    }
                )

    existing_orders_skipped = max(seen - imported_orders, 0)
    preview_rows = sorted(
        preview_rows,
        key=lambda row: (
            _allocation_datetime_sort_value(row.get("date")),
            _numeric_sort_value(row.get("order_name")),
        ),
        reverse=True,
    )
    return {
        "mode": mode_label,
        "orders_seen": seen,
        "shopify_orders_fetched": seen,
        "existing_orders_skipped": existing_orders_skipped,
        "new_orders_inserted": imported_orders,
        "new_lines_inserted": new_lines_imported,
        "existing_lines_preserved": existing_lines_preserved,
        "edition_allocations_created": assignments,
        "existing_allocations_preserved": existing_assignments_preserved,
        "missing_mapping_skipped": missing_mapping_skipped,
        "historical_orders_skipped": historical_orders_skipped,
        "historical_lines_skipped": historical_lines_skipped,
        "sold_out_skipped": sold_out_skipped,
        "preview_rows": preview_rows[:10],
        "errors": [],
    }


def preview_shopify_orders_to_supabase(
    config=None,
    *,
    query=None,
    max_orders=DEFAULT_INCREMENTAL_ORDER_FETCH_LIMIT,
    days=365,
):
    ensure_schema()
    config = config or shopify_sync.get_config()
    seen = 0
    pages_fetched = 0
    imported_orders = 0
    new_lines_imported = 0
    existing_lines_preserved = 0
    assignments = 0
    existing_assignments_preserved = 0
    missing_mapping_skipped = 0
    historical_orders_skipped = 0
    historical_lines_skipped = 0
    sold_out_skipped = 0
    errors = []
    sync_from = None
    bootstrap_recent_orders = False
    fetched_orders = []
    total_started = time.perf_counter()

    state = get_sync_state()
    tracking_start = _parse_datetime(state.get("edition_tracking_start_at"))
    if not tracking_start:
        tracking_start = ensure_edition_tracking_start()
    last_success = _parse_datetime(
        state.get("last_successful_order_fetch_at") or state.get("last_successful_order_sync_at")
    )
    if not last_success and count_shopify_orders() == 0:
        bootstrap_recent_orders = True
        bootstrap_now = utc_now_datetime()
        sync_from = bootstrap_now - timedelta(days=DEFAULT_INITIAL_ORDER_BOOTSTRAP_DAYS)
        if not state.get("edition_tracking_start_at"):
            tracking_start = bootstrap_now - timedelta(days=DEFAULT_INITIAL_ORDER_ASSIGNMENT_WINDOW_DAYS)
    else:
        last_success = last_success or tracking_start
        sync_from = last_success - timedelta(
            minutes=state.get("sync_lookback_buffer_minutes") or DEFAULT_SYNC_LOOKBACK_BUFFER_MINUTES
        )
    effective_query = query or (
        f"financial_status:paid fulfillment_status:unfulfilled "
        f"updated_at:>='{_datetime_to_shopify_query(sync_from)}'"
    )
    sync_config = dict(config)
    sync_limit = max(int(max_orders or DEFAULT_INCREMENTAL_ORDER_FETCH_LIMIT), 1)
    sync_config["max_orders"] = sync_limit
    for page in shopify_sync.iter_order_pages(
        query=effective_query,
        days=days,
        max_orders=sync_limit,
        page_size=50,
        config=sync_config,
    ):
        pages_fetched += 1
        page_orders = page.get("orders") or []
        seen += len(page_orders)
        fetched_orders.extend(page_orders)

    order_ids = [order.get("shopify_order_id") for order in fetched_orders]
    line_item_ids = []
    for order in fetched_orders:
        for line_item in order.get("line_items") or []:
            line_id = str(line_item.get("shopify_line_item_id") or "").strip()
            if line_id:
                line_item_ids.append(line_id)
    existing_order_ids = list_existing_shopify_order_ids(order_ids)
    existing_line_ids = list_existing_shopify_line_item_ids(line_item_ids)
    assignment_snapshot = get_order_line_assignment_snapshot(line_item_ids)
    imported_orders = sum(
        1 for order in fetched_orders if str(order.get("shopify_order_id") or "").strip() not in existing_order_ids
    )
    new_lines_imported = sum(1 for line_id in line_item_ids if line_id not in existing_line_ids)
    existing_lines_preserved = max(len(line_item_ids) - new_lines_imported, 0)

    product_state_cache = {}
    with connect() as conn:
        with conn.cursor() as cur:
            for order in sorted(fetched_orders, key=order_allocation_sort_key):
                should_assign_editions = True
                order_datetime = _order_effective_datetime(order)
                if order_datetime and tracking_start and order_datetime < tracking_start:
                    should_assign_editions = False
                    historical_orders_skipped += 1
                for line_index, line_item in enumerate(order.get("line_items") or [], start=1):
                    if not isinstance(line_item, dict):
                        line_item = {}
                    quantity = max(1, int(line_item.get("quantity") or 1))
                    line_item_id = str(
                        line_item.get("shopify_line_item_id")
                        or f"{order.get('shopify_order_id') or 'order'}:line:{line_index}"
                    )
                    snapshot = assignment_snapshot.get(line_item_id) or {}
                    existing_indexes = {
                        int(item.get("allocation_index") or 0)
                        for item in (snapshot.get("assignments") or [])
                        if int(item.get("allocation_index") or 0) > 0
                    }
                    if not should_assign_editions:
                        historical_lines_skipped += max(quantity - len(existing_indexes), 0)
                        existing_assignments_preserved += len(existing_indexes)
                        continue
                    product_state = _preview_product_counter_state(cur, line_item, product_state_cache)
                    handle = str(product_state.get("handle") or line_item.get("product_handle") or "").strip()
                    if not handle:
                        missing_mapping_skipped += max(quantity - len(existing_indexes), 0)
                        existing_assignments_preserved += len(existing_indexes)
                        continue
                    for allocation_index in range(1, quantity + 1):
                        if allocation_index in existing_indexes:
                            existing_assignments_preserved += 1
                            continue
                        next_number = int(product_state.get("next_edition_number") or 1)
                        edition_total = int(product_state.get("edition_total") or 100)
                        is_sold_out = (
                            product_state.get("run_status") == SOLD_OUT_RUN_STATUS
                            or bool(product_state.get("sold_out"))
                            or next_number > edition_total
                        )
                        if is_sold_out:
                            sold_out_skipped += 1
                            continue
                        assignments += 1
                        product_state["next_edition_number"] = next_number + 1

    existing_orders_skipped = max(seen - imported_orders, 0)
    return {
        "mode": "dry_run",
        "orders_seen": seen,
        "shopify_orders_fetched": seen,
        "pages_fetched": pages_fetched,
        "existing_orders_skipped": existing_orders_skipped,
        "new_orders_inserted": imported_orders,
        "new_lines_inserted": new_lines_imported,
        "existing_lines_preserved": existing_lines_preserved,
        "edition_allocations_created": assignments,
        "existing_allocations_preserved": existing_assignments_preserved,
        "missing_mapping_skipped": missing_mapping_skipped,
        "historical_orders_skipped": historical_orders_skipped,
        "historical_lines_skipped": historical_lines_skipped,
        "sold_out_skipped": sold_out_skipped,
        "sync_from": _datetime_to_setting(sync_from) if sync_from else "",
        "bootstrap_recent_orders": bootstrap_recent_orders,
        "fetch_duration_ms": int((time.perf_counter() - total_started) * 1000),
        "errors": errors[:10],
    }


def preview_latest_paid_orders_sync(
    config=None,
    *,
    limit=DEFAULT_LATEST_PAID_ORDER_FETCH_LIMIT,
    lookback_days=DEFAULT_LATEST_PAID_ORDER_LOOKBACK_DAYS,
    backfill_latest_paid=False,
):
    total_started = time.perf_counter()
    schema_started = time.perf_counter()
    ensure_schema()
    _sync_perf_log("schema guard", schema_started, mode="preview_latest_paid")
    config = config or shopify_sync.get_config()
    state_started = time.perf_counter()
    state = get_sync_state()
    _sync_perf_log("sync state read", state_started, mode="preview_latest_paid")
    tracking_start = _parse_datetime(state.get("edition_tracking_start_at"))
    if not tracking_start:
        tracking_start = ensure_edition_tracking_start()
    payload = _latest_paid_orders_payload(
        config,
        limit=limit,
        lookback_days=lookback_days,
        backfill_latest_paid=backfill_latest_paid,
    )
    analyze_started = time.perf_counter()
    result = _analyze_fetched_orders_for_preview(
        payload.get("orders") or [],
        tracking_start=tracking_start,
        mode_label="latest_paid_dry_run",
        respect_tracking_start=False,
    )
    _sync_perf_log(
        "preview analysis",
        analyze_started,
        orders=result.get("shopify_orders_fetched"),
        new_orders=result.get("new_orders_inserted"),
        existing_orders=result.get("existing_orders_skipped"),
        allocations=result.get("edition_allocations_created"),
    )
    result["query"] = payload.get("query") or ""
    result["lookback_days"] = payload.get("lookback_days") or lookback_days
    result["limit"] = payload.get("limit") or limit
    result["query_mode"] = payload.get("query_mode") or ""
    result["backfill_latest_paid"] = bool(payload.get("backfill_latest_paid"))
    result["pages_fetched"] = payload.get("pages_fetched") or 0
    result["line_items_fetched"] = payload.get("line_items_fetched") or 0
    result["metafields_fetched"] = payload.get("metafields_fetched") or 0
    result["fetch_duration_ms"] = int((time.perf_counter() - total_started) * 1000)
    _sync_perf_log("preview total sync time", total_started, orders=result.get("shopify_orders_fetched"))
    return result


def sync_latest_paid_orders_to_supabase(
    config=None,
    *,
    limit=DEFAULT_LATEST_PAID_ORDER_FETCH_LIMIT,
    lookback_days=DEFAULT_LATEST_PAID_ORDER_LOOKBACK_DAYS,
    backfill_latest_paid=False,
):
    total_started = time.perf_counter()
    schema_started = time.perf_counter()
    ensure_schema()
    _sync_perf_log("schema guard", schema_started, mode="latest_paid_sync")
    config = config or shopify_sync.get_config()
    run_started = time.perf_counter()
    run_id = start_sync_run("shopify_orders_latest_paid")
    _sync_perf_log("sync run start write", run_started, mode="latest_paid_sync")
    shopify_fetch_started = time.perf_counter()
    payload = _latest_paid_orders_payload(
        config,
        limit=limit,
        lookback_days=lookback_days,
        backfill_latest_paid=backfill_latest_paid,
    )
    shopify_fetch_ms = int((time.perf_counter() - shopify_fetch_started) * 1000)
    fetched_orders = payload.get("orders") or []
    seen = len(fetched_orders)
    processed_orders = 0
    assignments = 0
    existing_skipped = 0
    missing_mapping_skipped = 0
    errors = []
    changed_handles = set()
    imported_orders = 0
    imported_lines = 0
    shopify_ms = shopify_fetch_ms
    db_write_started = time.perf_counter()
    line_items_fetched = int(payload.get("line_items_fetched") or _sync_order_line_count(fetched_orders))
    skipped_status_orders, skipped_status_lines = _paid_order_skip_counts(fetched_orders)
    newest_processed_cursor = _newest_shopify_order_cursor(fetched_orders)
    newest_processed_cursor_text = _datetime_to_setting(newest_processed_cursor) if newest_processed_cursor else ""
    cursor_updated = False
    cursor_update_reason = ""

    try:
        attempt_started = time.perf_counter()
        _set_sync_attempt(LAST_ATTEMPTED_ORDER_SYNC_KEY)
        set_app_setting(LAST_ORDER_FETCH_STATUS_KEY, "Running")
        _sync_perf_log("sync state write", attempt_started, mode="latest_paid_sync")
        order_ids = [order.get("shopify_order_id") for order in fetched_orders]
        line_item_ids = [
            str(line_item.get("shopify_line_item_id") or "").strip()
            for order in fetched_orders
            for line_item in (order.get("line_items") or [])
            if str(line_item.get("shopify_line_item_id") or "").strip()
        ]
        existing_lookup_started = time.perf_counter()
        existing_order_ids = list_existing_shopify_order_ids(order_ids)
        _sync_perf_log(
            "Supabase existing-order lookup time",
            existing_lookup_started,
            orders_checked=len(order_ids),
            existing_orders=len(existing_order_ids),
        )
        line_lookup_started = time.perf_counter()
        existing_line_item_ids = list_existing_shopify_line_item_ids(line_item_ids)
        _sync_perf_log(
            "Supabase existing-line lookup time",
            line_lookup_started,
            line_items_checked=len(line_item_ids),
            existing_lines=len(existing_line_item_ids),
        )
        state_lookup_started = time.perf_counter()
        existing_order_states = list_existing_shopify_order_states(order_ids)
        _sync_perf_log(
            "Supabase existing-order state lookup time",
            state_lookup_started,
            orders_checked=len(order_ids),
            states=len(existing_order_states),
        )
        imported_orders = sum(
            1 for order in fetched_orders if str(order.get("shopify_order_id") or "").strip() not in existing_order_ids
        )
        imported_lines = sum(1 for line_id in line_item_ids if line_id not in existing_line_item_ids)
        existing_orders_preserved = sum(
            1 for order in fetched_orders if str(order.get("shopify_order_id") or "").strip() in existing_order_ids
        )
        existing_lines_preserved = max(len(line_item_ids) - imported_lines, 0)
        filter_started = time.perf_counter()
        candidate_orders = [
            order
            for order in fetched_orders
            if _latest_paid_order_needs_sync(order, existing_order_ids, existing_line_item_ids, existing_order_states)
        ]
        _sync_perf_log(
            "existing-order skip filter",
            filter_started,
            fetched_orders=seen,
            candidate_orders=len(candidate_orders),
            imported_orders=imported_orders,
            imported_lines=imported_lines,
            existing_orders=existing_orders_preserved,
            existing_lines=existing_lines_preserved,
        )
        known_repair_candidates = {
            str(order.get("order_name") or "").strip()
            for order in candidate_orders
            if str(order.get("order_name") or "").strip()
        }
        known_repair_started = time.perf_counter()
        known_repair = (
            apply_known_missing_edition_repair()
            if known_repair_candidates
            and any(repair.get("order_name") in known_repair_candidates for repair in KNOWN_MISSING_EDITION_REPAIRS)
            else {"applied_rows": 0, "already_exists_consistent": 0, "errors": []}
        )
        _sync_perf_log(
            "known missing-edition repair time",
            known_repair_started,
            candidates=len(known_repair_candidates),
            applied=known_repair.get("applied_rows") or 0,
            already_consistent=known_repair.get("already_exists_consistent") or 0,
        )
        known_applied = int(known_repair.get("applied_rows") or 0)
        known_consistent = int(known_repair.get("already_exists_consistent") or 0)
        if known_repair.get("errors"):
            errors.extend(known_repair.get("errors") or [])

        allocation_started = time.perf_counter()
        for order in sorted(candidate_orders, key=order_allocation_sort_key):
            result = process_shopify_order_for_editions(
                order,
                allocation_status="assigned",
                fetch_missing_products=False,
                generate_certificates=False,
                sync_product_metafields=False,
                assign_editions=True,
            )
            processed_orders += 1
            assignments += int(result.get("assignments_created") or 0)
            existing_skipped += int(result.get("existing_assignments_skipped") or 0)
            missing_mapping_skipped += int(result.get("missing_mapping_skipped") or 0)
            changed_handles.update(result.get("changed_handles") or [])
            errors.extend(result.get("errors") or [])
        allocation_elapsed_ms = (time.perf_counter() - allocation_started) * 1000
        _sync_perf_log(
            "edition allocation time",
            None,
            elapsed_ms=int(allocation_elapsed_ms),
            candidate_orders=len(candidate_orders),
            processed_orders=processed_orders,
            assignments=assignments,
            existing_assignments=existing_skipped,
        )

        assignments += known_applied
        existing_skipped += known_consistent
        state_success_started = time.perf_counter()
        if backfill_latest_paid:
            success_timestamp = ""
            cursor_update_reason = "Backfill mode does not advance the normal sync cursor."
        elif newest_processed_cursor:
            success_timestamp = _set_sync_success_at(LAST_SUCCESSFUL_ORDER_SYNC_KEY, newest_processed_cursor)
            cursor_updated = True
            cursor_update_reason = (
                "Cursor advanced to newest successfully fetched Shopify order updated_at."
            )
        else:
            success_timestamp = ""
            cursor_update_reason = (
                payload.get("empty_fetch_reason")
                or "No Shopify orders were fetched, so the cursor was left unchanged."
            )
        status = "No New Orders" if seen == 0 and known_applied == 0 else ("Success With Warnings" if errors else "Success")
        duration_ms = int((time.perf_counter() - total_started) * 1000)
        _record_order_fetch_metrics(
            status=status,
            duration_ms=duration_ms,
            imported_count=imported_orders,
            assignments_created=assignments,
            success_timestamp=success_timestamp,
        )
        _sync_perf_log("sync state success/metrics write", state_success_started, status=status)
        run_finish_started = time.perf_counter()
        finish_sync_run(run_id, "Complete" if not errors else "Complete With Warnings", seen, processed_orders)
        _sync_perf_log("sync run finish write", run_finish_started, status="Complete" if not errors else "Complete_With_Warnings")
        _sync_perf_log(
            "Shopify metafield mirror/update time",
            None,
            elapsed_ms=0,
            product_metafields_deferred=len(changed_handles),
            order_metafields_updated=0,
        )
        _log_order_fetch_timing(
            total_ms=duration_ms,
            shopify_ms=shopify_ms,
            pages=payload.get("pages_fetched") or (1 if seen else 0),
            orders=seen,
            db_load_ms=0,
            assign_ms=allocation_elapsed_ms,
            db_write_ms=(time.perf_counter() - db_write_started) * 1000,
        )
        return {
            "mode": "latest_paid_sync",
            "orders_seen": seen,
            "shopify_orders_fetched": seen,
            "orders_processed": processed_orders,
            "orders_inserted_or_updated": processed_orders,
            "orders_imported": imported_orders,
            "existing_orders_skipped": existing_orders_preserved,
            "new_orders_inserted": imported_orders,
            "new_lines_inserted": imported_lines,
            "existing_lines_skipped": existing_lines_preserved,
            "lines_already_existing": existing_lines_preserved,
            "supabase_rows_inserted": imported_orders + imported_lines,
            "assignments_created": assignments,
            "edition_allocations_created": assignments,
            "existing_assignments_skipped": existing_skipped,
            "existing_allocations_preserved": existing_skipped,
            "known_missing_repairs_applied": known_applied,
            "known_missing_repairs_already_consistent": known_consistent,
            "missing_mapping_skipped": missing_mapping_skipped,
            "generated_certificates": 0,
            "certificates_deferred": assignments,
            "product_metafields_deferred": len(changed_handles),
            "query": payload.get("query") or "",
            "query_parameters": payload.get("query_parameters") or {},
            "query_mode": payload.get("query_mode") or "",
            "backfill_latest_paid": bool(payload.get("backfill_latest_paid")),
            "lookback_days": payload.get("lookback_days") or lookback_days,
            "limit": payload.get("limit") or limit,
            "sync_from": payload.get("sync_from") or "",
            "cursor_source": payload.get("cursor_source") or "",
            "cursor_raw": payload.get("cursor_raw") or "",
            "cursor_timezone": payload.get("cursor_timezone") or "UTC",
            "cursor_warning": payload.get("cursor_warning") or "",
            "cursor_ignored": bool(payload.get("cursor_ignored")),
            "cursor_updated": cursor_updated,
            "cursor_update_reason": cursor_update_reason,
            "newest_shopify_updated_at_processed": newest_processed_cursor_text,
            "empty_fetch_reason": payload.get("empty_fetch_reason") or "",
            "pages_fetched": payload.get("pages_fetched") or (1 if seen else 0),
            "line_items_fetched": line_items_fetched,
            "metafields_fetched": payload.get("metafields_fetched") or _sync_order_metafield_count(fetched_orders),
            "skipped_unpaid_cancelled_refunded_orders": skipped_status_orders,
            "skipped_unpaid_cancelled_refunded_lines": skipped_status_lines,
            "fetch_duration_ms": duration_ms,
            "last_order_fetch_status": status,
            "errors": errors[:10],
        }
    except Exception as error:
        duration_ms = int((time.perf_counter() - total_started) * 1000)
        _record_order_fetch_metrics(
            status="Failed",
            duration_ms=duration_ms,
            imported_count=imported_orders,
            assignments_created=assignments,
            success_timestamp="",
        )
        finish_sync_run(run_id, "Failed", seen, processed_orders, "Latest paid Shopify order sync failed.")
        log_app_error("latest_paid_order_sync_failed", str(error), {"records_seen": seen})
        raise


def backfill_missing_shopify_order_details(config=None, *, limit=100, dry_run=True):
    ensure_schema()
    config = config or shopify_sync.get_config()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    o.shopify_order_id,
                    o.order_name,
                    COALESCE(NULLIF(o.customer_email, ''), '') AS customer_email,
                    COALESCE(NULLIF(o.raw_json->>'shipping_address_summary', ''), '') AS shipping_address_summary,
                    COUNT(*) FILTER (WHERE COALESCE(NULLIF(li.variant_title, ''), '') = '') AS missing_variant_rows,
                    COUNT(*) FILTER (WHERE COALESCE(NULLIF(li.product_title, ''), '') = '') AS missing_product_rows
                FROM shopify_orders o
                LEFT JOIN shopify_order_lines li ON li.shopify_order_id = o.shopify_order_id
                WHERE COALESCE(NULLIF(o.customer_email, ''), '') = ''
                   OR COALESCE(NULLIF(o.raw_json->>'shipping_address_summary', ''), '') = ''
                   OR EXISTS (
                       SELECT 1
                       FROM shopify_order_lines li2
                       WHERE li2.shopify_order_id = o.shopify_order_id
                         AND COALESCE(NULLIF(li2.variant_title, ''), '') = ''
                   )
                GROUP BY o.shopify_order_id, o.order_name, o.customer_email, o.raw_json->>'shipping_address_summary'
                ORDER BY COALESCE(o.processed_at, o.created_at, o.synced_at) DESC NULLS LAST, o.order_name DESC
                LIMIT %s
                """,
                (max(int(limit or 100), 1),),
            )
            candidate_rows = cur.fetchall()
    if not candidate_rows:
        return {
            "mode": "dry_run" if dry_run else "apply",
            "candidate_orders": 0,
            "orders_fetched": 0,
            "orders_updated": 0,
            "variant_rows_filled": 0,
            "shipping_rows_filled": 0,
            "email_rows_filled": 0,
            "errors": [],
        }

    by_order_id = {str(row.get("shopify_order_id") or ""): row for row in candidate_rows}
    fetched_orders = shopify_sync.fetch_orders_by_ids(by_order_id.keys(), config=config)
    updates = []
    for order in fetched_orders:
        order_id = str(order.get("shopify_order_id") or "").strip()
        existing = by_order_id.get(order_id) or {}
        shipping_summary = str(order.get("shipping_address_summary") or "").strip()
        variant_rows_filled = (
            sum(
                1
                for line_item in order.get("line_items") or []
                if str(line_item.get("variant_title") or "").strip()
            )
            if int(existing.get("missing_variant_rows") or 0) > 0
            else 0
        )
        email_filled = int(
            bool(str(order.get("customer_email") or "").strip() and not str(existing.get("customer_email") or "").strip())
        )
        shipping_filled = int(bool(shipping_summary and not str(existing.get("shipping_address_summary") or "").strip()))
        if not any((variant_rows_filled, email_filled, shipping_filled)):
            continue
        updates.append(
            {
                "shopify_order_id": order_id,
                "order_name": str(order.get("order_name") or existing.get("order_name") or ""),
                "variant_rows_filled": variant_rows_filled,
                "email_filled": email_filled,
                "shipping_filled": shipping_filled,
                "order": order,
                "old_value": {
                    "customer_email": existing.get("customer_email") or "",
                    "shipping_address_summary": existing.get("shipping_address_summary") or "",
                    "missing_variant_rows": int(existing.get("missing_variant_rows") or 0),
                },
                "new_value": {
                    "customer_email": order.get("customer_email") or "",
                    "shipping_address_summary": shipping_summary,
                    "line_items": [
                        {
                            "shopify_line_item_id": item.get("shopify_line_item_id") or "",
                            "variant_title": item.get("variant_title") or "",
                        }
                        for item in (order.get("line_items") or [])
                    ],
                },
            }
        )

    if not dry_run:
        for update in updates:
            _persist_order_snapshot(update["order"])
            with connect() as conn:
                with conn.cursor() as cur:
                    _insert_audit_log(
                        cur,
                        event_type="shopify_order_details_backfill",
                        entity_type="shopify_order",
                        entity_id=update["shopify_order_id"],
                        shopify_order_id=update["shopify_order_id"],
                        old_value=update["old_value"],
                        new_value=update["new_value"],
                        reason="Filled missing Shopify order fulfilment details from live Shopify order data.",
                        actor="sports_cave_os_sync",
                        source="shopify_backfill",
                    )
                conn.commit()

    return {
        "mode": "dry_run" if dry_run else "apply",
        "candidate_orders": len(candidate_rows),
        "orders_fetched": len(fetched_orders),
        "orders_updated": len(updates),
        "variant_rows_filled": sum(item["variant_rows_filled"] for item in updates),
        "shipping_rows_filled": sum(item["shipping_filled"] for item in updates),
        "email_rows_filled": sum(item["email_filled"] for item in updates),
        "errors": [],
    }


def _name_from_address(address):
    if not isinstance(address, dict):
        return ""
    full = " ".join(part for part in (address.get("first_name"), address.get("last_name")) if part).strip()
    return address.get("name") or full


def normalize_rest_order(payload):
    customer = payload.get("customer") or {}
    shipping = payload.get("shipping_address") or {}
    billing = payload.get("billing_address") or {}
    shipping_lines = payload.get("shipping_lines") or []
    primary_shipping = shipping_lines[0] if shipping_lines and isinstance(shipping_lines[0], dict) else {}
    customer_full_name = " ".join(
        part for part in (customer.get("first_name"), customer.get("last_name")) if part
    ).strip()
    customer_email = customer.get("email") or payload.get("email") or ""
    customer_name = (
        customer.get("name")
        or customer_full_name
        or _name_from_address(shipping)
        or _name_from_address(billing)
        or customer_email
        or "Customer not shown"
    )
    store_domain = shopify_sync.get_config().get("store_domain", "")
    legacy_order_id = str(payload.get("id") or "")
    line_items = []
    for item in payload.get("line_items") or []:
        product_id = item.get("product_id")
        variant_id = item.get("variant_id")
        properties = item.get("properties") or []
        line_items.append(
            {
                "shopify_line_item_id": str(item.get("id") or ""),
                "shopify_product_id": _shopify_gid("Product", product_id) if product_id else "",
                "shopify_variant_id": _shopify_gid("ProductVariant", variant_id) if variant_id else "",
                "variant_id": _shopify_gid("ProductVariant", variant_id) if variant_id else "",
                "product_title": item.get("title") or item.get("name") or "",
                "product_handle": "",
                "variant_title": item.get("variant_title") or item.get("variant") or "",
                "sku": item.get("sku") or "",
                "quantity": int(item.get("quantity") or 1),
                "custom_attributes": properties,
                "properties": properties,
                "note_attributes": properties,
            }
        )
    return {
        "shopify_order_id": _shopify_gid("Order", legacy_order_id),
        "legacy_resource_id": legacy_order_id,
        "order_name": payload.get("name") or f"#{payload.get('order_number') or legacy_order_id}",
        "order_number": str(payload.get("order_number") or "").lstrip("#"),
        "admin_url": shopify_sync.build_order_admin_url(store_domain, legacy_order_id),
        "customer_id": _shopify_gid("Customer", customer.get("id")) if customer.get("id") else customer_email,
        "customer_name": customer_name,
        "customer_email": customer_email,
        "financial_status": str(payload.get("financial_status") or "").upper(),
        "fulfillment_status": str(payload.get("fulfillment_status") or "UNFULFILLED").upper(),
        "shipping_title": primary_shipping.get("title") or primary_shipping.get("code") or "",
        "shipping_method": primary_shipping.get("title") or primary_shipping.get("code") or "",
        "shipping_lines": shipping_lines,
        "total_price": str(payload.get("total_price") or ""),
        "currency": payload.get("currency") or "",
        "created_at": payload.get("created_at") or "",
        "remote_updated_at": payload.get("updated_at") or "",
        "processed_at": payload.get("processed_at") or "",
        "cancelled_at": payload.get("cancelled_at") or "",
        "note": payload.get("note") or "",
        "custom_attributes": payload.get("note_attributes") or [],
        "note_attributes": payload.get("note_attributes") or [],
        "line_items": line_items,
        "raw_payload": payload,
        "customer_raw": customer,
    }


def process_order_paid_webhook(payload, webhook_id, topic="orders/paid"):
    ensure_schema()
    if not webhook_id:
        webhook_id = f"missing-id-{utc_now()}"
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO webhook_events(webhook_id, topic, status, payload, received_at)
                VALUES (%s, %s, 'Received', %s::jsonb, now())
                ON CONFLICT (webhook_id) DO NOTHING
                RETURNING webhook_id
                """,
                (webhook_id, topic, json_dumps(payload)),
            )
            inserted = cur.fetchone()
        conn.commit()
    if not inserted:
        return {"duplicate": True, "assignments_created": 0}
    try:
        result = process_shopify_order_for_editions(normalize_rest_order(payload))
        status = "Processed" if not result.get("errors") else "Processed With Warnings"
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE webhook_events SET status=%s, error_message=%s WHERE webhook_id=%s",
                    (status, "\n".join(result.get("errors") or []), webhook_id),
                )
            conn.commit()
        return {"duplicate": False, **result}
    except Exception as error:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE webhook_events SET status='Failed', error_message=%s WHERE webhook_id=%s",
                    (str(error), webhook_id),
                )
            conn.commit()
        log_app_error("webhook_order_processing_failed", str(error), {"webhook_id": webhook_id})
        raise


def _normalize_cached_order_snapshot(raw_value):
    payload = raw_value
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            return None
    if not isinstance(payload, dict):
        return None
    if payload.get("shopify_order_id") and isinstance(payload.get("line_items"), list):
        return payload
    if payload.get("id") and isinstance(payload.get("line_items"), list):
        return normalize_rest_order(payload)
    return None


def reprocess_cached_problem_orders(
    *,
    limit=150,
    statuses=None,
    generate_certificates=False,
    sync_product_metafields=False,
    respect_tracking_start=True,
):
    ensure_schema()
    selected_statuses = tuple(statuses or REPAIRABLE_ORDER_LINE_STATUSES)
    if not selected_statuses or int(limit or 0) <= 0:
        return {
            "orders_reprocessed": 0,
            "assignments_created": 0,
            "existing_assignments_skipped": 0,
            "generated_certificates": 0,
            "historical_lines_marked": 0,
            "skipped_missing_snapshot": 0,
            "errors": [],
        }

    placeholders = ", ".join(["%s"] * len(selected_statuses))
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT o.shopify_order_id, o.raw_json
                FROM shopify_orders o
                WHERE EXISTS (
                    SELECT 1
                    FROM shopify_order_lines li
                    WHERE li.shopify_order_id=o.shopify_order_id
                      AND COALESCE(li.assignment_status, '') IN ({placeholders})
                )
                ORDER BY COALESCE(o.remote_updated_at, o.created_at, o.synced_at) DESC NULLS LAST, o.order_name DESC
                LIMIT %s
                """,
                (*selected_statuses, int(limit)),
            )
            snapshots = cur.fetchall()

    tracking_start = ensure_edition_tracking_start()
    processed_orders = 0
    assignments_created = 0
    existing_assignments_skipped = 0
    generated_certificates = 0
    historical_lines_marked = 0
    skipped_missing_snapshot = 0
    errors = []
    normalized_snapshots = []

    for row in snapshots:
        order = _normalize_cached_order_snapshot(row.get("raw_json"))
        if not order:
            skipped_missing_snapshot += 1
            errors.append(
                f"Skipped cached repair for {row.get('shopify_order_id') or 'unknown order'} because no reusable order snapshot was stored."
            )
            continue
        normalized_snapshots.append((row, order))

    for row, order in sorted(normalized_snapshots, key=lambda item: order_allocation_sort_key(item[1])):
        should_assign_editions = True
        allocation_skip_reason = ""
        order_datetime = _order_effective_datetime(order)
        if respect_tracking_start and order_datetime and tracking_start and order_datetime < tracking_start:
            should_assign_editions = False
            allocation_skip_reason = HISTORICAL_ORDER_NOTE
        result = process_paid_order(
            order,
            generate_certificates=generate_certificates,
            sync_product_metafields=sync_product_metafields,
            assign_editions=should_assign_editions,
            allocation_skip_reason=allocation_skip_reason,
        )
        processed_orders += 1
        assignments_created += int(result.get("assignments_created") or 0)
        existing_assignments_skipped += int(result.get("existing_assignments_skipped") or 0)
        generated_certificates += int(result.get("generated_certificates") or 0)
        historical_lines_marked += int(result.get("historical_lines_marked") or 0)
        errors.extend(result.get("errors") or [])

    return {
        "orders_reprocessed": processed_orders,
        "assignments_created": assignments_created,
        "existing_assignments_skipped": existing_assignments_skipped,
        "generated_certificates": generated_certificates,
        "historical_lines_marked": historical_lines_marked,
        "skipped_missing_snapshot": skipped_missing_snapshot,
        "errors": errors[:10],
    }


def _missing_edition_candidate_rows(limit=100, statuses=None):
    ensure_schema()
    selected_statuses = tuple(statuses or MISSING_EDITION_REPAIRABLE_STATUSES)
    if not selected_statuses:
        return []
    placeholders = ", ".join(["%s"] * len(selected_statuses))
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    o.shopify_order_id,
                    o.order_name,
                    COALESCE(o.processed_at, o.created_at, o.synced_at) AS order_date,
                    COALESCE(o.customer_name, '') AS customer_name,
                    li.shopify_line_item_id,
                    li.shopify_handle,
                    li.shopify_product_id,
                    li.product_title,
                    li.variant_title,
                    li.quantity,
                    li.assignment_status,
                    li.last_error
                FROM shopify_order_lines li
                JOIN shopify_orders o ON o.shopify_order_id = li.shopify_order_id
                LEFT JOIN edition_orders eo ON eo.shopify_line_item_id = li.shopify_line_item_id
                WHERE eo.id IS NULL
                  AND COALESCE(li.assignment_status, '') IN ({placeholders})
                ORDER BY COALESCE(o.created_at, o.processed_at, o.synced_at) ASC NULLS LAST,
                         COALESCE(o.processed_at, o.created_at, o.synced_at) ASC NULLS LAST,
                         o.order_name ASC,
                         li.shopify_line_item_id ASC
                LIMIT %s
                """,
                (*selected_statuses, max(int(limit or 100), 1)),
            )
            return cur.fetchall()


def preview_missing_edition_repairs(limit=100, statuses=None):
    candidate_rows = _missing_edition_candidate_rows(limit=limit, statuses=statuses)
    preview_rows = []
    if candidate_rows:
        state_cache = {}
        with connect() as conn:
            with conn.cursor() as cur:
                for row in candidate_rows[:50]:
                    line_item = dict(row)
                    match = _resolve_edition_product_for_order_line_with_cursor(cur, line_item)
                    product = match.get("product") or {}
                    state = _preview_product_counter_state(cur, line_item, state_cache) if product else {}
                    proposed_number = _int_value(state.get("next_edition_number"), 0)
                    edition_total = _int_value(state.get("edition_total"), _int_value(product.get("edition_total"), 100))
                    preview_rows.append(
                        {
                            "order_name": str(row.get("order_name") or ""),
                            "date": str(row.get("order_date") or "")[:10],
                            "customer_name": str(row.get("customer_name") or ""),
                            "product_title": str(row.get("product_title") or ""),
                            "variant_title": str(row.get("variant_title") or ""),
                            "quantity": int(row.get("quantity") or 1),
                            "shopify_product_id": str(row.get("shopify_product_id") or ""),
                            "shopify_handle": str(row.get("shopify_handle") or ""),
                            "matched_handle": str(product.get("handle") or ""),
                            "match_status": str(match.get("status") or ""),
                            "match_reason": str(match.get("reason") or ""),
                            "proposed_edition": (
                                format_edition_display_number(proposed_number, edition_total)
                                if proposed_number
                                else ""
                            ),
                            "assignment_status": str(row.get("assignment_status") or ""),
                            "last_error": str(row.get("last_error") or ""),
                        }
                    )
    return {
        "mode": "dry_run",
        "candidate_rows": len(candidate_rows),
        "candidate_orders": len({str(row.get("shopify_order_id") or "") for row in candidate_rows}),
        "preview_rows": preview_rows[:50],
        "errors": [],
    }


def repair_missing_edition_orders(limit=100, statuses=None):
    result = reprocess_cached_problem_orders(
        limit=limit,
        statuses=statuses or MISSING_EDITION_REPAIRABLE_STATUSES,
        generate_certificates=False,
        sync_product_metafields=False,
        respect_tracking_start=False,
    )
    return {
        "mode": "apply",
        "candidate_rows": len(_missing_edition_candidate_rows(limit=limit, statuses=statuses)),
        "orders_reprocessed": int(result.get("orders_reprocessed") or 0),
        "edition_allocations_created": int(result.get("assignments_created") or 0),
        "existing_allocations_preserved": int(result.get("existing_assignments_skipped") or 0),
        "historical_lines_marked": int(result.get("historical_lines_marked") or 0),
        "skipped_missing_snapshot": int(result.get("skipped_missing_snapshot") or 0),
        "errors": result.get("errors") or [],
    }


def _known_repair_customer_key(value):
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _known_repair_order_key(value):
    return str(value or "").strip().casefold()


def _known_repair_target_key(target):
    return (
        _known_repair_order_key(target.get("order_name")),
        _known_repair_customer_key(target.get("customer_name")),
        _normalize_product_title_key(target.get("product_title")),
    )


def _known_repair_fetch_candidate_rows(cur):
    order_names = sorted({target["order_name"] for target in KNOWN_MISSING_EDITION_REPAIRS})
    placeholders = ", ".join(["%s"] * len(order_names))
    cur.execute(
        f"""
        SELECT
            o.shopify_order_id,
            o.order_name,
            COALESCE(o.processed_at, o.created_at, o.synced_at) AS order_date,
            COALESCE(o.customer_name, '') AS customer_name,
            COALESCE(o.customer_email, '') AS customer_email,
            li.shopify_line_item_id,
            li.shopify_product_id,
            li.shopify_handle,
            li.product_title,
            li.variant_title,
            li.sku,
            li.quantity,
            li.assignment_status,
            li.last_error,
            li.raw_json,
            eo.id AS edition_order_id,
            eo.edition_number AS existing_edition_number,
            eo.edition_total AS existing_edition_total
        FROM shopify_order_lines li
        JOIN shopify_orders o ON o.shopify_order_id = li.shopify_order_id
        LEFT JOIN edition_orders eo
          ON eo.shopify_line_item_id = li.shopify_line_item_id
         AND COALESCE(eo.allocation_index, 1) = 1
        WHERE o.order_name IN ({placeholders})
        ORDER BY COALESCE(o.processed_at, o.created_at, o.synced_at) ASC NULLS LAST,
                 o.order_name ASC,
                 li.shopify_line_item_id ASC
        """,
        tuple(order_names),
    )
    return [dict(row) for row in (cur.fetchall() or [])]


def _known_repair_conflict(cur, *, shopify_handle, edition_number, shopify_line_item_id):
    cur.execute(
        """
        SELECT id, shopify_order_id, shopify_order_name, shopify_line_item_id,
               allocation_index, shopify_handle, product_title, edition_number
        FROM edition_orders
        WHERE edition_number=%s
          AND COALESCE(shopify_handle, product_handle, '')=%s
          AND COALESCE(shopify_line_item_id, '') <> %s
        LIMIT 1
        """,
        (int(edition_number), str(shopify_handle or ""), str(shopify_line_item_id or "")),
    )
    return cur.fetchone()


def _known_repair_public_row(plan):
    target = plan["target"]
    row = plan.get("ledger_row") or {}
    product = plan.get("product") or {}
    conflict = plan.get("conflict") or {}
    return {
        "order_name": target.get("order_name"),
        "customer_name": target.get("customer_name"),
        "product_title": target.get("product_title"),
        "target_edition": f"#{int(target.get('edition_number') or 0):03d}/{int(target.get('edition_total') or 100)}",
        "current_edition": (
            f"#{int(row.get('existing_edition_number') or 0):03d}/{int(row.get('existing_edition_total') or target.get('edition_total') or 100)}"
            if _int_value(row.get("existing_edition_number"), 0)
            else ""
        ),
        "status": plan.get("status") or "",
        "reason": plan.get("reason") or "",
        "shopify_order_id": row.get("shopify_order_id") or "",
        "shopify_line_item_id": row.get("shopify_line_item_id") or "",
        "matched_handle": product.get("handle") or row.get("shopify_handle") or "",
        "conflict_order": conflict.get("shopify_order_name") or conflict.get("shopify_order_id") or "",
    }


def _known_missing_edition_repair_plan():
    ensure_schema()
    target_by_key = {_known_repair_target_key(target): target for target in KNOWN_MISSING_EDITION_REPAIRS}
    with connect() as conn:
        with conn.cursor() as cur:
            rows = _known_repair_fetch_candidate_rows(cur)
            rows_by_key = {}
            for row in rows:
                key = (
                    _known_repair_order_key(row.get("order_name")),
                    _known_repair_customer_key(row.get("customer_name")),
                    _normalize_product_title_key(row.get("product_title")),
                )
                rows_by_key.setdefault(key, []).append(row)

            plans = []
            for key, target in target_by_key.items():
                matches = rows_by_key.get(key) or []
                plan = {"target": target, "status": "ready", "reason": "", "ledger_row": {}, "product": {}, "conflict": {}}
                if not matches:
                    plan.update(status="missing_order_line", reason="No matching Shopify mirror line was found in Supabase.")
                    plans.append(plan)
                    continue
                if len(matches) > 1:
                    plan.update(status="manual_review_ambiguous_match", reason="More than one order line matched this repair target.")
                    plan["ledger_row"] = matches[0]
                    plans.append(plan)
                    continue

                row = matches[0]
                plan["ledger_row"] = row
                existing_number = _int_value(row.get("existing_edition_number"), 0)
                target_number = _int_value(target.get("edition_number"), 0)
                if existing_number:
                    if existing_number == target_number:
                        plan.update(status="already_assigned_correct", reason="The target edition is already assigned.")
                    else:
                        plan.update(
                            status="blocked_existing_edition",
                            reason=f"Existing edition #{existing_number:03d} is already assigned and will not be overwritten.",
                        )
                    plans.append(plan)
                    continue

                if not row.get("shopify_line_item_id") or not row.get("shopify_order_id"):
                    plan.update(status="missing_identifier", reason="Missing Shopify order or line item identifier.")
                    plans.append(plan)
                    continue

                lookup_line = {
                    **row,
                    "product_handle": row.get("shopify_handle") or "",
                    "variant_id": "",
                }
                lookup_result = _resolve_edition_product_for_order_line_with_cursor(cur, lookup_line)
                product = lookup_result.get("product") or {}
                plan["product"] = product
                handle = product.get("handle") or ""
                if not handle:
                    plan.update(
                        status="missing_mapping",
                        reason=lookup_result.get("reason") or "Could not confidently match the line to an edition product.",
                    )
                    plans.append(plan)
                    continue

                conflict = _known_repair_conflict(
                    cur,
                    shopify_handle=handle,
                    edition_number=target_number,
                    shopify_line_item_id=row.get("shopify_line_item_id"),
                )
                if conflict:
                    plan["conflict"] = dict(conflict)
                    plan.update(
                        status="blocked_conflict",
                        reason=(
                            f"Edition #{target_number:03d} is already used by "
                            f"{conflict.get('shopify_order_name') or conflict.get('shopify_order_id')}."
                        ),
                    )
                plans.append(plan)

    return plans


def _known_repair_counter_snapshot(handles):
    clean_handles = sorted({str(handle or "").strip() for handle in handles if str(handle or "").strip()})
    if not clean_handles:
        return []
    placeholders = ", ".join(["%s"] * len(clean_handles))
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT shopify_handle, product_title, edition_total, next_edition_number,
                       last_assigned_edition, remaining_count, sold_out, updated_at
                FROM edition_products
                WHERE shopify_handle IN ({placeholders})
                ORDER BY product_title ASC
                """,
                tuple(clean_handles),
            )
            return cur.fetchall() or []


def preview_known_missing_edition_repair():
    plans = _known_missing_edition_repair_plan()
    public_rows = [_known_repair_public_row(plan) for plan in plans]
    return {
        "mode": "dry_run",
        "target_rows": len(KNOWN_MISSING_EDITION_REPAIRS),
        "ready_rows": sum(1 for plan in plans if plan.get("status") == "ready"),
        "already_assigned_correct": sum(1 for plan in plans if plan.get("status") == "already_assigned_correct"),
        "blocked_rows": sum(
            1
            for plan in plans
            if plan.get("status")
            not in {"ready", "already_assigned_correct"}
        ),
        "preview_rows": public_rows,
        "errors": [],
    }


def apply_known_missing_edition_repair():
    plans = _known_missing_edition_repair_plan()
    applied_rows = []
    skipped_rows = []
    errors = []
    changed_handles = set()

    for plan in plans:
        public_row = _known_repair_public_row(plan)
        if plan.get("status") != "ready":
            skipped_rows.append(public_row)
            continue

        target = plan["target"]
        row = plan["ledger_row"]
        product = plan.get("product") or {}
        handle = product.get("handle") or row.get("shopify_handle") or ""
        try:
            allocation = allocate_edition_for_order_line(
                shopify_order_id=row.get("shopify_order_id"),
                shopify_order_name=row.get("order_name"),
                shopify_line_item_id=row.get("shopify_line_item_id"),
                allocation_index=1,
                shopify_handle=handle,
                shopify_product_id=product.get("shopify_product_id") or row.get("shopify_product_id") or "",
                product_title=product.get("title") or row.get("product_title") or target.get("product_title") or "",
                variant_title=row.get("variant_title") or "",
                sku=row.get("sku") or "",
                customer_name=row.get("customer_name") or target.get("customer_name") or "",
                customer_email=row.get("customer_email") or "",
                allocation_status="assigned",
                promised_edition_number=target.get("edition_number"),
                promised_edition_total=target.get("edition_total"),
                assignment_source="known_missing_truth_20260625",
            )
            if allocation.get("error"):
                failed = {**public_row, "status": "error", "reason": allocation["error"]}
                errors.append(allocation["error"])
                skipped_rows.append(failed)
                continue
            assignment = allocation.get("assignment") or {}
            assigned_number = _int_value(assignment.get("edition_number"), 0)
            target_number = _int_value(target.get("edition_number"), 0)
            if assigned_number != target_number:
                message = (
                    f"Known repair for {target.get('order_name')} expected #{target_number:03d} "
                    f"but found #{assigned_number:03d}."
                )
                errors.append(message)
                skipped_rows.append({**public_row, "status": "error", "reason": message})
                continue
            with connect() as conn:
                with conn.cursor() as cur:
                    _set_order_line_status(
                        cur,
                        row.get("shopify_line_item_id"),
                        "Assigned",
                        shopify_product_id=product.get("shopify_product_id") or row.get("shopify_product_id") or "",
                        shopify_handle=handle,
                        product_title=product.get("title") or row.get("product_title") or target.get("product_title") or "",
                        variant_title=row.get("variant_title") or "",
                        sku=row.get("sku") or "",
                    )
                conn.commit()
            changed_handles.add(handle)
            applied_rows.append({**public_row, "status": "applied" if allocation.get("created") else "already_exists_consistent", "reason": ""})
        except Exception as error:
            message = str(error)
            errors.append(message)
            skipped_rows.append({**public_row, "status": "error", "reason": message})

    counter_updates = _known_repair_counter_snapshot(changed_handles)
    return {
        "mode": "apply",
        "target_rows": len(KNOWN_MISSING_EDITION_REPAIRS),
        "applied_rows": len([row for row in applied_rows if row.get("status") == "applied"]),
        "already_exists_consistent": len([row for row in applied_rows if row.get("status") == "already_exists_consistent"]),
        "skipped_rows": len(skipped_rows),
        "applied": applied_rows,
        "skipped": skipped_rows,
        "counter_updates": counter_updates,
        "errors": errors[:10],
    }


def sync_shopify_orders_to_supabase(
    config=None,
    *,
    query=None,
    max_orders=DEFAULT_INCREMENTAL_ORDER_FETCH_LIMIT,
    historical_backfill=False,
    days=365,
    generate_certificates=False,
    sync_product_metafields=False,
    respect_tracking_start=True,
):
    ensure_schema()
    config = config or shopify_sync.get_config()
    run_id = start_sync_run("shopify_orders_backfill" if historical_backfill else "shopify_orders_incremental")
    seen = 0
    processed_orders = 0
    historical_orders_synced = 0
    historical_lines_marked = 0
    assignments = 0
    existing_skipped = 0
    generated_certificates = 0
    missing_mapping_skipped = 0
    changed_handles = set()
    errors = []
    sync_from = None
    bootstrap_recent_orders = False
    imported_orders = 0
    imported_lines = 0
    pages_fetched = 0
    total_started = time.perf_counter()
    db_load_ms = 0.0
    shopify_ms = 0.0
    assign_ms = 0.0
    db_write_ms = 0.0
    fetched_orders = []
    try:
        _set_sync_attempt(LAST_ATTEMPTED_ORDER_SYNC_KEY)
        if not historical_backfill:
            set_app_setting(LAST_ORDER_FETCH_STATUS_KEY, "Running")
        db_phase_started = time.perf_counter()
        if historical_backfill:
            effective_query = query or "financial_status:paid"
            allocation_status = "backfilled"
            generate_certificates_now = False
            sync_product_metafields_now = False
            tracking_start = None
        else:
            state = get_sync_state()
            tracking_start = _parse_datetime(state.get("edition_tracking_start_at"))
            if not tracking_start:
                tracking_start = ensure_edition_tracking_start()
            last_success = _parse_datetime(
                state.get("last_successful_order_fetch_at") or state.get("last_successful_order_sync_at")
            )
            if not last_success and count_shopify_orders() == 0:
                bootstrap_recent_orders = True
                bootstrap_now = utc_now_datetime()
                sync_from = bootstrap_now - timedelta(days=DEFAULT_INITIAL_ORDER_BOOTSTRAP_DAYS)
                if not state.get("edition_tracking_start_at"):
                    tracking_start = bootstrap_now - timedelta(days=DEFAULT_INITIAL_ORDER_ASSIGNMENT_WINDOW_DAYS)
                    set_app_setting(EDITION_TRACKING_START_KEY, _datetime_to_setting(tracking_start))
            else:
                last_success = last_success or tracking_start
                sync_from = last_success - timedelta(
                    minutes=state.get("sync_lookback_buffer_minutes") or DEFAULT_SYNC_LOOKBACK_BUFFER_MINUTES
                )
            effective_query = query or (
                f"financial_status:paid fulfillment_status:unfulfilled "
                f"updated_at:>='{_datetime_to_shopify_query(sync_from)}'"
            )
            allocation_status = "assigned"
            generate_certificates_now = bool(generate_certificates)
            sync_product_metafields_now = bool(sync_product_metafields)
        db_load_ms = (time.perf_counter() - db_phase_started) * 1000

        sync_config = dict(config)
        sync_limit = max(int(max_orders or DEFAULT_INCREMENTAL_ORDER_FETCH_LIMIT), 1)
        sync_config["max_orders"] = sync_limit
        page_iterator = iter(
            shopify_sync.iter_order_pages(
            query=effective_query,
            days=days,
            max_orders=sync_limit,
            page_size=50,
            config=sync_config,
            )
        )
        while True:
            page_fetch_started = time.perf_counter()
            try:
                page = next(page_iterator)
            except StopIteration:
                break
            shopify_ms += (time.perf_counter() - page_fetch_started) * 1000
            pages_fetched += 1
            page_orders = page["orders"]
            existing_order_ids = list_existing_shopify_order_ids(
                order.get("shopify_order_id") for order in page_orders
            )
            page_line_item_ids = [
                str(line_item.get("shopify_line_item_id") or "").strip()
                for order in page_orders
                for line_item in (order.get("line_items") or [])
                if str(line_item.get("shopify_line_item_id") or "").strip()
            ]
            existing_line_item_ids = list_existing_shopify_line_item_ids(page_line_item_ids)
            imported_orders += sum(
                1 for order in page_orders if str(order.get("shopify_order_id") or "").strip() not in existing_order_ids
            )
            imported_lines += sum(1 for line_id in page_line_item_ids if line_id not in existing_line_item_ids)
            fetched_orders.extend(page_orders)
            seen += len(page_orders)
            del page
            gc.collect()

        page_processing_started = time.perf_counter()
        assign_before_batch = assign_ms
        for order in sorted(fetched_orders, key=order_allocation_sort_key):
            should_assign_editions = True
            allocation_skip_reason = ""
            if not historical_backfill and respect_tracking_start:
                order_datetime = _order_effective_datetime(order)
                if order_datetime and tracking_start and order_datetime < tracking_start:
                    should_assign_editions = False
                    allocation_skip_reason = HISTORICAL_ORDER_NOTE
            order_assign_started = time.perf_counter()
            result = process_shopify_order_for_editions(
                order,
                allocation_status=allocation_status,
                generate_certificates=generate_certificates_now,
                sync_product_metafields=sync_product_metafields_now,
                assign_editions=should_assign_editions,
                allocation_skip_reason=allocation_skip_reason,
            )
            assign_ms += (time.perf_counter() - order_assign_started) * 1000
            processed_orders += 1
            if not should_assign_editions:
                historical_orders_synced += 1
            assignments += int(result.get("assignments_created") or 0)
            existing_skipped += int(result.get("existing_assignments_skipped") or 0)
            missing_mapping_skipped += int(result.get("missing_mapping_skipped") or 0)
            generated_certificates += int(result.get("generated_certificates") or 0)
            historical_lines_marked += int(result.get("historical_lines_marked") or 0)
            changed_handles.update(result.get("changed_handles") or [])
            errors.extend(result.get("errors") or [])
        batch_processing_ms = (time.perf_counter() - page_processing_started) * 1000
        db_write_ms += max(batch_processing_ms - (assign_ms - assign_before_batch), 0)
        if not historical_backfill:
            success_timestamp = _set_sync_success(LAST_SUCCESSFUL_ORDER_SYNC_KEY)
            last_fetch_status = "No New Orders" if seen == 0 else ("Success With Warnings" if errors else "Success")
            _record_order_fetch_metrics(
                status=last_fetch_status,
                duration_ms=int((time.perf_counter() - total_started) * 1000),
                imported_count=imported_orders,
                assignments_created=assignments,
                success_timestamp=success_timestamp,
            )
        finish_sync_run(run_id, "Complete" if not errors else "Complete With Warnings", seen, processed_orders)
        _log_order_fetch_timing(
            total_ms=(time.perf_counter() - total_started) * 1000,
            shopify_ms=shopify_ms,
            pages=pages_fetched,
            orders=seen,
            db_load_ms=db_load_ms,
            assign_ms=assign_ms,
            db_write_ms=db_write_ms,
        )
        return {
            "orders_seen": seen,
            "shopify_orders_fetched": seen,
            "orders_processed": processed_orders,
            "orders_inserted_or_updated": processed_orders,
            "orders_imported": imported_orders,
            "existing_orders_skipped": max(seen - imported_orders, 0),
            "new_orders_inserted": imported_orders,
            "new_lines_inserted": imported_lines,
            "assignments_created": assignments,
            "edition_allocations_created": assignments,
            "existing_assignments_skipped": existing_skipped,
            "existing_allocations_preserved": existing_skipped,
            "missing_mapping_skipped": missing_mapping_skipped,
            "generated_certificates": generated_certificates,
            "certificates_deferred": max(assignments - generated_certificates, 0),
            "product_metafields_deferred": len(changed_handles) if not sync_product_metafields_now else 0,
            "historical_orders_synced": historical_orders_synced,
            "historical_lines_marked": historical_lines_marked,
            "skipped_historical": historical_orders_synced,
            "sync_from": _datetime_to_setting(sync_from) if sync_from else "",
            "bootstrap_recent_orders": bootstrap_recent_orders,
            "pages_fetched": pages_fetched,
            "fetch_duration_ms": int((time.perf_counter() - total_started) * 1000),
            "last_order_fetch_status": "No New Orders" if seen == 0 else ("Success With Warnings" if errors else "Success"),
            "mode": "historical_backfill" if historical_backfill else "incremental",
            "errors": errors[:10],
        }
    except Exception as error:
        if not historical_backfill:
            _record_order_fetch_metrics(
                status="Failed",
                duration_ms=int((time.perf_counter() - total_started) * 1000),
                imported_count=imported_orders,
                assignments_created=assignments,
                success_timestamp="",
            )
        _log_order_fetch_timing(
            total_ms=(time.perf_counter() - total_started) * 1000,
            shopify_ms=shopify_ms,
            pages=pages_fetched,
            orders=seen,
            db_load_ms=db_load_ms,
            assign_ms=assign_ms,
            db_write_ms=db_write_ms,
        )
        finish_sync_run(run_id, "Failed", seen, processed_orders, "Shopify order sync failed.")
        log_app_error("shopify_order_sync_failed", str(error), {"records_seen": seen})
        raise


def _order_sort_clause(sort):
    return {
        "Date newest": "COALESCE(created_at, synced_at) DESC NULLS LAST, order_name DESC",
        "Date oldest": "COALESCE(created_at, synced_at) ASC NULLS LAST, order_name ASC",
        "Shopify updated": "COALESCE(remote_updated_at, created_at, synced_at) DESC NULLS LAST, order_name DESC",
        "Customer": "customer_name ASC NULLS LAST, order_name ASC",
        "Edition number": "first_edition_number ASC NULLS LAST, order_name DESC",
    }.get(sort, "COALESCE(created_at, synced_at) DESC NULLS LAST, order_name DESC")


def list_hybrid_order_rows(limit=250):
    total_started = time.perf_counter()
    base_started = time.perf_counter()
    limit_value = max(min(int(limit or 250), 1000), 1)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    o.shopify_order_id,
                    o.order_name,
                    o.order_number,
                    o.admin_url,
                    o.customer_name,
                    o.customer_email,
                    o.financial_status,
                    o.fulfillment_status,
                    o.total_price,
                    o.currency,
                    o.created_at,
                    o.remote_updated_at,
                    o.processed_at,
                    o.cancelled_at,
                    o.synced_at,
                    o.raw_json AS order_raw_json,
                    li.id AS order_line_id,
                    li.shopify_line_item_id,
                    li.quantity,
                    li.assignment_status,
                    li.last_error,
                    li.shopify_handle,
                    li.shopify_product_id,
                    COALESCE(NULLIF(li.raw_json->>'shopify_variant_id', ''), NULLIF(li.raw_json->>'variant_id', ''), NULLIF(li.raw_json->'variant'->>'id', '')) AS shopify_variant_id,
                    COALESCE(NULLIF(li.product_title, ''), NULLIF(li.raw_json->>'product_title', ''), NULLIF(li.raw_json->>'title', '')) AS product_title,
                    COALESCE(NULLIF(li.variant_title, ''), NULLIF(li.raw_json->>'variant_title', ''), NULLIF(li.raw_json->>'variantTitle', ''), NULLIF(li.raw_json->'variant'->>'title', '')) AS variant_title,
                    li.sku,
                    COALESCE(pd.prodigi_status, '') AS prodigi_status,
                    COALESCE(pd.row_id, '') AS prodigi_row_id,
                    COALESCE(NULLIF(sp.featured_image_url, ''), NULLIF(sp.image_url, '')) AS image_url
                FROM shopify_orders o
                LEFT JOIN shopify_order_lines li ON li.shopify_order_id = o.shopify_order_id
                LEFT JOIN shopify_products sp ON sp.handle = li.shopify_handle
                LEFT JOIN LATERAL (
                    SELECT pd.row_id, pd.prodigi_status
                    FROM prodigi_dispatch_rows pd
                    WHERE pd.shopify_line_item_id = li.shopify_line_item_id
                    ORDER BY pd.updated_at DESC NULLS LAST, pd.submitted_at DESC NULLS LAST
                    LIMIT 1
                ) pd ON TRUE
                ORDER BY COALESCE(o.created_at, o.synced_at) DESC NULLS LAST,
                         o.order_name DESC,
                         li.id ASC NULLS LAST
                LIMIT %s
                """,
                (limit_value,),
            )
            base_rows = cur.fetchall()
            print(
                f"PERF Orders base rows load {(time.perf_counter() - base_started):.3f}s rows={len(base_rows)}",
                flush=True,
            )

            line_ids = [
                str(row.get("shopify_line_item_id") or "").strip()
                for row in base_rows
                if str(row.get("shopify_line_item_id") or "").strip()
            ]
            overlay_started = time.perf_counter()
            edition_rows = []
            if line_ids:
                cur.execute(
                    """
                    SELECT
                        eo.id AS edition_order_id,
                        eo.shopify_order_id,
                        eo.shopify_order_name,
                        eo.shopify_line_item_id,
                        eo.shopify_product_id,
                        eo.shopify_variant_id,
                        eo.shopify_handle,
                        eo.product_handle,
                        eo.product_title,
                        eo.variant_title,
                        eo.sku,
                        eo.customer_name,
                        eo.customer_email,
                        eo.edition_number,
                        eo.edition_total,
                        eo.allocation_index,
                        eo.assigned_at,
                        eo.certificate_status,
                        eo.status AS edition_order_status,
                        eo.source AS assignment_source,
                        eo.manual_override,
                        c.certificate_id,
                        c.local_file_path,
                        COALESCE(NULLIF(c.shopify_file_url, ''), NULLIF(c.certificate_file_url, '')) AS shopify_file_url,
                        c.certificate_pdf_url,
                        c.certificate_print_jpg_url,
                        c.certificate_preview_image_url,
                        c.shopify_pdf_file_id,
                        c.shopify_print_jpg_file_id,
                        c.shopify_preview_file_id,
                        c.asset_sync_status,
                        c.asset_sync_error,
                        c.generated_at,
                        c.certificate_r2_bucket,
                        c.certificate_r2_key,
                        c.certificate_preview_r2_bucket,
                        c.certificate_preview_r2_key
                    FROM edition_orders eo
                    LEFT JOIN certificates c
                      ON COALESCE(c.related_edition_order_id::text, c.edition_order_id::text) = eo.id::text
                    WHERE eo.shopify_line_item_id = ANY(%s)
                    ORDER BY eo.shopify_line_item_id ASC,
                             eo.allocation_index ASC NULLS LAST,
                             eo.edition_number ASC NULLS LAST
                    """,
                    (line_ids,),
                )
                edition_rows = cur.fetchall()
            print(
                f"PERF Orders Supabase edition overlay load {(time.perf_counter() - overlay_started):.3f}s rows={len(edition_rows)}",
                flush=True,
            )

    merge_started = time.perf_counter()
    assignments_by_line = {}
    for edition_row in edition_rows:
        line_id = str(edition_row.get("shopify_line_item_id") or "").strip()
        if not line_id:
            continue
        assignments_by_line.setdefault(line_id, []).append(
            {
                "edition_order_id": edition_row.get("edition_order_id"),
                "edition_number": edition_row.get("edition_number"),
                "edition_total": edition_row.get("edition_total"),
                "allocation_index": edition_row.get("allocation_index"),
                "assigned_at": edition_row.get("assigned_at"),
                "certificate_status": edition_row.get("certificate_status"),
                "assignment_status": edition_row.get("edition_order_status") or "Assigned",
                "assignment_source": edition_row.get("assignment_source"),
                "manual_override": edition_row.get("manual_override"),
                "certificate_id": edition_row.get("certificate_id"),
                "local_file_path": edition_row.get("local_file_path"),
                "shopify_file_url": edition_row.get("shopify_file_url") or edition_row.get("certificate_pdf_url"),
                "certificate_pdf_url": edition_row.get("certificate_pdf_url"),
                "certificate_print_jpg_url": edition_row.get("certificate_print_jpg_url"),
                "certificate_preview_image_url": edition_row.get("certificate_preview_image_url"),
                "shopify_file_id": edition_row.get("shopify_pdf_file_id") or edition_row.get("shopify_file_id"),
                "shopify_pdf_file_id": edition_row.get("shopify_pdf_file_id"),
                "shopify_print_jpg_file_id": edition_row.get("shopify_print_jpg_file_id"),
                "shopify_preview_file_id": edition_row.get("shopify_preview_file_id"),
                "asset_sync_status": edition_row.get("asset_sync_status"),
                "asset_sync_error": edition_row.get("asset_sync_error"),
                "generated_at": edition_row.get("generated_at"),
                "certificate_r2_bucket": edition_row.get("certificate_r2_bucket"),
                "certificate_r2_key": edition_row.get("certificate_r2_key"),
                "certificate_preview_r2_bucket": edition_row.get("certificate_preview_r2_bucket"),
                "certificate_preview_r2_key": edition_row.get("certificate_preview_r2_key"),
            }
        )
    merged_rows = []
    for row in base_rows:
        line_id = str(row.get("shopify_line_item_id") or "").strip()
        merged = dict(row)
        merged["assignments"] = assignments_by_line.get(line_id, [])
        merged_rows.append(merged)
    print(
        f"PERF Orders merge time {(time.perf_counter() - merge_started):.3f}s rows={len(merged_rows)}",
        flush=True,
    )
    print(
        f"PERF Orders hybrid read total {(time.perf_counter() - total_started):.3f}s rows={len(merged_rows)}",
        flush=True,
    )
    return merged_rows


def list_orders(search="", sort="Date newest", status_filter="All", limit=250):
    ensure_order_read_schema()
    search_value = f"%{search.strip().lower()}%" if search.strip() else None
    order_by = _order_sort_clause(sort)
    base_sql = """
        WITH line_rows AS (
            SELECT o.shopify_order_id, o.order_name, o.order_number, o.admin_url,
                   COALESCE(NULLIF(o.customer_name, ''), NULLIF(eo.customer_name, '')) AS customer_name,
                   COALESCE(NULLIF(o.customer_email, ''), NULLIF(eo.customer_email, '')) AS customer_email,
                   o.financial_status, o.fulfillment_status,
                   o.total_price, o.currency, o.created_at, o.remote_updated_at, o.processed_at, o.cancelled_at, o.synced_at,
                   o.raw_json AS order_raw_json,
                   li.id AS order_line_id, COALESCE(eo.shopify_line_item_id, li.shopify_line_item_id) AS shopify_line_item_id, li.quantity,
                   li.assignment_status, li.last_error,
                   eo.id AS edition_order_id,
                   COALESCE(NULLIF(eo.shopify_handle, ''), NULLIF(li.shopify_handle, '')) AS shopify_handle,
                   COALESCE(NULLIF(eo.shopify_product_id, ''), NULLIF(li.shopify_product_id, '')) AS shopify_product_id,
                   COALESCE(
                       NULLIF(eo.shopify_variant_id, ''),
                       NULLIF(c.shopify_variant_id, ''),
                       NULLIF(li.raw_json->>'shopify_variant_id', ''),
                       NULLIF(li.raw_json->>'variant_id', ''),
                       NULLIF(li.raw_json->'variant'->>'id', '')
                   ) AS shopify_variant_id,
                   COALESCE(NULLIF(li.product_title, ''), NULLIF(eo.product_title, '')) AS product_title,
                   COALESCE(
                       NULLIF(li.variant_title, ''),
                       NULLIF(eo.variant_title, ''),
                       NULLIF(c.variant_title, ''),
                       NULLIF(li.raw_json->>'variant_title', ''),
                       NULLIF(li.raw_json->>'variantTitle', ''),
                       NULLIF(li.raw_json->'variant'->>'title', '')
                   ) AS variant_title,
                   COALESCE(NULLIF(eo.sku, ''), NULLIF(li.sku, '')) AS sku,
                   eo.edition_number,
                   eo.edition_total, eo.allocation_index, eo.assigned_at, eo.certificate_status, eo.status AS edition_order_status,
                   COALESCE(pd.prodigi_status, '') AS prodigi_status,
                   COALESCE(pd.row_id, '') AS prodigi_row_id,
                   COALESCE(NULLIF(ep.featured_image_url, ''), NULLIF(sp.featured_image_url, ''), NULLIF(sp.image_url, '')) AS image_url,
                   c.certificate_id, c.local_file_path,
                   COALESCE(NULLIF(c.shopify_file_url, ''), NULLIF(c.certificate_file_url, '')) AS shopify_file_url,
                   c.certificate_pdf_url, c.certificate_print_jpg_url, c.certificate_preview_image_url,
                   c.shopify_pdf_file_id, c.shopify_print_jpg_file_id, c.shopify_preview_file_id,
                   c.asset_sync_status, c.asset_sync_error,
                   c.generated_at,
                   c.certificate_r2_bucket, c.certificate_r2_key,
                   c.certificate_preview_r2_bucket, c.certificate_preview_r2_key,
                   COALESCE(NULLIF(psd.asset_url, ''), NULLIF(psd.google_drive_file_url, '')) AS psd_url,
                   COALESCE(NULLIF(prodigi.asset_url, ''), NULLIF(prodigi.google_drive_file_url, '')) AS prodigi_url
            FROM shopify_orders o
            LEFT JOIN shopify_order_lines li ON li.shopify_order_id = o.shopify_order_id
            LEFT JOIN edition_orders eo ON eo.shopify_line_item_id = li.shopify_line_item_id
            LEFT JOIN edition_products ep ON ep.shopify_handle = COALESCE(NULLIF(eo.shopify_handle, ''), NULLIF(li.shopify_handle, ''))
            LEFT JOIN shopify_products sp ON sp.handle = COALESCE(NULLIF(eo.shopify_handle, ''), NULLIF(li.shopify_handle, ''))
            LEFT JOIN LATERAL (
                SELECT pd.row_id, pd.prodigi_status
                FROM prodigi_dispatch_rows pd
                WHERE pd.shopify_line_item_id = COALESCE(eo.shopify_line_item_id, li.shopify_line_item_id)
                  AND (
                      eo.edition_number IS NULL
                      OR pd.edition_number IS NULL
                      OR pd.edition_number = eo.edition_number
                  )
                ORDER BY pd.updated_at DESC NULLS LAST, pd.submitted_at DESC NULLS LAST
                LIMIT 1
            ) pd ON TRUE
            LEFT JOIN certificates c ON COALESCE(c.related_edition_order_id::text, c.edition_order_id::text) = eo.id::text
            LEFT JOIN product_assets psd ON psd.shopify_handle = COALESCE(NULLIF(eo.shopify_handle, ''), NULLIF(li.shopify_handle, '')) AND psd.asset_type = 'psd_master_file' AND psd.is_primary IS DISTINCT FROM FALSE
            LEFT JOIN product_assets prodigi ON prodigi.shopify_handle = COALESCE(NULLIF(eo.shopify_handle, ''), NULLIF(li.shopify_handle, '')) AND prodigi.asset_type = 'prodigi_link'
            {where}
        )
        SELECT
            shopify_order_id, order_name, order_number, admin_url,
            customer_name, customer_email,
            financial_status, fulfillment_status,
            total_price, currency, created_at, remote_updated_at, processed_at, cancelled_at, synced_at,
            order_raw_json,
            order_line_id, shopify_line_item_id, quantity,
            assignment_status, last_error,
            shopify_handle, shopify_product_id, shopify_variant_id, product_title, variant_title, sku,
            prodigi_status, prodigi_row_id,
            COALESCE(image_url, '') AS image_url,
            COALESCE(psd_url, '') AS psd_url,
            COALESCE(prodigi_url, '') AS prodigi_url,
            COALESCE(
                jsonb_agg(
                    jsonb_build_object(
                        'edition_order_id', edition_order_id,
                        'edition_number', edition_number,
                        'edition_total', edition_total,
                        'allocation_index', allocation_index,
                        'assigned_at', assigned_at,
                        'certificate_status', certificate_status,
                        'assignment_status', edition_order_status,
                        'certificate_id', certificate_id,
                        'local_file_path', local_file_path,
                        'shopify_file_url', shopify_file_url,
                        'certificate_pdf_url', certificate_pdf_url,
                        'certificate_print_jpg_url', certificate_print_jpg_url,
                        'certificate_preview_image_url', certificate_preview_image_url,
                        'shopify_pdf_file_id', shopify_pdf_file_id,
                        'shopify_print_jpg_file_id', shopify_print_jpg_file_id,
                        'shopify_preview_file_id', shopify_preview_file_id,
                        'asset_sync_status', asset_sync_status,
                        'asset_sync_error', asset_sync_error,
                        'certificate_r2_bucket', certificate_r2_bucket,
                        'certificate_r2_key', certificate_r2_key,
                        'certificate_preview_r2_bucket', certificate_preview_r2_bucket,
                        'certificate_preview_r2_key', certificate_preview_r2_key,
                        'generated_at', generated_at
                    )
                    ORDER BY edition_number ASC NULLS LAST, allocation_index ASC NULLS LAST
                ) FILTER (WHERE edition_order_id IS NOT NULL),
                '[]'::jsonb
            ) AS assignments,
            COUNT(edition_order_id) FILTER (WHERE edition_order_id IS NOT NULL) AS assignments_count,
            MIN(edition_number) FILTER (WHERE edition_order_id IS NOT NULL) AS first_edition_number
        FROM line_rows
        GROUP BY
            shopify_order_id, order_name, order_number, admin_url,
            customer_name, customer_email,
            financial_status, fulfillment_status,
            total_price, currency, created_at, remote_updated_at, processed_at, cancelled_at, synced_at, order_raw_json,
            order_line_id, shopify_line_item_id, quantity,
            assignment_status, last_error,
            shopify_handle, shopify_product_id, shopify_variant_id, product_title, variant_title, sku,
            prodigi_status, prodigi_row_id,
            image_url, psd_url, prodigi_url
    """
    where_clauses = []
    params = []
    if search_value:
        where_clauses.append(
            """
            LOWER(COALESCE(o.order_name, '')) LIKE %s
               OR LOWER(COALESCE(o.order_number, '')) LIKE %s
               OR LOWER(COALESCE(o.customer_name, '')) LIKE %s
               OR LOWER(COALESCE(o.customer_email, '')) LIKE %s
               OR LOWER(COALESCE(eo.product_title, li.product_title, '')) LIKE %s
               OR LOWER(COALESCE(eo.variant_title, li.variant_title, '')) LIKE %s
               OR LOWER(COALESCE(eo.sku, li.sku, '')) LIKE %s
               OR LOWER(COALESCE(eo.shopify_handle, li.shopify_handle, '')) LIKE %s
               OR LOWER(COALESCE(li.assignment_status, '')) LIKE %s
               OR CAST(COALESCE(eo.edition_number, 0) AS TEXT) LIKE %s
            """
        )
        params = [search_value] * 9 + [f"%{search.strip()}%"]
    status_clauses = {
        "Needs edition": "COALESCE(li.assignment_status, '') IN ('Needs Edition', 'Product Not Found', 'Needs Edition Setup', 'Error')",
        "Assigned": "(COALESCE(li.assignment_status, '') = 'Assigned' OR eo.id IS NOT NULL)",
        "Historical": f"COALESCE(li.assignment_status, '') = '{HISTORICAL_ORDER_STATUS}' AND eo.id IS NULL",
        "Certificates missing": "eo.id IS NOT NULL AND c.id IS NULL",
        "PSD missing": "COALESCE(COALESCE(eo.shopify_handle, li.shopify_handle), '') <> '' AND COALESCE(NULLIF(psd.asset_url, ''), NULLIF(psd.google_drive_file_url, ''), '') = ''",
        "Prodigi missing": "COALESCE(COALESCE(eo.shopify_handle, li.shopify_handle), '') <> '' AND COALESCE(NULLIF(prodigi.asset_url, ''), NULLIF(prodigi.google_drive_file_url, ''), '') = ''",
        "Errors": "COALESCE(li.assignment_status, '') IN ('Error', 'Product Not Found', 'Needs Edition Setup', 'Sold Out')",
    }
    selected_status_clause = status_clauses.get(str(status_filter or "").strip())
    if selected_status_clause:
        where_clauses.append(selected_status_clause)
    where = f"WHERE {' AND '.join(f'({clause})' for clause in where_clauses)}" if where_clauses else ""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                base_sql.format(where=where) + f" ORDER BY {order_by} LIMIT %s",
                (*params, limit),
            )
            return cur.fetchall()


def get_order_summary():
    ensure_order_read_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH line_handles AS (
                    SELECT li.shopify_line_item_id,
                           COALESCE(NULLIF(MAX(eo.shopify_handle), ''), NULLIF(MAX(li.shopify_handle), '')) AS shopify_handle
                    FROM shopify_order_lines li
                    LEFT JOIN edition_orders eo ON eo.shopify_line_item_id=li.shopify_line_item_id
                    GROUP BY li.shopify_line_item_id
                )
                SELECT
                    (SELECT COUNT(*) FROM shopify_orders) AS orders_synced,
                    (SELECT COUNT(*) FROM shopify_order_lines
                     WHERE assignment_status IN ('Needs Edition', 'Product Not Found', 'Needs Edition Setup', 'Error')) AS needs_edition,
                    (SELECT COUNT(*) FROM shopify_order_lines
                     WHERE assignment_status = %s) AS historical_lines,
                    (SELECT COUNT(*) FROM edition_orders WHERE assigned_at::date = CURRENT_DATE) AS assigned_today,
                    (SELECT COUNT(*) FROM edition_orders eo
                     LEFT JOIN certificates c ON COALESCE(c.related_edition_order_id::text, c.edition_order_id::text)=eo.id::text
                     WHERE c.id IS NULL) AS certificates_missing,
                    (SELECT COUNT(*) FROM line_handles lh
                     LEFT JOIN product_assets pa ON pa.shopify_handle=lh.shopify_handle AND pa.asset_type='psd_master_file' AND pa.is_primary IS DISTINCT FROM FALSE
                     WHERE COALESCE(lh.shopify_handle, '') <> ''
                       AND COALESCE(NULLIF(pa.asset_url, ''), NULLIF(pa.google_drive_file_url, ''), '')='') AS psd_links_missing,
                    (SELECT COUNT(*) FROM line_handles lh
                     LEFT JOIN product_assets pa ON pa.shopify_handle=lh.shopify_handle AND pa.asset_type='prodigi_link'
                     WHERE COALESCE(lh.shopify_handle, '') <> ''
                       AND COALESCE(NULLIF(pa.asset_url, ''), NULLIF(pa.google_drive_file_url, ''), '')='') AS prodigi_links_missing
                """
                ,
                (HISTORICAL_ORDER_STATUS,),
            )
            return cur.fetchone() or {}


def get_order_activity(days=7):
    ensure_order_read_schema()
    window_days = min(max(int(days or 7), 3), 30)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH series AS (
                    SELECT generate_series(
                        CURRENT_DATE - (%s::integer - 1),
                        CURRENT_DATE,
                        interval '1 day'
                    )::date AS day
                ),
                order_counts AS (
                    SELECT COALESCE(created_at::date, synced_at::date) AS day,
                           COUNT(DISTINCT shopify_order_id) AS orders_synced
                    FROM shopify_orders
                    WHERE COALESCE(created_at, synced_at) >= CURRENT_DATE - (%s::integer - 1)
                    GROUP BY 1
                ),
                assignment_counts AS (
                    SELECT assigned_at::date AS day,
                           COUNT(*) AS editions_assigned
                    FROM edition_orders
                    WHERE assigned_at >= CURRENT_DATE - (%s::integer - 1)
                    GROUP BY 1
                )
                SELECT
                    series.day,
                    COALESCE(order_counts.orders_synced, 0) AS orders_synced,
                    COALESCE(assignment_counts.editions_assigned, 0) AS editions_assigned
                FROM series
                LEFT JOIN order_counts ON order_counts.day = series.day
                LEFT JOIN assignment_counts ON assignment_counts.day = series.day
                ORDER BY series.day
                """,
                (window_days, window_days, window_days),
            )
            return cur.fetchall()


def get_dashboard_summary():
    ensure_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM edition_products) AS edition_products,
                    (SELECT COUNT(*) FROM edition_products WHERE sold_out) AS sold_out_products,
                    (SELECT COUNT(*) FROM edition_products ep
                     WHERE NOT EXISTS (
                        SELECT 1 FROM product_assets pa
                        WHERE pa.shopify_handle=ep.shopify_handle
                          AND pa.asset_type='psd_master_file'
                          AND pa.is_primary IS DISTINCT FROM FALSE
                          AND COALESCE(NULLIF(pa.asset_url, ''), NULLIF(pa.google_drive_file_url, ''), '') <> ''
                     )) AS missing_psd,
                    (SELECT COUNT(*) FROM edition_orders WHERE certificate_status <> 'Certificate Ready') AS certificates_missing,
                    (SELECT COUNT(*) FROM app_errors WHERE created_at > now() - interval '7 days') AS recent_errors,
                    (SELECT COUNT(*) FROM shopify_orders) AS orders_synced
                """
            )
            return cur.fetchone() or {}


def _edition_order_search_filter(search):
    raw = str(search or "").strip()
    if not raw:
        return "", []

    conditions = []
    params = []
    order_terms = []
    general_terms = [raw]
    without_hash = raw[1:].strip() if raw.startswith("#") else raw
    if without_hash and without_hash != raw:
        order_terms.append(without_hash)
        general_terms.append(without_hash)
    if raw:
        order_terms.append(raw)
    if raw and not raw.startswith("#"):
        order_terms.append(f"#{raw}")

    unique_order_terms = []
    for term in order_terms:
        clean = str(term or "").strip()
        if clean and clean not in unique_order_terms:
            unique_order_terms.append(clean)

    for term in unique_order_terms:
        pattern = f"%{term}%"
        conditions.extend(
            [
                "COALESCE(NULLIF(eo.shopify_order_name, ''), NULLIF(o.order_name, ''), '') ILIKE %s",
                "COALESCE(eo.shopify_order_id, '') ILIKE %s",
            ]
        )
        params.extend([pattern, pattern])

    unique_general_terms = []
    for term in general_terms:
        clean = str(term or "").strip()
        if clean and clean not in unique_general_terms:
            unique_general_terms.append(clean)

    for term in unique_general_terms:
        pattern = f"%{term}%"
        conditions.extend(
            [
                "COALESCE(eo.customer_name, '') ILIKE %s",
                "COALESCE(eo.customer_email, '') ILIKE %s",
                "COALESCE(eo.product_title, '') ILIKE %s",
                "COALESCE(eo.variant_title, '') ILIKE %s",
                "COALESCE(eo.shopify_handle, eo.product_handle, '') ILIKE %s",
                "COALESCE(eo.sku, '') ILIKE %s",
                "COALESCE(eo.shopify_line_item_id, '') ILIKE %s",
            ]
        )
        params.extend([pattern] * 7)

    edition_match = re.fullmatch(r"#?0*(\d+)", raw)
    if edition_match:
        conditions.append("eo.edition_number = %s")
        params.append(int(edition_match.group(1)))

    uuid_value = _coerce_uuid_or_none(raw)
    if uuid_value:
        conditions.extend(
            [
                "eo.id::text = %s",
                "c.edition_order_id::text = %s",
                "c.related_edition_order_id::text = %s",
            ]
        )
        params.extend([uuid_value, uuid_value, uuid_value])

    if not conditions:
        return "", []
    return "WHERE " + "\n                       OR ".join(conditions), params


def list_edition_orders(search="", limit=250):
    ensure_schema()
    where_sql, search_params = _edition_order_search_filter(search)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT eo.*, o.order_name, o.admin_url, c.local_file_path,
                       COALESCE(NULLIF(eo.certificate_status, ''), NULLIF(c.status, ''), 'Certificate Missing') AS certificate_status,
                       COALESCE(NULLIF(c.shopify_file_url, ''), NULLIF(c.certificate_file_url, '')) AS shopify_file_url,
                       c.certificate_r2_bucket, c.certificate_r2_key,
                       c.certificate_preview_r2_bucket, c.certificate_preview_r2_key
                FROM edition_orders eo
                LEFT JOIN shopify_orders o ON o.shopify_order_id=eo.shopify_order_id
                LEFT JOIN certificates c ON COALESCE(c.related_edition_order_id::text, c.edition_order_id::text)=eo.id::text
                {where_sql}
                ORDER BY COALESCE(o.processed_at, o.created_at, eo.purchase_date, eo.assigned_at) DESC NULLS LAST,
                         COALESCE(NULLIF(eo.shopify_order_name, ''), NULLIF(o.order_name, '')) DESC NULLS LAST,
                         eo.shopify_line_item_id ASC NULLS LAST,
                         eo.allocation_index ASC NULLS LAST,
                         eo.edition_number ASC NULLS LAST
                LIMIT %s
                """,
                (*search_params, limit),
            )
            return cur.fetchall()


def generate_certificate_for_edition_order(edition_order_id, *, force=False):
    ensure_schema()
    assignment = None
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT eo.*, o.order_name
                FROM edition_orders eo
                LEFT JOIN shopify_orders o ON o.shopify_order_id=eo.shopify_order_id
                WHERE eo.id::text=%s
                """,
                (str(edition_order_id),),
            )
            assignment = cur.fetchone()
            if not assignment:
                raise ValueError("Edition order was not found.")
            path = _generate_certificate_for_assignment(cur, assignment, force=force)
        conn.commit()
    try:
        if assignment and assignment.get("shopify_order_id"):
            sync_order_certificate_metafields(assignment["shopify_order_id"])
    except Exception as error:
        log_app_error(
            "order_certificate_metafield_sync_failed",
            str(error),
            {
                "edition_order_id": edition_order_id,
                "shopify_order_id": assignment.get("shopify_order_id") if assignment else "",
            },
        )
    return path


def mark_certificates_checked(edition_order_ids):
    ensure_schema()
    ids = [str(value) for value in edition_order_ids if value]
    if not ids:
        return 0
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE edition_orders
                SET certificate_status='Certificate Ready'
                WHERE id::text = ANY(%s)
                """,
                (ids,),
            )
            count = cur.rowcount
        conn.commit()
    return count


def _edition_product_for_order_row(cur, row, *, lock=False):
    result = _resolve_edition_product_for_order_line_with_cursor(cur, row, lock=lock)
    return result.get("product") or None


def _edition_conflict_for_number(cur, *, row, product, edition_number):
    conditions = []
    params = [str(row.get("id")), int(edition_number)]
    run_id = row.get("edition_run_id")
    product_id = str((product or {}).get("shopify_product_id") or row.get("shopify_product_id") or "").strip()
    handle = str((product or {}).get("shopify_handle") or row.get("shopify_handle") or row.get("product_handle") or "").strip()
    if run_id:
        conditions.append("edition_run_id=%s")
        params.append(run_id)
    if product_id:
        conditions.append("shopify_product_id=%s")
        params.append(product_id)
    if handle:
        conditions.append("(shopify_handle=%s OR product_handle=%s)")
        params.extend([handle, handle])
    if not conditions:
        raise ValueError("Row has no matched edition product.")
    cur.execute(
        f"""
        SELECT id, shopify_order_id, shopify_order_name, shopify_line_item_id,
               product_title, shopify_handle, edition_number
        FROM edition_orders
        WHERE id::text <> %s
          AND edition_number=%s
          AND ({" OR ".join(conditions)})
        LIMIT 1
        """,
        tuple(params),
    )
    return cur.fetchone()


def _max_assigned_for_product(cur, product, run):
    conditions = []
    params = []
    if run and run.get("id"):
        conditions.append("edition_run_id=%s")
        params.append(run["id"])
    product_id = str((product or {}).get("shopify_product_id") or "").strip()
    handle = str((product or {}).get("shopify_handle") or "").strip()
    if product_id:
        conditions.append("shopify_product_id=%s")
        params.append(product_id)
    if handle:
        conditions.append("(shopify_handle=%s OR product_handle=%s)")
        params.extend([handle, handle])
    if not conditions:
        return 0
    cur.execute(
        f"""
        SELECT COALESCE(MAX(edition_number), 0) AS max_assigned
        FROM edition_orders
        WHERE {" OR ".join(conditions)}
        """,
        tuple(params),
    )
    return _int_value((cur.fetchone() or {}).get("max_assigned"), 0)


def _recalculate_next_edition_number_with_cursor(cur, product, run=None, *, reason="Manual edition override"):
    if not product:
        raise ValueError("No edition product was provided.")
    handle = str(product.get("shopify_handle") or "").strip()
    if not handle:
        raise ValueError("Edition product handle is missing.")
    if run is None:
        _, run = _get_active_edition_run_for_handle(cur, handle, lock=True, create_missing=True)
    edition_total = max(
        _int_value((run or {}).get("edition_total"), _int_value(product.get("edition_total"), 100)),
        1,
    )
    old_next = max(
        _int_value((run or {}).get("next_edition_number"), _int_value(product.get("next_edition_number"), 1)),
        1,
    )
    max_assigned = max(_max_assigned_for_product(cur, product, run), 0)
    sold_out = max_assigned >= edition_total
    next_number = edition_total if sold_out else min(max(max_assigned + 1, 1), edition_total)
    remaining = max(edition_total - max_assigned, 0)
    run_status = SOLD_OUT_RUN_STATUS if sold_out else ACTIVE_RUN_STATUS

    if run and run.get("id"):
        cur.execute(
            """
            UPDATE edition_runs
            SET next_edition_number=%s,
                status=%s,
                updated_at=now()
            WHERE id=%s
            """,
            (next_number, run_status, run.get("id")),
        )
    cur.execute(
        """
        UPDATE edition_products
        SET next_edition_number=%s,
            last_assigned_edition=%s,
            remaining_count=%s,
            active=%s,
            is_active=%s,
            sold_out=%s,
            is_sold_out=%s,
            updated_at=now()
        WHERE shopify_handle=%s
        RETURNING *
        """,
        (
            next_number,
            max_assigned,
            remaining,
            not sold_out,
            not sold_out,
            sold_out,
            sold_out,
            handle,
        ),
    )
    updated_product = cur.fetchone() or product
    _insert_edition_adjustment_with_cursor(
        cur,
        product=updated_product,
        run=run,
        old_next=old_next,
        new_next=next_number,
        old_total=edition_total,
        new_total=edition_total,
        reason=reason,
        source="manual_override",
    )
    return {
        "shopify_handle": handle,
        "shopify_product_id": updated_product.get("shopify_product_id") or product.get("shopify_product_id") or "",
        "edition_total": edition_total,
        "max_assigned": max_assigned,
        "next_edition_number": next_number,
        "remaining_count": remaining,
        "sold_out": sold_out,
        "status": run_status,
    }


def recalculate_next_edition_number(shopify_handle="", shopify_product_id="", *, sync_shopify=False, config=None):
    ensure_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            product = _edition_product_for_order_row(
                cur,
                {"shopify_handle": shopify_handle, "shopify_product_id": shopify_product_id},
                lock=True,
            )
            if not product:
                raise ValueError("Edition product was not found.")
            _, run = _get_active_edition_run_for_handle(
                cur,
                product.get("shopify_handle"),
                lock=True,
                create_missing=True,
            )
            result = _recalculate_next_edition_number_with_cursor(
                cur,
                product,
                run,
                reason="Manual product next edition recalculation",
            )
        conn.commit()
    warning = ""
    if sync_shopify:
        try:
            product_for_sync = {
                **result,
                "product_title": (product or {}).get("product_title") or "",
            }
            _sync_shopify_product_after_override(product_for_sync, config=config)
        except Exception as error:
            warning = f"Shopify product metafield sync failed: {error}"
            log_app_error("manual_recalculate_product_metafield_sync_failed", str(error), result)
    if warning:
        result["warning"] = warning
    return result


def _is_uploaded_certificate_row(row):
    return bool(
        (row or {}).get("shopify_file_id")
        or (row or {}).get("shopify_file_url")
        or (row or {}).get("certificate_file_url")
        or (row or {}).get("certificate_r2_bucket")
        or (row or {}).get("certificate_r2_key")
    )


def _sync_shopify_order_allocation_override(row, new_edition_number, reason="", config=None):
    import order_allocator

    order_id = row.get("shopify_order_id")
    line_id = order_allocator.line_item_gid(row.get("shopify_line_item_id"))
    if not order_id or not line_id:
        return {"ok": False, "warning": "Shopify order or line item ID is missing."}
    state = order_allocator.read_order_allocation_state(order_id, config=config)
    payload = order_allocator.parse_allocation_payload(state.get("payload") or {})
    payload.update(
        {
            "version": order_allocator.SNAPSHOT_VERSION,
            "source": "sports_cave_os_manual_override",
            "order_id": order_allocator.order_gid(order_id),
            "order_name": row.get("shopify_order_name") or row.get("order_name") or payload.get("order_name") or "",
            "updated_at": utc_now(),
        }
    )
    line_items = dict(payload.get("line_items") or {})
    allocation = dict(line_items.get(line_id) or {})
    quantity = max(_int_value(row.get("quantity"), 1), _int_value(row.get("allocation_index"), 1), 1)
    numbers = list(allocation.get("edition_numbers") or [])
    while len(numbers) < quantity:
        numbers.append(None)
    unit_index = max(_int_value(row.get("allocation_index"), 1), 1)
    numbers[unit_index - 1] = int(new_edition_number)
    positive_numbers = [number for number in numbers if _int_value(number, 0) > 0]
    unit_allocations = [unit for unit in allocation.get("unit_allocations") or [] if isinstance(unit, dict)]
    replaced_unit = False
    for unit in unit_allocations:
        if _int_value(unit.get("line_item_unit_index"), 0) == unit_index:
            unit.update(
                {
                    "edition_number": int(new_edition_number),
                    "manual_override": True,
                    "override_reason": reason or "Manual edition override",
                    "override_timestamp": utc_now(),
                }
            )
            replaced_unit = True
    if not replaced_unit:
        unit_allocations.append(
            {
                "order_gid": order_allocator.order_gid(order_id),
                "line_item_gid": line_id,
                "line_item_unit_index": unit_index,
                "product_gid": order_allocator.product_gid(row.get("shopify_product_id")),
                "variant_gid": row.get("shopify_variant_id") or "",
                "edition_number": int(new_edition_number),
                "manual_override": True,
                "override_reason": reason or "Manual edition override",
                "override_timestamp": utc_now(),
            }
        )
    allocation.update(
        {
            "line_item_id": line_id,
            "product_id": order_allocator.product_gid(row.get("shopify_product_id")),
            "variant_id": row.get("shopify_variant_id") or "",
            "handle": row.get("shopify_handle") or row.get("product_handle") or "",
            "product_title": row.get("product_title") or "",
            "variant_title": row.get("variant_title") or "",
            "quantity": quantity,
            "edition_numbers": numbers,
            "edition_number": positive_numbers[0] if positive_numbers else int(new_edition_number),
            "edition_total": _int_value(row.get("edition_total"), 100),
            "edition_display": order_allocator.format_edition_numbers(positive_numbers, row.get("edition_total") or 100),
            "status": "Manual Override",
            "manual_override": True,
            "override_reason": reason or "Manual edition override",
            "override_timestamp": utc_now(),
            "unit_allocations": unit_allocations,
        }
    )
    line_items[line_id] = allocation
    payload["line_items"] = line_items
    shopify_sync.sync_order_allocation_metafield(
        order_id,
        payload,
        compare_digest=state.get("compare_digest"),
        config=config,
    )
    return {"ok": True, "payload": payload}


def _sync_shopify_product_after_override(product_state, config=None):
    product_id = product_state.get("shopify_product_id")
    if not product_id:
        return {"ok": False, "warning": "Shopify product ID is missing; product metafields were not synced."}
    remaining = _int_value(product_state.get("remaining_count"), 0)
    result = shopify_sync.sync_limited_edition_metafields_for_products(
        [
            {
                "shopify_product_id": product_id,
                "handle": product_state.get("shopify_handle") or "",
                "title": product_state.get("product_title") or product_state.get("shopify_handle") or "",
                "edition_enabled": True,
                "edition_total": product_state.get("edition_total"),
                "edition_next_number": product_state.get("next_edition_number"),
                "edition_sold_count": product_state.get("max_assigned"),
                "edition_remaining": remaining,
                "edition_status": shopify_sync.calculate_limited_edition_status(remaining),
            }
        ],
        config=config,
        raise_on_failure=True,
    )
    return {"ok": True, **result}


def override_edition_order_number(edition_order_id, new_edition_number, *, reason="", config=None, sync_shopify=True):
    ensure_schema()
    row_id = str(edition_order_id or "").strip()
    new_number = _int_value(new_edition_number, 0)
    if not row_id:
        raise ValueError("Edition order ID is required.")
    if new_number <= 0:
        raise ValueError("New edition number must be at least 1.")

    shopify_warning = ""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT eo.*, o.order_name,
                       c.id AS certificate_row_id,
                       c.local_file_path,
                       COALESCE(NULLIF(c.shopify_file_url, ''), NULLIF(c.certificate_file_url, '')) AS shopify_file_url,
                       c.shopify_file_id AS certificate_shopify_file_id,
                       c.certificate_r2_bucket,
                       c.certificate_r2_key
                FROM edition_orders eo
                LEFT JOIN shopify_orders o ON o.shopify_order_id=eo.shopify_order_id
                LEFT JOIN certificates c ON COALESCE(c.related_edition_order_id::text, c.edition_order_id::text)=eo.id::text
                WHERE eo.id::text=%s
                ORDER BY c.updated_at DESC NULLS LAST
                LIMIT 1
                FOR UPDATE OF eo
                """,
                (row_id,),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("Edition order row was not found.")
            product = _edition_product_for_order_row(cur, row, lock=True)
            if not product:
                raise ValueError("Row has no matched edition product.")
            _, run = _get_active_edition_run_for_handle(
                cur,
                product.get("shopify_handle"),
                lock=True,
                create_missing=True,
            )
            edition_total = max(
                _int_value((run or {}).get("edition_total"), _int_value(product.get("edition_total"), row.get("edition_total") or 100)),
                1,
            )
            if new_number > edition_total:
                raise ValueError(f"Edition number must be between 1 and {edition_total}.")
            conflict = _edition_conflict_for_number(
                cur,
                row=row,
                product=product,
                edition_number=new_number,
            )
            if conflict:
                order_label = conflict.get("shopify_order_name") or conflict.get("shopify_order_id") or "another order"
                raise ValueError(f"Edition #{new_number:03d} is already used by {order_label} for this product.")

            old_number = _int_value(row.get("edition_number"), 0)
            certificate_uploaded = _is_uploaded_certificate_row(row)
            certificate_status = "Needs regeneration" if certificate_uploaded else "Generate"
            display = format_edition_display_number(new_number, edition_total)
            cur.execute(
                """
                UPDATE edition_orders
                SET edition_number=%s,
                    edition_total=%s,
                    edition_display=%s,
                    certificate_status=%s,
                    shopify_file_status=CASE
                        WHEN %s THEN 'STALE'
                        ELSE shopify_file_status
                    END,
                    manual_override=TRUE,
                    override_old_edition_number=%s,
                    override_new_edition_number=%s,
                    override_timestamp=now(),
                    override_reason=%s,
                    status='manual_override',
                    updated_at=now()
                WHERE id::text=%s
                RETURNING *
                """,
                (
                    new_number,
                    edition_total,
                    display,
                    certificate_status,
                    certificate_uploaded,
                    old_number,
                    new_number,
                    reason or "Manual edition override",
                    row_id,
                ),
            )
            updated_row = cur.fetchone()
            if row.get("certificate_row_id"):
                cur.execute(
                    """
                    UPDATE certificates
                    SET status='Stale - Needs regeneration',
                        certificate_status='Needs regeneration',
                        updated_at=now()
                    WHERE id=%s
                    """,
                    (row.get("certificate_row_id"),),
                )
            cur.execute(
                """
                UPDATE shopify_order_lines
                SET assignment_status='Assigned',
                    last_error='',
                    updated_at=now()
                WHERE shopify_line_item_id=%s
                """,
                (updated_row.get("shopify_line_item_id"),),
            )
            product_state = _recalculate_next_edition_number_with_cursor(
                cur,
                product,
                run,
                reason=reason or "Manual edition override",
            )
            _insert_audit_log(
                cur,
                event_type="edition_order_manual_override",
                entity_type="edition_order",
                entity_id=updated_row.get("id"),
                shopify_order_id=updated_row.get("shopify_order_id"),
                shopify_line_item_id=updated_row.get("shopify_line_item_id"),
                shopify_handle=updated_row.get("shopify_handle") or updated_row.get("product_handle"),
                old_value={
                    "edition_order_id": row.get("id"),
                    "edition_number": old_number,
                    "edition_total": row.get("edition_total"),
                    "certificate_status": row.get("certificate_status"),
                    "manual_override": bool(row.get("manual_override")),
                    "status": row.get("status"),
                },
                new_value={
                    "edition_order_id": updated_row.get("id"),
                    "edition_number": new_number,
                    "edition_total": updated_row.get("edition_total"),
                    "certificate_status": certificate_status,
                    "manual_override": True,
                    "status": updated_row.get("status"),
                    "next_edition_number": product_state.get("next_edition_number"),
                },
                reason=reason or "Manual edition override",
                actor="sports_cave_os",
                source="sports_cave_os_manual_override",
            )
        conn.commit()

    shopify_results = {}
    shopify_mirror_status = "pending"
    if sync_shopify:
        shopify_mirror_status = "updated"
        try:
            shopify_results["order_allocation"] = _sync_shopify_order_allocation_override(
                updated_row,
                new_number,
                reason=reason,
                config=config,
            )
        except Exception as error:
            shopify_warning = f"Shopify order allocation metafield sync failed: {error}"
            shopify_mirror_status = "failed"
            log_app_error("manual_override_order_metafield_sync_failed", str(error), {"edition_order_id": row_id})
        try:
            product_for_sync = {**product_state, "product_title": product.get("product_title") or ""}
            shopify_results["product_metafields"] = _sync_shopify_product_after_override(
                product_for_sync,
                config=config,
            )
        except Exception as error:
            warning = f"Shopify product metafield sync failed: {error}"
            shopify_warning = f"{shopify_warning} {warning}".strip()
            shopify_mirror_status = "failed"
            log_app_error("manual_override_product_metafield_sync_failed", str(error), {"edition_order_id": row_id})

    return {
        "edition_order": updated_row,
        "old_edition_number": old_number,
        "new_edition_number": new_number,
        "certificate_status": certificate_status,
        "product": product_state,
        "shopify": shopify_results,
        "shopify_mirror_status": shopify_mirror_status,
        "warning": shopify_warning,
    }


def list_certificates(search="", limit=250):
    ensure_schema()
    search_value = f"%{search.strip().lower()}%" if search.strip() else None
    with connect() as conn:
        with conn.cursor() as cur:
            if search_value:
                cur.execute(
                    """
                    SELECT c.*, eo.product_title, eo.customer_name, o.order_name
                    FROM certificates c
                    LEFT JOIN edition_orders eo ON eo.id::text=COALESCE(c.related_edition_order_id::text, c.edition_order_id::text)
                    LEFT JOIN shopify_orders o ON o.shopify_order_id=c.shopify_order_id
                    WHERE LOWER(COALESCE(eo.product_title, '')) LIKE %s
                       OR LOWER(COALESCE(eo.customer_name, '')) LIKE %s
                       OR LOWER(COALESCE(o.order_name, '')) LIKE %s
                    ORDER BY c.generated_at DESC
                    LIMIT %s
                    """,
                    (search_value, search_value, search_value, limit),
                )
            else:
                cur.execute(
                    """
                    SELECT c.*, eo.product_title, eo.customer_name, o.order_name
                    FROM certificates c
                    LEFT JOIN edition_orders eo ON eo.id::text=COALESCE(c.related_edition_order_id::text, c.edition_order_id::text)
                    LEFT JOIN shopify_orders o ON o.shopify_order_id=c.shopify_order_id
                    ORDER BY c.generated_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
            return cur.fetchall()


def list_webhook_events(limit=200):
    ensure_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM webhook_events ORDER BY received_at DESC LIMIT %s", (limit,))
            return cur.fetchall()


def list_sync_runs(limit=200):
    ensure_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM sync_runs ORDER BY started_at DESC LIMIT %s", (limit,))
            return cur.fetchall()


def list_app_errors(limit=200):
    ensure_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM app_errors ORDER BY created_at DESC LIMIT %s", (limit,))
            return cur.fetchall()


ADS_LAST_SUCCESSFUL_SYNC_KEY = "ads_meta_last_successful_sync_at"
ADS_LAST_SYNC_ERROR_KEY = "ads_meta_last_sync_error"
ADS_LAST_SYNC_RANGE_KEY = "ads_meta_last_sync_range"
ADS_SCHEMA_MIGRATIONS = (
    BASE_DIR / "migrations" / "20260626_ads_intelligence_v1.sql",
    BASE_DIR / "migrations" / "20260626_ads_intelligence_v2_breakdowns.sql",
    BASE_DIR / "migrations" / "20260626_ads_product_mapping_v1.sql",
)


def ensure_ads_schema():
    ensure_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            for migration in ADS_SCHEMA_MIGRATIONS:
                cur.execute(migration.read_text(encoding="utf-8"))
        conn.commit()


def _ads_float(value, default=0.0):
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _ads_int(value, default=0):
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def sanitize_ads_error(message):
    cleaned = str(message or "")
    for key in ("META_ACCESS_TOKEN", "META_APP_SECRET"):
        value = str(os.getenv(key, "")).strip()
        if value and len(value) >= 6:
            cleaned = cleaned.replace(value, "[redacted]")
    cleaned = re.sub(r"access_token=([^&\s]+)", "access_token=[redacted]", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(Bearer\s+)[A-Za-z0-9_\-.]+", r"\1[redacted]", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bEAA[A-Za-z0-9_\-]{12,}\b", "[redacted]", cleaned)
    return cleaned


def _meta_action_total(row, action_names, source_key="actions"):
    names = {str(name).lower() for name in action_names}
    total = 0.0
    for action in row.get(source_key) or []:
        if str(action.get("action_type", "")).lower() in names:
            total += _ads_float(action.get("value"))
    return total


def _meta_purchase_count(row):
    return _meta_action_total(
        row,
        {
            "purchase",
            "omni_purchase",
            "onsite_conversion.purchase",
            "offsite_conversion.fb_pixel_purchase",
        },
    )


def _meta_purchase_value(row):
    return _meta_action_total(
        row,
        {
            "purchase",
            "omni_purchase",
            "onsite_conversion.purchase",
            "offsite_conversion.fb_pixel_purchase",
        },
        source_key="action_values",
    )


def _meta_purchase_roas(row):
    for item in row.get("purchase_roas") or []:
        value = _ads_float(item.get("value"))
        if value:
            return value
    return 0.0


def _meta_add_to_cart(row):
    return _meta_action_total(
        row,
        {
            "add_to_cart",
            "omni_add_to_cart",
            "onsite_conversion.add_to_cart",
            "offsite_conversion.fb_pixel_add_to_cart",
        },
    )


def _meta_initiate_checkout(row):
    return _meta_action_total(
        row,
        {
            "initiate_checkout",
            "omni_initiated_checkout",
            "onsite_conversion.initiate_checkout",
            "offsite_conversion.fb_pixel_initiate_checkout",
        },
    )


def _ads_insert_action_log(cur, action_type, status, summary, context=None):
    cur.execute(
        """
        INSERT INTO ads_action_log(action_type, status, summary, context)
        VALUES (%s, %s, %s, %s::jsonb)
        """,
        (str(action_type or ""), str(status or ""), str(summary or ""), json_dumps(context or {})),
    )


def start_ads_sync_log(source="meta_ads_api", sync_type="manual", date_range=""):
    ensure_ads_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ads_sync_logs(source, sync_type, date_range, started_at, status)
                VALUES (%s, %s, %s, now(), 'started')
                RETURNING id
                """,
                (str(source or "meta_ads_api"), str(sync_type or "manual"), str(date_range or "")),
            )
            row = cur.fetchone() or {}
        conn.commit()
    return row.get("id")


def finish_ads_sync_log(
    log_id=None,
    *,
    source="meta_ads_api",
    sync_type="manual",
    date_range="",
    status="success",
    rows_fetched=0,
    rows_upserted=0,
    error_message="",
    context=None,
):
    ensure_ads_schema()
    safe_error = sanitize_ads_error(error_message)
    with connect() as conn:
        with conn.cursor() as cur:
            if log_id:
                cur.execute(
                    """
                    UPDATE ads_sync_logs
                    SET finished_at=now(),
                        status=%s,
                        rows_fetched=%s,
                        rows_upserted=%s,
                        error_message=%s,
                        context=%s::jsonb
                    WHERE id=%s
                    """,
                    (
                        str(status or "success"),
                        int(rows_fetched or 0),
                        int(rows_upserted or 0),
                        safe_error,
                        json_dumps(context or {}),
                        log_id,
                    ),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO ads_sync_logs(
                        source, sync_type, date_range, started_at, finished_at, status,
                        rows_fetched, rows_upserted, error_message, context
                    )
                    VALUES (%s, %s, %s, now(), now(), %s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        str(source or "meta_ads_api"),
                        str(sync_type or "manual"),
                        str(date_range or ""),
                        str(status or "success"),
                        int(rows_fetched or 0),
                        int(rows_upserted or 0),
                        safe_error,
                        json_dumps(context or {}),
                    ),
                )
        conn.commit()


def list_ads_sync_logs(limit=50):
    if not is_configured():
        return []
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM ads_sync_logs ORDER BY started_at DESC LIMIT %s", (int(limit or 50),))
                return cur.fetchall()
    except Exception:
        return []


def get_latest_ads_sync_log():
    if not is_configured():
        return {}
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM ads_sync_logs
                    ORDER BY COALESCE(finished_at, started_at) DESC, id DESC
                    LIMIT 1
                    """
                )
                return cur.fetchone() or {}
    except Exception:
        return {}


def ads_table_counts():
    tables = (
        "meta_ad_accounts",
        "meta_campaigns",
        "meta_adsets",
        "meta_ads",
        "meta_creatives",
        "meta_ad_insights_daily",
        "meta_ad_insights_country_daily",
        "meta_ad_insights_age_gender_daily",
        "meta_ad_insights_platform_daily",
        "ads_sync_logs",
    )
    counts = {table: 0 for table in tables}
    counts["meta_creatives_primary_text_populated"] = 0
    counts["meta_creatives_headline_populated"] = 0
    if not is_configured():
        return counts
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                for table in tables:
                    if not table_exists(cur, table):
                        continue
                    cur.execute(f"SELECT COUNT(*) AS count FROM {table}")
                    counts[table] = int((cur.fetchone() or {}).get("count") or 0)
                if table_exists(cur, "meta_creatives"):
                    cur.execute("SELECT COUNT(*) AS count FROM meta_creatives WHERE COALESCE(primary_text, '') <> ''")
                    counts["meta_creatives_primary_text_populated"] = int((cur.fetchone() or {}).get("count") or 0)
                    cur.execute("SELECT COUNT(*) AS count FROM meta_creatives WHERE COALESCE(headline, '') <> ''")
                    counts["meta_creatives_headline_populated"] = int((cur.fetchone() or {}).get("count") or 0)
    except Exception:
        pass
    return counts


def record_ads_sync_error(message, context=None):
    if not is_configured():
        return
    try:
        ensure_ads_schema()
        safe_message = sanitize_ads_error(message or "Unknown Meta sync error")
        set_app_setting(ADS_LAST_SYNC_ERROR_KEY, safe_message)
        with connect() as conn:
            with conn.cursor() as cur:
                _ads_insert_action_log(cur, "meta_sync", "error", safe_message or "Meta sync failed", context or {})
            conn.commit()
        log_app_error("meta_ads_sync", safe_message or "Meta sync failed", context or {})
    except Exception:
        pass


def get_ads_sync_status_read_only():
    status = {
        "last_successful_sync": "",
        "last_sync_error": "",
        "last_sync_range": "",
    }
    if not is_configured():
        return status
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT key, value FROM app_settings WHERE key = ANY(%s)",
                    ([ADS_LAST_SUCCESSFUL_SYNC_KEY, ADS_LAST_SYNC_ERROR_KEY, ADS_LAST_SYNC_RANGE_KEY],),
                )
                for row in cur.fetchall():
                    value = row.get("value")
                    if isinstance(value, dict):
                        value = value.get("value", "")
                    if row.get("key") == ADS_LAST_SUCCESSFUL_SYNC_KEY:
                        status["last_successful_sync"] = value or ""
                    elif row.get("key") == ADS_LAST_SYNC_ERROR_KEY:
                        status["last_sync_error"] = value or ""
                    elif row.get("key") == ADS_LAST_SYNC_RANGE_KEY:
                        status["last_sync_range"] = value or ""
    except Exception:
        pass
    return status


def _first_ads_text(*values):
    for value in values:
        if isinstance(value, dict):
            value = value.get("text") or value.get("value") or value.get("name")
        if value not in (None, ""):
            return str(value)
    return ""


def _asset_values(asset_feed_spec, key):
    values = []
    for item in (asset_feed_spec or {}).get(key) or []:
        if isinstance(item, dict):
            value = item.get("text") or item.get("value") or item.get("name")
        else:
            value = item
        if value not in (None, ""):
            values.append(str(value))
    return values


def _extract_creative_fields(creative):
    creative = creative if isinstance(creative, dict) else {}
    story_spec = creative.get("object_story_spec") if isinstance(creative.get("object_story_spec"), dict) else {}
    asset_feed_spec = creative.get("asset_feed_spec") if isinstance(creative.get("asset_feed_spec"), dict) else {}
    link_data = story_spec.get("link_data") if isinstance(story_spec.get("link_data"), dict) else {}
    video_data = story_spec.get("video_data") if isinstance(story_spec.get("video_data"), dict) else {}
    photo_data = story_spec.get("photo_data") if isinstance(story_spec.get("photo_data"), dict) else {}
    call_to_action = link_data.get("call_to_action") if isinstance(link_data.get("call_to_action"), dict) else {}
    cta_value = call_to_action.get("value") if isinstance(call_to_action.get("value"), dict) else {}
    asset_texts = _asset_values(asset_feed_spec, "bodies")
    asset_titles = _asset_values(asset_feed_spec, "titles")
    asset_descriptions = _asset_values(asset_feed_spec, "descriptions")
    primary_text = _first_ads_text(
        creative.get("body"),
        link_data.get("message"),
        video_data.get("message"),
        photo_data.get("message"),
        asset_texts[0] if asset_texts else "",
    )
    headline = _first_ads_text(
        creative.get("title"),
        link_data.get("name"),
        video_data.get("title"),
        asset_titles[0] if asset_titles else "",
    )
    description = _first_ads_text(
        creative.get("description"),
        link_data.get("description"),
        asset_descriptions[0] if asset_descriptions else "",
    )
    video_id = _first_ads_text(creative.get("video_id"), video_data.get("video_id"))
    image_hash = _first_ads_text(creative.get("image_hash"), link_data.get("image_hash"), photo_data.get("image_hash"))
    image_url = _first_ads_text(creative.get("image_url"), link_data.get("picture"), creative.get("thumbnail_url"))
    link_url = _first_ads_text(creative.get("link_url"), link_data.get("link"), cta_value.get("link"))
    if asset_feed_spec:
        creative_format = "dynamic creative"
    elif link_data.get("child_attachments"):
        creative_format = "carousel"
    elif video_id or video_data:
        creative_format = "video"
    elif image_hash or image_url or photo_data:
        creative_format = "image"
    else:
        creative_format = "unknown"
    return {
        "primary_text": primary_text,
        "headline": headline,
        "description": description,
        "call_to_action": _first_ads_text(creative.get("call_to_action_type"), call_to_action.get("type")),
        "link_url": link_url,
        "creative_format": creative_format,
        "image_url": image_url,
        "video_id": video_id,
        "image_hash": image_hash,
        "effective_object_story_id": _first_ads_text(
            creative.get("effective_object_story_id"),
            creative.get("object_story_id"),
        ),
        "object_story_spec": story_spec,
        "asset_feed_spec": asset_feed_spec,
        "asset_texts": asset_texts,
        "asset_titles": asset_titles,
        "asset_descriptions": asset_descriptions,
        "page_id": _first_ads_text(creative.get("page_id"), story_spec.get("page_id")),
        "instagram_actor_id": _first_ads_text(creative.get("instagram_actor_id"), story_spec.get("instagram_actor_id")),
    }


def save_meta_ads_sync(account=None, campaigns=None, adsets=None, ads=None, insights=None, date_range_label="", account_id=""):
    ensure_ads_schema()
    account = account or {}
    campaigns = campaigns or []
    adsets = adsets or []
    ads = ads or []
    insights = insights or []
    account_id = str(account.get("account_id") or account.get("id") or account_id or "").replace("act_", "")
    creative_count = 0
    started = time.perf_counter()
    with connect() as conn:
        with conn.cursor() as cur:
            if account_id:
                business = account.get("business") or {}
                cur.execute(
                    """
                    INSERT INTO meta_ad_accounts(
                        account_id, name, currency, timezone_name, account_status, business_name, raw, synced_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, now(), now())
                    ON CONFLICT (account_id) DO UPDATE SET
                        name=EXCLUDED.name,
                        currency=EXCLUDED.currency,
                        timezone_name=EXCLUDED.timezone_name,
                        account_status=EXCLUDED.account_status,
                        business_name=EXCLUDED.business_name,
                        raw=EXCLUDED.raw,
                        synced_at=now(),
                        updated_at=now()
                    """,
                    (
                        account_id,
                        account.get("name"),
                        account.get("currency"),
                        account.get("timezone_name"),
                        str(account.get("account_status") or ""),
                        business.get("name") if isinstance(business, dict) else "",
                        json_dumps(account),
                    ),
                )
            for campaign in campaigns:
                cur.execute(
                    """
                    INSERT INTO meta_campaigns(
                        campaign_id, account_id, campaign_name, status, effective_status, objective,
                        meta_created_at, meta_updated_at, raw, synced_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, now(), now())
                    ON CONFLICT (campaign_id) DO UPDATE SET
                        account_id=EXCLUDED.account_id,
                        campaign_name=EXCLUDED.campaign_name,
                        status=EXCLUDED.status,
                        effective_status=EXCLUDED.effective_status,
                        objective=EXCLUDED.objective,
                        meta_created_at=EXCLUDED.meta_created_at,
                        meta_updated_at=EXCLUDED.meta_updated_at,
                        raw=EXCLUDED.raw,
                        synced_at=now(),
                        updated_at=now()
                    """,
                    (
                        campaign.get("id"),
                        account_id,
                        campaign.get("name"),
                        campaign.get("status"),
                        campaign.get("effective_status"),
                        campaign.get("objective"),
                        campaign.get("created_time"),
                        campaign.get("updated_time"),
                        json_dumps(campaign),
                    ),
                )
            for adset in adsets:
                cur.execute(
                    """
                    INSERT INTO meta_adsets(
                        adset_id, account_id, campaign_id, adset_name, status, effective_status,
                        optimization_goal, billing_event, daily_budget, lifetime_budget,
                        meta_created_at, meta_updated_at, raw, synced_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, now(), now())
                    ON CONFLICT (adset_id) DO UPDATE SET
                        account_id=EXCLUDED.account_id,
                        campaign_id=EXCLUDED.campaign_id,
                        adset_name=EXCLUDED.adset_name,
                        status=EXCLUDED.status,
                        effective_status=EXCLUDED.effective_status,
                        optimization_goal=EXCLUDED.optimization_goal,
                        billing_event=EXCLUDED.billing_event,
                        daily_budget=EXCLUDED.daily_budget,
                        lifetime_budget=EXCLUDED.lifetime_budget,
                        meta_created_at=EXCLUDED.meta_created_at,
                        meta_updated_at=EXCLUDED.meta_updated_at,
                        raw=EXCLUDED.raw,
                        synced_at=now(),
                        updated_at=now()
                    """,
                    (
                        adset.get("id"),
                        account_id,
                        adset.get("campaign_id"),
                        adset.get("name"),
                        adset.get("status"),
                        adset.get("effective_status"),
                        adset.get("optimization_goal"),
                        adset.get("billing_event"),
                        _ads_float(adset.get("daily_budget")),
                        _ads_float(adset.get("lifetime_budget")),
                        adset.get("created_time"),
                        adset.get("updated_time"),
                        json_dumps(adset),
                    ),
                )
            for ad in ads:
                creative = ad.get("creative") or {}
                if not isinstance(creative, dict):
                    creative = {"id": str(creative or "")}
                creative_id = creative.get("id")
                cur.execute(
                    """
                    INSERT INTO meta_ads(
                        ad_id, account_id, campaign_id, adset_id, ad_name, status, effective_status,
                        creative_id, meta_created_at, meta_updated_at, raw, synced_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, now(), now())
                    ON CONFLICT (ad_id) DO UPDATE SET
                        account_id=EXCLUDED.account_id,
                        campaign_id=EXCLUDED.campaign_id,
                        adset_id=EXCLUDED.adset_id,
                        ad_name=EXCLUDED.ad_name,
                        status=EXCLUDED.status,
                        effective_status=EXCLUDED.effective_status,
                        creative_id=EXCLUDED.creative_id,
                        meta_created_at=EXCLUDED.meta_created_at,
                        meta_updated_at=EXCLUDED.meta_updated_at,
                        raw=EXCLUDED.raw,
                        synced_at=now(),
                        updated_at=now()
                    """,
                    (
                        ad.get("id"),
                        account_id,
                        ad.get("campaign_id"),
                        ad.get("adset_id"),
                        ad.get("name"),
                        ad.get("status"),
                        ad.get("effective_status"),
                        creative_id,
                        ad.get("created_time"),
                        ad.get("updated_time"),
                        json_dumps(ad),
                    ),
                )
                if creative_id:
                    creative_count += 1
                    creative_fields = _extract_creative_fields(creative)
                    cur.execute(
                        """
                        INSERT INTO meta_creatives(
                            creative_id, ad_id, account_id, name, thumbnail_url, object_story_id,
                            effective_object_story_id, object_story_spec, asset_feed_spec,
                            call_to_action, link_url, page_id, instagram_actor_id, primary_text,
                            headline, description, creative_format, image_url, video_id, image_hash,
                            asset_texts, asset_titles, asset_descriptions, raw, synced_at, updated_at
                        )
                        VALUES (
                            %s, %s, %s, %s, %s, %s,
                            %s, %s::jsonb, %s::jsonb,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s,
                            %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, now(), now()
                        )
                        ON CONFLICT (creative_id) DO UPDATE SET
                            ad_id=EXCLUDED.ad_id,
                            account_id=EXCLUDED.account_id,
                            name=EXCLUDED.name,
                            thumbnail_url=EXCLUDED.thumbnail_url,
                            object_story_id=EXCLUDED.object_story_id,
                            effective_object_story_id=EXCLUDED.effective_object_story_id,
                            object_story_spec=EXCLUDED.object_story_spec,
                            asset_feed_spec=EXCLUDED.asset_feed_spec,
                            call_to_action=EXCLUDED.call_to_action,
                            link_url=EXCLUDED.link_url,
                            page_id=EXCLUDED.page_id,
                            instagram_actor_id=EXCLUDED.instagram_actor_id,
                            primary_text=EXCLUDED.primary_text,
                            headline=EXCLUDED.headline,
                            description=EXCLUDED.description,
                            creative_format=EXCLUDED.creative_format,
                            image_url=EXCLUDED.image_url,
                            video_id=EXCLUDED.video_id,
                            image_hash=EXCLUDED.image_hash,
                            asset_texts=EXCLUDED.asset_texts,
                            asset_titles=EXCLUDED.asset_titles,
                            asset_descriptions=EXCLUDED.asset_descriptions,
                            raw=EXCLUDED.raw,
                            synced_at=now(),
                            updated_at=now()
                        """,
                        (
                            creative_id,
                            ad.get("id"),
                            account_id,
                            creative.get("name"),
                            creative.get("thumbnail_url"),
                            creative.get("object_story_id"),
                            creative_fields["effective_object_story_id"],
                            json_dumps(creative_fields["object_story_spec"]),
                            json_dumps(creative_fields["asset_feed_spec"]),
                            creative_fields["call_to_action"],
                            creative_fields["link_url"],
                            creative_fields["page_id"],
                            creative_fields["instagram_actor_id"],
                            creative_fields["primary_text"],
                            creative_fields["headline"],
                            creative_fields["description"],
                            creative_fields["creative_format"],
                            creative_fields["image_url"],
                            creative_fields["video_id"],
                            creative_fields["image_hash"],
                            json_dumps(creative_fields["asset_texts"]),
                            json_dumps(creative_fields["asset_titles"]),
                            json_dumps(creative_fields["asset_descriptions"]),
                            json_dumps(creative),
                        ),
                    )
            for insight in insights:
                spend = _ads_float(insight.get("spend"))
                purchases = _meta_purchase_count(insight)
                purchase_value = _meta_purchase_value(insight)
                add_to_cart = _meta_add_to_cart(insight)
                initiate_checkout = _meta_initiate_checkout(insight)
                cost_per_purchase = spend / purchases if purchases else 0
                roas = _meta_purchase_roas(insight) or (purchase_value / spend if spend else 0)
                placement = " / ".join(
                    part
                    for part in (
                        insight.get("publisher_platform"),
                        insight.get("platform_position"),
                    )
                    if part
                )
                cur.execute(
                    """
                    INSERT INTO meta_ad_insights_daily(
                        date, account_id, campaign_id, campaign_name, adset_id, adset_name, ad_id, ad_name,
                        spend, impressions, reach, clicks, inline_link_clicks, ctr, cpc, cpm, frequency,
                        purchases, purchase_value, cost_per_purchase, roas, add_to_cart, initiate_checkout,
                        country, placement, raw, synced_at, updated_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s::jsonb, now(), now()
                    )
                    ON CONFLICT (date, ad_id, country, placement) DO UPDATE SET
                        account_id=EXCLUDED.account_id,
                        campaign_id=EXCLUDED.campaign_id,
                        campaign_name=EXCLUDED.campaign_name,
                        adset_id=EXCLUDED.adset_id,
                        adset_name=EXCLUDED.adset_name,
                        ad_name=EXCLUDED.ad_name,
                        spend=EXCLUDED.spend,
                        impressions=EXCLUDED.impressions,
                        reach=EXCLUDED.reach,
                        clicks=EXCLUDED.clicks,
                        inline_link_clicks=EXCLUDED.inline_link_clicks,
                        ctr=EXCLUDED.ctr,
                        cpc=EXCLUDED.cpc,
                        cpm=EXCLUDED.cpm,
                        frequency=EXCLUDED.frequency,
                        purchases=EXCLUDED.purchases,
                        purchase_value=EXCLUDED.purchase_value,
                        cost_per_purchase=EXCLUDED.cost_per_purchase,
                        roas=EXCLUDED.roas,
                        add_to_cart=EXCLUDED.add_to_cart,
                        initiate_checkout=EXCLUDED.initiate_checkout,
                        raw=EXCLUDED.raw,
                        synced_at=now(),
                        updated_at=now()
                    """,
                    (
                        insight.get("date_start") or insight.get("date_stop"),
                        str(insight.get("account_id") or account_id).replace("act_", ""),
                        insight.get("campaign_id"),
                        insight.get("campaign_name"),
                        insight.get("adset_id"),
                        insight.get("adset_name"),
                        insight.get("ad_id"),
                        insight.get("ad_name"),
                        spend,
                        _ads_int(insight.get("impressions")),
                        _ads_int(insight.get("reach")),
                        _ads_int(insight.get("clicks")),
                        _ads_int(insight.get("inline_link_clicks")),
                        _ads_float(insight.get("ctr")),
                        _ads_float(insight.get("cpc")),
                        _ads_float(insight.get("cpm")),
                        _ads_float(insight.get("frequency")),
                        purchases,
                        purchase_value,
                        cost_per_purchase,
                        roas,
                        add_to_cart,
                        initiate_checkout,
                        insight.get("country") or "",
                        placement or "",
                        json_dumps(insight),
                    ),
                )
            _ads_insert_action_log(
                cur,
                "meta_sync",
                "success",
                f"Synced Meta Ads data for {date_range_label or 'selected range'}",
                {
                    "account_id": account_id,
                    "campaigns": len(campaigns),
                    "adsets": len(adsets),
                    "ads": len(ads),
                    "creatives": creative_count,
                    "insights": len(insights),
                    "rows_upserted": (1 if account_id else 0) + len(campaigns) + len(adsets) + len(ads) + creative_count + len(insights),
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                },
            )
        conn.commit()
    success_at = _datetime_to_setting(utc_now_datetime())
    set_app_setting(ADS_LAST_SUCCESSFUL_SYNC_KEY, success_at)
    set_app_setting(ADS_LAST_SYNC_ERROR_KEY, "")
    set_app_setting(ADS_LAST_SYNC_RANGE_KEY, date_range_label or "")
    return {
        "campaigns": len(campaigns),
        "adsets": len(adsets),
        "ads": len(ads),
        "creatives": creative_count,
        "insights": len(insights),
        "rows_upserted": (1 if account_id else 0) + len(campaigns) + len(adsets) + len(ads) + creative_count + len(insights),
        "last_successful_sync": success_at,
        "duration_ms": int((time.perf_counter() - started) * 1000),
    }


ADS_BREAKDOWN_TABLES = {
    "country": {
        "table": "meta_ad_insights_country_daily",
        "extra_columns": ("country",),
        "conflict": "date, ad_id, country",
    },
    "age_gender": {
        "table": "meta_ad_insights_age_gender_daily",
        "extra_columns": ("age", "gender"),
        "conflict": "date, ad_id, age, gender",
    },
    "platform": {
        "table": "meta_ad_insights_platform_daily",
        "extra_columns": ("publisher_platform", "platform_position"),
        "conflict": "date, ad_id, publisher_platform, platform_position",
    },
}


def save_meta_ads_breakdown_insights(kind, insights=None, account_id="", date_range_label=""):
    ensure_ads_schema()
    config = ADS_BREAKDOWN_TABLES.get(kind)
    if not config:
        raise ValueError(f"Unknown Meta Ads breakdown kind: {kind}")
    insights = insights or []
    account_id = str(account_id or "").replace("act_", "")
    table = config["table"]
    extra_columns = config["extra_columns"]
    conflict = config["conflict"]
    started = time.perf_counter()
    common_columns = (
        "date",
        "account_id",
        "campaign_id",
        "campaign_name",
        "adset_id",
        "adset_name",
        "ad_id",
        "ad_name",
    )
    metric_columns = (
        "spend",
        "impressions",
        "reach",
        "clicks",
        "inline_link_clicks",
        "ctr",
        "cpc",
        "cpm",
        "frequency",
        "purchases",
        "purchase_value",
        "cost_per_purchase",
        "roas",
        "add_to_cart",
        "initiate_checkout",
        "raw",
    )
    columns = common_columns + extra_columns + metric_columns
    placeholders = ", ".join(["%s"] * (len(columns) - 1) + ["%s::jsonb"])
    update_columns = [column for column in columns if column not in {"date", "ad_id", *extra_columns}]
    update_sql = ",\n                        ".join(f"{column}=EXCLUDED.{column}" for column in update_columns)
    with connect() as conn:
        with conn.cursor() as cur:
            for insight in insights:
                spend = _ads_float(insight.get("spend"))
                purchases = _meta_purchase_count(insight)
                purchase_value = _meta_purchase_value(insight)
                add_to_cart = _meta_add_to_cart(insight)
                initiate_checkout = _meta_initiate_checkout(insight)
                cost_per_purchase = spend / purchases if purchases else 0
                roas = _meta_purchase_roas(insight) or (purchase_value / spend if spend else 0)
                values = [
                    insight.get("date_start") or insight.get("date_stop"),
                    str(insight.get("account_id") or account_id).replace("act_", ""),
                    insight.get("campaign_id"),
                    insight.get("campaign_name"),
                    insight.get("adset_id"),
                    insight.get("adset_name"),
                    insight.get("ad_id"),
                    insight.get("ad_name"),
                ]
                values.extend(str(insight.get(column) or "") for column in extra_columns)
                values.extend(
                    [
                        spend,
                        _ads_int(insight.get("impressions")),
                        _ads_int(insight.get("reach")),
                        _ads_int(insight.get("clicks")),
                        _ads_int(insight.get("inline_link_clicks")),
                        _ads_float(insight.get("ctr")),
                        _ads_float(insight.get("cpc")),
                        _ads_float(insight.get("cpm")),
                        _ads_float(insight.get("frequency")),
                        purchases,
                        purchase_value,
                        cost_per_purchase,
                        roas,
                        add_to_cart,
                        initiate_checkout,
                        json_dumps(insight),
                    ]
                )
                cur.execute(
                    f"""
                    INSERT INTO {table}({", ".join(columns)}, synced_at, updated_at)
                    VALUES ({placeholders}, now(), now())
                    ON CONFLICT ({conflict}) DO UPDATE SET
                        {update_sql},
                        synced_at=now(),
                        updated_at=now()
                    """,
                    values,
                )
            _ads_insert_action_log(
                cur,
                "meta_sync",
                "success",
                f"Synced Meta Ads {kind.replace('_', ' ')} breakdown for {date_range_label or 'selected range'}",
                {
                    "breakdown": kind,
                    "account_id": account_id,
                    "rows": len(insights),
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                },
            )
        conn.commit()
    return {"rows": len(insights), "rows_upserted": len(insights), "duration_ms": int((time.perf_counter() - started) * 1000)}


def _list_meta_breakdown_insights(kind, days=None, limit=5000, date_range="last_30_days"):
    config = ADS_BREAKDOWN_TABLES.get(kind)
    if not config or not is_configured():
        return []
    table = config["table"]
    date_where, date_params = _ads_date_where("i.date", date_range=date_range, days=days)
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT i.*, t.product_handle, t.product_title, t.sport, t.country_focus,
                           t.mockup_type, t.room_type, t.ad_angle, t.hook_style, t.creative_format AS tag_creative_format,
                           t.funnel_stage, t.notes AS tag_notes,
                           a.status AS ad_status, a.effective_status AS ad_effective_status,
                           c.primary_text, c.headline, c.description, c.call_to_action, c.link_url,
                           c.creative_format AS detected_creative_format, c.image_url, c.thumbnail_url
                    FROM {table} i
                    LEFT JOIN meta_creative_tags t ON t.ad_id = i.ad_id
                    LEFT JOIN meta_ads a ON a.ad_id = i.ad_id
                    LEFT JOIN meta_creatives c ON c.ad_id = i.ad_id
                    WHERE 1=1
                    {date_where}
                    ORDER BY i.date DESC, i.spend DESC
                    LIMIT %s
                    """,
                    (*date_params, int(limit or 5000)),
                )
                return cur.fetchall()
    except Exception:
        return []


def list_meta_ad_insights_country(days=None, limit=5000, date_range="last_30_days"):
    return _list_meta_breakdown_insights("country", days=days, limit=limit, date_range=date_range)


def list_meta_ad_insights_age_gender(days=None, limit=5000, date_range="last_30_days"):
    return _list_meta_breakdown_insights("age_gender", days=days, limit=limit, date_range=date_range)


def list_meta_ad_insights_platform(days=None, limit=5000, date_range="last_30_days"):
    return _list_meta_breakdown_insights("platform", days=days, limit=limit, date_range=date_range)


def list_meta_ad_insights(days=None, limit=5000, date_range="last_30_days"):
    if not is_configured():
        return []
    date_where, date_params = _ads_date_where("i.date", date_range=date_range, days=days)
    params = (*date_params, int(limit or 5000))
    new_query = """
        SELECT i.*, t.product_handle, t.product_title, t.sport, t.country_focus,
               t.mockup_type, t.room_type, t.ad_angle, t.hook_style, t.creative_format AS tag_creative_format,
               t.funnel_stage, t.notes AS tag_notes,
               a.status AS ad_status, a.effective_status AS ad_effective_status,
               c.primary_text, c.headline, c.description, c.call_to_action, c.link_url,
               c.creative_format AS detected_creative_format, c.image_url, c.thumbnail_url
        FROM meta_ad_insights_daily i
        LEFT JOIN meta_creative_tags t ON t.ad_id = i.ad_id
        LEFT JOIN meta_ads a ON a.ad_id = i.ad_id
        LEFT JOIN meta_creatives c ON c.ad_id = i.ad_id
        WHERE 1=1
        {date_where}
        ORDER BY i.date DESC, i.spend DESC
        LIMIT %s
    """.format(date_where=date_where)
    fallback_query = """
        SELECT i.*, t.product_handle, t.product_title, t.sport, t.country_focus,
               t.mockup_type, t.ad_angle, t.funnel_stage, t.notes AS tag_notes,
               a.status AS ad_status, a.effective_status AS ad_effective_status
        FROM meta_ad_insights_daily i
        LEFT JOIN meta_creative_tags t ON t.ad_id = i.ad_id
        LEFT JOIN meta_ads a ON a.ad_id = i.ad_id
        WHERE 1=1
        {date_where}
        ORDER BY i.date DESC, i.spend DESC
        LIMIT %s
    """.format(date_where=date_where)
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(new_query, params)
                return cur.fetchall()
    except Exception:
        try:
            with connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(fallback_query, params)
                    return cur.fetchall()
        except Exception:
            return []


def _ads_days_from_range(date_range="last_7_days"):
    text = str(date_range or "").strip().lower().replace("-", "_").replace(" ", "_")
    if text in {"all", "all_stored", "all_stored_data", "all_data"}:
        return None
    if "12" in text or "365" in text:
        return 365
    if "6_month" in text or "180" in text:
        return 180
    if "3_month" in text or "90" in text:
        return 90
    if "30" in text:
        return 30
    if "14" in text:
        return 14
    return 7


def _ads_resolve_days(*, date_range=None, days=None):
    if days in (None, ""):
        return _ads_days_from_range(date_range or "last_7_days")
    try:
        return max(int(days), 1)
    except (TypeError, ValueError):
        return _ads_days_from_range(date_range or "last_7_days")


def _ads_date_where(column_sql, *, date_range=None, days=None, prefix="AND"):
    resolved_days = _ads_resolve_days(date_range=date_range, days=days)
    if resolved_days is None:
        return "", []
    return f" {prefix} {column_sql} >= CURRENT_DATE - (%s::int - 1)", [resolved_days]


def _ads_normalize_text(value):
    text = str(value or "").lower().replace("'", "").replace("’", "")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    stop_words = {
        "ad",
        "ads",
        "copy",
        "creative",
        "carousel",
        "mockup",
        "mockups",
        "ia",
        "v1",
        "v2",
        "test",
        "new",
    }
    return " ".join(part for part in text.split() if part not in stop_words)


def _ads_keyword_tokens(value):
    return {part for part in _ads_normalize_text(value).split() if len(part) >= 4}


def list_recent_product_sales_by_handle(date_range="last_7_days", limit=500):
    if not is_configured():
        return []
    date_where, date_params = _ads_date_where(
        "COALESCE(o.processed_at, o.created_at, li.synced_at)::date",
        date_range=date_range,
    )
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    WITH line_rows AS (
                        SELECT
                            NULLIF(li.shopify_handle, '') AS product_handle,
                            MAX(NULLIF(li.product_title, '')) AS product_title,
                            COUNT(DISTINCT li.shopify_order_id) AS total_orders,
                            SUM(COALESCE(li.quantity, 1)) AS total_units,
                            MAX(COALESCE(o.processed_at, o.created_at)) AS latest_order_date,
                            SUM(
                                CASE
                                    WHEN COALESCE(li.raw_json->>'price', '') ~ '^[0-9]+(\\.[0-9]+)?$'
                                    THEN (li.raw_json->>'price')::numeric * GREATEST(COALESCE(li.quantity, 1), 1)
                                    ELSE NULL
                                END
                            ) AS total_revenue
                        FROM shopify_order_lines li
                        LEFT JOIN shopify_orders o ON o.shopify_order_id = li.shopify_order_id
                        WHERE 1=1
                          {date_where}
                          AND (COALESCE(li.shopify_handle, '') <> '' OR COALESCE(li.product_title, '') <> '')
                        GROUP BY NULLIF(li.shopify_handle, '')
                    )
                    SELECT *
                    FROM line_rows
                    ORDER BY total_orders DESC NULLS LAST, latest_order_date DESC NULLS LAST
                    LIMIT %s
                    """,
                    (*date_params, int(limit or 500)),
                )
                return cur.fetchall()
    except Exception:
        return []


def list_product_edition_summary():
    if not is_configured():
        return []
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        ep.shopify_handle AS product_handle,
                        ep.product_title,
                        ep.shopify_product_id,
                        ep.edition_total,
                        ep.next_edition_number,
                        GREATEST(COALESCE(ep.edition_total, 0) - COALESCE(ep.next_edition_number, 1) + 1, 0) AS edition_remaining,
                        COALESCE(ep.is_active, ep.active, TRUE) AS is_active,
                        COALESCE(ep.is_sold_out, ep.sold_out, FALSE) AS is_sold_out,
                        ep.edition_status
                    FROM edition_products ep
                    WHERE COALESCE(ep.shopify_handle, '') <> '' OR COALESCE(ep.product_title, '') <> ''
                    ORDER BY ep.product_title NULLS LAST, ep.shopify_handle NULLS LAST
                    LIMIT 1000
                    """
                )
                return cur.fetchall()
    except Exception:
        return []


def list_ads_product_candidates(limit=500):
    if not is_configured():
        return []
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    WITH sales AS (
                        SELECT
                            NULLIF(li.shopify_handle, '') AS product_handle,
                            MAX(NULLIF(li.product_title, '')) AS sales_product_title,
                            COUNT(DISTINCT li.shopify_order_id) AS total_orders,
                            SUM(COALESCE(li.quantity, 1)) AS total_units,
                            MAX(COALESCE(o.processed_at, o.created_at)) AS latest_order_date,
                            SUM(
                                CASE
                                    WHEN COALESCE(li.raw_json->>'price', '') ~ '^[0-9]+(\\.[0-9]+)?$'
                                    THEN (li.raw_json->>'price')::numeric * GREATEST(COALESCE(li.quantity, 1), 1)
                                    ELSE NULL
                                END
                            ) AS total_revenue
                        FROM shopify_order_lines li
                        LEFT JOIN shopify_orders o ON o.shopify_order_id = li.shopify_order_id
                        WHERE COALESCE(li.shopify_handle, '') <> '' OR COALESCE(li.product_title, '') <> ''
                        GROUP BY NULLIF(li.shopify_handle, '')
                    ),
                    edition_candidates AS (
                        SELECT
                            ep.shopify_handle AS product_handle,
                            ep.product_title,
                            ep.shopify_product_id,
                            ep.edition_total,
                            ep.next_edition_number,
                            GREATEST(COALESCE(ep.edition_total, 0) - COALESCE(ep.next_edition_number, 1) + 1, 0) AS edition_remaining,
                            COALESCE(ep.is_active, ep.active, TRUE) AS is_active,
                            COALESCE(ep.is_sold_out, ep.sold_out, FALSE) AS is_sold_out,
                            ep.edition_status,
                            s.total_orders,
                            s.total_units,
                            s.total_revenue,
                            s.latest_order_date
                        FROM edition_products ep
                        LEFT JOIN sales s ON s.product_handle = ep.shopify_handle
                    ),
                    order_only_candidates AS (
                        SELECT
                            s.product_handle,
                            s.sales_product_title AS product_title,
                            NULL::TEXT AS shopify_product_id,
                            NULL::INTEGER AS edition_total,
                            NULL::INTEGER AS next_edition_number,
                            NULL::INTEGER AS edition_remaining,
                            NULL::BOOLEAN AS is_active,
                            NULL::BOOLEAN AS is_sold_out,
                            NULL::TEXT AS edition_status,
                            s.total_orders,
                            s.total_units,
                            s.total_revenue,
                            s.latest_order_date
                        FROM sales s
                        LEFT JOIN edition_products ep ON ep.shopify_handle = s.product_handle
                        WHERE ep.shopify_handle IS NULL
                    )
                    SELECT *
                    FROM (
                        SELECT * FROM edition_candidates
                        UNION ALL
                        SELECT * FROM order_only_candidates
                    ) candidates
                    WHERE COALESCE(product_handle, '') <> '' OR COALESCE(product_title, '') <> ''
                    ORDER BY total_orders DESC NULLS LAST, product_title NULLS LAST, product_handle NULLS LAST
                    LIMIT %s
                    """,
                    (int(limit or 500),),
                )
                return cur.fetchall()
    except Exception:
        return []


def _score_product_candidate_for_ad(candidate, combined_text):
    handle = str(candidate.get("product_handle") or "")
    title = str(candidate.get("product_title") or "")
    handle_norm = _ads_normalize_text(handle)
    title_norm = _ads_normalize_text(title)
    text_norm = _ads_normalize_text(combined_text)
    if handle_norm and (handle_norm == text_norm or handle_norm in text_norm):
        return 1.0, "Exact handle match"
    if title_norm and (title_norm == text_norm or title_norm in text_norm):
        return 0.9, "Exact product title match"
    title_tokens = _ads_keyword_tokens(title)
    text_tokens = _ads_keyword_tokens(text_norm)
    overlap = title_tokens & text_tokens
    if len(overlap) >= 2:
        return 0.75, f"Strong keyword match: {', '.join(sorted(overlap)[:5])}"
    if len(overlap) == 1 and len(next(iter(overlap))) >= 6:
        return 0.6, f"Keyword match: {next(iter(overlap))}"
    return 0.0, ""


def _known_ads_product_pattern_terms(combined_text):
    text = str(combined_text or "").upper()
    patterns = []
    if "BRUNSEN" in text or "KNICKS" in text:
        patterns.append(("brunson knicks", "Known pattern: BRUNSEN / Knicks"))
    if "LAP OF GOD" in text or "LAP OF THE GOD" in text:
        patterns.append(("lap gods", "Known pattern: Lap of the Gods"))
    if "MESSI" in text:
        patterns.append(("messi", "Known pattern: Messi"))
    if "RONALDO" in text:
        patterns.append(("ronaldo", "Known pattern: Ronaldo"))
    if "LEGENDS" in text:
        patterns.append(("legends football soccer", "Known pattern: Legends, needs review if ambiguous"))
    if "UFC" in text or "GAETHJE" in text:
        patterns.append(("ufc gaethje", "Known pattern: UFC / Gaethje"))
    if any(term in text for term in ("BROCK", "BATHURST", "LOWNDES", "WHINCUP")):
        patterns.append(("brock bathurst lowndes whincup motorsport", "Known pattern: motorsport"))
    if any(term in text for term in ("KOBE", "JORDAN", "GOAT")):
        patterns.append(("kobe jordan goat basketball", "Known pattern: basketball / GOAT"))
    return patterns


def _suggest_product_mapping_for_text(combined_text, candidates):
    scored = []
    for candidate in candidates or []:
        score, reason = _score_product_candidate_for_ad(candidate, combined_text)
        if score:
            scored.append((score, reason, candidate))
    if not scored:
        for pattern_terms, reason in _known_ads_product_pattern_terms(combined_text):
            pattern_tokens = _ads_keyword_tokens(pattern_terms)
            pattern_matches = []
            for candidate in candidates or []:
                candidate_text = f"{candidate.get('product_handle') or ''} {candidate.get('product_title') or ''}"
                candidate_tokens = _ads_keyword_tokens(candidate_text)
                overlap = pattern_tokens & candidate_tokens
                if overlap:
                    pattern_matches.append((len(overlap), candidate))
            pattern_matches = sorted(pattern_matches, key=lambda item: item[0], reverse=True)
            if pattern_matches:
                top_overlap = pattern_matches[0][0]
                top_candidates = [candidate for overlap, candidate in pattern_matches if overlap == top_overlap]
                confidence = 0.75 if len(top_candidates) == 1 else 0.5
                return {
                    "product_handle": top_candidates[0].get("product_handle") or "",
                    "product_title": top_candidates[0].get("product_title") or "",
                    "confidence": confidence,
                    "status": "suggested" if confidence >= 0.75 else "needs_review",
                    "reason": reason if len(top_candidates) == 1 else f"{reason}; multiple possible products",
                    "candidate_count": len(top_candidates),
                }
    if scored:
        scored = sorted(scored, key=lambda item: item[0], reverse=True)
        top_score = scored[0][0]
        top = [item for item in scored if item[0] == top_score]
        candidate = top[0][2]
        status = "suggested" if top_score >= 0.75 and len(top) == 1 else "needs_review"
        if top_score < 0.5:
            status = "unmapped"
        return {
            "product_handle": candidate.get("product_handle") or "",
            "product_title": candidate.get("product_title") or "",
            "confidence": top_score,
            "status": status,
            "reason": top[0][1] if len(top) == 1 else f"{top[0][1]}; multiple possible products",
            "candidate_count": len(top),
        }
    return {
        "product_handle": "",
        "product_title": "",
        "confidence": 0.0,
        "status": "unmapped",
        "reason": "No strong product match found",
        "candidate_count": 0,
    }


def get_product_candidate_for_ad_name(ad_name, campaign_name=None, adset_name=None):
    candidates = list_ads_product_candidates(limit=500)
    combined_text = f"{ad_name or ''} {campaign_name or ''} {adset_name or ''}"
    return _suggest_product_mapping_for_text(combined_text, candidates)


def list_ads_product_mapping_status(date_range="last_7_days", limit=500):
    if not is_configured():
        return []
    date_where, date_params = _ads_date_where("date", date_range=date_range)
    params = (*date_params, int(limit or 500))
    new_query = f"""
        WITH recent AS (
            SELECT *
            FROM meta_ad_insights_daily
            WHERE 1=1
            {date_where}
        )
        SELECT
            a.ad_id,
            COALESCE(MAX(recent.ad_name), a.ad_name) AS ad_name,
            COALESCE(MAX(recent.campaign_name), MAX(c.campaign_name), '') AS campaign_name,
            COALESCE(MAX(recent.adset_name), MAX(s.adset_name), '') AS adset_name,
            MAX(a.creative_id) AS creative_id,
            MAX(cr.name) AS creative_name,
            COALESCE(MAX(m.mapping_status), CASE WHEN COALESCE(MAX(m.product_handle), MAX(t.product_handle), '') <> '' THEN 'confirmed' ELSE 'unmapped' END) AS mapping_status,
            COALESCE(MAX(m.product_handle), MAX(t.product_handle), '') AS product_handle,
            COALESCE(MAX(m.product_title), MAX(t.product_title), '') AS product_title,
            MAX(m.suggested_product_handle) AS suggested_product_handle,
            MAX(m.suggested_product_title) AS suggested_product_title,
            MAX(m.suggestion_confidence) AS suggestion_confidence,
            MAX(m.suggestion_reason) AS suggestion_reason,
            COALESCE(MAX(m.sport), MAX(t.sport), '') AS sport,
            COALESCE(MAX(m.country_focus), MAX(t.country_focus), '') AS country_focus,
            COALESCE(MAX(m.mockup_type), MAX(t.mockup_type), '') AS mockup_type,
            COALESCE(MAX(m.room_type), MAX(t.room_type), '') AS room_type,
            COALESCE(MAX(m.ad_angle), MAX(t.ad_angle), '') AS ad_angle,
            COALESCE(MAX(m.hook_style), MAX(t.hook_style), '') AS hook_style,
            COALESCE(MAX(m.creative_format), MAX(t.creative_format), MAX(cr.creative_format), '') AS creative_format,
            COALESCE(MAX(m.funnel_stage), MAX(t.funnel_stage), '') AS funnel_stage,
            COALESCE(MAX(m.notes), MAX(t.notes), '') AS notes,
            SUM(COALESCE(recent.spend, 0)) AS spend,
            SUM(COALESCE(recent.purchases, 0)) AS purchases,
            SUM(COALESCE(recent.purchase_value, 0)) AS purchase_value,
            SUM(COALESCE(recent.clicks, 0)) AS clicks,
            SUM(COALESCE(recent.impressions, 0)) AS impressions,
            CASE WHEN SUM(COALESCE(recent.spend, 0)) > 0 THEN SUM(COALESCE(recent.purchase_value, 0)) / SUM(COALESCE(recent.spend, 0)) ELSE 0 END AS roas,
            CASE WHEN SUM(COALESCE(recent.purchases, 0)) > 0 THEN SUM(COALESCE(recent.spend, 0)) / SUM(COALESCE(recent.purchases, 0)) ELSE 0 END AS cpa,
            CASE WHEN SUM(COALESCE(recent.impressions, 0)) > 0 THEN SUM(COALESCE(recent.clicks, 0)) / SUM(COALESCE(recent.impressions, 0)) * 100 ELSE 0 END AS ctr
        FROM meta_ads a
        LEFT JOIN recent ON recent.ad_id = a.ad_id
        LEFT JOIN meta_campaigns c ON c.campaign_id = a.campaign_id
        LEFT JOIN meta_adsets s ON s.adset_id = a.adset_id
        LEFT JOIN meta_creatives cr ON cr.ad_id = a.ad_id
        LEFT JOIN ads_product_mapping m ON m.ad_id = a.ad_id
        LEFT JOIN meta_creative_tags t ON t.ad_id = a.ad_id
        GROUP BY a.ad_id, a.ad_name
        ORDER BY spend DESC NULLS LAST, ad_name NULLS LAST
        LIMIT %s
    """
    fallback_query = f"""
        WITH recent AS (
            SELECT *
            FROM meta_ad_insights_daily
            WHERE 1=1
            {date_where}
        )
        SELECT
            a.ad_id,
            COALESCE(MAX(recent.ad_name), a.ad_name) AS ad_name,
            COALESCE(MAX(recent.campaign_name), MAX(c.campaign_name), '') AS campaign_name,
            COALESCE(MAX(recent.adset_name), MAX(s.adset_name), '') AS adset_name,
            MAX(a.creative_id) AS creative_id,
            COALESCE(MAX(t.product_handle), '') AS product_handle,
            COALESCE(MAX(t.product_title), '') AS product_title,
            CASE WHEN COALESCE(MAX(t.product_handle), MAX(t.product_title), '') <> '' THEN 'confirmed' ELSE 'unmapped' END AS mapping_status,
            '' AS suggested_product_handle,
            '' AS suggested_product_title,
            0 AS suggestion_confidence,
            '' AS suggestion_reason,
            COALESCE(MAX(t.sport), '') AS sport,
            COALESCE(MAX(t.country_focus), '') AS country_focus,
            COALESCE(MAX(t.mockup_type), '') AS mockup_type,
            '' AS room_type,
            COALESCE(MAX(t.ad_angle), '') AS ad_angle,
            '' AS hook_style,
            '' AS creative_format,
            COALESCE(MAX(t.funnel_stage), '') AS funnel_stage,
            COALESCE(MAX(t.notes), '') AS notes,
            SUM(COALESCE(recent.spend, 0)) AS spend,
            SUM(COALESCE(recent.purchases, 0)) AS purchases,
            SUM(COALESCE(recent.purchase_value, 0)) AS purchase_value,
            SUM(COALESCE(recent.clicks, 0)) AS clicks,
            SUM(COALESCE(recent.impressions, 0)) AS impressions,
            CASE WHEN SUM(COALESCE(recent.spend, 0)) > 0 THEN SUM(COALESCE(recent.purchase_value, 0)) / SUM(COALESCE(recent.spend, 0)) ELSE 0 END AS roas,
            CASE WHEN SUM(COALESCE(recent.purchases, 0)) > 0 THEN SUM(COALESCE(recent.spend, 0)) / SUM(COALESCE(recent.purchases, 0)) ELSE 0 END AS cpa,
            CASE WHEN SUM(COALESCE(recent.impressions, 0)) > 0 THEN SUM(COALESCE(recent.clicks, 0)) / SUM(COALESCE(recent.impressions, 0)) * 100 ELSE 0 END AS ctr
        FROM meta_ads a
        LEFT JOIN recent ON recent.ad_id = a.ad_id
        LEFT JOIN meta_campaigns c ON c.campaign_id = a.campaign_id
        LEFT JOIN meta_adsets s ON s.adset_id = a.adset_id
        LEFT JOIN meta_creative_tags t ON t.ad_id = a.ad_id
        GROUP BY a.ad_id, a.ad_name
        ORDER BY spend DESC NULLS LAST, ad_name NULLS LAST
        LIMIT %s
    """
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(new_query, params)
                return cur.fetchall()
    except Exception:
        try:
            with connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(fallback_query, params)
                    return cur.fetchall()
        except Exception:
            return []


def suggest_ads_product_mappings(limit=500):
    ensure_ads_schema()
    rows = list_ads_product_mapping_status(date_range="last_30_days", limit=limit)
    candidates = list_ads_product_candidates(limit=500)
    saved = []
    with connect() as conn:
        with conn.cursor() as cur:
            for row in rows:
                if row.get("product_handle") or str(row.get("mapping_status") or "").lower() == "confirmed":
                    continue
                suggestion = _suggest_product_mapping_for_text(
                    f"{row.get('ad_name') or ''} {row.get('campaign_name') or ''} {row.get('adset_name') or ''} {row.get('creative_name') or ''}",
                    candidates,
                )
                status = suggestion["status"]
                if status == "unmapped":
                    continue
                cur.execute(
                    """
                    INSERT INTO ads_product_mapping(
                        ad_id, product_handle, product_title, mapping_status,
                        suggested_product_handle, suggested_product_title,
                        suggestion_confidence, suggestion_reason, updated_at
                    )
                    VALUES (%s, '', '', %s, %s, %s, %s, %s, now())
                    ON CONFLICT (ad_id) DO UPDATE SET
                        mapping_status=CASE
                            WHEN COALESCE(ads_product_mapping.product_handle, '') <> '' THEN ads_product_mapping.mapping_status
                            ELSE EXCLUDED.mapping_status
                        END,
                        suggested_product_handle=EXCLUDED.suggested_product_handle,
                        suggested_product_title=EXCLUDED.suggested_product_title,
                        suggestion_confidence=EXCLUDED.suggestion_confidence,
                        suggestion_reason=EXCLUDED.suggestion_reason,
                        updated_at=now()
                    """,
                    (
                        row.get("ad_id"),
                        status,
                        suggestion["product_handle"],
                        suggestion["product_title"],
                        suggestion["confidence"],
                        suggestion["reason"],
                    ),
                )
                saved.append({"ad_id": row.get("ad_id"), **suggestion})
            _ads_insert_action_log(
                cur,
                "product_mapping",
                "suggested",
                f"Generated {len(saved)} Ads Intelligence product mapping suggestions",
                {"limit": int(limit or 500)},
            )
        conn.commit()
    return {"suggested": len(saved), "rows": saved}


def list_product_opportunities_from_ads(date_range="last_7_days"):
    ad_rows = list_ads_product_mapping_status(date_range=date_range, limit=500)
    sales_rows = list_recent_product_sales_by_handle(date_range=date_range, limit=500)
    edition_rows = list_product_edition_summary()
    sales_by_handle = {str(row.get("product_handle") or ""): row for row in sales_rows}
    edition_by_handle = {str(row.get("product_handle") or ""): row for row in edition_rows}
    products = {}
    for row in ad_rows:
        status = str(row.get("mapping_status") or "unmapped")
        handle = row.get("product_handle") or row.get("suggested_product_handle") or ""
        title = row.get("product_title") or row.get("suggested_product_title") or "Untagged"
        key = handle or title or "Untagged"
        item = products.setdefault(
            key,
            {
                "product_handle": handle,
                "product_title": title,
                "mapping_status": status if status else "unmapped",
                "mapped_ads": 0,
                "spend": 0.0,
                "purchases": 0.0,
                "purchase_value": 0.0,
                "clicks": 0.0,
                "impressions": 0.0,
            },
        )
        item["mapping_status"] = "confirmed" if status == "confirmed" else item["mapping_status"]
        item["mapped_ads"] += 1
        item["spend"] += _ads_float(row.get("spend"))
        item["purchases"] += _ads_float(row.get("purchases"))
        item["purchase_value"] += _ads_float(row.get("purchase_value"))
        item["clicks"] += _ads_float(row.get("clicks"))
        item["impressions"] += _ads_float(row.get("impressions"))
    for handle, sale in sales_by_handle.items():
        if not handle:
            continue
        item = products.setdefault(
            handle,
            {
                "product_handle": handle,
                "product_title": sale.get("product_title") or handle,
                "mapping_status": "no_meta_spend",
                "mapped_ads": 0,
                "spend": 0.0,
                "purchases": 0.0,
                "purchase_value": 0.0,
                "clicks": 0.0,
                "impressions": 0.0,
            },
        )
        item["product_title"] = item["product_title"] or sale.get("product_title") or handle
    output = []
    for item in products.values():
        handle = item.get("product_handle") or ""
        sales = sales_by_handle.get(handle) or {}
        edition = edition_by_handle.get(handle) or {}
        spend = item["spend"]
        purchases = item["purchases"]
        value = item["purchase_value"]
        clicks = item["clicks"]
        impressions = item["impressions"]
        roas = value / spend if spend else 0
        cpa = spend / purchases if purchases else 0
        ctr = clicks / impressions * 100 if impressions else 0
        edition_remaining = edition.get("edition_remaining")
        status = item["mapping_status"] or "unmapped"
        if status in {"unmapped", "suggested"} and item["spend"] > 0:
            recommendation = "Needs tagging"
        elif status == "needs_review":
            recommendation = "Needs review"
        elif edition_remaining not in (None, "") and _ads_int(edition_remaining) <= 10 and sales.get("total_orders"):
            recommendation = "Low editions, final push opportunity"
        elif item["mapped_ads"] <= 0 and sales.get("total_orders"):
            recommendation = "Product selling organically, needs ads"
        elif purchases >= 2 and roas >= 2.5:
            recommendation = "Scale product"
        elif spend >= 30 and clicks >= 25 and purchases <= 0:
            recommendation = "High Meta clicks, weak purchase"
        elif spend > 0 and purchases <= 0:
            recommendation = "Create new creative"
        else:
            recommendation = "Directional only"
        output.append(
            {
                "product_handle": handle,
                "product_title": item.get("product_title") or handle or "Untagged",
                "mapping_status": status,
                "mapped_ads": item["mapped_ads"],
                "meta_spend": spend,
                "meta_purchases": purchases,
                "meta_purchase_value": value,
                "meta_roas": roas,
                "meta_cpa": cpa,
                "meta_ctr": ctr,
                "actual_orders": sales.get("total_orders"),
                "actual_units": sales.get("total_units"),
                "actual_revenue": sales.get("total_revenue"),
                "latest_order_date": sales.get("latest_order_date"),
                "edition_remaining": edition_remaining,
                "edition_total": edition.get("edition_total"),
                "recommendation": recommendation,
            }
        )
    return sorted(output, key=lambda row: (_ads_float(row.get("meta_purchase_value")), _ads_float(row.get("meta_spend"))), reverse=True)


def ads_product_mapping_diagnostics():
    rows = list_ads_product_mapping_status(date_range="last_30_days", limit=1000)
    opportunities = list_product_opportunities_from_ads(date_range="last_30_days")
    candidates = list_ads_product_candidates(limit=1000)
    return {
        "product_candidate_count": len(candidates),
        "ads_without_mapping": sum(1 for row in rows if not (row.get("product_handle") or row.get("product_title"))),
        "suggested_mappings_count": sum(1 for row in rows if str(row.get("mapping_status") or "") == "suggested"),
        "confirmed_mappings_count": sum(1 for row in rows if str(row.get("mapping_status") or "") == "confirmed" or row.get("product_handle")),
        "needs_review_count": sum(1 for row in rows if str(row.get("mapping_status") or "") == "needs_review"),
        "products_with_meta_spend_no_confirmed_mapping": sum(
            1
            for row in opportunities
            if _ads_float(row.get("meta_spend")) > 0 and str(row.get("mapping_status") or "") != "confirmed"
        ),
        "products_with_orders_no_meta_spend": sum(
            1
            for row in opportunities
            if _ads_int(row.get("actual_orders")) > 0 and _ads_float(row.get("meta_spend")) <= 0
        ),
    }


def list_ads_creative_tags(limit=500):
    if not is_configured():
        return []
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM meta_creative_tags ORDER BY updated_at DESC LIMIT %s",
                    (int(limit or 500),),
                )
                return cur.fetchall()
    except Exception:
        return []


def upsert_ads_creative_tag(tag):
    ensure_ads_schema()
    tag = tag or {}
    ad_id = str(tag.get("ad_id") or "").strip()
    if not ad_id:
        raise ValueError("ad_id is required to save creative tags.")
    mapping_status = str(tag.get("mapping_status") or "").strip()
    if not mapping_status:
        mapping_status = "confirmed" if (tag.get("product_handle") or tag.get("product_title")) else "unmapped"
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO meta_creative_tags(
                    ad_id, creative_id, product_handle, product_title, sport, country_focus,
                    mockup_type, room_type, ad_angle, hook_style, creative_format, funnel_stage, notes, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (ad_id) DO UPDATE SET
                    creative_id=EXCLUDED.creative_id,
                    product_handle=EXCLUDED.product_handle,
                    product_title=EXCLUDED.product_title,
                    sport=EXCLUDED.sport,
                    country_focus=EXCLUDED.country_focus,
                    mockup_type=EXCLUDED.mockup_type,
                    room_type=EXCLUDED.room_type,
                    ad_angle=EXCLUDED.ad_angle,
                    hook_style=EXCLUDED.hook_style,
                    creative_format=EXCLUDED.creative_format,
                    funnel_stage=EXCLUDED.funnel_stage,
                    notes=EXCLUDED.notes,
                    updated_at=now()
                """,
                (
                    ad_id,
                    tag.get("creative_id"),
                    tag.get("product_handle"),
                    tag.get("product_title"),
                    tag.get("sport"),
                    tag.get("country_focus"),
                    tag.get("mockup_type"),
                    tag.get("room_type"),
                    tag.get("ad_angle"),
                    tag.get("hook_style"),
                    tag.get("creative_format"),
                    tag.get("funnel_stage"),
                    tag.get("notes"),
                ),
            )
            cur.execute(
                """
                INSERT INTO ads_product_mapping(
                    ad_id, product_handle, product_title, sport, country_focus, mockup_type,
                    room_type, ad_angle, hook_style, creative_format, funnel_stage, notes,
                    mapping_status, suggested_product_handle, suggested_product_title,
                    suggestion_confidence, suggestion_reason, confirmed_at, confirmed_by, updated_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    CASE WHEN %s='confirmed' THEN now() ELSE NULL END,
                    %s, now()
                )
                ON CONFLICT (ad_id) DO UPDATE SET
                    product_handle=EXCLUDED.product_handle,
                    product_title=EXCLUDED.product_title,
                    sport=EXCLUDED.sport,
                    country_focus=EXCLUDED.country_focus,
                    mockup_type=EXCLUDED.mockup_type,
                    room_type=EXCLUDED.room_type,
                    ad_angle=EXCLUDED.ad_angle,
                    hook_style=EXCLUDED.hook_style,
                    creative_format=EXCLUDED.creative_format,
                    funnel_stage=EXCLUDED.funnel_stage,
                    notes=EXCLUDED.notes,
                    mapping_status=EXCLUDED.mapping_status,
                    suggested_product_handle=EXCLUDED.suggested_product_handle,
                    suggested_product_title=EXCLUDED.suggested_product_title,
                    suggestion_confidence=EXCLUDED.suggestion_confidence,
                    suggestion_reason=EXCLUDED.suggestion_reason,
                    confirmed_at=CASE WHEN EXCLUDED.mapping_status='confirmed' THEN COALESCE(ads_product_mapping.confirmed_at, now()) ELSE ads_product_mapping.confirmed_at END,
                    confirmed_by=EXCLUDED.confirmed_by,
                    updated_at=now()
                """,
                (
                    ad_id,
                    tag.get("product_handle"),
                    tag.get("product_title"),
                    tag.get("sport"),
                    tag.get("country_focus"),
                    tag.get("mockup_type"),
                    tag.get("room_type"),
                    tag.get("ad_angle"),
                    tag.get("hook_style"),
                    tag.get("creative_format"),
                    tag.get("funnel_stage"),
                    tag.get("notes"),
                    mapping_status,
                    tag.get("suggested_product_handle"),
                    tag.get("suggested_product_title"),
                    _ads_float(tag.get("suggestion_confidence")),
                    tag.get("suggestion_reason"),
                    mapping_status,
                    tag.get("confirmed_by") or "sports_cave_os",
                ),
            )
            _ads_insert_action_log(
                cur,
                "creative_tag",
                "saved",
                f"Saved creative tags for ad {ad_id}",
                {key: value for key, value in tag.items() if key != "notes"},
            )
        conn.commit()
    return {"saved": True, "ad_id": ad_id}


def list_ads_action_log(limit=100, action_type=None):
    if not is_configured():
        return []
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                if action_type:
                    cur.execute(
                        "SELECT * FROM ads_action_log WHERE action_type=%s ORDER BY created_at DESC LIMIT %s",
                        (str(action_type), int(limit or 100)),
                    )
                else:
                    cur.execute("SELECT * FROM ads_action_log ORDER BY created_at DESC LIMIT %s", (int(limit or 100),))
                return cur.fetchall()
    except Exception:
        return []


def run_integrity_check():
    ensure_schema()
    results = {}
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT shopify_handle, edition_number, COUNT(*) AS count
                FROM edition_orders
                GROUP BY shopify_handle, edition_number
                HAVING COUNT(*) > 1
                ORDER BY shopify_handle, edition_number
                """
            )
            results["duplicate_edition_numbers"] = cur.fetchall()

            cur.execute(
                """
                SELECT eo.*
                FROM edition_orders eo
                WHERE COALESCE(eo.shopify_handle, '') = ''
                ORDER BY eo.assigned_at DESC
                """
            )
            results["missing_product_handle"] = cur.fetchall()

            cur.execute(
                """
                SELECT ep.shopify_handle, ep.product_title, ep.next_edition_number,
                       COALESCE(MAX(eo.edition_number), 0) AS max_assigned,
                       COALESCE(MAX(eo.edition_number), 0) + 1 AS expected_next
                FROM edition_products ep
                LEFT JOIN edition_orders eo ON eo.shopify_handle = ep.shopify_handle
                GROUP BY ep.shopify_handle, ep.product_title, ep.next_edition_number, ep.allow_counter_history_override
                HAVING COALESCE(ep.next_edition_number, 1) < COALESCE(MAX(eo.edition_number), 0) + 1
                   AND COALESCE(ep.allow_counter_history_override, FALSE) = FALSE
                ORDER BY ep.shopify_handle
                """
            )
            results["counter_lower_than_expected"] = cur.fetchall()

            cur.execute(
                """
                SELECT ep.shopify_handle, ep.product_title, ep.edition_total, ep.next_edition_number
                FROM edition_products ep
                WHERE COALESCE(ep.next_edition_number, 1) > COALESCE(ep.edition_total, 100)
                  AND COALESCE(ep.sold_out, FALSE) = FALSE
                ORDER BY ep.shopify_handle
                """
            )
            results["sold_out_not_marked"] = cur.fetchall()

            cur.execute(
                """
                SELECT ep.shopify_handle, ep.product_title, ep.edition_total, ep.next_edition_number
                FROM edition_products ep
                WHERE COALESCE(ep.edition_total, 100) - COALESCE(ep.next_edition_number, 1) + 1 < 0
                ORDER BY ep.shopify_handle
                """
            )
            results["negative_remaining"] = cur.fetchall()

            cur.execute(
                """
                SELECT *
                FROM webhook_events
                WHERE status ILIKE '%fail%' OR COALESCE(error_message, '') <> ''
                ORDER BY received_at DESC
                LIMIT 100
                """
            )
            results["failed_webhooks"] = cur.fetchall()

            cur.execute(
                """
                SELECT *
                FROM app_errors
                WHERE error_type ILIKE '%certificate%'
                ORDER BY created_at DESC
                LIMIT 100
                """
            )
            results["certificate_failures"] = cur.fetchall()

            cur.execute(
                """
                SELECT ep.shopify_handle, ep.product_title
                FROM edition_products ep
                LEFT JOIN product_assets pa
                  ON pa.shopify_handle=ep.shopify_handle
                 AND pa.asset_type='psd_master_file'
                 AND pa.is_primary IS DISTINCT FROM FALSE
                WHERE COALESCE(pa.asset_url, '') = ''
                ORDER BY ep.product_title NULLS LAST, ep.shopify_handle
                """
            )
            results["missing_psd_links"] = cur.fetchall()

            cur.execute(
                """
                WITH ordered AS (
                    SELECT shopify_handle,
                           edition_number,
                           LAG(edition_number) OVER (PARTITION BY shopify_handle ORDER BY edition_number) AS previous_number
                    FROM edition_orders
                    WHERE edition_number IS NOT NULL
                )
                SELECT shopify_handle, previous_number, edition_number
                FROM ordered
                WHERE previous_number IS NOT NULL
                  AND edition_number <> previous_number + 1
                ORDER BY shopify_handle, edition_number
                """
            )
            results["skipped_edition_numbers"] = cur.fetchall()
    return results


def export_orders_csv(rows):
    fields = (
        "order_name",
        "created_at",
        "customer_name",
        "customer_email",
        "financial_status",
        "fulfillment_status",
        "total_price",
        "currency",
        "product_title",
        "variant_title",
        "sku",
        "edition_number",
        "edition_total",
        "certificate_status",
        "psd_url",
        "prodigi_url",
        "admin_url",
    )
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in fields})
    return buffer.getvalue()


def export_products_csv(rows):
    asset_map = get_product_asset_map()
    fields = (
        "product_title",
        "shopify_handle",
        "shopify_product_id",
        "edition_total",
        "next_edition_number",
        "remaining_editions",
        "sold_count",
        "remaining_count",
        "edition_status",
        "edition_display_text",
        "metafields_sync_status",
        "metafields_synced_at",
        "active",
        "sold_out",
        *ASSET_TYPES,
        "admin_url",
        "online_store_url",
    )
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        record = {field: row.get(field, "") for field in fields}
        for asset_type in ASSET_TYPES:
            record[asset_type] = (asset_map.get(row.get("shopify_handle")) or {}).get(asset_type, "")
        writer.writerow(record)
    return buffer.getvalue()
