from pathlib import Path
import hashlib
import json
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


def write_asset_files(root, stem, content):
    webp_path = Path(root) / "webp" / f"{stem}.webp"
    jpg_path = Path(root) / "jpg" / f"{stem}.jpg"
    webp_path.parent.mkdir(parents=True, exist_ok=True)
    jpg_path.parent.mkdir(parents=True, exist_ok=True)
    webp_path.write_bytes(f"{content}-webp".encode("utf-8"))
    jpg_path.write_bytes(f"{content}-jpg".encode("utf-8"))
    return webp_path, jpg_path


def asset_record(key, label, category, webp_path, jpg_path=None):
    return {
        "key": key,
        "label": label,
        "include_in_zip": True,
        "zip_group": category,
        "webp_path": str(webp_path),
        "jpg_path": str(jpg_path) if jpg_path else None,
    }


def manifest_hash(manifest):
    payload = json.dumps(
        [
            {
                "archive_name": entry["archive_name"],
                "byte_length": entry["byte_length"],
                "content_sha1": entry["content_sha1"],
            }
            for entry in manifest
        ],
        sort_keys=True,
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


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

        self.assertEqual(len(image_factory.LIFESTYLE_PROMPT_SPECS), 17)
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
            self.assertEqual(len(prompt_paths), 17)
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

    def test_one_prompt_card_social_upload_is_included_with_core_assets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_dir = Path(tmpdir) / "zip"
            zip_dir.mkdir()
            core_webp, core_jpg = write_asset_files(tmpdir, "core-black-framed", "core")
            social_webp, social_jpg = write_asset_files(
                tmpdir,
                "test-product-black-framed-afl-man-cave-lifestyle",
                "card-01",
            )
            assets = [
                asset_record(
                    "black",
                    "Black Framed",
                    image_factory.ASSET_CATEGORY_CORE,
                    core_webp,
                    core_jpg,
                ),
                asset_record(
                    "lifestyle::01-man-cave-prompt.txt",
                    "01 - Man Cave (Product Page)",
                    image_factory.ASSET_CATEGORY_SOCIAL,
                    social_webp,
                    social_jpg,
                ),
            ]
            selected_groups = {
                image_factory.ASSET_CATEGORY_CORE,
                image_factory.ASSET_CATEGORY_SOCIAL,
                image_factory.ASSET_CATEGORY_PRODUCT,
            }
            manifest = image_factory.build_asset_zip_manifest(assets, selected_groups)
            zip_path = image_factory.create_complete_pack_zip(
                zip_dir,
                "test-product",
                assets=assets,
                zip_groups=selected_groups,
            )

            with zipfile.ZipFile(zip_path) as archive:
                names = set(archive.namelist())

            self.assertEqual(names, {entry["archive_name"] for entry in manifest})
            self.assertEqual(len(names), len(manifest))
            self.assertIn("WEBP/core-black-framed.webp", names)
            self.assertIn("jpg/core-black-framed.jpg", names)
            self.assertIn("WEBP/test-product-black-framed-afl-man-cave-lifestyle.webp", names)
            self.assertIn("jpg/test-product-black-framed-afl-man-cave-lifestyle.jpg", names)
            self.assertEqual(len(names), 4)

    def test_multiple_prompt_card_social_uploads_are_all_included(self):
        prompt_stems = {
            "01": "test-product-black-framed-afl-man-cave-lifestyle",
            "02": "test-product-black-framed-afl-office-lifestyle",
            "07": "test-product-black-framed-afl-home-sports-bar",
            "14": "test-product-black-framed-afl-man-cave-pool-table",
            "15": "test-product-black-framed-afl-premium-tool-shed-workshop",
            "16": "test-product-black-framed-afl-man-cave-with-pool-table",
            "17": "test-product-black-framed-afl-architectural-loft",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_dir = Path(tmpdir) / "zip"
            zip_dir.mkdir()
            assets = []
            for prompt_number, stem in prompt_stems.items():
                webp_path, jpg_path = write_asset_files(tmpdir, stem, f"card-{prompt_number}")
                assets.append(
                    asset_record(
                        f"lifestyle::{prompt_number}",
                        f"{prompt_number} uploaded mockup",
                        image_factory.ASSET_CATEGORY_SOCIAL,
                        webp_path,
                        jpg_path,
                    )
                )

            manifest = image_factory.build_asset_zip_manifest(
                assets,
                {image_factory.ASSET_CATEGORY_SOCIAL},
            )
            zip_path = image_factory.create_complete_pack_zip(
                zip_dir,
                "test-product",
                assets=assets,
                zip_groups={image_factory.ASSET_CATEGORY_SOCIAL},
            )

            with zipfile.ZipFile(zip_path) as archive:
                names = set(archive.namelist())

            self.assertEqual(names, {entry["archive_name"] for entry in manifest})
            self.assertEqual(len(names), 14)
            for stem in prompt_stems.values():
                self.assertIn(f"WEBP/{stem}.webp", names)
                self.assertIn(f"jpg/{stem}.jpg", names)

    def test_prompt_card_uploads_persist_when_later_cards_are_added(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_dir = Path(tmpdir) / "zip"
            zip_dir.mkdir()
            first_webp, first_jpg = write_asset_files(tmpdir, "card-01", "card-01")
            second_webp, second_jpg = write_asset_files(tmpdir, "card-02", "card-02")

            restored_assets = [
                asset_record(
                    "lifestyle::01-man-cave-prompt.txt",
                    "01 - Man Cave",
                    image_factory.ASSET_CATEGORY_SOCIAL,
                    first_webp,
                    first_jpg,
                )
            ]
            restored_assets.append(
                asset_record(
                    "lifestyle::02-office-prompt.txt",
                    "02 - Office",
                    image_factory.ASSET_CATEGORY_SOCIAL,
                    second_webp,
                    second_jpg,
                )
            )

            zip_path = image_factory.create_complete_pack_zip(
                zip_dir,
                "test-product",
                assets=restored_assets,
                zip_groups={image_factory.ASSET_CATEGORY_SOCIAL},
            )

            with zipfile.ZipFile(zip_path) as archive:
                names = set(archive.namelist())

            self.assertEqual(
                names,
                {
                    "WEBP/card-01.webp",
                    "jpg/card-01.jpg",
                    "WEBP/card-02.webp",
                    "jpg/card-02.jpg",
                },
            )

    def test_zip_checkbox_filtering_uses_final_manifest_categories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_dir = Path(tmpdir) / "zip"
            zip_dir.mkdir()
            core_webp, core_jpg = write_asset_files(tmpdir, "core", "core")
            social_webp, social_jpg = write_asset_files(tmpdir, "social", "social")
            product_webp, product_jpg = write_asset_files(tmpdir, "product", "product")
            assets = [
                asset_record("core", "Core", image_factory.ASSET_CATEGORY_CORE, core_webp, core_jpg),
                asset_record("social", "Social", image_factory.ASSET_CATEGORY_SOCIAL, social_webp, social_jpg),
                asset_record("product", "Product", image_factory.ASSET_CATEGORY_PRODUCT, product_webp, product_jpg),
            ]

            cases = [
                (
                    "all",
                    {
                        image_factory.ASSET_CATEGORY_CORE,
                        image_factory.ASSET_CATEGORY_SOCIAL,
                        image_factory.ASSET_CATEGORY_PRODUCT,
                    },
                    {"WEBP/core.webp", "jpg/core.jpg", "WEBP/social.webp", "jpg/social.jpg", "WEBP/product.webp", "jpg/product.jpg"},
                ),
                (
                    "no-social",
                    {image_factory.ASSET_CATEGORY_CORE, image_factory.ASSET_CATEGORY_PRODUCT},
                    {"WEBP/core.webp", "jpg/core.jpg", "WEBP/product.webp", "jpg/product.jpg"},
                ),
                (
                    "no-core",
                    {image_factory.ASSET_CATEGORY_SOCIAL, image_factory.ASSET_CATEGORY_PRODUCT},
                    {"WEBP/social.webp", "jpg/social.jpg", "WEBP/product.webp", "jpg/product.jpg"},
                ),
                (
                    "no-product",
                    {image_factory.ASSET_CATEGORY_CORE, image_factory.ASSET_CATEGORY_SOCIAL},
                    {"WEBP/core.webp", "jpg/core.jpg", "WEBP/social.webp", "jpg/social.jpg"},
                ),
                (
                    "only-social",
                    {image_factory.ASSET_CATEGORY_SOCIAL},
                    {"WEBP/social.webp", "jpg/social.jpg"},
                ),
            ]

            for name, selected_groups, expected_names in cases:
                with self.subTest(case=name):
                    zip_path = image_factory.create_complete_pack_zip(
                        zip_dir,
                        "test-product",
                        assets=assets,
                        zip_groups=selected_groups,
                        zip_filename=f"{name}.zip",
                    )
                    with zipfile.ZipFile(zip_path) as archive:
                        self.assertEqual(set(archive.namelist()), expected_names)

    def test_zip_manifest_invalidates_when_social_upload_is_added(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            first_webp, first_jpg = write_asset_files(tmpdir, "card-01", "card-01")
            second_webp, second_jpg = write_asset_files(tmpdir, "card-02", "card-02")
            first_assets = [
                asset_record(
                    "lifestyle::01",
                    "01",
                    image_factory.ASSET_CATEGORY_SOCIAL,
                    first_webp,
                    first_jpg,
                )
            ]
            second_assets = first_assets + [
                asset_record(
                    "lifestyle::02",
                    "02",
                    image_factory.ASSET_CATEGORY_SOCIAL,
                    second_webp,
                    second_jpg,
                )
            ]

            first_manifest = image_factory.build_asset_zip_manifest(
                first_assets,
                {image_factory.ASSET_CATEGORY_SOCIAL},
            )
            second_manifest = image_factory.build_asset_zip_manifest(
                second_assets,
                {image_factory.ASSET_CATEGORY_SOCIAL},
            )

            self.assertNotEqual(manifest_hash(first_manifest), manifest_hash(second_manifest))
            self.assertEqual(len(first_manifest), 2)
            self.assertEqual(len(second_manifest), 4)

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

            manifest = image_factory.build_asset_zip_manifest(
                [
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
                {image_factory.ASSET_CATEGORY_SOCIAL},
            )
            self.assertEqual(len(names), 2)
            self.assertEqual(len(set(names)), 2)
            self.assertEqual(set(names), {entry["archive_name"] for entry in manifest})
            self.assertTrue(all(name.startswith("WEBP/") for name in names))

    def test_prompt_card_uploads_are_classed_as_social_mockups(self):
        self.assertEqual(
            image_factory.get_prompt_group("01-man-cave-prompt.txt"),
            image_factory.ASSET_CATEGORY_SOCIAL,
        )
        self.assertEqual(
            image_factory.get_prompt_group("17-architectural-loft-prompt.txt"),
            image_factory.ASSET_CATEGORY_SOCIAL,
        )
        self.assertEqual(
            image_factory.get_prompt_group("14-man-cave-pool-table-prompt.txt"),
            image_factory.ASSET_CATEGORY_SOCIAL,
        )
        self.assertEqual(
            image_factory.get_prompt_group("15-premium-tool-shed-workshop-prompt.txt"),
            image_factory.ASSET_CATEGORY_SOCIAL,
        )
        self.assertEqual(
            image_factory.get_prompt_group("16-man-cave-with-pool-table-prompt.txt"),
            image_factory.ASSET_CATEGORY_SOCIAL,
        )
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("def ensure_lifestyle_assets_registered", source)
        self.assertIn("zip_group=ASSET_CATEGORY_SOCIAL", source)

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
        self.assertIn("selected_assets = get_selected_zip_assets(result, selected_groups)", final_zip)
        self.assertIn("assets=selected_assets", source)


if __name__ == "__main__":
    unittest.main()
