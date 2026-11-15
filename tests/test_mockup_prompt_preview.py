import ast
import io
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from PIL import Image
from streamlit.testing.v1 import AppTest

import image_factory
import prompt_store
from sports_cave_prompt_blocks import (
    SPORTS_CAVE_PRODUCT_AND_ROOM_LOCK_BLOCK,
    SPORTS_CAVE_UGC_HUMAN_REALISM_BLOCK,
    SPORTS_CAVE_VIDEO_ARTWORK_FREEZE_LOCK,
)


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_MOCKUP_PROMPT_FILENAMES = [
    "01-man-cave-prompt.txt",
    "02-office-prompt.txt",
    "03-living-room-prompt.txt",

]


def load_app_prompt_labels():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "PROMPT_LABELS":
                    return ast.literal_eval(node.value)
    raise AssertionError("PROMPT_LABELS not found in app.py")


def tiny_png_bytes(color=(212, 165, 76)):
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), color).save(buffer, format="PNG")
    return buffer.getvalue()


def build_restored_generation_result(run_dir):
    run_dir = Path(run_dir)
    prompt_dir = run_dir / image_factory.PROMPTS_FOLDER_NAME
    zip_dir = run_dir / "zip"
    webp_dir = run_dir / image_factory.WEBP_CACHE_FOLDER_NAME
    jpg_dir = run_dir / image_factory.JPG_CACHE_FOLDER_NAME
    prompt_dir.mkdir(parents=True, exist_ok=True)
    zip_dir.mkdir(parents=True, exist_ok=True)
    webp_dir.mkdir(parents=True, exist_ok=True)
    jpg_dir.mkdir(parents=True, exist_ok=True)

    reference_path = run_dir / "reference.webp"
    reference_path.write_bytes(b"reference")
    _, _, prompt_paths, _ = image_factory.generate_lifestyle_prompt_pack(
        "AppTest Product",
        "AFL",
        "apptest-product",
        run_dir,
        reference_path,
    )

    core_webp_path = webp_dir / "apptest-product-black-framed-afl-wall-art.webp"
    core_jpg_path = jpg_dir / "apptest-product-black-framed-afl-wall-art.jpg"
    core_webp_path.write_bytes(b"core-webp")
    core_jpg_path.write_bytes(b"core-jpg")
    existing_zip_path = zip_dir / "existing.zip"
    existing_zip_path.write_bytes(b"existing")

    return {
        "product_name": "AppTest Product",
        "sport_category": "AFL",
        "created_at": "2026-07-19T00:00:00",
        "product_slug": "apptest-product",
        "sport_slug": "afl",
        "run_dir": str(run_dir),
        "zip_dir": str(zip_dir),
        "webp_dir": str(webp_dir),
        "jpg_dir": str(jpg_dir),
        "zip_path": str(existing_zip_path),
        "black_framed_webp_path": str(core_webp_path),
        "black_framed_jpg_path": str(core_jpg_path),
        "prompt_dir": str(prompt_dir),
        "prompt_paths": [str(path) for path in prompt_paths],
        "lifestyle_mockup_paths": {},
        "assets": [
            image_factory.build_asset_record(
                key="black",
                label="Black Framed",
                webp_path=str(core_webp_path),
                jpg_path=str(core_jpg_path),
                asset_group="generated",
                zip_group=image_factory.ASSET_CATEGORY_CORE,
            )
        ],
        "status_text": "Core Sports Cave product images are ready.",
    }


def build_stale_legacy_prompt_generation_result(run_dir):
    result = build_restored_generation_result(run_dir)
    prompt_dir = Path(result["prompt_dir"])
    stale_prompt_names = EXPECTED_MOCKUP_PROMPT_FILENAMES[:13] + [
        "14-retired-social-prompt.txt",
        "15-architectural-loft-prompt.txt",
    ]
    stale_prompt_paths = []
    for prompt_name in stale_prompt_names:
        prompt_path = prompt_dir / prompt_name
        prompt_path.write_text(f"Stale prompt: {prompt_name}\n", encoding="utf-8")
        stale_prompt_paths.append(str(prompt_path))

    result["prompt_paths"] = stale_prompt_paths
    result["final_prompt_items"] = [
        {
            "key": "14-retired-social",
            "filename": "14-retired-social-prompt.txt",
            "label": "Retired Social Prompt",
            "prompt": "Stale retired prompt",
        }
    ]
    return result


