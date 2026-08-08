from pathlib import Path
from unittest.mock import patch
import io
import os
import tempfile
import unittest

from PIL import Image

import app
import dropbox_integration
import image_factory
import mockup_storage


TEMPLATE_NAMES = (
    "black-frame-template.jpg",
    "oak-frame-template.jpg",
    "white-frame-template.jpg",
    "unframed-template.jpg",
    "size-guide-template.jpg",
)


class NoGetValueUpload(io.BytesIO):
    def __init__(self, data, name="huge-artwork.jpg", mime_type="image/jpeg"):
        super().__init__(data)
        self.name = name
        self.type = mime_type
        self.size = len(data)

    def getvalue(self):  # pragma: no cover - the test fails if this is called.
        raise AssertionError("getvalue() should not be used for mockups upload validation")


class FakeSessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as error:
            raise AttributeError(name) from error

    def __setattr__(self, name, value):
        self[name] = value


def jpeg_bytes(size=(4200, 2400), color=(12, 34, 56)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="JPEG", quality=82)
    return buffer.getvalue()


def write_test_templates(base_dir):
    templates_dir = Path(base_dir) / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)
    for name in TEMPLATE_NAMES:
        Image.new("RGB", (1000, 1000), (230, 226, 218)).save(
            templates_dir / name,
            format="JPEG",
            quality=92,
        )


def write_source_image(path):
    Image.new("RGB", (1200, 800), (20, 50, 90)).save(path, format="JPEG", quality=92)


