import io
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from PIL import Image
import requests
from streamlit.testing.v1 import AppTest

import ads_final_review
import ads_page


ROOT = Path(__file__).resolve().parents[1]


def image_bytes(image_format="PNG", size=(120, 90), color=(41, 62, 86, 255)):
    buffer = io.BytesIO()
    mode = "RGBA" if image_format == "PNG" else "RGB"
    image = Image.new(mode, size, color if mode == "RGBA" else color[:3])
    image.save(buffer, format=image_format)
    return buffer.getvalue()


def run_ads_page():
    app_test = AppTest.from_file(str(ROOT / "app.py"))
    app_test.session_state["sports_cave_authenticated"] = True
    app_test.session_state["selected_page"] = "Ads"
    app_test.session_state["startup_shell_loaded"] = True
    return app_test.run(timeout=20)


def select_option(app_test, label, value):
    for selectbox in app_test.selectbox:
        if selectbox.label == label:
            selectbox.select(value)
            return
    raise AssertionError(f"{label} was not rendered.")


def set_product_name(app_test, value):
    for widget in list(app_test.text_input) + list(app_test.selectbox):
        if widget.label == "Product name":
            if getattr(widget, "options", None):
                widget.select(value if value in widget.options else widget.options[0])
            else:
                widget.set_value(value)
            return
    raise AssertionError("Product name was not rendered.")


def button(app_test, label):
    for candidate in app_test.button:
        if candidate.label == label:
            return candidate
    raise AssertionError(f"{label} was not rendered.")


def uploader(app_test, label):
    for candidate in app_test.file_uploader:
        if candidate.label == label:
            return candidate
    raise AssertionError(f"{label} was not rendered.")


def text_area(app_test, label):
    for candidate in app_test.text_area:
        if candidate.label == label:
            return candidate
    raise AssertionError(f"{label} was not rendered.")


def submitted_ads_page(campaign_type="Carousel"):
    app_test = run_ads_page()
    set_product_name(app_test, "Six Laps Ahead")
    select_option(app_test, "Category", "Motorsport")
    select_option(app_test, "Country", "Australia")
    select_option(app_test, "Campaign type", campaign_type)
    button(app_test, "Submit").click().run(timeout=20)
    return app_test


def valid_review():
    breakdown = [
        {
            "category": category,
            "points_earned": available - 2,
            "points_available": available,
        }
        for category, available in ads_final_review.SCORE_RUBRIC
    ]
    return {
        "overall_score": 1,
        "verdict": "Small Changes",
        "brutal_truth": "Strong product focus. The CTA needs clearer mobile prominence.",
        "score_breakdown": breakdown,
        "strengths": ["The artwork is immediately visible."],
        "priority_changes": [
            {
                "priority": "High",
                "what_is_wrong": "The CTA is visually quiet.",
                "conversion_risk": "The next action is easy to miss.",
                "exact_correction": "Increase CTA contrast without changing its wording.",
                "expected_impact": "Clearer purchase intent.",
            }
        ],
        "creative_reviews": [
            {
                "image_number": 1,
                "purpose": "Product identity",
                "score": 8.2,
                "visual_verdict": "Premium and readable.",
                "copy_alignment": "The image supports the identity message.",
                "required_correction": "Keep as is",
            }
        ],
        "copy_review": [
            {
                "field": "Headline",
                "verdict": "Clear but too long.",
                "original": "Six Laps Forever",
                "replacement": "Six Laps",
                "current_character_count": 16,
                "maximum_character_count": ads_page.CAROUSEL_CARD_MAX_CHARACTERS,
                "replacement_character_count": 8,
                "unsupported_claims": "",
            }
        ],
        "recommended_final_copy": "Six Laps",
        "launch_decision": "Make these changes first",
        "next_actions": ["Shorten the headline."],
        "test_recommendation": "Test the current hero against one tighter product crop.",
        "unverified_items": ["Edition quantity"],
    }


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.payload = payload

    def json(self):
        return self.payload


