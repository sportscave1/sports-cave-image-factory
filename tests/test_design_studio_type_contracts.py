import hashlib
import unittest
from difflib import SequenceMatcher

import design_studio_styles


EXPECTED_TYPES = {
    "ultimate_moment": ("Ultimate Moment", "ONE DEFINING COMMERCIAL INSTANT"),
    "rivalry_faceoff": ("Rivalry Face-Off", "BALANCED COMPETITIVE TENSION"),
    "legends_jersey_display": ("Legends Jersey Display", "LOCKED REAR-JERSEY SERIES"),
    "nostalgic_tribute": ("Nostalgic Tribute", "A MEMORY OF THE ERA"),
    "motorsport_driver_car": ("Motorsport: Driver & Car", "ONE HISTORICALLY MATCHED MACHINE"),
    "minimalist_hero": ("Minimalist Hero", "ONE SUBJECT, ONE IDEA, CONTROLLED SPACE"),
    "championship_achievement": ("Championship / Achievement", "VISIBLE VERIFIED EVIDENCE"),
    "vintage_restoration": ("Vintage Restoration", "THE ORIGINAL FRAME IS THE ARTEFACT"),
    "update_existing": ("Update Existing Design", "SURGICAL CHANGE ONLY"),
}


def details_for(style_slug):
    details = {
        "design_title": "Verified collector concept",
        "sport": "Cricket",
        "principal_subject_one": "Alex Example",
        "team_country": "Australia",
        "season_era": "1999",
        "event_moment": "Verified final moment",
        "venue_location": "Melbourne",
        "uniform_equipment_livery": "Verified match uniform",
    }
    if style_slug in {"rivalry_faceoff", "legends_jersey_display"}:
        details["principal_subject_two"] = "Jordan Example"
    if style_slug == "update_existing":
        details["principal_subject_one"] = ""
    return details


def selected_assets_for(style_slug):
    style = design_studio_styles.get_design_style(style_slug)
    assets = []
    for index, role in enumerate(style.required_image_roles, start=1):
        subject = "Alex Example"
        if role in {"rival_two_photo", "rear_jersey_two"}:
            subject = "Jordan Example"
        assets.append(
            {
                "asset_id": f"asset-{style_slug}-{index}",
                "role": role,
                "subject_name": subject if role != "plaque_asset" else "",
            }
        )
    assets.append(
        {
            "asset_id": f"signature-{style_slug}-one",
            "role": "signature_asset",
            "subject_name": "Alex Example",
        }
    )
    if style_slug in {"rivalry_faceoff", "legends_jersey_display"}:
        assets.append(
            {
                "asset_id": f"signature-{style_slug}-two",
                "role": "signature_asset",
                "subject_name": "Jordan Example",
            }
        )
    return assets


