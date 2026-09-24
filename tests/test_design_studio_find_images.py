import hashlib
import json
from pathlib import Path
import unittest

import design_studio_page as page
import design_studio_styles as styles


BASELINE = json.loads((Path(__file__).parent / "fixtures" / "design_studio_non_find_images_baseline.json").read_text(encoding="utf-8"))


def assert_short_find_images(test, prompt):
    test.assertEqual(prompt.count(styles.COMMON_FIND_IMAGES_PROMPT), 1)
    for required in (
        "Research result immediately above", "Do not redo the research",
        "image search immediately", "REAL photographs", "directly in this ChatGPT conversation",
        "IMAGE CAROUSEL", "approximately 4–6", "before any commentary",
        "Best primary image:", "Best supporting image:", "Do not generate the artwork yet",
        "source URLs/references", "asset_id", "role", "use_mode", "actual image inputs",
    ):
        test.assertIn(required, prompt)
    for obsolete in (
        "Search three visual roles", "PRIMARY HERO", "SECONDARY MOMENT IMAGE",
        "BACKGROUND / ENVIRONMENT", "ENVIRONMENT / STORY SUPPORT", "Adapt focused searches",
        "[ATHLETE] [EXACT EVENT]", "IMAGE ROLE CONTRACT", "STYLE PHOTO TARGETS",
        "REQUIRED SEARCH AND CAROUSEL EXECUTION PLAN", "signature_slot_limit",
        "three strongest final-use photographs per principal", "1200 pixels", "2000 pixels",
    ):
        test.assertNotIn(obsolete, prompt)
    test.assertLess(len(prompt.split()), 420)


