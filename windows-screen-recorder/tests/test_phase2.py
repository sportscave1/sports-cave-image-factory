"""Focused integration checks; native acceptance is recorded separately."""
import json
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4
from unittest.mock import patch

from test_foundation import action, atomic, Store, Recording, Repository, Invalid
from desktop_recorder.coordinator import Coordinator
from desktop_recorder.catalogue import Catalogue


def command(kind, payload=None, key=None):
    return dict(v=1, id=key or str(uuid4()), kind=kind, payload=payload or {})


class Phase2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.c = Coordinator(Path(self.tmp.name))
        self.window = action()["target"]

    def start(self):
        return self.c.apply(command("record", {"window": self.window}))

    def event(self, a=None, generation=None):
        return self.c.apply(command("event", dict(
            action=a or action(), privacy="safe",
            generation=self.c.recording.generation if generation is None else generation)))

    def test_duplicate_record_and_changed_receipt_rejected(self):
        cmd = command("record", {"window": self.window})
        self.c.apply(cmd)
        task_id = self.c.recording.task["id"]
        self.c.apply(cmd)
        self.assertEqual(task_id, self.c.recording.task["id"])
        cmd["payload"]["window"] = {**self.window, "name": "changed"}
        with self.assertRaises(Invalid):
            self.c.apply(cmd)

    def test_final_text_flush_stop_save_and_reload(self):
        self.start()
        self.event()
        self.event({**action(), "kind": "set_text", "requires": ["uia.value.v1"],
                    "value": "", "observed_ms": 123})
        stop = command("stop")
        self.c.apply(stop)
        self.c.apply(stop)
        save = command("save", {"name": "Durable example"})
        self.c.apply(save)
        saved = dict(self.c.last_saved)
        self.c.apply(save)
        self.assertEqual(saved, self.c.last_saved)
        restarted = Coordinator(Path(self.tmp.name))
        self.assertEqual(restarted.recording.state, "idle")
        task = restarted.repository.get(saved["id"])
        self.assertEqual([a["kind"] for a in task["actions"]], ["invoke", "set_text"])
        self.assertEqual(task["starting_context"]["window"], self.window)

    def test_pause_late_event_generation_barrier(self):
        self.start()
        generation = self.c.recording.generation
        self.event()
        self.c.apply(command("pause"))
        self.event(generation=generation)
        self.c.apply(command("resume"))
        self.event(generation=generation)
        self.event()
        self.assertEqual(len(self.c.recording.task["actions"]), 2)

    def test_interrupted_recovery_never_resumes_and_requires_review(self):
        self.start()
        self.event()
        recovered = Coordinator(Path(self.tmp.name))
        self.assertEqual(recovered.recording.state, "interrupted")
        with self.assertRaises(Invalid):
            recovered.apply(command("save", {"name": "Unreviewed"}))
        recovered.apply(command("review"))
        recovered.apply(command("save", {"name": "Reviewed partial"}))
        self.assertEqual(len(recovered.repository.get(recovered.last_saved["id"])["actions"]), 1)

    def test_save_failure_retains_draft_and_same_id_retry(self):
        self.start()
        self.event()
        self.c.apply(command("stop"))
        original = self.c.recording.task["id"]
        with patch.object(self.c.repository, "atomic", side_effect=OSError("test disk full")):
            with self.assertRaises(OSError):
                self.c.apply(command("save", {"name": "Retry"}))
        self.assertIsNotNone(self.c.repository.load_draft())
        self.c.apply(command("save", {"name": "Retry"}))
        self.assertEqual(self.c.last_saved["id"], original)

    def test_stop_after_provider_interrupt_keeps_review_reachable(self):
        self.start()
        self.event()
        original = self.c.recording.task["id"]
        self.c.apply(command("interrupt", {"reason": "Accessibility provider timed out"}))
        stop = command("stop")
        self.c.apply(stop)
        self.c.apply(stop)
        self.assertEqual(self.c.recording.state, "interrupted")
        self.assertEqual(self.c.repository.load_draft()["state"], "interrupted")
        self.assertIsNone(self.c.playback.run)
        with self.assertRaisesRegex(Invalid, "Stop before Save"):
            self.c.apply(command("save", {"name": "Unreviewed"}))
        self.c.apply(command("review"))
        self.c.apply(command("save", {"name": "Reviewed incomplete draft"}))
        self.assertEqual(self.c.last_saved["id"], original)
        self.assertEqual(len(self.c.repository.get(original)["actions"]), 1)
        self.assertIsNone(self.c.playback.run)

    def test_catalogue_cache_legacy_passthrough_and_play_guard(self):
        self.start()
        self.event()
        self.c.apply(command("stop"))
        self.c.apply(command("save", {"name": "Desktop"}))
        task_id = self.c.last_saved["id"]
        legacy_row = dict(id=str(uuid4()), name="Legacy", revision="old", steps=2)
        class Legacy:
            def list(self):
                return [legacy_row]
        catalogue = Catalogue(self.c.repository, Legacy())
        rows = catalogue.summaries()
        self.assertIn(legacy_row, rows)
        with patch.object(self.c.repository, "get", side_effect=AssertionError("cache miss")):
            self.assertEqual(rows, catalogue.summaries())
        with self.assertRaisesRegex(Invalid, "Update the helper"):
            catalogue.inspect(task_id, 5)
        self.assertFalse(catalogue.inspect(task_id, {"format":"sports-cave.desktop", "version":1})["playback_available"])
        with self.assertRaisesRegex(Invalid, "native executor"):
            catalogue.guard_command("play", task_id)
        catalogue.guard_command("play", legacy_row["id"])

    def test_unknown_ipc_types_and_missing_selected_window(self):
        for cmd in ([], {"v": 1}, {**command("stop"), "v": True},
                    {**command("stop"), "payload": []}):
            with self.assertRaises(Invalid):
                self.c.apply(cmd)
        with self.assertRaisesRegex(Invalid, "Choose a starting window"):
            self.c.apply(command("record"))
        self.assertEqual(self.c.recording.state, "idle")

    def test_desktop_transitions_survive_pause_save_and_restart_in_order(self):
        self.c.apply(command("record", {"mode": "desktop_session"}))
        window = {**self.window, "control_type": "Window", "scope": [], "name": "Test.txt - Notepad"}
        def transition(value):
            return dict(version=2, kind="window_state", requires=["windows.state.v2"],
                        target=window, value=value, timeout_ms=2000)
        self.event(transition("minimized"))
        self.c.apply(command("pause"))
        self.event(transition("maximized"))
        self.c.apply(command("resume"))
        self.event(transition("normal"))
        self.c.apply(command("stop"))
        self.c.apply(command("save", {"name": "Desktop transition check"}))
        restarted = Coordinator(Path(self.tmp.name))
        task = restarted.repository.get(self.c.last_saved["id"])
        self.assertEqual(task["starting_context"], {"mode": "desktop_session", "binding": None})
        self.assertEqual([a["value"] for a in task["actions"]], ["minimized", "normal"])

    def test_window_transition_rejects_old_mode_and_invalid_states(self):
        from desktop_recorder.contract import validate
        self.start()
        transition = dict(version=2, kind="window_state", requires=["windows.state.v2"],
                          target={**self.window, "control_type": "Window", "scope": []},
                          value="minimized", timeout_ms=2000)
        task = {**self.c.recording.task, "actions": [transition]}
        with self.assertRaisesRegex(Invalid, "desktop session"):
            validate(task)
        task["starting_context"] = {"mode": "desktop_session", "binding": None}
        for value in (None, [], {}, True, "close", ""):
            with self.subTest(value=value), self.assertRaises(Invalid):
                validate({**task, "actions": [{**transition, "value": value}]})


if __name__ == "__main__":
    unittest.main()