class AdsFinalReviewServiceTests(unittest.TestCase):
    def test_png_jpeg_and_webp_are_validated_from_decoded_content(self):
        for image_format in ("PNG", "JPEG", "WEBP"):
            with self.subTest(image_format=image_format):
                item = ads_final_review.validate_review_image(
                    image_bytes(image_format),
                    filename=f"O'Neal & Jürgen.{image_format.casefold()}",
                )
                self.assertEqual(item["format"], image_format)
                self.assertEqual((item["width"], item["height"]), (120, 90))
                self.assertIn("O'Neal & Jürgen", item["filename"])

    def test_corrupt_and_unsupported_files_fail_safely(self):
        with self.assertRaisesRegex(ads_final_review.AdsReviewValidationError, "corrupt"):
            ads_final_review.validate_review_image(b"not an image", filename="broken.png")
        buffer = io.BytesIO()
        Image.new("RGB", (20, 20)).save(buffer, format="GIF")
        with self.assertRaisesRegex(ads_final_review.AdsReviewValidationError, "Unsupported"):
            ads_final_review.validate_review_image(buffer.getvalue(), filename="animated.gif")

    def test_request_contains_context_images_live_limit_and_no_credentials(self):
        screenshot = ads_final_review.validate_review_image(
            image_bytes("PNG"),
            filename="Meta setup.png",
        )
        creative = ads_final_review.validate_review_image(
            image_bytes("JPEG"),
            filename="Carousel 01.jpg",
        )
        context = {
            "product_name": "Six Laps Ahead",
            "category": "Motorsport",
            "country": "Australia",
            "campaign_type": "Carousel",
            "campaign_angle": "race memory",
            "generated_primary_text": "The mountain remembers.",
            "headlines": ["Six Laps"],
            "descriptions": ["Race Memory"],
            "cta": "Shop Now",
            "product_url": "https://sportscave.com.au/products/six-laps",
            "carousel_character_limit": ads_page.CAROUSEL_CARD_MAX_CHARACTERS,
        }
        payload = ads_final_review.build_review_request_payload(
            context,
            [screenshot],
            [creative],
            "Final exact copy",
            model="test-model",
        )
        serialized = json.dumps(payload)
        content = payload["input"][0]["content"]

        self.assertEqual(payload["model"], "test-model")
        self.assertFalse(payload["store"])
        self.assertEqual(
            [item["type"] for item in content].count("input_image"),
            2,
        )
        self.assertIn("Six Laps Ahead", serialized)
        self.assertIn("Final exact copy", serialized)
        self.assertIn(
            f"is {ads_page.CAROUSEL_CARD_MAX_CHARACTERS} characters",
            payload["instructions"],
        )
        self.assertNotIn("api_key", serialized.casefold())
        self.assertNotIn("bearer", serialized.casefold())

    def test_rubric_fact_check_tone_and_visual_requirements_are_present(self):
        instructions = ads_final_review.build_review_instructions(
            ads_page.CAROUSEL_CARD_MAX_CHARACTERS
        )
        for category, points in ads_final_review.SCORE_RUBRIC:
            self.assertIn(f"{category}: {points} points", instructions)
        for phrase in (
            "Unable to verify from the supplied ad",
            "factually supported",
            "wording fans could reasonably ridicule",
            "framed artwork the immediate hero",
            "country terminology",
            "repeated visual treatments",
            "Do not recommend obvious sports props",
        ):
            self.assertIn(phrase, instructions)

    def test_response_validation_uses_weighted_total_and_required_structure(self):
        review = ads_final_review.validate_review_response(valid_review())
        expected_total = sum(
            available - 2 for _category, available in ads_final_review.SCORE_RUBRIC
        )
        self.assertEqual(review["overall_score"], round(expected_total / 10, 1))
        broken = valid_review()
        broken["score_breakdown"][0]["points_available"] = 99
        with self.assertRaises(ads_final_review.AdsReviewValidationError):
            ads_final_review.validate_review_response(broken)

    def test_every_supplied_creative_requires_a_review_entry(self):
        with self.assertRaisesRegex(
            ads_final_review.AdsReviewValidationError,
            "missing",
        ):
            ads_final_review.validate_review_response(
                valid_review(),
                expected_creatives=2,
            )

    def test_invalid_structured_result_gets_exactly_one_safe_repair(self):
        repaired = valid_review()
        request_post = Mock(
            side_effect=[
                FakeResponse(200, {"output_text": "not json"}),
                FakeResponse(200, {"output_text": json.dumps(repaired)}),
            ]
        )
        result = ads_final_review.request_final_ad_review(
            {
                "carousel_character_limit": ads_page.CAROUSEL_CARD_MAX_CHARACTERS,
            },
            [],
            [],
            "Final copy",
            request_post=request_post,
            api_key="test-secret",
        )

        self.assertEqual(request_post.call_count, 2)
        self.assertEqual(result["verdict"], "Small Changes")
        repair_payload = request_post.call_args_list[1].kwargs["json"]
        self.assertIn("Repair", repair_payload["instructions"])
        self.assertFalse(repair_payload["store"])

    def test_second_invalid_result_returns_retryable_error(self):
        request_post = Mock(
            return_value=FakeResponse(200, {"output_text": "still not json"})
        )
        with self.assertRaisesRegex(ads_final_review.AdsReviewError, "Review Again"):
            ads_final_review.request_final_ad_review(
                {"carousel_character_limit": 17},
                [],
                [],
                "copy",
                request_post=request_post,
                api_key="test-secret",
            )
        self.assertEqual(request_post.call_count, 2)

    def test_timeout_and_rate_limit_have_safe_messages(self):
        timeout_post = Mock(side_effect=requests.Timeout("private details"))
        with self.assertRaisesRegex(ads_final_review.AdsReviewError, "timed out"):
            ads_final_review.request_final_ad_review(
                {"carousel_character_limit": 17},
                [],
                [],
                "copy",
                request_post=timeout_post,
                api_key="test-secret",
            )
        rate_post = Mock(return_value=FakeResponse(429, {"error": "private"}))
        with self.assertRaisesRegex(ads_final_review.AdsReviewError, "busy"):
            ads_final_review.request_final_ad_review(
                {"carousel_character_limit": 17},
                [],
                [],
                "copy",
                request_post=rate_post,
                api_key="test-secret",
            )

    def test_review_module_does_not_log_credentials_or_image_payloads(self):
        source = (ROOT / "ads_final_review.py").read_text(encoding="utf-8")
        self.assertNotIn("logging.", source)
        self.assertNotIn("print(", source)
        self.assertNotIn("response.text", source)


