import csv
import gc
import io
import json
import os
import re
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import shopify_sync
from certificate_service import certificate_id, generate_certificate_pdf


BASE_DIR = Path(__file__).resolve().parent
CERTIFICATE_OUTPUT_DIR = BASE_DIR / "output" / "certificates"
PSD_MASTER_FOLDER_SETTING_KEY = "psd_master_folder_url"
LAST_SUCCESSFUL_ORDER_SYNC_KEY = "last_successful_order_sync_at"
LAST_ATTEMPTED_ORDER_SYNC_KEY = "last_attempted_order_sync_at"
EDITION_TRACKING_START_KEY = "edition_tracking_start_at"
LAST_SUCCESSFUL_PRODUCT_SYNC_KEY = "last_successful_product_sync_at"
LAST_ATTEMPTED_PRODUCT_SYNC_KEY = "last_attempted_product_sync_at"
SYNC_LOOKBACK_BUFFER_KEY = "sync_lookback_buffer_minutes"
DEFAULT_SYNC_LOOKBACK_BUFFER_MINUTES = 10
DEFAULT_PSD_MASTER_FOLDER_SETTING = {
    "url": "https://drive.google.com/drive/folders/1UCs_EsyjVXZUNclAfnmO7y2x7rKutwhH",
    "name": "Sports Cave PSD Master Folder",
}
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
_SCHEMA_READY = False
_SCHEMA_LOCK = threading.Lock()

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
                    processed_at TIMESTAMPTZ,
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
                    shopify_order_id TEXT,
                    shopify_line_item_id TEXT,
                    shopify_product_id TEXT,
                    shopify_handle TEXT,
                    product_title TEXT,
                    variant_title TEXT,
                    sku TEXT,
                    customer_name TEXT,
                    customer_email TEXT,
                    edition_number INTEGER,
                    edition_total INTEGER,
                    allocation_index INTEGER DEFAULT 1,
                    assigned_at TIMESTAMPTZ DEFAULT now(),
                    certificate_status TEXT DEFAULT 'Certificate Missing',
                    UNIQUE (shopify_line_item_id, allocation_index)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS certificates (
                    id BIGSERIAL PRIMARY KEY,
                    edition_order_id BIGINT UNIQUE,
                    shopify_order_id TEXT,
                    shopify_handle TEXT,
                    certificate_id TEXT,
                    edition_number INTEGER,
                    edition_total INTEGER,
                    local_file_path TEXT,
                    shopify_file_id TEXT,
                    shopify_file_url TEXT,
                    generated_at TIMESTAMPTZ DEFAULT now(),
                    status TEXT DEFAULT 'Local PDF'
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
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value JSONB DEFAULT '{}'::jsonb,
                    updated_at TIMESTAMPTZ DEFAULT now()
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
                    ("processed_at", "TIMESTAMPTZ"),
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
                    ("shopify_order_id", "TEXT"),
                    ("shopify_order_name", "TEXT"),
                    ("shopify_line_item_id", "TEXT"),
                    ("shopify_product_id", "TEXT"),
                    ("shopify_variant_id", "TEXT"),
                    ("shopify_handle", "TEXT"),
                    ("product_title", "TEXT"),
                    ("variant_title", "TEXT"),
                    ("sku", "TEXT"),
                    ("customer_name", "TEXT"),
                    ("customer_email", "TEXT"),
                    ("shopify_customer_name", "TEXT"),
                    ("shopify_customer_email", "TEXT"),
                    ("edition_number", "INTEGER"),
                    ("edition_total", "INTEGER"),
                    ("allocation_index", "INTEGER DEFAULT 1"),
                    ("quantity", "INTEGER DEFAULT 1"),
                    ("status", "TEXT DEFAULT 'assigned'"),
                    ("assigned_at", "TIMESTAMPTZ DEFAULT now()"),
                    ("certificate_status", "TEXT DEFAULT 'Certificate Missing'"),
                    ("updated_at", "TIMESTAMPTZ DEFAULT now()"),
                ),
                "certificates": (
                    ("edition_order_id", "BIGINT"),
                    ("shopify_order_id", "TEXT"),
                    ("shopify_handle", "TEXT"),
                    ("certificate_id", "TEXT"),
                    ("edition_number", "INTEGER"),
                    ("edition_total", "INTEGER"),
                    ("local_file_path", "TEXT"),
                    ("shopify_file_id", "TEXT"),
                    ("shopify_file_url", "TEXT"),
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
                "certificates": (
                    ("edition_order_id", "BIGINT"),
                    ("shopify_order_id", "TEXT"),
                    ("shopify_handle", "TEXT"),
                    ("certificate_id", "TEXT"),
                    ("edition_number", "INTEGER"),
                    ("edition_total", "INTEGER"),
                    ("pdf_filename", "TEXT"),
                    ("local_file_path", "TEXT"),
                    ("shopify_file_id", "TEXT"),
                    ("shopify_file_url", "TEXT"),
                    ("order_metafields_synced_at", "TIMESTAMPTZ"),
                    ("order_metafields_sync_status", "TEXT DEFAULT 'Never Synced'"),
                    ("order_metafields_error", "TEXT"),
                    ("status", "TEXT DEFAULT 'Local PDF'"),
                    ("generated_at", "TIMESTAMPTZ DEFAULT now()"),
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
            }
            for table_name, columns in additive_columns.items():
                if not table_exists(cur, table_name):
                    continue
                for column_name, column_type in columns:
                    cur.execute(
                        f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} {column_type}"
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
                "certificates",
                "product_assets",
                "sync_runs",
                "app_errors",
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

            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_shopify_products_id_unique ON shopify_products(shopify_product_id)")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_shopify_products_handle_unique ON shopify_products(handle)")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_shopify_variants_id_unique ON shopify_variants(shopify_variant_id)")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_edition_products_handle_unique ON edition_products(shopify_handle)")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_shopify_customers_id_unique ON shopify_customers(shopify_customer_id)")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_shopify_orders_id_unique ON shopify_orders(shopify_order_id)")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_shopify_order_lines_line_id_unique ON shopify_order_lines(shopify_line_item_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_shopify_order_lines_order_id ON shopify_order_lines(shopify_order_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_shopify_order_lines_handle ON shopify_order_lines(shopify_handle)")
            cur.execute("ALTER TABLE edition_orders DROP CONSTRAINT IF EXISTS edition_orders_shopify_handle_edition_number_key")
            cur.execute("DROP INDEX IF EXISTS idx_edition_orders_handle_number_unique")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_edition_orders_handle_number ON edition_orders(shopify_handle, edition_number)")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_edition_orders_line_allocation_unique ON edition_orders(shopify_line_item_id, allocation_index)")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_certificates_edition_order_unique ON certificates(edition_order_id)")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_product_assets_handle_type_unique ON product_assets(shopify_handle, asset_type)")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_product_assets_handle_type_name_unique ON product_assets(shopify_handle, asset_type, asset_name)")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_app_settings_key_unique ON app_settings(key)")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_webhook_events_id_unique ON webhook_events(webhook_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_shopify_products_title ON shopify_products(title)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_shopify_orders_created_at ON shopify_orders(created_at DESC)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_shopify_orders_customer ON shopify_orders(customer_name)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_edition_orders_order_id ON edition_orders(shopify_order_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_edition_orders_handle ON edition_orders(shopify_handle)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_product_assets_handle ON product_assets(shopify_handle)")
        conn.commit()


def reset_schema_cache():
    global _SCHEMA_READY
    with _SCHEMA_LOCK:
        _SCHEMA_READY = False


def ensure_schema():
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return
        _ensure_schema_uncached()
        _SCHEMA_READY = True


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
        conn.commit()
    return processed


def sync_shopify_products_to_supabase(config=None, progress_callback=None, *, mode="incremental"):
    ensure_schema()
    config = config or shopify_sync.get_config()
    full_sync = str(mode or "").lower() in {"full", "initial_full", "initial"}
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
                if count_shopify_products() == 0:
                    finish_sync_run(
                        run_id,
                        "Skipped",
                        0,
                        0,
                        "No products synced yet. Run Initial Full Product Sync from Developer Tools.",
                    )
                    return {
                        "products_seen": 0,
                        "products_processed": 0,
                        "metafields_attempted": 0,
                        "metafields_synced": 0,
                        "metafield_errors": [],
                        "skipped": True,
                        "message": "No products synced yet. Run Initial Full Product Sync from Developer Tools.",
                    }
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
        }
    except Exception as error:
        finish_sync_run(run_id, "Failed", seen, processed, "Shopify product sync failed.")
        log_app_error("shopify_product_sync_failed", str(error), {"records_seen": seen})
        raise


def list_edition_products(search="", limit=500):
    ensure_schema()
    search_value = f"%{search.strip().lower()}%" if search.strip() else None
    with connect() as conn:
        with conn.cursor() as cur:
            if search_value:
                cur.execute(
                    """
                    SELECT ep.*, sp.admin_url, sp.online_store_url,
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
                    LEFT JOIN shopify_products sp ON sp.handle = ep.shopify_handle
                    WHERE LOWER(COALESCE(ep.product_title, '')) LIKE %s
                       OR LOWER(COALESCE(ep.shopify_handle, '')) LIKE %s
                    ORDER BY ep.product_title NULLS LAST, ep.shopify_handle
                    LIMIT %s
                    """,
                    (search_value, search_value, limit),
                )
            else:
                cur.execute(
                    """
                    SELECT ep.*, sp.admin_url, sp.online_store_url,
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
                    LEFT JOIN shopify_products sp ON sp.handle = ep.shopify_handle
                    ORDER BY ep.product_title NULLS LAST, ep.shopify_handle
                    LIMIT %s
                    """,
                    (limit,),
                )
            return cur.fetchall()


def get_edition_counter_state(shopify_handle):
    ensure_schema()
    handle = str(shopify_handle or "").strip()
    if not handle:
        raise ValueError("Shopify handle is required.")
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ep.shopify_handle,
                       ep.product_title,
                       COALESCE(ep.edition_total, 100) AS edition_total,
                       COALESCE(ep.next_edition_number, 1) AS next_edition_number,
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
                WHERE ep.shopify_handle=%s
                """,
                (handle,),
            )
            row = cur.fetchone()
    if not row:
        raise ValueError(f"No edition product found for {handle}.")
    return row


def update_edition_product(
    shopify_handle,
    *,
    edition_total=None,
    active=None,
    sold_out=None,
    current_edition=None,
    allow_history_override=False,
):
    ensure_schema()
    handle = str(shopify_handle or "").strip()
    if not handle:
        raise ValueError("Shopify handle is required.")
    state = get_edition_counter_state(handle)
    max_assigned = _safe_int(state.get("max_assigned_edition"), 0)
    new_total = _safe_int(edition_total, _safe_int(state.get("edition_total"), 100))
    if new_total < 1:
        raise ValueError("Edition total must be at least 1.")
    if new_total < max_assigned:
        raise ValueError("Edition total cannot be lower than already assigned edition history.")

    update_next_number = None
    if current_edition is not None:
        current = _safe_int(current_edition, 0)
        if current < 0:
            raise ValueError("Current edition cannot be below 0.")
        if current < max_assigned and not allow_history_override:
            raise ValueError("Cannot set current edition below already assigned edition history.")
        if current > new_total:
            raise ValueError("Current edition cannot be higher than edition total.")
        update_next_number = current + 1
        override_active = bool(allow_history_override and current < max_assigned)
    else:
        override_active = bool(state.get("allow_counter_history_override"))

    final_sold_out = sold_out
    if final_sold_out is None and update_next_number is not None:
        final_sold_out = update_next_number > new_total

    with connect() as conn:
        with conn.cursor() as cur:
            if edition_total is not None:
                cur.execute(
                    """
                    UPDATE edition_products
                    SET edition_total=%s,
                        sold_out=COALESCE(next_edition_number, 1) > %s,
                        is_sold_out=COALESCE(next_edition_number, 1) > %s,
                        updated_at=now()
                    WHERE shopify_handle=%s
                    """,
                    (new_total, new_total, new_total, handle),
                )
            if update_next_number is not None:
                cur.execute(
                    """
                    UPDATE edition_products
                    SET next_edition_number=%s,
                        last_assigned_edition=%s,
                        allow_counter_history_override=%s,
                        sold_out=%s,
                        is_sold_out=%s,
                        updated_at=now()
                    WHERE shopify_handle=%s
                    """,
                    (
                        update_next_number,
                        max(update_next_number - 1, 0),
                        override_active,
                        bool(final_sold_out),
                        bool(final_sold_out),
                        handle,
                    ),
                )
            if active is not None:
                cur.execute(
                    """
                    UPDATE edition_products
                    SET active=%s, is_active=%s, updated_at=now()
                    WHERE shopify_handle=%s
                    """,
                    (bool(active), bool(active), handle),
                )
            if sold_out is not None and update_next_number is None:
                cur.execute(
                    """
                    UPDATE edition_products
                    SET sold_out=%s, is_sold_out=%s, updated_at=now()
                    WHERE shopify_handle=%s
                    """,
                    (bool(sold_out), bool(sold_out), handle),
                )
        conn.commit()
    return get_edition_counter_state(handle)


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
    last_assigned = max(_safe_int(row.get("last_assigned_edition"), 0), next_number - 1)
    sold_count = max(_safe_int(row.get("sold_count"), 0), last_assigned)
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
            cur.execute(
                """
                SELECT ep.*, sp.shopify_product_id AS synced_shopify_product_id,
                       sp.shopify_product_gid AS synced_shopify_product_gid,
                       sp.admin_url, sp.online_store_url,
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
                LEFT JOIN shopify_products sp ON sp.handle = ep.shopify_handle
                WHERE ep.shopify_handle=%s
                """,
                (handle,),
            )
            row = cur.fetchone()
    if not row:
        raise ValueError(f"No edition product found for {handle}.")
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
        result = shopify_sync.sync_product_edition_metafields(
            payload,
            config=config,
            request_post=request_post,
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
                       c.edition_total, c.shopify_file_url, c.generated_at,
                       eo.product_title, eo.shopify_handle, o.shopify_order_id,
                       o.order_name
                FROM certificates c
                LEFT JOIN edition_orders eo ON eo.id=c.edition_order_id
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
                "product_title": row.get("product_title") or "",
                "shopify_handle": row.get("shopify_handle") or "",
                "edition_number": row.get("edition_number") or 0,
                "edition_total": row.get("edition_total") or 100,
                "edition_display": format_edition_display_number(
                    row.get("edition_number"),
                    row.get("edition_total") or 100,
                ),
                "certificate_id": row.get("certificate_id") or "",
                "certificate_url": row.get("shopify_file_url") or "",
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
                        order_metafields_error=''
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
                        order_metafields_error=%s
                    WHERE shopify_order_id=%s
                    """,
                    (str(error)[:1000], order_id),
                )
            conn.commit()
        log_app_error(
            "order_certificate_metafield_sync_failed",
            str(error),
            {"shopify_order_id": order_id},
        )
        raise


