import ast
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import image_factory
import prompt_store
from sports_cave_prompt_blocks import (
    SPORTS_CAVE_PRODUCT_AND_ROOM_LOCK_BLOCK,
    SPORTS_CAVE_UGC_HUMAN_REALISM_BLOCK,
    SPORTS_CAVE_VIDEO_ARTWORK_FREEZE_LOCK,
)


ROOT = Path(__file__).resolve().parents[1]


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
        self.assertEqual(
            [item["filename"] for item in prompt_items],
            expected_filenames,
        )
        self.assertEqual(len(prompt_items), len(image_factory.LIFESTYLE_PROMPT_SPECS))
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

        self.assertEqual(len(prompt_items), 20)
        first_prompt = prompt_items[0]["prompt"]
        self.assertIn("Product name: [PRODUCT TITLE]", first_prompt)
        self.assertIn("Sport category: AFL", first_prompt)
        self.assertIn("Reference image: [ARTWORK REFERENCE]", first_prompt)

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
                [item["filename"] for item in prompt_items],
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

    def test_mockups_page_renders_all_prompts_without_upload_or_product(self):
        prompt_labels = load_app_prompt_labels()
        app_test = run_mockups_page()

        self.assertEqual(len(app_test.exception), 0)
        self.assertEqual(len(app_test.expander), 0)
        self.assertEqual(len(app_test.text_area), 20)
        self.assertTrue(
            any(markdown.value == "### Image Generation Prompts" for markdown in app_test.markdown)
        )
        self.assertTrue(
            any(
                "Review the prompts used for the lifestyle and reel image pack."
                in caption.value
                for caption in app_test.caption
            )
        )
        self.assertEqual(
            [text_area.label for text_area in app_test.text_area],
            [
                f"{prompt_labels[filename]} prompt"
                for filename, _, _ in image_factory.LIFESTYLE_PROMPT_SPECS
            ],
        )
        self.assertTrue(all(text_area.disabled for text_area in app_test.text_area))
        self.assertIn("Product name: [PRODUCT TITLE]", app_test.text_area[0].value)
        self.assertIn("Sport category: AFL", app_test.text_area[0].value)
        self.assertIn("Reference image: [ARTWORK REFERENCE]", app_test.text_area[0].value)

    def test_mockups_page_does_not_render_old_expander_or_empty_state(self):
        app_test = run_mockups_page()
        rendered_text = "\n".join(
            [markdown.value for markdown in app_test.markdown]
            + [caption.value for caption in app_test.caption]
            + [text_area.label for text_area in app_test.text_area]
        )

        self.assertNotIn("Preview All Image Prompts", rendered_text)
        self.assertNotIn(
            "Upload artwork and complete the product name and sport category to preview all prompts.",
            rendered_text,
        )

    def test_mockups_prompt_preview_render_performs_no_generation_or_external_prompt_reads(self):
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
        self.assertEqual(len(app_test.text_area), 20)

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

    def test_mockups_page_previews_and_passes_the_same_collection_before_generation(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        preview_helper = source[
            source.index("def render_mockup_prompt_preview") : source.index("\n\ndef render_mockups_page")
        ]
        mockups_page = source[
            source.index("def render_mockups_page") : source.index("\n\ndef render_product_uploads_page")
        ]

        self.assertNotIn("st.expander", preview_helper)
        self.assertIn('st.markdown("### Image Generation Prompts")', preview_helper)
        self.assertIn("st.text_area", preview_helper)
        self.assertIn("disabled=True", preview_helper)
        self.assertNotIn("generate_product_images", preview_helper)
        self.assertLess(
            mockups_page.index("render_mockup_prompt_preview(final_prompt_items)"),
            mockups_page.index('st.button("Generate Core Shopify Images"'),
        )
        self.assertLess(
            mockups_page.index("final_prompt_items = build_mockup_final_prompt_items("),
            mockups_page.index('st.subheader("2. Generate Core Shopify Images")'),
        )
        self.assertIn("final_prompt_items=final_prompt_items", mockups_page)


if __name__ == "__main__":
    unittest.main()