class AdsFinalReviewStateTests(unittest.TestCase):
    def setUp(self):
        self.result = ads_page.build_ads_result_record(
            "Six Laps Ahead",
            "Motorsport",
            "Australia",
            "Carousel",
            product_url="https://sportscave.com.au/products/six-laps",
            variation_token="review-state",
        )

    def test_context_automatically_includes_current_campaign_values(self):
        self.result.update(
            {
                "generated_ad_output": "Final generated copy",
                "generated_primary_text": "Primary text",
                "headlines": ["Six Laps"],
                "descriptions": ["Race Memory"],
                "cta": "Shop Now",
            }
        )
        context = ads_page.build_ads_review_context(self.result)

        self.assertEqual(context["product_name"], "Six Laps Ahead")
        self.assertEqual(context["category"], "Motorsport")
        self.assertEqual(context["country"], "Australia")
        self.assertEqual(context["campaign_type"], "Carousel")
        self.assertEqual(context["generated_primary_text"], "Primary text")
        self.assertEqual(context["headlines"], ["Six Laps"])
        self.assertEqual(context["descriptions"], ["Race Memory"])
        self.assertEqual(context["cta"], "Shop Now")
        self.assertEqual(context["product_url"], self.result["product_url"])
        self.assertEqual(
            context["carousel_character_limit"],
            ads_page.CAROUSEL_CARD_MAX_CHARACTERS,
        )

    def test_generated_copy_prefills_only_when_actual_output_is_available(self):
        self.assertEqual(ads_page._ads_review_prefill(self.result), "")
        self.result["generated_ad_output"] = "Exact final Meta copy"
        workflow = ads_page._new_ads_review_workflow(self.result)
        self.assertEqual(workflow["final_copy"], "Exact final Meta copy")

    def test_minimum_material_gate(self):
        workflow = ads_page._new_ads_review_workflow(self.result)
        self.assertFalse(ads_page._review_ready(workflow))
        workflow["screenshots"] = [{"id": "screenshot"}]
        self.assertTrue(ads_page._review_ready(workflow))
        workflow["screenshots"] = []
        workflow["final_copy"] = "Exact copy"
        workflow["creatives"] = [{"id": "creative"}]
        self.assertTrue(ads_page._review_ready(workflow))

    def test_reordering_preserves_supplied_order(self):
        workflow = ads_page._new_ads_review_workflow(self.result)
        workflow["creatives"] = [{"id": "one"}, {"id": "two"}, {"id": "three"}]
        with patch.object(ads_page.st, "session_state", {ads_page.ADS_REVIEW_STATE_KEY: workflow}):
            ads_page._move_review_image(self.result, "creatives", 2, -1)
            reordered = ads_page.st.session_state[ads_page.ADS_REVIEW_STATE_KEY]["creatives"]
        self.assertEqual([item["id"] for item in reordered], ["one", "three", "two"])


