from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import dropbox_integration
import supabase_backend


ROOT = Path(__file__).resolve().parents[1]


class FakeCursor:
    def __init__(self):
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, _sql, params=None):
        self.params = params

    def fetchone(self):
        return {
            "id": "asset-1",
            "dropbox_file_id": self.params[0],
            "dropbox_path": self.params[1],
            "name": self.params[2],
            "file_extension": self.params[3],
            "size": self.params[4],
            "asset_type": self.params[5],
            "status": self.params[6],
            "uploaded_by_user_name": self.params[7],
            "uploaded_by_user_email": self.params[8],
        }


class FakeConnection:
    def __init__(self):
        self.cursor_obj = FakeCursor()
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True


class DropboxIntegrationTests(unittest.TestCase):
    def setUp(self):
        dropbox_integration.clear_team_space_client_cache()

    def tearDown(self):
        dropbox_integration.clear_team_space_client_cache()

    def test_missing_env_vars_are_reported(self):
        config = {"app_key": "", "app_secret": "secret", "redirect_uri": ""}

        self.assertEqual(
            dropbox_integration.missing_config_keys(config),
            ("DROPBOX_APP_KEY", "DROPBOX_REDIRECT_URI"),
        )

    def test_server_config_requires_refresh_or_access_token(self):
        config = {
            "app_key": "app-key",
            "app_secret": "secret",
            "redirect_uri": "",
            "refresh_token": "",
            "access_token": "",
        }

        self.assertEqual(
            dropbox_integration.missing_server_config_keys(config),
            ("DROPBOX_REFRESH_TOKEN", "DROPBOX_ACCESS_TOKEN"),
        )

    def test_dropbox_config_reads_access_token_from_environment(self):
        with patch.dict(
            "os.environ",
            {"DROPBOX_ACCESS_TOKEN": "temporary-access-token"},
        ):
            config = dropbox_integration.dropbox_config()

        self.assertEqual(config["access_token"], "temporary-access-token")

    def test_valid_refresh_token_is_preferred_over_access_token(self):
        config = {
            "app_key": "app-key",
            "app_secret": "app-secret",
            "refresh_token": "refresh-token",
            "access_token": "fallback-token",
        }
        account = {"email": "files@sportscave.test"}

        with patch.object(
            dropbox_integration,
            "refresh_access_token",
            return_value="short-access-token",
        ) as refresh, patch.object(
            dropbox_integration,
            "get_current_account",
            return_value=account,
        ) as get_account:
            auth = dropbox_integration.resolve_server_auth(config)

        refresh.assert_called_once_with("refresh-token", config)
        get_account.assert_called_once_with("short-access-token")
        self.assertEqual(auth["source"], "refresh_token")
        self.assertEqual(auth["access_token"], "short-access-token")
        self.assertEqual(auth["account"], account)

    def test_invalid_refresh_token_falls_back_to_access_token(self):
        config = {
            "app_key": "app-key",
            "app_secret": "app-secret",
            "refresh_token": "invalid-refresh-token",
            "access_token": "fallback-token",
        }

        with patch.object(
            dropbox_integration,
            "refresh_access_token",
            side_effect=dropbox_integration.DropboxApiError("invalid_grant"),
        ), patch.object(
            dropbox_integration,
            "get_current_account",
            return_value={"email": "files@sportscave.test"},
        ) as get_account:
            auth = dropbox_integration.resolve_server_auth(config)

        get_account.assert_called_once_with("fallback-token")
        self.assertEqual(auth["source"], "access_token")
        self.assertEqual(auth["access_token"], "fallback-token")

    def test_missing_refresh_token_uses_access_token(self):
        config = {
            "app_key": "app-key",
            "app_secret": "app-secret",
            "refresh_token": "",
            "access_token": "fallback-token",
        }

        with patch.object(dropbox_integration, "refresh_access_token") as refresh, patch.object(
            dropbox_integration,
            "get_current_account",
            return_value={"email": "files@sportscave.test"},
        ):
            auth = dropbox_integration.resolve_server_auth(config)

        refresh.assert_not_called()
        self.assertEqual(auth["source"], "access_token")

    def test_missing_or_invalid_server_tokens_raise_sanitized_failure(self):
        with self.assertRaisesRegex(
            dropbox_integration.DropboxConfigError,
            "server credentials are not configured",
        ):
            dropbox_integration.resolve_server_auth(
                {"app_key": "", "app_secret": "", "refresh_token": "", "access_token": ""}
            )

        config = {
            "app_key": "app-key",
            "app_secret": "app-secret",
            "refresh_token": "secret-refresh-value",
            "access_token": "secret-access-value",
        }
        with patch.object(
            dropbox_integration,
            "refresh_access_token",
            side_effect=dropbox_integration.DropboxApiError("invalid refresh"),
        ), patch.object(
            dropbox_integration,
            "get_current_account",
            side_effect=dropbox_integration.DropboxApiError("expired access"),
        ), self.assertRaises(dropbox_integration.DropboxApiError) as raised:
            dropbox_integration.resolve_server_auth(config)

        message = str(raised.exception)
        self.assertEqual(message, "Dropbox server credentials could not be verified.")
        self.assertNotIn("secret-refresh-value", message)
        self.assertNotIn("secret-access-value", message)

    def test_configured_root_path_defaults_and_can_be_overridden(self):
        self.assertEqual(
            dropbox_integration.configured_root_path({"root_path": ""}),
            "/Sportscave Team Folder",
        )
        self.assertEqual(
            dropbox_integration.configured_root_path({"root_path": "/Team Files"}),
            "/Team Files",
        )

    def test_oauth_url_requests_offline_refresh_token(self):
        config = {
            "app_key": "app-key",
            "app_secret": "app-secret",
            "redirect_uri": "https://example.test/dropbox/callback",
        }

        url = dropbox_integration.build_authorization_url("state-1", config)

        self.assertIn("token_access_type=offline", url)
        self.assertIn("response_type=code", url)
        self.assertIn("state=state-1", url)
        self.assertIn("redirect_uri=https%3A%2F%2Fexample.test%2Fdropbox%2Fcallback", url)

    def test_upload_path_uses_selected_team_folder(self):
        path = dropbox_integration.dropbox_upload_path("research_images", "hero.jpg")

        self.assertEqual(path, "/Sportscave Team Folder/09 Research Images/hero.jpg")

    def test_paths_are_normalized_for_dropbox(self):
        self.assertEqual(
            dropbox_integration.normalize_dropbox_path(
                "\\Sports Cave OS Assets\\05 Mockups\\"
            ),
            "/Sports Cave OS Assets/05 Mockups",
        )
        self.assertEqual(dropbox_integration.normalize_dropbox_path("/"), "")
        with self.assertRaises(ValueError):
            dropbox_integration.normalize_dropbox_path("/Sports Cave OS Assets/../Private")

    def test_folder_entries_sort_folders_first_then_by_name(self):
        entries = [
            {".tag": "file", "name": "Alpha.pdf"},
            {".tag": "folder", "name": "Zulu"},
            {".tag": "folder", "name": "Brand"},
            {".tag": "file", "name": "Beta.psd"},
        ]

        sorted_entries = dropbox_integration.sort_folder_entries(entries)

        self.assertEqual(
            [entry["name"] for entry in sorted_entries],
            ["Brand", "Zulu", "Alpha.pdf", "Beta.psd"],
        )

    def test_list_folder_uses_current_folder_only_and_is_bounded(self):
        client = MagicMock()
        client.files_list_folder.return_value = SimpleNamespace(
            entries=[{".tag": "folder", "name": "05 Mockups"}],
            has_more=False,
            cursor="",
        )
        with patch.object(dropbox_integration, "team_space_client", return_value=client):
            entries = dropbox_integration.list_folder(
                "access-token",
                "/Sports Cave OS Assets",
            )

        self.assertEqual(entries[0]["name"], "05 Mockups")
        client.files_list_folder.assert_called_once_with(
            "/Sports Cave OS Assets",
            recursive=False,
            include_deleted=False,
            include_media_info=False,
            limit=2000,
        )

    def test_list_folder_uses_dropbox_pagination_without_recursive_scan(self):
        first_page = SimpleNamespace(
            entries=[{".tag": "folder", "name": "01 Artwork"}],
            has_more=True,
            cursor="cursor-1",
        )
        second_page = SimpleNamespace(
            entries=[{".tag": "file", "name": "collector.pdf"}],
            has_more=False,
            cursor="",
        )
        client = MagicMock()
        client.files_list_folder.return_value = first_page
        client.files_list_folder_continue.return_value = second_page
        with patch.object(dropbox_integration, "team_space_client", return_value=client):
            entries = dropbox_integration.list_folder(
                "access-token",
                "/Sportscave Team Folder",
                max_entries=10,
            )

        self.assertEqual([entry["name"] for entry in entries], ["01 Artwork", "collector.pdf"])
        client.files_list_folder.assert_called_once_with(
            "/Sportscave Team Folder",
            recursive=False,
            include_deleted=False,
            include_media_info=False,
            limit=10,
        )
        client.files_list_folder_continue.assert_called_once_with("cursor-1")

    def test_team_space_client_selects_account_root_namespace(self):
        account = SimpleNamespace(
            account_id="dbid:account",
            email="hello@sportscave.com.au",
            name=SimpleNamespace(display_name="Sports Cave", familiar_name="Sports Cave"),
            root_info=SimpleNamespace(root_namespace_id="team-root-123"),
        )
        rooted_client = object()
        base_client = MagicMock()
        base_client.users_get_current_account.return_value = account
        base_client.with_path_root.return_value = rooted_client
        path_root = object()
        sdk = SimpleNamespace(
            common=SimpleNamespace(
                PathRoot=SimpleNamespace(root=MagicMock(return_value=path_root))
            )
        )

        with patch.object(
            dropbox_integration,
            "_new_dropbox_client",
            return_value=base_client,
        ), patch.object(dropbox_integration, "_dropbox_sdk", return_value=sdk):
            client = dropbox_integration.team_space_client("short-access-token", force=True)

        self.assertIs(client, rooted_client)
        base_client.users_get_current_account.assert_called_once_with()
        sdk.common.PathRoot.root.assert_called_once_with("team-root-123")
        base_client.with_path_root.assert_called_once_with(path_root)

    def test_rooted_client_is_reused_for_navigation_metadata_preview_and_upload(self):
        root_result = SimpleNamespace(
            entries=[{".tag": "folder", "name": "05 Mockups"}],
            has_more=False,
            cursor="",
        )
        child_result = SimpleNamespace(
            entries=[{".tag": "file", "name": "mockup.jpg"}],
            has_more=False,
            cursor="",
        )
        client = MagicMock()
        client.files_list_folder.side_effect = [root_result, child_result]
        client.files_get_metadata.return_value = {
            ".tag": "file",
            "name": "mockup.jpg",
        }
        client.files_get_temporary_link.return_value = SimpleNamespace(
            link="https://dropbox.test/mockup.jpg"
        )
        client.files_upload.return_value = {
            ".tag": "file",
            "name": "new.jpg",
            "path_display": "/Sportscave Team Folder/05 Mockups/new.jpg",
        }
        sdk = SimpleNamespace(files=SimpleNamespace(WriteMode=SimpleNamespace(add="add")))

        with patch.object(
            dropbox_integration,
            "team_space_client",
            return_value=client,
        ) as rooted, patch.object(dropbox_integration, "_dropbox_sdk", return_value=sdk):
            dropbox_integration.list_folder("token", "/Sportscave Team Folder")
            dropbox_integration.list_folder("token", "/Sportscave Team Folder/05 Mockups")
            details = dropbox_integration.file_open_details(
                "token",
                "/Sportscave Team Folder/05 Mockups/mockup.jpg",
            )
            uploaded = dropbox_integration.upload_file(
                "token",
                "/Sportscave Team Folder/05 Mockups/new.jpg",
                b"image-data",
            )

        self.assertEqual(rooted.call_count, 5)
        self.assertEqual(details["temporary_link"], "https://dropbox.test/mockup.jpg")
        self.assertEqual(uploaded["name"], "new.jpg")
        self.assertEqual(
            [call.args[0] for call in client.files_list_folder.call_args_list],
            [
                "/Sportscave Team Folder",
                "/Sportscave Team Folder/05 Mockups",
            ],
        )
        client.files_get_metadata.assert_called_once_with(
            "/Sportscave Team Folder/05 Mockups/mockup.jpg",
            include_media_info=False,
            include_deleted=False,
        )
        client.files_get_temporary_link.assert_called_once_with(
            "/Sportscave Team Folder/05 Mockups/mockup.jpg"
        )
        client.files_upload.assert_called_once_with(
            b"image-data",
            "/Sportscave Team Folder/05 Mockups/new.jpg",
            mode="add",
            autorename=True,
            mute=False,
        )

    def test_find_team_folder_resolves_real_dropbox_metadata(self):
        metadata = {
            ".tag": "folder",
            "name": "Sportscave Team Folder",
            "path_display": "/Sportscave Team Folder",
        }
        with patch.object(
            dropbox_integration,
            "get_file_metadata",
            return_value=metadata,
        ) as get_metadata, patch.object(
            dropbox_integration,
            "list_folder",
        ) as list_folder:
            path = dropbox_integration.find_team_folder("access-token")

        self.assertEqual(path, "/Sportscave Team Folder")
        get_metadata.assert_called_once_with("access-token", "/Sportscave Team Folder")
        list_folder.assert_not_called()

    def test_find_team_folder_can_match_display_case_from_root_listing(self):
        with patch.object(
            dropbox_integration,
            "get_file_metadata",
            side_effect=dropbox_integration.DropboxApiError("path/not_found/"),
        ), patch.object(
            dropbox_integration,
            "list_folder",
            return_value=[
                {
                    ".tag": "folder",
                    "name": "SPORTSCAVE TEAM FOLDER",
                    "path_display": "/SPORTSCAVE TEAM FOLDER",
                }
            ],
        ):
            path = dropbox_integration.find_team_folder("access-token")

        self.assertEqual(path, "/SPORTSCAVE TEAM FOLDER")

    def test_missing_team_folder_reports_possible_app_folder_restriction(self):
        with patch.object(
            dropbox_integration,
            "get_file_metadata",
            side_effect=dropbox_integration.DropboxApiError("path/not_found/"),
        ), patch.object(dropbox_integration, "list_folder", return_value=[]):
            with self.assertRaises(dropbox_integration.DropboxFolderAccessError) as raised:
                dropbox_integration.find_team_folder("access-token")

        self.assertEqual(raised.exception.reason, "not_visible")
        self.assertIn("App Folder access", str(raised.exception))

    def test_team_folder_permission_error_is_distinct_from_empty_folder(self):
        with patch.object(
            dropbox_integration,
            "get_file_metadata",
            side_effect=dropbox_integration.DropboxApiError("path/no_permission/"),
        ), patch.object(
            dropbox_integration,
            "list_folder",
            side_effect=dropbox_integration.DropboxApiError("missing_scope/files.metadata.read"),
        ):
            with self.assertRaises(dropbox_integration.DropboxFolderAccessError) as raised:
                dropbox_integration.find_team_folder("access-token")

        self.assertEqual(raised.exception.reason, "permission")
        self.assertIn("permission", str(raised.exception).casefold())

    def test_breadcrumbs_stay_inside_team_folder(self):
        items = dropbox_integration.breadcrumb_items(
            "/Sportscave Team Folder/05 Mockups/Final",
            "/Sportscave Team Folder",
        )

        self.assertEqual(
            items,
            (
                ("Files", ""),
                ("Sportscave Team Folder", "/Sportscave Team Folder"),
                ("05 Mockups", "/Sportscave Team Folder/05 Mockups"),
                ("Final", "/Sportscave Team Folder/05 Mockups/Final"),
            ),
        )
        self.assertTrue(
            dropbox_integration.path_is_within_root(
                "/Sportscave Team Folder/05 Mockups",
                "/Sportscave Team Folder",
            )
        )
        self.assertFalse(
            dropbox_integration.path_is_within_root(
                "/Other Folder",
                "/Sportscave Team Folder",
            )
        )

    def test_temporary_link_helper_is_used_for_file_open(self):
        metadata = {".tag": "file", "name": "collector.pdf"}
        with patch.object(
            dropbox_integration,
            "get_file_metadata",
            return_value=metadata,
        ), patch.object(
            dropbox_integration,
            "get_temporary_link",
            return_value="https://dropbox.test/temporary/collector.pdf",
        ) as temporary_link:
            result = dropbox_integration.file_open_details(
                "access-token",
                "/Sports Cave OS Assets/collector.pdf",
            )

        temporary_link.assert_called_once_with(
            "access-token",
            "/Sports Cave OS Assets/collector.pdf",
        )
        self.assertEqual(result["metadata"], metadata)
        self.assertEqual(
            result["temporary_link"],
            "https://dropbox.test/temporary/collector.pdf",
        )

    def test_file_size_formatting_is_compact(self):
        self.assertEqual(dropbox_integration.format_file_size(0), "0 B")
        self.assertEqual(dropbox_integration.format_file_size(1536), "1.5 KB")
        self.assertEqual(dropbox_integration.format_file_size(5 * 1024 * 1024), "5.0 MB")

    def test_metadata_normaliser_extracts_extension_and_actor(self):
        row = dropbox_integration.normalise_asset_metadata(
            dropbox_file_id="id:123",
            dropbox_path="/Sports Cave OS Assets/05 Mockups/mockup.PNG",
            name="mockup.PNG",
            size=42,
            asset_type="mockups",
            uploaded_by_user_name="Nathan",
            uploaded_by_user_email="nathan@sportscave.test",
        )

        self.assertEqual(row["file_extension"], "png")
        self.assertEqual(row["uploaded_by_user_name"], "Nathan")
        self.assertEqual(row["size"], 42)

    def test_dropbox_metadata_save_helper_inserts_row(self):
        fake_conn = FakeConnection()
        metadata = dropbox_integration.normalise_asset_metadata(
            dropbox_file_id="id:file",
            dropbox_path="/Sports Cave OS Assets/01 Brand Assets/logo.png",
            name="logo.png",
            size=100,
            asset_type="brand_assets",
            uploaded_by_user_name="Nathan",
            uploaded_by_user_email="nathan@sportscave.test",
        )

        with patch.object(supabase_backend, "ensure_dropbox_schema") as ensure_schema, patch.object(
            supabase_backend,
            "connect",
            return_value=fake_conn,
        ):
            saved = supabase_backend.save_dropbox_asset_metadata(metadata)

        ensure_schema.assert_called_once_with()
        self.assertTrue(fake_conn.committed)
        self.assertEqual(saved["dropbox_file_id"], "id:file")
        self.assertEqual(saved["dropbox_path"], "/Sports Cave OS Assets/01 Brand Assets/logo.png")
        self.assertEqual(saved["asset_type"], "brand_assets")

    def test_dropbox_migration_contains_asset_table(self):
        sql = (ROOT / "migrations" / "20260722_dropbox_assets.sql").read_text(encoding="utf-8")

        self.assertIn("CREATE TABLE IF NOT EXISTS dropbox_assets", sql)
        self.assertIn("dropbox_file_id TEXT", sql)
        self.assertIn("uploaded_by_user_name TEXT", sql)


if __name__ == "__main__":
    unittest.main()
