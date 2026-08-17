import inspect
from pathlib import Path
import unittest

import design_studio_page
import design_studio_styles
import run_migrations


STYLE_DETAILS = {
    "ultimate_moment": {
        "sport": "NFL",
        "event_moment": "The Catch",
    },
    "rivalry_faceoff": {
        "sport": "Motorsport",
        "principal_subject_one": "Peter Brock",
        "principal_subject_two": "Allan Moffat",
    },
    "legends_jersey_display": {
        "sport": "Football",
        "principal_subject_one": "Lionel Messi",
        "principal_subject_two": "Cristiano Ronaldo",
    },
    "nostalgic_tribute": {
        "sport": "Cricket",
        "principal_subject_one": "Shane Warne",
    },
    "motorsport_driver_car": {
        "sport": "Motorsport",
        "principal_subject_one": "Peter Brock",
    },
    "minimalist_hero": {
        "sport": "Basketball",
        "principal_subject_one": "Michael Jordan",
    },
    "championship_achievement": {
        "sport": "Basketball",
        "principal_subject_one": "Jalen Brunson",
    },
    "vintage_restoration": {
        "sport": "Motorsport",
        "event_moment": "One-Two Finish",
    },
    "update_existing": {},
}


class DesignStudioStyleRegistryTests(unittest.TestCase):
    def test_registry_contains_the_nine_stable_unique_styles(self):
        expected = (
            "ultimate_moment",
            "rivalry_faceoff",
            "legends_jersey_display",
            "nostalgic_tribute",
            "motorsport_driver_car",
            "minimalist_hero",
            "championship_achievement",
            "vintage_restoration",
            "update_existing",
        )
        self.assertEqual(design_studio_styles.style_slugs(), expected)
        self.assertEqual(len(expected), len(set(expected)))
        self.assertEqual(
            design_studio_styles.STYLE_REGISTRY_VERSION,
            "sports_cave_design_styles_v2",
        )

    def test_every_style_builds_all_four_prompts(self):
        for slug in design_studio_styles.style_slugs():
            with self.subTest(style=slug):
                bundle = design_studio_styles.build_prompt_bundle(
                    slug,
                    "Create the requested collector artwork",
                    STYLE_DETAILS[slug],
                )
                self.assertEqual(bundle["errors"], [])
                for prompt_name in (
                    "research",
                    "find_images",
                    "generation",
                    "signature_placement",
                    "review",
                ):
                    self.assertGreater(len(bundle[prompt_name]), 300)
                label = design_studio_styles.get_design_style(slug).label
                self.assertIn(label, bundle["generation"])
                self.assertIn(label, bundle["review"])

    def test_only_selected_sport_adapter_is_included(self):
        prompt = design_studio_styles.build_generation_prompt(
            "minimalist_hero",
            "Create Michael Jordan artwork",
            {
                "sport": "Basketball",
                "principal_subject_one": "Michael Jordan",
            },
        )
        self.assertIn("SPORT ADAPTER - BASKETBALL", prompt)
        self.assertNotIn("SPORT ADAPTER - MOTORSPORT", prompt)
        self.assertNotIn("SPORT ADAPTER - FOOTBALL", prompt)
        self.assertNotIn("If the sport is", prompt)

    def test_irrelevant_style_modules_are_absent(self):
        prompt = design_studio_styles.build_generation_prompt(
            "minimalist_hero",
            "Create Michael Jordan artwork",
            STYLE_DETAILS["minimalist_hero"],
        )
        self.assertIn("STYLE-SPECIFIC COMPOSITION - Minimalist Hero", prompt)
        self.assertNotIn("STYLE - Rivalry Face-Off", prompt)
        self.assertNotIn("STYLE - Legends Jersey Display", prompt)
        self.assertNotIn("modernise, reliver", prompt)
        self.assertNotIn("genuine rear or rear three-quarter", prompt)

    def test_generation_prompts_are_concise_and_legacy_blocks_are_absent(self):
        legacy_markers = (
            "HIGHEST-PRIORITY SOURCE SUBJECT LOCK",
            "SPORTS_CAVE_RIVALRY_COMPOSITION_RULES_V1",
            "SPORTS_CAVE_FINAL_ARTWORK_MASTER_PROMPT",
            "PRIMARY HERO DOMINANCE AND MINIMAL BACKGROUND",
            "AUTHENTIC SIGNATURE PRESERVATION AND PREMIUM TREATMENT",
        )
        for slug in design_studio_styles.style_slugs():
            prompt = design_studio_styles.build_generation_prompt(
                slug,
                "Create the requested collector artwork",
                STYLE_DETAILS[slug],
            )
            with self.subTest(style=slug):
                max_length = 14500 if slug == "rivalry_faceoff" else 9500
                self.assertLess(len(prompt), max_length)
                for marker in legacy_markers:
                    self.assertNotIn(marker, prompt)

    def test_style_specific_contracts_are_authoritative(self):
        expectations = {
            "ultimate_moment": "definitive authentic photograph of the exact moment",
            "rivalry_faceoff": "No third person",
            "legends_jersey_display": "genuine rear or rear three-quarter source photographs",
            "nostalgic_tribute": "Do not duplicate the athlete",
            "motorsport_driver_car": "same verified season, race, team and livery",
            "minimalist_hero": "maximum two visible figures",
            "championship_achievement": "Never invent a future or hypothetical achievement as fact",
            "vintage_restoration": "Preserve authentic film grain",
            "update_existing": "Change only the requested element",
        }
        for slug, expected in expectations.items():
            with self.subTest(style=slug):
                prompt = design_studio_styles.build_generation_prompt(
                    slug,
                    "Create the requested collector artwork",
                    STYLE_DETAILS[slug],
                )
                self.assertIn(expected, prompt)

    def test_update_existing_preserves_proven_mapping_and_skips_general_search(self):
        style = design_studio_styles.get_design_style("update_existing")
        self.assertTrue(style.skip_find_images_by_default)
        self.assertEqual(style.legacy_prompt_key, "design-studio::upgrade-existing-design")
        find_prompt = design_studio_styles.build_find_images_prompt(
            "update_existing",
            "Change edition number only",
        )
        generation = design_studio_styles.build_generation_prompt(
            "update_existing",
            "Change edition number only",
        )
        self.assertIn("Skip Find Images by default", find_prompt)
        self.assertIn("immutable edit target", generation)
        self.assertIn("Add no people", generation)


