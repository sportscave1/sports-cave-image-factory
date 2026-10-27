import copy
import hashlib
import unittest
from test_foundation import action
import test_phase2
from test_phase2 import command
from desktop_recorder.contract import validate, Invalid


class CopyTextTests(unittest.TestCase):
    setUp = test_phase2.Phase2Tests.setUp
    start = test_phase2.Phase2Tests.start
    event = test_phase2.Phase2Tests.event
    def copy_action(self):
        a = action()
        a.update(version=2, kind="copy_text", requires=["clipboard.copy-text.v2"],
                 value={"text": "Synthetic copied text", "source_sha256": hashlib.sha256(b"Synthetic copied text").hexdigest()})
        a["target"].update(control_type="Edit", automation_id="source", name="Source", scope=[])
        return a

    def test_copy_paste_save_reload_and_capability(self):
        self.start()
        self.event(self.copy_action())
        pasted = self.copy_action()
        pasted.update(kind="set_text", requires=["uia.value.v2"], value="Synthetic copied text")
        pasted["target"].update(automation_id="destination", name="Destination")
        self.event(pasted)
        self.c.apply(command("stop"))
        self.c.apply(command("save", {"name": "Copy and paste contract"}))
        saved = self.c.repository.get(self.c.last_saved["id"])
        self.assertEqual([a["kind"] for a in saved["actions"]], ["copy_text", "set_text"])
        self.assertEqual(saved["actions"][0]["value"], self.copy_action()["value"])

    def test_copy_rejects_unverified_or_page_wide_payloads(self):
        self.start()
        base = copy.deepcopy(self.c.recording.task)
        base["actions"] = [self.copy_action()]
        validate(base)
        for mutate in (
            lambda a: a["value"].update(source_sha256=""),
            lambda a: a["value"].update(text=""),
            lambda a: a["value"].update(text="x" * 2001),
            lambda a: a["target"].update(automation_id="RootWebArea"),
            lambda a: a["target"].update(control_type="Button"),
            lambda a: a.update(version=1, requires=["clipboard.copy-text.v1"]),
            lambda a: a["value"].update(unclassified_data="no"),
        ):
            task=copy.deepcopy(base)
            mutate(task["actions"][0])
            with self.assertRaises(Invalid):
                validate(task)


if __name__ == "__main__":
    unittest.main()
