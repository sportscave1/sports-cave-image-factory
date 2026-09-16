import hashlib
import csv
import io
import json
import unittest
from pathlib import Path

import ads_page as ads
import ads_ie_copy as copy
import posting_import_csv as posting
from tests.test_ads_page import run_ads_page, set_product_name, select_option, set_product_url, button_by_label, instant_experience_csv_notes, uploader_by_label


class CopyV2Tests(unittest.TestCase):
    def record(self, name="Don Mattingly October 4 1995", sport="Baseball", market="USA", **kw):
        return ads.build_ads_result_record(name, sport, market, "Instant Experience", variation_token="copy-v2", **kw)

    def notes(self):
        notes = instant_experience_csv_notes()
        for key, rows in notes.items():
            rows[0]["cta"] = copy.ROUTES[key][3]
        return notes

    def test_public_prompt_product_market_and_fact_contracts(self):
        for name, sport, market, metadata in (
            ("Don Mattingly October 4 1995", "Baseball", "USA", {"edition_limit": 100}),
            ("Peter Brock Historic Motorsport", "Motorsport", "Australia", {"product_era": "historic", "edition_limit": 100}),
            ("Current Cricket Athlete", "Cricket", "Australia", {}),
            ("Verified Rivalry", "Football", "UK", {"relationship_type": "rivalry"}),
        ):
            with self.subTest(name=name):
                r = self.record(name, sport, market, product_metadata=metadata)
                text = r["master_prompt"]
                for marker in (copy.VERSION, name, "OPTIONAL MICRO-RESEARCH", "2–4 focused searches", "Empty ATHLETE_NAMES", "35–65 words", "product truth", "identity, belonging", "Current Australian athletes", "verified rivalry/opposition", "Shop Now", ads.META_AD_URL_PARAMETERS):
                    self.assertIn(marker, text)
                for stale in ("exactly nine", "three-row", "Description 1", "Description 2", "Description 3", "COPY VARIATIONS"):
                    self.assertNotIn(stale, text)
                grouped = text.split("GROUPED INSTANT EXPERIENCE OUTPUT — COPY ONE ROUTE AT A TIME")[1]
                self.assertEqual(grouped.count("\nAD COPY\n"), 3)
                for cta in ("Claim Your Edition", "Secure Your Edition", "Own This Edition"):
                    self.assertIn("CTA:\n" + cta, grouped)
                self.assertNotIn("Limited to 100 worldwide.", text)
                if not metadata:
                    self.assertNotIn("LIMITED TO 100", grouped)
                    visuals = ads.resolve_standard_instant_experience_visuals(product_name=name, category=sport, product_metadata=metadata, variation_token="copy-v2")
                    self.assertTrue(all(v["edition_limit_used"] != "100" for v in visuals))

    def test_seed_is_deterministic_diverse_and_rivalry_gated(self):
        args = ("Single Athlete", "Baseball", "USA", "seed", {})
        self.assertEqual(copy.cues(*args), copy.cues(*args))
        results = [copy.cues("Single Athlete", "Baseball", "USA", str(i), {}) for i in range(30)]
        self.assertGreater(len({r[0]["opening_hook_family"] for r in results}), 1)
        self.assertGreater(len({r[0]["headline_family"] for r in results}), 1)
        self.assertNotIn("rivalry_challenge", str(results))
        rival = [copy.cues("A v B", "Football", "UK", str(i), {"RELATIONSHIP_TYPE": "rivalry"}) for i in range(30)]
        self.assertIn("rivalry_challenge", str(rival))
        previous = copy.cues(*args)
        fresh = copy.cues(*args, recent=previous)
        self.assertTrue(all(a["opening_hook_family"] != b["opening_hook_family"] for a, b in zip(previous, fresh)))
        current = [copy.cues("Current Athlete", "Cricket", "Australia", str(i), {"ERA": "current"}) for i in range(30)]
        self.assertNotIn("era_memory", str(current))
        self.assertNotIn("remembered_moment", str(current))

    def test_visual_bytes_unchanged_except_selected_copy_cta_metadata(self):
        cases = json.loads((Path(__file__).parent / "fixtures/ie_copy_v2_visual_baseline.json").read_text(encoding="utf8"))
        for case in cases:
            expected = case["sha256"]
            # Only these stale Meta-copy instructions change inside the Smart Hybrid prompt.
            actual = ads.build_standard_instant_experience_visual_prompts(**case["kwargs"])
            original = actual.replace("- Selected Meta copy uses Claim Your Edition for Smart Hybrid, Secure Your Edition for Private Gallery and Own This Edition for The Cave.", "- For the V4 Premium Scarcity room system, Description 1 in all three routes must use CTA field Claim Your Edition.").replace("- Each route has one selected Meta CTA; only Smart Hybrid repeats CLAIM YOUR EDITION on the image.", "- Description 1 for every route must use CTA field Claim Your Edition; only Smart Hybrid repeats this CTA on the image.")
            self.assertEqual(hashlib.sha256(original.encode()).hexdigest(), expected)

    def test_three_row_export_import_and_posting_hydration(self):
        r = self.record()
        data = ads.build_instant_experience_copy_csv(r, concept_notes=self.notes())
        rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
        self.assertEqual(len(rows), 3)
        self.assertEqual(tuple(rows[0]), ads.INSTANT_EXPERIENCE_COPY_CSV_HEADERS)
        self.assertTrue(all(row["output_mode"] == copy.OUTPUT_MODE for row in rows))
        parsed = ads.parse_instant_experience_copy_csv(data, r)
        self.assertEqual([len(v) for v in parsed.values()], [1, 1, 1])
        batch = posting.parse_posting_import_csv(data)
        self.assertEqual(batch, posting.parse_ads_import_csv(data))
        self.assertEqual(len(batch["ads"]), 3)
        for ad, key in zip(batch["ads"], copy.ROUTES):
            self.assertEqual(ad["primary_text"], self.notes()[key][0]["primary_text"])
            self.assertEqual(ad["cta"], copy.ROUTES[key][3])
            self.assertEqual(len(ad["variations"]), 1)

    def test_legacy_nine_rows_preserved_first_selected(self):
        r = self.record()
        legacy = {**r, "_legacy_ie_csv": True}
        data = ads.build_instant_experience_copy_csv(legacy, concept_notes=instant_experience_csv_notes())
        self.assertEqual(len(ads.parse_instant_experience_copy_csv(data, r)["premium_scarcity_front"]), 3)
        workflow = {}
        ads.apply_instant_experience_copy_csv(r, workflow, data)
        self.assertEqual(len(workflow["legacy_instant_experience_copy"]["premium_scarcity_front"]), 3)
        active = workflow["ad_notes"]["instant_experience_concepts"]
        self.assertEqual([len(v) for v in active.values()], [1, 1, 1])
        self.assertEqual(active["premium_scarcity_front"][0]["primary_text"], instant_experience_csv_notes()["premium_scarcity_front"][0]["primary_text"])
        self.assertTrue(ads.instant_experience_copy_complete(workflow))

    def test_import_is_transactional_and_records_actual_copy_history(self):
        result = self.record()
        workflow = {"ad_notes": {}}
        with self.assertRaises(ads.InstantExperienceCopyCSVError):
            ads.apply_instant_experience_copy_csv(result, workflow, b"broken")
        self.assertEqual(workflow, {"ad_notes": {}})
        ads.apply_instant_experience_copy_csv(result, workflow, ads.build_instant_experience_copy_csv(result, concept_notes=self.notes()))
        history = ads.st.session_state[ads.ADS_IE_RECENT_FINGERPRINTS_KEY]
        self.assertTrue(any(item.get("first_sentence_normalized") and item.get("headline") for item in history))
        self.assertTrue(ads.instant_experience_copy_complete(workflow))

    def test_actual_submit_ui_has_exactly_three_copy_sets(self):
        app = run_ads_page()
        set_product_name(app, "Don Mattingly")
        select_option(app, "Category", "Baseball")
        select_option(app, "Country", "USA")
        select_option(app, "Campaign type", "Instant Experience")
        set_product_url(app)
        button_by_label(app, "Submit").click().run(timeout=20)
        self.assertEqual(len(app.exception), 0)
        fields = [x for x in app.text_area if str(x.key).startswith("ads-ie-concept-copy-field::")]
        self.assertEqual(len(fields), 9)
        self.assertEqual([x.label for x in fields].count("Description"), 3)
        self.assertEqual([x.label for x in fields].count("Headline"), 3)
        self.assertEqual([x.label for x in fields].count("CTA"), 3)
        text = "\n".join(x.value for x in list(app.markdown) + list(app.caption))
        for value in ("PREMIUM SCARCITY — SMART HYBRID", "PRIVATE GALLERY", "THE CAVE"):
            self.assertIn(value, text)
        for stale in ("RIGHT ANGLE", "STRAIGHT ON", "LEFT ANGLE", "Description 1", "0 of 3 copy pairs"):
            self.assertNotIn(stale, text)
        self.assertEqual([x.value for x in fields if x.label == "CTA"], [v[3] for v in copy.ROUTES.values()])
        result = dict(app.session_state[ads.ADS_RESULT_STATE_KEY])
        data = ads.build_instant_experience_copy_csv(result, concept_notes=self.notes())
        uploader_by_label(app, "Import CSV").set_value([("copy.csv", data, "text/csv")])
        app.run(timeout=20)
        self.assertEqual(len(app.exception), 0)
        descriptions = [x.value for x in app.text_area if x.label == "Description"]
        self.assertEqual(descriptions, [rows[0]["primary_text"] for rows in self.notes().values()])
        workflow = app.session_state[ads._ads_image_state_key()]
        exported = ads.build_instant_experience_copy_csv(result, workflow)
        batch = posting.parse_posting_import_csv(exported)
        self.assertEqual([a["primary_text"] for a in batch["ads"]], descriptions)


if __name__ == "__main__":
    unittest.main()
