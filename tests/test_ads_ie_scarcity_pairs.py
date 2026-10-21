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

    def test_bank_matches_original_git_revision(self):
        import ast
        original = subprocess.check_output(["git", "show", "16515128:ads_ie_visual_systems.py"]).decode("utf-8")
        recovered = {}
        for node in ast.parse(original).body:
            if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") in ("HEADLINES", "APPROVED_SUPPORT_LINES"):
                recovered[node.targets[0].id] = ast.literal_eval(node.value)
        self.assertEqual(wording.HEADLINES, recovered["HEADLINES"])
        self.assertEqual(wording.APPROVED_SUPPORT_LINES, recovered["APPROVED_SUPPORT_LINES"])

    def test_exact_pairs_rotate_and_allow_small_eligible_bank(self):
        pairs = set()
        for seed in range(12):
            result = self.record(str(seed))
            rows = result["instant_experience_fingerprints"]
            self.assertEqual(len(rows), 3)
            self.assertEqual(len({r["headline_text"] for r in rows}), 1)
            self.assertEqual(len({r["supporting_line"] for r in rows}), 3)
            for row in rows:
                head, sub = row["headline_text"], row["supporting_line"]
                self.assertIn(head, wording.HEADLINES)
                self.assertIn(sub, wording.APPROVED_SUPPORT_LINES)
                self.assertTrue(wording.coherent_pair(head, sub))
                self.assertEqual(row["cta_text"], "CLAIM YOUR EDITION")
                pairs.add((head, sub))
        self.assertGreater(len(pairs), 3)

    def test_claim_gates_and_exact_quantity(self):
        for limit in (None, 25, 250):
            with self.assertRaisesRegex(ValueError, "verified 100"):
                self.record(metadata={"edition_limit": limit})
        base = {"edition_limit": 100}
        self.assertEqual(wording.eligible_headlines(base), [wording.HEADLINES[4]])
        full = {**base, "worldwide_verified": True, "no_second_run_verified": True,
                "remaining_editions": 100, "editions_sold": 0}
        self.assertEqual(set(wording.eligible_headlines(full)), set(wording.HEADLINES))
        self.assertNotIn(wording.HEADLINES[5], wording.eligible_headlines({**full, "editions_sold": 1}))

    def test_saved_unapproved_copy_is_rejected(self):
        result = self.record()
        for bad in ("SPORTS CAVE COLLECTOR", "FOR YOUR COLLECTION", "ONLY 100 WILL EVER EXIST"):
            metadata = copy.deepcopy(result["product_metadata"])
            metadata["instant_experience_footer_selections"][0]["headline_text"] = bad
            with self.assertRaisesRegex(ValueError, "outside"):
                self.record(metadata=metadata)

    def test_refresh_uses_same_bank_and_scene_contract(self):
        result = ads.build_ads_result_record("Volkanovski", "MMA", "Australia", "Instant Experience",
            product_metadata={"edition_limit": 100},
            creative_refresh_context={"winning_primary_text": "A collector story", "winning_headline": "Winner"})
        prompt = result["master_prompt"]
        self.assertIn("Premium residential man cave", prompt)
        self.assertIn("Premium collector hallway", prompt)
        self.assertNotIn("WHEN 100 GO, IT ENDS", prompt)
        for row in result["instant_experience_fingerprints"]:
            self.assertIn(row["headline_text"], wording.HEADLINES)
            self.assertIn("HEADLINE: " + row["headline_text"], prompt)
            self.assertIn("SUPPORTING LINE: " + row["supporting_line"], prompt)

    def test_prompt_and_saved_fields_reuse_exact_selections(self):
        result = self.record()
        rebuilt = self.record("ignored", result["product_metadata"])
        self.assertEqual(result["product_metadata"]["instant_experience_footer_selections"],
                         rebuilt["product_metadata"]["instant_experience_footer_selections"])
        for row in result["instant_experience_fingerprints"]:
            self.assertIn("HEADLINE: " + row["headline_text"], result["master_prompt"])
            self.assertIn("SUPPORTING LINE: " + row["supporting_line"], result["master_prompt"])
            self.assertEqual(row["eligible_headline_alternatives"], [])
        self.assertNotIn("28 characters", refresh.ie_refresh_image_rules())
        self.assertIn("shared original approved footer bank", refresh.ie_refresh_image_rules())


if __name__ == "__main__":
    unittest.main()
