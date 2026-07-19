from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import image_factory
import prompt_store
from sports_cave_prompt_blocks import (
    SPORTS_CAVE_PRODUCT_AND_ROOM_LOCK_BLOCK,
    SPORTS_CAVE_VIDEO_ARTWORK_FREEZE_LOCK,
)


ROOT = Path(__file__).resolve().parents[1]


class MockupReelsTests(unittest.TestCase):
    def test_legacy_reels_are_not_in_mockups_prompt_collection(self):
        specs_by_filename = {
            filename: (title, prompt)
            for filename, title, prompt in image_factory.LIFESTYLE_PROMPT_SPECS
        }
        legacy_specs_by_filename = {
            filename: (title, prompt)
            for filename, title, prompt in image_factory.LEGACY_MOCKUPS_REEL_PROMPT_SPECS
        }
        legacy_expected = {
            "16-man-cave-reel-prompt.txt": "16-man-cave-reel",
            "17-living-room-reel-prompt.txt": "17-living-room-reel",
            "18-office-reel-prompt.txt": "18-office-reel",
            "19-home-sports-bar-reel-prompt.txt": "19-home-sports-bar-reel",
            "20-collector-display-room-reel-prompt.txt": "20-collector-display-room-reel",
        }

        self.assertEqual(len(image_factory.LIFESTYLE_PROMPT_SPECS), 15)
        for filename, safe_name in legacy_expected.items():
            self.assertNotIn(filename, specs_by_filename)
            self.assertIn(filename, legacy_specs_by_filename)
            self.assertEqual(image_factory.LIFESTYLE_IMAGE_VARIANTS[filename], safe_name)
            self.assertIn("1080 x 1920 vertical 9:16", legacy_specs_by_filename[filename][1])

    def test_mockups_prompt_pack_excludes_legacy_reels_and_video_locks(self):
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
            self.assertEqual(len(prompt_paths), 15)
            self.assertNotIn("16-man-cave-reel-prompt.txt", prompt_names)
            self.assertNotIn("20-collector-display-room-reel-prompt.txt", prompt_names)

            for prompt_path in prompt_paths:
                with self.subTest(prompt=prompt_path.name):
                    prompt_text = prompt_path.read_text(encoding="utf-8")
                    self.assertIn(SPORTS_CAVE_PRODUCT_AND_ROOM_LOCK_BLOCK, prompt_text)
                    self.assertNotIn(SPORTS_CAVE_VIDEO_ARTWORK_FREEZE_LOCK, prompt_text)
                    self.assertNotIn("ARTWORK FREEZE LOCK", prompt_text)

            self.assertEqual(
                [path.name for path in prompt_paths],
                [filename for filename, _, _ in image_factory.LIFESTYLE_PROMPT_SPECS],
            )
            self.assertTrue(prompt_dir.exists())

    def test_complete_zip_includes_legacy_reel_assets_as_social_mockups_for_existing_runs(self):
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
                        "zip_group": "reels",
                        "webp_path": str(webp_path),
                        "jpg_path": str(jpg_path),
                    }
                ],
                zip_groups={image_factory.ASSET_CATEGORY_SOCIAL},
            )

            with zipfile.ZipFile(zip_path) as archive:
                names = set(archive.namelist())

            self.assertIn("WEBP/test-black-framed-soccer-16-man-cave-reel.webp", names)
            self.assertIn("jpg/test-black-framed-soccer-16-man-cave-reel.jpg", names)

    def test_complete_zip_filters_assets_by_group(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_dir = Path(tmpdir) / "zip"
            zip_dir.mkdir()
            asset_paths = {}
            for group in (
                image_factory.ASSET_CATEGORY_CORE,
                image_factory.ASSET_CATEGORY_PRODUCT,
                image_factory.ASSET_CATEGORY_SOCIAL,
            ):
                asset_path = Path(tmpdir) / f"{group}.webp"
                asset_path.write_bytes(group.encode("utf-8"))
                asset_paths[group] = asset_path

            zip_path = image_factory.create_complete_pack_zip(
                zip_dir,
                "test-product",
                assets=[
                    {
                        "label": group,
                        "include_in_zip": True,
                        "zip_group": group,
                        "webp_path": str(path),
                    }
                    for group, path in asset_paths.items()
                ],
                zip_groups={image_factory.ASSET_CATEGORY_CORE, image_factory.ASSET_CATEGORY_SOCIAL},
            )

            with zipfile.ZipFile(zip_path) as archive:
                names = set(archive.namelist())

            self.assertEqual(
                names,
                {
                    f"WEBP/{image_factory.ASSET_CATEGORY_CORE}.webp",
                    f"WEBP/{image_factory.ASSET_CATEGORY_SOCIAL}.webp",
                },
            )

    def test_complete_zip_uses_unique_archive_names_and_selected_count_matches_members(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_dir = Path(tmpdir) / "zip"
            zip_dir.mkdir()
            first = Path(tmpdir) / "first" / "duplicate.webp"
            second = Path(tmpdir) / "second" / "duplicate.webp"
            first.parent.mkdir()
            second.parent.mkdir()
            first.write_bytes(b"first")
            second.write_bytes(b"second")

            zip_path = image_factory.create_complete_pack_zip(
                zip_dir,
                "test-product",
                assets=[
                    {
                        "key": "social-one",
                        "label": "Social One",
                        "include_in_zip": True,
                        "zip_group": image_factory.ASSET_CATEGORY_SOCIAL,
                        "webp_path": str(first),
                    },
                    {
                        "key": "social-two",
                        "label": "Social Two",
                        "include_in_zip": True,
                        "zip_group": image_factory.ASSET_CATEGORY_SOCIAL,
                        "webp_path": str(second),
                    },
                ],
                zip_groups={image_factory.ASSET_CATEGORY_SOCIAL},
            )

            with zipfile.ZipFile(zip_path) as archive:
                names = archive.namelist()

            self.assertEqual(len(names), 2)
            self.assertEqual(len(set(names)), 2)
            self.assertTrue(all(name.startswith("WEBP/") for name in names))

    def test_prompt_override_lookup_for_legacy_reel_key_still_works(self):
        class FakeSupabaseBackend:
            class SupabaseNotConfigured(RuntimeError):
                pass

            def __init__(self):
                self.records = {}

            def is_configured(self):
                return True

            def ensure_prompt_template_schema(self):
                return None

            def get_prompt_template(self, prompt_key):
                return self.records.get(prompt_key)

            def upsert_prompt_template(self, prompt_key, **kwargs):
                record = {
                    "prompt_key": prompt_key,
                    "prompt_text": kwargs.get("prompt_text"),
                    "prompt_name": kwargs.get("prompt_name"),
                    "module": kwargs.get("module"),
                    "source": kwargs.get("source"),
                    "updated_by": kwargs.get("updated_by"),
                }
                self.records[prompt_key] = record
                return record

        backend = FakeSupabaseBackend()
        with patch.object(prompt_store, "_supabase_backend", return_value=backend):
            prompt_store.clear_prompt_cache()
            try:
                prompt_store.save_prompt(
                    "lifestyle::16-man-cave-reel",
                    "16 - Man Cave Reel",
                    "Edited reel prompt",
                )

                prompt_text = image_factory.get_lifestyle_prompt_text(
                    "16-man-cave-reel-prompt.txt",
                    "Default reel prompt",
                )
            finally:
                prompt_store.clear_prompt_cache()

        self.assertEqual(prompt_text, "Edited reel prompt")

    def test_mockups_page_no_longer_renders_reel_prompt_cards(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        result_render = source[
            source.index("def render_generation_result") : source.index("\n\ndef render_recent_runs_sidebar")
        ]
        prompt_cards = source[
            source.index("def render_prompt_cards") : source.index("\n\ndef render_optional_package_controls")
        ]
        mockup_actions = source[
            source.index("def render_mockup_prompt_editor") : source.index("\n\ndef prime_asset_selection_state")
        ]

        self.assertNotIn("reels_prompts", result_render)
        self.assertNotIn("Vertical 9:16 lifestyle mockups", result_render)
        self.assertIn("render_final_zip_download(result)", result_render)
        self.assertNotIn("render_primary_zip_download", result_render)
        self.assertNotIn("Save ZIP", result_render)
        self.assertNotIn("Open Drive Folder", result_render)
        self.assertNotIn("Download ZIP Instead", result_render)
        self.assertNotIn("Local output and Google Drive reminder", result_render)
        self.assertIn("current_lifestyle_prompt_text", prompt_cards)
        self.assertIn("render_mockup_prompt_action_row", prompt_cards)
        self.assertIn("render_mockup_prompt_bar(prompt_text", mockup_actions)
        self.assertNotIn("show_copy=False", prompt_cards)
        self.assertNotIn("if show_copy:", mockup_actions)
        self.assertIn("prompt_edit", mockup_actions)
        self.assertIn("mockup-prompt-edit-button", mockup_actions)
        self.assertIn("_mockup_prompt_edit_key(prompt_id)", mockup_actions)
        self.assertIn("st.text_area", mockup_actions)
        self.assertIn("prompt_store.save_prompt", mockup_actions)

    def test_final_zip_area_keeps_existing_filters_and_empty_selection_warning(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        final_zip = source[
            source.index("def render_final_zip_download") : source.index("\n\ndef render_prompt_cards")
        ]

        self.assertIn('st.subheader("Download ZIP")', final_zip)
        self.assertIn("Choose which image groups to include, then download one ZIP.", final_zip)
        for label in ("Core Images", "Social Mockups", "Product Images"):
            self.assertIn(label, source)
        self.assertIn("MOCKUPS_ZIP_GROUP_OPTIONS", final_zip)
        self.assertNotIn('"Reels"', source)
        self.assertIn("Select at least one image group to download.", final_zip)
        self.assertIn("value=True", final_zip)
        self.assertIn("zip_groups=selected_groups", source)


if __name__ == "__main__":
    unittest.main()
