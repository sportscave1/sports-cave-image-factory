import gc
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import weakref
import threading
from concurrent.futures import ThreadPoolExecutor

from PIL import Image, ImageOps
import image_factory as factory


class LifestyleMemoryHeadroomTests(unittest.TestCase):
    def test_estimate_boundary(self):
        with patch.object(factory, "lifestyle_available_memory_bytes", return_value=1024**3):
            required = factory.validate_lifestyle_processing_memory(1536, 1024)
        threshold = required + factory.LIFESTYLE_MEMORY_RESERVE_BYTES
        self.assertEqual(required, 1536 * 1024 * 16 + 1024 * 1024 * 8 + 16 * 1024**2)
        for available in (threshold - 1, threshold, threshold + 1):
            with self.subTest(available=available), patch.object(factory, "lifestyle_available_memory_bytes", return_value=available):
                if available < threshold:
                    with self.assertRaises(factory.MemoryLimitExceededError):
                        factory.validate_lifestyle_processing_memory(1536, 1024)
                else:
                    factory.validate_lifestyle_processing_memory(1536, 1024)

    def test_pixel_bound_applies_even_without_available_memory_telemetry(self):
        with patch.object(factory, "lifestyle_available_memory_bytes", return_value=None):
            factory.validate_lifestyle_processing_memory(5000, 5000)
            for dimensions in ((5001, 5000), (0, 5), (-1, 5)):
                with self.assertRaisesRegex(ValueError, "pixel dimensions"):
                    factory.validate_lifestyle_processing_memory(*dimensions)

    def fixture(self, directory, version=2, member="/child"):
        root = Path(directory)
        mount = root / "memory"
        (mount / "child").mkdir(parents=True)
        (root / "cgroup").write_text(f"0::{member}\n" if version == 2 else f"5:memory:{member}\n")
        fs = "cgroup2 cgroup rw" if version == 2 else "cgroup cgroup rw,memory"
        (root / "mountinfo").write_text(f"1 0 0:1 / {mount.as_posix()} rw - {fs}\n")
        return root, mount

    def test_cgroup_v2_uses_tightest_ancestor_and_handles_unlimited_child(self):
        with tempfile.TemporaryDirectory() as directory:
            proc, mount = self.fixture(directory)
            (mount / "memory.max").write_text("512000000")
            (mount / "memory.current").write_text("400000000")
            (mount / "child/memory.max").write_text("max")
            self.assertEqual(factory._cgroup_memory_headroom(proc), 112000000)
            (mount / "child/memory.max").write_text("100000000")
            (mount / "child/memory.current").write_text("90000000")
            self.assertEqual(factory._cgroup_memory_headroom(proc), 10000000)
            (mount / "child/memory.current").write_text("110000000")
            self.assertEqual(factory._cgroup_memory_headroom(proc), 0)

    def test_cgroup_v1_finite_and_unlimited_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            proc, mount = self.fixture(directory, version=1)
            (mount / "child/memory.limit_in_bytes").write_text("512000000")
            (mount / "child/memory.usage_in_bytes").write_text("450000000")
            self.assertEqual(factory._cgroup_memory_headroom(proc), 62000000)
            (mount / "child/memory.limit_in_bytes").write_text(str(1 << 62))
            self.assertIsNone(factory._cgroup_memory_headroom(proc))

    def test_mounted_subtree_and_namespace_root(self):
        for member in ("/tenant/child", "/"):
            with self.subTest(member=member), tempfile.TemporaryDirectory() as directory:
                proc, mount = self.fixture(directory, member=member)
                info = (proc / "mountinfo").read_text().replace(" / ", " /tenant ")
                (proc / "mountinfo").write_text(info)
                (mount / "memory.max").write_text("100")
                (mount / "memory.current").write_text("80")
                self.assertEqual(factory._cgroup_memory_headroom(proc), 20)

    def test_host_available_is_capped_by_container(self):
        with patch.object(factory, "psutil", SimpleNamespace(virtual_memory=lambda: SimpleNamespace(available=4096))), \
             patch.object(factory, "_cgroup_memory_headroom", return_value=512):
            self.assertEqual(factory.lifestyle_available_memory_bytes(), 512)
        with patch.object(factory, "psutil", None), patch.object(factory, "_cgroup_memory_headroom", return_value=None):
            self.assertIsNone(factory.lifestyle_available_memory_bytes())

    def test_known_container_limit_with_missing_usage_fails_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            proc, mount = self.fixture(directory)
            (mount / "child/memory.max").write_text("512000000")
            with self.assertRaisesRegex(RuntimeError, "memory monitoring"):
                factory._cgroup_memory_headroom(proc)

    def test_concurrent_calls_serialize_decoded_work(self):
        entered, release, second_started = threading.Event(), threading.Event(), threading.Event()
        calls = []
        def process(*args):
            calls.append(args[1])
            if args[1] == "first":
                entered.set()
                self.assertTrue(release.wait(5))
            return {}
        def second():
            second_started.set()
            return factory.save_lifestyle_mockup("unused", "second", "afl", "prompt", io.BytesIO())
        with patch.object(factory, "_save_lifestyle_mockup", side_effect=process), ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(factory.save_lifestyle_mockup, "unused", "first", "afl", "prompt", io.BytesIO())
            try:
                self.assertTrue(entered.wait(5))
                other = executor.submit(second)
                self.assertTrue(second_started.wait(5))
                self.assertEqual(calls, ["first"])
            finally:
                release.set()
            first.result(timeout=5)
            other.result(timeout=5)
        self.assertEqual(calls, ["first", "second"])

    def test_low_headroom_fails_before_pixel_decode(self):
        stream = io.BytesIO()
        with Image.new("RGB", (1536, 1024)) as image:
            image.save(stream, "PNG")
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(factory, "lifestyle_available_memory_bytes", return_value=1), \
             patch.object(factory.ImageOps, "exif_transpose") as decode:
            with self.assertRaises(factory.MemoryLimitExceededError):
                factory.save_lifestyle_mockup(directory, "test", "afl", "01-man-cave-prompt.txt", stream)
            decode.assert_not_called()
            self.assertEqual(stream.tell(), 0)

    def test_decoded_images_released_and_existing_output_pixels_preserved(self):
        for mode, orientation in (("RGB", 1), ("RGBA", 1), ("RGB", 6)):
            with self.subTest(mode=mode, orientation=orientation), tempfile.TemporaryDirectory() as directory:
                stream = io.BytesIO()
                with Image.new(mode, (90, 60), (12, 34, 56)) as image:
                    image.putpixel((0, 0), (200, 100, 50) if mode == "RGB" else (200, 100, 50, 100))
                    exif = Image.Exif()
                    exif[274] = orientation
                    image.save(stream, "PNG", exif=exif)
                stream.seek(0)
                # Reference the previous transform and export settings.
                with Image.open(stream) as source:
                    transposed = ImageOps.exif_transpose(source)
                    rgb = transposed.convert("RGB")
                    fitted = ImageOps.fit(rgb, (60, 60), method=Image.LANCZOS)
                    expected = Path(directory) / "expected.jpg"
                    fitted.save(expected, "JPEG", quality=factory.EXPORT_JPG_QUALITY, optimize=True)
                    expected_webp = Path(directory) / "expected.webp"
                    fitted.save(expected_webp, "WEBP", quality=factory.EXPORT_WEBP_QUALITY, method=factory.EXPORT_WEBP_METHOD)
                    expected_preview = Path(directory) / "expected-preview.webp"
                    preview = fitted.copy()
                    preview.thumbnail((factory.MAX_PREVIEW_EDGE, factory.MAX_PREVIEW_EDGE), Image.LANCZOS)
                    preview.save(expected_preview, "WEBP", quality=factory.PREVIEW_WEBP_QUALITY, method=factory.PREVIEW_WEBP_METHOD)
                    preview.close()
                    for image in (transposed, rgb, fitted):
                        image.close()
                refs = []
                transpose, fit = ImageOps.exif_transpose, ImageOps.fit
                def track_transpose(image, **kwargs):
                    refs.append(weakref.ref(image))
                    self.assertTrue(kwargs["in_place"])
                    return transpose(image, **kwargs)
                def track_fit(*args, **kwargs):
                    image = fit(*args, **kwargs)
                    refs.append(weakref.ref(image))
                    return image
                with patch.object(factory, "lifestyle_available_memory_bytes", return_value=1024**3), \
                     patch.object(ImageOps, "exif_transpose", side_effect=track_transpose), \
                     patch.object(ImageOps, "fit", side_effect=track_fit):
                    paths = factory.save_lifestyle_mockup(directory, "test", "afl", "01-man-cave-prompt.txt", stream)
                gc.collect()
                self.assertTrue(all(ref() is None for ref in refs))
                self.assertEqual(Path(paths["jpg_path"]).read_bytes(), expected.read_bytes())
                self.assertEqual(Path(paths["webp_path"]).read_bytes(), expected_webp.read_bytes())
                self.assertEqual(Path(paths["preview_path"]).read_bytes(), expected_preview.read_bytes())

    def test_stage_markers_do_not_reject_process_rss(self):
        with patch.object(factory, "get_memory_usage_mb", return_value=431):
            self.assertEqual(factory.ensure_memory_available("export"), 431)


if __name__ == "__main__":
    unittest.main()
