import unittest

import design_studio_page as page
import design_studio_styles as styles
from tests.test_design_studio_find_images import BASELINE


class GenerationHandoffTests(unittest.TestCase):
    def assert_execution(self, prompt):
        self.assertTrue(prompt.startswith("FINAL OUTPUT MODE: GENERATE ARTWORK"))
        self.assertTrue(prompt.endswith("Generate the completed artwork now."))
        self.assertEqual(prompt.count(styles.FINAL_GENERATION_EXECUTION_CONTRACT), 1)
        for requirement in (
            "REFERENCE/SOURCE IMAGES ONLY", "never the final deliverable",
            "YOU MUST USE IMAGE GENERATION", "NEW, fully composed Sports Cave",
            "display the generated artwork directly in ChatGPT",
            "PRIMARY HERO REFERENCE", "SECONDARY / ENVIRONMENT REFERENCE",
            "A link, attachment, local file path", "DOES NOT satisfy this task",
            "Simply adding a title, plaque, signature, border or small overlay",
            "Python/PIL", "Stop searching", "ASSET WITHIN THE ARTWORK",
        ):
            self.assertIn(requirement, prompt)
        self.assertNotIn("This is an image-editing and compositing task, not a request", prompt)
        self.assertNotIn("Before generating, show one concise PASS/REPLACE", prompt)

    def test_all_styles_preserve_contracts_and_references(self):
        for case in BASELINE["styles"]:
            with self.subTest(style=case["style"]):
                prompt = styles.build_generation_prompt(case["style"], case["task"], case["details"], case["assets"])
                self.assert_execution(prompt)
                style = styles.get_design_style(case["style"])
                self.assertIn(style.generation_rules, prompt)
                self.assertIn(style.label, prompt)
                self.assertIn(case["task"], prompt)
                for asset in styles.normalise_selected_assets(case["assets"]):
                    if asset["role"] != "signature_asset":
                        self.assertIn(asset["reference"], prompt)

    def test_kevin_garnett_game_six_is_generated_artwork_not_plaque_proof(self):
        details = {"principal_subject_one": "Kevin Garnett", "sport": "Basketball",
                   "event_moment": "2008 NBA Finals Game 6 celebration", "season_era": "2008",
                   "design_title": "ANYTHING IS POSSIBLE"}
        assets = [
            {"url": "https://example.com/game6.jpg", "role": "exact_moment_photo", "subject_name": "Kevin Garnett"},
            {"file_path": "sports-cave-plaque.png", "role": "plaque_asset"},
        ]
        prompt = styles.build_generation_prompt("ultimate_moment", "Kevin Garnett Ultimate Moment", details, assets)
        self.assert_execution(prompt)
        for text in ("2008 NBA Finals Game 6 celebration", "Kevin Garnett", "ANYTHING IS POSSIBLE",
                     "https://example.com/game6.jpg", "sports-cave-plaque.png", "ULTIMATE MOMENT LOCK",
                     "foreground/background depth", "unsigned photographic proof", "REFERENCE/SOURCE INPUTS ONLY"):
            self.assertIn(text, prompt)
        self.assertLess(prompt.index("https://example.com/game6.jpg"), prompt.index("SPORTS CAVE COLLECTOR DESIGN CONTRACT - MANDATORY"))

    def test_generic_and_saved_prompt_routes_get_same_contract(self):
        context = {"metadata": {"selected_assets": [{"url": "https://example.com/hero.jpg", "role": "hero_exact_photo"}]}}
        prompt = page.build_design_generation_prompt("Historical collector design", design_context=context)
        self.assert_execution(prompt)
        self.assertIn("https://example.com/hero.jpg", prompt)
        saved_prompt = page.build_design_studio_image_generation_prompt("Create a collector design", design_context=context)
        self.assert_execution(saved_prompt)
        self.assertIn("https://example.com/hero.jpg", saved_prompt)

    def test_finalizer_is_idempotent_and_keeps_explicit_asset_blocks(self):
        prompt = styles.build_generation_prompt("legends_jersey_display", "Legends", {}, [])
        self.assertEqual(styles.finalize_generation_handoff(prompt), prompt)
        self.assertIn("stop before final generation", prompt)
        self.assertEqual(styles.build_generation_prompt("unknown", "Task"), styles.STYLE_REQUIRED_LABEL)

    def test_locked_legacy_route_inherits_contract(self):
        for case in BASELINE["styles"]:
            if case["style"] not in ("ultimate_moment", "legends_jersey_display"):
                continue
            context = {"design_style": case["style"], "metadata": {"design_details": case["details"], "selected_assets": case["assets"]}}
            self.assert_execution(page.build_design_generation_prompt(case["task"], design_context=context))


if __name__ == "__main__":
    unittest.main()
