from pathlib import Path
import unittest

import design_studio_page


ROOT = Path(__file__).resolve().parents[1]


class DesignStudioResearchPromptTests(unittest.TestCase):
    def test_research_prompt_uses_pasted_task_without_finding_images(self):
        prompt = design_studio_page.build_design_research_prompt("Michael Jordan final shot collector piece")

        self.assertIn("TASK TO RESEARCH", prompt)
        self.assertIn("Michael Jordan final shot collector piece", prompt)
        self.assertIn("Use current web research", prompt)
        self.assertIn("do not find or display images yet", prompt)
        self.assertNotIn("display approximately 10-12 strong images", prompt)
        self.assertIn("Do not generate the final artwork yet.", prompt)

    def test_image_prompt_uses_research_answer_and_only_requests_carousel(self):
        prompt = design_studio_page.build_design_image_carousel_prompt(
            "Michael Jordan final shot collector piece",
            "The strongest angle is the final shot and Chicago nostalgia.",
        )

        self.assertIn("Michael Jordan final shot collector piece", prompt)
        self.assertIn("The strongest angle is the final shot", prompt)
        self.assertIn("display approximately 10-12 strong images", prompt)
        self.assertIn("as an image carousel", prompt)
        self.assertIn("This step is only for finding and displaying images.", prompt)
        self.assertIn("Do not analyse, rank or recommend the images.", prompt)
        self.assertIn("Stop after the image carousel.", prompt)
        self.assertIn("Do not generate the final artwork.", prompt)
        self.assertNotIn("Limited-edition plaque position", prompt)

    def test_design_generation_prompt_uses_research_context_and_design_system(self):
        prompt = design_studio_page.build_design_generation_prompt("Bathurst Brock tribute")

        self.assertIn("From the research and images above you found", prompt)
        self.assertIn("Bathurst Brock tribute", prompt)
        self.assertIn("Sports Cave Master Design System Prompt", prompt)
        self.assertIn("legend + moment + nostalgia + darkness + gold + framed collector energy", prompt)
        self.assertIn("Built for Sports Cave best seller potential.", prompt)

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
        self.assertIn("Paste research answer", renderer)
        self.assertIn("Copy Find Images Prompt", renderer)


if __name__ == "__main__":
    unittest.main()
