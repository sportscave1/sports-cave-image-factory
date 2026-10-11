"""Focused offline draft tests; no app imports, services or Git repository creation."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import drafts
import studio

class DraftTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.root = self.home / "task"
        self.root.mkdir()
        self.source = self.root / "screen.html"
        self.source.write_text("<h1>Original</h1>", encoding="utf-8")
        self.task = {"id": "task-a", "owner": "owner-a", "branch": "codex/task/a",
            "category": "CORE", "worktree_path": str(self.root), "base_commit": "a"*40}
        studio.atomic(self.home/".studio/registry.json", {"schema_version": 1,
            "original_repo": str(self.home/"original"), "tasks": [self.task], "marker": "preserved"})
        self.identity = patch.object(studio, "identity", side_effect=lambda r,t: Path(t["worktree_path"]))
        self.git = patch.object(studio, "git", return_value="a"*40)
        self.identity.start(); self.git.start()
        self.addCleanup(self.identity.stop); self.addCleanup(self.git.stop)
    def create(self):
        return drafts.new(self.home, "task-a", "owner-a", "Navigation draft")
    def save(self, draft, revision=0, files=None):
        return drafts.save(self.home, draft["id"], "owner-a", revision, files or ["screen.html"])
    def test_save_open_preserves_identity(self):
        draft = self.create()
        saved = self.save(draft)
        opened = drafts.inspect(self.home, draft["id"], "owner-a")
        self.assertEqual(opened["revision"], 1)
        self.assertEqual(opened["changed_since_checkpoint"], [])
        self.assertEqual(opened["task_id"], "task-a")
        self.assertEqual(opened["current_commit"], "a"*40)
        self.assertFalse(saved["preview"]["enabled"])
        self.assertFalse(saved["release_eligible"])
        self.assertEqual(studio.read(self.home/".studio/registry.json")["marker"], "preserved")
    def test_open_detects_changed_source_without_overwriting(self):
        draft = self.save(self.create())
        self.source.write_text("Changed")
        opened = drafts.inspect(self.home, draft["id"], "owner-a")
        self.assertEqual(opened["changed_since_checkpoint"], ["screen.html"])
        self.assertEqual(self.source.read_text(), "Changed")
    def test_recover_old_revision_into_new_folder(self):
        draft = self.save(self.create())
        self.source.write_text("New")
        self.save(draft, 1)
        recovered = drafts.recover_copy(self.home, draft["id"], "owner-a", 1)
        self.assertEqual((Path(recovered["recovery_path"])/"screen.html").read_text(), "<h1>Original</h1>")
        self.assertEqual(self.source.read_text(), "New")
        again = drafts.recover_copy(self.home, draft["id"], "owner-a", 1)
        self.assertNotEqual(again["recovery_path"], recovered["recovery_path"])
    def test_wrong_owner_rejected(self):
        draft = self.create()
        for action in [lambda: drafts.new(self.home,"task-a","intruder","No"),
                       lambda: drafts.save(self.home,draft["id"],"intruder",0,["screen.html"]),
                       lambda: drafts.inspect(self.home,draft["id"],"intruder"),
                       lambda: drafts.recover_copy(self.home,draft["id"],"intruder",1)]:
            with self.assertRaises(RuntimeError):
                action()
    def test_one_draft_per_task(self):
        self.create()
        with self.assertRaises(RuntimeError):
            drafts.new(self.home,"task-a","owner-a","Another")
    def test_revision_conflict_preserves_registry(self):
        draft = self.save(self.create())
        before = (self.home/".studio/registry.json").read_bytes()
        with self.assertRaises(RuntimeError):
            self.save(draft,0)
        self.assertEqual(before,(self.home/".studio/registry.json").read_bytes())
    def test_path_restrictions(self):
        for name in ["../outside.py","/outside.py","C:/outside.py","dir\\file.py",
                     ".env",".git/config","secrets.py","dir/credentials.html","tmp/a.py",
                     "file.html:stream","a/../file.html","a//file.html","file.txt","file.html."]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                drafts.safe_file(self.root,name)
    def test_hardlink_rejected(self):
        os.link(self.source,self.root/"linked.html")
        with self.assertRaises(ValueError):
            drafts.safe_file(self.root,"linked.html")
    def test_reparse_rejected(self):
        class Attr:
            st_mode = 0
            st_file_attributes = 0x400
        with patch.object(Path,"lstat",return_value=Attr()):
            with self.assertRaises(ValueError):
                drafts.plain_path(self.source)
    def test_sensitive_content_rejected(self):
        self.source.write_text("ghp_"+"a"*36)
        with self.assertRaises(ValueError):
            self.save(self.create())
    def test_binary_and_oversized_rejected(self):
        draft=self.create()
        for data in [b"\0binary",b"a"*(drafts.MAX_FILE+1)]:
            self.source.write_bytes(data)
            with self.assertRaises(ValueError):
                self.save(draft)
    def test_blob_path_tampering_rejected(self):
        with self.assertRaises(ValueError):
            drafts.blob_path(self.home,"../../outside")
    def test_recovery_requires_revision(self):
        draft=self.create()
        with self.assertRaises(ValueError):
            drafts.recover_copy(self.home,draft["id"],"owner-a",None)
    def test_corruption_rejected(self):
        draft = self.save(self.create())
        meta = draft["revisions"][0]["files"][0]
        (self.home/".studio/drafts/blobs"/meta["sha256"]).write_bytes(b"broken")
        with self.assertRaises(RuntimeError):
            drafts.inspect(self.home,draft["id"],"owner-a")
    def test_save_captures_deletion(self):
        draft=self.save(self.create())
        self.source.unlink()
        draft=self.save(draft,1)
        self.assertTrue(draft["revisions"][-1]["files"][0]["deleted"])
        self.assertEqual(drafts.inspect(self.home,draft["id"],"owner-a")["changed_since_checkpoint"],[])
    def test_concurrent_edit_is_rejected(self):
        draft=self.create()
        real=drafts.read_source
        calls=[]
        def racing(*args,**kwargs):
            result=real(*args,**kwargs)
            calls.append(1)
            if len(calls)==1:self.source.write_text("Concurrent edit")
            return result
        with patch.object(drafts,"read_source",side_effect=racing):
            with self.assertRaises(RuntimeError):
                self.save(draft)
        self.assertEqual(drafts.inspect(self.home,draft["id"],"owner-a")["revision"],0)
    def test_original_checkout_rejected(self):
        file=self.home/".studio/registry.json"
        registry=studio.read(file);registry["original_repo"]=str(self.root);studio.atomic(file,registry)
        with self.assertRaises(ValueError):
            self.create()
    def test_listing_filters_owner(self):
        self.create()
        self.assertEqual(drafts.listing(self.home,"other"),[])
        self.assertEqual(len(drafts.listing(self.home,"owner-a")),1)
    def test_invalid_uuid(self):
        with self.assertRaises(ValueError):
            drafts.inspect(self.home,"../../original","owner-a")
    def test_preview_still_fails_closed(self):
        with self.assertRaises(RuntimeError):
            studio.main(["preview"])
    def test_registry_write_failure_preserves_checkpoint(self):
        draft=self.save(self.create())
        self.source.write_text("Second")
        before=(self.home/".studio/registry.json").read_bytes()
        with patch.object(studio,"atomic",side_effect=OSError("simulated")):
            with self.assertRaises(OSError):
                self.save(draft,1)
        self.assertEqual((self.home/".studio/registry.json").read_bytes(),before)
        self.assertEqual(drafts.inspect(self.home,draft["id"],"owner-a",1)["selected_revision"]["number"],1)

if __name__ == "__main__":
    unittest.main(verbosity=2)
