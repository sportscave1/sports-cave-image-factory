import csv
import importlib
import io
import json
import re
from datetime import date
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from PIL import Image
from streamlit.testing.v1 import AppTest

import ads_page
from tests.ads_prompt_contracts import current_ie
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


def run_ads_page_with_product_rows(rows, **session_values):
    app_test = AppTest.from_file(str(ROOT / "app.py"))
    app_test.session_state["sports_cave_authenticated"] = True
    app_test.session_state["selected_page"] = "Ads"
    app_test.session_state["startup_shell_loaded"] = True
    app_test.session_state[ads_page.EDITION_OPS_ROWS_SESSION_KEY] = list(rows)
    for key, value in session_values.items():
        app_test.session_state[key] = value
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
    if ads_page.ADS_IE_COMBINED_EXECUTION_VERSION in prompt:
        return prompt
    marker = "MASTER RESPONSE AND VISUAL OUTPUT CONTRACT"
    return prompt[prompt.index(marker) :]


def carousel_prompt_card_sections(contract):
    sections = {}
    for index in range(1, ads_page.CAROUSEL_CARD_COUNT + 1):
        marker = f"CARD {index} IMAGE GENERATION PROMPT"
        start = contract.rindex(marker + "\n\n")
        next_marker = (
            f"CARD {index + 1} IMAGE GENERATION PROMPT"
            if index < ads_page.CAROUSEL_CARD_COUNT
            else "Return exactly these five image-prompt entries"
        )
        end = contract.rindex(next_marker + "\n\n") if index < ads_page.CAROUSEL_CARD_COUNT else contract.index(next_marker, start)
        sections[index] = contract[start:end]
    return sections


def square_png_bytes(color=(46, 76, 112)):
    buffer = io.BytesIO()
    Image.new("RGB", (96, 96), color).save(buffer, format="PNG")
    return buffer.getvalue()


def square_image_bytes(image_format, color=(46, 76, 112)):
    buffer = io.BytesIO()
    Image.new("RGB", (96, 96), color).save(buffer, format=image_format)
    return buffer.getvalue()


def instant_experience_csv_result(output_mode=None):
    result = {
        "context_key": "instant-experience-csv-test",
        # Historical CSV fixtures remain nine-row; new active UI is tested separately.
        "_legacy_ie_csv": True,
        "product_name": "Senna’s Legacy — Collector Edition",
        "product_url": "https://www.sportscaveshop.com/products/sennas-legacy-collector-edition",
        "country": "Australia",
        "category": "Motorsport",
        "campaign_type": "Instant Experience",
    }
    if output_mode:
        result["instant_experience_settings"] = {"output_mode": output_mode}
    return result


def instant_experience_csv_notes():
    notes = {}
    for concept_index, concept in enumerate(ads_page.INSTANT_EXPERIENCE_CONCEPTS):
        variations = []
        for variation in range(1, ads_page.INSTANT_EXPERIENCE_COPY_VARIATION_COUNT + 1):
            description_variant = ads_page._instant_experience_description_variant(variation)
            cta = ads_page.INSTANT_EXPERIENCE_APPROVED_CREATIVE_CTAS[
                (concept_index + variation - 1)
                % len(ads_page.INSTANT_EXPERIENCE_APPROVED_CREATIVE_CTAS)
            ]
            if variation == 1:
                cta = ads_page.INSTANT_EXPERIENCE_PRIMARY_IMAGE_CTAS[concept["id"]]
            variations.append(
                {
                    "description_key": description_variant["key"],
                    "description_label": description_variant["label"],
                    "primary_text": (
                        ("This isn’t just wall art. It’s the name you back.\n" if concept_index == 0 else "") +
                        f"{concept['display_name']} variation {variation}, first line.\n" +
                        ("The name means years of loyalty and a collector identity that lasts beyond any result. ",
                         "Recall the anticipation, the atmosphere and the feeling behind this artwork's depicted moment. ",
                         "A specific detail gives knowledgeable fans a different way into the subject's significance. ")[concept_index] +
                        "Second line with \"quotes\", apostrophe’s, ampersand & emoji 🏁. "
                        f"{ads_page.INSTANT_EXPERIENCE_PRIMARY_TEXT_CTA_ENDINGS[cta]}"
                    ),
                    "headline": f"{concept['display_name']} Headline {variation}",
                    "description": "",
                    "cta": cta,
                }
            )
        notes[concept["id"]] = variations
    return notes


def carousel_csv_result():
    return {
        "context_key": "carousel-csv-test",
        "product_name": "Senna’s Legacy — Collector Edition",
        "campaign_type": "Carousel",
    }


def carousel_csv_notes():
    return {
        "headlines": [
            f"Headline {index}, collector’s choice"
            for index in range(1, 6)
        ],
        "descriptions": [
            f"Description {index}\nSecond line, with commas & apostrophe’s."
            for index in range(1, 6)
        ],
        "primary_texts": [
            f"Primary text {index}, first line.\nSecond line — café 🏁"
            for index in range(1, 6)
        ],
        "cards": [
            {
                "position": index,
                "slot_id": f"carousel-{index:02d}",
                "image_filename": f"carousel-image-{index:02d}.jpg",
                "headline": f"Hook, {index}",
                "description": f"Fan's pick {index}",
                "destination_url": (
                    f"https://www.sportscaveshop.com/products/example?card={index}&src=carousel"
                ),
                "cta": "Shop Now",
                "setup_notes": (
                    f"Card {index} note, line one.\nKeep order #{index}."
                    if index < 5
                    else ""
                ),
            }
            for index in range(1, 6)
        ],
        "setup_notes": "Overall setup, first line.\nSecond line with apostrophe’s & symbols.",
    }


def instant_experience_description_payload(
    product_name,
    category,
    *,
    metadata=None,
    country="USA",
):
    context = ads_page.resolve_instant_experience_description_context(
        product_name,
        category,
        product_metadata=metadata or {},
        country=country,
    )
    payload = ads_page.build_instant_experience_description_variants(context)
    copies = {
        variant["key"]: variant["copy"]
        for variant in payload["description_variants"]
    }
    return context, payload, copies


def csv_bytes_from_rows(rows, headers=None):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=list(headers or ads_page.INSTANT_EXPERIENCE_COPY_CSV_HEADERS),
        lineterminator="\r\n",
    )
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")


def instant_experience_settings(output_mode=ads_page.IE_MODE_SMART, **overrides):
    settings = ads_page.default_instant_experience_settings(output_mode=output_mode)
    settings.update(overrides)
    if "advanced_visual" in overrides:
        settings["advanced_visual"] = {
            **ads_page.default_instant_experience_settings()["advanced_visual"],
            **overrides["advanced_visual"],
        }
    return settings


def seed_saved_result(app_test):
    """Exercise the saved-draft renderer without restoring the retired Submit UI."""
    def value(label, default=''):
        for widget in list(app_test.text_input)+list(app_test.selectbox):
            if widget.label==label:return widget.value
        return default
    record=ads_page.build_ads_result_record(value('Product name'),value('Category'),
        value('Country'),value('Campaign type'),product_url=value('Product page URL *'),
        variation_token='saved-renderer-fixture')
    app_test.session_state[ads_page.ADS_RESULT_STATE_KEY]=record
    return app_test.run(timeout=20)


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


def instant_experience_cover_uploaders(app_test):
    cover_labels = {
        f"{concept['scene_name']} Cover"
        for concept in ads_page.INSTANT_EXPERIENCE_CONCEPTS
    }
    return [
        uploader
        for uploader in app_test.file_uploader
        if uploader.label in cover_labels
    ]


def carousel_image_uploaders(app_test):
    return [
        uploader
        for uploader in app_test.file_uploader
        if uploader.label in {f"Carousel {index}" for index in range(1, 6)}
    ]


