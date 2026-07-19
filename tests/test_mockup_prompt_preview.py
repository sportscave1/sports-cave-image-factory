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
    "04-close-up-wall-prompt.txt",
    "05-limited-edition-detail-prompt.txt",
    "06-instant-experience-cover-prompt.txt",
    "07-home-sports-bar-prompt.txt",
    "08-collector-display-room-prompt.txt",
    "09-luxury-entry-wall-prompt.txt",
    "10-private-club-lounge-prompt.txt",
    "11-wall-upgrade-moment-prompt.txt",
    "12-fireplace-feature-wall-prompt.txt",
    "13-premium-bedroom-prompt.txt",
    "14-premium-garage-prompt.txt",
    "15-premium-tool-shed-workshop-prompt.txt",
    "16-man-cave-with-pool-table-prompt.txt",
    "17-architectural-loft-prompt.txt",
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


def run_mockups_page():
    app_test = AppTest.from_file(str(ROOT / "app.py"))
    app_test.session_state["selected_page"] = "Mockups"
    app_test.session_state["startup_shell_loaded"] = True
    return app_test.run(timeout=20)


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


def build_stale_home_gym_generation_result(run_dir):
    result = build_restored_generation_result(run_dir)
    prompt_dir = Path(result["prompt_dir"])
    stale_prompt_names = EXPECTED_MOCKUP_PROMPT_FILENAMES[:13] + [
        "14-home-gym-prompt.txt",
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
            "key": "14-home-gym",
            "filename": "14-home-gym-prompt.txt",
            "label": "Home Gym / Motivation Wall",
            "prompt": "Stale Home Gym prompt",
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
        self.assertEqual(len(prompt_items), 17)
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

        self.assertEqual(len(prompt_items), 17)
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

        self.assertEqual(first_items, second_items)
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

        self.assertEqual(len(prompt_items), 17)
        self.assertEqual(filenames, EXPECTED_MOCKUP_PROMPT_FILENAMES)
        self.assertIn("Private Club Lounge / Collector Retreat", labels[9])
        self.assertEqual(labels[13], "Premium Garage")
        self.assertEqual(labels[14], "Premium Tool Shed / Workshop")
        self.assertEqual(labels[15], "Man Cave With Pool Table")
        self.assertEqual(labels[16], "Architectural Loft / Statement Wall")
        self.assertFalse(any("Reel" in label for label in labels))
        self.assertNotIn("10-premium-unboxing-prompt.txt", filenames)
        self.assertNotIn("15-premium-gift-reveal-prompt.txt", filenames)
        self.assertNotIn("14-home-gym-prompt.txt", filenames)
        self.assertNotIn("Premium Garage / Collector Space", "\n".join(labels))
        self.assertFalse(any(filename.endswith("-reel-prompt.txt") for filename in filenames))

        joined_labels = "\n".join(labels)
        self.assertNotIn("Premium Unboxing / Collector Arrival", joined_labels)
        self.assertNotIn("Premium Gift Reveal Scene", joined_labels)
        self.assertNotIn("Home Gym / Motivation Wall", joined_labels)

    def test_replacement_prompts_include_real_room_sport_and_product_guidance(self):
        prompt_items = {
            item["filename"]: item["prompt"]
            for item in image_factory.build_lifestyle_prompt_items(
                "Senna Monaco Legacy",
                "Motorsport",
                local_only=True,
            )
        }

        prompt_10 = prompt_items["10-private-club-lounge-prompt.txt"]
        prompt_15 = prompt_items["17-architectural-loft-prompt.txt"]
        for prompt_text in (prompt_10, prompt_15):
            self.assertIn("30-50-year-old male sports", prompt_text)
            self.assertIn("selected sport category and product title", prompt_text)
            self.assertIn(image_factory.ROOM_STYLE_GUIDANCE_MARKER, prompt_text)
            self.assertIn("real premium lived-in interior", prompt_text)
            self.assertIn("colour, materiality, mood", prompt_text)
            self.assertIn("Do not add sports balls", prompt_text)
            self.assertIn("Do not add jerseys", prompt_text)
            self.assertNotIn("premium ribbon", prompt_text)
            self.assertNotIn("shipping box", prompt_text)
            self.assertNotIn("gift box", prompt_text)

    def test_new_garage_workshop_and_pool_table_prompts_have_required_style_and_shared_locks(self):
        prompt_items = {
            item["filename"]: item["prompt"]
            for item in image_factory.build_lifestyle_prompt_items(
                "Bathurst Pride",
                "Motorsport",
                local_only=True,
            )
        }
        new_prompt_names = [
            "14-premium-garage-prompt.txt",
            "15-premium-tool-shed-workshop-prompt.txt",
            "16-man-cave-with-pool-table-prompt.txt",
        ]

        for filename in new_prompt_names:
            with self.subTest(filename=filename):
                prompt_text = prompt_items[filename]
                self.assertIn("Create a 1024 x 1024 ultra-realistic Meta ad carousel mockup", prompt_text)
                self.assertIn("This image is for a paid Meta ad carousel", prompt_text)
                self.assertIn("The artwork and frame must remain exactly the same", prompt_text)
                self.assertIn("Do not redesign the artwork", prompt_text)
                self.assertIn("The framed artwork must be the hero of the image.", prompt_text)
                self.assertIn("Lighting:", prompt_text)
                self.assertIn("Composition:", prompt_text)
                self.assertIn("Final result:", prompt_text)
                self.assertEqual(prompt_text.count(image_factory.ROOM_STYLE_GUIDANCE_MARKER), 1)
                self.assertEqual(prompt_text.count(SPORTS_CAVE_PRODUCT_AND_ROOM_LOCK_BLOCK), 1)
                self.assertEqual(prompt_text.count("FRAME REALISM:"), 1)
                self.assertEqual(prompt_text.count("ROOM REALISM:"), 1)

        garage_prompt = prompt_items["14-premium-garage-prompt.txt"]
        workshop_prompt = prompt_items["15-premium-tool-shed-workshop-prompt.txt"]
        pool_table_prompt = prompt_items["16-man-cave-with-pool-table-prompt.txt"]

        self.assertIn("For non-Motorsport products, do not force a vehicle into the scene.", garage_prompt)
        self.assertNotIn("Collector Space", garage_prompt)
        self.assertIn("not dirty, cluttered, unsafe, cheap, or gimmicky", workshop_prompt)
        self.assertIn("Do not add dirty floors.", workshop_prompt)
        self.assertIn("physically believable proportions", pool_table_prompt)
        self.assertIn("Keep the pool table physically accurate", pool_table_prompt)

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

        self.assertNotIn(image_factory.ROOM_STYLE_GUIDANCE_MARKER, prompt_items["04-close-up-wall-prompt.txt"])
        self.assertNotIn(image_factory.ROOM_STYLE_GUIDANCE_MARKER, prompt_items["05-limited-edition-detail-prompt.txt"])
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
            result = image_factory.generate_product_images(
                "Preview Test Product",
                "Tennis",
                ROOT / "input" / "artwork.jpg",
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

    def test_mockups_page_does_not_render_prompt_ui_before_generation(self):
        prompt_labels = load_app_prompt_labels()
        app_test = run_mockups_page()
        expected_labels = [
            prompt_labels[filename]
            for filename, _, _ in image_factory.LIFESTYLE_PROMPT_SPECS
        ]
        rendered_markdown = [markdown.value for markdown in app_test.markdown]
        rendered_text = "\n".join(
            rendered_markdown
            + [caption.value for caption in app_test.caption]
            + [button.label for button in app_test.button]
        )

        self.assertEqual(len(app_test.exception), 0)
        self.assertEqual(len(app_test.expander), 0)
        self.assertEqual(len(app_test.text_area), 0)
        self.assertIn("Generate Core Shopify Images", [button.label for button in app_test.button])
        self.assertNotIn("Image Generation Prompts", rendered_text)
        self.assertNotIn("Copy Prompt", rendered_text)
        for label in expected_labels:
            self.assertNotIn(f"**{label}**", rendered_markdown)

    def test_first_artwork_upload_preserves_mockups_route_and_uses_stable_widget_key(self):
        app_test = run_mockups_page()

        self.assertEqual(app_test.session_state["selected_page"], "Mockups")
        app_test.file_uploader[0].set_value(
            [("first-upload.png", tiny_png_bytes(), "image/png")]
        )
        app_test.run(timeout=20)

        self.assertEqual(app_test.session_state["selected_page"], "Mockups")
        self.assertEqual(len(app_test.exception), 0)
        self.assertIn("Uploaded Artwork", [subheader.value for subheader in app_test.subheader])
        self.assertIn("mockups_upload_processing_cache", app_test.session_state)

    def test_upload_validation_error_stays_on_mockups_page(self):
        app_test = run_mockups_page()

        app_test.file_uploader[0].set_value(
            [("bad-upload.png", b"not an image", "image/png")]
        )
        app_test.run(timeout=20)

        self.assertEqual(app_test.session_state["selected_page"], "Mockups")
        self.assertTrue(
            any("not a valid image" in error.value for error in app_test.error)
        )

    def test_mockups_upload_reruns_do_not_reset_selected_page_to_dashboard(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        init_source = source[source.index("def init_session_state") : source.index("\n\ndef log_app_memory")]
        mockups_page = source[
            source.index("def render_mockups_page") : source.index("\n\ndef render_product_uploads_page")
        ]

        self.assertNotIn('st.session_state.selected_page = "Dashboard"\n        st.session_state.startup_shell_loaded = True', init_source)
        self.assertIn('key="mockups_artwork_upload"', mockups_page)
        self.assertIn("process_uploaded_artwork_once(uploaded_file)", mockups_page)
        self.assertNotIn("on_change", mockups_page)

    def test_same_upload_is_processed_once_across_product_and_sport_reruns(self):
        app_test = run_mockups_page()
        upload_bytes = tiny_png_bytes()

        app_test.file_uploader[0].set_value(
            [("cached-upload.png", upload_bytes, "image/png")]
        )
        app_test.run(timeout=20)
        first_cache = dict(app_test.session_state["mockups_upload_processing_cache"])

        app_test.text_input[0].set_value("Cached Product Name")
        app_test.run(timeout=20)
        second_cache = dict(app_test.session_state["mockups_upload_processing_cache"])

        app_test.selectbox[0].select("Motorsport")
        app_test.run(timeout=20)
        third_cache = dict(app_test.session_state["mockups_upload_processing_cache"])

        self.assertEqual(first_cache, second_cache)
        self.assertEqual(second_cache, third_cache)
        self.assertEqual(app_test.session_state["selected_page"], "Mockups")

    def test_mockups_page_does_not_render_old_expander_or_empty_state(self):
        app_test = run_mockups_page()
        rendered_text = "\n".join(
            [markdown.value for markdown in app_test.markdown]
            + [caption.value for caption in app_test.caption]
        )

        self.assertNotIn("Preview All Image Prompts", rendered_text)
        self.assertNotIn(
            "Upload artwork and complete the product name and sport category to preview all prompts.",
            rendered_text,
        )

    def test_mockups_initial_render_performs_no_generation_or_external_prompt_reads(self):
        with patch.dict(
            os.environ,
            {prompt_store.ENABLE_LIFESTYLE_SUPABASE_READS_ENV: "true"},
        ), patch.object(
            prompt_store,
            "_load_prompt_from_supabase",
            side_effect=AssertionError("prompt preview must not read Supabase"),
        ), patch.object(
            image_factory,
            "generate_product_images",
            side_effect=AssertionError("prompt preview must not generate images"),
        ):
            app_test = run_mockups_page()

        self.assertEqual(len(app_test.exception), 0)
        self.assertEqual(len(app_test.text_area), 0)

    def test_generation_still_requires_valid_artwork_before_generator_runs(self):
        app_test = run_mockups_page()
        generate_button_index = [
            index
            for index, button in enumerate(app_test.button)
            if button.label == "Generate Core Shopify Images"
        ][0]

        with patch.object(
            image_factory,
            "generate_product_images",
            side_effect=AssertionError("generator must not run without artwork"),
        ):
            app_test.button[generate_button_index].click().run(timeout=20)

        self.assertTrue(
            any(exception.value == "Please upload an artwork image first." for exception in app_test.exception)
        )
        self.assertFalse(
            any("generator must not run without artwork" in str(exception.value) for exception in app_test.exception)
        )

    def test_mockups_page_has_no_pre_generation_prompt_preview_path(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        mockups_page = source[
            source.index("def render_mockups_page") : source.index("\n\ndef render_product_uploads_page")
        ]

        self.assertNotIn("def render_mockup_prompt_preview", source)
        self.assertNotIn("render_mockup_prompt_preview", source)
        self.assertNotIn("Image Generation Prompts", mockups_page)
        self.assertNotIn("prompt_preview_rendered", mockups_page)
        self.assertLess(
            mockups_page.index("final_prompt_items = build_mockup_final_prompt_items("),
            mockups_page.index('st.subheader("2. Generate Core Shopify Images")'),
        )
        self.assertIn("final_prompt_items=final_prompt_items", mockups_page)
        self.assertIn("render_generation_result(st.session_state.last_generation_result)", mockups_page)

    def test_generated_previews_render_above_post_generation_prompt_cards(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        generation_result = source[
            source.index("def render_generation_result") : source.index("\n\ndef render_recent_runs_sidebar")
        ]
        mockups_page = source[
            source.index("def render_mockups_page") : source.index("\n\ndef render_product_uploads_page")
        ]

        self.assertIn("render_generated_previews(result)", generation_result)
        self.assertLess(
            generation_result.index("render_generated_previews(result)"),
            generation_result.index("render_prompt_cards("),
        )
        self.assertLess(
            generation_result.index("render_prompt_cards("),
            generation_result.index("render_final_zip_download(result)"),
        )
        self.assertIn("render_generation_result(st.session_state.last_generation_result)", mockups_page)
        self.assertNotIn("render_lifestyle_cards=False", mockups_page)
        self.assertNotIn("render_zip=False", mockups_page)

    def test_stale_home_gym_prompt_paths_are_refreshed_to_current_prompt_collection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            app_test = AppTest.from_file(str(ROOT / "app.py"))
            app_test.session_state["selected_page"] = "Mockups"
            app_test.session_state["startup_shell_loaded"] = True
            app_test.session_state["last_generation_result"] = build_stale_home_gym_generation_result(run_dir)
            app_test.run(timeout=30)

            self.assertEqual(len(app_test.exception), 0)
            result = app_test.session_state["last_generation_result"]
            prompt_names = [Path(prompt_path).name for prompt_path in result["prompt_paths"]]
            rendered_text = "\n".join(
                [markdown.value for markdown in app_test.markdown]
                + [caption.value for caption in app_test.caption]
            )

            self.assertEqual(prompt_names, EXPECTED_MOCKUP_PROMPT_FILENAMES)
            self.assertEqual(
                [item["filename"] for item in result["final_prompt_items"]],
                EXPECTED_MOCKUP_PROMPT_FILENAMES,
            )
            self.assertNotIn("14-home-gym-prompt.txt", prompt_names)
            self.assertNotIn("Home Gym / Motivation Wall", rendered_text)
            self.assertIn("14 - Premium Garage (Social)", rendered_text)
            self.assertIn("15 - Premium Tool Shed / Workshop (Social)", rendered_text)
            self.assertIn("16 - Man Cave With Pool Table (Social)", rendered_text)
            self.assertIn("17 - Architectural Loft / Statement Wall (Social)", rendered_text)

    def test_image_factory_import_is_reloaded_when_prompt_specs_change(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        get_image_factory_source = source[source.index("def get_image_factory") : source.index("\n\ndef get_os_pages")]

        self.assertIn("__sports_cave_loaded_mtime__", get_image_factory_source)
        self.assertIn("image_factory.py", get_image_factory_source)
        self.assertIn("importlib.reload(image_factory)", get_image_factory_source)

    def test_prompt_card_upload_auto_registers_for_zip_without_add_to_zip_click(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            app_test = AppTest.from_file(str(ROOT / "app.py"))
            app_test.session_state["selected_page"] = "Mockups"
            app_test.session_state["startup_shell_loaded"] = True
            app_test.session_state["last_generation_result"] = build_restored_generation_result(run_dir)
            app_test.run(timeout=20)

            self.assertEqual(len(app_test.exception), 0)
            self.assertEqual(len(app_test.file_uploader), 18)
            self.assertNotIn("Add To ZIP", [button.label for button in app_test.button])

            app_test.file_uploader[-1].set_value(
                [("architectural-loft.png", tiny_png_bytes((20, 40, 80)), "image/png")]
            )
            app_test.run(timeout=30)

            result = app_test.session_state["last_generation_result"]
            prompt_name = "15-premium-tool-shed-workshop-prompt.txt"
            self.assertIn(prompt_name, result["lifestyle_mockup_paths"])
            social_assets = [
                asset
                for asset in result["assets"]
                if asset.get("prompt_filename") == prompt_name
                and asset.get("zip_group") == image_factory.ASSET_CATEGORY_SOCIAL
            ]
            self.assertEqual(len(social_assets), 1)
            self.assertTrue(Path(social_assets[0]["webp_path"]).exists())
            self.assertTrue(Path(social_assets[0]["jpg_path"]).exists())

            core_checkbox = next(
                checkbox
                for checkbox in app_test.checkbox
                if checkbox.label == "Core Images"
            )
            core_checkbox.uncheck()
            app_test.run(timeout=30)

            captions = [caption.value for caption in app_test.caption]
            selected_count_captions = [
                caption
                for caption in captions
                if "files selected for ZIP" in caption
            ]
            self.assertIn("2 files selected for ZIP", selected_count_captions)

            zip_paths = sorted((run_dir / "zip").glob("apptest-product-selected-*.zip"), key=lambda path: path.stat().st_mtime)
            self.assertTrue(zip_paths)
            with zipfile.ZipFile(zip_paths[-1]) as archive:
                names = set(archive.namelist())

            self.assertEqual(
                names,
                {
                    "WEBP/apptest-product-black-framed-afl-premium-tool-shed-workshop-lifestyle.webp",
                    "jpg/apptest-product-black-framed-afl-premium-tool-shed-workshop-lifestyle.jpg",
                },
            )
            self.assertNotIn("WEBP/apptest-product-black-framed-afl-wall-art.webp", names)
            self.assertEqual(len(names), 2)

    def test_post_generation_prompt_cards_render_copy_prompt_upload_and_zip_controls(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        prompt_cards = source[
            source.index("def render_prompt_cards") : source.index("\n\ndef render_optional_package_controls")
        ]
        mockup_actions = source[
            source.index("def render_mockup_prompt_action_row") : source.index("\n\ndef prime_asset_selection_state")
        ]

        self.assertIn("render_mockup_prompt_action_row", prompt_cards)
        self.assertIn("Upload image from ChatGPT", prompt_cards)
        self.assertNotIn("Add To ZIP", prompt_cards)
        self.assertIn("auto_register_lifestyle_upload", prompt_cards)
        self.assertIn("Saved — included when Social Mockups is selected.", prompt_cards)
        self.assertIn('st.markdown(f"**{prompt_title}**")', prompt_cards)
        self.assertIn("current_lifestyle_prompt_text", prompt_cards)
        self.assertIn("render_mockup_prompt_bar", mockup_actions)
        self.assertIn("mockup-copy::{key}", mockup_actions)
        self.assertNotIn("show_copy=False", prompt_cards)
        self.assertNotIn("if show_copy:", mockup_actions)


if __name__ == "__main__":
    unittest.main()
