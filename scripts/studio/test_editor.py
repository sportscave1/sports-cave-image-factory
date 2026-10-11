"""Editor filesystem, conflict and recovery tests using synthetic assigned worktrees."""
from pathlib import Path
import unittest
from unittest.mock import patch
import test_drafts
import drafts
import editor
import studio

FIXTURE='''
STYLE = """
.sc-login-wrap { padding: 1rem; }
.sc-login-kicker { color: #111111; }
.sc-login-title { color: #111111; font-size: 1rem; }
.sc-login-copy { color: #222222; }
@media(max-width:760px) { .sc-login-wrap { padding: 1rem; } }
"""
HTML = """
<div class="sc-login-kicker">Sports Cave</div>
<div class="sc-login-title">Welcome back</div>
<div class="sc-login-copy">Sign in.</div>
"""
def sample():
    submitted = st.form_submit_button("Sign in", type="primary")
'''

class EditorTests(unittest.TestCase):
    def setUp(self):
        test_drafts.DraftTests.setUp(self)
        (self.root/"app.py").write_text(FIXTURE)
        file=self.root/editor.CODE_FILES[0]
        file.parent.mkdir(parents=True)
        file.write_text("<h1>Example</h1>")
        self.draft=drafts.new(self.home,"task-a","owner-a","Editor fixture")
    def open(self,path="app.py",owner="owner-a"):
        return editor.open_file(self.home,self.draft["id"],owner,path)
    def write(self,opened,**kwargs):
        return editor.write(self.home,self.draft["id"],"owner-a",opened["path"],opened["hash"],opened["revision"],**kwargs)
    def test_visual_updates_real_source_and_checkpoint(self):
        before=self.open()
        result=self.write(before,component="title",changes={"text":"Draft heading","properties":{"color":"#123456","font-size":"2rem"}})
        self.assertTrue(result["changed"])
        source=(self.root/"app.py").read_text()
        self.assertIn("Draft heading",source);self.assertIn("#123456",source)
        self.assertEqual(self.open()["revision"],1)
        self.assertEqual(drafts.inspect(self.home,self.draft["id"],"owner-a")["changed_since_checkpoint"],[])
    def test_source_edits_are_limited_to_authorised_frontend(self):
        source=self.open(editor.CODE_FILES[0])
        self.write(source,source="<h1>Changed</h1>")
        self.assertEqual((self.root/editor.CODE_FILES[0]).read_text(),"<h1>Changed</h1>")
        with self.assertRaises(ValueError):
            self.write(self.open(),source="print('arbitrary Python')")
    def test_path_and_wrong_owner_denied(self):
        for path in ["../app.py",".env","sc_auth.py","scripts/studio/editor.py","C:/app.py"]:
            with self.assertRaises(ValueError):self.open(path)
        with self.assertRaises(RuntimeError):self.open(owner="wrong")
    def test_concurrent_source_edit_preserved(self):
        opened=self.open()
        (self.root/"app.py").write_text(FIXTURE+"\n# other editor\n")
        with self.assertRaises(RuntimeError):
            self.write(opened,component="title",changes={"text":"Mine"})
        self.assertIn("other editor",(self.root/"app.py").read_text())
    def test_stale_registry_revision_preserved(self):
        opened=self.open()
        drafts.save(self.home,self.draft["id"],"owner-a",0,["app.py"])
        with self.assertRaises(RuntimeError):self.write(opened,component="title",changes={"text":"Mine"})
        self.assertEqual((self.root/"app.py").read_text(),FIXTURE)
    def test_visual_injection_escaped_and_css_urls_refused(self):
        self.write(self.open(),component="title",changes={"text":'"""<script>alert(1)</script>'})
        text=(self.root/"app.py").read_text()
        self.assertIn("&lt;script&gt;",text)
        for value in ["url(https://example.invalid)","red; display:none","expression(alert(1))"]:
            with self.assertRaises(ValueError):
                self.write(self.open(),component="title",changes={"properties":{"background":value}})
    def test_unknown_mapping_refused(self):
        with self.assertRaises(ValueError):self.write(self.open(),component="arbitrary",changes={})
    def test_undo_and_restore_preserve_history(self):
        self.write(self.open(),component="title",changes={"text":"Edited"})
        saved=self.open(); revision=saved["history"][-1]["id"]
        self.write(saved,restore={"id":revision,"side":"before"})
        self.assertEqual((self.root/"app.py").read_text(),FIXTURE)
        self.write(self.open(),restore={"id":revision,"side":"after"})
        self.assertIn("Edited",(self.root/"app.py").read_text())
        self.assertEqual(len(self.open()["history"]),3)
    def test_interrupted_metadata_finish_recovers_once(self):
        opened=self.open()
        atomic=studio.atomic
        count=0
        def fail_second(*args):
            nonlocal count
            count+=1
            if count==2: raise OSError("simulated interruption")
            return atomic(*args)
        with patch.object(studio,"atomic",side_effect=fail_second):
            with self.assertRaises(OSError):
                self.write(opened,component="title",changes={"text":"Recovered"})
        self.assertEqual(self.open()["revision"],1)
        self.assertEqual(self.open()["revision"],1)
        self.assertEqual(len(self.open()["history"]),1)
    def test_diff_reads_real_selected_source(self):
        self.write(self.open(),component="title",changes={"text":"Changed heading"})
        diff=editor.view_changes(self.home,self.draft["id"],"owner-a","app.py")["diff"]
        self.assertIn("+",diff);self.assertIn("Changed heading",diff)
    def test_mobile_and_shared_button_properties(self):
        self.write(self.open(),component="mobile_panel",changes={"properties":{"padding":"2rem","text-align":"center"}})
        self.write(self.open(),component="submit",changes={"text":"Open draft","properties":{"background":"#123456","border-radius":"8px"}})
        opened=self.open()
        self.assertEqual(opened["visual"]["mobile_panel"]["properties"]["padding"],"2rem")
        self.assertEqual(opened["visual"]["submit"]["text"],"Open draft")
if __name__=="__main__":
    unittest.main()
