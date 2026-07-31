import unittest
from datetime import date
from urllib.parse import parse_qs, urlsplit

import social_media_creator as creator


def base_payload(**overrides):
    payload = {
        "scheduled_date": date(2026, 7, 31),
        "content_focus": "Product",
        "product_id": "gid://shopify/Product/123",
        "product_title": "Brock Legends Collector's Edition",
        "product_handle": "brock-legends-collector-s-edition",
        "product_url": "https://sportscaveshop.com/products/brock-legends",
        "market": "Australia",
        "sport": "Motorsport",
        "format": "Feed carousel",
        "series": "THE MOMENT",
        "platforms": ["All suitable platforms"],
        "production_method": "",
        "objective": "Reach",
        "funnel_stage": "Cold",
        "hook": "When racing was raw.",
        "cta": "See the complete edition.",
        "rights_status": "Approved original product photography",
    }
    payload.update(overrides)
    return payload


class SocialPromptContractTests(unittest.TestCase):
    def test_carousel_has_complete_standalone_prompts_for_every_slide(self):
        package = creator.build_content_package(base_payload())

        self.assertEqual(len(package["visual_prompts"]), 6)
        for prompt in package["visual_prompts"]:
            text = prompt["prompt"]
            self.assertIn("PRODUCT AND ARTWORK LOCK - MANDATORY", text)
            self.assertIn("PHOTOREALISM AND HUMAN REALISM - MANDATORY", text)
            self.assertIn("Create exactly one 4:5 image at 1080 x 1350", text)
            self.assertIn("exact black frame colour", text)
            self.assertIn("Never invent or change an edition number", text)
            self.assertIn("FINAL QUALITY CHECK", text)
        self.assertIn(
            "do not combine a shared prompt with fragments",
            package["production_plan"].casefold(),
        )

    def test_story_frames_are_complete_and_use_native_stickers(self):
        package = creator.build_content_package(
            base_payload(
                format="Story sequence",
                platforms=["Instagram"],
                series="CAVE DEBATE",
                objective="Engagement",
            )
        )

        self.assertEqual(len(package["visual_prompts"]), 5)
        for prompt in package["visual_prompts"]:
            self.assertIn("Create exactly one 9:16 image at 1080 x 1920", prompt["prompt"])
            self.assertIn("PRODUCT AND ARTWORK LOCK - MANDATORY", prompt["prompt"])
        self.assertIn("Add polls, quizzes, sliders", package["production_plan"])
        self.assertIn("Never render fake platform stickers", package["production_plan"])

    def test_launch_story_uses_the_longer_exception(self):
        package = creator.build_content_package(
            base_payload(
                content_focus="Launch/event",
                event="Bathurst launch",
                format="Launch sequence",
                series="NEW DROP",
                platforms=["Instagram", "Facebook"],
            )
        )

        self.assertGreaterEqual(len(package["visual_prompts"]), 6)
        self.assertLessEqual(len(package["visual_prompts"]), 10)

    def test_reel_includes_timing_cover_export_and_ai_reels_handoff(self):
        package = creator.build_content_package(
            base_payload(
                format="Reel",
                production_method="AI Reels Studio",
                platforms=["All suitable platforms"],
            )
        )

        plan = package["production_plan"]
        self.assertIn("0-2 seconds - Hook", plan)
        self.assertIn("6-11 seconds - Product reveal", plan)
        self.assertIn("Cover: 1080 x 1920", plan)
        self.assertIn("Export: 1080 x 1920", plan)
        self.assertIn(
            "Create the stills in ChatGPT, then open AI Reels Studio in Sports Cave OS.",
            plan,
        )
        self.assertEqual(len(package["visual_prompts"]), 3)
        self.assertEqual(len(package["video_prompts"]), 3)

    def test_every_image_prompt_has_the_complete_product_and_realism_contract(self):
        for content_format in (
            "Static feed post",
            "Pinterest Pin",
            "UGC/collector proof",
            "Feed carousel",
            "Story sequence",
            "Reel",
        ):
            with self.subTest(content_format=content_format):
                package = creator.build_content_package(
                    base_payload(
                        format=content_format,
                        production_method=(
                            "Film and edit manually"
                            if content_format == "Reel"
                            else ""
                        ),
                        platforms=["All suitable platforms"],
                    )
                )
                for prompt in package["visual_prompts"]:
                    self.assertIn("PRODUCT AND ARTWORK LOCK - MANDATORY", prompt["prompt"])
                    self.assertIn("PHOTOREALISM AND HUMAN REALISM - MANDATORY", prompt["prompt"])
                    self.assertIn("Faces must remain natural", prompt["prompt"])
                    self.assertIn("Generated-image text rule".upper(), prompt["prompt"].upper())

    def test_missing_claims_use_verification_markers_and_are_not_invented(self):
        package = creator.build_content_package(base_payload(rights_status=""))

        self.assertEqual(
            package["warnings"],
            [
                "[VERIFY LIVE EDITION COUNT]",
                "[VERIFY PRICE]",
                "[VERIFY OFFER END DATE]",
                "[VERIFY DELIVERY CLAIM]",
                "[VERIFY USAGE RIGHTS]",
            ],
        )
        self.assertIn("Never fabricate a price", package["creative_prompt"])

    def test_global_prompt_excludes_supplied_market_price_and_fulfilment_claim(self):
        package = creator.build_content_package(
            base_payload(
                market="Global",
                price="AUD $199",
                shipping_claim="Made and shipped in Australia",
            )
        )

        self.assertNotIn("AUD $199", package["creative_prompt"])
        self.assertNotIn("Made and shipped in Australia", package["creative_prompt"])
        self.assertIn("Do not show a country-specific price, flag", package["creative_prompt"])

    def test_uk_and_us_football_language_are_distinct(self):
        uk = creator.build_content_package(
            base_payload(market="United Kingdom", sport="Football")
        )
        usa = creator.build_content_package(
            base_payload(market="United States", sport="Football")
        )

        self.assertIn("Use football, match and supporter", uk["creative_prompt"])
        self.assertIn("Use soccer for association football", usa["creative_prompt"])

    def test_platform_adaptations_and_utms_are_platform_specific(self):
        package = creator.build_content_package(base_payload())

        instagram = package["platform_adaptations"]["Instagram"]
        facebook = package["platform_adaptations"]["Facebook"]
        self.assertNotEqual(instagram["guidance"], facebook["guidance"])
        instagram_query = parse_qs(urlsplit(instagram["tracked_url"]).query)
        facebook_query = parse_qs(urlsplit(facebook["tracked_url"]).query)
        self.assertEqual(instagram_query["utm_source"], ["instagram"])
        self.assertEqual(facebook_query["utm_source"], ["facebook"])
        self.assertEqual(instagram_query["utm_medium"], ["organic_social"])
        self.assertEqual(
            instagram_query["utm_campaign"],
            ["the-moment_brock-legends-collector-s-edit_australia_202607"],
        )

    def test_input_or_contract_change_invalidates_signature(self):
        first = creator.input_signature(base_payload())
        changed_product = creator.input_signature(
            base_payload(product_title="A Different Protected Product")
        )
        changed_format = creator.input_signature(base_payload(format="Static feed post"))

        self.assertNotEqual(first, changed_product)
        self.assertNotEqual(first, changed_format)
        self.assertEqual(
            creator.build_content_package(base_payload())["contract_version"],
            creator.SOCIAL_PROMPT_CONTRACT_VERSION,
        )

    def test_community_post_does_not_require_a_product(self):
        package = creator.build_content_package(
            base_payload(
                content_focus="Community/fan conversation",
                product_id="",
                product_title="",
                product_handle="",
                product_url="",
                format="Story sequence",
                series="CAVE DEBATE",
                hook="Which rivalry still divides the fanbase?",
                objective="Engagement",
            )
        )

        self.assertEqual(package["input"]["product_title"], "")
        self.assertIn("Which rivalry still divides", package["creative_prompt"])