class DesignStudioImageContractTests(unittest.TestCase):
    def test_legacy_asset_roles_are_preserved_with_safe_v2_roles(self):
        assets = design_studio_styles.normalise_selected_assets(
            [
                {
                    "file_path": "C:/assets/player.jpg",
                    "role": "hero_image",
                    "subject_name": "Michael Jordan",
                },
                {"file_path": "C:/assets/face.jpg", "role": "identity_reference"},
                {"file_path": "C:/assets/arena.jpg", "role": "background"},
                {"file_path": "C:/assets/plaque.png", "role": "plaque_asset"},
            ]
        )
        self.assertEqual(
            [(asset["role"], asset["use_mode"]) for asset in assets],
            [
                ("hero_exact_photo", "visible_cutout"),
                ("historical_reference", "reference_only"),
                ("venue_reference", "reference_only"),
                ("plaque_asset", "visible_cutout"),
            ],
        )

    def test_generation_states_visible_and_reference_only_use_modes(self):
        prompt = design_studio_styles.build_generation_prompt(
            "minimalist_hero",
            "Create Michael Jordan artwork",
            STYLE_DETAILS["minimalist_hero"],
            [
                {
                    "file_path": "C:/assets/player.jpg",
                    "role": "hero_exact_photo",
                    "subject_name": "Michael Jordan",
                },
                {"file_path": "C:/assets/arena.jpg", "role": "venue_reference"},
            ],
        )
        self.assertIn("C:/assets/player.jpg | role=hero_exact_photo | use_mode=visible_cutout", prompt)
        self.assertIn("C:/assets/arena.jpg | role=venue_reference | use_mode=reference_only", prompt)
        self.assertIn("Reference-only images provide facts", prompt)
        self.assertNotIn("use all images visibly", prompt.casefold())

    def test_signatures_map_only_to_valid_named_humans_once(self):
        prompt = design_studio_styles.build_generation_prompt(
            "rivalry_faceoff",
            "Peter Brock vs Allan Moffat",
            STYLE_DETAILS["rivalry_faceoff"],
            [
                {"file_path": "brock.png", "role": "signature_asset", "subject_name": "Peter Brock"},
                {"file_path": "brock-duplicate.png", "role": "signature_asset", "subject_name": "Peter Brock"},
                {"file_path": "moffat.png", "role": "signature_asset", "subject_name": "Allan Moffat"},
                {"file_path": "thin.png", "role": "signature_asset", "subject_name": "Thin Sports Cave"},
                {"file_path": "style.png", "role": "signature_asset", "subject_name": "Cinematic Realistic"},
            ],
        )
        self.assertIn("Peter Brock -> brock.png", prompt)
        self.assertIn("Allan Moffat -> moffat.png", prompt)
        self.assertNotIn("brock-duplicate.png", prompt)
        self.assertNotIn("Thin Sports Cave", prompt)
        self.assertNotIn("Cinematic Realistic", prompt)

    def test_generation_requires_every_principal_name_signature_and_exact_plaque_once(self):
        prompt = design_studio_styles.build_generation_prompt(
            "rivalry_faceoff",
            "Peter Brock vs Allan Moffat",
            STYLE_DETAILS["rivalry_faceoff"],
            [
                {"file_path": "brock.jpg", "role": "rival_one_photo", "subject_name": "Peter Brock"},
                {"file_path": "moffat.jpg", "role": "rival_two_photo", "subject_name": "Allan Moffat"},
                {"file_path": "brock-signature.png", "role": "signature_asset", "subject_name": "Peter Brock"},
                {"file_path": "moffat-signature.png", "role": "signature_asset", "subject_name": "Allan Moffat"},
                {"file_path": "limited-edition-plaque.png", "role": "plaque_asset"},
            ],
        )

        self.assertEqual(prompt.count("EXACT REQUIRED PRINCIPAL NAMES"), 1)
        self.assertIn("* Peter Brock", prompt)
        self.assertIn("* Allan Moffat", prompt)
        self.assertEqual(prompt.count("EXACT SIGNATURE-TO-PRINCIPAL MAPPING"), 1)
        self.assertEqual(prompt.count("* Peter Brock -> brock-signature.png"), 1)
        self.assertEqual(prompt.count("* Allan Moffat -> moffat-signature.png"), 1)
        self.assertEqual(prompt.count("EXACT PLAQUE ASSET MAPPING"), 1)
        self.assertIn(
            "* Sports Cave limited-edition plaque -> limited-edition-plaque.png | role=plaque_asset | use exact asset unchanged",
            prompt,
        )

    def test_find_images_is_compact_and_references_research_recommendation(self):
        prompt = design_studio_styles.build_find_images_prompt(
            "minimalist_hero",
            "Create Michael Jordan collector artwork",
            STYLE_DETAILS["minimalist_hero"],
        )
        fixed_body = prompt.split("TASK VARIABLES", 1)[0]

        self.assertLessEqual(len(fixed_body), 6500)
        self.assertIn("immediately preceding Research response", fixed_body)
        self.assertIn("Do not repeat or redo the research", fixed_body)
        self.assertIn("three strongest final-use photographs per principal", fixed_body)
        self.assertIn("exactly one clearest verified signature candidate", fixed_body)

    def test_signature_placement_appears_immediately_after_generation(self):
        bundle = design_studio_styles.build_prompt_bundle(
            "minimalist_hero",
            "Create Michael Jordan collector artwork",
            STYLE_DETAILS["minimalist_hero"],
            [
                {"file_path": "jordan.png", "role": "signature_asset", "subject_name": "Michael Jordan"},
            ],
        )

        self.assertEqual(
            list(bundle.keys()),
            ["errors", "research", "find_images", "generation", "signature_placement", "review"],
        )
        placement = bundle["signature_placement"]
        self.assertIn("SPORTS CAVE SIGNATURE PLACEMENT PASS - MANDATORY", placement)
        self.assertIn("immediately preceding step", placement)
        self.assertIn("* Michael Jordan -> jordan.png", placement)
        self.assertIn("Do not regenerate people, vehicles, background or composition", placement)

    def test_vehicle_and_non_human_prompts_do_not_invent_signatures(self):
        vehicle_prompt = design_studio_styles.build_generation_prompt(
            "motorsport_driver_car",
            "Create Peter Brock with the Bathurst-winning car",
            {
                "sport": "Motorsport",
                "principal_subject_one": "Peter Brock",
            },
            [{"file_path": "torana.png", "role": "vehicle_exact_photo"}],
        )
        non_human_prompt = design_studio_styles.build_generation_prompt(
            "update_existing",
            "Update vehicle-only Mount Panorama artwork",
            {},
            [{"file_path": "mount-panorama.png", "role": "venue_reference"}],
        )

        self.assertIn("* Peter Brock -> MISSING VERIFIED SIGNATURE ASSET", vehicle_prompt)
        self.assertIn("No named human principal is supplied", non_human_prompt)
        self.assertIn("non-human designs must not invent signatures", non_human_prompt)

    def test_harsh_review_applies_missing_detail_score_cap(self):
        prompt = design_studio_styles.build_harsh_review_prompt(
            "minimalist_hero",
            "Create Michael Jordan collector artwork",
            STYLE_DETAILS["minimalist_hero"],
        )

        self.assertIn("Hard-cap the score at 6/10", prompt)
        self.assertIn("any required name, verified signature or exact plaque is missing", prompt)
        self.assertIn("Ignore stale names, signatures or research details from previous tasks", prompt)

    def test_three_named_people_are_supported_without_silent_removal(self):
        errors = design_studio_styles.validate_design_request(
            "ultimate_moment",
            {
                "principal_subjects": [
                    "Michael Jordan",
                    "Kobe Bryant",
                    "LeBron James",
                ]
            },
            "Three legends",
        )
        self.assertEqual(errors, [])
        prompt = design_studio_styles.build_generation_prompt(
            "ultimate_moment",
            "Three legends",
            {
                "principal_subjects": [
                    "Michael Jordan",
                    "Kobe Bryant",
                    "LeBron James",
                ]
            },
        )
        for name in ("Michael Jordan", "Kobe Bryant", "LeBron James"):
            self.assertIn(f"* {name}", prompt)
            self.assertIn(
                f"* {name} -> MISSING VERIFIED SIGNATURE ASSET",
                prompt,
            )

    def test_four_named_people_are_blocked(self):
        errors = design_studio_styles.validate_design_request(
            "ultimate_moment",
            {
                "principal_subjects": [
                    "Michael Jordan",
                    "Kobe Bryant",
                    "LeBron James",
                    "Magic Johnson",
                ]
            },
            "Four legends",
        )
        self.assertEqual(
            errors,
            [
                "This task exceeds the Sports Cave prompt limit of three principal people. "
                "Reduce it to one, two or three named principal subjects before generating prompts."
            ],
        )

    def test_style_adjectives_never_become_principal_subjects(self):
        subjects = design_studio_styles.principal_subjects(
            {
                "principal_subjects": [
                    "Thin Sports Cave",
                    "The Sports Cave",
                    "Cinematic Realistic",
                    "Michael Jordan",
                ]
            }
        )
        self.assertEqual(subjects, ["Michael Jordan"])


