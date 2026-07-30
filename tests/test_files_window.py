import asyncio
import io
import json
from pathlib import Path
import threading
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


def authenticated_get_request(path, user_id):
    token = files_upload_api.sc_auth.create_user_auth_token(
        user_id,
        password=files_upload_api.sc_auth.DEFAULT_APP_PASSWORD,
    )
    return files_upload_api.Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "query_string": b"",
            "headers": [
                (
                    b"cookie",
                    f"{files_upload_api.sc_auth.AUTH_COOKIE_NAME}={token}".encode(
                        "ascii"
                    ),
                )
            ],
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
            "timezone": "Asia/Manila",
            "is_active": True,
            "page_permissions": ["files"],
        }
        files_upload_api._DIRECTORY_CACHE.clear()

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

    def test_files_auth_gate_requires_explicit_permission_and_active_account(self):
        allowed = {**self.user, "id": "worker-files"}
        without_permission = {
            **self.user,
            "id": "worker-no-files",
            "page_permissions": ["dashboard"],
        }
        inactive = {
            **self.user,
            "id": "worker-inactive",
            "is_active": False,
        }

        with patch.object(
            files_upload_api.os_accounts.DEFAULT_STORE,
            "get_user",
            return_value=allowed,
        ):
            user = files_upload_api._request_user(
                authenticated_get_request("/files-window", allowed["id"])
            )
        self.assertEqual(user["id"], allowed["id"])

        for blocked in (without_permission, inactive):
            with self.subTest(user=blocked["id"]), patch.object(
                files_upload_api.os_accounts.DEFAULT_STORE,
                "get_user",
                return_value=blocked,
            ):
                with self.assertRaises(files_upload_api.FilesUploadError) as caught:
                    files_upload_api._request_user(
                        authenticated_get_request("/files-window", blocked["id"])
                    )
                self.assertEqual(caught.exception.status_code, 403)
                self.assertEqual(caught.exception.code, "access_denied")

    def test_direct_files_window_route_cannot_bypass_permission_check(self):
        worker = {
            **self.user,
            "id": "worker-direct-denied",
            "page_permissions": ["dashboard"],
        }
        request = authenticated_get_request("/files-window", worker["id"])

        with patch.object(
            files_upload_api.os_accounts.DEFAULT_STORE,
            "get_user",
            return_value=worker,
        ):
            response = asyncio.run(files_upload_api.files_window_page(request))

        self.assertEqual(response.status_code, 403)
        self.assertIn("Files access is not approved", response.body.decode("utf-8"))

    def test_files_view_permission_does_not_grant_delete_permission(self):
        viewer = {**self.user, "id": "worker-view-only"}
        request = authenticated_get_request("/api/files-delete", viewer["id"])

        with patch.object(
            files_upload_api.os_accounts.DEFAULT_STORE,
            "get_user",
            return_value=viewer,
        ):
            with self.assertRaises(files_upload_api.FilesUploadError) as caught:
                files_upload_api._request_files_delete_user(request)

        self.assertEqual(caught.exception.status_code, 403)
        self.assertEqual(caught.exception.code, "access_denied")

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
        self.assertEqual(payload["items"][0]["modified"], "2026-07-23T00:10:00Z")
        self.assertEqual(payload["items"][0]["modified_label"], "23 Jul 2026, 8:10 AM")
        self.assertEqual(payload["items"][0]["modified_tooltip_label"], "23 Jul 2026, 8:10 AM PHT")
        self.assertEqual(payload["timezone"], "Asia/Manila")
        self.assertNotIn("thumbnail_url", payload["items"][0])
        self.assertIn("thumbnail_url", payload["items"][1])
        self.assertNotIn("secret-token", response.body.decode("utf-8"))
        directory.assert_called_once_with(
            "secret-token",
            path,
            force=False,
            root_path=TEAM_ROOT,
            user_id="worker-1",
        )

    def test_timestamp_formatting_converts_to_configured_timezone_and_handles_missing_values(self):
        value = "2026-07-25T02:41:00Z"
        self.assertEqual(
            files_upload_api._format_files_timestamp(value, "Asia/Manila"),
            "25 Jul 2026, 10:41 AM",
        )
        self.assertEqual(
            files_upload_api._format_files_timestamp(
                value,
                "Asia/Manila",
                include_zone=True,
            ),
            "25 Jul 2026, 10:41 AM PHT",
        )
        self.assertEqual(
            files_upload_api._format_files_timestamp(value, "Australia/Sydney"),
            "25 Jul 2026, 12:41 PM",
        )
        self.assertEqual(files_upload_api._format_files_timestamp("", "Asia/Manila"), "-")
        self.assertEqual(files_upload_api._format_files_timestamp("not-a-date", "Asia/Manila"), "-")

    def test_tooltip_metadata_uses_cached_dimensions_only_and_omits_folder_modified_time(self):
        image = files_upload_api._public_file_item(
            {
                ".tag": "file",
                "name": "Campaign.png",
                "path_display": f"{TEAM_ROOT}/Campaign.png",
                "server_modified": "2026-07-25T02:41:00Z",
                "size": 2_107_392,
                "dimensions": {"width": 1448, "height": 1086},
            },
            TEAM_ROOT,
            timezone_name="Asia/Manila",
        )
        image_without_dimensions = files_upload_api._public_file_item(
            {
                ".tag": "file",
                "name": "Preview.jpg",
                "path_display": f"{TEAM_ROOT}/Preview.jpg",
                "server_modified": "2026-07-25T02:41:00Z",
                "size": 10,
            },
            TEAM_ROOT,
            timezone_name="Asia/Manila",
        )
        document = files_upload_api._public_file_item(
            {
                ".tag": "file",
                "name": "Brief.pdf",
                "path_display": f"{TEAM_ROOT}/Brief.pdf",
                "server_modified": "invalid",
                "size": 512,
                "dimensions": {"width": 99, "height": 88},
            },
            TEAM_ROOT,
            timezone_name="Asia/Manila",
        )
        folder = files_upload_api._public_file_item(
            {
                ".tag": "folder",
                "name": "Approved",
                "path_display": f"{TEAM_ROOT}/Approved",
                "server_modified": "2026-07-25T02:41:00Z",
            },
            TEAM_ROOT,
            timezone_name="Asia/Manila",
        )
        folder_with_activity = files_upload_api._public_file_item(
            {
                ".tag": "folder",
                "name": "Archive",
                "path_display": f"{TEAM_ROOT}/Archive",
                "latest_known_activity": "2026-07-25T02:41:00Z",
            },
            TEAM_ROOT,
            timezone_name="Asia/Manila",
        )

        self.assertEqual(image["tooltip_type"], "PNG File")
        self.assertEqual(image["tooltip_size_label"], "2.01 MB")
        self.assertEqual(image["dimensions"], {"width": 1448, "height": 1086})
        self.assertNotIn("dimensions", image_without_dimensions)
        self.assertEqual(document["modified_label"], "-")
        self.assertNotIn("dimensions", document)
        self.assertEqual(folder["tooltip_type"], "File folder")
        self.assertEqual(folder["modified"], "")
        self.assertEqual(folder["modified_label"], "-")
        self.assertEqual(folder["latest_activity"], "")
        self.assertEqual(
            folder_with_activity["latest_activity_tooltip_label"],
            "25 Jul 2026, 10:41 AM PHT",
        )

    def test_listing_many_rows_does_not_fetch_per_row_metadata_or_thumbnails(self):
        entries = [
            {
                ".tag": "file",
                "name": f"Image {index}.png",
                "path_display": f"{TEAM_ROOT}/Image {index}.png",
                "server_modified": f"2026-07-25T02:{index:02d}:00Z",
                "size": index + 1,
                "rev": f"rev-{index}",
            }
            for index in range(20)
        ]
        request = get_request("/api/files-list", {"path": TEAM_ROOT})
        with patch.object(files_upload_api, "_request_user", return_value=self.user), patch.object(
            files_upload_api,
            "_dropbox_context",
            return_value={"access_token": "secret-token", "root_path": TEAM_ROOT},
        ), patch.object(
            files_upload_api,
            "_directory_entries",
            return_value=entries,
        ) as directory, patch.object(
            files_upload_api.dropbox_integration,
            "get_file_metadata",
        ) as metadata, patch.object(
            files_upload_api,
            "_thumbnail_bytes",
        ) as thumbnail:
            response = asyncio.run(files_upload_api.list_files(request))

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(payload["items"]), 20)
        directory.assert_called_once_with(
            "secret-token",
            TEAM_ROOT,
            force=False,
            root_path=TEAM_ROOT,
            user_id="worker-1",
        )
        metadata.assert_not_called()
        thumbnail.assert_not_called()

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

    def test_image_preview_supports_root_level_unicode_and_special_characters(self):
        relative = "O'Neal & J\u00fcrgen Final.png"
        request = get_request("/api/files-image-preview", {"path": relative})
        upstream = type(
            "Upstream",
            (),
            {
                "content": b"PNG",
                "close": lambda self: None,
            },
        )()
        with patch.object(files_upload_api, "_request_user", return_value=self.user), patch.object(
            files_upload_api,
            "_dropbox_context",
            return_value={"access_token": "secret-token", "root_path": TEAM_ROOT},
        ), patch.object(
            files_upload_api.dropbox_integration,
            "get_file_response",
            return_value=({".tag": "file", "size": 3}, upstream),
        ) as download:
            response = asyncio.run(files_upload_api.image_preview(request))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(asyncio.run(response_bytes(response)), b"PNG")
        self.assertEqual(response.media_type, "image/png")
        download.assert_called_once_with(
            "secret-token",
            f"{TEAM_ROOT}/{relative}",
        )

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

    def test_native_transfer_manifest_is_revision_scoped_and_keeps_unicode_names(self):
        manager = files_upload_api.NativeTransferManager()
        relative = "Designs/O'Neal & J\u00fcrgen.psd"
        full_path = f"{TEAM_ROOT}/{relative}"
        metadata = {
            ".tag": "file",
            "id": "id:unicode-file",
            "name": "O'Neal & J\u00fcrgen.psd",
            "path_display": full_path,
            "size": 27,
            "rev": "revision-9",
        }
        with patch.object(
            files_upload_api.dropbox_integration,
            "get_file_metadata",
            return_value=metadata,
        ):
            record = manager.create(
                access_token="server-only-token",
                root_path=TEAM_ROOT,
                user=self.user,
                selections=[
                    {
                        "path": relative,
                        "id": "id:unicode-file",
                        "revision": "revision-9",
                        "tag": "file",
                    }
                ],
            )

        self.assertEqual(record.items[0]["relative_path"], "O'Neal & J\u00fcrgen.psd")
        self.assertEqual(record.items[0]["revision"], "revision-9")
        self.assertEqual(
            record.roots,
            [
                {
                    "source_relative_path": relative,
                    "name": "O'Neal & J\u00fcrgen.psd",
                    "is_directory": False,
                    "revision": "revision-9",
                }
            ],
        )
        self.assertNotIn("server-only-token", json.dumps(record.items))
        self.assertIs(manager.get(record.ticket, record.secret), record)
        with self.assertRaises(files_upload_api.FilesUploadError):
            manager.get(record.ticket, "wrong-secret")

    def test_native_transfer_rejects_traversal_absolute_and_wrong_dropbox_identity(self):
        manager = files_upload_api.NativeTransferManager()
        for invalid in ("../outside.jpg", "/absolute.jpg", "C:/Windows/file.jpg"):
            with self.subTest(invalid=invalid), self.assertRaises(
                files_upload_api.FilesUploadError
            ):
                manager.create(
                    access_token="token",
                    root_path=TEAM_ROOT,
                    user=self.user,
                    selections=[{"path": invalid}],
                )
        with patch.object(
            files_upload_api.dropbox_integration,
            "get_file_metadata",
            return_value={
                ".tag": "file",
                "id": "id:actual",
                "name": "Image.jpg",
                "path_display": f"{TEAM_ROOT}/Image.jpg",
                "size": 1,
                "rev": "r1",
            },
        ):
            with self.assertRaises(files_upload_api.FilesUploadError) as caught:
                manager.create(
                    access_token="token",
                    root_path=TEAM_ROOT,
                    user=self.user,
                    selections=[{"path": "Image.jpg", "id": "id:forged"}],
                )
        self.assertEqual(caught.exception.code, "item_changed")

    def test_native_folder_manifest_preserves_tree_and_empty_folders(self):
        manager = files_upload_api.NativeTransferManager()
        folder = f"{TEAM_ROOT}/Campaign"
        with patch.object(
            files_upload_api.dropbox_integration,
            "get_file_metadata",
            return_value={
                ".tag": "folder",
                "id": "id:folder",
                "name": "Campaign",
                "path_display": folder,
            },
        ), patch.object(
            files_upload_api.dropbox_integration,
            "list_folder_recursive",
            return_value=[
                {
                    ".tag": "folder",
                    "id": "id:nested",
                    "name": "Empty",
                    "path_display": f"{folder}/Empty",
                },
                {
                    ".tag": "file",
                    "id": "id:file",
                    "name": "Final.png",
                    "path_display": f"{folder}/Final.png",
                    "size": 4,
                    "rev": "r2",
                },
            ],
        ):
            record = manager.create(
                access_token="token",
                root_path=TEAM_ROOT,
                user=self.user,
                selections=[{"path": "Campaign", "id": "id:folder"}],
            )
        self.assertEqual(
            [item["relative_path"] for item in record.items],
            ["Campaign", "Campaign/Empty", "Campaign/Final.png"],
        )
        self.assertEqual(
            [item["is_directory"] for item in record.items],
            [True, True, False],
        )
        self.assertEqual(record.roots[0]["source_relative_path"], "Campaign")
        self.assertTrue(record.roots[0]["is_directory"])

    def test_helper_package_selects_real_windows_and_macos_installers(self):
        for platform, expected in (("windows", "Install.ps1"), ("macos", "Install.command")):
            request = get_request("/api/files-desktop-helper", {"platform": platform})
            with patch.object(files_upload_api, "_request_user", return_value=self.user):
                response = asyncio.run(files_upload_api.desktop_helper_package(request))
            with zipfile.ZipFile(io.BytesIO(response.body)) as archive:
                self.assertIn(expected, archive.namelist())
                if platform == "windows":
                    self.assertIn("SportsCaveFiles.ico", archive.namelist())
                    self.assertIn("SportsCaveFilesDesktop.cs", archive.namelist())
                    self.assertIn("lib/Microsoft.Web.WebView2.Core.dll", archive.namelist())
                    self.assertIn("lib/Microsoft.Web.WebView2.Wpf.dll", archive.namelist())
                    self.assertIn("runtimes/win-x64/native/WebView2Loader.dll", archive.namelist())
                    self.assertIn("SportsCaveFilesHelper.ps1", archive.namelist())
                    self.assertNotIn("PhotoshopProtocolLauncher.cs", archive.namelist())
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

    def test_directory_cache_is_scoped_by_user_root_and_path(self):
        first_root = "/Sportscave Team Folder"
        second_root = "/Other Team Folder"
        path = f"{first_root}/Designs"
        with patch.object(
            files_upload_api.dropbox_integration,
            "list_folder",
            side_effect=[
                [{"name": "worker"}],
                [{"name": "admin"}],
                [{"name": "other-root"}],
            ],
        ) as listing:
            self.assertEqual(
                files_upload_api._directory_entries("token", path, root_path=first_root, user_id="worker")[0]["name"],
                "worker",
            )
            self.assertEqual(
                files_upload_api._directory_entries("token", path, root_path=first_root, user_id="worker")[0]["name"],
                "worker",
            )
            self.assertEqual(
                files_upload_api._directory_entries("token", path, root_path=first_root, user_id="admin")[0]["name"],
                "admin",
            )
            self.assertEqual(
                files_upload_api._directory_entries("token", path, root_path=second_root, user_id="worker")[0]["name"],
                "other-root",
            )

        self.assertEqual(listing.call_count, 3)

    def test_identical_inflight_directory_requests_share_one_dropbox_listing(self):
        path = f"{TEAM_ROOT}/Concurrent"
        gate = threading.Event()
        calls = 0

        def slow_listing(_token, _path):
            nonlocal calls
            calls += 1
            gate.wait(timeout=2)
            return [{"name": "shared"}]

        results = []
        errors = []

        def worker():
            try:
                results.append(
                    files_upload_api._directory_entries(
                        "token",
                        path,
                        root_path=TEAM_ROOT,
                        user_id="worker-1",
                    )[0]["name"]
                )
            except Exception as error:
                errors.append(error)

        with patch.object(files_upload_api.dropbox_integration, "list_folder", side_effect=slow_listing):
            first = threading.Thread(target=worker)
            second = threading.Thread(target=worker)
            first.start()
            second.start()
            gate.set()
            first.join(timeout=3)
            second.join(timeout=3)

        self.assertFalse(errors)
        self.assertEqual(results, ["shared", "shared"])
        self.assertEqual(calls, 1)

    def test_files_list_can_return_first_page_then_append_later_pages(self):
        path = f"{TEAM_ROOT}/Large"
        first_page = {
            "entries": [
                {".tag": "file", "name": "A.jpg", "path_display": f"{path}/A.jpg", "rev": "a"},
            ],
            "cursor": "cursor-1",
            "has_more": True,
        }
        second_page = {
            "entries": [
                {".tag": "file", "name": "B.jpg", "path_display": f"{path}/B.jpg", "rev": "b"},
            ],
            "cursor": "",
            "has_more": False,
        }
        with patch.object(files_upload_api, "_request_user", return_value=self.user), patch.object(
            files_upload_api,
            "_dropbox_context",
            return_value={"access_token": "secret-token", "root_path": TEAM_ROOT},
        ), patch.object(
            files_upload_api.dropbox_integration,
            "list_folder_page",
            side_effect=[first_page, second_page],
        ) as listing:
            first_response = asyncio.run(
                files_upload_api.list_files(
                    get_request("/api/files-list", {"path": path, "page_size": "1"})
                )
            )
            first_payload = json.loads(first_response.body)
            second_response = asyncio.run(
                files_upload_api.list_files(
                    get_request(
                        "/api/files-list",
                        {"path": path, "page_size": "1", "page": first_payload["next_page"]},
                    )
                )
            )

        second_payload = json.loads(second_response.body)
        self.assertEqual(first_response.status_code, 200)
        self.assertEqual([item["name"] for item in first_payload["items"]], ["A.jpg"])
        self.assertTrue(first_payload["has_more"])
        self.assertTrue(first_payload["next_page"])
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual([item["name"] for item in second_payload["items"]], ["A.jpg", "B.jpg"])
        self.assertFalse(second_payload["has_more"])
        self.assertFalse(second_payload["next_page"])
        self.assertIn("cache_namespace", first_payload)
        self.assertEqual(listing.call_count, 2)

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
        self.assertEqual(routes["/api/files-native-transfer"], ("POST",))
        self.assertEqual(routes["/api/files-native-transfer/manifest"], ("GET",))
        self.assertEqual(routes["/api/files-native-transfer/content"], ("GET",))
        self.assertEqual(routes["/api/files-delete"], ("POST",))
        self.assertEqual(routes["/api/files-paste"], ("POST",))
        self.assertNotIn("/api/files-drag-token", routes)
        self.assertNotIn("/api/files-drag/{token}", routes)

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

    def test_files_sidebar_opens_browser_window_for_approved_accounts(self):
        self.assertIn('window.open("/files-window"', self.launcher)
        self.assertIn('"sports-cave-files-window"', self.launcher)
        self.assertIn("popup.focus()", self.launcher)
        self.assertNotIn('href="sports-cave-files://app"', self.launcher)
        self.assertNotIn("desktopLink.click()", self.launcher)
        self.assertNotIn("parentWindow.open", self.launcher)
        self.assertIn("openBrowserFilesWindow", self.launcher)
        self.assertNotIn("fallbackTimer", self.launcher)
        self.assertNotIn("window.setTimeout", self.launcher)
        self.assertNotIn("Sports Cave Desktop did not open", self.launcher)
        branch = self.app[self.app.index('if page == "Files":') : self.app.index("if st.sidebar.button(", self.app.index('if page == "Files":'))]
        self.assertIn("_files_window_launcher_component", branch)
        self.assertIn("continue", branch)
        self.assertNotIn("set_current_page", branch)

    def test_one_click_open_multi_select_and_keyboard_navigation_have_no_checkboxes(self):
        item_handler = self.client[self.client.index("function createItemElement") : self.client.index("function detailCell")]
        self.assertIn('row.addEventListener("click"', item_handler)
        self.assertIn("setSingleSelection(item.path, index)", item_handler)
        self.assertIn("openItem(item)", item_handler)
        self.assertNotIn("item-checkbox", self.client)
        self.assertNotIn('document.createElement("input")', item_handler)
        self.assertIn("event.ctrlKey || event.metaKey", item_handler)
        self.assertIn("event.shiftKey", item_handler)
        self.assertIn('row.addEventListener("contextmenu"', item_handler)
        self.assertIn("if (!state.selection.has(item.path)) setSingleSelection", item_handler)
        self.assertIn('event.key === "Enter"', self.client)
        self.assertIn('event.key === "Escape"', self.client)
        self.assertIn('event.key === "Backspace"', self.client)
        self.assertIn('event.altKey && event.key === "ArrowLeft"', self.client)

    def test_open_never_downloads_and_uses_desktop_bridge(self):
        open_block = self.client[self.client.index("function desktopApplication") : self.client.index("function startDownload")]
        self.assertIn('item.kind === "photoshop"', open_block)
        self.assertIn('return "Photoshop"', open_block)
        self.assertIn('desktopRequest("openFile", [item])', open_block)
        self.assertIn('hasDesktopCapability("openFile")', open_block)
        self.assertIn("item.desktop_relative_path", open_block)
        self.assertNotIn("/api/files-download", open_block)
        self.assertIn("Opening in ${application}...", open_block)
        self.assertIn('elements.protocolLink.href = "sports-cave-files://app"', open_block)
        self.assertIn("elements.protocolLink.click()", open_block)
        self.assertNotIn("Sports Cave Desktop required", self.client)
        self.assertNotIn("Update Sports Cave Desktop to enable native drag and Copy.", self.client)
        self.assertNotIn("Sports Cave Desktop did not open.", self.client)
        self.assertNotIn('elements.helperPanel.classList.add("visible")', self.client)

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
        item_menu = self.client[
            self.client.index("function showItemContextMenu") :
            self.client.index("function showEmptyContextMenu")
        ]
        self.assertNotIn('label: "Open in desktop app"', item_menu)
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

    def test_date_modified_sort_and_timezone_formatting_use_raw_utc_metadata(self):
        sort_block = self.client[
            self.client.index("function visibleItems") :
            self.client.index("function renderBreadcrumbs")
        ]
        self.assertIn('Date.parse(left.modified || "")', sort_block)
        self.assertIn('Date.parse(right.modified || "")', sort_block)
        self.assertIn("if (left.tag !== right.tag)", sort_block)
        self.assertIn('left.tag === "folder" ? -1 : 1', sort_block)
        self.assertIn('Date modified \\u2014 newest first', self.client)
        self.assertIn('Date modified \\u2014 oldest first', self.client)
        self.assertIn('setSort("modified", "desc")', self.client)
        self.assertIn('setSort("modified", "asc")', self.client)
        self.assertIn("elements.dateModifiedHeader.onclick", self.client)
        self.assertIn('state.sortKey === "modified" && state.sortDir === "desc" ? "asc" : "desc"', self.client)
        self.assertIn('timeZone: state.timeZone', self.client)
        self.assertIn('state.timeZone = String(payload.timezone || "UTC")', self.client)
        self.assertIn('parts.day} ${parts.month} ${parts.year}, ${parts.hour}:${parts.minute}', self.client)

    def test_delayed_tooltip_uses_existing_item_metadata_without_fetching(self):
        tooltip_block = self.client[
            self.client.index("function hideFileTooltip") :
            self.client.index("function showToast")
        ]
        self.assertIn("window.setTimeout(() => showFileTooltip(item), 600)", tooltip_block)
        self.assertIn('lines.push(`Item type:', tooltip_block)
        self.assertIn('lines.push(`Date modified:', tooltip_block)
        self.assertIn('lines.push(`Size:', tooltip_block)
        self.assertIn('lines.push(`Dimensions:', tooltip_block)
        self.assertIn("if (item.latest_activity)", tooltip_block)
        self.assertNotIn("fetch(", tooltip_block)
        item_handler = self.client[
            self.client.index("function createItemElement") :
            self.client.index("function detailCell")
        ]
        for event_name in ("mouseenter", "mousemove", "mouseleave", "mousedown", "click", "contextmenu", "dragstart"):
            self.assertIn(f'row.addEventListener("{event_name}"', item_handler)
        self.assertIn("pointer-events: none", self.client)
        self.assertIn("elements.results.addEventListener(\"scroll\", hideFileTooltip", self.client)

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
        self.assertIn("!state.outboundDrag", self.client)
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

    def test_images_use_native_viewer_bridge_with_browser_popup_fallback(self):
        open_block = self.client[self.client.index("function imageViewerFeatures") : self.client.index("function downloadHelper")]
        self.assertIn('hasDesktopCapability("openViewer")', open_block)
        self.assertIn('desktopPost({ action: "openViewer"', open_block)
        self.assertIn("path: viewerRequest.path", open_block)
        self.assertIn('new URL("/files-image-viewer", location.origin)', open_block)
        self.assertIn('window.open(viewerUrl, "sports-cave-image-viewer"', open_block)
        self.assertIn("state.imageViewerReady", open_block)
        self.assertIn("&& state.imageViewerReady", open_block)
        self.assertIn("queueImageViewerRequest(viewerRequest)", open_block)
        self.assertIn("deliverPendingImageViewerRequest", open_block)
        self.assertIn("if (!pending || !viewer || viewer.closed || !state.imageViewerReady) return", open_block)
        self.assertIn('type: "sports-cave-image-viewer-open"', open_block)
        self.assertIn('type: "sports-cave-image-viewer-opened"', self.viewer)
        self.assertIn("state.imageViewerWindow.focus()", open_block)
        self.assertIn("state.imageViewerReady = false", open_block)
        self.assertIn('sports-cave-image-viewer-ready', self.client)
        self.assertIn('actionLabel: "Open here"', open_block)
        self.assertIn("location.assign(viewerUrl)", open_block)
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

    def test_viewer_streams_directly_into_image_and_has_a_real_error_state(self):
        self.assertIn("This image could not be opened", self.viewer)
        self.assertIn('class="image-error"', self.viewer)
        self.assertIn("showImageError", self.viewer)
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
        self.assertIn("function notifyOpenerReady", self.viewer)
        self.assertIn('type: "sports-cave-image-viewer-ready"', self.viewer)
        self.assertIn("state.openerReadyAttempts >= 20", self.viewer)
        self.assertIn("window.setTimeout(notifyOpenerReady, 250)", self.viewer)
        self.assertIn('"sports-cave-image-viewer-parent-ready"', self.viewer)
        self.assertIn('type: "sports-cave-image-viewer-parent-ready"', self.client)

    def test_viewer_handshake_validates_origin_source_and_message_shape(self):
        self.assertIn("event.origin !== location.origin", self.viewer)
        self.assertIn("event.source !== window.opener", self.viewer)
        self.assertIn("message.version !== IMAGE_VIEWER_PROTOCOL_VERSION", self.viewer)
        self.assertIn("validRelativeValue(message.path, { required: true })", self.viewer)
        self.assertIn("validRelativeValue(message.folder)", self.viewer)
        self.assertIn("validViewerName(message.name)", self.viewer)
        self.assertIn("keys.some(key => ![", self.viewer)
        self.assertIn("state.lastOpenRequestId", self.viewer)
        self.assertIn("acknowledgeViewerOpen(message.requestId)", self.viewer)

    def test_folder_listing_cache_deduplicates_requests_and_keeps_stale_navigation_guard(self):
        self.assertIn("folderCache: new Map()", self.client)
        self.assertIn("folderRequests: new Map()", self.client)
        self.assertIn("folderControllers: new Map()", self.client)
        self.assertIn("cacheNamespace:", self.client)
        self.assertIn("const FOLDER_PAGE_SIZE = 500", self.client)
        self.assertIn("const CLIENT_FOLDER_REVALIDATE_SECONDS = 20", self.client)
        self.assertIn("function cachedFolderEntry(path)", self.client)
        self.assertIn("function cachedFolder(path)", self.client)
        self.assertIn("function requestFolder(path, refresh, page = \"\")", self.client)
        self.assertIn('params.set("page_size", String(FOLDER_PAGE_SIZE))', self.client)
        self.assertIn("state.folderRequests.has(requestKey)", self.client)
        self.assertIn("rememberFolder(payload, path)", self.client)
        self.assertIn("const shouldRevalidate = !needsMorePages", self.client)
        self.assertIn("if (!shouldRevalidate) return true", self.client)
        self.assertIn("continueFolderPages(path, payload, token", self.client)
        self.assertIn("await continueFolderPages(path, cached, token", self.client)
        self.assertIn("if (token !== state.navigationToken) return false", self.client)
        self.assertIn("if (token !== state.navigationToken) return;", self.client)
        self.assertIn("function abortStaleFolderRequests(exceptPath = null)", self.client)
        self.assertIn('typeof AbortController === "function"', self.client)
        self.assertIn("controller.abort()", self.client)
        self.assertIn("state.loadingMore", self.client)
        self.assertIn('elements.itemCount.textContent = "Opening folder..."', self.client)
        self.assertIn('Loading more...', self.client)
        self.assertIn("function invalidateClientFolderCache(...paths)", self.client)
        self.assertIn("state.thumbnailControllers.forEach(controller => controller.abort())", self.client)
        self.assertIn("MAX_CLIENT_FOLDER_CACHE = 24", self.client)

    def test_search_sort_and_view_do_not_refetch_folder(self):
        search_block = self.client[
            self.client.index('elements.searchInput.addEventListener("input"') :
            self.client.index("elements.searchClear.onclick")
        ]
        sort_block = self.client[
            self.client.index("function setSort") :
            self.client.index("function setView")
        ]
        view_block = self.client[
            self.client.index("function setView") :
            self.client.index("function setUploadConflict")
        ]
        self.assertIn("renderItems()", search_block)
        self.assertIn("renderItems()", sort_block)
        self.assertIn("renderItems()", view_block)
        self.assertNotIn("requestFolder", search_block + sort_block + view_block)
        self.assertNotIn("apiJson", search_block + sort_block + view_block)

    def test_mutations_invalidate_client_folder_cache_before_refresh(self):
        for snippet in (
            "invalidateClientFolderCache(state.currentPath);",
            "invalidateClientFolderCache(state.currentPath, item.path);",
            "invalidateClientFolderCache(state.currentPath, ...items.map(item => item.path));",
            "invalidateClientFolderCache(row.destinationPath);",
        ):
            self.assertIn(snippet, self.client)

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

    def test_external_drag_uses_capability_detected_webview_bridge(self):
        self.assertIn("function beginExternalDragPointer(event, item, index)", self.client)
        self.assertIn("function moveExternalDragPointer(event)", self.client)
        self.assertIn("function startNativeOutboundDrag(items, x, y)", self.client)
        self.assertIn('hasDesktopCapability("drag")', self.client)
        self.assertIn('desktopRequest("drag", items, requestId)', self.client)
        self.assertIn("window.chrome.webview.postMessage(message)", self.client)
        self.assertIn('desktopPost({ action: "cancel", request_id: requestId })', self.client)
        self.assertIn('row.draggable = false', self.client)
        self.assertIn('row.addEventListener("pointerdown"', self.client)
        self.assertIn('document.addEventListener("pointermove", moveExternalDragPointer, true)', self.client)
        self.assertIn("showOutboundDragPreview(items, x, y)", self.client)
        self.assertIn("selectedItems();", self.client)
        self.assertIn("state.suppressClickUntil", self.client)
        for removed in (
            "item-checkbox",
            "drag-ghost",
            "Preparing file...",
            "Ready to drag",
            "new File(",
            "dataTransfer.items.add",
            "DownloadURL",
            "text/uri-list",
            "/api/files-drag-token",
            "sports-cave-files://drag?paths=",
            "127.0.0.1:17384",
        ):
            self.assertNotIn(removed, self.client)
        drag_block = self.client[
            self.client.index("function externalDragItems") :
            self.client.index("function showItemContextMenu")
        ]
        self.assertNotIn("/api/files-delete", drag_block)
        self.assertNotIn("operation: \"move\"", drag_block)
        self.assertNotIn("window.location", drag_block)
        self.assertNotIn("protocolLink", drag_block)
        self.assertNotIn("dataTransfer", drag_block)
        self.assertIn("state.outboundDrag = true", drag_block)
        self.assertIn("state.outboundDrag = false", drag_block)
        self.assertIn("cancelExternalDrag()", self.client)

    def test_copy_uses_native_helper_while_cut_remains_internal(self):
        block = self.client[
            self.client.index("function invokeDesktopClipboard") :
            self.client.index("function invokeDesktopHelper")
        ]
        self.assertIn("const action = nativeClipboardAction(items)", block)
        self.assertIn("desktopRequest(action, items)", block)
        self.assertIn('action === "copyImage"', block)
        self.assertIn('items.length === 1 && items[0].kind === "image"', self.client)
        self.assertIn('? "copyImage"', self.client)
        self.assertIn(': "copyFile"', self.client)
        self.assertIn("item.desktop_relative_path || item.relative_path", self.client)
        self.assertIn('revision: String(item.revision || "")', self.client)
        self.assertNotIn("protocolLink", block)
        self.assertNotIn("sports-cave-files://clipboard", self.client)
        self.assertIn('mode === "copy" && hasDesktopCapability(nativeAction)', self.client)
        self.assertIn("ready to move inside Sports Cave Files", self.client)
        self.assertNotIn('invokeDesktopClipboard(chosen, "move")', self.client)

    def test_image_context_menu_omits_redundant_desktop_open_action(self):
        block = self.client[
            self.client.index("function showItemContextMenu") :
            self.client.index("function showEmptyContextMenu")
        ]
        self.assertNotIn("Open in desktop app", block)
        self.assertNotIn(">Open in desktop app<", self.client)
        self.assertIn('{ label: "Open"', block)
        self.assertIn('{ label: "Copy"', block)

    def test_folder_render_reuses_sorted_items_and_updates_only_target_thumbnail(self):
        self.assertIn("visibleItemsCache:", self.client)
        self.assertIn("cached.items === state.items", self.client)
        self.assertIn("cached.sortKey === state.sortKey", self.client)
        thumbnail_block = self.client[
            self.client.index("function installThumbnail") :
            self.client.index("function drainThumbnailQueue")
        ]
        self.assertIn("image.isConnected", thumbnail_block)
        self.assertIn("installThumbnail(task.image, task.key, objectUrl)", thumbnail_block)
        self.assertNotIn('document.querySelectorAll("img[data-thumbnail-key]")', thumbnail_block)

    def test_missing_or_outdated_helper_has_compact_update_fallback(self):
        self.assertIn('if (!window.chrome || !window.chrome.webview)', self.client)
        self.assertIn("Open in Sports Cave Desktop to drag or copy files", self.client)
        self.assertIn('elements.protocolLink.href = "sports-cave-files://app"', self.client)
        self.assertIn("const MINIMUM_DESKTOP_VERSION = 9", self.client)
        self.assertIn("desktop_outdated", self.client)
        self.assertIn('desktopError("", "desktop_outdated")', self.client)
        self.assertNotIn("Update Sports Cave Desktop to enable native drag and Copy.", self.client)
        self.assertNotIn("Sports Cave Desktop did not open.", self.client)
        self.assertNotIn('elements.helperPanel.classList.add("visible")', self.client)

    def test_files_window_uses_folder_app_mark_instead_of_generic_blue_window(self):
        self.assertIn(".app-mark", self.client)
        self.assertIn("background: #ffd45c", self.client)
        self.assertIn("background: #ffe38a", self.client)
        self.assertIn("background: #1b82d1", self.client)
        app_mark_block = self.client[
            self.client.index(".app-mark {") :
            self.client.index(".address-row {")
        ]
        self.assertNotIn("background: var(--accent);", app_mark_block)

    def test_image_viewer_supports_pixel_and_original_file_copy(self):
        self.assertIn('id="copyImageButton"', self.viewer)
        self.assertIn('id="copyFileButton"', self.viewer)
        self.assertIn('desktopRequest("copyImage")', self.viewer)
        self.assertIn('desktopRequest("copyFile")', self.viewer)
        self.assertIn('new ClipboardItem({ "image/png": png })', self.viewer)
        self.assertIn("if (event.shiftKey) copyOriginalFile()", self.viewer)
        self.assertIn('<img class="image" id="image"', self.viewer)
        self.assertIn('draggable="false"', self.viewer)
        self.assertIn("pointer-events: auto", self.viewer)
        self.assertIn("window.sportsCaveCopyImagePixels = copyImagePixels", self.viewer)
        self.assertIn('hasDesktopCapability("drag")', self.viewer)
        self.assertIn('desktopRequest("drag")', self.viewer)
        self.assertIn("const MINIMUM_DESKTOP_VERSION = 9", self.viewer)


if __name__ == "__main__":
    unittest.main()
