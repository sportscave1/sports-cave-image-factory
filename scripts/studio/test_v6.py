"""V6 boundary and static page discovery checks; disposable fixtures only."""
import ast,io,json,tarfile,time,unittest,hashlib
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
import studio,drafts,draft_ui,editor,page_catalog,preview_export
import test_drafts
from test_editor import FIXTURE

class V6Tests(unittest.TestCase):
    setUp=test_drafts.DraftTests.setUp
    def server(self):
        (self.root/'app.py').write_text(FIXTURE)
        self.draft=drafts.new(self.home,'task-a','owner-a','V6 fixture')
        server=draft_ui.DraftServer(self.home,'task-a','owner-a')
        self.addCleanup(server.server_close)
        return server
    def test_editor_grant_owner_scope_expiry_and_revocation(self):
        s=self.server();grant=s.workspace_grant(self.draft['id']);cap=grant['capability']
        call=lambda command:s.workspace_request({'capability':cap,'command':command})
        model=call({'action':'workspace-model'})
        self.assertEqual(model['draft']['id'],self.draft['id']);self.assertNotIn('worktree_path',model['task'])
        for cmd in [{'action':'execute'},{'action':'release-operation'},{'action':'editor-open','path':'.env'},{'action':'editor-open','path':'../app.py'},{'action':'editor-files','owner':'intruder'}]:
            with self.assertRaises((ValueError,RuntimeError)):call(cmd)
        s.workspace_grants[cap]['expires']=time.monotonic()-1
        with self.assertRaises(ValueError):call({'action':'editor-files'})
        grant=s.workspace_grant(self.draft['id']);s.action({'action':'workspace-revoke',**grant})
        with self.assertRaises(ValueError):s.workspace_request({**grant,'command':{'action':'editor-files'}})
        reg=studio.read(self.home/'.studio/registry.json');reg['drafts'][0]['owner']='other';studio.atomic(self.home/'.studio/registry.json',reg)
        with self.assertRaises(RuntimeError):s.workspace_grant(self.draft['id'])
    def test_static_pages_does_not_execute_application(self):
        (self.root/'os_accounts.py').write_text("raise RuntimeError('must not execute')\nPAGE_REGISTRY=({'key':'home','route':'Home','label':'Home','group':'Main'},)")
        rows=page_catalog.pages(self.root);self.assertEqual(rows[1]['key'],'home')
        (self.root/'os_accounts.py').write_text("PAGE_REGISTRY=__import__('os').system('never')")
        with self.assertRaises(ValueError):page_catalog.pages(self.root)
    def test_real_os_pages_and_exact_source_locations(self):
        root=Path(__file__).resolve().parents[2]
        rows=page_catalog.pages(root)
        self.assertGreater(len(rows),40);self.assertIn('developer_studio',{r['key'] for r in rows})
        self.assertNotIn('Collections',{r['label'] for r in rows})
        s=self.server();opened=editor.open_file(self.home,self.draft['id'],'owner-a')
        self.assertIn('sc-login-title',opened['locations']['title']['excerpt'])
        self.assertGreater(opened['locations']['title']['line'],0)
    def test_incremental_refresh_is_explicit_and_does_not_capture_other_files(self):
        self.server();previous={'commit':'a'*40,'files':[{'path':'other.py','sha256':'untouched'}]}
        (self.root/'other.py').write_text('unfinished')
        archive,manifest=preview_export.capture_delta(self.home,'task-a','owner-a',['app.py'],previous)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:self.assertEqual(tar.getnames(),['source/app.py'])
        self.assertIn({'path':'other.py','sha256':'untouched'},manifest['files'])
        for paths in [['.env'],['../app.py'],['other.py'],[]]:
            with self.assertRaises(ValueError):preview_export.capture_delta(self.home,'task-a','owner-a',paths,previous)
        with self.assertRaises(ValueError):preview_export.capture_delta(self.home,'task-a','owner-a',['app.py'],{**previous,'commit':'b'*40})
    def test_inspection_is_read_only_when_preview_source_is_stale(self):
        import preview_runtime
        self.server();runtime=preview_runtime.Preview(self.home,'task-a','owner-a');runtime.name='fixture'
        runtime.manifest={'files':[{'path':'app.py','sha256':hashlib.sha256(preview_export.source_bytes(self.root,'app.py')[0]).hexdigest()}]}
        config={'Config':{'Labels':{'sports-cave-studio.task':'task-a'}}}
        def response(*a,**k):return SimpleNamespace(returncode=0,stdout=json.dumps({'inspection':{'supported':True,'component':'title'}}).encode())
        with patch.object(preview_runtime.boundary,'docker',return_value=SimpleNamespace(stdout=json.dumps([config]))),patch.object(preview_runtime.subprocess,'run',side_effect=response):
            self.assertTrue(runtime.event({'action':'inspect','x':10,'y':10})['inspection']['supported'])
            (self.root/'app.py').write_text(FIXTURE+'\n# external unsaved change\n')
            self.assertFalse(runtime.event({'action':'inspect','x':10,'y':10})['inspection']['supported'])
            with self.assertRaises(ValueError):runtime.event({'action':'evaluate','script':'arbitrary()'})

    def test_preview_exports_ui_assets_but_not_local_backend(self):
        for name in preview_export.STUDIO_UI:self.assertTrue(preview_export.allowed(name))
        for name in ['scripts/studio/companion.py','scripts/studio/device_trust.py','scripts/studio/ui/pair.js']:
            self.assertFalse(preview_export.allowed(name))

if __name__=='__main__':unittest.main()