def persistence_counts():
    ensure_schema()
    tables = (
        "edition_products",
        "edition_orders",
        "product_assets",
        "certificates",
        "shopify_products",
        "shopify_orders",
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
        "edition_tracking_start_at": get_sync_setting(EDITION_TRACKING_START_KEY, ""),
        "last_successful_product_sync_at": get_sync_setting(LAST_SUCCESSFUL_PRODUCT_SYNC_KEY, ""),
        "last_attempted_product_sync_at": get_sync_setting(LAST_ATTEMPTED_PRODUCT_SYNC_KEY, ""),
        "sync_lookback_buffer_minutes": _sync_lookback_minutes(),
    }


def _set_sync_attempt(key):
    timestamp = _datetime_to_setting(utc_now_datetime())
    set_app_setting(key, timestamp)
    return timestamp


def _set_sync_success(key):
    timestamp = _datetime_to_setting(utc_now_datetime())
    set_app_setting(key, timestamp)
    return timestamp


def reset_incremental_sync_timestamps():
    ensure_sync_defaults()
    for key in (
        LAST_SUCCESSFUL_ORDER_SYNC_KEY,
        LAST_ATTEMPTED_ORDER_SYNC_KEY,
        LAST_SUCCESSFUL_PRODUCT_SYNC_KEY,
        LAST_ATTEMPTED_PRODUCT_SYNC_KEY,
    ):
        set_app_setting(key, "")
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


