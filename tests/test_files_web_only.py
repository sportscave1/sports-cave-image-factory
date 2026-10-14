"""Files web-only boundary: no provider credentials, desktop launches or live data."""
import ast
import asyncio
import subprocess
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import files_upload_api as api
from tests.test_files_window import get_request

ROOT = Path(__file__).resolve().parents[1]


class FilesWebOnlyTests(unittest.TestCase):
    def test_retired_routes_and_launch_components_are_absent(self):
        routes = {route[0] for route in api.FILES_UPLOAD_ROUTES}
        for path in ["/files-native-launch", "/api/files-native-open", "/api/files-native-launch", "/api/files-native-launch/claim", "/api/files-native-transfer"]:
            self.assertNotIn(path, routes)
        for path in ["/api/files-native-transfer/manifest", "/api/files-native-transfer/content", "/api/files-desktop-helper", "/api/files-psd-open"]:
            self.assertIn(path, routes, "Shared Photoshop/preparation dependency must remain")
        self.assertFalse((ROOT / "files_native_launch.py").exists())
        self.assertFalse((ROOT / "components/files_window/native_launch.html").exists())

    def test_files_clients_cannot_contact_or_launch_companion(self):
        for name in ["files_window", "files_image_viewer"]:
            source = (ROOT / "components" / name / "index.html").read_text(encoding="utf8")
            for forbidden in ["chrome.webview", "desktopRequest", "hasDesktopCapability", "sports-cave-files://", "sports-cave-desktop", "window.open(", "window.close(", "files-native-", "files-desktop-helper", "localhost", "127.0.0.1", "Open With", "Get helper", "Desktop app"]:
                self.assertNotIn(forbidden, source)

    def test_shared_automation_sources_and_transfer_consumers_are_unchanged(self):
        for name in ["desktop_helper/SportsCaveFilesDesktop.cs", "desktop_helper/Install.ps1", "desktop_helper_macos/SportsCaveFilesHelper.py", "auto_editions_api.py", "auto_editions_setup_api.py", "edition_test_api.py", "scripts/studio/auto_editions_local.py", "scripts/studio/edition_test_local.py", "components/psd_open/index.html", "dropbox_integration.py", "supabase_backend.py", "design_studio_page.py", "developer_studio_page.py", "scripts/studio/companion.py", "render.yaml"]:
            self.assertEqual((ROOT / name).read_bytes(), subprocess.check_output(["git", "show", "7ad36065:" + name], cwd=ROOT), name)
        before = subprocess.check_output(["git", "show", "7ad36065:files_upload_api.py"], cwd=ROOT).decode()
        after = (ROOT / "files_upload_api.py").read_text(encoding="utf8")
        for start, end in [("class NativeTransferManager:", "NATIVE_TRANSFER_MANAGER ="), ("async def native_transfer_manifest", "async def file_thumbnail"), ("async def desktop_helper_package", "async def")]:
            def section(text):
                offset = text.index(start)
                return text[offset:text.index(end, offset + len(start))]
            self.assertEqual(section(before), section(after), start)

    def test_app_changes_are_exclusively_files_code(self):
        before = subprocess.check_output(["git", "show", "7ad36065:app.py"], cwd=ROOT).decode()
        after = (ROOT / "app.py").read_text(encoding="utf8")
        def functions(source):
            return {node.name:ast.dump(node) for node in ast.parse(source).body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
        old, new = functions(before), functions(after)
        allowed = {"inject_styles", "_files_interaction_rows", "_files_desktop_application", "_files_open_strategy", "_files_desktop_open_available", "_render_files_preview"}
        changed = {name for name in old.keys() | new.keys() if old.get(name) != new.get(name)}
        self.assertLessEqual(changed, allowed)
        self.assertNotIn("sports-cave-files://", (ROOT / "components/files_chunk_uploader/index.html").read_text(encoding="utf8"))

    def test_legacy_preview_reuses_small_viewer_without_original_lookup(self):
        tree = ast.parse((ROOT / "app.py").read_text(encoding="utf8"))
        names = {"_render_files_preview", "_files_preview_kind", "_files_download_url"}
        module = ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names], type_ignores=[])
        import html
        from urllib.parse import quote
        st = Mock()
        environment = {"st":st, "dropbox_integration":api.dropbox_integration, "Path":Path, "html":html, "quote":quote, "_render_files_navigation":Mock()}
        exec(compile(module,"legacy-files-fixture","exec"),environment)
        with patch.object(api.dropbox_integration,"file_open_details") as original:
            for name in ["Large.jpg","Master.psd","Manual.pdf","Unsupported.zip"]:
                environment["_render_files_preview"]("synthetic",{},"/Synthetic","/Synthetic/"+name)
                self.assertIn("/files-image-viewer?legacy=1&path=",st.iframe.call_args.args[0])
            original.assert_not_called()
        self.assertNotIn('target="_blank"',st.markdown.call_args.args[0])

    def test_pdf_assets_are_versioned_and_cannot_escape_the_static_directory(self):
        from starlette.requests import Request
        def asset(path, encoding=""):
            request = Request({"type":"http","method":"GET","path":"/files-preview-assets/6.4.299/"+path,"path_params":{"asset":path},"headers":[(b"accept-encoding",encoding.encode())]})
            return asyncio.run(api.preview_asset(request))
        good=asset("build/pdf.min.mjs")
        self.assertEqual(good.status_code,200)
        self.assertTrue(good.headers["content-type"].startswith("text/javascript"))
        self.assertIn("immutable",good.headers["cache-control"])
        compressed=asset("build/pdf.min.mjs", "gzip, deflate, br")
        self.assertEqual(compressed.headers["content-encoding"],"gzip")
        import gzip
        self.assertEqual(gzip.decompress(Path(compressed.path).read_bytes()),Path(good.path).read_bytes())
        self.assertNotIn("content-encoding",asset("build/pdf.min.mjs", "gzip;q=0").headers)
        self.assertEqual(asset("build/pdf.min.mjs", "gzip;q=...").status_code,200)
        for path in ["../../../app.py","C:/Windows/win.ini","build/../../index.html","missing.mjs"]:
            self.assertEqual(asset(path).status_code,404)

    def pdf(self, path="Manual.pdf", revision="r1"):
        return asyncio.run(api.pdf_preview(get_request("/api/files-pdf-preview", {"path":path, "rev":revision})))

    def test_pdf_authenticated_scoped_stream_preserves_bytes(self):
        content = b"%PDF-1.4\nsynthetic fixture"
        metadata = {".tag":"file", "id":"id:pdf", "rev":"r1", "size":len(content)}
        upstream = Mock(); upstream.iter_content.return_value = [content]
        with patch.object(api, "_request_user", return_value={"id":"worker"}) as auth, patch.object(api, "_dropbox_context", return_value={"access_token":"synthetic", "root_path":"/Synthetic"}), patch.object(api.dropbox_integration,"get_file_metadata",return_value=metadata), patch.object(api.dropbox_integration,"get_file_response",return_value=(metadata,upstream)) as download:
            response = self.pdf()
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.headers["content-type"],"application/pdf")
            self.assertEqual(response.headers["cache-control"],"private, no-store")
            async def consume():
                return b"".join([part async for part in response.body_iterator])
            self.assertEqual(asyncio.run(consume()),content)
            download.assert_called_once_with("synthetic","/Synthetic/Manual.pdf")
            auth.assert_called_once(); upstream.close.assert_called_once()

    def test_pdf_rejects_permissions_wrong_types_traversal_size_and_revision(self):
        meta = {".tag":"file", "id":"id:pdf", "rev":"r1", "size":100}
        with patch.object(api, "_request_user", return_value={"id":"worker"}) as auth, patch.object(api, "_dropbox_context", return_value={"access_token":"synthetic", "root_path":"/Synthetic"}), patch.object(api.dropbox_integration,"get_file_metadata",return_value=meta), patch.object(api.dropbox_integration,"get_file_response") as download:
            for path in ["../Manual.pdf", "Manual.psd", "Manual.exe"]:
                self.assertGreaterEqual(self.pdf(path).status_code,400)
            self.assertEqual(self.pdf(revision="changed").status_code,409)
            meta["size"]=26*1024*1024
            self.assertEqual(self.pdf().status_code,413)
            auth.side_effect=api.FilesUploadError("Denied",status_code=403)
            self.assertEqual(self.pdf().status_code,403)
            download.assert_not_called()

    def test_pdf_changed_during_open_closes_stream(self):
        meta={".tag":"file","id":"id:pdf","rev":"r1","size":100}
        upstream=Mock()
        with patch.object(api,"_request_user",return_value={"id":"worker"}), patch.object(api,"_dropbox_context",return_value={"access_token":"synthetic","root_path":"/Synthetic"}), patch.object(api.dropbox_integration,"get_file_metadata",return_value=meta), patch.object(api.dropbox_integration,"get_file_response",return_value=({**meta,"rev":"r2"},upstream)):
            self.assertEqual(self.pdf().status_code,409)
            upstream.close.assert_called_once()
