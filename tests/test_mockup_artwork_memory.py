import gc
import io
from pathlib import Path
import tempfile
import unittest
import weakref
from unittest.mock import patch

from PIL import Image, ImageOps
import app
import image_factory as factory
from tests.test_mockup_memory_pipeline import FakeSessionState, assert_lightweight, write_test_templates
from tests.test_mockup_upload_validation import Upload, image_bytes


class ArtworkMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.enterContext(patch.object(factory, "get_memory_usage_mb", return_value=600))
        self.enterContext(patch.object(factory, "lifestyle_available_memory_bytes", return_value=1024**3))
        self.enterContext(patch.object(app, "image_factory", factory))

    def source(self, dimensions=(120, 80), mode="RGB", orientation=1):
        path = self.root / "source.png"
        with Image.new(mode, dimensions, (20, 40, 80, 100) if mode == "RGBA" else (20, 40, 80)) as image:
            exif = Image.Exif()
            exif[274] = orientation
            image.save(path, exif=exif)
        return path

    def test_original_full_generation_preview_and_zip_above_old_rss_limit(self):
        write_test_templates(self.root)
        source = self.source((2600, 2200))
        original = source.read_bytes()
        result = factory.generate_product_images("Test", "Hockey", source, base_dir=self.root,
                                                 output_root=self.root / "runs")
        self.assertEqual(len(result["assets"]), 5)
        for asset in result["assets"]:
            for key in ("preview_path", "webp_path", "jpg_path"):
                with Image.open(asset[key]) as image:
                    image.load()
                    self.assertLessEqual(max(image.size), factory.MAX_EXPORT_EDGE)
        archive = factory.create_complete_pack_zip(result["zip_dir"], "test", assets=result["assets"])
        self.assertTrue(archive.exists())
        self.assertEqual(source.read_bytes(), original)
        assert_lightweight(result)

    def test_original_orientation_alpha_and_decoded_resources_released(self):
        source = self.source(mode="RGBA", orientation=6)
        refs = []
        transpose = ImageOps.exif_transpose
        def track(image, **kwargs):
            refs.append(weakref.ref(image))
            self.assertTrue(kwargs["in_place"])
            return transpose(image, **kwargs)
        for _ in range(3):
            with patch.object(ImageOps, "exif_transpose", side_effect=track):
                path = factory.prepare_working_artwork(source, self.root / "working")
            with Image.open(path) as image:
                self.assertEqual(image.size, (80, 120))
                self.assertEqual(image.mode, "RGBA")
                self.assertEqual(image.getpixel((0, 0))[3], 100)
        gc.collect()  # Liveness, not an assertion about allocator RSS.
        self.assertTrue(all(ref() is None for ref in refs))
        self.assertEqual(list(path.parent.iterdir()), [path])

    def test_original_failed_export_preserves_previous_and_retry(self):
        source = self.source()
        path = factory.prepare_working_artwork(source, self.root / "working")
        previous = path.read_bytes()
        with patch.object(Image.Image, "save", side_effect=MemoryError("allocation failed")):
            with self.assertRaisesRegex(factory.MemoryLimitExceededError, "prepare the uploaded artwork"):
                factory.prepare_working_artwork(source, path.parent)
        self.assertEqual(path.read_bytes(), previous)
        self.assertEqual(list(path.parent.iterdir()), [path])
        factory.prepare_working_artwork(source, path.parent)

    def test_small_compressed_excessive_dimensions_and_insufficient_headroom(self):
        source = self.source((5001, 5000))
        self.assertLess(source.stat().st_size, 1024**2)
        with self.assertRaisesRegex(ValueError, "25 million pixels"):
            factory.prepare_working_artwork(source, self.root / "working")
        source = self.source()
        with patch.object(factory, "lifestyle_available_memory_bytes", return_value=1), patch.object(ImageOps, "exif_transpose") as decode:
            with self.assertRaises(factory.MemoryLimitExceededError):
                factory.prepare_working_artwork(source, self.root / "working")
            decode.assert_not_called()

    def test_original_invalid_and_file_size_errors(self):
        source = self.root / "bad.jpg"
        source.write_bytes(b"invalid")
        with self.assertRaisesRegex(ValueError, "valid JPG"):
            factory.prepare_working_artwork(source, self.root / "working")
        source = self.source()
        with source.open("ab") as stream:
            stream.truncate(factory.MAX_UPLOAD_SIZE_BYTES + 1)
        with self.assertRaisesRegex(ValueError, "20 MB upload file-size"):
            factory.prepare_working_artwork(source, self.root / "working")

    def test_original_supported_formats(self):
        for format_name, suffix in (("JPEG", "jpg"), ("PNG", "png"), ("WEBP", "webp")):
            with self.subTest(format=format_name):
                source = self.root / ("source." + suffix)
                source.write_bytes(image_bytes(format_name, dimensions=(1536, 1024)))
                path = factory.prepare_working_artwork(source, self.root / "working")
                with Image.open(path) as image:
                    image.load()
                    self.assertEqual(image.size, (1536, 1024))

    def test_failed_preview_keeps_upload_open_and_does_not_cache_partial_file(self):
        state = FakeSessionState()
        preview_dir = self.root / "preview"
        upload = Upload(image_bytes())
        with patch.object(app.st, "session_state", state), patch.object(app, "UPLOAD_PREVIEW_DIR", preview_dir):
            with patch.object(Image.Image, "save", side_effect=MemoryError("preview allocation")):
                with self.assertRaises(factory.MemoryLimitExceededError):
                    app.process_uploaded_artwork_once(upload)
            self.assertFalse(upload.closed)
            self.assertEqual(upload.tell(), 0)
            self.assertEqual(list(preview_dir.iterdir()), [])
            self.assertFalse(state["mockups_upload_processing_cache"])
            details = app.process_uploaded_artwork_once(upload)
            self.assertTrue(Path(details["preview_path"]).exists())

    def test_artwork_rerun_uses_disk_metadata_cache_without_redecode(self):
        state = FakeSessionState()
        with patch.object(app.st, "session_state", state), patch.object(app, "UPLOAD_PREVIEW_DIR", self.root / "preview"):
            upload = Upload(image_bytes())
            first = app.process_uploaded_artwork_once(upload)
            with patch.object(Image, "open", side_effect=AssertionError("decoded on rerun")):
                self.assertEqual(app.process_uploaded_artwork_once(upload), first)
            app.process_uploaded_artwork_once(Upload(image_bytes(dimensions=(40, 30))))
            assert_lightweight(state)
            self.assertEqual(upload.tell(), 0)

    def test_lifestyle_all_slots_partial_export_failure_preserves_previous(self):
        original_save = Image.Image.save
        for slot in sorted(factory.PRODUCT_PAGE_PROMPT_FILENAMES):
            paths = factory.save_lifestyle_mockup(self.root, "test", "hockey", slot, Upload(image_bytes()))
            previous = {key: Path(path).read_bytes() for key, path in paths.items()}
            def fail_jpeg(image, path, *args, **kwargs):
                if kwargs.get("format") == "JPEG":
                    raise MemoryError("export failure after WebP")
                return original_save(image, path, *args, **kwargs)
            with patch.object(Image.Image, "save", new=fail_jpeg):
                with self.assertRaises(factory.MemoryLimitExceededError):
                    factory.save_lifestyle_mockup(self.root, "test", "hockey", slot, Upload(image_bytes(dimensions=(40, 30))))
            for key, path in paths.items():
                self.assertEqual(Path(path).read_bytes(), previous[key])
            factory.save_lifestyle_mockup(self.root, "test", "hockey", slot, Upload(image_bytes(dimensions=(40, 30))))
            self.assertFalse(list(self.root.glob("lifestyle-stage-*")))

    def test_lifestyle_commit_failure_rolls_back(self):
        slot = "01-man-cave-prompt.txt"
        paths = factory.save_lifestyle_mockup(self.root, "test", "hockey", slot, Upload(image_bytes()))
        previous = {key: Path(path).read_bytes() for key, path in paths.items()}
        replace = factory.os.replace
        calls = 0
        def fail_second(source, target):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("commit failed")
            return replace(source, target)
        with patch.object(factory.os, "replace", side_effect=fail_second):
            with self.assertRaises(OSError):
                factory.save_lifestyle_mockup(self.root, "test", "hockey", slot, Upload(image_bytes(dimensions=(40, 30))))
        for key, path in paths.items():
            self.assertEqual(Path(path).read_bytes(), previous[key])


if __name__ == "__main__":
    unittest.main()
