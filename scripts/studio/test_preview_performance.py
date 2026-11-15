"""Focused relay/silent-launch and immutable ownership regressions."""
import json
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import preview_boundary
import preview_runtime
import preview_relay
import studio


class PerformanceTests(unittest.TestCase):
    def test_windows_background_docker_keeps_capture_timeout_and_no_console(self):
        result=SimpleNamespace(returncode=0,stdout='{}')
        with patch.object(preview_boundary.subprocess,'run',return_value=result) as run:
            preview_boundary.docker('inspect','verified-id',timeout=7,context='desktop-linux')
        args=run.call_args
        self.assertEqual(args.args[0],['docker','--context','desktop-linux','inspect','verified-id'])
        self.assertEqual(args.kwargs['creationflags'],subprocess.CREATE_NO_WINDOW)
        self.assertTrue(args.kwargs['capture_output'])
        self.assertEqual(args.kwargs['timeout'],7)

    def test_pinned_id_replaces_name_without_global_context_switch(self):
        runtime=preview_runtime.Preview(None,'task','owner')
        runtime.name='owned-name';runtime.container_id='a'*64;runtime.docker_context='desktop-linux'
        with patch.object(preview_boundary,'docker') as docker:
            runtime._docker('exec',runtime.name,'python')
        docker.assert_called_once_with('exec','a'*64,'python',context='desktop-linux')

    def test_repeated_start_preserves_running_container_and_frame(self):
        runtime=preview_runtime.Preview(None,'task','owner')
        runtime.name='owned-name';runtime.last_frame={'image':'previous'}
        runtime.container_id='a'*64
        with patch.object(runtime,'_scope') as scope,patch.object(runtime,'event',return_value={'alive':True}) as event:
            self.assertEqual(runtime.start(),{'image':'previous'})
        scope.assert_called_once();event.assert_called_once_with({'action':'health'})

    def test_dead_runtime_cannot_return_cached_success(self):
        runtime=preview_runtime.Preview(None,'task','owner')
        runtime.name='owned-name';runtime.last_frame={'image':'previous'};runtime.container_id='a'*64
        with patch.object(runtime,'_scope'),patch.object(runtime,'event',return_value={'alive':False}):
            with self.assertRaises(RuntimeError):runtime.start()

    def test_oversized_relay_input_fails_before_write(self):
        relay=object.__new__(preview_relay.Relay)
        relay.process=Mock()
        with self.assertRaises(ValueError):relay.request({'text':'x'*12000})
        relay.process.stdin.write.assert_not_called()

    def test_lease_change_blocks_cached_frame(self):
        runtime=preview_runtime.Preview(None,'task','owner')
        runtime.name='owned-name';runtime.last_frame={'image':'previous'}
        with patch.object(runtime,'_scope',side_effect=RuntimeError('ownership changed')):
            with self.assertRaises(RuntimeError):runtime.start()

    def test_one_time_sanitisation_still_checks_changed_source(self):
        import preview_export
        from test_drafts import DraftTests
        fixture=DraftTests();fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        (fixture.root/'app.py').write_text('print("safe")')
        (fixture.root/'sc_auth.py').write_text('DEFAULT_APP_PASSWORD="synthetic-old-password"')
        original=preview_export.raw_source
        counts={}
        def changed(root,name):
            counts[name]=counts.get(name,0)+1
            value=original(root,name)
            return value+b'\n# concurrent source' if name=='app.py' and counts[name]>1 else value
        def git(repo,*args):return 'app.py\nsc_auth.py' if args==('ls-files',) else 'a'*40
        with patch.object(preview_export,'raw_source',side_effect=changed),patch.object(studio,'git',side_effect=git):
            with self.assertRaises(RuntimeError):preview_export.capture(fixture.home,'task-a','owner-a')

    def test_successful_save_refresh_is_preview_activity(self):
        import editor,draft_ui
        from test_v6 import V6Tests
        fixture=V6Tests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        server=fixture.server()
        opened=editor.open_file(fixture.home,fixture.draft['id'],'owner-a')
        server.preview_runtime=Mock();server.preview_runtime.name='synthetic-preview'
        server.preview_runtime.refresh_source.return_value={'image':'synthetic'}
        server.last_preview_activity=0
        with patch.object(draft_ui.time,'monotonic',return_value=100):
            server.action({'action':'editor-save','path':'app.py','expected_hash':opened['hash'],
                           'expected_revision':opened['revision'],'component':'title','changes':{'text':'Saved activity'}})
        self.assertEqual(server.last_preview_activity,100)


if __name__=='__main__':unittest.main()
