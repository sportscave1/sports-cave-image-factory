import re
import unittest
from unittest import mock

import social_media_store


def complete_columns():
    return {
        table: set(columns)
        for table, columns in social_media_store.SOCIAL_MEDIA_REQUIRED_SCHEMA.items()
    }


class FakeCursor:
    def __init__(self, columns=None):
        self.columns = columns if columns is not None else complete_columns()
        self.executed = []
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, sql, params=None):
        clean_sql = " ".join(str(sql).split())
        self.executed.append((clean_sql, params))
        if "FROM information_schema.columns" in clean_sql:
            self._rows = [
                {"table_name": table, "column_name": column}
                for table, columns in self.columns.items()
                for column in columns
            ]
        else:
            self._rows = []

    def fetchall(self):
        return list(self._rows)


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1


class FakeBackend:
    def __init__(self, cursor, *, failures=0):
        self.cursor = cursor
        self.failures = failures
        self.connect_calls = 0
        self.connections = []

    @staticmethod
    def is_configured():
        return True

    def connect(self):
        self.connect_calls += 1
        if self.connect_calls <= self.failures:
            raise RuntimeError("temporary provider response with private details")
        connection = FakeConnection(self.cursor)
        self.connections.append(connection)
        return connection


class SocialMediaReadinessTests(unittest.TestCase):
    def setUp(self):
        social_media_store.reset_schema_cache()

    def tearDown(self):
        social_media_store.reset_schema_cache()

    def test_empty_valid_tables_are_ready_and_success_is_cached(self):
        cursor = FakeCursor()
        backend = FakeBackend(cursor)

        with mock.patch.object(social_media_store, "_backend", return_value=backend):
            first = social_media_store.schema_status()
            second = social_media_store.schema_status()

        self.assertTrue(first["ready"])
        self.assertEqual(first["reason"], "ok")
        self.assertEqual(second, first)
        self.assertEqual(backend.connect_calls, 1)
        access_checks = [
            sql for sql, _params in cursor.executed
            if sql.startswith("SELECT 1 FROM social_")
        ]
        self.assertEqual(len(access_checks), len(complete_columns()))

    def test_missing_tables_are_created_from_the_packaged_migration(self):
        cursor = FakeCursor(columns={})
        backend = FakeBackend(cursor)

        def apply_migration(selected_cursor):
            selected_cursor.columns = complete_columns()

        with (
            mock.patch.object(social_media_store, "_backend", return_value=backend),
            mock.patch.object(
                social_media_store,
                "_apply_social_media_migration",
                side_effect=apply_migration,
            ) as apply_mock,
        ):
            status = social_media_store.schema_status()

        self.assertTrue(status["ready"])
        apply_mock.assert_called_once_with(cursor)
        self.assertEqual(backend.connections[0].commits, 1)

    def test_missing_tables_report_initialisation_failure_safely(self):
        cursor = FakeCursor(columns={})
        backend = FakeBackend(cursor)

        with (
            mock.patch.object(social_media_store, "_backend", return_value=backend),
            mock.patch.object(
                social_media_store,
                "_apply_social_media_migration",
                side_effect=RuntimeError("PRIVATE_PROVIDER_DETAIL_123"),
            ),
        ):
            status = social_media_store.schema_status()

        self.assertFalse(status["ready"])
        self.assertEqual(status["reason"], "schema_initialisation_failed")
        self.assertNotIn("PRIVATE_PROVIDER_DETAIL_123", str(status))

    def test_missing_columns_are_diagnosed_without_treating_empty_data_as_failure(self):
        columns = complete_columns()
        columns["social_posts"].remove("content_name")
        cursor = FakeCursor(columns=columns)
        backend = FakeBackend(cursor)

        with (
            mock.patch.object(social_media_store, "_backend", return_value=backend),
            mock.patch.object(
                social_media_store,
                "_apply_social_media_migration",
            ) as apply_mock,
        ):
            status = social_media_store.schema_status()

        self.assertFalse(status["ready"])
        self.assertEqual(status["reason"], "schema_mismatch")
        self.assertEqual(
            status["missing_columns"],
            {"social_posts": ["content_name"]},
        )
        apply_mock.assert_not_called()

    def test_temporary_failure_is_not_permanently_cached_and_force_recovers(self):
        cursor = FakeCursor()
        backend = FakeBackend(cursor, failures=1)

        with mock.patch.object(social_media_store, "_backend", return_value=backend):
            failed = social_media_store.schema_status()
            cached_failure = social_media_store.schema_status()
            recovered = social_media_store.schema_status(force=True)

        self.assertFalse(failed["ready"])
        self.assertTrue(failed["retryable"])
        self.assertEqual(cached_failure, failed)
        self.assertEqual(backend.connect_calls, 2)
        self.assertTrue(recovered["ready"])

    def test_failed_status_retries_after_the_short_cache_window(self):
        cursor = FakeCursor()
        backend = FakeBackend(cursor, failures=1)

        with (
            mock.patch.object(social_media_store, "_backend", return_value=backend),
            mock.patch.object(
                social_media_store.time,
                "monotonic",
                side_effect=(10.0, 10.0, 25.0, 25.0),
            ),
        ):
            failed = social_media_store.schema_status()
            recovered = social_media_store.schema_status()

        self.assertFalse(failed["ready"])
        self.assertTrue(recovered["ready"])
        self.assertEqual(backend.connect_calls, 2)

    def test_migration_and_application_require_the_same_tables_and_columns(self):
        sql = social_media_store._migration_path().read_text(encoding="utf-8")
        table_marker = "CREATE TABLE IF NOT EXISTS "
        chunks = sql.split(table_marker)[1:]
        blocks = {
            chunk.split("(", 1)[0].strip(): chunk
            for chunk in chunks
        }

        self.assertEqual(
            set(blocks),
            set(social_media_store.SOCIAL_MEDIA_REQUIRED_SCHEMA),
        )
        for table, columns in social_media_store.SOCIAL_MEDIA_REQUIRED_SCHEMA.items():
            block = blocks[table]
            for column in columns:
                with self.subTest(table=table, column=column):
                    self.assertRegex(
                        block,
                        rf"(?m)^\s*{re.escape(column)}\s+",
                    )


if __name__ == "__main__":
    unittest.main()
