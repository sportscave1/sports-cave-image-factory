"""Real SQL and RLS on disposable PostgreSQL; no environment database discovery."""
import os
from pathlib import Path
import socket
import subprocess
import time
import unittest
from unittest.mock import Mock, patch

import requests
import social_community_store as store
from meta_social import assess_creator
from scripts.retire_social_workspace import inventory, retire, TABLES, validate_local_dsn
from tests.community_fixtures import ADMIN, FakeCommunity

ROOT = Path(__file__).resolve().parents[1]


class Cursor:
    def __init__(self, url):
        self.url = url
        self.rows = []
        self.description = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, statement, args=()):
        statement = statement if isinstance(statement, str) else statement.as_string(None)
        for index in range(len(args)):
            statement = statement.replace("%s", "$" + str(index + 1), 1)
        result = requests.post(self.url, json={"sql": statement, "args": list(args)}, timeout=10)
        if result.status_code != 200:
            raise RuntimeError(result.json()["error"])
        payload = result.json()
        self.rows = payload.get("rows", [])
        self.description = payload.get("fields")

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    def fetchall(self):
        rows, self.rows = self.rows, []
        return rows


class Connection:
    def __init__(self, url):
        self.url = url

    def __enter__(self):
        self.cursor().execute("BEGIN")
        return self

    def __exit__(self, kind, *args):
        self.cursor().execute("ROLLBACK" if kind else "COMMIT")

    def cursor(self):
        return Cursor(self.url)

    def commit(self):
        self.cursor().execute("COMMIT")
        self.cursor().execute("BEGIN")


class CommunityDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        cls.url = f"http://127.0.0.1:{port}"
        cls.process = subprocess.Popen(["node", "tests/social_community_postgres.mjs", str(port)], cwd=ROOT,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       env={key: value for key, value in os.environ.items() if key.upper() in
                                            ("PATH", "SYSTEMROOT", "TEMP", "TMP", "COMSPEC", "PATHEXT")})
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                Cursor(cls.url).execute("SELECT 1")
                return
            except (requests.RequestException, RuntimeError):
                if cls.process.poll() is not None:
                    raise AssertionError(cls.process.stderr.read().decode())
                time.sleep(.1)
        cls.process.terminate()
        cls.process.wait(timeout=5)
        raise AssertionError("Local SQL fixture did not become ready")

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=5)
        cls.process.stdout.close()
        cls.process.stderr.close()

    def setUp(self):
        cur = Cursor(self.url)
        cur.execute("DELETE FROM public.social_collaborators")
        cur.execute("DELETE FROM public.social_community_settings")
        self.backend = patch.object(store, "_backend", return_value=Mock(connect=lambda: Connection(self.url)))
        self.backend.start()
        self.addCleanup(self.backend.stop)
        self.profile = assess_creator(FakeCommunity(ADMIN).discover("fixture"))

    def test_upsert_keeps_custom_draft_pipeline_and_sent_marker(self):
        store.save_creator(ADMIN, self.profile)
        store.update_creator(ADMIN, "fixture", "shortlisted", "A personal invitation")
        store.save_creator(ADMIN, dict(self.profile, followers=6000))
        row = store.list_creators(ADMIN)[0]
        self.assertEqual(row["followers"], 6000)
        self.assertEqual(row["draft"], "A personal invitation")
        self.assertEqual(row["state"], "shortlisted")

    def test_atomic_claim_and_terminal_sent_marker_block_repeat_invitation(self):
        store.save_creator(ADMIN, self.profile)
        self.assertTrue(store.claim_invitation(ADMIN, "fixture"))
        self.assertFalse(store.claim_invitation(ADMIN, "fixture"))
        store.finish_invitation(ADMIN, "fixture", state="sent", message_id="sent-message")
        store.update_creator(ADMIN, "fixture", "shortlisted", "Follow up")
        self.assertFalse(store.claim_invitation(ADMIN, "fixture"))
        self.assertEqual(store.list_creators(ADMIN)[0]["message_id"], "sent-message")

    def test_unknown_and_inflight_results_cannot_be_overwritten_or_retried(self):
        store.save_creator(ADMIN, self.profile)
        self.assertTrue(store.claim_invitation(ADMIN, "fixture"))
        store.finish_invitation(ADMIN, "fixture", state="unknown")
        self.assertEqual(store.update_creator(ADMIN, "fixture", "discovered", "Try again"), [])
        self.assertFalse(store.claim_invitation(ADMIN, "fixture"))

    def test_unsuitable_declined_and_agreed_prospects_cannot_be_claimed(self):
        store.save_creator(ADMIN, dict(self.profile, fit=False))
        self.assertFalse(store.claim_invitation(ADMIN, "fixture"))
        store.save_creator(ADMIN, self.profile)
        for state in ("declined", "agreed"):
            store.update_creator(ADMIN, "fixture", state, "Saved invitation")
            self.assertFalse(store.claim_invitation(ADMIN, "fixture"))

    def test_automation_defaults_off_and_admin_only_can_change(self):
        self.assertFalse(store.automation(ADMIN)["automation_enabled"])
        worker = {"id": "worker", "role": "worker", "is_active": True, "page_permissions": ["social_media"]}
        with self.assertRaises(PermissionError):
            store.automation(worker, True)
        self.assertTrue(store.automation(ADMIN, True)["automation_enabled"])

    def test_unauthorized_user_does_not_open_database(self):
        with patch.object(store, "_backend", side_effect=AssertionError("Database opened")):
            with self.assertRaises(PermissionError):
                store.list_creators({"role": "worker", "is_active": True})

    def test_tables_have_rls_and_browser_roles_have_no_select_or_insert(self):
        cur = Cursor(self.url)
        cur.execute("SELECT relname,relrowsecurity FROM pg_class WHERE relname IN ('social_collaborators','social_community_settings')")
        self.assertTrue(all(row["relrowsecurity"] for row in cur.fetchall()))
        for role in ("anon", "authenticated"):
            for table in ("social_collaborators", "social_community_settings"):
                cur.execute("SELECT has_table_privilege(%s,%s,'SELECT') AS allowed", (role, "public." + table))
                self.assertFalse(cur.fetchone()["allowed"])
                cur.execute("SELECT has_table_privilege(%s,%s,'INSERT') AS allowed", (role, "public." + table))
                self.assertFalse(cur.fetchone()["allowed"])

    def test_schema_is_repeatable_and_list_is_bounded(self):
        store.save_creator(ADMIN, self.profile)
        cur = Cursor(self.url)
        cur.execute("""INSERT INTO public.social_collaborators(username,followers,fit,score,reason,draft)
            SELECT 'fixture'||i,1000,true,10,'synthetic','Hello' FROM generate_series(1,250) i""")
        self.assertEqual(len(store.list_creators(ADMIN)), 200)
        cur.execute("SELECT count(*) AS n FROM public.social_collaborators")
        self.assertEqual(cur.fetchone()["n"], 251)

    def test_cleanup_drops_only_retired_tables_and_exact_reel_prompts(self):
        # Real foreign keys ensure deletion order is correct and no CASCADE is needed.
        with Connection(self.url) as conn:
            cur = conn.cursor()
            for table in reversed(TABLES):
                cur.execute(f"CREATE TABLE public.{table}(id integer PRIMARY KEY)")
            cur.execute("ALTER TABLE public.social_content_jobs ADD COLUMN destination_path text")
            cur.execute("ALTER TABLE public.social_daily_priorities ADD COLUMN plan_id integer REFERENCES public.social_daily_plans(id)")
            cur.execute("INSERT INTO public.social_content_jobs VALUES (1,'04_OUTPUT/social-media/fixture')")
            cur.execute("CREATE TABLE public.prompt_templates(prompt_key text PRIMARY KEY,module text)")
            cur.execute("CREATE TABLE public.prompt_template_versions(prompt_key text)")
            cur.execute("INSERT INTO public.prompt_templates VALUES ('reel','social_reels'),('other','ads')")
            cur.execute("INSERT INTO public.prompt_template_versions VALUES ('reel'),('other')")
            report = inventory(cur)
            self.assertEqual(report["generated_destinations"], ["04_OUTPUT/social-media/fixture"])
            self.assertEqual(report["reel_prompt_count"], 1)
            retire(cur)
            self.assertEqual(inventory(cur)["tables"], {})
            cur.execute("SELECT prompt_key FROM public.prompt_templates")
            self.assertEqual(cur.fetchall(), [{"prompt_key": "other"}])
            cur.execute("SELECT prompt_key FROM public.prompt_template_versions")
            self.assertEqual(cur.fetchall(), [{"prompt_key": "other"}])
            cur.execute("SELECT count(*) AS n FROM public.social_collaborators")
            # Cleanup retains the new ledger and the rest of the OS.
            self.assertIsNotNone(cur.fetchone())
            cur.execute("DROP TABLE public.prompt_template_versions")
            cur.execute("DROP TABLE public.prompt_templates")

    def test_cleanup_refuses_remote_or_libpq_host_overrides(self):
        for dsn in ("", "postgresql://test@production/db", "postgresql://test@localhost/db?host=production",
                    "postgresql://test@127.0.0.1/db#fragment"):
            with self.assertRaises(ValueError):
                validate_local_dsn(dsn)
        self.assertEqual(validate_local_dsn("postgresql://test@127.0.0.1/disposable"), "postgresql://test@127.0.0.1/disposable")


if __name__ == "__main__":
    unittest.main()
