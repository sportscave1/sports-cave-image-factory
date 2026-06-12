from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
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
    "webp_folder_url",
    "mockup_folder_url",
    "certificate_folder_url",
    "notes",
)

CORE_FILE_FIELDS = (
    ("psd_file_url", "PSD link"),
    ("jpg_file_url", "JPG link"),
    ("webp_folder_url", "WebP folder"),
    ("mockup_folder_url", "Mockup folder"),
)

FILE_HUB_FIELDS = (
    *CORE_FILE_FIELDS,
    ("certificate_folder_url", "Certificate folder"),
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
                webp_folder_url TEXT,
                mockup_folder_url TEXT,
                certificate_folder_url TEXT,
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

            CREATE INDEX IF NOT EXISTS idx_products_name ON products(product_name);
            CREATE INDEX IF NOT EXISTS idx_products_status ON products(status);
            CREATE INDEX IF NOT EXISTS idx_products_sport ON products(sport_category);
            CREATE INDEX IF NOT EXISTS idx_editions_status ON limited_editions(edition_status);
            """
        )
        ensure_column(connection, "products", "prodigi_product_url", "TEXT")
        ensure_column(connection, "products", "prodigi_notes", "TEXT")
        ensure_column(connection, "products", "archived_at", "TEXT")
        connection.execute("UPDATE products SET status = 'Idea' WHERE status = 'Draft'")
        connection.execute("UPDATE products SET status = 'Ready for Review' WHERE status = 'Needs Review'")


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
    return enrich_product(dict(row)) if row else None


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
    return [enrich_product(dict(row)) for row in rows]


def get_readiness_items(product):
    return (
        ("Product name added", bool(product.get("product_name"))),
        ("Handle added", bool(product.get("handle"))),
        ("Sport category selected", bool(product.get("sport_category"))),
        ("Country focus selected", bool(product.get("country_focus"))),
        ("PSD link added", bool(product.get("psd_file_url"))),
        ("JPG link added", bool(product.get("jpg_file_url"))),
        ("WebP folder added", bool(product.get("webp_folder_url"))),
        ("Mockup folder added", bool(product.get("mockup_folder_url"))),
        ("Prodigi ID added", bool(product.get("prodigi_product_id"))),
        ("Edition limit set", product.get("edition_limit") is not None),
        ("Shopify admin URL added", bool(product.get("shopify_admin_url"))),
        ("Live product URL added", bool(product.get("live_product_url"))),
        ("Notes added", bool(product.get("notes"))),
    )


def get_missing_items(product):
    return [label for label, complete in get_readiness_items(product) if not complete]


def get_readiness_status(product):
    if product.get("status") == "Archived":
        return "Archived"
    if product.get("status") == "Live":
        return "Live"
    if not product.get("product_name") or not product.get("handle"):
        return "Not Ready"
    if any(not product.get(field) for field, _ in CORE_FILE_FIELDS):
        return "Needs Files"
    if not product.get("prodigi_product_id"):
        return "Needs Prodigi"
    if product.get("edition_limit") is None:
        return "Needs Edition Setup"
    return "Ready for Upload"


def get_file_readiness_status(product):
    missing_count = sum(not product.get(field) for field, _ in FILE_HUB_FIELDS)
    if missing_count == 0:
        return "All Files Connected"
    if all(product.get(field) for field, _ in CORE_FILE_FIELDS):
        return "Core Files Ready"
    return "Missing Files"


def get_shopify_link_status(product):
    if product.get("live_product_url"):
        return "Live Link Added"
    if product.get("shopify_admin_url"):
        return "Admin Link Added"
    return "Missing"


def enrich_product(product):
    product["readiness_status"] = get_readiness_status(product)
    product["file_readiness_status"] = get_file_readiness_status(product)
    product["prodigi_status"] = "Connected" if product.get("prodigi_product_id") else "Missing"
    product["shopify_link_status"] = get_shopify_link_status(product)
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
    }
    focus = {
        "missing_psd": [product for product in products if not product.get("psd_file_url")],
        "missing_mockup": [product for product in products if not product.get("mockup_folder_url")],
        "missing_prodigi": [product for product in products if not product.get("prodigi_product_id")],
        "missing_edition_limit": [product for product in products if product.get("edition_limit") is None],
        "ready_for_review": [product for product in products if product.get("status") == "Ready for Review"],
        "ready_for_upload": [product for product in products if product["readiness_status"] == "Ready for Upload"],
        "final_editions": [product for product in products if product.get("edition_status") == "Final Editions"],
    }
    return metrics, focus


def list_file_hub_products(file_filter="All products"):
    products = list_products(include_archived=False)
    filter_fields = {
        "Missing PSD": "psd_file_url",
        "Missing JPG": "jpg_file_url",
        "Missing WebP folder": "webp_folder_url",
        "Missing mockup folder": "mockup_folder_url",
        "Missing certificate folder": "certificate_folder_url",
    }
    if file_filter in filter_fields:
        field = filter_fields[file_filter]
        return [product for product in products if not product.get(field)]
    if file_filter == "All connected":
        return [
            product
            for product in products
            if all(product.get(field) for field, _ in FILE_HUB_FIELDS)
        ]
    return products


def products_for_export():
    return list_products(include_archived=True)
