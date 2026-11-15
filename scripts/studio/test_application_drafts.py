"""V8 lifecycle regressions. Disposable repositories; no provider or production writes."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import application_drafts as apps
import draft_ui
import drafts
import studio
from test_editor import FIXTURE


class ApplicationDraftTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / "repo"
        self.repo.mkdir()
        studio.git(self.repo, "init", "-b", "main")
        studio.git(self.repo, "config", "user.email", "fixture@example.invalid")
        studio.git(self.repo, "config", "user.name", "Synthetic fixture")
        (self.repo / "app.py").write_text(FIXTURE, encoding="utf-8")
        (self.repo / "screen.html").write_text("<h1>live</h1>", encoding="utf-8")
        (self.repo / "os_accounts.py").write_text("PAGE_REGISTRY=({'key':'home','route':'Home','label':'Home','group':'Main'},)", encoding="utf-8")
        studio.git(self.repo, "add", ".")
        studio.git(self.repo, "commit", "-m", "Disposable synthetic fixture")
        self.sha = studio.git(self.repo, "rev-parse", "HEAD")
        self.home = self.base / "studio"
        studio.initialize(self.home, self.repo, self.sha, "Synthetic test receipt", "owner")
        self.task = studio.create_task(self.home, "Technical task", "CORE", "owner", "fixture-owner")
        self.legacy = drafts.new(self.home, self.task["id"], "owner", "V6 technical acceptance")
        self.receipt = {"service_id": apps.SERVICE, "repository": apps.REPOSITORY,
                        "status": "live", "revision": self.sha, "deployment_id": "dep-fixture",
                        "verified_at": studio.now(), "evidence": "synthetic fixture"}
        studio.atomic(apps.live_path(self.home), self.receipt)
        self.remote = patch.object(apps, "remote_main", return_value=self.sha)
        self.remote_mock = self.remote.start()
        self.addCleanup(self.remote.stop)

    def create(self, **kwargs):
        return apps.create(self.home, self.task["id"], "owner", **kwargs)

    def review(self, draft):
        return apps.review(self.home, draft["id"], "owner")

    def test_default_idempotent_real_worktree_and_latest_base(self):
        draft = self.create(default=True)
        again = self.create(default=True)
        self.assertEqual(draft["id"], again["id"])
        self.assertEqual(draft["name"], "Sports Cave OS copy")
        root = Path(draft["worktree_path"])
        self.assertNotEqual(root, self.repo)
        self.assertEqual(studio.git(root, "rev-parse", "HEAD"), self.sha)
        self.assertEqual(studio.git(root, "branch", "--show-current"), draft["branch"])
        self.assertEqual((root/"screen.html").read_bytes(), (self.repo/"screen.html").read_bytes())
        self.assertFalse(draft["release_eligible"])

    def test_missing_stale_mismatched_live_fail_without_new_task(self):
        before = studio.read(self.home/".studio/registry.json")
        for receipt in [None, {**self.receipt, "verified_at": "2020-01-01T00:00:00+00:00"},
                        {**self.receipt, "service_id": "other"}]:
            if receipt is None:
                apps.live_path(self.home).unlink()
            else:
                studio.atomic(apps.live_path(self.home), receipt)
            with self.assertRaises(ValueError):
                self.create()
        studio.atomic(apps.live_path(self.home), self.receipt)
        with patch.object(apps, "remote_main", return_value="b"*40), self.assertRaises(ValueError):
            self.create()
        self.assertEqual(before, studio.read(self.home/".studio/registry.json"))

    def test_rename_does_not_change_branch_id_files_or_worktree(self):
        draft = self.create()
        before = studio.snapshot(Path(draft["worktree_path"]))
        apps.rename_or_archive(self.home, draft["id"], "owner", "rename",
                               self.review(draft)["fingerprint"], name="Summer refresh")
        renamed = drafts.inspect(self.home, draft["id"], "owner")
        for key in ["id", "task_id", "branch", "worktree_path", "base_commit"]:
            self.assertEqual(renamed[key], draft[key])
        self.assertEqual(studio.snapshot(Path(draft["worktree_path"])), before)
        self.assertEqual(renamed["name"], "Summer refresh")

    def test_duplicate_copies_only_selected_source_and_distinct_identity(self):
        draft = self.create()
        root = Path(draft["worktree_path"])
        (root/"screen.html").write_text("Uncommitted selected application change")
        (Path(self.task["worktree_path"])/"screen.html").write_text("Unfinished technical task")
        duplicate = self.create(source_id=draft["id"], expected=self.review(draft)["fingerprint"])
        self.assertEqual(duplicate["name"], "Sports Cave OS copy 2")
        self.assertNotEqual(duplicate["id"], draft["id"])
        self.assertNotEqual(duplicate["branch"], draft["branch"])
        self.assertEqual((Path(duplicate["worktree_path"])/"screen.html").read_text(), "Uncommitted selected application change")
        self.assertEqual((self.repo/"screen.html").read_text(), "<h1>live</h1>")
        self.assertEqual((Path(self.task["worktree_path"])/"screen.html").read_text(), "Unfinished technical task")
        self.assertEqual(self.create()["name"], "Sports Cave OS copy 3")

    def test_duplicate_rejects_changed_review_and_forbidden_source(self):
        draft = self.create()
        reviewed = self.review(draft)
        (Path(draft["worktree_path"])/"screen.html").write_text("Concurrent edit")
        with self.assertRaises(ValueError):
            self.create(source_id=draft["id"], expected=reviewed["fingerprint"])
        (Path(draft["worktree_path"])/".env").write_text("SYNTHETIC_SECRET=placeholder")
        with self.assertRaises(ValueError):
            self.create(source_id=draft["id"], expected=self.review(draft)["fingerprint"])

    def test_catalog_hides_technical_tasks_without_mutating_them(self):
        draft = self.create()
        server = draft_ui.DraftServer(self.home, self.task["id"], "owner")
        self.addCleanup(server.server_close)
        before = (self.home/".studio/registry.json").read_bytes()
        self.assertEqual([r["id"] for r in server.catalog()["rows"]], [draft["id"]])
        self.assertEqual([r["id"] for r in server.catalog(True)["rows"]], [self.legacy["id"]])
        self.assertEqual((self.home/".studio/registry.json").read_bytes(), before)

    def test_default_selection_verifies_ancestry_and_persists_authorised_id(self):
        older=self.create()
        (self.repo/"screen.html").write_text("new verified Live")
        studio.git(self.repo,"add",".")
        studio.git(self.repo,"commit","-m","New synthetic revision")
        newer_sha=studio.git(self.repo,"rev-parse","HEAD")
        self.remote_mock.return_value=newer_sha
        studio.atomic(apps.live_path(self.home),{**self.receipt,"revision":newer_sha})
        newer=self.create()
        registry=studio.read(self.home/".studio/registry.json")
        self.assertEqual(apps.default_selection(self.home,registry,"owner"),newer["id"])
        apps.remember_selection(self.home,older["id"],"owner")
        self.assertEqual(apps.default_selection(self.home,registry,"owner"),older["id"])
        with self.assertRaises((ValueError, RuntimeError)):apps.remember_selection(self.home,older["id"],"intruder")
        server=draft_ui.DraftServer(self.home,self.task["id"],"owner")
        self.addCleanup(server.server_close)
        catalog=server.catalog()
        self.assertEqual(catalog["default_draft_id"],older["id"])
        row=next(r for r in catalog["rows"] if r["id"]==older["id"])
        self.assertTrue(row["live_newer"])
        (Path(older["worktree_path"])/"screen.html").write_text("unfinished")
        row=next(r for r in server.catalog()["rows"] if r["id"]==older["id"])
        self.assertTrue(row["dirty"])
        self.assertEqual(studio.git(older["worktree_path"],"rev-parse","HEAD"),self.sha)
        registry["drafts"][-1]["archived_at"]=studio.now()
        registry["drafts"][-2]["archived_at"]=studio.now()
        self.assertIsNone(apps.default_selection(self.home,registry,"owner"))

    def test_archive_requires_review_and_retains_source_and_task(self):
        draft = self.create()
        root = Path(draft["worktree_path"])
        (root/"screen.html").write_text("Unfinished retained")
        review = self.review(draft)
        self.assertTrue(review["has_unfinished_changes"])
        with self.assertRaises(ValueError):
            apps.rename_or_archive(self.home, draft["id"], "owner", "archive", review["fingerprint"], confirmation="yes")
        apps.rename_or_archive(self.home, draft["id"], "owner", "archive", review["fingerprint"], confirmation="ARCHIVE "+draft["name"])
        self.assertEqual((root/"screen.html").read_text(), "Unfinished retained")
        self.assertEqual(studio.git(root, "branch", "--show-current"), draft["branch"])
        with self.assertRaises(ValueError):
            drafts.inspect(self.home, draft["id"], "owner")
        # Merely opening/configuring cannot recreate a copy after archival.
        self.assertEqual(self.create(default=True)["id"], draft["id"])

    def test_other_owner_cannot_manage_or_copy(self):
        draft = self.create()
        for run in [lambda: apps.review(self.home, draft["id"], "other"),
                    lambda: apps.create(self.home, self.task["id"], "other"),
                    lambda: apps.rename_or_archive(self.home, draft["id"], "other", "rename", "", name="no")]:
            with self.assertRaises(RuntimeError):
                run()

    def test_local_confirmation_is_one_use_and_scope_not_browser_controlled(self):
        server = draft_ui.DraftServer(self.home, self.task["id"], "owner")
        self.addCleanup(server.server_close)
        plan = server.application_prepare({"operation": "configure"})
        result = server.application_run({"ticket": plan["ticket"]})
        self.assertEqual(result["name"], apps.DEFAULT_NAME)
        with self.assertRaises(ValueError):
            server.application_run({"ticket": plan["ticket"]})
        with self.assertRaises(ValueError):
            server.application_prepare({"operation": "publish"})
        with self.assertRaises(ValueError):
            server.application_prepare({"operation": "duplicate", "draft_id": self.legacy["id"]})

    def test_update_dirty_refused_no_reset_or_merge(self):
        draft = self.create()
        root = Path(draft["worktree_path"])
        (root/"screen.html").write_text("Unfinished")
        plan = apps.update_plan(self.home, draft["id"], "owner")
        self.assertTrue(plan["conflicts"])
        before = studio.snapshot(root)
        with self.assertRaises(ValueError):
            apps.update_from_live(self.home, draft["id"], "owner", plan["fingerprint"], plan["confirmation"])
        self.assertEqual(before, studio.snapshot(root))

    def test_update_live_checkpoint_reopens_saves_undoes_and_retains_recovery(self):
        import editor
        draft = self.create()
        root = Path(draft["worktree_path"])
        drafts.save(self.home, draft["id"], "owner", 0, ["screen.html"])
        (self.repo/"screen.html").write_text("New synthetic live source")
        studio.git(self.repo, "add", "screen.html")
        studio.git(self.repo, "commit", "-m", "Disposable new live fixture")
        newer = studio.git(self.repo, "rev-parse", "HEAD")
        studio.atomic(apps.live_path(self.home), {**self.receipt, "revision": newer})
        with patch.object(apps, "remote_main", return_value=newer):
            plan = apps.update_plan(self.home, draft["id"], "owner")
            self.assertEqual(plan["conflicts"], [])
            with self.assertRaises(ValueError):
                apps.update_from_live(self.home, draft["id"], "owner", plan["fingerprint"], "UPDATE wrong")
            result = apps.update_from_live(self.home, draft["id"], "owner", plan["fingerprint"], plan["confirmation"])
            self.assertEqual(studio.git(root, "rev-parse", result["recovery_branch"]), self.sha)
            self.assertEqual(studio.git(root, "rev-parse", "HEAD"), newer)
            self.assertEqual((root/"screen.html").read_text(), "New synthetic live source")
            server = draft_ui.DraftServer(self.home, draft["task_id"], "owner")
            self.addCleanup(server.server_close)
            reopened = server.state()["draft"]
            self.assertEqual(reopened["changed_since_checkpoint"], [])
            self.assertEqual(reopened["selected_revision"]["commit"], newer)
            recovered = drafts.recover_copy(self.home, draft["id"], "owner", reopened["revision"])
            self.assertEqual((Path(recovered["recovery_path"])/"screen.html").read_text(), "New synthetic live source")
            opened = editor.open_file(self.home, draft["id"], "owner", "app.py")
            editor.write(self.home, draft["id"], "owner", "app.py", opened["hash"], opened["revision"],
                         component="title", changes={"text": "After Live update", "properties": {}})
            saved = editor.open_file(self.home, draft["id"], "owner", "app.py")
            editor.write(self.home, draft["id"], "owner", "app.py", saved["hash"], saved["revision"],
                         restore={"id": saved["history"][-1]["id"], "side": "before"})
            self.assertEqual(editor.open_file(self.home, draft["id"], "owner", "app.py")["hash"], opened["hash"])
            with self.assertRaises(ValueError):
                apps.update_from_live(self.home, draft["id"], "owner", plan["fingerprint"], plan["confirmation"])

    def test_diverged_update_lists_overlapping_source_without_integrating(self):
        import releases
        draft = self.create()
        with patch.object(releases.GitObjects, "ancestor", return_value=False), \
                patch.object(releases.GitObjects, "tree", side_effect=[{"app.py":"base"}, {"app.py":"draft"}, {"app.py":"live"}]):
            plan = apps.update_plan(self.home, draft["id"], "owner")
        self.assertEqual(plan["conflicting_files"], ["app.py"])
        self.assertTrue(plan["conflicts"])

    def test_save_undo_source_restrictions_and_tests_still_scoped(self):
        import editor
        draft = self.create()
        original = editor.open_file(self.home, draft["id"], "owner", "app.py")
        editor.write(self.home, draft["id"], "owner", "app.py", original["hash"], original["revision"],
                     component="title", changes={"text": "V8 test", "properties": {}})
        saved = editor.open_file(self.home, draft["id"], "owner", "app.py")
        with self.assertRaises(RuntimeError):
            editor.write(self.home, draft["id"], "owner", "app.py", original["hash"], original["revision"],
                         component="title", changes={"text": "stale", "properties": {}})
        with self.assertRaises(ValueError):
            editor.open_file(self.home, draft["id"], "owner", ".env")
        result = apps.check(self.home, draft["id"], "owner")
        self.assertTrue(result["passed"])
        self.assertEqual(result["scope"], "static-only")
        editor.write(self.home, draft["id"], "owner", "app.py", saved["hash"], saved["revision"],
                     restore={"id": saved["history"][-1]["id"], "side": "before"})
        self.assertEqual(editor.open_file(self.home, draft["id"], "owner", "app.py")["hash"], original["hash"])


if __name__ == "__main__":
    unittest.main()