def _csv_value(row, *names):
    lowered = {str(key or "").strip().lower(): value for key, value in (row or {}).items()}
    for name in names:
        value = lowered.get(str(name).strip().lower())
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return ""


def _match_product_handle(cur, *, handle="", shopify_product_id="", product_title=""):
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

    if product_title:
        cur.execute(
            """
            SELECT shopify_handle
            FROM edition_products
            WHERE LOWER(COALESCE(product_title, '')) = LOWER(%s)
            UNION
            SELECT handle AS shopify_handle
            FROM shopify_products
            WHERE LOWER(COALESCE(title, '')) = LOWER(%s)
            LIMIT 1
            """,
            (product_title, product_title),
        )
        row = cur.fetchone()
        if row and row.get("shopify_handle"):
            return row["shopify_handle"]

    return normalized_handle


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


def get_product_asset_map():
    ensure_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT shopify_handle, asset_type,
                       COALESCE(NULLIF(asset_url, ''), NULLIF(google_drive_file_url, '')) AS asset_url
                FROM product_assets
                WHERE is_primary IS DISTINCT FROM FALSE
                """
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
            total_price, currency, created_at, processed_at, raw_json, raw, synced_at, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
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
            processed_at=EXCLUDED.processed_at,
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
            order.get("processed_at") or "",
            raw_json,
            raw_json,
        ),
    )


def _upsert_order_lines(cur, order):
    for line_index, line_item in enumerate(order.get("line_items") or [], start=1):
        line_item_id = str(
            line_item.get("shopify_line_item_id")
            or f"{order.get('shopify_order_id') or 'order'}:line:{line_index}"
        ).strip()
        if not line_item_id:
            continue
        cur.execute(
            """
            INSERT INTO shopify_order_lines(
                shopify_line_item_id, shopify_order_id, shopify_product_id, shopify_handle,
                product_title, variant_title, sku, quantity, assignment_status, last_error,
                raw_json, synced_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Needs Edition', '', %s::jsonb, now(), now())
            ON CONFLICT (shopify_line_item_id) DO UPDATE SET
                shopify_order_id=EXCLUDED.shopify_order_id,
                shopify_product_id=COALESCE(NULLIF(EXCLUDED.shopify_product_id, ''), shopify_order_lines.shopify_product_id),
                shopify_handle=COALESCE(NULLIF(EXCLUDED.shopify_handle, ''), shopify_order_lines.shopify_handle),
                product_title=COALESCE(NULLIF(EXCLUDED.product_title, ''), shopify_order_lines.product_title),
                variant_title=COALESCE(NULLIF(EXCLUDED.variant_title, ''), shopify_order_lines.variant_title),
                sku=COALESCE(NULLIF(EXCLUDED.sku, ''), shopify_order_lines.sku),
                quantity=EXCLUDED.quantity,
                raw_json=EXCLUDED.raw_json,
                synced_at=now(),
                updated_at=now()
            """,
            (
                line_item_id,
                order.get("shopify_order_id") or "",
                line_item.get("shopify_product_id") or "",
                line_item.get("product_handle") or "",
                line_item.get("product_title") or "",
                line_item.get("variant_title") or "",
                line_item.get("sku") or "",
                max(1, int(line_item.get("quantity") or 1)),
                json_dumps(line_item),
            ),
        )


def _set_order_line_status(
    cur,
    shopify_line_item_id,
    assignment_status,
    *,
    shopify_product_id="",
    shopify_handle="",
    product_title="",
    variant_title="",
    sku="",
    last_error="",
):
    cur.execute(
        """
        UPDATE shopify_order_lines
        SET assignment_status=%s,
            last_error=%s,
            shopify_product_id=CASE
                WHEN %s <> '' THEN %s
                ELSE shopify_product_id
            END,
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
    handle = line_item.get("product_handle") or ""
    product_id = line_item.get("shopify_product_id") or ""
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


def _generate_certificate_for_assignment(cur, assignment):
    local_file_path = ""
    try:
        cur.execute(
            """
            SELECT local_file_path, shopify_file_url
            FROM certificates
            WHERE edition_order_id=%s
            """,
            (assignment["id"],),
        )
        existing_certificate = cur.fetchone()
        if existing_certificate and (
            existing_certificate.get("shopify_file_url")
            or existing_certificate.get("local_file_path")
        ):
            cur.execute(
                "UPDATE edition_orders SET certificate_status='Certificate Ready' WHERE id=%s",
                (assignment["id"],),
            )
            return existing_certificate.get("local_file_path") or existing_certificate.get("shopify_file_url")

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
        generated_certificate_id = certificate_id(
            assignment.get("order_name") or assignment.get("shopify_order_id"),
            assignment.get("edition_number"),
        )
        cur.execute(
            """
            INSERT INTO certificates(
                edition_order_id, shopify_order_id, shopify_handle, certificate_id, edition_number,
                edition_total, pdf_filename, local_file_path, status, generated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Local PDF', now())
            ON CONFLICT (edition_order_id) DO UPDATE SET
                certificate_id=EXCLUDED.certificate_id,
                pdf_filename=EXCLUDED.pdf_filename,
                local_file_path=EXCLUDED.local_file_path,
                generated_at=now(),
                status='Local PDF'
            """,
            (
                assignment["id"],
                assignment.get("shopify_order_id"),
                assignment.get("shopify_handle"),
                generated_certificate_id,
                assignment.get("edition_number"),
                assignment.get("edition_total"),
                Path(local_file_path).name,
                local_file_path,
            ),
        )
        cur.execute(
            "UPDATE edition_orders SET certificate_status='Certificate Ready' WHERE id=%s",
            (assignment["id"],),
        )
    except Exception as error:
        cur.execute(
            "UPDATE edition_orders SET certificate_status='Certificate Missing' WHERE id=%s",
            (assignment["id"],),
        )
        raise error
    return local_file_path


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
                next_number = int(edition_product.get("next_edition_number") or 1)
                edition_total = int(edition_product.get("edition_total") or 100)
                cur.execute(
                    """
                    SELECT COALESCE(MAX(edition_number), 0) AS max_assigned
                    FROM edition_orders
                    WHERE shopify_handle=%s
                    """,
                    (shopify_handle,),
                )
                max_assigned = int((cur.fetchone() or {}).get("max_assigned") or 0)
                should_be_next = max_assigned + 1
                allow_counter_override = bool(edition_product.get("allow_counter_history_override"))
                if next_number < should_be_next and allow_counter_override:
                    cur.execute(
                        """
                        INSERT INTO app_errors(error_type, message, context)
                        VALUES ('edition_counter_manual_override_active', %s, %s::jsonb)
                        """,
                        (
                            f"Manual edition counter override is active for {shopify_handle}.",
                            json_dumps(
                                {
                                    "shopify_handle": shopify_handle,
                                    "next_edition_number": next_number,
                                    "history_expected_next_edition_number": should_be_next,
                                    "max_assigned": max_assigned,
                                }
                            ),
                        ),
                    )
                elif next_number < should_be_next:
                    cur.execute(
                        """
                        UPDATE edition_products
                        SET next_edition_number=%s, updated_at=now()
                        WHERE shopify_handle=%s
                        """,
                        (should_be_next, shopify_handle),
                    )
                    cur.execute(
                        """
                        INSERT INTO app_errors(error_type, message, context)
                        VALUES ('edition_counter_auto_corrected', %s, %s::jsonb)
                        """,
                        (
                            f"Edition counter for {shopify_handle} was below assigned history and was corrected.",
                            json_dumps(
                                {
                                    "shopify_handle": shopify_handle,
                                    "previous_next_edition_number": next_number,
                                    "corrected_next_edition_number": should_be_next,
                                    "max_assigned": max_assigned,
                                }
                            ),
                        ),
                    )
                    next_number = should_be_next
                elif next_number > should_be_next:
                    message = (
                        f"Edition counter gap detected for {shopify_handle}. "
                        f"next_edition_number={next_number}, expected={should_be_next}."
                    )
                    cur.execute(
                        """
                        INSERT INTO app_errors(error_type, message, context)
                        VALUES ('edition_counter_gap_detected', %s, %s::jsonb)
                        """,
                        (
                            message,
                            json_dumps(
                                {
                                    "shopify_order_id": shopify_order_id,
                                    "shopify_line_item_id": shopify_line_item_id,
                                    "allocation_index": allocation_index,
                                    "shopify_handle": shopify_handle,
                                    "next_edition_number": next_number,
                                    "expected_next_edition_number": should_be_next,
                                    "max_assigned": max_assigned,
                                }
                            ),
                        ),
                    )
                    conn.commit()
                    return {"created": False, "assignment": None, "sold_out": False, "error": message}

                if next_number > edition_total:
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

                cur.execute(
                    """
                    INSERT INTO edition_orders(
                        shopify_order_id, shopify_order_name, shopify_line_item_id, shopify_product_id,
                        shopify_handle, product_title, variant_title, sku,
                        customer_name, customer_email, shopify_customer_name, shopify_customer_email,
                        edition_number, edition_total, allocation_index, quantity,
                        assigned_at, certificate_status, status, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1,
                            now(), 'Certificate Missing', %s, now())
                    ON CONFLICT DO NOTHING
                    RETURNING id, shopify_order_id, shopify_line_item_id, shopify_product_id,
                              shopify_handle, product_title, variant_title, sku, customer_name,
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
                        variant_title,
                        sku,
                        customer_name,
                        customer_email,
                        customer_name,
                        customer_email,
                        next_number,
                        edition_total,
                        allocation_index,
                        allocation_status or "assigned",
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
                        f"#{next_number}/{edition_total}."
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
                                    "edition_number": next_number,
                                }
                            ),
                        ),
                    )
                    conn.commit()
                    return {"created": False, "assignment": None, "sold_out": False, "error": message}

                incremented_next = next_number + 1
                cur.execute(
                    """
                    UPDATE edition_products
                    SET next_edition_number=%s,
                        sold_out=%s,
                        is_sold_out=%s,
                        updated_at=now()
                    WHERE shopify_handle=%s
                    """,
                    (
                        incremented_next,
                        incremented_next > edition_total,
                        incremented_next > edition_total,
                        shopify_handle,
                    ),
                )
                inserted["order_name"] = shopify_order_name
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
):
    ensure_schema()
    if not order.get("shopify_order_id"):
        raise ValueError("Shopify order ID is missing.")
    assignments_created = 0
    existing_assignments_skipped = 0
    changed_handles = set()
    generated_certificates = 0
    errors = []
    with connect() as conn:
        try:
            with conn.cursor() as cur:
                customer = _customer_from_order(order)
                _upsert_customer(cur, customer)
                _upsert_order(cur, order)
                _upsert_order_lines(cur, order)
                _backfill_edition_customer_details(cur, order)
                conn.commit()
        except Exception:
            conn.rollback()
            raise

    financial_status = str(order.get("financial_status") or "").upper()
    if financial_status and financial_status not in {"PAID", "PARTIALLY_PAID"}:
        return {
            "assignments_created": 0,
            "existing_assignments_skipped": 0,
            "generated_certificates": 0,
            "changed_handles": [],
            "errors": [],
        }

    order_customer_name = _customer_name_for_storage(order)
    order_customer_email = str(order.get("customer_email") or order.get("email") or "").strip()
    new_assignments = []
    product_cache = {}
    for line_index, line_item in enumerate(order.get("line_items") or [], start=1):
        quantity = max(1, int(line_item.get("quantity") or 1))
        line_item_id = str(
            line_item.get("shopify_line_item_id")
            or f"{order['shopify_order_id']}:line:{line_index}"
        )
        line_cache_keys = [
            str(line_item.get("shopify_product_id") or "").strip(),
            str(line_item.get("product_handle") or "").strip().lower(),
            str(line_item.get("product_title") or "").strip().lower(),
        ]
        cached_product = next((product_cache[key] for key in line_cache_keys if key and key in product_cache), None)
        try:
            product = cached_product if cached_product is not None else resolve_product_for_line(
                line_item,
                fetch_missing_products=fetch_missing_products,
            )
        except Exception as error:
            product = None
            errors.append(f"Product fetch failed for {line_item.get('product_title')}: {error}")
            with connect() as conn:
                with conn.cursor() as cur:
                    _set_order_line_status(
                        cur,
                        line_item_id,
                        "Error",
                        shopify_product_id=line_item.get("shopify_product_id") or "",
                        shopify_handle=line_item.get("product_handle") or "",
                        product_title=line_item.get("product_title") or "",
                        variant_title=line_item.get("variant_title") or "",
                        sku=line_item.get("sku") or "",
                        last_error=str(error),
                    )
                conn.commit()
            continue

        if product:
            for cache_key in (
                str(product.get("shopify_product_id") or "").strip(),
                str(product.get("handle") or "").strip().lower(),
                str(product.get("title") or "").strip().lower(),
                *line_cache_keys,
            ):
                if cache_key:
                    product_cache[cache_key] = product

        handle = (product or {}).get("handle") or line_item.get("product_handle") or ""
        if not handle:
            errors.append(f"Missing product handle for line item {line_item_id}.")
            with connect() as conn:
                with conn.cursor() as cur:
                    _set_order_line_status(
                        cur,
                        line_item_id,
                        "Product Not Found",
                        shopify_product_id=(product or {}).get("shopify_product_id") or line_item.get("shopify_product_id") or "",
                        product_title=(product or {}).get("title") or line_item.get("product_title") or "",
                        variant_title=line_item.get("variant_title") or "",
                        sku=line_item.get("sku") or "",
                        last_error="Missing product handle returned from Shopify.",
                    )
                conn.commit()
            continue
        product_title = (product or {}).get("title") or line_item.get("product_title") or "Sports Cave Artwork"
        product_id = (product or {}).get("shopify_product_id") or line_item.get("shopify_product_id") or ""
        line_created = 0
        line_existing = 0
        line_sold_out = False
        line_errors = []

        for allocation_index in range(1, quantity + 1):
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
            )
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
        with connect() as conn:
            with conn.cursor() as cur:
                _set_order_line_status(
                    cur,
                    line_item_id,
                    line_status,
                    shopify_product_id=product_id,
                    shopify_handle=handle,
                    product_title=product_title,
                    variant_title=line_item.get("variant_title") or "",
                    sku=line_item.get("sku") or "",
                    last_error=line_error,
                )
            conn.commit()

    if generate_certificates:
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

    if sync_product_metafields:
        for handle in sorted(changed_handles):
            try:
                sync_product_edition_metafields(handle)
            except Exception as error:
                errors.append(f"Product metafield sync failed for {handle}: {error}")

    for message in errors:
        log_app_error("order_processing_warning", message, {"shopify_order_id": order.get("shopify_order_id")})
    return {
        "assignments_created": assignments_created,
        "existing_assignments_skipped": existing_assignments_skipped,
        "generated_certificates": generated_certificates,
        "changed_handles": sorted(changed_handles),
        "errors": errors,
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
        line_items.append(
            {
                "shopify_line_item_id": str(item.get("id") or ""),
                "shopify_product_id": _shopify_gid("Product", product_id) if product_id else "",
                "product_title": item.get("title") or item.get("name") or "",
                "product_handle": "",
                "variant_title": item.get("variant_title") or item.get("variant") or "",
                "sku": item.get("sku") or "",
                "quantity": int(item.get("quantity") or 1),
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
        "total_price": str(payload.get("total_price") or ""),
        "currency": payload.get("currency") or "",
        "created_at": payload.get("created_at") or "",
        "processed_at": payload.get("processed_at") or "",
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
        result = process_paid_order(normalize_rest_order(payload))
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


def sync_shopify_orders_to_supabase(
    config=None,
    *,
    query=None,
    max_orders=250,
    historical_backfill=False,
    days=365,
    generate_certificates=False,
    sync_product_metafields=False,
):
    ensure_schema()
    config = config or shopify_sync.get_config()
    run_id = start_sync_run("shopify_orders_backfill" if historical_backfill else "shopify_orders_incremental")
    seen = 0
    processed_orders = 0
    skipped_historical = 0
    assignments = 0
    existing_skipped = 0
    generated_certificates = 0
    changed_handles = set()
    errors = []
    sync_from = None
    try:
        _set_sync_attempt(LAST_ATTEMPTED_ORDER_SYNC_KEY)
        if historical_backfill:
            effective_query = query or "financial_status:paid"
            allocation_status = "backfilled"
            generate_certificates_now = False
            sync_product_metafields_now = False
            tracking_start = None
        else:
            tracking_start = ensure_edition_tracking_start()
            state = get_sync_state()
            last_success = _parse_datetime(state.get("last_successful_order_sync_at")) or tracking_start
            sync_from = last_success - timedelta(
                minutes=state.get("sync_lookback_buffer_minutes") or DEFAULT_SYNC_LOOKBACK_BUFFER_MINUTES
            )
            effective_query = query or f"financial_status:paid updated_at:>='{_datetime_to_shopify_query(sync_from)}'"
            allocation_status = "assigned"
            generate_certificates_now = bool(generate_certificates)
            sync_product_metafields_now = bool(sync_product_metafields)

        sync_config = dict(config)
        sync_config["max_orders"] = max(int(max_orders or 50), 1)
        for page in shopify_sync.iter_order_pages(
            query=effective_query,
            days=days,
            max_orders=max_orders,
            page_size=50,
            config=sync_config,
        ):
            for order in page["orders"]:
                if not historical_backfill:
                    order_datetime = _order_effective_datetime(order)
                    if order_datetime and tracking_start and order_datetime < tracking_start:
                        skipped_historical += 1
                        continue
                result = process_paid_order(
                    order,
                    allocation_status=allocation_status,
                    generate_certificates=generate_certificates_now,
                    sync_product_metafields=sync_product_metafields_now,
                )
                processed_orders += 1
                assignments += int(result.get("assignments_created") or 0)
                existing_skipped += int(result.get("existing_assignments_skipped") or 0)
                generated_certificates += int(result.get("generated_certificates") or 0)
                changed_handles.update(result.get("changed_handles") or [])
                errors.extend(result.get("errors") or [])
            seen += len(page["orders"])
            del page
            gc.collect()
        if not historical_backfill:
            _set_sync_success(LAST_SUCCESSFUL_ORDER_SYNC_KEY)
        finish_sync_run(run_id, "Complete" if not errors else "Complete With Warnings", seen, processed_orders)
        return {
            "orders_seen": seen,
            "orders_processed": processed_orders,
            "orders_inserted_or_updated": processed_orders,
            "assignments_created": assignments,
            "existing_assignments_skipped": existing_skipped,
            "generated_certificates": generated_certificates,
            "certificates_deferred": max(assignments - generated_certificates, 0),
            "product_metafields_deferred": len(changed_handles) if not sync_product_metafields_now else 0,
            "skipped_historical": skipped_historical,
            "sync_from": _datetime_to_setting(sync_from) if sync_from else "",
            "mode": "historical_backfill" if historical_backfill else "incremental",
            "errors": errors[:10],
        }
    except Exception as error:
        finish_sync_run(run_id, "Failed", seen, assignments, "Shopify order sync failed.")
        log_app_error("shopify_order_sync_failed", str(error), {"records_seen": seen})
        raise


def _order_sort_clause(sort):
    return {
        "Date newest": "COALESCE(o.created_at, o.synced_at) DESC NULLS LAST, o.order_name DESC",
        "Date oldest": "COALESCE(o.created_at, o.synced_at) ASC NULLS LAST, o.order_name ASC",
        "Order number": "o.order_name ASC",
        "Customer": "o.customer_name ASC NULLS LAST",
        "Edition number": "eo.edition_number ASC NULLS LAST",
        "Certificate status": "eo.certificate_status ASC NULLS LAST",
        "PSD status": "psd.asset_url ASC NULLS LAST",
    }.get(sort, "COALESCE(o.created_at, o.synced_at) DESC NULLS LAST, o.order_name DESC")


def list_orders(search="", sort="Date newest", status_filter="All", limit=250):
    ensure_schema()
    search_value = f"%{search.strip().lower()}%" if search.strip() else None
    order_by = _order_sort_clause(sort)
    base_sql = f"""
        SELECT o.shopify_order_id, o.order_name, o.order_number, o.admin_url,
               COALESCE(NULLIF(o.customer_name, ''), NULLIF(eo.customer_name, '')) AS customer_name,
               COALESCE(NULLIF(o.customer_email, ''), NULLIF(eo.customer_email, '')) AS customer_email,
               o.financial_status, o.fulfillment_status,
               o.total_price, o.currency, o.created_at, o.processed_at,
               li.id AS order_line_id, COALESCE(eo.shopify_line_item_id, li.shopify_line_item_id) AS shopify_line_item_id, li.quantity,
               li.assignment_status, li.last_error,
               eo.id AS edition_order_id,
               COALESCE(NULLIF(eo.shopify_handle, ''), NULLIF(li.shopify_handle, '')) AS shopify_handle,
               COALESCE(NULLIF(eo.shopify_product_id, ''), NULLIF(li.shopify_product_id, '')) AS shopify_product_id,
               COALESCE(NULLIF(eo.product_title, ''), NULLIF(li.product_title, '')) AS product_title,
               COALESCE(NULLIF(eo.variant_title, ''), NULLIF(li.variant_title, '')) AS variant_title,
               COALESCE(NULLIF(eo.sku, ''), NULLIF(li.sku, '')) AS sku,
               eo.edition_number,
               eo.edition_total, eo.allocation_index, eo.assigned_at, eo.certificate_status,
               COALESCE(NULLIF(ep.featured_image_url, ''), NULLIF(sp.featured_image_url, ''), NULLIF(sp.image_url, '')) AS image_url,
               c.local_file_path, c.shopify_file_url,
               COALESCE(NULLIF(psd.asset_url, ''), NULLIF(psd.google_drive_file_url, '')) AS psd_url,
               COALESCE(NULLIF(prodigi.asset_url, ''), NULLIF(prodigi.google_drive_file_url, '')) AS prodigi_url
        FROM shopify_orders o
        LEFT JOIN shopify_order_lines li ON li.shopify_order_id = o.shopify_order_id
        LEFT JOIN edition_orders eo ON eo.shopify_line_item_id = li.shopify_line_item_id
        LEFT JOIN edition_products ep ON ep.shopify_handle = COALESCE(NULLIF(eo.shopify_handle, ''), NULLIF(li.shopify_handle, ''))
        LEFT JOIN shopify_products sp ON sp.handle = COALESCE(NULLIF(eo.shopify_handle, ''), NULLIF(li.shopify_handle, ''))
        LEFT JOIN certificates c ON c.edition_order_id = eo.id
        LEFT JOIN product_assets psd ON psd.shopify_handle = COALESCE(NULLIF(eo.shopify_handle, ''), NULLIF(li.shopify_handle, '')) AND psd.asset_type = 'psd_master_file' AND psd.is_primary IS DISTINCT FROM FALSE
        LEFT JOIN product_assets prodigi ON prodigi.shopify_handle = COALESCE(NULLIF(eo.shopify_handle, ''), NULLIF(li.shopify_handle, '')) AND prodigi.asset_type = 'prodigi_link'
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
               OR LOWER(COALESCE(li.assignment_status, '')) LIKE %s
               OR CAST(COALESCE(eo.edition_number, 0) AS TEXT) LIKE %s
            """
        )
        params = [search_value] * 8 + [f"%{search.strip()}%"]
    status_clauses = {
        "Needs edition": "COALESCE(li.assignment_status, '') IN ('Needs Edition', 'Product Not Found', 'Needs Edition Setup', 'Error')",
        "Assigned": "(COALESCE(li.assignment_status, '') = 'Assigned' OR eo.id IS NOT NULL)",
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
                f"{base_sql} {where} ORDER BY {order_by} LIMIT %s",
                (*params, limit),
            )
            return cur.fetchall()


def get_order_summary():
    ensure_schema()
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
                    (SELECT COUNT(*) FROM edition_orders WHERE assigned_at::date = CURRENT_DATE) AS assigned_today,
                    (SELECT COUNT(*) FROM edition_orders eo
                     LEFT JOIN certificates c ON c.edition_order_id=eo.id
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
            )
            return cur.fetchone() or {}


def get_order_activity(days=7):
    ensure_schema()
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


def list_edition_orders(search="", limit=250):
    ensure_schema()
    search_value = f"%{search.strip().lower()}%" if search.strip() else None
    with connect() as conn:
        with conn.cursor() as cur:
            if search_value:
                cur.execute(
                    """
                    SELECT eo.*, o.order_name, o.admin_url, c.local_file_path, c.shopify_file_url
                    FROM edition_orders eo
                    LEFT JOIN shopify_orders o ON o.shopify_order_id=eo.shopify_order_id
                    LEFT JOIN certificates c ON c.edition_order_id=eo.id
                    WHERE LOWER(COALESCE(eo.product_title, '')) LIKE %s
                       OR LOWER(COALESCE(eo.shopify_handle, '')) LIKE %s
                       OR LOWER(COALESCE(o.order_name, '')) LIKE %s
                       OR LOWER(COALESCE(eo.customer_name, '')) LIKE %s
                    ORDER BY eo.assigned_at DESC
                    LIMIT %s
                    """,
                    (search_value, search_value, search_value, search_value, limit),
                )
            else:
                cur.execute(
                    """
                    SELECT eo.*, o.order_name, o.admin_url, c.local_file_path, c.shopify_file_url
                    FROM edition_orders eo
                    LEFT JOIN shopify_orders o ON o.shopify_order_id=eo.shopify_order_id
                    LEFT JOIN certificates c ON c.edition_order_id=eo.id
                    ORDER BY eo.assigned_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
            return cur.fetchall()


def generate_certificate_for_edition_order(edition_order_id):
    ensure_schema()
    assignment = None
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT eo.*, o.order_name
                FROM edition_orders eo
                LEFT JOIN shopify_orders o ON o.shopify_order_id=eo.shopify_order_id
                WHERE eo.id=%s
                """,
                (edition_order_id,),
            )
            assignment = cur.fetchone()
            if not assignment:
                raise ValueError("Edition order was not found.")
            path = _generate_certificate_for_assignment(cur, assignment)
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
    ids = [int(value) for value in edition_order_ids if value]
    if not ids:
        return 0
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE edition_orders
                SET certificate_status='Certificate Ready'
                WHERE id = ANY(%s)
                """,
                (ids,),
            )
            count = cur.rowcount
        conn.commit()
    return count


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
                    LEFT JOIN edition_orders eo ON eo.id=c.edition_order_id
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
                    LEFT JOIN edition_orders eo ON eo.id=c.edition_order_id
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
