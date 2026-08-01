import unittest
from datetime import date
from unittest import mock
from urllib.parse import parse_qs, urlsplit

import social_media_creator as creator
from sports_cave_prompt_blocks import SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER


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
    }
    payload.update(overrides)
    return payload


class SocialPromptContractTests(unittest.TestCase):
    def test_scene_variable_option_lists_are_complete(self):
        self.assertEqual(
            creator.ROOM_TYPE_OPTIONS,
            (
                "Auto — vary appropriately",
                "Man Cave",
                "Premium Living Room",
                "Lounge",
                "Apartment Living Room",
                "Bedroom",
                "Home Office",
                "Executive Office",
                "Study / Library",
                "Garage",
                "Premium Workshop",
                "Home Bar",
                "Sports Bar",
                "Games Room",
                "Pool Table Room",
                "Media Room / Home Cinema",
                "Listening / Music Room",
                "Hallway",
                "Entryway / Foyer",
                "Staircase / Landing",
                "Dining Room",
                "Collector Gallery",
                "Trophy Room",
                "Club Lounge",
                "Home Gym",
                "Loft",
                "Basement Retreat",
                "No Room — Clean Studio Product Shot",
                "Custom",
            ),
        )
        self.assertEqual(
            creator.WALL_COLOUR_OPTIONS,
            (
                "Auto — choose from approved palette",
                "Sports Cave Black",
                "Deep Charcoal",
                "Graphite",
                "Warm Off-White",
                "Soft Greige",
                "Stone Beige",
                "Sandstone",
                "Concrete Grey",
                "Warm Taupe",
                "Dark Walnut",
                "Deep Navy",
                "Forest Green",
                "Muted Olive",
                "Warm Clay",
                "Natural Brick Red",
                "Whitewashed Brick",
                "Custom",
            ),
        )
        self.assertEqual(
            creator.WALL_MATERIAL_FINISH_OPTIONS,
            (
                "Auto — match the selected room",
                "Smooth Painted Plaster",
                "Fine Textured Plaster",
                "Venetian Plaster",
                "Painted Masonry",
                "Exposed Red Brick",
                "Charcoal Brick",
                "Whitewashed Brick",
                "Sandstone Block",
                "Natural Limestone",
                "Stone Cladding",
                "Raw Concrete",
                "Polished Concrete",
                "Board-Formed Concrete",
                "Dark Oak Wall Panels",
                "Light Oak Wall Panels",
                "Timber Slat Wall",
                "Acoustic Timber Panels",
                "Smooth Ceramic Tile",
                "Matte Tile",
                "Stone Tile",
                "Subway Tile",
                "Custom",
            ),
        )
        self.assertEqual(
            creator.CAMERA_ANGLE_OPTIONS,
            (
                "Auto — choose the strongest product-led angle",
                "Straight-On Eye Level",
                "Centred Symmetrical",
                "Slight Left Three-Quarter — 15–25 Degrees",
                "Slight Right Three-Quarter — 15–25 Degrees",
                "Left Three-Quarter — 25–35 Degrees",
                "Right Three-Quarter — 25–35 Degrees",
                "Slight Low-Angle Hero",
                "Slight Elevated View",
                "Corner-of-Room View",
                "Doorway / Entry Reveal",
                "Over-Furniture Lifestyle View",
                "Close Side-Depth Detail",
                "Custom",
            ),
        )
        self.assertEqual(
            creator.SHOT_DISTANCE_PROMINENCE_OPTIONS,
            (
                "Close Product Hero — approximately 65–80% prominence",
                "Medium-Close — approximately 55–70% prominence",
                "Medium Lifestyle — approximately 45–60% prominence",
                "Collector Detail — approximately 60–80% prominence",
                "Auto — keep the product dominant",
            ),
        )
        self.assertEqual(
            creator.LIGHTING_STYLE_OPTIONS,
            (
                "Auto — match the room naturally",
                "Soft Natural Daylight",
                "Bright Diffused Daylight",
                "Soft Overcast Daylight",
                "Warm Late-Afternoon Light",
                "Golden-Hour Light",
                "Moody Evening Lamplight",
                "Controlled Gallery Lighting",
                "Mixed Natural Light and Warm Lamps",
                "Custom",
            ),
        )
        self.assertEqual(
            creator.VARIATION_BEHAVIOUR_OPTIONS,
            (
                "Use Exact Selections",
                "Vary Camera Angle Only",
                "Vary Room and Wall",
                "Vary Lighting",
                "Vary All Approved Scene Variables",
            ),
        )

    def test_carousel_has_complete_standalone_prompts_for_every_slide(self):
        package = creator.build_content_package(base_payload())

        self.assertEqual(len(package["visual_prompts"]), 6)
        for prompt in package["visual_prompts"]:
            text = prompt["prompt"]
            self.assertEqual(text.count(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER), 1)
            self.assertIn("PRODUCT AND ARTWORK LOCK - MANDATORY", text)
            self.assertIn("SPORTS CAVE PRODUCT AND MOCKUP LOCK - MANDATORY", text)
            self.assertIn("PHOTOREALISM AND HUMAN REALISM - MANDATORY", text)
            self.assertIn("GLOBAL PHOTOGRAPHIC REALISM RULES - MANDATORY", text)
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
        self.assertIn("Add real polls, quizzes, sliders", package["production_plan"])
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
        self.assertEqual(len(package["visual_prompts"]), 4)
        self.assertEqual(len(package["video_prompts"]), 4)
        self.assertIn("premium product-led end card", plan)

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
                    self.assertEqual(
                        prompt["prompt"].count(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER),
                        1,
                    )
                    self.assertIn("PRODUCT AND ARTWORK LOCK - MANDATORY", prompt["prompt"])
                    self.assertIn("SPORTS CAVE PRODUCT AND MOCKUP LOCK - MANDATORY", prompt["prompt"])
                    self.assertIn("PHOTOREALISM AND HUMAN REALISM - MANDATORY", prompt["prompt"])
                    self.assertIn("Faces must remain natural", prompt["prompt"])
                    self.assertIn("STAGE 1 - CLEAN VISUAL GENERATION", prompt["prompt"])
                    self.assertIn(
                        "SPORTS CAVE BRANDING AND OVERLAY PLAN",
                        prompt["prompt"],
                    )
                    self.assertIn(
                        "Composite this exact verified file at export time",
                        prompt["prompt"],
                    )

    def test_claim_safety_is_system_level_without_legacy_markers(self):
        package = creator.build_content_package(base_payload())

        self.assertEqual(package["warnings"], [])
        self.assertNotIn("[VERIFY", package["creative_prompt"])
        self.assertTrue(package["publish_ready"])
        self.assertIn("Never fabricate a price", package["creative_prompt"])
        self.assertIn("if rights are uncertain", package["creative_prompt"])

    def test_v5_brand_contract_is_complete_for_every_public_format(self):
        self.assertEqual(
            creator.SOCIAL_PROMPT_CONTRACT_VERSION,
            "SOCIAL CONTENT PROMPT V5",
        )
        for content_format in (
            "Static feed post",
            "Feed carousel",
            "Story sequence",
            "Launch sequence",
            "Reel",
            "Pinterest Pin",
            "UGC/collector proof",
        ):
            with self.subTest(content_format=content_format):
                package = creator.build_content_package(
                    base_payload(
                        format=content_format,
                        production_method=(
                            "AI Reels Studio" if content_format == "Reel" else ""
                        ),
                    )
                )
                self.assertEqual(
                    len(package["export_branding_plans"]),
                    len(package["visual_prompts"]),
                )
                self.assertEqual(
                    package["branding_manifest"]["logo_asset"],
                    "assets/sports-cave-logo-landscape-gold-transparent.webp",
                )
                for prompt in package["visual_prompts"]:
                    plan = prompt["branding_plan"]
                    self.assertTrue(plan["clean_master"]["required"])
                    self.assertFalse(plan["clean_master"]["generated_overlays"])
                    self.assertTrue(
                        plan["branded_final"]["deterministic_compositing"]
                    )
                    self.assertIn(
                        package["branding_manifest"]["logo_sha256"],
                        prompt["prompt"],
                    )
                    self.assertIn("Safe zone:", prompt["prompt"])
                    self.assertIn(
                        "Never ask an image or video model to recreate the logo",
                        prompt["prompt"],
                    )
                if content_format == "UGC/collector proof":
                    self.assertIn(
                        "Restrained UGC treatment",
                        package["visual_prompts"][0]["prompt"],
                    )

    def test_social_image_prompts_have_shared_marker_without_ads_instructions(self):
        ads_only_terms = (
            "CAROUSEL CARD CHARACTER LIMIT",
            "MASTER RESPONSE AND VISUAL OUTPUT CONTRACT",
            "INSTANT EXPERIENCE SETUP",
            "META URL PARAMETERS",
            "Would you like me to generate Card 1?",
        )
        for content_format in (
            "Story sequence",
            "Reel",
            "Feed carousel",
            "Static feed post",
            "Pinterest Pin",
            "UGC/collector proof",
        ):
            with self.subTest(content_format=content_format):
                package = creator.build_content_package(
                    base_payload(
                        format=content_format,
                        production_method=(
                            "AI Reels Studio" if content_format == "Reel" else ""
                        ),
                        platforms=["All suitable platforms"],
                    )
                )
                for prompt in package["visual_prompts"]:
                    self.assertEqual(
                        prompt["prompt"].count(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER),
                        1,
                    )
                    for ads_term in ads_only_terms:
                        self.assertNotIn(ads_term, prompt["prompt"])

    def test_selected_scene_values_appear_once_before_realism_rules(self):
        package = creator.build_content_package(
            base_payload(
                format="Static feed post",
                room_type="Man Cave",
                wall_colour="Deep Charcoal",
                wall_material_finish="Dark Oak Wall Panels",
                camera_angle="Straight-On Eye Level",
                shot_distance_product_prominence=(
                    "Close Product Hero — approximately 65–80% prominence"
                ),
                lighting_style="Controlled Gallery Lighting",
                variation_behaviour="Use Exact Selections",
            )
        )
        prompt = package["visual_prompts"][0]["prompt"]

        self.assertEqual(prompt.count(creator.SOCIAL_SCENE_VARIABLES_MARKER), 1)
        self.assertLess(
            prompt.index(creator.SOCIAL_SCENE_VARIABLES_MARKER),
            prompt.index(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER),
        )
        for line in (
            "Product featured: Brock Legends Collector's Edition",
            "Room type: Man Cave",
            "Wall colour: Deep Charcoal",
            "Wall material/finish: Dark Oak Wall Panels",
            "Camera angle: Straight-On Eye Level",
            "Shot distance/product prominence: Close Product Hero — approximately 65–80% prominence",
            "Lighting style: Controlled Gallery Lighting",
            "Variation behaviour: Use Exact Selections",
        ):
            self.assertIn(line, prompt)
        self.assertIn("PRODUCT AND ARTWORK LOCK - MANDATORY", prompt)

    def test_every_product_social_image_format_receives_scene_variables(self):
        for content_format in (
            "Story sequence",
            "Reel",
            "Feed carousel",
            "Static feed post",
            "Pinterest Pin",
            "UGC/collector proof",
        ):
            with self.subTest(content_format=content_format):
                package = creator.build_content_package(
                    base_payload(
                        format=content_format,
                        production_method=(
                            "AI Reels Studio" if content_format == "Reel" else ""
                        ),
                    )
                )
                for prompt in package["visual_prompts"]:
                    self.assertEqual(
                        prompt["prompt"].count(creator.SOCIAL_SCENE_VARIABLES_MARKER),
                        1,
                    )
                    self.assertIn(
                        "Product featured: Brock Legends Collector's Edition",
                        prompt["prompt"],
                    )

    def test_carousel_and_reel_variation_keeps_product_lock_authoritative(self):
        for content_format in ("Feed carousel", "Reel"):
            with self.subTest(content_format=content_format):
                package = creator.build_content_package(
                    base_payload(
                        format=content_format,
                        production_method=(
                            "AI Reels Studio" if content_format == "Reel" else ""
                        ),
                        room_type="Auto — vary appropriately",
                        wall_colour="Auto — choose from approved palette",
                        wall_material_finish="Auto — match the selected room",
                        camera_angle="Auto — choose the strongest product-led angle",
                        lighting_style="Auto — match the room naturally",
                        variation_behaviour="Vary All Approved Scene Variables",
                    )
                )
                self.assertGreater(len(package["visual_prompts"]), 1)
                for prompt in package["visual_prompts"]:
                    text = prompt["prompt"]
                    self.assertEqual(
                        text.count(creator.SOCIAL_SCENE_VARIABLES_MARKER),
                        1,
                    )
                    self.assertIn("Approved room types:", text)
                    self.assertIn("Approved camera angles:", text)
                    self.assertIn(
                        "Variation must never override product lock",
                        text,
                    )
                    self.assertIn("PRODUCT AND ARTWORK LOCK - MANDATORY", text)
                    self.assertIn("SPORTS CAVE PRODUCT AND MOCKUP LOCK", text)

    def test_caption_only_outputs_do_not_receive_scene_variables(self):
        package = creator.build_content_package(base_payload())

        for caption in package["caption_variations"]:
            self.assertNotIn(creator.SOCIAL_SCENE_VARIABLES_MARKER, caption)
        self.assertNotIn(
            creator.SOCIAL_SCENE_VARIABLES_MARKER,
            creator.build_social_copy_text(package),
        )

    def test_no_room_clean_studio_mode_sets_wall_values_not_applicable(self):
        package = creator.build_content_package(
            base_payload(
                format="Pinterest Pin",
                room_type=creator.NO_ROOM_STUDIO_OPTION,
                wall_colour="Custom",
                wall_material_finish="Custom",
                camera_angle="Centred Symmetrical",
                lighting_style="Bright Diffused Daylight",
            )
        )
        prompt = package["visual_prompts"][0]["prompt"]

        self.assertIn(
            f"Room type: {creator.NO_ROOM_STUDIO_OPTION}",
            prompt,
        )
        self.assertIn("Wall colour: Not applicable", prompt)
        self.assertIn("Wall material/finish: Not applicable", prompt)
        self.assertIn("Do not invent a room", prompt)
        self.assertIn("approved clean studio product background", prompt)

    def test_non_product_social_visuals_do_not_get_room_instructions(self):
        package = creator.build_content_package(
            base_payload(
                content_focus="Community/fan conversation",
                product_id="",
                product_title="",
                product_handle="",
                product_url="",
                collection="",
                format="Story sequence",
                series="CAVE DEBATE",
                hook="Which rivalry still divides the fanbase?",
                objective="Engagement",
            )
        )

        for prompt in package["visual_prompts"]:
            self.assertNotIn(creator.SOCIAL_SCENE_VARIABLES_MARKER, prompt["prompt"])

    def test_story_branding_is_consistent_and_cta_is_final_only(self):
        package = creator.build_content_package(
            base_payload(
                product_title="The Rivals: Brock vs Moffat Wall Art",
                format="Story sequence",
                series="CAVE DEBATE",
                objective="Engagement",
                cta="See the edition.",
                platforms=["Instagram"],
            )
        )
        plans = [item["branding_plan"] for item in package["visual_prompts"]]

        self.assertEqual(len(plans), 5)
        self.assertEqual({item["logo"]["placement"] for item in plans}, {"top-left"})
        self.assertEqual({item["logo"]["asset"] for item in plans}, {
            "assets/sports-cave-logo-landscape-gold-transparent.webp"
        })
        self.assertEqual(plans[0]["copy"]["headline"], "WHEN RACING WAS RAW.")
        self.assertEqual(plans[0]["copy"]["subline"], "THE RIVALS")
        self.assertEqual(plans[1]["copy"]["headline"], "BROCK OR MOFFAT?")
        self.assertIn("poll", plans[1]["placement"]["native_sticker_space"].casefold())
        self.assertEqual(
            plans[2]["copy"]["headline"],
            "TWO ICONS. ONE RIVALRY.",
        )
        self.assertTrue(all(not plan["copy"]["cta"] for plan in plans[:-1]))
        self.assertEqual(plans[-1]["copy"]["cta"], "SEE THE EDITION.")
        self.assertIn(
            "link sticker",
            plans[-1]["placement"]["native_sticker_space"].casefold(),
        )

    def test_unverified_edition_claim_blocks_only_the_branded_final(self):
        package = creator.build_content_package(
            base_payload(
                format="Story sequence",
                series="ONLY 100",
                cta="Only 100 Made",
            )
        )

        self.assertEqual(package["warnings"], ["[VERIFY EDITION LIMIT]"])
        self.assertFalse(package["publish_ready"])
        self.assertEqual(package["cta"], "[VERIFY EDITION LIMIT]")
        self.assertTrue(
            all(item["branding_plan"]["clean_master"]["required"]
                for item in package["visual_prompts"])
        )
        self.assertFalse(
            package["visual_prompts"][-1]["branding_plan"]["branded_final"][
                "publish_ready"
            ]
        )

        verified = creator.build_content_package(
            base_payload(
                format="Story sequence",
                series="ONLY 100",
                cta="Only 100 Made",
                edition_limit=100,
                edition_limit_verified=True,
                edition_limit_source="Edition Ops product ledger",
            )
        )
        self.assertEqual(verified["warnings"], [])
        self.assertTrue(verified["publish_ready"])
        self.assertEqual(verified["cta"], "Only 100 Made")
        self.assertIn(
            "ONLY 100 MADE",
            verified["visual_prompts"][-1]["branding_plan"]["copy"]["cta"],
        )

    def test_string_false_cannot_verify_an_edition_claim(self):
        package = creator.build_content_package(
            base_payload(
                series="ONLY 100",
                cta="Only 100 Made",
                edition_limit=100,
                edition_limit_verified="false",
            )
        )

        self.assertFalse(package["input"]["edition_limit_verified"])
        self.assertFalse(package["publish_ready"])

    def test_global_prompt_ignores_legacy_price_and_fulfilment_values(self):
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

    def test_all_formats_ignore_removed_legacy_fields(self):
        legacy_values = {
            "audience": "LEGACY AUDIENCE SENTINEL",
            "proof_asset": "LEGACY PROOF SENTINEL",
            "edition_count": "LEGACY COUNT SENTINEL",
            "price": "LEGACY PRICE SENTINEL",
            "shipping_claim": "LEGACY SHIPPING SENTINEL",
            "restrictions": "LEGACY RESTRICTIONS SENTINEL",
            "rights_status": "LEGACY RIGHTS SENTINEL",
            "additional_notes": "LEGACY NOTES SENTINEL",
        }
        formats = (
            "Static feed post",
            "Feed carousel",
            "Story sequence",
            "Reel",
            "Pinterest Pin",
            "UGC/collector proof",
            "Launch sequence",
        )

        for content_format in formats:
            with self.subTest(content_format=content_format):
                package = creator.build_content_package(
                    base_payload(
                        **legacy_values,
                        format=content_format,
                        production_method=(
                            "AI Reels Studio" if content_format == "Reel" else ""
                        ),
                    )
                )
                exported = "\n".join(
                    (
                        package["creative_prompt"],
                        creator.build_brief_text(package),
                        creator.build_social_copy_text(package),
                    )
                )
                for field, sentinel in legacy_values.items():
                    self.assertNotIn(field, package["input"])
                    self.assertNotIn(sentinel, exported)
                for retired_contract_fragment in (
                    '"audience":',
                    '"proof_asset":',
                    '"verified_edition_count":',
                    '"verified_price":',
                    '"verified_shipping_claim":',
                    '"restrictions":',
                    '"rights_status":',
                    '"additional_notes":',
                    "Proof element:",
                    "VERIFICATION WARNINGS",
                    "[VERIFY",
                ):
                    self.assertNotIn(retired_contract_fragment, exported)
                self.assertIn(
                    "PRODUCT AND ARTWORK LOCK - MANDATORY",
                    package["creative_prompt"],
                )
                self.assertIn(
                    "ACCURACY, RIGHTS AND CLAIMS - MANDATORY",
                    package["creative_prompt"],
                )

    def test_hook_and_cta_options_are_complete_and_strategy_ranked(self):
        self.assertEqual(
            set(creator.HOOK_OPTIONS),
            {
                "Nostalgia / Sporting Memory",
                "Fan Identity",
                "Iconic Moment",
                "Rivalry / Debate",
                "Product Desire",
                "Wall Transformation",
                "Collector Proof",
                "Craftsmanship / Quality",
                "Behind the Edition",
                "Limited to 100 / Scarcity",
                "Retired Forever",
                "Gifting / Fan Reaction",
                "New Drop / Teaser",
                "Community Vote",
                "Room Inspiration",
                "Size / Product Education",
            },
        )
        self.assertEqual(len(creator.CTA_OPTIONS), 15)
        self.assertEqual(
            creator.recommended_hook_options(
                objective="Reach",
                funnel_stage="Cold",
                series="THE MOMENT",
                content_format="Reel",
            )[:4],
            (
                "Nostalgia / Sporting Memory",
                "Iconic Moment",
                "Fan Identity",
                "Rivalry / Debate",
            ),
        )
        self.assertEqual(
            creator.recommended_hook_options(
                objective="Trust",
                funnel_stage="Warm",
                series="REAL COLLECTORS",
                content_format="UGC/collector proof",
            )[0],
            "Collector Proof",
        )
        self.assertEqual(
            creator.recommended_cta_options(
                objective="Engagement",
                funnel_stage="Warm",
                series="CAVE DEBATE",
            )[:2],
            ("Comment your side.", "Vote for your favourite."),
        )
        self.assertEqual(
            creator.recommended_cta_options(
                objective="Reach",
                funnel_stage="Cold",
                series="GIFTED GREATNESS",
            )[0],
            "Send this to a gift buyer.",
        )

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
        changed_hook = creator.input_signature(base_payload(hook="Fan Identity"))
        changed_cta = creator.input_signature(base_payload(cta="See the edition."))
        changed_offer = creator.input_signature(base_payload(offer="Free shipping"))
        changed_offer_date = creator.input_signature(
            base_payload(offer_end_date="2026-08-31")
        )
        changed_room = creator.input_signature(base_payload(room_type="Man Cave"))
        changed_wall = creator.input_signature(base_payload(wall_colour="Deep Navy"))
        changed_camera = creator.input_signature(
            base_payload(camera_angle="Straight-On Eye Level")
        )
        changed_lighting = creator.input_signature(
            base_payload(lighting_style="Controlled Gallery Lighting")
        )

        self.assertNotEqual(first, changed_product)
        self.assertNotEqual(first, changed_format)
        self.assertNotEqual(first, changed_hook)
        self.assertNotEqual(first, changed_cta)
        self.assertNotEqual(first, changed_offer)
        self.assertNotEqual(first, changed_offer_date)
        self.assertNotEqual(first, changed_room)
        self.assertNotEqual(first, changed_wall)
        self.assertNotEqual(first, changed_camera)
        self.assertNotEqual(first, changed_lighting)
        self.assertEqual(
            creator.build_content_package(base_payload())["contract_version"],
            creator.SOCIAL_PROMPT_CONTRACT_VERSION,
        )

    def test_v4_cached_prompt_signature_is_invalidated(self):
        with mock.patch.object(
            creator,
            "SOCIAL_PROMPT_CONTRACT_VERSION",
            "SOCIAL CONTENT PROMPT V4",
        ):
            v4_signature = creator.input_signature(base_payload())

        self.assertNotEqual(v4_signature, creator.input_signature(base_payload()))

    def test_custom_hook_and_exactly_one_custom_cta_are_preserved(self):
        hook = "The night the Mountain fell silent"
        cta = "Open the full collector story."
        package = creator.build_content_package(
            base_payload(hook=hook, cta=cta)
        )

        self.assertEqual(package["input"]["hook"], hook)
        self.assertEqual(package["cta"], cta)
        self.assertEqual(package["on_screen_text"][-1], cta)
        self.assertIn(hook, package["creative_prompt"])
        self.assertIn(cta, package["creative_prompt"])
        for suggested_cta in creator.CTA_OPTIONS:
            self.assertNotIn(suggested_cta, package["creative_prompt"])

    def test_offer_context_is_fully_optional_and_never_invented(self):
        blank = creator.build_content_package(base_payload())
        self.assertEqual(blank["offer_context"], {})
        self.assertNotIn("optional_offer_context", blank["creative_prompt"])
        self.assertNotIn(
            "OPTIONAL OFFER CONTEXT",
            creator.build_social_copy_text(blank),
        )

        offer_only = creator.build_content_package(
            base_payload(offer="Free shipping on the selected edition")
        )
        self.assertIn(
            "Free shipping on the selected edition",
            offer_only["creative_prompt"],
        )
        self.assertNotIn("offer_end_date", offer_only["creative_prompt"])
        self.assertIn(
            "Do not invent an end date",
            offer_only["creative_prompt"],
        )

        date_only = creator.build_content_package(
            base_payload(offer_end_date="2026-08-31")
        )
        self.assertIn("2026-08-31", date_only["creative_prompt"])
        self.assertIn("No offer was supplied", date_only["creative_prompt"])
        self.assertNotIn("confirmed_offer", date_only["creative_prompt"])
        self.assertIn(
            "Offer end date context (no offer supplied): 2026-08-31",
            creator.build_brief_text(date_only),
        )
        self.assertIn(
            "OPTIONAL OFFER CONTEXT",
            creator.build_social_copy_text(date_only),
        )

        complete = creator.build_content_package(
            base_payload(
                offer="15% off two verified editions",
                offer_end_date="2026-09-15",
            )
        )
        self.assertEqual(
            complete["offer_context"]["confirmed_offer"],
            "15% off two verified editions",
        )
        self.assertEqual(
            complete["offer_context"]["offer_end_date"],
            "2026-09-15",
        )

    def test_legacy_saved_values_are_ignored_but_current_values_restore(self):
        legacy = base_payload(
            hook="Custom saved angle",
            cta="Custom saved CTA.",
            offer="Verified saved offer",
            offer_end_date="2026-09-01",
            audience="Old audience",
            price="$199",
            rights_status="Old rights note",
            restrictions="Old restriction",
        )
        clean = creator.normalise_creator_input(legacy)
        prefill = creator.prefill_from_assignment(legacy)

        self.assertEqual(clean["hook"], "Custom saved angle")
        self.assertEqual(clean["cta"], "Custom saved CTA.")
        self.assertEqual(clean["offer"], "Verified saved offer")
        self.assertEqual(clean["offer_end_date"], "2026-09-01")
        self.assertEqual(clean["room_type"], "Auto — vary appropriately")
        self.assertEqual(
            clean["shot_distance_product_prominence"],
            "Auto — keep the product dominant",
        )
        self.assertEqual(prefill["hook"], "Custom saved angle")
        self.assertEqual(prefill["cta"], "Custom saved CTA.")
        self.assertEqual(prefill["offer"], "Verified saved offer")
        self.assertEqual(prefill["offer_end_date"], "2026-09-01")
        for legacy_field in (
            "audience",
            "price",
            "rights_status",
            "restrictions",
        ):
            self.assertNotIn(legacy_field, clean)
            self.assertNotIn(legacy_field, prefill)

        saved = base_payload(
            room_type="Executive Office",
            wall_colour="Graphite",
            wall_material_finish="Fine Textured Plaster",
            camera_angle="Slight Right Three-Quarter — 15–25 Degrees",
            shot_distance_product_prominence="Medium-Close — approximately 55–70% prominence",
            lighting_style="Soft Natural Daylight",
            variation_behaviour="Vary Camera Angle Only",
        )
        restored = creator.prefill_from_assignment(
            creator.normalise_creator_input(saved)
        )

        self.assertEqual(restored["room_type"], "Executive Office")
        self.assertEqual(restored["wall_colour"], "Graphite")
        self.assertEqual(restored["wall_material_finish"], "Fine Textured Plaster")
        self.assertEqual(
            restored["camera_angle"],
            "Slight Right Three-Quarter — 15–25 Degrees",
        )
        self.assertEqual(
            restored["shot_distance_product_prominence"],
            "Medium-Close — approximately 55–70% prominence",
        )
        self.assertEqual(restored["lighting_style"], "Soft Natural Daylight")
        self.assertEqual(restored["variation_behaviour"], "Vary Camera Angle Only")

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
        self.assertNotIn("VERIFICATION WARNINGS", brief)

    def test_strategy_assignment_is_not_saved_or_product_invented(self):
        assignment = creator.strategy_assignment_for_date(date(2026, 7, 31))

        self.assertEqual(assignment["day"], "Friday")
        self.assertEqual(assignment["series"], "ONLY 100")
        self.assertEqual(assignment["product_title"], "")
        self.assertEqual(assignment["status"], "Strategy recommendation")

    def test_approved_assignment_prefill_keeps_only_simplified_brief_fields(self):
        prefill = creator.prefill_from_assignment(
            {
                "product_title": "Brock Legends Collector's Edition",
                "hook": "Custom collector angle",
                "cta": "Open the collector story.",
                "offer": "Verified free shipping",
                "offer_end_date": "2026-08-31",
                "restrictions": "Do not publish before 6 pm.",
                "rights_status": "Approved original product photography",
            }
        )

        self.assertEqual(prefill["hook"], "Custom collector angle")
        self.assertEqual(prefill["cta"], "Open the collector story.")
        self.assertEqual(prefill["offer"], "Verified free shipping")
        self.assertEqual(prefill["offer_end_date"], "2026-08-31")
        self.assertNotIn("restrictions", prefill)
        self.assertNotIn("rights_status", prefill)


if __name__ == "__main__":
    unittest.main()
