import os
from pathlib import Path
import re

import psycopg


BASE_DIR = Path(__file__).resolve().parent
MIGRATIONS_DIR = BASE_DIR / "migrations"
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
UNSAFE_SQL_PATTERN = re.compile(r"\b(DROP|DELETE|TRUNCATE|UPDATE|INSERT)\b", re.IGNORECASE)


def get_database_url():
    for key in DATABASE_URL_ENV_KEYS:
        value = os.getenv(key, "").strip()
        if value:
            return value, key
    return "", ""


def safe_migration_sql(sql):
    return not UNSAFE_SQL_PATTERN.search(sql)


def migration_files():
    return sorted(path for path in MIGRATIONS_DIR.glob("*.sql") if path.is_file())


def run_migrations():
    database_url, source = get_database_url()
    if not database_url:
        raise SystemExit("DATABASE_URL missing. Set DATABASE_URL before running migrations.")

    applied = []
    skipped = []
    with psycopg.connect(database_url, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ DEFAULT now()
                )
                """
            )
            for path in migration_files():
                sql = path.read_text(encoding="utf-8")
                if not safe_migration_sql(sql):
                    skipped.append((path.name, "contains data-moving or destructive SQL"))
                    continue
                cur.execute("SELECT 1 FROM schema_migrations WHERE filename=%s", (path.name,))
                if cur.fetchone():
                    skipped.append((path.name, "already applied"))
                    continue
                cur.execute(sql)
                cur.execute(
                    "INSERT INTO schema_migrations(filename) VALUES (%s)",
                    (path.name,),
                )
                applied.append(path.name)
        conn.commit()

    print(f"Database URL source: {source}")
    for filename in applied:
        print(f"APPLIED {filename}")
    for filename, reason in skipped:
        print(f"SKIPPED {filename}: {reason}")


if __name__ == "__main__":
    run_migrations()
