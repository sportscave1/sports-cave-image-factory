"""Original downloads: synthetic upstream only, never credentials or provider traffic."""
import asyncio
import io
import unittest
from unittest.mock import Mock, patch
from urllib.parse import quote
from PIL import Image
import files_upload_api as api
from tests.test_files_window import get_request


class OriginalFilesTests(unittest.TestCase):
    def request(self, query, content=b"original", denied=False, name=None):
        upstream = Mock()
        upstream.iter_content.return_value = [content[:7], b"", content[7:]]
        with patch.object(api, "_request_user", side_effect=api.FilesUploadError("Denied", status_code=403) if denied else None,
                          return_value={"id":"synthetic"}), patch.object(api, "_dropbox_context",
                          return_value={"root_path":"/Synthetic", "access_token":"synthetic"}), patch.object(
                          api.dropbox_integration, "get_file_response", return_value=({"size":len(content), "name":name}, upstream)) as fetch, patch.object(
                          api, "record_activity_log"), patch.object(api, "_preview_bytes") as preview:
            response = asyncio.run(api.download_file(get_request("/api/files-download", query)))
            preview.assert_not_called()
            return response, upstream, fetch

    def test_original_formats_bytes_dimensions_and_unicode_filename(self):
        for fmt, extension in [("PNG","png"), ("JPEG","jpg"), ("WEBP","webp"), (None,"psd"), (None,"pdf")]:
            with self.subTest(format=extension):
                data = io.BytesIO()
                if fmt:
                    Image.new("RGB", (2400, 1600), "#123456").save(data, format=fmt)
                else:
                    data.write(b"original binary\x00\xff\x01" * 100)
                content = data.getvalue()
                name = f"Designs/O'Neal & Jürgen.{extension}"
                for query in [{"relative_path":name}, {"path":"/Synthetic/"+name}]:
                    response, upstream, fetch = self.request(query, content)
                    async def consume():
                        return b"".join([chunk async for chunk in response.body_iterator])
                    downloaded = asyncio.run(consume())
                    self.assertEqual(downloaded, content)
                    self.assertEqual(response.headers["content-length"], str(len(content)))
                    self.assertIn(quote(name.split("/")[-1], safe=""), response.headers["content-disposition"])
                    self.assertTrue(response.headers["content-disposition"].startswith("attachment;"))
                    self.assertEqual(response.headers["cache-control"], "private, no-store")
                    if fmt:
                        self.assertEqual(Image.open(io.BytesIO(downloaded)).size, (2400, 1600))
                    fetch.assert_called_once_with("synthetic", "/Synthetic/"+name)
                    upstream.close.assert_called_once()

    def test_denied_and_outside_root_do_not_retrieve_original(self):
        for query, denied in [({"relative_path":"art.png"},True), ({"path":"/Other/art.png"},False), ({"relative_path":"../art.png"},False)]:
            response, _, fetch = self.request(query, denied=denied)
            self.assertGreaterEqual(response.status_code, 400)
            fetch.assert_not_called()

    def test_filename_uses_provider_original_casing(self):
        response, _, _ = self.request({"relative_path":"art.png"}, name="Art Original.PNG")
        self.assertIn("Art%20Original.PNG", response.headers["content-disposition"])

    def test_missing_original_never_substitutes_preview(self):
        with patch.object(api, "_request_user", return_value={"id":"synthetic"}), patch.object(api, "_dropbox_context",
                         return_value={"root_path":"/Synthetic", "access_token":"synthetic"}), patch.object(
                         api.dropbox_integration, "get_file_response", side_effect=api.FilesUploadError("Missing", status_code=404)), patch.object(
                         api, "_preview_bytes") as preview:
            response = asyncio.run(api.download_file(get_request("/api/files-download", {"relative_path":"missing.png"})))
            self.assertEqual(response.status_code, 404)
            preview.assert_not_called()
