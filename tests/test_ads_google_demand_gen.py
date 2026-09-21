import csv
import hashlib
import io
import json
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from streamlit.testing.v1 import AppTest

import ads_google_demand_gen as google
import ads_google_ui as ui
import ads_page as ads
import ads_posting_handoff as handoff
import ads_posting_page as posting
from posting_import_csv import PostingImportCSVError, parse_posting_import_csv


def record(**kwargs):
    return google.build_result("Collector Legacy", "Motorsport", "Australia",
                               "https://www.sportscaveshop.com/products/collector-legacy", **kwargs)


def completed_csv(**overrides):
    row = next(csv.DictReader(io.StringIO(google.build_csv(record()).decode("utf-8-sig"))))
    row.update({"campaign_name": "AU | Collector Legacy", "ad_group_name": "Cold", "ad_name": "Image + Products",
                "product_feed_mode": "SINGLE PRODUCT", "product_feed_guidance": "Selected artwork and its valid variants",
                "audience_name": "AU | Collector Legacy | Search Intent | Cold",
                "custom_search_terms": "; ".join(f"collector art {i}" for i in range(12)),
                "demographic_signal": "All Demographics", "final_url_suffix": "utm_source=google&utm_medium=paid"})
    row.update({f"headline_{i}": f"Collector's Legacy {i}" for i in range(1, 6)})
    row.update({f"description_{i}": f"A collector piece for fans who remember the moment. Edition {i}." for i in range(1, 6)})
    row.update({f"{s['id']}_prompt": f"{s['label']}\nUse exact artwork, original ‘quotes’ and frame.\nSize {s['width']} × {s['height']}." for s in google.IMAGE_SLOTS})
    row.update(overrides)
    return csv_data(row)


def csv_data(row, headers=None, count=1):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=headers or google.CSV_HEADERS, lineterminator="\r\n", extrasaction="ignore")
    writer.writeheader()
    for _ in range(count):
        writer.writerow(row)
    return output.getvalue().encode("utf-8-sig")


def image_bytes(spec, fmt="PNG", transparent=False):
    buffer = io.BytesIO()
    with Image.new("RGBA" if transparent else "RGB", (spec["width"], spec["height"]),
                   (0, 0, 0, 0) if transparent else (30, 50, 70)) as image:
        image.save(buffer, format=fmt)
    return buffer.getvalue()


class MemoryDropbox:
    def __init__(self):
        self.files = {}
        self.fail = ""

    def upload(self, token, folder, items, **kwargs):
        successes = []
        for item in items:
            if item["relative_path"] == self.fail:
                return {"successes": [], "failures": [{"error": "offline"}]}
            path = folder + "/" + item["relative_path"]
            self.files[path] = item["data"]
            successes.append({"metadata": {"path_display": path}})
        return {"successes": successes, "failures": []}

    def read(self, token, path):
        return self.files[path]