def assert_lightweight(value, path="root"):
    heavy_types = (bytes, bytearray, io.BytesIO, Image.Image)
    if isinstance(value, heavy_types):
        raise AssertionError(f"{path} retained heavyweight image data: {type(value).__name__}")
    if isinstance(value, str) and len(value) > 4096 and "base64" in value.casefold():
        raise AssertionError(f"{path} retained a base64-like string")
    if isinstance(value, dict):
        for key, child in value.items():
            assert_lightweight(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            assert_lightweight(child, f"{path}[{index}]")


class MockupMemoryPipelineTests(unittest.TestCase):
    def test_high_resolution_upload_validation_streams_without_getvalue(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            app.image_factory = image_factory
            session_state = FakeSessionState()
            upload = NoGetValueUpload(jpeg_bytes())
            preview_dir = Path(tmpdir) / "previews"
            with patch.object(app.st, "session_state", session_state), patch.object(
                app,
                "UPLOAD_PREVIEW_DIR",
                preview_dir,
            ):
                details = app.process_uploaded_artwork_once(upload)

            self.assertEqual(details["width"], 4200)
            self.assertEqual(details["height"], 2400)
            self.assertNotIn("data", session_state["mockups_upload_processing_cache"])
            assert_lightweight(session_state)

    def test_outputs_upload_and_release_sequentially(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"SPORTS_CAVE_TEMP_DIR": tmpdir}):
                base_dir = Path(tmpdir) / "base"
                write_test_templates(base_dir)
                source_path = Path(tmpdir) / "source.jpg"
                write_source_image(source_path)
                temp_root = image_factory.create_temp_run_parent()
                uploaded_local_paths = []
                previous_local_paths = []
                uploaded_dimensions = {}

                def fake_upload(_token, dropbox_path, stream, **kwargs):
                    self.assertEqual(kwargs.get("simple_limit"), 0)
                    self.assertEqual(
                        kwargs.get("chunk_size"),
                        mockup_storage.MOCKUP_DROPBOX_UPLOAD_CHUNK_SIZE,
                    )
                    local_path = Path(stream.name)
                    self.assertTrue(local_path.exists())
                    with Image.open(stream) as generated:
                        uploaded_dimensions[Path(dropbox_path).name] = generated.size
                    uploaded_local_paths.append(str(local_path))
                    return {
                        ".tag": "file",
                        "id": f"id:{Path(dropbox_path).name}",
                        "name": Path(dropbox_path).name,
                        "path_display": dropbox_path,
                        "size": local_path.stat().st_size,
                    }

                def upload_callback(asset_record, job, *, run_dir):
                    del job, run_dir
                    for previous in previous_local_paths:
                        self.assertFalse(Path(previous).exists())
                    result = mockup_storage.upload_asset_files_to_dropbox(
                        "token",
                        "/Sportscave Team Folder/04_OUTPUT/product-images/apptest-product",
                        asset_record,
                    )
                    previous_local_paths.extend(
                        str(asset_record[key])
                        for key in ("review_path", "webp_path", "jpg_path")
                        if asset_record.get(key)
                    )
                    return result["asset"]

                with patch.object(
                    dropbox_integration,
                    "upload_stream",
                    side_effect=fake_upload,
                ):
                    result = image_factory.generate_product_images(
                        "Apptest Product",
                        "AFL",
                        source_path,
                        base_dir=base_dir,
                        output_root=temp_root,
                        asset_completed_callback=upload_callback,
                    )

                self.assertEqual(len(result["assets"]), 5)
                self.assertEqual(len(uploaded_local_paths), 10)
                for path in previous_local_paths:
                    self.assertFalse(Path(path).exists())
                for asset in result["assets"]:
                    self.assertIsNone(asset["review_path"])
                    self.assertIsNone(asset["webp_path"])
                    self.assertIsNone(asset["jpg_path"])
                    self.assertTrue(asset["preview_path"])
                    self.assertTrue(Path(asset["preview_path"]).exists())
                    self.assertTrue(asset["webp_path_dropbox_path"].startswith("/Sportscave Team Folder/"))
                    self.assertTrue(asset["jpg_path_dropbox_path"].startswith("/Sportscave Team Folder/"))
                self.assertEqual(
                    uploaded_dimensions["apptest-product-black-framed-afl-wall-art.webp"],
                    (1000, 1000),
                )
                self.assertEqual(
                    uploaded_dimensions["apptest-product-black-framed-afl-wall-art.jpg"],
                    (1000, 1000),
                )
                assert_lightweight(result)

    def test_final_result_records_dropbox_metadata_and_no_master_paths_after_success(self):
        result = {
            "product_name": "Apptest Product",
            "sport_category": "AFL",
            "run_dir": "/tmp/sports-cave-image-factory/mockup-runs/mockup-run-apptest",
            "product_slug": "apptest-product",
            "assets": [
                {
                    "key": "black",
                    "label": "Black Framed",
                    "webp_path": None,
                    "jpg_path": None,
                    "webp_path_dropbox_path": "/Sportscave Team Folder/04_OUTPUT/product-images/apptest/WEBP/black.webp",
                    "jpg_path_dropbox_path": "/Sportscave Team Folder/04_OUTPUT/product-images/apptest/jpg/black.jpg",
                }
            ],
        }
        final = app.finalise_mockups_dropbox_result(
            result,
            {
                "root_path": "/Sportscave Team Folder",
                "destination": "/Sportscave Team Folder/04_OUTPUT/product-images/apptest",
                "destination_parent": "/Sportscave Team Folder/04_OUTPUT/product-images",
            },
            [{"relative_path": "WEBP/black.webp", "metadata": {"id": "id:black"}}],
            [],
        )

        self.assertEqual(final["dropbox_upload_status"], "saved")
        self.assertEqual(
            final["black_framed_dropbox_path"],
            "/Sportscave Team Folder/04_OUTPUT/product-images/apptest/WEBP/black.webp",
        )
        self.assertEqual(final["dropbox_retry_files"], [])
        assert_lightweight(final)

    def test_dropbox_failure_keeps_retry_file_without_ram_image_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"SPORTS_CAVE_TEMP_DIR": tmpdir}):
                temp_root = image_factory.create_temp_run_parent()
                run_dir = temp_root / "mockup-run-failure"
                webp_path = run_dir / image_factory.WEBP_CACHE_FOLDER_NAME / "hero.webp"
                jpg_path = run_dir / image_factory.JPG_CACHE_FOLDER_NAME / "hero.jpg"
                webp_path.parent.mkdir(parents=True)
                jpg_path.parent.mkdir(parents=True)
                Image.new("RGB", (20, 20), (1, 2, 3)).save(webp_path, format="WEBP")
                Image.new("RGB", (20, 20), (1, 2, 3)).save(jpg_path, format="JPEG")
                asset = {
                    "key": "black",
                    "label": "Black Framed",
                    "webp_path": webp_path,
                    "jpg_path": jpg_path,
                }

                with patch.object(
                    dropbox_integration,
                    "upload_stream",
                    side_effect=dropbox_integration.DropboxApiError("temporary failure"),
                ):
                    upload = mockup_storage.upload_asset_files_to_dropbox(
                        "token",
                        "/Sportscave Team Folder/04_OUTPUT/product-images/failure",
                        asset,
                        retries=1,
                    )

                self.assertEqual(upload["asset"]["dropbox_upload_status"], "failed")
                self.assertEqual(len(upload["retry_files"]), 2)
                self.assertTrue(webp_path.exists())
                self.assertTrue(jpg_path.exists())
                assert_lightweight(upload)

    def test_retry_uploads_do_not_regenerate_and_remove_retry_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"SPORTS_CAVE_TEMP_DIR": tmpdir}):
                temp_root = image_factory.create_temp_run_parent()
                run_dir = temp_root / "mockup-run-retry"
                webp_path = run_dir / image_factory.WEBP_CACHE_FOLDER_NAME / "hero.webp"
                webp_path.parent.mkdir(parents=True)
                Image.new("RGB", (20, 20), (1, 2, 3)).save(webp_path, format="WEBP")
                result = {
                    "run_dir": str(run_dir),
                    "dropbox_saved_path": "/Sportscave Team Folder/04_OUTPUT/product-images/retry",
                    "assets": [{"key": "black", "webp_path": str(webp_path), "jpg_path": None}],
                }
                upload_calls = []

                def fake_upload(_token, dropbox_path, stream, **kwargs):
                    self.assertEqual(kwargs.get("simple_limit"), 0)
                    upload_calls.append((dropbox_path, str(stream.name)))
                    return {
                        ".tag": "file",
                        "id": "id:hero",
                        "name": "hero.webp",
                        "path_display": dropbox_path,
                        "size": Path(stream.name).stat().st_size,
                    }

                with patch.object(
                    dropbox_integration,
                    "upload_stream",
                    side_effect=fake_upload,
                ), patch.object(image_factory, "generate_product_images") as generator:
                    updated = mockup_storage.retry_result_uploads("token", result)

                generator.assert_not_called()
                self.assertEqual(len(upload_calls), 1)
                self.assertFalse(webp_path.exists())
                self.assertEqual(updated["dropbox_upload_status"], "saved")
                self.assertEqual(updated["dropbox_retry_files"], [])

    def test_mockups_generation_does_not_auto_save_to_dropbox(self):
        source = Path(app.__file__).read_text(encoding="utf-8")
        block = source[
            source.index("if generate_clicked:")
            : source.index("if st.session_state.last_generation_result is not None:")
        ]

        self.assertNotIn("_files_access_token()", block)
        self.assertNotIn("resolve_mockups_dropbox_run", block)
        self.assertNotIn("asset_completed_callback=", block)
        self.assertNotIn("finalise_mockups_dropbox_result", block)
        self.assertIn("temporary_until_manual_save", block)

    def test_manual_mockup_save_uses_streaming_upload_batch(self):
        source = Path(app.__file__).read_text(encoding="utf-8")
        block = source[
            source.index("def _save_mockups_to_dropbox")
            : source.index("\n\ndef _open_files_folder")
        ]

        self.assertIn("dropbox_integration.upload_batch", block)
        self.assertIn("simple_limit=0", block)
        self.assertIn("chunk_size=mockup_storage.MOCKUP_DROPBOX_UPLOAD_CHUNK_SIZE", block)

    def test_duplicate_generation_guard_is_nonblocking(self):
        self.assertTrue(app.MOCKUPS_GENERATION_SEMAPHORE.acquire(blocking=False))
        try:
            self.assertFalse(app.MOCKUPS_GENERATION_SEMAPHORE.acquire(blocking=False))
        finally:
            app.MOCKUPS_GENERATION_SEMAPHORE.release()

    def test_memory_error_is_rendered_once_in_mockups_page(self):
        source = Path(app.__file__).read_text(encoding="utf-8")
        block = source[
            source.index("except image_factory.MemoryLimitExceededError")
            : source.index("except Exception as error:", source.index("except image_factory.MemoryLimitExceededError"))
        ]
        self.assertEqual(block.count("status_container.error(str(error))"), 1)
        self.assertNotIn("st.error(str(error))", block)


if __name__ == "__main__":
    unittest.main()
