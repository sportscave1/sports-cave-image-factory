from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from difflib import SequenceMatcher
import json
import os
import re
import sqlite3


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "sports_cave_os.db"
DB_PATH = Path(os.getenv("SPORTS_CAVE_DB_PATH", str(DEFAULT_DB_PATH)))

PRODUCT_STATUSES = (
    "Idea",
    "Artwork Ready",
    "Mockups Ready",
    "Upload In Progress",
    "Ready for Review",
    "Live",
    "Needs Fixing",
    "Archived",
)

SPORT_CATEGORIES = (
    "NBA",
    "Soccer",
    "Motorsport",
    "Cricket",
    "AFL",
    "NFL",
    "Baseball",
    "Hockey",
    "Horse Racing",
    "Tennis",
    "Boxing",
    "MMA",
    "Golf",
    "Other",
)

COUNTRY_FOCUS_OPTIONS = (
    "Australia",
    "USA",
    "UK",
    "Canada",
    "New Zealand",
    "Global",
)

EDITION_STATUSES = (
    "Not Set",
    "Available",
    "Count",
    "Low",
    "Final Editions",
    "Sold Out",
    "Archived",
)

ORDER_ASSIGNMENT_STATUSES = (
    "Needs Edition",
    "Assigned",
    "Already Assigned",
    "Product Not Found",
    "Needs Edition Setup",
    "Sold Out",
    "Error",
    "Voided",
    "Refunded",
)

PRODUCT_FIELDS = (
    "shopify_product_id",
    "product_name",
    "handle",
    "sport_category",
    "country_focus",
    "status",
    "shopify_admin_url",
    "live_product_url",
    "prodigi_product_id",
    "prodigi_product_url",
    "prodigi_notes",
    "psd_file_url",
    "jpg_file_url",
    "final_jpg_url",
    "webp_folder_url",
    "mockup_folder_url",
    "size_guide_url",
    "lifestyle_folder_url",
    "prompt_pack_url",
    "product_upload_zip_url",
    "certificate_folder_url",
    "ads_social_folder_url",
    "google_drive_root_folder_url",
    "notes",
)

ASSET_STATUS_OPTIONS = (
    "Missing",
    "Connected",
    "Needs Review",
    "Approved",
)

ASSET_DEFINITIONS = (
    {
        "key": "psd",
        "url_field": "psd_file_url",
        "label": "PSD File",
        "short_label": "PSD",
        "open_label": "Open PSD",
        "group": "Source Files",
        "core": True,
    },
    {
        "key": "final_jpg",
        "url_field": "final_jpg_url",
        "label": "Final JPG",
        "short_label": "JPG",
        "open_label": "Open JPG",
        "group": "Source Files",
        "core": True,
    },
    {
        "key": "webp",
        "url_field": "webp_folder_url",
        "label": "WebP Folder",
        "short_label": "WebP",
        "open_label": "Open WebP Folder",
        "group": "Shopify Upload Assets",
        "core": True,
    },
    {
        "key": "mockups",
        "url_field": "mockup_folder_url",
        "label": "Mockup Folder",
        "short_label": "Mockups",
        "open_label": "Open Mockups",
        "group": "Shopify Upload Assets",
        "core": True,
    },
    {
        "key": "size_guide",
        "url_field": "size_guide_url",
        "label": "Size Guide",
        "short_label": "Size Guide",
        "open_label": "Open Size Guide",
        "group": "Shopify Upload Assets",
        "core": False,
    },
    {
        "key": "product_upload_zip",
        "url_field": "product_upload_zip_url",
        "label": "Product Upload ZIP",
        "short_label": "ZIP",
        "open_label": "Open ZIP",
        "group": "Shopify Upload Assets",
        "core": False,
    },
    {
        "key": "lifestyle",
        "url_field": "lifestyle_folder_url",
        "label": "Lifestyle Folder",
        "short_label": "Lifestyle",
        "open_label": "Open Lifestyle",
        "group": "Lifestyle & Marketing Assets",
        "core": False,
    },
    {
        "key": "prompt_pack",
        "url_field": "prompt_pack_url",
        "label": "Prompt Pack",
        "short_label": "Prompt Pack",
        "open_label": "Open Prompt Pack",
        "group": "Lifestyle & Marketing Assets",
        "core": False,
    },
    {
        "key": "ads_social",
        "url_field": "ads_social_folder_url",
        "label": "Ads/Social Folder",
        "short_label": "Ads/Social",
        "open_label": "Open Ads/Social",
        "group": "Lifestyle & Marketing Assets",
        "core": False,
    },
    {
        "key": "certificates",
        "url_field": "certificate_folder_url",
        "label": "Certificate Folder",
        "short_label": "Certificates",
        "open_label": "Open Certificates",
        "group": "Collector / Certificate Assets",
        "core": False,
    },
)

ASSET_BY_KEY = {asset["key"]: asset for asset in ASSET_DEFINITIONS}
ASSET_GROUP_NAMES = tuple(dict.fromkeys(asset["group"] for asset in ASSET_DEFINITIONS))
CORE_ASSET_KEYS = tuple(asset["key"] for asset in ASSET_DEFINITIONS if asset["core"])

CORE_FILE_FIELDS = (
    ("psd_file_url", "PSD link"),
    ("final_jpg_url", "Final JPG link"),
    ("webp_folder_url", "WebP folder"),
    ("mockup_folder_url", "Mockup folder"),
)

FILE_HUB_FIELDS = tuple(
    (asset["url_field"], asset["label"])
    for asset in ASSET_DEFINITIONS
)

