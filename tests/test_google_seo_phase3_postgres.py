import os
from pathlib import Path
import unittest
import uuid
from urllib.parse import urlsplit

from pglast import parse_sql
from pglast.keywords import COL_NAME_KEYWORDS, RESERVED_KEYWORDS, TYPE_FUNC_NAME_KEYWORDS
from pglast.parser import ParseError
from pglast.visitors import Visitor
import psycopg
from psycopg import sql

import google_seo
import google_seo_import as importer


ROOT = Path(__file__).resolve().parents[1]
PHASE1_SQL = (ROOT / "migrations" / google_seo.GOOGLE_SEO_MIGRATION).read_text(encoding="utf-8")
PHASE3_SQL = (ROOT / "migrations" / importer.SEO_IMPORT_MIGRATION).read_text(encoding="utf-8")
LOCAL_POSTGRES_URL = os.getenv("SPORTS_CAVE_TEST_POSTGRES_URL", "").strip()


class _ColumnNameVisitor(Visitor):
    def __init__(self):
        super().__init__()
        self.names = []

    def visit_ColumnDef(self, _ancestors, node):
        self.names.append(node.colname)


class Phase3PostgresParserTests(unittest.TestCase):
    def test_complete_phase3_migration_parses_with_postgresql_grammar(self):
        statements = parse_sql(PHASE3_SQL)

        self.assertGreater(len(statements), 1)
        self.assertIn("active_slice_date DATE", PHASE3_SQL)
        self.assertNotRegex(PHASE3_SQL, r"\bcurrent_date\b")

    def test_phase3_column_names_are_valid_postgresql_identifiers(self):
        visitor = _ColumnNameVisitor()
        visitor(parse_sql(PHASE3_SQL))
        restricted = RESERVED_KEYWORDS | TYPE_FUNC_NAME_KEYWORDS | COL_NAME_KEYWORDS

        self.assertEqual(
            sorted({name for name in visitor.names if name.lower() in restricted}),
            [],
        )

    def test_regression_postgresql_rejects_reserved_current_date_column(self):
        broken_sql = PHASE3_SQL.replace(
            "active_slice_date DATE",
            "current_date DATE",
            1,
        )

        with self.assertRaises(ParseError):
            parse_sql(broken_sql)


@unittest.skipUnless(
    LOCAL_POSTGRES_URL,
    "Set SPORTS_CAVE_TEST_POSTGRES_URL to an isolated local PostgreSQL database.",
)
class Phase3PostgresExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        host = (urlsplit(LOCAL_POSTGRES_URL).hostname or "").lower()
        if host not in {"localhost", "127.0.0.1", "::1"}:
            raise unittest.SkipTest("Phase 3 migration tests refuse non-local PostgreSQL hosts.")

    def test_phase3_executes_twice_and_preserves_encrypted_connection(self):
        schema_name = f"seo_phase3_test_{uuid.uuid4().hex}"
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
                    (
                        "sports-cave",
                        "admin-1",
                        sentinel,
                        "https://example.test/",
                        "properties/123",
                    ),
                )
                partial_phase3_sql = PHASE3_SQL.split(
                    "CREATE TABLE IF NOT EXISTS seo_sync_runs",
                    1,
                )[0]
                cursor.execute(partial_phase3_sql)
                cursor.execute(PHASE3_SQL)
                cursor.execute(PHASE3_SQL)
                cursor.execute(
                    """
                    SELECT encrypted_refresh_token, gsc_site_url, ga4_property_id
                    FROM seo_google_connections WHERE workspace_key=%s
                    """,
                    ("sports-cave",),
                )
                preserved = cursor.fetchone()
                cursor.execute(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema=%s AND table_name='seo_sync_runs'
                    """,
                    (schema_name,),
                )
                columns = {row[0] for row in cursor.fetchall()}

            self.assertEqual(
                preserved,
                (sentinel, "https://example.test/", "properties/123"),
            )
            self.assertIn("active_slice_date", columns)
            self.assertIn("checkpoint_date", columns)
            self.assertNotIn("current_date", columns)
        finally:
            with connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                        sql.Identifier(schema_name)
                    )
                )
            connection.close()


if __name__ == "__main__":
    unittest.main()
