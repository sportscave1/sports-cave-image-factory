import argparse
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
DROP_CONSTRAINT_PATTERN = re.compile(
    r"ALTER\s+TABLE\s+(?P<table>[a-z_][a-z0-9_]*)\s+"
    r"DROP\s+CONSTRAINT\s+IF\s+EXISTS\s+(?P<constraint>[a-z_][a-z0-9_]*)\s*;",
    re.IGNORECASE,
)
ALLOWED_CONSTRAINT_REPLACEMENTS = frozenset(
    {
        (
            "daily_execution_task_timers",
            "daily_execution_task_timers_outcome_check",
        ),
    }
)


def get_database_url():
    for key in DATABASE_URL_ENV_KEYS:
        value = os.getenv(key, "").strip()
        if value:
            return value, key
    return "", ""


def safe_migration_sql(sql):
    def remove_reviewed_constraint_drop(match):
        key = (match.group("table").casefold(), match.group("constraint").casefold())
        return "" if key in ALLOWED_CONSTRAINT_REPLACEMENTS else match.group(0)

    reviewed_sql = DROP_CONSTRAINT_PATTERN.sub(remove_reviewed_constraint_drop, sql)
    return not UNSAFE_SQL_PATTERN.search(reviewed_sql)


def migration_files(only=None):
    paths = sorted(path for path in MIGRATIONS_DIR.glob("*.sql") if path.is_file())
    if not only:
        return paths
    clean_name = Path(str(only)).name
    if clean_name != str(only) or not clean_name.endswith(".sql"):
        raise ValueError("Choose a migration filename from the migrations directory.")
    selected = [path for path in paths if path.name == clean_name]
    if not selected:
        raise ValueError(f"Migration not found: {clean_name}")
    return selected


def run_migrations(*, only=None, check=False):
    selected = migration_files(only)
    unsafe = [path.name for path in selected if not safe_migration_sql(path.read_text(encoding="utf-8"))]
    if unsafe and only:
        raise SystemExit(f"Migration failed the safety check: {unsafe[0]}")
    if check:
        for path in selected:
            state = "READY" if path.name not in unsafe else "SKIPPED unsafe"
            print(f"{state} {path.name}")
        return

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
            for path in selected:
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
    parser = argparse.ArgumentParser(description="Apply reviewed Sports Cave database migrations.")
    parser.add_argument("--only", help="Apply one migration filename from the migrations directory.")
    parser.add_argument("--check", action="store_true", help="Validate selection and safety without connecting.")
    args = parser.parse_args()
    run_migrations(only=args.only, check=args.check)
