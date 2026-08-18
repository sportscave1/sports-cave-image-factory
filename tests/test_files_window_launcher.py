from pathlib import Path
import unittest
from unittest import mock

import files_window_launcher


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER_CLIENT = ROOT / "components" / "files_window_launcher" / "index.html"


class _ComponentRecorder:
    def __init__(self):
        self.declarations = []
        self.mounts = []

    def declare_component(self, name, **kwargs):
        self.declarations.append((name, kwargs))

        def mount(**mount_kwargs):
            self.mounts.append(mount_kwargs)

        return mount


class _StreamlitRecorder:
    def __init__(self):
        self.markdown_calls = []

    def markdown(self, body, **kwargs):
        self.markdown_calls.append((body, kwargs))


class FilesWindowLauncherLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.original_component = files_window_launcher._COMPONENT
        files_window_launcher._COMPONENT = None

    def tearDown(self):
        files_window_launcher._COMPONENT = self.original_component

    def test_packaged_component_assets_are_available_from_source_relative_path(self):
        component_dir = files_window_launcher.validate_component_assets()

        self.assertTrue(component_dir.is_absolute())
        self.assertEqual(ROOT / "components" / "files_window_launcher", component_dir)
        self.assertTrue((component_dir / "index.html").is_file())

    def test_registration_is_process_stable_and_never_uses_a_development_url(self):
        components = _ComponentRecorder()

        first = files_window_launcher.get_component(components)
        second = files_window_launcher.get_component(components)

        self.assertIs(first, second)
        self.assertEqual(1, len(components.declarations))
        name, kwargs = components.declarations[0]
        self.assertEqual("files_window_launcher", name)
        self.assertEqual(str(files_window_launcher.COMPONENT_DIR), kwargs["path"])
        self.assertNotIn("url", kwargs)

    def test_repeated_renders_keep_one_registration_and_one_stable_widget_key(self):
        components = _ComponentRecorder()
        st_module = _StreamlitRecorder()

        for _attempt in range(5):
            self.assertTrue(files_window_launcher.render(st_module, components))

        self.assertEqual(1, len(components.declarations))
        self.assertEqual(5, len(components.mounts))
        self.assertTrue(
            all(
                mount == {"key": files_window_launcher.COMPONENT_KEY, "default": None}
                for mount in components.mounts
            )
        )
        self.assertEqual([], st_module.markdown_calls)

    def test_registration_failure_keeps_a_compact_files_fallback(self):
        components = _ComponentRecorder()
        st_module = _StreamlitRecorder()

        with mock.patch.object(
            files_window_launcher,
            "validate_component_assets",
            side_effect=FileNotFoundError("fixture missing"),
        ):
            self.assertFalse(files_window_launcher.render(st_module, components))

        self.assertEqual(1, len(st_module.markdown_calls))
        body, kwargs = st_module.markdown_calls[0]
        self.assertIn('href="/files-window"', body)
        self.assertIn('target="_blank"', body)
        self.assertEqual({"unsafe_allow_html": True}, kwargs)

    def test_iframe_lifecycle_cleans_up_and_suppresses_duplicate_launches(self):
        source = LAUNCHER_CLIENT.read_text(encoding="utf-8")

        self.assertIn("new AbortController()", source)
        self.assertIn("listenerController.abort()", source)
        self.assertIn('window.addEventListener("pagehide", destroy', source)
        self.assertIn("if (launchPending) return", source)
        self.assertIn('window.open("/files-window", "sports-cave-files-window"', source)
        self.assertIn("popup.focus()", source)
        self.assertIn("window.SportsCaveFilesLauncher?.destroy?.()", source)
        self.assertNotIn("streamlit:setComponentValue", source)


if __name__ == "__main__":
    unittest.main()
