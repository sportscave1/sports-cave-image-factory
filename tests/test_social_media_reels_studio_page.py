from pathlib import Path
import base64
import io
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from PIL import Image

import prompt_store
import social_media_reels_studio_page as reels
ROOT = Path(__file__).resolve().parents[1]


class FakePromptBackend:
    class SupabaseNotConfigured(RuntimeError):
        pass

    def __init__(self, records=None, fail_writes=False):
        self.records = dict(records or {})
        self.fail_writes = fail_writes
        self.bulk_reads = 0
        self.writes = 0

    def is_configured(self):
        return True

    def ensure_prompt_template_schema(self):
        return None

    def get_prompt_template(self, prompt_key):
        return self.records.get(prompt_key)

    def get_prompt_templates(self, prompt_keys):
        self.bulk_reads += 1
        return [self.records[key] for key in prompt_keys if key in self.records]

    def upsert_prompt_template(self, prompt_key, **kwargs):
        self.writes += 1
        if self.fail_writes:
            raise RuntimeError("simulated database failure")
        record = {
            "prompt_key": prompt_key,
            "prompt_name": kwargs.get("prompt_name"),
            "module": kwargs.get("module"),
            "prompt_text": kwargs.get("prompt_text"),
        }
        self.records[prompt_key] = record
        return record


