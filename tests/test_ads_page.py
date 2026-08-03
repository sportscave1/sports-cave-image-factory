import importlib
import io
import json
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from streamlit.testing.v1 import AppTest

import ads_page
import ads_product_catalog
import image_factory
import social_media_catalog
from sports_cave_prompt_blocks import SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER


ROOT = Path(__file__).resolve().parents[1]


def run_ads_page():
    app_test = AppTest.from_file(str(ROOT / "app.py"))
    app_test.session_state["sports_cave_authenticated"] = True
    app_test.session_state["selected_page"] = "Ads"
    app_test.session_state["startup_shell_loaded"] = True
    return app_test.run(timeout=20)


def set_product_name(app_test, value):
    for text_input in app_test.text_input:
        if text_input.label == "Product name":
            text_input.set_value(value)
            app_test.run(timeout=20)
            return
    for selectbox in app_test.selectbox:
        if selectbox.label == "Product name":
            if getattr(selectbox, "options", None) and value not in selectbox.options:
                selectbox.select(selectbox.options[0])
            elif value in getattr(selectbox, "options", ()):
                selectbox.select(value)
            else:
                selectbox.set_value(value)
            app_test.run(timeout=20)
            return
    raise AssertionError("Product name widget was not rendered.")


def select_option(app_test, label, value):
    for selectbox in app_test.selectbox:
        if selectbox.label == label:
            selectbox.select(value)
            app_test.run(timeout=20)
            return
    raise AssertionError(f"{label} selectbox was not rendered.")


def set_product_url(app_test, value="https://sportscave.com.au/products/six-laps-ahead"):
    for text_input in app_test.text_input:
        if text_input.label == "Product page URL *":
            text_input.set_value(value)
            app_test.run(timeout=20)
            return
    raise AssertionError("Product page URL field was not rendered.")


def visual_contract(prompt):
    marker = "MASTER RESPONSE AND VISUAL OUTPUT CONTRACT"
    return prompt[prompt.index(marker) :]


def carousel_prompt_card_sections(contract):
    sections = {}
    for index in range(1, ads_page.CAROUSEL_CARD_COUNT + 1):
        marker = f"CARD {index} IMAGE GENERATION PROMPT"
        start = contract.index(marker)
        next_marker = (
            f"CARD {index + 1} IMAGE GENERATION PROMPT"
            if index < ads_page.CAROUSEL_CARD_COUNT
            else "Return exactly these five image-prompt entries"
        )
        end = contract.index(next_marker, start)
        sections[index] = contract[start:end]
    return sections


def square_png_bytes(color=(46, 76, 112)):
    buffer = io.BytesIO()
    Image.new("RGB", (96, 96), color).save(buffer, format="PNG")
    return buffer.getvalue()


def instant_experience_settings(output_mode=ads_page.IE_MODE_SMART, **overrides):
    settings = ads_page.default_instant_experience_settings(output_mode=output_mode)
    settings.update(overrides)
    if "advanced_visual" in overrides:
        settings["advanced_visual"] = {
            **ads_page.default_instant_experience_settings()["advanced_visual"],
            **overrides["advanced_visual"],
        }
    return settings


def button_by_label(app_test, label):
    for button in app_test.button:
        if button.label == label:
            return button
    raise AssertionError(f"{label} button was not rendered.")


def buttons_by_label(app_test, label):
    return [button for button in app_test.button if button.label == label]