class GoogleContractsTests(unittest.TestCase):
    def test_meta_prompts_are_byte_for_byte_unchanged(self):
        baseline = json.loads(Path(__file__).with_name("fixtures").joinpath("meta_new_ads_prompt_hashes.json").read_text())
        for category, campaign_type, country, expected_hash in baseline:
            with self.subTest(category=category, campaign_type=campaign_type, country=country):
                prompt = ads.build_ads_prompt("Collector Legacy", category, country, campaign_type,
                    product_url="https://www.sportscaveshop.com/products/collector-legacy", variation_token="regression-fixed",
                    product_metadata={"edition_limit": 100, "edition_limit_source": "Edition Ops product ledger"})
                self.assertEqual(hashlib.sha256(prompt.encode()).hexdigest(), expected_hash)

    def test_prompt_resolves_all_variables_for_every_category_and_market(self):
        for category in ads.CATEGORY_OPTIONS[1:]:
            for country in ads.COUNTRY_OPTIONS[1:]:
                with self.subTest(category=category, country=country):
                    prompt = google.build_google_prompt("The Collector — Edition of 75", category, country,
                        "https://www.sportscaveshop.com/products/the-collector",
                        product_metadata={"edition_limit": 75, "athlete_names": ["Verified Athlete"], "team_names": ["Verified Club"]})
                    self.assertNotIn("{{", prompt)
                    self.assertNotIn("Allan Moffat", prompt)
                    self.assertIn("Verified Athlete", prompt)
                    self.assertIn(country, prompt)
                    self.assertIn("ONLY 75 WILL EVER EXIST", prompt)
                    self.assertIn("IF A SPORTS CAVE GOOGLE DEMAND GEN CSV TEMPLATE IS ATTACHED:", prompt)
                    self.assertIn("Return the completed CSV as a downloadable .csv file.", prompt)
                    self.assertIn("Do not invoke image generation.", prompt)
                    self.assertIn("all 25 headline-description combinations", prompt)
                    self.assertIn("PRODUCT / ARTWORK LOCK", prompt)

    def test_unverified_baseball_scarcity_is_not_inherited(self):
        prompt = google.build_google_prompt("Baseball Collection", "Baseball", "USA", "https://example.com/product")
        self.assertIn("Scarcity verified:\nfalse", prompt)
        self.assertIn("Verified edition limit:\nNot verified", prompt)
        self.assertNotIn("ONLY 100", prompt)

    def test_slot_matrix_and_filenames(self):
        self.assertEqual(len(google.IMAGE_SLOTS), 9)
        self.assertEqual(len({s["id"] for s in google.IMAGE_SLOTS}), 9)
        for fmt, width, height, ratio in google.FORMATS:
            self.assertEqual(sum((s["width"], s["height"]) == (width, height) for s in google.IMAGE_SLOTS), 3)
        self.assertEqual(google.IMAGE_SLOTS[0]["filename"], "01-right-square.jpg")
        self.assertEqual(google.IMAGE_SLOTS[-1]["filename"], "09-left-vertical.jpg")

    def test_blank_template_is_generic_one_row_and_no_meta_fields(self):
        rows = list(csv.DictReader(io.StringIO(google.build_csv(template=True).decode("utf-8-sig"))))
        self.assertEqual(len(rows), 1)
        self.assertEqual(tuple(rows[0]), google.CSV_HEADERS)
        for key, value in google.FIXED_DEFAULTS.items():
            self.assertEqual(rows[0][key], value)
        self.assertEqual(rows[0]["product_name"], "")
        self.assertNotIn("primary_text", rows[0])
        self.assertNotIn("route_key", rows[0])

    def test_csv_import_export_roundtrip_multiline_unicode_and_blank_images(self):
        result, workflow = google.import_csv(completed_csv())
        self.assertEqual(len(result["google_config"]["headlines"]), 5)
        self.assertEqual(len(result["google_config"]["descriptions"]), 5)
        self.assertEqual(google.asset_count(workflow), 0)
        self.assertIn("Incomplete — 0/9", google.completion_label(workflow))
        self.assertEqual(google.parse_csv(google.build_csv(result, workflow)), google.parse_csv(completed_csv()))
        for spec in google.IMAGE_SLOTS:
            self.assertIn(spec["label"], result["google_config"]["image_slots"][spec["id"]]["prompt"])

    def test_csv_rejection_is_atomic_and_useful(self):
        original = record()
        work = google.new_workflow(original)
        before = deepcopy((original, work))
        cases = ({"platform": "meta"}, {"campaign_type": "Carousel"}, {"headline_1": "x" * 41},
                 {"description_2": "x" * 91}, {"headline_5": ""}, {"description_5": ""},
                 {"business_name": ""}, {"cta": ""}, {"product_url": ""}, {"product_url": "javascript:test"},
                 {"right_square_prompt": ""}, {"custom_search_terms": "one;two"})
        for values in cases:
            with self.subTest(values=values), self.assertRaises(google.GoogleCampaignError) as caught:
                google.import_csv(completed_csv(**values), current=original, workflow=work)
            self.assertTrue(str(caught.exception))
            self.assertEqual((original, work), before)
        row = google.parse_csv(completed_csv())
        for headers in (google.CSV_HEADERS[:-1], (*google.CSV_HEADERS, "headline_6"),
                        (*google.CSV_HEADERS, "headline_1"), tuple(h for h in google.CSV_HEADERS if h != "left_vertical_prompt")):
            with self.assertRaises(google.GoogleCampaignError):
                google.parse_csv(csv_data(row, headers))
        for count in (0, 2):
            with self.assertRaises(google.GoogleCampaignError):
                google.parse_csv(csv_data(row, count=count))

    def test_import_keeps_same_product_images_but_resets_changed_product(self):
        original, work = google.import_csv(completed_csv())
        work["slots"]["right_square"] = {"valid": True, "data": b"test"}
        same, same_work = google.import_csv(completed_csv(headline_1="New hook"), current=original, workflow=work)
        self.assertEqual(same["campaign_id"], original["campaign_id"])
        self.assertEqual(google.asset_count(same_work), 1)
        other, other_work = google.import_csv(completed_csv(product_name="Another product"), current=original, workflow=work)
        self.assertNotEqual(other["campaign_id"], original["campaign_id"])
        self.assertEqual(google.asset_count(other_work), 0)

    def test_images_keep_exact_dimensions_and_flatten_transparency(self):
        for spec in google.IMAGE_SLOTS:
            converted = google.process_image(image_bytes(spec, transparent=True), spec, original_name="transparent.png")
            with Image.open(io.BytesIO(converted["data"])) as image:
                self.assertEqual(image.format, "JPEG")
                self.assertEqual(image.mode, "RGB")
                self.assertEqual(image.size, (spec["width"], spec["height"]))
                self.assertTrue(all(channel > 245 for channel in image.getpixel((0, 0))))
                self.assertTrue(image.info["icc_profile"])
            self.assertEqual(converted["content_type"], "image/jpeg")
        with self.assertRaisesRegex(google.GoogleCampaignError, "requires 1200 × 628"):
            google.process_image(image_bytes(google.IMAGE_SLOTS[0]), google.IMAGE_SLOTS[1])

    def test_meta_new_upload_preserves_source_size_and_quality_95(self):
        source = io.BytesIO(image_bytes({"width": 123, "height": 123}, transparent=True))
        source.name = "source.png"
        result = {"context_key": "legacy-meta", "campaign_type": "Carousel", "product_name": "Collector"}
        workflow = {"slots": {}, "outcomes": {}}
        spec = ads.ads_image_workflow.campaign_image_slots("Carousel")[0]
        with patch.object(ads.st, "session_state", {}):
            ads._process_ads_image_upload(result, workflow, spec, source)
        slot = workflow["slots"][spec["id"]]
        with Image.open(io.BytesIO(slot["data"])) as output:
            self.assertEqual(output.size, (123, 123))
            self.assertEqual(output.format, "JPEG")
            expected = io.BytesIO()
            Image.new("RGB", (1, 1)).save(expected, format="JPEG", quality=95)
            with Image.open(io.BytesIO(expected.getvalue())) as quality_reference:
                self.assertEqual(output.quantization, quality_reference.quantization)
        self.assertFalse(ads._uses_new_ads_jpeg({"campaign_type": "Creative Refresh"}))

    def test_save_reopen_incomplete_and_complete_with_integrity_and_failure(self):
        storage = MemoryDropbox()
        with patch.object(google.dropbox, "upload_batch", side_effect=storage.upload), \
             patch.object(google.dropbox, "get_file_bytes", side_effect=storage.read), \
             patch.object(google.dropbox, "ensure_folder_path"):
            result, workflow = google.import_csv(completed_csv())
            google.save_campaign("token", "/Team", "/Team/Ads", result, workflow)
            manifest = workflow["outcomes"]["_campaign"]["path"]
            reopened, rework = google.load_campaign("token", "/Team", manifest)
            self.assertEqual(reopened, result)
            self.assertEqual(google.asset_count(rework), 0)
            for spec in google.IMAGE_SLOTS:
                rework["slots"][spec["id"]] = google.process_image(image_bytes(spec), spec, original_name="historical.png")
            google.save_campaign("token", "/Team", "/Team/Ads", reopened, rework)
            complete, complete_work = google.load_campaign("token", "/Team", manifest)
            self.assertEqual(google.asset_count(complete_work), 9)
            self.assertEqual(complete["status"], "complete")
            self.assertEqual(complete["created_at"], result["created_at"])
            for spec in google.IMAGE_SLOTS:
                slot = complete["google_config"]["image_slots"][spec["id"]]
                self.assertTrue(slot["saved_path"].endswith(".jpg"))
                self.assertEqual(slot["content_type"], "image/jpeg")
                self.assertEqual(hashlib.sha256(storage.files[slot["saved_path"]]).hexdigest(), slot["sha256"])
                self.assertEqual(complete_work["slots"][spec["id"]]["data"], storage.files[slot["saved_path"]])
            committed = storage.files[manifest]
            storage.fail = google.MANIFEST_FILENAME
            complete_work["slots"].pop("right_square")
            with self.assertRaisesRegex(google.GoogleCampaignError, "Retry saving"):
                google.save_campaign("token", "/Team", "/Team/Ads", complete, complete_work)
            self.assertEqual(storage.files[manifest], committed)
            self.assertEqual(google.asset_count(google.load_campaign("token", "/Team", manifest)[1]), 9)
            storage.fail = ""
            google.save_campaign("token", "/Team", "/Team/Ads", complete, complete_work)
            self.assertEqual(google.asset_count(google.load_campaign("token", "/Team", manifest)[1]), 8)
            with self.assertRaises(google.GoogleCampaignError):
                google.load_campaign("token", "/Different", manifest)

    def test_google_never_enters_meta_posting_and_legacy_defaults_meta(self):
        self.assertEqual(google.platform_for({}), "meta")
        self.assertEqual(google.platform_for({"platform": None}), "meta")
        with self.assertRaises(PostingImportCSVError):
            parse_posting_import_csv(completed_csv())
        with self.assertRaisesRegex(handoff.SavedPackageError, "Only Meta"):
            handoff.build_saved_package(result={"platform": "google", "campaign_type": "Carousel"},
                source_signature="", source_copy={}, copy_csv=b"", assets=[], files=[], folder="")
        with self.assertRaisesRegex(handoff.SavedPackageError, "Only Meta"):
            handoff.queue_saved_package({"platform": "google", "version": 1}, state={})
        state = {"untouched": True}
        with self.assertRaisesRegex(PostingImportCSVError, "Only Meta"):
            posting.apply_posting_import_to_state({"platform": "google"}, [], state=state)
        self.assertEqual(state, {"untouched": True})
        value = record()
        self.assertIs(ads.ensure_current_ads_result_prompt(value), value)


