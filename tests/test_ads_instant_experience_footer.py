from pathlib import Path
import unittest

import ads_page
from sports_cave_prompt_blocks import SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER


ROOT = Path(__file__).resolve().parents[1]


def instant_experience_prompt(country="Australia"):
    return ads_page.build_ads_prompt(
        "Shane Warne King of Spin",
        "Cricket",
        country,
        "Instant Experience",
        product_url="https://sportscave.com.au/products/shane-warne-king-of-spin",
        variation_token=f"fixed-footer-{country}",
    )


def route_sections(prompt):
    markers = (
        "Route key: premium_scarcity_right",
        "Route key: premium_scarcity_front",
        "Route key: premium_scarcity_left",
    )
    starts = [prompt.index(marker) for marker in markers]
    return (
        prompt[starts[0] : starts[1]],
        prompt[starts[1] : starts[2]],
        prompt[starts[2] :],
    )


class InstantExperienceFooterRegressionTests(unittest.TestCase):
    def test_each_standalone_cover_contains_one_fixed_footer_contract(self):
        prompt = instant_experience_prompt()
        marker = ads_page.SPORTS_CAVE_IE_FIXED_OPAQUE_FOOTER_RULES_V1.splitlines()[0]
        self.assertEqual(prompt.count(marker), 3)
        for section in route_sections(prompt):
            self.assertEqual(section.count(marker), 1)

    def test_footer_is_fixed_opaque_full_width_and_bottom_anchored(self):
        contract = ads_page.build_instant_experience_fixed_opaque_footer_rules()
        for wording in (
            "span the complete image width from the left edge to the right edge",
            "occupy approximately the bottom 21–23% of the canvas",
            "anchored flush to the bottom edge",
            "perfectly straight, hard top edge",
            "be fully opaque",
            "completely conceal the room photograph behind it",
            "thin restrained gold separator",
        ):
            self.assertIn(wording, contract)

    def test_footer_rejects_fades_gradients_transparency_and_room_visibility(self):
        contract = ads_page.build_instant_experience_fixed_opaque_footer_rules()
        for wording in (
            "fade upward",
            "black gradient",
            "transparency",
            "feathering",
            "vignette",
            "reveal furniture, flooring, walls or any part of the room",
        ):
            self.assertIn(wording, contract)
        default_prompt = ads_page.build_default_instant_experience_cover_prompt_requirements(
            "Shane Warne King of Spin",
            "Cricket",
            "Australia",
        )
        self.assertNotIn("Restrained vignette", default_prompt)
        self.assertNotIn("No loud gradients", default_prompt)

    def test_australia_and_usa_use_the_identical_footer_contract(self):
        footer = ads_page.build_instant_experience_fixed_opaque_footer_rules()
        australia = instant_experience_prompt("Australia")
        usa = instant_experience_prompt("USA")
        self.assertEqual(australia.count(footer), 3)
        self.assertEqual(usa.count(footer), 3)
        for country in ("Australia", "USA", "UK", "Canada", "New Zealand"):
            self.assertEqual(instant_experience_prompt(country).count(footer), 3)
        self.assertIn("Never create separate Australian layout behaviour", footer)

    def test_headline_validator_accepts_control_and_rejects_warne_regression(self):
        valid = "ONLY 100 WILL EVER EXIST"
        invalid = "THE WARNE EDITION STOPS AT 100"
        self.assertTrue(ads_page.instant_experience_on_image_headline_is_valid(valid))
        self.assertFalse(ads_page.instant_experience_on_image_headline_is_valid(invalid))
        errors = ads_page.instant_experience_on_image_headline_errors(invalid)
        self.assertTrue(any("28 characters" in error for error in errors))
        self.assertEqual(
            ads_page.shorten_instant_experience_on_image_headline(invalid),
            valid,
        )
        resolved = ads_page.resolve_instant_experience_on_image_copy(
            invalid,
            "Once they're claimed, this edition retires forever.",
            "CLAIM YOUR EDITION",
        )
        self.assertEqual(resolved["headline_text"], valid)
        self.assertNotIn(invalid, instant_experience_prompt())

    def test_on_image_copy_limits_and_one_line_rules_are_enforced(self):
        self.assertTrue(
            ads_page.instant_experience_on_image_headline_errors(
                "ONE TWO THREE FOUR FIVE SIX SEVEN"
            )
        )
        errors = ads_page.validate_instant_experience_on_image_copy(
            "ONLY 100 WILL EVER EXIST\nTODAY",
            "This supporting line is deliberately far too long to fit comfortably inside the footer on one mobile-readable line",
            "CLAIM YOUR LIMITED EDITION TODAY",
        )
        self.assertTrue(any("headline must remain on one line" in error for error in errors))
        self.assertTrue(any("supporting line exceeds" in error for error in errors))
        self.assertTrue(any("CTA exceeds" in error for error in errors))

    def test_resolved_cover_copy_is_valid_before_prompt_generation(self):
        visuals = ads_page.resolve_standard_instant_experience_visuals(
            product_name="Shane Warne King of Spin",
            category="Cricket",
            product_metadata={"edition_limit": 100},
            variation_token="copy-fit",
        )
        self.assertEqual(len(visuals), 3)
        for visual in visuals:
            self.assertEqual(
                ads_page.validate_instant_experience_on_image_copy(
                    visual["headline_text"],
                    visual["supporting_line"],
                    visual["cta_text"],
                ),
                (),
            )

    def test_copy_fit_contract_requires_shortening_not_smaller_typography(self):
        contract = ads_page.build_instant_experience_on_image_copy_fit_rules()
        for wording in (
            "no more than six words and no more than 28 characters",
            "no more than 12 words and no more than 70 characters",
            "no more than four words and no more than 24 characters",
            "shorten it before returning the standalone image-generation prompt",
            "Never solve overflow by shrinking typography",
            "on exactly one line",
        ):
            self.assertIn(wording, contract)

    def test_existing_routes_output_product_lock_and_realism_are_preserved(self):
        prompt = instant_experience_prompt()
        grouped = ads_page.build_standard_instant_experience_group_output_contract(
            product_name="Shane Warne King of Spin",
            category="Cricket",
            country="Australia",
            product_url="https://sportscave.com.au/products/shane-warne-king-of-spin",
            variation_token="fixed-footer-Australia",
        )
        for route_key in (
            "premium_scarcity_right",
            "premium_scarcity_front",
            "premium_scarcity_left",
        ):
            self.assertIn(f"Route key: {route_key}", prompt)
        self.assertEqual(
            grouped.count("| Description | Description Key | Description Label | Description Copy | Headline | CTA |"),
            3,
        )
        self.assertEqual(prompt.count("PRODUCT LOCK — ABSOLUTE"), 3)
        self.assertEqual(prompt.count(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER), 3)

    def test_non_instant_experience_prompts_do_not_receive_footer_contract(self):
        marker = ads_page.SPORTS_CAVE_IE_FIXED_OPAQUE_FOOTER_RULES_V1.splitlines()[0]
        for campaign_type in ("Carousel", "Single Image / Video"):
            prompt = ads_page.build_ads_prompt(
                "Shane Warne King of Spin",
                "Cricket",
                "Australia",
                campaign_type,
                product_url="https://sportscave.com.au/products/shane-warne-king-of-spin",
            )
            self.assertNotIn(marker, prompt)
        social_source = (ROOT / "social_media_creator.py").read_text(encoding="utf-8")
        self.assertNotIn(marker, social_source)


if __name__ == "__main__":
    unittest.main()