class SocialMediaReelsStudioPageTests(unittest.TestCase):
    def tearDown(self):
        prompt_store.clear_prompt_cache()

    def _png_bytes(self, size=(3, 2), color=(212, 165, 76)):
        buffer = io.BytesIO()
        Image.new("RGB", size, color).save(buffer, format="PNG")
        return buffer.getvalue()

    def test_app_sidebar_and_router_include_reels_studio_page(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")

        self.assertIn('"Social Media Reels Studio"', source)
        self.assertIn("get_social_media_reels_studio_page().render_page(", source)
        self.assertIn("developer_password=DEVELOPER_PAGE_PASSWORD", source)

    def test_marketing_factory_route_does_not_import_legacy_page_bundle(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        route_source = source[source.index("def render_selected_page") : source.index("def main")]

        self.assertIn('elif current_page == "Marketing Factory":', route_source)
        self.assertIn("get_marketing_factory_page().render_page()", route_source)
        self.assertNotIn("os_route_pages().render_marketing_factory_page()", route_source)

    def test_top_level_page_errors_keep_technical_details_developer_only(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        main_source = source[source.index("def main") :]

        self.assertIn("if _developer_unlocked():", main_source)
        self.assertIn("st.exception(error)", main_source)
        self.assertIn("Open Developer diagnostics for the technical exception details.", main_source)

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

    def test_reels_image_uploader_does_not_client_reject_image_extensions(self):
        source = (ROOT / "social_media_reels_studio_page.py").read_text(encoding="utf-8")
        helper_source = source[
            source.index("def reels_image_input") : source.index("def _prompt_preview_key")
        ]

        self.assertNotIn("type=list(accepted_types)", helper_source)
        self.assertIn("Supported image types", helper_source)
        self.assertIn("uploaded_asset = image_asset_from_uploaded_file", helper_source)
        self.assertIn("has_valid_image_asset(uploaded_asset)", helper_source)
        self.assertIn("could not be read as a valid image", helper_source)

    def test_reels_hub_prompts_are_available_without_uploads(self):
        payload = reels.build_reels_hub_payload("", "", "", "", "collector-admire")

        self.assertIn("Use the uploaded black framed Sports Cave product mockup", payload["background_prompt"])
        self.assertIn("Image A is the exact Sports Cave black framed product mockup.", payload["image_prompt"])
        self.assertIn("PRODUCT LOCK", payload["image_prompt"])
        self.assertIn("Create an ultra-realistic 5 second cinematic lifestyle video", payload["video_prompt"])
        self.assertEqual(payload["product_handle"], "athlete-name-product-handle")
        self.assertEqual(payload["prompt_product_handle"], "[PRODUCT HANDLE]")
        self.assertIn("[SPORT]", payload["background_prompt"])
        self.assertIn("[PRODUCT TITLE]", payload["image_prompt"])
        self.assertIn("[PRODUCT ANGLE]", payload["image_prompt"])

    def test_every_social_reels_prompt_has_a_stable_unique_key(self):
        specs = reels.social_reels_prompt_specs()
        keys = [spec["prompt_key"] for spec in specs]

        self.assertEqual(len(specs), 9)
        self.assertEqual(len(keys), len(set(keys)))
        self.assertIn("social_reels.background_finder", keys)
        self.assertIn("social_reels.mockup_creation.wall_only", keys)
        self.assertIn("social_reels.image_to_video.collector_admire", keys)
        self.assertTrue(all(spec["default_text"].strip() for spec in specs))

    def test_saved_custom_prompt_loads_and_bulk_read_does_not_write(self):
        key = reels.IMAGE_PROMPT_KEYS["collector-admire"]
        custom = "Custom mockup for [PRODUCT TITLE] in [SPORT]. Direction: [PRODUCT ANGLE]"
        backend = FakePromptBackend({key: {"prompt_key": key, "prompt_text": custom}})
        with patch.object(prompt_store, "_supabase_backend", return_value=backend):
            prompt_store.clear_prompt_cache()
            records = reels.load_social_reels_prompt_records()
            prompt = reels.build_image_prompt(
                reels.get_scene_by_slug("collector-admire"),
                "roger-federer",
                "Roger Federer",
                "Tennis",
                "Warm room",
                records,
            )

        self.assertEqual(prompt, "Custom mockup for Roger Federer in Tennis. Direction: Warm room")
        self.assertEqual(backend.bulk_reads, 1)
        self.assertEqual(backend.writes, 0)

    def test_unsaved_edit_does_not_overwrite_saved_prompt(self):
        key = reels.BACKGROUND_FINDER_PROMPT_KEY
        backend = FakePromptBackend({key: {"prompt_key": key, "prompt_text": "Saved prompt"}})
        unsaved_editor_text = "Unsaved editor text"
        with patch.object(prompt_store, "_supabase_backend", return_value=backend):
            prompt_store.clear_prompt_cache()
            records = reels.load_social_reels_prompt_records()
            self.assertEqual(records[key]["text"], "Saved prompt")

        self.assertEqual(unsaved_editor_text, "Unsaved editor text")
        self.assertEqual(backend.records[key]["prompt_text"], "Saved prompt")
        self.assertEqual(backend.writes, 0)

    def test_save_persists_and_restore_returns_locked_default(self):
        key = reels.BACKGROUND_FINDER_PROMPT_KEY
        spec = next(item for item in reels.social_reels_prompt_specs() if item["prompt_key"] == key)
        backend = FakePromptBackend()
        with patch.object(prompt_store, "_supabase_backend", return_value=backend):
            prompt_store.clear_prompt_cache()
            prompt_store.save_prompt(key, spec["prompt_name"], "Edited prompt", module=reels.SOCIAL_REELS_MODULE)
            self.assertEqual(backend.records[key]["prompt_text"], "Edited prompt")
            prompt_store.reset_prompt_to_default(
                key,
                spec["prompt_name"],
                spec["default_text"],
                module=reels.SOCIAL_REELS_MODULE,
            )

        self.assertEqual(backend.records[key]["prompt_text"], spec["default_text"])
        self.assertEqual(backend.writes, 2)

    def test_one_social_reels_prompt_cannot_overwrite_another(self):
        first = reels.IMAGE_PROMPT_KEYS["collector-admire"]
        second = reels.IMAGE_PROMPT_KEYS["wall-only"]
        backend = FakePromptBackend(
            {
                first: {"prompt_key": first, "prompt_text": "First saved"},
                second: {"prompt_key": second, "prompt_text": "Second saved"},
            }
        )
        with patch.object(prompt_store, "_supabase_backend", return_value=backend):
            prompt_store.clear_prompt_cache()
            prompt_store.save_prompt(first, "First", "First edited", module=reels.SOCIAL_REELS_MODULE)

        self.assertEqual(backend.records[first]["prompt_text"], "First edited")
        self.assertEqual(backend.records[second]["prompt_text"], "Second saved")

    def test_save_failure_preserves_editor_text_and_saved_value(self):
        key = reels.VIDEO_PROMPT_KEYS["wall-only"]
        backend = FakePromptBackend(
            {key: {"prompt_key": key, "prompt_text": "Existing saved prompt"}},
            fail_writes=True,
        )
        editor_text = "Keep this unsaved edit visible"
        with patch.object(prompt_store, "_supabase_backend", return_value=backend):
            prompt_store.clear_prompt_cache()
            with self.assertRaises(RuntimeError):
                prompt_store.save_prompt(key, "Wall Only", editor_text, module=reels.SOCIAL_REELS_MODULE)

        self.assertEqual(editor_text, "Keep this unsaved edit visible")
        self.assertEqual(backend.records[key]["prompt_text"], "Existing saved prompt")

    def test_custom_prompt_dynamic_placeholders_still_render(self):
        key = reels.IMAGE_PROMPT_KEYS["wall-admire"]
        records = {
            key: {
                "prompt_key": key,
                "text": "Use [PRODUCT TITLE] for [SPORT]. Product [PRODUCT HANDLE]. Notes [PRODUCT ANGLE].",
            }
        }
        prompt = reels.build_image_prompt(
            reels.get_scene_by_slug("wall-admire"),
            "Roger Federer Wall Art",
            "Roger Federer",
            "Tennis",
            "Warm premium wall",
            records,
        )

        self.assertEqual(
            prompt,
            "Use Roger Federer for Tennis. Product roger-federer-wall-art. Notes Warm premium wall.",
        )
        generic = reels.build_reels_hub_payload(
            "",
            "",
            "",
            "",
            "wall-admire",
            prompt_records=records,
        )
        self.assertIn("Product [PRODUCT HANDLE]", generic["image_prompt"])

    def test_prompt_ui_is_editable_and_uses_explicit_save_restore_actions(self):
        source = (ROOT / "social_media_reels_studio_page.py").read_text(encoding="utf-8")
        helper = source[source.index("def _render_editable_prompt") : source.index("def render_page")]

        self.assertIn("st.text_area", helper)
        self.assertIn("disabled=not editing_enabled", helper)
        self.assertIn('"Save Prompt"', helper)
        self.assertIn('"Restore Default"', helper)
        self.assertIn('"No changes to save"', helper)
        self.assertIn('"Prompt saved"', helper)
        self.assertIn('"Prompt restored to default"', helper)
        self.assertIn('"Save failed — existing prompt remains unchanged"', helper)

    def test_reels_hub_scene_changes_image_and_video_prompts(self):
        holding = reels.build_reels_hub_payload("roger-federer", "Roger Federer", "Tennis", "", "collector-admire")
        wall_only = reels.build_reels_hub_payload("roger-federer", "Roger Federer", "Tennis", "", "wall-only")

        self.assertNotEqual(holding["image_prompt"], wall_only["image_prompt"])
        self.assertNotEqual(holding["video_prompt"], wall_only["video_prompt"])
        self.assertIn("HUMAN ANATOMY LOCK:", holding["image_prompt"])
        self.assertIn("NEGATIVE HUMAN ANATOMY:", holding["image_prompt"])
        self.assertIn("Reject and regenerate if any hand, wrist, forearm", holding["image_prompt"])
        self.assertNotIn("HUMAN ANATOMY LOCK:", wall_only["image_prompt"])
        self.assertNotIn("NEGATIVE HUMAN ANATOMY:", wall_only["image_prompt"])

    def test_reels_hub_wall_hanging_keeps_connected_arm_wording(self):
        payload = reels.build_reels_hub_payload("roger-federer", "Roger Federer", "Tennis", "", "wall-hanging-adjust")

        self.assertIn("A single customer stands centered in front of the frame", payload["image_prompt"])
        self.assertIn("Both arms are visible and naturally connected from shoulder to hand.", payload["image_prompt"])
        self.assertIn("The pose must be physically possible and natural.", payload["image_prompt"])

    def test_reels_hub_filename_and_save_instructions(self):
        payload = reels.build_reels_hub_payload(
            "roger-federer",
            "Roger Federer",
            "Tennis",
            "",
            "wall-admire",
            "v01",
            "final",
        )

        self.assertEqual(
            payload["video_filename"],
            "roger-federer__meta-reel__wall-admire__9x16__v01__final.mp4",
        )
        self.assertEqual(
            payload["mockup_filename"],
            "roger-federer__mockup__wall-admire__1x1__v01__final.png",
        )
        for folder in (
            "mockup-backgrounds",
            "social-media-mockups",
            "social-media-reels",
            "social-media-video-content",
        ):
            self.assertIn(folder, payload["save_instructions"])

    def test_render_page_is_non_gated_prompt_hub(self):
        source = (ROOT / "social_media_reels_studio_page.py").read_text(encoding="utf-8")
        render_source = source[source.index("def render_page") :]

        self.assertNotIn("Product setup", render_source)
        self.assertIn("1. Find the Best Background", render_source)
        self.assertIn("2. Create the Real-Life Mockup", render_source)
        self.assertIn("3. Create the Reel Video", render_source)
        self.assertIn("4. Upload Final Reel / File Naming", render_source)
        self.assertLess(render_source.index("1. Find the Best Background"), render_source.index("2. Create the Real-Life Mockup"))
        self.assertNotIn("Complete Step", render_source)
        self.assertNotIn("Upload Product Mockup", render_source)
        self.assertNotIn("roger-federer", render_source)
        self.assertNotIn("Roger Federer", render_source)
        self.assertEqual(render_source.count("st.file_uploader("), 1)

    def test_final_file_naming_card_contains_bottom_product_fields(self):
        source = (ROOT / "social_media_reels_studio_page.py").read_text(encoding="utf-8")
        render_source = source[source.index("def render_page") :]

        for text in (
            "Product handle",
            "Product title",
            "Athlete / product name",
            "Sport category",
            "Scene",
            "Version",
            "Status",
            "athlete-name-product-handle",
            "Athlete Name Wall Art",
            "Athlete name",
            "Choose or add sport category",
        ):
            with self.subTest(text=text):
                self.assertIn(text, render_source)

    def test_bottom_filename_generation_uses_version_status_and_scene(self):
        payload = reels.build_reels_hub_payload(
            "athlete-name-product-handle",
            "Athlete Name Wall Art",
            "Soccer",
            "Athlete name",
            "collector-admire",
            "v02",
            "ad-test",
        )

        self.assertEqual(
            payload["video_filename"],
            "athlete-name-product-handle__meta-reel__collector-admire__9x16__v02__ad-test.mp4",
        )
        self.assertEqual(
            payload["mockup_filename"],
            "athlete-name-product-handle__mockup__collector-admire__1x1__v02__ad-test.png",
        )

    def test_mockups_sport_dropdown_options_are_alphabetical_with_custom_last(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        options_source = source[source.index("SPORT_OPTIONS = [") : source.index("]\nPROMPT_LABELS")]
        options = [
            line.strip().strip('",')
            for line in options_source.splitlines()
            if line.strip().startswith('"')
        ]

        self.assertEqual(options[:-1], sorted(options[:-1]))
        self.assertEqual(options[-1], "Custom")

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

    def test_image_prompts_use_premium_still_mockup_structure(self):
        prompts = reels.build_image_prompts("roger-federer", "Roger Federer", "Tennis", "")
        required_text = (
            "Create a 1024 x 1024 ultra-realistic Sports Cave lifestyle mockup",
            "Image A is the exact Sports Cave black framed product mockup.",
            "Image B is the selected background/reference room.",
            "The uploaded product artwork is the hero. Preserve it exactly.",
            "PRODUCT LOCK",
            "FRAME REALISM",
            "GLASS REALISM",
            "ROOM REALISM",
            "LIGHTING",
            "COMPOSITION",
            "NEGATIVE RULES",
            "FINAL RESULT",
            "Do not redesign the artwork.",
            "Do not change the athlete, subject, team, colours, text, typography, badge, edition plate",
            "premium matte black timber frame",
            "realistic timber or frame depth",
            "sharp square mitred corners",
            "museum-quality glass",
            "no floating frame",
            "no pasted-on look",
            "Do not add text overlays.",
            "Do not add watermarks.",
        )

        for prompt in prompts.values():
            for text in required_text:
                with self.subTest(text=text):
                    self.assertIn(text, prompt)

    def test_person_image_prompts_include_person_and_hand_realism(self):
        prompts = reels.build_image_prompts("roger-federer", "Roger Federer", "Tennis", "")

        for slug in ("collector-admire", "wall-hanging-adjust", "wall-admire"):
            prompt = prompts[slug]
            self.assertIn("PERSON REALISM", prompt)
            self.assertIn("one realistic male customer only", prompt)
            self.assertIn("realistic hands", prompt)
            self.assertIn("Correct number of fingers", prompt)
            self.assertIn("No extra fingers", prompt)

        self.assertIn("No warped hands", prompts["collector-admire"])
        self.assertIn("No warped hands", prompts["wall-hanging-adjust"])
        self.assertIn("hands must only touch the outer frame edges", prompts["collector-admire"])
        self.assertIn("hands must only touch the outer frame edges", prompts["wall-hanging-adjust"])

    def test_person_image_prompts_include_human_anatomy_lock(self):
        prompts = reels.build_image_prompts("roger-federer", "Roger Federer", "Tennis", "")
        required_text = (
            "HUMAN ANATOMY LOCK:",
            "exactly one real everyday adult customer",
            "all visible body parts connected naturally",
            "Both shoulders, upper arms, elbows, forearms, wrists, hands, torso, hips, legs, and feet must align anatomically.",
            "No detached limbs.",
            "No floating hands.",
            "No hands appearing without visible wrists and arms.",
            "No arm emerging from behind the frame unless the full arm connection to the shoulder is clearly visible.",
            "No duplicated arms.",
            "No extra hands.",
            "No missing elbows.",
            "No twisted wrists.",
            "No broken fingers.",
            "No stretched arms.",
            "No rubbery limbs.",
            "No impossible reach across the frame.",
            "No cropped-off body parts that make limbs look disconnected.",
            "NEGATIVE HUMAN ANATOMY:",
            "Do not create detached arms, floating hands, disconnected wrists, duplicate limbs",
            "Reject and regenerate if any hand, wrist, forearm, elbow, upper arm, shoulder, leg, foot, head, or torso is detached",
        )

        for slug in ("collector-admire", "wall-hanging-adjust", "wall-admire"):
            prompt = prompts[slug]
            for text in required_text:
                with self.subTest(slug=slug, text=text):
                    self.assertIn(text, prompt)

    def test_wall_hanging_prompt_uses_safe_connected_body_pose(self):
        prompt = reels.build_image_prompts("roger-federer", "Roger Federer", "Tennis", "")["wall-hanging-adjust"]

        self.assertIn("A single customer stands centered in front of the frame", prompt)
        self.assertIn("full torso and both shoulders visible", prompt)
        self.assertIn("Both arms are visible and naturally connected from shoulder to hand.", prompt)
        self.assertIn("Elbows are slightly bent.", prompt)
        self.assertIn("Wrists and fingers are normal.", prompt)
        self.assertIn("The pose must be physically possible and natural.", prompt)

    def test_wall_only_image_prompt_has_no_people_and_no_person_realism_section(self):
        prompt = reels.build_image_prompts("roger-federer", "Roger Federer", "Tennis", "")["wall-only"]

        self.assertIn("No people.", prompt)
        self.assertNotIn("PERSON REALISM", prompt)
        self.assertNotIn("HUMAN ANATOMY LOCK:", prompt)
        self.assertNotIn("NEGATIVE HUMAN ANATOMY:", prompt)

    def test_video_prompts_use_premium_commercial_structure(self):
        prompts = reels.build_video_prompts("roger-federer", "Roger Federer", "Tennis")

        required_text = (
            "Create an ultra-realistic 5 second cinematic lifestyle video from this exact image.",
            "This is a premium Sports Cave advertisement.",
            "MUST remain EXACTLY the same",
            "NON-NEGOTIABLE:",
            "Do NOT regenerate the artwork.",
            "Do NOT alter the typography.",
            "Do NOT alter the badge.",
            "Do NOT alter the edition plate.",
            "The artwork must stay razor sharp throughout the entire video.",
            "SCENE",
            "CAMERA",
            "MOVEMENT",
            "FRAME REALISM",
            "GLASS",
            "LIGHTING",
            "BACKGROUND",
            "ENDING",
            "OUTPUT",
            "The existing room from the uploaded still image must remain the same.",
            "ARTWORK FREEZE LOCK",
            "Treat the artwork inside the frame as a flat, frozen, printed poster texture",
            "Do not zoom closer than the starting composition",
            "Keep the framed artwork fully visible",
            "Reject the video if the artwork text changes",
            "9:16 vertical.",
            "5 seconds.",
            "4K quality.",
            "Meta Ads ready.",
        )

        for prompt in prompts.values():
            for text in required_text:
                with self.subTest(text=text):
                    self.assertIn(text, prompt)

    def test_video_prompts_use_artwork_freeze_lock_and_safe_camera_defaults(self):
        prompts = reels.build_video_prompts("roger-federer", "Roger Federer", "Tennis")
        required_text = (
            "ARTWORK FREEZE LOCK",
            "Treat the artwork inside the frame as a flat, frozen, printed poster texture",
            "The artwork must remain perfectly stable frame-to-frame.",
            "No text changes.",
            "No plaque distortion.",
            "No badge distortion.",
            "No moving elements inside the printed artwork.",
            "Keep the full framed artwork visible and readable for the entire shot.",
            "SAFE VIDEO CAMERA DEFAULTS",
            "Do not zoom closer than the starting composition",
            "Keep the framed artwork fully visible",
            "Reject the video if the artwork text changes",
        )

        for slug, prompt in prompts.items():
            for text in required_text:
                with self.subTest(slug=slug, text=text):
                    self.assertIn(text, prompt)

    def test_video_prompts_do_not_include_risky_camera_phrases(self):
        prompts = reels.build_video_prompts("roger-federer", "Roger Federer", "Tennis")
        risky_phrases = (
            "dramatic push-in",
            "slow zoom into the artwork",
            "pan across the artwork",
            "orbit around the frame",
            "dynamic camera movement",
            "macro shot of the badge",
            "cinematic push-in",
        )

        for slug, prompt in prompts.items():
            prompt_lower = prompt.lower()
            for phrase in risky_phrases:
                with self.subTest(slug=slug, phrase=phrase):
                    self.assertNotIn(phrase, prompt_lower)

    def test_mockup_prompts_do_not_expose_internal_metadata_headers(self):
        image_prompts = reels.build_image_prompts(
            "roger-federer",
            "Roger Federer",
            "Tennis",
            "Warm collector room",
        )
        disallowed_headers = (
            "Product handle:",
            "Product title:",
            "Sport category:",
            "Creative notes:",
            "Scene slug:",
            "Video scene:",
            "Video scene slug:",
            "Version:",
            "Status:",
        )

        for prompt in image_prompts.values():
            for header in disallowed_headers:
                with self.subTest(header=header):
                    self.assertNotIn(header, prompt)

    def test_video_prompts_do_not_expose_internal_metadata_headers(self):
        video_prompts = reels.build_video_prompts(
            "roger-federer",
            "Roger Federer",
            "Tennis",
            {
                "collector-admire": {"version": "v03", "status": "winner"},
            },
        )
        disallowed_headers = (
            "Product handle:",
            "Product title:",
            "Sport category:",
            "Scene:",
            "Scene slug:",
            "Video scene:",
            "Video scene slug:",
            "Version:",
            "Status:",
        )

        for prompt in video_prompts.values():
            self.assertIn("Create an ultra-realistic 5 second cinematic lifestyle video from this exact image.", prompt)
            self.assertIn("Do NOT change the room from the uploaded still image.", prompt)
            for header in disallowed_headers:
                with self.subTest(header=header):
                    self.assertNotIn(header, prompt)

    def test_video_prompts_remove_old_six_to_eight_second_language(self):
        video_prompts = reels.build_video_prompts("roger-federer", "Roger Federer", "Tennis")

        for prompt in video_prompts.values():
            self.assertNotIn("6-8 second", prompt)
            self.assertNotIn("6–8 second", prompt)

    def test_video_prompts_include_scene_specific_premium_reel_details(self):
        prompts = reels.build_video_prompts("roger-federer", "Roger Federer", "Tennis")

        self.assertIn(
            "holding the framed artwork naturally with both hands at chest height",
            prompts["collector-admire"],
        )
        self.assertIn("His hands never cover important parts", prompts["collector-admire"])

        self.assertIn("final adjustment after hanging", prompts["wall-hanging-adjust"])
        self.assertIn("Hands only touch the outer frame edges.", prompts["wall-hanging-adjust"])
        self.assertIn("The frame is perfectly level.", prompts["wall-hanging-adjust"])

        self.assertIn("stands a few steps back", prompts["wall-admire"])
        self.assertIn("He is not touching the frame.", prompts["wall-admire"])

        self.assertIn("No people.", prompts["wall-only"])
        self.assertIn("No movement inside the artwork.", prompts["wall-only"])

    def test_background_finder_prompt_uses_uploaded_image_not_metadata_headers(self):
        prompt = reels.build_background_finder_prompt(
            "roger-federer",
            "Roger Federer",
            "Tennis",
            "Warm collector room",
        )

        self.assertIn("Use the uploaded black framed Sports Cave product mockup as the product reference.", prompt)
        self.assertIn("Analyse the uploaded product image directly instead of relying on product metadata.", prompt)
        self.assertIn("Use the supplied image, not a screenshot or compressed preview.", prompt)
        self.assertNotIn("Product handle:", prompt)
        self.assertNotIn("Product title:", prompt)
        self.assertNotIn("Sport category:", prompt)
        self.assertNotIn("Creative notes:", prompt)

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
