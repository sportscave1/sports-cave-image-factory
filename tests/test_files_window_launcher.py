from pathlib import Path
import unittest
from unittest import mock
from types import SimpleNamespace
import subprocess
import tempfile
import importlib

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
    def test_import_is_lazy_and_sidebar_order_and_permission_gate_are_unchanged(self):
        import streamlit.components.v1 as components
        with mock.patch.object(components, 'declare_component') as declaration:
            importlib.reload(files_window_launcher)
        declaration.assert_not_called()
        source = (ROOT/'app.py').read_text(encoding='utf-8')
        start = source.index('def render_sidebar():')
        growth = source.index('_render_sidebar_create_growth(', start)
        reporting = source.index('reporting_overview_allowed =', growth)
        accounts = source.index('"Accounts & Access"', reporting)
        self.assertLess(growth, reporting)
        self.assertLess(reporting, accounts)
        self.assertNotIn('files_window_launcher.render(', source)
        self.assertNotIn('files-window-launcher-slot', source)
        config = (ROOT/'top_bar.py').read_text(encoding='utf-8')
        self.assertIn('"filesEnabled": "Files" in allowed_routes', config)

    def test_real_production_route_recovers_after_bare_declaration_and_runtime_reset(self):
        from starlette.applications import Starlette
        from starlette.testclient import TestClient
        import streamlit.components.v1 as components
        from streamlit.components.v1 import component_registry
        from streamlit.components.lib.local_component_registry import LocalComponentRegistry
        from streamlit.web.server.starlette.starlette_routes import create_component_routes

        with mock.patch.object(component_registry, 'get_script_run_ctx', return_value=None):
            early = files_window_launcher.get_component(components)
        self.assertEqual('files_window_launcher.files_window_launcher', early.name)
        for _runtime in range(2):
            registry = LocalComponentRegistry()
            with TestClient(Starlette(routes=create_component_routes(registry, None))) as client:
                url = '/component/' + early.name + '/index.html'
                self.assertEqual(404, client.get(url).status_code)
                with mock.patch.object(component_registry, 'get_script_run_ctx', return_value=object()), \
                     mock.patch.object(component_registry, 'get_instance', return_value=SimpleNamespace(component_registry=registry)):
                    for _rerun in range(3):
                        files_window_launcher.get_component(components)
                        response = client.get(url)
                        self.assertEqual(200, response.status_code)
                        self.assertIn('streamlit:componentReady', response.text)
                        self.assertNotIn('Component not found', response.text)
                self.assertEqual(1, len(registry.get_components()))

    def test_tracked_asset_survives_clean_export_without_build_or_local_files(self):
        relative = 'components/files_window_launcher/index.html'
        tracked = subprocess.check_output(['git','ls-files','--error-unmatch',relative], cwd=ROOT, text=True)
        self.assertEqual(relative, tracked.strip())
        # Export the tracked working-tree asset so uncommitted presentation updates are tested.
        bundled = LAUNCHER_CLIENT.read_bytes()
        self.assertNotIn(b'<script src=', bundled)
        self.assertNotIn(b'<link ', bundled)
        with tempfile.TemporaryDirectory() as directory:
            clean = Path(directory)
            target = clean / relative
            target.parent.mkdir(parents=True)
            target.write_bytes(bundled)
            # Package the current Python and HTML sources without generated dependencies.
            (clean/'files_window_launcher.py').write_bytes(Path(files_window_launcher.__file__).read_bytes())
            subprocess.run([__import__('sys').executable,'-c',
                'import files_window_launcher as f; assert f.validate_component_assets().is_dir(); '
                'assert f.COMPONENT_ENTRYPOINT.is_file()'],cwd=clean,check=True)

    def test_packaged_component_assets_are_available_from_source_relative_path(self):
        component_dir = files_window_launcher.validate_component_assets()

        self.assertTrue(component_dir.is_absolute())
        self.assertEqual(ROOT / "components" / "files_window_launcher", component_dir)
        self.assertTrue((component_dir / "index.html").is_file())

    def test_registration_is_refreshed_and_never_uses_a_development_url(self):
        components = _ComponentRecorder()

        first = files_window_launcher.get_component(components)
        second = files_window_launcher.get_component(components)

        self.assertIsNot(first, second)
        self.assertEqual(2, len(components.declarations))
        name, kwargs = components.declarations[0]
        self.assertEqual("files_window_launcher", name)
        self.assertEqual(str(files_window_launcher.COMPONENT_DIR), kwargs["path"])
        self.assertNotIn("url", kwargs)

    def test_repeated_renders_refresh_registration_and_keep_one_stable_widget_key(self):
        components = _ComponentRecorder()
        st_module = _StreamlitRecorder()

        for _attempt in range(5):
            self.assertTrue(files_window_launcher.render(st_module, components))

        self.assertEqual(5, len(components.declarations))
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
        self.assertIn('window.open(href, "sports-cave-files-window"', source)
        self.assertIn("popup.focus()", source)
        self.assertIn("SportsCaveFilesWindow", source)
        self.assertIn("relative_path", source)
        self.assertIn("window.SportsCaveFilesLauncher?.destroy?.()", source)
        self.assertNotIn("streamlit:setComponentValue", source)

    def test_scoped_folder_url_is_relative_validated_and_uses_existing_window(self):
        relative = "02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED"
        href = files_window_launcher.files_window_href(relative)
        handler = files_window_launcher.table_click_handler_html(relative_path=relative)

        self.assertEqual(f"/files-window?relative_path={relative}", href)
        self.assertIn("SportsCaveFilesWindow", handler)
        self.assertIn(files_window_launcher.FILES_WINDOW_NAME, handler)
        self.assertIn("popup.focus()", handler)
        self.assertIn("AbortController", handler)

        for unsafe in ("../private", "/absolute", "folder\\child", "C:/private", "folder//child"):
            with self.assertRaises(ValueError):
                files_window_launcher.files_window_href(unsafe)


if __name__ == "__main__":
    unittest.main()
