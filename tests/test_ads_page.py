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
        self.assertIn("Target 8 to 12 characters including spaces.", prompt)
        self.assertIn("Have a hard maximum of 13 characters including spaces.", prompt)
        self.assertIn("Every headline is 13 characters or fewer including spaces.", prompt)
        self.assertIn("Every description is 13 characters or fewer including spaces.", prompt)
        self.assertNotIn("17 characters", prompt)
        self.assertNotIn("Maximum 32 characters including spaces.", prompt)
        self.assertNotIn("Maximum 24 characters including spaces.", prompt)
        self.assertIn("Use the supplied product name as the source of identity.", prompt)
        self.assertIn("Do not invent race results", prompt)
        self.assertIn("PRODUCT SPECIFICITY TEST", prompt)
        self.assertIn("At least four of the five card pairs must include a product-specific anchor", prompt)
        self.assertIn("Silently create multiple candidate options for each card.", prompt)
        self.assertIn("could this card be copied unchanged onto an unrelated sports artwork?", prompt)

    def test_carousel_card_rules_prohibit_commas_and_full_stops(self):
        prompt = ads_page.build_ads_prompt("Six Laps Ahead", "Motorsport", "UK", "Carousel")

        mobile_section = prompt[
            prompt.index("CAROUSEL MOBILE-SAFE LENGTH RULES") : prompt.index("Use this strategic role")
        ]

        self.assertIn("Never contain a comma or full stop.", mobile_section)
        self.assertIn("No commas.", prompt)
        self.assertIn("No full stops.", prompt)
        self.assertIn("No duplicate carousel headlines.", prompt)
        self.assertIn("No duplicate carousel descriptions.", prompt)
        self.assertIn(
            "Before returning the result count every carousel headline and description including spaces. "
            "Reject and rewrite every field above 13 characters",
            prompt,
        )

    def test_carousel_card_rules_are_shared_for_carousel_templates(self):
        source = (ROOT / "ads_page.py").read_text(encoding="utf-8")

        self.assertEqual(ads_page.CAROUSEL_CARD_MAX_CHARACTERS, 17)
        self.assertIn("def build_carousel_card_copy_rules", source)
        self.assertIn("def build_carousel_story_and_specificity_rules", source)
        self.assertIn("def build_carousel_final_quality_check", source)
        self.assertIn("def apply_campaign_copy_rule_blocks", source)
        self.assertIn('campaign_type != "Carousel"', source)
        self.assertIn("carousel_card_copy_rules = build_carousel_card_copy_rules()", source)
        self.assertIn("category=category", source)
        self.assertIn(
            "carousel_final_quality_check = build_carousel_final_quality_check(include_primary_text_variations=True)",
            source,
        )
        self.assertIn("return apply_campaign_copy_rule_blocks(", source)

    def test_primary_text_rules_use_stronger_australian_motorsport_block(self):
        prompt = ads_page.build_ads_prompt("Six Laps Ahead", "Motorsport", "UK", "Carousel")
        primary_text_section = prompt[prompt.index("PRIMARY TEXT") : prompt.index("VERIFIED PRODUCT POSITIONING")]

        self.assertIn("Approximately 25 to 45 words.", primary_text_section)
        self.assertIn("Approximately 60 to 95 words.", primary_text_section)
        self.assertIn("Approximately 70 to 105 words.", primary_text_section)
        self.assertIn("Approximately 70 to 110 words.", primary_text_section)
        self.assertIn("CORE AUSTRALIAN MOTORSPORT EMOTION", primary_text_section)
        self.assertIn("The first sentence or fragment of every variation must immediately use a product-specific memory anchor.", primary_text_section)
        self.assertIn("All five primary-text variations must include the real scarcity naturally.", primary_text_section)
        self.assertIn("FINAL PRIMARY-TEXT QUALITY CHECK", primary_text_section)
        self.assertNotIn("Approximately 60 to 100 words.", primary_text_section)
        self.assertNotIn("PRIMARY-TEXT RULES", primary_text_section)

    def test_motorsport_prompt_pushes_product_specific_connected_cards(self):
        prompt = ads_page.build_ads_prompt("Peter Brock Six Laps Ahead", "Motorsport", "Australia", "Carousel")

        self.assertIn("Product name: Peter Brock Six Laps Ahead", prompt)
        self.assertIn("Card 1 Hero Identity", prompt)
        self.assertIn("Card 2 Memory Anchor", prompt)
        self.assertIn("Card 3 Collector Meaning", prompt)
        self.assertIn("Card 4 Ownership", prompt)
        self.assertIn("Card 5 Real Scarcity", prompt)
        self.assertIn("favour language drawn from circuit, machine, rivalry", prompt)
        self.assertIn("Do not hardcode examples or famous names from another product.", prompt)
        self.assertIn("Peter Brock", prompt)

    def test_non_motorsport_category_uses_same_story_framework(self):
        cricket_rules = ads_page.build_carousel_story_and_specificity_rules("Cricket")

        self.assertIn("Card 1 Hero Identity", cricket_rules)
        self.assertIn("Card 5 Real Scarcity", cricket_rules)
        self.assertIn("crease, spell, innings, summer, Ashes", cricket_rules)
        self.assertIn("could this card be copied unchanged onto an unrelated sports artwork?", cricket_rules)

    def test_carousel_validator_accepts_exact_five_product_specific_cards(self):
        cards = [
            {"headline": "Peter Brock", "description": "Six Laps Ahead"},
            {"headline": "Bathurst 1979", "description": "Mountain Roar"},
            {"headline": "Era Framed", "description": "Brock Memory"},
            {"headline": "Own The Era", "description": "Collector Wall"},
            {"headline": "Only 100 Exist", "description": "No Second Run"},
        ]

        self.assertEqual(ads_page.validate_carousel_cards(cards, edition_info_supplied=True), [])

    def test_carousel_validator_rejects_bad_card_structure_and_fields(self):
        cards = [
            {"headline": "History Framed", "description": "Those Who Know"},
            {"headline": "Too Long For Meta Cards", "description": "Valid"},
            {"headline": "Comma, Bad", "description": "Full. Stop"},
            {"headline": "Repeat", "description": "Repeat"},
            {"headline": "Repeat", "description": "Repeat"},
        ]

        errors = ads_page.validate_carousel_cards(cards, edition_info_supplied=True)

        self.assertTrue(any("banned generic filler" in error for error in errors))
        self.assertTrue(any("exceeds 17 characters" in error for error in errors))
        self.assertTrue(any("contains a comma" in error for error in errors))
        self.assertTrue(any("contains a full stop" in error for error in errors))
        self.assertTrue(any("duplicates another headline" in error for error in errors))
        self.assertTrue(any("duplicates another description" in error for error in errors))

    def test_carousel_validator_rejects_missing_cards_and_blank_fields(self):
        errors = ads_page.validate_carousel_cards(
            [{"headline": "", "description": "Six Laps"}],
            edition_info_supplied=True,
        )

        self.assertEqual(errors, ["Carousel output must contain exactly 5 cards."])

        blank_errors = ads_page.validate_carousel_cards(
            [
                {"headline": "Brock", "description": "Six Laps"},
                {"headline": "", "description": "Mountain"},
                {"headline": "Era", "description": "Memory"},
                {"headline": "Wall", "description": "Garage"},
                {"headline": "Only 100", "description": "No Run"},
            ],
            edition_info_supplied=True,
        )
        self.assertIn("Card 2 headline is blank.", blank_errors)

    def test_carousel_validator_rejects_scarcity_without_supplied_edition_info(self):
        cards = [
            {"headline": "Peter Brock", "description": "Six Laps"},
            {"headline": "Bathurst", "description": "The Mountain"},
            {"headline": "Era Framed", "description": "Brock Memory"},
            {"headline": "Own The Era", "description": "Garage Wall"},
            {"headline": "Only 100 Exist", "description": "No Second Run"},
        ]

        errors = ads_page.validate_carousel_cards(cards, edition_info_supplied=False)
        self.assertIn("Card 5 uses scarcity without supplied edition information.", errors)
        self.assertEqual(ads_page.validate_carousel_cards(cards, edition_info_supplied=True), [])

    def test_repair_instruction_rewrites_invalid_fields_without_truncation(self):
        errors = ["Card 1 headline exceeds 17 characters.", "Card 2 description contains a comma."]

        instruction = ads_page.build_carousel_repair_instruction(errors)

        self.assertIn("Rewrite only the invalid carousel-card fields", instruction)
        self.assertIn("Do not silently truncate text.", instruction)
        self.assertIn("- Card 1 headline exceeds 17 characters.", instruction)

    def test_parse_carousel_cards_extracts_exact_output_shape(self):
        output = """CAROUSEL CARDS

Card 1
Headline: Peter Brock
Description: Six Laps Ahead

Card 2
Headline: Bathurst 1979
Description: Mountain Roar

Card 3
Headline: Era Framed
Description: Brock Memory

Card 4
Headline: Own The Era
Description: Collector Wall

Card 5
Headline: Only 100 Exist
Description: No Second Run

PRIMARY TEXT VARIATIONS
"""

        cards = ads_page.parse_carousel_cards(output)

        self.assertEqual(len(cards), 5)
        self.assertEqual(cards[0]["headline"], "Peter Brock")
        self.assertEqual(cards[-1]["description"], "No Second Run")

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
