import csv
import io
from datetime import date, datetime
from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import Image
from streamlit.testing.v1 import AppTest

import ads_creative_refresh
import ads_navigation
import ads_page
import navigation_runtime
import os_accounts
import seo_navigation


ROOT = Path(__file__).resolve().parents[1]


def square_png_bytes():
    output = io.BytesIO()
    Image.new("RGB", (96, 96), (30, 30, 30)).save(output, format="PNG")
    return output.getvalue()


def csv_bytes(rows, headers):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=headers, lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")


def sample_periods():
    return (
        {
            "date_start": "2026-06-01",
            "date_end": "2026-06-07",
            "spend": 100,
            "results": 5,
            "purchase_value": 400,
            "ctr": 2.0,
            "cpc": 1.0,
            "cpm": 10.0,
            "frequency": 2.0,
            "reach": 10000,
            "impressions": 20000,
        },
        {
            "date_start": "2026-07-01",
            "date_end": "2026-07-07",
            "spend": 140,
            "results": 5,
            "purchase_value": 392,
            "ctr": 1.4,
            "cpc": 1.3,
            "cpm": 12.0,
            "frequency": 3.0,
            "reach": 10000,
            "impressions": 30000,
        },
    )


def sample_inputs(campaign_type="Instant Experience"):
    return {
        "product_name": "Purple Reign",
        "product_source_url": "https://cdn.example.com/purple-reign.webp",
        "category": "NBA",
        "country": "USA",
        "campaign_type": campaign_type,
        "product_url": "https://sportscave.com.au/products/purple-reign",
        "campaign_moment": ads_page.empty_campaign_moment(),
        "winning_primary_text": "Remember the night the whole city believed.",
        "winning_meta_headline": "Purple Reign",
        "winning_meta_description": "A limited collector edition.",
        "winning_meta_cta": "Shop Now",
        "winning_emotional_angle": "Nostalgia",
        "winning_emotional_angle_other": "",
        "winning_on_image_headline": "PURPLE REIGN",
        "winning_supporting_line": "",
        "winning_on_image_cta": "CLAIM YOUR EDITION",
        "no_on_image_headline": False,
        "no_supporting_line": True,
        "no_on_image_cta": False,
        "why_it_worked": "Strong nostalgia and immediate product recognition.",
        "recognisable_elements": "Dark premium room and collector hierarchy.",
        "hybrid_mode": False,
        "hybrid_notes": "",
        "original_prompt_text": "Create a premium collector room.",
        "original_prompt_available": True,
        "metrics_csv_available": False,
        "performance_mode": "Manual metrics",
        "refresh_intensity": "Balanced",
        "protected_elements": ads_creative_refresh.PROTECTED_ELEMENTS,
        "elements_to_remain": "Collector tone.",
        "elements_to_change": "Fresh camera and wall treatment.",
        "original_problems": "Product was slightly too small.",
        "environments_to_avoid": "Neon games room.",
        "new_context_opportunity": "Evergreen launch.",
        "audience_context": {
            "audience_type": "Broad",
            "audience_size": "1.2m",
            "age_range": "30-55",
            "gender_targeting": "All",
            "interests": "Basketball",
            "placements": "Feeds",
            "campaign_objective": "Sales",
            "optimisation_event": "Purchase",
            "attribution_setting": "7-day click",
        },
        "winning_creative_signature": "winner-signature",
    }


