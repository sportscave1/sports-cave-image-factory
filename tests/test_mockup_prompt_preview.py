import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import image_factory
import prompt_store
from sports_cave_prompt_blocks import (
    SPORTS_CAVE_PRODUCT_AND_ROOM_LOCK_BLOCK,
    SPORTS_CAVE_UGC_HUMAN_REALISM_BLOCK,
    SPORTS_CAVE_VIDEO_ARTWORK_FREEZE_LOCK,
)


ROOT = Path(__file__).resolve().parents[1]


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
            "Reference image: Upload the black framed WebP from this run into ChatGPT before using this prompt.",
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

    def test_mockups_page_previews_and_passes_the_same_collection_before_generation(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        preview_helper = source[
            source.index("def render_mockup_prompt_preview") : source.index("\n\ndef render_mockups_page")
        ]
        mockups_page = source[
            source.index("def render_mockups_page") : source.index("\n\ndef render_product_uploads_page")
        ]

        self.assertIn('st.expander("Preview All Image Prompts", expanded=False)', preview_helper)
        self.assertIn('st.code(prompt_item["prompt"]', preview_helper)
        self.assertNotIn("generate_product_images", preview_helper)
        self.assertLess(
            mockups_page.index("render_mockup_prompt_preview(final_prompt_items)"),
            mockups_page.index('st.button("Generate Core Shopify Images"'),
        )
        self.assertIn("final_prompt_items=final_prompt_items", mockups_page)


if __name__ == "__main__":
    unittest.main()
