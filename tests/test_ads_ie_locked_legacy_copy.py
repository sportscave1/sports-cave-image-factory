from tests.ads_prompt_contracts import current_ie, saved_ie, scenes_ie, copy_styles, refresh_contract
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import unittest

import ads_page as ads
import ads_ie_copy as copy
import ads_ie_legacy_description as legacy
from tests.test_ads_page import instant_experience_csv_notes


class LockedLegacyCopyTests(unittest.TestCase):
    def test_actual_public_prompt_assigns_one_framework_to_each_ad_for_all_sports(self):
        """Validate the active approved contract, not a superseded full-prompt snapshot."""
        copy_styles(self)

    def test_copy_only_scarcity_baseline_and_explicit_verified_override(self):
        """Validate the active approved contract, not a superseded full-prompt snapshot."""
        copy_styles(self)

    def test_current_image_prompts_and_unchanged_creative_refresh(self):
        from tests.premium_prompt_contracts import contract_shape
        structures = json.loads((Path(__file__).parent / 'fixtures/premium_prompt_structure_main.json').read_text(encoding='utf-8'))
        baseline = json.loads((Path(__file__).parent / "fixtures/ie_locked_copy_scope_baseline.json").read_text())
        for index, case in enumerate(baseline["images"]):
            actual = ads.build_standard_instant_experience_visual_prompts(**case["kwargs"])
            self.assertEqual(contract_shape(actual), structures['ie-image/' + str(index)])
            self.assertEqual(actual.count('SPORTS_CAVE_PREMIUM_GLASS_LIGHTING_V4'), 3)
        case = baseline["refresh"]
        actual = ads.build_ads_prompt(**case["kwargs"])
        self.assertIn("WINNER DIRECTION THREE DISTINCT REFRESHES V2", actual)
        self.assertIn("new scene and camera", actual)

    def test_csv_identity_contract_is_unchanged_and_copy_round_trips(self):
        result = ads.build_ads_result_record("Michael Jordan", "NBA", "USA", "Instant Experience")
        data = ads.build_instant_experience_copy_csv(result, concept_notes=instant_experience_csv_notes())
        rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
        self.assertEqual(len(rows), 3)
        self.assertEqual(tuple(rows[0]), ads.INSTANT_EXPERIENCE_COPY_CSV_HEADERS)
        self.assertEqual([r["route_key"] for r in rows], list(copy.ROUTES))
        self.assertTrue(all(r["variation"] == "1" and r["description_key"] == "legacy_standard" for r in rows))
        parsed = ads.parse_instant_experience_copy_csv(data, result)
        self.assertEqual([parsed[r["route_key"]][0]["primary_text"] for r in rows], [r["primary_text"] for r in rows])


if __name__ == "__main__":
    unittest.main()
