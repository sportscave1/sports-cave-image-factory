import importlib
import json
from pathlib import Path
import tempfile
import unittest

from streamlit.testing.v1 import AppTest

import ads_page


ROOT = Path(__file__).resolve().parents[1]


def run_ads_page():
    app_test = AppTest.from_file(str(ROOT / "app.py"))
    app_test.session_state["selected_page"] = "Ads"
    app_test.session_state["startup_shell_loaded"] = True
    return app_test.run(timeout=20)


def set_product_name(app_test, value):
    for text_input in app_test.text_input:
        if text_input.label == "Product name":
            text_input.set_value(value)
            return
    for selectbox in app_test.selectbox:
        if selectbox.label == "Product name":
            if getattr(selectbox, "options", None) and value not in selectbox.options:
                selectbox.select(selectbox.options[0])
            elif value in getattr(selectbox, "options", ()):
                selectbox.select(value)
            else:
                selectbox.set_value(value)
            return
    raise AssertionError("Product name widget was not rendered.")


def select_option(app_test, label, value):
    for selectbox in app_test.selectbox:
        if selectbox.label == label:
            selectbox.select(value)
            return
    raise AssertionError(f"{label} selectbox was not rendered.")


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

    def test_category_specific_templates_cover_carousel_and_instant_experience_with_generic_fallback(self):
        for category in ads_page.SUPPORTED_AD_CATEGORIES:
            with self.subTest(category=category, campaign_type="Carousel"):
                self.assertIsNotNone(ads_page.get_template_key(category, "Carousel"))
                self.assertIsNotNone(ads_page.get_winner_pattern_key(category, "Carousel"))
            with self.subTest(category=category, campaign_type="Instant Experience"):
                self.assertIsNotNone(ads_page.get_template_key(category, "Instant Experience"))
                self.assertIsNotNone(ads_page.get_winner_pattern_key(category, "Instant Experience"))

        self.assertEqual(ads_page.get_template_key("Motorsport", "Carousel"), "motorsport_carousel")
        self.assertEqual(ads_page.get_template_key("Baseball", "Instant Experience"), "baseball_instant_experience")
        self.assertIsNone(ads_page.get_template_key("Rugby League", "Carousel"))
        self.assertEqual(ads_page.get_winner_pattern_key("Rugby League", "Carousel"), "generic_carousel")
        self.assertIn(
            "SPORTS CAVE GENERIC CAROUSEL WINNER PATTERN",
            ads_page.build_ads_prompt("Test Product", "Rugby League", "Australia", "Carousel"),
        )

    def test_baseball_instant_experience_is_supported_with_required_url(self):
        self.assertEqual(
            ads_page.get_template_key("Baseball", "Instant Experience"),
            "baseball_instant_experience",
        )
        self.assertEqual(
            ads_page.validate_ads_inputs(
                "Shohei Ohtani 50/50",
                "Baseball",
                "USA",
                "Instant Experience",
                product_url="",
            ),
            "",
        )
        self.assertEqual(
            ads_page.validate_ads_inputs(
                "Shohei Ohtani 50/50",
                "Baseball",
                "USA",
                "Instant Experience",
                product_url="https://sportscave.com.au/products/ohtani-50-50",
            ),
            "",
        )

    def test_generated_prompt_contains_required_dynamic_and_rule_text(self):
        prompt = ads_page.build_ads_prompt("Six Laps Ahead", "Motorsport", "UK", "Carousel")

        self.assertIn("Product name: Six Laps Ahead", prompt)
        self.assertIn("Category: Motorsport", prompt)
        self.assertIn("Market: UK", prompt)
        self.assertIn("Campaign type: Carousel", prompt)
        self.assertIn("Maximum 17 characters including spaces and punctuation.", prompt)
        self.assertIn("Every headline is 17 characters or fewer including spaces and punctuation.", prompt)
        self.assertIn("Every description is 17 characters or fewer including spaces and punctuation.", prompt)
        self.assertNotIn("13 characters", prompt)
        self.assertNotIn("Maximum 32 characters including spaces.", prompt)
        self.assertNotIn("Maximum 24 characters including spaces.", prompt)
        self.assertIn("Use the supplied product name as the source of identity.", prompt)
        self.assertIn("Do not invent race results", prompt)
        self.assertIn("PRODUCT SPECIFICITY TEST", prompt)
        self.assertIn("At least four of the five card pairs must include a product-specific anchor", prompt)
        self.assertIn("Silently create several possible headline and description options", prompt)
        self.assertIn("could this card be copied unchanged onto an unrelated sports artwork?", prompt)

    def test_carousel_card_rules_prohibit_commas_and_full_stops(self):
        prompt = ads_page.build_ads_prompt("Six Laps Ahead", "Motorsport", "UK", "Carousel")

        mobile_section = prompt[
            prompt.index("CAROUSEL CARD CHARACTER LIMIT") : prompt.index("PRIMARY TEXT VARIATIONS")
        ]

        self.assertIn("Never contain a comma or full stop.", mobile_section)
        self.assertIn("Every headline is 17 characters or fewer including spaces and punctuation.", prompt)
        self.assertIn("Every description is 17 characters or fewer including spaces and punctuation.", prompt)
        self.assertIn("No duplicate headlines.", prompt)
        self.assertIn("No duplicate descriptions.", prompt)
        self.assertIn(
            "If any carousel field exceeds 17 characters, rewrite it before answering.",
            prompt,
        )

    def test_carousel_card_rules_are_shared_for_carousel_templates(self):
        source = (ROOT / "ads_page.py").read_text(encoding="utf-8")

        self.assertEqual(ads_page.CAROUSEL_CARD_MAX_CHARACTERS, 17)
        self.assertIn("def build_carousel_card_copy_rules", source)
        self.assertIn("def build_carousel_story_and_specificity_rules", source)
        self.assertIn("def build_carousel_final_quality_check", source)
        self.assertIn("def compose_final_ads_prompt", source)
        self.assertIn("def apply_campaign_copy_rule_blocks", source)
        self.assertIn('campaign_type != "Carousel"', source)
        self.assertIn("carousel_card_copy_rules = build_carousel_card_copy_rules()", source)
        self.assertIn("category=category", source)
        self.assertIn(
            "carousel_final_quality_check = build_carousel_final_quality_check(include_primary_text_variations=True)",
            source,
        )
        self.assertIn("return compose_final_ads_prompt(", source)

    def test_primary_text_rules_use_stronger_australian_motorsport_block(self):
        prompt = ads_page.build_ads_prompt("Six Laps Ahead", "Motorsport", "UK", "Carousel")
        primary_text_section = prompt[prompt.index("PRIMARY TEXT") : prompt.index("VERIFIED PRODUCT POSITIONING")]

        self.assertIn("Approximately 25 to 45 words.", primary_text_section)
        self.assertIn("Approximately 60 to 100 words.", primary_text_section)
        self.assertIn("Approximately 70 to 105 words.", primary_text_section)
        self.assertIn("Approximately 80 to 120 words.", primary_text_section)
        self.assertIn("CORE AUSTRALIAN MOTORSPORT EMOTION", primary_text_section)
        self.assertIn("PRIMARY-TEXT FORMATTING", primary_text_section)
        self.assertIn("The first sentence or fragment of every variation must immediately use a product-specific memory anchor.", primary_text_section)
        self.assertIn("All five primary-text variations must include the real scarcity naturally.", primary_text_section)
        self.assertIn("Insert a blank line between the hook, story, product value and scarcity close.", primary_text_section)
        self.assertIn("Do not produce a single uninterrupted wall of text.", primary_text_section)
        self.assertIn("Preserve the line breaks when copied from Sports Cave OS.", primary_text_section)
        self.assertIn("BULLET FORMATTING", primary_text_section)
        self.assertIn("FINAL PRIMARY-TEXT QUALITY CHECK", primary_text_section)
        self.assertNotIn("PRIMARY-TEXT RULES", primary_text_section)

    def test_baseball_instant_experience_prompt_outputs_one_best_package(self):
        prompt = ads_page.build_ads_prompt(
            "Shohei Ohtani 50/50 Season",
            "Baseball",
            "USA",
            "Instant Experience",
            product_url="https://sportscave.com.au/products/ohtani-50-50",
        )

        self.assertIn("SPORTS CAVE BASEBALL INSTANT EXPERIENCE AD", prompt)
        self.assertIn("Product name: Shohei Ohtani 50/50 Season", prompt)
        self.assertIn("Product page URL: https://sportscave.com.au/products/ohtani-50-50", prompt)
        self.assertIn("Generate exactly:", prompt)
        self.assertIn("- one best primary text", prompt)
        self.assertIn("- one best headline", prompt)
        self.assertIn("- one CTA", prompt)
        self.assertIn("Return one final primary text only.", prompt)
        self.assertIn("Generate exactly one headline.", prompt)
        self.assertIn("CALL TO ACTION\n\nClaim Your Edition", prompt)
        self.assertIn("PRIMARY TEXT\n\n[one complete primary-text ad]", prompt)
        self.assertIn("HEADLINE\n\n[one strongest headline]", prompt)
        self.assertIn("INSTANT EXPERIENCE SETUP\n\n[the required setup instructions]", prompt)
        self.assertNotIn("Create exactly five genuinely different Meta primary-text variations.", prompt)
        self.assertNotIn("CAROUSEL CARDS\n\nCard 1", prompt)
        self.assertNotIn("CAROUSEL CARD CHARACTER LIMIT", prompt)
        self.assertNotIn("13 characters", prompt)
        self.assertIn("META URL PARAMETERS", prompt)
        self.assertIn(ads_page.META_AD_URL_PARAMETERS, prompt)

    def test_baseball_instant_experience_uses_brand_opening_identity_and_ownership_rules(self):
        prompt = ads_page.build_ads_prompt(
            "Ohtani Judge The Titans",
            "Baseball",
            "Australia",
            "Instant Experience",
            product_url="https://sportscave.com.au/products/the-titans",
        )

        self.assertIn("Greatness doesn’t fade. It gets framed.", prompt)
        self.assertIn("genuine baseball-fan identity", prompt)
        self.assertIn("That belongs on my wall.", prompt)
        self.assertIn("This is not for casual fans", prompt)
        self.assertIn("If this copy could work for almost any baseball artwork", prompt)
        self.assertIn("rewrite it with stronger product-specific identity", prompt)
        self.assertIn("ownership-triggering", prompt)
        self.assertIn("the silence before the swing", prompt)
        self.assertIn("pressure at the plate", prompt)
        self.assertIn("the crack of the bat", prompt)
        self.assertIn("Authentic baseball terms must remain baseball-specific in every country", prompt)

    def test_baseball_instant_experience_approved_claims_are_injected_through_claim_helper(self):
        prompt = ads_page.build_ads_prompt(
            "Shohei Ohtani 50/50 Season",
            "Baseball",
            "USA",
            "Instant Experience",
            product_url="https://sportscave.com.au/products/ohtani-50-50",
        )
        source = (ROOT / "ads_page.py").read_text(encoding="utf-8")

        self.assertIn("def build_baseball_instant_experience_claim_block", source)
        self.assertIn("BASEBALL_INSTANT_EXPERIENCE_APPROVED_CLAIMS", source)
        self.assertIn("✔ Only 100 editions.", prompt)
        self.assertIn("✔ Numbered C.O.A. included.", prompt)
        self.assertIn("✔ Made in the USA.", prompt)
        self.assertIn("✔ Rated 4.9 / 5 by thousands of collectors.", prompt)
        self.assertIn("These claim lines are supplied through the approved Baseball Instant Experience claim path.", prompt)
        self.assertIn("Do not replace Made in the USA with another manufacturing country", prompt)
        self.assertIn("Do not invent statistics, dates, records", prompt)
        self.assertIn("Strictly limited. Claim your number before the next one is gone.", prompt)

    def test_baseball_instant_experience_setup_uses_required_meta_instructions(self):
        prompt = ads_page.build_ads_prompt(
            "The Summer of 98",
            "Baseball",
            "UK",
            "Instant Experience",
            product_url="https://sportscave.com.au/products/summer-98",
        )

        self.assertIn("06 - Instant Experience Cover Banner (Social)", prompt)
        self.assertIn("Select the connected Shopify Product Catalog.", prompt)
        self.assertIn("Baseball Wall Art", prompt)
        self.assertIn("Use the actual connected Baseball product-set name if stored in the app.", prompt)
        self.assertIn("Upload the Instant Experience Cover Banner from the Mockups ZIP as the cover image.", prompt)
        self.assertIn("Automatically group into relevant sections turned OFF", prompt)
        self.assertIn("Under Product headline, use:\n   product.name", prompt)
        self.assertIn("Under Product description, use:\n   Limited Edition", prompt)
        self.assertIn("Under Fixed button, set the label to:\n    Claim Your Edition", prompt)
        self.assertIn("Under URL parameters, use:\n    " + ads_page.META_AD_URL_PARAMETERS, prompt)
        self.assertIn("https://sportscave.com.au/products/summer-98", prompt)
        self.assertIn("Do not invent the destination URL.", prompt)

    def test_shared_meta_url_parameters_are_added_to_every_supported_ads_prompt(self):
        motorsport_prompt = ads_page.build_ads_prompt(
            "Six Laps Ahead",
            "Motorsport",
            "Australia",
            "Carousel",
        )
        baseball_prompt = ads_page.build_ads_prompt(
            "Shohei Ohtani 50/50 Season",
            "Baseball",
            "USA",
            "Instant Experience",
            product_url="https://sportscave.com.au/products/ohtani-50-50",
        )

        self.assertIn("def build_meta_url_parameters_guidance", (ROOT / "ads_page.py").read_text(encoding="utf-8"))
        self.assertIn("META URL PARAMETERS", motorsport_prompt)
        self.assertIn("META URL PARAMETERS", baseball_prompt)
        self.assertIn(ads_page.META_AD_URL_PARAMETERS, motorsport_prompt)
        self.assertIn(ads_page.META_AD_URL_PARAMETERS, baseball_prompt)
        self.assertEqual(
            ads_page.META_AD_URL_PARAMETERS,
            "utm_source=facebook&utm_medium=paid_social&utm_campaign={{campaign.name}}&utm_content={{ad.name}}&utm_term={{adset.name}}&placement={{placement}}",
        )

    def test_football_instant_experience_works_for_every_supported_country(self):
        expected_terms = {
            "Australia": "football or soccer depending on the product context",
            "UK": "use football, supporters, wall, home bar, collection",
            "USA": "use soccer, fans, collector wall art, sports room",
            "Canada": "use football or soccer depending on the product context",
            "New Zealand": "use football or soccer depending on the product context",
        }

        for country in ads_page.COUNTRY_OPTIONS[1:]:
            with self.subTest(country=country):
                prompt = ads_page.build_ads_prompt(
                    "Messi World Cup Night",
                    "Football",
                    country,
                    "Instant Experience",
                )
                self.assertIn("SPORTS CAVE FOOTBALL INSTANT EXPERIENCE WINNER PATTERN", prompt)
                self.assertIn(f"Market: {country}", prompt)
                self.assertIn(expected_terms[country], prompt)
                self.assertIn("PRIMARY TEXT", prompt)
                self.assertIn("Variant 5:", prompt)
                self.assertIn("HEADLINE", prompt)
                self.assertIn("DESCRIPTION", prompt)
                self.assertIn("INSTANT EXPERIENCE COVER PROMPT", prompt)
                self.assertIn("LIMITED TO 100 WORLDWIDE", prompt)
                self.assertIn("Once it sells out, it's gone.", prompt)
                self.assertIn("Claim Your Edition", prompt)
                self.assertIn("top 60-68%", prompt)
                self.assertIn("bottom 32-40%", prompt)
                self.assertIn("META URL PARAMETERS", prompt)
                self.assertIn(ads_page.META_AD_URL_PARAMETERS, prompt)
                self.assertNotEqual(prompt, "")

    def test_every_category_returns_carousel_output_for_every_supported_country(self):
        required_roles = [
            "Product Identity",
            "Moment / Legacy",
            "Emotional Hook",
            "Fan Ownership",
            "Scarcity",
        ]

        for category in ads_page.SUPPORTED_AD_CATEGORIES:
            for country in ads_page.COUNTRY_OPTIONS[1:]:
                with self.subTest(category=category, country=country):
                    prompt = ads_page.build_ads_prompt(
                        f"{category} Collector Moment",
                        category,
                        country,
                        "Carousel",
                    )
                    self.assertNotEqual(prompt, "")
                    self.assertNotIn("Insufficient winner data", prompt)
                    self.assertIn(f"Market: {country}", prompt)
                    self.assertIn("CAROUSEL CARDS", prompt)
                    self.assertIn("PRIMARY TEXT", prompt)
                    self.assertIn("CTA GUIDANCE", prompt)
                    self.assertIn("Claim Your Edition", prompt)
                    self.assertIn("META URL PARAMETERS", prompt)
                    self.assertIn(ads_page.META_AD_URL_PARAMETERS, prompt)
                    if category == "Motorsport":
                        self.assertIn("SPORTS CAVE MOTORSPORT CAROUSEL AD", prompt)
                        self.assertIn("Race Or Moment", prompt)
                        self.assertIn("Legacy", prompt)
                    else:
                        self.assertIn(
                            f"SPORTS CAVE {category.upper()} CAROUSEL WINNER PATTERN",
                            prompt,
                        )
                        self.assertIn("CATEGORY-SPECIFIC CAROUSEL WINNER ANGLE", prompt)
                        for role in required_roles:
                            self.assertIn(role, prompt)

    def test_every_category_returns_instant_experience_output_for_every_supported_country(self):
        for category in ads_page.SUPPORTED_AD_CATEGORIES:
            for country in ads_page.COUNTRY_OPTIONS[1:]:
                with self.subTest(category=category, country=country):
                    prompt = ads_page.build_ads_prompt(
                        f"{category} Collector Moment",
                        category,
                        country,
                        "Instant Experience",
                    )
                    self.assertNotEqual(prompt, "")
                    self.assertNotIn("Insufficient winner data", prompt)
                    self.assertIn(f"Market: {country}", prompt)
                    self.assertIn("META URL PARAMETERS", prompt)
                    self.assertIn(ads_page.META_AD_URL_PARAMETERS, prompt)
                    if category == "Baseball":
                        self.assertIn("SPORTS CAVE BASEBALL INSTANT EXPERIENCE AD", prompt)
                        self.assertIn("INSTANT EXPERIENCE SETUP", prompt)
                    else:
                        self.assertIn(
                            f"SPORTS CAVE {category.upper()} INSTANT EXPERIENCE WINNER PATTERN",
                            prompt,
                        )
                        self.assertIn("CATEGORY-SPECIFIC INSTANT EXPERIENCE WINNER ANGLE", prompt)
                        self.assertIn("Variant 5:", prompt)
                        self.assertIn("INSTANT EXPERIENCE COVER PROMPT", prompt)
                        self.assertIn("LIMITED TO 100 WORLDWIDE", prompt)
                        self.assertIn("Once it sells out, it's gone.", prompt)
                        self.assertIn("black/gold CTA panel", prompt)
                        self.assertIn("Top 60-68%", prompt)
                        self.assertIn("Bottom 32-40%", prompt)
                        self.assertIn("Claim Your Edition", prompt)

    def test_football_carousel_has_football_specific_winner_angle_and_five_cards(self):
        prompt = ads_page.build_ads_prompt("Arsenal Derby Night", "Football", "UK", "Carousel")

        self.assertIn("SPORTS CAVE FOOTBALL CAROUSEL WINNER PATTERN", prompt)
        self.assertIn("football legacy, matchday memory, finals, rivalries", prompt)
        self.assertIn("supporter identity", prompt)
        self.assertIn("Card 1 - Product Identity", prompt)
        self.assertIn("Card 2 - Moment / Legacy", prompt)
        self.assertIn("Card 3 - Emotional Hook", prompt)
        self.assertIn("Card 4 - Fan Ownership", prompt)
        self.assertIn("Card 5 - Scarcity", prompt)
        self.assertIn("Maximum 17 characters", prompt)
        self.assertIn("No commas", prompt)
        self.assertIn("No full stops", prompt)

    def test_football_instant_experience_uses_black_gold_panel_and_collector_framing(self):
        prompt = ads_page.build_ads_prompt("Messi World Cup Night", "Football", "USA", "Instant Experience")

        self.assertIn("SPORTS CAVE FOOTBALL INSTANT EXPERIENCE WINNER PATTERN", prompt)
        self.assertIn("football collector wall art", prompt)
        self.assertIn("World Cup nights", prompt)
        self.assertIn("black/gold CTA panel", prompt)
        self.assertIn("LIMITED TO 100 WORLDWIDE", prompt)
        self.assertIn("Once it sells out, it's gone.", prompt)
        self.assertIn("Claim Your Edition", prompt)

    def test_cricket_single_image_video_works_for_every_supported_country(self):
        for country in ads_page.COUNTRY_OPTIONS[1:]:
            with self.subTest(country=country):
                prompt = ads_page.build_ads_prompt(
                    "The Ashes Final Session",
                    "Cricket",
                    country,
                    "Single Image / Video",
                )
                self.assertIn("SPORTS CAVE GENERIC SINGLE IMAGE VIDEO WINNER PATTERN", prompt)
                self.assertIn(f"Market: {country}", prompt)
                self.assertIn("PRIMARY TEXT", prompt)
                self.assertIn("Variant 5:", prompt)
                self.assertIn("HEADLINE", prompt)
                self.assertIn("DESCRIPTION", prompt)
                self.assertIn("CREATIVE PROMPT FOR SINGLE IMAGE/VIDEO", prompt)
                self.assertIn("CTA GUIDANCE", prompt)
                self.assertIn("META URL PARAMETERS", prompt)

    def test_category_without_specific_winner_data_still_returns_fallback_output(self):
        prompt = ads_page.build_ads_prompt(
            "Cup Day Final Straight",
            "Rugby League",
            "Australia",
            "Instant Experience",
        )

        self.assertIsNone(ads_page.get_template_key("Rugby League", "Instant Experience"))
        self.assertEqual(ads_page.get_winner_pattern_key("Rugby League", "Instant Experience"), "generic_instant_experience")
        self.assertIn("SPORTS CAVE GENERIC INSTANT EXPERIENCE WINNER PATTERN", prompt)
        self.assertIn("Using generic Sports Cave winner pattern for this category.", prompt)
        self.assertIn("Cup Day Final Straight", prompt)

    def test_country_selection_changes_wording_only_not_output_availability(self):
        uk_prompt = ads_page.build_ads_prompt("Arsenal Derby Night", "Football", "UK", "Instant Experience")
        usa_prompt = ads_page.build_ads_prompt("Arsenal Derby Night", "Football", "USA", "Instant Experience")

        self.assertIn("SPORTS CAVE FOOTBALL INSTANT EXPERIENCE WINNER PATTERN", uk_prompt)
        self.assertIn("SPORTS CAVE FOOTBALL INSTANT EXPERIENCE WINNER PATTERN", usa_prompt)
        self.assertIn("Selected country: UK", uk_prompt)
        self.assertIn("Selected country: USA", usa_prompt)
        self.assertIn("football, supporters", uk_prompt)
        self.assertIn("soccer, fans", usa_prompt)
        self.assertNotEqual(uk_prompt, "")
        self.assertNotEqual(usa_prompt, "")

    def test_uk_and_usa_football_localisation_use_expected_terms(self):
        uk_prompt = ads_page.build_ads_prompt("Arsenal Derby Night", "Football", "UK", "Carousel")
        usa_prompt = ads_page.build_ads_prompt("Arsenal Derby Night", "Football", "USA", "Carousel")

        self.assertIn("UK must use football and supporters, not soccer.", uk_prompt)
        self.assertIn("football and supporters", uk_prompt)
        self.assertIn("USA should use soccer when association football is intended.", usa_prompt)
        self.assertIn("soccer", usa_prompt)
        self.assertIn("COUNTRY LANGUAGE AND LOCALISATION RULES", uk_prompt)
        self.assertIn("COUNTRY LANGUAGE AND LOCALISATION RULES", usa_prompt)

    def test_generic_carousel_card_limit_is_17_characters(self):
        prompt = ads_page.build_ads_prompt("Final Whistle Glory", "Football", "UK", "Carousel")
        cards = [
            {"headline": "Football Glory", "description": "Claim Edition"},
            {"headline": "Final Whistle", "description": "Matchday Wall"},
            {"headline": "Legacy Framed", "description": "Supporter Pride"},
            {"headline": "Own The Night", "description": "Home Bar Wall"},
            {"headline": "Only 100 Made", "description": "No Second Run"},
        ]

        self.assertIn("Maximum 17 characters", prompt)
        self.assertIn("No commas", prompt)
        self.assertIn("No full stops", prompt)
        self.assertEqual(ads_page.validate_carousel_card_length(cards, max_characters=17), [])
        self.assertEqual(
            ads_page.validate_carousel_card_length(
                [{"headline": "Collector Edition", "description": "Valid"}],
                max_characters=17,
            ),
            [],
        )
        self.assertEqual(
            ads_page.validate_carousel_card_length(
                [{"headline": "Far Too Long For Cards", "description": "Valid"}],
                max_characters=17,
            ),
            ["Card 1 headline exceeds 17 characters."],
        )

    def test_baseball_instant_experience_receives_country_localisation_without_changing_baseball_terms(self):
        countries = {
            "USA": "American English",
            "Australia": "Australian English",
            "UK": "British English",
        }

        for country, expected_language in countries.items():
            with self.subTest(country=country):
                prompt = ads_page.build_ads_prompt(
                    "Shohei Ohtani 50/50 Season",
                    "Baseball",
                    country,
                    "Instant Experience",
                    product_url="https://sportscave.com.au/products/ohtani-50-50",
                )
                self.assertIn("COUNTRY LANGUAGE AND LOCALISATION RULES", prompt)
                self.assertIn(f"Selected country: {country}", prompt)
                self.assertIn(expected_language, prompt)
                self.assertIn("home run", prompt)
                self.assertIn("stolen base", prompt)
                self.assertIn("at the plate", prompt)
                self.assertIn("ballpark", prompt)
                self.assertIn("Country-language rules change spelling", prompt)
                self.assertIn("They do not change player identity, baseball facts", prompt)

    def test_baseball_instant_experience_does_not_change_other_campaigns_or_sports(self):
        self.assertIn(
            "SPORTS CAVE BASEBALL CAROUSEL WINNER PATTERN",
            ads_page.build_ads_prompt(
                "Baseball Product",
                "Baseball",
                "USA",
                "Carousel",
                product_url="https://sportscave.com.au/products/baseball-product",
            ),
        )
        self.assertIn(
            "SPORTS CAVE GENERIC SINGLE IMAGE VIDEO WINNER PATTERN",
            ads_page.build_ads_prompt(
                "Baseball Product",
                "Baseball",
                "USA",
                "Single Image / Video",
                product_url="https://sportscave.com.au/products/baseball-product",
            ),
        )
        self.assertIn(
            "SPORTS CAVE NBA INSTANT EXPERIENCE WINNER PATTERN",
            ads_page.build_ads_prompt("Test Product", "NBA", "USA", "Instant Experience"),
        )

    def test_motorsport_prompt_pushes_product_specific_connected_cards(self):
        prompt = ads_page.build_ads_prompt("Peter Brock Six Laps Ahead", "Motorsport", "Australia", "Carousel")

        self.assertIn("Product name: Peter Brock Six Laps Ahead", prompt)
        self.assertIn("Card 1 — Product Identity", prompt)
        self.assertIn("Card 2 — Race Or Moment", prompt)
        self.assertIn("Card 3 — Legacy", prompt)
        self.assertIn("Card 4 — Fan Ownership", prompt)
        self.assertIn("Card 5 — Scarcity", prompt)
        self.assertIn("favour language drawn from circuit, machine, rivalry", prompt)
        self.assertIn("Do not hardcode examples or famous names from another product.", prompt)
        self.assertIn("Peter Brock", prompt)
        self.assertIn("Six Laps", prompt)
        self.assertIn("Bathurst 1979", prompt)
        self.assertIn("Garage Pride", prompt)

    def test_non_motorsport_category_uses_same_story_framework(self):
        cricket_rules = ads_page.build_carousel_story_and_specificity_rules("Cricket")

        self.assertIn("Card 1 — Product Identity", cricket_rules)
        self.assertIn("Card 5 — Scarcity", cricket_rules)
        self.assertIn("crease, spell, innings, summer, Ashes", cricket_rules)
        self.assertIn("could this card be copied unchanged onto an unrelated sports artwork?", cricket_rules)

    def test_carousel_validator_accepts_exact_five_product_specific_cards(self):
        cards = [
            {"headline": "Six Laps", "description": "Peter Brock"},
            {"headline": "Bathurst 1979", "description": "Mt Panorama"},
            {"headline": "Brock Legacy", "description": "Still Roars"},
            {"headline": "Holden Fans", "description": "Fan Pride"},
            {"headline": "Only 100 Made", "description": "No Second Run"},
        ]

        self.assertEqual(ads_page.validate_carousel_cards(cards, edition_info_supplied=True), [])

    def test_carousel_validator_uses_python_len_and_rejects_over_limit_without_truncation(self):
        self.assertEqual(len("Bathurst 1979"), 13)
        self.assertEqual(len("Only 100 Made"), 13)
        self.assertEqual(len("No Second Run"), 13)
        self.assertEqual(len("Claim Your Edition"), 18)

        valid_cards = [
            {"headline": "Six Laps", "description": "Peter Brock"},
            {"headline": "Bathurst 1979", "description": "Mt Panorama"},
            {"headline": "Brock Legacy", "description": "Still Roars"},
            {"headline": "Race Legend", "description": "Fan Pride"},
            {"headline": "Only 100 Made", "description": "No Second Run"},
        ]
        self.assertEqual(ads_page.validate_carousel_cards(valid_cards, edition_info_supplied=True), [])

        invalid_cards = [
            {"headline": "Claim Your Edition", "description": "Peter Brock"},
            {"headline": "Mount Panorama Glory", "description": "Mt Panorama"},
            {"headline": "Brock Legacy", "description": "Still Roars"},
            {"headline": "Race Legend", "description": "Fan Pride"},
            {"headline": "The Ultimate Collector Piece", "description": "No Second Run"},
        ]
        errors = ads_page.validate_carousel_cards(invalid_cards, edition_info_supplied=True)

        self.assertTrue(any("Card 1 headline exceeds 17 characters." == error for error in errors))
        self.assertTrue(any("Card 2 headline exceeds 17 characters." == error for error in errors))
        self.assertTrue(any("Card 5 headline exceeds 17 characters." == error for error in errors))
        self.assertFalse(any("Six Laps" == error for error in errors))

    def test_carousel_validator_counts_punctuation_and_rejects_punctuation_rules(self):
        cards = [
            {"headline": "Six Laps", "description": "Peter Brock"},
            {"headline": "Ford,Holden", "description": "Mt Panorama"},
            {"headline": "Brock Legacy", "description": "Still.Roars"},
            {"headline": "Race Legend", "description": "Fan Pride"},
            {"headline": "Only 100 Made", "description": "No Second Run"},
        ]

        errors = ads_page.validate_carousel_cards(cards, edition_info_supplied=True)

        self.assertIn("Card 2 headline contains a comma.", errors)
        self.assertIn("Card 3 description contains a full stop.", errors)

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
            {"headline": "Only 100 Made", "description": "No Second Run"},
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

