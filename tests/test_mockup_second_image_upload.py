import io
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from PIL import Image

import app
import image_factory


class FakeSessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as error:
            raise AttributeError(name) from error

    def __setattr__(self, name, value):
        self[name] = value


class CountingUpload(io.BytesIO):
    def __init__(self, data, *, file_id, name="mockup.png", mime_type="image/png"):
        super().__init__(data)
        self.file_id = file_id
        self.name = name
        self.type = mime_type
        self.size = len(data)
        self.read_calls = 0

    def read(self, *args, **kwargs):
        self.read_calls += 1
        return super().read(*args, **kwargs)

    def getvalue(self):  # pragma: no cover - any call is a test failure.
        raise AssertionError("Mockups upload identity must not copy bytes with getvalue()")


def png_bytes(color):
    buffer = io.BytesIO()
    Image.new("RGB", (12, 12), color).save(buffer, format="PNG")
    return buffer.getvalue()


def bmp_bytes(color):
    buffer = io.BytesIO()
    Image.new("RGB", (12, 12), color).save(buffer, format="BMP")
    return buffer.getvalue()


def generation_result(run_dir="run-1"):
    return {
        "run_dir": run_dir,
        "product_name": "Existing Product",
        "product_slug": "existing-product",
        "sport_slug": "motorsport",
        "lifestyle_mockup_paths": {},
        "assets": [],
        "completed_work": {"core_design": "preserve-me"},
    }


def successful_save(call_log):
    def save(result, prompt_path, uploaded_file):
        prompt_name = Path(prompt_path).name
        call_log.append((prompt_name, uploaded_file.file_id))
        updated = dict(result)
        updated["lifestyle_mockup_paths"] = dict(result["lifestyle_mockup_paths"])
        updated["lifestyle_mockup_paths"][prompt_name] = {
            "jpg_path": f"{prompt_name}-{uploaded_file.file_id}.jpg",
            "preview_path": f"{prompt_name}-{uploaded_file.file_id}-preview.webp",
        }
        return updated

    return save


