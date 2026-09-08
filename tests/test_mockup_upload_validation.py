import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

import app
import image_factory


class Upload(io.BytesIO):
    def __init__(self, data, name="chatgpt.png"):
        super().__init__(data)
        self.name = name
        self.size = len(data)

    def getvalue(self):
        raise AssertionError("Upload validation must keep the existing streaming path")


class SessionState(dict):
    def __setattr__(self, name, value):
        self[name] = value


def image_bytes(image_format="PNG", dimensions=(24, 24), source_size=None):
    with Image.new("RGB", dimensions, (20, 40, 80)) as image:
        stream = io.BytesIO()
        image.save(stream, format=image_format)
    data = stream.getvalue()
    # Legal trailing padding exercises exact original-file lengths without large
    # fixtures or expensive random-pixel compression. PIL still decodes the image.
    return data if source_size is None else data + b"\0" * (source_size - len(data))


class MockupUploadValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.enterContext(patch.object(app, "image_factory", image_factory))
        self.enterContext(patch.object(app.st, "session_state", SessionState()))
        # Deterministic headroom; individual resource-error tests override this.
        self.enterContext(patch.object(image_factory, "get_memory_usage_mb", return_value=100))

    def save(self, upload, prompt="01-man-cave-prompt.txt"):
        return image_factory.save_lifestyle_mockup(
            self.temp.name, "test-product", "afl", prompt, upload
        )

    def test_supported_source_size_matrix_and_complete_stream(self):
        for image_format, suffix in (("PNG", "png"), ("JPEG", "jpg"), ("WEBP", "webp")):
            for size in (None, 2_000_000, 2_100_000, 5_000_000, 10_000_000, 14_900_000):
                with self.subTest(format=image_format, source_bytes=size):
                    data = image_bytes(image_format, source_size=size)
                    upload = Upload(data, f"image.{suffix}")
                    upload.seek(7)
                    self.assertTrue(app.get_uploaded_lifestyle_signature(upload))
                    self.assertEqual(upload.tell(), 0)
                    paths = self.save(upload)
                    self.assertEqual(upload.tell(), 0)
                    self.assertEqual(upload.read(), data)
                    with Image.open(paths["jpg_path"]) as output:
                        output.load()
                        self.assertEqual(output.size, (24, 24))

    def test_exact_binary_boundary_and_one_byte_over(self):
        limit = image_factory.MAX_LIFESTYLE_UPLOAD_SIZE_BYTES
        self.assertEqual(limit, 15 * 1024 * 1024)
        for size in (limit - 1, limit, limit + 1):
            with self.subTest(source_bytes=size):
                upload = Upload(image_bytes(source_size=size))
                if size <= limit:
                    self.assertTrue(app.get_uploaded_lifestyle_signature(upload))
                    self.save(upload)
                else:
                    for validate in (app.get_uploaded_lifestyle_signature, self.save):
                        with self.assertRaises(ValueError) as caught:
                            validate(upload)
                        self.assertEqual(str(caught.exception), image_factory.LIFESTYLE_UPLOAD_TOO_LARGE_MESSAGE)
                self.assertEqual(upload.tell(), 0)

    def test_missing_or_understated_metadata_checks_actual_source_bytes(self):
        for declared_size in (None, 12):
            with self.subTest(declared_size=declared_size):
                upload = Upload(image_bytes(source_size=image_factory.MAX_LIFESTYLE_UPLOAD_SIZE_BYTES + 1))
                upload.size = declared_size
                for validate in (app.get_uploaded_lifestyle_signature, self.save):
                    with self.assertRaisesRegex(ValueError, "This uploaded image is too large"):
                        validate(upload)
                    self.assertEqual(upload.tell(), 0)

    def test_copy_rewinds_even_when_source_exceeds_limit_without_metadata(self):
        upload = io.BytesIO(b"x" * (image_factory.MAX_LIFESTYLE_UPLOAD_SIZE_BYTES + 1))
        upload.seek(8)
        with self.assertRaisesRegex(ValueError, "This uploaded image is too large"):
            image_factory.copy_uploaded_image_to_temp(upload, self.temp.name)
        self.assertEqual(upload.tell(), 0)

    def test_compressed_png_large_decoded_pixels_is_accepted(self):
        data = image_bytes(dimensions=(2600, 2200))
        self.assertLess(len(data), image_factory.MAX_LIFESTYLE_UPLOAD_SIZE_BYTES)
        with Image.open(io.BytesIO(data)) as image:
            self.assertGreater(len(image.tobytes()), image_factory.MAX_LIFESTYLE_UPLOAD_SIZE_BYTES)
        upload = Upload(data)
        self.assertTrue(app.get_uploaded_lifestyle_signature(upload))
        self.assertTrue(Path(self.save(upload)["jpg_path"]).exists())

    def test_process_rss_limit_is_not_source_size_error(self):
        upload = Upload(image_bytes(source_size=2_100_000))
        with patch.object(image_factory, "get_memory_usage_mb", return_value=431):
            # Source validation succeeds even when the process has no headroom.
            self.assertTrue(app.get_uploaded_lifestyle_signature(upload))
            with self.assertRaises(image_factory.MemoryLimitExceededError) as caught:
                self.save(upload)
        self.assertEqual(str(caught.exception), image_factory.LIFESTYLE_UPLOAD_MEMORY_MESSAGE)
        self.assertEqual(app._safe_lifestyle_upload_error(caught.exception), str(caught.exception))
        self.assertNotIn("15 MB", str(caught.exception))
        self.assertEqual(upload.tell(), 0)

    def test_decoder_memory_error_is_not_source_size_error(self):
        with patch.object(image_factory.ImageOps, "exif_transpose", side_effect=MemoryError("private detail")):
            with self.assertRaises(image_factory.MemoryLimitExceededError) as caught:
                self.save(Upload(image_bytes()))
        self.assertEqual(str(caught.exception), image_factory.LIFESTYLE_UPLOAD_MEMORY_MESSAGE)
        self.assertNotIn("private detail", app._safe_lifestyle_upload_error(caught.exception))

    def test_export_memory_error_is_not_source_size_error(self):
        upload = Upload(image_bytes())
        with patch.object(image_factory.Image.Image, "save", side_effect=MemoryError()):
            with self.assertRaises(MemoryError) as caught:
                self.save(upload)
        self.assertNotIn("15 MB", app._safe_lifestyle_upload_error(caught.exception))

    def test_corrupt_unsupported_and_empty_files_are_not_size_errors(self):
        for data in (b"invalid png", image_bytes("BMP"), b""):
            with self.subTest(source_bytes=len(data)):
                upload = Upload(data)
                with self.assertRaises((ValueError, RuntimeError)) as caught:
                    self.save(upload)
                self.assertEqual(str(caught.exception), image_factory.LIFESTYLE_UPLOAD_INVALID_MESSAGE)
                self.assertNotIn("15 MB", app._safe_lifestyle_upload_error(caught.exception))
                self.assertEqual(upload.tell(), 0)

    def test_other_processing_failure_gets_generic_safe_error(self):
        upload = Upload(image_bytes())
        with patch.object(image_factory.ImageOps, "fit", side_effect=OSError("private detail")):
            with self.assertRaises(OSError) as caught:
                self.save(upload)
        self.assertEqual(app._safe_lifestyle_upload_error(caught.exception), "Could not save the lifestyle image for this prompt.")

    def test_all_mockups_prompt_callers_use_source_validation_and_real_save(self):
        self.assertEqual(image_factory.PRODUCT_PAGE_PROMPT_FILENAMES, {
            "01-man-cave-prompt.txt", "02-office-prompt.txt", "03-living-room-prompt.txt",
        })
        result = {
            "run_dir": self.temp.name, "product_slug": "test", "sport_slug": "afl",
            "lifestyle_mockup_paths": {}, "assets": [],
        }
        with patch.object(app, "normalize_generation_result", side_effect=lambda value: value), \
             patch.object(app, "rebuild_result_artifacts", side_effect=lambda value: value), \
             patch.object(app, "record_activity_log"), \
             patch.object(image_factory, "validate_lifestyle_upload_size", wraps=image_factory.validate_lifestyle_upload_size) as validate:
            for prompt in image_factory.LIFESTYLE_IMAGE_VARIANTS:
                with self.subTest(prompt=prompt):
                    upload = Upload(image_bytes(source_size=2_100_000))
                    result = app.auto_register_lifestyle_upload(result, Path(prompt), upload)
                    validate.assert_called_with(upload)
                    self.assertEqual(app.get_lifestyle_upload_lifecycle(result, Path(prompt))["status"], "SUCCEEDED")
                    self.assertTrue(Path(result["lifestyle_mockup_paths"][prompt]["jpg_path"]).exists())

    def test_prompt_card_ui_routes_uploads_through_auto_registration(self):
        source = Path(app.__file__).read_text(encoding="utf-8")
        cards = source[source.index("def _render_prompt_card_group("):source.index("\n\ndef ", source.index("def _render_prompt_card_group(") + 1)]
        self.assertIn('"Upload image from ChatGPT"', cards)
        self.assertIn("auto_register_lifestyle_upload(", cards)
        self.assertNotIn("st.exception(", cards)
        self.assertIn('(product_page_prompts, "Product Page Lifestyle Mockups", None)', source)


if __name__ == "__main__":
    unittest.main()
