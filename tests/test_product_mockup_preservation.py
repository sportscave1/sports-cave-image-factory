"""Offline import/export safeguards; these do not certify AI artwork fidelity."""
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageOps

import image_factory as factory


class ProductMockupPreservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.enterContext(patch.object(factory, "lifestyle_available_memory_bytes", return_value=1024**3))
        self.enterContext(patch.object(factory, "get_memory_usage_mb", return_value=100))

    def scene(self, size=(180, 120), colour=(67, 89, 123)):
        image = Image.new("RGB", size, colour)
        draw = ImageDraw.Draw(image)
        # Rigid black frame at the edge would be cut off by the former square crop.
        draw.rectangle((0, 0, size[0] - 1, size[1] - 1), outline="black", width=4)
        draw.text((5, 8), "Athlete / Edition 01 / Signature", fill="white")
        draw.rectangle((4, size[1] - 15, size[0] - 5, size[1] - 5), fill=(191, 157, 55))
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        return image, stream

    def save(self, stream, slot="01-man-cave-prompt.txt"):
        return factory.save_lifestyle_mockup(self.root, "collector", "tennis", slot, stream)

    def test_complete_frame_text_and_pixels_survive_each_room_webp(self):
        for slot in sorted(factory.PRODUCT_PAGE_PROMPT_FILENAMES):
            for dimensions in ((180, 120), (120, 180), (120, 120)):
                with self.subTest(slot=slot, dimensions=dimensions):
                    original, stream = self.scene(dimensions)
                    self.addCleanup(original.close)
                    before = stream.getvalue()
                    paths = self.save(stream, slot)
                    with Image.open(paths["webp_path"]) as exported:
                        self.assertEqual(exported.format, "WEBP")
                        self.assertEqual(exported.size, original.size)
                        self.assertEqual(exported.convert("RGB").tobytes(), original.tobytes())
                    self.assertEqual(stream.getvalue(), before)
                    self.assertEqual(stream.tell(), 0)

    def test_large_import_is_bounded_without_cropping_or_stretching(self):
        original, stream = self.scene((2400, 1200))
        self.addCleanup(original.close)
        paths = self.save(stream)
        original.thumbnail((factory.MAX_EXPORT_EDGE, factory.MAX_EXPORT_EDGE), Image.LANCZOS)
        with Image.open(paths["webp_path"]) as exported:
            self.assertEqual(exported.size, (1600, 800))
            self.assertEqual(exported.convert("RGB").tobytes(), original.tobytes())

    def test_non_product_lifestyle_export_retains_previous_behaviour(self):
        original, stream = self.scene()
        self.addCleanup(original.close)
        paths = self.save(stream, "04-close-up-wall-prompt.txt")
        self.assertIsNone(paths["webp_path"])
        with ImageOps.fit(original, (120, 120), method=Image.LANCZOS) as fitted:
            expected = io.BytesIO()
            fitted.save(expected, format="JPEG", quality=factory.EXPORT_JPG_QUALITY, optimize=True)
        self.assertEqual(paths["jpg_path"].read_bytes(), expected.getvalue())

    def test_bad_encoded_pixels_rejected_before_replacing_previous_files(self):
        original, stream = self.scene()
        self.addCleanup(original.close)
        paths = self.save(stream)
        before = {key: path.read_bytes() for key, path in paths.items()}
        save = Image.Image.save

        def corrupt(image, path, *args, **kwargs):
            if kwargs.get("lossless"):
                with Image.new("RGB", image.size, "red") as wrong:
                    return save(wrong, path, *args, **kwargs)
            return save(image, path, *args, **kwargs)

        with patch.object(Image.Image, "save", corrupt):
            with self.assertRaisesRegex(ValueError, "changed imported pixels"):
                self.save(stream)
        self.assertEqual(before, {key: path.read_bytes() for key, path in paths.items()})
        self.assertFalse(list(self.root.glob("lifestyle-stage-*")))

    def test_failed_local_replacement_rolls_back_and_retry_succeeds(self):
        original, stream = self.scene()
        self.addCleanup(original.close)
        paths = self.save(stream)
        before = {key: path.read_bytes() for key, path in paths.items()}
        changed, replacement = self.scene(colour=(130, 95, 60))
        self.addCleanup(changed.close)
        replace = factory.os.replace

        def fail_preview(source, target):
            if Path(source).suffix != ".backup" and Path(target) == paths["preview_path"]:
                raise OSError("simulated interrupted replacement")
            return replace(source, target)

        with patch.object(factory.os, "replace", side_effect=fail_preview):
            with self.assertRaisesRegex(OSError, "interrupted"):
                self.save(replacement)
        self.assertEqual(before, {key: path.read_bytes() for key, path in paths.items()})
        retried = self.save(replacement)
        with Image.open(retried["webp_path"]) as exported:
            self.assertEqual(exported.convert("RGB").tobytes(), changed.tobytes())

    def test_only_target_room_changes_and_gallery_identities_remain_stable(self):
        assets = []
        for index, spec in enumerate(factory.PRODUCT_IMAGE_SLOT_SPECS):
            path = self.root / (spec["slot_id"] + ".webp")
            with Image.new("RGB", (12, 12), (index * 20, 20, 50)) as image:
                image.save(path, format="WEBP", lossless=True)
            assets.append({"key": spec["asset_key"], "webp_path": path})
        before = {asset["key"]: asset["webp_path"].read_bytes() for asset in assets}
        original, stream = self.scene()
        self.addCleanup(original.close)
        paths = self.save(stream, "02-office-prompt.txt")
        assets[2]["webp_path"] = paths["webp_path"]
        manifest = factory.build_product_image_manifest(assets, product_slug="collector", sport_slug="tennis")
        payload = factory.build_shopify_draft_image_payload(manifest)
        self.assertEqual([row["slot_id"] for row in payload],
                         ["black-frame", "man-cave", "office", "living-room", "size-guide", "oak-frame", "white-frame", "unframed"])
        self.assertEqual([row["position"] for row in payload], list(range(1, 9)))
        for asset in assets:
            if asset["key"] != "lifestyle::02-office-prompt.txt":
                self.assertEqual(asset["webp_path"].read_bytes(), before[asset["key"]])
        for row in payload[1:4]:
            self.assertIn("lifestyle", row["filename"])
            self.assertTrue(row["filename"].endswith(".webp"))
            self.assertIn("lifestyle room", row["alt_text_source"])

    def test_existing_product_prompt_file_is_byte_identical(self):
        prompt = Path(factory.__file__).with_name("mockup_product_prompts.py")
        self.assertEqual(hashlib.sha256(prompt.read_bytes()).hexdigest(),
                         "b1f637e56e66988c3933ee8e0a5a1a2768548816669e1bd7a918c65710afdc7d")


if __name__ == "__main__":
    unittest.main()
