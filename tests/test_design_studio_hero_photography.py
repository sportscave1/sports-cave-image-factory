import inspect
import unittest

import design_studio_page
import design_studio_styles


class DesignStudioInlineImageContractTests(unittest.TestCase):
    def test_find_images_requires_visible_tool_native_images_not_links(self):
        prompt = design_studio_styles.build_find_images_prompt(
            "minimalist_hero",
            "Michael Jordan minimalist collector artwork",
            {
                "sport": "Basketball",
                "principal_subject_one": "Michael Jordan",
            },
        )

        self.assertIn("dedicated image-search capability", prompt)
        self.assertIn("actual tool-native image-result card", prompt)
        self.assertIn("A source URL, markdown link, filename or text description by itself is not an image result", prompt)
        self.assertIn("replace it with the next suitable authentic candidate", prompt)
        self.assertIn("source-page attribution link", prompt)
        self.assertIn("asset_id", prompt)
        self.assertIn("use_mode", prompt)

    def test_rivalry_principal_and_signature_result_limits_remain_exact(self):
        prompt = design_studio_styles.build_find_images_prompt(
            "rivalry_faceoff",
            "Peter Brock vs Allan Moffat",
            {
                "sport": "Motorsport",
                "principal_subject_one": "Peter Brock",
                "principal_subject_two": "Allan Moffat",
            },
        )

        self.assertIn("exact two-group candidate and signature limits", prompt)
        self.assertIn("three strongest compatible final-use photographs", prompt)
        self.assertIn("one clearest verified signature candidate last", prompt)
        self.assertIn("Do not return stadiums, venues, crowds, shared moments", prompt)
        self.assertIn("Required: rival_one_photo, rival_two_photo. Optional: signature_asset", prompt)
        self.assertNotIn("no more than one relevant venue or shared-moment image", prompt)
        self.assertNotIn("Optional: venue_reference", prompt)

    def test_legacy_find_images_builder_carries_the_same_inline_contract(self):
        prompt = design_studio_page.build_design_image_carousel_prompt(
            "Michael Jordan final shot",
            "Use the 1998 Finals moment.",
            design_context={"principal_subject_one": "Michael Jordan"},
        )

        self.assertEqual(
            prompt.count(design_studio_styles.HERO_PHOTOGRAPHIC_DOMINANCE_CONTRACT_MARKER),
            1,
        )
        self.assertEqual(prompt.count("INLINE IMAGE RESULT CONTRACT"), 1)
        self.assertIn("actual tool-native image-result card", prompt)
        self.assertIn("RESEARCH BRIEF: Use the 1998 Finals moment.", prompt)


