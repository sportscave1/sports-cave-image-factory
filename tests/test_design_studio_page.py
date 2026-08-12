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
        self.assertNotIn("Michael Jordan final shot collector piece", prompt)
        self.assertNotIn("The strongest angle is the final shot", prompt)
        self.assertNotIn("recommendations, or creative direction", prompt.split("Only find and display the images.")[1])
        self.assertNotIn("display approximately 10-12 strong images", prompt)
        self.assertNotIn("Limited-edition plaque position", prompt)
        self.assertNotIn(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER, prompt)

    def test_design_generation_prompt_uses_research_context_and_design_system(self):
        prompt = design_studio_page.build_design_generation_prompt("Bathurst Brock tribute")
        hero_marker = design_studio_page.DESIGN_STUDIO_HERO_DOMINANCE_MARKER
        border_marker = design_studio_page.DESIGN_STUDIO_LIMITED_EDITION_BORDER_MARKER

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
        hero_marker = design_studio_page.DESIGN_STUDIO_HERO_DOMINANCE_MARKER

        self.assertTrue(prompt.startswith(marker))
        self.assertEqual(prompt.count(marker), 1)
        self.assertLess(
            prompt.index("7. If any instruction conflicts with these rules"),
            prompt.index(hero_marker),
        )
        self.assertLess(prompt.index(hero_marker), prompt.index("TASK:\nBathurst Brock tribute"))
        self.assertLess(prompt.index(marker), prompt.index("TASK:\nBathurst Brock tribute"))
        self.assertLess(prompt.index(marker), prompt.index("Reference roles:"))
        self.assertLess(prompt.index(marker), prompt.index("Create the artwork in landscape 4:3 ratio."))
        self.assertLess(prompt.index(marker), prompt.index("Sports Cave collector style:"))
        self.assertIn("USE THE ORIGINAL SUPPLIED SUBJECT IMAGE ITSELF.", prompt)
        self.assertIn("Do not face-swap the subject.", prompt)
        self.assertIn("The background and design will adapt to the subject.", prompt)

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
                self.assertEqual(prompt.count(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER), 1)
                self.assertIn("Never generate extra supporting players.", prompt)
                self.assertIn("Any crowd treatment must remain distant, abstract, blurred and textural.", prompt)
                self.assertIn("The border must remain:", prompt)
                self.assertIn("4:3 landscape", prompt)
                self.assertIn("collector artwork", prompt)
                self.assertIn("Sports Cave", prompt)

    def test_unrelated_design_studio_prompts_do_not_receive_subject_lock(self):
        marker = design_studio_page.DESIGN_STUDIO_SUBJECT_PRESERVATION_MARKER
        hero_marker = design_studio_page.DESIGN_STUDIO_HERO_DOMINANCE_MARKER
        border_marker = design_studio_page.DESIGN_STUDIO_LIMITED_EDITION_BORDER_MARKER
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

    def test_subject_lock_composition_is_idempotent_and_preserves_prompt_details(self):
        marker = design_studio_page.DESIGN_STUDIO_SUBJECT_PRESERVATION_MARKER
        hero_marker = design_studio_page.DESIGN_STUDIO_HERO_DOMINANCE_MARKER
        border_marker = design_studio_page.DESIGN_STUDIO_LIMITED_EDITION_BORDER_MARKER
        once = design_studio_page.build_design_studio_image_generation_prompt(
            design_studio_page.CREATE_SPORTS_CAVE_STYLE_ARTWORK_PROMPT
        )
        twice = design_studio_page.build_design_studio_image_generation_prompt(once)

        self.assertEqual(once, twice)
        self.assertEqual(twice.count(marker), 1)
        self.assertEqual(twice.count(hero_marker), 1)
        self.assertEqual(twice.count(border_marker), 1)
        self.assertEqual(
            twice.count(design_studio_page._clean_prompt(design_studio_page.DESIGN_STUDIO_HERO_DOMINANCE_AND_BORDER_LOCK)),
            1,
        )
        self.assertEqual(twice.count(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER), 1)
        self.assertIn("[PASTE SELECTED MOMENT]", twice)
        self.assertIn("[PASTE HERO IMAGE DIRECTION]", twice)
        self.assertIn("[PASTE BACKGROUND IMAGE DIRECTION]", twice)
        self.assertIn("Use the Sports Cave limited-edition plaque attached to this project", twice)

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