def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_database_directory():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_connection():
    ensure_database_directory()
    connection = sqlite3.connect(DB_PATH, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def ensure_column(connection, table_name, column_name, definition):
    columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def init_db():
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shopify_product_id TEXT,
                product_name TEXT NOT NULL,
                handle TEXT,
                sport_category TEXT NOT NULL DEFAULT 'Other',
                country_focus TEXT NOT NULL DEFAULT 'Global',
                status TEXT NOT NULL DEFAULT 'Idea',
                shopify_admin_url TEXT,
                live_product_url TEXT,
                prodigi_product_id TEXT,
                prodigi_product_url TEXT,
                prodigi_notes TEXT,
                psd_file_url TEXT,
                jpg_file_url TEXT,
                final_jpg_url TEXT,
                webp_folder_url TEXT,
                mockup_folder_url TEXT,
                size_guide_url TEXT,
                lifestyle_folder_url TEXT,
                prompt_pack_url TEXT,
                product_upload_zip_url TEXT,
                certificate_folder_url TEXT,
                ads_social_folder_url TEXT,
                google_drive_root_folder_url TEXT,
                notes TEXT,
                archived_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS limited_editions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL UNIQUE,
                edition_limit INTEGER,
                editions_sold INTEGER NOT NULL DEFAULT 0,
                editions_remaining INTEGER,
                next_edition_number INTEGER,
                edition_status TEXT NOT NULL DEFAULT 'Not Set',
                last_synced_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS product_assets (
                product_id INTEGER NOT NULL,
                asset_key TEXT NOT NULL,
                manual_status TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (product_id, asset_key),
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS shopify_products (
                shopify_product_id TEXT PRIMARY KEY,
                legacy_resource_id TEXT,
                title TEXT NOT NULL,
                handle TEXT,
                status TEXT,
                vendor TEXT,
                product_type TEXT,
                variant_count INTEGER NOT NULL DEFAULT 0,
                image_count INTEGER NOT NULL DEFAULT 0,
                tags_json TEXT NOT NULL DEFAULT '[]',
                collections_json TEXT NOT NULL DEFAULT '[]',
                variants_json TEXT NOT NULL DEFAULT '[]',
                images_json TEXT NOT NULL DEFAULT '[]',
                metafields_json TEXT NOT NULL DEFAULT '[]',
                online_store_url TEXT,
                admin_url TEXT,
                remote_updated_at TEXT,
                synced_at TEXT NOT NULL,
                matched_product_id INTEGER UNIQUE,
                match_source TEXT,
                FOREIGN KEY (matched_product_id) REFERENCES products(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS shopify_sync_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL,
                products_seen INTEGER NOT NULL DEFAULT 0,
                pages_synced INTEGER NOT NULL DEFAULT 0,
                error_message TEXT,
                api_version TEXT,
                store_domain TEXT
            );

            CREATE TABLE IF NOT EXISTS shopify_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shopify_order_id TEXT NOT NULL UNIQUE,
                legacy_resource_id TEXT,
                order_name TEXT,
                order_number TEXT,
                admin_url TEXT,
                created_at TEXT,
                processed_at TEXT,
                paid_at TEXT,
                financial_status TEXT,
                fulfillment_status TEXT,
                customer_name TEXT,
                customer_email TEXT,
                total_price TEXT,
                currency TEXT,
                cancelled_at TEXT,
                last_synced_at TEXT NOT NULL,
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS order_line_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                shopify_line_item_id TEXT NOT NULL UNIQUE,
                shopify_product_id TEXT,
                product_title TEXT,
                product_handle TEXT,
                variant_title TEXT,
                sku TEXT,
                quantity INTEGER NOT NULL DEFAULT 1,
                assignment_status TEXT NOT NULL DEFAULT 'Needs Edition',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (order_id) REFERENCES shopify_orders(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS edition_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                line_item_id INTEGER NOT NULL,
                shopify_order_id TEXT NOT NULL,
                shopify_line_item_id TEXT NOT NULL,
                shopify_product_id TEXT NOT NULL,
                product_title TEXT,
                edition_number INTEGER NOT NULL,
                edition_limit INTEGER NOT NULL,
                assignment_status TEXT NOT NULL DEFAULT 'Assigned',
                assigned_at TEXT NOT NULL,
                voided_at TEXT,
                certificate_pdf_path TEXT,
                certificate_id TEXT,
                certificate_generated_at TEXT,
                notes TEXT,
                FOREIGN KEY (order_id) REFERENCES shopify_orders(id) ON DELETE CASCADE,
                FOREIGN KEY (line_item_id) REFERENCES order_line_items(id) ON DELETE CASCADE,
                UNIQUE (shopify_product_id, edition_number),
                UNIQUE (shopify_line_item_id, edition_number)
            );

            CREATE TABLE IF NOT EXISTS edition_assignment_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                assignment_id INTEGER,
                shopify_order_id TEXT,
                shopify_line_item_id TEXT,
                shopify_product_id TEXT,
                old_edition_number INTEGER,
                new_edition_number INTEGER,
                action TEXT NOT NULL,
                notes TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (assignment_id) REFERENCES edition_assignments(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS shopify_order_sync_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL,
                orders_seen INTEGER NOT NULL DEFAULT 0,
                assignments_created INTEGER NOT NULL DEFAULT 0,
                pages_synced INTEGER NOT NULL DEFAULT 0,
                error_message TEXT,
                api_version TEXT,
                store_domain TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_products_name ON products(product_name);
            CREATE INDEX IF NOT EXISTS idx_products_status ON products(status);
            CREATE INDEX IF NOT EXISTS idx_products_sport ON products(sport_category);
            CREATE INDEX IF NOT EXISTS idx_editions_status ON limited_editions(edition_status);
            CREATE INDEX IF NOT EXISTS idx_product_assets_status ON product_assets(manual_status);
            CREATE INDEX IF NOT EXISTS idx_shopify_products_handle ON shopify_products(handle);
            CREATE INDEX IF NOT EXISTS idx_shopify_products_status ON shopify_products(status);
            CREATE INDEX IF NOT EXISTS idx_shopify_products_match ON shopify_products(matched_product_id);
            CREATE INDEX IF NOT EXISTS idx_shopify_orders_created ON shopify_orders(created_at);
            CREATE INDEX IF NOT EXISTS idx_order_line_items_order ON order_line_items(order_id);
            CREATE INDEX IF NOT EXISTS idx_order_line_items_product ON order_line_items(shopify_product_id);
            CREATE INDEX IF NOT EXISTS idx_assignments_order ON edition_assignments(order_id);
            CREATE INDEX IF NOT EXISTS idx_assignments_line ON edition_assignments(line_item_id);
            """
        )
        ensure_column(connection, "products", "prodigi_product_url", "TEXT")
        ensure_column(connection, "products", "prodigi_notes", "TEXT")
        ensure_column(connection, "products", "archived_at", "TEXT")
        for field in (
            "final_jpg_url",
            "size_guide_url",
            "lifestyle_folder_url",
            "prompt_pack_url",
            "product_upload_zip_url",
            "ads_social_folder_url",
            "google_drive_root_folder_url",
        ):
            ensure_column(connection, "products", field, "TEXT")
        ensure_column(connection, "shopify_products", "variant_count", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(connection, "shopify_products", "image_count", "INTEGER NOT NULL DEFAULT 0")
        for column_name, definition in (
            ("processed_at", "TEXT"),
            ("total_price", "TEXT"),
            ("currency", "TEXT"),
        ):
            ensure_column(connection, "shopify_orders", column_name, definition)
        ensure_column(connection, "order_line_items", "sku", "TEXT")
        for column_name, definition in (
            ("certificate_pdf_path", "TEXT"),
            ("certificate_id", "TEXT"),
            ("certificate_generated_at", "TEXT"),
        ):
            ensure_column(connection, "edition_assignments", column_name, definition)
        for column_name, definition in (
            ("edition_limit", "INTEGER DEFAULT 100"),
            ("next_available_edition", "INTEGER DEFAULT 1"),
            ("editions_sold", "INTEGER DEFAULT 0"),
            ("editions_remaining", "INTEGER DEFAULT 100"),
            ("edition_status", "TEXT DEFAULT 'Available'"),
            ("psd_file_url", "TEXT"),
            ("prodigi_url", "TEXT"),
            ("prodigi_product_id", "TEXT"),
            ("edition_notes", "TEXT"),
            ("last_edition_sync_at", "TEXT"),
            ("edition_updated_at", "TEXT"),
            ("created_at", "TEXT"),
            ("updated_at", "TEXT"),
        ):
            ensure_column(connection, "shopify_products", column_name, definition)
        connection.execute(
            """
            UPDATE products
            SET final_jpg_url = jpg_file_url
            WHERE COALESCE(final_jpg_url, '') = '' AND COALESCE(jpg_file_url, '') != ''
            """
        )
        connection.execute(
            """
            UPDATE products
            SET jpg_file_url = final_jpg_url
            WHERE COALESCE(jpg_file_url, '') = '' AND COALESCE(final_jpg_url, '') != ''
            """
        )
        connection.execute("UPDATE products SET status = 'Idea' WHERE status = 'Draft'")
        connection.execute("UPDATE products SET status = 'Ready for Review' WHERE status = 'Needs Review'")
        timestamp = utc_now()
        connection.execute(
            """
            UPDATE shopify_products
            SET edition_limit = COALESCE(edition_limit, 100),
                next_available_edition = COALESCE(next_available_edition, 1),
                editions_sold = COALESCE(editions_sold, 0),
                editions_remaining = COALESCE(editions_remaining, 100),
                edition_status = COALESCE(NULLIF(edition_status, ''), 'Available'),
                created_at = COALESCE(created_at, synced_at, ?),
                updated_at = COALESCE(updated_at, synced_at, ?)
            """,
            (timestamp, timestamp),
        )
        connection.execute(
            """
            UPDATE shopify_products
            SET edition_limit = COALESCE(
                    (SELECT le.edition_limit FROM limited_editions le
                     WHERE le.product_id = shopify_products.matched_product_id), edition_limit),
                next_available_edition = COALESCE(
                    (SELECT le.next_edition_number FROM limited_editions le
                     WHERE le.product_id = shopify_products.matched_product_id), next_available_edition),
                editions_sold = COALESCE(
                    (SELECT le.editions_sold FROM limited_editions le
                     WHERE le.product_id = shopify_products.matched_product_id), editions_sold),
                editions_remaining = COALESCE(
                    (SELECT le.editions_remaining FROM limited_editions le
                     WHERE le.product_id = shopify_products.matched_product_id), editions_remaining),
                edition_status = COALESCE(
                    (SELECT le.edition_status FROM limited_editions le
                     WHERE le.product_id = shopify_products.matched_product_id), edition_status),
                psd_file_url = COALESCE(NULLIF(psd_file_url, ''),
                    (SELECT p.psd_file_url FROM products p
                     WHERE p.id = shopify_products.matched_product_id), ''),
                prodigi_url = COALESCE(NULLIF(prodigi_url, ''),
                    (SELECT p.prodigi_product_url FROM products p
                     WHERE p.id = shopify_products.matched_product_id), ''),
                prodigi_product_id = COALESCE(NULLIF(prodigi_product_id, ''),
                    (SELECT p.prodigi_product_id FROM products p
                     WHERE p.id = shopify_products.matched_product_id), '')
            WHERE matched_product_id IS NOT NULL
            """
        )


def parse_json_list(value):
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def normalize_match_value(value):
    return " ".join(str(value or "").strip().lower().split())


def start_shopify_sync(store_domain, api_version):
    timestamp = utc_now()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO shopify_sync_runs (
                started_at, status, products_seen, pages_synced, api_version, store_domain
            ) VALUES (?, 'Running', 0, 0, ?, ?)
            """,
            (timestamp, api_version, store_domain),
        )
    return cursor.lastrowid


def update_shopify_sync_run(
    run_id,
    *,
    status=None,
    products_seen=None,
    pages_synced=None,
    error_message=None,
    api_version=None,
):
    fields = {}
    if status is not None:
        fields["status"] = status
    if products_seen is not None:
        fields["products_seen"] = int(products_seen)
    if pages_synced is not None:
        fields["pages_synced"] = int(pages_synced)
    if error_message is not None:
        fields["error_message"] = str(error_message)[:2000]
    if api_version is not None:
        fields["api_version"] = str(api_version)
    if status in {"Complete", "Failed"}:
        fields["completed_at"] = utc_now()
    if not fields:
        return

    assignments = ", ".join(f"{field} = ?" for field in fields)
    with get_connection() as connection:
        connection.execute(
            f"UPDATE shopify_sync_runs SET {assignments} WHERE id = ?",
            (*fields.values(), run_id),
        )


def get_latest_shopify_sync_run():
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM shopify_sync_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def upsert_shopify_products(products):
    timestamp = utc_now()
    with get_connection() as connection:
        for product in products:
            connection.execute(
                """
                INSERT INTO shopify_products (
                    shopify_product_id, legacy_resource_id, title, handle, status,
                    vendor, product_type, variant_count, image_count,
                    tags_json, collections_json, variants_json,
                    images_json, metafields_json, online_store_url, admin_url,
                    remote_updated_at, synced_at, edition_limit,
                    next_available_edition, editions_sold, editions_remaining,
                    edition_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 100, 1, 0, 100, 'Available', ?, ?)
                ON CONFLICT(shopify_product_id) DO UPDATE SET
                    legacy_resource_id = excluded.legacy_resource_id,
                    title = excluded.title,
                    handle = excluded.handle,
                    status = excluded.status,
                    vendor = excluded.vendor,
                    product_type = excluded.product_type,
                    variant_count = excluded.variant_count,
                    image_count = excluded.image_count,
                    tags_json = excluded.tags_json,
                    collections_json = excluded.collections_json,
                    variants_json = excluded.variants_json,
                    images_json = excluded.images_json,
                    metafields_json = excluded.metafields_json,
                    online_store_url = excluded.online_store_url,
                    admin_url = excluded.admin_url,
                    remote_updated_at = excluded.remote_updated_at,
                    synced_at = excluded.synced_at,
                    updated_at = excluded.updated_at
                """,
                (
                    product["shopify_product_id"],
                    product.get("legacy_resource_id") or "",
                    product.get("title") or "Untitled Shopify Product",
                    product.get("handle") or "",
                    product.get("status") or "UNKNOWN",
                    product.get("vendor") or "",
                    product.get("product_type") or "",
                    len(product.get("variants") or []),
                    len(product.get("images") or []),
                    json.dumps(product.get("tags") or []),
                    json.dumps(product.get("collections") or []),
                    json.dumps(product.get("variants") or []),
                    json.dumps(product.get("images") or []),
                    json.dumps(product.get("metafields") or []),
                    product.get("online_store_url") or "",
                    product.get("admin_url") or "",
                    product.get("remote_updated_at") or "",
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )


def auto_match_shopify_products():
    matched_count = 0
    with get_connection() as connection:
        remote_rows = connection.execute(
            """
            SELECT shopify_product_id, handle
            FROM shopify_products
            WHERE matched_product_id IS NULL
            """
        ).fetchall()
        for remote in remote_rows:
            internal = connection.execute(
                """
                SELECT id
                FROM products
                WHERE shopify_product_id = ? AND status != 'Archived'
                ORDER BY id
                LIMIT 1
                """,
                (remote["shopify_product_id"],),
            ).fetchone()
            source = "Existing ID"
            if not internal and remote["handle"]:
                handle_matches = connection.execute(
                    """
                    SELECT id
                    FROM products
                    WHERE LOWER(TRIM(handle)) = LOWER(TRIM(?)) AND status != 'Archived'
                    ORDER BY id
                    """,
                    (remote["handle"],),
                ).fetchall()
                if len(handle_matches) == 1:
                    internal = handle_matches[0]
                    source = "Exact Handle"
            if not internal:
                continue
            existing_match = connection.execute(
                "SELECT shopify_product_id FROM shopify_products WHERE matched_product_id = ?",
                (internal["id"],),
            ).fetchone()
            if existing_match:
                continue
            connection.execute(
                """
                UPDATE shopify_products
                SET matched_product_id = ?, match_source = ?
                WHERE shopify_product_id = ?
                """,
                (internal["id"], source, remote["shopify_product_id"]),
            )
            matched_count += 1
        matched_rows = connection.execute(
            """
            SELECT sp.*, p.handle AS internal_handle
            FROM shopify_products sp
            JOIN products p ON p.id = sp.matched_product_id
            """
        ).fetchall()
        for row in matched_rows:
            connection.execute(
                """
                UPDATE products
                SET shopify_product_id = ?,
                    handle = CASE WHEN COALESCE(TRIM(handle), '') = '' THEN ? ELSE handle END,
                    shopify_admin_url = ?,
                    live_product_url = CASE
                        WHEN COALESCE(?, '') != '' THEN ? ELSE live_product_url END,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    row["shopify_product_id"],
                    row["handle"],
                    row["admin_url"],
                    row["online_store_url"],
                    row["online_store_url"],
                    utc_now(),
                    row["matched_product_id"],
                ),
            )
    return matched_count


def hydrate_shopify_product(row):
    if not row:
        return None
    product = dict(row)
    for field in ("tags", "collections", "variants", "images", "metafields"):
        product[field] = parse_json_list(product.pop(f"{field}_json", "[]"))
    product["variant_count"] = int(product.get("variant_count") or len(product["variants"]))
    product["image_count"] = int(product.get("image_count") or len(product["images"]))
    return product


def hydrate_shopify_summary(row):
    if not row:
        return None
    product = dict(row)
    product["variant_count"] = int(product.get("variant_count") or 0)
    product["image_count"] = int(product.get("image_count") or 0)
    return product


def list_shopify_products(search="", status="All", match_filter="All"):
    clauses = []
    values = []
    if search.strip():
        clauses.append("(LOWER(sp.title) LIKE ? OR LOWER(sp.handle) LIKE ?)")
        value = f"%{search.strip().lower()}%"
        values.extend((value, value))
    if status != "All":
        clauses.append("sp.status = ?")
        values.append(status)
    if match_filter == "Matched":
        clauses.append("sp.matched_product_id IS NOT NULL")
    elif match_filter == "Unmatched":
        clauses.append("sp.matched_product_id IS NULL")
    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT sp.shopify_product_id, sp.legacy_resource_id, sp.title, sp.handle,
                   sp.status, sp.vendor, sp.product_type, sp.variant_count, sp.image_count,
                   sp.online_store_url, sp.admin_url, sp.remote_updated_at, sp.synced_at,
                   sp.matched_product_id, sp.match_source,
                   p.product_name AS matched_product_name
            FROM shopify_products sp
            LEFT JOIN products p ON p.id = sp.matched_product_id
            {where_clause}
            ORDER BY sp.remote_updated_at DESC, sp.title COLLATE NOCASE
            """,
            values,
        ).fetchall()
    return [hydrate_shopify_summary(row) for row in rows]


def mark_missing_shopify_products(fetched_product_ids):
    fetched_ids = {str(product_id or "").strip() for product_id in fetched_product_ids if product_id}
    if not fetched_ids:
        return 0
    placeholders = ", ".join("?" for _ in fetched_ids)
    timestamp = utc_now()
    with get_connection() as connection:
        cursor = connection.execute(
            f"""
            UPDATE shopify_products
            SET status = 'MISSING', updated_at = ?
            WHERE shopify_product_id NOT IN ({placeholders})
              AND status != 'MISSING'
            """,
            (timestamp, *fetched_ids),
        )
    return cursor.rowcount


def get_shopify_product(shopify_product_id):
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT sp.*, p.product_name AS matched_product_name
            FROM shopify_products sp
            LEFT JOIN products p ON p.id = sp.matched_product_id
            WHERE sp.shopify_product_id = ?
            """,
            (shopify_product_id,),
        ).fetchone()
    return hydrate_shopify_product(row)


def match_shopify_product(shopify_product_id, product_id, source="Manual"):
    timestamp = utc_now()
    with get_connection() as connection:
        remote = connection.execute(
            "SELECT * FROM shopify_products WHERE shopify_product_id = ?",
            (shopify_product_id,),
        ).fetchone()
        internal = connection.execute(
            "SELECT id, handle FROM products WHERE id = ?",
            (product_id,),
        ).fetchone()
        if not remote or not internal:
            raise ValueError("The Shopify or internal product record could not be found.")

        previous_product_id = remote["matched_product_id"]
        if previous_product_id and previous_product_id != product_id:
            connection.execute(
                """
                UPDATE products
                SET shopify_product_id = '', updated_at = ?
                WHERE id = ? AND shopify_product_id = ?
                """,
                (timestamp, previous_product_id, shopify_product_id),
            )

        connection.execute(
            "UPDATE shopify_products SET matched_product_id = NULL, match_source = NULL WHERE matched_product_id = ?",
            (product_id,),
        )
        connection.execute(
            """
            UPDATE shopify_products
            SET matched_product_id = ?, match_source = ?
            WHERE shopify_product_id = ?
            """,
            (product_id, source, shopify_product_id),
        )
        connection.execute(
            """
            UPDATE products
            SET shopify_product_id = ?,
                handle = CASE WHEN COALESCE(TRIM(handle), '') = '' THEN ? ELSE handle END,
                shopify_admin_url = ?,
                live_product_url = CASE WHEN COALESCE(?, '') != '' THEN ? ELSE live_product_url END,
                updated_at = ?
            WHERE id = ?
            """,
            (
                shopify_product_id,
                remote["handle"],
                remote["admin_url"],
                remote["online_store_url"],
                remote["online_store_url"],
                timestamp,
                product_id,
            ),
        )


def unmatch_shopify_product(shopify_product_id):
    with get_connection() as connection:
        row = connection.execute(
            "SELECT matched_product_id FROM shopify_products WHERE shopify_product_id = ?",
            (shopify_product_id,),
        ).fetchone()
        if not row:
            return
        matched_product_id = row["matched_product_id"]
        connection.execute(
            """
            UPDATE shopify_products
            SET matched_product_id = NULL, match_source = NULL
            WHERE shopify_product_id = ?
            """,
            (shopify_product_id,),
        )
        if matched_product_id:
            connection.execute(
                """
                UPDATE products
                SET shopify_product_id = '', updated_at = ?
                WHERE id = ? AND shopify_product_id = ?
                """,
                (utc_now(), matched_product_id, shopify_product_id),
            )


def create_product_from_shopify(shopify_product_id):
    remote = get_shopify_product(shopify_product_id)
    if not remote:
        raise ValueError("The Shopify product could not be found in the local sync cache.")
    if remote.get("matched_product_id"):
        return remote["matched_product_id"]

    status_map = {"ACTIVE": "Live", "ARCHIVED": "Archived", "DRAFT": "Idea"}
    product_id = create_product(
        {
            "shopify_product_id": remote["shopify_product_id"],
            "product_name": remote["title"],
            "handle": remote["handle"],
            "sport_category": "Other",
            "country_focus": "Global",
            "status": status_map.get(remote["status"], "Idea"),
            "shopify_admin_url": remote["admin_url"],
            "live_product_url": remote["online_store_url"],
        }
    )
    match_shopify_product(shopify_product_id, product_id, source="Created from Shopify")
    return product_id


def get_shopify_match_map(product_ids):
    product_ids = tuple(dict.fromkeys(int(product_id) for product_id in product_ids))
    if not product_ids:
        return {}
    placeholders = ", ".join("?" for _ in product_ids)
    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT shopify_product_id, legacy_resource_id, title, handle, status,
                   vendor, product_type, variant_count, image_count,
                   online_store_url, admin_url, remote_updated_at, synced_at,
                   matched_product_id, match_source
            FROM shopify_products
            WHERE matched_product_id IN ({placeholders})
            """,
            product_ids,
        ).fetchall()
    return {row["matched_product_id"]: hydrate_shopify_summary(row) for row in rows}


def get_shopify_summary():
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN matched_product_id IS NOT NULL THEN 1 ELSE 0 END) AS matched,
                   SUM(CASE WHEN matched_product_id IS NULL THEN 1 ELSE 0 END) AS unmatched,
                   MAX(synced_at) AS last_synced_at
            FROM shopify_products
            """
        ).fetchone()
    return {
        "total": int(row["total"] or 0),
        "matched": int(row["matched"] or 0),
        "unmatched": int(row["unmatched"] or 0),
        "last_synced_at": row["last_synced_at"],
    }


def calculate_shopify_edition_values(
    edition_limit,
    next_available_edition,
    editions_sold,
    *,
    allow_oversold=False,
):
    if edition_limit in (None, ""):
        return {
            "edition_limit": None,
            "next_available_edition": None,
            "editions_sold": max(int(editions_sold or 0), 0),
            "editions_remaining": None,
            "edition_status": "Not Set",
            "edition_display_text": "EDITION DETAILS COMING SOON",
        }

    limit_value = int(edition_limit)
    next_value = int(next_available_edition or 1)
    sold_value = int(editions_sold or 0)
    if limit_value < 1:
        raise ValueError("Edition limit must be at least 1.")
    if next_value < 1 or next_value > limit_value + 1:
        raise ValueError("Next available edition must be between 1 and edition limit + 1.")
    if sold_value < 0:
        raise ValueError("Editions sold cannot be negative.")
    if sold_value > limit_value and not allow_oversold:
        raise ValueError("Editions sold cannot exceed the edition limit without confirmation.")

    remaining = max(limit_value - sold_value, 0)
    if remaining <= 0 or next_value > limit_value:
        status = "Sold Out"
        display_text = "SOLD OUT EDITION"
    elif remaining <= 3:
        status = "Final Editions"
        display_text = f"FINAL EDITION #{next_value} OF {limit_value} AVAILABLE"
    elif remaining <= 6:
        status = "Low"
        display_text = f"EDITION #{next_value} OF {limit_value} AVAILABLE"
    elif remaining <= 12:
        status = "Count"
        display_text = f"EDITION #{next_value} OF {limit_value} AVAILABLE"
    else:
        status = "Available"
        display_text = f"EDITION #{next_value} OF {limit_value} AVAILABLE"

    return {
        "edition_limit": limit_value,
        "next_available_edition": next_value,
        "editions_sold": sold_value,
        "editions_remaining": remaining,
        "edition_status": status,
        "edition_display_text": display_text,
    }


def hydrate_shopify_edition_product(row):
    if not row:
        return None
    product = dict(row)
    for field in (
        "edition_limit",
        "next_available_edition",
        "editions_sold",
        "editions_remaining",
    ):
        if product.get(field) is not None:
            product[field] = int(product[field])
    values = calculate_shopify_edition_values(
        product.get("edition_limit"),
        product.get("next_available_edition"),
        product.get("editions_sold"),
        allow_oversold=True,
    )
    product.update(values)
    product["shopify_handle"] = product.get("handle") or ""
    product["product_title"] = product.get("title") or "Untitled Shopify Product"
    product["prodigi_status"] = "Connected" if product.get("prodigi_url") else "Missing"
    product["psd_status"] = "Connected" if product.get("psd_file_url") else "Missing"
    product["last_shopify_sync_at"] = product.get("synced_at")
    last_sync = product.get("last_edition_sync_at") or ""
    local_update = product.get("edition_updated_at") or product.get("updated_at") or ""
    product["widget_sync_status"] = "Synced" if last_sync and last_sync >= local_update else "Needs Sync"
    return product


def list_shopify_edition_products(
    search="",
    shopify_status="All",
    edition_filter="All",
    limit=25,
    missing_psd_only=False,
    missing_prodigi_only=False,
):
    clauses = []
    values = []
    if search.strip():
        search_value = f"%{search.strip().lower()}%"
        clauses.append(
            """
            (
                LOWER(sp.title) LIKE ?
                OR LOWER(sp.handle) LIKE ?
                OR LOWER(sp.variants_json) LIKE ?
                OR EXISTS (
                    SELECT 1
                    FROM order_line_items li
                    WHERE li.shopify_product_id = sp.shopify_product_id
                      AND (
                          LOWER(li.product_title) LIKE ?
                          OR LOWER(li.variant_title) LIKE ?
                      )
                )
            )
            """
        )
        values.extend((search_value, search_value, search_value, search_value, search_value))
    if shopify_status != "All":
        clauses.append("sp.status = ?")
        values.append(shopify_status.upper())
    filter_clauses = {
        "Edition Not Set": "(sp.edition_limit IS NULL OR sp.edition_status = 'Not Set')",
        "Not Set": "(sp.edition_limit IS NULL OR sp.edition_status = 'Not Set')",
        "Available": "sp.edition_status IN ('Available', 'Count', 'Low')",
        "Count": "sp.edition_status = 'Count'",
        "Low": "sp.edition_status = 'Low'",
        "Final Editions": "sp.edition_status = 'Final Editions'",
        "Sold Out": "sp.edition_status = 'Sold Out'",
        "Missing PSD": "COALESCE(NULLIF(sp.psd_file_url, ''), NULLIF(p.psd_file_url, '')) IS NULL",
        "Missing Prodigi": "COALESCE(NULLIF(sp.prodigi_url, ''), NULLIF(p.prodigi_product_url, '')) IS NULL",
    }
    if edition_filter in filter_clauses:
        clauses.append(filter_clauses[edition_filter])
    if missing_psd_only:
        clauses.append("COALESCE(NULLIF(sp.psd_file_url, ''), NULLIF(p.psd_file_url, '')) IS NULL")
    if missing_prodigi_only:
        clauses.append("COALESCE(NULLIF(sp.prodigi_url, ''), NULLIF(p.prodigi_product_url, '')) IS NULL")
    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    display_limit = min(max(int(limit), 1), 5000)
    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT sp.shopify_product_id, sp.legacy_resource_id, sp.title, sp.handle,
                   sp.status, sp.online_store_url, sp.admin_url, sp.synced_at,
                   sp.edition_limit, sp.next_available_edition, sp.editions_sold,
                   sp.editions_remaining, sp.edition_status,
                   COALESCE(NULLIF(sp.psd_file_url, ''), p.psd_file_url, '') AS psd_file_url,
                   COALESCE(NULLIF(sp.prodigi_url, ''), p.prodigi_product_url, '') AS prodigi_url,
                   COALESCE(NULLIF(sp.prodigi_product_id, ''), p.prodigi_product_id, '') AS prodigi_product_id,
                   sp.edition_notes, sp.last_edition_sync_at, sp.edition_updated_at,
                   sp.updated_at, sp.matched_product_id
            FROM shopify_products sp
            LEFT JOIN products p ON p.id = sp.matched_product_id
            {where_clause}
            ORDER BY sp.title COLLATE NOCASE
            LIMIT ?
            """,
            (*values, display_limit),
        ).fetchall()
    return [hydrate_shopify_edition_product(row) for row in rows]


def list_all_shopify_edition_products():
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT sp.shopify_product_id, sp.legacy_resource_id, sp.title, sp.handle,
                   sp.status, sp.online_store_url, sp.admin_url, sp.synced_at,
                   sp.edition_limit, sp.next_available_edition, sp.editions_sold,
                   sp.editions_remaining, sp.edition_status,
                   COALESCE(NULLIF(sp.psd_file_url, ''), p.psd_file_url, '') AS psd_file_url,
                   COALESCE(NULLIF(sp.prodigi_url, ''), p.prodigi_product_url, '') AS prodigi_url,
                   COALESCE(NULLIF(sp.prodigi_product_id, ''), p.prodigi_product_id, '') AS prodigi_product_id,
                   sp.edition_notes, sp.last_edition_sync_at, sp.edition_updated_at,
                   sp.updated_at, sp.matched_product_id
            FROM shopify_products sp
            LEFT JOIN products p ON p.id = sp.matched_product_id
            ORDER BY sp.title COLLATE NOCASE
            """
        ).fetchall()
    return [hydrate_shopify_edition_product(row) for row in rows]


def list_shopify_products_needing_widget_sync(limit=500):
    products = list_all_shopify_edition_products()
    return [
        product
        for product in products
        if product.get("widget_sync_status") == "Needs Sync"
    ][: min(max(int(limit), 1), 500)]


def find_shopify_edition_product_for_import(shopify_product_id="", handle="", title=""):
    clauses = []
    values = []
    if str(shopify_product_id or "").strip():
        clauses.append("shopify_product_id = ?")
        values.append(str(shopify_product_id).strip())
    if str(handle or "").strip():
        clauses.append("LOWER(TRIM(handle)) = LOWER(TRIM(?))")
        values.append(str(handle).strip())
    if str(title or "").strip():
        clauses.append("LOWER(TRIM(title)) = LOWER(TRIM(?))")
        values.append(str(title).strip())
    if not clauses:
        return None
    with get_connection() as connection:
        row = connection.execute(
            f"""
            SELECT shopify_product_id
            FROM shopify_products
            WHERE {' OR '.join(clauses)}
            ORDER BY
                CASE
                    WHEN shopify_product_id = ? THEN 1
                    WHEN LOWER(TRIM(handle)) = LOWER(TRIM(?)) THEN 2
                    ELSE 3
                END
            LIMIT 1
            """,
            (*values, str(shopify_product_id or "").strip(), str(handle or "").strip()),
        ).fetchone()
    return row["shopify_product_id"] if row else None


def get_shopify_edition_product(shopify_product_id):
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT sp.shopify_product_id, sp.legacy_resource_id, sp.title, sp.handle,
                   sp.status, sp.online_store_url, sp.admin_url, sp.synced_at,
                   sp.edition_limit, sp.next_available_edition, sp.editions_sold,
                   sp.editions_remaining, sp.edition_status,
                   COALESCE(NULLIF(sp.psd_file_url, ''), p.psd_file_url, '') AS psd_file_url,
                   COALESCE(NULLIF(sp.prodigi_url, ''), p.prodigi_product_url, '') AS prodigi_url,
                   COALESCE(NULLIF(sp.prodigi_product_id, ''), p.prodigi_product_id, '') AS prodigi_product_id,
                   sp.edition_notes, sp.last_edition_sync_at, sp.edition_updated_at,
                   sp.updated_at, sp.matched_product_id
            FROM shopify_products sp
            LEFT JOIN products p ON p.id = sp.matched_product_id
            WHERE sp.shopify_product_id = ?
            """,
            (shopify_product_id,),
        ).fetchone()
    return hydrate_shopify_edition_product(row)


