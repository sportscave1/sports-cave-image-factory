import unittest

import ads_page
from ads_image_contracts import INSTANT_EXPERIENCE_CONCEPTS
from sports_cave_prompt_blocks import SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER


class ThreeVisualSystemsTests(unittest.TestCase):
    def visuals(self, token="visual-test", metadata=None):
        return ads_page.resolve_standard_instant_experience_visuals(
            product_name="Collector Cricket Print", category="Cricket",
            product_metadata=metadata, variation_token=token,
        )

    def prompts(self, metadata=None):
        return [ads_page.build_standard_instant_experience_image_prompt(
            i, v, product_name="Collector Cricket Print", category="Cricket",
            country="Australia", product_url="https://example.com/products/collector",
        ) for i, v in enumerate(self.visuals(metadata=metadata), 1)]

    def test_three_families_preserve_persisted_identities(self):
        visuals = self.visuals()
        self.assertEqual([v["concept_id"] for v in visuals], [c["id"] for c in INSTANT_EXPERIENCE_CONCEPTS])
        self.assertEqual([v["visual_family"] for v in visuals],
                         ["premium_scarcity"] * 3)
        self.assertEqual([v["group_heading"] for v in visuals], [
            "GROUP 1 — PREMIUM SCARCITY — RIGHT ANGLE", "GROUP 2 — PREMIUM SCARCITY — STRAIGHT ON", "GROUP 3 — PREMIUM SCARCITY — LEFT ANGLE"])

    def test_shared_banner_and_three_different_rooms(self):
        visuals = self.visuals(metadata={"edition_limit": 100})
        for field in ("room_profile", "wall_colour", "primary_cue", "architectural_cue", "lighting", "product_width", "shot_distance"):
            self.assertEqual(len({v[field] for v in visuals}), 3)
        for i, prompt in enumerate(self.prompts({"edition_limit":100})):
            for required in (visuals[i]["headline_text"], visuals[i]["supporting_line"],
                             "CLAIM YOUR EDITION", "24–28%", "72–76%", "Never mirror artwork"):
                self.assertIn(required, prompt)
            self.assertIn(ads_page.ie_visuals.CAMERAS[i], prompt)

    def test_fan_style_is_product_aware_and_preserves_room_assignments(self):
        styles = {}
        for sport in ("Motorsport", "NBA", "NFL", "Baseball", "Cricket", "Horse Racing"):
            rows = ads_page.resolve_standard_instant_experience_visuals(
                product_name="Collector Subject", category=sport, product_metadata={"edition_limit":100})
            self.assertEqual([r["room_profile_key"] for r in rows], ["hallway_gallery", "minimal_art_wall", "collector_interior"])
            self.assertEqual(len({r["supporting_line"] for r in rows}), 3)
            styles[sport] = [r["room_materials"] for r in rows]
        self.assertGreaterEqual(len({tuple(v) for v in styles.values()}), 4)
        for values in styles.values():
            self.assertTrue(all("whisky" not in value and "leather" not in value for value in values))

    def test_unknown_and_other_limits_remain_truthful(self):
        self.assertEqual(len({v['headline_text'] for v in self.visuals()}), 3)
        self.assertTrue(all(not v['scarcity_verified'] for v in self.visuals()))
        self.assertEqual(len({v['headline_text'] for v in self.visuals(metadata={'edition_limit':250})}), 3)
        self.assertTrue(all('100' not in v['headline_text'] for v in self.visuals(metadata={'edition_limit':250})))

    def test_fixed_camera_roles_and_determinism(self):
        self.assertEqual(self.visuals(), self.visuals())
        for token in ('one', 'two'):
            self.assertEqual([v['camera_role'] for v in self.visuals(token)], ['RIGHT','FRONT','LEFT'])

    def test_all_prompts_keep_realism_and_smart_product_selection(self):
        for prompt in self.prompts():
            self.assertEqual(prompt.count(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER), 1)
            for phrase in ("PRODUCT SOURCE-ASSET FIDELITY", "LIGHTING, GLASS AND MOUNTING PHYSICS",
                           "ANTI-AI INTERIOR CONTROL", "1024 x 1024", "CREATIVE_VARIATION_TOKEN: visual-test",
                           "Resolve exactly ONE camera", "palette, brightness, frame colour",
                           "Do not append geographic scope", "Never invent a limit"):
                self.assertIn(phrase, prompt)
            self.assertNotIn("Don Mattingly", prompt)

    def test_approved_copy_fit_diversity_and_stability(self):
        self.assertEqual(len(ads_page.ie_visuals.HEADLINES), 6)
        self.assertEqual(len(set(ads_page.ie_visuals.APPROVED_SUPPORT_LINES)), 9)
        eligible = {h for h in ads_page.ie_visuals.eligible_headlines({"edition_limit": 100})
                    if ads_page.instant_experience_on_image_headline_is_valid(h)}
        self.assertIn("LIMITED EDITION", eligible)
        seen = set()
        for token in map(str, range(30)):
            rows = self.visuals(token, {"edition_limit": 100})
            self.assertEqual(rows, self.visuals(token, {"edition_limit": 100}))
            self.assertEqual(len({r["headline_text"] for r in rows}), 3)
            self.assertTrue({r["headline_text"] for r in rows} <= eligible)
            self.assertEqual(len({(r["headline_text"], r["supporting_line"]) for r in rows}), 3)
            self.assertEqual(len({r["supporting_line"] for r in rows}), 3)
            for r in rows:
                self.assertIn(r["supporting_line"], ads_page.ie_visuals.eligible_support_lines({"edition_limit": 100}))
                self.assertEqual(r["cta_text"], "CLAIM YOUR EDITION")
                self.assertEqual(ads_page.validate_instant_experience_on_image_copy(
                    r["headline_text"], r["supporting_line"], r["cta_text"]), ())
                seen.add((r["headline_text"], r["supporting_line"]))
        self.assertGreater(len(seen), 3)

    def test_claim_evidence_and_available_inventory(self):
        headlines = ads_page.ie_visuals.HEADLINES
        eligible = ads_page.ie_visuals.eligible_headlines
        base = {"edition_limit": 100}
        self.assertIn("LIMITED TO 100 EDITIONS", eligible(base))
        self.assertIn("LIMITED EDITION", eligible(base))
        self.assertNotIn(headlines[2], eligible(base))
        self.assertNotIn(headlines[3], eligible(base))
        supported = {**base, "worldwide_verified": True, "no_second_run_verified": True,
                     "remaining_editions": 100, "editions_sold": 0}
        self.assertTrue(set(headlines) | set(ads_page.ie_visuals.SAFE_HEADLINES) <= set(eligible(supported)))
        for remaining, sold in ((99, 1), (100, 1), (None, None)):
            self.assertNotIn(headlines[5], eligible({**supported, "remaining_editions": remaining, "editions_sold": sold}))
        self.assertNotIn(headlines[0], eligible({**base, "worldwide_verified": "false"}))
        seen = set()
        for token in map(str, range(40)):
            rows = self.visuals(token, {"edition_limit": 100, "worldwide_edition_verified": True,
                                      "no_second_run_verified": True, "remaining_editions": 100, "editions_sold": 0})
            seen.update(r["headline_text"] for r in rows)
            self.assertEqual(len({r["headline_text"] for r in rows}), 3)
            reserves = [h for r in rows for h in [r["headline_fit_fallback"], *r["eligible_headline_alternatives"]]]
            self.assertTrue(all(r["eligible_headline_alternatives"] for r in rows))
            self.assertFalse({h for r in rows for h in r["eligible_headline_alternatives"]} & {r["headline_text"] for r in rows})
        self.assertTrue(seen <= set(eligible(supported)))
        self.assertGreater(len(seen), len(headlines) + len(ads_page.ie_visuals.SAFE_HEADLINES))

    def test_expanded_rooms_are_reachable_and_route_appropriate(self):
        seen = [set(), set(), set()]
        for token in map(str, range(80)):
            for i, row in enumerate(self.visuals(token)):
                self.assertIn(row["room_type"], ads_page.ie_visuals.ROOM_OPTIONS[i])
                seen[i].add(row["room_type"])
        for i in range(3):
            self.assertEqual(seen[i], set(ads_page.ie_visuals.ROOM_OPTIONS[i]))
            self.assertGreaterEqual(len(seen[i]), 8)

    def test_unverified_baseball_has_no_assumed_limit(self):
        rows = ads_page.resolve_standard_instant_experience_visuals(
            product_name="Collector Print", category="Baseball")
        self.assertTrue(all(not r["scarcity_verified"] for r in rows))
        self.assertEqual(len({r["headline_text"] for r in rows}), 3)
        self.assertTrue(all("100" not in r["headline_text"] for r in rows))

    def test_prominence_and_underline_are_explicit_without_weakening_fidelity(self):
        for prompt in self.prompts({"edition_limit": 100}):
            self.assertIn("Achieve prominence through camera distance", prompt)
            self.assertIn("Complete frame visible", prompt)
            self.assertIn("Width targets yield to source aspect ratio", prompt)
            self.assertIn("full measured glyph width", prompt)
            self.assertIn("most important scarcity term", prompt)
            self.assertNotIn("96-100% of the complete measured headline", prompt)
            self.assertIn("no decorative flourishes", prompt)

    def test_fingerprints_capture_new_layouts(self):
        for i, visual in enumerate(self.visuals(), 1):
            fp = ads_page.standard_instant_experience_fingerprint(i, visual)
            self.assertEqual(fp["visual_family"], visual["visual_family"])
            self.assertEqual(fp["camera_family"], visual["camera_side"])
            self.assertEqual(fp["urgency_placement"], visual["overlay_position"])
            self.assertEqual(fp["campaign_line"], visual["headline_text"])

    def test_group_tables_and_setup_contract(self):
        grouped = ads_page.build_standard_instant_experience_group_output_contract(
            product_name="Collector Cricket Print", category="Cricket", country="Australia")
        self.assertEqual(grouped.count("\nIMAGE GENERATION PROMPT\n"), 3)
        self.assertEqual(grouped.count("\nAD COPY\n"), 3)
        self.assertNotIn("COPY VARIATIONS", grouped)
        master = ads_page.build_ads_prompt("Collector Cricket Print", "Cricket", "Australia", "Instant Experience")
        self.assertIn(ads_page.META_AD_URL_PARAMETERS, master)
        self.assertIn("Catalogue product headline field uses: product.name", master)


if __name__ == "__main__":
    unittest.main()