Card 1 — Product Identity
Headline: Peter Brock
Description: Six Laps

Card 2 — Race Or Moment
Headline: Bathurst 1979
Description: Mt Panorama

Card 3 — Legacy
Headline: Brock Legacy
Description: Still Roars

Card 4 — Fan Ownership
Headline: Holden Fans
Description: Fan Pride

Card 5 — Scarcity
Headline: Only 100 Made
Description: No Second Run

PRIMARY TEXT VARIATIONS
"""

        cards = ads_page.parse_carousel_cards(output)

        self.assertEqual(len(cards), 5)
        self.assertEqual(cards[0]["headline"], "Peter Brock")
        self.assertEqual(cards[-1]["description"], "No Second Run")

    def test_country_language_guidance_profiles_cover_supported_countries(self):
        australia = ads_page.build_country_language_guidance("Australia")
        usa = ads_page.build_country_language_guidance("USA")
        uk = ads_page.build_country_language_guidance("UK")
        canada = ads_page.build_country_language_guidance("Canada")
        new_zealand = ads_page.build_country_language_guidance("New Zealand")

        self.assertIn("Australian English", australia)
        self.assertIn("colour", australia)
        self.assertIn("favourite", australia)
        self.assertIn("Do not use American spelling", australia)
        self.assertIn("Do not mix Australian, American and British English", australia)

        self.assertIn("American English", usa)
        self.assertIn("color", usa)
        self.assertIn("favorite", usa)
        self.assertIn("shipping", usa)
        self.assertIn("add to cart", usa)
        self.assertIn("soccer", usa)

        self.assertIn("British English", uk)
        self.assertIn("colour", uk)
        self.assertIn("favourite", uk)
        self.assertIn("add to basket", uk)
        self.assertIn("football, not soccer", uk)

        self.assertIn("Canadian English", canada)
        self.assertIn("New Zealand English", new_zealand)
        self.assertIn("Do not force", australia)
        self.assertIn("Do not force stereotypes", usa)

    def test_country_language_guidance_is_injected_through_common_prompt_composer(self):
        base_prompt = "BASE AD PROMPT\n\nPRIMARY TEXT\nWrite copy."

        single_image_prompt = ads_page.compose_final_ads_prompt(
            base_prompt,
            category="Football",
            country="USA",
            campaign_type="Single Image / Video",
            include_primary_text_variations=False,
        )
        instant_experience_prompt = ads_page.compose_final_ads_prompt(
            base_prompt,
            category="Cricket",
            country="UK",
            campaign_type="Instant Experience",
            include_primary_text_variations=False,
        )
        carousel_prompt = ads_page.compose_final_ads_prompt(
            base_prompt,
            category="Motorsport",
            country="Australia",
            campaign_type="Carousel",
            include_primary_text_variations=True,
        )

        self.assertIn("COUNTRY LANGUAGE AND LOCALISATION RULES", single_image_prompt)
        self.assertIn("COUNTRY LANGUAGE AND LOCALISATION RULES", instant_experience_prompt)
        self.assertIn("COUNTRY LANGUAGE AND LOCALISATION RULES", carousel_prompt)
        self.assertIn("American English", single_image_prompt)
        self.assertIn("British English", instant_experience_prompt)
        self.assertIn("Australian English", carousel_prompt)
        self.assertIn("CAROUSEL CARD CHARACTER LIMIT", carousel_prompt)
        self.assertNotIn("CAROUSEL CARD CHARACTER LIMIT", single_image_prompt)

    def test_motorsport_carousel_prompt_receives_country_block_for_every_supported_country(self):
        for country in ads_page.COUNTRY_OPTIONS[1:]:
            with self.subTest(country=country):
                prompt = ads_page.build_ads_prompt("Six Laps Ahead", "Motorsport", country, "Carousel")
                self.assertIn("COUNTRY LANGUAGE AND LOCALISATION RULES", prompt)
                self.assertIn(f"Selected country: {country}", prompt)
                self.assertIn("customer-facing field", prompt)
                self.assertIn("primary-text variations", prompt)
                self.assertIn("carousel cards", prompt)

    def test_country_localisation_validator_flags_clear_cross_market_terms_and_protects_names(self):
        au_errors = ads_page.validate_country_localisation(
            "Favorite color. Add to cart.",
            "Australia",
        )
        us_errors = ads_page.validate_country_localisation(
            "Favourite colour. Add to basket.",
            "USA",
        )
        uk_errors = ads_page.validate_country_localisation(
            "Soccer fan copy. Add to cart.",
            "UK",
            sport_category="Football",
        )
        protected_errors = ads_page.validate_country_localisation(
            "Official artwork title: Favorite Color",
            "Australia",
            protected_terms=("Favorite Color",),
        )

        self.assertTrue(any("color" in error for error in au_errors))
        self.assertTrue(any("favorite" in error for error in au_errors))
        self.assertTrue(any("colour" in error for error in us_errors))
        self.assertTrue(any("basket" in error for error in us_errors))
        self.assertTrue(any("soccer" in error for error in uk_errors))
        self.assertTrue(any("add to cart" in error for error in uk_errors))
        self.assertEqual(protected_errors, [])

    def test_unknown_country_uses_explicit_neutral_fallback(self):
        guidance = ads_page.build_country_language_guidance("Ireland")

        self.assertIn("Selected country: Ireland", guidance)
        self.assertIn("NEUTRAL INTERNATIONAL ENGLISH", guidance)
        self.assertIn("Do not silently treat unknown countries as American English", guidance)

    def test_edition_ops_product_names_load_from_local_snapshot_without_sync(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot_path = Path(temp_dir) / "edition_ops_products_snapshot.json"
            snapshot_path.write_text(
                json.dumps(
                    {
                        "rows": [
                            {"product_title": "Peter Brock Six Laps Ahead"},
                            {"Product title": "Shohei Ohtani 50/50"},
                            {"title": "Fallback Title"},
                            {"product_title": "peter brock six laps ahead"},
                            {"online_store_url": "https://example.com/products/no-title"},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            names = ads_page.load_edition_ops_product_name_options(snapshot_path)

        self.assertEqual(
            names,
            [
                "Peter Brock Six Laps Ahead",
                "Shohei Ohtani 50/50",
                "Fallback Title",
            ],
        )

    def test_ads_product_name_input_uses_searchable_edition_ops_options_when_available(self):
        source = (ROOT / "ads_page.py").read_text(encoding="utf-8")

        self.assertIn("def render_product_name_input", source)
        self.assertIn("load_edition_ops_product_name_options()", source)
        self.assertIn('st.selectbox(\n            "Product name"', source)
        self.assertIn("accept_new_options=True", source)
        self.assertIn('filter_mode="fuzzy"', source)
        self.assertIn("EDITION_OPS_SNAPSHOT_PATH", source)
        self.assertNotIn("import edition_ops", source)

    def test_supported_prompt_uses_copy_button_instead_of_visible_prompt_code(self):
        source = (ROOT / "ads_page.py").read_text(encoding="utf-8")
        supported_result_source = source[source.index("def render_supported_result") : source.index("def render_page")]

        self.assertIn("def render_prompt_copy_button", source)
        self.assertIn("components.html", source)
        self.assertIn("navigator.clipboard.writeText(promptText)", source)
        self.assertIn("render_prompt_copy_button(", supported_result_source)
        self.assertNotIn("st.code(build_ads_prompt", supported_result_source)

    def test_submit_supported_result_renders_compact_sections_with_url_parameters(self):
        app_test = run_ads_page()
        set_product_name(app_test, "Six Laps Ahead")
        select_option(app_test, "Category", "Motorsport")
        select_option(app_test, "Country", "Canada")
        select_option(app_test, "Campaign type", "Carousel")
        app_test.button[0].click().run(timeout=20)

        self.assertEqual(
            [subheader.value for subheader in app_test.subheader],
            [
                "1. Upload these five images",
                "2. Copy this ChatGPT prompt",
                "3. Build it in Meta",
                "4. URL parameters",
            ],
        )
        self.assertEqual(len(app_test.code), 1)
        self.assertEqual(app_test.code[0].value, ads_page.META_AD_URL_PARAMETERS)
        self.assertFalse(any("Product name: Six Laps Ahead" in code.value for code in app_test.code))
        self.assertFalse(any("Market: Canada" in code.value for code in app_test.code))
        self.assertEqual(len(app_test.exception), 0)

    def test_submit_valid_category_campaign_renders_category_specific_output(self):
        app_test = run_ads_page()
        set_product_name(app_test, "Six Laps Ahead")
        select_option(app_test, "Category", "Motorsport")
        select_option(app_test, "Country", "Australia")
        select_option(app_test, "Campaign type", "Instant Experience")
        app_test.button[0].click().run(timeout=20)

        self.assertNotIn("Insufficient winner data", [subheader.value for subheader in app_test.subheader])
        self.assertIn("1. Copy this ChatGPT prompt", [subheader.value for subheader in app_test.subheader])
        self.assertFalse(any("Using generic Sports Cave winner pattern" in caption.value for caption in app_test.caption))
        self.assertEqual(len(app_test.code), 1)
        self.assertEqual(app_test.code[0].value, ads_page.META_AD_URL_PARAMETERS)
        self.assertEqual(len(app_test.exception), 0)

    def test_valid_category_campaign_country_combinations_never_have_insufficient_winner_data(self):
        for category in ads_page.SUPPORTED_AD_CATEGORIES:
            for campaign_type in ("Carousel", "Instant Experience"):
                for country in ads_page.COUNTRY_OPTIONS[1:]:
                    with self.subTest(category=category, campaign_type=campaign_type, country=country):
                        self.assertIsNotNone(ads_page.get_winner_pattern_key(category, campaign_type))
                        prompt = ads_page.build_ads_prompt(
                            f"{category} Collector Moment",
                            category,
                            country,
                            campaign_type,
                        )
                        self.assertNotEqual(prompt, "")
                        self.assertNotIn("Insufficient winner data", prompt)

    def test_ads_page_source_has_no_external_backend_execution_path(self):
        source = (ROOT / "ads_page.py").read_text(encoding="utf-8")
        source_lower = source.casefold()

        for blocked in ("supabase", "meta_ads_client", "openai", "requests", "analytics"):
            self.assertNotIn(blocked, source_lower)
        self.assertNotIn("import shopify", source_lower)
        self.assertNotIn("from shopify", source_lower)
        self.assertNotIn("shopify_client", source_lower)
        self.assertNotIn("st.tabs", source)
        self.assertNotIn("st.metric", source)
        self.assertNotIn("saved packs", source_lower)
        self.assertNotIn("dashboard", source_lower)

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