class SocialOutputContractTests(unittest.TestCase):
    def test_folder_and_assets_are_short_windows_safe_and_traversal_safe(self):
        payload = base_payload(
            product_title=(
                "A Very Long Collector's Product Name With International Punctuation "
                "And More Words Than A Windows Filename Needs"
            ),
            product_handle="../../CON:AUX?Very Long Product Handle",
            series="BUILT FOR FANS WHO KNOW",
            market="United Kingdom",
        )
        relative = creator.output_relative_folder(payload)
        filename = creator.asset_filename(
            payload,
            index=2,
            extension=".PNG",
            platform="master",
        )

        self.assertTrue(relative.startswith("04_OUTPUT/social-media/2026-07-31__"))
        self.assertLess(len(relative), 150)
        self.assertNotIn("..", relative)
        self.assertNotIn(":", relative)
        self.assertRegex(filename, r"^[a-z0-9-]+__[a-z0-9-]+__master__02\.png$")
        self.assertEqual(creator.validate_relative_output_path(relative), relative)
        with self.assertRaises(creator.SocialCreatorValidationError):
            creator.validate_relative_output_path("../outside")

    def test_text_exports_use_crlf_and_preserve_unicode_copy(self):
        package = creator.build_content_package(
            base_payload(
                hook="When racing was raw.\nCollectors remember Brock's final charge — always.",
            )
        )
        brief = creator.build_brief_text(package)
        copy = creator.build_social_copy_text(package)

        self.assertIn("\r\n", brief)
        self.assertNotIn("\n", brief.replace("\r\n", ""))
        self.assertIn("Brock's", copy)
        self.assertIn("—", copy)
        self.assertIn("[not supplied]", brief)

    def test_strategy_assignment_is_not_saved_or_product_invented(self):
        assignment = creator.strategy_assignment_for_date(date(2026, 7, 31))

        self.assertEqual(assignment["day"], "Friday")
        self.assertEqual(assignment["series"], "ONLY 100")
        self.assertEqual(assignment["product_title"], "")
        self.assertEqual(assignment["status"], "Strategy recommendation")

    def test_approved_assignment_prefill_preserves_advanced_brief_fields(self):
        prefill = creator.prefill_from_assignment(
            {
                "product_title": "Brock Legends Collector's Edition",
                "offer": "Verified free shipping",
                "restrictions": "Do not publish before 6 pm.",
                "rights_status": "Approved original product photography",
            }
        )

        self.assertEqual(prefill["offer"], "Verified free shipping")
        self.assertEqual(
            prefill["restrictions"],
            "Do not publish before 6 pm.",
        )
        self.assertEqual(
            prefill["rights_status"],
            "Approved original product photography",
        )


if __name__ == "__main__":
    unittest.main()
