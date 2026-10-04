import io
import unittest

from PIL import Image

import wall_preview_api
import wall_preview_store


class WallPreviewFeatureTests(unittest.TestCase):
    def _jpeg(self, size=(640, 480)):
        stream = io.BytesIO()
        Image.new("RGB", size, "white").save(stream, format="JPEG", quality=90)
        return stream.getvalue()

    def test_storefront_origins_are_allowed_by_default(self):
        allowed = wall_preview_api._allowed_origins()
        self.assertIn("https://www.sportscaveshop.com", allowed)
        self.assertIn("https://sportscaveshop.com", allowed)

    def test_image_validation_accepts_email_safe_jpeg(self):
        width, height = wall_preview_api._inspect_image(
            self._jpeg(),
            "image/jpeg",
        )
        self.assertEqual((width, height), (640, 480))

    def test_image_validation_rejects_non_image_payload(self):
        with self.assertRaises(ValueError):
            wall_preview_api._inspect_image(b"not-an-image", "image/jpeg")

    def test_dropbox_path_is_scoped_to_wall_previews(self):
        folder, destination = wall_preview_api._dropbox_destination(
            "/Sportscave Team Folder",
            "Cristiano Ronaldo — The Mentality",
            "a" * 64,
            "image/jpeg",
        )
        self.assertIn("/11 Wall Preview Inbox/", folder)
        self.assertTrue(destination.startswith(folder + "/"))
        self.assertTrue(destination.endswith(".jpg"))
        self.assertNotIn("—", destination)

    def test_approval_states_are_bounded(self):
        self.assertEqual(
            wall_preview_store.VALID_STATUSES,
            ("new", "approved", "used", "archived"),
        )


if __name__ == "__main__":
    unittest.main()
