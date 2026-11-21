from tests.ads_prompt_contracts import current_ie, saved_ie, rotated_ie, scenes_ie
"""Original footer bank contracts; offline prompt/export checks only."""
import copy
import subprocess
import unittest
import ads_ie_visual_systems as wording
import ads_page as ads
import ads_refresh_generation as refresh


class ScarcityPairTests(unittest.TestCase):
    def record(self, token="original-bank", metadata=None, history=()):
        return ads.build_ads_result_record("Volkanovski", "MMA", "Australia", "Instant Experience",
            product_metadata=metadata if metadata is not None else {"edition_limit": 100},
            variation_token=token, recent_instant_experience_fingerprints=history)

    def test_exact_pairs_rotate_with_three_distinct_headlines(self):
        """Current approved two-line/immutable-pack contract replaces retired layout assertions."""
        rotated_ie(self)

    def test_claim_gates_and_exact_quantity(self):
        for limit in (None, 25, 250):
            self.record(metadata={"edition_limit": limit, "worldwide_edition_verified": False})
        base = {"edition_limit": 100}
        self.assertEqual(wording.eligible_headlines(base), list(wording.HEADLINES))
        full = {**base, "worldwide_verified": True, "no_second_run_verified": True,
                "remaining_editions": 100, "editions_sold": 0}
        self.assertEqual(set(wording.eligible_headlines(full)), set(wording.HEADLINES))
        self.assertEqual(wording.eligible_headlines({**full, "editions_sold": 1}), list(wording.HEADLINES))

    def test_refresh_uses_same_bank_and_scene_contract(self):
        """Current approved two-line/immutable-pack contract replaces retired layout assertions."""
        scenes_ie(self)

    def test_prompt_and_saved_fields_reuse_exact_selections(self):
        """Current approved two-line/immutable-pack contract replaces retired layout assertions."""
        saved_ie(self)


if __name__ == "__main__":
    unittest.main()