class MockupSecondImageUploadTests(unittest.TestCase):
    def setUp(self):
        app.image_factory = image_factory
        self.session_state = FakeSessionState(
            {
                "last_generation_result": None,
                "mockups_upload_identity_cache": {},
                "mockups_lifestyle_upload_lifecycle": {},
                "prompt_text": "Keep this prompt",
                "selected_mockup_option": "Keep this option",
                "task_metadata": {"completed": True},
            }
        )
        self.normalize_patch = patch.object(app, "normalize_generation_result", side_effect=lambda value: value)
        self.session_patch = patch.object(app.st, "session_state", self.session_state)
        self.normalize_patch.start()
        self.session_patch.start()

    def tearDown(self):
        self.session_patch.stop()
        self.normalize_patch.stop()

    def test_first_upload_processes_once_and_same_reruns_do_not_repeat_work(self):
        calls = []
        result = generation_result()
        prompt = Path("01-man-cave-prompt.txt")
        upload = CountingUpload(png_bytes((20, 40, 80)), file_id="upload-a")

        with patch.object(app, "save_uploaded_lifestyle_result", side_effect=successful_save(calls)):
            result = app.auto_register_lifestyle_upload(result, prompt, upload)
            reads_after_first_upload = upload.read_calls
            result = app.auto_register_lifestyle_upload(result, prompt, upload)
            result = app.auto_register_lifestyle_upload(result, prompt, upload)

        self.assertEqual(calls, [(prompt.name, "upload-a")])
        self.assertEqual(upload.read_calls, reads_after_first_upload)
        self.assertIn(prompt.name, result["lifestyle_mockup_paths"])
        self.assertEqual(app.get_lifestyle_upload_lifecycle(result, prompt)["status"], "SUCCEEDED")
        self.assertEqual(self.session_state["prompt_text"], "Keep this prompt")
        self.assertEqual(self.session_state["selected_mockup_option"], "Keep this option")

    def test_second_prompt_upload_preserves_first_image_and_task_state(self):
        calls = []
        result = generation_result()
        first_prompt = Path("01-man-cave-prompt.txt")
        second_prompt = Path("02-office-prompt.txt")
        first_upload = CountingUpload(png_bytes((10, 20, 30)), file_id="upload-a")
        second_upload = CountingUpload(png_bytes((30, 20, 10)), file_id="upload-b")

        with patch.object(app, "save_uploaded_lifestyle_result", side_effect=successful_save(calls)):
            result = app.auto_register_lifestyle_upload(result, first_prompt, first_upload)
            result = app.auto_register_lifestyle_upload(result, second_prompt, second_upload)
            result = app.auto_register_lifestyle_upload(result, first_prompt, first_upload)
            result = app.auto_register_lifestyle_upload(result, second_prompt, second_upload)

        self.assertEqual(calls, [(first_prompt.name, "upload-a"), (second_prompt.name, "upload-b")])
        self.assertEqual(set(result["lifestyle_mockup_paths"]), {first_prompt.name, second_prompt.name})
        self.assertEqual(result["completed_work"], {"core_design": "preserve-me"})
        self.assertEqual(self.session_state["task_metadata"], {"completed": True})

    def test_same_filename_with_different_content_is_a_new_replacement(self):
        calls = []
        result = generation_result()
        prompt = Path("01-man-cave-prompt.txt")
        first = CountingUpload(png_bytes((1, 2, 3)), file_id="upload-a", name="same-name.png")
        second = CountingUpload(png_bytes((3, 2, 1)), file_id="upload-b", name="same-name.png")

        with patch.object(app, "save_uploaded_lifestyle_result", side_effect=successful_save(calls)):
            result = app.auto_register_lifestyle_upload(result, prompt, first)
            first_signature = app.get_lifestyle_upload_lifecycle(result, prompt)["content_signature"]
            result = app.auto_register_lifestyle_upload(result, prompt, second)
            second_signature = app.get_lifestyle_upload_lifecycle(result, prompt)["content_signature"]

        self.assertNotEqual(first_signature, second_signature)
        self.assertEqual(calls, [(prompt.name, "upload-a"), (prompt.name, "upload-b")])
        self.assertTrue(result["lifestyle_mockup_paths"][prompt.name]["jpg_path"].endswith("upload-b.jpg"))

    def test_same_content_with_a_different_name_does_not_consume_another_job(self):
        calls = []
        result = generation_result()
        prompt = Path("01-man-cave-prompt.txt")
        content = png_bytes((1, 20, 200))
        first = CountingUpload(content, file_id="upload-a", name="first-name.png")
        renamed = CountingUpload(content, file_id="upload-b", name="renamed.png")

        with patch.object(app, "save_uploaded_lifestyle_result", side_effect=successful_save(calls)):
            result = app.auto_register_lifestyle_upload(result, prompt, first)
            result = app.auto_register_lifestyle_upload(result, prompt, renamed)

        self.assertEqual(calls, [(prompt.name, "upload-a")])
        self.assertTrue(result["lifestyle_mockup_paths"][prompt.name]["jpg_path"].endswith("upload-a.jpg"))

    def test_failed_replacement_is_terminal_until_file_changes_and_next_upload_recovers(self):
        calls = []
        result = generation_result()
        prompt = Path("01-man-cave-prompt.txt")
        first = CountingUpload(png_bytes((1, 2, 3)), file_id="upload-a")
        failing = CountingUpload(png_bytes((4, 5, 6)), file_id="upload-b")
        recovery = CountingUpload(png_bytes((7, 8, 9)), file_id="upload-c")
        normal_save = successful_save(calls)

        def save(result_value, prompt_path, uploaded_file):
            if uploaded_file.file_id == "upload-b":
                calls.append((Path(prompt_path).name, uploaded_file.file_id))
                raise image_factory.MemoryLimitExceededError("Memory limit reached while preparing image.")
            return normal_save(result_value, prompt_path, uploaded_file)

        with patch.object(app, "save_uploaded_lifestyle_result", side_effect=save):
            result = app.auto_register_lifestyle_upload(result, prompt, first)
            previous_paths = dict(result["lifestyle_mockup_paths"])
            with self.assertRaises(image_factory.MemoryLimitExceededError):
                app.auto_register_lifestyle_upload(result, prompt, failing)
            failed_lifecycle = app.get_lifestyle_upload_lifecycle(result, prompt)
            self.assertEqual(failed_lifecycle["status"], "FAILED")
            self.assertNotEqual(failed_lifecycle["status"], "PROCESSING")
            self.assertEqual(self.session_state["last_generation_result"]["lifestyle_mockup_paths"], previous_paths)
            result = app.auto_register_lifestyle_upload(result, prompt, failing)
            result = app.auto_register_lifestyle_upload(result, prompt, recovery)

        self.assertEqual(calls, [(prompt.name, "upload-a"), (prompt.name, "upload-b"), (prompt.name, "upload-c")])
        self.assertEqual(app.get_lifestyle_upload_lifecycle(result, prompt)["status"], "SUCCEEDED")
        self.assertTrue(result["lifestyle_mockup_paths"][prompt.name]["jpg_path"].endswith("upload-c.jpg"))
        self.assertEqual(self.session_state["prompt_text"], "Keep this prompt")

    def test_invalid_upload_is_not_revalidated_on_every_rerun(self):
        calls = []
        result = generation_result()
        prompt = Path("01-man-cave-prompt.txt")
        invalid = CountingUpload(png_bytes((1, 2, 3)), file_id="invalid-upload")
        invalid.size = image_factory.MAX_LIFESTYLE_UPLOAD_SIZE_BYTES + 1
        recovery = CountingUpload(png_bytes((3, 2, 1)), file_id="recovery-upload")

        with patch.object(app, "save_uploaded_lifestyle_result", side_effect=successful_save(calls)):
            with self.assertRaises(ValueError):
                app.auto_register_lifestyle_upload(result, prompt, invalid)
            reads_after_failure = invalid.read_calls
            returned = app.auto_register_lifestyle_upload(result, prompt, invalid)
            returned = app.auto_register_lifestyle_upload(returned, prompt, recovery)

        self.assertEqual(invalid.read_calls, reads_after_failure)
        self.assertEqual(calls, [(prompt.name, "recovery-upload")])
        self.assertEqual(app.get_lifestyle_upload_lifecycle(returned, prompt)["status"], "SUCCEEDED")

    def test_superseded_completion_cannot_overwrite_newer_authoritative_result(self):
        result = generation_result()
        prompt = Path("01-man-cave-prompt.txt")
        upload = CountingUpload(png_bytes((11, 22, 33)), file_id="upload-a")
        newer_result = generation_result()
        newer_result["lifestyle_mockup_paths"][prompt.name] = {"jpg_path": "newer-b.jpg"}

        def complete_after_superseded(result_value, prompt_path, uploaded_file):
            slot_key = app.get_lifestyle_upload_slot_key(result_value, prompt_path)
            app._store_lifestyle_upload_lifecycle(
                slot_key,
                {
                    "content_signature": "newer-signature",
                    "request_id": "newer-request",
                    "status": "PROCESSING",
                    "started_at": time.time(),
                    "error_message": "",
                },
            )
            self.session_state["last_generation_result"] = newer_result
            stale_result = dict(result_value)
            stale_result["lifestyle_mockup_paths"] = {prompt.name: {"jpg_path": "stale-a.jpg"}}
            return stale_result

        with patch.object(app, "save_uploaded_lifestyle_result", side_effect=complete_after_superseded):
            returned = app.auto_register_lifestyle_upload(result, prompt, upload)

        self.assertEqual(returned["lifestyle_mockup_paths"][prompt.name]["jpg_path"], "newer-b.jpg")
        self.assertEqual(self.session_state["last_generation_result"], newer_result)
        self.assertNotIn(f"lifestyle-upload-signature::{result['run_dir']}::{prompt.name}", self.session_state)

    def test_stale_processing_record_is_released_without_restarting_work(self):
        result = generation_result()
        prompt = Path("01-man-cave-prompt.txt")
        upload = CountingUpload(png_bytes((90, 80, 70)), file_id="upload-a")
        signature = app.get_uploaded_lifestyle_signature(upload)
        slot_key = app.get_lifestyle_upload_slot_key(result, prompt)
        app._store_lifestyle_upload_lifecycle(
            slot_key,
            {
                "content_signature": signature,
                "request_id": "stale-request",
                "status": "PROCESSING",
                "started_at": time.time() - app.MOCKUPS_LIFESTYLE_UPLOAD_PROCESSING_STALE_SECONDS - 1,
                "error_message": "",
            },
        )

        with patch.object(app, "save_uploaded_lifestyle_result") as save:
            returned = app.auto_register_lifestyle_upload(result, prompt, upload)

        save.assert_not_called()
        self.assertIs(returned, result)
        lifecycle = app.get_lifestyle_upload_lifecycle(result, prompt)
        self.assertEqual(lifecycle["status"], "FAILED")
        self.assertIn("did not finish", lifecycle["error_message"])

    def test_primary_artwork_cache_uses_content_not_filename_size_or_type(self):
        first_bytes = bmp_bytes((10, 20, 30))
        second_bytes = bmp_bytes((30, 20, 10))
        self.assertEqual(len(first_bytes), len(second_bytes))
        first = CountingUpload(first_bytes, file_id="main-a", name="same.png")
        second = CountingUpload(second_bytes, file_id="main-b", name="same.png")

        with tempfile.TemporaryDirectory() as tmpdir, patch.object(
            app, "UPLOAD_PREVIEW_DIR", Path(tmpdir)
        ):
            first_details = app.process_uploaded_artwork_once(first)
            first_read_count = first.read_calls
            repeated_details = app.process_uploaded_artwork_once(first)
            second_details = app.process_uploaded_artwork_once(second)

        self.assertEqual(first_details, repeated_details)
        self.assertEqual(first.read_calls, first_read_count)
        self.assertNotEqual(first_details["signature"], second_details["signature"])
        self.assertEqual((first_details["width"], first_details["height"]), (12, 12))
        self.assertEqual((second_details["width"], second_details["height"]), (12, 12))

    def test_lifestyle_upload_handler_contains_no_rerun_loop(self):
        source = Path(app.__file__).read_text(encoding="utf-8")
        handler = source[
            source.index("def auto_register_lifestyle_upload")
            : source.index("\n\ndef render_asset_selection_controls")
        ]
        self.assertNotIn("st.rerun", handler)


if __name__ == "__main__":
    unittest.main()
