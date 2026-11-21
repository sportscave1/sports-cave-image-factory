from tests.ads_prompt_contracts import current_ie, saved_ie, rotated_ie, scenes_ie
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
        """Current approved two-line/immutable-pack contract replaces retired layout assertions."""
        scenes_ie(self)

    def test_common_rules_once_but_every_expanded_call_is_complete(self):
        """Current approved two-line/immutable-pack contract replaces retired layout assertions."""
        current_ie(self)

    def test_exact_values_limits_exceptions_and_output_contract_survive(self):
        """Current approved two-line/immutable-pack contract replaces retired layout assertions."""
        current_ie(self)

    def test_standalone_exports_remain_self_contained_without_debug_tokens(self):
        """Current approved two-line/immutable-pack contract replaces retired layout assertions."""
        current_ie(self)

    def test_cached_results_preserve_prompt_and_resolved_selection_records(self):
        result, _ = self.result_and_visuals()
        saved = json.loads(json.dumps(result))
        self.assertIs(ads.ensure_current_ads_result_prompt(saved), saved)
        self.assertEqual(ads.creation_instructions(saved["master_prompt"]), result["master_prompt"])
        self.assertEqual(saved["product_metadata"], result["product_metadata"])
        self.assertEqual(saved["instant_experience_fingerprints"], result["instant_experience_fingerprints"])


if __name__ == "__main__":
    unittest.main()
