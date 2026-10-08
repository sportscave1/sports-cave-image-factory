"""Account reads keep fresh permissions without per-user round trips."""
from unittest import TestCase, main
from unittest.mock import patch
from scripts.benchmark_account_reads import Connection, Cursor
from os_accounts import PostgresAccountStore


class AccountReadQueryTests(TestCase):
    def test_each_read_uses_one_authoritative_query(self):
        for name, args, kwargs in (("first_admin", (), {}), ("get_user", ("a",), {}),
                                  ("get_user", ("a",), {"include_removed": True}),
                                  ("find_user_by_login", ("Staff",), {}), ("list_users", (), {})):
            with self.subTest(name=name, kwargs=kwargs):
                cur, store = Cursor(), PostgresAccountStore()
                with patch.object(store, "ensure_schema"), patch.object(store, "_connect", return_value=Connection(cur)), patch("scripts.benchmark_account_reads.time.sleep"):
                    value = getattr(store, name)(*args, **kwargs)
                self.assertEqual(cur.calls, 1)
                self.assertIn("p.user_id=u.id AND p.can_access IS TRUE", cur.sql)
                self.assertIn("ORDER BY p.page_key", cur.sql)
                self.assertNotIn("_page_permissions", value[0] if isinstance(value, list) else value)
                self.assertEqual((value[0] if isinstance(value, list) else value)["page_permissions"], ["dashboard"])
                if not kwargs.get("include_removed"):
                    self.assertIn("account_status <> 'removed'", cur.sql)
                if name == "list_users": self.assertNotIn("password_hash", cur.sql)

    def test_no_row_and_no_permissions_are_safe(self):
        self.assertEqual(PostgresAccountStore._clean_read_user(None), {})
        row = PostgresAccountStore._clean_read_user({"id": "worker", "_page_permissions": []})
        self.assertEqual(row["page_permissions"], [])


if __name__ == "__main__": main()
