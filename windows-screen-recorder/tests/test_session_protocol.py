import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
from desktop_recorder.coordinator import Coordinator
from desktop_recorder.session_protocol import page, wire, verify_package, verify_adapter, Invalid
from test_phase2 import command
import test_recovery_ui as recovery


class AdapterCompatibilityTests(unittest.TestCase):
    def test_retained_and_prepared_adapters_and_rejection_boundaries(self):
        with tempfile.TemporaryDirectory() as root:
            manifest = Path(root) / 'manifest.json'
            manifest.write_text(json.dumps({'version': '0.3.4'}))
            verify_adapter(manifest)
            scripts = ['prepared-context.js', 'browser-identity.js']
            value = {'version': '0.3.5', 'content_scripts': [{
                'matches': ['https://sports-cave-image-factory.onrender.com/*'], 'js': scripts}]}
            manifest.write_text(json.dumps(value))
            with self.assertRaises(Invalid):
                verify_adapter(manifest)
            manifest.with_name('prepared-context.js').write_text('// isolated fixture')
            verify_adapter(manifest)
            scripts.reverse()
            manifest.write_text(json.dumps(value))
            with self.assertRaises(Invalid):
                verify_adapter(manifest)
            for version in ['0.3.3', '0.3.6', '1.0.0', None]:
                manifest.write_text(json.dumps({'version': version}))
                with self.subTest(version=version), self.assertRaises(Invalid):
                    verify_adapter(manifest)


class LibraryReceiptTests(unittest.IsolatedAsyncioTestCase):
    async def test_reconnect_replaces_only_stale_generic_disconnect_notice(self):
        import asyncio
        from desktop_recorder.helper import DesktopRunner
        from desktop_recorder.session_protocol import identity
        generic = "Native toolbar disconnected. Review the preserved recording or run before continuing."
        specific = "Native connection interrupted: OSError. Review preserved state; no command will be repeated."
        for message, compatible, draft_problem in [(generic, True, ""), (specific, True, ""),
                                                   (generic, False, ""), (generic, True, "Review the interrupted draft.")]:
            with self.subTest(message=message, compatible=compatible, draft=draft_problem), tempfile.TemporaryDirectory() as root:
                runner = DesktopRunner.__new__(DesktopRunner)
                runner.desktop = Coordinator(Path(root))
                runner.desktop.message = message
                runner.desktop.recording.problem = draft_problem
                runner.native_ready = asyncio.get_running_loop().create_future()
                runner.capture_waiters = {}
                runner.control_trace = Mock()
                runner.publish_native = AsyncMock()
                payload = dict(kind="toolbar_ready", protocol=2, build=identity()["build"] if compatible else "wrong-build")
                cmd = command("diagnostic", payload)
                await runner.apply_native(cmd)
                published = runner.publish_native.call_args.args[0]
                self.assertEqual(published["ack"], cmd["id"])
                if not compatible:
                    self.assertIn("Incompatible toolbar build", str(runner.native_ready.exception()))
                    self.assertEqual(runner.desktop.message, generic)
                elif message == generic:
                    self.assertIn("reconnected", runner.desktop.message)
                    self.assertEqual(published["message"], draft_problem or runner.desktop.message)
                else:
                    self.assertEqual(published["message"], specific)
                self.assertIsNone(runner.desktop.playback.run)
                self.assertIsNone(runner.desktop.pending_play)

    async def test_rename_receipt_does_not_embed_entire_large_library(self):
        from desktop_recorder.helper import DesktopRunner
        from types import SimpleNamespace
        rows = [dict(id=str(i), name='錄製' * 100) for i in range(1000)]
        runner = DesktopRunner.__new__(DesktopRunner)
        runner.desktop = SimpleNamespace(repository=SimpleNamespace(manage=Mock(return_value={'id':'1'})),
                                         library_offset=0)
        runner.catalogue = SimpleNamespace(summaries=lambda: rows)
        runner.busy = lambda: False
        runner.recording = False
        runner.publish_native = AsyncMock()
        result = await runner.desktop_command('rename', {'id':'1', 'name':'Updated'}, 'isolated-command')
        self.assertLessEqual(len(result['tasks']), 20)
        self.assertIsNotNone(result['library_page']['next'])
        self.assertLess(len(json.dumps(result)), 128000)


