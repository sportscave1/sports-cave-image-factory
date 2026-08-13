import os
from pathlib import Path
import unittest
import uuid
from urllib.parse import urlsplit

from pglast import parse_sql
from pglast.keywords import COL_NAME_KEYWORDS, RESERVED_KEYWORDS, TYPE_FUNC_NAME_KEYWORDS
from pglast.visitors import Visitor
import psycopg
from psycopg import sql

import google_seo
import google_seo_import
import google_seo_phase4


ROOT = Path(__file__).resolve().parents[1]
PHASE1_SQL = (ROOT / "migrations" / google_seo.GOOGLE_SEO_MIGRATION).read_text(encoding="utf-8")
PHASE3_SQL = (ROOT / "migrations" / google_seo_import.SEO_IMPORT_MIGRATION).read_text(encoding="utf-8")
PHASE4_SQL = (ROOT / "migrations" / google_seo_phase4.PHASE4_MIGRATION).read_text(encoding="utf-8")
LOCAL_POSTGRES_URL = os.getenv("SPORTS_CAVE_TEST_POSTGRES_URL", "").strip()


class _ColumnNameVisitor(Visitor):
    def __init__(self):
        super().__init__()
        self.names = []

    def visit_ColumnDef(self, _ancestors, node):
        self.names.append(node.colname)


class Phase4PostgresParserTests(unittest.TestCase):
    def test_complete_phase4_migration_parses_with_postgresql_grammar(self):
        statements = parse_sql(PHASE4_SQL)
        self.assertGreater(len(statements), 10)
        self.assertIn("CREATE TABLE IF NOT EXISTS seo_canonical_pages", PHASE4_SQL)
        self.assertIn("CREATE TABLE IF NOT EXISTS seo_revenue_reconciliations", PHASE4_SQL)

    def test_phase4_column_names_are_valid_postgresql_identifiers(self):
        visitor = _ColumnNameVisitor()
        visitor(parse_sql(PHASE4_SQL))
        restricted = RESERVED_KEYWORDS | TYPE_FUNC_NAME_KEYWORDS | COL_NAME_KEYWORDS
        self.assertEqual(sorted({name for name in visitor.names if name.lower() in restricted}), [])


@unittest.skipUnless(
    LOCAL_POSTGRES_URL,
    "Set SPORTS_CAVE_TEST_POSTGRES_URL to an isolated local PostgreSQL database.",
)
class Phase4PostgresExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        host = (urlsplit(LOCAL_POSTGRES_URL).hostname or "").lower()
        if host not in {"localhost", "127.0.0.1", "::1"}:
            raise unittest.SkipTest("Phase 4 migration tests refuse non-local PostgreSQL hosts.")

    def test_phase4_executes_twice_and_preserves_phase1_and_phase3_data(self):
        schema_name = f"seo_phase4_test_{uuid.uuid4().hex}"
        sentinel = "encrypted-refresh-token-sentinel"
        connection = psycopg.connect(LOCAL_POSTGRES_URL, autocommit=True)
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name)))
                cursor.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema_name)))
                cursor.execute(PHASE1_SQL)
                cursor.execute(
                    """
                    INSERT INTO seo_google_connections(
                        workspace_key, owner_user_id, encrypted_refresh_token,
                        gsc_site_url, ga4_property_id
                    ) VALUES (%s, %s, %s, %s, %s)
                    """,
                    ("sports-cave", "admin-1", sentinel, "https://example.test/", "properties/123"),
                )
                cursor.execute(PHASE3_SQL)
                cursor.execute(
                    """
                    INSERT INTO seo_gsc_daily_totals(
                        workspace_key, gsc_site_url, date, clicks, impressions, ctr, average_position
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    ("sports-cave", "https://example.test/", "2026-08-01", 1, 10, .1, 2),
                )
                cursor.execute(PHASE4_SQL)
                cursor.execute(PHASE4_SQL)
                cursor.execute(
                    "SELECT encrypted_refresh_token FROM seo_google_connections WHERE workspace_key=%s",
                    ("sports-cave",),
                )
                self.assertEqual(cursor.fetchone()[0], sentinel)
                cursor.execute("SELECT COUNT(*) FROM seo_gsc_daily_totals")
                self.assertEqual(cursor.fetchone()[0], 1)
        finally:
            with connection.cursor() as cursor:
                cursor.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema_name)))
            connection.close()


if __name__ == "__main__":
    unittest.main()
