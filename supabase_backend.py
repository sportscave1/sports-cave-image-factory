import csv
import gc
import io
import json
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import shopify_sync
from certificate_service import certificate_id, generate_certificate_pdf


BASE_DIR = Path(__file__).resolve().parent
CERTIFICATE_OUTPUT_DIR = BASE_DIR / "output" / "certificates"

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


def get_database_url():
    return os.getenv("DATABASE_URL", "").strip()


def is_configured():
    return bool(get_database_url())


def _database_url_with_ssl():
    url = get_database_url()
    if not url:
        raise SupabaseNotConfigured("DATABASE_URL is not configured.")
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.setdefault("sslmode", "require")
    query.setdefault("connect_timeout", "5")
    return urlunparse(parsed._replace(query=urlencode(query)))


def connect():
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as error:
        raise RuntimeError(
            "Postgres support is not installed. Add psycopg[binary] to requirements.txt."
        ) from error
    return psycopg.connect(
        _database_url_with_ssl(),
        row_factory=dict_row,
        connect_timeout=5,
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


def ensure_schema():
    if not is_configured():
        raise SupabaseNotConfigured("DATABASE_URL is not configured.")
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
                    UNIQUE (shopify_handle, edition_number),
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
                    ("legacy_resource_id", "TEXT"),
                    ("title", "TEXT"),
                    ("handle", "TEXT"),
                    ("status", "TEXT"),
                    ("vendor", "TEXT"),
                    ("product_type", "TEXT"),
                    ("online_store_url", "TEXT"),
                    ("admin_url", "TEXT"),
                    ("image_url", "TEXT"),
                    ("raw_json", "JSONB DEFAULT '{}'::jsonb"),
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
                    ("shopify_handle", "TEXT"),
                    ("product_title", "TEXT"),
                    ("edition_total", "INTEGER DEFAULT 100"),
                    ("next_edition_number", "INTEGER DEFAULT 1"),
                    ("active", "BOOLEAN DEFAULT TRUE"),
                    ("sold_out", "BOOLEAN DEFAULT FALSE"),
                    ("updated_at", "TIMESTAMPTZ DEFAULT now()"),
                ),
                "shopify_customers": (
                    ("customer_name", "TEXT"),
                    ("email", "TEXT"),
                    ("raw_json", "JSONB DEFAULT '{}'::jsonb"),
                    ("updated_at", "TIMESTAMPTZ DEFAULT now()"),
                ),
                "shopify_orders": (
                    ("legacy_resource_id", "TEXT"),
                    ("order_name", "TEXT"),
                    ("order_number", "TEXT"),
                    ("admin_url", "TEXT"),
                    ("customer_id", "TEXT"),
                    ("customer_name", "TEXT"),
                    ("customer_email", "TEXT"),
                    ("financial_status", "TEXT"),
                    ("fulfillment_status", "TEXT"),
                    ("total_price", "TEXT"),
                    ("currency", "TEXT"),
                    ("created_at", "TIMESTAMPTZ"),
                    ("processed_at", "TIMESTAMPTZ"),
                    ("raw_json", "JSONB DEFAULT '{}'::jsonb"),
                    ("synced_at", "TIMESTAMPTZ DEFAULT now()"),
                ),
                "edition_orders": (
                    ("shopify_order_id", "TEXT"),
                    ("shopify_line_item_id", "TEXT"),
                    ("shopify_product_id", "TEXT"),
                    ("shopify_handle", "TEXT"),
                    ("product_title", "TEXT"),
                    ("variant_title", "TEXT"),
                    ("sku", "TEXT"),
                    ("customer_name", "TEXT"),
                    ("customer_email", "TEXT"),
                    ("edition_number", "INTEGER"),
                    ("edition_total", "INTEGER"),
                    ("allocation_index", "INTEGER DEFAULT 1"),
                    ("assigned_at", "TIMESTAMPTZ DEFAULT now()"),
                    ("certificate_status", "TEXT DEFAULT 'Certificate Missing'"),
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
                    ("error_type", "TEXT"),
                    ("message", "TEXT"),
                    ("context", "JSONB DEFAULT '{}'::jsonb"),
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

            uuid_id_tables = (
                "shopify_products",
                "shopify_variants",
                "edition_products",
                "shopify_customers",
                "shopify_orders",
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
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_edition_orders_handle_number_unique ON edition_orders(shopify_handle, edition_number)")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_edition_orders_line_allocation_unique ON edition_orders(shopify_line_item_id, allocation_index)")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_certificates_edition_order_unique ON certificates(edition_order_id)")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_product_assets_handle_type_unique ON product_assets(shopify_handle, asset_type)")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_webhook_events_id_unique ON webhook_events(webhook_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_shopify_products_title ON shopify_products(title)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_shopify_orders_created_at ON shopify_orders(created_at DESC)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_shopify_orders_customer ON shopify_orders(customer_name)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_edition_orders_order_id ON edition_orders(shopify_order_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_edition_orders_handle ON edition_orders(shopify_handle)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_product_assets_handle ON product_assets(shopify_handle)")
        conn.commit()


def test_connection():
    ensure_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT now() AS server_time")
            row = cur.fetchone() or {}
    return {"connected": True, "server_time": row.get("server_time")}


def log_app_error(error_type, message, context=None):
    if not is_configured():
        return
    try:
        ensure_schema()
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO app_errors(error_type, message, context)
                    VALUES (%s, %s, %s::jsonb)
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
                cur.execute(
                    """
                    INSERT INTO shopify_products(
                        shopify_product_id, legacy_resource_id, title, handle, status, vendor,
                        product_type, online_store_url, admin_url, image_url, raw_json, synced_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, now(), now())
                    ON CONFLICT (shopify_product_id) DO UPDATE SET
                        legacy_resource_id=EXCLUDED.legacy_resource_id,
                        title=EXCLUDED.title,
                        handle=EXCLUDED.handle,
                        status=EXCLUDED.status,
                        vendor=EXCLUDED.vendor,
                        product_type=EXCLUDED.product_type,
                        online_store_url=EXCLUDED.online_store_url,
                        admin_url=EXCLUDED.admin_url,
                        image_url=EXCLUDED.image_url,
                        raw_json=EXCLUDED.raw_json,
                        synced_at=now(),
                        updated_at=now()
                    """,
                    (
                        product.get("shopify_product_id"),
                        product.get("legacy_resource_id"),
                        product.get("title"),
                        handle,
                        product.get("status"),
                        product.get("vendor"),
                        product.get("product_type"),
                        product.get("online_store_url"),
                        product.get("admin_url"),
                        _first_image_url(product),
                        json_dumps(product),
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
                        shopify_product_id, shopify_handle, product_title,
                        edition_total, next_edition_number, active, sold_out, updated_at
                    )
                    VALUES (%s, %s, %s, 100, 1, %s, FALSE, now())
                    ON CONFLICT (shopify_handle) DO UPDATE SET
                        shopify_product_id=EXCLUDED.shopify_product_id,
                        product_title=EXCLUDED.product_title,
                        active=EXCLUDED.active,
                        updated_at=now()
                    """,
                    (
                        product.get("shopify_product_id"),
                        handle,
                        product.get("title"),
                        str(product.get("status") or "").upper() == "ACTIVE",
                    ),
                )
                processed += 1
        conn.commit()
    return processed


def sync_shopify_products_to_supabase(config=None):
    ensure_schema()
    config = config or shopify_sync.get_config()
    run_id = start_sync_run("shopify_products")
    seen = 0
    processed = 0
    try:
        sync_config = dict(config)
        sync_config["max_products"] = max(int(sync_config.get("max_products") or 0), 1000)
        for page in shopify_sync.iter_catalog_pages(search="status:active", page_size=50, config=sync_config):
            seen += len(page["products"])
            processed += upsert_products(page["products"])
            del page
            gc.collect()
        finish_sync_run(run_id, "Complete", seen, processed)
        return {"products_seen": seen, "products_processed": processed}
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
                           (
                               SELECT MAX(eo.edition_number)
                               FROM edition_orders eo
                               WHERE eo.shopify_handle = ep.shopify_handle
                           ) AS last_assigned_edition,
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
                           (
                               SELECT MAX(eo.edition_number)
                               FROM edition_orders eo
                               WHERE eo.shopify_handle = ep.shopify_handle
                           ) AS last_assigned_edition,
                           GREATEST(COALESCE(ep.edition_total, 100) - COALESCE(ep.next_edition_number, 1) + 1, 0) AS remaining_editions
                    FROM edition_products ep
                    LEFT JOIN shopify_products sp ON sp.handle = ep.shopify_handle
                    ORDER BY ep.product_title NULLS LAST, ep.shopify_handle
                    LIMIT %s
                    """,
                    (limit,),
                )
            return cur.fetchall()


def update_edition_product(shopify_handle, *, edition_total=None, active=None):
    ensure_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            if edition_total is not None:
                cur.execute(
                    """
                    UPDATE edition_products
                    SET edition_total=%s,
                        sold_out=COALESCE(next_edition_number, 1) > %s,
                        updated_at=now()
                    WHERE shopify_handle=%s
                    """,
                    (int(edition_total), int(edition_total), shopify_handle),
                )
            if active is not None:
                cur.execute(
                    """
                    UPDATE edition_products
                    SET active=%s, updated_at=now()
                    WHERE shopify_handle=%s
                    """,
                    (bool(active), shopify_handle),
                )
        conn.commit()


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


def import_limited_edition_rows(rows, *, overwrite_existing_orders=False):
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
                    active_raw = _csv_value(row, "active", "Active")
                    active = False if active_raw.lower() in {"false", "no", "0", "inactive"} else True

                    cur.execute(
                        """
                        INSERT INTO edition_products(
                            shopify_product_id, shopify_handle, product_title,
                            edition_total, next_edition_number, active, sold_out, updated_at
                        )
                        VALUES (%s, %s, %s, %s, COALESCE(%s, 1), %s, FALSE, now())
                        ON CONFLICT (shopify_handle) DO UPDATE SET
                            shopify_product_id=COALESCE(EXCLUDED.shopify_product_id, edition_products.shopify_product_id),
                            product_title=COALESCE(NULLIF(EXCLUDED.product_title, ''), edition_products.product_title),
                            edition_total=EXCLUDED.edition_total,
                            next_edition_number=GREATEST(edition_products.next_edition_number, EXCLUDED.next_edition_number),
                            active=EXCLUDED.active,
                            sold_out=GREATEST(edition_products.next_edition_number, EXCLUDED.next_edition_number) > EXCLUDED.edition_total,
                            updated_at=now()
                        RETURNING (xmax = 0) AS inserted
                        """,
                        (
                            shopify_product_id or None,
                            matched_handle,
                            product_title,
                            int(edition_total),
                            int(next_number) if next_number else None,
                            bool(active),
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
                                ON CONFLICT (shopify_handle, edition_number) DO UPDATE SET
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
            cur.execute("SELECT shopify_handle, asset_type, asset_url FROM product_assets WHERE is_primary IS DISTINCT FROM FALSE")
            rows = cur.fetchall()
    result = {}
    for row in rows:
        result.setdefault(row["shopify_handle"], {})[row["asset_type"]] = row.get("asset_url") or ""
    return result


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


def _shopify_gid(resource_type, value):
    raw = str(value or "").strip()
    if raw.startswith("gid://"):
        return raw
    if not raw:
        return ""
    return f"gid://shopify/{resource_type}/{raw}"


def _customer_from_order(order):
    customer_email = order.get("customer_email") or order.get("email") or ""
    customer_name = order.get("customer_name") or customer_email or "Customer not shown"
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
    cur.execute(
        """
        INSERT INTO shopify_customers(shopify_customer_id, customer_name, email, raw_json, updated_at)
        VALUES (%s, %s, %s, %s::jsonb, now())
        ON CONFLICT (shopify_customer_id) DO UPDATE SET
            customer_name=EXCLUDED.customer_name,
            email=EXCLUDED.email,
            raw_json=EXCLUDED.raw_json,
            updated_at=now()
        """,
        (
            customer["shopify_customer_id"],
            customer.get("customer_name"),
            customer.get("email"),
            json_dumps(customer.get("raw_json")),
        ),
    )


def _upsert_order(cur, order):
    cur.execute(
        """
        INSERT INTO shopify_orders(
            shopify_order_id, legacy_resource_id, order_name, order_number, admin_url,
            customer_id, customer_name, customer_email, financial_status, fulfillment_status,
            total_price, currency, created_at, processed_at, raw_json, synced_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULLIF(%s, '')::timestamptz,
                NULLIF(%s, '')::timestamptz, %s::jsonb, now())
        ON CONFLICT (shopify_order_id) DO UPDATE SET
            legacy_resource_id=EXCLUDED.legacy_resource_id,
            order_name=EXCLUDED.order_name,
            order_number=EXCLUDED.order_number,
            admin_url=EXCLUDED.admin_url,
            customer_id=EXCLUDED.customer_id,
            customer_name=EXCLUDED.customer_name,
            customer_email=EXCLUDED.customer_email,
            financial_status=EXCLUDED.financial_status,
            fulfillment_status=EXCLUDED.fulfillment_status,
            total_price=EXCLUDED.total_price,
            currency=EXCLUDED.currency,
            created_at=EXCLUDED.created_at,
            processed_at=EXCLUDED.processed_at,
            raw_json=EXCLUDED.raw_json,
            synced_at=now()
        """,
        (
            order.get("shopify_order_id"),
            order.get("legacy_resource_id"),
            order.get("order_name"),
            order.get("order_number"),
            order.get("admin_url"),
            order.get("customer_id") or order.get("shopify_customer_id") or "",
            order.get("customer_name"),
            order.get("customer_email"),
            order.get("financial_status"),
            order.get("fulfillment_status"),
            order.get("total_price"),
            order.get("currency"),
            order.get("created_at") or "",
            order.get("processed_at") or "",
            json_dumps(order),
        ),
    )


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
                edition_total, local_file_path, status, generated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'Local PDF', now())
            ON CONFLICT (edition_order_id) DO UPDATE SET
                certificate_id=EXCLUDED.certificate_id,
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
                    conn.commit()
                    return {"created": False, "assignment": existing, "sold_out": False, "error": ""}

                cur.execute(
                    """
                    INSERT INTO edition_products(
                        shopify_product_id, shopify_handle, product_title,
                        edition_total, next_edition_number, active, sold_out, updated_at
                    )
                    VALUES (%s, %s, %s, 100, 1, TRUE, FALSE, now())
                    ON CONFLICT (shopify_handle) DO UPDATE SET
                        shopify_product_id=COALESCE(EXCLUDED.shopify_product_id, edition_products.shopify_product_id),
                        product_title=COALESCE(EXCLUDED.product_title, edition_products.product_title),
                        updated_at=now()
                    """,
                    (shopify_product_id, shopify_handle, product_title),
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

                if next_number > edition_total:
                    cur.execute(
                        """
                        UPDATE edition_products
                        SET sold_out=TRUE, updated_at=now()
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
                        shopify_order_id, shopify_line_item_id, shopify_product_id, shopify_handle,
                        product_title, variant_title, sku, customer_name, customer_email,
                        edition_number, edition_total, allocation_index, assigned_at, certificate_status
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), 'Certificate Missing')
                    ON CONFLICT DO NOTHING
                    RETURNING id, shopify_order_id, shopify_line_item_id, shopify_product_id,
                              shopify_handle, product_title, variant_title, sku, customer_name,
                              customer_email, edition_number, edition_total, allocation_index,
                              assigned_at, certificate_status
                    """,
                    (
                        shopify_order_id,
                        shopify_line_item_id,
                        shopify_product_id,
                        shopify_handle,
                        product_title,
                        variant_title,
                        sku,
                        customer_name,
                        customer_email,
                        next_number,
                        edition_total,
                        allocation_index,
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
                        updated_at=now()
                    WHERE shopify_handle=%s
                    """,
                    (incremented_next, incremented_next > edition_total, shopify_handle),
                )
                inserted["order_name"] = shopify_order_name
                conn.commit()
                return {"created": True, "assignment": inserted, "sold_out": False, "error": ""}
        except Exception:
            conn.rollback()
            raise


def process_paid_order(order, *, fetch_missing_products=True):
    ensure_schema()
    if not order.get("shopify_order_id"):
        raise ValueError("Shopify order ID is missing.")
    assignments_created = 0
    changed_handles = set()
    generated_certificates = 0
    errors = []
    with connect() as conn:
        try:
            with conn.cursor() as cur:
                customer = _customer_from_order(order)
                _upsert_customer(cur, customer)
                _upsert_order(cur, order)
                conn.commit()
        except Exception:
            conn.rollback()
            raise

    financial_status = str(order.get("financial_status") or "").upper()
    if financial_status and financial_status not in {"PAID", "PARTIALLY_PAID"}:
        return {
            "assignments_created": 0,
            "generated_certificates": 0,
            "changed_handles": [],
            "errors": [],
        }

    new_assignments = []
    for line_index, line_item in enumerate(order.get("line_items") or [], start=1):
        quantity = max(1, int(line_item.get("quantity") or 1))
        line_item_id = str(
            line_item.get("shopify_line_item_id")
            or f"{order['shopify_order_id']}:line:{line_index}"
        )
        try:
            product = resolve_product_for_line(line_item, fetch_missing_products=fetch_missing_products)
        except Exception as error:
            product = None
            errors.append(f"Product fetch failed for {line_item.get('product_title')}: {error}")

        handle = (product or {}).get("handle") or line_item.get("product_handle") or ""
        if not handle:
            errors.append(f"Missing product handle for line item {line_item_id}.")
            continue
        product_title = (product or {}).get("title") or line_item.get("product_title") or "Sports Cave Artwork"
        product_id = (product or {}).get("shopify_product_id") or line_item.get("shopify_product_id") or ""

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
                customer_name=order.get("customer_name") or order.get("customer_email") or "",
                customer_email=order.get("customer_email") or "",
            )
            if result.get("error"):
                errors.append(result["error"])
            assignment = result.get("assignment")
            if result.get("created") and assignment:
                assignments_created += 1
                changed_handles.add(handle)
                new_assignments.append(assignment)

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

    for message in errors:
        log_app_error("order_processing_warning", message, {"shopify_order_id": order.get("shopify_order_id")})
    return {
        "assignments_created": assignments_created,
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


def sync_shopify_orders_to_supabase(config=None, *, query=None, max_orders=50):
    ensure_schema()
    config = config or shopify_sync.get_config()
    run_id = start_sync_run("shopify_orders")
    seen = 0
    assignments = 0
    errors = []
    try:
        sync_config = dict(config)
        sync_config["max_orders"] = max(int(max_orders or 50), 1)
        for page in shopify_sync.iter_order_pages(
            query=query,
            max_orders=max_orders,
            page_size=50,
            config=sync_config,
        ):
            for order in page["orders"]:
                result = process_paid_order(order)
                assignments += int(result.get("assignments_created") or 0)
                errors.extend(result.get("errors") or [])
            seen += len(page["orders"])
            del page
            gc.collect()
        finish_sync_run(run_id, "Complete" if not errors else "Complete With Warnings", seen, assignments)
        return {"orders_seen": seen, "assignments_created": assignments, "errors": errors[:10]}
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


def list_orders(search="", sort="Date newest", limit=250):
    ensure_schema()
    search_value = f"%{search.strip().lower()}%" if search.strip() else None
    order_by = _order_sort_clause(sort)
    base_sql = f"""
        SELECT o.shopify_order_id, o.order_name, o.order_number, o.admin_url,
               o.customer_name, o.customer_email, o.financial_status, o.fulfillment_status,
               o.total_price, o.currency, o.created_at, o.processed_at,
               eo.id AS edition_order_id, eo.shopify_line_item_id, eo.shopify_handle,
               eo.product_title, eo.variant_title, eo.sku, eo.edition_number,
               eo.edition_total, eo.allocation_index, eo.assigned_at, eo.certificate_status,
               c.local_file_path, c.shopify_file_url,
               psd.asset_url AS psd_url,
               prodigi.asset_url AS prodigi_url
        FROM shopify_orders o
        LEFT JOIN edition_orders eo ON eo.shopify_order_id = o.shopify_order_id
        LEFT JOIN certificates c ON c.edition_order_id = eo.id
        LEFT JOIN product_assets psd ON psd.shopify_handle = eo.shopify_handle AND psd.asset_type = 'psd_master_file' AND psd.is_primary IS DISTINCT FROM FALSE
        LEFT JOIN product_assets prodigi ON prodigi.shopify_handle = eo.shopify_handle AND prodigi.asset_type = 'prodigi_link'
    """
    where = ""
    params = []
    if search_value:
        where = """
            WHERE LOWER(COALESCE(o.order_name, '')) LIKE %s
               OR LOWER(COALESCE(o.order_number, '')) LIKE %s
               OR LOWER(COALESCE(o.customer_name, '')) LIKE %s
               OR LOWER(COALESCE(o.customer_email, '')) LIKE %s
               OR LOWER(COALESCE(eo.product_title, '')) LIKE %s
               OR LOWER(COALESCE(eo.sku, '')) LIKE %s
               OR CAST(COALESCE(eo.edition_number, 0) AS TEXT) LIKE %s
        """
        params = [search_value] * 6 + [f"%{search.strip()}%"]
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
                SELECT
                    (SELECT COUNT(*) FROM shopify_orders) AS orders_synced,
                    (SELECT COUNT(*) FROM shopify_orders o
                     WHERE NOT EXISTS (
                        SELECT 1 FROM edition_orders eo WHERE eo.shopify_order_id=o.shopify_order_id
                     )) AS needs_edition,
                    (SELECT COUNT(*) FROM edition_orders WHERE assigned_at::date = CURRENT_DATE) AS assigned_today,
                    (SELECT COUNT(*) FROM edition_orders eo
                     LEFT JOIN certificates c ON c.edition_order_id=eo.id
                     WHERE c.id IS NULL) AS certificates_missing,
                    (SELECT COUNT(*) FROM edition_orders eo
                     LEFT JOIN product_assets pa ON pa.shopify_handle=eo.shopify_handle AND pa.asset_type='psd_master_file' AND pa.is_primary IS DISTINCT FROM FALSE
                     WHERE COALESCE(pa.asset_url, '')='') AS psd_links_missing,
                    (SELECT COUNT(*) FROM edition_orders eo
                     LEFT JOIN product_assets pa ON pa.shopify_handle=eo.shopify_handle AND pa.asset_type='prodigi_link'
                     WHERE COALESCE(pa.asset_url, '')='') AS prodigi_links_missing
                """
            )
            return cur.fetchone() or {}


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
                          AND COALESCE(pa.asset_url, '') <> ''
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
                GROUP BY ep.shopify_handle, ep.product_title, ep.next_edition_number
                HAVING COALESCE(ep.next_edition_number, 1) < COALESCE(MAX(eo.edition_number), 0) + 1
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
