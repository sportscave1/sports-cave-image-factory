import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
from desktop_recorder.coordinator import Coordinator
from desktop_recorder.session_protocol import page, wire, verify_package, Invalid
from test_phase2 import command
import test_recovery_ui as recovery


class SessionProtocolTests(unittest.TestCase):
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
