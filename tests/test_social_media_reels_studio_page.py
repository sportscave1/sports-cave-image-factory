from pathlib import Path
import base64
import io
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from PIL import Image

import social_media_reels_studio_page as reels
from sports_cave_prompt_blocks import (
    SPORTS_CAVE_PRODUCT_AND_ROOM_LOCK_BLOCK,
    SPORTS_CAVE_UGC_HUMAN_REALISM_BLOCK,
    SPORTS_CAVE_UGC_VIDEO_REALISM_BLOCK,
)


ROOT = Path(__file__).resolve().parents[1]


class SocialMediaReelsStudioPageTests(unittest.TestCase):
    def _png_bytes(self, size=(3, 2), color=(212, 165, 76)):
        buffer = io.BytesIO()
        Image.new("RGB", size, color).save(buffer, format="PNG")
        return buffer.getvalue()

    def test_app_sidebar_and_router_include_reels_studio_page(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")

        self.assertIn('"Social Media Reels Studio"', source)
        self.assertIn("get_social_media_reels_studio_page().render_page()", source)

    def test_video_filename_generator_for_required_handles(self):
        handles = [
            "roger-federer",
            "cristiano-ronaldo-black-framed-soccer-sports-wall-art",
            "legends-never-die-kobe-jordan",
            "mbappe-born-for-the-world-stage",
        ]

        for handle in handles:
            with self.subTest(handle=handle):
                self.assertEqual(
                    reels.video_filename(handle, "collector-admire", "v01", "final"),
                    f"{handle}__meta-reel__collector-admire__9x16__v01__final.mp4",
                )
                self.assertEqual(
                    reels.image_mockup_filename(handle, "wall-only"),
                    f"{handle}__mockup__wall-only__1x1__v01__final.png",
                )

    def test_handle_sanitizer_and_filename_status_version(self):
        self.assertEqual(reels.sanitize_handle("Mbappe Born For The World Stage!!"), "mbappe-born-for-the-world-stage")
        self.assertEqual(
            reels.video_filename("Roger Federer", "wall-admire", "2", "ad-test"),
            "roger-federer__meta-reel__wall-admire__9x16__v02__ad-test.mp4",
        )

    def test_filename_parsing_removes_uuid_and_detects_sport(self):
        cases = [
            (
                "cristiano-ronaldo-soccer-art-e157b372-b7b0-4fa7-a667-b6aaca3ed2a5.jpeg",
                "cristiano-ronaldo-soccer-art",
                "Cristiano Ronaldo Soccer Art",
                "Soccer",
            ),
            (
                "roger-federer-the-art-of-greatness.png",
                "roger-federer-the-art-of-greatness",
                "Roger Federer The Art Of Greatness",
                "Tennis",
            ),
            (
                "legends-never-die-kobe-jordan.webp",
                "legends-never-die-kobe-jordan",
                "Legends Never Die Kobe Jordan",
                "Basketball",
            ),
            (
                "mbappe-born-for-the-world-stage.jpg",
                "mbappe-born-for-the-world-stage",
                "Mbappe Born For The World Stage",
                "Soccer",
            ),
            (
                "peter-brock-bathurst-v8-supercars.jpeg",
                "peter-brock-bathurst-v8-supercars",
                "Peter Brock Bathurst V8 Supercars",
                "Motorsport",
            ),
            (
                "ohtani-judge-legends-never-die-baseball.png",
                "ohtani-judge-legends-never-die-baseball",
                "Ohtani Judge Legends Never Die Baseball",
                "Baseball",
            ),
        ]

        for filename, handle, title, sport in cases:
            with self.subTest(filename=filename):
                details = reels.derive_product_details_from_filename(filename)
                self.assertEqual(details["product_handle"], handle)
                self.assertEqual(details["product_title"], title)
                self.assertEqual(details["sport_category"], sport)

    def test_sport_detection_ambiguity_and_meaningful_numbers(self):
        self.assertEqual(reels.detect_sport_category("classic-football-wall-art"), "Soccer")
        self.assertEqual(reels.detect_sport_category("brady-super-bowl-football-wall-art"), "NFL")
        self.assertEqual(reels.strip_trailing_random_id("lebron-23"), "lebron-23")

    def test_image_asset_preserves_original_bytes_and_dimensions(self):
        original = self._png_bytes(size=(7, 5))
        asset = reels.image_asset_from_bytes(original, "Original Mockup.PNG", "image/png", source="upload")

        self.assertEqual(asset["bytes"], original)
        self.assertEqual(asset["width"], 7)
        self.assertEqual(asset["height"], 5)
        self.assertEqual(asset["size_bytes"], len(original))
        self.assertEqual(asset["mime_type"], "image/png")
        self.assertEqual(asset["source"], "upload")
        self.assertTrue(reels.has_valid_image_asset(asset))

    def test_pasted_image_payload_decodes_and_generates_safe_filename(self):
        original = self._png_bytes(size=(4, 4))
        payload = {
            "filename": "",
            "mime": "image/png",
            "data_base64": base64.b64encode(original).decode("ascii"),
            "source": "paste",
        }

        asset = reels.image_asset_from_paste_payload(payload, "roger-federer", "mockup", "collector-admire")

        self.assertIsNotNone(asset)
        self.assertEqual(asset["bytes"], original)
        self.assertEqual(asset["filename"], "roger-federer__mockup__collector-admire__pasted__v01.png")
        self.assertEqual(asset["source"], "paste")
        self.assertEqual(asset["width"], 4)
        self.assertEqual(asset["height"], 4)
        self.assertTrue(reels.has_valid_image_asset(asset))

    def test_dropped_image_payload_decodes_as_valid_asset(self):
        original = self._png_bytes(size=(5, 3))
        payload = {
            "filename": "Dropped Image.PNG",
            "mime": "image/png",
            "data_base64": base64.b64encode(original).decode("ascii"),
            "source": "drop",
        }

        asset = reels.image_asset_from_paste_payload(payload, "roger-federer", "product-mockup")

        self.assertEqual(asset["bytes"], original)
        self.assertEqual(asset["source"], "drop")
        self.assertTrue(reels.has_valid_image_asset(asset))

    def test_wizard_unlocks_are_linear(self):
        self.assertEqual(
            reels.wizard_unlocks({}),
            {"step_1": True, "step_2": False, "step_3": False, "step_4": False, "step_5": False},
        )
        self.assertTrue(reels.wizard_unlocks({"reels_step_1_complete": True})["step_2"])
        self.assertFalse(reels.wizard_unlocks({"reels_step_1_complete": True})["step_3"])
        self.assertTrue(
            reels.wizard_unlocks({"reels_step_1_complete": True, "reels_step_2_complete": True})["step_3"]
        )
        self.assertFalse(
            reels.wizard_unlocks(
                {
                    "reels_step_1_complete": True,
                    "reels_step_2_complete": True,
                    "reels_step_3_complete": True,
                }
            )["step_5"]
        )
        self.assertTrue(reels.wizard_unlocks({"reels_step_3_complete": True})["step_4"])
        self.assertTrue(reels.wizard_unlocks({"reels_step_4_complete": True})["step_5"])

    def test_wizard_completion_is_based_on_valid_image_assets(self):
        original = self._png_bytes(size=(8, 8))
        product = reels.image_asset_from_bytes(original, "product.png", "image/png", source="upload")
        background = reels.image_asset_from_bytes(original, "background.png", "image/png", source="paste")
        mockup = reels.image_asset_from_bytes(original, "mockup.png", "image/png", source="drop")
        state = {
            "files": {
                "product_mockup": product,
                "selected_background": background,
                "image_mockups": {"collector-admire": mockup},
                "videos": {},
            }
        }

        try:
            reels._ensure_wizard_flags()
            reels._sync_wizard_completion_from_assets(state)
            flags = reels._wizard_flags()
        finally:
            for key in reels.WIZARD_FLAG_DEFAULTS:
                reels.st.session_state.pop(key, None)

        self.assertTrue(flags["reels_step_1_complete"])
        self.assertTrue(flags["reels_step_2_complete"])
        self.assertTrue(flags["reels_step_3_complete"])
        self.assertTrue(reels.wizard_unlocks(flags)["step_2"])
        self.assertTrue(reels.wizard_unlocks(flags)["step_3"])
        self.assertTrue(reels.wizard_unlocks(flags)["step_4"])

    def test_step_one_upload_paste_and_drop_assets_unlock_step_two(self):
        for source in ("upload", "paste", "drop"):
            with self.subTest(source=source):
                asset = reels.image_asset_from_bytes(
                    self._png_bytes(size=(6, 4)),
                    f"{source}-product.png",
                    "image/png",
                    source=source,
                )
                state = {
                    "files": {
                        "product_mockup": asset,
                        "selected_background": None,
                        "image_mockups": {},
                        "videos": {},
                    }
                }
                try:
                    reels._ensure_wizard_flags()
                    reels._sync_wizard_completion_from_assets(state)
                    unlocks = reels.wizard_unlocks(reels._wizard_flags())
                finally:
                    for key in reels.WIZARD_FLAG_DEFAULTS:
                        reels.st.session_state.pop(key, None)

                self.assertTrue(unlocks["step_2"])

    def test_image_display_uses_original_bytes_without_action_buttons(self):
        original = self._png_bytes(size=(10, 10))
        asset = reels.image_asset_from_bytes(original, "full-res.png", "image/png", source="upload")

        with patch.object(reels.st, "image") as image_mock:
            reels.render_full_resolution_image_tools(asset, "Product Mockup", "test_product")

        image_mock.assert_called()
        self.assertEqual(image_mock.call_args.args[0], original)

        source = (ROOT / "social_media_reels_studio_page.py").read_text(encoding="utf-8")
        self.assertNotIn("Download original", source)
        self.assertNotIn("Open full-resolution image", source)
        self.assertNotIn("Copy full-res image", source)
        self.assertNotIn("Copy not available in this browser", source)

    def test_person_image_prompts_include_ugc_human_realism_block(self):
        prompts = reels.build_image_prompts("roger-federer", "Roger Federer", "Tennis", "")

        self.assertIn(SPORTS_CAVE_UGC_HUMAN_REALISM_BLOCK, prompts["wall-hanging-adjust"])
        self.assertIn(SPORTS_CAVE_UGC_HUMAN_REALISM_BLOCK, prompts["collector-admire"])
        self.assertIn(SPORTS_CAVE_PRODUCT_AND_ROOM_LOCK_BLOCK, prompts["wall-hanging-adjust"])
        self.assertIn(SPORTS_CAVE_PRODUCT_AND_ROOM_LOCK_BLOCK, prompts["collector-admire"])

    def test_artwork_only_prompt_excludes_human_block_but_keeps_product_lock(self):
        prompt = reels.build_image_prompts("roger-federer", "Roger Federer", "Tennis", "")["wall-only"]

        self.assertNotIn(SPORTS_CAVE_UGC_HUMAN_REALISM_BLOCK, prompt)
        self.assertIn(SPORTS_CAVE_PRODUCT_AND_ROOM_LOCK_BLOCK, prompt)

    def test_person_video_prompt_includes_video_and_product_lock_blocks(self):
        prompts = reels.build_video_prompts("roger-federer", "Roger Federer", "Tennis")

        self.assertIn(SPORTS_CAVE_UGC_HUMAN_REALISM_BLOCK, prompts["collector-admire"])
        self.assertIn(SPORTS_CAVE_UGC_VIDEO_REALISM_BLOCK, prompts["collector-admire"])
        self.assertIn(SPORTS_CAVE_PRODUCT_AND_ROOM_LOCK_BLOCK, prompts["collector-admire"])
        self.assertNotIn(SPORTS_CAVE_UGC_HUMAN_REALISM_BLOCK, prompts["wall-only"])
        self.assertNotIn(SPORTS_CAVE_UGC_VIDEO_REALISM_BLOCK, prompts["wall-only"])
        self.assertIn(SPORTS_CAVE_PRODUCT_AND_ROOM_LOCK_BLOCK, prompts["wall-only"])

    def test_product_lock_block_is_in_all_reels_studio_mockup_and_video_prompts(self):
        image_prompts = reels.build_image_prompts("roger-federer", "Roger Federer", "Tennis", "")
        video_prompts = reels.build_video_prompts("roger-federer", "Roger Federer", "Tennis")

        for prompt in list(image_prompts.values()) + list(video_prompts.values()):
            self.assertIn(SPORTS_CAVE_PRODUCT_AND_ROOM_LOCK_BLOCK, prompt)

    def test_zip_export_creates_required_folder_structure_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            product = run_dir / "source" / "product-mockup-original.png"
            background = run_dir / "source" / "selected-background-original.jpg"
            mockup = run_dir / "social-media-mockups" / reels.image_mockup_filename("roger-federer", "collector-admire")
            video = run_dir / "social-media-reels" / reels.video_filename("roger-federer", "collector-admire")
            for path, payload in (
                (product, b"product"),
                (background, b"background"),
                (mockup, b"mockup"),
                (video, b"video"),
            ):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)

            state = {
                "files": {
                    "product_mockup": {"path": str(product), "filename": product.name},
                    "selected_background": {"path": str(background), "filename": background.name},
                    "image_mockups": {
                        "collector-admire": {
                            "path": str(mockup),
                            "filename": mockup.name,
                            "original_name": "mockup.png",
                        }
                    },
                    "videos": {
                        "collector-admire": {
                            "path": str(video),
                            "filename": video.name,
                            "original_name": "video.mp4",
                            "version": "v01",
                            "status": "final",
                        }
                    },
                }
            }

            background_prompt = reels.build_background_finder_prompt(
                "roger-federer",
                "Roger Federer Wall Art",
                "Tennis",
                "Luxury collector room",
            )
            image_prompts = reels.build_image_prompts("roger-federer", "Roger Federer Wall Art", "Tennis", "")
            video_prompts = reels.build_video_prompts("roger-federer", "Roger Federer Wall Art", "Tennis")

            zip_path = reels.build_social_media_reels_zip(
                run_dir,
                "roger-federer",
                "Roger Federer Wall Art",
                "Tennis",
                state,
                background_prompt,
                image_prompts,
                video_prompts,
            )

            with zipfile.ZipFile(zip_path) as archive:
                names = set(archive.namelist())
                manifest = archive.read("manifest.json").decode("utf-8")

            self.assertIn("mockup-backgrounds/", names)
            self.assertIn("social-media-mockups/", names)
            self.assertIn("social-media-reels/", names)
            self.assertIn("social-media-video-content/", names)
            self.assertIn("sport-videos/", names)
            self.assertIn("mockup-backgrounds/roger-federer/product-mockup-original.png", names)
            self.assertIn("mockup-backgrounds/roger-federer/selected-background-original.jpg", names)
            self.assertIn("mockup-backgrounds/roger-federer/background-finder-prompt.txt", names)
            self.assertIn(f"social-media-mockups/roger-federer/{mockup.name}", names)
            self.assertIn("social-media-mockups/roger-federer/image-prompts.txt", names)
            self.assertIn(f"social-media-reels/roger-federer/{video.name}", names)
            self.assertIn(f"social-media-video-content/roger-federer/final/{video.name}", names)
            self.assertIn(f"sport-videos/tennis/roger-federer/{video.name}", names)
            self.assertIn("README-INSTRUCTIONS.txt", names)
            self.assertIn('"product_handle": "roger-federer"', manifest)

    def test_zip_uses_cleaned_detected_handle_not_uuid_filename(self):
        details = reels.derive_product_details_from_filename(
            "cristiano-ronaldo-soccer-art-e157b372-b7b0-4fa7-a667-b6aaca3ed2a5.jpeg"
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            product = run_dir / "source" / "product-mockup-original.jpeg"
            product.parent.mkdir(parents=True, exist_ok=True)
            product.write_bytes(b"product")
            state = {
                "files": {
                    "product_mockup": {"path": str(product), "filename": product.name},
                    "selected_background": None,
                    "image_mockups": {},
                    "videos": {},
                }
            }
            background_prompt = reels.build_background_finder_prompt(
                details["product_handle"],
                details["product_title"],
                details["sport_category"],
                "",
            )
            image_prompts = reels.build_image_prompts(
                details["product_handle"],
                details["product_title"],
                details["sport_category"],
                "",
            )
            video_prompts = reels.build_video_prompts(
                details["product_handle"],
                details["product_title"],
                details["sport_category"],
            )

            zip_path = reels.build_social_media_reels_zip(
                run_dir,
                details["product_handle"],
                details["product_title"],
                details["sport_category"],
                state,
                background_prompt,
                image_prompts,
                video_prompts,
            )

            self.assertEqual(zip_path.name, "cristiano-ronaldo-soccer-art__social-media-reels-pack__v01.zip")

    def test_zip_export_uses_original_asset_bytes(self):
        original = self._png_bytes(size=(6, 6), color=(11, 11, 13))
        product_asset = reels.image_asset_from_bytes(original, "full-res-product.png", "image/png", source="paste")
        state = {
            "files": {
                "product_mockup": {
                    **product_asset,
                    "path": "",
                    "filename": "product-mockup-original.png",
                    "original_name": "full-res-product.png",
                },
                "selected_background": None,
                "image_mockups": {},
                "videos": {},
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            zip_path = reels.build_social_media_reels_zip(
                run_dir,
                "roger-federer",
                "Roger Federer",
                "Tennis",
                state,
                reels.build_background_finder_prompt("roger-federer", "Roger Federer", "Tennis", ""),
                reels.build_image_prompts("roger-federer", "Roger Federer", "Tennis", ""),
                reels.build_video_prompts("roger-federer", "Roger Federer", "Tennis"),
            )

            with zipfile.ZipFile(zip_path) as archive:
                zipped = archive.read("mockup-backgrounds/roger-federer/product-mockup-original.png")
                manifest = archive.read("manifest.json").decode("utf-8")

        self.assertEqual(zipped, original)
        self.assertIn('"product_mockup_source": "paste"', manifest)


if __name__ == "__main__":
    unittest.main()