def update_shopify_edition_product(
    shopify_product_id,
    *,
    edition_limit,
    next_available_edition,
    editions_sold,
    psd_file_url="",
    prodigi_url="",
    prodigi_product_id="",
    notes="",
    allow_oversold=False,
):
    values = calculate_shopify_edition_values(
        edition_limit,
        next_available_edition,
        editions_sold,
        allow_oversold=allow_oversold,
    )
    timestamp = utc_now()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE shopify_products
            SET edition_limit = ?, next_available_edition = ?, editions_sold = ?,
                editions_remaining = ?, edition_status = ?, psd_file_url = ?,
                prodigi_url = ?, prodigi_product_id = ?, edition_notes = ?,
                edition_updated_at = ?, updated_at = ?
            WHERE shopify_product_id = ?
            """,
            (
                values["edition_limit"],
                values["next_available_edition"],
                values["editions_sold"],
                values["editions_remaining"],
                values["edition_status"],
                str(psd_file_url or "").strip(),
                str(prodigi_url or "").strip(),
                str(prodigi_product_id or "").strip(),
                str(notes or "").strip(),
                timestamp,
                timestamp,
                shopify_product_id,
            ),
        )
        if cursor.rowcount != 1:
            raise ValueError("The Shopify product could not be found in the local cache.")
    return get_shopify_edition_product(shopify_product_id)


def mark_shopify_edition_synced(shopify_product_id):
    timestamp = utc_now()
    with get_connection() as connection:
        connection.execute(
            "UPDATE shopify_products SET last_edition_sync_at = ?, updated_at = ? WHERE shopify_product_id = ?",
            (timestamp, timestamp, shopify_product_id),
        )


def start_shopify_order_sync(store_domain, api_version):
    timestamp = utc_now()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO shopify_order_sync_runs (
                started_at, status, orders_seen, assignments_created,
                pages_synced, api_version, store_domain
            ) VALUES (?, 'Running', 0, 0, 0, ?, ?)
            """,
            (timestamp, api_version, store_domain),
        )
    return cursor.lastrowid


