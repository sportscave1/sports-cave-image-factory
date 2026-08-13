from pathlib import Path
import inspect
import unittest

import design_studio_page
from sports_cave_prompt_blocks import SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER


ROOT = Path(__file__).resolve().parents[1]


class DesignStudioResearchPromptTests(unittest.TestCase):
    def test_research_prompt_uses_pasted_task_without_finding_images(self):
        prompt = design_studio_page.build_design_research_prompt("Michael Jordan final shot collector piece")

        self.assertIn("TASK TO RESEARCH", prompt)
        self.assertIn("Michael Jordan final shot collector piece", prompt)
        self.assertIn("Use current web research", prompt)
        self.assertIn("do not find or display images yet", prompt)
        self.assertIn("research the sporting moment", prompt)
        self.assertIn("The best design angle for the moment", prompt)
        self.assertIn("Why the moment matters now", prompt)
        self.assertNotIn("display approximately 10-12 strong images", prompt)
        self.assertNotIn("commercial", prompt.casefold())
        self.assertNotIn("copyright", prompt.casefold())
        self.assertNotIn("country markets", prompt.casefold())
        self.assertNotIn("strong enough to sell", prompt.casefold())
        self.assertNotIn("bestseller", prompt.casefold())
        self.assertIn("Do not generate the final artwork yet.", prompt)
        self.assertNotIn(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER, prompt)

    def test_image_prompt_only_requests_image_carousel(self):
        prompt = design_studio_page.build_design_image_carousel_prompt(
            "Michael Jordan final shot collector piece",
            "The strongest angle is the final shot and Chicago nostalgia.",
        )

        self.assertIn(
            "find me the strongest, most accurate, and most useful reference images",
            prompt,
        )
        self.assertIn("using the separate image carousels required below", prompt)
        self.assertIn("Find multiple different image types, not just one hero photo.", prompt)
        self.assertIn("The correct athlete, driver, team, rivalry, event, season, era", prompt)
        self.assertIn("If Motorsport:", prompt)
        self.assertIn("For Bathurst/Supercars, prioritise Mount Panorama", prompt)
        self.assertIn("If Soccer/Football:", prompt)
        self.assertIn("If NBA/Basketball:", prompt)
        self.assertIn("If Cricket:", prompt)
        self.assertIn("If Boxing/UFC:", prompt)
        self.assertIn("If NFL/Baseball/Ice Hockey:", prompt)
        self.assertIn("Across the separate carousels", prompt)
        self.assertIn("Only display the strongest and most accurate images directly in this chat", prompt)
        self.assertIn("DESIGN TITLE: Michael Jordan final shot collector piece", prompt)
        self.assertEqual(
            prompt.count(design_studio_page.SPORTS_CAVE_HIGH_QUALITY_IMAGE_SEARCH_RULES_V2_MARKER),
            1,
        )
        self.assertIn("* Michael Jordan -> authentic signature image; role: signature_asset; subject_name: Michael Jordan", prompt)
        self.assertIn("RESEARCH BRIEF: The strongest angle is the final shot", prompt)
        self.assertNotIn("recommendations, or creative direction", prompt.split("Only find and display the images.")[1])
        self.assertNotIn("display approximately 10-12 strong images", prompt)
        self.assertNotIn("Limited-edition plaque position", prompt)
        self.assertNotIn(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER, prompt)

    def test_find_images_signature_search_targets_named_single_player(self):
        prompt = design_studio_page.build_design_image_carousel_prompt(
            "Create Michael Jordan final shot collector artwork",
            "",
        )

        self.assertEqual(
            prompt.count(design_studio_page.SPORTS_CAVE_HIGH_QUALITY_IMAGE_SEARCH_RULES_V2_MARKER),
            1,
        )
        self.assertIn("Return exactly one signature image for each distinct principal named person", prompt)
        self.assertIn("* Michael Jordan -> authentic signature image; role: signature_asset; subject_name: Michael Jordan", prompt)
        self.assertIn("1. PLAYER — Michael Jordan", prompt)
        self.assertIn("2. DESIGN REFERENCES", prompt)
        self.assertIn("3. SIGNATURES: return exactly 1 signature asset(s)", prompt)
        self.assertIn("A signature reference must never count as a player", prompt)
        self.assertIn("If no reliable signature can be verified", prompt)
        self.assertIn("Never fabricate or approximate it", prompt)
        self.assertEqual(prompt.count("signature_slot_limit: 1"), 1)

    def test_find_images_signature_search_targets_each_rival(self):
        prompt = design_studio_page.build_design_image_carousel_prompt(
            "Create Joe Montana vs Terry Bradshaw minimalist rivalry artwork",
            "",
        )

        self.assertEqual(
            prompt.count(design_studio_page.SPORTS_CAVE_HIGH_QUALITY_IMAGE_SEARCH_RULES_V2_MARKER),
            1,
        )
        self.assertIn("* Joe Montana -> authentic signature image; role: signature_asset; subject_name: Joe Montana", prompt)
        self.assertIn("* Terry Bradshaw -> authentic signature image; role: signature_asset; subject_name: Terry Bradshaw", prompt)
        self.assertIn("1. PLAYER — Joe Montana", prompt)
        self.assertIn("2. PLAYER — Terry Bradshaw", prompt)
        self.assertIn("4. SIGNATURES: return exactly 2 signature asset(s)", prompt)
        self.assertIn("Return exactly one signature image for each distinct principal named person", prompt)
        self.assertEqual(prompt.count("signature_slot_limit: 1"), 2)

    def test_find_images_signature_search_targets_multi_player_context(self):
        prompt = design_studio_page.build_design_image_carousel_prompt(
            "Create a Chicago legends collector artwork",
            "",
            design_context={
                "principal_subjects": [
                    {"name": "Michael Jordan"},
                    {"name": "Scottie Pippen"},
                    {"name": "Dennis Rodman"},
                ]
            },
        )

        for name in ("Michael Jordan", "Scottie Pippen", "Dennis Rodman"):
            self.assertIn(f"* {name} -> authentic signature image; role: signature_asset; subject_name: {name}", prompt)
        for index, name in enumerate(("Michael Jordan", "Scottie Pippen", "Dennis Rodman"), start=1):
            self.assertIn(f"{index}. PLAYER — {name}", prompt)
        self.assertIn("5. SIGNATURES: return exactly 3 signature asset(s)", prompt)
        self.assertEqual(prompt.count("signature_slot_limit: 1"), 3)

    def test_find_images_signature_slots_are_deduplicated_by_featured_person(self):
        prompt = design_studio_page.build_design_image_carousel_prompt(
            "Create a Michael Jordan collector artwork",
            "",
            design_context={
                "principal_subjects": [
                    {"name": "Michael Jordan"},
                    {"name": "michael jordan"},
                    {"name": "Michael Jordan"},
                ]
            },
        )

        self.assertIn("PRINCIPAL SUBJECTS: Michael Jordan", prompt)
        self.assertEqual(prompt.count("PLAYER — Michael Jordan:"), 1)
        self.assertEqual(prompt.count("signature_slot_limit: 1"), 1)

    def test_find_images_shared_reference_balance_is_authoritative_and_ordered(self):
        prompt = design_studio_page.build_design_image_carousel_prompt(
            "Create Michael Jordan final shot collector artwork",
            "",
        )

        priority_headings = (
            "MANDATORY MULTI-SEARCH WORKFLOW",
            "PLAYER CAROUSEL — MINIMUM CONTENT PER PLAYER",
            "SHARED DESIGN-REFERENCE CAROUSEL",
            "SIGNATURE CAROUSEL — ALWAYS LAST",
        )
        heading_positions = [prompt.index(heading) for heading in priority_headings]
        self.assertEqual(heading_positions, sorted(heading_positions))
        self.assertIn("Do not perform one broad image search and mix all results together.", prompt)
        self.assertIn("Return 6 to 10 genuinely useful", prompt)
        self.assertIn("At least half of every player's carousel must show that player's face clearly", prompt)
        self.assertIn("target at least 1200 pixels on the longest edge and prefer 2000 pixels or more", prompt)
        self.assertIn("Only after every player carousel is complete", prompt)
        self.assertIn("return one separate shared carousel containing 5 to 8 strong images", prompt)
        self.assertIn("Return exactly one signature image for each distinct principal named person", prompt)
        self.assertIn("Signed material is permitted only in the final signature carousel", prompt)
        self.assertIn("* Trading cards of any kind", prompt)
        self.assertIn("* Autographed player photographs", prompt)
        self.assertIn("* Signed cards, balls, helmets, jerseys or boots", prompt)
        self.assertNotIn("Place the strongest signature reference for each named subject directly in the same image carousel", prompt)

    def test_find_images_shared_rules_appear_once_for_single_rivalry_and_group_designs(self):
        cases = (
            (
                "single",
                "Create Michael Jordan final shot collector artwork",
                None,
                1,
            ),
            (
                "rivalry",
                "Create Joe Montana versus Terry Bradshaw face-off artwork",
                None,
                2,
            ),
            (
                "group",
                "Create a Chicago legends collector artwork",
                {
                    "principal_subjects": [
                        {"name": "Michael Jordan"},
                        {"name": "Scottie Pippen"},
                        {"name": "Dennis Rodman"},
                    ]
                },
                3,
            ),
        )

        for label, task, context, expected_slots in cases:
            with self.subTest(label=label):
                prompt = design_studio_page.build_design_image_carousel_prompt(
                    task,
                    "",
                    design_context=context,
                )
                self.assertEqual(
                    prompt.count(
                        design_studio_page.SPORTS_CAVE_HIGH_QUALITY_IMAGE_SEARCH_RULES_V2_MARKER
                    ),
                    1,
                )
                self.assertEqual(prompt.count("signature_slot_limit: 1"), expected_slots)
                self.assertIn(
                    f"SIGNATURES: return exactly {expected_slots} signature asset(s)",
                    prompt,
                )

    def test_find_images_signature_search_skips_vehicle_or_venue_only_targets(self):
        prompt = design_studio_page.build_design_image_carousel_prompt(
            "Create vehicle-only Ford Mustang race car collector artwork",
            "",
        )

        self.assertEqual(
            prompt.count(design_studio_page.SPORTS_CAVE_HIGH_QUALITY_IMAGE_SEARCH_RULES_V2_MARKER),
            1,
        )
        self.assertIn("Do not request an irrelevant signature", prompt)
        self.assertNotIn("Ford Mustang -> authentic signature image", prompt)
        self.assertNotIn("race car -> authentic signature image", prompt)

        task_context = prompt.split("TASK-SPECIFIC VARIABLES AND RESEARCH CONTEXT", 1)[1]
        self.assertNotIn(". PLAYER —", task_context)
        self.assertIn("Omit PLAYER and SIGNATURES carousels", task_context)

    def test_find_images_signature_search_targets_named_motorsport_driver(self):
        prompt = design_studio_page.build_design_image_carousel_prompt(
            "Create Ayrton Senna Monaco driver collector artwork",
            "",
        )

        self.assertIn("* Ayrton Senna -> authentic signature image; role: signature_asset; subject_name: Ayrton Senna", prompt)

    def test_find_images_v2_source_is_inserted_verbatim_before_task_context(self):
        prompt = design_studio_page.build_design_image_carousel_prompt(
            "Create Michael Jordan final shot collector artwork",
            "Verified research context.",
        )
        source = design_studio_page.HIGH_QUALITY_IMAGE_SEARCH_V2_PROMPT_PATH.read_text(
            encoding="utf-8"
        ).strip()
        source_start = prompt.index(
            design_studio_page.SPORTS_CAVE_HIGH_QUALITY_IMAGE_SEARCH_RULES_V2_MARKER
        )
        context_start = prompt.index("TASK-SPECIFIC VARIABLES AND RESEARCH CONTEXT")

        self.assertEqual(prompt[source_start:context_start].strip(), source)
        self.assertLess(source_start, context_start)
        self.assertEqual(prompt.count(source), 1)

    def test_find_images_player_carousels_precede_design_references_and_signatures(self):
        prompt = design_studio_page.build_design_image_carousel_prompt(
            "Create a Chicago legends collector artwork",
            "Verified three-player research.",
            design_context={
                "principal_subjects": [
                    {"name": "Michael Jordan"},
                    {"name": "Scottie Pippen"},
                    {"name": "Dennis Rodman"},
                ]
            },
        )
        execution_plan = prompt.split("REQUIRED SEARCH AND CAROUSEL EXECUTION PLAN", 1)[1]
        expected = (
            "1. PLAYER — Michael Jordan",
            "2. PLAYER — Scottie Pippen",
            "3. PLAYER — Dennis Rodman",
            "4. DESIGN REFERENCES",
            "5. SIGNATURES",
        )
        positions = [execution_plan.index(item) for item in expected]

        self.assertEqual(positions, sorted(positions))
        self.assertEqual(execution_plan.count("signature_slot_limit: 1"), 3)
        self.assertIn("run and complete a separate search", execution_plan)

    def test_find_images_v2_does_not_leak_into_research_or_artwork_generation(self):
        research_prompt = design_studio_page.build_design_research_prompt(
            "Michael Jordan final shot collector artwork"
        )
        artwork_prompt = design_studio_page.build_design_generation_prompt(
            "Michael Jordan final shot collector artwork"
        )
        marker = design_studio_page.SPORTS_CAVE_HIGH_QUALITY_IMAGE_SEARCH_RULES_V2_MARKER

        self.assertNotIn(marker, research_prompt)
        self.assertNotIn(marker, artwork_prompt)
        self.assertIn(
            design_studio_page.SPORTS_CAVE_FINAL_ARTWORK_MASTER_PROMPT_MARKER,
            artwork_prompt,
        )
        self.assertNotIn(
            design_studio_page.DESIGN_STUDIO_SUBJECT_PRESERVATION_MARKER,
            artwork_prompt,
        )
        self.assertNotIn(
            design_studio_page.DESIGN_STUDIO_LIMITED_EDITION_BORDER_MARKER,
            artwork_prompt,
        )

    def test_design_generation_prompt_uses_concise_master_instructions(self):
        prompt = design_studio_page.build_design_generation_prompt("Bathurst Brock tribute")
        master_marker = design_studio_page.SPORTS_CAVE_FINAL_ARTWORK_MASTER_PROMPT_MARKER
        legacy_markers = (
            design_studio_page.DESIGN_STUDIO_SUBJECT_PRESERVATION_MARKER,
            design_studio_page.SPORTS_CAVE_RIVALRY_COMPOSITION_RULES_MARKER,
            design_studio_page.SPORTS_CAVE_AUTHENTIC_SIGNATURE_APPLICATION_RULES_MARKER,
            design_studio_page.SPORTS_CAVE_SIGNATURE_PREMIUM_TREATMENT_MARKER,
            design_studio_page.DESIGN_STUDIO_HERO_DOMINANCE_MARKER,
            design_studio_page.DESIGN_STUDIO_LIMITED_EDITION_BORDER_MARKER,
            design_studio_page.DESIGN_STUDIO_STRICT_BORDER_CONTAINMENT_MARKER,
            SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER,
        )

        self.assertIn(
            "Create a premium Sports Cave limited-edition collector artwork using the task variables and all supplied reference images.",
            prompt,
        )
        self.assertIn("TASK:\nBathurst Brock tribute", prompt)
        self.assertIn("Select the strongest supplied action or full-body photograph", prompt)
        self.assertIn("Never redraw, regenerate, face-swap or recreate a player.", prompt)
        self.assertIn("Never combine a face from one image with a body from another.", prompt)
        self.assertIn("If an image cannot be extended naturally, retain its original crop.", prompt)
        self.assertIn("The supplied players are the heroes and must dominate.", prompt)
        self.assertIn("Do not add generated players, detailed AI crowds", prompt)
        self.assertIn("Never generate, rewrite or imitate a signature.", prompt)
        self.assertIn("If no verified signature exists for a player, omit it.", prompt)
        self.assertIn("Never invent, redraw or approximate a plaque.", prompt)
        self.assertIn("Create a landscape 4:3 composition", prompt)
        self.assertIn("professional photographic composite", prompt)
        self.assertEqual(prompt.count(master_marker), 1)
        self.assertLess(
            len(
                design_studio_page._clean_prompt(
                    design_studio_page.SPORTS_CAVE_FINAL_ARTWORK_MASTER_PROMPT
                )
            ),
            3000,
        )
        for marker in legacy_markers:
            self.assertNotIn(marker, prompt)

    def test_new_design_step_three_contains_master_once_before_task(self):
        prompt = design_studio_page.build_design_generation_prompt("Bathurst Brock tribute")
        marker = design_studio_page.SPORTS_CAVE_FINAL_ARTWORK_MASTER_PROMPT_MARKER

        self.assertTrue(prompt.startswith(marker))
        self.assertEqual(prompt.count(marker), 1)
        self.assertLess(prompt.index(marker), prompt.index("TASK:\nBathurst Brock tribute"))
        self.assertNotIn(design_studio_page.DESIGN_STUDIO_SUBJECT_PRESERVATION_MARKER, prompt)
        self.assertNotIn(design_studio_page.DESIGN_STUDIO_HERO_DOMINANCE_MARKER, prompt)

    def test_rivalry_step_three_uses_same_concise_cohero_master_prompt(self):
        prompt = design_studio_page.build_design_generation_prompt(
            "Create a minimalist Messi vs Ronaldo face-off collector design"
        )

        self.assertEqual(
            prompt.count(design_studio_page.SPORTS_CAVE_FINAL_ARTWORK_MASTER_PROMPT_MARKER),
            1,
        )
        self.assertIn(
            "TASK:\nCreate a minimalist Messi vs Ronaldo face-off collector design",
            prompt,
        )
        self.assertIn("The supplied players are the heroes and must dominate.", prompt)
        self.assertNotIn(design_studio_page.SPORTS_CAVE_RIVALRY_COMPOSITION_RULES_MARKER, prompt)

    def test_rivalry_text_does_not_append_legacy_blocks_to_step_three_prompt(self):
        trigger_tasks = (
            "Create Messi VS Ronaldo collector artwork",
            "Create Messi versus Ronaldo collector artwork",
            "Create an AFL rivalry artwork",
            "Create a boxing face-off collector piece",
            "Create head-to-head legends artwork",
            "Create the great debate collector artwork",
            "Create a two-legend legacy design",
            "Create a legacy design built around two famous jersey backs",
        )

        for task in trigger_tasks:
            with self.subTest(task=task):
                prompt = design_studio_page.build_design_generation_prompt(task)
                self.assertEqual(
                    prompt.count(design_studio_page.SPORTS_CAVE_FINAL_ARTWORK_MASTER_PROMPT_MARKER),
                    1,
                )
                self.assertNotIn(
                    design_studio_page.SPORTS_CAVE_RIVALRY_COMPOSITION_RULES_MARKER,
                    prompt,
                )

    def test_structured_rivalry_context_activates_generation_prompt(self):
        structured_values = (
            "rivalry",
            "vs",
            "versus",
            "face_off",
            "head-to-head",
            "great debate",
            "two_legend",
            "jersey_back",
        )

        for value in structured_values:
            with self.subTest(value=value):
                prompt = design_studio_page.build_design_studio_image_generation_prompt(
                    "Create a premium 4:3 landscape Sports Cave collector artwork.",
                    design_context={"metadata": {"design_type": value}},
                )
                self.assertEqual(
                    prompt.count(design_studio_page.SPORTS_CAVE_RIVALRY_COMPOSITION_RULES_MARKER),
                    1,
                )

    def test_structured_non_rivalry_context_does_not_fall_back_to_text_detection(self):
        prompt = design_studio_page.build_design_studio_image_generation_prompt(
            "Create a premium 4:3 Sports Cave artwork for Title With VS In It.",
            design_context={"metadata": {"design_type": "single-athlete"}, "title": "Title With VS In It"},
        )

        self.assertNotIn(design_studio_page.SPORTS_CAVE_RIVALRY_COMPOSITION_RULES_MARKER, prompt)

    def test_new_design_generation_prompt_uses_structured_task_context_when_supplied(self):
        rivalry_prompt = design_studio_page.build_design_generation_prompt(
            "Create a premium collector artwork",
            design_context={
                "title": "Create a premium collector artwork",
                "metadata": {"design_type": "rivalry"},
            },
        )
        single_subject_prompt = design_studio_page.build_design_generation_prompt(
            "Create a premium VS title artwork",
            design_context={
                "title": "Create a premium VS title artwork",
                "metadata": {"design_type": "single-athlete"},
            },
        )

        for prompt in (rivalry_prompt, single_subject_prompt):
            self.assertEqual(
                prompt.count(design_studio_page.SPORTS_CAVE_FINAL_ARTWORK_MASTER_PROMPT_MARKER),
                1,
            )
            self.assertNotIn(
                design_studio_page.SPORTS_CAVE_RIVALRY_COMPOSITION_RULES_MARKER,
                prompt,
            )
        self.assertIn("TASK:\nCreate a premium collector artwork", rivalry_prompt)
        self.assertIn("TASK:\nCreate a premium VS title artwork", single_subject_prompt)

    def test_rivalry_rules_apply_once_to_all_final_artwork_routes_when_context_matches(self):
        generation_names = (
            "Upgrade Existing Design Prompt",
            "Expired Edition / Next Chapter Design Prompt",
            "Create Sports Cave Style Artwork Prompt",
        )

        step_three_prompt = design_studio_page.build_design_generation_prompt(
            "Create a rivalry design: Messi vs Ronaldo"
        )
        prompts = [
            design_studio_page.build_design_studio_image_generation_prompt(
                design_studio_page.PROMPT_BOXES[prompt_name][0],
                design_context={"artwork_type": "rivalry"},
            )
            for prompt_name in generation_names
        ]

        self.assertEqual(
            step_three_prompt.count(
                design_studio_page.SPORTS_CAVE_FINAL_ARTWORK_MASTER_PROMPT_MARKER
            ),
            1,
        )
        self.assertNotIn(
            design_studio_page.SPORTS_CAVE_RIVALRY_COMPOSITION_RULES_MARKER,
            step_three_prompt,
        )

        for prompt in prompts:
            with self.subTest(prompt=prompt[:60]):
                self.assertEqual(prompt.count(design_studio_page.DESIGN_STUDIO_SUBJECT_PRESERVATION_MARKER), 1)
                self.assertEqual(prompt.count(design_studio_page.SPORTS_CAVE_RIVALRY_COMPOSITION_RULES_MARKER), 1)
                self.assertEqual(prompt.count(design_studio_page.SPORTS_CAVE_AUTHENTIC_SIGNATURE_APPLICATION_RULES_MARKER), 1)
                self.assertEqual(prompt.count(design_studio_page.DESIGN_STUDIO_HERO_DOMINANCE_MARKER), 1)
                self.assertEqual(prompt.count(design_studio_page.DESIGN_STUDIO_STRICT_BORDER_CONTAINMENT_MARKER), 1)
                self.assertEqual(prompt.count(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER), 1)
                self.assertIn("Two opposing co-equal heroes", prompt)
                self.assertIn("Do not mirror, rotate, repose or reconstruct either person", prompt)
                self.assertIn("Never create a generated jersey-back replacement.", prompt)
                self.assertIn("Use one authentic signature for each principal rival.", prompt)
                self.assertIn("Nothing may overlap, sit over, pass through, hide or extend beyond the border.", prompt)

    def test_final_generation_maps_selected_signature_assets(self):
        prompt = design_studio_page.build_design_generation_prompt(
            "Create Joe Montana collector artwork",
            design_context={
                "principal_subjects": [{"name": "Joe Montana"}],
                "selected_images": [
                    {
                        "role": "hero_image",
                        "subject_name": "Joe Montana",
                        "image_reference": "C:/selected/joe-montana-action.jpg",
                    },
                    {
                        "role": "signature_asset",
                        "subject_name": "Joe Montana",
                        "image_reference": "C:/selected/joe-montana-signature.png",
                    }
                ],
            },
        )

        self.assertIn("SELECTED IMAGE ASSETS AND ROLE METADATA", prompt)
        self.assertIn("Pass and use these actual selected image files as image inputs.", prompt)
        self.assertIn(
            "* C:/selected/joe-montana-action.jpg | role: hero_image; subject: Joe Montana",
            prompt,
        )
        self.assertIn(
            "* C:/selected/joe-montana-signature.png | role: signature_asset; subject: Joe Montana",
            prompt,
        )
        self.assertIn("VERIFIED SIGNATURE ASSET MAPPING", prompt)
        self.assertIn("* Joe Montana -> C:/selected/joe-montana-signature.png", prompt)
        self.assertNotIn(
            design_studio_page.SPORTS_CAVE_AUTHENTIC_SIGNATURE_APPLICATION_RULES_MARKER,
            prompt,
        )
        self.assertNotIn(
            design_studio_page.SPORTS_CAVE_SIGNATURE_PREMIUM_TREATMENT_MARKER,
            prompt,
        )

    def test_final_generation_preserves_selected_asset_roles_and_subjects(self):
        prompt = design_studio_page.build_design_generation_prompt(
            "Create Joe Montana collector artwork",
            design_context={
                "principal_subjects": [{"name": "Joe Montana"}],
                "selected_images": [
                    {
                        "role": "hero_image",
                        "subject_name": "Joe Montana",
                        "file_path": "C:/assets/joe-action.jpg",
                    },
                    {
                        "role": "identity_reference",
                        "subject_name": "Joe Montana",
                        "file_path": "C:/assets/joe-face.jpg",
                    },
                    {
                        "role": "background",
                        "file_path": "C:/assets/candlestick-park.jpg",
                    },
                    {
                        "role": "plaque_asset",
                        "file_path": "C:/assets/sports-cave-plaque.png",
                    },
                    {
                        "role": "signature_asset",
                        "subject_name": "Joe Montana",
                        "file_path": "C:/assets/joe-signature.png",
                    },
                ],
            },
        )

        expected_asset_lines = (
            "* C:/assets/joe-action.jpg | role: hero_image; subject: Joe Montana",
            "* C:/assets/joe-face.jpg | role: identity_reference; subject: Joe Montana",
            "* C:/assets/candlestick-park.jpg | role: background",
            "* C:/assets/sports-cave-plaque.png | role: plaque_asset",
            "* C:/assets/joe-signature.png | role: signature_asset; subject: Joe Montana",
        )
        for line in expected_asset_lines:
            self.assertIn(line, prompt)
        self.assertIn("* Joe Montana -> C:/assets/joe-signature.png", prompt)
        self.assertLess(
            prompt.index("SELECTED IMAGE ASSETS AND ROLE METADATA"),
            prompt.index("VERIFIED SIGNATURE ASSET MAPPING"),
        )

    def test_final_generation_rejects_style_phrases_as_signature_subjects(self):
        prompt = design_studio_page.build_design_generation_prompt(
            "Create Joe Montana collector artwork",
            design_context={
                "principal_subjects": [{"name": "Joe Montana"}],
                "selected_images": [
                    {
                        "role": "signature_asset",
                        "subject_name": "Joe Montana",
                        "file_path": "C:/assets/joe-signature.png",
                    },
                    {
                        "role": "signature_asset",
                        "subject_name": "Thin Sports Cave",
                        "file_path": "C:/assets/false-thin.png",
                    },
                    {
                        "role": "signature_asset",
                        "subject_name": "The Sports Cave",
                        "file_path": "C:/assets/false-brand.png",
                    },
                    {
                        "role": "signature_asset",
                        "subject_name": "Cinematic Realistic",
                        "file_path": "C:/assets/false-style.png",
                    },
                ],
            },
        )

        self.assertEqual(prompt.count("VERIFIED SIGNATURE ASSET MAPPING"), 1)
        self.assertIn("* Joe Montana -> C:/assets/joe-signature.png", prompt)
        for invalid_value in (
            "Thin Sports Cave",
            "The Sports Cave",
            "Cinematic Realistic",
            "C:/assets/false-thin.png",
            "C:/assets/false-brand.png",
            "C:/assets/false-style.png",
        ):
            self.assertNotIn(invalid_value, prompt)

    def test_final_generation_does_not_invent_plaque_without_asset(self):
        prompt = design_studio_page.build_design_generation_prompt(
            "Create Joe Montana collector artwork",
            design_context={
                "principal_subjects": [{"name": "Joe Montana"}],
                "selected_images": [
                    {
                        "role": "hero_image",
                        "subject_name": "Joe Montana",
                        "file_path": "C:/assets/joe-action.jpg",
                    }
                ],
            },
        )

        self.assertIn("Use an exact supplied Sports Cave limited-edition plaque asset only when one is supplied.", prompt)
        self.assertIn("Never invent, redraw or approximate a plaque.", prompt)
        self.assertNotIn("role: plaque_asset", prompt)

    def test_final_generation_signature_fallback_never_generates_missing_signature(self):
        prompt = design_studio_page.build_design_generation_prompt("Create vehicle-only Mount Panorama circuit artwork")

        self.assertNotIn("VERIFIED SIGNATURE ASSET MAPPING", prompt)
        self.assertIn("If no verified signature exists for a player, omit it.", prompt)
        self.assertIn("Never generate, rewrite or imitate a signature.", prompt)

    def test_signature_premium_treatment_applies_to_all_final_routes_with_verified_assets(self):
        premium_marker = design_studio_page.SPORTS_CAVE_SIGNATURE_PREMIUM_TREATMENT_MARKER
        signature_context = {
            "principal_subjects": [{"name": "Joe Montana"}],
            "signature_assets": [
                {
                    "subject_name": "Joe Montana",
                    "image_reference": "selected signature carousel image 4",
                }
            ],
        }
        generation_names = (
            "Upgrade Existing Design Prompt",
            "Expired Edition / Next Chapter Design Prompt",
            "Create Sports Cave Style Artwork Prompt",
        )

        step_three_prompt = design_studio_page.build_design_generation_prompt(
            "Create Joe Montana collector artwork",
            design_context=signature_context,
        )
        prompts = [
            design_studio_page.build_design_studio_image_generation_prompt(
                design_studio_page.PROMPT_BOXES[prompt_name][0],
                design_context=signature_context,
            )
            for prompt_name in generation_names
        ]

        self.assertNotIn(premium_marker, step_three_prompt)
        self.assertIn("VERIFIED SIGNATURE ASSET MAPPING", step_three_prompt)
        self.assertIn(
            "* Joe Montana -> selected signature carousel image 4",
            step_three_prompt,
        )

        for prompt in prompts:
            with self.subTest(prompt=prompt[:60]):
                self.assertEqual(prompt.count(premium_marker), 1)
                self.assertIn("Only use the supplied, selected or reliably sourced authentic signature", prompt)
                self.assertIn("Do not use a script font, invented handwriting or generic autograph styling.", prompt)
                self.assertIn("If no reliable signature reference is supplied or found, omit the signature.", prompt)
                self.assertIn("Where technically possible, use the supplied signature as a preserved composited asset", prompt)
                self.assertIn("Keep the signature’s scale modest.", prompt)
                self.assertIn("* Joe Montana -> selected signature carousel image 4", prompt)

    def test_signature_premium_treatment_does_not_apply_without_verified_assets(self):
        prompt = design_studio_page.build_design_generation_prompt(
            "Create Michael Jordan collector artwork",
            design_context={
                "principal_subjects": [
                    {
                        "name": "Michael Jordan",
                        "image_reference": "selected hero carousel image 1",
                    }
                ]
            },
        )

        self.assertNotIn(design_studio_page.SPORTS_CAVE_SIGNATURE_PREMIUM_TREATMENT_MARKER, prompt)
        self.assertNotIn("VERIFIED SIGNATURE ASSET MAPPING", prompt)
        self.assertNotIn("* Michael Jordan -> selected hero carousel image 1", prompt)

    def test_signature_premium_treatment_accepts_role_tagged_signature_assets(self):
        prompt = design_studio_page.build_design_generation_prompt(
            "Create Joe Montana collector artwork",
            design_context={
                "selected_images": [
                    {
                        "role": "signature_asset",
                        "subject_name": "Joe Montana",
                        "image_reference": "selected image carousel item 7",
                    }
                ]
            },
        )

        self.assertNotIn(design_studio_page.SPORTS_CAVE_SIGNATURE_PREMIUM_TREATMENT_MARKER, prompt)
        self.assertIn("VERIFIED SIGNATURE ASSET MAPPING", prompt)
        self.assertIn(
            "* selected image carousel item 7 | role: signature_asset; subject: Joe Montana",
            prompt,
        )
        self.assertIn("* Joe Montana -> selected image carousel item 7", prompt)

    def test_existing_approved_artwork_signature_rules_do_not_add_unrelated_signatures(self):
        prompt = design_studio_page.build_design_studio_image_generation_prompt(
            design_studio_page.UPGRADE_EXISTING_DESIGN_PROMPT,
        )

        self.assertIn("For an existing approved design:", prompt)
        self.assertIn("Preserve every existing signature exactly unless the user requests a change.", prompt)
        self.assertIn("Do not add new signatures during an unrelated edit.", prompt)
        self.assertNotIn("signature-style graphic", prompt)

    def test_design_studio_regeneration_and_refinement_prompts_include_subject_lock_once(self):
        marker = design_studio_page.DESIGN_STUDIO_SUBJECT_PRESERVATION_MARKER
        generation_names = (
            "Upgrade Existing Design Prompt",
            "Expired Edition / Next Chapter Design Prompt",
            "Create Sports Cave Style Artwork Prompt",
        )

        for prompt_name in generation_names:
            with self.subTest(prompt_name=prompt_name):
                default_prompt, key = design_studio_page.PROMPT_BOXES[prompt_name]
                self.assertIn(key, design_studio_page.DESIGN_STUDIO_IMAGE_GENERATION_PROMPT_KEYS)
                prompt = design_studio_page.build_design_studio_image_generation_prompt(default_prompt)

                self.assertTrue(prompt.startswith(marker))
                self.assertEqual(prompt.count(marker), 1)
                self.assertEqual(prompt.count(design_studio_page.DESIGN_STUDIO_HERO_DOMINANCE_MARKER), 1)
                self.assertEqual(prompt.count(design_studio_page.DESIGN_STUDIO_LIMITED_EDITION_BORDER_MARKER), 1)
                self.assertEqual(prompt.count(design_studio_page.DESIGN_STUDIO_STRICT_BORDER_CONTAINMENT_MARKER), 1)
                self.assertNotIn(design_studio_page.SPORTS_CAVE_RIVALRY_COMPOSITION_RULES_MARKER, prompt)
                self.assertEqual(prompt.count(design_studio_page.SPORTS_CAVE_AUTHENTIC_SIGNATURE_APPLICATION_RULES_MARKER), 1)
                self.assertEqual(prompt.count(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER), 1)
                self.assertIn("Never generate extra supporting players.", prompt)
                self.assertIn("Any crowd treatment must remain distant, abstract, blurred and textural.", prompt)
                self.assertIn("The border must remain:", prompt)
                self.assertIn("Outside the border, allow only a clean, uniform deep-black or near-black outer margin.", prompt)
                self.assertNotIn("signature-style graphic", prompt)
                self.assertIn("4:3 landscape", prompt)
                self.assertIn("collector artwork", prompt)
                self.assertIn("Sports Cave", prompt)

    def test_unrelated_design_studio_prompts_do_not_receive_subject_lock(self):
        marker = design_studio_page.DESIGN_STUDIO_SUBJECT_PRESERVATION_MARKER
        hero_marker = design_studio_page.DESIGN_STUDIO_HERO_DOMINANCE_MARKER
        border_marker = design_studio_page.DESIGN_STUDIO_LIMITED_EDITION_BORDER_MARKER
        containment_marker = design_studio_page.DESIGN_STUDIO_STRICT_BORDER_CONTAINMENT_MARKER
        rivalry_marker = design_studio_page.SPORTS_CAVE_RIVALRY_COMPOSITION_RULES_MARKER
        signature_application_marker = design_studio_page.SPORTS_CAVE_AUTHENTIC_SIGNATURE_APPLICATION_RULES_MARKER
        unrelated_prompts = [
            design_studio_page.build_design_research_prompt("Michael Jordan final shot"),
            design_studio_page.build_design_image_carousel_prompt("Michael Jordan final shot", ""),
            design_studio_page.FIND_THE_MOMENT_PROMPT,
            design_studio_page.HARSH_REVIEW_PROMPT,
        ]

        for prompt in unrelated_prompts:
            with self.subTest(prompt=prompt[:40]):
                self.assertNotIn(marker, prompt)
                self.assertNotIn(hero_marker, prompt)
                self.assertNotIn(border_marker, prompt)
                self.assertNotIn(containment_marker, prompt)
                self.assertNotIn(rivalry_marker, prompt)
                self.assertNotIn(signature_application_marker, prompt)

    def test_subject_lock_composition_is_idempotent_and_preserves_prompt_details(self):
        marker = design_studio_page.DESIGN_STUDIO_SUBJECT_PRESERVATION_MARKER
        hero_marker = design_studio_page.DESIGN_STUDIO_HERO_DOMINANCE_MARKER
        border_marker = design_studio_page.DESIGN_STUDIO_LIMITED_EDITION_BORDER_MARKER
        containment_marker = design_studio_page.DESIGN_STUDIO_STRICT_BORDER_CONTAINMENT_MARKER
        signature_marker = design_studio_page.SPORTS_CAVE_AUTHENTIC_SIGNATURE_APPLICATION_RULES_MARKER
        once = design_studio_page.build_design_studio_image_generation_prompt(
            design_studio_page.CREATE_SPORTS_CAVE_STYLE_ARTWORK_PROMPT
        )
        twice = design_studio_page.build_design_studio_image_generation_prompt(once)

        self.assertEqual(once, twice)
        self.assertEqual(twice.count(marker), 1)
        self.assertEqual(twice.count(hero_marker), 1)
        self.assertEqual(twice.count(border_marker), 1)
        self.assertEqual(twice.count(containment_marker), 1)
        self.assertEqual(twice.count(signature_marker), 1)
        self.assertEqual(
            twice.count(design_studio_page._clean_prompt(design_studio_page.DESIGN_STUDIO_HERO_DOMINANCE_AND_BORDER_LOCK)),
            1,
        )
        self.assertEqual(twice.count(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER), 1)
        self.assertIn("[PASTE SELECTED MOMENT]", twice)
        self.assertIn("[PASTE HERO IMAGE DIRECTION]", twice)
        self.assertIn("[PASTE BACKGROUND IMAGE DIRECTION]", twice)
        self.assertIn("Use the Sports Cave limited-edition plaque attached to this project", twice)

    def test_step_three_master_is_stable_when_signature_selected(self):
        design_context = {
            "principal_subjects": [{"name": "Joe Montana"}],
            "signature_assets": [
                {
                    "subject_name": "Joe Montana",
                    "image_reference": "selected signature carousel image 4",
                }
            ],
        }
        once = design_studio_page.build_design_generation_prompt(
            "Create Joe Montana collector artwork",
            design_context=design_context,
        )
        twice = design_studio_page.build_design_generation_prompt(
            "Create Joe Montana collector artwork",
            design_context=design_context,
        )

        self.assertEqual(once, twice)
        self.assertEqual(
            twice.count(design_studio_page.SPORTS_CAVE_FINAL_ARTWORK_MASTER_PROMPT_MARKER),
            1,
        )
        self.assertEqual(twice.count("VERIFIED SIGNATURE ASSET MAPPING"), 1)

    def test_step_three_master_is_stable_for_rivalry_task(self):
        marker = design_studio_page.SPORTS_CAVE_FINAL_ARTWORK_MASTER_PROMPT_MARKER
        once = design_studio_page.build_design_generation_prompt("Create a motorsport rivalry design: Brock vs Moffat")
        twice = design_studio_page.build_design_generation_prompt("Create a motorsport rivalry design: Brock vs Moffat")

        self.assertEqual(once, twice)
        self.assertEqual(twice.count(marker), 1)
        self.assertNotIn(design_studio_page.SPORTS_CAVE_RIVALRY_COMPOSITION_RULES_MARKER, twice)

    def test_design_studio_sources_do_not_contain_active_signature_style_permission(self):
        source = (ROOT / "design_studio_page.py").read_text(encoding="utf-8")
        expired_prompt = (
            ROOT / "design_studio_prompts" / "expired_edition_next_chapter_prompt.txt"
        ).read_text(encoding="utf-8")

        self.assertNotIn("Where appropriate, include a subtle signature-style graphic.", source)
        self.assertNotIn("Where suitable, include a subtle signature-style graphic.", source)
        self.assertNotIn("Where appropriate, include a subtle signature-style graphic.", expired_prompt)
        self.assertNotIn("Where suitable, include a subtle signature-style graphic.", expired_prompt)

    def test_rendered_design_studio_image_prompt_boxes_use_shared_subject_lock_helper(self):
        source = (ROOT / "design_studio_page.py").read_text(encoding="utf-8")
        renderer = source[
            source.index("def render_copy_prompt_box") :
            source.index("\n\ndef render_generated_prompt_box")
        ]

        self.assertIn("DESIGN_STUDIO_IMAGE_GENERATION_PROMPT_KEYS", renderer)
        self.assertIn("build_design_studio_image_generation_prompt(effective_prompt)", renderer)
        self.assertNotIn("DESIGN_STUDIO_SUBJECT_PRESERVATION_LOCK +", renderer)

    def test_new_design_task_titles_use_open_new_design_tasks_only(self):
        tasks = [
            {"title": "Create New NASCAR Design", "section": "New designs to complete"},
            {"title": "Refresh NFL collection", "section": "Collections to update"},
            {"text": "Create New Golf Design", "category": "New designs to complete"},
            {"title": "Create New NASCAR Design", "section": "New designs to complete"},
            {"title": "", "section": "New designs to complete"},
        ]

        def fake_list_tasks(status="open"):
            self.assertEqual(status, "open")
            return tasks

        self.assertEqual(
            design_studio_page.list_new_design_task_titles(fake_list_tasks),
            ["Create New NASCAR Design", "Create New Golf Design"],
        )

    def test_new_design_task_records_preserve_metadata(self):
        tasks = [
            {
                "title": "Create Legends Rivalry Design",
                "section": "New designs to complete",
                "metadata": {"design_type": "rivalry"},
            },
        ]

        records = design_studio_page.list_new_design_task_records(lambda status="open": tasks)

        self.assertEqual(records[0]["title"], "Create Legends Rivalry Design")
        self.assertEqual(records[0]["metadata"], {"design_type": "rivalry"})

    def test_new_design_task_titles_fall_back_to_empty_list(self):
        def failing_list_tasks(status="open"):
            raise RuntimeError("saving unavailable")

        self.assertEqual(design_studio_page.list_new_design_task_titles(failing_list_tasks), [])

    def test_design_studio_active_renderer_has_no_legacy_workflow_tabs(self):
        renderer = inspect.getsource(design_studio_page.render_design_studio_page)
        v2_renderer = inspect.getsource(design_studio_page.render_design_studio_v2)

        self.assertNotIn("st.tabs", renderer)
        self.assertNotIn("st.tabs", v2_renderer)
        self.assertNotIn("Upgrade Existing Design", v2_renderer)
        self.assertNotIn("Update Expired Edition", v2_renderer)

    def test_design_studio_v2_renderer_has_three_prompt_steps_in_order(self):
        renderer = inspect.getsource(design_studio_page.render_design_studio_v2)

        self.assertLess(renderer.index("Research Prompt"), renderer.index("Find Images Prompt"))
        self.assertLess(renderer.index("Find Images Prompt"), renderer.index("Design Generation Prompt"))
        self.assertLess(renderer.index("Design Generation Prompt"), renderer.index("Harsh Review"))
        self.assertIn("Choose design task", renderer)
        self.assertIn("Design style", renderer)
        self.assertIn("Design details", inspect.getsource(design_studio_page._render_design_details))


if __name__ == "__main__":
    unittest.main()