class AdsPageTests(unittest.TestCase):
    def test_streamlit_config_is_valid_for_local_file_uploads(self):
        with (ROOT / ".streamlit" / "config.toml").open("rb") as config_file:
            config = tomllib.load(config_file)

        self.assertEqual(config["server"]["address"], "0.0.0.0")
        self.assertTrue(config["server"]["headless"])
        self.assertFalse(config["server"]["enableCORS"])
        self.assertFalse(config["server"]["enableXsrfProtection"])
        self.assertFalse(config["browser"]["gatherUsageStats"])

    def test_visible_title_and_navigation_are_ads_only(self):
        app_test = run_ads_page()

        self.assertEqual([title.value for title in app_test.title], ["Ads"])
        self.assertIn("Ads", [button.label for button in app_test.button])
        self.assertNotIn("Marketing Factory", [title.value for title in app_test.title])
        self.assertNotIn("Marketing Factory", [button.label for button in app_test.button])
        self.assertEqual(len(app_test.exception), 0)

    def test_initial_render_defers_result_image_review_and_dropbox_work(self):
        final_review_module = ads_page.ads_final_review._module
        image_workflow_module = ads_page.ads_image_workflow._module
        image_factory_module = ads_page.image_factory._module
        ads_page.ads_final_review._module = None
        ads_page.ads_image_workflow._module = None
        ads_page.image_factory._module = None
        try:
            with (
                patch("ads_page.load_edition_ops_product_rows", return_value=[]),
                patch("ads_page.build_ads_result_record") as build_result,
                patch("ads_page._ads_dropbox_connection") as dropbox_connection,
                patch("ads_page._instant_experience_package_items") as build_package,
            ):
                app_test = AppTest.from_string(
                    "import ads_page\nads_page.render_page()"
                ).run(timeout=20)

            self.assertFalse(app_test.exception)
            build_result.assert_not_called()
            dropbox_connection.assert_not_called()
            build_package.assert_not_called()
            self.assertIsNone(ads_page.ads_final_review._module)
            self.assertIsNone(ads_page.ads_image_workflow._module)
            self.assertIsNone(ads_page.image_factory._module)
            self.assertNotIn(ads_page.ADS_RESULT_STATE_KEY, app_test.session_state)
        finally:
            ads_page.ads_final_review._module = final_review_module
            ads_page.ads_image_workflow._module = image_workflow_module
            ads_page.image_factory._module = image_factory_module

    def test_initial_setup_is_compact_and_optional_sections_start_collapsed(self):
        app_test=run_ads_page()
        expanders={e.label:e.proto.expanded for e in app_test.expander}
        self.assertFalse(expanders['How to use'])
        self.assertFalse(expanders['Canonical black-frame product image'])
        self.assertNotIn('Campaign Moment (Optional)',expanders)

    def test_snapshot_and_selector_caches_are_input_keyed_and_user_safe(self):
        ads_page._read_edition_ops_snapshot_rows.clear()
        ads_page._merge_edition_ops_product_rows.clear()
        ads_page.build_ads_product_selector_records.clear()
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "products.json"
            snapshot.write_text(
                json.dumps({"rows": [{"product_title": "Cached Product"}]}),
                encoding="utf-8",
            )
            original_read_text = Path.read_text
            calls = []

            def tracked_read_text(path, *args, **kwargs):
                calls.append(str(path))
                return original_read_text(path, *args, **kwargs)

            with patch.object(Path, "read_text", autospec=True, side_effect=tracked_read_text):
                first = ads_page._edition_ops_rows_from_local_snapshot(snapshot)
                second = ads_page._edition_ops_rows_from_local_snapshot(snapshot)

            self.assertEqual(first, second)
            self.assertEqual(len(calls), 1)

        nathan_rows = ads_page._merge_edition_ops_product_rows(
            [],
            [{"product_title": "Nathan Product"}],
            [],
        )
        reina_rows = ads_page._merge_edition_ops_product_rows(
            [],
            [{"product_title": "Reina Product"}],
            [],
        )
        self.assertEqual(nathan_rows[0]["product_title"], "Nathan Product")
        self.assertEqual(reina_rows[0]["product_title"], "Reina Product")

        first_records = ads_page.build_ads_product_selector_records(nathan_rows)
        second_records = ads_page.build_ads_product_selector_records(nathan_rows)
        self.assertEqual(first_records, second_records)

    def test_dropdown_options_are_in_required_order(self):
        self.assertEqual(
            ads_page.CATEGORY_OPTIONS,
            list(__import__("sports_categories").sport_category_options("Select category")),
        )
        self.assertEqual(
            ads_page.COUNTRY_OPTIONS,
            ["Select country", "Australia", "Canada", "New Zealand", "UK", "USA"],
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
                self.assertEqual(bool(ads_page.get_template_key(category, "Carousel")), category in ads_page.CATEGORY_WINNER_ANGLES)
                self.assertIsNotNone(ads_page.get_winner_pattern_key(category, "Carousel"))
            with self.subTest(category=category, campaign_type="Instant Experience"):
                self.assertEqual(bool(ads_page.get_template_key(category, "Instant Experience")), category in ads_page.CATEGORY_WINNER_ANGLES)
                self.assertIsNotNone(ads_page.get_winner_pattern_key(category, "Instant Experience"))
            with self.subTest(category=category, campaign_type="Single Image / Video"):
                self.assertEqual(bool(ads_page.get_template_key(category, "Single Image / Video")), category in ads_page.CATEGORY_WINNER_ANGLES)
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
                if category in ads_page.CATEGORY_WINNER_ANGLES:
                    self.assertIn(category, ads_page.CATEGORY_COPY_CUES)
                    self.assertTrue(required_fields.issubset(ads_page.CATEGORY_WINNER_ANGLES[category]))
                else:
                    self.assertEqual(ads_page.get_category_winner_angle(category), {})
                    self.assertEqual(ads_page.get_winner_pattern_key(category, "Carousel"), "generic_carousel")

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
        app_test=run_ads_page()
        set_product_name(app_test,'Verified Edition')
        set_product_url(app_test,'not-a-url')
        self.assertEqual(ads_page.validate_ads_inputs('Verified Edition','Cricket','Australia','Instant Experience',product_url='not-a-url'),ads_page.PRODUCT_URL_ERROR)
        app_test.run(timeout=20)
        self.assertEqual(next(w.value for w in app_test.text_input if w.label=='Product page URL *'),'not-a-url')
        self.assertNotIn(ads_page.ADS_RESULT_STATE_KEY,app_test.session_state)

    def test_product_page_url_validation_has_focus_hook(self):
        source = (ROOT / "ads_page.py").read_text(encoding="utf-8")

        self.assertIn("Product page URL *", source)
        self.assertIn("input.focus()", source)
        self.assertIn(ads_page.PRODUCT_URL_ERROR, source)

    def test_campaign_moment_form_is_optional_and_validates_missing_name(self):
        app_test=run_ads_page()
        # New Ads exposes queue-first setup. Historical campaign moments still validate at the API boundary.
        self.assertNotIn('Moment Type',[w.label for w in app_test.selectbox])
        self.assertIn('Add to queue',[b.label for b in app_test.button])
        self.assertTrue(ads_page.validate_campaign_moment({'type':'Sporting Event'},selected_country='Australia'))
        self.assertEqual(ads_page.validate_campaign_moment({},selected_country='Australia'),'')

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
        self.assertIn("select different supported identity anchors across Cards 1–4", prompt)
        self.assertIn("WHO/WHAT → FAN RECOGNITION → DEFINING HOOK → CAVE OWNERSHIP → AUTHENTIC SCARCITY", prompt)
        self.assertIn("Product facts win when supplied details are sparse", prompt)

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
        self.assertIn("compose_final_ads_prompt(", source)
        with patch.object(ads_page, 'compose_final_ads_prompt', wraps=ads_page.compose_final_ads_prompt) as compose, patch.object(ads_page, 'build_carousel_card_copy_rules', wraps=ads_page.build_carousel_card_copy_rules) as rules:
            prompt = ads_page.build_ads_prompt('Collector', 'Cricket', 'Australia', 'Carousel')
        compose.assert_called_once()
        rules.assert_called_once()
        self.assertIn('CAROUSEL CARD CHARACTER LIMIT', prompt)
        self.assertIn('Maximum 17 characters', prompt)

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

    def test_baseball_instant_experience_prompt_outputs_three_grouped_routes(self):
        record,rows,briefs=current_ie(self,product='Verified Baseball Edition',category='Baseball')
        self.assertEqual([row['route_key'] for row in rows],['premium_scarcity_right','premium_scarcity_front','premium_scarcity_left'])
        self.assertIn('GROUPED INSTANT EXPERIENCE OUTPUT',record['master_prompt'])

    def test_baseball_instant_experience_uses_grouped_copy_rules(self):
        record,rows,briefs=current_ie(self,product='Verified Baseball Edition',category='Baseball')
        self.assertEqual([row['route_key'] for row in rows],['premium_scarcity_right','premium_scarcity_front','premium_scarcity_left'])
        self.assertIn('GROUPED INSTANT EXPERIENCE OUTPUT',record['master_prompt'])

    def test_baseball_instant_experience_approved_claims_are_injected_through_claim_helper(self):
        with patch.object(ads_page,'build_baseball_instant_experience_claim_block',return_value='UNVERIFIED LEGACY CLAIM'):
            record,_,_=current_ie(self,category='Baseball',metadata={'edition_limit':100,'edition_limit_source':'verified fixture'})
        self.assertNotIn('UNVERIFIED LEGACY CLAIM',record['master_prompt'])
        self.assertEqual(record['product_metadata']['edition_limit'],100)

    def test_baseball_instant_experience_setup_uses_required_meta_instructions(self):
        record,_,_=current_ie(self,category='Baseball')
        self.assertIn(record['product_url'],record['master_prompt'])
        self.assertNotIn('collections/baseball',record['master_prompt'])
        self.assertIn('Shop Now',record['master_prompt'])

    def test_shared_meta_url_parameters_are_added_to_every_supported_ads_prompt(self):
        from ads_creation_ui import creation_instructions
        for campaign in ('Carousel','Instant Experience','Single Image / Video'):
            prompt=ads_page.build_ads_prompt('Verified Edition','Cricket','Australia',campaign)
            before=prompt
            displayed=creation_instructions(prompt)
            # Posting owns tracking; formatting the copyable prompt never mutates its saved source.
            self.assertEqual(before,prompt)
            self.assertIn('Verified Edition',displayed)
            self.assertNotIn('Paste this into the Meta URL parameters',displayed)

    def test_meta_tracking_guidance_keeps_paid_channel_and_stable_ids(self):
        guidance = ads_page.build_meta_url_parameters_guidance()
        for parameter in (
            "utm_source=facebook", "utm_medium=paid_social",
            "utm_id={{campaign.id}}", "adset_id={{adset.id}}",
            "ad_id={{ad.id}}", "site_source={{site_source_name}}",
        ):
            with self.subTest(parameter=parameter):
                self.assertIn(parameter, guidance)

    def test_football_instant_experience_works_for_every_supported_country(self):
        for country in ads_page.COUNTRY_OPTIONS:
            record,_,_=current_ie(self,category='Football',country=country)
            self.assertEqual(record['country'],country)
            self.assertIn('Sport: Football',record['master_prompt'])

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
                            f"SPORTS CAVE {category.upper()} CAROUSEL WINNER PATTERN" if category in ads_page.CATEGORY_WINNER_ANGLES else "SPORTS CAVE GENERIC CAROUSEL WINNER PATTERN",
                            prompt,
                        )
                        if category in ads_page.CATEGORY_WINNER_ANGLES:
                            self.assertIn("CATEGORY-SPECIFIC CAROUSEL WINNER ANGLE", prompt)
                        else:
                            self.assertIn("UNIVERSAL SPORTS CAVE WINNER RULES", prompt)
                        for role in required_roles:
                            self.assertIn(role, prompt)

    def test_every_category_returns_instant_experience_output_for_every_supported_country(self):
        for category in ads_page.SUPPORTED_AD_CATEGORIES:
            for country in ads_page.COUNTRY_OPTIONS[1:]:
                current_ie(self,product=f'{category} Collector Moment',category=category,country=country)

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
        import ads_ie_two_line as footer
        record,rows,briefs=current_ie(self,category='Football')
        self.assertIn(footer.FOOTER_RULES,record['master_prompt'])
        for row,brief in zip(rows,briefs):
            self.assertIn(footer.image_copy(row),brief)
            self.assertNotIn(row['meta_headline_text'],brief.split('META HEADLINE')[0])

    def test_added_categories_have_specific_outputs_for_all_campaign_sections(self):
        for category in ('Golf','Rugby Union','Other'):
            current_ie(self,product=f'{category} Collector Moment',category=category)
            for campaign in ('Carousel','Single Image / Video'):
                prompt=ads_page.build_ads_prompt(f'{category} Collector Moment',category,'Australia',campaign)
                self.assertIn(category.upper(),prompt)
                self.assertNotIn('Insufficient winner data',prompt)

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
        record,_,_=current_ie(self,category='Other')
        self.assertNotIn('Insufficient winner data',record['master_prompt'])
        self.assertNotIn('Using generic Sports Cave winner pattern',record['master_prompt'])

    def test_country_selection_changes_wording_only_not_output_availability(self):
        for country in ads_page.COUNTRY_OPTIONS:
            record,_,_=current_ie(self,category='Baseball',country=country)
            self.assertEqual(record['country'],country)
            self.assertIn('Sport: Baseball',record['master_prompt'])

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
        text='This primary text deliberately exceeds the seventeen character card-field limit.'
        self.assertEqual(ads_page.validate_carousel_card_length([{'headline':'Product Hero','description':'Fan Identity','primary_text':text}]),[])
        record,_,_=current_ie(self)
        self.assertNotIn('CAROUSEL CARD CHARACTER LIMIT',record['master_prompt'])

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
        self.assertIn(ads_page.ie_copy.VERSION, instant_prompt)
        self.assertIn("Each group contains AD COPY with one Description, one Headline and one CTA.", instant_prompt)
        self.assertIn("Return exactly THREE active ad-copy combinations total.", instant_prompt)
        self.assertIn("No separate Meta link-description or Meta Ad Description field is allowed.", instant_prompt)
        self.assertIn("Three different opening sentences and emotional propositions", instant_prompt)

        self.assertNotIn(ads_page.META_WINNER_COPY_BLOCK_VERSION, single_prompt)

    def test_factual_wording_gate_is_injected_once_into_every_ads_request(self):
        for campaign in ('Carousel','Instant Experience','Single Image / Video'):
            prompt=ads_page.build_ads_prompt('Verified Collector Edition','Cricket','Australia',campaign)
            self.assertRegex(prompt.casefold(),r'(?:never|not) invent')
            self.assertIn('Verified Collector Edition',prompt)

    def test_factual_wording_gate_treats_vs_and_teammates_as_ambiguous(self):
        gate = ads_page.SPORTS_CAVE_ADS_FACTUAL_WORDING_GATE_V1
        prompt = ads_page.build_ads_prompt(
            "Papaya Pressure: Piastri vs Norris Wall Art",
            "Motorsport",
            "Australia",
            "Instant Experience",
            variation_token="ambiguous-vs",
        )

        self.assertIn("Papaya Pressure: Piastri vs Norris Wall Art", prompt)
        self.assertIn(
            'Two named people or a title containing "vs" does not by itself prove rivalry',
            gate,
        )
        self.assertIn(
            "The subjects may be teammates, contemporaries, comparisons or opposing subjects.",
            gate,
        )
        self.assertIn(
            "Teammate context must never be contradicted by invented rivalry or hostility.",
            gate,
        )
        self.assertNotIn("Piastri", gate)
        self.assertNotIn("Norris", gate)

    def test_factual_wording_gate_allows_verified_rivalry_and_simplifies_unsupported_claims(self):
        gate = ads_page.SPORTS_CAVE_ADS_FACTUAL_WORDING_GATE_V1

        self.assertIn(
            "equivalent relationship wording is permitted only when that relationship is explicitly supported by verified facts",
            gate,
        )
        self.assertIn(
            "Never invent or imply a victory, championship, record, historic moment, venue, date, rivalry status",
            gate,
        )
        self.assertIn(
            "rewrite only that line with a simpler emotional phrase",
            gate,
        )
        self.assertIn(
            "Do not hardcode one replacement phrase or universal CTA",
            gate,
        )

    def test_factual_wording_gate_propagates_exact_approved_copy_to_image_prompts(self):
        gate = ads_page.SPORTS_CAVE_ADS_FACTUAL_WORDING_GATE_V1

        self.assertIn(
            "propagate the exact approved wording consistently everywhere it appears",
            gate,
        )
        self.assertIn(
            "including copy tables, setup copy where relevant and the corresponding image-generation prompt",
            gate,
        )
        self.assertIn(
            "The exact Headline, CTA and supporting wording approved for an image must match the wording written inside that image prompt.",
            gate,
        )
        self.assertIn(
            "Perform this check silently when generating the ad output. Do not output warnings, research notes, rejected alternatives or internal reasoning.",
            gate,
        )
        self.assertIn(
            "In review requests, apply the same factual check inside the existing review fields without adding or removing review sections.",
            gate,
        )

    def test_staccato_and_framed_greatness_rules_are_reusable_and_fact_safe(self):
        import ads_ie_legacy_description as legacy
        normal=legacy.build_new_ad_style_rules('Verified Edition','NBA',{})
        verified=legacy.build_new_ad_style_rules('Verified Edition','NBA',{'EDITION_LIMIT':250})
        self.assertIn('Limited to 100 worldwide.',normal)
        self.assertIn('Limited to 100 worldwide.',verified)
        self.assertNotIn('Limited to 250',verified)
        self.assertIn('invented',legacy.DESCRIPTION_WORDING_INSTRUCTIONS.casefold())

    def test_shared_winner_copy_upgrade_is_idempotent_and_preserves_custom_text(self):
        custom_prompt = "CUSTOM SAVED INSTRUCTION\nKeep this exact specialist direction."

        once = ads_page.apply_shared_meta_winner_copy_upgrade(custom_prompt, "Carousel")
        twice = ads_page.apply_shared_meta_winner_copy_upgrade(once, "Carousel")

        self.assertEqual(once, twice)
        self.assertEqual(once.count(ads_page.META_WINNER_COPY_BLOCK_VERSION), 1)
        self.assertIn(custom_prompt, once)
        self.assertIn("If the approved campaign-specific template requires exactly one primary text", once)
        self.assertNotIn(ads_page.ie_copy.VERSION, once)
        self.assertIn(
            ads_page.ie_copy.VERSION,
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

        self.assertEqual(prompt.count("ONE PERSONALISED COPY SET PER VISUAL"), 1)
        self.assertIn(ads_page.ie_copy.VERSION, prompt)
        self.assertIn("Each group contains AD COPY with one Description, one Headline and one CTA.", prompt)
        self.assertIn("Return exactly THREE active ad-copy combinations total.", prompt)
        self.assertIn("No row may be placeholder copy.", prompt)
        self.assertNotIn("PRIMARY TEXT VARIATIONS\n\nVariation 1:", prompt)
        self.assertNotIn("Return one final primary text only.", prompt)

    def test_baseball_instant_experience_receives_country_localisation_without_changing_baseball_terms(self):
        for country in ads_page.COUNTRY_OPTIONS:
            record,_,_=current_ie(self,category='Baseball',country=country)
            self.assertEqual(record['country'],country)
            self.assertIn('Sport: Baseball',record['master_prompt'])

    def test_baseball_instant_experience_does_not_change_other_campaigns_or_sports(self):
        for category in ('Baseball','NBA','Football'):
            record,_,_=current_ie(self,category=category)
            self.assertEqual(record['category'],category)
        for campaign in ('Carousel','Single Image / Video'):
            record=ads_page.build_ads_result_record('Verified Baseball Edition','Baseball','Australia',campaign)
            self.assertEqual(record['campaign_type'],campaign)

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
        moment={'type':'Gifting Occasion','name':'Father’s Day','market':'Australia','promotion':'15% off 2+ editions'}
        for campaign in ('Carousel','Instant Experience','Single Image / Video'):
            record=ads_page.build_ads_result_record('Verified Edition','Cricket','Australia',campaign,campaign_moment=moment)
            self.assertEqual(record['campaign_moment']['name'],'Father’s Day')
            self.assertEqual(record['campaign_moment']['promotion'],'15% off 2+ editions')
            self.assertEqual(json.loads(json.dumps(record))['campaign_moment'],record['campaign_moment'])

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
        moment={'type':'Gifting Occasion','name':'Father’s Day','market':'Australia','include_in_image_prompts':False}
        self.assertEqual(ads_page.build_campaign_moment_visual_context(moment,selected_country='Australia'),'')
        moment['include_in_image_prompts']=True
        self.assertIn('Father’s Day',ads_page.build_campaign_moment_visual_context(moment,selected_country='Australia'))

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
        self.assertIn("CARD 5 PRODUCT-PROMINENT LIFESTYLE SCARCITY — MANDATORY:", contract)

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
        self.assertIn("build_ads_product_selector_records(rows)", source)
        self.assertIn('st.selectbox(\n            "Product name"', source)
        self.assertIn("accept_new_options=True", source)
        self.assertIn('filter_mode="fuzzy"', source)
        self.assertIn("format_func=lambda identity", source)
        self.assertIn("key=ADS_PRODUCT_SELECTOR_KEY", source)
        self.assertIn("EDITION_OPS_SNAPSHOT_PATH", source)
        self.assertNotIn("import edition_ops", source)

    def test_shared_live_catalogue_joins_authoritative_product_url(self):
        captured = {}
        expected_rows = [
            {
                "shopify_product_id": "product-123",
                "product_title": "Six Laps Ahead",
                "product_handle": "six-laps-ahead",
                "online_store_url": "https://www.sportscaveshop.com/products/six-laps-ahead",
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
                "online_store_url": "https://www.sportscaveshop.com/products/six-laps-ahead",
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
                "online_store_url": "https://www.sportscaveshop.com/products/six-laps-ahead",
            }
        ]
        session_state = {}

        with patch.object(ads_page.st, "session_state", session_state):
            state = ads_page.prepare_ads_product_url_state("Six Laps Ahead", rows=rows)

        self.assertEqual(state["product_id"], "product-123")
        self.assertEqual(
            session_state[ads_page.ADS_PRODUCT_URL_KEY],
            "https://www.sportscaveshop.com/products/six-laps-ahead",
        )
        self.assertEqual(session_state[ads_page.ADS_PRODUCT_URL_AUTOFILL_PRODUCT_KEY], "id::product-123")
        self.assertEqual(state["message"], "")

    def test_ads_product_url_manual_edit_survives_reruns_until_product_changes(self):
        rows = [
            {
                "product_id": "product-123",
                "product_title": "Six Laps Ahead",
                "online_store_url": "https://www.sportscaveshop.com/products/six-laps-ahead",
            },
            {
                "product_id": "product-456",
                "product_title": "Bathurst Winner",
                "online_store_url": "https://www.sportscaveshop.com/products/bathurst-winner",
            },
        ]
        session_state = {}

        with patch.object(ads_page.st, "session_state", session_state):
            ads_page.prepare_ads_product_url_state("Six Laps Ahead", rows=rows)
            session_state[ads_page.ADS_PRODUCT_URL_KEY] = "https://www.sportscaveshop.com/products/manual-campaign-url"
            ads_page._on_ads_product_url_changed()
            ads_page.prepare_ads_product_url_state("Six Laps Ahead", rows=rows)

            self.assertEqual(
                session_state[ads_page.ADS_PRODUCT_URL_KEY],
                "https://www.sportscaveshop.com/products/manual-campaign-url",
            )

            ads_page.prepare_ads_product_url_state("Bathurst Winner", rows=rows)

        self.assertEqual(
            session_state[ads_page.ADS_PRODUCT_URL_KEY],
            "https://www.sportscaveshop.com/products/bathurst-winner",
        )
        self.assertEqual(session_state[ads_page.ADS_PRODUCT_URL_AUTOFILL_PRODUCT_KEY], "id::product-456")

    def test_ads_product_url_handles_missing_url_and_cleared_product(self):
        rows = [
            {
                "product_id": "product-empty",
                "product_title": "No URL Product",
                "online_store_url": "not-a-url",
            }
        ]
        session_state = {
            ads_page.ADS_PRODUCT_URL_KEY: "https://www.sportscaveshop.com/products/manual-url",
            ads_page.ADS_PRODUCT_URL_AUTOFILL_PRODUCT_KEY: "previous-product",
        }

        with patch.object(ads_page.st, "session_state", session_state):
            state = ads_page.prepare_ads_product_url_state("No URL Product", rows=rows)

            self.assertEqual(session_state[ads_page.ADS_PRODUCT_URL_KEY], "")
            self.assertEqual(state["message"], ads_page.NO_EDITION_OPS_PRODUCT_URL_MESSAGE)

            session_state[ads_page.ADS_PRODUCT_URL_KEY] = "https://www.sportscaveshop.com/products/manual-url"
            session_state[ads_page.ADS_PRODUCT_URL_AUTOFILL_PRODUCT_KEY] = "product-empty"
            ads_page.prepare_ads_product_url_state("", rows=rows)

        self.assertEqual(session_state[ads_page.ADS_PRODUCT_URL_KEY], "")
        self.assertEqual(session_state[ads_page.ADS_PRODUCT_URL_AUTOFILL_PRODUCT_KEY], "")

    def test_draft_restoration_does_not_override_authoritative_selected_product_url(self):
        rows = [
            {
                "product_id": "product-123",
                "product_title": "Six Laps Ahead",
                "online_store_url": "https://www.sportscaveshop.com/products/edition-ops-url",
            },
            {
                "product_id": "product-456",
                "product_title": "Bathurst Winner",
                "online_store_url": "https://www.sportscaveshop.com/products/bathurst-winner",
            },
        ]
        result = {
            "product_id": "product-123",
            "product_name": "Six Laps Ahead",
            "product_url": "https://www.sportscaveshop.com/products/saved-draft-url",
        }
        session_state = {}

        with patch.object(ads_page.st, "session_state", session_state):
            ads_page.prepare_ads_product_url_state("Six Laps Ahead", result=result, rows=rows)

            self.assertEqual(
                session_state[ads_page.ADS_PRODUCT_URL_KEY],
                "https://www.sportscaveshop.com/products/edition-ops-url",
            )

            ads_page.prepare_ads_product_url_state("Bathurst Winner", result=result, rows=rows)

        self.assertEqual(
            session_state[ads_page.ADS_PRODUCT_URL_KEY],
            "https://www.sportscaveshop.com/products/bathurst-winner",
        )

    def test_duplicate_ads_product_names_resolve_url_through_stable_record(self):
        rows = [
            {
                "product_id": "product-a",
                "product_title": "Untitled Product",
                "shopify_handle": "legends-never-die",
                "online_store_url": "https://www.sportscaveshop.com/products/legends-never-die",
            },
            {
                "product_id": "product-b",
                "product_title": "Untitled Product",
                "shopify_handle": "goat-debate-wall-art",
                "online_store_url": "https://www.sportscaveshop.com/products/goat-debate-wall-art",
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
            "https://www.sportscaveshop.com/products/goat-debate-wall-art",
        )

    def test_stable_product_id_resolves_ambiguous_display_name(self):
        rows = [
            {
                "product_id": "product-a",
                "product_title": "Untitled Product",
                "shopify_handle": "legends-never-die",
                "online_store_url": "https://www.sportscaveshop.com/products/legends-never-die",
            },
            {
                "product_id": "product-b",
                "product_title": "Untitled Product",
                "shopify_handle": "goat-debate-wall-art",
                "online_store_url": "https://www.sportscaveshop.com/products/goat-debate-wall-art",
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
            "https://www.sportscaveshop.com/products/goat-debate-wall-art",
        )

    def test_legacy_exact_name_matching_handles_punctuation_without_fuzzy_collisions(self):
        rows = [
            {
                "product_title": "Driver’s Legacy – 1998",
                "online_store_url": "https://www.sportscaveshop.com/products/drivers-legacy-1998",
            },
            {
                "product_title": "Driver’s Legacy – 1998 Revisited",
                "online_store_url": "https://www.sportscaveshop.com/products/drivers-legacy-revisited",
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
            "https://www.sportscaveshop.com/products/drivers-legacy-1998",
        )
        self.assertIsNone(similar_name["row"])

    def test_unknown_product_change_clears_previous_manual_url_and_shows_message(self):
        rows = [
            {
                "product_id": "product-a",
                "product_title": "Known Product",
                "online_store_url": "https://www.sportscaveshop.com/products/known-product",
            }
        ]
        session_state = {}

        with patch.object(ads_page.st, "session_state", session_state):
            ads_page.prepare_ads_product_url_state("Known Product", rows=rows)
            session_state[ads_page.ADS_PRODUCT_URL_KEY] = (
                "https://www.sportscaveshop.com/products/manual-campaign-url"
            )
            state = ads_page.prepare_ads_product_url_state("Unknown Product", rows=rows)

        self.assertEqual(session_state[ads_page.ADS_PRODUCT_URL_KEY], "")
        self.assertEqual(state["message"], ads_page.NO_EDITION_OPS_PRODUCT_URL_MESSAGE)

    def test_product_url_flows_to_ads_and_instant_experience_destination_output(self):
        product_url = "https://www.sportscaveshop.com/products/six-laps-ahead"
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
        self.assertIn("selection=product_selection", render_page_source)
        self.assertIn(url_widget, render_page_source)
        self.assertIn("key=ADS_PRODUCT_URL_KEY", render_page_source)
        self.assertIn("on_change=_on_ads_product_url_changed", render_page_source)
        self.assertLess(render_page_source.index(prepare_call), render_page_source.index(url_widget))
        self.assertNotIn(
            "st.session_state[ADS_PRODUCT_URL_KEY]",
            render_page_source[render_page_source.index(url_widget) :],
        )

    def test_rendered_ads_selector_autofills_switches_clears_and_preserves_real_manual_edits(self):
        rows = [
            {
                "product_id": "product-a",
                "product_title": "Product A",
                "shopify_handle": "product-a",
                "online_store_url": "https://www.sportscaveshop.com/products/product-a",
            },
            {
                "product_id": "product-b",
                "product_title": "Product B",
                "shopify_handle": "product-b",
                "online_store_url": "https://www.sportscaveshop.com/products/product-b",
            },
        ]
        app_test = run_ads_page_with_product_rows(rows)
        product_selector = next(
            selectbox for selectbox in app_test.selectbox if selectbox.label == "Product name"
        )
        product_selector.select("Product A")
        app_test.run(timeout=20)
        product_url = next(
            text_input
            for text_input in app_test.text_input
            if text_input.label == "Product page URL *"
        )
        self.assertEqual(
            product_url.value,
            "https://www.sportscaveshop.com/products/product-a",
        )

        product_url.set_value("https://www.sportscaveshop.com/products/product-a-campaign")
        app_test.run(timeout=20)
        select_option(app_test, "Category", "Motorsport")
        product_url = next(
            text_input
            for text_input in app_test.text_input
            if text_input.label == "Product page URL *"
        )
        self.assertEqual(
            product_url.value,
            "https://www.sportscaveshop.com/products/product-a-campaign",
        )

        product_url.set_value("")
        app_test.run(timeout=20)
        select_option(app_test, "Country", "Australia")
        product_url = next(
            text_input
            for text_input in app_test.text_input
            if text_input.label == "Product page URL *"
        )
        self.assertEqual(product_url.value, "")
        self.assertTrue(
            app_test.session_state[ads_page.ADS_PRODUCT_URL_MANUALLY_EDITED_KEY]
        )

        product_selector = next(
            selectbox for selectbox in app_test.selectbox if selectbox.label == "Product name"
        )
        product_selector.select("Product B")
        app_test.run(timeout=20)
        self.assertEqual(
            next(
                text_input
                for text_input in app_test.text_input
                if text_input.label == "Product page URL *"
            ).value,
            "https://www.sportscaveshop.com/products/product-b",
        )

        product_selector = next(
            selectbox for selectbox in app_test.selectbox if selectbox.label == "Product name"
        )
        product_selector.select(None)
        app_test.run(timeout=20)
        self.assertEqual(
            next(
                text_input
                for text_input in app_test.text_input
                if text_input.label == "Product page URL *"
            ).value,
            "",
        )
        self.assertEqual(
            app_test.session_state[ads_page.ADS_PRODUCT_URL_AUTOFILL_PRODUCT_KEY],
            "",
        )
        self.assertEqual(len(app_test.exception), 0)

    def test_rendered_ads_page_repairs_stale_blank_url_for_selected_product(self):
        rows = [
            {
                "product_id": "product-a",
                "product_title": "Product A",
                "shopify_handle": "product-a",
                "online_store_url": "https://www.sportscaveshop.com/products/product-a",
            }
        ]
        app_test = run_ads_page_with_product_rows(
            rows,
            **{
                ads_page.ADS_PRODUCT_SELECTOR_KEY: "id::product-a",
                ads_page.ADS_PRODUCT_NAME_KEY: "Product A",
                ads_page.ADS_PRODUCT_URL_KEY: "",
                ads_page.ADS_PRODUCT_URL_AUTOFILL_PRODUCT_KEY: "id::product-a",
                ads_page.ADS_PRODUCT_URL_AUTOFILL_SELECTION_KEY: "Product A",
                ads_page.ADS_PRODUCT_URL_LAST_AUTO_VALUE_KEY: (
                    "https://www.sportscaveshop.com/products/product-a"
                ),
            },
        )

        product_url = next(
            text_input
            for text_input in app_test.text_input
            if text_input.label == "Product page URL *"
        )
        self.assertEqual(
            product_url.value,
            "https://www.sportscaveshop.com/products/product-a",
        )
        self.assertTrue(
            app_test.session_state[ads_page.ADS_PRODUCT_URL_INITIALIZED_KEY]
        )
        self.assertFalse(
            app_test.session_state[ads_page.ADS_PRODUCT_URL_MANUALLY_EDITED_KEY]
        )
        self.assertEqual(len(app_test.exception), 0)

    def test_rendered_ads_product_without_url_stays_editable_and_shows_message(self):
        rows = [
            {
                "product_id": "product-empty",
                "product_title": "No URL Product",
                "shopify_handle": "",
                "online_store_url": "",
            }
        ]
        app_test = run_ads_page_with_product_rows(rows)
        product_selector = next(
            selectbox for selectbox in app_test.selectbox if selectbox.label == "Product name"
        )
        product_selector.select("No URL Product")
        app_test.run(timeout=20)

        product_url = next(
            text_input
            for text_input in app_test.text_input
            if text_input.label == "Product page URL *"
        )
        self.assertEqual(product_url.value, "")
        self.assertIn(
            ads_page.NO_EDITION_OPS_PRODUCT_URL_MESSAGE,
            [caption.value for caption in app_test.caption],
        )
        product_url.set_value("https://www.sportscaveshop.com/products/manual-destination")
        app_test.run(timeout=20)
        self.assertEqual(
            next(
                text_input
                for text_input in app_test.text_input
                if text_input.label == "Product page URL *"
            ).value,
            "https://www.sportscaveshop.com/products/manual-destination",
        )
        self.assertEqual(len(app_test.exception), 0)

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
        self.assertIn("Require a subtle 5–12 degree off-axis / slight three-quarter camera angle", card_one)
        self.assertNotIn("almost perfectly straight-on", card_one)
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

        self.assertIn("CARD 5 PRODUCT-PROMINENT LIFESTYLE SCARCITY — MANDATORY:", sections[5])
        self.assertIn("fourth distinct premium lifestyle room", sections[5])
        self.assertIn("45-65% of the useful square composition", sections[5])
        self.assertIn("Keep a genuine edition plate/badge readable", sections[5])
        self.assertIn("invent an edition number", sections[5])
        self.assertIn("Never alter or magnify printed pixels artificially", sections[5])
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
                self.assertIn("genuine high-end product photograph" if index == 1 else "genuine high-end interior photograph", section)
                self.assertIn("Create realistic contact shadows behind and below the frame.", section)
                self.assertIn("subtle, controlled glass reflections without obscuring the artwork", section)
                material_depth = "convincing depth in its exact source material" if index == 1 else "convincing depth in the exact source frame material"
                self.assertIn(f"{material_depth}, sharp corners, natural texture and accurate mounting", section)
                self.assertIn("Avoid warped walls, bent furniture, duplicate objects", section)
                self.assertIn("No people, furniture or decor" if index == 1 else "Do not add people unless the individual carousel concept explicitly requires them", section)
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
            self.assertNotIn("CARD 5 PRODUCT-PROMINENT LIFESTYLE SCARCITY — MANDATORY:", contract)
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
        # Ads keeps its existing foundation independently of the retired Mockups card.
        self.assertNotIn(
            image_factory.CLOSE_UP_WALL_PROMPT_FILENAME,
            [item["filename"] for item in prompt_items],
        )
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
        self.assertIn("PREMIUM SCARCITY — RIGHT ANGLE", instant_notes)
        self.assertIn("Slight right-angle product photograph", instant_notes)
        self.assertIn(
            "Description 1 — Legacy Standard\r\nDESCRIPTION KEY:\r\n"
            "legacy_standard\r\nDESCRIPTION COPY:\r\nPrimary option 1",
            instant_notes,
        )
        self.assertIn("PREMIUM SCARCITY — STRAIGHT ON", instant_notes)
        self.assertIn("Straight-on product photograph", instant_notes)
        self.assertIn(
            "Description 1 — Legacy Standard\r\nDESCRIPTION KEY:\r\n"
            "legacy_standard\r\nDESCRIPTION COPY:\r\nPrimary option 2\r\nwith preserved second line",
            instant_notes,
        )
        self.assertIn(
            "Description 2 — Framed Greatness\r\nDESCRIPTION KEY:\r\n"
            "framed_greatness\r\nDESCRIPTION COPY:\r\nPrimary option 3",
            instant_notes,
        )
        self.assertIn("PREMIUM SCARCITY — LEFT ANGLE", instant_notes)
        self.assertIn("Slight left-angle product photograph", instant_notes)
        self.assertIn(
            "Description 1 — Legacy Standard\r\nDESCRIPTION KEY:\r\n"
            "legacy_standard\r\nDESCRIPTION COPY:\r\nPrimary option 5",
            instant_notes,
        )
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
        self.assertIn("Card 2: supported fan identity with memory or present-day connection.", contract)
        self.assertIn("Card 3: a defining verified product hook distinct from Card 1.", contract)
        self.assertIn("Card 4: For The Cave ownership in the mandatory Sports Cave environment.", contract)
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
        for campaign in ('Carousel','Instant Experience','Single Image / Video'):
            prompt=ads_page.build_ads_prompt('Verified Collector Edition','Cricket','Australia',campaign)
            self.assertIn(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER,prompt)
            self.assertNotIn('SOCIAL CONTENT',prompt)
            self.assertRegex(prompt.casefold(),r'(?s)preserve.*(?:frame|product)')
            if campaign=='Instant Experience':
                # The common block is included once, then expanded for each separate call.
                self.assertEqual(prompt.count(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER),1)
                current_ie(self)

    def test_ads_visual_contracts_do_not_receive_social_specific_instructions(self):
        for campaign in ('Carousel','Instant Experience','Single Image / Video'):
            prompt=ads_page.build_ads_prompt('Verified Collector Edition','Cricket','Australia',campaign)
            self.assertIn(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER,prompt)
            self.assertNotIn('SOCIAL CONTENT',prompt)
            self.assertRegex(prompt.casefold(),r'(?s)preserve.*(?:frame|product)')
            if campaign=='Instant Experience':
                # The common block is included once, then expanded for each separate call.
                self.assertEqual(prompt.count(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER),1)
                current_ie(self)

    def test_every_ads_prompt_requires_text_first_no_automatic_image_generation(self):
        current_ie(self)
        # The active IE contract executes three images. Carousel remains text-first.
        prompt=ads_page.build_ads_prompt('Verified Edition','Cricket','Australia','Carousel')
        self.assertIn('Within this text-only scope, do not use an image-generation tool.',prompt)
        self.assertIn('only to copy-only or prompt-only requests',prompt)
        self.assertEqual(len(carousel_prompt_card_sections(visual_contract(prompt))),5)

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
        prompt=ads_page.build_ads_prompt('Verified Edition','Motorsport','Australia','Carousel')
        sections=carousel_prompt_card_sections(visual_contract(prompt))
        self.assertEqual(list(sections),[1,2,3,4,5])
        for index,section in sections.items():
            self.assertIn(f'CARD {index} IMAGE GENERATION PROMPT',section)
            self.assertIn('SQUARE FORMAT',section)
        self.assertIn('Would you like me to generate Card 1?',prompt)

    def test_instant_experience_offer_serializes_without_moment_type(self):
        moment={'type':'Gifting Occasion','name':'Father’s Day','market':'Australia','promotion':'15% off 2+ editions'}
        for campaign in ('Carousel','Instant Experience','Single Image / Video'):
            record=ads_page.build_ads_result_record('Verified Edition','Cricket','Australia',campaign,campaign_moment=moment)
            self.assertEqual(record['campaign_moment']['name'],'Father’s Day')
            self.assertEqual(record['campaign_moment']['promotion'],'15% off 2+ editions')
            self.assertEqual(json.loads(json.dumps(record))['campaign_moment'],record['campaign_moment'])

    def test_instant_experience_prompt_resolves_three_visual_formats(self):
        from ads_ie_legacy_description import NEW_AD_STYLE_KEYS
        record,_,_=current_ie(self,category='NBA')
        for style in NEW_AD_STYLE_KEYS:self.assertIn(style,record['master_prompt'])
        self.assertEqual(record['master_prompt'].count('\nAD COPY\n'),3)
        self.assertNotIn('COPY VARIATIONS',record['master_prompt'])

    def test_instant_experience_v4_product_aware_room_selection_and_fallback(self):
        record,rows,_=current_ie(self,category='Motorsport')
        reopened=ads_page.build_ads_result_record(record['product_name'],record['category'],record['country'],'Instant Experience',
            product_metadata=json.loads(json.dumps(record['product_metadata'])),variation_token='different-token')
        for key in ('instant_experience_scene_selections','instant_experience_footer_selections'):
            self.assertEqual(record['product_metadata'][key],reopened['product_metadata'][key])
        self.assertTrue(rows[0]['camera_side'].startswith('RIGHT'))
        self.assertIn('front',rows[1]['camera_side'].casefold())
        self.assertTrue(rows[2]['camera_side'].startswith('LEFT'))

    def test_instant_experience_camera_and_room_roles_remain_locked_across_seeds(self):
        record,rows,_=current_ie(self,category='Motorsport')
        reopened=ads_page.build_ads_result_record(record['product_name'],record['category'],record['country'],'Instant Experience',
            product_metadata=json.loads(json.dumps(record['product_metadata'])),variation_token='different-token')
        for key in ('instant_experience_scene_selections','instant_experience_footer_selections'):
            self.assertEqual(record['product_metadata'][key],reopened['product_metadata'][key])
        self.assertTrue(rows[0]['camera_side'].startswith('RIGHT'))
        self.assertIn('front',rows[1]['camera_side'].casefold())
        self.assertTrue(rows[2]['camera_side'].startswith('LEFT'))

    def test_instant_experience_description_schema_order_and_connected_legends(self):
        context, payload, copies = instant_experience_description_payload(
            "Jordan and Bryant Legacy Only 100 Will Ever Exist",
            "Basketball",
            metadata={
                "athlete_names": ["Michael Jordan", "Kobe Bryant"],
                "relationship_type": "Inspiration or succession",
                "edition_limit": 100,
                "edition_limit_source": "unit test",
                "is_numbered": True,
                "no_reprint_verified": True,
                "retires_when_sold_out": True,
            },
        )

        self.assertTrue(ads_page.validate_instant_experience_description_variants(payload))
        self.assertEqual(
            [variant["key"] for variant in payload["description_variants"]],
            ["legacy_standard", "framed_greatness", "choose_a_side"],
        )
        self.assertEqual(context["ARTWORK_TYPE"], "Two connected legends")
        self.assertEqual(context["RELATIONSHIP_TYPE"], "Inspiration or succession")
        self.assertIn("The same standard.", copies["legacy_standard"])
        self.assertIn("This isn't wall art.", copies["legacy_standard"])
        self.assertIn("Limited to 100 worldwide.", copies["legacy_standard"])
        self.assertIn("When they're gone, they're gone.", copies["legacy_standard"])
        self.assertIn("A numbered collector drop.", copies["framed_greatness"])
        self.assertIn("No reprint.", copies["framed_greatness"])
        self.assertIn("No second run.", copies["framed_greatness"])
        self.assertIn("Wrong question.", copies["choose_a_side"])
        self.assertIn("Only 100 exist.", copies["choose_a_side"])
        self.assertNotIn("No middle ground.", copies["choose_a_side"])
        self.assertNotRegex("\n".join(copies.values()), r"\{\{[^}]+\}\}")

    def test_instant_experience_description_rivalry_single_team_historic_and_motorsport_cases(self):
        import ads_ie_legacy_description as legacy
        for product,sport,context in [('Verified Athlete','Cricket',{'ARTWORK_TYPE':'Single athlete'}),('Verified Team','NBA',{'ARTWORK_TYPE':'Team'}),('Verified Race','Motorsport',{'ARTWORK_TYPE':'historic moment'})]:
            rules=legacy.build_new_ad_style_rules(product,sport,context)
            self.assertIn(product,rules)
            self.assertIn('rivalry requires verified rivalry',rules)
            self.assertIn('never invent',rules)
            self.assertIn('Limited to 100 worldwide.',rules)

    def test_instant_experience_description_scarcity_gates_and_missing_metadata(self):
        import ads_ie_legacy_description as legacy
        normal=legacy.build_new_ad_style_rules('Verified Edition','NBA',{})
        verified=legacy.build_new_ad_style_rules('Verified Edition','NBA',{'EDITION_LIMIT':250})
        self.assertIn('Limited to 100 worldwide.',normal)
        self.assertIn('Limited to 100 worldwide.',verified)
        self.assertNotIn('Limited to 250',verified)
        self.assertIn('invented',legacy.DESCRIPTION_WORDING_INSTRUCTIONS.casefold())

    def test_instant_experience_description_prompt_reuses_same_ordered_options_for_all_routes(self):
        from ads_ie_legacy_description import NEW_AD_STYLE_KEYS
        record,_,_=current_ie(self,category='NBA')
        for style in NEW_AD_STYLE_KEYS:self.assertIn(style,record['master_prompt'])
        self.assertEqual(record['master_prompt'].count('\nAD COPY\n'),3)
        self.assertNotIn('COPY VARIATIONS',record['master_prompt'])

    def test_instant_experience_image_prompts_keep_lower_panel_copy_separate_from_descriptions(self):
        import ads_ie_two_line as footer
        record,rows,briefs=current_ie(self,category='Football')
        self.assertIn(footer.FOOTER_RULES,record['master_prompt'])
        for row,brief in zip(rows,briefs):
            self.assertIn(footer.image_copy(row),brief)
            self.assertNotIn(row['meta_headline_text'],brief.split('META HEADLINE')[0])

    def test_instant_experience_does_not_use_obsolete_collection_destination(self):
        record,_,_=current_ie(self,category='Baseball')
        self.assertIn(record['product_url'],record['master_prompt'])
        self.assertNotIn('collections/baseball',record['master_prompt'])
        self.assertIn('Shop Now',record['master_prompt'])

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
            {
                "Framed Greatness Scarcity Hybrid",
                "Pure Limited-Release Scarcity",
                "Collector Proof Scarcity",
            },
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
        record=ads_page.build_ads_result_record('Verified Edition','Cricket','UK','Single Image / Video')
        self.assertEqual(record['campaign_type'],'Single Image / Video')
        self.assertEqual(len(ads_page._result_image_slots(record)),3)
        self.assertNotIn('CARD 1 IMAGE GENERATION PROMPT',record['master_prompt'])

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
        app_test=run_ads_page()
        self.assertIn('Add to queue',[b.label for b in app_test.button])
        self.assertNotIn('Submit',[b.label for b in app_test.button])
        self.assertFalse(app_test.exception)

    def test_supported_prompt_uses_copy_button_instead_of_visible_prompt_code(self):
        source = (ROOT / "ads_page.py").read_text(encoding="utf-8")
        supported_result_source = source[source.index("def render_supported_result") : source.index("def render_page")]

        self.assertIn("def render_prompt_copy_button", source)
        self.assertIn("components.html", source)
        self.assertIn("navigator.clipboard.writeText(promptText)", source)
        self.assertIn("render_prompt_copy_button(", supported_result_source)
        self.assertNotIn("st.code(build_ads_prompt", supported_result_source)

    def test_generated_image_uploads_include_compact_setup_notes_before_save(self):
        import inspect,ads_auto_post
        source=inspect.getsource(ads_auto_post.save_and_queue)
        self.assertLess(source.index('save_ads_images_to_dropbox'),source.index('queue_saved_package'))
        self.assertIn('_ads_saved_source_signature',source)
        self.assertIn('source_signature',source)
        self.assertIn('posting_package_error',source)

    def test_instant_experience_copy_fields_are_grouped_by_three_concepts(self):
        record,_,_=current_ie(self)
        concepts=ads_page._ie_concepts_for_result(record)
        self.assertEqual([c['id'] for c in concepts],[c['id'] for c in ads_page.INSTANT_EXPERIENCE_CONCEPTS])
        self.assertTrue(all(c['display_name']==c['scene_name'] for c in concepts))
        self.assertEqual(len(ads_page._instant_experience_copy_csv_expected_rows(record)),3)

    def test_carousel_csv_template_has_versioned_ordered_example_rows(self):
        result = carousel_csv_result()
        data = ads_page.build_carousel_copy_csv(result, {}, template=True)
        rows = list(
            csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline=""))
        )

        self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(tuple(rows[0]), ads_page.CAROUSEL_COPY_CSV_HEADERS)
        self.assertEqual(len(rows), 21)
        self.assertEqual(
            [(row["row_type"], row["position"]) for row in rows],
            [
                *(("headline", str(position)) for position in range(1, 6)),
                *(("description", str(position)) for position in range(1, 6)),
                *(("primary_text", str(position)) for position in range(1, 6)),
                *(("card", str(position)) for position in range(1, 6)),
                ("setup_notes", ""),
            ],
        )
        card_rows = [row for row in rows if row["row_type"] == "card"]
        self.assertEqual(
            [row["slot_id"] for row in card_rows],
            [f"carousel-{position:02d}" for position in range(1, 6)],
        )
        self.assertTrue(all("example.com" in row["destination_url"] for row in card_rows))
        self.assertNotIn("sportscaveshop.com", data.decode("utf-8-sig").casefold())

    def test_carousel_csv_round_trip_preserves_all_structured_copy_and_cards(self):
        result = carousel_csv_result()
        expected = carousel_csv_notes()
        data = ads_page.build_carousel_copy_csv(
            result,
            carousel_notes=expected,
        )

        parsed = ads_page.parse_carousel_copy_csv(data, result)

        self.assertEqual(parsed, expected)
        self.assertIn(b"\r\n", data)
        self.assertIn("🏁", data.decode("utf-8-sig"))
        self.assertIn("apostrophe’s", data.decode("utf-8-sig"))
        self.assertEqual(parsed["cards"][4]["setup_notes"], "")
        self.assertEqual(
            [card["slot_id"] for card in parsed["cards"]],
            [f"carousel-{position:02d}" for position in range(1, 6)],
        )
        self.assertEqual(
            [card["position"] for card in parsed["cards"]],
            list(range(1, 6)),
        )

    def test_carousel_save_writes_structured_csv_beside_setup_notes(self):
        result = carousel_csv_result()
        expected = carousel_csv_notes()
        workflow = {
            "export_date": "2026-08-24",
            "slots": {},
            "outcomes": {},
            "ad_notes": {"carousel": expected},
        }
        uploaded_items = []

        def upload_batch(_token, folder, items, **_kwargs):
            item = dict(items[0])
            uploaded_items.append(item)
            filename = item["relative_path"]
            return {
                "successes": [
                    {
                        "metadata": {
                            "name": filename,
                            "path_display": f"{folder}/{filename}",
                            "size": item["size"],
                        }
                    }
                ],
                "failures": [],
            }

        with patch.object(
            ads_page.dropbox_integration,
            "ensure_folder_path",
        ), patch.object(
            ads_page.dropbox_integration,
            "upload_batch",
            side_effect=upload_batch,
        ):
            outcomes = ads_page.save_ads_images_to_dropbox(
                "test-token",
                "/Files",
                "/Files/Ads",
                result,
                workflow,
            )

        self.assertEqual(
            [item["relative_path"] for item in uploaded_items],
            [ads_page.ADS_COPY_FILENAME, ads_page.CAROUSEL_COPY_FILENAME],
        )
        saved_notes = uploaded_items[0]["data"].decode("utf-8")
        self.assertIn("STRUCTURED CAROUSEL CARDS", saved_notes)
        self.assertIn("- Image slot: carousel-03", saved_notes)
        self.assertIn(expected["cards"][2]["destination_url"], saved_notes)
        saved_csv = ads_page.parse_carousel_copy_csv(uploaded_items[1]["data"], result)
        self.assertEqual(saved_csv, expected)
        self.assertEqual(outcomes["_carousel_copy_csv"]["status"], "saved")
        self.assertEqual(outcomes["_carousel_copy_csv"]["asset_type"], "meta_ads_copy_csv")

    def test_carousel_csv_validation_is_transactional(self):
        result = carousel_csv_result()
        valid_data = ads_page.build_carousel_copy_csv(
            result,
            carousel_notes=carousel_csv_notes(),
        )
        valid_rows = list(
            csv.DictReader(io.StringIO(valid_data.decode("utf-8-sig"), newline=""))
        )
        invalid_cases = {}

        missing_header_rows = [
            {key: value for key, value in row.items() if key != "cta"}
            for row in valid_rows
        ]
        invalid_cases["missing header"] = csv_bytes_from_rows(
            missing_header_rows,
            headers=[
                header for header in ads_page.CAROUSEL_COPY_CSV_HEADERS
                if header != "cta"
            ],
        )

        unsupported = [dict(row) for row in valid_rows]
        unsupported[0]["row_type"] = "unknown"
        invalid_cases["unsupported row"] = csv_bytes_from_rows(
            unsupported,
            headers=ads_page.CAROUSEL_COPY_CSV_HEADERS,
        )

        wrong_slot = [dict(row) for row in valid_rows]
        first_card = next(row for row in wrong_slot if row["row_type"] == "card")
        first_card["slot_id"] = "carousel-05"
        invalid_cases["wrong slot"] = csv_bytes_from_rows(
            wrong_slot,
            headers=ads_page.CAROUSEL_COPY_CSV_HEADERS,
        )

        missing_row = [dict(row) for row in valid_rows[:-1]]
        invalid_cases["missing row"] = csv_bytes_from_rows(
            missing_row,
            headers=ads_page.CAROUSEL_COPY_CSV_HEADERS,
        )

        existing_widget_key = ads_page._carousel_copy_widget_key(
            result["context_key"],
            "headlines",
            1,
        )
        for label, invalid_data in invalid_cases.items():
            with self.subTest(label=label):
                session_state = {existing_widget_key: "Keep existing headline"}
                workflow = {
                    "ad_notes": {
                        "headlines": "Legacy headline",
                        "cards": "Keep legacy setup",
                    }
                }
                original_workflow = json.loads(json.dumps(workflow))
                with patch.object(ads_page.st, "session_state", session_state):
                    with self.assertRaises(ads_page.CarouselCopyCSVError):
                        ads_page.apply_carousel_copy_csv(
                            result,
                            workflow,
                            invalid_data,
                        )
                self.assertEqual(session_state, {existing_widget_key: "Keep existing headline"})
                self.assertEqual(workflow, original_workflow)

    def test_carousel_csv_export_reads_current_widget_values(self):
        result = carousel_csv_result()
        expected = carousel_csv_notes()
        workflow = {"ad_notes": {"carousel": expected}}
        headline_key = ads_page._carousel_copy_widget_key(
            result["context_key"],
            "headlines",
            1,
        )
        card_note_key = ads_page._carousel_card_widget_key(
            result["context_key"],
            2,
            "setup_notes",
        )
        session_state = {
            headline_key: "Edited headline, exact",
            card_note_key: "Edited card note\nwith a second line",
        }

        with patch.object(ads_page.st, "session_state", session_state):
            exported = ads_page.build_carousel_copy_csv(result, workflow)
        parsed = ads_page.parse_carousel_copy_csv(exported, result)

        self.assertEqual(parsed["headlines"][0], "Edited headline, exact")
        self.assertEqual(
            parsed["cards"][1]["setup_notes"],
            "Edited card note\nwith a second line",
        )
        self.assertEqual(parsed["cards"][0], expected["cards"][0])

    def test_legacy_carousel_notes_load_without_losing_original_text(self):
        result = carousel_csv_result()
        workflow = {
            "ad_notes": {
                "headlines": "Legacy one\nLegacy two",
                "descriptions": "First description\nSecond description",
                "primary_text_variations": "Primary one\n\nPrimary two, exact.",
                "cards": "Legacy card and setup notes\nKeep this text.",
            }
        }

        structured = ads_page._carousel_copy_notes_from_workflow(result, workflow)

        self.assertEqual(structured["headlines"][:2], ["Legacy one", "Legacy two"])
        self.assertEqual(
            structured["primary_texts"][:2],
            ["Primary one", "Primary two, exact."],
        )
        self.assertEqual(
            structured["setup_notes"],
            "Legacy card and setup notes\nKeep this text.",
        )
        self.assertEqual(len(structured["cards"]), 5)
        self.assertEqual(
            [card["slot_id"] for card in structured["cards"]],
            [f"carousel-{position:02d}" for position in range(1, 6)],
        )

    def test_rendered_carousel_csv_import_survives_sequential_image_uploads(self):
        app_test = run_ads_page()
        set_product_name(app_test, "Six Laps Ahead")
        select_option(app_test, "Category", "Motorsport")
        select_option(app_test, "Country", "Australia")
        select_option(app_test, "Campaign type", "Carousel")
        set_product_url(app_test)
        seed_saved_result(app_test)
        result = dict(app_test.session_state[ads_page.ADS_RESULT_STATE_KEY])
        expected = carousel_csv_notes()
        data = ads_page.build_carousel_copy_csv(
            result,
            carousel_notes=expected,
        )

        uploader_by_label(app_test, "Import CSV").set_value(
            [("carousel-copy.csv", data, "text/csv")]
        )
        app_test.run(timeout=30)

        self.assertEqual(
            next(
                area.value for area in app_test.text_area
                if area.label == "Headline variation 1"
            ),
            expected["headlines"][0],
        )
        self.assertEqual(
            next(
                field.value for field in app_test.text_input
                if field.label == "Card 3 destination URL"
            ),
            expected["cards"][2]["destination_url"],
        )
        image = square_png_bytes()
        carousel_image_uploaders(app_test)[0].set_value(
            [("carousel-one.png", image, "image/png")]
        )
        app_test.run(timeout=30)
        carousel_image_uploaders(app_test)[1].set_value(
            [("carousel-two.png", image, "image/png")]
        )
        app_test.run(timeout=30)

        workflow = app_test.session_state[ads_page.ADS_IMAGE_STATE_KEY]
        structured = workflow["ad_notes"]["carousel"]
        self.assertEqual(structured["headlines"], expected["headlines"])
        self.assertEqual(
            structured["cards"][2]["destination_url"],
            expected["cards"][2]["destination_url"],
        )
        self.assertEqual(len(workflow["slots"]), 2)
        self.assertEqual(len(carousel_image_uploaders(app_test)), 5)
        self.assertEqual(len(app_test.exception), 0)

    def test_instant_experience_blank_copy_csv_uses_current_concept_structure(self):
        result = instant_experience_csv_result()
        data = ads_page.build_instant_experience_copy_csv(
            result,
            {},
            blank=True,
        )
        self.assertEqual(
            data,
            ads_page.build_instant_experience_copy_csv(
                result,
                {"ad_notes": {}},
            ),
        )
        rows = list(
            csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline=""))
        )

        self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(
            tuple(rows[0]),
            ads_page.INSTANT_EXPERIENCE_COPY_CSV_HEADERS,
        )
        self.assertEqual(len(rows), 9)
        self.assertEqual(
            [(row["route_key"], row["variation"]) for row in rows],
            [
                (concept["id"], str(variation))
                for concept in ads_page.INSTANT_EXPERIENCE_CONCEPTS
                for variation in range(1, 4)
            ],
        )
        self.assertTrue(
            all(
                row["primary_text"]
                == row["headline"]
                == row["cta"]
                == ""
                for row in rows
            )
        )

    def test_instant_experience_current_copy_csv_round_trips_multiline_utf8(self):
        result = instant_experience_csv_result()
        expected = instant_experience_csv_notes()
        data = ads_page.build_instant_experience_copy_csv(
            result,
            concept_notes=expected,
        )

        parsed = ads_page.parse_instant_experience_copy_csv(data, result)

        self.assertEqual(parsed, expected)
        self.assertIn(b"\r\n", data)
        rows = list(
            csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline=""))
        )
        reordered = csv_bytes_from_rows(
            rows,
            headers=reversed(ads_page.INSTANT_EXPERIENCE_COPY_CSV_HEADERS),
        )
        self.assertEqual(
            ads_page.parse_instant_experience_copy_csv(reordered, result),
            expected,
        )
        self.assertEqual(
            ads_page.parse_instant_experience_copy_csv(
                data.replace(b"\r\n", b"\n"),
                result,
            ),
            expected,
        )
        decorated_headers = [
            f"  {header.replace('_', ' ').title()}  "
            for header in ads_page.INSTANT_EXPERIENCE_COPY_CSV_HEADERS
        ]
        decorated_output = io.StringIO(newline="")
        decorated_writer = csv.DictWriter(
            decorated_output,
            fieldnames=decorated_headers,
            lineterminator="\n",
        )
        decorated_writer.writeheader()
        for row in rows:
            decorated_writer.writerow(
                {
                    decorated_header: row[canonical_header]
                    for decorated_header, canonical_header in zip(
                        decorated_headers,
                        ads_page.INSTANT_EXPERIENCE_COPY_CSV_HEADERS,
                    )
                }
            )
        self.assertEqual(
            ads_page.parse_instant_experience_copy_csv(
                decorated_output.getvalue().encode("utf-8-sig"),
                result,
            ),
            expected,
        )
        self.assertIn("emoji 🏁", data.decode("utf-8-sig"))

    def test_instant_experience_copy_csv_accepts_spreadsheet_index_columns(self):
        result = instant_experience_csv_result()
        expected = instant_experience_csv_notes()
        canonical = ads_page.build_instant_experience_copy_csv(
            result,
            concept_notes=expected,
        )
        canonical_rows = list(
            csv.DictReader(
                io.StringIO(canonical.decode("utf-8-sig"), newline="")
            )
        )

        for index_header in ("index", "Unnamed: 0", ""):
            with self.subTest(index_header=index_header):
                indexed_rows = [
                    {index_header: str(index), **row}
                    for index, row in enumerate(canonical_rows)
                ]
                indexed_rows.reverse()
                indexed = csv_bytes_from_rows(
                    indexed_rows,
                    headers=(
                        index_header,
                        *ads_page.INSTANT_EXPERIENCE_COPY_CSV_HEADERS,
                    ),
                )

                parsed = ads_page.parse_instant_experience_copy_csv(
                    indexed,
                    result,
                )

                self.assertEqual(parsed, expected)
                self.assertIn(
                    "Second line with \"quotes\"",
                    parsed["premium_scarcity_right"][0]["primary_text"],
                )
                self.assertEqual(
                    parsed["premium_scarcity_front"][1]["headline"],
                    expected["premium_scarcity_front"][1]["headline"],
                )
                self.assertEqual(
                    parsed["premium_scarcity_left"][2]["cta"],
                    expected["premium_scarcity_left"][2]["cta"],
                )

    def test_instant_experience_copy_csv_rejects_duplicate_index_header(self):
        result = instant_experience_csv_result()
        canonical = ads_page.build_instant_experience_copy_csv(
            result,
            concept_notes=instant_experience_csv_notes(),
        )
        rows = list(
            csv.DictReader(
                io.StringIO(canonical.decode("utf-8-sig"), newline="")
            )
        )
        output = io.StringIO(newline="")
        writer = csv.writer(output, lineterminator="\r\n")
        writer.writerow(
            ("index", "index", *ads_page.INSTANT_EXPERIENCE_COPY_CSV_HEADERS)
        )
        for index, row in enumerate(rows):
            writer.writerow(
                (
                    index,
                    index,
                    *(row[header] for header in ads_page.INSTANT_EXPERIENCE_COPY_CSV_HEADERS),
                )
            )

        with self.assertRaisesRegex(
            ads_page.InstantExperienceCopyCSVError,
            "duplicate column headers",
        ):
            ads_page.parse_instant_experience_copy_csv(
                output.getvalue().encode("utf-8-sig"),
                result,
            )

    def test_instant_experience_copy_csv_rejects_posting_schema_with_useful_error(self):
        with self.assertRaisesRegex(
            ads_page.InstantExperienceCopyCSVError,
            "Instant Experience CSV is missing required column:",
        ):
            ads_page.parse_instant_experience_copy_csv(
                (
                    "schema_version,product_name,primary_text,headline,cta\r\n"
                    "2,Example product,Copy,Headline,Shop Now\r\n"
                ).encode("utf-8-sig"),
                instant_experience_csv_result(),
            )

    def test_instant_experience_copy_csv_round_trips_every_supported_output_mode(self):
        for output_mode in (
            ads_page.IE_MODE_SMART,
            ads_page.IE_MODE_SELECTED,
            ads_page.IE_MODE_CLASSIC,
        ):
            with self.subTest(output_mode=output_mode):
                result = instant_experience_csv_result(output_mode)
                expected = instant_experience_csv_notes()
                data = ads_page.build_instant_experience_copy_csv(
                    result,
                    concept_notes=expected,
                )
                rows = list(
                    csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline=""))
                )

                self.assertEqual(
                    ads_page.parse_instant_experience_copy_csv(data, result),
                    expected,
                )
                self.assertEqual(
                    {row["output_mode"] for row in rows},
                    {ads_page._instant_experience_copy_csv_output_mode(result)},
                )

    def test_instant_experience_copy_csv_rejects_invalid_identity_rows(self):
        result = instant_experience_csv_result()
        valid_data = ads_page.build_instant_experience_copy_csv(
            result,
            concept_notes=instant_experience_csv_notes(),
        )
        valid_rows = list(
            csv.DictReader(io.StringIO(valid_data.decode("utf-8-sig"), newline=""))
        )
        invalid_cases = {}

        missing = [dict(row) for row in valid_rows[:-1]]
        invalid_cases["missing row"] = csv_bytes_from_rows(missing)

        duplicate = [dict(row) for row in valid_rows]
        duplicate[1] = dict(duplicate[0])
        invalid_cases["duplicate row"] = csv_bytes_from_rows(duplicate)

        unknown_route = [dict(row) for row in valid_rows]
        unknown_route[0]["route_key"] = "unknown"
        invalid_cases["unknown route"] = csv_bytes_from_rows(unknown_route)

        wrong_campaign = [dict(row) for row in valid_rows]
        wrong_campaign[0]["campaign_type"] = "carousel"
        invalid_cases["wrong campaign"] = csv_bytes_from_rows(wrong_campaign)

        wrong_mode = [dict(row) for row in valid_rows]
        wrong_mode[0]["output_mode"] = "classic_collector"
        invalid_cases["wrong mode"] = csv_bytes_from_rows(wrong_mode)

        wrong_schema = [dict(row) for row in valid_rows]
        wrong_schema[0]["schema_version"] = "999"
        invalid_cases["wrong schema"] = csv_bytes_from_rows(wrong_schema)

        wrong_description_key = [dict(row) for row in valid_rows]
        wrong_description_key[0]["description_key"] = "choose_a_side"
        invalid_cases["wrong description key"] = csv_bytes_from_rows(wrong_description_key)

        missing_header_rows = [
            {key: value for key, value in row.items() if key != "cta"}
            for row in valid_rows
        ]
        invalid_cases["missing header"] = csv_bytes_from_rows(
            missing_header_rows,
            headers=[
                header
                for header in ads_page.INSTANT_EXPERIENCE_COPY_CSV_HEADERS
                if header != "cta"
            ],
        )

        unexpected = [dict(row) for row in valid_rows]
        unexpected.append(dict(valid_rows[-1]))
        invalid_cases["unexpected row"] = csv_bytes_from_rows(unexpected)

        for label, data in invalid_cases.items():
            with self.subTest(label=label):
                with self.assertRaises(ads_page.InstantExperienceCopyCSVError):
                    ads_page.parse_instant_experience_copy_csv(data, result)

    def test_instant_experience_copy_csv_import_is_transactional_and_not_replayed(self):
        result = instant_experience_csv_result()
        expected = instant_experience_csv_notes()
        valid_data = ads_page.build_instant_experience_copy_csv(
            result,
            concept_notes=expected,
        )
        invalid_rows = list(
            csv.DictReader(io.StringIO(valid_data.decode("utf-8-sig"), newline=""))
        )
        invalid_rows[0]["route_key"] = "not-a-route"
        invalid_data = csv_bytes_from_rows(invalid_rows)
        first_key = ads_page._instant_experience_copy_widget_key(
            result["context_key"],
            "premium_scarcity_right",
            "primary_text",
            1,
        )
        session_state = {first_key: "Keep this existing value"}
        workflow = {"ad_notes": {}}

        with patch.object(ads_page.st, "session_state", session_state):
            with self.assertRaises(ads_page.InstantExperienceCopyCSVError):
                ads_page.apply_instant_experience_copy_csv(
                    result,
                    workflow,
                    invalid_data,
                )
            self.assertEqual(session_state, {first_key: "Keep this existing value"})
            self.assertEqual(workflow, {"ad_notes": {}})

            status = ads_page._process_instant_experience_copy_csv_upload(
                result,
                workflow,
                io.BytesIO(valid_data),
            )
            self.assertTrue(status["ok"])
            self.assertEqual(status["message"], "CSV imported — ad copy applied.")
            self.assertTrue(ads_page.instant_experience_copy_complete(workflow))
            for concept in ads_page.INSTANT_EXPERIENCE_CONCEPTS:
                self.assertEqual(
                    ads_page._instant_experience_concept_complete_count(
                        workflow,
                        concept["id"],
                    ),
                    3,
                )

            session_state[first_key] = "Manual change after import"
            ads_page._process_instant_experience_copy_csv_upload(
                result,
                workflow,
                io.BytesIO(valid_data),
            )
            self.assertEqual(session_state[first_key], "Manual change after import")

    def test_failed_instant_experience_upload_does_not_poison_valid_replacement(self):
        result = instant_experience_csv_result()
        valid_data = ads_page.build_instant_experience_copy_csv(
            result,
            concept_notes=instant_experience_csv_notes(),
        )
        workflow = {"ad_notes": {}}
        session_state = {}

        with patch.object(ads_page.st, "session_state", session_state):
            failed = ads_page._process_instant_experience_copy_csv_upload(
                result,
                workflow,
                io.BytesIO(b"schema_version,product_name\r\n2,Example product\r\n"),
            )
            succeeded = ads_page._process_instant_experience_copy_csv_upload(
                result,
                workflow,
                io.BytesIO(valid_data),
            )

        self.assertFalse(failed["ok"])
        self.assertIn("missing required column", failed["message"])
        self.assertTrue(succeeded["ok"])
        self.assertEqual(succeeded["message"], "CSV imported — ad copy applied.")
        self.assertTrue(ads_page.instant_experience_copy_complete(workflow))

    def test_rendered_instant_experience_csv_import_populates_existing_fields(self):
        app_test = run_ads_page()
        set_product_name(app_test, "Six Laps Ahead")
        select_option(app_test, "Category", "Motorsport")
        select_option(app_test, "Country", "Australia")
        select_option(app_test, "Campaign type", "Instant Experience")
        set_product_url(app_test)
        seed_saved_result(app_test)
        result = dict(app_test.session_state[ads_page.ADS_RESULT_STATE_KEY])
        expected = instant_experience_csv_notes()
        canonical = ads_page.build_instant_experience_copy_csv(
            result,
            concept_notes=expected,
        )
        canonical_rows = list(
            csv.DictReader(
                io.StringIO(canonical.decode("utf-8-sig"), newline="")
            )
        )
        indexed_rows = [
            {"index": str(index), **row}
            for index, row in enumerate(canonical_rows)
        ]
        indexed_rows.reverse()
        data = csv_bytes_from_rows(
            indexed_rows,
            headers=("index", *ads_page.INSTANT_EXPERIENCE_COPY_CSV_HEADERS),
        )

        uploader_by_label(app_test, "Import CSV").set_value(
            [("instant-experience-copy.csv", data, "text/csv")]
        )
        app_test.run(timeout=30)

        primary_values = [
            text_area.value
            for text_area in app_test.text_area
            if text_area.label == "Description"
        ]
        headline_values = [
            text_area.value
            for text_area in app_test.text_area
            if text_area.label == "Headline"
        ]
        cta_values = [
            text_area.value
            for text_area in app_test.text_area
            if text_area.label == "CTA"
        ]
        self.assertEqual(len(primary_values), 3)
        self.assertEqual(primary_values[0], expected["premium_scarcity_right"][0]["primary_text"])
        self.assertEqual(primary_values[-1], expected["premium_scarcity_left"][0]["primary_text"])
        self.assertEqual(headline_values[1], expected["premium_scarcity_front"][0]["headline"])
        self.assertEqual(cta_values[2], expected["premium_scarcity_left"][0]["cta"])
        self.assertTrue(
            all(
                any(
                    f"{concept['display_name']}: " in caption.value
                    and "Copy complete" in caption.value
                    for caption in app_test.caption
                )
                for concept in ads_page._ie_concepts_for_result({"campaign_type": "Instant Experience"})
            )
        )
        self.assertEqual(len(app_test.exception), 0)

    def test_instant_experience_csv_control_is_compact_and_prompt_instruction_is_once(self):
        record,_,_=current_ie(self)
        prompt=record['master_prompt']
        self.assertIn(','.join(ads_page.INSTANT_EXPERIENCE_COPY_CSV_HEADERS),prompt)
        self.assertIn('UTF-8',prompt)
        self.assertEqual(len(ads_page._instant_experience_copy_csv_expected_rows(record)),3)

    def test_submit_supported_result_renders_compact_sections_with_url_parameters(self):
        app_test = run_ads_page()
        set_product_name(app_test, "Six Laps Ahead")
        select_option(app_test, "Category", "Motorsport")
        select_option(app_test, "Country", "Canada")
        select_option(app_test, "Campaign type", "Carousel")
        set_product_url(app_test)
        seed_saved_result(app_test)

        self.assertEqual(
            [subheader.value for subheader in app_test.subheader],
            [
                "1. Copy this ChatGPT prompt",
                "Generated Ad Images",
            ],
        )
        self.assertEqual(len(app_test.code), 0)
        self.assertIn(ads_page.META_AD_URL_PARAMETERS, app_test.session_state[ads_page.ADS_RESULT_STATE_KEY]['master_prompt'])
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
        seed_saved_result(app_test)

        self.assertNotIn("Insufficient winner data", [subheader.value for subheader in app_test.subheader])
        self.assertIn("1. Copy this ChatGPT prompt", [subheader.value for subheader in app_test.subheader])
        self.assertFalse(any("Using generic Sports Cave winner pattern" in caption.value for caption in app_test.caption))
        self.assertEqual(len(app_test.code), 0)
        self.assertIn(ads_page.META_AD_URL_PARAMETERS, app_test.session_state[ads_page.ADS_RESULT_STATE_KEY]['master_prompt'])
        self.assertEqual(len(app_test.exception), 0)

    def test_carousel_renders_five_slots_and_upload_state_survives_reruns(self):
        app_test = run_ads_page()
        set_product_name(app_test, "Six Laps Ahead")
        select_option(app_test, "Category", "Motorsport")
        select_option(app_test, "Country", "Australia")
        select_option(app_test, "Campaign type", "Carousel")
        set_product_url(app_test)
        seed_saved_result(app_test)

        self.assertEqual(
            [uploader.label for uploader in carousel_image_uploaders(app_test)],
            ["Carousel 1", "Carousel 2", "Carousel 3", "Carousel 4", "Carousel 5"],
        )
        self.assertTrue(button_by_label(app_test, "Post now").disabled)
        original_result = dict(app_test.session_state[ads_page.ADS_RESULT_STATE_KEY])
        image = square_png_bytes()
        carousel_image_uploaders(app_test)[0].set_value([("Carousel 1.png", image, "image/png")])
        app_test.run(timeout=30)
        self.assertTrue(button_by_label(app_test, "Post now").disabled)
        for uploader in carousel_image_uploaders(app_test):
            uploader.set_value([(f"{uploader.label}.png", image, "image/png")])
        app_test.run(timeout=30)

        persisted_result = dict(app_test.session_state[ads_page.ADS_RESULT_STATE_KEY])
        self.assertEqual(persisted_result["variation_token"], original_result["variation_token"])
        self.assertEqual(persisted_result["master_prompt"], original_result["master_prompt"])
        self.assertEqual(
            len(app_test.session_state[ads_page.ADS_IMAGE_STATE_KEY]["slots"]),
            5,
        )
        self.assertTrue(button_by_label(app_test, "Post now").disabled)
        self.assertEqual(len(app_test.exception), 0)

    def test_remove_and_replace_keeps_carousel_partial_save_available(self):
        app_test = run_ads_page()
        set_product_name(app_test, "Six Laps Ahead")
        select_option(app_test, "Category", "Motorsport")
        select_option(app_test, "Country", "Australia")
        select_option(app_test, "Campaign type", "Carousel")
        set_product_url(app_test)
        seed_saved_result(app_test)
        image = square_png_bytes()
        for uploader in carousel_image_uploaders(app_test):
            uploader.set_value([(f"{uploader.label}.png", image, "image/png")])
        app_test.run(timeout=30)

        button_by_label(app_test, "Remove").click().run(timeout=20)
        self.assertTrue(button_by_label(app_test, "Post now").disabled)
        self.assertEqual(
            len(app_test.session_state[ads_page.ADS_IMAGE_STATE_KEY]["slots"]),
            4,
        )
        carousel_image_uploaders(app_test)[0].set_value(
            [("Carousel 1 replacement.webp", image, "image/webp")]
        )
        app_test.run(timeout=30)
        self.assertTrue(button_by_label(app_test, "Post now").disabled)
        self.assertEqual(len(app_test.exception), 0)

    def test_instant_experience_save_package_button_opens_existing_destination_workflow(self):
        import inspect,ads_auto_post
        source=inspect.getsource(ads_auto_post.save_and_queue)
        self.assertLess(source.index('save_ads_images_to_dropbox'),source.index('queue_saved_package'))
        self.assertIn('_ads_saved_source_signature',source)
        self.assertIn('source_signature',source)
        self.assertIn('posting_package_error',source)

    def test_instant_experience_package_exports_flat_jpegs_and_keeps_historical_text_without_posting_schema(self):
        result = instant_experience_csv_result()
        notes = instant_experience_csv_notes()
        slots = {}
        image_cases = (
            ("right.jpg", "JPEG"),
            ("front.png", "PNG"),
            ("left.webp", "WEBP"),
        )
        for slot, (filename, image_format) in zip(
            ads_page.ads_image_workflow.campaign_image_slots(
                "Instant Experience"
            ),
            image_cases,
        ):
            source = square_image_bytes(image_format)
            details = ads_page.ads_image_workflow.inspect_instant_experience_original(
                source,
                original_name=filename,
            )
            slots[slot["id"]] = {
                **details,
                "data": source,
                "output_format": details["source_format"],
                "output_width": details["source_width"],
                "output_height": details["source_height"],
                "output_size": details["source_size"],
                "slot_id": slot["id"],
                "label": slot["label"],
                "concept_id": slot.get("concept_id"),
                "position": slot["position"],
                "valid": True,
                "error": "",
            }
        workflow = {
            "context_key": result["context_key"],
            "campaign_type": "Instant Experience",
            "slots": slots,
            "outcomes": {},
            "ad_notes": {"instant_experience_concepts": notes},
        }

        items = ads_page._instant_experience_package_items(result, workflow)
        paths = {item["relative_path"] for item in items}
        image_items = [item for item in items if item["kind"] == "image"]

        self.assertEqual(len(image_items), 3)
        self.assertEqual(
            [item["concept_id"] for item in image_items],
            [
                "premium_scarcity_right",
                "premium_scarcity_front",
                "premium_scarcity_left",
            ],
        )
        self.assertEqual(
            [item["filename"] for item in image_items],
            [
                "01-premium-scarcity-right.jpg",
                "02-premium-scarcity-front.jpg",
                "03-premium-scarcity-left.jpg",
            ],
        )
        self.assertTrue(all(item["filename"].endswith(".jpg") for item in image_items))
        self.assertTrue(all("/" not in path for path in paths))
        self.assertIn("notes.txt", paths)
        self.assertIn("ad_copy.csv", paths)
        for image_item in image_items:
            self.assertEqual(image_item["content_type"], "image/jpeg")
            self.assertTrue(image_item["data"].startswith(b"\xff\xd8\xff"))
            with Image.open(io.BytesIO(image_item["data"])) as exported:
                exported.load()
                self.assertEqual(exported.format, "JPEG")
                self.assertEqual(exported.mode, "RGB")
                self.assertEqual(exported.size, (96, 96))
        for concept in ads_page.INSTANT_EXPERIENCE_CONCEPTS:
            self.assertIn(f"{concept['folder']}-ad-copy.txt", paths)
            for variation_number in range(
                1,
                ads_page.INSTANT_EXPERIENCE_COPY_VARIATION_COUNT + 1,
            ):
                variant = ads_page._instant_experience_description_variant(
                    variation_number
                )
                variation_folder = (
                    f"{concept['folder']}--{variation_number:02d}-"
                    f"{variant['key'].replace('_', '-')}"
                )
                self.assertIn(
                    f"{variation_folder}--{ads_page.ADS_PRIMARY_TEXT_FILENAME}",
                    paths,
                )
                self.assertIn(
                    f"{variation_folder}--{ads_page.ADS_HEADLINE_FILENAME}",
                    paths,
                )

        copy_csv_items = [
            item for item in items if item["asset_type"] == "meta_ads_copy_csv"
        ]
        self.assertEqual(len(copy_csv_items), 1)
        self.assertEqual(
            ads_page.parse_instant_experience_copy_csv(
                copy_csv_items[0]["data"],
                result,
            ),
            notes,
        )
        self.assertFalse(any("posting" in path.casefold() for path in paths))
        self.assertFalse(
            any(item["asset_type"] == "meta_ads_posting_import" for item in items)
        )

        current_slot_id = ads_page.ads_image_workflow.campaign_image_slots(
            "Instant Experience"
        )[0]["id"]
        workflow["outcomes"].update(
            {
                current_slot_id: {"status": "saved", "label": "Right Angle"},
                "instant-experience": {"status": "failed"},
                "_new_ads_copy_csv": {"status": "saved"},
                "_instant_experience_package": {
                    "status": "saved",
                    "signature": "package-signature",
                },
            }
        )
        ads_page._compact_instant_experience_slots(workflow)
        self.assertEqual(workflow["outcomes"][current_slot_id]["status"], "saved")
        self.assertNotIn("instant-experience", workflow["outcomes"])
        self.assertEqual(
            workflow["outcomes"]["_new_ads_copy_csv"]["status"],
            "saved",
        )
        self.assertEqual(
            workflow["outcomes"]["_instant_experience_package"]["signature"],
            "package-signature",
        )

    def test_invalid_generated_image_shows_inline_error_and_keeps_save_disabled(self):
        app_test = run_ads_page()
        set_product_name(app_test, "Final Whistle Glory")
        select_option(app_test, "Category", "Football")
        select_option(app_test, "Country", "UK")
        select_option(app_test, "Campaign type", "Instant Experience")
        set_product_url(app_test, "https://sportscave.com.au/products/final-whistle-glory")
        seed_saved_result(app_test)

        instant_experience_cover_uploaders(app_test)[0].set_value(
            [("broken.png", b"not an image", "image/png")]
        )
        app_test.run(timeout=20)

        self.assertTrue(any("corrupt" in error.value for error in app_test.error))
        self.assertTrue(button_by_label(app_test, "Post now").disabled)
        self.assertEqual(len(app_test.exception), 0)

    def assert_instant_experience_v4_routes(self, prompt):
        for route_key in (
            "premium_scarcity_right",
            "premium_scarcity_front",
            "premium_scarcity_left",
        ):
            self.assertIn(f"Route key: {route_key}", prompt)
        self.assertIn(ads_page.ie_visuals.VERSION, prompt)
        self.assertIn("Upper photographed residential room scene: approximately 80–82%", prompt)
        self.assertIn("Fixed opaque black footer: approximately the bottom 18–20%", prompt)
        self.assertIn("CLAIM YOUR EDITION", prompt)
        self.assertNotIn("FRAMED GREATNESS SCARCITY HYBRID", prompt)
        self.assertNotIn("PURE LIMITED-RELEASE SCARCITY", prompt)
        self.assertNotIn("COLLECTOR PROOF SCARCITY", prompt)

    def test_ads_setup_notes_text_matches_campaign_type_and_pasted_copy(self):
        result = ads_page.build_ads_result_record(
            "Final Whistle Glory",
            "Football",
            "UK",
            "Instant Experience",
            product_url="https://sportscave.com.au/products/final-whistle-glory",
        )
        workflow = {
            "ad_notes": {
                "instant_experience_concepts": instant_experience_csv_notes(),
            }
        }

        notes = ads_page.build_ads_setup_notes_text(result, workflow)

        self.assertIn("Sports Cave Ad Setup Notes", notes)
        self.assertIn("Campaign type: Instant Experience", notes)
        self.assertIn("Premium Scarcity", notes)
        self.assertIn("DESCRIPTION COPY", notes)
        self.assertIn("DESCRIPTION KEY", notes)
        self.assertIn("legacy_standard", notes)
        self.assertNotIn("Carousel cards / ad setup", notes)

    def test_baseball_instant_experience_approved_claims_are_injected_through_claim_helper(self):
        with patch.object(ads_page,'build_baseball_instant_experience_claim_block',return_value='UNVERIFIED LEGACY CLAIM'):
            record,_,_=current_ie(self,category='Baseball',metadata={'edition_limit':100,'edition_limit_source':'verified fixture'})
        self.assertNotIn('UNVERIFIED LEGACY CLAIM',record['master_prompt'])
        self.assertEqual(record['product_metadata']['edition_limit'],100)

    def test_baseball_instant_experience_uses_master_cover_prompt_and_claim_path(self):
        record,rows,briefs=current_ie(self,product='Verified Baseball Edition',category='Baseball')
        self.assertEqual([row['route_key'] for row in rows],['premium_scarcity_right','premium_scarcity_front','premium_scarcity_left'])
        self.assertIn('GROUPED INSTANT EXPERIENCE OUTPUT',record['master_prompt'])

    def test_dedicated_baseball_instant_experience_keeps_grouped_copy_schema(self):
        prompt = ads_page.build_ads_prompt(
            "Shohei Ohtani 50/50 Season",
            "Baseball",
            "USA",
            "Instant Experience",
            product_url="https://sportscave.com.au/products/ohtani-50-50",
        )

        self.assertEqual(prompt.count("ONE PERSONALISED COPY SET PER VISUAL"), 1)
        self.assertIn(ads_page.ie_copy.VERSION, prompt)
        self.assertIn("Each group contains AD COPY with one Description, one Headline and one CTA.", prompt)
        self.assertIn("Return exactly THREE active ad-copy combinations total.", prompt)
        self.assertGreaterEqual(prompt.count("AD COPY"), 3)
        self.assertNotIn("DESCRIPTION\n\n1. [description]", prompt)

    def test_every_ads_prompt_requires_text_first_no_automatic_image_generation(self):
        current_ie(self)
        # The active IE contract executes three images. Carousel remains text-first.
        prompt=ads_page.build_ads_prompt('Verified Edition','Cricket','Australia','Carousel')
        self.assertIn('Within this text-only scope, do not use an image-generation tool.',prompt)
        self.assertIn('only to copy-only or prompt-only requests',prompt)
        self.assertEqual(len(carousel_prompt_card_sections(visual_contract(prompt))),5)

    def test_every_category_returns_instant_experience_output_for_every_supported_country(self):
        for category in ads_page.SUPPORTED_AD_CATEGORIES:
            for country in ads_page.COUNTRY_OPTIONS[1:]:
                current_ie(self,product=f'{category} Collector Moment',category=category,country=country)

    def test_football_instant_experience_works_for_every_supported_country(self):
        for country in ads_page.COUNTRY_OPTIONS:
            record,_,_=current_ie(self,category='Baseball',country=country)
            self.assertEqual(record['country'],country)
            self.assertIn('Sport: Baseball',record['master_prompt'])

    def test_football_instant_experience_uses_bottom_strip_and_collector_framing(self):
        import ads_ie_two_line as footer
        record,rows,briefs=current_ie(self,category='Football')
        self.assertIn(footer.FOOTER_RULES,record['master_prompt'])
        for row,brief in zip(rows,briefs):
            self.assertIn(footer.image_copy(row),brief)
            self.assertNotIn(row['meta_headline_text'],brief.split('META HEADLINE')[0])

    def test_instant_experience_auto_scenes_are_specific_and_pairwise_distinct(self):
        visuals = ads_page.resolve_standard_instant_experience_visuals(
            product_name="Sunday at the Crease",
            category="Cricket",
            product_metadata={"edition_limit": 100, "edition_limit_source": "unit test"},
            variation_token="scene-specificity",
        )

        self.assertTrue(ads_page.validate_instant_experience_set_differentiation(visuals))
        self.assertEqual(len({visual["camera_side"] for visual in visuals}), 3)
        self.assertEqual(len({visual["wall_colour"] for visual in visuals}), 3)
        self.assertEqual(len({visual["primary_cue"] for visual in visuals}), 3)

    def test_instant_experience_copy_csv_validates_cta_field_without_forcing_description_ending(self):
        result = instant_experience_csv_result()
        valid_data = ads_page.build_instant_experience_copy_csv(
            result,
            concept_notes=instant_experience_csv_notes(),
        )
        valid_rows = list(
            csv.DictReader(io.StringIO(valid_data.decode("utf-8-sig"), newline=""))
        )

        invalid_cta_rows = [dict(row) for row in valid_rows]
        invalid_cta_rows[0]["cta"] = "Feel It Again"
        invalid_cta_rows[0]["primary_text"] = "A supported memory opens this ad. Feel it again."
        with self.assertRaisesRegex(
            ads_page.InstantExperienceCopyCSVError,
            "Premium Scarcity.*CTA must be exactly one of",
        ):
            ads_page.parse_instant_experience_copy_csv(
                csv_bytes_from_rows(invalid_cta_rows),
                result,
            )

        archetype_ending_rows = [dict(row) for row in valid_rows]
        front_row = next(
            row
            for row in archetype_ending_rows
            if row["route_key"] == "premium_scarcity_front" and row["variation"] == "2"
        )
        front_row["cta"] = "Secure Your Edition"
        front_row["primary_text"] = (
            "Greatness doesn't fade. It gets framed.\n\n"
            "A limited collector release.\n"
            "Made for the fans who know what this moment means.\n\n"
            "Limited to 100 worldwide.\n"
            "Made for serious collectors.\n"
            "Built for the fans who know why it matters.\n\n"
            "Secure yours."
        )

        parsed = ads_page.parse_instant_experience_copy_csv(
            csv_bytes_from_rows(archetype_ending_rows),
            result,
        )

        self.assertEqual(
            parsed["premium_scarcity_front"][1]["primary_text"],
            front_row["primary_text"],
        )
        self.assertEqual(parsed["premium_scarcity_front"][1]["cta"], "Secure Your Edition")

    def test_instant_experience_creative_cta_contract_is_central_and_route_scoped(self):
        import ads_ie_two_line as footer
        record,rows,briefs=current_ie(self,category='Football')
        self.assertIn(footer.FOOTER_RULES,record['master_prompt'])
        for row,brief in zip(rows,briefs):
            self.assertIn(footer.image_copy(row),brief)
            self.assertNotIn(row['meta_headline_text'],brief.split('META HEADLINE')[0])

    def test_instant_experience_ignores_obsolete_route_settings_and_uses_standard_output(self):
        for mode in (ads_page.IE_MODE_SMART,ads_page.IE_MODE_SELECTED):
            prompt=ads_page.build_ads_prompt('Verified Edition','Cricket','Australia','Instant Experience',instant_experience_settings=instant_experience_settings(mode))
            self.assertIn(ads_page.ADS_IE_COMBINED_EXECUTION_VERSION,prompt)
            self.assertEqual(prompt.count('\nHEADLINE: '),3)
            self.assertNotIn('SUPPORTING LINE:',prompt)

    def test_instant_experience_renders_three_required_cover_slots_immediately(self):
        app_test = run_ads_page()
        set_product_name(app_test, "Final Whistle Glory")
        select_option(app_test, "Category", "Football")
        select_option(app_test, "Country", "UK")
        select_option(app_test, "Campaign type", "Instant Experience")
        set_product_url(app_test, "https://sportscave.com.au/products/final-whistle-glory")
        seed_saved_result(app_test)

        expected_labels = [
            f"{concept['scene_name']} Cover"
            for concept in ads_page.INSTANT_EXPERIENCE_CONCEPTS
        ]
        self.assertEqual(
            [uploader.label for uploader in instant_experience_cover_uploaders(app_test)],
            expected_labels,
        )
        self.assertTrue(button_by_label(app_test, "Post now").disabled)
        self.assertEqual(len(ads_page._ads_image_valid_slots(app_test.session_state[ads_page.ADS_RESULT_STATE_KEY],app_test.session_state[ads_page.ADS_IMAGE_STATE_KEY])),0)
        for index in range(1, 4):
            instant_experience_cover_uploaders(app_test)[index - 1].set_value(
                [(f"instant-{index}.png", square_png_bytes(color=(40 + index, 70, 110)), "image/png")]
            )
            app_test.run(timeout=30)
            self.assertEqual(len(ads_page._ads_image_valid_slots(app_test.session_state[ads_page.ADS_RESULT_STATE_KEY],app_test.session_state[ads_page.ADS_IMAGE_STATE_KEY])),index)
            self.assertTrue(button_by_label(app_test, "Post now").disabled)
        self.assertEqual(len(app_test.exception), 0)

    def test_instant_experience_preview_remove_replace_and_rerun_persistence(self):
        app_test = run_ads_page()
        set_product_name(app_test, "Final Whistle Glory")
        select_option(app_test, "Category", "Football")
        select_option(app_test, "Country", "UK")
        select_option(app_test, "Campaign type", "Instant Experience")
        set_product_url(app_test, "https://sportscave.com.au/products/final-whistle-glory")
        seed_saved_result(app_test)

        slot_id = "instant-experience-premium-scarcity-right"
        instant_experience_cover_uploaders(app_test)[0].set_value(
            [("uploaded-filename.png", square_png_bytes(), "image/png")]
        )
        app_test.run(timeout=30)
        workflow = app_test.session_state[ads_page.ADS_IMAGE_STATE_KEY]
        self.assertTrue(workflow["slots"][slot_id]["valid"])
        self.assertEqual(workflow["slots"][slot_id]["original_name"], "uploaded-filename.png")
        result = app_test.session_state[ads_page.ADS_RESULT_STATE_KEY]
        filename = ads_page._meta_output_filename(
            result,
            workflow,
            ads_page.ads_image_workflow.campaign_image_slots("Instant Experience")[0],
        )
        self.assertEqual(filename, "01-premium-scarcity-right.jpg")
        app_test.run(timeout=20)
        workflow = app_test.session_state[ads_page.ADS_IMAGE_STATE_KEY]
        self.assertIn(slot_id, workflow["slots"])
        button_by_label(app_test, "Remove").click().run(timeout=20)
        workflow = app_test.session_state[ads_page.ADS_IMAGE_STATE_KEY]
        self.assertEqual(workflow["slots"], {})
        instant_experience_cover_uploaders(app_test)[0].set_value(
            [("replacement.webp", square_png_bytes(color=(90, 120, 150)), "image/webp")]
        )
        app_test.run(timeout=30)
        workflow = app_test.session_state[ads_page.ADS_IMAGE_STATE_KEY]
        self.assertEqual(workflow["slots"][slot_id]["original_name"], "replacement.webp")

    def test_local_instant_experience_upload_accepts_jpg_jpeg_png_and_webp(self):
        result = instant_experience_csv_result()
        slot = ads_page.ads_image_workflow.campaign_image_slots(
            "Instant Experience"
        )[0]
        cases = (
            ("jpg", "JPEG", "image/jpeg"),
            ("jpeg", "JPEG", "image/jpeg"),
            ("png", "PNG", "image/png"),
            ("webp", "WEBP", "image/webp"),
        )

        for case_index, (extension, image_format, _mime_type) in enumerate(cases):
            with self.subTest(extension=extension):
                workflow = {
                    "context_key": result["context_key"],
                    "campaign_type": "Instant Experience",
                    "slots": {},
                    "widget_nonces": {},
                    "outcomes": {},
                    "ad_notes": {},
                }
                session_state = {}
                source = square_image_bytes(
                    image_format,
                    color=(46 + case_index, 76, 112),
                )
                upload = io.BytesIO(source)
                upload.name = f"cover.{extension}"

                with (
                    patch.object(ads_page.st, "session_state", session_state),
                    patch("ads_page._ads_dropbox_connection") as dropbox_connection,
                    patch("ads_page.save_ads_images_to_dropbox") as save_to_dropbox,
                    patch("ads_image_workflow.prepare_meta_posting_image") as posting_prepare,
                ):
                    ads_page._process_ads_image_upload(
                        result,
                        workflow,
                        slot,
                        upload,
                    )

                saved = workflow["slots"][slot["id"]]
                self.assertTrue(saved["valid"])
                self.assertEqual(saved["data"], source)
                self.assertEqual(saved["original_name"], f"cover.{extension}")
                self.assertEqual(saved["source_format"], image_format)
                self.assertEqual((saved["source_width"], saved["source_height"]), (96, 96))
                self.assertTrue(saved["preview_data"])
                self.assertIs(session_state[ads_page.ADS_IMAGE_STATE_KEY], workflow)
                dropbox_connection.assert_not_called()
                save_to_dropbox.assert_not_called()
                posting_prepare.assert_not_called()

    def test_rendered_instant_experience_supported_images_replace_without_red_error(self):
        app_test = run_ads_page()
        set_product_name(app_test, "Final Whistle Glory")
        select_option(app_test, "Category", "Football")
        select_option(app_test, "Country", "UK")
        select_option(app_test, "Campaign type", "Instant Experience")
        set_product_url(app_test, "https://sportscave.com.au/products/final-whistle-glory")
        seed_saved_result(app_test)

        slot_id = "instant-experience-premium-scarcity-right"
        cases = (
            ("cover.jpg", "JPEG", "image/jpeg"),
            ("cover.jpeg", "JPEG", "image/jpeg"),
            ("cover.png", "PNG", "image/png"),
            ("cover.webp", "WEBP", "image/webp"),
        )
        for case_index, (filename, image_format, mime_type) in enumerate(cases):
            with self.subTest(filename=filename):
                instant_experience_cover_uploaders(app_test)[0].set_value(
                    [
                        (
                            filename,
                            square_image_bytes(
                                image_format,
                                color=(20 + case_index * 50, 60 + case_index * 20, 110),
                            ),
                            mime_type,
                        )
                    ]
                )
                app_test.run(timeout=30)
                saved = app_test.session_state[ads_page.ADS_IMAGE_STATE_KEY]["slots"][slot_id]
                self.assertTrue(saved["valid"])
                self.assertEqual(saved["original_name"], filename)
                self.assertEqual(saved["source_format"], image_format)
                self.assertFalse(app_test.error)
                self.assertFalse(app_test.exception)

        app_test.run(timeout=20)
        persisted = app_test.session_state[ads_page.ADS_IMAGE_STATE_KEY]["slots"][slot_id]
        self.assertEqual(persisted["original_name"], "cover.webp")
        self.assertTrue(persisted["valid"])

    def test_failed_instant_experience_image_does_not_poison_valid_replacement(self):
        app_test = run_ads_page()
        set_product_name(app_test, "Final Whistle Glory")
        select_option(app_test, "Category", "Football")
        select_option(app_test, "Country", "UK")
        select_option(app_test, "Campaign type", "Instant Experience")
        set_product_url(app_test, "https://sportscave.com.au/products/final-whistle-glory")
        seed_saved_result(app_test)

        instant_experience_cover_uploaders(app_test)[0].set_value(
            [("broken.jpg", b"not an image", "image/jpeg")]
        )
        app_test.run(timeout=20)
        self.assertTrue(any("corrupt" in error.value for error in app_test.error))

        instant_experience_cover_uploaders(app_test)[0].set_value(
            [("recovered.jpg", square_image_bytes("JPEG"), "image/jpeg")]
        )
        app_test.run(timeout=30)
        slot = app_test.session_state[ads_page.ADS_IMAGE_STATE_KEY]["slots"][
            "instant-experience-premium-scarcity-right"
        ]
        self.assertTrue(slot["valid"])
        self.assertEqual(slot["original_name"], "recovered.jpg")
        self.assertFalse(app_test.error)

    def test_instant_experience_remove_middle_cover_preserves_route_slots(self):
        app_test = run_ads_page()
        set_product_name(app_test, "Final Whistle Glory")
        select_option(app_test, "Category", "Football")
        select_option(app_test, "Country", "UK")
        select_option(app_test, "Campaign type", "Instant Experience")
        set_product_url(app_test, "https://sportscave.com.au/products/final-whistle-glory")
        seed_saved_result(app_test)

        for index in range(1, 4):
            instant_experience_cover_uploaders(app_test)[index - 1].set_value(
                [(f"variation-{index}.png", square_png_bytes(color=(40 + index, 80, 120)), "image/png")]
            )
            app_test.run(timeout=30)

        buttons_by_label(app_test, "Remove")[1].click().run(timeout=20)
        workflow = app_test.session_state[ads_page.ADS_IMAGE_STATE_KEY]
        self.assertEqual(
            list(workflow["slots"].keys()),
            [
                "instant-experience-premium-scarcity-right",
                "instant-experience-premium-scarcity-left",
            ],
        )
        self.assertEqual(
            workflow["slots"]["instant-experience-premium-scarcity-left"]["original_name"],
            "variation-3.png",
        )

    def test_instant_experience_sport_country_and_fingerprints_are_automatic(self):
        baseball = ads_page.instant_experience_sport_direction("Baseball")
        basketball = ads_page.instant_experience_sport_direction("NBA")
        self.assertIn("ballpark memory", baseball)
        self.assertIn("charcoal limewash", basketball)
        self.assertNotIn("vehicles", baseball)

        fingerprints = ads_page.build_standard_instant_experience_fingerprints(
            product_name="Historic Baseball Legend Only 100 Will Ever Exist",
            category="Baseball",
            product_metadata={"edition_limit": 100, "edition_limit_source": "unit test"},
        )
        self.assertEqual(len(fingerprints), 3)
        self.assertEqual(
            {fingerprint["route_key"] for fingerprint in fingerprints},
            {
                "premium_scarcity_right",
                "premium_scarcity_front",
                "premium_scarcity_left",
            },
        )
        self.assertEqual(len({fingerprint["camera_family"] for fingerprint in fingerprints}), 3)
        self.assertEqual(len({fingerprint["wall_colour_family"] for fingerprint in fingerprints}), 3)

    def test_instant_experience_text_first_contract_uses_grouped_description_schema(self):
        from ads_ie_legacy_description import NEW_AD_STYLE_KEYS
        record,_,_=current_ie(self,category='NBA')
        for style in NEW_AD_STYLE_KEYS:self.assertIn(style,record['master_prompt'])
        self.assertEqual(record['master_prompt'].count('\nAD COPY\n'),3)
        self.assertNotIn('COPY VARIATIONS',record['master_prompt'])

    def test_instant_experience_three_scarcity_copy_structures_are_distinct(self):
        from ads_ie_legacy_description import NEW_AD_STYLE_KEYS
        record,_,_=current_ie(self,category='NBA')
        for style in NEW_AD_STYLE_KEYS:self.assertIn(style,record['master_prompt'])
        self.assertEqual(record['master_prompt'].count('\nAD COPY\n'),3)
        self.assertNotIn('COPY VARIATIONS',record['master_prompt'])

    def test_instant_experience_v2_image_contract_strengthens_source_and_room_physics(self):
        import ads_ie_two_line as footer
        record,rows,briefs=current_ie(self,category='Football')
        self.assertIn(footer.FOOTER_RULES,record['master_prompt'])
        for row,brief in zip(rows,briefs):
            self.assertIn(footer.image_copy(row),brief)
            self.assertNotIn(row['meta_headline_text'],brief.split('META HEADLINE')[0])

    def test_instant_experience_visual_contract_returns_three_grouped_concept_prompts(self):
        from ads_ie_legacy_description import NEW_AD_STYLE_KEYS
        record,_,_=current_ie(self,category='NBA')
        for style in NEW_AD_STYLE_KEYS:self.assertIn(style,record['master_prompt'])
        self.assertEqual(record['master_prompt'].count('\nAD COPY\n'),3)
        self.assertNotIn('COPY VARIATIONS',record['master_prompt'])

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
        slot_id = "instant-experience-premium-scarcity-right"
        self.assertEqual(list(workflow["slots"].keys()), [slot_id])
        self.assertEqual(workflow["slots"][slot_id]["original_name"], "legacy.png")
        self.assertIn("Hallway", workflow["slots"][slot_id]["label"])

    def test_new_campaign_submit_resets_only_incompatible_ads_upload_state(self):
        app_test = run_ads_page()
        set_product_name(app_test, "Six Laps Ahead")
        select_option(app_test, "Category", "Motorsport")
        select_option(app_test, "Country", "Australia")
        select_option(app_test, "Campaign type", "Carousel")
        set_product_url(app_test)
        seed_saved_result(app_test)
        carousel_image_uploaders(app_test)[0].set_value(
            [("carousel-one.png", square_png_bytes(), "image/png")]
        )
        app_test.run(timeout=30)
        old_context = app_test.session_state[ads_page.ADS_RESULT_STATE_KEY]["context_key"]

        select_option(app_test, "Campaign type", "Instant Experience")
        set_product_url(app_test)
        seed_saved_result(app_test)

        new_result = app_test.session_state[ads_page.ADS_RESULT_STATE_KEY]
        new_workflow = app_test.session_state[ads_page.ADS_IMAGE_STATE_KEY]
        self.assertNotEqual(new_result["context_key"], old_context)
        self.assertEqual(new_workflow["context_key"], new_result["context_key"])
        self.assertEqual(new_workflow["slots"], {})
        self.assertEqual(
            [uploader.label for uploader in instant_experience_cover_uploaders(app_test)],
            [
                f"{concept['scene_name']} Cover"
                for concept in ads_page.INSTANT_EXPERIENCE_CONCEPTS
            ],
        )

    def test_non_carousel_text_first_contract_requires_one_copyable_prompt(self):
        current_ie(self)
        # The active IE contract executes three images. Carousel remains text-first.
        prompt=ads_page.build_ads_prompt('Verified Edition','Cricket','Australia','Carousel')
        self.assertIn('Within this text-only scope, do not use an image-generation tool.',prompt)
        self.assertIn('only to copy-only or prompt-only requests',prompt)
        self.assertEqual(len(carousel_prompt_card_sections(visual_contract(prompt))),5)

    def test_old_instant_experience_cached_result_refreshes_to_v6_contract(self):
        record,_,_=current_ie(self)
        record['prompt_contract_version']='historical saved version'
        record['master_prompt']='Previously submitted owner-approved prompt'
        record['generated_ad_output']=record['master_prompt']
        saved=json.loads(json.dumps(record))
        self.assertIs(ads_page.ensure_current_ads_result_prompt(saved),saved)
        self.assertEqual(saved['master_prompt'],record['master_prompt'])
        self.assertEqual(saved['product_metadata'],record['product_metadata'])

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
        self.assertIn("Route key: premium_scarcity_right", contract)
        self.assertIn("Route key: premium_scarcity_front", contract)
        self.assertIn("Route key: premium_scarcity_left", contract)
        self.assertIn("Product name: Masters Sunday Frame", contract)
        self.assertIn("Sport/category: Golf", contract)
        self.assertIn("Country/market: Canada", contract)
        self.assertNotIn("Social Media Reels", contract)

    def test_shared_winner_copy_upgrade_is_idempotent_and_preserves_custom_text(self):
        custom_prompt = "CUSTOM SAVED INSTRUCTION\nKeep this exact specialist direction."

        once = ads_page.apply_shared_meta_winner_copy_upgrade(custom_prompt, "Carousel")
        twice = ads_page.apply_shared_meta_winner_copy_upgrade(once, "Carousel")

        self.assertEqual(once, twice)
        self.assertEqual(once.count(ads_page.META_WINNER_COPY_BLOCK_VERSION), 1)
        self.assertIn(custom_prompt, once)
        self.assertIn("If the approved campaign-specific template requires exactly one primary text", once)
        self.assertNotIn(ads_page.ie_copy.VERSION, once)
        self.assertIn(
            ads_page.ie_copy.VERSION,
            ads_page.apply_shared_meta_winner_copy_upgrade(custom_prompt, "Instant Experience"),
        )
        self.assertEqual(
            ads_page.apply_shared_meta_winner_copy_upgrade(custom_prompt, "Single Image / Video"),
            custom_prompt,
        )

    def test_shared_winner_copy_upgrade_reaches_carousel_and_instant_experience(self):
        carousel = ads_page.build_ads_prompt(
            "Final Whistle Glory",
            "Football",
            "UK",
            "Carousel",
            variation_token="winner-copy-carousel",
        )
        instant = ads_page.build_ads_prompt(
            "Final Whistle Glory",
            "Football",
            "UK",
            "Instant Experience",
            variation_token="winner-copy-instant",
        )

        self.assertIn(ads_page.META_WINNER_COPY_BLOCK_VERSION, carousel)
        self.assertIn(ads_page.ie_copy.VERSION, instant)
        self.assertIn("PRIMARY-TEXT ANGLE BALANCE", carousel)
        self.assertIn(ads_page.ie_copy.VERSION, instant)

    def test_staccato_and_framed_greatness_rules_are_reusable_and_fact_safe(self):
        import ads_ie_legacy_description as legacy
        normal=legacy.build_new_ad_style_rules('Verified Edition','NBA',{})
        verified=legacy.build_new_ad_style_rules('Verified Edition','NBA',{'EDITION_LIMIT':250})
        self.assertIn('Limited to 100 worldwide.',normal)
        self.assertIn('Limited to 100 worldwide.',verified)
        self.assertNotIn('Limited to 250',verified)
        self.assertIn('invented',legacy.DESCRIPTION_WORDING_INSTRUCTIONS.casefold())

    def test_instant_experience_v2_quality_contracts_are_centralized_and_once_per_cover(self):
        import ads_ie_two_line as footer
        record,rows,briefs=current_ie(self,category='Football')
        self.assertIn(footer.FOOTER_RULES,record['master_prompt'])
        for row,brief in zip(rows,briefs):
            self.assertIn(footer.image_copy(row),brief)
            self.assertNotIn(row['meta_headline_text'],brief.split('META HEADLINE')[0])

    def test_instant_experience_route_wording_and_typography_are_route_specific(self):
        import ads_ie_two_line as footer
        record,rows,briefs=current_ie(self,category='Football')
        self.assertIn(footer.FOOTER_RULES,record['master_prompt'])
        for row,brief in zip(rows,briefs):
            self.assertIn(footer.image_copy(row),brief)
            self.assertNotIn(row['meta_headline_text'],brief.split('META HEADLINE')[0])

    def test_instant_experience_scarcity_prompt_uses_bottom_strip_layout(self):
        import ads_ie_two_line as footer
        record,rows,briefs=current_ie(self,category='Football')
        self.assertIn(footer.FOOTER_RULES,record['master_prompt'])
        for row,brief in zip(rows,briefs):
            self.assertIn(footer.image_copy(row),brief)
            self.assertNotIn(row['meta_headline_text'],brief.split('META HEADLINE')[0])

    def test_instant_experience_scarcity_routes_use_distinct_compositions(self):
        import ads_ie_two_line as footer
        record,rows,briefs=current_ie(self,category='Football')
        self.assertIn(footer.FOOTER_RULES,record['master_prompt'])
        for row,brief in zip(rows,briefs):
            self.assertIn(footer.image_copy(row),brief)
            self.assertNotIn(row['meta_headline_text'],brief.split('META HEADLINE')[0])

    def test_instant_experience_package_readiness_rejects_manual_soft_cta(self):
        notes = instant_experience_csv_notes()
        workflow = {"ad_notes": {"instant_experience_concepts": notes}}
        self.assertTrue(ads_page.instant_experience_copy_complete(workflow))

        notes["premium_scarcity_front"][0] = {
            "primary_text": "This belongs with the fans who understand it. Make it yours.",
            "headline": "This Belongs With Fans",
            "cta": "Make It Yours",
        }
        self.assertFalse(ads_page.instant_experience_copy_complete(workflow))
        self.assertEqual(
            ads_page._instant_experience_concept_complete_count(
                workflow,
                "premium_scarcity_front",
            ),
            2,
        )

    def test_rendered_instant_experience_csv_import_populates_existing_fields(self):
        app_test = run_ads_page()
        set_product_name(app_test, "Six Laps Ahead")
        select_option(app_test, "Category", "Motorsport")
        select_option(app_test, "Country", "Australia")
        select_option(app_test, "Campaign type", "Instant Experience")
        set_product_url(app_test)
        seed_saved_result(app_test)
        result = dict(app_test.session_state[ads_page.ADS_RESULT_STATE_KEY])
        expected = instant_experience_csv_notes()
        data = ads_page.build_instant_experience_copy_csv(
            result,
            concept_notes=expected,
        )

        uploader_by_label(app_test, "Import CSV").set_value(
            [("instant-experience-copy.csv", data, "text/csv")]
        )
        app_test.run(timeout=30)

        primary_values = [
            text_area.value
            for text_area in app_test.text_area
            if text_area.label == "Description"
        ]
        headline_values = [
            text_area.value
            for text_area in app_test.text_area
            if text_area.label == "Headline"
        ]
        cta_values = [
            text_area.value
            for text_area in app_test.text_area
            if text_area.label == "CTA"
        ]
        self.assertEqual(len(primary_values), 3)
        self.assertEqual(primary_values[0], expected["premium_scarcity_right"][0]["primary_text"])
        self.assertEqual(primary_values[-1], expected["premium_scarcity_left"][0]["primary_text"])
        self.assertEqual(headline_values[1], expected["premium_scarcity_front"][0]["headline"])
        self.assertEqual(cta_values[2], expected["premium_scarcity_left"][0]["cta"])
        self.assertEqual(len(app_test.exception), 0)

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