class MockupPromptPreviewTests(unittest.TestCase):
    def tearDown(self):
        prompt_store.clear_prompt_cache()

    def test_final_prompt_items_exist_in_generation_order_with_stable_keys(self):
        prompt_items = image_factory.build_lifestyle_prompt_items(
            "Roger Federer Legacy",
            "Tennis",
            local_only=True,
        )

        expected_filenames = [
            filename for filename, _, _ in image_factory.LIFESTYLE_PROMPT_SPECS
        ]
        self.assertEqual(expected_filenames, EXPECTED_MOCKUP_PROMPT_FILENAMES)
        self.assertEqual(
            [item["filename"] for item in prompt_items],
            expected_filenames,
        )
        self.assertEqual(len(prompt_items), 3)
        self.assertTrue(all(item["key"] and item["label"] and item["prompt"] for item in prompt_items))
        self.assertEqual(
            [item["key"] for item in prompt_items],
            [
                image_factory.prompt_key_from_prompt_filename(filename)
                for filename in expected_filenames
            ],
        )

    def test_prompt_items_exist_without_product_name_or_artwork(self):
        prompt_items = image_factory.build_lifestyle_prompt_items(
            "",
            "AFL",
            local_only=True,
            artwork_reference_available=False,
        )

        self.assertEqual(len(prompt_items), 3)
        first_prompt = prompt_items[0]["prompt"]
        self.assertIn("Product name: [PRODUCT TITLE]", first_prompt)
        self.assertIn("Sport category: AFL", first_prompt)
        self.assertIn("Reference image: [ARTWORK REFERENCE]", first_prompt)
        self.assertIn(image_factory.ROOM_STYLE_GUIDANCE_MARKER, first_prompt)
        self.assertIn("[PRODUCT TITLE]", first_prompt)

    def test_missing_custom_sport_uses_clear_placeholder(self):
        prompt_items = image_factory.build_lifestyle_prompt_items(
            "",
            "",
            local_only=True,
            artwork_reference_available=False,
        )

        first_prompt = prompt_items[0]["prompt"]
        self.assertIn("Product name: [PRODUCT TITLE]", first_prompt)
        self.assertIn("Sport category: [SPORT]", first_prompt)
        self.assertIn("Reference image: [ARTWORK REFERENCE]", first_prompt)

    def test_final_prompt_items_contain_existing_substitutions(self):
        prompt_items = image_factory.build_lifestyle_prompt_items(
            "Roger Federer Legacy",
            "Tennis",
            local_only=True,
        )

        first_prompt = prompt_items[0]["prompt"]
        self.assertIn("Product name: Roger Federer Legacy", first_prompt)
        self.assertIn("Sport category: Tennis", first_prompt)
        self.assertIn(
            f"Reference image: {image_factory.LIFESTYLE_REFERENCE_PROMPT_TEXT}",
            first_prompt,
        )

    def test_repeated_composition_is_idempotent_and_does_not_duplicate_blocks(self):
        first_items = image_factory.build_lifestyle_prompt_items(
            "Roger Federer Legacy",
            "Tennis",
            local_only=True,
        )
        second_items = image_factory.build_lifestyle_prompt_items(
            "Roger Federer Legacy",
            "Tennis",
            local_only=True,
        )

        from mockup_product_prompts import SCENE
        self.assertEqual([SCENE.sub("", i["prompt"]) for i in first_items], [SCENE.sub("", i["prompt"]) for i in second_items])
        for prompt_item in second_items:
            prompt_text = prompt_item["prompt"]
            self.assertEqual(prompt_text.count(SPORTS_CAVE_PRODUCT_AND_ROOM_LOCK_BLOCK), 1)
            self.assertLessEqual(prompt_text.count(SPORTS_CAVE_UGC_HUMAN_REALISM_BLOCK), 1)
            self.assertLessEqual(prompt_text.count(SPORTS_CAVE_VIDEO_ARTWORK_FREEZE_LOCK), 1)
            self.assertLessEqual(prompt_text.count(image_factory.ROOM_STYLE_GUIDANCE_MARKER), 1)

    def test_mockups_collection_replaces_gift_prompts_and_removes_reels(self):
        prompt_items = image_factory.build_lifestyle_prompt_items(
            "Senna Monaco Legacy",
            "Motorsport",
            local_only=True,
        )
        labels = [item["label"] for item in prompt_items]
        filenames = [item["filename"] for item in prompt_items]

        self.assertEqual(len(prompt_items), 3)
        self.assertEqual(filenames, EXPECTED_MOCKUP_PROMPT_FILENAMES)
        self.assertEqual(labels, ["Man Cave", "Office", "Living Room"])
        self.assertFalse(any("Reel" in label for label in labels))
        self.assertNotIn("10-premium-unboxing-prompt.txt", filenames)
        self.assertNotIn("15-premium-gift-reveal-prompt.txt", filenames)
        self.assertNotIn("14-retired-social-prompt.txt", filenames)
        self.assertNotIn("Premium Garage / Collector Space", "\n".join(labels))
        self.assertFalse(any(filename.endswith("-reel-prompt.txt") for filename in filenames))

        joined_labels = "\n".join(labels)
        self.assertNotIn("Premium Unboxing / Collector Arrival", joined_labels)
        self.assertNotIn("Premium Gift Reveal Scene", joined_labels)
        self.assertNotIn("Retired Social Prompt", joined_labels)

    def test_product_prompts_include_selected_scene_and_shared_locks(self):
        from mockup_product_prompts import ROOMS, ANGLES, MARKER
        items=image_factory.build_lifestyle_prompt_items("Bathurst Pride", "Motorsport", local_only=True)
        for item in items:
            text=item["prompt"]
            self.assertEqual(text.count(MARKER),1)
            self.assertTrue(any("Selected room: "+room in text for room in ROOMS[item["filename"]]))
            self.assertTrue(any("Selected camera angle: "+angle in text for angle in ANGLES))
            self.assertEqual(text.count(SPORTS_CAVE_PRODUCT_AND_ROOM_LOCK_BLOCK),1)
            self.assertIn("Do not redesign the artwork",text)
            self.assertIn("1024 x 1024",text)

    def test_room_guidance_changes_with_sport_and_product_title(self):
        motorsport_prompt = image_factory.build_lifestyle_prompt_items(
            "Senna Monaco Legacy",
            "Motorsport",
            local_only=True,
        )[0]["prompt"]
        tennis_prompt = image_factory.build_lifestyle_prompt_items(
            "Federer Modern Statement",
            "Tennis",
            local_only=True,
        )[0]["prompt"]

        self.assertIn("graphite, charcoal, black metal", motorsport_prompt)
        self.assertIn("legendary or classic", motorsport_prompt)
        self.assertIn("lighter refined neutrals", tennis_prompt)
        self.assertIn("bold or modern", tennis_prompt)
        self.assertNotEqual(motorsport_prompt, tennis_prompt)

    def test_non_room_prompts_are_not_given_room_guidance(self):
        prompt_items = {
            item["filename"]: item["prompt"]
            for item in image_factory.build_lifestyle_prompt_items(
                "Roger Federer Legacy",
                "Tennis",
                local_only=True,
            )
        }

        self.assertNotIn("04-close-up-wall-prompt.txt", prompt_items)
        self.assertNotIn("05-limited-edition-detail-prompt.txt", prompt_items)
        self.assertIn(image_factory.ROOM_STYLE_GUIDANCE_MARKER, prompt_items["03-living-room-prompt.txt"])

    def test_prompt_pack_writes_the_exact_supplied_prompt_collection(self):
        prompt_items = image_factory.build_lifestyle_prompt_items(
            "Roger Federer Legacy",
            "Tennis",
            local_only=True,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            reference_path = run_dir / "reference.webp"
            reference_path.write_bytes(b"reference")

            with patch.object(
                image_factory,
                "build_lifestyle_prompt_items",
                side_effect=AssertionError("supplied prompts must not be rebuilt"),
            ):
                _, _, prompt_paths, _ = image_factory.generate_lifestyle_prompt_pack(
                    "Different Product",
                    "Different Sport",
                    "roger-federer-legacy",
                    run_dir,
                    reference_path,
                    prompt_items=prompt_items,
                )

            self.assertEqual(
                [path.name for path in prompt_paths],
                EXPECTED_MOCKUP_PROMPT_FILENAMES,
            )
            for prompt_item, prompt_path in zip(prompt_items, prompt_paths):
                self.assertEqual(
                    prompt_path.read_text(encoding="utf-8"),
                    prompt_item["prompt"] + "\n",
                )

    def test_core_generation_keeps_output_names_and_carries_previewed_prompts(self):
        prompt_items = image_factory.build_lifestyle_prompt_items(
            "Preview Test Product",
            "Tennis",
            local_only=True,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            shutil.copytree(ROOT / "templates", base_dir / "templates")
            artwork_path = base_dir / "artwork.png"
            Image.new("RGB", (1800, 1200), "#385477").save(artwork_path)
            result = image_factory.generate_product_images(
                "Preview Test Product",
                "Tennis",
                artwork_path,
                base_dir=base_dir,
                final_prompt_items=prompt_items,
            )

        self.assertEqual(result["final_prompt_items"], prompt_items)
        self.assertEqual(
            [Path(asset["webp_path"]).name for asset in result["assets"]],
            [
                "preview-test-product-black-framed-tennis-wall-art.webp",
                "preview-test-product-oak-framed-tennis-wall-art.webp",
                "preview-test-product-white-framed-tennis-wall-art.webp",
                "preview-test-product-unframed-tennis-wall-art.webp",
                "preview-test-product-framed-tennis-wall-art-sizing-guide.webp",
            ],
        )

    def test_preview_prompt_composition_never_reads_supabase(self):
        with patch.dict(
            os.environ,
            {prompt_store.ENABLE_LIFESTYLE_SUPABASE_READS_ENV: "true"},
        ), patch.object(
            prompt_store,
            "_load_prompt_from_supabase",
            side_effect=AssertionError("preview must remain local"),
        ):
            prompt_items = image_factory.build_lifestyle_prompt_items(
                "Roger Federer Legacy",
                "Tennis",
                local_only=True,
            )

        self.assertEqual(len(prompt_items), len(image_factory.LIFESTYLE_PROMPT_SPECS))


    def test_image_factory_import_is_reloaded_when_prompt_specs_change(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        get_image_factory_source = source[source.index("def get_image_factory") : source.index("\n\ndef get_os_pages")]
        import_branch_source = get_image_factory_source[
            get_image_factory_source.index("if image_factory is None:") : get_image_factory_source.index("return image_factory")
        ]
        reload_branch_source = get_image_factory_source[
            get_image_factory_source.index('if getattr(image_factory, "__sports_cave_loaded_mtime__", None)')
            : get_image_factory_source.index("return image_factory")
        ]

        self.assertIn("__sports_cave_loaded_mtime__", get_image_factory_source)
        self.assertIn("image_factory.py", get_image_factory_source)
        self.assertIn("importlib.reload(image_factory)", get_image_factory_source)
        self.assertIn("importlib.import_module", import_branch_source)
        self.assertIn("importlib.reload(image_factory)", reload_branch_source)


    def test_prompt_card_uploads_do_not_force_full_page_reruns(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        upload_handler = source[
            source.index("def auto_register_lifestyle_upload")
            : source.index("\n\ndef render_asset_selection_controls")
        ]
        prompt_cards = source[
            source.index("def _render_prompt_card_group")
            : source.index("\n\ndef render_optional_package_controls")
        ]

        self.assertNotIn("st.rerun", upload_handler)
        self.assertIn("return updated_result", upload_handler)
        self.assertIn("@st.fragment\ndef render_prompt_cards", prompt_cards)
        self.assertLess(
            prompt_cards.index("uploaded_lifestyle_image = st.file_uploader"),
            prompt_cards.index('if saved_lifestyle_paths:'),
        )


    def test_post_generation_prompt_cards_render_copy_prompt_upload_and_zip_controls(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        prompt_cards = source[
            source.index("def _render_prompt_card_group") : source.index("\n\ndef render_optional_package_controls")
        ]
        mockup_actions = source[
            source.index("def render_mockup_prompt_action_row") : source.index("\n\ndef prime_asset_selection_state")
        ]

        self.assertIn("render_mockup_prompt_action_row", prompt_cards)
        self.assertIn("Upload image from ChatGPT", prompt_cards)
        self.assertNotIn("Add To ZIP", prompt_cards)
        self.assertIn("auto_register_lifestyle_upload", prompt_cards)
        self.assertIn("Saved - included when {group_label} is selected.", prompt_cards)
        self.assertIn('st.markdown(f"**{prompt_title}**")', prompt_cards)
        self.assertIn("current_lifestyle_prompt_text", prompt_cards)
        self.assertIn("render_mockup_prompt_bar", mockup_actions)
        self.assertIn("mockup-copy::{key}", mockup_actions)
        self.assertNotIn("show_copy=False", prompt_cards)
        self.assertNotIn("if show_copy:", mockup_actions)


if __name__ == "__main__":
    unittest.main()

# Shared coverage formerly reached through the retired standalone page.
# Exercise the preserved services directly with a Product Uploads result binding.
class SharedMockupRegressionTests(unittest.TestCase):
    def test_stale_prompt_paths_are_refreshed_to_current_prompt_collection(self):
        import app
        with tempfile.TemporaryDirectory() as folder, patch.object(app, 'image_factory', image_factory):
            result = build_stale_legacy_prompt_generation_result(folder)
            result = app.ensure_lifestyle_prompts(result)
            self.assertEqual([Path(p).name for p in result['prompt_paths']], EXPECTED_MOCKUP_PROMPT_FILENAMES)
            self.assertEqual([p['filename'] for p in result['final_prompt_items']], EXPECTED_MOCKUP_PROMPT_FILENAMES)
            self.assertNotIn('Retired Social Prompt', str(result['final_prompt_items']))

    def test_prompt_upload_registers_real_assets_and_retains_other_slots(self):
        import app
        from tests.test_mockup_second_image_upload import FakeSessionState, CountingUpload
        with tempfile.TemporaryDirectory() as folder:
            result = build_restored_generation_result(folder)
            result['_product_upload_intake'] = 'isolated-intake'
            for key in ('black_framed_webp_path', 'black_framed_jpg_path'):
                Image.new('RGB', (40, 30), 'navy').save(result[key])
            state = FakeSessionState(current_page='Product Uploads', _product_upload_active='isolated-intake',
                                     _product_upload_mockups_result=result)
            with patch.object(app, 'image_factory', image_factory), patch.object(app.st, 'session_state', state), patch.object(app, 'record_activity_log'):
                for i, prompt in enumerate(result['prompt_paths']):
                    upload = CountingUpload(tiny_png_bytes((20+i, 40, 80)), file_id='upload-'+str(i))
                    result = app.auto_register_lifestyle_upload(result, Path(prompt), upload)
                    self.assertEqual(len(result['lifestyle_mockup_paths']), i+1)
                    self.assertEqual(len(result['prompt_paths']), 3)
                    paths = result['lifestyle_mockup_paths'][Path(prompt).name]
                    self.assertTrue(Path(paths['webp_path']).is_file())
                    self.assertFalse(paths.get('jpg_path'))
                    again = app.auto_register_lifestyle_upload(result, Path(prompt), upload)
                    self.assertEqual(again['lifestyle_mockup_paths'], result['lifestyle_mockup_paths'])
                assets = [a for a in result['assets'] if a.get('prompt_filename') in EXPECTED_MOCKUP_PROMPT_FILENAMES]
                self.assertEqual(len(assets), 3)
                manifest = app._mockup_dropbox_manifest(result, [image_factory.ASSET_CATEGORY_PRODUCT])
                self.assertEqual(len(manifest), 3)
                self.assertTrue(all(x['archive_name'].lower().endswith('.webp') for x in manifest))

    def test_shared_previews_still_precede_prompt_and_download_controls(self):
        source = (ROOT / 'app.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'render_generation_result')
        body = ast.get_source_segment(source, node)
        self.assertLess(body.index('render_generated_previews(result)'), body.index('render_prompt_cards('))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'render_prompt_cards')
        self.assertIn('render_final_zip_download(result)', ast.get_source_segment(source, node))

    def test_mockup_callbacks_do_not_contain_home_navigation(self):
        source = (ROOT / 'app.py').read_text(encoding='utf-8')
        names = {'save_uploaded_lifestyle_result', 'auto_register_lifestyle_upload',
                 '_consume_mockup_prompt_edit_request', 'remove_uploaded_lifestyle_result'}
        bodies = [ast.get_source_segment(source, n) for n in ast.parse(source).body
                  if isinstance(n, ast.FunctionDef) and n.name in names]
        self.assertEqual(len(bodies), len(names))
        for body in bodies:
            self.assertNotIn('set_current_page("Dashboard"', body)
            self.assertNotIn('session_state["current_page"] = "Dashboard"', body)
            self.assertNotIn('session_state.selected_page = "Dashboard"', body)
