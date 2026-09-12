import argparse
import hashlib
import os
from pathlib import Path
import re

import psycopg
import manual_certificate_schema


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
REFERENTIAL_DELETE_PATTERN = re.compile(
    r"\bON\s+DELETE\s+(?:CASCADE|SET\s+NULL|SET\s+DEFAULT|RESTRICT|NO\s+ACTION)\b",
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
SHOPIFY_MARKETPLACE_MIGRATION = "20260818_shopify_marketplace_order_reconciliation.sql"
LEGACY_ALLOCATOR_REPAIR_MIGRATION = "20260828_fix_sparse_legacy_allocator.sql"
MANUAL_EXPIRED_EDITION_MIGRATION = "20260828_manual_expired_order_line_editions.sql"
MANUAL_EXPIRED_EDITION_IDENTITY_MIGRATION = (
    "20260829_fix_manual_expired_edition_identity.sql"
)
REVIEWED_MIGRATION_SHA256 = {
    '20260912231446_manual_certificate_identity.sql': 'b90b3d649e86ba5cccba05231d1e8c0ae8f80965b470d8f12ee390847ad7591d',
    "20260912224424_manual_certificate_controls.sql": "59b72a16e4e41d78ed261374cddeee449e75a5f34300836c8ebf1f44be7a8c24",
    "20260912045939_independent_edition_cursor.sql": "145bcd1ee8d87c1bb6ce9aa56deb1bb65ed7dd20ffd22dab69d216e3c8172fbe",
    LEGACY_ALLOCATOR_REPAIR_MIGRATION: (
        "488120bb6f36c3b7dcd59a8a933db74c3fb2266e5c5bc06f1d283392e35be4e9"
    ),
    MANUAL_EXPIRED_EDITION_MIGRATION: (
        "3d95c350db7cca6fddcfd533fc0545efe99e69252056835ac7ff843e9229ff4b"
    ),
    MANUAL_EXPIRED_EDITION_IDENTITY_MIGRATION: (
        "4bb67951fac76d71ec4023360c24f21c9db843225458b00d7513f9d2ba966209"
    ),
}
# Explicit deployment manifest: do not replay historic allocator/repair migrations.
# Every entry additionally requires its reviewed SHA, even for additive SQL.
DEPLOYMENT_MIGRATIONS = (
    "20260912224424_manual_certificate_controls.sql",
    "20260912231446_manual_certificate_identity.sql",
)
MARKETPLACE_SCHEMA_MIGRATIONS = (SHOPIFY_MARKETPLACE_MIGRATION,)
MARKETPLACE_SCHEMA_COLUMNS = {
    ("shopify_orders", "source_name"): ("text", "NO", "''"),
    ("shopify_orders", "ingestion_status"): ("text", "NO", "pending"),
    ("shopify_orders", "ingestion_method"): ("text", "NO", "''"),
    ("shopify_orders", "ingestion_result"): ("text", "NO", "''"),
    ("shopify_orders", "ingestion_reason"): ("text", "NO", "''"),
    ("shopify_orders", "ingestion_duration_ms"): ("integer", "NO", "0"),
    ("shopify_orders", "last_ingested_at"): ("timestamp with time zone", "YES", ""),
    ("shopify_order_lines", "shopify_variant_id"): ("text", "YES", ""),
    ("shopify_order_lines", "mapping_method"): ("text", "NO", "''"),
    ("webhook_events", "source_name"): ("text", "NO", "''"),
    ("webhook_events", "import_result"): ("text", "NO", "''"),
    ("webhook_events", "rejection_reason"): ("text", "NO", "''"),
}
MARKETPLACE_SCHEMA_INDEXES = {
    ("shopify_variants", "idx_shopify_variants_sku_normalized"),
}


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
    reviewed_sql = REFERENTIAL_DELETE_PATTERN.sub("", reviewed_sql)
    return not UNSAFE_SQL_PATTERN.search(reviewed_sql)


def reviewed_migration_sql(path, sql):
    """Admit a data-writing function body only when its reviewed bytes match."""

    expected = REVIEWED_MIGRATION_SHA256.get(Path(path).name, "")
    if not expected:
        return False
    actual = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    return actual == expected


def migration_sql_is_allowed(path, sql):
    return safe_migration_sql(sql) or reviewed_migration_sql(path, sql)


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


def _schema_issues(cur, *, migrations, columns, indexes):
    """Return PII-free compatibility failures using read-only catalogue queries."""

    issues = []
    cur.execute("SELECT to_regclass('public.schema_migrations') AS table_name")
    migration_table = (cur.fetchone() or {}).get("table_name")
    applied_migrations = set()
    if migration_table:
        cur.execute(
            "SELECT filename FROM schema_migrations WHERE filename = ANY(%s)",
            (list(migrations),),
        )
        applied_migrations = {
            str(row.get("filename") or "") for row in (cur.fetchall() or [])
        }
    for filename in migrations:
        if filename not in applied_migrations:
            issues.append(f"missing migration record: {filename}")

    cur.execute(
        """
        SELECT table_name, column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema='public'
          AND table_name = ANY(%s)
        """,
        (sorted({table for table, _column in columns}),),
    )
    live_columns = {
        (str(row.get("table_name") or ""), str(row.get("column_name") or "")): row
        for row in (cur.fetchall() or [])
    }
    for key, expected in columns.items():
        table_name, column_name = key
        expected_type, expected_nullable, default_fragment = expected
        row = live_columns.get(key)
        if not row:
            issues.append(f"missing column: {table_name}.{column_name}")
            continue
        live_type = str(row.get("data_type") or "").casefold()
        live_nullable = str(row.get("is_nullable") or "").upper()
        live_default = str(row.get("column_default") or "").casefold()
        if live_type != expected_type.casefold():
            issues.append(
                f"wrong type: {table_name}.{column_name} expected={expected_type} actual={live_type or 'unknown'}"
            )
        if live_nullable != expected_nullable:
            issues.append(
                f"wrong nullability: {table_name}.{column_name} expected={expected_nullable} actual={live_nullable or 'unknown'}"
            )
        if default_fragment and default_fragment.casefold() not in live_default:
            issues.append(f"wrong default: {table_name}.{column_name}")

    cur.execute(
        """
        SELECT tablename, indexname
        FROM pg_indexes
        WHERE schemaname='public'
          AND tablename = ANY(%s)
        """,
        (sorted({table for table, _index in indexes}),),
    )
    live_indexes = {
        (str(row.get("tablename") or ""), str(row.get("indexname") or ""))
        for row in (cur.fetchall() or [])
    }
    for table_name, index_name in indexes:
        if (table_name, index_name) not in live_indexes:
            issues.append(f"missing index: {index_name} on {table_name}")
    return issues


def required_schema_issues(cur):
    """Core Shopify has no dependency on the optional marketplace migration."""

    del cur
    return []


def marketplace_schema_issues(cur):
    """Report optional marketplace diagnostic schema gaps without gating Shopify."""

    return _schema_issues(
        cur,
        migrations=MARKETPLACE_SCHEMA_MIGRATIONS,
        columns=MARKETPLACE_SCHEMA_COLUMNS,
        indexes=MARKETPLACE_SCHEMA_INDEXES,
    )


def _verify_schema(*, issue_loader, ready_message, failure_message):

    database_url, source = get_database_url()
    if not database_url:
        raise SystemExit("Schema verification failed: DATABASE_URL is missing.")
    from psycopg.rows import dict_row

    with psycopg.connect(
        database_url,
        autocommit=True,
        row_factory=dict_row,
        options="-c default_transaction_read_only=on",
    ) as conn:
        with conn.cursor() as cur:
            issues = issue_loader(cur)
    if issues:
        print(f"Schema verification source: {source}")
        for issue in issues:
            print(f"MISSING {issue}")
        raise SystemExit(
            failure_message
        )
    print(f"Schema verification source: {source}")
    print(ready_message)
    return True


def verify_required_schema():
    """Verify only schema required by the core application and Shopify ingestion."""

    return _verify_schema(
        issue_loader=required_schema_issues,
        ready_message="READY required core application schema",
        failure_message="Required core application schema verification failed.",
    )


def verify_marketplace_schema():
    """Explicitly verify optional marketplace diagnostics without gating startup."""

    return _verify_schema(
        issue_loader=marketplace_schema_issues,
        ready_message="READY optional Shopify marketplace diagnostics schema",
        failure_message=(
            "Optional marketplace schema verification failed. Apply "
            f"{SHOPIFY_MARKETPLACE_MIGRATION} to enable full marketplace diagnostics."
        ),
    )


def run_migrations(*, only=None, check=False):
    selected = migration_files(only)
    unsafe = [
        path.name
        for path in selected
        if not migration_sql_is_allowed(path, path.read_text(encoding="utf-8"))
    ]
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
                if not migration_sql_is_allowed(path, sql):
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


def _migration_body(sql):
    # SQL files carry their own transaction wrappers for manual execution.
    # Deployment owns one transaction for DDL, validation AND tracking records.
    return re.sub(r"(?im)^\s*(?:BEGIN|COMMIT);\s*$", "", sql)


def _existing_controls_match(cur, sql):
    if manual_certificate_schema.schema_issues(cur, include_identity=False):
        return False
    expected = dict(re.findall(
        r"CREATE OR REPLACE FUNCTION\s+(\w+)\(\).*?AS\s+\$\$(.*?)\$\$",
        sql, flags=re.S | re.I,
    ))
    cur.execute("""SELECT proname, prosrc FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
                   WHERE n.nspname='public' AND pronargs=0 AND proname=ANY(%s)""", (list(expected),))
    actual = {r['proname']: r['prosrc'].strip() for r in cur.fetchall()}
    return bool(expected) and all(actual.get(name) == body.strip() for name, body in expected.items())


def run_deployment_migrations(*, check=False):
    """Apply only the explicit SHA-reviewed deployment set; fail closed."""
    selected = [(MIGRATIONS_DIR / name, (MIGRATIONS_DIR / name).read_text(encoding='utf-8'))
                for name in DEPLOYMENT_MIGRATIONS]
    for path, sql in selected:
        if not reviewed_migration_sql(path, sql):
            raise RuntimeError(f"Deployment migration is not SHA-reviewed: {path.name}")
    if check:
        print('READY deployment migration manifest: ' + ', '.join(DEPLOYMENT_MIGRATIONS))
        return
    database_url, source = get_database_url()
    if not database_url:
        raise RuntimeError('Deployment migration failed: database URL is missing')
    from psycopg.rows import dict_row
    applied = []
    with psycopg.connect(database_url, row_factory=dict_row, connect_timeout=15,
                          prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout='60s'")
            cur.execute("SET LOCAL statement_timeout='120s'")
            cur.execute("SELECT pg_advisory_xact_lock(731948321)")
            before = manual_certificate_schema.schema_issues(cur)
            print('DEPLOY manual certificate schema before: ' + ('; '.join(before) or 'ready'), flush=True)
            cur.execute("CREATE TABLE IF NOT EXISTS schema_migrations (filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT now())")
            for path, sql in selected:
                cur.execute('SELECT filename FROM schema_migrations WHERE filename=%s', (path.name,))
                if cur.fetchone():
                    continue
                already_present = (path.name == DEPLOYMENT_MIGRATIONS[0] and _existing_controls_match(cur, sql))
                if not already_present:
                    cur.execute(_migration_body(sql))
                cur.execute('INSERT INTO schema_migrations(filename) VALUES (%s)', (path.name,))
                applied.append((path.name, 'recorded verified existing schema' if already_present else 'applied'))
            issues = manual_certificate_schema.schema_issues(cur)
            if issues:
                raise RuntimeError('Deployment schema incompatible: ' + '; '.join(issues))
        conn.commit()
    # Independently verify committed schema. No application listener starts first.
    with psycopg.connect(database_url, row_factory=dict_row, connect_timeout=15,
                          options='-c default_transaction_read_only=on') as conn:
        with conn.cursor() as cur:
            issues = manual_certificate_schema.schema_issues(cur)
            if issues:
                raise RuntimeError('Post-commit deployment verification failed: ' + '; '.join(issues))
            cur.execute('SELECT count(*) AS count FROM manual_order_line_editions')
            count = cur.fetchone()['count']
    for name, result in applied:
        print(f'DEPLOY {result}: {name}', flush=True)
    print(f'READY manual certificate schema source={source} persisted_overrides={count}', flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply reviewed Sports Cave database migrations.")
    parser.add_argument("--only", help="Apply one migration filename from the migrations directory.")
    parser.add_argument("--check", action="store_true", help="Validate selection and safety without connecting.")
    parser.add_argument("--deploy", action="store_true", help="Apply the SHA-reviewed deployment manifest and verify compatibility.")
    parser.add_argument(
        "--verify-required-schema",
        action="store_true",
        help="Read-only verification that deployment-required migrations, columns and indexes exist.",
    )
    parser.add_argument(
        "--verify-marketplace-schema",
        action="store_true",
        help="Read-only verification of optional marketplace diagnostic columns and indexes.",
    )
    args = parser.parse_args()
    if args.deploy:
        if args.only or args.verify_required_schema or args.verify_marketplace_schema:
            parser.error('--deploy cannot be combined with another migration selection')
        run_deployment_migrations(check=args.check)
    elif args.verify_required_schema or args.verify_marketplace_schema:
        if args.only or args.check:
            parser.error("schema verification cannot be combined with --only or --check.")
        if args.verify_required_schema and args.verify_marketplace_schema:
            parser.error("choose one schema verification mode.")
        if args.verify_marketplace_schema:
            verify_marketplace_schema()
        else:
            verify_required_schema()
    else:
        run_migrations(only=args.only, check=args.check)
