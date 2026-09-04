import ast
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

from PIL import Image
from streamlit.testing.v1 import AppTest

import app
import design_studio_styles
import image_factory
import prompt_store
import sports_cave_prompt_blocks
import website_mockups as website
from tests.test_mockup_second_image_upload import CountingUpload, FakeSessionState, png_bytes


ROOT = Path(__file__).resolve().parents[1]


def make_result(root):
    assets = []
    for spec in image_factory.PRODUCT_IMAGE_SLOT_SPECS:
        if spec.get("prompt_filename"):
            continue
        path = Path(root) / f"{spec['asset_key']}.webp"
        Image.new("RGB", (24, 24), "navy").save(path, "WEBP")
        assets.append(image_factory.build_asset_record(key=spec["asset_key"], label=spec["display_label"], webp_path=str(path)))
    return app.normalize_generation_result({
        "product_name": "Cricket Collector Legacy", "sport_category": "Cricket",
        "product_slug": "cricket-collector-legacy", "sport_slug": "cricket", "run_dir": str(root),
        "website_mockups_version": 2, "assets": assets, "black_framed_webp_path": str(Path(root) / "black.webp"),
    })


def mockup_ui():
    import app
    import streamlit as st
    app.render_website_mockup_brief(st.session_state.last_generation_result)


