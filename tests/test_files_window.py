import asyncio
import io
import json
from pathlib import Path
import unittest
from urllib.parse import urlencode
from unittest.mock import patch
import zipfile

import files_upload_api


ROOT = Path(__file__).resolve().parents[1]
TEAM_ROOT = "/Sportscave Team Folder"


def get_request(path, query=None):
    return files_upload_api.Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "query_string": urlencode(query or {}).encode("utf-8"),
            "headers": [],
            "scheme": "https",
            "server": ("sports-cave.test", 443),
        }
    )


def json_request(path, payload):
    body = json.dumps(payload).encode("utf-8")
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return files_upload_api.Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "query_string": b"",
            "headers": [(b"content-type", b"application/json")],
            "scheme": "https",
            "server": ("sports-cave.test", 443),
        },
        receive,
    )


async def response_bytes(response):
    if hasattr(response, "body"):
        return bytes(response.body)
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(bytes(chunk))
    return b"".join(chunks)


class FilesWindowApiTests(unittest.TestCase):
    def setUp(self):
        self.user = {
            "id": "worker-1",
            "username": "worker",
            "display_name": "Worker",
            "role": "worker",
            "is_active": True,
            "page_permissions": ["files"],
        }
        files_upload_api._DIRECTORY_CACHE.clear()
        files_upload_api.DRAG_DOWNLOAD_MANAGER._records.clear()

    def test_standalone_page_requires_files_access_and_serves_no_streamlit_shell(self):
        request = get_request("/files-window")
        with patch.object(files_upload_api, "_request_user", return_value=self.user):
            response = asyncio.run(files_upload_api.files_window_page(request))

        source = response.body.decode("utf-8")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Sports Cave Files", source)
        self.assertIn('class="results" id="results"', source)
        self.assertNotIn("stSidebar", source)
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_image_viewer_is_a_separate_authenticated_page(self):
        request = get_request("/files-image-viewer")
        with patch.object(files_upload_api, "_request_user", return_value=self.user):
            response = asyncio.run(files_upload_api.files_image_viewer_page(request))

        source = response.body.decode("utf-8")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Sports Cave Image Viewer", source)
        self.assertIn('class="stage" id="stage"', source)
        self.assertNotIn("stSidebar", source)
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_metadata_list_is_root_scoped_and_keeps_special_characters(self):
        path = f"{TEAM_ROOT}/Designs & Uploads"
        entries = [
            {
                ".tag": "file",
                "name": "O'Neal & J\u00fcnger.psd",
                "path_display": f"{path}/O'Neal & J\u00fcnger.psd",
                "server_modified": "2026-07-23T00:10:00Z",
                "size": 1234,
                "rev": "psd-revision",
            },
            {
                ".tag": "file",
                "name": "Preview & Final.png",
                "path_display": f"{path}/Preview & Final.png",
                "server_modified": "2026-07-23T00:11:00Z",
                "size": 4321,
                "rev": "png-revision",
            },
        ]
        request = get_request("/api/files-list", {"path": path})
        with patch.object(files_upload_api, "_request_user", return_value=self.user), patch.object(
            files_upload_api,
            "_dropbox_context",
            return_value={"access_token": "secret-token", "root_path": TEAM_ROOT},
        ), patch.object(files_upload_api, "_directory_entries", return_value=entries) as directory:
            response = asyncio.run(files_upload_api.list_files(request))

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["current_path"], path)
        self.assertEqual(payload["items"][0]["name"], "O'Neal & J\u00fcnger.psd")
        self.assertEqual(payload["items"][0]["desktop_relative_path"], "Designs & Uploads/O'Neal & J\u00fcnger.psd")
        self.assertEqual(payload["items"][0]["kind"], "photoshop")
        self.assertNotIn("thumbnail_url", payload["items"][0])
        self.assertIn("thumbnail_url", payload["items"][1])
        self.assertNotIn("secret-token", response.body.decode("utf-8"))
        directory.assert_called_once_with("secret-token", path, force=False)

    def test_psd_and_psb_are_metadata_only_and_thumbnail_endpoint_rejects_them(self):
        for extension in ("psd", "psb"):
            item = files_upload_api._public_file_item(
                {
                    ".tag": "file",
                    "name": f"Artwork.{extension}",
                    "path_display": f"{TEAM_ROOT}/Artwork.{extension}",
                    "size": 99,
                    "rev": "large-design",
                },
                TEAM_ROOT,
            )
            self.assertEqual(item["kind"], "photoshop")
            self.assertNotIn("thumbnail_url", item)

            request = get_request(
                "/api/files-thumbnail",
                {"path": f"{TEAM_ROOT}/Artwork.{extension}", "rev": "large-design"},
            )
            with patch.object(files_upload_api, "_request_user", return_value=self.user), patch.object(
                files_upload_api,
                "_dropbox_context",
                return_value={"access_token": "secret-token", "root_path": TEAM_ROOT},
            ), patch.object(files_upload_api, "_thumbnail_bytes") as thumbnail:
                response = asyncio.run(files_upload_api.file_thumbnail(request))

            self.assertEqual(response.status_code, 404)
            thumbnail.assert_not_called()

    def test_jpg_jpeg_and_png_get_only_secure_lazy_thumbnail_urls(self):
        for extension in ("jpg", "jpeg", "png"):
            item = files_upload_api._public_file_item(
                {
                    ".tag": "file",
                    "name": f"Image.{extension}",
                    "path_display": f"{TEAM_ROOT}/Image.{extension}",
                    "size": 99,
                    "rev": "image-revision",
                },
                TEAM_ROOT,
            )
            self.assertTrue(item["thumbnail_url"].startswith("/api/files-thumbnail?"))
            self.assertNotIn("secret", item["thumbnail_url"])

    def test_webp_and_gif_are_images_but_do_not_request_list_thumbnails(self):
        for extension in ("webp", "gif"):
            item = files_upload_api._public_file_item(
                {
                    ".tag": "file",
                    "name": f"Image.{extension}",
                    "path_display": f"{TEAM_ROOT}/Image.{extension}",
                    "size": 99,
                },
                TEAM_ROOT,
            )
            self.assertEqual(item["kind"], "image")
            self.assertNotIn("thumbnail_url", item)

    def test_image_preview_accepts_only_validated_root_relative_image_paths(self):
        relative = "Designs & Uploads/O'Neal & J\u00fcnger.png"
        full_path = f"{TEAM_ROOT}/{relative}"
        request = get_request("/api/files-image-preview", {"path": relative})
        with patch.object(files_upload_api, "_request_user", return_value=self.user), patch.object(
            files_upload_api,
            "_dropbox_context",
            return_value={"access_token": "secret-token", "root_path": TEAM_ROOT},
        ), patch.object(
            files_upload_api.dropbox_integration,
            "get_file_metadata",
            return_value={".tag": "file", "size": 7},
        ), patch.object(
            files_upload_api.dropbox_integration,
            "get_file_response",
            return_value=(
                {".tag": "file", "size": 7},
                type("Upstream", (), {"content": b"PNGDATA", "close": lambda self: None})(),
            ),
        ) as download:
            response = asyncio.run(files_upload_api.image_preview(request))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(asyncio.run(response_bytes(response)), b"PNGDATA")
        self.assertEqual(response.media_type, "image/png")
        self.assertEqual(response.headers["content-length"], "7")
        download.assert_called_once_with("secret-token", full_path)

        for invalid in ("../outside.png", "/absolute.png", "C:/Windows/file.png", "Artwork.psd"):
            denied = get_request("/api/files-image-preview", {"path": invalid})
            with patch.object(files_upload_api, "_request_user", return_value=self.user), patch.object(
                files_upload_api,
                "_dropbox_context",
                return_value={"access_token": "secret-token", "root_path": TEAM_ROOT},
            ), patch.object(files_upload_api.dropbox_integration, "get_file_response") as original:
                denied_response = asyncio.run(files_upload_api.image_preview(denied))
            self.assertIn(denied_response.status_code, {403, 404})
            original.assert_not_called()

    def test_image_navigation_returns_only_root_relative_images_from_current_folder(self):
        folder = "Designs & Uploads"
        full_folder = f"{TEAM_ROOT}/{folder}"
        entries = [
            {".tag": "file", "name": "One.jpg", "path_display": f"{full_folder}/One.jpg"},
            {".tag": "file", "name": "Two.gif", "path_display": f"{full_folder}/Two.gif"},
            {".tag": "file", "name": "Large.psd", "path_display": f"{full_folder}/Large.psd"},
            {".tag": "folder", "name": "Nested", "path_display": f"{full_folder}/Nested"},
        ]
        request = get_request("/api/files-image-items", {"folder": folder})
        with patch.object(files_upload_api, "_request_user", return_value=self.user), patch.object(
            files_upload_api,
            "_dropbox_context",
            return_value={"access_token": "secret-token", "root_path": TEAM_ROOT},
        ), patch.object(files_upload_api, "_directory_entries", return_value=entries) as listing:
            response = asyncio.run(files_upload_api.image_folder_items(request))

        payload = json.loads(response.body)
        self.assertEqual([item["path"] for item in payload["images"]], [f"{folder}/One.jpg", f"{folder}/Two.gif"])
        listing.assert_called_once_with("secret-token", full_folder)

    def test_relative_download_path_is_root_scoped(self):
        relative = "Designs/O'Neal & Final.pdf"
        request = get_request("/api/files-download", {"relative_path": relative})
        with patch.object(files_upload_api, "_request_user", return_value=self.user), patch.object(
            files_upload_api,
            "_dropbox_context",
            return_value={"access_token": "secret-token", "root_path": TEAM_ROOT},
        ), patch.object(
            files_upload_api.dropbox_integration,
            "get_temporary_link",
            return_value="https://dropbox.example/download",
        ) as temporary_link:
            response = asyncio.run(files_upload_api.download_file(request))

        self.assertEqual(response.status_code, 307)
        temporary_link.assert_called_once_with("secret-token", f"{TEAM_ROOT}/{relative}")

    def test_helper_package_selects_real_windows_and_macos_installers(self):
        for platform, expected in (("windows", "Install.ps1"), ("macos", "Install.command")):
            request = get_request("/api/files-desktop-helper", {"platform": platform})
            with patch.object(files_upload_api, "_request_user", return_value=self.user):
                response = asyncio.run(files_upload_api.desktop_helper_package(request))
            with zipfile.ZipFile(io.BytesIO(response.body)) as archive:
                self.assertIn(expected, archive.namelist())
                if platform == "macos":
                    mode = archive.getinfo("Install.command").external_attr >> 16
                    self.assertTrue(mode & 0o100)

    def test_directory_cache_reuses_metadata_and_can_be_invalidated_per_folder(self):
        first = f"{TEAM_ROOT}/First"
        second = f"{TEAM_ROOT}/Second"
        with patch.object(
            files_upload_api.dropbox_integration,
            "list_folder",
            side_effect=[[{"name": "one"}], [{"name": "two"}], [{"name": "one-new"}]],
        ) as listing:
            self.assertEqual(files_upload_api._directory_entries("token", first)[0]["name"], "one")
            self.assertEqual(files_upload_api._directory_entries("token", first)[0]["name"], "one")
            self.assertEqual(files_upload_api._directory_entries("token", second)[0]["name"], "two")
            files_upload_api.invalidate_directory_cache(first)
            self.assertEqual(files_upload_api._directory_entries("token", first)[0]["name"], "one-new")

        self.assertEqual(listing.call_count, 3)

    def test_rename_and_delete_item_validation_rejects_root_traversal_and_other_folders(self):
        current = f"{TEAM_ROOT}/Current"
        valid = f"{current}/O'Neal & Final.psd"
        self.assertEqual(
            files_upload_api._validated_item_in_folder(valid, current, TEAM_ROOT),
            (valid, current),
        )
        for invalid in (
            TEAM_ROOT,
            f"{TEAM_ROOT}/Other/file.psd",
            "/Outside/file.psd",
            "C:/Windows/file.psd",
            f"{current}/../outside.psd",
        ):
            with self.assertRaises(files_upload_api.FilesUploadError):
                files_upload_api._validated_item_in_folder(invalid, current, TEAM_ROOT)

    def test_new_folder_endpoint_uses_current_root_and_invalidates_only_that_listing(self):
        current = f"{TEAM_ROOT}/Designs"
        request = json_request(
            "/api/files-folder",
            {"current_path": current, "name": "O'Neal & Finals", "conflict": "cancel"},
        )
        metadata = {
            ".tag": "folder",
            "name": "O'Neal & Finals",
            "path_display": f"{current}/O'Neal & Finals",
        }
        with patch.object(files_upload_api, "_request_user", return_value=self.user), patch.object(
            files_upload_api,
            "_dropbox_context",
            return_value={"access_token": "secret-token", "root_path": TEAM_ROOT},
        ), patch.object(
            files_upload_api.dropbox_integration,
            "create_folder",
            return_value=metadata,
        ) as create, patch.object(files_upload_api, "invalidate_directory_cache") as invalidate, patch.object(
            files_upload_api,
            "record_activity_log",
        ) as activity:
            response = asyncio.run(files_upload_api.create_files_folder(request))

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["item"]["name"], "O'Neal & Finals")
        create.assert_called_once_with(
            "secret-token",
            current,
            "O'Neal & Finals",
            conflict="cancel",
        )
        invalidate.assert_called_once_with(current)
        self.assertEqual(activity.call_args.kwargs["actor"], "Worker")

    def test_rename_endpoint_validates_parent_and_invalidates_old_and_new_paths(self):
        current = f"{TEAM_ROOT}/Designs"
        old_path = f"{current}/Old & Final.psd"
        new_path = f"{current}/O'Neal Final.psd"
        request = json_request(
            "/api/files-rename",
            {"current_path": current, "path": old_path, "name": "O'Neal Final.psd"},
        )
        metadata = {
            ".tag": "file",
            "name": "O'Neal Final.psd",
            "path_display": new_path,
            "size": 900,
        }
        with patch.object(files_upload_api, "_request_user", return_value=self.user), patch.object(
            files_upload_api,
            "_dropbox_context",
            return_value={"access_token": "secret-token", "root_path": TEAM_ROOT},
        ), patch.object(
            files_upload_api.dropbox_integration,
            "rename_path",
            return_value=metadata,
        ) as rename, patch.object(files_upload_api, "invalidate_directory_cache") as invalidate_directory, patch.object(
            files_upload_api,
            "invalidate_thumbnail_cache",
        ) as invalidate_thumbnail, patch.object(files_upload_api, "record_activity_log"):
            response = asyncio.run(files_upload_api.rename_files_item(request))

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["item"]["path"], new_path)
        self.assertNotIn("thumbnail_url", payload["item"])
        rename.assert_called_once_with(
            "secret-token",
            old_path,
            "O'Neal Final.psd",
            root_path=TEAM_ROOT,
        )
        invalidate_directory.assert_called_once_with(current, old_path, new_path)
        invalidate_thumbnail.assert_called_once_with(old_path, new_path)

    def test_new_window_routes_are_registered_without_replacing_secure_existing_routes(self):
        routes = {path: methods for path, _endpoint, methods in files_upload_api.FILES_UPLOAD_ROUTES}
        self.assertEqual(routes["/files-window"], ("GET",))
        self.assertEqual(routes["/files-image-viewer"], ("GET",))
        self.assertEqual(routes["/api/files-list"], ("GET",))
        self.assertEqual(routes["/api/files-folder"], ("POST",))
        self.assertEqual(routes["/api/files-rename"], ("POST",))
        self.assertEqual(routes["/api/files-download"], ("GET",))
        self.assertEqual(routes["/api/files-image-preview"], ("GET",))
        self.assertEqual(routes["/api/files-image-items"], ("GET",))
        self.assertEqual(routes["/api/files-delete"], ("POST",))
        self.assertEqual(routes["/api/files-paste"], ("POST",))
        self.assertEqual(routes["/api/files-drag-token"], ("POST",))
        self.assertEqual(routes["/api/files-drag/{token}"], ("GET",))

    def test_transfer_validation_rejects_traversal_outside_root_and_folder_descendants(self):
        sources, destination = files_upload_api._validated_transfer_paths(
            ["Source/One.jpg", "Source/Two.png"],
            "Destination",
            TEAM_ROOT,
        )
        self.assertEqual(
            sources,
            [f"{TEAM_ROOT}/Source/One.jpg", f"{TEAM_ROOT}/Source/Two.png"],
        )
        self.assertEqual(destination, f"{TEAM_ROOT}/Destination")
        for paths, target in (
            (["../outside.jpg"], "Destination"),
            (["Source"], "Source"),
            (["Source"], "Source/Nested"),
            (["C:/Windows/file.jpg"], "Destination"),
        ):
            with self.subTest(paths=paths, target=target):
                with self.assertRaises(files_upload_api.FilesUploadError):
                    files_upload_api._validated_transfer_paths(paths, target, TEAM_ROOT)

    def test_copy_and_multi_item_move_use_dropbox_server_side_operations(self):
        source_metadata = {
            f"{TEAM_ROOT}/Source/One.jpg": {".tag": "file", "name": "One.jpg"},
            f"{TEAM_ROOT}/Source/Folder": {".tag": "folder", "name": "Folder"},
        }
        copy_request = json_request(
            "/api/files-paste",
            {
                "paths": ["Source/One.jpg"],
                "destination": "Destination",
                "operation": "copy",
                "conflict": "prompt",
            },
        )
        with patch.object(files_upload_api, "_request_user", return_value=self.user), patch.object(
            files_upload_api,
            "_dropbox_context",
            return_value={"access_token": "token", "root_path": TEAM_ROOT},
        ), patch.object(
            files_upload_api.dropbox_integration,
            "get_file_metadata",
            side_effect=lambda _token, path: source_metadata[path],
        ), patch.object(
            files_upload_api.dropbox_integration,
            "get_metadata_if_exists",
            return_value=None,
        ), patch.object(
            files_upload_api.dropbox_integration,
            "copy_path",
            return_value={
                ".tag": "file",
                "name": "One.jpg",
                "path_display": f"{TEAM_ROOT}/Destination/One.jpg",
                "size": 4,
            },
        ) as copy_path, patch.object(files_upload_api, "record_activity_log"):
            copy_response = asyncio.run(files_upload_api.paste_files(copy_request))

        self.assertEqual(copy_response.status_code, 200)
        self.assertEqual(len(json.loads(copy_response.body)["successful"]), 1)
        copy_path.assert_called_once_with(
            "token",
            f"{TEAM_ROOT}/Source/One.jpg",
            f"{TEAM_ROOT}/Destination/One.jpg",
            root_path=TEAM_ROOT,
        )

        move_request = json_request(
            "/api/files-paste",
            {
                "paths": ["Source/One.jpg", "Source/Folder"],
                "destination": "Destination",
                "operation": "move",
                "conflict": "prompt",
            },
        )
        with patch.object(files_upload_api, "_request_user", return_value=self.user), patch.object(
            files_upload_api,
            "_dropbox_context",
            return_value={"access_token": "token", "root_path": TEAM_ROOT},
        ), patch.object(
            files_upload_api.dropbox_integration,
            "get_file_metadata",
            side_effect=lambda _token, path: source_metadata[path],
        ), patch.object(
            files_upload_api.dropbox_integration,
            "get_metadata_if_exists",
            return_value=None,
        ), patch.object(
            files_upload_api.dropbox_integration,
            "move_path",
            side_effect=lambda _token, _source, target, **_kwargs: {
                ".tag": "folder" if target.endswith("/Folder") else "file",
                "name": target.rsplit("/", 1)[-1],
                "path_display": target,
            },
        ) as move_path, patch.object(files_upload_api, "record_activity_log"):
            move_response = asyncio.run(files_upload_api.paste_files(move_request))

        move_payload = json.loads(move_response.body)
        self.assertEqual(len(move_payload["successful"]), 2)
        self.assertFalse(move_payload["failed"])
        self.assertEqual(move_path.call_count, 2)

    def test_paste_conflicts_require_choice_and_keep_both_starts_at_two(self):
        source = f"{TEAM_ROOT}/Source/image.jpg"
        destination = f"{TEAM_ROOT}/Destination"
        with patch.object(
            files_upload_api.dropbox_integration,
            "get_file_metadata",
            return_value={".tag": "file", "name": "image.jpg"},
        ), patch.object(
            files_upload_api.dropbox_integration,
            "get_metadata_if_exists",
            return_value={".tag": "file", "name": "image.jpg"},
        ):
            with self.assertRaises(files_upload_api.FilesUploadError) as caught:
                files_upload_api._paste_plan(
                    "token", [source], destination, operation="copy", conflict="prompt"
                )
        self.assertEqual(caught.exception.code, "paste_conflict")
        self.assertEqual(caught.exception.details["conflicts"][0]["name"], "image.jpg")

        with patch.object(
            files_upload_api.dropbox_integration,
            "path_exists",
            side_effect=[True, False],
        ):
            kept = files_upload_api.dropbox_integration.windows_numbered_path(
                "token", f"{destination}/image.jpg"
            )
        self.assertEqual(kept, f"{destination}/image (3).jpg")

    def test_drag_tokens_expire_and_stream_original_filename_mime_and_content(self):
        record = files_upload_api.DRAG_DOWNLOAD_MANAGER.issue(
            path=f"{TEAM_ROOT}/Images/O'Neal & Jünger.jpg",
            name="O'Neal & Jünger.jpg",
            media_type="image/jpeg",
            size=8,
            user_id="worker-1",
            now=100,
        )
        with self.assertRaises(files_upload_api.FilesUploadError) as caught:
            files_upload_api.DRAG_DOWNLOAD_MANAGER.consume(
                record.token,
                now=100 + files_upload_api.FILES_DRAG_TOKEN_SECONDS,
            )
        self.assertEqual(caught.exception.code, "drag_expired")

        record = files_upload_api.DRAG_DOWNLOAD_MANAGER.issue(
            path=f"{TEAM_ROOT}/Images/O'Neal & Jünger.jpg",
            name="O'Neal & Jünger.jpg",
            media_type="image/jpeg",
            size=8,
            user_id="worker-1",
        )
        request = files_upload_api.Request(
            {
                "type": "http",
                "method": "GET",
                "path": f"/api/files-drag/{record.token}",
                "path_params": {"token": record.token},
                "query_string": b"",
                "headers": [],
                "scheme": "https",
                "server": ("sports-cave.test", 443),
            }
        )
        upstream = type(
            "Upstream",
            (),
            {
                "iter_content": lambda self, chunk_size: iter((b"ORIGINAL",)),
                "close": lambda self: setattr(self, "closed", True),
                "closed": False,
            },
        )()
        with patch.object(
            files_upload_api,
            "_dropbox_context",
            return_value={"access_token": "token", "root_path": TEAM_ROOT},
        ), patch.object(
            files_upload_api.dropbox_integration,
            "get_file_response",
            return_value=({"size": 8}, upstream),
        ), patch.object(
            files_upload_api.dropbox_integration,
            "delete_path_recoverable",
        ) as delete_source:
            response = asyncio.run(files_upload_api.drag_file(request))
            content = asyncio.run(response_bytes(response))

        self.assertEqual(content, b"ORIGINAL")
        self.assertEqual(response.media_type, "image/jpeg")
        self.assertIn("attachment", response.headers["content-disposition"])
        self.assertIn("O%27Neal%20%26%20J%C3%BCnger.jpg", response.headers["content-disposition"])
        self.assertTrue(upstream.closed)
        delete_source.assert_not_called()

    def test_drag_token_creation_revalidates_relative_paths_and_exposes_no_cloud_secret(self):
        relative = "Images/O'Neal & J\u00fcnger.jpg"
        request = json_request("/api/files-drag-token", {"paths": [relative]})
        with patch.object(files_upload_api, "_request_user", return_value=self.user), patch.object(
            files_upload_api,
            "_dropbox_context",
            return_value={"access_token": "secret-token", "root_path": TEAM_ROOT},
        ), patch.object(
            files_upload_api.dropbox_integration,
            "get_file_metadata",
            return_value={
                ".tag": "file",
                "name": "O'Neal & J\u00fcnger.jpg",
                "size": 123,
            },
        ) as metadata:
            response = asyncio.run(files_upload_api.create_drag_tokens(request))

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["downloads"][0]["name"], "O'Neal & J\u00fcnger.jpg")
        self.assertEqual(payload["downloads"][0]["media_type"], "image/jpeg")
        self.assertTrue(payload["downloads"][0]["url"].startswith("/api/files-drag/"))
        self.assertNotIn("secret-token", response.body.decode("utf-8"))
        self.assertNotIn(TEAM_ROOT, response.body.decode("utf-8"))
        metadata.assert_called_once_with("secret-token", f"{TEAM_ROOT}/{relative}")

        denied = json_request("/api/files-drag-token", {"paths": ["../outside.jpg"]})
        with patch.object(files_upload_api, "_request_user", return_value=self.user), patch.object(
            files_upload_api,
            "_dropbox_context",
            return_value={"access_token": "secret-token", "root_path": TEAM_ROOT},
        ), patch.object(files_upload_api.dropbox_integration, "get_file_metadata") as denied_metadata:
            denied_response = asyncio.run(files_upload_api.create_drag_tokens(denied))
        self.assertEqual(denied_response.status_code, 403)
        denied_metadata.assert_not_called()


class FilesWindowInteractionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = (ROOT / "app.py").read_text(encoding="utf-8")
        cls.launcher = (
            ROOT / "components" / "files_window_launcher" / "index.html"
        ).read_text(encoding="utf-8")
        cls.client = (ROOT / "components" / "files_window" / "index.html").read_text(
            encoding="utf-8"
        )
        cls.viewer = (
            ROOT / "components" / "files_image_viewer" / "index.html"
        ).read_text(encoding="utf-8")

    def test_files_sidebar_uses_one_named_centered_window_and_keeps_main_page(self):
        self.assertIn('const FILES_WINDOW_NAME = "sports-cave-files"', self.launcher)
        self.assertIn('parentWindow.open("", FILES_WINDOW_NAME, filesWindowFeatures())', self.launcher)
        self.assertIn("width=${width},height=${height},left=${left},top=${top}", self.launcher)
        self.assertIn("parentWindow.__sportsCaveFilesWindow", self.launcher)
        self.assertIn("filesWindow.focus()", self.launcher)
        self.assertIn("The browser blocked the popup", self.launcher)
        branch = self.app[self.app.index('if page == "Files":') : self.app.index("if st.sidebar.button(", self.app.index('if page == "Files":'))]
        self.assertIn("_files_window_launcher_component", branch)
        self.assertIn("continue", branch)
        self.assertNotIn("set_current_page", branch)

    def test_one_click_open_checkbox_multi_select_and_keyboard_navigation_are_explicit(self):
        item_handler = self.client[self.client.index("function createItemElement") : self.client.index("function detailCell")]
        self.assertIn('row.addEventListener("click"', item_handler)
        self.assertIn("setSingleSelection(item.path, index)", item_handler)
        self.assertIn("openItem(item)", item_handler)
        self.assertIn('checkbox.type = "checkbox"', item_handler)
        self.assertIn("event.ctrlKey || event.metaKey", item_handler)
        self.assertIn("event.shiftKey", item_handler)
        self.assertIn('row.addEventListener("contextmenu"', item_handler)
        self.assertIn("if (!state.selection.has(item.path)) setSingleSelection", item_handler)
        self.assertIn('event.key === "Enter"', self.client)
        self.assertIn('event.key === "Escape"', self.client)
        self.assertIn('event.key === "Backspace"', self.client)
        self.assertIn('event.altKey && event.key === "ArrowLeft"', self.client)

    def test_open_never_downloads_and_psd_uses_desktop_helper_protocol(self):
        open_block = self.client[self.client.index("function desktopApplication") : self.client.index("function startDownload")]
        self.assertIn('item.kind === "photoshop"', open_block)
        self.assertIn('return "Photoshop"', open_block)
        self.assertIn('"sports-cave-photoshop"', open_block)
        self.assertIn('"sports-cave-files"', open_block)
        self.assertIn("function desktopProtocolScheme", open_block)
        self.assertIn("function isWindowsPlatform()", open_block)
        self.assertIn("return /Win/i.test(platform)", open_block)
        self.assertIn("const protocolUrl = `${scheme}://open?path=", open_block)
        self.assertIn("item.desktop_relative_path", open_block)
        self.assertNotIn("/api/files-download", open_block)
        self.assertIn("Opening in ${application}...", open_block)
        self.assertIn("elements.protocolLink.click()", open_block)
        self.assertIn("File didn't open?", self.client)
        self.assertIn("Check desktop helper", self.client)
        self.assertIn("Reinstall helper", self.client)
        self.assertIn("Download instead", self.client)

    def test_every_standard_open_action_uses_the_authoritative_open_item(self):
        self.assertEqual(self.client.count("function openItem(item)"), 1)
        self.assertIn("elements.openButton.onclick = () => openItem(selectedItems()[0])", self.client)
        self.assertIn('{ label: "Open", disabled: !single, action: () => openItem(item) }', self.client)
        self.assertIn('if (event.key === "Enter")', self.client)
        item_handler = self.client[self.client.index("function createItemElement") : self.client.index("function detailCell")]
        self.assertIn("openItem(item)", item_handler)

    def test_toolbar_download_enablement_order_context_menus_and_confirmation(self):
        self.assertIn('id="openButton"', self.client)
        self.assertIn("elements.openButton.disabled = chosen.length !== 1", self.client)
        command_bar = self.client[self.client.index('id="newButton"') : self.client.index('id="moreButton"') + 120]
        order = [command_bar.index(f'id="{name}Button"') for name in ("new", "upload", "download", "rename", "delete", "sort", "view", "more")]
        self.assertEqual(order, sorted(order))
        selection = self.client[self.client.index("function updateSelectionUi") : self.client.index("function setSingleSelection")]
        self.assertIn("chosen.every(item => item.tag !== \"folder\")", selection)
        self.assertIn("elements.downloadButton.disabled = !allFiles", selection)
        for label in ("Open", "Download", "Rename", "Delete", "Copy path", "Properties"):
            self.assertIn(f'label: "{label}"', self.client)
        self.assertIn(': "Open in Windows File Explorer"', self.client)
        self.assertIn('? "Open in Finder"', self.client)
        self.assertIn('label: "Open in desktop app"', self.client)
        for label in ("New folder", "Upload", "Refresh", "Sort by", "View"):
            self.assertIn(f'label: "{label}"', self.client)
        self.assertIn("items.forEach(item =>", self.client)
        self.assertIn("row.textContent = item.name", self.client)
        self.assertIn("Delete ${countText}?", self.client)

    def test_all_views_sort_and_folder_search_persist_across_refresh(self):
        for view in ("large", "medium", "small", "list", "details"):
            self.assertIn(view, self.client)
        for sort_key in ("name", "modified", "type", "size"):
            self.assertIn(sort_key, self.client)
        self.assertIn("localStorage.setItem(STORAGE_KEY", self.client)
        self.assertIn("currentPath: state.currentPath", self.client)
        self.assertIn("searchByPath: state.searchByPath", self.client)
        self.assertIn("history.replaceState", self.client)

    def test_results_own_scroll_viewport_and_thumbnail_work_is_bounded(self):
        self.assertIn("grid-template-rows: auto auto auto minmax(0, 1fr) 27px", self.client)
        self.assertIn("overflow-y: auto", self.client)
        self.assertIn("overflow: hidden", self.client)
        self.assertIn("new IntersectionObserver", self.client)
        self.assertIn('rootMargin: "240px 0px"', self.client)
        self.assertIn("MAX_THUMBNAIL_CONCURRENT = 4", self.client)
        self.assertIn("state.thumbnailControllers.forEach(controller => controller.abort())", self.client)
        self.assertIn('event.key === "PageDown"', self.client)
        self.assertIn('event.key === "Home"', self.client)
        self.assertIn('event.key === "End"', self.client)

    def test_drag_drop_uses_chunked_upload_progress_and_prevents_browser_navigation(self):
        self.assertIn('window.addEventListener("dragover"', self.client)
        self.assertIn('window.addEventListener("drop"', self.client)
        self.assertIn("event.preventDefault()", self.client)
        self.assertIn("droppedItems(event.dataTransfer)", self.client)
        self.assertIn("row.file.slice(row.uploaded, end)", self.client)
        self.assertIn("const CHUNK_BYTES = 8 * 1024 * 1024", self.client)
        self.assertIn("Uploading ${percent}%", self.client)
        self.assertIn("MAX_UPLOAD_CONCURRENT = 2", self.client)

    def test_files_surface_is_neutral_and_psd_icon_has_windows_photoshop_details(self):
        self.assertNotIn("#D4A54C", self.client.upper())
        self.assertNotIn("#E1B23D", self.client.upper())
        self.assertIn('fill="#001d35"', self.client)
        self.assertIn('stroke="#23a8f2"', self.client)
        self.assertIn('>Ps</text>', self.client)
        self.assertIn('${label}</text>', self.client)
        self.assertIn("overflow-wrap: anywhere", self.client)

    def test_images_open_in_one_reused_named_window_with_blocked_popup_fallback(self):
        open_block = self.client[self.client.index("function imageViewerFeatures") : self.client.index("function downloadHelper")]
        self.assertIn('window.open(viewerUrl, "sports-cave-image-viewer"', open_block)
        self.assertIn("state.imageViewerWindow.postMessage", open_block)
        self.assertIn("state.imageViewerWindow.focus()", open_block)
        self.assertIn('actionLabel: "Open image viewer"', open_block)
        self.assertIn('item.kind === "image"', open_block)

    def test_no_inline_image_preview_and_viewer_has_full_interaction_contract(self):
        self.assertNotIn("image-preview", self.client)
        self.assertIn('/api/files-image-preview?path=', self.viewer)
        self.assertIn('/api/files-image-items?folder=', self.viewer)
        self.assertIn('window.addEventListener("message"', self.viewer)
        self.assertIn('event.key === "ArrowLeft"', self.viewer)
        self.assertIn('event.key === "+"', self.viewer)
        self.assertIn('event.key === "0"', self.viewer)
        self.assertIn('event.key === "Escape"', self.viewer)
        self.assertIn('elements.stage.addEventListener("wheel"', self.viewer)
        self.assertIn('elements.stage.addEventListener("pointermove"', self.viewer)
        for control in ("previousButton", "nextButton", "zoomOutButton", "zoomInButton", "fitButton", "actualButton", "rotateLeftButton", "rotateRightButton", "downloadButton", "desktopButton", "closeButton"):
            self.assertIn(f'id="{control}"', self.viewer)

    def test_viewer_has_no_stale_loading_overlay_and_streams_directly_into_image(self):
        self.assertNotIn("Image could not be opened", self.viewer)
        self.assertNotIn("Loading image", self.viewer)
        self.assertNotIn('class="spinner"', self.viewer)
        self.assertNotIn("response.blob()", self.viewer)
        self.assertNotIn("URL.createObjectURL", self.viewer)
        self.assertIn('decoding="async"', self.viewer)
        self.assertIn('fetchpriority="high"', self.viewer)
        self.assertIn("const generation = ++state.loadGeneration", self.viewer)
        self.assertIn('elements.image.src = `/api/files-image-preview?path=', self.viewer)
        self.assertIn('elements.image.style.display = "block"', self.viewer)
        self.assertIn("if (generation !== state.loadGeneration) return", self.viewer)

    def test_cut_copy_paste_context_menus_keyboard_and_session_persistence(self):
        self.assertIn('const CLIPBOARD_KEY = "sports-cave-files-clipboard-v1"', self.client)
        self.assertIn("sessionStorage.getItem(CLIPBOARD_KEY)", self.client)
        self.assertIn("sessionStorage.setItem(CLIPBOARD_KEY", self.client)
        self.assertIn("function setFilesClipboard(mode", self.client)
        self.assertIn("function pasteFiles(conflict", self.client)
        self.assertIn('apiJson("/api/files-paste"', self.client)
        self.assertIn('operation === "move" && successful.length', self.client)
        self.assertIn("const movedPaths = new Set", self.client)
        self.assertIn("Failed items remain in the clipboard", self.client)
        self.assertIn("Skipped items remain in the clipboard", self.client)
        self.assertIn(".file-item.cut-pending", self.client)
        for label in ("Cut", "Copy", "Paste"):
            self.assertIn(f'label: "{label}"', self.client)
        for choice in ("Skip", "Keep both", "Replace"):
            self.assertIn(f'choice("{choice}"', self.client)
        self.assertIn("event.target.matches(\"input, textarea, select, [contenteditable='true']\")", self.client)
        self.assertIn('shortcut && key === "c"', self.client)
        self.assertIn('shortcut && key === "x"', self.client)
        self.assertIn('shortcut && key === "v"', self.client)
        self.assertIn('event.key === "Delete"', self.client)
        self.assertIn('event.key === "F2"', self.client)

    def test_external_drag_prepares_only_selection_and_supplies_real_file_and_download_url(self):
        self.assertIn("function prepareExternalDrag(items, key)", self.client)
        self.assertIn('apiJson("/api/files-drag-token"', self.client)
        self.assertIn("items.map(item => item.desktop_relative_path)", self.client)
        self.assertIn("files.push(new File([blob], download.name", self.client)
        self.assertIn("event.dataTransfer.items.add(file)", self.client)
        self.assertIn('event.dataTransfer.setData(\n            "DownloadURL"', self.client)
        self.assertIn('event.dataTransfer.setData("text/uri-list"', self.client)
        self.assertIn('event.dataTransfer.effectAllowed = "copy"', self.client)
        self.assertIn('event.dataTransfer.dropEffect = "copy"', self.client)
        self.assertIn('showToast("Preparing file..."', self.client)
        self.assertIn('showToast("Ready to drag"', self.client)
        self.assertIn("state.suppressClickUntil", self.client)
        self.assertIn("createDragGhost(item, items.length)", self.client)
        drag_block = self.client[
            self.client.index("function externalDragItems") :
            self.client.index("function showItemContextMenu")
        ]
        self.assertNotIn("/api/files-delete", drag_block)
        self.assertNotIn("operation: \"move\"", drag_block)

    def test_copy_and_cut_also_request_native_windows_file_clipboard(self):
        block = self.client[
            self.client.index("function invokeDesktopClipboard") :
            self.client.index("function invokeDesktopHelper")
        ]
        self.assertIn("sports-cave-files://clipboard?paths=", block)
        self.assertIn("encodeURIComponent(JSON.stringify(paths))", block)
        self.assertIn('effect === "move" ? "move" : "copy"', block)
        self.assertIn('mode === "cut" ? "move" : "copy"', self.client)


if __name__ == "__main__":
    unittest.main()