class CreativeRefreshNavigationTests(unittest.TestCase):
    def test_ads_registry_has_one_top_level_parent_and_one_explicit_child(self):
        self.assertEqual(
            ads_navigation.ADS_ROUTES,
            ("Ads", "Creative Refresh"),
        )
        parent = os_accounts.PAGE_BY_KEY[ads_navigation.ADS_PAGE_KEY]
        child = os_accounts.PAGE_BY_KEY[ads_navigation.CREATIVE_REFRESH_PAGE_KEY]
        top_level_routes = tuple(page["route"] for page in os_accounts.navigation_pages())

        self.assertEqual(parent["route"], ads_navigation.ADS_CREATE_ROUTE)
        self.assertEqual(child["parent_key"], parent["key"])
        self.assertTrue(child["navigation_child"])
        self.assertFalse(child["worker_assignable"])
        self.assertEqual(top_level_routes.count(ads_navigation.ADS_CREATE_ROUTE), 1)
        self.assertNotIn(ads_navigation.CREATIVE_REFRESH_ROUTE, top_level_routes)

    def test_ads_submenu_uses_shared_child_filter_and_never_renders_create_ads(self):
        self.assertEqual(
            navigation_runtime.disclosure_child_routes(
                ads_navigation.ADS_ROUTES,
                ads_navigation.ADS_CREATE_ROUTE,
            ),
            (ads_navigation.CREATIVE_REFRESH_ROUTE,),
        )
        self.assertEqual(
            navigation_runtime.active_disclosure_group(
                "Creative Refresh",
                social_routes=(),
                seo_routes=(),
                ads_routes=ads_navigation.ADS_ROUTES,
            ),
            "ads",
        )

        source = (ROOT / "app.py").read_text(encoding="utf-8")
        ads_start = source.index("    if ads_nav.ADS_CREATE_ROUTE in allowed_routes:")
        seo_start = source.index("    if seo_nav.SEO_OVERVIEW_ROUTE in allowed_routes:", ads_start)
        ads_source = source[ads_start:seo_start]
        self.assertIn("navigation_runtime.disclosure_child_routes(", ads_source)
        self.assertIn("ads_nav.ADS_CREATE_ROUTE,", ads_source)
        self.assertNotIn("for route in ads_nav.ADS_ROUTES:", ads_source)
        self.assertLess(
            source.index('key="sidebar-ads-children"'),
            source.index('key="sidebar-seo-children"'),
        )

    def test_ads_disclosure_uses_shared_toggle_and_submenu_layout_contract(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        disclosure_start = source.index("    def disclosure(")
        disclosure_end = source.index("    def child_button(", disclosure_start)
        disclosure_source = source[disclosure_start:disclosure_end]

        self.assertIn("_toggle_sidebar_group(group)", disclosure_source)
        self.assertEqual(navigation_runtime.toggle_disclosure_group("", "ads"), "ads")
        self.assertEqual(navigation_runtime.toggle_disclosure_group("ads", "ads"), "")
        self.assertEqual(navigation_runtime.toggle_disclosure_group("seo", "ads"), "ads")
        for selector in (
            ".st-key-sidebar-ads-children,",
            '.st-key-sidebar-ads-children div[data-testid="stButton"] button,',
        ):
            self.assertIn(selector, source)
        self.assertIn("max-width: calc(100% - 1.15rem);", source)
        self.assertIn("width: calc(100% - 1.15rem);", source)

    def test_seo_cannot_claim_the_creative_refresh_route(self):
        self.assertNotIn(
            ads_navigation.CREATIVE_REFRESH_ROUTE,
            seo_navigation.SEO_ROUTES,
        )
        self.assertEqual(
            navigation_runtime.active_disclosure_group(
                ads_navigation.CREATIVE_REFRESH_ROUTE,
                social_routes=("Social Media", "AI Reels"),
                seo_routes=seo_navigation.SEO_ROUTES,
                ads_routes=ads_navigation.ADS_ROUTES,
            ),
            "ads",
        )

    def test_creative_refresh_inherits_ads_permission(self):
        worker = {
            "id": "reina",
            "role": os_accounts.ROLE_WORKER,
            "is_active": True,
            "page_permissions": [ads_navigation.ADS_PAGE_KEY],
        }
        denied = {**worker, "page_permissions": []}
        self.assertTrue(os_accounts.can_access_page(worker, "Ads"))
        self.assertTrue(os_accounts.can_access_page(worker, "Creative Refresh"))
        self.assertFalse(os_accounts.can_access_page(denied, "Creative Refresh"))

    def test_creative_refresh_route_loads_directly(self):
        app_test = AppTest.from_file(str(ROOT / "app.py"))
        app_test.session_state["sports_cave_authenticated"] = True
        app_test.query_params["page"] = ads_navigation.CREATIVE_REFRESH_PAGE_KEY
        app_test.session_state["startup_shell_loaded"] = True
        app_test.run(timeout=30)
        self.assertFalse(app_test.exception)
        self.assertEqual([title.value for title in app_test.title], ["Creative Refresh"])
        sidebar_buttons = [(button.label, button.key) for button in app_test.sidebar.button]
        self.assertIn(("Ads", "sidebar-disclosure::ads"), sidebar_buttons)
        self.assertIn(
            ("Creative Refresh", "sidebar-child::Creative Refresh"),
            sidebar_buttons,
        )
        self.assertNotIn(("Create Ads", "sidebar-child::Ads"), sidebar_buttons)
        self.assertEqual(app_test.session_state["sidebar-open-group"], "ads")
        labels = [button.label for button in app_test.button]
        self.assertIn("Generate Creative Refresh Package", labels)

        next(
            button
            for button in app_test.sidebar.button
            if button.key == "sidebar-disclosure::ads"
        ).click()
        app_test.run(timeout=30)
        self.assertFalse(app_test.exception)
        self.assertEqual([title.value for title in app_test.title], ["Ads"])
        self.assertIn(
            "sidebar-child::Creative Refresh",
            {button.key for button in app_test.sidebar.button},
        )

        next(
            button
            for button in app_test.sidebar.button
            if button.key == "sidebar-disclosure::ads"
        ).click()
        app_test.run(timeout=30)
        self.assertFalse(app_test.exception)
        self.assertNotIn(
            "sidebar-child::Creative Refresh",
            {button.key for button in app_test.sidebar.button},
        )

    def test_existing_ads_route_and_renderer_remain_in_place(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        route_source = source[source.index("def render_selected_page"):]
        self.assertIn('elif current_page in {"Ads", "Marketing Factory"}:', route_source)
        self.assertIn("get_ads_page().render_page()", route_source)
        self.assertIn('st.title("Ads")', (ROOT / "ads_page.py").read_text(encoding="utf-8"))
        self.assertEqual(
            os_accounts.PAGE_BY_KEY[ads_navigation.ADS_PAGE_KEY]["key"],
            "ads",
        )
        self.assertEqual(
            os_accounts.PAGE_BY_KEY[ads_navigation.CREATIVE_REFRESH_PAGE_KEY]["key"],
            "ads_creative_refresh",
        )


class CreativeRefreshMetricTests(unittest.TestCase):
    def test_percentage_currency_and_blank_parsing(self):
        self.assertEqual(ads_creative_refresh.parse_metric_number("A$1,234.50"), 1234.5)
        self.assertEqual(
            ads_creative_refresh.parse_metric_number("2.75%", percentage=True),
            2.75,
        )
        self.assertIsNone(ads_creative_refresh.parse_metric_number(""))
        self.assertIsNone(ads_creative_refresh.parse_metric_number("N/A"))

    def test_manual_metrics_derive_without_overwriting_explicit_meta_values(self):
        derived = ads_creative_refresh.derive_period_metrics(
            {
                "spend": "$100",
                "results": "5",
                "purchase_value": "400",
                "cpa": "17.50",
                "link_clicks": "50",
                "reach": "1000",
                "impressions": "2000",
            }
        )
        self.assertEqual(derived["cpa"], 17.5)
        self.assertEqual(derived["roas"], 4.0)
        self.assertEqual(derived["ctr"], 2.5)
        self.assertEqual(derived["cpc"], 2.0)
        self.assertEqual(derived["cpm"], 50.0)
        self.assertEqual(derived["frequency"], 2.0)
        self.assertNotIn("cpa", derived["derived_fields"])

    def test_zero_spend_and_zero_results_are_safe(self):
        derived = ads_creative_refresh.derive_period_metrics(
            {"spend": 0, "results": 0, "purchase_value": 100, "impressions": 0, "reach": 0}
        )
        self.assertIsNone(derived["cpa"])
        self.assertIsNone(derived["roas"])
        self.assertIsNone(derived["cpm"])
        self.assertIsNone(derived["frequency"])
        self.assertIsNone(ads_creative_refresh.percentage_change(0, 10))

    def test_meta_csv_normalises_common_columns_and_derives_metrics(self):
        headers = [
            "Campaign name",
            "Ad set name",
            "Ad name",
            "Reporting starts",
            "Reporting ends",
            "Amount spent (AUD)",
            "Website purchases",
            "Website purchase conversion value",
            "CTR (link click-through rate)",
            "Reach",
            "Impressions",
        ]
        rows = [
            {
                "Campaign name": "Evergreen",
                "Ad set name": "Broad",
                "Ad name": "Winner",
                "Reporting starts": "01/06/2026",
                "Reporting ends": "07/06/2026",
                "Amount spent (AUD)": "$100.00",
                "Website purchases": "5",
                "Website purchase conversion value": "$400",
                "CTR (link click-through rate)": "2.4%",
                "Reach": "10,000",
                "Impressions": "20,000",
            },
            {
                "Campaign name": "Evergreen",
                "Ad set name": "Broad",
                "Ad name": "Winner",
                "Reporting starts": "01/07/2026",
                "Reporting ends": "07/07/2026",
                "Amount spent (AUD)": "$140.00",
                "Website purchases": "5",
                "Website purchase conversion value": "$392",
                "CTR (link click-through rate)": "1.5%",
                "Reach": "10,000",
                "Impressions": "30,000",
            },
        ]
        parsed = ads_creative_refresh.parse_meta_ads_csv(
            csv_bytes(rows, headers),
            filename="meta.csv",
        )
        self.assertEqual(len(parsed["rows"]), 2)
        self.assertTrue(parsed["requires_explicit_selection"])
        self.assertEqual(parsed["column_map"]["spend"], "Amount spent (AUD)")
        self.assertEqual(parsed["rows"][0]["cpa"], 20.0)
        self.assertEqual(parsed["rows"][0]["roas"], 4.0)
        self.assertEqual(parsed["rows"][0]["frequency"], 2.0)
        self.assertEqual(parsed["rows"][0]["ctr"], 2.4)

    def test_meta_csv_ambiguous_rows_require_explicit_distinct_selection(self):
        headers = ["Ad name", "Reporting starts", "Reporting ends", "Amount spent"]
        rows = [
            {"Ad name": "A", "Reporting starts": "2026-06-01", "Reporting ends": "2026-06-07", "Amount spent": "10"},
            {"Ad name": "B", "Reporting starts": "2026-06-01", "Reporting ends": "2026-06-07", "Amount spent": "20"},
            {"Ad name": "C", "Reporting starts": "2026-06-01", "Reporting ends": "2026-06-07", "Amount spent": "30"},
        ]
        parsed = ads_creative_refresh.parse_meta_ads_csv(csv_bytes(rows, headers), filename="meta.csv")
        with self.assertRaisesRegex(ads_creative_refresh.MetaCSVValidationError, "Choose one CSV row"):
            ads_creative_refresh.select_meta_csv_periods(parsed, "", "")
        row_id = parsed["rows"][0]["row_id"]
        with self.assertRaisesRegex(ads_creative_refresh.MetaCSVValidationError, "different CSV rows"):
            ads_creative_refresh.select_meta_csv_periods(parsed, row_id, row_id)

    def test_meta_csv_reports_unmappable_essential_columns(self):
        data = csv_bytes([{"Name": "Winner", "Spend": "10"}], ["Name", "Spend"])
        with self.assertRaisesRegex(ads_creative_refresh.MetaCSVValidationError, "reporting start and end"):
            ads_creative_refresh.parse_meta_ads_csv(data, filename="meta.csv")
        with self.assertRaisesRegex(ads_creative_refresh.MetaCSVValidationError, "CSV file"):
            ads_creative_refresh.parse_meta_ads_csv(data, filename="meta.xlsx")

    def test_likely_fatigue_requires_frequency_and_two_negative_movements(self):
        winning, recent = sample_periods()
        diagnosis = ads_creative_refresh.diagnose_creative_fatigue(winning, recent)
        self.assertEqual(diagnosis["classification"], "Likely Creative Fatigue")
        self.assertTrue(diagnosis["frequency_rise"])
        self.assertGreaterEqual(len(diagnosis["negative_signals"]), 2)

    def test_confounders_reduce_diagnostic_certainty(self):
        winning, recent = sample_periods()
        diagnosis = ads_creative_refresh.diagnose_creative_fatigue(
            winning,
            recent,
            confounders=["Offer changed"],
        )
        self.assertEqual(diagnosis["classification_before_confounders"], "Likely Creative Fatigue")
        self.assertEqual(diagnosis["classification"], "Possible Creative Fatigue")
        self.assertIn("cannot be attributed solely", diagnosis["summary"])

    def test_all_directional_diagnostic_outcomes_are_reachable(self):
        cases = (
            (
                {"frequency": 2.0, "cpa": 20.0, "ctr": 2.0},
                {"frequency": 2.8, "cpa": 25.0, "ctr": 1.9},
                "Possible Creative Fatigue",
            ),
            (
                {"frequency": 2.0, "cpa": 20.0, "ctr": 2.0},
                {"frequency": 2.0, "cpa": 15.0, "ctr": 1.5},
                "Mixed Signals",
            ),
            (
                {"frequency": 2.0, "ctr": 2.0},
                {"frequency": 2.1, "ctr": 2.05},
                "Probably Not Primarily Creative Fatigue",
            ),
        )
        for winning, recent, expected in cases:
            with self.subTest(expected=expected):
                diagnosis = ads_creative_refresh.diagnose_creative_fatigue(winning, recent)
                self.assertEqual(diagnosis["classification"], expected)

    def test_no_metrics_mode_is_usable_and_explicit(self):
        diagnosis = ads_creative_refresh.diagnose_creative_fatigue({}, {})
        self.assertEqual(diagnosis["classification"], "Insufficient Evidence")
        result = ads_creative_refresh.build_creative_refresh_result(
            sample_inputs(),
            diagnosis,
            generated_at=datetime(2026, 8, 17, 10, 0),
        )
        self.assertIn("Insufficient Evidence", result["performance_evidence_summary"])
        self.assertTrue(result["prompt"])


class CreativeRefreshPromptTests(unittest.TestCase):
    def setUp(self):
        winning, recent = sample_periods()
        self.diagnosis = ads_creative_refresh.diagnose_creative_fatigue(winning, recent)

    def test_existing_option_sources_are_reused(self):
        source = (ROOT / "ads_creative_refresh.py").read_text(encoding="utf-8")
        self.assertIn("ads_page.CATEGORY_OPTIONS", source)
        self.assertIn("ads_page.COUNTRY_OPTIONS", source)
        self.assertIn("ads_page.CAMPAIGN_TYPE_OPTIONS", source)
        self.assertIn("ads_page.load_edition_ops_product_rows()", source)
        self.assertNotIn("CATEGORY_OPTIONS = [", source)
        self.assertNotIn("COUNTRY_OPTIONS = [", source)
        self.assertNotIn("CAMPAIGN_TYPE_OPTIONS = [", source)

    def test_required_field_validation_and_intentional_blank_on_image_fields(self):
        inputs = sample_inputs()
        valid = ads_creative_refresh.validate_creative_refresh_inputs(
            inputs,
            winning_creative={"signature": "ok"},
        )
        self.assertEqual(valid, {})
        inputs["no_supporting_line"] = False
        errors = ads_creative_refresh.validate_creative_refresh_inputs(
            inputs,
            winning_creative={"signature": "ok"},
        )
        self.assertIn("winning_ad", errors)
        self.assertTrue(any("supporting line" in message for message in errors["winning_ad"]))

    def test_other_emotional_angle_keeps_valid_state_and_resolves_for_prompt(self):
        inputs = sample_inputs()
        inputs["winning_emotional_angle"] = "Other"
        inputs["winning_emotional_angle_other"] = "Underdog pride"
        errors = ads_creative_refresh.validate_creative_refresh_inputs(
            inputs,
            winning_creative={"signature": "ok"},
        )
        self.assertEqual(errors, {})
        self.assertIn(
            "Winning emotional angle: Underdog pride",
            ads_creative_refresh.build_input_summary(inputs),
        )

    def test_image_validation_accepts_real_images_and_rejects_wrong_files(self):
        item = ads_creative_refresh.validate_winning_creative(
            square_png_bytes(),
            filename="winner.png",
        )
        self.assertEqual(item["format"], "PNG")
        with self.assertRaisesRegex(ads_creative_refresh.CreativeRefreshValidationError, "PNG"):
            ads_creative_refresh.validate_winning_creative(b"text", filename="winner.txt")
        with self.assertRaisesRegex(ads_creative_refresh.CreativeRefreshValidationError, "corrupt"):
            ads_creative_refresh.validate_winning_creative(b"not-an-image", filename="winner.png")

    def test_prompt_requests_exactly_three_materially_distinct_routes(self):
        prompt = ads_creative_refresh.build_creative_refresh_prompt(sample_inputs(), self.diagnosis)
        self.assertEqual(len(ads_creative_refresh.REFRESH_ROUTES), 3)
        self.assertEqual(prompt.count("MANDATORY ROUTE "), 3)
        for route in ("WINNER EVOLUTION", "SCENE EXPANSION", "PATTERN INTERRUPT"):
            self.assertIn(route, prompt)
        self.assertIn("three different camera perspectives", prompt)
        self.assertIn("Do not return three minor colour or wording variations", prompt)
        self.assertIn("do not blindly repeat a left-angle composition", prompt)

    def test_every_route_requires_complete_copy_and_standalone_prompt_fields(self):
        prompt = ads_creative_refresh.build_creative_refresh_prompt(sample_inputs(), self.diagnosis)
        for field in ads_creative_refresh.ROUTE_OUTPUT_FIELDS:
            self.assertIn(f"- {field}.", prompt)
        self.assertIn("Every route's copy and image prompt must be internally matched", prompt)
        self.assertIn('Never write "same as previous prompt"', prompt)

    def test_product_source_and_winner_roles_are_separated(self):
        prompt = ads_creative_refresh.build_creative_refresh_prompt(sample_inputs(), self.diagnosis)
        self.assertIn("Exact Sports Cave product source - immutable product asset", prompt)
        self.assertIn("Original winning ad creative - strategy, composition and style reference only", prompt)
        self.assertIn("must never replace the exact product source", prompt)
        self.assertIn("Do not treat the product visible inside the winning room mockup", prompt)

    def test_instant_experience_uses_square_contract_in_every_route_instruction(self):
        prompt = ads_creative_refresh.build_creative_refresh_prompt(sample_inputs("Instant Experience"), self.diagnosis)
        self.assertIn("Each route must produce one ultra-realistic 1024 × 1024 square Instant Experience cover", prompt)
        self.assertIn("repeat in every route prompt", prompt.casefold())
        self.assertIn("PRODUCT LOCK - INCLUDE IN EVERY RETURNED IMAGE PROMPT", prompt)
        self.assertIn("DYNAMIC ROOM REALISM - INCLUDE IN EVERY RETURNED IMAGE PROMPT", prompt)

    def test_prompt_contains_full_fidelity_and_realism_locks(self):
        prompt = ads_creative_refresh.build_creative_refresh_prompt(sample_inputs(), self.diagnosis)
        for phrase in (
            "Preserve faces, expressions, bodies, uniforms, poses, vehicles, liveries",
            "Never redraw, reconstruct, face-swap, re-pose",
            "Natural contact shadows behind and below the frame",
            "No warped furniture, duplicated objects, malformed architecture",
            "No element may compete with the product",
        ):
            self.assertIn(phrase, prompt)

    def test_prompt_forbids_automatic_images_unsupported_facts_and_guarantees(self):
        prompt = ads_creative_refresh.build_creative_refresh_prompt(sample_inputs(), self.diagnosis)
        self.assertIn(
            '"Do not generate any image automatically. Only generate Refresh Image 1, 2 or 3 after I explicitly request that image."',
            prompt,
        )
        self.assertIn("Do not invent facts, records, dates, teams, athletes, venues", prompt)
        self.assertIn("Do not claim that a refresh will double results, guarantee improvement", prompt)
        self.assertIn("Do not use \"Own the Feeling\"", prompt)

    def test_response_order_is_exact_and_winner_analysis_marks_assumptions(self):
        prompt = ads_creative_refresh.build_creative_refresh_prompt(sample_inputs(), self.diagnosis)
        ordered = [
            "1. Fatigue Evidence Summary.",
            "2. Winner DNA.",
            "3. Lock vs Change Matrix.",
            "4. Refresh 1 — Winner Evolution.",
            "5. Refresh 2 — Scene Expansion.",
            "6. Refresh 3 — Pattern Interrupt.",
            "7. Recommended Test Order.",
            "8. Final Quality Check.",
        ]
        positions = [prompt.index(item) for item in ordered]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("Separate supported observations from assumptions", prompt)


class CreativeRefreshPackageTests(unittest.TestCase):
    def test_state_reset_cannot_touch_create_ads_state(self):
        state = {
            "ads_product_name": "Create Ads product",
            "ads_campaign_type": "Carousel",
            f"{ads_creative_refresh.STATE_PREFIX}product": "Refresh product",
            f"{ads_creative_refresh.STATE_PREFIX}result": {"prompt": "x"},
        }
        ads_creative_refresh.reset_creative_refresh_state(state)
        self.assertEqual(state["ads_product_name"], "Create Ads product")
        self.assertEqual(state["ads_campaign_type"], "Carousel")
        self.assertFalse(any(key.startswith(ads_creative_refresh.STATE_PREFIX) for key in state))

    def test_package_name_and_items_include_supported_assets(self):
        winning, recent = sample_periods()
        diagnosis = ads_creative_refresh.diagnose_creative_fatigue(winning, recent)
        result = ads_creative_refresh.build_creative_refresh_result(
            sample_inputs(),
            diagnosis,
            generated_at=datetime(2026, 8, 17, 10, 0),
        )
        self.assertEqual(result["package_name"], "purple-reign-usa-creative-refresh-2026-08-17")
        items = ads_creative_refresh.build_creative_refresh_package_items(
            result,
            winning_creative={"filename": "winner.webp", "data": b"winner"},
            original_prompt_upload={"filename": "prompt.md", "data": b"prompt"},
            imported_metrics_csv={"filename": "meta.csv", "data": b"csv"},
        )
        names = {item["relative_path"] for item in items}
        self.assertTrue(
            {
                "creative-refresh-prompt.txt",
                "winner-inputs-summary.txt",
                "performance-evidence-summary.txt",
                "winning-creative-reference.webp",
                "original-image-prompt-upload.md",
                "original-image-prompt-pasted.txt",
                "imported-meta-metrics.csv",
                "refresh-strategy-summary.txt",
                "attachment-checklist.txt",
            }.issubset(names)
        )

    @patch("ads_creative_refresh.dropbox_integration.ensure_folder_path")
    @patch("ads_creative_refresh.dropbox_integration.windows_numbered_path")
    @patch("ads_creative_refresh.dropbox_integration.get_metadata_if_exists")
    @patch("ads_creative_refresh.dropbox_integration.upload_batch")
    def test_save_export_reuses_dropbox_collision_and_cancel_contract(
        self,
        upload_batch,
        metadata,
        numbered_path,
        ensure_folder,
    ):
        result = {
            "package_name": "purple-reign-usa-creative-refresh-2026-08-17",
        }
        items = [
            {"relative_path": "creative-refresh-prompt.txt", "data": b"prompt", "size": 6},
            {"relative_path": "winner-inputs-summary.txt", "data": b"inputs", "size": 6},
        ]
        metadata.return_value = {".tag": "folder"}
        numbered_path.return_value = (
            "/Sportscave Team Folder/04_OUTPUT/product-images/"
            "purple-reign-usa-creative-refresh-2026-08-17 (2)"
        )
        upload_batch.return_value = {
            "successes": [{"relative_path": item["relative_path"]} for item in items],
            "failures": [],
        }
        outcome = ads_creative_refresh.save_creative_refresh_package_to_dropbox(
            "token",
            "/Sportscave Team Folder",
            "/Sportscave Team Folder/04_OUTPUT/product-images",
            result,
            items,
        )
        self.assertTrue(outcome["path"].endswith("(2)"))
        ensure_folder.assert_called_once_with(
            "token",
            outcome["path"],
            root_path="/Sportscave Team Folder",
        )
        self.assertEqual(upload_batch.call_args.kwargs["conflict"], "cancel")

    def test_layout_contract_has_compact_mobile_overflow_protection(self):
        source = (ROOT / "ads_creative_refresh.py").read_text(encoding="utf-8")
        self.assertIn("@media (max-width: 720px)", source)
        self.assertIn("min-width: 0", source)
        self.assertIn("overflow-wrap: anywhere", source)
        self.assertIn("with st.container(border=True", source)
        self.assertNotIn("st.tabs(", source)


if __name__ == "__main__":
    unittest.main()