class SessionProtocolTests(unittest.TestCase):
    def test_native_recent_task_outside_page_stays_available_and_bounded(self):
        from test_foundation import action
        with tempfile.TemporaryDirectory() as root:
            c = Coordinator(Path(root))
            tasks = {str(i): dict(id=str(i), name='Saved task ' + str(i),
                                 actions=[action()] * 30) for i in range(45)}
            c.preview_task_id = '44'
            with patch.object(c.repository, 'visible', return_value=[(Path(i+'.json'), {}) for i in tasks]), \
                 patch.object(c.repository, 'get', side_effect=tasks.__getitem__), \
                 patch.object(c.repository, 'display_name', side_effect=lambda task: task['name']), \
                 patch.object(c.repository, 'revision', return_value='immutable'):
                state = c.state()
            self.assertEqual(len(state['tasks']), 20)
            self.assertNotIn('44', [row['id'] for row in state['tasks']])
            self.assertEqual(state['selected_task']['id'], '44')
            self.assertEqual(len(state['selected_task']['action_log']), 13)
            self.assertLess(len(wire(state)), 65536)

    def test_pending_task_outside_library_page_still_projects_starting(self):
        from desktop_recorder.helper import DesktopRunner
        from types import SimpleNamespace
        rows = [dict(id=str(i), name='Saved task ' + str(i), steps=3) for i in range(45)]
        with tempfile.TemporaryDirectory() as root:
            runner = DesktopRunner.__new__(DesktopRunner)
            runner.desktop = Coordinator(Path(root))
            runner.desktop.pending_play = dict(task_id='44')
            runner.catalogue = SimpleNamespace(summaries=lambda: rows)
            runner.last_engine = 'desktop'
            runner.native = None
            with patch('task_recorder.runner.Runner.state', return_value={'mode':'idle'}):
                state = runner.state()
            self.assertEqual(state['mode'], 'starting')
            self.assertEqual(state['active_task_id'], '44')
            self.assertEqual(state['active_task_name'], 'Saved task 44')
            self.assertEqual(state['total'], 3)
            self.assertEqual(len(state['tasks']), 20)
            self.assertEqual(state['library_page']['next'], 20)

    def test_injected_input_is_explicit_and_refused_for_installed_data(self):
        import os
        from desktop_recorder.helper import native_arguments
        from task_recorder.schema import Invalid as LaunchInvalid
        base=Path(os.environ['LOCALAPPDATA'])/'SportsCaveOS'
        self.assertEqual(native_arguments(base/'TaskRecorderV1'), ['--candidate'])
        with self.assertRaisesRegex(LaunchInvalid, 'isolated'):
            native_arguments(base/'TaskRecorderV1', True)
        self.assertEqual(native_arguments(base/'TaskRecorderPhase1-20261022', True),
                         ['--candidate','--accept-injected-test-input'])

    def test_normal_stop_draft_is_not_an_interrupted_connection(self):
        from desktop_recorder.helper import DesktopRunner
        from types import SimpleNamespace
        from test_foundation import action
        with tempfile.TemporaryDirectory() as root:
            runner = DesktopRunner.__new__(DesktopRunner)
            runner.desktop = Coordinator(Path(root))
            runner.catalogue = SimpleNamespace(summaries=lambda: [])
            runner.last_engine = 'desktop'
            runner.native = None
            runner.desktop.apply(command('record', {'window':action()['target']}))
            runner.desktop.apply(command('stop'))
            with patch('task_recorder.runner.Runner.state', return_value={'mode':'idle'}):
                state=runner.state()
            self.assertEqual(state['mode'], 'draft')
            self.assertFalse(state['recording'])
            self.assertEqual(state['active_task_id'], runner.desktop.recording.task['id'])

    def test_idle_desktop_does_not_inherit_legacy_stop_or_selection(self):
        from desktop_recorder.helper import DesktopRunner
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as root:
            runner = DesktopRunner.__new__(DesktopRunner)
            runner.desktop = Coordinator(Path(root))
            runner.desktop.preview_task_id = 'saved-desktop'
            runner.catalogue = SimpleNamespace(summaries=lambda: [])
            runner.last_engine = 'desktop'
            runner.native = None
            with patch('task_recorder.runner.Runner.state', return_value={
                'mode':'stopped','selected_id':'old-browser-task','active_task_id':None}):
                state = runner.state()
            self.assertEqual(state['mode'], 'idle')
            self.assertEqual(state['selected_id'], 'saved-desktop')

    def test_large_unicode_library_pages_fit_and_preserve_every_entry(self):
        rows = [dict(id=str(i), name="錄製" * 100) for i in range(1001)]
        offset, found = 0, []
        while True:
            result, cursor = page(rows, offset)
            self.assertLess(len(wire(dict(tasks=result))), 65536)
            found.extend(result)
            if cursor['next'] is None:
                break
            offset = cursor['next']
        self.assertEqual(found, rows)

    def test_mismatched_executable_refused_before_launch(self):
        with tempfile.TemporaryDirectory() as root:
            exe = Path(root) / 'DesktopRecorder.exe'
            exe.write_bytes(b'changed')
            exe.with_name('build-manifest.json').write_text(json.dumps({'executable_sha256':'wrong'}))
            with self.assertRaisesRegex(Invalid, 'differs'):
                verify_package(exe)

    def test_compatible_package_reports_actual_selected_executable(self):
        import hashlib
        with tempfile.TemporaryDirectory() as root:
            exe = Path(root) / 'DesktopRecorder.exe'
            exe.write_bytes(b'isolated candidate identity fixture')
            digest = hashlib.sha256(exe.read_bytes()).hexdigest()
            exe.with_name('build-manifest.json').write_text(json.dumps({'executable_sha256': digest}))
            result = verify_package(exe)
            self.assertEqual(result['native_sha256'], digest)
            self.assertEqual(result['adapter_protocol'], 1)

    def test_oversize_instruction_rejected(self):
        with self.assertRaisesRegex(Invalid, '64 KiB'):
            wire({'instruction': 'x' * 65536})

    def test_start_timeout_rejects_late_ready_and_duplicate_play_never_rearms(self):
        fixture = recovery.RecoveryTests()
        fixture.setUp()
        try:
            fixture.failed_run()
            c = fixture.c
            run = c.playback.run
            c.playback.reconcile_observed_result(run['id'], run['revision'], 0, 'Synthetic unit-test result inspected.')
            cmd = command('play', fixture.saved)
            c.apply(cmd)
            deadline = c.start_deadline
            self.assertTrue(c.expire_start(deadline))
            self.assertIsNone(c.pending_play)
            self.assertEqual(c.native_instruction['kind'], 'disarm')
            with self.assertRaisesRegex(Invalid, 'No pending Play'):
                c.apply(command('play_ready'))
            c.apply(cmd)
            self.assertIsNone(c.pending_play)
            self.assertNotEqual(c.playback.run['state'], 'completed')
        finally:
            fixture.doCleanups()

    def test_native_state_bounds_history_without_changing_journal(self):
        with tempfile.TemporaryDirectory() as root:
            c = Coordinator(Path(root))
            run = dict(state='stopped', results=[dict(step=i,verified=True) for i in range(500)])
            c.playback.run = run
            state = c.state()
            self.assertEqual(len(state['run']['results']), 12)
            self.assertEqual(len(run['results']), 500)
            self.assertEqual(state['runtime']['ipc'], 2)

    def test_disconnect_erases_executable_instruction_before_reopen(self):
        from desktop_recorder.helper import DesktopRunner
        with tempfile.TemporaryDirectory() as root:
            runner = DesktopRunner.__new__(DesktopRunner)
            runner.desktop = Coordinator(Path(root))
            runner.desktop.instruct('execute', step=0, action={'sentinel':True})
            runner.native_ready = None
            runner.capture_waiters = {}
            runner.notify_state = lambda: None
            runner.native_disconnected()
            self.assertEqual(runner.desktop.native_instruction['kind'], 'disarm')
            self.assertIsNone(runner.desktop.pending_play)
