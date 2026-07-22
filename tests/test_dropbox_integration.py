from pathlib import Path
import unittest
from unittest.mock import patch

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
    def test_missing_env_vars_are_reported(self):
        config = {"app_key": "", "app_secret": "secret", "redirect_uri": ""}

        self.assertEqual(
            dropbox_integration.missing_config_keys(config),
            ("DROPBOX_APP_KEY", "DROPBOX_REDIRECT_URI"),
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

    def test_upload_path_uses_selected_app_folder(self):
        path = dropbox_integration.dropbox_upload_path("research_images", "hero.jpg")

        self.assertEqual(path, "/Sports Cave OS Assets/09 Research Images/hero.jpg")

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
