from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import json
import os
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
    "Selling Quickly",
    "Final Editions",
    "Sold Out",
    "Archived",
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

            CREATE INDEX IF NOT EXISTS idx_products_name ON products(product_name);
            CREATE INDEX IF NOT EXISTS idx_products_status ON products(status);
            CREATE INDEX IF NOT EXISTS idx_products_sport ON products(sport_category);
            CREATE INDEX IF NOT EXISTS idx_editions_status ON limited_editions(edition_status);
            CREATE INDEX IF NOT EXISTS idx_product_assets_status ON product_assets(manual_status);
            CREATE INDEX IF NOT EXISTS idx_shopify_products_handle ON shopify_products(handle);
            CREATE INDEX IF NOT EXISTS idx_shopify_products_status ON shopify_products(status);
            CREATE INDEX IF NOT EXISTS idx_shopify_products_match ON shopify_products(matched_product_id);
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
                    remote_updated_at, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    synced_at = excluded.synced_at
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
    elif remaining <= 5:
        status = "Final Editions"
    elif remaining <= 15:
        status = "Selling Quickly"
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