class AdsFinalReviewUiTests(unittest.TestCase):
    def test_section_is_at_bottom_with_two_multiple_upload_areas(self):
        app_test = submitted_ads_page()
        labels = [candidate.label for candidate in app_test.file_uploader]
        self.assertEqual(labels[-2:], ["Finished Meta Ad Screenshots", "Final Creative Images"])
        self.assertTrue(uploader(app_test, "Finished Meta Ad Screenshots").accept_multiple_files)
        self.assertTrue(uploader(app_test, "Final Creative Images").accept_multiple_files)
        self.assertTrue(button(app_test, "Review Finished Ad").disabled)
        self.assertEqual(len(app_test.exception), 0)

    def test_multiple_uploads_persist_and_screenshot_enables_review(self):
        app_test = submitted_ads_page()
        screenshot_uploader = uploader(app_test, "Finished Meta Ad Screenshots")
        screenshot_uploader.set_value(
            [
                ("Meta mobile.png", image_bytes("PNG"), "image/png"),
                ("Meta desktop.jpg", image_bytes("JPEG"), "image/jpeg"),
            ]
        )
        app_test.run(timeout=30)

        workflow = app_test.session_state[ads_page.ADS_REVIEW_STATE_KEY]
        self.assertEqual(
            [item["filename"] for item in workflow["screenshots"]],
            ["Meta mobile.png", "Meta desktop.jpg"],
        )
        self.assertFalse(button(app_test, "Review Finished Ad").disabled)
        app_test.run(timeout=20)
        self.assertEqual(len(app_test.session_state[ads_page.ADS_REVIEW_STATE_KEY]["screenshots"]), 2)

    def test_copy_plus_creative_enables_review_and_clear_resets_only_review(self):
        app_test = submitted_ads_page()
        original_prompt = app_test.session_state[ads_page.ADS_RESULT_STATE_KEY]["master_prompt"]
        uploader(app_test, "Final Creative Images").set_value(
            [("Carousel 01.webp", image_bytes("WEBP"), "image/webp")]
        )
        text_area(app_test, "Final Copy").set_value("Exact final Meta copy")
        app_test.run(timeout=30)

        self.assertFalse(button(app_test, "Review Finished Ad").disabled)
        button(app_test, "Clear Review").click().run(timeout=20)
        workflow = app_test.session_state[ads_page.ADS_REVIEW_STATE_KEY]
        self.assertEqual(workflow["screenshots"], [])
        self.assertEqual(workflow["creatives"], [])
        self.assertIsNone(workflow["review"])
        self.assertEqual(
            app_test.session_state[ads_page.ADS_RESULT_STATE_KEY]["master_prompt"],
            original_prompt,
        )

    def test_creative_can_be_removed_and_replaced_without_duplicate_uploads(self):
        app_test = submitted_ads_page()
        uploader(app_test, "Final Creative Images").set_value(
            [
                ("Carousel 01.png", image_bytes("PNG", color=(10, 20, 30, 255)), "image/png"),
                ("Carousel 02.png", image_bytes("PNG", color=(40, 50, 60, 255)), "image/png"),
            ]
        )
        text_area(app_test, "Final Copy").set_value("Exact final copy")
        app_test.run(timeout=30)
        self.assertEqual(
            len(app_test.session_state[ads_page.ADS_REVIEW_STATE_KEY]["creatives"]),
            2,
        )

        button(app_test, "Remove").click().run(timeout=20)
        self.assertEqual(
            [item["filename"] for item in app_test.session_state[ads_page.ADS_REVIEW_STATE_KEY]["creatives"]],
            ["Carousel 02.png"],
        )
        uploader(app_test, "Final Creative Images").set_value(
            [("Carousel 01 replacement.webp", image_bytes("WEBP"), "image/webp")]
        )
        app_test.run(timeout=30)
        filenames = [
            item["filename"]
            for item in app_test.session_state[ads_page.ADS_REVIEW_STATE_KEY]["creatives"]
        ]
        self.assertEqual(filenames, ["Carousel 02.png", "Carousel 01 replacement.webp"])
        self.assertEqual(len(set(filenames)), 2)

    def test_review_result_renders_and_review_again_does_not_duplicate_submission(self):
        app_test = submitted_ads_page()
        uploader(app_test, "Finished Meta Ad Screenshots").set_value(
            [("Meta setup.png", image_bytes("PNG"), "image/png")]
        )
        app_test.run(timeout=30)

        with patch(
            "ads_final_review.request_final_ad_review",
            return_value=ads_final_review.validate_review_response(valid_review()),
        ) as review_request:
            button(app_test, "Review Finished Ad").click().run(timeout=30)

        self.assertEqual(review_request.call_count, 1)
        self.assertIn("Review Again", [candidate.label for candidate in app_test.button])
        self.assertTrue(any("Overall Score" in markdown.value for markdown in app_test.markdown))
        self.assertTrue(any("Brutal Truth" in markdown.value for markdown in app_test.markdown))
        self.assertEqual(len(app_test.exception), 0)

    def test_campaign_change_resets_review_identity_without_touching_ads_exports(self):
        app_test = submitted_ads_page()
        uploader(app_test, "Finished Meta Ad Screenshots").set_value(
            [("Meta setup.png", image_bytes("PNG"), "image/png")]
        )
        app_test.run(timeout=30)
        old_context = app_test.session_state[ads_page.ADS_REVIEW_STATE_KEY]["context_key"]

        select_option(app_test, "Campaign type", "Instant Experience")
        button(app_test, "Submit").click().run(timeout=20)
        review_workflow = app_test.session_state[ads_page.ADS_REVIEW_STATE_KEY]
        image_workflow = app_test.session_state[ads_page.ADS_IMAGE_STATE_KEY]
        self.assertNotEqual(review_workflow["context_key"], old_context)
        self.assertEqual(review_workflow["screenshots"], [])
        self.assertEqual(review_workflow["creatives"], [])
        self.assertEqual(
            review_workflow["context_key"],
            image_workflow["context_key"],
        )

    def test_existing_campaign_prompt_and_export_contract_remain_unchanged(self):
        prompt = ads_page.build_ads_prompt(
            "Six Laps Ahead",
            "Motorsport",
            "Australia",
            "Carousel",
            variation_token="unchanged-review-test",
        )
        self.assertIn("SPORTS CAVE MOTORSPORT CAROUSEL AD", prompt)
        self.assertIn("MASTER RESPONSE AND VISUAL OUTPUT CONTRACT", prompt)
        self.assertNotIn("Final Ad Review", prompt)
        self.assertEqual(len(ads_page.ads_image_workflow.campaign_image_slots("Carousel")), 5)
