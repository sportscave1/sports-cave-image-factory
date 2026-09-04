import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock

import ads_page
from sports_cave_prompt_blocks import SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER
from tests.test_ads_page import carousel_prompt_card_sections, visual_contract


def final_prompt(category="Cricket", country="Australia", **kwargs):
    return ads_page.build_ads_prompt(
        "Collector Detail Test", category, country, "Carousel",
        product_url="https://www.sportscaveshop.com/products/collector",
        variation_token="fixed-detail-test", **kwargs,
    )


class CarouselDetailPromptTests(unittest.TestCase):
    def test_final_card_one_enforces_angle_glass_shadows_and_exact_product_for_every_sport(self):
        for category in ads_page.CATEGORY_OPTIONS[1:]:
            with self.subTest(category=category):
                card = carousel_prompt_card_sections(visual_contract(final_prompt(category)))[1]
                for instruction in (
                    "5–12 degree off-axis / slight three-quarter camera angle",
                    "genuine transparent frame glass", "subtle premium glare", "soft controlled reflection",
                    "fake white streak overlays or synthetic CGI shine", "realistic wall contact shadow",
                    "soft directional shadow", "ambient occlusion", "consistent lighting direction",
                    "ONE rigid rectangular physical object only", "distort typography or faces",
                    "change the artwork crop", "all four outer frame edges",
                    "exact compositing source", "never mirror or recolour",
                    "Required nostalgic wall tone:", "matte plaster or painted-wall finish", "low saturation",
                    f"Selected sport: {category}", "Selected Sports Cave product: Collector Detail Test",
                ):
                    self.assertIn(instruction, card)
                self.assertNotIn("2-4 degree", card)
                self.assertNotIn("almost perfectly straight-on", card)
                self.assertNotIn("or a different off-centre placement. These are examples only", card)

    def test_wall_tone_uses_taxonomy_aliases_case_and_neutral_fallback(self):
        resolve = ads_page.carousel_nostalgic_wall_treatment
        for canonical, aliases in {
            "NBA": ("Basketball", " nba ", "NBA basketball", "Basketball / NBA"),
            "Football": ("Soccer", "Association Football", "Football / Soccer"),
            "NFL": ("American Football", "American Football / NFL"),
            "Australian Rules": ("AFL", "Australian Rules / AFL"),
            "Ice Hockey": ("NHL", "Ice Hockey / NHL", "ice_hockey"),
            "Combat": ("MMA", "Boxing", "Combat sports / Boxing / MMA"),
            "Cricket": (" CRICKET ", "cricket"),
            "Rugby League": ("NRL",),
        }.items():
            for alias in aliases:
                with self.subTest(alias=alias):
                    self.assertEqual(resolve(canonical), resolve(alias))
        self.assertNotEqual(resolve("Cricket"), resolve("Basketball"))
        self.assertIn("pavilion green", resolve("Cricket"))
        self.assertIn("hardwood tan", resolve("Basketball"))
        for unknown in (None, "", "unmapped sport", "Select category"):
            self.assertEqual(resolve(unknown), resolve("Other"))
            self.assertIn("muted gallery taupe", resolve(unknown))
        for category in ads_page.CATEGORY_OPTIONS[1:]:
            if category != "Other":
                self.assertNotEqual(resolve(category), resolve("Other"))

    def test_resolved_tone_reaches_final_card_and_survives_missing_mockups_foundation(self):
        for category in ("Cricket", "Basketball", "Unmapped sport"):
            card = carousel_prompt_card_sections(visual_contract(final_prompt(category)))[1]
            self.assertIn(ads_page.carousel_nostalgic_wall_treatment(category), card)
        with mock.patch.object(ads_page.image_factory, "get_close_up_wall_prompt_foundation", return_value=""):
            card = carousel_prompt_card_sections(visual_contract(final_prompt()))[1]
            self.assertIn("pavilion green", card)
            self.assertIn("5–12 degree off-axis", card)

    def test_final_card_five_has_genuine_numbered_detail_and_physical_magnifier(self):
        card = carousel_prompt_card_sections(visual_contract(final_prompt()))[5]
        for instruction in (
            "premium photorealistic magnifying glass detail shot",
            "ACTUALLY visible", "prioritise the NUMBERED EDITION PLATE",
            "bottom centre", "actual visible location, never an assumed position",
            "clear glass lens, premium metal rim, realistic handle",
            "optical magnification/refraction ONLY inside the physical lens",
            "unchanged printed product", "No distortion or artificial blur outside the magnifying glass",
            "Do not excessively enlarge text", "genuine transparent artwork glazing AND a clear magnifying-glass lens",
            "must NEVER conceal the edition information", "realistic mitred joins",
            "correct aspect ratio", "ONE rigid rectangular physical object",
            "soft natural directional light", "contact shadows", "ambient occlusion",
            "No random props except the magnifying glass", "No room decor", "No furniture", "No people",
            "No neon signs", "No extra wall art", "No added text",
            "No excessive HDR, bloom, glow, fisheye distortion, fake blur",
            "Selected sport: Cricket", "Selected Sports Cave product: Collector Detail Test",
        ):
            self.assertIn(instruction, card)
        for prohibition in (
            "Do not create fake text.", "Do not create a fake edition number.", "Do not change the edition number.",
            "Do not invent scarcity information.", "Do not add new badges.", "Do not add new logos.",
            "Do not add extra text overlays.", "Do not add watermarks.",
        ):
            self.assertIn(prohibition, card)
        self.assertIn("If no genuine edition detail is visible/readable", card)
        self.assertIn("immutable physical reference", card)
        self.assertIn("Preserve every athlete, face, body", card)
        self.assertIn("font, colour, border, crop, layout", card)
        self.assertIn("frame colour, material, thickness, geometry and proportions", card)
        self.assertNotIn("unless the approved card concept explicitly requires on-image text", card)

    def test_final_master_retains_shared_realism_once_and_five_ordered_slots(self):
        prompt = visual_contract(final_prompt())
        sections = carousel_prompt_card_sections(prompt)
        self.assertEqual(list(sections), [1, 2, 3, 4, 5])
        self.assertEqual(prompt.count(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER), 1)
        self.assertIn("SPORTS CAVE PRODUCT AND MOCKUP LOCK - MANDATORY", prompt)
        self.assertIn("every limited-edition badge, plaque, collector badge, numbered detail and edition plate", prompt)
        self.assertIn("Card 1 must use its resolved sport-nostalgic wall tone", prompt)
        self.assertIn("Generic room variety, sporting atmosphere, campaign context", prompt)
        self.assertNotIn("magnifying glass detail shot", sections[1])
        for index in (2, 3, 4):
            self.assertNotIn("Required nostalgic wall tone:", sections[index])
            self.assertNotIn("magnifying glass", sections[index])
        self.assertEqual([slot["id"] for slot in ads_page.ads_image_workflow.campaign_image_slots("Carousel")],
                         [f"carousel-{index:02d}" for index in range(1, 6)])

    def test_unaffected_prompts_match_captured_prechange_bytes(self):
        rows = json.loads((Path(__file__).parent / "fixtures" / "carousel_detail_prompt_baseline.json").read_text())
        for row in rows:
            with self.subTest(category=row["category"], kind=row["kind"]):
                kind = row["kind"]
                kwargs = dict(product_name="Collector Prompt Regression", category=row["category"], country=row["country"],
                              product_url="https://www.sportscaveshop.com/products/collector", variation_token="fixed-prompt-regression")
                if kind.startswith("refresh_"):
                    prompt = ads_page.build_ads_prompt(**kwargs, campaign_type=kind.removeprefix("refresh_"),
                                                      creative_refresh_context={"winning_primary_text": "Proven collector copy", "winning_headline": "Proven headline"})
                elif kind.startswith("card_"):
                    prompt = carousel_prompt_card_sections(visual_contract(ads_page.build_ads_prompt(**kwargs, campaign_type="Carousel")))[int(kind[-1])]
                else:
                    prompt = ads_page.build_ads_prompt(**kwargs, campaign_type=kind)
                self.assertEqual(hashlib.sha256(prompt.encode()).hexdigest(), row["sha256"])

    def test_existing_new_ads_prompt_refreshes_without_changing_completed_copy_or_context(self):
        result = ads_page.build_ads_result_record("Collector Test", "Cricket", "Australia", "Carousel",
                                                product_url="https://www.sportscaveshop.com/products/collector", variation_token="stable")
        old = {**result, "prompt_contract_version": ads_page.ADS_PROMPT_CONTRACT_VERSION,
               "master_prompt": "previous prompt", "generated_ad_output": "Previously completed copy"}
        refreshed = ads_page.ensure_current_ads_result_prompt(old)
        self.assertEqual(refreshed["context_key"], result["context_key"])
        self.assertEqual(refreshed["generated_ad_output"], "Previously completed copy")
        self.assertIn(ads_page.ADS_CAROUSEL_DETAIL_CONTRACT_VERSION, refreshed["master_prompt"])
        self.assertIn("magnifying glass", refreshed["master_prompt"])
        self.assertIs(ads_page.ensure_current_ads_result_prompt(refreshed), refreshed)
        for campaign, mode in (("Instant Experience", "new"), ("Carousel", "creative_refresh"), ("Instant Experience", "creative_refresh")):
            self.assertNotIn(ads_page.ADS_CAROUSEL_DETAIL_CONTRACT_VERSION,
                             ads_page.ads_prompt_contract_version_for_campaign(campaign, workflow_mode=mode))

    def test_cards_two_to_four_preserve_existing_prompts_across_all_categories_and_markets(self):
        winner = {"winning_primary_text": "Existing winner", "winning_headline": "Existing headline"}
        for category in ads_page.CATEGORY_OPTIONS[1:]:
            for country in ads_page.COUNTRY_OPTIONS[1:]:
                current = carousel_prompt_card_sections(visual_contract(final_prompt(category, country)))
                unchanged = carousel_prompt_card_sections(visual_contract(final_prompt(category, country, creative_refresh_context=winner)))
                for index in (2, 3, 4):
                    with self.subTest(category=category, country=country, card=index):
                        self.assertEqual(current[index], unchanged[index])

    def test_visual_contract_upgrade_replaces_old_version_once(self):
        kwargs = dict(product_name="Collector Detail Test", category="Cricket", country="Australia", campaign_type="Carousel")
        legacy = ads_page.build_campaign_visual_output_contract(**kwargs, workflow_mode="creative_refresh")
        upgraded = ads_page.apply_campaign_visual_output_contract(legacy, **kwargs)
        self.assertIn(ads_page.ADS_CAROUSEL_DETAIL_CONTRACT_VERSION, upgraded)
        self.assertIn("magnifying glass detail shot", upgraded)
        self.assertEqual(upgraded.count("MASTER RESPONSE AND VISUAL OUTPUT CONTRACT"), 1)
        self.assertIs(ads_page.apply_campaign_visual_output_contract(upgraded, **kwargs), upgraded)


if __name__ == "__main__":
    unittest.main()
