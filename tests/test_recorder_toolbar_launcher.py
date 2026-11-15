import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from task_recorder.server import Bridge
from task_recorder.schema import Invalid
from task_recorder.install import LAUNCHER


class ToolbarLauncherTests(unittest.TestCase):
    def test_reveal_preserves_current_session(self):
        for mode in ("idle", "recording", "paused", "interrupted", "playing"):
            with self.subTest(mode=mode):
                state = {"mode": mode, "draft": {"id": "preserve-me"}}
                runner = SimpleNamespace(
                    open_toolbar=AsyncMock(), publish_native=AsyncMock(),
                    desktop=SimpleNamespace(state=lambda: state),
                )
                result = asyncio.run(Bridge.show_toolbar(SimpleNamespace(runner=runner)))
                runner.open_toolbar.assert_awaited_once_with()
                runner.publish_native.assert_awaited_once_with({**state, "show_toolbar": True})
                self.assertEqual(state, {"mode": mode, "draft": {"id": "preserve-me"}})
                self.assertIn("opened", result["message"])

    def test_old_helper_fails_explicitly(self):
        with self.assertRaises(Invalid):
            asyncio.run(Bridge.show_toolbar(SimpleNamespace(runner=object())))

    def test_installed_launcher_allows_toolbar_flag(self):
        self.assertIn('"--toolbar"', LAUNCHER)


if __name__ == "__main__":
    unittest.main()