class WebsiteMockupPromptTests(unittest.TestCase):
    def snapshot(self, rooms=None):
        return website.create_snapshot("Cricket Collector Legacy", "Cricket", "Nostalgic Tribute", "1990-1999",
                                       rooms or website.recommend_rooms("Cricket", "Nostalgic Tribute", "1990-1999"))

    def test_authoritative_design_types_and_exact_era_options(self):
        self.assertEqual(website.design_type_options(), design_studio_styles.style_labels())
        self.assertEqual(website.ERA_OPTIONS, ("Pre-1950", "1950-1969", "1970-1979", "1980-1989", "1990-1999",
                                             "2000-2009", "2010-2019", "2020-Present", "Timeless / Multiple Eras", "Not Sure"))

    def test_room_library_reuses_existing_rooms_without_duplicate_aliases(self):
        self.assertEqual(len(website.ROOMS), 33)
        for filename in ("01-man-cave-prompt.txt", "02-office-prompt.txt", "03-living-room-prompt.txt",
                         "07-home-sports-bar-prompt.txt", "08-collector-display-room-prompt.txt", "09-luxury-entry-wall-prompt.txt",
                         "10-private-club-lounge-prompt.txt", "12-fireplace-feature-wall-prompt.txt", "13-premium-bedroom-prompt.txt",
                         "15-premium-tool-shed-workshop-prompt.txt", "16-man-cave-with-pool-table-prompt.txt", "17-architectural-loft-prompt.txt"):
            self.assertIn(filename, {room.source for room in website.ROOMS})
        self.assertEqual(website.room_for("Office"), website.room_for("Home Office"))
        self.assertEqual(website.room_for("Home Sports Bar"), website.room_for("Premium Home Sports Bar"))
        for room in website.ROOMS:
            self.assertGreater(len(room.brief), 90)
        for label in ("Home Gym", "Garage", "Collector Garage", "Luxury Garage", "Study / Library", "Staircase / Landing Gallery"):
            self.assertTrue(website.room_for(label).brief)

    def test_best_three_are_deterministic_unique_and_diverse_for_all_contexts(self):
        for sport in (*website.SPORT_PALETTES, "unknown"):
            for style in website.design_type_options():
                for era in website.ERA_OPTIONS:
                    rooms = website.recommend_rooms(sport, style, era)
                    self.assertEqual(rooms, website.recommend_rooms(sport, style, era))
                    self.assertEqual(len(set(rooms)), 3)
                    self.assertEqual(len({website.room_for(key).family for key in rooms}), 3)
        self.assertEqual(website.recommend_rooms("Cricket", "Nostalgic Tribute", "1990-1999"),
                         ("study-library", "clubhouse", "heritage-living"))
        self.assertNotEqual(website.recommend_rooms("Cricket", "Nostalgic Tribute", "1990-1999"),
                            website.recommend_rooms("Motorsport", "Minimalist Hero", "2020-Present"))

    def test_aliases_and_unknown_sport_have_safe_distinct_palette_families(self):
        for first, second in ((" Cricket ", "cricket"), ("NBA", "Basketball"), ("Soccer", "Football"),
                              ("American Football", "NFL"), ("AFL", "Australian Rules"), ("Formula 1", "Motorsport")):
            self.assertEqual(website.sport_key(first), website.sport_key(second))
        self.assertEqual(website.sport_key("unmapped sport"), "other")
        for tones in website.SPORT_PALETTES.values():
            self.assertEqual(len(set(tones)), 3)
        self.assertNotEqual(website.SPORT_PALETTES["cricket"], website.SPORT_PALETTES["basketball"])

    def test_manual_overrides_keep_exact_submitted_order_and_reject_duplicates(self):
        chosen = ["Luxury Garage", "Home Gym", "Man Cave"]
        brief = self.snapshot(chosen)
        self.assertEqual([slot["label"] for slot in brief["slots"]], chosen)
        self.assertEqual([slot["number"] for slot in brief["slots"]], [1, 2, 3])
        self.assertEqual([slot["filename"] for slot in brief["slots"]], list(website.SLOT_FILENAMES))
        for invalid in (("Office", "Home Office", "Garage"), ("Man Cave",) * 3, ("Garage", "Home Gym")):
            with self.assertRaises(ValueError):
                self.snapshot(invalid)

    def test_final_master_prompt_keeps_full_authoritative_rules_and_audience_context(self):
        snapshot = self.snapshot()
        prompt = snapshot["master_prompt"]
        self.assertEqual(prompt.count(sports_cave_prompt_blocks.build_sports_cave_image_realism_rules()), 1)
        for fragment in ("PRODUCT NAME: Cricket Collector Legacy", "SPORT: Cricket", "DESIGN TYPE: Nostalgic Tribute",
                         "ERA: 1990-1999", "Warm 1990s fan nostalgia", "Warm, heritage, emotionally familiar",
                         "muted pavilion green", "warm heritage clubhouse cream", "deep charcoal-green",
                         "original full-resolution", "Design Type, Era and Sport influence ONLY", "Never change their order",
                         "THREE DIFFERENT REAL CUSTOMER HOMES", "Generate MOCKUP 1 first", '"Generate Mockup 2"',
                         '"Generate Mockup 3"', "Never combine them into a collage", "Do not generate all three simultaneously",
                         "Never change their order", "roughly 50mm", "roughly 40mm", "roughly 55mm", "1024 x 1024",
                         "about 45–60%", "Before returning each image", "never a preview or a previously generated mockup"):
            self.assertIn(fragment, prompt)
        for slot in snapshot["slots"]:
            self.assertIn(f"MOCKUP {slot['number']} — {slot['label']}", prompt)
        self.assertEqual(prompt.count("ASSIGNED WALL TREATMENT:"), 3)
        self.assertEqual(prompt.count("ASSIGNED CUSTOMER HOME:"), 3)
        self.assertIn("authentic timber, textured plaster, natural stone", prompt)

    def test_snapshot_freezes_prompt_even_if_cached_room_template_changes(self):
        snapshot = self.snapshot(["Man Cave", "Office", "Living Room"])
        original = snapshot["master_prompt"]
        with mock.patch.object(image_factory, "get_lifestyle_prompt_spec", return_value={"prompt": "Changed template"}):
            self.assertTrue(all(item["prompt"] == original for item in website.prompt_items(snapshot)))
        self.assertIn("minimal premium office", original)
        self.assertNotIn("from the last image created", original)

    def test_prompt_creation_never_calls_external_prompt_storage(self):
        with mock.patch.object(prompt_store, "_load_prompt_from_supabase", side_effect=AssertionError("external call")):
            for room in website.ROOMS:
                self.assertTrue(website.room_prompt(room))
            self.snapshot()

    def test_unchanged_master_legacy_prompts_top_assets_and_export_code(self):
        baseline = json.loads((ROOT / "tests/fixtures/website_mockups_baseline.json").read_text())
        for filename, _, prompt in image_factory.LIFESTYLE_PROMPT_SPECS:
            self.assertEqual(hashlib.sha256(prompt.encode()).hexdigest(), baseline["prompts"][filename])
        self.assertEqual(hashlib.sha256(sports_cave_prompt_blocks.build_sports_cave_image_realism_rules().encode()).hexdigest(), baseline["master"])
        trees = {}
        for identity, digest in baseline["functions"].items():
            filename, function = identity.split(":")
            if filename not in trees:
                trees[filename] = ast.parse((ROOT / filename).read_text(encoding="utf-8-sig"))
            node = next(node for node in trees[filename].body if isinstance(node, ast.FunctionDef) and node.name == function)
            self.assertEqual(hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest(), digest, identity)


class WebsiteMockupStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = FakeSessionState(last_generation_result=None)
        self.patcher = mock.patch.object(app.st, "session_state", self.state)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.activity = mock.patch.object(app, "record_activity_log")
        self.activity.start()
        self.addCleanup(self.activity.stop)
        self.result = make_result(self.temp.name)

    def submit(self, rooms=("Man Cave", "Home Office", "Living Room")):
        self.result = app.submit_website_mockup_brief(self.result, "Nostalgic Tribute", "1990-1999", rooms)
        return self.result

    def upload(self, number, color):
        slot = self.result["website_mockup_brief"]["slots"][number - 1]
        upload = CountingUpload(png_bytes(color), file_id=f"image-{number}-{color}")
        self.result = app.auto_register_lifestyle_upload(self.result, Path(slot["filename"]), upload)
        return self.result

    def test_existing_room_filename_and_conversion_match_old_implementation(self):
        for room, legacy_filename in (("Man Cave", "01-man-cave-prompt.txt"), ("Office", "02-office-prompt.txt"), ("Living Room", "03-living-room-prompt.txt")):
            original = image_factory.save_lifestyle_mockup(self.temp.name, "known-product", "cricket", legacy_filename, io.BytesIO(png_bytes((40, 70, 90))))
            dynamic = image_factory.save_lifestyle_mockup(self.temp.name, "known-product", "cricket", website.SLOT_FILENAMES[0],
                                                         io.BytesIO(png_bytes((40, 70, 90))), room_variant=website.room_for(room).variant)
            self.assertEqual(original, dynamic)
            self.assertEqual(Path(dynamic["webp_path"]).name, f"known-product-black-framed-cricket-{website.room_for(room).variant}.webp")
            with Image.open(dynamic["webp_path"]) as image:
                self.assertEqual((image.format, image.size), ("WEBP", (12, 12)))

    def test_dynamic_rooms_keep_upload_manifest_and_zip_order(self):
        rooms = ("Luxury Garage", "Study / Library", "Premium Home Sports Bar")
        self.submit(rooms)
        before_core = [dict(asset) for asset in self.result["assets"] if asset["asset_group"] == "generated"]
        for number in (1, 2, 3):
            self.upload(number, (number * 55, 30, 70))
            self.assertEqual(len(self.result["lifestyle_mockup_paths"]), number)
        manifest = self.result["product_image_manifest"]
        self.assertEqual([row["display_label"] for row in manifest[1:4]], list(rooms))
        self.assertEqual([row["sort_position"] for row in manifest], list(range(1, 9)))
        self.assertEqual([row["slot_id"] for row in manifest[1:4]], ["man-cave", "office", "living-room"])
        self.assertTrue(self.result["product_image_readiness"]["complete"])
        self.assertEqual(before_core, [asset for asset in self.result["assets"] if asset["asset_group"] == "generated"])
        expected = [f"cricket-collector-legacy-black-framed-cricket-{website.room_for(room).variant}.webp" for room in rooms]
        self.assertEqual([row["output_filename"] for row in manifest[1:4]], expected)
        for row in manifest[1:4]:
            self.assertEqual(Path(row["local_path"]).name, row["output_filename"])
        package = app.build_filtered_download_zip(self.result, [image_factory.ASSET_CATEGORY_CORE, image_factory.ASSET_CATEGORY_PRODUCT])
        with zipfile.ZipFile(package) as archive:
            names = archive.namelist()
        self.assertEqual([name for name in names if name.startswith("WEBP/")], [f"WEBP/{row['output_filename']}" for row in manifest])
        self.assertEqual(len([name for name in names if name.startswith("jpg/")]), 3)
        dropbox = app._mockup_dropbox_manifest(self.result, [image_factory.ASSET_CATEGORY_CORE, image_factory.ASSET_CATEGORY_PRODUCT])
        self.assertEqual([entry["archive_name"] for entry in dropbox], names)

    def test_resubmit_clears_associations_keeps_files_and_rejects_stale_upload(self):
        self.submit()
        self.upload(1, (10, 80, 90))
        old = self.result
        old_snapshot = old["website_mockup_brief"]
        old_path = Path(old["lifestyle_mockup_paths"][website.SLOT_FILENAMES[0]]["webp_path"])
        old_bytes = old_path.read_bytes()
        old_key = app.get_lifestyle_upload_slot_key(old, website.SLOT_FILENAMES[0])
        self.submit(("Home Gym", "Luxury Garage", "Study / Library"))
        self.assertNotEqual(old_snapshot["id"], self.result["website_mockup_brief"]["id"])
        self.assertEqual(self.result["lifestyle_mockup_paths"], {})
        self.assertEqual(old_path.read_bytes(), old_bytes)
        self.assertEqual(self.result["website_mockup_history"][0]["brief"], old_snapshot)
        self.assertNotEqual(old_key, app.get_lifestyle_upload_slot_key(self.result, website.SLOT_FILENAMES[0]))
        old = {**old, "run_dir": Path(old["run_dir"])}
        with mock.patch.object(app, "save_uploaded_lifestyle_result", side_effect=AssertionError("stale upload")):
            current = app.auto_register_lifestyle_upload(old, Path(website.SLOT_FILENAMES[0]), CountingUpload(png_bytes((90, 80, 70)), file_id="stale"))
        self.assertEqual(current["website_mockup_brief"], self.result["website_mockup_brief"])
        self.assertEqual(current["lifestyle_mockup_paths"], {})

    def test_invalid_resubmit_leaves_current_run_untouched(self):
        self.submit()
        before = self.result["website_mockup_brief"]
        with self.assertRaises(ValueError):
            self.submit(("Man Cave", "Man Cave", "Man Cave"))
        self.assertEqual(self.state.last_generation_result["website_mockup_brief"], before)

    def test_manifest_restore_and_prompt_pack_retain_submitted_snapshot(self):
        self.submit(("Home Gym", "Luxury Garage", "Study / Library"))
        self.upload(2, (110, 20, 30))
        disk = json.loads((Path(self.temp.name) / "manifest.json").read_text())
        restored = app.normalize_generation_result({**disk, "run_dir": self.temp.name, "black_framed_webp_path": self.result["black_framed_webp_path"]})
        restored = app.ensure_lifestyle_prompts(restored)
        self.assertEqual(restored["website_mockup_brief"], self.result["website_mockup_brief"])
        self.assertEqual([Path(path).name for path in restored["prompt_paths"]], list(website.SLOT_FILENAMES))
        self.assertTrue(restored["product_image_manifest"][2]["ready"])
        packed = app.build_lifestyle_prompt_pack(restored)
        for item in packed["final_prompt_items"]:
            self.assertEqual(item["prompt"], self.result["website_mockup_brief"]["master_prompt"])


class WebsiteMockupUITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.activity = mock.patch.object(app, "record_activity_log")
        self.activity.start()
        self.addCleanup(self.activity.stop)
        # app.main() runs during a bare module import; Streamlit's inactive root
        # can retain the login form metadata. The tested UI starts outside it.
        self.form_state = mock.patch.object(app.st._main, "_form_data", None)
        self.form_state.start()
        self.addCleanup(self.form_state.stop)
        self.ui = AppTest.from_function(mockup_ui)
        self.ui.session_state.last_generation_result = make_result(self.temp.name)
        self.ui.run(timeout=30)

    def submit(self):
        next(button for button in self.ui.button if button.label == "Create Mockup Brief").click()
        self.ui.run(timeout=30)
        self.assertFalse(self.ui.exception)

    def test_compact_brief_then_three_cards_with_one_copy_master(self):
        self.assertFalse(self.ui.exception)
        self.assertEqual(len(self.ui.selectbox), 5)
        self.assertEqual(len(self.ui.file_uploader), 0)
        self.ui.selectbox[0].select("Nostalgic Tribute")
        self.ui.selectbox[1].select("1990-1999")
        self.ui.run(timeout=30)
        self.assertEqual([select.value for select in self.ui.selectbox[2:]], ["study-library", "clubhouse", "heritage-living"])
        self.submit()
        self.assertEqual(len(self.ui.file_uploader), 3)
        headings = "\n".join(element.value for element in self.ui.markdown)
        for number, room in enumerate(("Study / Library", "Clubhouse-Inspired Lounge", "Heritage Living Room"), 1):
            self.assertIn(f"{number:02d} — {room}", headings)
        for removed in ("Close-Up Premium Wall Shot", "Limited Edition Detail Shot", "Instant Experience Cover Banner", "Social Lifestyle Mockups", "Product Page Lifestyle Mockups"):
            self.assertNotIn(removed, headings)
        html = "\n".join(element.proto.srcdoc for element in self.ui.get("iframe"))
        self.assertEqual(html.count("Copy Master Prompt"), 1)

    def test_draft_edits_and_upload_reruns_keep_active_snapshot_and_order(self):
        self.submit()
        before = self.ui.session_state.last_generation_result["website_mockup_brief"]
        keys = [uploader.key for uploader in self.ui.file_uploader]
        self.ui.file_uploader[0].set_value([("first.png", png_bytes((35, 60, 80)), "image/png")])
        self.ui.run(timeout=30)
        self.ui.selectbox[2].select("home-gym")
        self.ui.run(timeout=30)
        self.assertEqual(self.ui.session_state.last_generation_result["website_mockup_brief"], before)
        self.assertEqual([uploader.key for uploader in self.ui.file_uploader], keys)
        self.assertIn(website.SLOT_FILENAMES[0], self.ui.session_state.last_generation_result["lifestyle_mockup_paths"])
        self.ui.file_uploader[1].set_value([("second.png", png_bytes((80, 60, 35)), "image/png")])
        self.ui.run(timeout=30)
        self.assertEqual(len(self.ui.session_state.last_generation_result["lifestyle_mockup_paths"]), 2)
        self.assertFalse(self.ui.exception)
        self.submit()
        after = self.ui.session_state.last_generation_result
        self.assertEqual(after["website_mockup_brief"]["slots"][0]["room_key"], "home-gym")
        self.assertEqual(after["lifestyle_mockup_paths"], {})
        self.assertNotEqual([uploader.key for uploader in self.ui.file_uploader], keys)

    def test_duplicate_room_submission_is_visible_and_keeps_existing_cards(self):
        self.submit()
        before = self.ui.session_state.last_generation_result["website_mockup_brief"]
        for select in self.ui.selectbox[2:]:
            select.select("man-cave")
        self.ui.run(timeout=30)
        self.submit()
        self.assertTrue(any("three different room" in error.value for error in self.ui.error))
        self.assertEqual(self.ui.session_state.last_generation_result["website_mockup_brief"], before)
        self.assertEqual(len(self.ui.file_uploader), 3)


if __name__ == "__main__":
    unittest.main()