class DesignStudioHeroDominanceContractTests(unittest.TestCase):
    def test_shared_contract_is_applied_to_all_required_v2_stages(self):
        cases = (
            ("minimalist_hero", "Michael Jordan minimalist hero", {"sport": "Basketball", "principal_subject_one": "Michael Jordan"}),
            ("rivalry_faceoff", "Peter Brock vs Allan Moffat", {"sport": "Motorsport", "principal_subject_one": "Peter Brock", "principal_subject_two": "Allan Moffat"}),
            ("nostalgic_tribute", "Shane Warne MCG tribute", {"sport": "Cricket", "principal_subject_one": "Shane Warne"}),
            ("championship_achievement", "Specific sporting moment", {"sport": "Basketball", "principal_subject_one": "Jalen Brunson"}),
            ("vintage_restoration", "Historical low-resolution subject", {"sport": "Motorsport", "event_moment": "One-Two Finish"}),
        )

        for style, task, details in cases:
            bundle = design_studio_styles.build_prompt_bundle(style, task, details)
            with self.subTest(style=style):
                for stage in ("research", "find_images", "generation", "review"):
                    self.assertEqual(
                        bundle[stage].count(
                            design_studio_styles.HERO_PHOTOGRAPHIC_DOMINANCE_CONTRACT_MARKER
                        ),
                        1,
                    )

    def test_research_requires_a_composition_ready_photo_brief(self):
        prompt = design_studio_styles.build_research_prompt(
            "minimalist_hero",
            "Michael Jordan minimalist hero",
            {"sport": "Basketball", "principal_subject_one": "Michael Jordan"},
        )

        for phrase in (
            "required chest-up, waist-up or three-quarter crop",
            "desired expression and emotional tone",
            "correct uniform, number, equipment and era",
            "primary or secondary asset role",
            "minimum useful resolution after the intended crop",
            "distant or unsuitable full-body treatments to reject",
        ):
            self.assertIn(phrase, prompt)

    def test_single_and_two_hero_scale_rules_are_explicit(self):
        contract = design_studio_styles.HERO_PHOTOGRAPHIC_DOMINANCE_CONTRACT
        self.assertIn("60-80% of the usable artwork height", contract)
        self.assertIn("recognisable at Shopify-thumbnail size", contract)
        self.assertIn("both principals dominant with comparable facial importance", contract)
        self.assertIn("small background ghost", contract)
        self.assertIn("fully inside the Sports Cave border", contract)

    def test_distant_full_body_and_low_resolution_sources_are_rejected(self):
        prompt = design_studio_styles.build_find_images_prompt(
            "nostalgic_tribute",
            "Historical low-resolution tribute",
            {"sport": "Cricket", "principal_subject_one": "Shane Warne"},
        )

        self.assertIn("distant crowd shots", prompt)
        self.assertIn("full-body sources that cannot support a strong close crop", prompt)
        self.assertIn("at least 1200 pixels on the useful crop axis", prompt)
        self.assertIn("2000 pixels or more is ideal", prompt)
        self.assertIn("Judge resolution on the intended crop", prompt)

    def test_immutable_source_and_no_reconstruction_rules_remain(self):
        contract = design_studio_styles.HERO_PHOTOGRAPHIC_DOMINANCE_CONTRACT
        self.assertIn("non-generative cropping", contract)
        self.assertIn("proportional scaling", contract)
        self.assertIn("Never redraw or regenerate a face", contract)
        self.assertIn("invent missing limbs", contract)
        self.assertIn("combine a face from one source with a body from another", contract)

    def test_generation_requires_visible_asset_validation_before_artwork(self):
        prompt = design_studio_styles.build_generation_prompt(
            "rivalry_faceoff",
            "Peter Brock vs Allan Moffat",
            {
                "sport": "Motorsport",
                "principal_subject_one": "Peter Brock",
                "principal_subject_two": "Allan Moffat",
            },
            [
                {"file_path": "brock.jpg", "role": "rival_one_photo", "subject_name": "Peter Brock"},
                {"file_path": "moffat.jpg", "role": "rival_two_photo", "subject_name": "Allan Moffat"},
            ],
        )

        self.assertIn("VISIBLE PRE-GENERATION ASSET VALIDATION", prompt)
        self.assertIn("one concise PASS/REPLACE line per selected hero asset", prompt)
        self.assertIn("landscape 4:3 Sports Cave border", prompt)
        self.assertIn("Build the background around the available hero crop", prompt)
        self.assertIn("Do not shrink principals", prompt)

    def test_names_signatures_plaque_roles_and_use_modes_are_preserved(self):
        prompt = design_studio_styles.build_generation_prompt(
            "rivalry_faceoff",
            "Peter Brock vs Allan Moffat",
            {
                "sport": "Motorsport",
                "principal_subject_one": "Peter Brock",
                "principal_subject_two": "Allan Moffat",
            },
            [
                {"file_path": "brock.jpg", "role": "rival_one_photo", "subject_name": "Peter Brock"},
                {"file_path": "moffat.jpg", "role": "rival_two_photo", "subject_name": "Allan Moffat"},
                {"file_path": "brock-signature.png", "role": "signature_asset", "subject_name": "Peter Brock"},
                {"file_path": "moffat-signature.png", "role": "signature_asset", "subject_name": "Allan Moffat"},
                {"file_path": "plaque.png", "role": "plaque_asset"},
            ],
        )

        self.assertIn("brock.jpg | role=rival_one_photo | use_mode=visible_cutout", prompt)
        self.assertIn("moffat.jpg | role=rival_two_photo | use_mode=visible_cutout", prompt)
        self.assertIn("* Peter Brock -> brock-signature.png", prompt)
        self.assertIn("* Allan Moffat -> moffat-signature.png", prompt)
        self.assertIn("plaque.png | role=plaque_asset", prompt)
        self.assertIn("landscape 4:3", prompt)

    def test_harsh_review_has_every_new_score_cap_and_allows_ten(self):
        prompt = design_studio_styles.build_harsh_review_prompt(
            "minimalist_hero",
            "Michael Jordan minimalist hero",
            {"sport": "Basketball", "principal_subject_one": "Michael Jordan"},
        )

        self.assertIn("may score 10/10", prompt)
        self.assertIn("too small to recognise at thumbnail size", prompt)
        self.assertIn("distant or full-body source materially weakens", prompt)
        self.assertIn("minor background element", prompt)
        self.assertIn("contained only links instead of visible candidates", prompt)
        self.assertIn("replacing only that source photograph through Find Images", prompt)


class DesignStudioPromptDeliveryRegressionTests(unittest.TestCase):
    def test_copy_path_serializes_the_complete_prompt_without_sanitising_it(self):
        card_source = inspect.getsource(design_studio_page._render_v2_prompt_card)
        copy_source = inspect.getsource(design_studio_page._render_copy_button)
        self.assertIn("_render_copy_button(prompt_text", card_source)
        self.assertIn("prompt_json = json.dumps(prompt_text)", copy_source)
        self.assertIn("navigator.clipboard.writeText(promptText)", copy_source)

    def test_legacy_task_substitution_and_stage_order_are_unchanged(self):
        task = "Kobe Bryant final game tribute"
        research = design_studio_page.build_design_research_prompt(task)
        generation = design_studio_page.build_design_generation_prompt(task)
        renderer = inspect.getsource(design_studio_page.render_design_studio_v2)

        self.assertIn(task, research)
        self.assertIn(task, generation)
        self.assertLess(renderer.index("Research Prompt"), renderer.index("Find Images Prompt"))
        self.assertLess(renderer.index("Find Images Prompt"), renderer.index("Design Generation Prompt"))
        self.assertLess(renderer.index("Design Generation Prompt"), renderer.index("Signature Placement Prompt"))
        self.assertLess(renderer.index("Signature Placement Prompt"), renderer.rindex("Harsh Review"))


if __name__ == "__main__":
    unittest.main()
