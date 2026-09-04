import inspect
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import app
import image_factory
import mockup_storage


EXPECTED_SLOTS = [
    "black-frame",
    "man-cave",
    "office",
    "living-room",
    "size-guide",
    "oak-frame",
    "white-frame",
    "unframed",
]
EXPECTED_LABELS = [
    "Black Framed",
    "Man Cave",
    "Office",
    "Living Room",
    "Size Guide",
    "Oak Framed",
    "White Framed",
    "Unframed",
]


class _Progress:
    def progress(self, *args, **kwargs):
        return self

    def empty(self):
        return None


class MockupEightImageManifestTests(unittest.TestCase):
    def make_assets(self, root, count=8, *, include_jpg=False):
        root = Path(root)
        assets = []
        for index, spec in enumerate(image_factory.PRODUCT_IMAGE_SLOT_SPECS[:count], start=1):
            webp_path = root / f"distinct-source-{index}.webp"
            webp_path.write_bytes(f"webp-{index}".encode("ascii"))
            jpg_path = None
            if include_jpg:
                jpg_path = root / f"distinct-source-{index}.jpg"
                jpg_path.write_bytes(f"jpg-{index}".encode("ascii"))
            assets.append(
                image_factory.build_asset_record(
                    key=spec["asset_key"],
                    label=spec["display_label"],
                    webp_path=webp_path,
                    jpg_path=jpg_path,
                    asset_group="lifestyle" if spec.get("prompt_filename") else "generated",
                    zip_group=spec["zip_group"],
                    prompt_filename=spec.get("prompt_filename"),
                    export_to_shopify=True,
                    export_to_socials=bool(jpg_path),
                )
            )
        return assets

    def make_result(self, root, count=8, *, include_jpg=False):
        root = Path(root)
        return app.normalize_generation_result(
            {
                "product_name": "Eight Image Test",
                "product_slug": "eight-image-test",
                "sport_category": "Cricket",
                "sport_slug": "cricket",
                "run_dir": root,
                "assets": self.make_assets(root, count, include_jpg=include_jpg),
                "lifestyle_mockup_paths": {},
            }
        )

    def test_all_upload_slots_remain_available(self):
        filenames = [row[0] for row in image_factory.LIFESTYLE_PROMPT_SPECS]
        self.assertEqual(17, len(filenames))
        self.assertEqual(17, len(set(filenames)))
        for filename in image_factory.PRODUCT_PAGE_PROMPT_FILENAMES:
            self.assertIn(filename, filenames)

    def test_eight_sequential_images_survive_normalized_fragment_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.make_result(temp_dir, 0)
            for asset in self.make_assets(temp_dir, 8):
                result["assets"].append(asset)
                result = app.normalize_generation_result(dict(result))
            self.assertEqual(EXPECTED_SLOTS, [row["slot_id"] for row in result["product_image_manifest"]])
            self.assertTrue(result["product_image_readiness"]["complete"])

    def test_each_lifestyle_room_survives_later_images(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.make_result(temp_dir)
            references = {
                row["slot_id"]: row["uploaded_image_reference"]
                for row in result["product_image_manifest"]
                if row["slot_id"] in {"man-cave", "office", "living-room"}
            }
            result = app.normalize_generation_result(dict(result))
            for slot_id, reference in references.items():
                entry = next(row for row in result["product_image_manifest"] if row["slot_id"] == slot_id)
                self.assertEqual(reference, entry["uploaded_image_reference"])
                self.assertTrue(entry["ready"])

    def test_readiness_reaches_eight_of_eight(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            readiness = self.make_result(temp_dir)["product_image_readiness"]
            self.assertEqual(8, readiness["ready_count"])
            self.assertEqual(8, readiness["required_count"])
            self.assertTrue(readiness["complete"])

    def test_zip_has_exactly_eight_unique_product_webp_entries_in_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.make_result(temp_dir)
            assets = image_factory.order_assets_by_product_manifest(
                result["assets"], result["product_image_manifest"]
            )
            zip_dir = Path(temp_dir) / "zip"
            zip_dir.mkdir()
            zip_path = image_factory.create_complete_pack_zip(
                zip_dir, "eight-image-test", assets=assets
            )
            with zipfile.ZipFile(zip_path) as archive:
                names = archive.namelist()
            self.assertEqual(8, len(names))
            self.assertEqual(8, len(set(names)))
            self.assertEqual(
                [f"WEBP/{row['output_filename']}" for row in result["product_image_manifest"]],
                names,
            )

    def test_output_folder_manifest_and_files_have_all_eight(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.make_result(temp_dir)
            unrelated = Path(temp_dir) / image_factory.SHOPIFY_UPLOADS_FOLDER_NAME / "keep-me.txt"
            unrelated.parent.mkdir(parents=True)
            unrelated.write_text("supporting", encoding="utf-8")
            rebuilt = image_factory.rebuild_export_folders(
                temp_dir,
                result["assets"],
                product_name=result["product_name"],
                sport_category=result["sport_category"],
                product_slug=result["product_slug"],
                sport_slug=result["sport_slug"],
                product_image_manifest=result["product_image_manifest"],
            )
            output_files = sorted(Path(rebuilt["shopify_uploads_dir"]).glob("*.webp"))
            self.assertEqual(8, len(output_files))
            self.assertTrue(unrelated.exists())
            persisted = json.loads(Path(rebuilt["product_image_manifest_path"]).read_text(encoding="utf-8"))
            self.assertEqual(EXPECTED_SLOTS, [row["slot_id"] for row in persisted["images"]])

    def test_dropbox_batch_receives_the_same_eight_slots(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.make_result(temp_dir)
            manifest = app._mockup_dropbox_manifest(
                result,
                [image_factory.ASSET_CATEGORY_CORE, image_factory.ASSET_CATEGORY_PRODUCT],
            )
            captured = {}

            def upload_batch(access_token, destination, items, **kwargs):
                captured["items"] = list(items)
                return {
                    "successes": [dict(item) for item in items],
                    "failures": [],
                }

            with (
                mock.patch.object(app.dropbox_integration, "get_metadata_if_exists", return_value=None),
                mock.patch.object(app.dropbox_integration, "ensure_folder_path"),
                mock.patch.object(app.dropbox_integration, "upload_batch", side_effect=upload_batch),
                mock.patch.object(app.st, "progress", return_value=_Progress()),
                mock.patch.object(app, "_files_save_upload_metadata"),
                mock.patch.object(app, "_files_clear_directory_cache"),
                mock.patch.object(app, "record_activity_log"),
            ):
                saved = app._save_mockups_to_dropbox(
                    "token", {"id": "test-user"}, result, manifest,
                    "/root", "/root/output", "eight-image-test", "merge_replace",
                )
            self.assertFalse(saved["failures"])
            self.assertEqual(8, len(captured["items"]))
            self.assertEqual(
                [f"WEBP/{row['output_filename']}" for row in result["product_image_manifest"]],
                [row["relative_path"] for row in captured["items"]],
            )

    def test_shopify_payload_contains_eight_in_gallery_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.make_result(temp_dir)
            payload = image_factory.build_shopify_draft_image_payload(result["product_image_manifest"])
            self.assertEqual(8, len(payload))
            self.assertEqual(EXPECTED_SLOTS, [row["slot_id"] for row in payload])
            self.assertEqual(list(range(1, 9)), [row["position"] for row in payload])

    def test_no_five_image_slice_can_remove_lifestyle_slots(self):
        source = inspect.getsource(image_factory.build_product_image_manifest)
        self.assertNotIn("[:5]", source)
        with tempfile.TemporaryDirectory() as temp_dir:
            slots = [row["slot_id"] for row in self.make_result(temp_dir)["product_image_manifest"]]
            self.assertEqual(["man-cave", "office", "living-room"], slots[1:4])

    def test_replacing_one_lifestyle_slot_keeps_order_and_other_references(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.make_result(temp_dir)
            before = {row["slot_id"]: row["uploaded_image_reference"] for row in result["product_image_manifest"]}
            replacement = Path(temp_dir) / "office-replacement.webp"
            replacement.write_bytes(b"replacement")
            office = next(asset for asset in result["assets"] if asset["key"] == "lifestyle::02-office-prompt.txt")
            office["webp_path"] = replacement
            result["lifestyle_mockup_paths"]["02-office-prompt.txt"]["webp_path"] = str(replacement)
            result = app.normalize_generation_result(result)
            after = {row["slot_id"]: row["uploaded_image_reference"] for row in result["product_image_manifest"]}
            self.assertEqual(str(replacement), after["office"])
            self.assertEqual(before["man-cave"], after["man-cave"])
            self.assertEqual(before["living-room"], after["living-room"])
            self.assertEqual(EXPECTED_SLOTS, [row["slot_id"] for row in result["product_image_manifest"]])

    def test_distinct_slots_with_same_source_filename_cannot_overwrite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            assets = self.make_assets(temp_dir)
            manifest = image_factory.build_product_image_manifest(
                assets, product_slug="same", sport_slug="cricket"
            )
            names = [row["output_filename"] for row in manifest]
            self.assertEqual(8, len(set(name.casefold() for name in names)))

    def test_retry_is_idempotent_for_output_and_shopify_payload(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.make_result(temp_dir)
            kwargs = {
                "product_name": result["product_name"],
                "sport_category": result["sport_category"],
                "product_slug": result["product_slug"],
                "sport_slug": result["sport_slug"],
                "product_image_manifest": result["product_image_manifest"],
            }
            first = image_factory.rebuild_export_folders(temp_dir, result["assets"], **kwargs)
            first_payload = image_factory.build_shopify_draft_image_payload(result["product_image_manifest"])
            second = image_factory.rebuild_export_folders(temp_dir, result["assets"], **kwargs)
            second_payload = image_factory.build_shopify_draft_image_payload(result["product_image_manifest"])
            self.assertEqual(first_payload, second_payload)
            self.assertEqual(8, len(list(Path(second["shopify_uploads_dir"]).glob("*.webp"))))
            self.assertEqual(first["product_image_manifest_path"], second["product_image_manifest_path"])

    def test_removing_one_room_removes_only_its_managed_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.make_result(temp_dir)
            kwargs = {
                "product_name": result["product_name"],
                "sport_category": result["sport_category"],
                "product_slug": result["product_slug"],
                "sport_slug": result["sport_slug"],
            }
            first = image_factory.rebuild_export_folders(
                temp_dir,
                result["assets"],
                product_image_manifest=result["product_image_manifest"],
                **kwargs,
            )
            output_dir = Path(first["shopify_uploads_dir"])
            unrelated = output_dir / "unrelated-support.webp"
            unrelated.write_bytes(b"keep")
            remaining_assets = [
                asset for asset in result["assets"]
                if asset["key"] != "lifestyle::02-office-prompt.txt"
            ]
            incomplete_manifest = image_factory.build_product_image_manifest(
                remaining_assets,
                product_slug=result["product_slug"],
                sport_slug=result["sport_slug"],
            )
            image_factory.rebuild_export_folders(
                temp_dir,
                remaining_assets,
                product_image_manifest=incomplete_manifest,
                **kwargs,
            )
            office_name = next(
                entry["output_filename"]
                for entry in result["product_image_manifest"]
                if entry["slot_id"] == "office"
            )
            self.assertFalse((output_dir / office_name).exists())
            self.assertTrue(unrelated.exists())
            for entry in incomplete_manifest:
                if entry["ready"]:
                    self.assertTrue((output_dir / entry["output_filename"]).exists())

    def test_five_image_state_is_incomplete_and_lists_rooms(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            # Build the historical five by selecting the non-room slot specs.
            assets = self.make_assets(temp_dir)
            assets = [
                asset for asset in assets
                if asset["key"] not in {
                    "lifestyle::01-man-cave-prompt.txt",
                    "lifestyle::02-office-prompt.txt",
                    "lifestyle::03-living-room-prompt.txt",
                }
            ]
            result = app.normalize_generation_result(
                {
                    "run_dir": temp_dir,
                    "product_slug": "five",
                    "sport_slug": "cricket",
                    "assets": assets,
                }
            )
            readiness = result["product_image_readiness"]
            self.assertEqual(5, readiness["ready_count"])
            self.assertEqual(["Man Cave", "Office", "Living Room"], readiness["missing_labels"])
            with self.assertRaises(image_factory.IncompleteProductImagePackageError):
                image_factory.build_shopify_draft_image_payload(result["product_image_manifest"])
            with self.assertRaises(image_factory.IncompleteProductImagePackageError):
                app.build_filtered_download_zip(
                    result,
                    [image_factory.ASSET_CATEGORY_CORE, image_factory.ASSET_CATEGORY_PRODUCT],
                )

    def test_legacy_saved_state_restores_three_room_slots(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            assets = self.make_assets(temp_dir)
            room_assets = {
                asset["key"]: asset
                for asset in assets
                if str(asset["key"]).startswith("lifestyle::")
            }
            core_assets = [asset for asset in assets if asset["key"] not in room_assets]
            result = app.normalize_generation_result(
                {
                    "run_dir": temp_dir,
                    "product_slug": "legacy",
                    "sport_slug": "cricket",
                    "assets": core_assets,
                    "uploaded_lifestyle_images": {
                        "man_cave_path": room_assets["lifestyle::01-man-cave-prompt.txt"]["webp_path"],
                        "office": {"path": room_assets["lifestyle::02-office-prompt.txt"]["webp_path"]},
                        "living-room": room_assets["lifestyle::03-living-room-prompt.txt"]["webp_path"],
                    },
                }
            )
            self.assertTrue(result["product_image_readiness"]["complete"])
            self.assertEqual(
                set(image_factory.PRODUCT_PAGE_PROMPT_FILENAMES),
                set(result["lifestyle_mockup_paths"]),
            )

    def test_upload_fragment_has_no_forced_full_page_rerun(self):
        source = "\n".join(
            [
                inspect.getsource(app.render_prompt_cards),
                inspect.getsource(app._render_prompt_card_group),
                inspect.getsource(app.auto_register_lifestyle_upload),
                inspect.getsource(app.save_uploaded_lifestyle_result),
            ]
        )
        self.assertIn("@st.fragment", inspect.getsource(app.render_prompt_cards))
        self.assertNotIn("st.rerun", source)
        self.assertIn("lifestyle-upload::{get_lifestyle_upload_slot_key(result, prompt_path)}", source)
        self.assertEqual(app.get_lifestyle_upload_slot_key({"run_dir": "existing-run"}, "01-man-cave-prompt.txt"),
                         "existing-run::01-man-cave-prompt.txt")

    def test_complete_zip_keeps_supporting_prompt_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.make_result(temp_dir)
            assets = image_factory.order_assets_by_product_manifest(
                result["assets"], result["product_image_manifest"]
            )
            prompt_dir = Path(temp_dir) / "prompts"
            prompt_dir.mkdir()
            support = prompt_dir / "instructions.txt"
            support.write_text("keep this", encoding="utf-8")
            zip_dir = Path(temp_dir) / "zip"
            zip_dir.mkdir()
            zip_path = image_factory.create_complete_pack_zip(
                zip_dir, "support", prompt_dir=prompt_dir, assets=assets
            )
            with zipfile.ZipFile(zip_path) as archive:
                self.assertEqual(
                    b"keep this",
                    archive.read(f"{image_factory.PROMPTS_FOLDER_NAME}/instructions.txt"),
                )

    def test_shopify_image_merge_preserves_every_non_image_field(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.make_result(temp_dir)
            original = {
                "title": "Untouched",
                "description": "Untouched body",
                "status": "DRAFT",
                "variants": [{"sku": "KEEP"}],
                "images": [{"old": True}],
            }
            merged = image_factory.merge_shopify_draft_images(
                original, result["product_image_manifest"]
            )
            for key in ("title", "description", "status", "variants"):
                self.assertEqual(original[key], merged[key])
            self.assertEqual(8, len(merged["images"]))

    def test_dropbox_backed_manifest_uses_same_order_and_stable_names(self):
        assets = []
        for spec in image_factory.PRODUCT_IMAGE_SLOT_SPECS:
            assets.append(
                {
                    "key": spec["asset_key"],
                    "label": spec["display_label"],
                    "zip_group": spec["zip_group"],
                    "include_in_zip": True,
                    "webp_path_dropbox_path": f"/remote/{spec['slot_id']}.webp",
                    "prompt_filename": spec.get("prompt_filename"),
                }
            )
        manifest = image_factory.build_product_image_manifest(
            assets, product_slug="remote", sport_slug="cricket"
        )
        ordered = image_factory.order_assets_by_product_manifest(assets, manifest)
        entries = mockup_storage.dropbox_selected_manifest(
            ordered,
            [image_factory.ASSET_CATEGORY_CORE, image_factory.ASSET_CATEGORY_PRODUCT],
        )
        self.assertEqual(EXPECTED_SLOTS, [row["product_slot_id"] for row in entries])
        self.assertEqual(
            [f"WEBP/{row['output_filename']}" for row in manifest],
            [row["relative_path"] for row in entries],
        )


if __name__ == "__main__":
    unittest.main()
