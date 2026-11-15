"""Requirement coverage and shared-to-call expansion; never runs an image model."""
import json
import re
import unittest

import ads_page as ads
import sports_cave_physical_realism as physical


class PromptSimplificationTests(unittest.TestCase):
    def result_and_visuals(self, metadata=None):
        result = ads.build_ads_result_record("Alexander Volkanovski Collector", "MMA", "Australia", "Instant Experience",
            product_metadata=metadata or {"edition_limit": 250}, variation_token="simplification")
        visuals = ads.resolve_standard_instant_experience_visuals(product_name=result["product_name"], category="MMA",
            country="Australia", product_metadata=result["product_metadata"], variation_token="different-token")
        return result, visuals

    def test_checklist_is_an_index_at_the_top_before_detailed_requirements(self):
        result, _ = self.result_and_visuals()
        prompt = result["master_prompt"]
        self.assertLess(prompt.index(ads.IE_EXECUTION_CHECKLIST), prompt.index("Product:"))
        self.assertEqual(ads.IE_EXECUTION_CHECKLIST.count("\n- "), 9)
        self.assertIn("Read the complete brief before acting. This checklist is an index, not a replacement for the detailed requirements below. Resolve all three ads before generation, and check each output against its assigned specification.", prompt)
        self.assertNotRegex(prompt, r"(?i)checklist guarantees|guaranteed compliance")

    def test_common_rules_once_but_every_expanded_call_is_complete(self):
        result, visuals = self.result_and_visuals({"edition_limit": 250,
            "frame_specs": {"verified": True, "source": "offline fixture", "glazing": "acrylic"}})
        prompt = result["master_prompt"]
        shared = ads.build_instant_experience_shared_template(visuals[0]["physical_product"])
        self.assertEqual(prompt.count(shared), 1)
        self.assertEqual(len(physical.BLOCK.findall(prompt)), 1)
        for common in (ads.ie_visuals.SCENE_REFERENCE_RULES, ads.ie_visuals.SCENE_VISIBILITY_RULES, ads.ie_visuals.SCARCITY_RULE):
            self.assertEqual(prompt.count(common.strip()), 1)
        briefs = re.findall(r"\nIMAGE GENERATION PROMPT\n(.*?)\nAD COPY\n", prompt, re.S)
        for index, (brief, visual) in enumerate(zip(briefs, visuals)):
            scene = re.search(r"^SCENE: (.+)$", brief, re.M).group(1)
            self.assertEqual(ads.ie_visuals.SCENE_REFERENCE_RULES + scene + ads.ie_visuals.SCENE_VISIBILITY_RULES, visual["scene_brief"])
            expanded = shared + "\n" + brief
            for contract in (ads.build_instant_experience_fixed_opaque_footer_rules(),
                             ads.build_instant_experience_on_image_copy_fit_rules(),
                             ads.build_instant_experience_typography_quality_rules(shared=True),
                             physical.build(visual["physical_product"], compact=True)):
                self.assertIn(contract, expanded)
            self.assertEqual(len(physical.BLOCK.findall(expanded)), 1)
            self.assertIn(visual["camera_side"], expanded)
            self.assertIn("Never place the long description or Meta headline inside the image.", expanded)
            for sibling_index, sibling in enumerate(visuals):
                if sibling_index != index:
                    self.assertNotIn(sibling["architecture_style"], brief)
                    self.assertNotIn("HEADLINE: " + sibling["headline_text"], brief)

    def test_exact_values_limits_exceptions_and_output_contract_survive(self):
        prompt = self.result_and_visuals()[0]["master_prompt"]
        requirements = {
            "format": ("1024 x 1024", "1:1, sRGB", "80–82%", "18–20%", "256 x 256"),
            "fit": ("880–896 px usable width", "Do not render a supporting line, secondary sentence or replacement text", "four words and no more than 24 characters"),
            "type": ("headline 42–48 px", "CTA 26–28 px, Montserrat Medium", "0.04–0.06 em", "22–30 px", "Thickness is approximately 1 px", "3–5 px", "4-8 px", "64-72 px"),
            "copy": ("Usually 40–75 words", "at most six words", "0.90 or more", "Exactly one description uses this construction", "Claim Your Edition", "Shop Now"),
            "execution": ("exactly three successful image-generation calls", "No variants, alternatives, correction or replacement generations", "Once access succeeds, automatically resume the original task", "Retry only a missing output", "never repeat a successful call", "Never restart the set", "If it is unclear whether an image was created", "Recover or redisplay an existing asset if display fails", "Never claim an image or CSV exists unless it was created"),
            "csv": ("UTF-8 with BOM (utf-8-sig)", "CRLF row terminators", "quote fields containing commas/newlines/quotes", "double embedded quotes", "variation stays 1", "If file creation is genuinely unavailable", "product.name", ads.META_AD_URL_PARAMETERS),
            "realism": ("source-matched moulding", "clean mitred corners", "narrow contact shadows", "Never add glazing to known unglazed", "without obscuring important artwork details", "do not invent measurements", "No competing framed art, trophies, helmets"),
        }
        for category, values in requirements.items():
            for value in values:
                self.assertIn(value, prompt, (category, value))
        self.assertIn(",".join(ads.INSTANT_EXPERIENCE_COPY_CSV_HEADERS), prompt)
        self.assertEqual(prompt.count("\nAD COPY\n"), 3)

    def test_standalone_exports_remain_self_contained_without_debug_tokens(self):
        result, visuals = self.result_and_visuals()
        for index, visual in enumerate(visuals, 1):
            prompt = ads.build_standard_instant_experience_image_prompt(index, visual,
                product_name=result["product_name"], category="MMA", country="Australia")
            self.assertIn(visual["scene_brief"], prompt)
            self.assertIn(physical.build(visual["physical_product"], compact=True), prompt)
            self.assertIn(ads.build_instant_experience_typography_quality_rules(visual), prompt)
            self.assertIn("HEADLINE: " + visual["headline_text"], prompt)
            self.assertNotIn("SUPPORTING LINE:", prompt)
            self.assertNotIn(visual["supporting_line"], prompt)
            self.assertIn("CTA: CLAIM YOUR EDITION", prompt)
            self.assertNotIn("CREATIVE_VARIATION_TOKEN:", prompt)

    def test_cached_results_preserve_prompt_and_resolved_selection_records(self):
        result, _ = self.result_and_visuals()
        saved = json.loads(json.dumps(result))
        self.assertIs(ads.ensure_current_ads_result_prompt(saved), saved)
        self.assertEqual(ads.creation_instructions(saved["master_prompt"]), result["master_prompt"])
        self.assertEqual(saved["product_metadata"], result["product_metadata"])
        self.assertEqual(saved["instant_experience_fingerprints"], result["instant_experience_fingerprints"])


if __name__ == "__main__":
    unittest.main()
