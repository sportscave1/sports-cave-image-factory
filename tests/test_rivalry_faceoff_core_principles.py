import unittest

import design_studio_page
import design_studio_styles


DETAILS = {
    "sport": "Basketball",
    "principal_subject_one": "Michael Jordan",
    "principal_subject_two": "Kobe Bryant",
    "team_country": "Chicago Bulls / Los Angeles Lakers",
    "season_era": "1990s-2000s",
    "event_moment": "Two generations compared",
    "special_instructions": "Respect mixed with competitive tension",
}

ASSETS = (
    {
        "file_path": "jordan-photo.jpg",
        "role": "rival_one_photo",
        "subject_name": "Michael Jordan",
    },
    {
        "file_path": "bryant-photo.jpg",
        "role": "rival_two_photo",
        "subject_name": "Kobe Bryant",
    },
    {
        "file_path": "jordan-signature.png",
        "role": "signature_asset",
        "subject_name": "Michael Jordan",
    },
    {
        "file_path": "bryant-signature.png",
        "role": "signature_asset",
        "subject_name": "Kobe Bryant",
    },
    {
        "file_path": "sports-cave-plaque.png",
        "role": "plaque_asset",
    },
)


class RivalryFaceOffCorePrinciplesTests(unittest.TestCase):
    def test_style_keeps_exactly_two_principals_and_only_signature_optional(self):
        style = design_studio_styles.get_design_style("rivalry_faceoff")

        self.assertEqual(style.minimum_named_principals, 2)
        self.assertEqual(style.exact_named_principals, 2)
        self.assertEqual(style.required_image_roles, ("rival_one_photo", "rival_two_photo"))
        self.assertEqual(style.optional_image_roles, ("signature_asset",))

    def test_research_selects_one_unique_rivalry_hook_and_title(self):
        prompt = design_studio_styles.build_research_prompt(
            "rivalry_faceoff",
            "Create a Jordan and Bryant rivalry face-off",
            DETAILS,
        )

        self.assertIn("Identify what makes these two named principals a meaningful rivalry", prompt)
        self.assertIn("return only the single strongest rivalry-specific title", prompt)
        self.assertIn("Do not return a menu of competing concepts", prompt)
        self.assertIn("THE MENTALITY only as a benchmark", prompt)
        self.assertIn("Do not reuse its title, portrait positions, smoke pattern", prompt)
        self.assertIn("PRINCIPAL ONE: Michael Jordan", prompt)
        self.assertIn("PRINCIPAL TWO: Kobe Bryant", prompt)
        self.assertIn("RIVALRY STORY: Two generations compared Respect mixed", prompt)

    def test_find_images_returns_only_portraits_and_one_signature_per_principal(self):
        prompt = design_studio_styles.build_find_images_prompt(
            "rivalry_faceoff",
            "Create a Jordan and Bryant rivalry face-off",
            DETAILS,
        )
        style_section = prompt.split("STYLE PHOTO TARGETS - Rivalry Face-Off", 1)[1]

        self.assertIn("overrides the general allowance for a shared moment", style_section)
        self.assertIn("three strongest compatible final-use photographs", style_section)
        self.assertIn("one clearest verified signature candidate last", style_section)
        self.assertIn("Do not return stadiums, venues, crowds, shared moments", style_section)
        self.assertIn("Never manufacture eye contact", style_section)
        self.assertIn("Required: rival_one_photo, rival_two_photo. Optional: signature_asset", prompt)
        self.assertNotIn("Optional: vehicle_exact_photo", prompt)
        self.assertNotIn("Optional: venue_reference", prompt)

    def test_generation_uses_benchmark_without_reskinning_it(self):
        prompt = design_studio_styles.build_generation_prompt(
            "rivalry_faceoff",
            "Create a Jordan and Bryant rivalry face-off",
            DETAILS,
            ASSETS,
        )
        marker = design_studio_styles.RIVALRY_FACE_OFF_CORE_PRINCIPLES_MARKER

        self.assertEqual(prompt.count(marker), 1)
        self.assertIn("THE MENTALITY is a benchmark only", prompt)
        self.assertIn("Do not recreate, duplicate or reskin it", prompt)
        self.assertIn("Do not reuse its title, exact portrait positions, smoke pattern", prompt)
        self.assertIn("its own title, atmosphere, identity and emotional reason to exist", prompt)

    def test_generation_enforces_one_title_and_close_two_person_composition(self):
        prompt = design_studio_styles.build_generation_prompt(
            "rivalry_faceoff",
            "Create a Jordan and Bryant rivalry face-off",
            DETAILS,
            ASSETS,
        )

        self.assertIn("Use exactly two principal rivals. No third person.", prompt)
        self.assertIn("close portrait, head-and-shoulders or upper-torso", prompt)
        self.assertIn("ONE ORIGINAL COLLECTOR TITLE ONLY", prompt)
        self.assertIn("usually contain one to four words", prompt)
        self.assertIn("Show no subtitle, Legacy Edition, Rivalry Edition", prompt)
        self.assertIn("unless the user explicitly requests a special-release secondary line", prompt)

    def test_generation_preserves_photos_signatures_names_and_exact_plaque(self):
        prompt = design_studio_styles.build_generation_prompt(
            "rivalry_faceoff",
            "Create a Jordan and Bryant rivalry face-off",
            DETAILS,
            ASSETS,
        )

        self.assertIn("immutable source asset", prompt)
        self.assertIn("Do not mirror, rotate, repose or reconstruct either person", prompt)
        self.assertIn("Never regenerate a face, face-swap, turn a head", prompt)
        self.assertIn("* Michael Jordan -> jordan-signature.png", prompt)
        self.assertIn("* Kobe Bryant -> bryant-signature.png", prompt)
        self.assertIn("Use the exact supplied official Sports Cave plaque asset", prompt)
        self.assertIn("SPORTS CAVE COLLECTOR SERIES wording", prompt)
        self.assertIn("001 / 100 numbering", prompt)
        self.assertIn("* Sports Cave limited-edition plaque -> sports-cave-plaque.png", prompt)

    def test_generation_requires_unique_restrained_collector_identity(self):
        prompt = design_studio_styles.build_generation_prompt(
            "rivalry_faceoff",
            "Create a Jordan and Bryant rivalry face-off",
            DETAILS,
            ASSETS,
        )

        self.assertIn("deep-black or charcoal foundation", prompt)
        self.assertIn("Do not reuse one smoke, split-colour, subject-placement or lighting template", prompt)
        self.assertIn("landscape 4:3, framed-first and photographically realistic", prompt)
        self.assertIn("one thin refined symmetrical gold border fully inside the canvas", prompt)
        self.assertIn("Use both correctly spelled full principal names", prompt)

    def test_signature_pass_preserves_one_correct_signature_per_side(self):
        prompt = design_studio_styles.build_signature_placement_prompt(
            "rivalry_faceoff",
            "Create a Jordan and Bryant rivalry face-off",
            DETAILS,
            ASSETS,
        )

        self.assertIn("RIVALRY FACE-OFF SIGNATURE PLACEMENT", prompt)
        self.assertIn("exactly one verified authentic signature for each principal", prompt)
        self.assertIn("correctly mapped principal's side", prompt)
        self.assertIn("Do not cross the central rivalry space", prompt)

    def test_review_rejects_benchmark_reskins_and_secondary_titles(self):
        prompt = design_studio_styles.build_harsh_review_prompt(
            "rivalry_faceoff",
            "Create a Jordan and Bryant rivalry face-off",
            DETAILS,
            ASSETS,
        )

        self.assertIn("Reject the artwork if it resembles a reskin of THE MENTALITY", prompt)
        self.assertIn("includes a subtitle, edition label, tagline, supporting line or second headline", prompt)
        self.assertIn("one verified authentic signature per rival", prompt)
        self.assertIn("genuinely specific to this rivalry", prompt)

    def test_legacy_wrapper_uses_same_core_contract_and_non_rivalry_stays_clean(self):
        marker = design_studio_styles.RIVALRY_FACE_OFF_CORE_PRINCIPLES_MARKER
        legacy = design_studio_page.build_design_studio_image_generation_prompt(
            "Create premium artwork",
            design_context={"metadata": {"design_type": "rivalry"}},
        )
        non_rivalry = design_studio_styles.build_generation_prompt(
            "minimalist_hero",
            "Create Michael Jordan collector artwork",
            {"sport": "Basketball", "principal_subject_one": "Michael Jordan"},
        )

        self.assertEqual(legacy.count(marker), 1)
        self.assertEqual(
            design_studio_page.SPORTS_CAVE_RIVALRY_COMPOSITION_RULES_V1.count(marker),
            1,
        )
        self.assertNotIn("MODE B — LEGENDS JERSEY-BACK COMPOSITION", legacy)
        self.assertNotIn(marker, non_rivalry)


if __name__ == "__main__":
    unittest.main()