class DesignStudioV2PageContractTests(unittest.TestCase):
    def test_active_renderer_is_one_page_without_legacy_tabs(self):
        page_source = inspect.getsource(design_studio_page.render_design_studio_page)
        renderer = inspect.getsource(design_studio_page.render_design_studio_v2)
        self.assertNotIn("st.tabs", page_source)
        self.assertNotIn("st.tabs", renderer)
        self.assertIn("render_design_schedule", renderer)
        self.assertIn("if not selected_task", renderer)
        self.assertIn("Design style", renderer)
        self.assertIn("Design details", inspect.getsource(design_studio_page._render_design_details))
        self.assertIn("Research Prompt", renderer)
        self.assertIn("Find Images Prompt", renderer)
        self.assertIn("Design Generation Prompt", renderer)
        self.assertIn("Harsh Review", renderer)

    def test_task_switch_resets_style_from_saved_task(self):
        renderer = inspect.getsource(design_studio_page.render_design_studio_v2)
        self.assertIn("previous_identity != task_identity", renderer)
        self.assertIn("_task_design_style(selected_task)", renderer)
        self.assertIn("DESIGN_STUDIO_V2_STYLE_MEMORY_KEY", renderer)
        self.assertIn("DESIGN_STUDIO_V2_DETAILS_MEMORY_KEY", renderer)
        self.assertIn("details_memory.pop(task_identity, None)", renderer)
        self.assertEqual(
            design_studio_page._task_design_style(
                {
                    "design_style": "Rivalry Face-Off",
                    "metadata": {"design_style": "minimalist_hero"},
                }
            ),
            "rivalry_faceoff",
        )
        self.assertEqual(design_studio_page._task_design_style({"metadata": {}}), "")

    def test_imported_task_handoff_populates_every_design_detail_and_prompts(self):
        details = {
            "design_title": "The Mountain Rivals",
            "sport": "Motorsport",
            "principal_subject_one": "Peter Brock",
            "principal_subject_two": "Allan Moffat",
            "team_country": "Australia",
            "season_era": "1970s",
            "event_moment": "Bathurst rivalry",
            "venue_location": "Mount Panorama",
            "uniform_equipment_livery": "Correct period suits and cars",
            "essential_text": "BROCK VS MOFFAT",
            "special_instructions": "Keep both heroes equal",
        }
        task = {
            "title": "Build the Bathurst rivalry",
            "design_style": "rivalry_faceoff",
            "metadata": {
                "design_style": "rivalry_faceoff",
                "design_details": details,
            },
        }

        loaded = design_studio_page._task_design_details(task)
        prompts = design_studio_styles.build_prompt_bundle(
            design_studio_page._task_design_style(task),
            task["title"],
            loaded,
        )

        for key, value in details.items():
            self.assertEqual(loaded[key], value)
        for prompt_name in ("research", "find_images", "generation", "review"):
            for value in details.values():
                self.assertIn(value, prompts[prompt_name])

    def test_loading_a_second_task_does_not_reuse_first_task_metadata(self):
        first = design_studio_page._task_design_details(
            {
                "metadata": {
                    "design_details": {
                        "design_title": "First design",
                        "principal_subject_one": "Michael Jordan",
                        "special_instructions": "First task only",
                    }
                }
            }
        )
        second = design_studio_page._task_design_details({"metadata": {}})

        self.assertEqual(first["design_title"], "First design")
        for key in design_studio_styles.DESIGN_DETAIL_KEYS:
            self.assertEqual(second[key], "")

    def test_unified_save_replaces_style_only_action(self):
        renderer = inspect.getsource(design_studio_page.render_design_studio_v2)
        details_renderer = inspect.getsource(design_studio_page._render_design_details)
        persistence = inspect.getsource(design_studio_page._persist_task_design_details)

        self.assertIn("Save design details", details_renderer)
        self.assertIn("update_task_design_details", persistence)
        self.assertNotIn("Assign style to task", renderer)
        self.assertNotIn("Save changed style", renderer)
        self.assertNotIn("st.rerun", persistence)

    def test_legacy_three_person_metadata_remains_visible_to_validation(self):
        details = design_studio_page._task_design_details(
            {
                "metadata": {
                    "team_or_athlete": "Michael Jordan, Kobe Bryant and LeBron James"
                }
            }
        )
        self.assertEqual(
            details["_saved_principal_subjects"],
            ["Michael Jordan", "Kobe Bryant", "LeBron James"],
        )

    def test_copy_button_receives_the_complete_prompt(self):
        card_source = inspect.getsource(design_studio_page._render_v2_prompt_card)
        copy_source = inspect.getsource(design_studio_page._render_copy_button)
        self.assertIn("_render_copy_button(prompt_text", card_source)
        self.assertIn("navigator.clipboard.writeText(promptText)", copy_source)


