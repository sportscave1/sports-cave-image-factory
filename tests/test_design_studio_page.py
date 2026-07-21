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
        self.assertNotIn("Michael Jordan final shot collector piece", prompt)
        self.assertNotIn("The strongest angle is the final shot", prompt)
        self.assertNotIn("recommendations, or creative direction", prompt.split("Only find and display the images.")[1])
        self.assertNotIn("display approximately 10-12 strong images", prompt)
        self.assertNotIn("Limited-edition plaque position", prompt)

    def test_design_generation_prompt_uses_research_context_and_design_system(self):
        prompt = design_studio_page.build_design_generation_prompt("Bathurst Brock tribute")

        self.assertIn(
            "From the research and images above, create a premium Sports Cave limited-edition collector artwork",
            prompt,
        )
        self.assertIn("TASK:\nBathurst Brock tribute", prompt)
        self.assertIn("Bathurst Brock tribute", prompt)
        self.assertIn("Use the selected hero image as the main subject reference.", prompt)
        self.assertIn("Use the Sports Cave limited-edition plaque attached to this project", prompt)
        self.assertIn("This must feel like premium limited-edition sports wall art", prompt)
        self.assertIn("Realism and reference accuracy lock:", prompt)
        self.assertIn("Use the selected images as strict visual references.", prompt)
        self.assertIn("Do not redesign the athlete, driver, car, uniform, trophy, venue, or moment.", prompt)
        self.assertIn("Do not mirror images if it reverses numbers, logos, sponsor text, or kit details.", prompt)
        self.assertIn("legend + moment + nostalgia + darkness + subtle gold + framed collector energy", prompt)
        self.assertIn("Use a dark cinematic foundation:", prompt)
        self.assertIn("Use gold sparingly only for premium emphasis:", prompt)
        self.assertIn("It must never overpower the subject.", prompt)
        self.assertIn("If motorsport: realistic race cars", prompt)
        self.assertIn("Refine toward realism, emotion, collectibility, and wall-worthy bestseller potential.", prompt)
        self.assertNotIn("Continue with this Sports Cave design system:", prompt)
        self.assertNotIn("Sports Cave Master Design System Prompt", prompt)

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
