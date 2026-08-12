from pathlib import Path
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
        self.assertIn("display them directly in this chat as an image carousel", prompt)
        self.assertIn("Find multiple different image types, not just one hero photo.", prompt)
        self.assertIn("The correct athlete, driver, team, rivalry, event, season, era", prompt)
        self.assertIn("If Motorsport:", prompt)
        self.assertIn("For Bathurst/Supercars, prioritise Mount Panorama", prompt)
        self.assertIn("If Soccer/Football:", prompt)
        self.assertIn("If NBA/Basketball:", prompt)
        self.assertIn("If Cricket:", prompt)
        self.assertIn("If Boxing/UFC:", prompt)
        self.assertIn("If NFL/Baseball/Ice Hockey:", prompt)
        self.assertIn("Display a strong variety of images", prompt)
        self.assertIn("Only display the strongest and most accurate images directly in this chat", prompt)
        self.assertIn("Task context: Michael Jordan final shot collector piece", prompt)
        self.assertEqual(prompt.count(design_studio_page.SPORTS_CAVE_SIGNATURE_IMAGE_SEARCH_RULES_MARKER), 1)
        self.assertIn("* Michael Jordan -> authentic signature image; role: signature_asset; subject_name: Michael Jordan", prompt)
        self.assertNotIn("The strongest angle is the final shot", prompt)
        self.assertNotIn("recommendations, or creative direction", prompt.split("Only find and display the images.")[1])
        self.assertNotIn("display approximately 10-12 strong images", prompt)
        self.assertNotIn("Limited-edition plaque position", prompt)
        self.assertNotIn(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER, prompt)

    def test_find_images_signature_search_targets_named_single_player(self):
        prompt = design_studio_page.build_design_image_carousel_prompt(
            "Create Michael Jordan final shot collector artwork",
            "",
        )

        self.assertEqual(prompt.count(design_studio_page.SPORTS_CAVE_SIGNATURE_IMAGE_SEARCH_RULES_MARKER), 1)
        self.assertIn("find one and only one authentic signature or autograph image", prompt)
        self.assertIn("* Michael Jordan -> authentic signature image; role: signature_asset; subject_name: Michael Jordan", prompt)
        self.assertIn("Place the strongest signature reference for each named subject directly in the same image carousel", prompt)
        self.assertIn("A signature must never be classified as:", prompt)
        self.assertIn("* Hero image", prompt)
        self.assertIn("* Background image", prompt)
        self.assertIn("If no sufficiently reliable signature can be found", prompt)
        self.assertIn("Do not fabricate or approximate one", prompt)
        self.assertIn("Maximum signature images permitted in the entire carousel: 1", prompt)
        self.assertEqual(prompt.count("signature_slot_limit: 1"), 1)

    def test_find_images_signature_search_targets_each_rival(self):
        prompt = design_studio_page.build_design_image_carousel_prompt(
            "Create Joe Montana vs Terry Bradshaw minimalist rivalry artwork",
            "",
        )

        self.assertEqual(prompt.count(design_studio_page.SPORTS_CAVE_SIGNATURE_IMAGE_SEARCH_RULES_MARKER), 1)
        self.assertIn("* Joe Montana -> authentic signature image; role: signature_asset; subject_name: Joe Montana", prompt)
        self.assertIn("* Terry Bradshaw -> authentic signature image; role: signature_asset; subject_name: Terry Bradshaw", prompt)
        self.assertIn("For a two-player rivalry, retrieve one authentic signature for each rival.", prompt)
        self.assertIn("Never assign one player's signature to another player.", prompt)
        self.assertIn("Maximum signature images permitted in the entire carousel: 2", prompt)
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
        self.assertIn("For a multi-player design, retrieve one authentic signature for every principal named player", prompt)
        self.assertIn("Maximum signature images permitted in the entire carousel: 3", prompt)
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

        self.assertIn("Distinct named principal human subjects: 1", prompt)
        self.assertIn("Maximum signature images permitted in the entire carousel: 1", prompt)
        self.assertEqual(prompt.count("signature_slot_limit: 1"), 1)

    def test_find_images_shared_reference_balance_is_authoritative_and_ordered(self):
        prompt = design_studio_page.build_design_image_carousel_prompt(
            "Create Michael Jordan final shot collector artwork",
            "",
        )

        priority_headings = (
            "1. FEATURED PLAYER / HERO REFERENCES - HIGHEST PRIORITY",
            "2. VENUE / BACKGROUND REFERENCES - SECOND PRIORITY",
            "3. EQUIPMENT / TROPHY / HISTORICAL DETAIL REFERENCES - THIRD PRIORITY",
            "4. SIGNATURE REFERENCES - SUPPORTING REFERENCES ONLY AND ALWAYS LAST",
        )
        heading_positions = [prompt.index(heading) for heading in priority_headings]
        self.assertEqual(heading_positions, sorted(heading_positions))
        self.assertIn("Player and hero photographs must dominate the results.", prompt)
        self.assertIn("The clear majority of all non-signature results must be useful, high-quality player or hero photographs.", prompt)
        self.assertIn("Player/hero and venue/background references together must dominate the complete carousel.", prompt)
        self.assertIn("provide balanced coverage of every featured hero", prompt)
        self.assertIn("Never classify memorabilia-product photography as a background reference.", prompt)
        self.assertIn("Never return a second signature example for the same person.", prompt)
        self.assertIn("Never fill unused carousel positions with additional signature or autograph material.", prompt)
        self.assertIn("including a signed action photograph, consumes that person's one signature slot", prompt)
        self.assertIn("must not also count as a player, hero or action reference", prompt)
        self.assertIn("Never return several such items for the same person.", prompt)
        self.assertIn("Signature references must appear at the very end of the carousel", prompt)

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
                    prompt.count(design_studio_page.SPORTS_CAVE_SIGNATURE_IMAGE_SEARCH_RULES_MARKER),
                    1,
                )
                self.assertEqual(prompt.count("signature_slot_limit: 1"), expected_slots)
                self.assertIn(
                    f"Maximum signature images permitted in the entire carousel: {expected_slots}",
                    prompt,
                )

    def test_find_images_signature_search_skips_vehicle_or_venue_only_targets(self):
        prompt = design_studio_page.build_design_image_carousel_prompt(
            "Create vehicle-only Ford Mustang race car collector artwork",
            "",
        )

        self.assertEqual(prompt.count(design_studio_page.SPORTS_CAVE_SIGNATURE_IMAGE_SEARCH_RULES_MARKER), 1)
        self.assertIn("do not request a signature asset", prompt)
        self.assertNotIn("Ford Mustang -> authentic signature image", prompt)
        self.assertNotIn("race car -> authentic signature image", prompt)

    def test_find_images_signature_search_targets_named_motorsport_driver(self):
        prompt = design_studio_page.build_design_image_carousel_prompt(
            "Create Ayrton Senna Monaco driver collector artwork",
            "",
        )

        self.assertIn("* Ayrton Senna -> authentic signature image; role: signature_asset; subject_name: Ayrton Senna", prompt)

    def test_design_generation_prompt_uses_research_context_and_design_system(self):
        prompt = design_studio_page.build_design_generation_prompt("Bathurst Brock tribute")
        hero_marker = design_studio_page.DESIGN_STUDIO_HERO_DOMINANCE_MARKER
        border_marker = design_studio_page.DESIGN_STUDIO_LIMITED_EDITION_BORDER_MARKER
        containment_marker = design_studio_page.DESIGN_STUDIO_STRICT_BORDER_CONTAINMENT_MARKER
        signature_premium_marker = design_studio_page.SPORTS_CAVE_SIGNATURE_PREMIUM_TREATMENT_MARKER

        self.assertIn(
            "From the research and images above, create a premium Sports Cave limited-edition collector artwork",
            prompt,
        )
        self.assertIn("TASK:\nBathurst Brock tribute", prompt)
        self.assertIn("Bathurst Brock tribute", prompt)
        self.assertIn("Hero image: immutable principal subject asset", prompt)
        self.assertIn("Composite the original supplied subject unchanged into the generated Sports Cave environment.", prompt)
        self.assertIn("Background/support image: atmosphere, venue and story reference", prompt)
        self.assertIn("Detail references: factual accuracy references only", prompt)
        self.assertIn("Limited-edition plaque: exact supplied graphic asset to composite, not regenerate.", prompt)
        self.assertIn("Use the Sports Cave limited-edition plaque attached to this project", prompt)
        self.assertIn("This must feel like premium limited-edition sports wall art", prompt)
        self.assertIn("Realism and reference accuracy lock:", prompt)
        self.assertIn("Use the selected images as strict source assets and factual references according to their roles above.", prompt)
        self.assertIn("Do not redesign the athlete, driver, car, uniform, trophy, venue, or moment.", prompt)
        self.assertIn("Do not mirror images if it reverses numbers, logos, sponsor text, or kit details.", prompt)
        self.assertIn("legend + moment + nostalgia + darkness + subtle gold + framed collector energy", prompt)
        self.assertIn("Use a dark cinematic foundation:", prompt)
        self.assertIn("Use gold sparingly only for premium emphasis:", prompt)
        self.assertIn("It must never overpower the subject.", prompt)
        self.assertIn("If motorsport: realistic race cars", prompt)
        self.assertIn("Refine toward realism, emotion, collectibility, and wall-worthy bestseller potential.", prompt)
        self.assertEqual(prompt.count(hero_marker), 1)
        self.assertEqual(prompt.count(border_marker), 1)
        self.assertEqual(prompt.count(containment_marker), 1)
        self.assertEqual(
            prompt.count(design_studio_page._clean_prompt(design_studio_page.DESIGN_STUDIO_HERO_DOMINANCE_AND_BORDER_LOCK)),
            1,
        )
        self.assertIn("Use only the supplied main heroes.", prompt)
        self.assertIn("Do not invent, generate, duplicate, reconstruct, or add any additional athletes", prompt)
        self.assertIn("AI-generated background players", prompt)
        self.assertIn("recognisable individual people, faces, bodies or AI-generated players", prompt)
        self.assertIn("The supplied main heroes must carry the emotional and visual weight", prompt)
        self.assertIn("Keep the background minimal, cinematic, relevant and controlled.", prompt)
        self.assertIn("Every finished collector artwork must include a clean, precise and premium Sports Cave border", prompt)
        self.assertIn("The Sports Cave branded border is a hard containment boundary", prompt)
        self.assertIn("Every visual element must remain completely inside the inner edge of the border", prompt)
        self.assertIn("The border must always render as the uninterrupted topmost structural layer.", prompt)
        self.assertIn("Reduce its scale.", prompt)
        self.assertIn("Reposition it inward.", prompt)
        self.assertIn("Do not continue scenery, lighting, smoke, people, vehicles, typography or decorative effects outside the border.", prompt)
        self.assertNotIn(design_studio_page.SPORTS_CAVE_RIVALRY_COMPOSITION_RULES_MARKER, prompt)
        self.assertEqual(prompt.count(design_studio_page.SPORTS_CAVE_AUTHENTIC_SIGNATURE_APPLICATION_RULES_MARKER), 1)
        self.assertIn("AUTHENTIC SIGNATURE ASSETS", prompt)
        self.assertIn("Never invent, approximate, font-set, trace or regenerate a missing signature.", prompt)
        self.assertIn("Do not add claims such as:", prompt)
        self.assertIn("* Hand-signed", prompt)
        self.assertIn("unless the product is genuinely hand-signed", prompt)
        self.assertNotIn(signature_premium_marker, prompt)
        self.assertEqual(prompt.count(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER), 1)
        self.assertIn("GLOBAL PHOTOGRAPHIC REALISM RULES - MANDATORY", prompt)
        self.assertIn("ORIGINAL ARTWORK MODE - PRODUCT LOCK EXCLUSION", prompt)
        self.assertNotIn("Treat the uploaded full-resolution product as an immutable physical asset.", prompt)
        self.assertNotIn("SPORTS CAVE PRODUCT AND MOCKUP LOCK - MANDATORY", prompt)
        self.assertNotIn("Continue with this Sports Cave design system:", prompt)
        self.assertNotIn("Sports Cave Master Design System Prompt", prompt)

    def test_new_design_step_three_includes_subject_lock_once_before_creative_direction(self):
        prompt = design_studio_page.build_design_generation_prompt("Bathurst Brock tribute")
        marker = design_studio_page.DESIGN_STUDIO_SUBJECT_PRESERVATION_MARKER
        signature_marker = design_studio_page.SPORTS_CAVE_AUTHENTIC_SIGNATURE_APPLICATION_RULES_MARKER
        hero_marker = design_studio_page.DESIGN_STUDIO_HERO_DOMINANCE_MARKER
        border_marker = design_studio_page.DESIGN_STUDIO_LIMITED_EDITION_BORDER_MARKER
        containment_marker = design_studio_page.DESIGN_STUDIO_STRICT_BORDER_CONTAINMENT_MARKER

        self.assertTrue(prompt.startswith(marker))
        self.assertEqual(prompt.count(marker), 1)
        self.assertEqual(prompt.count(containment_marker), 1)
        self.assertLess(
            prompt.index("7. If any instruction conflicts with these rules"),
            prompt.index(signature_marker),
        )
        self.assertLess(
            prompt.index(signature_marker),
            prompt.index(hero_marker),
        )
        self.assertLess(prompt.index(border_marker), prompt.index(containment_marker))
        self.assertLess(prompt.index(containment_marker), prompt.index("TASK:\nBathurst Brock tribute"))
        self.assertLess(prompt.index(hero_marker), prompt.index("TASK:\nBathurst Brock tribute"))
        self.assertLess(prompt.index(marker), prompt.index("TASK:\nBathurst Brock tribute"))
        self.assertLess(prompt.index(marker), prompt.index("Reference roles:"))
        self.assertLess(prompt.index(marker), prompt.index("Create the artwork in landscape 4:3 ratio."))
        self.assertLess(prompt.index(marker), prompt.index("Sports Cave collector style:"))
        self.assertIn("USE THE ORIGINAL SUPPLIED SUBJECT IMAGE ITSELF.", prompt)
        self.assertIn("Do not face-swap the subject.", prompt)
        self.assertIn("The background and design will adapt to the subject.", prompt)

    def test_rivalry_step_three_prompt_includes_rivalry_rules_once_after_subject_lock(self):
        prompt = design_studio_page.build_design_generation_prompt(
            "Create a minimalist Messi vs Ronaldo face-off collector design"
        )
        subject_marker = design_studio_page.DESIGN_STUDIO_SUBJECT_PRESERVATION_MARKER
        rivalry_marker = design_studio_page.SPORTS_CAVE_RIVALRY_COMPOSITION_RULES_MARKER
        signature_marker = design_studio_page.SPORTS_CAVE_AUTHENTIC_SIGNATURE_APPLICATION_RULES_MARKER
        hero_marker = design_studio_page.DESIGN_STUDIO_HERO_DOMINANCE_MARKER

        self.assertEqual(prompt.count(subject_marker), 1)
        self.assertEqual(prompt.count(rivalry_marker), 1)
        self.assertEqual(prompt.count(signature_marker), 1)
        self.assertEqual(prompt.count(hero_marker), 1)
        self.assertLess(prompt.index(subject_marker), prompt.index(rivalry_marker))
        self.assertLess(prompt.index(rivalry_marker), prompt.index(signature_marker))
        self.assertLess(prompt.index(signature_marker), prompt.index(hero_marker))
        self.assertLess(prompt.index(hero_marker), prompt.index("TASK:\nCreate a minimalist Messi vs Ronaldo face-off collector design"))
        self.assertLess(prompt.index(rivalry_marker), prompt.index(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER))
        self.assertIn("The two opposing principal subjects are the only visual heroes.", prompt)
        self.assertIn("equal status, comparable scale and balanced visual weight", prompt)
        self.assertIn("MODE A — MINIMAL FACE-OFF RIVALRY", prompt)
        self.assertIn("MODE B — LEGENDS JERSEY-BACK COMPOSITION", prompt)
        self.assertIn("Never add anonymous players, generated athletes", prompt)
        self.assertIn("Background players", prompt)
        self.assertIn("The two opposing principal subjects must be co-equal heroes.", prompt)
        self.assertNotIn("The subject must be the hero.", prompt)
        self.assertIn("Use one authentic signature for each principal rival.", prompt)
        self.assertIn("Left hero -> left hero's authentic signature", prompt)
        self.assertIn("Right hero -> right hero's authentic signature", prompt)
        for example_name in ("Jordan", "Bryant", "Bradshaw", "Montana"):
            self.assertNotIn(example_name, prompt)

    def test_rivalry_text_triggers_activate_step_three_prompt(self):
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
                    prompt.count(design_studio_page.SPORTS_CAVE_RIVALRY_COMPOSITION_RULES_MARKER),
                    1,
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

        self.assertEqual(
            rivalry_prompt.count(design_studio_page.SPORTS_CAVE_RIVALRY_COMPOSITION_RULES_MARKER),
            1,
        )
        self.assertNotIn(
            design_studio_page.SPORTS_CAVE_RIVALRY_COMPOSITION_RULES_MARKER,
            single_subject_prompt,
        )

    def test_rivalry_rules_apply_once_to_all_final_artwork_routes_when_context_matches(self):
        generation_names = (
            "Upgrade Existing Design Prompt",
            "Expired Edition / Next Chapter Design Prompt",
            "Create Sports Cave Style Artwork Prompt",
        )

        prompts = [
            design_studio_page.build_design_generation_prompt("Create a rivalry design: Messi vs Ronaldo")
        ]
        prompts.extend(
            design_studio_page.build_design_studio_image_generation_prompt(
                design_studio_page.PROMPT_BOXES[prompt_name][0],
                design_context={"artwork_type": "rivalry"},
            )
            for prompt_name in generation_names
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
        signature_marker = design_studio_page.SPORTS_CAVE_AUTHENTIC_SIGNATURE_APPLICATION_RULES_MARKER
        premium_marker = design_studio_page.SPORTS_CAVE_SIGNATURE_PREMIUM_TREATMENT_MARKER
        prompt = design_studio_page.build_design_generation_prompt(
            "Create Joe Montana collector artwork",
            design_context={
                "principal_subjects": [{"name": "Joe Montana"}],
                "signature_assets": [
                    {
                        "subject_name": "Joe Montana",
                        "image_reference": "selected signature carousel image 4",
                    }
                ],
            },
        )

        self.assertEqual(prompt.count(signature_marker), 1)
        self.assertEqual(prompt.count(premium_marker), 1)
        self.assertLess(prompt.index(signature_marker), prompt.index(premium_marker))
        self.assertLess(prompt.index(premium_marker), prompt.index("COLLECTOR PLACEMENT"))
        self.assertIn("AUTHENTIC SIGNATURE ASSETS", prompt)
        self.assertIn("* Joe Montana -> selected signature carousel image 4", prompt)
        self.assertIn("Use only signature images selected from the Find Images carousel", prompt)
        self.assertIn("Composite the original signature mark itself", prompt)
        self.assertIn("Only use the supplied, selected or reliably sourced authentic signature belonging to the featured person.", prompt)
        self.assertIn("Preserve its genuine handwritten structure exactly", prompt)
        self.assertIn("* Natural pressure and line-weight variation", prompt)
        self.assertIn("* Overall width-to-height ratio", prompt)
        self.assertIn("Do not redraw, reinterpret, simplify, correct, beautify or replace the authentic signature.", prompt)
        self.assertIn("Present the authentic signature as a thin, elegant and restrained collector detail.", prompt)
        self.assertIn("Preserve genuine stroke variation while ensuring the overall presentation remains visually light", prompt)
        self.assertIn("* Thick or chunky signature rendering", prompt)
        self.assertIn("* Generic cursive fonts", prompt)
        self.assertIn("* Signatures placed outside the Sports Cave border", prompt)
        self.assertIn("* Remain fully inside the Sports Cave branded border", prompt)
        self.assertIn("The signature adds authenticity and collector value. It must never become the dominant visual element.", prompt)

    def test_final_generation_signature_fallback_never_generates_missing_signature(self):
        prompt = design_studio_page.build_design_generation_prompt("Create vehicle-only Mount Panorama circuit artwork")

        self.assertEqual(prompt.count(design_studio_page.SPORTS_CAVE_AUTHENTIC_SIGNATURE_APPLICATION_RULES_MARKER), 1)
        self.assertNotIn(design_studio_page.SPORTS_CAVE_SIGNATURE_PREMIUM_TREATMENT_MARKER, prompt)
        self.assertIn("If a listed subject has no valid authentic signature asset, omit only that signature.", prompt)
        self.assertIn("Do not generate one.", prompt)
        self.assertIn("Do not use a script font.", prompt)
        self.assertIn("Do not approximate the athlete's autograph.", prompt)
        self.assertIn("For a rivalry, never duplicate the available rival's signature", prompt)

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

        prompts = [
            design_studio_page.build_design_generation_prompt(
                "Create Joe Montana collector artwork",
                design_context=signature_context,
            )
        ]
        prompts.extend(
            design_studio_page.build_design_studio_image_generation_prompt(
                design_studio_page.PROMPT_BOXES[prompt_name][0],
                design_context=signature_context,
            )
            for prompt_name in generation_names
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
        self.assertIn("* Michael Jordan -> selected signature image reference for Michael Jordan", prompt)
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

        self.assertEqual(prompt.count(design_studio_page.SPORTS_CAVE_SIGNATURE_PREMIUM_TREATMENT_MARKER), 1)
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

    def test_signature_premium_treatment_is_idempotent_when_signature_selected(self):
        premium_marker = design_studio_page.SPORTS_CAVE_SIGNATURE_PREMIUM_TREATMENT_MARKER
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
        twice = design_studio_page.build_design_studio_image_generation_prompt(
            once,
            design_context=design_context,
        )

        self.assertEqual(once, twice)
        self.assertEqual(twice.count(premium_marker), 1)
        self.assertEqual(twice.count(design_studio_page.SPORTS_CAVE_AUTHENTIC_SIGNATURE_APPLICATION_RULES_MARKER), 1)
        self.assertLess(twice.index(premium_marker), twice.index("COLLECTOR PLACEMENT"))

    def test_rivalry_composition_is_idempotent(self):
        marker = design_studio_page.SPORTS_CAVE_RIVALRY_COMPOSITION_RULES_MARKER
        once = design_studio_page.build_design_generation_prompt("Create a motorsport rivalry design: Brock vs Moffat")
        twice = design_studio_page.build_design_studio_image_generation_prompt(once)

        self.assertEqual(once, twice)
        self.assertEqual(twice.count(marker), 1)
        self.assertEqual(twice.count(design_studio_page.SPORTS_CAVE_AUTHENTIC_SIGNATURE_APPLICATION_RULES_MARKER), 1)
        self.assertEqual(twice.count(design_studio_page.DESIGN_STUDIO_SUBJECT_PRESERVATION_MARKER), 1)
        self.assertEqual(twice.count(design_studio_page.DESIGN_STUDIO_HERO_DOMINANCE_MARKER), 1)
        self.assertEqual(twice.count(design_studio_page.DESIGN_STUDIO_STRICT_BORDER_CONTAINMENT_MARKER), 1)
        self.assertEqual(twice.count(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER), 1)

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

    def test_new_design_tab_is_second_after_upgrade_existing_design(self):
        source = (ROOT / "design_studio_page.py").read_text(encoding="utf-8")
        tabs_source = source[
            source.index("upgrade_tab, research_tab") : source.index("\n\n    with upgrade_tab:")
        ]

        self.assertLess(
            tabs_source.index('"Upgrade Existing Design"'),
            tabs_source.index('"New Design"'),
        )
        self.assertLess(
            tabs_source.index('"New Design"'),
            tabs_source.index('"Update Expired Edition"'),
        )

    def test_new_design_renderer_has_three_steps_in_order(self):
        source = (ROOT / "design_studio_page.py").read_text(encoding="utf-8")
        renderer = source[
            source.index("def render_new_design_tab") : source.index("\n\ndef _render_prompt_box")
        ]

        self.assertLess(renderer.index("Step 1 - Research"), renderer.index("Step 2 - Find Images"))
        self.assertLess(renderer.index("Step 2 - Find Images"), renderer.index("Step 3 - Generate Design"))
        self.assertIn("Choose design task", renderer)
        self.assertIn("No new design tasks waiting", renderer)
        self.assertNotIn("Paste research answer", renderer)
        self.assertIn("Copy Find Images Prompt", renderer)


if __name__ == "__main__":
    unittest.main()
