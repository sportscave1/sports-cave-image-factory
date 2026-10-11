"""Offline tests: temporary JSON only; no application imports, network or repositories."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import studio

class RoutingTests(unittest.TestCase):
    def test_all_categories(self):
        examples = {
            "ADS": "Meta Ads posting popup", "EMAIL": "Email subscribers welcome series",
            "PRODUCTS": "Product Upload mockups Design Studio", "EDITIONS": "Edition Ops certificates numbering",
            "CORE": "Navigation shared UI site speed security", "INTEGRATIONS": "Shared APIs Analytics Reporting",
            "COMMERCE": "Orders Fulfilment returns", "GROWTH": "Social Media SEO Reviews",
            "RELEASE": "Approved integration and publishing"}
        for expected, text in examples.items():
            with self.subTest(expected=expected):
                self.assertEqual(studio.route(text), [expected])
    def test_ambiguous(self):
        self.assertEqual(studio.route("Email and Meta Ads"), ["ADS", "EMAIL"])
    def test_unknown(self):
        self.assertEqual(studio.route("make it better"), [])
    def test_override(self):
        self.assertEqual(studio.route("Email and Meta Ads", "CORE"), ["CORE"])
    def test_meta_review(self):
        self.assertEqual(studio.route("Meta Review"), ["ADS"])
    def test_word_boundaries(self):
        self.assertEqual(studio.route("address a problem"), [])

class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
    def test_atomic_roundtrip(self):
        path = self.home / "registry.json"
        studio.atomic(path, {"value": 1})
        studio.atomic(path, {"value": 2})
        self.assertEqual(json.loads(path.read_text()), {"value": 2})
        self.assertEqual(list(self.home.glob("*.tmp")), [])
    def test_atomic_failure_preserves_existing(self):
        path = self.home / "registry.json"
        studio.atomic(path, {"value": 1})
        with patch.object(studio.os, "replace", side_effect=OSError("simulated")):
            with self.assertRaises(OSError):
                studio.atomic(path, {"value": 2})
        self.assertEqual(json.loads(path.read_text()), {"value": 1})
    def test_lock_refuses_concurrent_writer(self):
        with studio.locked(self.home):
            with self.assertRaises(RuntimeError):
                with studio.locked(self.home):
                    self.fail("Second lock acquired")
        with studio.locked(self.home):
            pass
    def test_lock_exception_releases(self):
        with self.assertRaises(ValueError):
            with studio.locked(self.home):
                raise ValueError()
        self.assertFalse((self.home / ".studio/registry.lock").exists())
    def test_unknown_schema_refused(self):
        path = self.home / "r.json"
        studio.atomic(path, {"schema_version": 2})
        with self.assertRaises(RuntimeError):
            studio.read(path)
    def test_owner_mismatch(self):
        with self.assertRaises(RuntimeError):
            studio.task_by_id({"tasks": [{"id": "one", "owner": "alice"}]}, "one", "bob")
    def test_missing_task(self):
        with self.assertRaises(ValueError):
            studio.task_by_id({"tasks": []}, "missing")
    def test_ambiguous_allocates_nothing(self):
        result = studio.create_task(self.home, "Email and Meta Ads", None, "test-session")
        self.assertTrue(result["needs_confirmation"])
        self.assertFalse((self.home / ".studio").exists())
    def test_invalid_id_allocates_nothing(self):
        with self.assertRaises(ValueError):
            studio.create_task(self.home, "Meta Ads", None, "test-session", "../../other")
        self.assertFalse((self.home / ".studio").exists())
    def test_duplicate_id_preserves_registry(self):
        path = self.home / ".studio/registry.json"
        studio.atomic(path, {"schema_version": 1, "tasks": [{"id": "same", "name": "old"}]})
        before = path.read_bytes()
        with self.assertRaises(RuntimeError):
            studio.create_task(self.home, "Meta Ads", "ADS", "owner", "same")
        self.assertEqual(path.read_bytes(), before)
    def test_duplicate_name_preserves_registry(self):
        path = self.home / ".studio/registry.json"
        studio.atomic(path, {"schema_version": 1, "tasks": [{"id": "old", "name": "Meta Ads", "status": "In Progress"}]})
        before = path.read_bytes()
        with self.assertRaises(RuntimeError):
            studio.create_task(self.home, "meta ads", "ADS", "owner", "new-id")
        self.assertEqual(path.read_bytes(), before)
    def test_branch_name_not_immutable_base(self):
        with self.assertRaises(ValueError):
            studio.sha(self.home, "main")
    def test_workspace_identity_mismatch(self):
        with patch.object(studio, "common", return_value="wrong"):
            with self.assertRaises(RuntimeError):
                studio.identity({"common_dir": "expected"}, {"worktree_path": str(self.home), "branch": "task"})
    def test_clean_does_not_mean_completed(self):
        task = {"id": "task", "owner": "owner", "status": "In Progress",
                "worktree_path": str(self.home), "branch": "task", "verification": None,
                "integration_readiness": False}
        path = self.home / ".studio/registry.json"
        studio.atomic(path, {"schema_version": 1, "tasks": [task]})
        with patch.object(studio, "identity", return_value=self.home), patch.object(
                studio, "snapshot", return_value={"commit": "a"*40, "files_hash": "x", "status": ""}):
            result = studio.list_tasks(self.home)[0]
        self.assertEqual(result["status"], "In Progress")
        self.assertFalse(result["integration_readiness"])
        self.assertTrue(result["occupied"])
    def test_review_requires_tests(self):
        path = self.home / ".studio/registry.json"
        studio.atomic(path, {"schema_version": 1, "tasks": [{"id": "task", "owner": "owner", "last_verified_test": None}]})
        with patch.object(studio, "identity", return_value=self.home), patch.object(
                studio, "snapshot", return_value={"commit": "a"*40, "files_hash": "x", "status": ""}):
            with self.assertRaises(RuntimeError):
                studio.update_task(self.home, "task", "owner", "status", "Ready for Review")
    def test_dirty_or_changed_revision_rejects_review(self):
        original = {"commit": "a"*40, "files_hash": "x", "status": ""}
        task = {"id": "task", "owner": "owner", "last_verified_test": {"passed": True, "snapshot": original},
                "verification": {"passed": True, "snapshot": original}}
        for change in [{"commit": "b"*40}, {"files_hash": "y"}, {"status": " M file"}]:
            current = {**original, **change}
            path = self.home / ".studio/registry.json"
            studio.atomic(path, {"schema_version": 1, "tasks": [task]})
            with patch.object(studio, "identity", return_value=self.home), patch.object(
                    studio, "snapshot", return_value=current):
                with self.assertRaises(RuntimeError):
                    studio.update_task(self.home, "task", "owner", "status", "Ready for Review")
    def test_secret_patterns(self):
        self.assertTrue(studio.secret_findings("ghp_" + "a"*36))
        self.assertFalse(studio.secret_findings("api_key = os.environ.get('TOKEN')"))
    def test_preview_denied(self):
        with self.assertRaises(RuntimeError):
            studio.main(["preview"])

if __name__ == "__main__":
    unittest.main(verbosity=2)
