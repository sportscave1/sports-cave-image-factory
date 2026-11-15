import importlib
import os
import unittest
from unittest.mock import patch

from services import r2_storage


R2_KEYS = {
    "R2_ACCOUNT_ID": "",
    "R2_ACCESS_KEY_ID": "",
    "R2_SECRET_ACCESS_KEY": "",
    "R2_ENDPOINT": "",
    "R2_BUCKET_CERTIFICATES": "",
    "R2_BUCKET_ASSETS": "",
    "R2_BUCKET_BACKUPS": "",
    "R2_BUCKET_PSD_ARCHIVE": "",
    "R2_PRESIGNED_URL_EXPIRY_SECONDS": "",
}


class R2StorageTests(unittest.TestCase):
    def test_safe_r2_enabled_false_when_env_vars_are_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(r2_storage.safe_r2_enabled())

    def test_certificate_object_keys_are_stable(self):
        self.assertEqual(
            r2_storage.certificate_pdf_key("Legends Never Die", "#SC2809", 29),
            "certificates/legends-never-die/sc2809/edition-29.pdf",
        )
        self.assertEqual(
            r2_storage.certificate_preview_key("Legends Never Die", "#SC2809", 29),
            "certificates/legends-never-die/sc2809/edition-29-preview.png",
        )

    def test_presigned_download_url_uses_mocked_client(self):
        class FakeClient:
            def generate_presigned_url(self, operation, Params, ExpiresIn):
                return f"https://example.test/{Params['Bucket']}/{Params['Key']}?expires={ExpiresIn}&op={operation}"

        with patch.object(r2_storage, "get_r2_client", return_value=FakeClient()):
            url = r2_storage.generate_presigned_download_url("sports-cave-backups", "test/file.txt", 90)

        self.assertEqual(
            url,
            "https://example.test/sports-cave-backups/test/file.txt?expires=90&op=get_object",
        )

    def test_app_imports_without_r2_environment(self):
        with patch.dict(os.environ, R2_KEYS, clear=False):
            module = importlib.import_module("app")

        self.assertTrue(hasattr(module, "render_selected_page"))


if __name__ == "__main__":
    unittest.main()