def update_shopify_order_sync_run(
    run_id,
    *,
    status=None,
    orders_seen=None,
    assignments_created=None,
    pages_synced=None,
    error_message=None,
):
    fields = {}
    if status is not None:
        fields["status"] = status
    if orders_seen is not None:
        fields["orders_seen"] = int(orders_seen)
    if assignments_created is not None:
        fields["assignments_created"] = int(assignments_created)
    if pages_synced is not None:
        fields["pages_synced"] = int(pages_synced)
    if error_message is not None:
        fields["error_message"] = str(error_message)[:500]
    if status in {"Complete", "Failed"}:
        fields["completed_at"] = utc_now()
    if not fields:
        return
    assignments = ", ".join(f"{field} = ?" for field in fields)
    with get_connection() as connection:
        connection.execute(
            f"UPDATE shopify_order_sync_runs SET {assignments} WHERE id = ?",
            (*fields.values(), run_id),
        )


def get_latest_shopify_order_sync_run():
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM shopify_order_sync_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def _assignment_state_for_order(order):
    financial_status = str(order.get("financial_status") or "").upper()
    if order.get("cancelled_at"):
        return "Voided"
    if financial_status in {"REFUNDED", "PARTIALLY_REFUNDED"}:
        return "Refunded"
    return None


def normalize_product_match_text(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def find_cached_shopify_product_for_order_line(connection, product_id="", handle="", title=""):
    product_id = str(product_id or "").strip()
    handle = str(handle or "").strip()
    title = str(title or "").strip()
    if product_id:
        product = connection.execute(
            """
            SELECT shopify_product_id, title, handle, edition_limit,
                   next_available_edition, editions_sold
            FROM shopify_products
            WHERE shopify_product_id = ?
            """,
            (product_id,),
        ).fetchone()
        if product:
            return product

    if handle:
        matches = connection.execute(
            """
            SELECT shopify_product_id, title, handle, edition_limit,
                   next_available_edition, editions_sold
            FROM shopify_products
            WHERE LOWER(TRIM(handle)) = LOWER(TRIM(?))
            ORDER BY shopify_product_id
            """,
            (handle,),
        ).fetchall()
        if len(matches) == 1:
            return matches[0]

    normalized_title = normalize_product_match_text(title)
    if not normalized_title:
        return None

    candidates = connection.execute(
        """
        SELECT shopify_product_id, title, handle, edition_limit,
               next_available_edition, editions_sold
        FROM shopify_products
        WHERE COALESCE(TRIM(title), '') != ''
        """
    ).fetchall()
    exact_matches = [
        row for row in candidates
        if normalize_product_match_text(row["title"]) == normalized_title
    ]
    if len(exact_matches) == 1:
        return exact_matches[0]

    scored = [
        (SequenceMatcher(None, normalized_title, normalize_product_match_text(row["title"])).ratio(), row)
        for row in candidates
    ]
    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored:
        return None
    best_score, best_row = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0
    if best_score >= 0.96 and best_score - second_score >= 0.03:
        return best_row
    return None


def process_shopify_order_for_editions(order):
    """Idempotently cache one order and assign editions inside one write lock.

    Future webhook endpoint should call this function.
    """
    timestamp = utc_now()
    shopify_order_id = str(order.get("shopify_order_id") or "").strip()
    if not shopify_order_id:
        raise ValueError("Shopify order ID is required.")

    result = {
        "order_id": None,
        "assignments_created": 0,
        "changed_product_ids": set(),
        "warnings": [],
    }
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            INSERT INTO shopify_orders (
                shopify_order_id, legacy_resource_id, order_name, order_number,
                admin_url, created_at, processed_at, paid_at, financial_status,
                fulfillment_status, customer_name, customer_email, total_price,
                currency, cancelled_at,
                last_synced_at, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(shopify_order_id) DO UPDATE SET
                legacy_resource_id = excluded.legacy_resource_id,
                order_name = excluded.order_name,
                order_number = excluded.order_number,
                admin_url = excluded.admin_url,
                created_at = excluded.created_at,
                processed_at = excluded.processed_at,
                paid_at = excluded.paid_at,
                financial_status = excluded.financial_status,
                fulfillment_status = excluded.fulfillment_status,
                customer_name = excluded.customer_name,
                customer_email = excluded.customer_email,
                total_price = excluded.total_price,
                currency = excluded.currency,
                cancelled_at = excluded.cancelled_at,
                last_synced_at = excluded.last_synced_at
            """,
            (
                shopify_order_id,
                order.get("legacy_resource_id") or "",
                order.get("order_name") or "",
                order.get("order_number") or "",
                order.get("admin_url") or "",
                order.get("created_at") or timestamp,
                order.get("processed_at") or "",
                order.get("paid_at") or "",
                order.get("financial_status") or "",
                order.get("fulfillment_status") or "",
                order.get("customer_name") or "",
                order.get("customer_email") or "",
                order.get("total_price") or "",
                order.get("currency") or "",
                order.get("cancelled_at") or "",
                timestamp,
                order.get("notes") or "",
            ),
        )
        order_row = connection.execute(
            "SELECT id FROM shopify_orders WHERE shopify_order_id = ?",
            (shopify_order_id,),
        ).fetchone()
        order_id = int(order_row["id"])
        result["order_id"] = order_id
        terminal_state = _assignment_state_for_order(order)
        financial_status = str(order.get("financial_status") or "").upper()

        for item in order.get("line_items") or []:
            line_item_id = str(item.get("shopify_line_item_id") or "").strip()
            if not line_item_id:
                continue
            quantity = max(int(item.get("quantity") or 1), 1)
            connection.execute(
                """
                INSERT INTO order_line_items (
                    order_id, shopify_line_item_id, shopify_product_id,
                    product_title, product_handle, variant_title, sku, quantity,
                    assignment_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Needs Edition', ?, ?)
                ON CONFLICT(shopify_line_item_id) DO UPDATE SET
                    order_id = excluded.order_id,
                    shopify_product_id = excluded.shopify_product_id,
                    product_title = excluded.product_title,
                    product_handle = excluded.product_handle,
                    variant_title = excluded.variant_title,
                    sku = excluded.sku,
                    quantity = excluded.quantity,
                    updated_at = excluded.updated_at
                """,
                (
                    order_id,
                    line_item_id,
                    item.get("shopify_product_id") or "",
                    item.get("product_title") or "",
                    item.get("product_handle") or "",
                    item.get("variant_title") or "",
                    item.get("sku") or "",
                    quantity,
                    timestamp,
                    timestamp,
                ),
            )
            line_row = connection.execute(
                "SELECT id, shopify_product_id FROM order_line_items WHERE shopify_line_item_id = ?",
                (line_item_id,),
            ).fetchone()
            local_line_id = int(line_row["id"])

            if terminal_state:
                connection.execute(
                    """
                    UPDATE edition_assignments
                    SET assignment_status = ?, voided_at = COALESCE(voided_at, ?)
                    WHERE line_item_id = ? AND assignment_status NOT IN ('Voided', 'Refunded')
                    """,
                    (terminal_state, timestamp, local_line_id),
                )
                connection.execute(
                    "UPDATE order_line_items SET assignment_status = ?, updated_at = ? WHERE id = ?",
                    (terminal_state, timestamp, local_line_id),
                )
                continue

            existing_count = int(
                connection.execute(
                    "SELECT COUNT(*) AS count FROM edition_assignments WHERE line_item_id = ?",
                    (local_line_id,),
                ).fetchone()["count"]
            )
            if existing_count >= quantity:
                connection.execute(
                    "UPDATE order_line_items SET assignment_status = 'Already Assigned', updated_at = ? WHERE id = ?",
                    (timestamp, local_line_id),
                )
                continue
            if financial_status != "PAID":
                connection.execute(
                    "UPDATE order_line_items SET assignment_status = 'Needs Edition', updated_at = ? WHERE id = ?",
                    (timestamp, local_line_id),
                )
                continue

            product = find_cached_shopify_product_for_order_line(
                connection,
                product_id=line_row["shopify_product_id"],
                handle=item.get("product_handle") or "",
                title=item.get("product_title") or "",
            )
            if not product:
                connection.execute(
                    "UPDATE order_line_items SET assignment_status = 'Product Not Found', updated_at = ? WHERE id = ?",
                    (timestamp, local_line_id),
                )
                continue
            product_id = product["shopify_product_id"]
            connection.execute(
                """
                UPDATE order_line_items
                SET shopify_product_id = ?,
                    product_handle = CASE
                        WHEN COALESCE(TRIM(product_handle), '') = '' THEN ? ELSE product_handle END,
                    updated_at = ?
                WHERE id = ?
                """,
                (product_id, product["handle"] or "", timestamp, local_line_id),
            )

            needed = quantity - existing_count
            if product["edition_limit"] is None:
                connection.execute(
                    "UPDATE order_line_items SET assignment_status = 'Needs Edition Setup', updated_at = ? WHERE id = ?",
                    (timestamp, local_line_id),
                )
                continue
            edition_values = calculate_shopify_edition_values(
                product["edition_limit"],
                product["next_available_edition"],
                product["editions_sold"],
                allow_oversold=True,
            )
            next_number = edition_values["next_available_edition"]
            edition_limit = edition_values["edition_limit"]
            if (
                edition_limit is None
                or next_number is None
                or next_number + needed - 1 > edition_limit
                or edition_values["editions_remaining"] < needed
            ):
                connection.execute(
                    "UPDATE order_line_items SET assignment_status = 'Sold Out', updated_at = ? WHERE id = ?",
                    (timestamp, local_line_id),
                )
                result["warnings"].append(
                    f"{item.get('product_title') or 'Product'} does not have enough edition numbers available."
                )
                continue

            for offset in range(needed):
                edition_number = next_number + offset
                connection.execute(
                    """
                    INSERT INTO edition_assignments (
                        order_id, line_item_id, shopify_order_id,
                        shopify_line_item_id, shopify_product_id, product_title,
                        edition_number, edition_limit, assignment_status,
                        assigned_at, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Assigned', ?, '')
                    """,
                    (
                        order_id,
                        local_line_id,
                        shopify_order_id,
                        line_item_id,
                        product_id,
                        item.get("product_title") or product["title"] or "",
                        edition_number,
                        edition_limit,
                        timestamp,
                    ),
                )
            new_values = calculate_shopify_edition_values(
                edition_limit,
                next_number + needed,
                edition_values["editions_sold"] + needed,
                allow_oversold=True,
            )
            connection.execute(
                """
                UPDATE shopify_products
                SET next_available_edition = ?, editions_sold = ?,
                    editions_remaining = ?, edition_status = ?,
                    edition_updated_at = ?, updated_at = ?
                WHERE shopify_product_id = ?
                """,
                (
                    new_values["next_available_edition"],
                    new_values["editions_sold"],
                    new_values["editions_remaining"],
                    new_values["edition_status"],
                    timestamp,
                    timestamp,
                    product_id,
                ),
            )
            connection.execute(
                "UPDATE order_line_items SET assignment_status = 'Assigned', updated_at = ? WHERE id = ?",
                (timestamp, local_line_id),
            )
            result["assignments_created"] += needed
            result["changed_product_ids"].add(product_id)
    result["changed_product_ids"] = sorted(result["changed_product_ids"])
    return result


def list_shopify_orders(search="", status_filter="All", limit=100):
    clauses = []
    values = []
    if search.strip():
        search_value = f"%{search.strip().lower()}%"
        clauses.append(
            "(LOWER(o.order_name) LIKE ? OR LOWER(o.order_number) LIKE ? OR "
            "LOWER(o.customer_name) LIKE ? OR LOWER(o.customer_email) LIKE ? OR "
            "EXISTS (SELECT 1 FROM order_line_items li "
            "WHERE li.order_id = o.id AND (LOWER(li.product_title) LIKE ? "
            "OR LOWER(li.variant_title) LIKE ? OR LOWER(li.sku) LIKE ?)) OR "
            "EXISTS (SELECT 1 FROM edition_assignments ea "
            "WHERE ea.order_id = o.id AND CAST(ea.edition_number AS TEXT) LIKE ?))"
        )
        values.extend(
            (
                search_value,
                search_value,
                search_value,
                search_value,
                search_value,
                search_value,
                search_value,
                search_value,
            )
        )
    status_clauses = {
        "Needs Edition": "EXISTS (SELECT 1 FROM order_line_items li WHERE li.order_id = o.id AND li.assignment_status = 'Needs Edition')",
        "Assigned": "EXISTS (SELECT 1 FROM edition_assignments ea WHERE ea.order_id = o.id AND ea.assignment_status IN ('Assigned', 'Manual Override'))",
        "Paid": "o.financial_status = 'PAID'",
        "Unfulfilled": "o.fulfillment_status IN ('UNFULFILLED', '')",
        "Error": "EXISTS (SELECT 1 FROM order_line_items li WHERE li.order_id = o.id AND li.assignment_status IN ('Error', 'Product Not Found', 'Needs Edition Setup'))",
        "Sold Out Issue": "EXISTS (SELECT 1 FROM order_line_items li WHERE li.order_id = o.id AND li.assignment_status = 'Sold Out')",
    }
    if status_filter in status_clauses:
        clauses.append(status_clauses[status_filter])
    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_connection() as connection:
        order_rows = connection.execute(
            f"""
            SELECT o.* FROM shopify_orders o
            {where_clause}
            ORDER BY o.created_at DESC, o.id DESC
            LIMIT ?
            """,
            (*values, min(max(int(limit), 1), 500)),
        ).fetchall()
        order_ids = [row["id"] for row in order_rows]
        if not order_ids:
            return []
        placeholders = ", ".join("?" for _ in order_ids)
        line_rows = connection.execute(
            f"""
            SELECT li.*, sp.psd_file_url,
                   sp.prodigi_url, sp.prodigi_product_id
            FROM order_line_items li
            LEFT JOIN shopify_products sp ON sp.shopify_product_id = li.shopify_product_id
            WHERE li.order_id IN ({placeholders})
            ORDER BY li.id
            """,
            order_ids,
        ).fetchall()
        line_ids = [row["id"] for row in line_rows]
        assignment_rows = []
        if line_ids:
            line_placeholders = ", ".join("?" for _ in line_ids)
            assignment_rows = connection.execute(
                f"""
                SELECT * FROM edition_assignments
                WHERE line_item_id IN ({line_placeholders})
                ORDER BY edition_number
                """,
                line_ids,
            ).fetchall()

    assignments_by_line = {}
    for row in assignment_rows:
        assignments_by_line.setdefault(row["line_item_id"], []).append(dict(row))
    lines_by_order = {}
    for row in line_rows:
        line = dict(row)
        line["assignments"] = assignments_by_line.get(line["id"], [])
        lines_by_order.setdefault(line["order_id"], []).append(line)
    orders = []
    for row in order_rows:
        order = dict(row)
        order["line_items"] = lines_by_order.get(order["id"], [])
        orders.append(order)
    return orders


def save_assignment_certificate(assignment_id, pdf_path, certificate_id):
    timestamp = utc_now()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE edition_assignments
            SET certificate_pdf_path = ?, certificate_id = ?, certificate_generated_at = ?
            WHERE id = ?
            """,
            (str(pdf_path or ""), str(certificate_id or ""), timestamp, int(assignment_id)),
        )
        if cursor.rowcount != 1:
            raise ValueError("Certificate assignment could not be found.")


def get_assignment_certificate_details(assignment_id):
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT ea.*, o.order_name, o.order_number, o.customer_name, o.created_at,
                   o.processed_at, li.product_handle, li.variant_title, li.quantity
            FROM edition_assignments ea
            JOIN shopify_orders o ON o.id = ea.order_id
            JOIN order_line_items li ON li.id = ea.line_item_id
            WHERE ea.id = ?
            """,
            (int(assignment_id),),
        ).fetchone()
    return dict(row) if row else None


def list_generated_certificates(limit=100):
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT ea.id, ea.certificate_id, ea.certificate_pdf_path, ea.certificate_generated_at,
                   ea.product_title, ea.edition_number, ea.edition_limit,
                   o.order_name, o.customer_name
            FROM edition_assignments ea
            JOIN shopify_orders o ON o.id = ea.order_id
            WHERE COALESCE(ea.certificate_pdf_path, '') != ''
            ORDER BY ea.certificate_generated_at DESC, ea.id DESC
            LIMIT ?
            """,
            (min(max(int(limit), 1), 500),),
        ).fetchall()
    return [dict(row) for row in rows]


def get_certificate_summary():
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT COUNT(*) AS generated
            FROM edition_assignments
            WHERE COALESCE(certificate_pdf_path, '') != ''
            """
        ).fetchone()
    return {"generated": int(row["generated"] or 0)}


def get_shopify_order_summary():
    today_prefix = datetime.now(timezone.utc).date().isoformat()
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN EXISTS (
                       SELECT 1 FROM order_line_items li
                       WHERE li.order_id = o.id AND li.assignment_status IN ('Needs Edition', 'Product Not Found', 'Needs Edition Setup', 'Sold Out', 'Error')
                   ) THEN 1 ELSE 0 END) AS needs_assignment,
                   MAX(last_synced_at) AS last_synced_at
            FROM shopify_orders o
            """
        ).fetchone()
        assigned_today = connection.execute(
            "SELECT COUNT(*) AS count FROM edition_assignments WHERE assigned_at LIKE ?",
            (f"{today_prefix}%",),
        ).fetchone()["count"]
    return {
        "total": int(row["total"] or 0),
        "needs_assignment": int(row["needs_assignment"] or 0),
        "assigned_today": int(assigned_today or 0),
        "last_synced_at": row["last_synced_at"],
    }


def get_shopify_edition_summary():
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN edition_limit IS NULL THEN 1 ELSE 0 END) AS missing_setup,
                   SUM(CASE WHEN COALESCE(psd_file_url, '') = '' THEN 1 ELSE 0 END) AS missing_psd,
                   SUM(CASE WHEN COALESCE(prodigi_url, '') = '' THEN 1 ELSE 0 END) AS missing_prodigi,
                   SUM(CASE WHEN edition_status = 'Final Editions' THEN 1 ELSE 0 END) AS final_editions,
                   SUM(CASE WHEN edition_status = 'Sold Out' THEN 1 ELSE 0 END) AS sold_out,
                   SUM(CASE WHEN last_edition_sync_at IS NULL
                         OR COALESCE(last_edition_sync_at, '') < COALESCE(edition_updated_at, updated_at, '')
                       THEN 1 ELSE 0 END) AS needs_widget_sync
            FROM shopify_products
            """
        ).fetchone()
    return {key: int(row[key] or 0) for key in row.keys()}


def manual_override_edition_assignment(line_item_id, edition_number, notes="", force=False):
    edition_number = int(edition_number)
    if edition_number < 1:
        raise ValueError("Edition number must be at least 1.")
    timestamp = utc_now()
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        line = connection.execute(
            """
            SELECT li.*, o.shopify_order_id
            FROM order_line_items li
            JOIN shopify_orders o ON o.id = li.order_id
            WHERE li.id = ?
            """,
            (line_item_id,),
        ).fetchone()
        if not line or not line["shopify_product_id"]:
            raise ValueError("This order line is not connected to a Shopify product.")
        product = connection.execute(
            "SELECT * FROM shopify_products WHERE shopify_product_id = ?",
            (line["shopify_product_id"],),
        ).fetchone()
        if not product or product["edition_limit"] is None:
            raise ValueError("Set the product edition limit before assigning an edition.")
        if edition_number > int(product["edition_limit"]):
            raise ValueError("Edition number cannot exceed the edition limit.")
        duplicate = connection.execute(
            """
            SELECT id FROM edition_assignments
            WHERE shopify_product_id = ? AND edition_number = ? AND line_item_id != ?
            """,
            (line["shopify_product_id"], edition_number, line_item_id),
        ).fetchone()
        if duplicate and not force:
            raise ValueError("That edition number is already assigned to this product.")
        if duplicate and force:
            raise ValueError("Duplicate collector edition numbers cannot be forced.")

        existing = connection.execute(
            "SELECT * FROM edition_assignments WHERE line_item_id = ? ORDER BY id LIMIT 1",
            (line_item_id,),
        ).fetchone()
        if existing:
            old_number = int(existing["edition_number"])
            connection.execute(
                """
                UPDATE edition_assignments
                SET edition_number = ?, assignment_status = 'Manual Override', notes = ?
                WHERE id = ?
                """,
                (edition_number, str(notes or "").strip(), existing["id"]),
            )
            assignment_id = existing["id"]
        else:
            old_number = None
            cursor = connection.execute(
                """
                INSERT INTO edition_assignments (
                    order_id, line_item_id, shopify_order_id, shopify_line_item_id,
                    shopify_product_id, product_title, edition_number, edition_limit,
                    assignment_status, assigned_at, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Manual Override', ?, ?)
                """,
                (
                    line["order_id"],
                    line_item_id,
                    line["shopify_order_id"],
                    line["shopify_line_item_id"],
                    line["shopify_product_id"],
                    line["product_title"],
                    edition_number,
                    product["edition_limit"],
                    timestamp,
                    str(notes or "").strip(),
                ),
            )
            assignment_id = cursor.lastrowid
            next_number = max(int(product["next_available_edition"] or 1), edition_number + 1)
            new_values = calculate_shopify_edition_values(
                product["edition_limit"],
                next_number,
                int(product["editions_sold"] or 0) + 1,
                allow_oversold=True,
            )
            connection.execute(
                """
                UPDATE shopify_products
                SET next_available_edition = ?, editions_sold = ?, editions_remaining = ?,
                    edition_status = ?, edition_updated_at = ?, updated_at = ?
                WHERE shopify_product_id = ?
                """,
                (
                    new_values["next_available_edition"],
                    new_values["editions_sold"],
                    new_values["editions_remaining"],
                    new_values["edition_status"],
                    timestamp,
                    timestamp,
                    line["shopify_product_id"],
                ),
            )
        connection.execute(
            "UPDATE order_line_items SET assignment_status = 'Assigned', updated_at = ? WHERE id = ?",
            (timestamp, line_item_id),
        )
        connection.execute(
            """
            INSERT INTO edition_assignment_audit (
                assignment_id, shopify_order_id, shopify_line_item_id,
                shopify_product_id, old_edition_number, new_edition_number,
                action, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'Manual Override', ?, ?)
            """,
            (
                assignment_id,
                line["shopify_order_id"],
                line["shopify_line_item_id"],
                line["shopify_product_id"],
                old_number,
                edition_number,
                str(notes or "").strip(),
                timestamp,
            ),
        )
    return get_shopify_edition_product(line["shopify_product_id"])


def clean_product_payload(payload):
    cleaned = {}
    for field in PRODUCT_FIELDS:
        value = payload.get(field, "")
        cleaned[field] = str(value or "").strip()

    cleaned["product_name"] = cleaned["product_name"] or "Untitled Product"
    if cleaned["status"] not in PRODUCT_STATUSES:
        cleaned["status"] = "Idea"
    if cleaned["sport_category"] not in SPORT_CATEGORIES:
        cleaned["sport_category"] = "Other"
    if cleaned["country_focus"] not in COUNTRY_FOCUS_OPTIONS:
        cleaned["country_focus"] = "Global"
    if not cleaned["final_jpg_url"] and cleaned["jpg_file_url"]:
        cleaned["final_jpg_url"] = cleaned["jpg_file_url"]
    if not cleaned["jpg_file_url"] and cleaned["final_jpg_url"]:
        cleaned["jpg_file_url"] = cleaned["final_jpg_url"]
    return cleaned


def create_product(payload):
    product = clean_product_payload(payload)
    timestamp = utc_now()
    columns = ", ".join(PRODUCT_FIELDS)
    placeholders = ", ".join("?" for _ in PRODUCT_FIELDS)
    values = [product[field] for field in PRODUCT_FIELDS]

    with get_connection() as connection:
        archived_at = timestamp if product["status"] == "Archived" else None
        cursor = connection.execute(
            f"INSERT INTO products ({columns}, archived_at, created_at, updated_at) "
            f"VALUES ({placeholders}, ?, ?, ?)",
            (*values, archived_at, timestamp, timestamp),
        )
        product_id = cursor.lastrowid
        connection.execute(
            """
            INSERT INTO limited_editions (
                product_id, edition_limit, editions_sold, editions_remaining,
                next_edition_number, edition_status, created_at, updated_at
            ) VALUES (?, NULL, 0, NULL, NULL, 'Not Set', ?, ?)
            """,
            (product_id, timestamp, timestamp),
        )
    return product_id


def update_product(product_id, payload):
    product = clean_product_payload(payload)
    assignments = ", ".join(f"{field} = ?" for field in PRODUCT_FIELDS)
    values = [product[field] for field in PRODUCT_FIELDS]

    with get_connection() as connection:
        connection.execute(
            f"UPDATE products SET {assignments}, archived_at = ?, updated_at = ? WHERE id = ?",
            (
                *values,
                utc_now() if product["status"] == "Archived" else None,
                utc_now(),
                product_id,
            ),
        )


def update_product_fields(product_id, **fields):
    allowed_fields = {field: value for field, value in fields.items() if field in PRODUCT_FIELDS}
    if "final_jpg_url" in allowed_fields and "jpg_file_url" not in allowed_fields:
        allowed_fields["jpg_file_url"] = allowed_fields["final_jpg_url"]
    if "jpg_file_url" in allowed_fields and "final_jpg_url" not in allowed_fields:
        allowed_fields["final_jpg_url"] = allowed_fields["jpg_file_url"]
    if not allowed_fields:
        return

    assignments = ", ".join(f"{field} = ?" for field in allowed_fields)
    values = [str(value or "").strip() for value in allowed_fields.values()]
    timestamp = utc_now()
    with get_connection() as connection:
        connection.execute(
            f"UPDATE products SET {assignments}, updated_at = ? WHERE id = ?",
            (*values, timestamp, product_id),
        )
        if "status" in allowed_fields:
            archived_at = timestamp if allowed_fields["status"] == "Archived" else None
            connection.execute(
                "UPDATE products SET archived_at = ? WHERE id = ?",
                (archived_at, product_id),
            )


def archive_product(product_id):
    update_product_fields(product_id, status="Archived")


def restore_product(product_id):
    update_product_fields(product_id, status="Idea")


def get_product(product_id):
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT p.*, le.edition_limit, le.editions_sold, le.editions_remaining,
                   le.next_edition_number, le.edition_status, le.last_synced_at
            FROM products p
            LEFT JOIN limited_editions le ON le.product_id = p.id
            WHERE p.id = ?
            """,
            (product_id,),
        ).fetchone()
    if not row:
        return None
    product = dict(row)
    records = get_asset_record_map((product["id"],)).get(product["id"], {})
    shopify_match = get_shopify_match_map((product["id"],)).get(product["id"])
    return enrich_product(product, records, shopify_match)