class DesignStudioTypeContractTests(unittest.TestCase):
    def test_registry_keeps_the_exact_nine_existing_types(self):
        self.assertEqual(
            {style.slug: style.label for style in design_studio_styles.get_style_registry().values()},
            {slug: values[0] for slug, values in EXPECTED_TYPES.items()},
        )

    def test_every_type_has_complete_dedicated_contract_routing(self):
        self.assertEqual(set(design_studio_styles.STYLE_TYPE_CONTRACTS), set(EXPECTED_TYPES))
        self.assertEqual(set(design_studio_styles.STYLE_SIGNATURE_PLACEMENT_RULES), set(EXPECTED_TYPES))
        self.assertEqual(set(design_studio_styles.STYLE_TARGETED_CORRECTION_RULES), set(EXPECTED_TYPES))

        for slug, (label, unique_marker) in EXPECTED_TYPES.items():
            with self.subTest(style=slug):
                details = details_for(slug)
                assets = selected_assets_for(slug)
                bundle = design_studio_styles.build_prompt_bundle(
                    slug,
                    "Create the verified Sports Cave artwork.",
                    details,
                    assets,
                )
                self.assertEqual(bundle["errors"], [])
                self.assertTrue(bundle["research"].startswith(f"SELECTED DESIGN TYPE: {label}"))
                self.assertTrue(bundle["generation"].startswith(f"SELECTED DESIGN TYPE: {label}"))
                for stage in ("research", "find_images", "generation", "signature_placement", "review"):
                    self.assertIn(f"SELECTED DESIGN TYPE: {label}", bundle[stage])
                    self.assertIn(unique_marker, bundle[stage])

    def test_type_contracts_and_assembled_generation_prompts_are_materially_distinct(self):
        contracts = design_studio_styles.STYLE_TYPE_CONTRACTS
        slugs = list(EXPECTED_TYPES)
        generation_hashes = set()
        for index, first_slug in enumerate(slugs):
            first_contract = contracts[first_slug]
            generation = design_studio_styles.build_generation_prompt(
                first_slug,
                "Create the verified Sports Cave artwork.",
                details_for(first_slug),
                selected_assets_for(first_slug),
            )
            generation_hashes.add(hashlib.sha256(generation.encode("utf-8")).hexdigest())
            for second_slug in slugs[index + 1 :]:
                similarity = SequenceMatcher(None, first_contract, contracts[second_slug]).ratio()
                self.assertLess(similarity, 0.50, (first_slug, second_slug, similarity))
        self.assertEqual(len(generation_hashes), len(EXPECTED_TYPES))

    def test_shared_source_realism_and_signature_safety_reach_every_generation(self):
        for slug, (label, _marker) in EXPECTED_TYPES.items():
            with self.subTest(style=slug):
                prompt = design_studio_styles.build_generation_prompt(
                    slug,
                    "Create the verified Sports Cave artwork.",
                    details_for(slug),
                    selected_assets_for(slug),
                )
                self.assertIn(f"SELECTED DESIGN TYPE: {label}", prompt)
                self.assertIn("AUTHENTIC SOURCE ASSET LOCK - IMMUTABLE AFTER APPROVAL", prompt)
                self.assertIn("Never redraw or regenerate a face", prompt)
                self.assertIn("Do not mirror", prompt)
                self.assertIn("PHOTOGRAPHIC REALISM AND ANATOMY LOCK - MANDATORY", prompt)
                self.assertIn("Maintain natural skin pores and realistic subsurface scattering", prompt)
                self.assertIn("VERIFIED SIGNATURE CONTRACT - NO GENERATION OR APPROXIMATION", prompt)
                self.assertIn("SIGNATURE UNAVAILABLE", prompt)

    def test_find_images_requires_visible_cards_complete_metadata_and_real_image_inputs(self):
        for slug in EXPECTED_TYPES:
            with self.subTest(style=slug):
                prompt = design_studio_styles.build_find_images_prompt(
                    slug,
                    "Find the exact approved sources.",
                    details_for(slug),
                )
                self.assertIn("actual tool-native image-result card or supported inline", prompt)
                self.assertIn("available resolution", prompt)
                self.assertIn("estimated useful resolution", prompt)
                self.assertIn("use mode", prompt.casefold())
                self.assertIn("actual image inputs", prompt)
                self.assertNotIn("a plain webpage link is a completed result", prompt.casefold())

    def test_signature_placement_is_verified_locked_and_type_specific(self):
        prompts = {}
        for slug, (label, unique_marker) in EXPECTED_TYPES.items():
            prompt = design_studio_styles.build_signature_placement_prompt(
                slug,
                "Place verified signatures.",
                details_for(slug),
                selected_assets_for(slug),
            )
            prompts[slug] = prompt
            self.assertIn(f"SELECTED DESIGN TYPE: {label}", prompt)
            self.assertIn(unique_marker, prompt)
            self.assertIn(f"TYPE-SPECIFIC SIGNATURE PLACEMENT - {label}", prompt)
            self.assertIn("Never invent, approximate, trace, redraw", prompt)
            self.assertIn("Preserve the complete approved artwork unchanged", prompt)
        self.assertEqual(len(set(prompts.values())), len(EXPECTED_TYPES))

    def test_review_fails_unrecognisable_type_and_emits_locked_correction_handoff(self):
        for slug, (label, unique_marker) in EXPECTED_TYPES.items():
            with self.subTest(style=slug):
                prompt = design_studio_styles.build_harsh_review_prompt(
                    slug,
                    "Review this artwork.",
                    details_for(slug),
                    selected_assets_for(slug),
                )
                self.assertIn(f"SELECTED DESIGN TYPE: {label}", prompt)
                self.assertIn(unique_marker, prompt)
                self.assertIn("STYLE CONTRACT: PASS or FAIL", prompt)
                self.assertIn("not immediately recognisable", prompt)
                self.assertIn("capped at 6/10", prompt)
                self.assertIn(design_studio_styles.TARGETED_CORRECTION_EDIT_LOCK, prompt)
                self.assertIn(f"TYPE-SPECIFIC CORRECTION BOUNDARY - {label}", prompt)

    def test_targeted_correction_starts_with_exact_edit_lock_and_preserves_type(self):
        prompts = {}
        for slug, (label, unique_marker) in EXPECTED_TYPES.items():
            prompt = design_studio_styles.build_targeted_correction_prompt(
                slug,
                "Correct the approved artwork.",
                "Correct only the identified left hand.",
                details_for(slug),
                selected_assets_for(slug),
            )
            prompts[slug] = prompt
            self.assertTrue(prompt.startswith(design_studio_styles.TARGETED_CORRECTION_EDIT_LOCK))
            self.assertIn(f"SELECTED DESIGN TYPE: {label}", prompt)
            self.assertIn(unique_marker, prompt)
            self.assertIn("SPECIFIC CORRECTION: Correct only the identified left hand.", prompt)
            self.assertIn("PHOTOGRAPHIC REALISM AND ANATOMY LOCK", prompt)
        self.assertEqual(len(set(prompts.values())), len(EXPECTED_TYPES))

    def test_existing_bundle_schema_and_task_variables_are_unchanged(self):
        bundle = design_studio_styles.build_prompt_bundle(
            "minimalist_hero",
            "Create a restrained hero artwork.",
            details_for("minimalist_hero"),
            selected_assets_for("minimalist_hero"),
        )
        self.assertEqual(
            list(bundle),
            ["errors", "research", "find_images", "generation", "signature_placement", "review"],
        )
        for stage in ("research", "find_images", "generation", "signature_placement", "review"):
            self.assertIn("TASK VARIABLES", bundle[stage])
            self.assertIn("SPORT: Cricket", bundle[stage])
            self.assertIn("PRINCIPAL SUBJECTS: Alex Example", bundle[stage])


if __name__ == "__main__":
    unittest.main()
