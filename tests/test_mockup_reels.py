from pathlib import Path
import tempfile
import unittest
import zipfile

import image_factory


ROOT = Path(__file__).resolve().parents[1]


class MockupReelsTests(unittest.TestCase):
    def test_reels_prompts_are_registered_with_safe_filenames(self):
        specs_by_filename = {
            filename: (title, prompt)
            for filename, title, prompt in image_factory.LIFESTYLE_PROMPT_SPECS
        }
        expected = {
            "16-man-cave-reel-prompt.txt": "16-man-cave-reel",
            "17-living-room-reel-prompt.txt": "17-living-room-reel",
            "18-office-reel-prompt.txt": "18-office-reel",
            "19-home-sports-bar-reel-prompt.txt": "19-home-sports-bar-reel",
            "20-collector-display-room-reel-prompt.txt": "20-collector-display-room-reel",
        }

        self.assertEqual(len(image_factory.LIFESTYLE_PROMPT_SPECS), 20)
        for filename, safe_name in expected.items():
            self.assertIn(filename, specs_by_filename)
            self.assertEqual(image_factory.LIFESTYLE_IMAGE_VARIANTS[filename], safe_name)
            self.assertIn("1080 x 1920 vertical 9:16", specs_by_filename[filename][1])

    def test_reels_prompt_pack_uses_stable_prompt_keys_and_exact_reels_body(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            reference_path = run_dir / "reference.webp"
            reference_path.write_bytes(b"reference")

            prompt_dir, _, prompt_paths, _ = image_factory.generate_lifestyle_prompt_pack(
                "Test Product",
                "Soccer",
                "test-product",
                run_dir,
                reference_path,
            )

            prompt_names = {path.name for path in prompt_paths}
            self.assertIn("16-man-cave-reel-prompt.txt", prompt_names)
            self.assertEqual(len(prompt_paths), 20)

            reel_prompt = (prompt_dir / "16-man-cave-reel-prompt.txt").read_text(encoding="utf-8")
            self.assertTrue(reel_prompt.startswith("Using the uploaded Sports Cave artwork"))
            self.assertNotIn("Product name: Test Product", reel_prompt)
            self.assertIn("roughly 70–85% of the image width", reel_prompt)

    def test_complete_zip_includes_uploaded_reels_assets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_dir = Path(tmpdir) / "zip"
            zip_dir.mkdir()
            webp_path = Path(tmpdir) / "test-black-framed-soccer-16-man-cave-reel.webp"
            jpg_path = Path(tmpdir) / "test-black-framed-soccer-16-man-cave-reel.jpg"
            webp_path.write_bytes(b"webp")
            jpg_path.write_bytes(b"jpg")

            zip_path = image_factory.create_complete_pack_zip(
                zip_dir,
                "test-product",
                assets=[
                    {
                        "label": "16 - Man Cave Reel",
                        "include_in_zip": True,
                        "webp_path": str(webp_path),
                        "jpg_path": str(jpg_path),
                    }
                ],
            )

            with zipfile.ZipFile(zip_path) as archive:
                names = set(archive.namelist())

            self.assertIn("WEBP/test-black-framed-soccer-16-man-cave-reel.webp", names)
            self.assertIn("jpg/test-black-framed-soccer-16-man-cave-reel.jpg", names)

    def test_mockups_page_has_reels_section_and_no_drive_reminder_expander(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        result_render = source[
            source.index("def render_generation_result") : source.index("\n\ndef render_recent_runs_sidebar")
        ]

        self.assertIn('"Reels"', result_render)
        self.assertIn("Vertical 9:16 lifestyle mockups", result_render)
        self.assertIn("reels_prompts", result_render)
        self.assertNotIn("Local output and Google Drive reminder", result_render)


if __name__ == "__main__":
    unittest.main()