def field(elements, label):
    return next(element for element in elements if element.label == label)


class GoogleUITests(unittest.TestCase):
    def setUp(self):
        self.rows = patch.object(ads, "load_edition_ops_product_rows", return_value=[])
        self.rows.start()
        self.addCleanup(self.rows.stop)

    def start(self):
        app = AppTest.from_string("import ads_page\nads_page.render_page()").run(timeout=20)
        field(app.text_input, "Product name").set_value("Collector Legacy").run()
        field(app.selectbox, "Category").select("Motorsport").run()
        field(app.selectbox, "Country").select("Australia").run()
        field(app.text_input, "Product page URL *").set_value("https://www.sportscaveshop.com/products/collector-legacy").run()
        return app

    def test_platform_default_types_copy_csv_upload_and_assets(self):
        app = self.start()
        self.assertEqual(field(app.selectbox, "Platform").value, "Meta")
        self.assertEqual(field(app.selectbox, "Campaign type").options, ads.CAMPAIGN_TYPE_OPTIONS)
        field(app.selectbox, "Platform").select("Google").run()
        self.assertEqual(field(app.selectbox, "Campaign type").options, ["Demand Gen"])
        field(app.button, "Submit").click().run()
        self.assertFalse(app.exception)
        self.assertIn("GOOGLE DEMAND GEN", app.session_state[google.RESULT_KEY]["master_prompt"])
        self.assertEqual(sum(u.label == "Upload image" for u in app.file_uploader), 9)
        self.assertTrue(field(app.button, "Post Now").disabled)
        self.assertFalse(field(app.button, "Save campaign").disabled)
        self.assertEqual(len(app.session_state[google.RESULT_KEY]["google_config"]["headlines"]), 5)
        field(app.file_uploader, "Upload Completed Google CSV").set_value([("complete.csv", completed_csv(), "text/csv")]).run()
        self.assertFalse(app.exception)
        self.assertIn("Google Copy Loaded ✓", [e.value for e in app.success])
        uploads = [u for u in app.file_uploader if u.label == "Upload image"]
        uploads[0].set_value([("square.png", image_bytes(google.IMAGE_SLOTS[0]), "image/png")]).run()
        self.assertFalse(app.exception)
        self.assertIn("Google Assets: 1 / 9", [e.value for e in app.caption])
        remove = next(b for b in app.button if b.label == "Remove" and not b.disabled)
        remove.click().run()
        self.assertIn("Google Assets: 0 / 9", [e.value for e in app.caption])

    def test_switching_platforms_preserves_each_result_images_and_form(self):
        app = self.start()
        field(app.selectbox, "Campaign type").select("Carousel").run()
        field(app.button, "Submit").click().run()
        field(app.file_uploader, "Carousel 1").set_value([("meta.png", image_bytes(google.IMAGE_SLOTS[0]), "image/png")]).run()
        meta = deepcopy(app.session_state[ads.ADS_RESULT_STATE_KEY])
        meta_work = deepcopy(app.session_state[ads.ADS_IMAGE_STATE_KEY])
        field(app.selectbox, "Platform").select("Google").run()
        field(app.button, "Submit").click().run()
        field(app.file_uploader, "Upload Completed Google CSV").set_value([("complete.csv", completed_csv(), "text/csv")]).run()
        google_before = deepcopy(app.session_state[google.RESULT_KEY])
        field(app.selectbox, "Platform").select("Meta").run()
        self.assertFalse(app.exception)
        self.assertEqual(field(app.selectbox, "Campaign type").value, "Carousel")
        self.assertEqual(app.session_state[ads.ADS_RESULT_STATE_KEY], meta)
        self.assertEqual(app.session_state[ads.ADS_IMAGE_STATE_KEY], meta_work)
        field(app.text_input, "Product name").set_value("Different Meta draft").run()
        field(app.selectbox, "Platform").select("Google").run()
        self.assertFalse(app.exception)
        self.assertEqual(field(app.text_input, "Product name").value, "Collector Legacy")
        self.assertEqual(app.session_state[google.RESULT_KEY], google_before)

    def test_incomplete_save_and_reopen_from_existing_files_picker(self):
        storage = MemoryDropbox()
        with patch.object(ads, "_ads_dropbox_connection", return_value=("token", "/Team")), \
             patch.object(ads.os_accounts, "can_access_page", return_value=True), \
             patch.object(ads, "_render_ads_folder_picker", return_value="/Team/Ads") as picker, \
             patch.object(google.dropbox, "upload_batch", side_effect=storage.upload), \
             patch.object(google.dropbox, "get_file_bytes", side_effect=storage.read), \
             patch.object(google.dropbox, "ensure_folder_path"):
            app = self.start()
            field(app.selectbox, "Platform").select("Google").run()
            field(app.button, "Submit").click().run()
            field(app.button, "Save campaign").click().run()
            field(app.button, "Save campaign here").click().run()
            self.assertFalse(app.exception)
            saved = deepcopy(app.session_state[google.RESULT_KEY])
            folder = app.session_state[google.WORKFLOW_KEY]["saved_folder_path"]
            self.assertEqual(saved["asset_count"], 0)
            picker.return_value = folder
            reopened = AppTest.from_string("import ads_page\nads_page.render_page()")
            reopened.session_state[ui.PLATFORM_KEY] = "Google"
            reopened.run()
            field(reopened.button, "Browse saved campaigns").click().run()
            field(reopened.button, "Open this Google campaign").click().run()
            self.assertFalse(reopened.exception)
            self.assertEqual(reopened.session_state[google.RESULT_KEY], saved)
            self.assertEqual(field(reopened.text_input, "Product name").value, saved["product_name"])
            self.assertEqual(field(reopened.text_input, "Product page URL *").value, saved["product_url"])
            self.assertFalse(field(reopened.button, "Save campaign").disabled)

    def test_csv_import_updates_form_and_rejects_meta_without_changing_draft(self):
        app = self.start()
        field(app.selectbox, "Platform").select("Google").run()
        field(app.button, "Submit").click().run()
        field(app.file_uploader, "Upload Completed Google CSV").set_value([("complete.csv", completed_csv(
            product_name="Different Product", product_url="https://example.com/products/different", country="USA"), "text/csv")]).run()
        self.assertFalse(app.exception)
        self.assertEqual(field(app.text_input, "Product name").value, "Different Product")
        self.assertEqual(field(app.selectbox, "Country").value, "USA")
        self.assertEqual(field(app.text_input, "Product page URL *").value, "https://example.com/products/different")
        before = deepcopy(app.session_state[google.RESULT_KEY])
        field(app.file_uploader, "Upload Completed Google CSV").set_value([("bad.csv", completed_csv(platform="meta"), "text/csv")]).run()
        self.assertEqual(app.session_state[google.RESULT_KEY], before)
        self.assertTrue(app.error)


if __name__ == "__main__":
    unittest.main()