class DesignStudioV2PersistenceContractTests(unittest.TestCase):
    def test_migration_is_additive_rerun_safe_and_legacy_nullable(self):
        migration_path = (
            Path(__file__).resolve().parents[1]
            / "migrations"
            / "20260813_design_studio_v2_styles.sql"
        )
        migration = migration_path.read_text(encoding="utf-8")
        self.assertIn("ADD COLUMN IF NOT EXISTS design_style TEXT", migration)
        self.assertIn("design_style IS NULL", migration)
        self.assertIn("CREATE INDEX IF NOT EXISTS", migration)
        for slug in design_studio_styles.style_slugs():
            self.assertIn(f"'{slug}'", migration)

    def test_migration_parses_with_the_postgresql_parser(self):
        try:
            from pglast import parse_sql
        except ImportError:
            self.skipTest("pglast is not installed")
        migration = (
            Path(__file__).resolve().parents[1]
            / "migrations"
            / "20260813_design_studio_v2_styles.sql"
        ).read_text(encoding="utf-8")
        self.assertEqual(len(parse_sql(migration)), 3)

    def test_migration_is_discovered_by_the_normal_runner(self):
        migration_name = "20260813_design_studio_v2_styles.sql"
        discovered = {path.name: path for path in run_migrations.migration_files()}

        self.assertIn(migration_name, discovered)
        self.assertTrue(
            run_migrations.safe_migration_sql(
                discovered[migration_name].read_text(encoding="utf-8")
            )
        )

    def test_postgres_backend_reads_writes_and_updates_the_dedicated_field(self):
        backend_source = (
            Path(__file__).resolve().parents[1] / "supabase_backend.py"
        ).read_text(encoding="utf-8")
        self.assertIn("SELECT id, title, section, status, created_at, completed_at, completed_by, design_style, metadata", backend_source)
        self.assertIn("INSERT INTO dashboard_tasks(title, section, design_style, metadata)", backend_source)
        self.assertIn("def update_dashboard_task_design_style", backend_source)
        self.assertIn("def update_dashboard_task_design_details", backend_source)
        self.assertIn("'design_details', %s::jsonb", backend_source)
        self.assertIn("jsonb_build_object('design_style', %s)", backend_source)


if __name__ == "__main__":
    unittest.main()
