import importlib
from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest

import ads_page


ROOT = Path(__file__).resolve().parents[1]


def run_ads_page():
    app_test = AppTest.from_file(str(ROOT / "app.py"))
    app_test.session_state["selected_page"] = "Ads"
    app_test.session_state["startup_shell_loaded"] = True
    return app_test.run(timeout=20)


class AdsPageTests(unittest.TestCase):
    def test_visible_title_and_navigation_are_ads_only(self):
        app_test = run_ads_page()

        self.assertEqual([title.value for title in app_test.title], ["Ads"])
        self.assertIn("Ads", [button.label for button in app_test.button])
        self.assertNotIn("Marketing Factory", [title.value for title in app_test.title])
        self.assertNotIn("Marketing Factory", [button.label for button in app_test.button])
        self.assertEqual(len(app_test.exception), 0)

    def test_dropdown_options_are_in_required_order(self):
        self.assertEqual(
            ads_page.CATEGORY_OPTIONS,
            [
                "Select category",
                "NBA",
                "Motorsport",
                "Football",
                "Cricket",
                "Horse Racing",
                "Baseball",
                "Combat",
                "Ice Hockey",
                "NFL",
                "Tennis",
            ],
        )
        self.assertEqual(
            ads_page.COUNTRY_OPTIONS,
            ["Select country", "Australia", "USA", "UK", "Canada", "New Zealand"],
        )
        self.assertEqual(
            ads_page.CAMPAIGN_TYPE_OPTIONS,
            ["Select campaign type", "Carousel", "Instant Experience", "Single Image / Video"],
        )

    def test_blank_or_incomplete_inputs_are_rejected_with_one_message(self):
        message = ads_page.validate_ads_inputs("", "Motorsport", "Australia", "Carousel")
        self.assertEqual(message, "Enter a product name and choose a category, country and campaign type.")

        message = ads_page.validate_ads_inputs("Six Laps Ahead", "Select category", "Australia", "Carousel")
        self.assertEqual(message, "Enter a product name and choose a category, country and campaign type.")

    def test_motorsport_carousel_is_supported_for_every_country(self):
        for country in ads_page.COUNTRY_OPTIONS[1:]:
            with self.subTest(country=country):
                prompt = ads_page.build_ads_prompt("Six Laps Ahead", "Motorsport", country, "Carousel")
                self.assertIn("SPORTS CAVE MOTORSPORT CAROUSEL AD", prompt)
                self.assertIn(f"Market: {country}", prompt)
                self.assertIn("Create exactly five cards.", prompt)
                self.assertIn("Create exactly five genuinely different Meta primary-text variations.", prompt)

    def test_unsupported_combinations_have_no_generic_template(self):
        self.assertIsNone(ads_page.get_template_key("Motorsport", "Instant Experience"))
        self.assertIsNone(ads_page.get_template_key("Motorsport", "Single Image / Video"))
        self.assertIsNone(ads_page.get_template_key("NBA", "Carousel"))
        self.assertEqual(ads_page.build_ads_prompt("Test Product", "NBA", "Australia", "Carousel"), "")

    def test_generated_prompt_contains_required_dynamic_and_rule_text(self):
        prompt = ads_page.build_ads_prompt("Six Laps Ahead", "Motorsport", "UK", "Carousel")

        self.assertIn("Product name: Six Laps Ahead", prompt)
        self.assertIn("Category: Motorsport", prompt)
        self.assertIn("Market: UK", prompt)
        self.assertIn("Campaign type: Carousel", prompt)
        self.assertIn("Maximum 17 characters including spaces.", prompt)
        self.assertIn("Every carousel headline is 17 characters or fewer including spaces.", prompt)
        self.assertIn("Every carousel description is 17 characters or fewer including spaces.", prompt)
        self.assertNotIn("Maximum 32 characters including spaces.", prompt)
        self.assertNotIn("Maximum 24 characters including spaces.", prompt)
        self.assertIn("Use the supplied product name as the source of identity.", prompt)
        self.assertIn("Do not invent race results", prompt)

    def test_carousel_card_rules_prohibit_commas_and_full_stops(self):
        prompt = ads_page.build_ads_prompt("Six Laps Ahead", "Motorsport", "UK", "Carousel")

        headline_section = prompt[prompt.index("Headline rules:") : prompt.index("Description rules:")]
        description_section = prompt[prompt.index("Description rules:") : prompt.index("Use this strategic role")]

        self.assertIn("Do not use commas.", headline_section)
        self.assertIn("Do not use full stops.", headline_section)
        self.assertIn("Do not use commas.", description_section)
        self.assertIn("Do not use full stops.", description_section)
        self.assertIn("No carousel headline contains a comma.", prompt)
        self.assertIn("No carousel headline contains a full stop.", prompt)
        self.assertIn("No carousel description contains a comma.", prompt)
        self.assertIn("No carousel description contains a full stop.", prompt)
        self.assertIn(
            "Before answering count every headline and description including spaces. "
            "Rewrite any carousel field that exceeds 17 characters or contains a comma or full stop.",
            prompt,
        )

    def test_carousel_card_rules_are_shared_for_carousel_templates(self):
        source = (ROOT / "ads_page.py").read_text(encoding="utf-8")

        self.assertEqual(ads_page.CAROUSEL_CARD_MAX_CHARACTERS, 17)
        self.assertIn("def build_carousel_card_copy_rules", source)
        self.assertIn("def build_carousel_final_quality_check", source)
        self.assertIn("def apply_campaign_copy_rule_blocks", source)
        self.assertIn('campaign_type != "Carousel"', source)
        self.assertIn("carousel_card_copy_rules = build_carousel_card_copy_rules()", source)
        self.assertIn(
            "carousel_final_quality_check = build_carousel_final_quality_check(include_primary_text_variations=True)",
            source,
        )
        self.assertIn("return apply_campaign_copy_rule_blocks(", source)

    def test_primary_text_rules_are_not_restricted_to_17_characters(self):
        prompt = ads_page.build_ads_prompt("Six Laps Ahead", "Motorsport", "UK", "Carousel")
        primary_text_section = prompt[prompt.index("PRIMARY TEXT") : prompt.index("VERIFIED PRODUCT POSITIONING")]

        self.assertIn("Approximately 25 to 45 words.", primary_text_section)
        self.assertIn("Approximately 60 to 100 words.", primary_text_section)
        self.assertIn("Approximately 70 to 110 words.", primary_text_section)
        self.assertIn("Approximately 80 to 120 words.", primary_text_section)
        self.assertNotIn("17 characters", primary_text_section)

    def test_submit_supported_result_renders_three_compact_sections(self):
        app_test = run_ads_page()
        app_test.text_input[0].set_value("Six Laps Ahead")
        app_test.selectbox[0].select("Motorsport")
        app_test.selectbox[1].select("Canada")
        app_test.selectbox[2].select("Carousel")
        app_test.button[0].click().run(timeout=20)

        self.assertEqual(
            [subheader.value for subheader in app_test.subheader],
            ["1. Upload these five images", "2. Copy this ChatGPT prompt", "3. Build it in Meta"],
        )
        self.assertEqual(len(app_test.code), 1)
        self.assertIn("Product name: Six Laps Ahead", app_test.code[0].value)
        self.assertIn("Market: Canada", app_test.code[0].value)
        self.assertEqual(len(app_test.exception), 0)

    def test_submit_unsupported_result_renders_insufficient_winner_data(self):
        app_test = run_ads_page()
        app_test.text_input[0].set_value("Six Laps Ahead")
        app_test.selectbox[0].select("Motorsport")
        app_test.selectbox[1].select("Australia")
        app_test.selectbox[2].select("Instant Experience")
        app_test.button[0].click().run(timeout=20)

        self.assertIn("Insufficient winner data", [subheader.value for subheader in app_test.subheader])
        self.assertTrue(
            any(
                caption.value == "Approved winner examples have not been added for this category and campaign type yet."
                for caption in app_test.caption
            )
        )
        self.assertEqual(len(app_test.code), 0)
        self.assertEqual(len(app_test.exception), 0)

    def test_ads_page_source_has_no_external_backend_execution_path(self):
        source = (ROOT / "ads_page.py").read_text(encoding="utf-8")

        for blocked in ("supabase", "shopify", "meta_ads_client", "openai", "requests", "analytics"):
            self.assertNotIn(blocked, source.casefold())
        self.assertNotIn("st.tabs", source)
        self.assertNotIn("st.metric", source)
        self.assertNotIn("saved packs", source.casefold())
        self.assertNotIn("dashboard", source.casefold())

    def test_app_route_uses_lightweight_ads_module_and_preserves_compatibility(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        route_source = source[source.index("def render_selected_page") : source.index("def main")]

        self.assertIn('"Ads"', source)
        self.assertIn('elif current_page in {"Ads", "Marketing Factory"}:', route_source)
        self.assertIn("get_ads_page().render_page()", route_source)
        self.assertNotIn('elif current_page == "Marketing Factory":', route_source)
        self.assertNotIn("importlib.import_module(\"marketing_factory_page\")", source)

    def test_existing_unrelated_route_modules_still_import_successfully(self):
        for module_name in ("image_factory", "orders_page", "edition_ops", "social_media_reels_studio_page"):
            with self.subTest(module_name=module_name):
                self.assertIsNotNone(importlib.import_module(module_name))


if __name__ == "__main__":
    unittest.main()
