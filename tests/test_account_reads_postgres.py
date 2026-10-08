"""Opt-in real PostgreSQL verification using temporary tables, always rolled back."""
from contextlib import nullcontext
import os
import unittest
from unittest.mock import patch
import uuid

import os_accounts


@unittest.skipUnless(os.getenv("LOCAL_ACCOUNT_TEST_DSN"), "Set LOCAL_ACCOUNT_TEST_DSN to an isolated loopback PostgreSQL")
class AccountPostgresTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg.conninfo import conninfo_to_dict
        from psycopg.rows import dict_row
        dsn = os.environ["LOCAL_ACCOUNT_TEST_DSN"]
        self.assertIn(conninfo_to_dict(dsn).get("host"), ("127.0.0.1", "localhost"))
        self.conn = psycopg.connect(dsn, row_factory=dict_row)
        self.addCleanup(self.conn.close)
        self.addCleanup(self.conn.rollback)
        self.conn.execute("""CREATE TEMP TABLE os_users(
            id uuid, username text, email text, display_name text, password_hash text,
            role text, country text, timezone text, is_active boolean DEFAULT true,
            session_version integer DEFAULT 1, account_status text DEFAULT 'active',
            removed_at timestamptz, removed_by uuid, created_at timestamptz DEFAULT now(),
            updated_at timestamptz, last_login_at timestamptz)""")
        self.conn.execute("CREATE TEMP TABLE os_user_page_permissions(user_id uuid, page_key text, can_access boolean)")
        self.ids = [str(uuid.uuid4()) for _ in range(3)]
        for index, identity in enumerate(self.ids):
            self.conn.execute("INSERT INTO os_users(id,username,display_name,password_hash,role,account_status) VALUES(%s,%s,%s,'hash',%s,%s)",
                              (identity, f"fixture-{index}", f"Fixture {index}", "admin" if index == 0 else "worker", "removed" if index == 2 else "active"))
        self.conn.execute("INSERT INTO os_user_page_permissions VALUES (%s,'orders',true),(%s,'dashboard',true),(%s,'settings',false)", [self.ids[1]]*3)
        self.store = os_accounts.PostgresAccountStore()
        self.store._schema_ready = True
        self.connection_patch = patch.object(self.store, "_connect", side_effect=lambda: nullcontext(self.conn))
        self.connection_patch.start()
        self.addCleanup(self.connection_patch.stop)

    def test_read_contract_and_immediate_revocation(self):
        self.assertEqual(self.store.first_admin()["id"], self.ids[0])
        user = self.store.get_user(self.ids[1])
        self.assertEqual(user["page_permissions"], ["dashboard", "orders"])
        self.assertEqual(user["password_hash"], "hash")
        self.assertEqual(self.store.find_user_by_login("FIXTURE-1")["id"], self.ids[1])
        self.assertEqual(self.store.get_user(self.ids[2]), {})
        self.assertFalse(self.store.get_user(self.ids[2], include_removed=True)["is_active"])
        listed = self.store.list_users()
        self.assertEqual(len(listed), 2)
        self.assertTrue(all("password_hash" not in row for row in listed))
        self.conn.execute("UPDATE os_user_page_permissions SET can_access=false WHERE user_id=%s", (self.ids[1],))
        self.conn.execute("UPDATE os_users SET session_version=2 WHERE id=%s", (self.ids[1],))
        refreshed = self.store.get_user(self.ids[1])
        self.assertEqual(refreshed["page_permissions"], [])
        self.assertEqual(refreshed["session_version"], 2)


if __name__ == "__main__": unittest.main()
