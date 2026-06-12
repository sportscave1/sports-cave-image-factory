from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import os
import sqlite3


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "sports_cave_os.db"
DB_PATH = Path(os.getenv("SPORTS_CAVE_DB_PATH", str(DEFAULT_DB_PATH)))

PRODUCT_STATUSES = (
    "Draft",
    "Mockups Ready",
    "Upload In Progress",
    "Live",
    "Needs Review",
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
    "psd_file_url",
    "jpg_file_url",
    "webp_folder_url",
    "mockup_folder_url",
    "certificate_folder_url",
    "notes",
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
                status TEXT NOT NULL DEFAULT 'Draft',
                shopify_admin_url TEXT,
                live_product_url TEXT,
                prodigi_product_id TEXT,
                psd_file_url TEXT,
                jpg_file_url TEXT,
                webp_folder_url TEXT,
                mockup_folder_url TEXT,
                certificate_folder_url TEXT,
                notes TEXT,
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


def clean_product_payload(payload):
    cleaned = {}
    for field in PRODUCT_FIELDS:
        value = payload.get(field, "")
        cleaned[field] = str(value or "").strip()

    cleaned["product_name"] = cleaned["product_name"] or "Untitled Product"
    if cleaned["status"] not in PRODUCT_STATUSES:
        cleaned["status"] = "Draft"
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
        cursor = connection.execute(
            f"INSERT INTO products ({columns}, created_at, updated_at) VALUES ({placeholders}, ?, ?)",
            (*values, timestamp, timestamp),
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
            f"UPDATE products SET {assignments}, updated_at = ? WHERE id = ?",
            (*values, utc_now(), product_id),
        )


def update_product_fields(product_id, **fields):
    allowed_fields = {field: value for field, value in fields.items() if field in PRODUCT_FIELDS}
    if not allowed_fields:
        return

    assignments = ", ".join(f"{field} = ?" for field in allowed_fields)
    values = [str(value or "").strip() for value in allowed_fields.values()]
    with get_connection() as connection:
        connection.execute(
            f"UPDATE products SET {assignments}, updated_at = ? WHERE id = ?",
            (*values, utc_now(), product_id),
        )


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
    return dict(row) if row else None


def list_products(search="", sport_category="All", status="All"):
    clauses = []
    values = []
    if search.strip():
        clauses.append("(LOWER(p.product_name) LIKE ? OR LOWER(p.handle) LIKE ?)")
        search_value = f"%{search.strip().lower()}%"
        values.extend((search_value, search_value))
    if sport_category != "All":
        clauses.append("p.sport_category = ?")
        values.append(sport_category)
    if status != "All":
        clauses.append("p.status = ?")
        values.append(status)

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
    return [dict(row) for row in rows]


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
    clause = ""
    values = []
    if status != "All":
        clause = "WHERE COALESCE(le.edition_status, 'Not Set') = ?"
        values.append(status)

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
    products = list_products()
    metrics = {
        "total_products": len(products),
        "live_products": sum(product["status"] == "Live" for product in products),
        "needs_review": sum(product["status"] == "Needs Review" for product in products),
        "missing_edition_limits": sum(product.get("edition_limit") is None for product in products),
        "final_editions": sum(product.get("edition_status") == "Final Editions" for product in products),
        "sold_out": sum(product.get("edition_status") == "Sold Out" for product in products),
    }
    focus = {
        "missing_psd": [product for product in products if not product.get("psd_file_url")],
        "missing_prodigi": [product for product in products if not product.get("prodigi_product_id")],
        "missing_edition_limit": [product for product in products if product.get("edition_limit") is None],
        "not_live": [product for product in products if product.get("status") != "Live"],
    }
    return metrics, focus