def uploader_by_label(app_test, label):
    for uploader in app_test.file_uploader:
        if uploader.label == label:
            return uploader
    raise AssertionError(f"{label} uploader was not rendered.")


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
                "Golf",
                "Horse Racing",
                "Baseball",
                "Combat",
                "Ice Hockey",
                "NFL",
                "Rugby Union",
                "Tennis",
                "Other",
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
            with self.subTest(category=category, campaign_type="Single Image / Video"):
                self.assertIsNotNone(ads_page.get_template_key(category, "Single Image / Video"))
                self.assertIsNotNone(ads_page.get_winner_pattern_key(category, "Single Image / Video"))

        self.assertEqual(ads_page.get_template_key("Motorsport", "Carousel"), "motorsport_carousel")
        self.assertEqual(ads_page.get_template_key("Baseball", "Instant Experience"), "baseball_instant_experience")
        self.assertIsNone(ads_page.get_template_key("Rugby League", "Carousel"))
        self.assertEqual(ads_page.get_winner_pattern_key("Rugby League", "Carousel"), "generic_carousel")
        self.assertIn(
            "SPORTS CAVE GENERIC CAROUSEL WINNER PATTERN",
            ads_page.build_ads_prompt("Test Product", "Rugby League", "Australia", "Carousel"),
        )

    def test_supported_categories_have_complete_ad_category_profiles(self):
        required_fields = {
            "audience",
            "emotion",
            "carousel_flow",
            "ie_setting",
            "headline_examples",
            "description_examples",
            "country_note",
        }

        for category in ads_page.SUPPORTED_AD_CATEGORIES:
            with self.subTest(category=category):
                self.assertIn(category, ads_page.CATEGORY_COPY_CUES)
                self.assertTrue(required_fields.issubset(ads_page.CATEGORY_WINNER_ANGLES[category]))

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
            ads_page.PRODUCT_URL_ERROR,
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

    def test_product_page_url_is_required_and_must_be_absolute_http_url(self):
        for bad_url in ("", "sportscave.com.au/products/six-laps", "ftp://example.com/item", "https://bad url"):
            with self.subTest(bad_url=bad_url):
                self.assertEqual(
                    ads_page.validate_ads_inputs(
                        "Six Laps Ahead",
                        "Motorsport",
                        "Australia",
                        "Carousel",
                        product_url=bad_url,
                    ),
                    ads_page.PRODUCT_URL_ERROR,
                )
        for good_url in ("http://sportscave.com.au/products/six-laps", "https://sportscave.com.au/products/six-laps"):
            with self.subTest(good_url=good_url):
                self.assertEqual(
                    ads_page.validate_ads_inputs(
                        "Six Laps Ahead",
                        "Motorsport",
                        "Australia",
                        "Carousel",
                        product_url=good_url,
                    ),
                    "",
                )

    def test_product_page_url_field_validates_on_submit_and_preserves_value(self):
        app_test = run_ads_page()
        set_product_name(app_test, "Six Laps Ahead")
        select_option(app_test, "Category", "Motorsport")
        select_option(app_test, "Country", "Australia")
        select_option(app_test, "Campaign type", "Carousel")

        self.assertFalse(button_by_label(app_test, "Submit").disabled)
        set_product_url(app_test, "not-a-url")
        button_by_label(app_test, "Submit").click().run(timeout=20)
        self.assertTrue(any(ads_page.PRODUCT_URL_ERROR in error.value for error in app_test.error))
        self.assertNotIn(ads_page.ADS_RESULT_STATE_KEY, app_test.session_state)

        set_product_url(app_test, "  http://sportscave.com.au/products/six-laps  ")
        self.assertFalse(button_by_label(app_test, "Submit").disabled)
        button_by_label(app_test, "Submit").click().run(timeout=20)
        self.assertEqual(
            app_test.session_state[ads_page.ADS_RESULT_STATE_KEY]["product_url"],
            "http://sportscave.com.au/products/six-laps",
        )
        app_test.run(timeout=20)
        self.assertEqual(
            app_test.session_state[ads_page.ADS_RESULT_STATE_KEY]["product_url"],
            "http://sportscave.com.au/products/six-laps",
        )

    def test_product_page_url_validation_has_focus_hook(self):
        source = (ROOT / "ads_page.py").read_text(encoding="utf-8")

        self.assertIn("Product page URL *", source)
        self.assertIn("input.focus()", source)
        self.assertIn(ads_page.PRODUCT_URL_ERROR, source)

    def test_campaign_moment_form_is_optional_and_validates_missing_name(self):
        app_test = run_ads_page()

        self.assertIn("Moment Type", [selectbox.label for selectbox in app_test.selectbox])
        self.assertIn("Relevant Country or Market", [selectbox.label for selectbox in app_test.selectbox])
        self.assertIn("Relevance Strength", [selectbox.label for selectbox in app_test.selectbox])
        self.assertIn("Moment Name", [text_input.label for text_input in app_test.text_input])
        self.assertIn("Promotion or Offer", [text_input.label for text_input in app_test.text_input])
        self.assertIn("Use this moment in image prompts", [checkbox.label for checkbox in app_test.checkbox])
        self.assertIn("Clear moment", [button.label for button in app_test.button])

        set_product_name(app_test, "Six Laps Ahead")
        select_option(app_test, "Category", "Motorsport")
        select_option(app_test, "Country", "Australia")
        select_option(app_test, "Campaign type", "Carousel")
        set_product_url(app_test)
        select_option(app_test, "Moment Type", "Sporting Event")

        button_by_label(app_test, "Submit").click().run(timeout=20)

        self.assertTrue(
            any(
                "Enter the specific campaign moment, such as Father’s Day or NBA Playoffs."
                in warning.value
                for warning in app_test.warning
            )
        )
        self.assertNotIn(ads_page.ADS_RESULT_STATE_KEY, app_test.session_state)

    def test_generated_prompt_contains_required_dynamic_and_rule_text(self):
        prompt = ads_page.build_ads_prompt("Six Laps Ahead", "Motorsport", "UK", "Carousel")

        self.assertIn("Product name: Six Laps Ahead", prompt)
        self.assertIn("Category: Motorsport", prompt)
        self.assertIn("Market: UK", prompt)
        self.assertIn("Campaign type: Carousel", prompt)
        self.assertIn("Maximum 17 characters including spaces and punctuation.", prompt)
        self.assertIn("Every headline is 17 characters or fewer including spaces and punctuation.", prompt)
        self.assertIn("Every description is 17 characters or fewer including spaces and punctuation.", prompt)
        self.assertNotIn("Prefer 10 to 13 characters", prompt)
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
        self.assertIn("def build_carousel_high_conversion_quality_rules", source)
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

    def test_baseball_instant_experience_prompt_outputs_three_grouped_concepts(self):
        prompt = ads_page.build_ads_prompt(
            "Shohei Ohtani 50/50 Season",
            "Baseball",
            "USA",
            "Instant Experience",
            product_url="https://sportscave.com.au/products/ohtani-50-50",
        )

        self.assertIn("SPORTS CAVE BASEBALL INSTANT EXPERIENCE AD", prompt)
        self.assertIn("Product name: Shohei Ohtani 50/50 Season", prompt)
        self.assertIn("Destination guidance: Use this selected product page URL", prompt)
        self.assertIn("https://sportscave.com.au/products/ohtani-50-50", prompt)
        for heading in (
            "GROUP 1 — NOSTALGIA",
            "GROUP 2 — OWNERSHIP",
            "GROUP 3 — SCARCITY",
        ):
            self.assertIn(heading, prompt)
        self.assertIn("| Variation | Primary Text | Headline | CTA |", prompt)
        self.assertIn("Every group table must contain exactly three completed rows.", prompt)
        self.assertIn("Across all groups, output exactly nine complete ad-copy combinations.", prompt)
        self.assertIn("INSTANT EXPERIENCE SETUP", prompt)
        self.assertEqual(prompt.count("Creative concept: Nostalgia"), 1)
        self.assertEqual(prompt.count("Creative concept: Ownership"), 1)
        self.assertEqual(prompt.count("Creative concept: Scarcity"), 1)
        self.assertEqual(prompt.count(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER), 3)
        self.assertNotIn("Create exactly five genuinely different Meta primary-text variations.", prompt)
        self.assertNotIn("Return one final primary text only.", prompt)
        self.assertNotIn("Generate exactly one headline.", prompt)
        self.assertNotIn("DESCRIPTION\n\n1. [description]", prompt)
        self.assertNotIn("CAROUSEL CARDS\n\nCard 1", prompt)
        self.assertNotIn("CAROUSEL CARD CHARACTER LIMIT", prompt)
        self.assertNotIn("13 characters", prompt)
        self.assertIn("META URL PARAMETERS", prompt)
        self.assertIn(ads_page.META_AD_URL_PARAMETERS, prompt)

    def test_baseball_instant_experience_uses_grouped_copy_rules(self):
        prompt = ads_page.build_ads_prompt(
            "Ohtani Judge The Titans",
            "Baseball",
            "Australia",
            "Instant Experience",
            product_url="https://sportscave.com.au/products/the-titans",
        )

        self.assertIn("NOSTALGIA — Moment & Memory", prompt)
        self.assertIn("OWNERSHIP — Identity & Display", prompt)
        self.assertIn("SCARCITY — Collector & Limited Edition", prompt)
        self.assertIn("make the fan remember the athlete", prompt)
        self.assertIn("make the fan picture the artwork on their wall", prompt)
        self.assertIn("convert established desire using verified limited-edition collector scarcity", prompt)
        self.assertIn("ballpark memory", prompt)
        self.assertIn("generations", prompt)
        self.assertIn("swing and legacy", prompt)
        self.assertIn("Use natural selected-country English.", prompt)

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
        self.assertIn("Do not identify or guess a person", prompt)
        self.assertIn("Never invent history, achievements, product facts or sporting events.", prompt)

    def test_baseball_instant_experience_setup_uses_required_meta_instructions(self):
        prompt = ads_page.build_ads_prompt(
            "The Summer of 98",
            "Baseball",
            "UK",
            "Instant Experience",
            product_url="https://sportscave.com.au/products/summer-98",
        )

        self.assertIn("Generate and upload the three covers from the three image prompts below.", prompt)
        self.assertIn("Keep the connected category catalogue attached.", prompt)
        self.assertIn("Baseball Wall Art", prompt)
        self.assertIn("Use the Meta Instant Experience Product template.", prompt)
        self.assertNotIn("Mockups ZIP", prompt)
        self.assertNotIn("Social Media Reels", prompt)
        self.assertIn("Catalogue product headline field uses: product.name", prompt)
        self.assertIn("Product descriptor/subtitle uses: Limited Edition when approved.", prompt)
        self.assertIn("Fixed button label remains: Shop Now.", prompt)
        self.assertIn("URL parameters use exactly: " + ads_page.META_AD_URL_PARAMETERS, prompt)
        self.assertIn("https://sportscave.com.au/products/summer-98", prompt)
        self.assertIn("Do not introduce collection-page routing in this workflow.", prompt)

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
                self.assertIn("SPORTS CAVE FOOTBALL INSTANT EXPERIENCE STANDARD WORKFLOW", prompt)
                self.assertIn(f"Market: {country}", prompt)
                self.assertIn(expected_terms[country], prompt)
                self.assertIn("GROUP 1 — NOSTALGIA", prompt)
                self.assertIn("GROUP 2 — OWNERSHIP", prompt)
                self.assertIn("GROUP 3 — SCARCITY", prompt)
                self.assertIn("| Variation | Primary Text | Headline | CTA |", prompt)
                self.assertIn("COPY VARIATIONS", prompt)
                self.assertNotIn("DESCRIPTION\n\n1. [description]", prompt)
                self.assertIn("Creative concept: Nostalgia", prompt)
                self.assertIn("Creative concept: Ownership", prompt)
                self.assertIn("Creative concept: Scarcity", prompt)
                self.assertIn("LIMITED TO 100 WORLDWIDE", prompt)
                self.assertIn("Once it sells out", prompt)
                self.assertIn("CLAIM YOUR EDITION", prompt)
                self.assertIn("full-width upper lifestyle/product image across approximately 76-78%", prompt)
                self.assertIn("full-width matte-black scarcity strip across the bottom approximately 22-24%", prompt)
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
                            f"SPORTS CAVE {category.upper()} INSTANT EXPERIENCE STANDARD WORKFLOW",
                            prompt,
                        )
                        self.assertIn("CATEGORY-SPECIFIC INSTANT EXPERIENCE WINNER ANGLE", prompt)
                        self.assertIn("GROUP 1 — NOSTALGIA", prompt)
                        self.assertIn("GROUP 2 — OWNERSHIP", prompt)
                        self.assertIn("GROUP 3 — SCARCITY", prompt)
                        self.assertIn("| Variation | Primary Text | Headline | CTA |", prompt)
                        self.assertNotIn("DESCRIPTION\n\n1. [description]", prompt)
                        self.assertIn("Creative concept: Nostalgia", prompt)
                        self.assertIn("Creative concept: Ownership", prompt)
                        self.assertIn("Creative concept: Scarcity", prompt)
                        self.assertIn("LIMITED TO 100 WORLDWIDE", prompt)
                        self.assertIn("Once it sells out", prompt)
                        self.assertIn("full-width upper lifestyle/product image across approximately 76-78%", prompt)
                        self.assertIn("full-width matte-black scarcity strip across the bottom approximately 22-24%", prompt)
                        self.assertIn("No left/right split, no right sidebar and no vertical scarcity panel.", prompt)
                        self.assertIn("CLAIM YOUR EDITION", prompt)

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

    def test_football_instant_experience_uses_bottom_strip_and_collector_framing(self):
        prompt = ads_page.build_ads_prompt("Messi World Cup Night", "Football", "USA", "Instant Experience")

        self.assertIn("SPORTS CAVE FOOTBALL INSTANT EXPERIENCE STANDARD WORKFLOW", prompt)
        self.assertIn("Football collector wall art", prompt)
        self.assertIn("GROUP 3 — SCARCITY", prompt)
        self.assertIn("Creative concept: Scarcity", prompt)
        self.assertIn("full-width upper lifestyle/product image across approximately 76-78%", prompt)
        self.assertIn("full-width matte-black scarcity strip across the bottom approximately 22-24%", prompt)
        self.assertIn("thin restrained metallic-gold divider across the top edge of the black strip", prompt)
        self.assertIn("No left/right split, no right sidebar and no vertical scarcity panel.", prompt)
        self.assertIn("LIMITED TO 100 WORLDWIDE", prompt)
        self.assertIn("Once it sells out", prompt)
        self.assertIn("CLAIM YOUR EDITION", prompt)

    def test_added_categories_have_specific_outputs_for_all_campaign_sections(self):
        expected_terms = {
            "Golf": ("major pressure", "clubhouse"),
            "Rugby Union": ("test-match pressure", "rugby union"),
            "Other": ("verified moment", "defining moment"),
        }

        for category, terms in expected_terms.items():
            for campaign_type in ("Carousel", "Instant Experience", "Single Image / Video"):
                with self.subTest(category=category, campaign_type=campaign_type):
                    prompt = ads_page.build_ads_prompt(
                        f"{category} Collector Moment",
                        category,
                        "Australia",
                        campaign_type,
                    )
                    self.assertNotIn("Insufficient winner data", prompt)
                    self.assertNotIn("Using generic Sports Cave winner pattern", prompt)
                    self.assertIn(f"SPORTS CAVE {category.upper()} ", prompt)
                    for term in terms:
                        self.assertIn(term, prompt)

    def test_ad_prompt_generation_records_activity_log(self):
        with patch("ads_page.record_activity_log") as record_activity:
            ads_page.record_ad_prompt_generated(
                "Six Laps Ahead",
                "Motorsport",
                "Australia",
                "Carousel",
            )

        record_activity.assert_called_once()
        args, kwargs = record_activity.call_args
        self.assertEqual(args[:3], ("ad_prompt_generated", "Ads", "Generated ad prompt: Six Laps Ahead"))
        self.assertEqual(kwargs["entity_type"], "ad_prompt")
        self.assertEqual(kwargs["metadata"]["campaign_type"], "Carousel")

    def test_cricket_single_image_video_works_for_every_supported_country(self):
        for country in ads_page.COUNTRY_OPTIONS[1:]:
            with self.subTest(country=country):
                prompt = ads_page.build_ads_prompt(
                    "The Ashes Final Session",
                    "Cricket",
                    country,
                    "Single Image / Video",
                )
                self.assertIn("SPORTS CAVE CRICKET SINGLE IMAGE VIDEO WINNER PATTERN", prompt)
                self.assertIn("CATEGORY-SPECIFIC SINGLE IMAGE / VIDEO WINNER ANGLE", prompt)
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
        self.assertIn("SPORTS CAVE STANDARD INSTANT EXPERIENCE WORKFLOW", prompt)
        self.assertIn("Using generic Sports Cave winner pattern for this category.", prompt)
        self.assertIn("Cup Day Final Straight", prompt)

    def test_country_selection_changes_wording_only_not_output_availability(self):
        uk_prompt = ads_page.build_ads_prompt("Arsenal Derby Night", "Football", "UK", "Instant Experience")
        usa_prompt = ads_page.build_ads_prompt("Arsenal Derby Night", "Football", "USA", "Instant Experience")

        self.assertIn("SPORTS CAVE FOOTBALL INSTANT EXPERIENCE STANDARD WORKFLOW", uk_prompt)
        self.assertIn("SPORTS CAVE FOOTBALL INSTANT EXPERIENCE STANDARD WORKFLOW", usa_prompt)
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
        self.assertEqual(ads_page.validate_carousel_card_length(cards), [])
        self.assertEqual(
            ads_page.validate_carousel_card_length(
                [{"headline": "123456789012345", "description": "Valid"}],
            ),
            [],
        )
        self.assertEqual(
            ads_page.validate_carousel_card_length(
                [{"headline": "12345678901234567", "description": "Valid"}],
            ),
            [],
        )
        self.assertEqual(
            ads_page.validate_carousel_card_length(
                [{"headline": "123456789012345678", "description": "Valid"}],
            ),
            ["Card 1 headline exceeds 17 characters."],
        )

    def test_carousel_limit_counts_spaces_and_rejects_18_characters(self):
        exactly_seventeen = "12345678901 12345"
        eighteen = "123456789012 12345"

        self.assertEqual(len(exactly_seventeen), 17)
        self.assertEqual(len(eighteen), 18)
        self.assertEqual(
            ads_page.validate_carousel_card_length(
                [{"headline": exactly_seventeen, "description": exactly_seventeen}],
            ),
            [],
        )
        self.assertEqual(
            ads_page.validate_carousel_card_length(
                [{"headline": eighteen, "description": eighteen}],
            ),
            [
                "Card 1 headline exceeds 17 characters.",
                "Card 1 description exceeds 17 characters.",
            ],
        )

    def test_carousel_limit_does_not_restrict_primary_text_or_instant_experience(self):
        long_primary_text = (
            "This primary text intentionally exceeds seventeen characters and remains valid."
        )
        cards = [
            {
                "headline": "Product Hero",
                "description": "Fan Identity",
                "primary_text": long_primary_text,
            }
        ]

        self.assertEqual(ads_page.validate_carousel_card_length(cards), [])
        instant_prompt = ads_page.build_ads_prompt(
            "Final Whistle Glory",
            "Football",
            "UK",
            "Instant Experience",
        )
        self.assertNotIn("CAROUSEL CARD CHARACTER LIMIT", instant_prompt)
        self.assertNotIn("HIGH-CONVERSION CAROUSEL QUALITY", instant_prompt)
        self.assertIn("4 to 6 words max.", instant_prompt)

    def test_carousel_winner_examples_fit_limit_without_changing_other_campaigns(self):
        for category, angle in ads_page.CATEGORY_WINNER_ANGLES.items():
            for field in ("headline_examples", "description_examples"):
                with self.subTest(category=category, field=field):
                    rendered = ads_page.build_carousel_winner_examples(angle[field])
                    self.assertTrue(rendered)
                    self.assertTrue(
                        all(
                            len(example.strip()) <= ads_page.CAROUSEL_CARD_MAX_CHARACTERS
                            for example in rendered.split(";")
                        )
                    )

        cricket_carousel = ads_page.build_category_winner_angle_block(
            "Cricket",
            "Carousel",
            "Australia",
        )
        cricket_instant = ads_page.build_category_winner_angle_block(
            "Cricket",
            "Instant Experience",
            "Australia",
        )
        baseball_carousel = ads_page.build_category_winner_angle_block(
            "Baseball",
            "Carousel",
            "USA",
        )
        baseball_instant = ads_page.build_category_winner_angle_block(
            "Baseball",
            "Instant Experience",
            "USA",
        )

        self.assertIn("For Cricket Fans", cricket_carousel)
        self.assertIn("For Cricket Fans", cricket_instant)
        self.assertIn("For Baseball Fans", baseball_carousel)
        self.assertIn("For Baseball Fans", baseball_instant)

    def test_high_conversion_rules_are_shared_without_changing_card_schema(self):
        rules = ads_page.build_carousel_high_conversion_quality_rules()
        role_markers = (
            "Card 1 - Product Identity",
            "Card 2 - Display Desire",
            "Card 3 - Collector Appeal",
            "Card 4 - Emotional Meaning",
            "Card 5 - Authentic Scarcity",
        )

        self.assertEqual(
            [rules.index(marker) for marker in role_markers],
            sorted(rules.index(marker) for marker in role_markers),
        )
        for required in (
            "one connected persuasion journey",
            "different buying reason",
            "must complement one another rather than repeat",
            "Write for fast mobile scanning.",
            "Reject anything exceeding 17 characters.",
            "Reject awkward abbreviations and incomplete phrases.",
            "Select only the strongest connected five-card sequence.",
            "Output only the final campaign in the existing format.",
        ):
            self.assertIn(required, rules)

        motorsport_prompt = ads_page.build_ads_prompt(
            "Six Laps Ahead",
            "Motorsport",
            "Australia",
            "Carousel",
        )
        football_prompt = ads_page.build_ads_prompt(
            "Final Whistle Glory",
            "Football",
            "UK",
            "Carousel",
        )
        self.assertEqual(motorsport_prompt.count("HIGH-CONVERSION CAROUSEL QUALITY"), 1)
        self.assertEqual(football_prompt.count("HIGH-CONVERSION CAROUSEL QUALITY"), 1)
        self.assertIn(
            "Keep the approved output role labels Product Identity, Race Or Moment, "
            "Legacy, Fan Ownership and Scarcity exactly as shown in the output schema.",
            motorsport_prompt,
        )
        self.assertIn("Card 2 - Moment / Legacy", football_prompt)
        self.assertIn("Card 3 - Emotional Hook", football_prompt)

    def test_shared_winner_copy_upgrade_reaches_carousel_and_instant_experience(self):
        carousel_prompt = ads_page.build_ads_prompt(
            "Six Laps Ahead",
            "Motorsport",
            "Australia",
            "Carousel",
        )
        instant_prompt = ads_page.build_ads_prompt(
            "Final Whistle Glory",
            "Football",
            "UK",
            "Instant Experience",
        )
        single_prompt = ads_page.build_ads_prompt(
            "Final Whistle Glory",
            "Football",
            "UK",
            "Single Image / Video",
        )

        self.assertEqual(carousel_prompt.count(ads_page.META_WINNER_COPY_BLOCK_VERSION), 1)
        self.assertIn("Variation 1 - Staccato Legacy Story", carousel_prompt)
        self.assertIn("Variation 2 - Framed Greatness", carousel_prompt)
        self.assertIn("Variation 3 - Nostalgia And Remembered Moment", carousel_prompt)
        self.assertIn("Variation 4 - Fan Identity And Ownership", carousel_prompt)
        self.assertIn("Variation 5 - Collector Scarcity Or Gifting", carousel_prompt)
        self.assertIn("UNIVERSAL PRIMARY-TEXT QUALITY", carousel_prompt)
        self.assertIn("Lead with the emotional hook rather than a product description.", carousel_prompt)
        self.assertIn("Write for a mobile Meta feed", carousel_prompt)
        self.assertIn("Use the product title and supplied artwork as the factual source of truth.", carousel_prompt)

        self.assertEqual(instant_prompt.count(ads_page.META_WINNER_COPY_BLOCK_VERSION), 1)
        self.assertIn("STANDARD INSTANT EXPERIENCE GROUPED COPY DIVERSITY", instant_prompt)
        self.assertIn("Each concept table must contain exactly three completed rows.", instant_prompt)
        self.assertIn("The full response must contain exactly nine complete ad-copy combinations.", instant_prompt)
        self.assertIn("No Description or Meta Ad Description field is allowed.", instant_prompt)
        self.assertIn("Scarcity must be concentrated in the Scarcity concept.", instant_prompt)

        self.assertNotIn(ads_page.META_WINNER_COPY_BLOCK_VERSION, single_prompt)

    def test_staccato_and_framed_greatness_rules_are_reusable_and_fact_safe(self):
        rules = ads_page.build_shared_meta_winner_copy_upgrade()
        opening = "Greatness doesn’t fade.\nIt gets framed."

        self.assertEqual(rules.count(opening), 1)
        self.assertIn("Begin with two to four short sharp lines.", rules)
        self.assertIn("Do not mechanically force they or a rivalry structure", rules)
        self.assertIn("single athlete, team, car, horse, event or championship product", rules)
        self.assertIn("Close with: Limited to {authentic edition limit} worldwide.", rules)
        self.assertIn(
            "When the confirmed edition limit is 100, write exactly: "
            "Limited to 100 worldwide. Secure your edition before it’s gone.",
            rules,
        )
        self.assertIn("When no edition quantity is confirmed", rules)
        self.assertNotIn("Kobe", rules)
        self.assertNotIn("Jordan", rules)

    def test_shared_winner_copy_upgrade_is_idempotent_and_preserves_custom_text(self):
        custom_prompt = "CUSTOM SAVED INSTRUCTION\nKeep this exact specialist direction."

        once = ads_page.apply_shared_meta_winner_copy_upgrade(custom_prompt, "Carousel")
        twice = ads_page.apply_shared_meta_winner_copy_upgrade(once, "Carousel")

        self.assertEqual(once, twice)
        self.assertEqual(once.count(ads_page.META_WINNER_COPY_BLOCK_VERSION), 1)
        self.assertIn(custom_prompt, once)
        self.assertIn("If the approved campaign-specific template requires exactly one primary text", once)
        self.assertNotIn("STANDARD INSTANT EXPERIENCE GROUPED COPY DIVERSITY", once)
        self.assertIn(
            "STANDARD INSTANT EXPERIENCE GROUPED COPY DIVERSITY",
            ads_page.apply_shared_meta_winner_copy_upgrade(custom_prompt, "Instant Experience"),
        )
        self.assertEqual(
            ads_page.apply_shared_meta_winner_copy_upgrade(custom_prompt, "Single Image / Video"),
            custom_prompt,
        )

    def test_dedicated_baseball_instant_experience_keeps_grouped_copy_schema(self):
        prompt = ads_page.build_ads_prompt(
            "Shohei Ohtani 50/50 Season",
            "Baseball",
            "USA",
            "Instant Experience",
            product_url="https://sportscave.com.au/products/ohtani-50-50",
        )

        self.assertEqual(prompt.count(ads_page.META_WINNER_COPY_BLOCK_VERSION), 1)
        self.assertIn("STANDARD INSTANT EXPERIENCE GROUPED COPY DIVERSITY", prompt)
        self.assertIn("Each concept table must contain exactly three completed rows.", prompt)
        self.assertIn("The full response must contain exactly nine complete ad-copy combinations.", prompt)
        self.assertIn("No row may be placeholder copy.", prompt)
        self.assertNotIn("PRIMARY TEXT VARIATIONS\n\nVariation 1:", prompt)
        self.assertNotIn("Return one final primary text only.", prompt)

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
            "SPORTS CAVE BASEBALL SINGLE IMAGE VIDEO WINNER PATTERN",
            ads_page.build_ads_prompt(
                "Baseball Product",
                "Baseball",
                "USA",
                "Single Image / Video",
                product_url="https://sportscave.com.au/products/baseball-product",
            ),
        )
        self.assertIn(
            "SPORTS CAVE NBA INSTANT EXPERIENCE STANDARD WORKFLOW",
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

    def test_empty_campaign_moment_preserves_existing_prompt_output(self):
        base_prompt = ads_page.build_ads_prompt(
            "Six Laps Ahead",
            "Motorsport",
            "Australia",
            "Carousel",
            variation_token="no-moment-test",
        )
        empty_prompt = ads_page.build_ads_prompt(
            "Six Laps Ahead",
            "Motorsport",
            "Australia",
            "Carousel",
            variation_token="no-moment-test",
            campaign_moment=ads_page.empty_campaign_moment(),
        )

        self.assertEqual(empty_prompt, base_prompt)
        self.assertNotIn("CAMPAIGN MOMENT", empty_prompt)

    def test_campaign_moment_type_without_name_triggers_validation(self):
        message = ads_page.validate_campaign_moment(
            {"type": "Sporting Event"},
            selected_country="Australia",
        )

        self.assertEqual(
            message,
            "Enter the specific campaign moment, such as Father’s Day or NBA Playoffs.",
        )

    def test_expired_campaign_moment_is_blocked_from_timely_prompt_use(self):
        message = ads_page.validate_campaign_moment(
            {
                "type": "Sale Period",
                "name": "Black Friday",
                "date": "2026-01-01",
            },
            selected_country="Australia",
            today=date(2026, 7, 29),
        )

        self.assertEqual(
            message,
            "This campaign moment has expired. Update the date or remove the moment before generating timely copy.",
        )

    def test_campaign_moment_copy_layer_reaches_all_campaign_types(self):
        moment = {
            "type": "Gifting Occasion",
            "name": "Father’s Day",
            "market": "Australia",
            "date": "2026-09-06",
            "strength": "Subtle",
        }

        for campaign_type in ("Carousel", "Instant Experience", "Single Image / Video"):
            with self.subTest(campaign_type=campaign_type):
                prompt = ads_page.build_ads_prompt(
                    "Six Laps Ahead",
                    "Motorsport",
                    "Australia",
                    campaign_type,
                    variation_token=f"moment-{campaign_type}",
                    campaign_moment=moment,
                )

                self.assertIn("CAMPAIGN MOMENT — OPTIONAL RELEVANCE LAYER", prompt)
                self.assertIn("- Moment type: Gifting Occasion", prompt)
                self.assertIn("- Moment name: Father’s Day", prompt)
                self.assertIn("- Relevant market: Australia", prompt)
                self.assertIn("- Event/end date: 2026-09-06", prompt)
                self.assertIn("- Confirmed promotion: none supplied", prompt)
                self.assertIn("- Relevance strength: Subtle", prompt)
                self.assertIn("Use this moment in exactly one primary ad-text variation", prompt)
                self.assertIn("1. Evergreen emotional/nostalgia angle", prompt)
                self.assertIn("2. Evergreen collector, product or fan-identity angle", prompt)
                self.assertIn("3. Timely angle", prompt)
                self.assertIn("At least two evergreen primary-text variations", prompt)

    def test_campaign_moment_strengths_have_distinct_instruction_contracts(self):
        for strength, expected in (
            ("Subtle", "Mention the moment naturally and briefly in one variation."),
            ("Moderate", "Make one variation clearly connected to the moment"),
            ("Campaign-led", "Make one variation primarily built around the selected moment"),
        ):
            with self.subTest(strength=strength):
                block = ads_page.build_campaign_moment_copy_relevance_block(
                    {
                        "type": "Seasonal Moment",
                        "name": "Christmas",
                        "strength": strength,
                    },
                    selected_country="Australia",
                )

                self.assertIn(f"- Relevance strength: {strength}", block)
                self.assertIn(expected, block)
                self.assertIn("Preserve two evergreen alternatives.", block)

    def test_blank_promotion_cannot_create_offer_claims_and_exact_promotion_passes_through(self):
        blank_block = ads_page.build_campaign_moment_copy_relevance_block(
            {
                "type": "Sporting Event",
                "name": "NBA Playoffs",
                "market": "USA",
                "strength": "Moderate",
            },
            selected_country="USA",
        )
        offer_block = ads_page.build_campaign_moment_copy_relevance_block(
            {
                "type": "Sale Period",
                "name": "Black Friday",
                "market": "Global",
                "promotion": "Free shipping",
                "strength": "Campaign-led",
            },
            selected_country="Australia",
        )

        self.assertIn("- Confirmed promotion: none supplied", blank_block)
        self.assertIn("do not create a discount, free-shipping claim", blank_block)
        self.assertIn("- Confirmed promotion: Free shipping", offer_block)
        self.assertIn("Only use the exact promotion entered by the user.", offer_block)

    def test_campaign_moment_excludes_image_prompts_until_image_toggle_is_enabled(self):
        moment = {
            "type": "Gifting Occasion",
            "name": "Father’s Day",
            "market": "Australia",
            "strength": "Subtle",
            "include_in_image_prompts": False,
        }
        prompt = ads_page.build_ads_prompt(
            "Six Laps Ahead",
            "Motorsport",
            "Australia",
            "Carousel",
            variation_token="moment-image-off",
            campaign_moment=moment,
        )
        contract = visual_contract(prompt)

        self.assertNotIn("Father’s Day", contract)
        self.assertNotIn("CAMPAIGN MOMENT VISUAL CONTEXT", contract)
        self.assertIn("SQUARE FORMAT — MANDATORY:", contract)
        self.assertIn("CARD 1 CLOSE-UP PRODUCT HERO LOCK — MANDATORY:", contract)
        self.assertIn("PRODUCT DOMINANCE PRINCIPLE — MANDATORY:", contract)

    def test_campaign_moment_image_toggle_adds_restrained_visual_context(self):
        moment = {
            "type": "Sporting Event",
            "name": "Bathurst",
            "market": "Australia",
            "strength": "Moderate",
            "include_in_image_prompts": True,
        }
        prompt = ads_page.build_ads_prompt(
            "Six Laps Ahead",
            "Motorsport",
            "Australia",
            "Carousel",
            variation_token="moment-image-on",
            campaign_moment=moment,
        )
        contract = visual_contract(prompt)

        self.assertEqual(
            contract.count("CAMPAIGN MOMENT VISUAL CONTEXT — OPTIONAL:"),
            ads_page.CAROUSEL_CARD_COUNT,
        )
        self.assertIn("The selected campaign moment is Bathurst for Australia.", contract)
        self.assertIn("The framed artwork must remain the visual hero.", contract)
        self.assertIn("Do not add official event logos, trademarks, branded graphics", contract)
        self.assertIn("Do not make every room look themed.", contract)
        self.assertIn("SQUARE FORMAT — MANDATORY:", contract)
        self.assertIn("CARD 5 PRODUCT-PROMINENT SCARCITY COMPOSITION — MANDATORY:", contract)

    def test_campaign_moment_visual_context_can_reach_single_prompt_campaigns_when_enabled(self):
        moment = {
            "type": "Product Drop",
            "name": "Launch Week",
            "market": "Global",
            "include_in_image_prompts": True,
        }

        for campaign_type in ("Instant Experience", "Single Image / Video"):
            with self.subTest(campaign_type=campaign_type):
                prompt = ads_page.build_ads_prompt(
                    "Collector Test Product",
                    "Cricket",
                    "New Zealand",
                    campaign_type,
                    variation_token=f"single-visual-{campaign_type}",
                    campaign_moment=moment,
                )
                contract = visual_contract(prompt)

                self.assertIn("CAMPAIGN MOMENT VISUAL CONTEXT — OPTIONAL:", contract)
                self.assertIn("Launch Week for Global", contract)
                self.assertIn("Do not automatically place the event name as text inside the image.", contract)

    def test_campaign_moment_result_storage_legacy_compatibility_and_clear_action(self):
        moment = {
            "type": "Sale Period",
            "name": "Black Friday",
            "market": "Global",
            "promotion": "Free shipping",
            "strength": "Campaign-led",
            "include_in_image_prompts": True,
        }
        result = ads_page.build_ads_result_record(
            "Six Laps Ahead",
            "Motorsport",
            "Australia",
            "Carousel",
            product_id="product-123",
            product_url="https://sportscave.com.au/products/six-laps-ahead",
            variation_token="moment-storage-test",
            campaign_moment=moment,
        )

        self.assertEqual(result["campaign_moment"]["name"], "Black Friday")
        self.assertEqual(result["campaign_moment"]["promotion"], "Free shipping")
        self.assertTrue(result["campaign_moment"]["include_in_image_prompts"])
        self.assertIn("CAMPAIGN MOMENT — OPTIONAL RELEVANCE LAYER", result["master_prompt"])

        legacy_moment = ads_page.campaign_moment_from_result({})
        self.assertFalse(ads_page.campaign_moment_is_active(legacy_moment))
        self.assertEqual(legacy_moment["market"], "Use selected ad country")

        session_state = {
            "ads_product_name": "Six Laps Ahead",
            "ads_campaign_moment_type": "Sale Period",
            "ads_campaign_moment_name": "Black Friday",
            "ads_campaign_moment_market": "Global",
            "ads_campaign_moment_date": date(2026, 11, 27),
            "ads_campaign_moment_promotion": "Free shipping",
            "ads_campaign_moment_strength": "Campaign-led",
            "ads_campaign_moment_include_images": True,
        }
        with patch.object(ads_page.st, "session_state", session_state):
            ads_page.clear_campaign_moment_state()

        self.assertEqual(session_state, {"ads_product_name": "Six Laps Ahead"})

    def test_campaign_moment_safety_rules_prevent_invention_and_unsupported_claims(self):
        block = ads_page.build_campaign_moment_copy_relevance_block(
            {
                "type": "Sporting Event",
                "name": "World Cup",
                "market": "UK",
                "date": "2026-07-19",
            },
            selected_country="UK",
        )

        self.assertIn("Never invent event dates, match results, teams", block)
        self.assertIn("Never claim a product is officially licensed, endorsed by or affiliated", block)
        self.assertIn("Do not convert a normal product into a \"Father’s Day Edition\"", block)
        self.assertIn("Do not claim \"ends soon\", \"last chance\" or \"final hours\"", block)
        self.assertIn("football\" for the UK", block)

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

    def test_edition_ops_product_dropdown_preserves_duplicate_titles_with_handles(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot_path = Path(temp_dir) / "edition_ops_products_snapshot.json"
            snapshot_path.write_text(
                json.dumps(
                    {
                        "rows": [
                            {"product_title": "Untitled Product", "shopify_handle": "legends-never-die"},
                            {"product_title": "Untitled Product", "shopify_handle": "goat-debate-wall-art"},
                            {"product_title": "Peter Brock Six Laps Ahead", "shopify_handle": "six-laps-ahead"},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            names = ads_page.load_edition_ops_product_name_options(snapshot_path)

        self.assertEqual(
            names,
            [
                "Untitled Product (legends-never-die)",
                "Untitled Product (goat-debate-wall-art)",
                "Peter Brock Six Laps Ahead",
            ],
        )

    def test_ads_product_name_input_uses_searchable_edition_ops_options_when_available(self):
        source = (ROOT / "ads_page.py").read_text(encoding="utf-8")

        self.assertIn("def render_product_name_input", source)
        self.assertIn("load_edition_ops_product_name_options(rows=rows)", source)
        self.assertIn('st.selectbox(\n            "Product name"', source)
        self.assertIn("accept_new_options=True", source)
        self.assertIn('filter_mode="fuzzy"', source)
        self.assertIn("EDITION_OPS_SNAPSHOT_PATH", source)
        self.assertNotIn("import edition_ops", source)

    def test_shared_live_catalogue_joins_authoritative_product_url(self):
        captured = {}
        expected_rows = [
            {
                "shopify_product_id": "product-123",
                "product_title": "Six Laps Ahead",
                "product_handle": "six-laps-ahead",
                "online_store_url": "https://sportscave.com.au/products/six-laps-ahead",
            }
        ]

        class FakeCursor:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def execute(self, query):
                captured["query"] = query

            def fetchall(self):
                return expected_rows

        class FakeConnection:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def cursor(self):
                return FakeCursor()

        ads_product_catalog.load_live_edition_product_rows.clear()
        try:
            with (
                patch("supabase_backend.is_configured", return_value=True),
                patch("supabase_backend.connect", return_value=FakeConnection()),
            ):
                rows = ads_product_catalog.load_live_edition_product_rows()
        finally:
            ads_product_catalog.load_live_edition_product_rows.clear()

        self.assertEqual(rows, expected_rows)
        self.assertIn("FULL OUTER JOIN shopify_products", captured["query"])
        self.assertIn("sp.online_store_url", captured["query"])

    def test_social_media_and_ads_share_the_authoritative_product_rows(self):
        rows = [
            {
                "shopify_product_id": "product-123",
                "product_title": "Six Laps Ahead",
                "online_store_url": "https://sportscave.com.au/products/six-laps-ahead",
            }
        ]

        with patch.object(
            social_media_catalog,
            "load_live_edition_product_rows",
            return_value=rows,
        ):
            self.assertEqual(social_media_catalog._database_products(), rows)

    def test_edition_ops_dropdown_combines_live_catalogue_with_snapshot_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot_path = Path(temp_dir) / "edition_ops_products_snapshot.json"
            snapshot_path.write_text(
                json.dumps(
                    {
                        "rows": [
                            {
                                "product_title": "Snapshot Product",
                                "shopify_handle": "snapshot-product",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            names = ads_page.load_edition_ops_product_name_options(
                snapshot_path,
                live_loader=lambda: [
                    {
                        "product_title": "Live Product",
                        "product_handle": "live-product",
                    },
                    {
                        "product_title": "Snapshot Product",
                        "shopify_handle": "snapshot-product",
                    },
                ],
            )

        self.assertEqual(names, ["Live Product", "Snapshot Product"])

    def test_selected_edition_ops_product_id_is_persisted_with_generated_result(self):
        with patch(
            "ads_page.load_edition_ops_product_rows",
            return_value=[
                {
                    "product_id": "product-123",
                    "product_title": "Six Laps Ahead",
                    "shopify_handle": "six-laps-ahead",
                }
            ],
        ):
            product_id = ads_page.resolve_edition_ops_product_id("Six Laps Ahead")
        result = ads_page.build_ads_result_record(
            "Six Laps Ahead",
            "Motorsport",
            "Australia",
            "Carousel",
            product_id=product_id,
            variation_token="product-id-test",
        )

        self.assertEqual(result["product_id"], "product-123")
        self.assertEqual(result["product_name"], "Six Laps Ahead")
        self.assertEqual(result["variation_token"], "product-id-test")

    def test_selected_edition_ops_product_url_autofills_from_record(self):
        rows = [
            {
                "product_id": "product-123",
                "product_title": "Six Laps Ahead",
                "shopify_handle": "six-laps-ahead",
                "online_store_url": "https://sportscave.com.au/products/six-laps-ahead",
            }
        ]
        session_state = {}

        with patch.object(ads_page.st, "session_state", session_state):
            state = ads_page.prepare_ads_product_url_state("Six Laps Ahead", rows=rows)

        self.assertEqual(state["product_id"], "product-123")
        self.assertEqual(
            session_state[ads_page.ADS_PRODUCT_URL_KEY],
            "https://sportscave.com.au/products/six-laps-ahead",
        )
        self.assertEqual(session_state[ads_page.ADS_PRODUCT_URL_AUTOFILL_PRODUCT_KEY], "product-123")
        self.assertEqual(state["message"], "")

    def test_ads_product_url_manual_edit_survives_reruns_until_product_changes(self):
        rows = [
            {
                "product_id": "product-123",
                "product_title": "Six Laps Ahead",
                "online_store_url": "https://sportscave.com.au/products/six-laps-ahead",
            },
            {
                "product_id": "product-456",
                "product_title": "Bathurst Winner",
                "online_store_url": "https://sportscave.com.au/products/bathurst-winner",
            },
        ]
        session_state = {}

        with patch.object(ads_page.st, "session_state", session_state):
            ads_page.prepare_ads_product_url_state("Six Laps Ahead", rows=rows)
            session_state[ads_page.ADS_PRODUCT_URL_KEY] = "https://sportscave.com.au/products/manual-campaign-url"
            ads_page.prepare_ads_product_url_state("Six Laps Ahead", rows=rows)

            self.assertEqual(
                session_state[ads_page.ADS_PRODUCT_URL_KEY],
                "https://sportscave.com.au/products/manual-campaign-url",
            )

            ads_page.prepare_ads_product_url_state("Bathurst Winner", rows=rows)

        self.assertEqual(
            session_state[ads_page.ADS_PRODUCT_URL_KEY],
            "https://sportscave.com.au/products/bathurst-winner",
        )
        self.assertEqual(session_state[ads_page.ADS_PRODUCT_URL_AUTOFILL_PRODUCT_KEY], "product-456")

    def test_ads_product_url_handles_missing_url_and_cleared_product(self):
        rows = [
            {
                "product_id": "product-empty",
                "product_title": "No URL Product",
                "online_store_url": "not-a-url",
            }
        ]
        session_state = {
            ads_page.ADS_PRODUCT_URL_KEY: "https://sportscave.com.au/products/manual-url",
            ads_page.ADS_PRODUCT_URL_AUTOFILL_PRODUCT_KEY: "previous-product",
        }

        with patch.object(ads_page.st, "session_state", session_state):
            state = ads_page.prepare_ads_product_url_state("No URL Product", rows=rows)

            self.assertEqual(session_state[ads_page.ADS_PRODUCT_URL_KEY], "")
            self.assertEqual(state["message"], ads_page.NO_EDITION_OPS_PRODUCT_URL_MESSAGE)

            session_state[ads_page.ADS_PRODUCT_URL_KEY] = "https://sportscave.com.au/products/manual-url"
            session_state[ads_page.ADS_PRODUCT_URL_AUTOFILL_PRODUCT_KEY] = "product-empty"
            ads_page.prepare_ads_product_url_state("", rows=rows)

        self.assertEqual(session_state[ads_page.ADS_PRODUCT_URL_KEY], "")
        self.assertEqual(session_state[ads_page.ADS_PRODUCT_URL_AUTOFILL_PRODUCT_KEY], "")

    def test_existing_ads_draft_preserves_saved_url_until_product_changes(self):
        rows = [
            {
                "product_id": "product-123",
                "product_title": "Six Laps Ahead",
                "online_store_url": "https://sportscave.com.au/products/edition-ops-url",
            },
            {
                "product_id": "product-456",
                "product_title": "Bathurst Winner",
                "online_store_url": "https://sportscave.com.au/products/bathurst-winner",
            },
        ]
        result = {
            "product_id": "product-123",
            "product_name": "Six Laps Ahead",
            "product_url": "https://sportscave.com.au/products/saved-draft-url",
        }
        session_state = {}

        with patch.object(ads_page.st, "session_state", session_state):
            ads_page.prepare_ads_product_url_state("Six Laps Ahead", result=result, rows=rows)

            self.assertEqual(
                session_state[ads_page.ADS_PRODUCT_URL_KEY],
                "https://sportscave.com.au/products/saved-draft-url",
            )

            ads_page.prepare_ads_product_url_state("Bathurst Winner", result=result, rows=rows)

        self.assertEqual(
            session_state[ads_page.ADS_PRODUCT_URL_KEY],
            "https://sportscave.com.au/products/bathurst-winner",
        )

    def test_duplicate_ads_product_names_resolve_url_through_stable_record(self):
        rows = [
            {
                "product_id": "product-a",
                "product_title": "Untitled Product",
                "shopify_handle": "legends-never-die",
                "online_store_url": "https://sportscave.com.au/products/legends-never-die",
            },
            {
                "product_id": "product-b",
                "product_title": "Untitled Product",
                "shopify_handle": "goat-debate-wall-art",
                "online_store_url": "https://sportscave.com.au/products/goat-debate-wall-art",
            },
        ]

        selection = ads_page.resolve_edition_ops_product_selection(
            "Untitled Product (goat-debate-wall-art)",
            rows=rows,
        )

        self.assertEqual(selection["product_id"], "product-b")
        self.assertEqual(selection["record_key"], "product-b")
        self.assertEqual(
            selection["product_url"],
            "https://sportscave.com.au/products/goat-debate-wall-art",
        )

    def test_stable_product_id_resolves_ambiguous_display_name(self):
        rows = [
            {
                "product_id": "product-a",
                "product_title": "Untitled Product",
                "shopify_handle": "legends-never-die",
                "online_store_url": "https://sportscave.com.au/products/legends-never-die",
            },
            {
                "product_id": "product-b",
                "product_title": "Untitled Product",
                "shopify_handle": "goat-debate-wall-art",
                "online_store_url": "https://sportscave.com.au/products/goat-debate-wall-art",
            },
        ]

        unresolved = ads_page.resolve_edition_ops_product_selection(
            "Untitled Product",
            rows=rows,
        )
        resolved = ads_page.resolve_edition_ops_product_selection(
            "Untitled Product",
            rows=rows,
            product_id="product-b",
        )

        self.assertIsNone(unresolved["row"])
        self.assertEqual(resolved["product_id"], "product-b")
        self.assertEqual(
            resolved["product_url"],
            "https://sportscave.com.au/products/goat-debate-wall-art",
        )

    def test_legacy_exact_name_matching_handles_punctuation_without_fuzzy_collisions(self):
        rows = [
            {
                "product_title": "Driver’s Legacy – 1998",
                "online_store_url": "https://sportscave.com.au/products/drivers-legacy-1998",
            },
            {
                "product_title": "Driver’s Legacy – 1998 Revisited",
                "online_store_url": "https://sportscave.com.au/products/drivers-legacy-revisited",
            },
        ]

        selection = ads_page.resolve_edition_ops_product_selection(
            "  DRIVER'S LEGACY - 1998  ",
            rows=rows,
        )
        similar_name = ads_page.resolve_edition_ops_product_selection(
            "Driver's Legacy",
            rows=rows,
        )

        self.assertEqual(
            selection["product_url"],
            "https://sportscave.com.au/products/drivers-legacy-1998",
        )
        self.assertIsNone(similar_name["row"])

    def test_unknown_product_change_clears_previous_manual_url_and_shows_message(self):
        rows = [
            {
                "product_id": "product-a",
                "product_title": "Known Product",
                "online_store_url": "https://sportscave.com.au/products/known-product",
            }
        ]
        session_state = {}

        with patch.object(ads_page.st, "session_state", session_state):
            ads_page.prepare_ads_product_url_state("Known Product", rows=rows)
            session_state[ads_page.ADS_PRODUCT_URL_KEY] = (
                "https://sportscave.com.au/products/manual-campaign-url"
            )
            state = ads_page.prepare_ads_product_url_state("Unknown Product", rows=rows)

        self.assertEqual(session_state[ads_page.ADS_PRODUCT_URL_KEY], "")
        self.assertEqual(state["message"], ads_page.NO_EDITION_OPS_PRODUCT_URL_MESSAGE)

    def test_product_url_flows_to_ads_and_instant_experience_destination_output(self):
        product_url = "https://sportscave.com.au/products/six-laps-ahead"
        prompt = ads_page.build_ads_prompt(
            "Six Laps Ahead",
            "Motorsport",
            "Australia",
            "Instant Experience",
            product_url=product_url,
            variation_token="product-url-flow",
        )

        self.assertIn(product_url, prompt)
        self.assertIn(ads_page.META_AD_URL_PARAMETERS, prompt)

    def test_ads_product_url_state_is_prepared_before_widget_render(self):
        source = (ROOT / "ads_page.py").read_text(encoding="utf-8")
        render_page_source = source[source.index("def render_page") :]
        prepare_call = "product_url_state = prepare_ads_product_url_state("
        url_widget = 'product_url = st.text_input(\n        "Product page URL *"'

        self.assertIn(prepare_call, render_page_source)
        self.assertIn("rows=product_rows", render_page_source)
        self.assertIn(url_widget, render_page_source)
        self.assertLess(render_page_source.index(prepare_call), render_page_source.index(url_widget))
        self.assertNotIn(
            "st.session_state[ADS_PRODUCT_URL_KEY]",
            render_page_source[render_page_source.index(url_widget) :],
        )

    def test_carousel_visual_contract_has_exactly_five_card_matched_prompts(self):
        prompt = ads_page.build_ads_prompt(
            "Six Laps Ahead",
            "Motorsport",
            "Australia",
            "Carousel",
            variation_token="carousel-test",
        )
        contract = visual_contract(prompt)
        expected_roles = (
            "Product Identity",
            "Race Or Moment",
            "Legacy",
            "Fan Ownership",
            "Scarcity",
        )

        self.assertEqual(
            contract.count("IMAGE GENERATION PROMPTS — COPY ONE AT A TIME"),
            1,
        )
        for index, role in enumerate(expected_roles, start=1):
            self.assertEqual(
                contract.count(f"CARD {index} IMAGE GENERATION PROMPT"),
                1,
            )
            self.assertIn(f"Approved card role: {role}", contract)
            self.assertIn("Selected Sports Cave product: Six Laps Ahead", contract)
            self.assertIn("Selected sport: Motorsport", contract)
            self.assertIn("Selected market: Australia", contract)
        self.assertIn(
            "A Creative direction line may remain in the card-copy section as supplementary context, "
            "but it can never substitute for, abbreviate or satisfy the required standalone image prompt.",
            contract,
        )
        self.assertIn("Do not output only Creative direction.", contract)
        self.assertIn("Do not output one shared prompt followed by five short variations.", contract)
        self.assertIn("Return exactly these five image-prompt entries and no sixth prompt.", contract)

    def test_every_carousel_card_prompt_has_mandatory_square_format_lock(self):
        contract = visual_contract(
            ads_page.build_ads_prompt(
                "Six Laps Ahead",
                "Motorsport",
                "Australia",
                "Carousel",
                variation_token="square-lock-test",
            )
        )
        sections = carousel_prompt_card_sections(contract)
        final_check = ads_page.build_carousel_final_square_format_check()

        self.assertEqual(contract.count("SQUARE FORMAT — MANDATORY:"), ads_page.CAROUSEL_CARD_COUNT)
        self.assertEqual(contract.count(final_check), ads_page.CAROUSEL_CARD_COUNT)
        for index, section in sections.items():
            with self.subTest(card=index):
                self.assertIn("true 1:1 square canvas", section)
                self.assertIn("1024 × 1024", section)
                self.assertIn("1:1 square", section)
                self.assertIn("width and height are identical", section)
                self.assertIn(final_check, section)

    def test_carousel_card_one_uses_mockups_close_up_foundation_with_close_lock_only(self):
        contract = visual_contract(
            ads_page.build_ads_prompt(
                "Final Whistle Glory",
                "Football",
                "UK",
                "Carousel",
                variation_token="card-one-product-hero-test",
            )
        )
        sections = carousel_prompt_card_sections(contract)
        card_one = sections[1]

        self.assertIn("CARD 1 CLOSE-UP PRODUCT HERO LOCK — MANDATORY:", card_one)
        self.assertIn("Mockups/Reel Close-Up Premium Wall Shot", card_one)
        self.assertIn("MOCKUPS CLOSE-UP WALL SHOT FOUNDATION — REUSED:", card_one)
        self.assertIn("Use only the framed artwork on a premium textured wall.", card_one)
        self.assertIn("No room decor.", card_one)
        self.assertIn("No furniture.", card_one)
        self.assertIn("The frame should be the hero of the image.", card_one)
        self.assertIn("approximately 65-80% of the useful square composition", card_one)
        self.assertIn("Keep all four outer frame edges and all four corners completely visible.", card_one)
        self.assertIn("Use an almost perfectly straight-on camera position", card_one)
        self.assertIn("premium 70-85 mm product-photography lens", card_one)
        self.assertIn("No wide-angle room view.", card_one)
        self.assertIn("No room-establishing composition.", card_one)
        self.assertIn("Do not generate an entry gallery, living room, office, man cave, home bar", card_one)
        self.assertIn("Show the complete outer frame without cropping any edge.", card_one)
        self.assertIn("Avoid wide establishing shots.", card_one)
        self.assertIn("Use the uploaded framed product as the exact compositing source.", card_one)
        self.assertIn("Preserve the entire original frame and everything inside it exactly", card_one)
        self.assertIn("Card 1 must resemble genuine commercial product photography.", card_one)
        self.assertIn("Retain all existing product-lock and artwork-preservation instructions.", card_one)

        for index in range(2, ads_page.CAROUSEL_CARD_COUNT + 1):
            with self.subTest(card=index):
                self.assertIn("SQUARE FORMAT — MANDATORY:", sections[index])
                self.assertNotIn("CARD 1 CLOSE-UP PRODUCT HERO LOCK — MANDATORY:", sections[index])
                self.assertNotIn("MOCKUPS CLOSE-UP WALL SHOT FOUNDATION — REUSED:", sections[index])
                self.assertNotIn("approximately 65-80% of the useful square composition", sections[index])

    def test_every_carousel_card_prompt_has_product_dominance_lock(self):
        contract = visual_contract(
            ads_page.build_ads_prompt(
                "Final Whistle Glory",
                "Football",
                "USA",
                "Carousel",
                variation_token="product-dominance-test",
            )
        )
        sections = carousel_prompt_card_sections(contract)

        self.assertEqual(
            contract.count("PRODUCT DOMINANCE PRINCIPLE — MANDATORY:"),
            ads_page.CAROUSEL_CARD_COUNT,
        )
        for index, section in sections.items():
            with self.subTest(card=index):
                self.assertIn("We are selling the framed Sports Cave edition, not the room.", section)
                self.assertIn("must never overpower the framed artwork or make it look small", section)
                self.assertIn("dominant, instantly recognizable and readable", section)
                self.assertIn("without creating distant product shots", section)

    def test_carousel_card_distance_rules_keep_products_dominant(self):
        contract = visual_contract(
            ads_page.build_ads_prompt(
                "Six Laps Ahead",
                "Motorsport",
                "Australia",
                "Carousel",
                variation_token="card-distance-test",
            )
        )
        sections = carousel_prompt_card_sections(contract)

        self.assertIn("approximately 65-80% of the useful square composition", sections[1])
        self.assertIn("must be a premium close-up product photograph", sections[1])
        for index in (2, 3, 4):
            with self.subTest(card=index):
                self.assertIn("CARDS 2-4 PRODUCT-DOMINANT LIFESTYLE COMPOSITION — MANDATORY:", sections[index])
                self.assertIn("medium or medium-close lifestyle composition, not a distant wide-angle room shot", sections[index])
                self.assertIn("approximately 45-65% of the useful square composition", sections[index])
                self.assertIn("small Facebook carousel card on a phone", sections[index])
                self.assertIn("Never use an extreme wide shot", sections[index])
                self.assertIn("Keep the complete outer frame visible", sections[index])
                self.assertNotIn("approximately 65-80% of the useful square composition", sections[index])

        self.assertIn("CARD 5 PRODUCT-PROMINENT SCARCITY COMPOSITION — MANDATORY:", sections[5])
        self.assertIn("dramatic product-led scarcity image using a close or medium-close composition", sections[5])
        self.assertIn("must remain one of the largest elements", sections[5])
        self.assertIn("must not become secondary to scarcity messaging", sections[5])
        self.assertIn("never invent, replace or modify an edition number", sections[5])
        self.assertIn("Do not zoom out significantly farther than Cards 2-4.", sections[5])
        self.assertIn("Keep the complete outer frame visible", sections[5])
        self.assertNotIn("approximately 65-80% of the useful square composition", sections[5])

    def test_every_carousel_card_prompt_has_strict_product_lock_and_photorealism(self):
        contract = visual_contract(
            ads_page.build_ads_prompt(
                "Collector Test Product",
                "Cricket",
                "New Zealand",
                "Carousel",
                variation_token="carousel-product-realism-test",
            )
        )
        sections = carousel_prompt_card_sections(contract)

        self.assertEqual(contract.count("STRICT PRODUCT LOCK — MANDATORY:"), ads_page.CAROUSEL_CARD_COUNT)
        self.assertEqual(
            contract.count("CAROUSEL PHOTOREALISM REQUIREMENTS — MANDATORY:"),
            ads_page.CAROUSEL_CARD_COUNT,
        )
        for index, section in sections.items():
            with self.subTest(card=index):
                self.assertIn("Create a 1024 × 1024 square image.", section)
                self.assertIn("Selected Sports Cave product: Collector Test Product", section)
                self.assertIn("Selected sport: Cricket", section)
                self.assertIn("Selected market: New Zealand", section)
                self.assertIn("Use the uploaded product image as the exact compositing source.", section)
                self.assertIn("Use the supplied product reference as the exact framed Sports Cave product.", section)
                self.assertIn("Preserve the exact artwork, outer frame, colours, text, typography", section)
                self.assertIn("Do not redraw, regenerate, reinterpret or replace anything inside the frame.", section)
                self.assertIn("Do not change the frame colour, thickness, shape, proportions or material.", section)
                self.assertIn("Keep the complete outer frame visible.", section)
                self.assertIn("The artwork must remain sharp and visually legible.", section)
                self.assertIn("PRODUCT LOCK - INCLUDE IN EVERY RETURNED IMAGE PROMPT", section)
                self.assertIn("FRAME AND GLASS REALISM - INCLUDE IN EVERY RETURNED IMAGE PROMPT", section)
                self.assertIn("DYNAMIC ROOM REALISM - INCLUDE IN EVERY RETURNED IMAGE PROMPT", section)
                self.assertIn("LAST-IMAGE VARIATION LOCK - INCLUDE IN EVERY RETURNED IMAGE PROMPT", section)
                self.assertIn("SPORT AND COUNTRY VISUAL ADAPTATION", section)
                self.assertIn("genuine high-end interior photograph", section)
                self.assertIn("Create realistic contact shadows behind and below the frame.", section)
                self.assertIn("subtle, controlled glass reflections without obscuring the artwork", section)
                self.assertIn("convincing timber depth, sharp corners, natural texture and accurate mounting", section)
                self.assertIn("Avoid warped walls, bent furniture, duplicate objects", section)
                self.assertIn("Do not add people unless the individual carousel concept explicitly requires them", section)
                self.assertIn(ads_page.build_carousel_final_square_format_check(), section)

    def test_carousel_square_lock_reaches_every_category_country_and_role_variation(self):
        for category in ads_page.CATEGORY_OPTIONS[1:]:
            for country in ads_page.COUNTRY_OPTIONS[1:]:
                with self.subTest(category=category, country=country):
                    prompt = ads_page.build_ads_prompt(
                        f"{category} Square Test",
                        category,
                        country,
                        "Carousel",
                        variation_token="all-carousel-square-test",
                    )
                    contract = visual_contract(prompt)
                    sections = carousel_prompt_card_sections(contract)
                    self.assertEqual(len(sections), ads_page.CAROUSEL_CARD_COUNT)
                    for section in sections.values():
                        self.assertIn("SQUARE FORMAT — MANDATORY:", section)
                        self.assertIn("1024 × 1024", section)
                        self.assertIn("1:1 square", section)
                        self.assertIn("PRODUCT DOMINANCE PRINCIPLE — MANDATORY:", section)
                        self.assertIn("STRICT PRODUCT LOCK — MANDATORY:", section)
                        self.assertIn("CAROUSEL PHOTOREALISM REQUIREMENTS — MANDATORY:", section)
                        self.assertIn(ads_page.build_carousel_final_square_format_check(), section)

    def test_non_carousel_visual_contracts_do_not_receive_carousel_square_lock(self):
        instant_contract = visual_contract(
            ads_page.build_ads_prompt(
                "Final Whistle Glory",
                "Football",
                "UK",
                "Instant Experience",
                variation_token="non-carousel-instant-test",
            )
        )
        single_contract = visual_contract(
            ads_page.build_ads_prompt(
                "Final Whistle Glory",
                "Football",
                "UK",
                "Single Image / Video",
                variation_token="non-carousel-single-test",
            )
        )

        for contract in (instant_contract, single_contract):
            self.assertNotIn("SQUARE FORMAT — MANDATORY:", contract)
            self.assertNotIn("CARD 1 CLOSE-UP PRODUCT HERO LOCK — MANDATORY:", contract)
            self.assertNotIn("MOCKUPS CLOSE-UP WALL SHOT FOUNDATION — REUSED:", contract)
            self.assertNotIn("PRODUCT DOMINANCE PRINCIPLE — MANDATORY:", contract)
            self.assertNotIn("CARDS 2-4 PRODUCT-DOMINANT LIFESTYLE COMPOSITION — MANDATORY:", contract)
            self.assertNotIn("CARD 5 PRODUCT-PROMINENT SCARCITY COMPOSITION — MANDATORY:", contract)
            self.assertNotIn("STRICT PRODUCT LOCK — MANDATORY:", contract)
            self.assertNotIn("CAROUSEL PHOTOREALISM REQUIREMENTS — MANDATORY:", contract)
            self.assertNotIn(ads_page.build_carousel_final_square_format_check(), contract)

    def test_mockups_close_up_prompt_foundation_matches_existing_reel_prompt_source(self):
        foundation = image_factory.get_close_up_wall_prompt_foundation()
        prompt_items = image_factory.build_lifestyle_prompt_items(
            "Six Laps Ahead",
            "Motorsport",
            local_only=True,
        )
        close_up_item = next(
            item
            for item in prompt_items
            if item["filename"] == image_factory.CLOSE_UP_WALL_PROMPT_FILENAME
        )

        self.assertIn("Close-Up Premium Wall Shot", close_up_item["label"])
        self.assertIn(foundation, close_up_item["prompt"])
        self.assertIn("create a 1024 x 1024 ultra-realistic close-up lifestyle mockup", foundation)
        self.assertIn("Use only the framed artwork on a premium textured wall.", foundation)

    def test_ads_setup_notes_text_matches_campaign_type_and_pasted_copy(self):
        carousel_result = ads_page.build_ads_result_record(
            "Six Laps Ahead",
            "Motorsport",
            "Australia",
            "Carousel",
            product_url="https://sportscave.com.au/products/six-laps-ahead",
            variation_token="notes-carousel",
        )
        carousel_workflow = {
            "export_date": "2026-07-29",
            "slots": {},
            "outcomes": {},
            "ad_notes": {
                "headlines": "Six Laps\nRace Memory",
                "descriptions": "Built For Fans\nLimited Run",
                "primary_text_variations": (
                    "A collector’s wall deserves this.\n\n"
                    "O’Neal’s legacy — unchanged."
                ),
                "cards": "Card 1: Identity\nCard 2: Moment",
            },
        }

        carousel_notes = ads_page.build_ads_setup_notes_text(carousel_result, carousel_workflow)

        self.assertIn("Campaign type: Carousel", carousel_notes)
        self.assertIn("Six Laps\r\nRace Memory", carousel_notes)
        self.assertIn("Card 1: Identity\r\nCard 2: Moment", carousel_notes)
        self.assertIn(
            "A collector’s wall deserves this.\r\n\r\nO’Neal’s legacy — unchanged.",
            carousel_notes,
        )
        self.assertIn("Carousel setup checklist", carousel_notes)
        self.assertIn("Use exactly 5 carousel cards", carousel_notes)
        headings = (
            "HEADLINES",
            "DESCRIPTIONS",
            "PRIMARY TEXT VARIATIONS",
            "CAROUSEL CARDS / AD SETUP",
        )
        positions = [carousel_notes.index(heading) for heading in headings]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("\n", carousel_notes.replace("\r\n", ""))

        instant_result = ads_page.build_ads_result_record(
            "Final Whistle Glory",
            "Football",
            "UK",
            "Instant Experience",
            product_url="https://sportscave.com.au/products/final-whistle-glory",
            variation_token="notes-instant",
        )
        instant_workflow = {
            "export_date": "2026-07-29",
            "slots": {},
            "outcomes": {},
            "ad_notes": {
                "instant_experience": {
                    "primary_text": [
                        "Primary option 1",
                        "Primary option 2\nwith preserved second line",
                        "Primary option 3",
                        "Primary option 4",
                        "Primary option 5",
                    ],
                    "headlines": [
                        "Headline 1",
                        "Headline 2",
                        "Headline 3",
                        "Headline 4",
                        "Headline 5",
                    ],
                    "call_to_action": [
                        "Shop Now",
                        "Learn More",
                        "View Shop",
                        "See More",
                        "Get Offer",
                    ],
                }
            },
        }

        instant_notes = ads_page.build_ads_setup_notes_text(instant_result, instant_workflow)

        self.assertIn("Campaign type: Instant Experience", instant_notes)
        self.assertIn("INSTANT EXPERIENCE AD COPY", instant_notes)
        self.assertIn("NOSTALGIA — Moment & Memory", instant_notes)
        self.assertIn("VARIATION 1\r\nPRIMARY TEXT:\r\nPrimary option 1", instant_notes)
        self.assertIn("OWNERSHIP — Identity & Display", instant_notes)
        self.assertIn("VARIATION 1\r\nPRIMARY TEXT:\r\nPrimary option 2\r\nwith preserved second line", instant_notes)
        self.assertIn("VARIATION 2\r\nPRIMARY TEXT:\r\nPrimary option 3", instant_notes)
        self.assertIn("SCARCITY — Collector & Limited Edition", instant_notes)
        self.assertIn("VARIATION 1\r\nPRIMARY TEXT:\r\nPrimary option 5", instant_notes)
        self.assertNotIn("DESCRIPTIONS", instant_notes)
        self.assertNotIn("CAROUSEL CARDS / AD SETUP", instant_notes)
        self.assertNotIn("Use exactly 5 carousel cards", instant_notes)

    def test_ads_setup_notes_preserve_user_spacing_and_empty_optional_sections(self):
        result = ads_page.build_ads_result_record(
            "Unicode Collector",
            "Football",
            "UK",
            "Carousel",
            variation_token="notes-preservation",
        )
        workflow = {
            "export_date": "2026-07-31",
            "slots": {},
            "outcomes": {},
            "ad_notes": {
                "headlines": "  Keep leading spaces\nLine with  two spaces  ",
                "descriptions": "",
                "primary_text_variations": "Don’t rewrite this — ever.\n\nCafé supporters’ choice",
                "cards": "Card 1:\tExact tab",
            },
        }

        notes = ads_page.build_ads_setup_notes_text(result, workflow)

        self.assertIn(
            "HEADLINES\r\n\r\n  Keep leading spaces\r\nLine with  two spaces  ",
            notes,
        )
        self.assertIn("DESCRIPTIONS\r\n\r\n[not supplied]", notes)
        self.assertIn(
            "PRIMARY TEXT VARIATIONS\r\n\r\n"
            "Don’t rewrite this — ever.\r\n\r\nCafé supporters’ choice",
            notes,
        )
        self.assertIn("CAROUSEL CARDS / AD SETUP\r\n\r\nCard 1:\tExact tab", notes)

    def test_generic_carousel_visual_contract_preserves_approved_generic_roles(self):
        prompt = ads_page.build_ads_prompt(
            "Final Whistle Glory",
            "Football",
            "UK",
            "Carousel",
            variation_token="generic-carousel-test",
        )
        contract = visual_contract(prompt)

        for role in (
            "Product Identity",
            "Moment / Legacy",
            "Emotional Hook",
            "Fan Ownership",
            "Scarcity",
        ):
            self.assertIn(f"Approved card role: {role}", contract)
        self.assertNotIn("Approved card role: Race Or Moment", contract)

    def test_carousel_visual_contract_requires_distinct_coherent_standalone_rooms(self):
        contract = visual_contract(
            ads_page.build_ads_prompt(
                "Six Laps Ahead",
                "Motorsport",
                "Australia",
                "Carousel",
                variation_token="room-test",
            )
        )

        self.assertIn("The five images must form one premium visual story", contract)
        self.assertIn("Do not merely recolour the same room.", contract)
        self.assertIn("do not repeat a room type, wall treatment, principal furniture arrangement", contract)
        self.assertIn("Every image prompt must be fully standalone.", contract)
        self.assertIn('Never write "same as above"', contract)
        self.assertIn("Normally do not place the card headline or description inside the image", contract)
        self.assertIn("Each visual must clearly support its assigned card message", contract)
        self.assertIn(
            "Card 1 must deliver the strongest immediate product presentation and be the most zoomed-in card",
            contract,
        )
        self.assertIn(
            "Card 5 must deliver the strongest truthful scarcity or final-claim presentation while keeping the product prominent.",
            contract,
        )
        self.assertIn("framed product remains the unmistakable hero", contract)
        self.assertIn("Avoid five near-identical framed mockups", contract)
        self.assertIn("fake edition details", contract)
        self.assertIn(
            "Card 1: product identity and a scroll-stopping close-up hero based on the Mockups/Reel Close-Up Premium Wall Shot.",
            contract,
        )
        self.assertIn("Card 2: the verified moment, era or legacy.", contract)
        self.assertIn("Card 3: an emotional collector hook.", contract)
        self.assertIn("Card 4: fan ownership and how the framed edition commands the wall.", contract)
        self.assertIn("exact generated headline, exact generated description, creative direction", contract)
        self.assertIn("Do not use abstract room symbolism", contract)
        self.assertIn("Never crop the outer frame", contract)

    def test_every_carousel_prompt_has_sequential_photo_variation_lock(self):
        contract = visual_contract(
            ads_page.build_ads_prompt(
                "Six Laps Ahead",
                "Motorsport",
                "Australia",
                "Carousel",
                variation_token="sequential-photo-test",
            )
        )
        sections = carousel_prompt_card_sections(contract)

        self.assertEqual(
            contract.count("SEQUENTIAL PHOTO VARIATION — MANDATORY"),
            ads_page.CAROUSEL_CARD_COUNT,
        )
        self.assertIn(
            "establish the sequence's closest and most product-dominant viewpoint",
            sections[1],
        )
        for index in range(2, ads_page.CAROUSEL_CARD_COUNT + 1):
            with self.subTest(card=index):
                self.assertIn(
                    f"visibly different from the preceding Card {index - 1}",
                    sections[index],
                )
                self.assertIn(
                    "Never create variation by zooming too far out or making the product smaller.",
                    sections[index],
                )

    def test_non_carousel_prompts_do_not_receive_sequential_photo_variation(self):
        for campaign_type in ("Instant Experience", "Single Image / Video"):
            with self.subTest(campaign_type=campaign_type):
                contract = visual_contract(
                    ads_page.build_ads_prompt(
                        "Final Whistle Glory",
                        "Football",
                        "UK",
                        campaign_type,
                        variation_token="no-sequential-photo-test",
                    )
                )
                self.assertNotIn("SEQUENTIAL PHOTO VARIATION — MANDATORY", contract)

    def test_last_image_variation_lock_is_required_inside_every_carousel_prompt(self):
        contract = visual_contract(
            ads_page.build_ads_prompt(
                "Six Laps Ahead",
                "Motorsport",
                "Australia",
                "Carousel",
                variation_token="last-image-test",
            )
        )

        self.assertIn(
            "LAST-IMAGE VARIATION LOCK - INCLUDE IN EVERY RETURNED IMAGE PROMPT",
            contract,
        )
        for instruction in (
            "Analyze the uploaded Sports Cave product image.",
            "previously generated image for this same product",
            "noticeably different house and visual setting",
            "new wall colour and wall material",
            "new lighting direction",
            "new camera height, camera distance and camera angle",
            "Make the difference obvious at thumbnail size.",
            "Never sacrifice the product lock",
        ):
            self.assertIn(instruction, contract)
        self.assertEqual(
            sum(
                contract.count(f"CARD {index} IMAGE GENERATION PROMPT")
                for index in range(1, ads_page.CAROUSEL_CARD_COUNT + 1)
            ),
            ads_page.CAROUSEL_CARD_COUNT,
        )
        for section in carousel_prompt_card_sections(contract).values():
            self.assertIn(
                "LAST-IMAGE VARIATION LOCK - INCLUDE IN EVERY RETURNED IMAGE PROMPT",
                section,
            )
        self.assertIn("No two cards may repeat the room type, house architecture", contract)
        self.assertIn("time-of-day treatment, camera composition, camera height", contract)

    def test_every_visual_contract_contains_product_frame_glass_and_room_realism(self):
        for campaign_type in ("Carousel", "Instant Experience", "Single Image / Video"):
            with self.subTest(campaign_type=campaign_type):
                contract = visual_contract(
                    ads_page.build_ads_prompt(
                        "Collector Test Product",
                        "Cricket",
                        "New Zealand",
                        campaign_type,
                        variation_token="realism-test",
                    )
                )
                if campaign_type == "Instant Experience":
                    self.assertEqual(
                        contract.count(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER),
                        3,
                    )
                    self.assertIn("SPORTS CAVE PRODUCT AND MOCKUP LOCK - MANDATORY", contract)
                    self.assertIn("Do not redesign the artwork.", contract)
                    self.assertIn("FRAME REALISM:", contract)
                    self.assertIn("GLASS REALISM:", contract)
                    self.assertIn("Require realistic transparent glass", contract)
                    self.assertIn("ROOM REALISM:", contract)
                    self.assertIn("Require believable placement", contract)
                else:
                    self.assertIn("PRODUCT LOCK - INCLUDE IN EVERY RETURNED IMAGE PROMPT", contract)
                    self.assertIn("Do not redesign, repaint, redraw, replace, reinterpret or regenerate", contract)
                    self.assertIn("FRAME AND GLASS REALISM - INCLUDE IN EVERY RETURNED IMAGE PROMPT", contract)
                    self.assertIn("real glass over the artwork", contract)
                    self.assertIn("DYNAMIC ROOM REALISM - INCLUDE IN EVERY RETURNED IMAGE PROMPT", contract)
                    self.assertIn("correct ceiling and wall geometry", contract)
                self.assertIn("SPORT AND COUNTRY VISUAL ADAPTATION", contract)
                self.assertIn("Selected country: New Zealand", contract)
                expected_marker_count = 3 if campaign_type == "Instant Experience" else 1
                self.assertEqual(
                    contract.count(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER),
                    expected_marker_count,
                )
                self.assertIn("SPORTS CAVE PRODUCT AND MOCKUP LOCK - MANDATORY", contract)
                self.assertIn("GLOBAL PHOTOGRAPHIC REALISM RULES - MANDATORY", contract)

    def test_ads_visual_contracts_do_not_receive_social_specific_instructions(self):
        social_only_terms = (
            "SPORTS CAVE BRANDING AND OVERLAY PLAN",
            "Native platform stickers",
            "deterministic branded-composition stage",
            "Clean master plus deterministic branded final",
            "Social Media Reels",
        )
        for campaign_type in ("Carousel", "Instant Experience", "Single Image / Video"):
            with self.subTest(campaign_type=campaign_type):
                contract = visual_contract(
                    ads_page.build_ads_prompt(
                        "Collector Test Product",
                        "Cricket",
                        "New Zealand",
                        campaign_type,
                        variation_token="no-social-leak-test",
                    )
                )
                expected_marker_count = 3 if campaign_type == "Instant Experience" else 1
                self.assertEqual(
                    contract.count(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER),
                    expected_marker_count,
                )
                for social_term in social_only_terms:
                    self.assertNotIn(social_term, contract)

    def test_every_ads_prompt_requires_text_first_no_automatic_image_generation(self):
        for campaign_type in ("Carousel", "Instant Experience", "Single Image / Video"):
            with self.subTest(campaign_type=campaign_type):
                contract = visual_contract(
                    ads_page.build_ads_prompt(
                        "Collector Test Product",
                        "Football",
                        "Australia",
                        campaign_type,
                        variation_token="text-first-test",
                    )
                )

                self.assertIn("TEXT-FIRST IMAGE-GENERATION GATE - MANDATORY", contract)
                self.assertIn("Your first response must be text and planning only.", contract)
                self.assertIn("Do not call, invoke, open or use any image-generation tool", contract)
                self.assertIn("Having artwork attached", contract)
                self.assertIn("must not be treated as permission to create an image automatically", contract)
                self.assertIn("Any imperative wording inside an image-prompt block is copy", contract)
                if campaign_type == "Instant Experience":
                    self.assertIn("After GROUP 3 — SCARCITY and the shared INSTANT EXPERIENCE SETUP block are complete, stop.", contract)
                    self.assertNotIn("Would you like me", contract)
                else:
                    self.assertIn('"Would you like me to generate Card 1?"', contract)
                self.assertIn("Then wait for explicit approval before generating anything.", contract)
                self.assertIn('"generate the image now"', contract)
                self.assertIn("generate only that requested image immediately", contract)

    def test_text_first_contract_requires_complete_ad_package_before_images(self):
        contract = visual_contract(
            ads_page.build_ads_prompt(
                "Six Laps Ahead",
                "Motorsport",
                "Australia",
                "Carousel",
                variation_token="package-test",
            )
        )

        for required_item in (
            "Campaign objective and funnel stage.",
            "Target market and audience.",
            "Main emotional/creative angle.",
            "Primary ad text variants.",
            "Headlines.",
            "Description lines.",
            "CTA recommendation.",
            "Optional event or seasonal integration, when supplied.",
            "Card-by-card or creative-by-creative strategy.",
            "The text shown on each creative, where applicable.",
            "A complete production-ready image prompt for every required image.",
            "placement, sizing, export, consistency, artwork-preservation and realism instructions",
        ):
            self.assertIn(required_item, contract)

        self.assertIn("Print every image prompt in full in clearly separated, copyable blocks.", contract)
        self.assertIn("Do not shorten, summarise, collapse or hide them behind buttons.", contract)
        self.assertIn("Every image prompt must be self-contained", contract)
        self.assertIn("fresh ChatGPT conversation", contract)

    def test_carousel_text_first_contract_requires_all_five_card_prompts_first(self):
        prompt = ads_page.build_ads_prompt(
            "Six Laps Ahead",
            "Motorsport",
            "Australia",
            "Carousel",
            variation_token="carousel-text-first-test",
        )
        contract = visual_contract(prompt)

        self.assertIn("For Carousel campaigns, the first text-only response must include", contract)
        self.assertIn("five complete, separately copyable image prompts", contract)
        self.assertIn("Card 1 must remain the strongest, closest and most scroll-stopping product hero", contract)
        self.assertIn("Cards 2-4 may show more environment while keeping the framed artwork dominant", contract)
        self.assertIn("Card 5 must focus on scarcity and final conversion", contract)
        self.assertIn("17-character Carousel headline and description validation", contract)
        self.assertIn("country terminology", contract)
        self.assertIn("optional event relevance", contract)
        self.assertIn("strict artwork lock, frame realism, product dominance and photorealism rules", contract)
        self.assertIn("IMAGE GENERATION PROMPTS — COPY ONE AT A TIME", contract)
        for index in range(1, ads_page.CAROUSEL_CARD_COUNT + 1):
            self.assertIn(f"CARD {index} IMAGE GENERATION PROMPT", contract)
        self.assertNotIn("IMAGE PROMPTS — GENERATE IN THIS ORDER", contract)
        self.assertTrue(
            prompt.rstrip().endswith("Would you like me to generate Card 1?"),
            "The complete text-only package must end with the generation approval question.",
        )

    def test_instant_experience_text_first_contract_uses_grouped_concepts_no_description(self):
        contract = visual_contract(
            ads_page.build_ads_prompt(
                "Collector Test Product",
                "Cricket",
                "UK",
                "Instant Experience",
                variation_token="instant-text-first-test",
            )
        )

        self.assertIn("GROUP 1 — NOSTALGIA with one IMAGE GENERATION PROMPT and one three-row COPY VARIATIONS table.", contract)
        self.assertIn("GROUP 2 — OWNERSHIP with one IMAGE GENERATION PROMPT and one three-row COPY VARIATIONS table.", contract)
        self.assertIn("GROUP 3 — SCARCITY with one IMAGE GENERATION PROMPT and one three-row COPY VARIATIONS table.", contract)
        self.assertIn("Exactly nine complete ad-copy combinations total.", contract)
        self.assertIn("Exactly one shared INSTANT EXPERIENCE SETUP block after the three groups.", contract)
        self.assertIn("No Description or Meta Ad Description field is allowed.", contract)
        self.assertNotIn("6. Description lines.", contract)

    def test_old_cached_result_is_refreshed_to_current_full_visual_prompt_contract(self):
        current = ads_page.build_ads_result_record(
            "Six Laps Ahead",
            "Motorsport",
            "Australia",
            "Carousel",
            product_id="product-123",
            product_url="https://sportscave.com.au/products/six-laps-ahead",
            variation_token="cached-result-test",
        )
        legacy = {
            **current,
            "master_prompt": (
                "OLD CAROUSEL PROMPT\n\nMASTER RESPONSE AND VISUAL OUTPUT CONTRACT\n\n"
                "Card 1 - Product Identity\nCreative direction: Use the framed artwork."
            ),
            "generated_ad_output": (
                "OLD CAROUSEL PROMPT\n\nMASTER RESPONSE AND VISUAL OUTPUT CONTRACT\n\n"
                "Card 1 - Product Identity\nCreative direction: Use the framed artwork."
            ),
        }
        legacy.pop("prompt_contract_version")

        refreshed = ads_page.ensure_current_ads_result_prompt(legacy)

        self.assertEqual(
            refreshed["prompt_contract_version"],
            ads_page.ADS_PROMPT_CONTRACT_VERSION,
        )
        self.assertEqual(refreshed["product_id"], "product-123")
        self.assertEqual(refreshed["variation_token"], "cached-result-test")
        self.assertNotIn("OLD CAROUSEL PROMPT", refreshed["master_prompt"])
        self.assertIn(
            "IMAGE GENERATION PROMPTS — COPY ONE AT A TIME",
            refreshed["master_prompt"],
        )
        for index in range(1, ads_page.CAROUSEL_CARD_COUNT + 1):
            self.assertIn(
                f"CARD {index} IMAGE GENERATION PROMPT",
                refreshed["master_prompt"],
            )

    def test_old_instant_experience_cached_result_refreshes_to_v3_quality_contract(self):
        current = ads_page.build_ads_result_record(
            "Final Whistle Glory",
            "Football",
            "UK",
            "Instant Experience",
            product_id="product-999",
            product_url="https://sportscave.com.au/products/final-whistle-glory",
            variation_token="cached-ie-result-test",
        )
        legacy = {
            **current,
            "prompt_contract_version": current["prompt_contract_version"].replace(
                "ADS INSTANT EXPERIENCE STANDARD V3",
                "ADS INSTANT EXPERIENCE STANDARD V2",
            ),
            "master_prompt": "OLD INSTANT EXPERIENCE PROMPT\n\nDESCRIPTION\n\n1. [description]",
            "generated_ad_output": "OLD INSTANT EXPERIENCE PROMPT\n\nDESCRIPTION\n\n1. [description]",
        }

        refreshed = ads_page.ensure_current_ads_result_prompt(legacy)

        self.assertEqual(
            refreshed["prompt_contract_version"],
            ads_page.ads_prompt_contract_version_for_campaign("Instant Experience"),
        )
        self.assertEqual(refreshed["product_id"], "product-999")
        self.assertEqual(refreshed["variation_token"], "cached-ie-result-test")
        self.assertNotIn("OLD INSTANT EXPERIENCE PROMPT", refreshed["master_prompt"])
        self.assertIn("GROUP 1 — NOSTALGIA", refreshed["master_prompt"])
        self.assertIn("GROUP 2 — OWNERSHIP", refreshed["master_prompt"])
        self.assertIn("GROUP 3 — SCARCITY", refreshed["master_prompt"])
        self.assertIn("| Variation | Primary Text | Headline | CTA |", refreshed["master_prompt"])
        self.assertIn("ADS INSTANT EXPERIENCE STANDARD V3", refreshed["master_prompt"])
        self.assertIn("SPORTS_CAVE_IE_CORE_IMAGE_QUALITY_RULES_V2", refreshed["master_prompt"])
        self.assertEqual(refreshed["master_prompt"].count("Creative concept: Nostalgia"), 1)
        self.assertEqual(refreshed["master_prompt"].count("Creative concept: Ownership"), 1)
        self.assertEqual(refreshed["master_prompt"].count("Creative concept: Scarcity"), 1)
        self.assertNotIn("DESCRIPTION\n\n1. [description]", refreshed["master_prompt"])

    def test_non_carousel_text_first_contract_requires_one_copyable_prompt(self):
        for campaign_type, expected in (
            ("Instant Experience", "one complete standalone cover image prompt followed by a three-row Markdown table"),
            ("Single Image / Video", "one complete, separately copyable, production-ready creative prompt"),
        ):
            with self.subTest(campaign_type=campaign_type):
                contract = visual_contract(
                    ads_page.build_ads_prompt(
                        "Collector Test Product",
                        "Cricket",
                        "UK",
                        campaign_type,
                        variation_token="non-carousel-text-first",
                    )
                )

                self.assertIn(expected, contract)
                if campaign_type == "Instant Experience":
                    self.assertIn("After GROUP 3 — SCARCITY and the shared INSTANT EXPERIENCE SETUP block are complete, stop.", contract)
                else:
                    self.assertIn("before asking for approval to generate anything", contract)
                self.assertNotIn("CARD 1 IMAGE GENERATION PROMPT", contract)

    def test_instant_experience_visual_contract_returns_three_grouped_concept_prompts(self):
        prompt = ads_page.build_ads_prompt(
            "fg",
            "AFL",
            "Australia",
            "Instant Experience",
            variation_token="instant-test",
        )
        contract = visual_contract(prompt)

        self.assertIn("GROUP 1 — NOSTALGIA", contract)
        self.assertIn("GROUP 2 — OWNERSHIP", contract)
        self.assertIn("GROUP 3 — SCARCITY", contract)
        self.assertEqual(contract.count("Creative concept: Nostalgia"), 1)
        self.assertEqual(contract.count("Creative concept: Ownership"), 1)
        self.assertEqual(contract.count("Creative concept: Scarcity"), 1)
        self.assertIn("GROUPED INSTANT EXPERIENCE OUTPUT — COPY ONE CONCEPT AT A TIME", contract)
        self.assertNotIn("IMAGE PROMPTS — GENERATE IN THIS ORDER", contract)
        self.assertIn("Return exactly three complete grouped Instant Experience concepts", contract)
        self.assertIn("Product name: fg", contract)
        self.assertIn("Sport/category: AFL", contract)
        self.assertIn("Country/market: Australia", contract)
        self.assertIn("1024 x 1024 square Meta Instant Experience cover", contract)
        self.assertIn("full-width upper lifestyle/product image across approximately 76-78%", contract)
        self.assertIn("full-width matte-black scarcity strip across the bottom approximately 22-24%", contract)
        self.assertIn("LIMITED TO 100 WORLDWIDE", contract)
        self.assertIn("Once it sells out", contract)
        self.assertIn("CLAIM YOUR EDITION", contract)
        self.assertIn("Selected product name: fg", contract)
        self.assertEqual(contract.count(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER), 3)
        for concept_line in (
            "Creative concept: Nostalgia",
            "Creative concept: Ownership",
            "Creative concept: Scarcity",
        ):
            cover = contract[contract.index(concept_line) :]
            self.assertIn("SPORTS CAVE PRODUCT AND MOCKUP LOCK - MANDATORY", cover)
            self.assertIn("SPORT AND COUNTRY VISUAL ADAPTATION", cover)
        self.assertNotIn("Social Media Reels", contract)
        self.assertNotIn("Six Laps Ahead", contract)

    def test_instant_experience_v2_quality_contracts_are_centralized_and_once_per_cover(self):
        prompt = ads_page.build_ads_prompt(
            "Final Whistle Glory",
            "Football",
            "UK",
            "Instant Experience",
            product_url="https://sportscave.com.au/products/final-whistle-glory",
            variation_token="ie-quality-v2",
        )
        contract = visual_contract(prompt)
        image_markers = (
            ads_page.SPORTS_CAVE_IE_CORE_IMAGE_QUALITY_RULES_V2.splitlines()[0],
            ads_page.SPORTS_CAVE_IE_TYPOGRAPHY_RULES_V2,
            ads_page.SPORTS_CAVE_IE_SET_DIFFERENTIATION_RULES_V2,
            ads_page.SPORTS_CAVE_IE_FINAL_REJECTION_GATE_V2.splitlines()[0],
            SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER,
        )

        self.assertEqual(
            prompt.count(
                ads_page.SPORTS_CAVE_IE_CORE_COPY_QUALITY_RULES_V2.splitlines()[0]
            ),
            1,
        )
        for marker in image_markers:
            self.assertEqual(contract.count(marker), 3, marker)

        group_starts = (
            "GROUP 1 — NOSTALGIA\n\nIMAGE GENERATION PROMPT",
            "GROUP 2 — OWNERSHIP\n\nIMAGE GENERATION PROMPT",
            "GROUP 3 — SCARCITY\n\nIMAGE GENERATION PROMPT",
        )
        for group_start in group_starts:
            start = contract.index(group_start)
            cover_prompt = contract[start : contract.index("COPY VARIATIONS", start)]
            for marker in image_markers:
                self.assertEqual(cover_prompt.count(marker), 1, (group_start, marker))

        self.assertEqual(
            contract.count("| Variation | Primary Text | Headline | CTA |"),
            3,
        )
        self.assertIn("ADS INSTANT EXPERIENCE STANDARD V3", contract)

    def test_instant_experience_v2_image_contract_strengthens_source_and_room_physics(self):
        prompt = ads_page.build_ads_prompt(
            "Collector Test Product",
            "Baseball",
            "USA",
            "Instant Experience",
            variation_token="ie-physics-v2",
        )

        for expected in (
            "one immutable photographic source asset",
            "Isolate the complete product from its original surrounding wall",
            "Retain the uploaded product pixels wherever technically possible",
            "Keep all four outside frame edges visible",
            "one rigid rectangular object",
            "approximately 8-15 mm from the wall",
            "one identifiable primary light source",
            "no more than one secondary practical light source",
            "remain confined to the glass surface",
            "generic AI luxury-room formula",
            "Use no more than two secondary decorative objects",
            "must not resemble a showroom, furniture catalogue or AI staging template",
        ):
            self.assertIn(expected, prompt)

        self.assertIn("If native generation returns another square size", prompt)
        self.assertIn("exactly 1024 x 1024 pixels", prompt)
        self.assertIn("The workflow must correct failures", prompt)

    def test_instant_experience_auto_scenes_are_specific_and_pairwise_distinct(self):
        exact_scene_fields = (
            "room_type",
            "wall_colour",
            "wall_material",
            "camera_side",
            "camera_height",
            "lens",
            "lighting",
            "time_of_day",
            "overlay_position",
            "product_position",
            "architectural_cue",
        )
        visuals = ads_page.INSTANT_EXPERIENCE_STANDARD_VISUALS
        self.assertTrue(ads_page.validate_instant_experience_set_differentiation())
        for visual in visuals:
            for field in exact_scene_fields:
                self.assertNotRegex(
                    visual[field].casefold(),
                    r"\b(?:or)\b",
                    (visual["route"], field, visual[field]),
                )
        for index, first in enumerate(visuals):
            for second in visuals[index + 1 :]:
                self.assertGreaterEqual(
                    ads_page._instant_experience_pairwise_difference_count(first, second),
                    5,
                )

        prompt = ads_page.build_ads_prompt(
            "Sunday at the Crease",
            "Cricket",
            "Australia",
            "Instant Experience",
            variation_token="resolved-scenes-v2",
        )
        for visual in visuals:
            for field in exact_scene_fields:
                self.assertIn(visual[field], prompt)

    def test_instant_experience_route_wording_and_typography_are_route_specific(self):
        contract = visual_contract(
            ads_page.build_ads_prompt(
                "The Final Lap",
                "Motorsport",
                "Canada",
                "Instant Experience",
                variation_token="route-wording-v2",
            )
        )
        nostalgia_start = contract.index("GROUP 1 — NOSTALGIA\n\nIMAGE GENERATION PROMPT")
        ownership_start = contract.index("GROUP 2 — OWNERSHIP\n\nIMAGE GENERATION PROMPT")
        scarcity_start = contract.index("GROUP 3 — SCARCITY\n\nIMAGE GENERATION PROMPT")
        nostalgia = contract[nostalgia_start : contract.index("COPY VARIATIONS", nostalgia_start)]
        ownership = contract[ownership_start : contract.index("COPY VARIATIONS", ownership_start)]
        scarcity = contract[scarcity_start : contract.index("COPY VARIATIONS", scarcity_start)]

        for cover in (nostalgia, ownership, scarcity):
            self.assertIn("ROUTE WORDING LOCK - RESOLVE BEFORE RETURNING", cover)
            self.assertIn("These are the only permitted advertising words", cover)
            self.assertIn("Forbidden other-route wording:", cover)
            self.assertIn("Never place Primary Text on the image.", cover)

        self.assertIn("APPROVED FLOATING LIFESTYLE TYPOGRAPHY", nostalgia)
        self.assertIn("Montserrat SemiBold", nostalgia)
        self.assertIn("Maintain at least a 7% safe margin", nostalgia)
        self.assertNotIn("APPROVED SCARCITY STRIP TYPOGRAPHY", nostalgia)
        self.assertIn("APPROVED FLOATING LIFESTYLE TYPOGRAPHY", ownership)
        self.assertIn("Maintain at least a 7% safe margin", ownership)
        self.assertNotIn("APPROVED SCARCITY STRIP TYPOGRAPHY", ownership)
        self.assertIn("APPROVED SCARCITY STRIP TYPOGRAPHY", scarcity)
        self.assertNotIn("APPROVED FLOATING LIFESTYLE TYPOGRAPHY", scarcity)
        for line in ads_page.BASEBALL_INSTANT_EXPERIENCE_COVER_LINES:
            self.assertIn(line, scarcity)

    def test_instant_experience_quality_is_dynamic_and_does_not_leak_to_other_prompt_systems(self):
        cases = (
            ("Ballpark Night", "Baseball", "USA"),
            ("Summer at the Crease", "Cricket", "Australia"),
        )
        for product_name, sport, market in cases:
            with self.subTest(product_name=product_name, sport=sport, market=market):
                prompt = ads_page.build_ads_prompt(
                    product_name,
                    sport,
                    market,
                    "Instant Experience",
                    variation_token="dynamic-quality-v2",
                )
                self.assertIn(f"Product name: {product_name}", prompt)
                self.assertIn(f"Sport/category: {sport}", prompt)
                self.assertIn(f"Country/market: {market}", prompt)

        quality_contracts = "\n".join(
            (
                ads_page.SPORTS_CAVE_IE_CORE_IMAGE_QUALITY_RULES_V2,
                ads_page.SPORTS_CAVE_IE_CORE_COPY_QUALITY_RULES_V2,
                ads_page.SPORTS_CAVE_IE_FINAL_REJECTION_GATE_V2,
            )
        )
        self.assertNotIn("Brock", quality_contracts)
        self.assertNotIn("Moffat", quality_contracts)

        carousel = ads_page.build_ads_prompt(
            "The Final Lap",
            "Motorsport",
            "Canada",
            "Carousel",
            variation_token="route-isolation-v2",
        )
        for marker in (
            "SPORTS_CAVE_IE_CORE_IMAGE_QUALITY_RULES_V2",
            "SPORTS_CAVE_IE_CORE_COPY_QUALITY_RULES_V2",
            "SPORTS_CAVE_IE_TYPOGRAPHY_RULES_V2",
            "SPORTS_CAVE_IE_SET_DIFFERENTIATION_RULES_V2",
            "SPORTS_CAVE_IE_FINAL_REJECTION_GATE_V2",
        ):
            self.assertNotIn(marker, carousel)

    def test_instant_experience_scarcity_prompt_uses_bottom_strip_layout(self):
        prompt = ads_page.build_ads_prompt(
            "Collector Test Product",
            "Baseball",
            "USA",
            "Instant Experience",
            variation_token="scarcity-bottom-strip-test",
        )
        contract = visual_contract(prompt)
        scarcity_start = contract.index("GROUP 3 — SCARCITY\n\nIMAGE GENERATION PROMPT")
        scarcity_prompt = contract[
            scarcity_start : contract.index("COPY VARIATIONS", scarcity_start)
        ]

        self.assertIn(
            "full-width upper lifestyle/product image across approximately 76-78%",
            scarcity_prompt,
        )
        self.assertIn(
            "full-width matte-black scarcity strip across the bottom approximately 22-24%",
            scarcity_prompt,
        )
        self.assertIn(
            "thin restrained metallic-gold divider across the top edge of the black strip",
            scarcity_prompt,
        )
        self.assertIn(
            "frame occupying approximately 74-82% of usable canvas width inside the upper image region",
            scarcity_prompt,
        )
        self.assertIn(
            "All scarcity wording must be contained inside the bottom strip; no wording may appear beside or over the product image.",
            scarcity_prompt,
        )
        self.assertIn("No left/right split, no right sidebar and no vertical scarcity panel.", scarcity_prompt)
        self.assertIn("LIMITED TO 100 WORLDWIDE", scarcity_prompt)
        self.assertIn("Once it sells out, it’s gone.", scarcity_prompt)
        self.assertIn("CLAIM YOUR EDITION", scarcity_prompt)
        self.assertIn("SPORTS CAVE PRODUCT AND MOCKUP LOCK - MANDATORY", scarcity_prompt)
        self.assertIn("FRAME REALISM:", scarcity_prompt)
        self.assertIn("GLASS REALISM:", scarcity_prompt)
        self.assertIn(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER, scarcity_prompt)
        self.assertNotIn("64-68% lifestyle", scarcity_prompt)
        self.assertNotIn("32-36% deep matte-black collector panel", scarcity_prompt)
        self.assertNotIn("right-side black panel", scarcity_prompt)
        self.assertNotIn("lifestyle/panel division remains", scarcity_prompt)

    def test_old_instant_experience_prompt_schema_gets_upgraded_default_contract(self):
        prompt = ads_page.compose_final_ads_prompt(
            "SAVED INSTANT EXPERIENCE PROMPT\n\nINSTANT EXPERIENCE COVER PROMPT\n\n[old saved cover prompt]",
            category="Golf",
            country="Canada",
            campaign_type="Instant Experience",
            product_name="Masters Sunday Frame",
            variation_token="saved-compatible",
        )
        contract = visual_contract(prompt)

        self.assertIn("INSTANT EXPERIENCE COVER PROMPT", prompt)
        self.assertIn("GROUP 1 — NOSTALGIA", contract)
        self.assertIn("GROUP 2 — OWNERSHIP", contract)
        self.assertIn("GROUP 3 — SCARCITY", contract)
        self.assertEqual(contract.count("Creative concept: Nostalgia"), 1)
        self.assertEqual(contract.count("Creative concept: Ownership"), 1)
        self.assertEqual(contract.count("Creative concept: Scarcity"), 1)
        self.assertIn("Product name: Masters Sunday Frame", contract)
        self.assertIn("Sport/category: Golf", contract)
        self.assertIn("Country/market: Canada", contract)
        self.assertIn(
            "The final campaign-specific visual heading, exact headings and prompt count below are authoritative.",
            contract,
        )
        self.assertIn("LIMITED TO 100 WORLDWIDE", contract)
        self.assertIn("Once it sells out, it’s gone.", contract)
        self.assertNotIn("Social Media Reels", contract)

    def test_baseball_instant_experience_uses_master_cover_prompt_and_claim_path(self):
        prompt = ads_page.build_ads_prompt(
            "Shohei Ohtani 50/50 Season",
            "Baseball",
            "USA",
            "Instant Experience",
            product_url="https://sportscave.com.au/products/ohtani-50-50",
            variation_token="baseball-cover-test",
        )
        contract = visual_contract(prompt)

        self.assertIn("GROUP 1 — NOSTALGIA", contract)
        self.assertIn("GROUP 2 — OWNERSHIP", contract)
        self.assertIn("GROUP 3 — SCARCITY", contract)
        self.assertEqual(contract.count("Creative concept: Nostalgia"), 1)
        self.assertEqual(contract.count("Creative concept: Ownership"), 1)
        self.assertEqual(contract.count("Creative concept: Scarcity"), 1)
        self.assertIn("LIMITED TO 100 WORLDWIDE", contract)
        self.assertNotIn("Mockups ZIP", prompt)
        self.assertNotIn("Social Media Reels", prompt)
        self.assertNotIn("Create a square 1024 x 1024", contract)
        self.assertIn("SPORTS CAVE BASEBALL INSTANT EXPERIENCE AD", prompt)
        self.assertIn("INSTANT EXPERIENCE SETUP", prompt)

    def test_instant_experience_ignores_obsolete_route_settings_and_uses_standard_output(self):
        settings = instant_experience_settings(output_mode=ads_page.IE_MODE_SMART)
        prompt = ads_page.build_ads_prompt(
            "Shohei Ohtani 50/50 Season",
            "Baseball",
            "USA",
            "Instant Experience",
            product_url="https://sportscave.com.au/products/ohtani-50-50",
            variation_token="standard-route-ignore-test",
            instant_experience_settings=settings,
        )

        self.assertIn("SPORTS CAVE BASEBALL INSTANT EXPERIENCE AD", prompt)
        self.assertIn("GROUP 1 — NOSTALGIA", prompt)
        self.assertIn("GROUP 2 — OWNERSHIP", prompt)
        self.assertIn("GROUP 3 — SCARCITY", prompt)
        self.assertEqual(prompt.count("Creative concept: Nostalgia"), 1)
        self.assertEqual(prompt.count("Creative concept: Ownership"), 1)
        self.assertEqual(prompt.count("Creative concept: Scarcity"), 1)
        self.assertNotIn("OPTION A", prompt)
        self.assertNotIn("OUTPUT EXACTLY FOR THIS OPTION", prompt)
        self.assertNotIn("META AD DESCRIPTION\n", prompt)
        self.assertNotIn("Which Instant Experience cover", prompt)
        self.assertEqual(prompt.count(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER), 3)

    def test_instant_experience_nostalgia_and_scarcity_rules_are_separated(self):
        prompt = ads_page.build_ads_prompt(
            "Final Whistle Glory",
            "Football",
            "UK",
            "Instant Experience",
            product_url="https://sportscave.com.au/products/final-whistle-glory",
            variation_token="standard-angle-test",
        )
        prompt_one = prompt[
            prompt.index("GROUP 1 — NOSTALGIA\n\nIMAGE GENERATION PROMPT") :
            prompt.index("GROUP 2 — OWNERSHIP\n\nIMAGE GENERATION PROMPT")
        ]
        prompt_two = prompt[
            prompt.index("GROUP 2 — OWNERSHIP\n\nIMAGE GENERATION PROMPT") :
            prompt.index("GROUP 3 — SCARCITY\n\nIMAGE GENERATION PROMPT")
        ]
        prompt_three = prompt[prompt.index("GROUP 3 — SCARCITY\n\nIMAGE GENERATION PROMPT") :]

        self.assertIn("No scarcity language, no offer, no discount", prompt_one)
        self.assertIn("no hard black panel", prompt_one)
        self.assertNotIn("32-36% deep matte-black collector panel", prompt_one)
        self.assertNotIn("full-width matte-black scarcity strip across the bottom", prompt_one)
        self.assertIn("asymmetrical lifestyle composition", prompt_two)
        self.assertNotIn("full-width matte-black scarcity strip across the bottom", prompt_two)
        self.assertIn("full-width matte-black scarcity strip across the bottom approximately 22-24%", prompt_three)
        self.assertIn("No left/right split, no right sidebar and no vertical scarcity panel.", prompt_three)
        for line in ads_page.BASEBALL_INSTANT_EXPERIENCE_COVER_LINES:
            self.assertIn(line, prompt_three)

    def test_instant_experience_offer_serializes_without_moment_type(self):
        prompt = ads_page.build_ads_prompt(
            "Collector Pair",
            "Baseball",
            "USA",
            "Instant Experience",
            product_url="https://sportscave.com.au/products/collector-pair",
            variation_token="offer-serialization-test",
            campaign_moment={"promotion": "15% off 2+ editions"},
        )

        self.assertIn("PROMOTION OR OFFER", prompt)
        self.assertIn("Exact Promotion or Offer entered: 15% off 2+ editions", prompt)
        self.assertIn("Serialize this field independently of Moment Type.", prompt)
        self.assertIn("Use it only in Scarcity variation 3", prompt)

    def test_instant_experience_does_not_use_obsolete_collection_destination(self):
        settings = instant_experience_settings(
            output_mode=ads_page.IE_MODE_SMART,
            destination_scope="Curated collection page + catalogue",
            collection_name="Baseball Icons",
            collection_url="https://sportscave.com.au/collections/baseball-icons",
            collection_product_set_name="Baseball Icons Set",
            eligible_product_count=4,
            multi_product_reference_count=2,
            route_c="BUILD",
        )
        prompt = ads_page.build_ads_prompt(
            "Ohtani Hero",
            "Baseball",
            "USA",
            "Instant Experience",
            product_url="https://sportscave.com.au/products/ohtani-hero",
            variation_token="collection-url-test",
            instant_experience_settings=settings,
        )

        self.assertIn("Destination guidance: Use this selected product page URL", prompt)
        self.assertIn("https://sportscave.com.au/products/ohtani-hero", prompt)
        self.assertNotIn("https://sportscave.com.au/collections/baseball-icons", prompt)
        self.assertIn("Do not introduce collection-page routing in this workflow.", prompt)

    def test_instant_experience_sport_country_and_fingerprints_are_automatic(self):
        baseball = ads_page.instant_experience_sport_direction("Baseball")
        basketball = ads_page.instant_experience_sport_direction("NBA")
        self.assertIn("ballpark memory", baseball)
        self.assertIn("charcoal limewash", basketball)
        self.assertNotIn("vehicles", baseball)

        fingerprints = ads_page.build_standard_instant_experience_fingerprints(category="Baseball")
        self.assertEqual(len(fingerprints), 3)
        self.assertEqual(
            {fingerprint["route"] for fingerprint in fingerprints},
            {"Nostalgia", "Ownership", "Scarcity"},
        )
        self.assertGreaterEqual(
            len({fingerprint["cover_layout"] for fingerprint in fingerprints}),
            3,
        )
        self.assertGreaterEqual(
            len({fingerprint["camera_family"] for fingerprint in fingerprints}),
            3,
        )

    def test_instant_experience_creative_direction_panel_no_longer_renders(self):
        source = (ROOT / "ads_page.py").read_text(encoding="utf-8")
        render_page_source = source[source.index("def render_page") :]
        panel_source = source[source.index("def render_instant_experience_creative_panel") : source.index("def _template_slug")]

        self.assertEqual(panel_source.count("st.selectbox("), 0)
        self.assertNotIn("render_instant_experience_creative_panel(campaign_type)", render_page_source)
        self.assertNotIn("validate_instant_experience_settings(", render_page_source)

    def test_single_image_video_preserves_one_creative_prompt_route(self):
        prompt = ads_page.build_ads_prompt(
            "The Ashes Final Session",
            "Cricket",
            "UK",
            "Single Image / Video",
            variation_token="single-test",
        )
        contract = visual_contract(prompt)

        self.assertIn("SPORTS CAVE CRICKET SINGLE IMAGE VIDEO WINNER PATTERN", prompt)
        self.assertEqual(contract.count("CREATIVE PROMPT FOR SINGLE IMAGE/VIDEO"), 1)
        self.assertIn("Preserve the existing Single Image / Video route and output fields.", contract)
        self.assertIn("Do not create a five-prompt Carousel sequence.", contract)
        self.assertNotIn("IMAGE PROMPTS — GENERATE IN THIS ORDER", contract)

    def test_master_contract_includes_selected_context_and_finished_output_order(self):
        contract = visual_contract(
            ads_page.build_ads_prompt(
                "Six Laps Ahead",
                "Motorsport",
                "Canada",
                "Carousel",
                variation_token="context-test",
            )
        )

        self.assertIn("Selected product name: Six Laps Ahead", contract)
        self.assertIn("Selected sport category: Motorsport", contract)
        self.assertIn("Selected country: Canada", contract)
        self.assertIn("Selected campaign type: Carousel", contract)
        self.assertIn("Creative variation token: context-test", contract)
        self.assertIn("Return the finished existing ad-copy output first", contract)
        self.assertIn("Directly beneath that complete existing output", contract)
        self.assertIn("Do not output a preliminary brief, duplicate visual field or second prompt.", contract)
        self.assertIn(
            "The final campaign-specific visual heading, exact headings and prompt count below are authoritative.",
            contract,
        )
        self.assertIn("Do not repeat the research", contract)

    def test_product_name_is_collapsed_to_one_safe_prompt_line(self):
        prompt = ads_page.build_ads_prompt(
            '  Title <b>"quoted"</b> {value}\r\nSecond line  ',
            "Golf",
            "Canada",
            "Single Image / Video",
            variation_token="safe-title-test",
        )

        self.assertIn('Product name: Title <b>"quoted"</b> {value} Second line', prompt)
        self.assertIn('Selected product name: Title <b>"quoted"</b> {value} Second line', prompt)
        self.assertNotIn("{value}\r", prompt)
        self.assertNotIn("{value}\n", prompt)

    def test_visual_variation_tokens_are_fresh_and_non_sensitive(self):
        first = ads_page.build_visual_variation_token()
        second = ads_page.build_visual_variation_token()

        self.assertNotEqual(first, second)
        self.assertRegex(first, r"^[a-f0-9]{12}$")
        self.assertRegex(second, r"^[a-f0-9]{12}$")

    def test_copy_button_receives_one_combined_copy_and_visual_prompt(self):
        prompt = ads_page.build_ads_prompt(
            "Six Laps Ahead",
            "Motorsport",
            "Australia",
            "Carousel",
            variation_token="clipboard-test",
        )

        with patch("ads_page.components.html") as render_html:
            ads_page.render_prompt_copy_button(prompt, "combined-copy-test")

        clipboard_html = render_html.call_args.args[0]
        self.assertIn("SPORTS CAVE MOTORSPORT CAROUSEL AD", clipboard_html)
        self.assertIn("MASTER RESPONSE AND VISUAL OUTPUT CONTRACT", clipboard_html)
        self.assertIn("IMAGE GENERATION PROMPTS", clipboard_html)
        self.assertEqual(render_html.call_count, 1)

    def test_ads_prompt_code_has_no_external_ai_api_path(self):
        source = "\n".join(
            [
                (ROOT / "ads_page.py").read_text(encoding="utf-8"),
                (ROOT / "ads_product_catalog.py").read_text(encoding="utf-8"),
            ]
        ).casefold()

        for blocked in ("import openai", "from openai", "requests.post", "httpx", "urllib.request"):
            self.assertNotIn(blocked, source)

    def test_how_to_use_describes_one_master_prompt_and_matching_images(self):
        source = (ROOT / "ads_page.py").read_text(encoding="utf-8")

        self.assertIn("Upload the black-framed Sports Cave product WebP into ChatGPT.", source)
        self.assertIn("Copy and paste the generated master prompt.", source)
        self.assertIn("ChatGPT will return the ad copy first and the matching image prompt or prompts underneath.", source)
        self.assertIn("Generate and upload the images in the displayed order.", source)

    def test_supported_prompt_uses_copy_button_instead_of_visible_prompt_code(self):
        source = (ROOT / "ads_page.py").read_text(encoding="utf-8")
        supported_result_source = source[source.index("def render_supported_result") : source.index("def render_page")]

        self.assertIn("def render_prompt_copy_button", source)
        self.assertIn("components.html", source)
        self.assertIn("navigator.clipboard.writeText(promptText)", source)
        self.assertIn("render_prompt_copy_button(", supported_result_source)
        self.assertNotIn("st.code(build_ads_prompt", supported_result_source)

    def test_generated_image_uploads_include_compact_setup_notes_before_save(self):
        source = (ROOT / "ads_page.py").read_text(encoding="utf-8")
        supported_result_source = source[source.index("def render_supported_result") : source.index("def render_page")]

        self.assertIn('st.expander("Ad setup notes (optional)"', source)
        self.assertIn("Paste the 5 headlines, one per line.", source)
        self.assertIn("Paste the 5 descriptions, one per line.", source)
        self.assertIn('"Primary Text Variations"', source)
        self.assertIn("ads-notes-primary-text::", source)
        self.assertIn(".st-key-ads-setup-notes [data-testid=\"stHorizontalBlock\"]", source)
        carousel_slots_index = supported_result_source.rindex("_render_ads_image_slots(result, workflow)")
        carousel_notes_index = supported_result_source.rindex("_render_ads_setup_notes(result, workflow)")
        carousel_save_index = supported_result_source.rindex("_render_ads_image_save(result, workflow)")
        self.assertLess(carousel_slots_index, carousel_notes_index)
        self.assertLess(carousel_notes_index, carousel_save_index)

        app_test = run_ads_page()
        set_product_name(app_test, "Six Laps Ahead")
        select_option(app_test, "Category", "Motorsport")
        select_option(app_test, "Country", "Australia")
        select_option(app_test, "Campaign type", "Carousel")
        set_product_url(app_test)
        button_by_label(app_test, "Submit").click().run(timeout=20)
        note_labels = [text_area.label for text_area in app_test.text_area]
        self.assertIn("Headlines", note_labels)
        self.assertIn("Descriptions", note_labels)
        self.assertIn("Carousel cards / ad setup", note_labels)
        self.assertIn("Primary Text Variations", note_labels)

    def test_instant_experience_copy_fields_are_grouped_by_three_concepts(self):
        source = (ROOT / "ads_page.py").read_text(encoding="utf-8")

        self.assertIn("INSTANT_EXPERIENCE_CONCEPTS", source)
        self.assertIn("ads-ie-concept-copy-field::", source)
        self.assertIn("height: 50px", source)
        self.assertIn("overflow-y: auto", source)

        app_test = run_ads_page()
        set_product_name(app_test, "Six Laps Ahead")
        select_option(app_test, "Category", "Motorsport")
        select_option(app_test, "Country", "Australia")
        select_option(app_test, "Campaign type", "Instant Experience")
        set_product_url(app_test)

        select_labels = [selectbox.label for selectbox in app_test.selectbox]
        for label in (
            "Creative output mode",
            "Audience mindset",
            "Primary creative angle",
            "Urgency placement",
            "Destination scope",
            "Visual direction",
        ):
            self.assertNotIn(label, select_labels)

        button_by_label(app_test, "Submit").click().run(timeout=20)

        note_labels = [text_area.label for text_area in app_test.text_area]
        self.assertEqual(
            [label for label in note_labels if label == "Primary Text"],
            ["Primary Text"] * 9,
        )
        self.assertEqual(
            [label for label in note_labels if label == "Headline"],
            ["Headline"] * 9,
        )
        self.assertEqual(
            [label for label in note_labels if label == "CTA"],
            ["CTA"] * 9,
        )
        self.assertNotIn("Call to Action 1", note_labels)
        self.assertNotIn("Descriptions", note_labels)
        self.assertNotIn("Carousel cards / ad setup", note_labels)
        self.assertNotIn("Primary Text Variations", note_labels)

    def test_submit_supported_result_renders_compact_sections_with_url_parameters(self):
        app_test = run_ads_page()
        set_product_name(app_test, "Six Laps Ahead")
        select_option(app_test, "Category", "Motorsport")
        select_option(app_test, "Country", "Canada")
        select_option(app_test, "Campaign type", "Carousel")
        set_product_url(app_test)
        button_by_label(app_test, "Submit").click().run(timeout=20)

        self.assertEqual(
            [subheader.value for subheader in app_test.subheader],
            [
                "1. Copy this ChatGPT prompt",
                "Generated Ad Images",
                "2. Build it in Meta",
                "3. URL parameters",
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
        set_product_url(app_test)
        button_by_label(app_test, "Submit").click().run(timeout=20)

        self.assertNotIn("Insufficient winner data", [subheader.value for subheader in app_test.subheader])
        self.assertIn("1. Copy this ChatGPT prompt", [subheader.value for subheader in app_test.subheader])
        self.assertFalse(any("Using generic Sports Cave winner pattern" in caption.value for caption in app_test.caption))
        self.assertEqual(len(app_test.code), 1)
        self.assertEqual(app_test.code[0].value, ads_page.META_AD_URL_PARAMETERS)
        self.assertEqual(len(app_test.exception), 0)

    def test_carousel_renders_five_slots_and_upload_state_survives_reruns(self):
        app_test = run_ads_page()
        set_product_name(app_test, "Six Laps Ahead")
        select_option(app_test, "Category", "Motorsport")
        select_option(app_test, "Country", "Australia")
        select_option(app_test, "Campaign type", "Carousel")
        set_product_url(app_test)
        button_by_label(app_test, "Submit").click().run(timeout=20)

        self.assertEqual(
            [uploader.label for uploader in app_test.file_uploader[:5]],
            ["Carousel 1", "Carousel 2", "Carousel 3", "Carousel 4", "Carousel 5"],
        )
        self.assertFalse(button_by_label(app_test, "Save Images").disabled)
        original_result = dict(app_test.session_state[ads_page.ADS_RESULT_STATE_KEY])
        image = square_png_bytes()
        app_test.file_uploader[0].set_value([("Carousel 1.png", image, "image/png")])
        app_test.run(timeout=30)
        self.assertFalse(button_by_label(app_test, "Save Images").disabled)
        for uploader in app_test.file_uploader[:5]:
            uploader.set_value([(f"{uploader.label}.png", image, "image/png")])
        app_test.run(timeout=30)

        persisted_result = dict(app_test.session_state[ads_page.ADS_RESULT_STATE_KEY])
        self.assertEqual(persisted_result["variation_token"], original_result["variation_token"])
        self.assertEqual(persisted_result["master_prompt"], original_result["master_prompt"])
        self.assertEqual(
            len(app_test.session_state[ads_page.ADS_IMAGE_STATE_KEY]["slots"]),
            5,
        )
        self.assertFalse(button_by_label(app_test, "Save Images").disabled)
        self.assertEqual(len(app_test.exception), 0)

    def test_remove_and_replace_keeps_carousel_partial_save_available(self):
        app_test = run_ads_page()
        set_product_name(app_test, "Six Laps Ahead")
        select_option(app_test, "Category", "Motorsport")
        select_option(app_test, "Country", "Australia")
        select_option(app_test, "Campaign type", "Carousel")
        set_product_url(app_test)
        button_by_label(app_test, "Submit").click().run(timeout=20)
        image = square_png_bytes()
        for uploader in app_test.file_uploader[:5]:
            uploader.set_value([(f"{uploader.label}.png", image, "image/png")])
        app_test.run(timeout=30)

        button_by_label(app_test, "Remove").click().run(timeout=20)
        self.assertFalse(button_by_label(app_test, "Save Images").disabled)
        self.assertEqual(
            len(app_test.session_state[ads_page.ADS_IMAGE_STATE_KEY]["slots"]),
            4,
        )
        app_test.file_uploader[0].set_value(
            [("Carousel 1 replacement.webp", image, "image/webp")]
        )
        app_test.run(timeout=30)
        self.assertFalse(button_by_label(app_test, "Save Images").disabled)
        self.assertEqual(len(app_test.exception), 0)

    def test_instant_experience_renders_three_required_cover_slots_immediately(self):
        app_test = run_ads_page()
        set_product_name(app_test, "Final Whistle Glory")
        select_option(app_test, "Category", "Football")
        select_option(app_test, "Country", "UK")
        select_option(app_test, "Campaign type", "Instant Experience")
        set_product_url(app_test, "https://sportscave.com.au/products/final-whistle-glory")
        button_by_label(app_test, "Submit").click().run(timeout=20)

        self.assertEqual(
            [uploader.label for uploader in app_test.file_uploader],
            [
                "Nostalgia Cover",
                "Ownership Cover",
                "Scarcity Cover",
            ],
        )
        self.assertTrue(button_by_label(app_test, "Save Images").disabled)
        self.assertTrue(any("0 of 3 images ready." in caption.value for caption in app_test.caption))
        for index in range(1, 4):
            app_test.file_uploader[index - 1].set_value(
                [(f"instant-{index}.png", square_png_bytes(color=(40 + index, 70, 110)), "image/png")]
            )
            app_test.run(timeout=30)
            self.assertEqual(
                [uploader.label for uploader in app_test.file_uploader],
                [
                    "Nostalgia Cover",
                    "Ownership Cover",
                    "Scarcity Cover",
                ],
            )
            self.assertTrue(any(f"{index} of 3 images ready." in caption.value for caption in app_test.caption))
            self.assertTrue(button_by_label(app_test, "Save Images").disabled)
        self.assertEqual(len(app_test.exception), 0)

    def test_instant_experience_preview_remove_replace_and_rerun_persistence(self):
        app_test = run_ads_page()
        set_product_name(app_test, "Final Whistle Glory")
        select_option(app_test, "Category", "Football")
        select_option(app_test, "Country", "UK")
        select_option(app_test, "Campaign type", "Instant Experience")
        set_product_url(app_test, "https://sportscave.com.au/products/final-whistle-glory")
        button_by_label(app_test, "Submit").click().run(timeout=20)

        app_test.file_uploader[0].set_value(
            [("uploaded-filename.png", square_png_bytes(), "image/png")]
        )
        app_test.run(timeout=30)
        workflow = app_test.session_state[ads_page.ADS_IMAGE_STATE_KEY]
        self.assertTrue(workflow["slots"]["instant-experience-nostalgia"]["valid"])
        self.assertEqual(workflow["slots"]["instant-experience-nostalgia"]["original_name"], "uploaded-filename.png")
        self.assertTrue(any("Original: 96 x 96 px" in caption.value for caption in app_test.caption))
        result = app_test.session_state[ads_page.ADS_RESULT_STATE_KEY]
        filename = ads_page._meta_output_filename(
            result,
            workflow,
            ads_page.ads_image_workflow.campaign_image_slots("Instant Experience")[0],
        )
        self.assertEqual(filename, "nostalgia-cover-original.png")
        self.assertTrue(filename.endswith(".png"))
        self.assertTrue(button_by_label(app_test, "Save Images").disabled)

        app_test.run(timeout=20)
        workflow = app_test.session_state[ads_page.ADS_IMAGE_STATE_KEY]
        self.assertIn("instant-experience-nostalgia", workflow["slots"])
        self.assertEqual(workflow["slots"]["instant-experience-nostalgia"]["original_name"], "uploaded-filename.png")

        button_by_label(app_test, "Remove").click().run(timeout=20)
        workflow = app_test.session_state[ads_page.ADS_IMAGE_STATE_KEY]
        self.assertEqual(workflow["slots"], {})
        self.assertTrue(button_by_label(app_test, "Save Images").disabled)

        app_test.file_uploader[0].set_value(
            [("replacement.webp", square_png_bytes(color=(90, 120, 150)), "image/webp")]
        )
        app_test.run(timeout=30)
        workflow = app_test.session_state[ads_page.ADS_IMAGE_STATE_KEY]
        self.assertEqual(workflow["slots"]["instant-experience-nostalgia"]["original_name"], "replacement.webp")
        self.assertTrue(button_by_label(app_test, "Save Images").disabled)

    def test_instant_experience_remove_middle_cover_preserves_route_slots(self):
        app_test = run_ads_page()
        set_product_name(app_test, "Final Whistle Glory")
        select_option(app_test, "Category", "Football")
        select_option(app_test, "Country", "UK")
        select_option(app_test, "Campaign type", "Instant Experience")
        set_product_url(app_test, "https://sportscave.com.au/products/final-whistle-glory")
        button_by_label(app_test, "Submit").click().run(timeout=20)

        for index in range(1, 4):
            app_test.file_uploader[index - 1].set_value(
                [(f"variation-{index}.png", square_png_bytes(color=(40 + index, 80, 120)), "image/png")]
            )
            app_test.run(timeout=30)

        buttons_by_label(app_test, "Remove")[1].click().run(timeout=20)
        workflow = app_test.session_state[ads_page.ADS_IMAGE_STATE_KEY]
        self.assertEqual(
            list(workflow["slots"].keys()),
            ["instant-experience-nostalgia", "instant-experience-scarcity"],
        )
        self.assertEqual(
            workflow["slots"]["instant-experience-scarcity"]["original_name"],
            "variation-3.png",
        )
        self.assertEqual(
            [uploader.label for uploader in app_test.file_uploader],
            [
                "Nostalgia Cover",
                "Ownership Cover",
                "Scarcity Cover",
            ],
        )

    def test_invalid_generated_image_shows_inline_error_and_keeps_save_disabled(self):
        app_test = run_ads_page()
        set_product_name(app_test, "Final Whistle Glory")
        select_option(app_test, "Category", "Football")
        select_option(app_test, "Country", "UK")
        select_option(app_test, "Campaign type", "Instant Experience")
        set_product_url(app_test, "https://sportscave.com.au/products/final-whistle-glory")
        button_by_label(app_test, "Submit").click().run(timeout=20)

        app_test.file_uploader[0].set_value(
            [("broken.png", b"not an image", "image/png")]
        )
        app_test.run(timeout=20)

        self.assertTrue(any("corrupt" in error.value for error in app_test.error))
        self.assertTrue(button_by_label(app_test, "Save Images").disabled)
        self.assertEqual(len(app_test.exception), 0)

    def test_new_campaign_submit_resets_only_incompatible_ads_upload_state(self):
        app_test = run_ads_page()
        set_product_name(app_test, "Six Laps Ahead")
        select_option(app_test, "Category", "Motorsport")
        select_option(app_test, "Country", "Australia")
        select_option(app_test, "Campaign type", "Carousel")
        set_product_url(app_test)
        button_by_label(app_test, "Submit").click().run(timeout=20)
        app_test.file_uploader[0].set_value(
            [("carousel-one.png", square_png_bytes(), "image/png")]
        )
        app_test.run(timeout=30)
        old_context = app_test.session_state[ads_page.ADS_RESULT_STATE_KEY]["context_key"]

        select_option(app_test, "Campaign type", "Instant Experience")
        set_product_url(app_test)
        button_by_label(app_test, "Submit").click().run(timeout=20)

        new_result = app_test.session_state[ads_page.ADS_RESULT_STATE_KEY]
        new_workflow = app_test.session_state[ads_page.ADS_IMAGE_STATE_KEY]
        self.assertNotEqual(new_result["context_key"], old_context)
        self.assertEqual(new_workflow["context_key"], new_result["context_key"])
        self.assertEqual(new_workflow["slots"], {})
        self.assertEqual(
            [uploader.label for uploader in app_test.file_uploader],
            [
                "Nostalgia Cover",
                "Ownership Cover",
                "Scarcity Cover",
            ],
        )

    def test_legacy_single_instant_experience_slot_loads_as_variation_one(self):
        result = ads_page.build_ads_result_record(
            "Final Whistle Glory",
            "Football",
            "UK",
            "Instant Experience",
            product_id="legacy-product",
        )
        processed = ads_page.ads_image_workflow.optimize_meta_image(
            square_png_bytes(),
            original_name="legacy.png",
        )
        workflow = {
            "context_key": result["context_key"],
            "campaign_type": "Instant Experience",
            "slots": {
                "instant-experience": {
                    **processed,
                    "slot_id": "instant-experience",
                    "label": "Instant Experience Image",
                    "position": 1,
                    "valid": True,
                    "error": "",
                }
            },
            "outcomes": {},
        }

        self.assertFalse(ads_page.ads_images_ready(result, workflow))
        self.assertEqual(list(workflow["slots"].keys()), ["instant-experience-nostalgia"])
        self.assertEqual(workflow["slots"]["instant-experience-nostalgia"]["original_name"], "legacy.png")
        self.assertEqual(workflow["slots"]["instant-experience-nostalgia"]["label"], "Nostalgia Cover")

    def test_valid_category_campaign_country_combinations_never_have_insufficient_winner_data(self):
        for category in ads_page.SUPPORTED_AD_CATEGORIES:
            for campaign_type in ("Carousel", "Instant Experience", "Single Image / Video"):
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

    def test_ads_page_source_has_no_external_ai_or_shopify_execution_path(self):
        source = (ROOT / "ads_page.py").read_text(encoding="utf-8")
        source_lower = source.casefold()

        for blocked in ("meta_ads_client", "openai", "requests.post", "httpx", "analytics"):
            self.assertNotIn(blocked, source_lower)
        self.assertNotIn("import shopify", source_lower)
        self.assertNotIn("from shopify", source_lower)
        self.assertNotIn("shopify_client", source_lower)
        self.assertIn("dropbox_integration.upload_batch", source)
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
