import copy
import unittest
from test_foundation import action
import test_phase2
from test_phase2 import command
from desktop_recorder.contract import validate, Invalid


class BrowserTabTests(unittest.TestCase):
    setUp = test_phase2.Phase2Tests.setUp
    start = test_phase2.Phase2Tests.start
    event = test_phase2.Phase2Tests.event

    def tab_action(self):
        a = action()
        a.update(version=2, kind="browser_tab", requires=["edge.tab.v2"])
        a["target"].update(app=r"C:\Apps\msedge.exe", control_type="TabItem",
                           automation_id="", name="Local destination", scope=[])
        return a

    def test_save_and_reload_preserves_transition(self):
        self.start()
        self.event(self.tab_action())
        self.c.apply(command("stop"))
        self.c.apply(command("save", {"name": "Existing tab transition"}))
        saved = self.c.repository.get(self.c.last_saved["id"])
        self.assertEqual(saved["actions"][0], self.tab_action())

    def test_rejects_other_apps_and_unscoped_or_payload_actions(self):
        self.start()
        base = copy.deepcopy(self.c.recording.task)
        base["actions"] = [self.tab_action()]
        validate(base)
        for mutate in (
            lambda a: a["target"].update(app="notepad.exe"),
            lambda a: a["target"].update(control_type="Button"),
            lambda a: a["target"].update(name=""),
            lambda a: a["target"].update(automation_id="generated-id"),
            lambda a: a["target"].update(scope=[dict(control_type="Document", automation_id="RootWebArea", name="Page")]),
            lambda a: a.update(value="arbitrary"),
            lambda a: a.update(version=1, requires=["edge.tab.v1"]),
        ):
            invalid = copy.deepcopy(base)
            mutate(invalid["actions"][0])
            with self.assertRaises(Invalid):
                validate(invalid)
