"""Contract tests use the reviewed package storage primitives and disposable data."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from uuid import uuid4

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from desktop_recorder.dependencies import load
load(BASE)
# Import definitions only; never construct a Store against existing task data.
from task_recorder.store import atomic, Store
from task_recorder.schema import validate_task
from desktop_recorder.contract import validate, route, Invalid, FORMAT
from desktop_recorder.integration import Repository, prepare_play, Cancellation, input_scope
from desktop_recorder.lifecycle import Recording


def action():
    return dict(version=1, kind="invoke", requires=["uia.invoke.v1"],
                target=dict(app="notepad", window_key="test-document",
                            control_type="Button", automation_id="test", name=""),
                timeout_ms=2000)


class FoundationTests(unittest.TestCase):
    def test_generation_result_contract_is_scoped_to_edge_invoke(self):
        self.start()
        a=action()
        a.update(version=2, requires=["uia.invoke.v2"])
        a["target"].update(app=r"C:\Apps\msedge.exe",name="Generate mockups",scope=[],
                           postcondition="sports-cave.product-generation.v1")
        self.assertTrue(self.accept(a))
        for changes in ({"postcondition":"arbitrary"},{"app":"other.exe"},{"name":"Other"},{"app":None}):
            invalid=copy.deepcopy(a);invalid["target"].update(changes)
            with self.assertRaises(Invalid):validate({**self.rec.task,"actions":[invalid]})
        invalid=copy.deepcopy(a);invalid.update(kind="wait_ready",requires=["uia.readiness.v2"])
        with self.assertRaises(Invalid):validate({**self.rec.task,"actions":[invalid]})

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Repository(self.tmp.name, atomic, Store.revision)
        self.now = 0.0
        self.rec = Recording(self.repo, lambda: self.now)

    def start(self):
        return self.rec.record({"mode": "prepared", "binding": None}, indicator_visible=True)

    def accept(self, a=None, g=None, **kwargs):
        return self.rec.accept(a or action(), generation=self.rec.generation if g is None else g,
                               privacy=kwargs.pop("privacy", "safe"), **kwargs)

    def saved(self):
        self.start()
        self.accept()
        self.rec.stop()
        return self.rec.save("Example")

    def test_pause_timer_and_flush_barrier(self):
        g = self.start()
        self.now = 2
        self.rec.pause(lambda: self.accept(g=g))
        self.now = 80
        self.assertEqual(self.rec.elapsed_ms, 2000)
        self.assertFalse(self.accept(g=g))
        self.rec.resume(indicator_visible=True)
        self.assertFalse(self.accept(g=g))
        self.now = 81
        self.rec.stop(lambda: self.accept())
        self.assertEqual(self.rec.elapsed_ms, 3000)
        self.assertEqual(len(self.rec.task["actions"]), 2)

    def test_no_capture_without_indicator_or_during_idle(self):
        self.assertFalse(self.accept())
        with self.assertRaises(Invalid):
            self.rec.record({"mode":"prepared","binding":None}, indicator_visible=False)
        self.assertEqual(self.rec.state, "idle")

    def test_secure_unknown_and_toolbar_never_persist(self):
        self.start()
        self.assertFalse(self.accept(toolbar=True))
        secret = {**action(), "kind": "set_text", "requires": ["uia.value.v1"], "value": "private-canary"}
        self.assertFalse(self.accept(secret, privacy="unknown"))
        self.assertEqual(self.rec.state, "interrupted")
        self.assertNotIn("private-canary", (self.repo.root / "draft.json").read_text())
        self.rec.stop()
        with self.assertRaises(Invalid):
            self.rec.save("Incomplete")

    def test_unsupported_and_overflow_are_visible(self):
        self.rec.capacity = 1
        self.start()
        self.accept()
        self.assertFalse(self.accept())
        self.assertIn("capacity", self.rec.problem)
        self.rec.discard()
        self.start()
        self.assertFalse(self.accept({**action(), "kind":"mouse_move"}))
        self.assertIn("Unsupported", self.rec.problem)

    def test_save_never_executes_and_is_immutable(self):
        saved = self.saved()
        path = self.repo.root / (saved["id"] + ".json")
        before = path.read_bytes()
        task = self.repo.get(saved["id"])
        prepared = prepare_play(task, {"uia.invoke.v1"}, explicit_play=True,
                                controls_visible=True, emergency_stop_ready=True)
        prepared["actions"].clear()
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(len(task["actions"]), 1)
        self.assertEqual(self.repo.save(task), saved)
        with self.assertRaises(Invalid):
            self.repo.save({**task, "name":"Changed"})
        self.assertIsNone(self.repo.load_draft())

    def test_play_requires_explicit_safety_and_capabilities(self):
        task = self.repo.get(self.saved()["id"])
        for key in ("explicit_play","controls_visible","emergency_stop_ready"):
            options = dict(explicit_play=True, controls_visible=True, emergency_stop_ready=True)
            options[key] = False
            with self.assertRaises(Invalid):
                prepare_play(task, {"uia.invoke.v1"}, **options)
        with self.assertRaises(Invalid):
            prepare_play(task, set(), explicit_play=True, controls_visible=True, emergency_stop_ready=True)

    def test_restart_retains_draft_without_resuming(self):
        self.start()
        self.accept()
        other = Recording(Repository(self.tmp.name, atomic, Store.revision))
        self.assertIsNotNone(other.recover())
        self.assertEqual(other.state, "interrupted")
        self.assertFalse(other.accept(action(), generation=other.generation, privacy="safe"))
        other.discard()
        self.assertIsNone(self.repo.load_draft())

    def test_browser_format_not_reinterpreted(self):
        old = {"version":1,"name":"Browser","inputs":[],"steps":[]}
        original = copy.deepcopy(old)
        self.assertEqual(route(old), "browser")
        self.assertEqual(validate_task(old), original)
        with self.assertRaises(Invalid):
            validate(old)
        self.assertEqual(old, original)

    def test_scroll_contract_rejects_unbounded_or_unclassified_positions(self):
        task = self.repo.get(self.saved()["id"])
        item = {**action(), "version":2, "kind":"scroll", "requires":["uia.scroll.v2"],
                "target":{**action()["target"], "scope":[]},
                "value":{"horizontal":-1, "vertical":37.5}}
        task["actions"] = [item]
        self.assertEqual(validate(task)["actions"][0]["value"]["vertical"], 37.5)
        for bad in (-2, 101, True, "30", float("nan"), float("inf")):
            item["value"]["vertical"] = bad
            with self.subTest(bad=bad), self.assertRaises(Invalid):
                validate(task)
        item["value"] = {"horizontal":-1, "vertical":-1}
        with self.assertRaises(Invalid):
            validate(task)

    def test_menu_expansion_requires_an_explicit_state(self):
        task = self.repo.get(self.saved()["id"])
        task["actions"] = [{**action(), "version":2, "kind":"expand", "requires":["uia.expand.v2"],
                            "target":{**action()["target"], "scope":[]}, "value":False}]
        self.assertIs(validate(task)["actions"][0]["value"], False)
        task["actions"][0]["value"] = 0
        with self.assertRaises(Invalid):
            validate(task)

    def test_draft_write_failure_stops_capture(self):
        self.start()
        def fail(*args):
            raise OSError("synthetic disk failure")
        self.repo.checkpoint = fail
        with self.assertRaises(OSError):
            self.accept()
        self.assertEqual(self.rec.state, "interrupted")
        self.assertFalse(self.accept())

    def test_flush_failure_prevents_save(self):
        self.start()
        def fail():
            raise RuntimeError("synthetic capture failure")
        with self.assertRaises(RuntimeError):
            self.rec.stop(fail)
        self.assertEqual(self.rec.state, "interrupted")
        self.assertIsNotNone(self.repo.load_draft())

    def test_versions_identity_and_context_fail_closed(self):
        self.start()
        t = copy.deepcopy(self.rec.task)
        for invalid in (
            {**t, "version":2},
            {**t, "starting_context":{"mode":"specific_product","binding":None}},
            {**t, "actions":[{**action(),"requires":[]}]},
            {**t, "actions":[{**action(),"target":{**action()["target"],"x":50}}]},
            {**t, "actions":[{**action(),"target":{**action()["target"],"name":"Password"}}]},
        ):
            with self.assertRaises(Invalid):
                validate(invalid)

    def test_cancel_is_independent_of_control_queue(self):
        cancel = Cancellation()
        cancel.check()
        cancel.stop()
        with self.assertRaises(InterruptedError):
            cancel.check()

    def test_cleanup_on_cancel_and_failure(self):
        released = []
        class Executor:
            def release_held_input(self):
                released.append(True)
        for fail in (False, True):
            cancel = Cancellation()
            with self.assertRaises((InterruptedError, RuntimeError)):
                with input_scope(Executor(), cancel):
                    if fail:
                        raise RuntimeError("synthetic failure")
                    cancel.stop()
        self.assertEqual(released, [True, True])


if __name__ == "__main__":
    unittest.main()
