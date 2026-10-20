import json
from unittest import TestCase
from unittest.mock import patch

import test_phase2 as phase2
from desktop_recorder.playback import Playback
from desktop_recorder.contract import CAPABILITIES, Invalid
from uuid import uuid4


command = phase2.command


class PlaybackTests(TestCase):
    setUp = phase2.Phase2Tests.setUp
    start = phase2.Phase2Tests.start
    event = phase2.Phase2Tests.event
    def saved(self):
        self.start()
        self.event()
        self.c.apply(command("stop"))
        self.c.apply(command("save", {"name": "Journal test"}))
        return self.c.last_saved

    def begin(self, p, saved, run=None):
        return p.begin(run or str(uuid4()), saved["id"], saved["revision"], CAPABILITIES.values(),
                       controls_visible=True, emergency_stop_ready=True)

    def test_dispatch_is_durable_and_restart_never_repeats(self):
        saved = self.saved()
        p = Playback(self.c.repository)
        run = str(uuid4())
        self.begin(p, saved, run)
        before = self.c.repository.get(saved["id"])
        p.dispatch(0)
        disk = json.loads((p.root / (run + ".json")).read_text())
        self.assertEqual(disk["state"], "uncertain")
        restarted = Playback(self.c.repository)
        self.assertEqual(restarted.recover()[0]["pending"], 0)
        with self.assertRaisesRegex(Invalid, "will not run again"):
            self.begin(restarted, saved, run)
        with self.assertRaisesRegex(Invalid, "uncertain previous action"):
            self.begin(restarted, saved)
        self.assertEqual(before, self.c.repository.get(saved["id"]))

    def test_failed_journal_write_prevents_dispatch_and_retry(self):
        p = Playback(self.c.repository)
        self.begin(p, self.saved())
        with patch.object(self.c.repository, "atomic", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                p.dispatch(0)
        with self.assertRaises(Invalid):
            p.dispatch(0)

    def test_shutdown_preserves_completed_run_and_journal_bytes(self):
        p = Playback(self.c.repository)
        self.begin(p, self.saved())
        p.dispatch(0)
        p.acknowledge(0, verified=True)
        path = p.root / (p.run["id"] + ".json")
        before = path.read_bytes()
        self.assertEqual(p.run["state"], "completed")
        p.stop()
        self.assertEqual(path.read_bytes(), before)
        recovered = Playback(self.c.repository).recover()
        self.assertEqual(recovered[0]["state"], "completed")

    def test_stop_preserves_uncertainty_and_late_verified_result(self):
        p = Playback(self.c.repository)
        self.begin(p, self.saved())
        p.dispatch(0)
        p.stop()
        self.assertEqual(p.run["state"], "uncertain")
        p.acknowledge(0, verified=True)
        self.assertEqual(p.run["state"], "stopped")
        self.assertEqual(p.run["next_step"], 1)
        with self.assertRaises(Invalid):
            p.dispatch(0)

    def test_revision_and_safety_controls_gate_start(self):
        p = Playback(self.c.repository)
        saved = self.saved()
        with self.assertRaisesRegex(Invalid, "revision"):
            self.begin(p, {**saved, "revision": "0" * 64})
        with self.assertRaises(Invalid):
            p.begin(str(uuid4()), saved["id"], saved["revision"], CAPABILITIES.values(),
                    controls_visible=True, emergency_stop_ready=False)
        self.assertIsNone(p.run)

    def test_late_cancellation_result_preserves_manual_stop_reason(self):
        p = Playback(self.c.repository)
        self.begin(p, self.saved())
        p.dispatch(0)
        reason = "Manual input stopped playback. Check any unconfirmed action."
        p.stop(reason=reason)
        self.assertEqual(p.run["state"], "uncertain")
        p.acknowledge(0, verified=False, message="Playback stopped.", no_effect=True)
        recovered = Playback(self.c.repository).recover()[0]
        self.assertEqual(recovered["message"], reason)
        self.assertEqual(recovered["state"], "stopped")
        self.assertIsNone(recovered["pending"])

    def test_unverified_invoke_cannot_continue_or_resume(self):
        p = Playback(self.c.repository)
        self.begin(p, self.saved())
        p.dispatch(0)
        p.acknowledge(0, verified=False, message="Check actual result")
        with self.assertRaises(Invalid):
            p.resume()
        self.assertEqual(p.run["state"], "uncertain")
        with self.assertRaises(Invalid):
            p.acknowledge(0, verified=True)

    def test_native_handshake_journals_before_execute(self):
        self.start()
        a = phase2.action()
        a.update(version=2, requires=["uia.invoke.v2"], target={**a["target"], "scope":[]})
        self.event(a)
        self.c.apply(command("stop"))
        self.c.apply(command("save", {"name":"Scoped"}))
        saved = self.c.last_saved
        state = self.c.apply(command("play", {"id": saved["id"], "revision": saved["revision"]}))
        self.assertEqual(state["instruction"]["kind"], "arm")
        self.assertIsNone(self.c.playback.run)
        state = self.c.apply(command("play_ready"))
        self.assertEqual(state["instruction"]["kind"], "execute")
        self.assertEqual(state["run"]["state"], "uncertain")
        with self.assertRaises(Invalid):
            self.c.apply(command("record", {"window": self.window}))

    def test_resume_disk_failure_keeps_capture_suspended(self):
        self.start()
        self.c.apply(command("pause"))
        with patch.object(self.c.repository, "atomic", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.c.apply(command("resume"))
        self.assertEqual(self.c.recording.state, "interrupted")

    def test_no_effect_failure_stops_without_automatic_retry(self):
        saved = self.saved()
        p = self.c.playback
        self.begin(p, saved)
        p.dispatch(0)
        self.c.apply(command("play_result", {"step": 0, "verified": False,
                     "no_effect": True, "message": "Focus timed out"}))
        self.assertEqual(p.run["state"], "stopped")
        self.assertIsNone(p.run["pending"])
        self.assertEqual(self.c.state()["state"], "idle")
        self.assertEqual(self.c.state()["instruction"]["kind"], "disarm")
        with self.assertRaises(Invalid):
            p.dispatch(0)
        self.begin(p, saved)  # Only a new explicit Play may start again.

    def test_uncertain_result_removes_playing_controls_but_blocks_retry(self):
        saved = self.saved()
        p = self.c.playback
        self.begin(p, saved)
        p.dispatch(0)
        self.c.apply(command("play_result", {"step": 0, "verified": False,
                     "message": "Provider result unknown"}))
        self.assertEqual(self.c.state()["state"], "idle")
        self.assertEqual(p.run["state"], "uncertain")
        with self.assertRaises(Invalid):
            self.begin(p, saved)

    def test_recovery_only_reconciles_returned_focus_failure(self):
        self.start()
        a = phase2.action()
        a.update(kind="focus_window", requires=["windows.focus.v1"])
        a.pop("value", None)
        self.event(a)
        self.c.apply(command("stop"))
        self.c.apply(command("save", {"name": "Focus recovery"}))
        saved = self.c.last_saved
        p = self.c.playback
        self.begin(p, saved)
        p.dispatch(0)
        p.acknowledge(0, verified=False, message="Window focus changed")
        recovered = Playback(self.c.repository).recover()[0]
        self.assertEqual(recovered["state"], "stopped")
        self.assertIn("focus-only", recovered["reconciliation"])
        self.assertEqual(self.c.repository.revision(self.c.repository.get(saved["id"])), saved["revision"])

    def test_operator_reconciliation_never_marks_run_completed(self):
        saved = self.saved()
        p = self.c.playback
        self.begin(p, saved)
        run_id = p.run["id"]
        p.dispatch(0)
        with self.assertRaises(Invalid):
            p.reconcile_observed_result(run_id, saved["revision"], 0, "Observed result")
        p.acknowledge(0, verified=False)
        with self.assertRaises(Invalid):
            p.reconcile_observed_result(run_id, "0" * 64, 0, "Observed result")
        reconciled = p.reconcile_observed_result(run_id, saved["revision"], 0, "User observed the expected field value")
        self.assertEqual(reconciled["state"], "stopped")
        self.assertEqual(reconciled["next_step"], 0)
        self.assertIn("not counted as completed", reconciled["reconciliation"]["disposition"])
        self.assertEqual(self.c.repository.revision(self.c.repository.get(saved["id"])), saved["revision"])
        self.begin(p, saved)
