from pathlib import Path
import unittest

import design_studio_page


ROOT = Path(__file__).resolve().parents[1]


class DesignStudioResearchPromptTests(unittest.TestCase):
    def test_research_prompt_uses_pasted_task_and_image_carousel_direction(self):
        prompt = design_studio_page.build_design_research_prompt("Michael Jordan final shot collector piece")

        self.assertIn("TASK TO RESEARCH", prompt)
        self.assertIn("Michael Jordan final shot collector piece", prompt)
        self.assertIn("Search the web and display the best visual references", prompt)
        self.assertIn("image carousel", prompt)
        self.assertIn("Do not generate the final artwork yet.", prompt)

    def test_design_generation_prompt_uses_research_context_and_design_system(self):
        prompt = design_studio_page.build_design_generation_prompt("Bathurst Brock tribute")

        self.assertIn("From the research and images above you found", prompt)
        self.assertIn("Bathurst Brock tribute", prompt)
        self.assertIn("Sports Cave Master Design System Prompt", prompt)
        self.assertIn("legend + moment + nostalgia + darkness + gold + framed collector energy", prompt)
        self.assertIn("Built for Sports Cave best seller potential.", prompt)

    def test_design_research_tab_is_second_after_upgrade_existing_design(self):
        source = (ROOT / "design_studio_page.py").read_text(encoding="utf-8")
        tabs_source = source[
            source.index("upgrade_tab, research_tab") : source.index("\n\n    with upgrade_tab:")
        ]

        self.assertLess(
            tabs_source.index('"Upgrade Existing Design"'),
            tabs_source.index('"Design Research"'),
        )
        self.assertLess(
            tabs_source.index('"Design Research"'),
            tabs_source.index('"Update Expired Edition"'),
        )


if __name__ == "__main__":
    unittest.main()