def list_products(
    search="",
    sport_category="All",
    country_focus="All",
    status="All",
    edition_status="All",
    include_archived=False,
):
    clauses = []
    values = []
    if search.strip():
        clauses.append("(LOWER(p.product_name) LIKE ? OR LOWER(p.handle) LIKE ?)")
        search_value = f"%{search.strip().lower()}%"
        values.extend((search_value, search_value))
    if sport_category != "All":
        clauses.append("p.sport_category = ?")
        values.append(sport_category)
    if country_focus != "All":
        clauses.append("p.country_focus = ?")
        values.append(country_focus)
    if status != "All":
        clauses.append("p.status = ?")
        values.append(status)
    elif not include_archived:
        clauses.append("p.status != 'Archived'")
    if edition_status != "All":
        clauses.append("COALESCE(le.edition_status, 'Not Set') = ?")
        values.append(edition_status)

    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT p.*, le.edition_limit, le.editions_sold, le.editions_remaining,
                   le.next_edition_number, le.edition_status, le.last_synced_at
            FROM products p
            LEFT JOIN limited_editions le ON le.product_id = p.id
            {where_clause}
            ORDER BY p.updated_at DESC, p.product_name COLLATE NOCASE
            """,
            values,
        ).fetchall()
    products = [dict(row) for row in rows]
    records = get_asset_record_map(product["id"] for product in products)
    shopify_matches = get_shopify_match_map(product["id"] for product in products)
    return [
        enrich_product(
            product,
            records.get(product["id"], {}),
            shopify_matches.get(product["id"]),
        )
        for product in products
    ]


def get_asset_record_map(product_ids):
    product_ids = tuple(dict.fromkeys(int(product_id) for product_id in product_ids))
    if not product_ids:
        return {}

    placeholders = ", ".join("?" for _ in product_ids)
    with get_connection() as connection:
        rows = connection.execute(
            f"SELECT product_id, asset_key, manual_status, updated_at "
            f"FROM product_assets WHERE product_id IN ({placeholders})",
            product_ids,
        ).fetchall()

    records = {product_id: {} for product_id in product_ids}
    for row in rows:
        records[row["product_id"]][row["asset_key"]] = dict(row)
    return records


def effective_asset_status(product, asset, record=None):
    if not product.get(asset["url_field"]):
        return "Missing"
    manual_status = (record or {}).get("manual_status")
    if manual_status in {"Needs Review", "Approved"}:
        return manual_status
    return "Connected"


def update_product_assets(product_id, asset_updates):
    timestamp = utc_now()
    with get_connection() as connection:
        for asset_key, update in asset_updates.items():
            asset = ASSET_BY_KEY.get(asset_key)
            if not asset:
                continue

            url = str(update.get("url") or "").strip()
            manual_status = update.get("manual_status")
            if manual_status not in {"Needs Review", "Approved"}:
                manual_status = None

            connection.execute(
                f"UPDATE products SET {asset['url_field']} = ?, updated_at = ? WHERE id = ?",
                (url, timestamp, product_id),
            )
            if asset["url_field"] == "final_jpg_url":
                connection.execute(
                    "UPDATE products SET jpg_file_url = ? WHERE id = ?",
                    (url, product_id),
                )
            connection.execute(
                """
                INSERT INTO product_assets (product_id, asset_key, manual_status, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(product_id, asset_key) DO UPDATE SET
                    manual_status = excluded.manual_status,
                    updated_at = excluded.updated_at
                """,
                (product_id, asset_key, manual_status, timestamp),
            )


def get_required_readiness_items(product):
    return (
        ("Product name added", bool(product.get("product_name"))),
        ("Handle added", bool(product.get("handle"))),
        ("Sport category selected", bool(product.get("sport_category"))),
        ("Country focus selected", bool(product.get("country_focus"))),
        ("PSD file URL added", bool(product.get("psd_file_url"))),
        ("Final JPG URL added", bool(product.get("final_jpg_url"))),
        ("WebP folder URL added", bool(product.get("webp_folder_url"))),
        ("Mockup folder URL added", bool(product.get("mockup_folder_url"))),
        ("Edition limit set", product.get("edition_limit") is not None),
    )


def get_optional_readiness_items(product):
    return (
        ("Size guide URL added", bool(product.get("size_guide_url"))),
        ("Lifestyle folder URL added", bool(product.get("lifestyle_folder_url"))),
        ("Prompt pack URL added", bool(product.get("prompt_pack_url"))),
        ("Product upload ZIP URL added", bool(product.get("product_upload_zip_url"))),
        ("Certificate folder URL added", bool(product.get("certificate_folder_url"))),
        ("Ads/social folder URL added", bool(product.get("ads_social_folder_url"))),
        ("Prodigi ID added", bool(product.get("prodigi_product_id"))),
        ("Shopify admin URL added", bool(product.get("shopify_admin_url"))),
        ("Live product URL added", bool(product.get("live_product_url"))),
    )


def get_readiness_items(product):
    return (*get_required_readiness_items(product), *get_optional_readiness_items(product))


def get_missing_items(product):
    return [label for label, complete in get_required_readiness_items(product) if not complete]


def get_readiness_status(product):
    if product.get("status") == "Archived":
        return "Archived"
    if product.get("status") == "Live":
        return "Live"
    if any(not complete for _, complete in get_required_readiness_items(product)[:4]):
        return "Not Ready"
    if any(not product.get(field) for field, _ in CORE_FILE_FIELDS):
        return "Needs Files"
    if product.get("edition_limit") is None:
        return "Needs Edition Setup"
    return "Ready for Upload"


def get_file_readiness_status(product):
    return get_overall_asset_readiness(product)


def get_overall_asset_readiness(product):
    statuses = product.get("asset_statuses") or {
        asset["key"]: effective_asset_status(product, asset)
        for asset in ASSET_DEFINITIONS
    }
    core_statuses = [statuses[key] for key in CORE_ASSET_KEYS]
    all_statuses = list(statuses.values())

    if product.get("status") == "Live" and "Missing" in core_statuses:
        return "Live Product Missing Files"
    if "Needs Review" in all_statuses:
        return "Needs Review"
    if all(status == "Approved" for status in all_statuses):
        return "Asset Pack Approved"
    if "Missing" in core_statuses:
        return "Core Assets Missing"
    return "Core Assets Connected"


def get_shopify_link_status(product):
    if product.get("live_product_url"):
        return "Live Link Added"
    if product.get("shopify_admin_url"):
        return "Admin Link Added"
    return "Missing"


def enrich_product(product, asset_records=None, shopify_match=None):
    if not product.get("final_jpg_url") and product.get("jpg_file_url"):
        product["final_jpg_url"] = product["jpg_file_url"]
    if not product.get("jpg_file_url") and product.get("final_jpg_url"):
        product["jpg_file_url"] = product["final_jpg_url"]

    asset_records = asset_records or {}
    product["asset_statuses"] = {}
    product["asset_manual_statuses"] = {}
    product["asset_updated_at"] = {}
    for asset in ASSET_DEFINITIONS:
        record = asset_records.get(asset["key"], {})
        status = effective_asset_status(product, asset, record)
        product["asset_statuses"][asset["key"]] = status
        product["asset_manual_statuses"][asset["key"]] = record.get("manual_status") or "Automatic"
        product["asset_updated_at"][asset["key"]] = record.get("updated_at") or product.get("updated_at")
        product[f"{asset['key']}_status"] = status
        product[f"{asset['key']}_updated_at"] = product["asset_updated_at"][asset["key"]]

    product["overall_asset_readiness"] = get_overall_asset_readiness(product)
    product["readiness_status"] = get_readiness_status(product)
    product["file_readiness_status"] = get_file_readiness_status(product)
    product["prodigi_status"] = "Connected" if product.get("prodigi_product_id") else "Missing"
    product["shopify_link_status"] = get_shopify_link_status(product)
    product["shopify_match"] = shopify_match
    product["shopify_sync_status"] = (
        f"Shopify {(shopify_match.get('status') or 'Synced').title()}"
        if shopify_match
        else ("ID Not Synced" if product.get("shopify_product_id") else "Not Matched")
    )
    product["shopify_last_synced_at"] = shopify_match.get("synced_at") if shopify_match else None
    product["shopify_remote_updated_at"] = shopify_match.get("remote_updated_at") if shopify_match else None
    product["shopify_variant_count"] = shopify_match.get("variant_count", 0) if shopify_match else 0
    product["shopify_image_count"] = shopify_match.get("image_count", 0) if shopify_match else 0
    product["missing_items"] = get_missing_items(product)
    return product


def calculate_edition_values(edition_limit, editions_sold):
    if edition_limit in (None, ""):
        return {
            "edition_limit": None,
            "editions_sold": max(int(editions_sold or 0), 0),
            "editions_remaining": None,
            "next_edition_number": None,
            "edition_status": "Not Set",
        }

    limit_value = max(int(edition_limit), 0)
    sold_value = min(max(int(editions_sold or 0), 0), limit_value)
    remaining = max(limit_value - sold_value, 0)
    next_number = sold_value + 1 if remaining > 0 else None

    if remaining == 0:
        status = "Sold Out"
    elif remaining <= 3:
        status = "Final Editions"
    elif remaining <= 6:
        status = "Low"
    elif remaining <= 12:
        status = "Count"
    else:
        status = "Available"

    return {
        "edition_limit": limit_value,
        "editions_sold": sold_value,
        "editions_remaining": remaining,
        "next_edition_number": next_number,
        "edition_status": status,
    }


def update_limited_edition(product_id, edition_limit, editions_sold):
    values = calculate_edition_values(edition_limit, editions_sold)
    timestamp = utc_now()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO limited_editions (
                product_id, edition_limit, editions_sold, editions_remaining,
                next_edition_number, edition_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(product_id) DO UPDATE SET
                edition_limit = excluded.edition_limit,
                editions_sold = excluded.editions_sold,
                editions_remaining = excluded.editions_remaining,
                next_edition_number = excluded.next_edition_number,
                edition_status = excluded.edition_status,
                updated_at = excluded.updated_at
            """,
            (
                product_id,
                values["edition_limit"],
                values["editions_sold"],
                values["editions_remaining"],
                values["next_edition_number"],
                values["edition_status"],
                timestamp,
                timestamp,
            ),
        )
    return values