class ShortFindImagesTests(unittest.TestCase):
    def test_every_supported_type_uses_one_short_template(self):
        self.assertEqual({case["style"] for case in BASELINE["styles"]}, set(styles.style_slugs()))
        for case in BASELINE["styles"]:
            with self.subTest(style=case["style"]):
                prompt = styles.build_find_images_prompt(case["style"], case["task"], case["details"])
                assert_short_find_images(self, prompt)
                self.assertIn(styles.get_design_style(case["style"]).label, prompt)
                self.assertLess(len(prompt), case["old_find_characters"] * 0.4)
                self.assertLess(len(styles.get_design_style(case["style"]).find_images_rules.split()), 30)

    def test_legacy_routes_every_style_to_the_same_short_source(self):
        for case in BASELINE["styles"]:
            with self.subTest(style=case["style"]):
                context = {"design_style": case["style"], "metadata": {"design_details": case["details"]}}
                prompt = page.build_design_image_carousel_prompt(case["task"], "FULL RESEARCH RESPONSE " * 1000, design_context=context)
                assert_short_find_images(self, prompt)
                self.assertNotIn("FULL RESEARCH RESPONSE", prompt)

    def test_research_generation_and_other_stages_are_byte_for_byte_unchanged(self):
        for case in BASELINE["styles"]:
            for stage, method in (("research", "research"), ("generation", "generation"), ("signature_placement", "signature_placement"), ("review", "harsh_review")):
                with self.subTest(style=case["style"], stage=stage):
                    args = [case["style"], case["task"], case["details"]]
                    if stage != "research":
                        args.append(case["assets"])
                    output = getattr(styles, f"build_{method}_prompt")(*args)
                    self.assertEqual(hashlib.sha256(output.encode()).hexdigest(), case["hashes"][stage])
        for stage in ("research", "generation"):
            output = getattr(page, f"build_design_{stage}_prompt")(BASELINE["legacy"]["task"])
            self.assertEqual(hashlib.sha256(output.encode()).hexdigest(), BASELINE["legacy"]["hashes"][stage])

    def test_ultimate_moment_keeps_the_exact_event_and_confirmation_handoff(self):
        details = {"principal_subject_one": "Dale Earnhardt Sr.", "sport": "NASCAR", "event_moment": "1998 Daytona 500 victory", "season_era": "1998", "uniform_equipment_livery": "No. 3 Goodwrench Chevrolet", "special_instructions": "Victory photographs only"}
        prompt = styles.build_find_images_prompt("ultimate_moment", "Dale Earnhardt Sr. victory", details)
        assert_short_find_images(self, prompt)
        for value in details.values():
            self.assertIn(value, prompt)
        self.assertIn("exact locked moment/event", prompt)
        self.assertIn("MOMENT LOCK CONFIRMATION", prompt)

    def test_rivalry_keeps_both_named_principals_and_era(self):
        prompt = styles.build_find_images_prompt("rivalry_faceoff", "Two generations", {"principal_subject_one": "Michael Jordan", "principal_subject_two": "Kobe Bryant", "season_era": "1998", "sport": "Basketball"})
        assert_short_find_images(self, prompt)
        for value in ("Michael Jordan", "Kobe Bryant", "1998", "individual photographs of both principals"):
            self.assertIn(value, prompt)

    def test_horse_racing_does_not_become_a_driver_car_search(self):
        for style in ("rivalry_faceoff", "ultimate_moment", "nostalgic_tribute"):
            prompt = styles.build_find_images_prompt(style, "Winx vs Black Caviar", {"principal_subject_one": "Winx", "principal_subject_two": "Black Caviar", "sport": "Horse racing"})
            assert_short_find_images(self, prompt)
            for value in ("Winx", "Black Caviar", "genuine separate photographs", "do not substitute one horse for another"):
                self.assertIn(value, prompt)
            self.assertNotIn("Prioritise accurate driver", prompt)

    def test_motorsport_preserves_driver_car_livery_and_event_context(self):
        details = {"principal_subject_one": "Peter Brock", "event_moment": "1987 Bathurst", "sport": "Motorsport", "uniform_equipment_livery": "HDT VL Commodore #10"}
        for style in ("motorsport_driver_car", "ultimate_moment", "nostalgic_tribute"):
            prompt = styles.build_find_images_prompt(style, "Peter Brock", details)
            assert_short_find_images(self, prompt)
            for value in details.values():
                self.assertIn(value, prompt)
            self.assertEqual(prompt.count("Prioritise accurate driver, car/livery and event-era photographs."), 1)

    def test_jersey_references_keep_both_subjects_and_jersey_identity(self):
        prompt = styles.build_find_images_prompt("legends_jersey_display", "Legends jerseys", {"principal_subject_one": "Shohei Ohtani", "principal_subject_two": "Aaron Judge", "uniform_equipment_livery": "Ohtani #17; Judge #99"})
        assert_short_find_images(self, prompt)
        for value in ("rear-jersey", "both principals", "surnames and numbers", "Ohtani #17; Judge #99"):
            self.assertIn(value, prompt)

    def test_image_selection_handoff_keeps_reference_and_subject_mapping(self):
        assets = [{"asset_id": "image-2", "url": "https://example.com/jordan.jpg", "role": "exact_moment_photo", "subject_name": "Michael Jordan", "use_mode": "visible_whole_photo"}]
        normalized = styles.normalise_selected_assets(assets)
        self.assertEqual(normalized[0]["reference"], assets[0]["url"])
        self.assertEqual(normalized[0]["subject_name"], "Michael Jordan")
        generation = styles.build_generation_prompt("ultimate_moment", "1998 NBA Finals Game 6", {"principal_subject_one": "Michael Jordan", "event_moment": "1998 NBA Finals Game 6"}, assets)
        self.assertIn("https://example.com/jordan.jpg | role=exact_moment_photo", generation)
        self.assertIn("use_mode=visible_whole_photo", generation)

    def test_generic_legacy_context_is_compact_without_research_body(self):
        context = {"metadata": {"principal_subjects": [{"name": "Michael Jordan"}, {"name": "Michael Jordan"}, {"name": "Scottie Pippen"}], "year": "1998", "event": "NBA Finals", "uniform": "Chicago Bulls"}}
        prompt = page.build_design_image_carousel_prompt("Chicago legends", "Research body " * 1000, design_context=context)
        assert_short_find_images(self, prompt)
        self.assertIn("PRINCIPAL SUBJECTS: Michael Jordan; Scottie Pippen", prompt)
        for value in ("1998", "NBA Finals", "Chicago Bulls"):
            self.assertIn(value, prompt)
        self.assertNotIn("Research body", prompt)


if __name__ == "__main__":
    unittest.main()