def list_limited_editions(status="All"):
    clauses = ["p.status != 'Archived'"]
    values = []
    if status != "All":
        clauses.append("COALESCE(le.edition_status, 'Not Set') = ?")
        values.append(status)
    clause = f"WHERE {' AND '.join(clauses)}"

    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT p.id AS product_id, p.product_name, p.sport_category, p.status AS product_status,
                   le.edition_limit, COALESCE(le.editions_sold, 0) AS editions_sold,
                   le.editions_remaining, le.next_edition_number,
                   COALESCE(le.edition_status, 'Not Set') AS edition_status,
                   le.last_synced_at, le.updated_at
            FROM products p
            LEFT JOIN limited_editions le ON le.product_id = p.id
            {clause}
            ORDER BY
                CASE COALESCE(le.edition_status, 'Not Set')
                    WHEN 'Sold Out' THEN 1
                    WHEN 'Final Editions' THEN 2
                    WHEN 'Selling Quickly' THEN 3
                    WHEN 'Available' THEN 4
                    ELSE 5
                END,
                p.product_name COLLATE NOCASE
            """,
            values,
        ).fetchall()
    return [dict(row) for row in rows]


def get_dashboard_data():
    products = list_products(include_archived=False)
    shopify_editions = get_shopify_edition_summary()
    orders = get_shopify_order_summary()
    certificates = get_certificate_summary()
    metrics = {
        "total_products": len(products),
        "live_products": sum(product["status"] == "Live" for product in products),
        "needs_review": sum(product["status"] == "Ready for Review" for product in products),
        "missing_psd": sum(not product.get("psd_file_url") for product in products),
        "missing_prodigi": sum(not product.get("prodigi_product_id") for product in products),
        "missing_edition_limits": sum(product.get("edition_limit") is None for product in products),
        "ready_for_upload": sum(product["readiness_status"] == "Ready for Upload" for product in products),
        "final_editions": sum(product.get("edition_status") == "Final Editions" for product in products),
        "sold_out": sum(product.get("edition_status") == "Sold Out" for product in products),
        "missing_core_assets": sum(
            product["overall_asset_readiness"] in {"Core Assets Missing", "Live Product Missing Files"}
            for product in products
        ),
        "assets_needing_review": sum(
            "Needs Review" in product["asset_statuses"].values() for product in products
        ),
        "approved_asset_packs": sum(
            product["overall_asset_readiness"] == "Asset Pack Approved" for product in products
        ),
        "live_missing_files": sum(
            product["overall_asset_readiness"] == "Live Product Missing Files" for product in products
        ),
        "missing_drive_root": sum(not product.get("google_drive_root_folder_url") for product in products),
        "shopify_matched": sum(bool(product.get("shopify_match")) for product in products),
        "shopify_needs_match": sum(not product.get("shopify_match") for product in products),
        "shopify_products_synced": shopify_editions["total"],
        "orders_synced": orders["total"],
        "orders_needing_assignment": orders["needs_assignment"],
        "orders_assigned_today": orders["assigned_today"],
        "certificate_pdfs_generated": certificates["generated"],
        "shopify_missing_edition_setup": shopify_editions["missing_setup"],
        "shopify_missing_psd": shopify_editions["missing_psd"],
        "shopify_missing_prodigi": shopify_editions["missing_prodigi"],
        "shopify_needs_widget_sync": shopify_editions["needs_widget_sync"],
        "shopify_final_editions": shopify_editions["final_editions"],
        "shopify_sold_out": shopify_editions["sold_out"],
    }
    focus = {
        "missing_psd": [product for product in products if not product.get("psd_file_url")],
        "missing_mockup": [product for product in products if not product.get("mockup_folder_url")],
        "missing_prodigi": [product for product in products if not product.get("prodigi_product_id")],
        "missing_edition_limit": [product for product in products if product.get("edition_limit") is None],
        "ready_for_review": [product for product in products if product.get("status") == "Ready for Review"],
        "ready_for_upload": [product for product in products if product["readiness_status"] == "Ready for Upload"],
        "final_editions": [product for product in products if product.get("edition_status") == "Final Editions"],
        "missing_final_jpg": [product for product in products if not product.get("final_jpg_url")],
        "missing_webp": [product for product in products if not product.get("webp_folder_url")],
        "assets_needing_review": [
            product for product in products if "Needs Review" in product["asset_statuses"].values()
        ],
        "live_missing_files": [
            product for product in products if product["overall_asset_readiness"] == "Live Product Missing Files"
        ],
        "shopify_needs_match": [product for product in products if not product.get("shopify_match")],
    }
    return metrics, focus


def list_file_hub_products(file_filter="All products"):
    products = list_products(include_archived=False)
    filter_assets = {
        "Missing PSD": "psd",
        "Missing JPG": "final_jpg",
        "Missing WebP": "webp",
        "Missing Mockups": "mockups",
        "Missing Size Guide": "size_guide",
        "Missing Lifestyle": "lifestyle",
        "Missing Prompt Pack": "prompt_pack",
        "Missing ZIP": "product_upload_zip",
        "Missing Certificate Folder": "certificates",
        "Missing Ads/Social Folder": "ads_social",
    }
    if file_filter in filter_assets:
        asset_key = filter_assets[file_filter]
        return [product for product in products if product["asset_statuses"][asset_key] == "Missing"]
    if file_filter == "Needs Review":
        return [product for product in products if "Needs Review" in product["asset_statuses"].values()]
    if file_filter == "Approved":
        return [product for product in products if product["overall_asset_readiness"] == "Asset Pack Approved"]
    if file_filter in {"All Connected", "All connected"}:
        return [
            product
            for product in products
            if all(status in {"Connected", "Approved"} for status in product["asset_statuses"].values())
        ]
    return products


def products_for_export():
    return list_products(include_archived=True)
