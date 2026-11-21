from tests.ads_prompt_contracts import current_ie, saved_ie, scenes_ie, copy_styles, refresh_contract
"""Brand wall styling only; no image generation or visual-compliance claims."""
import json
import unittest

import ads_page as ads
import ads_ie_scenes as scenes
import ads_refresh_plan as refresh
import ads_refresh_generation as generation


FINISHES = {"matte painted brick", "textured plaster", "concrete", "natural stone", "aged timber"}
COLOURS = ("charcoal", "graphite", "smoky grey", "deep navy", "midnight blue", "heritage green",
           "muted olive", "earthy taupe", "weathered stone")


class BrandRoomPaletteTests(unittest.TestCase):
    def test_only_brand_walls_are_automatic_candidates(self):
        for colour, _, _, _, finish in scenes.WALLS:
            self.assertTrue(any(c in colour for c in COLOURS), colour)
            self.assertIn(finish, FINISHES)
        for style in refresh.STYLES:
            self.assertTrue(any(c in style["wall_hue"] for c in COLOURS), style)
            self.assertIn(style["wall_material"], FINISHES)

    def test_both_selectors_mix_values_and_finishes_without_slot_colour_locks(self):
        fresh_history = []
        new_colours, refresh_colours = [set() for _ in range(3)], [set() for _ in range(3)]
        for seed in range(60):
            pack = scenes.select(str(seed), {}, recent=fresh_history)
            self.assertEqual(len({s["wall_colour_family"] for s in pack}), 3)
            self.assertEqual(len({s["wall_finish"] for s in pack}), 3)
            self.assertEqual({s["wall_lightness"] for s in pack}, {"dark", "mid", "light"})
            self.assertEqual(len({s["home_setting"] for s in pack}), 3)
            self.assertFalse(any(scenes._history_conflict(s, old) for s in pack for old in fresh_history[:36]))
            fresh_history = pack + fresh_history
            styles = refresh.select_styles(seed, category="MMA")
            self.assertEqual(len({s["wall_material"] for s in styles}), 3)
            self.assertEqual({s["wall_value"] for s in styles}, {"dark", "mid", "light"})
            self.assertEqual(len({s["architecture"] for s in styles}), 3)
            for i in range(3):
                new_colours[i].add(pack[i]["wall_colour_family"])
                refresh_colours[i].add(styles[i]["wall_hue"])
        self.assertTrue(all(len(values) >= 4 for values in new_colours + refresh_colours))

    def test_complete_new_and_refresh_exports_share_style_and_keep_copy_contracts(self):
        """Validate the active approved contract, not a superseded full-prompt snapshot."""
        current_ie(self)
        refresh_contract(self)

    def test_saved_packs_are_not_restyled_when_reopened(self):
        """Validate the active approved contract, not a superseded full-prompt snapshot."""
        saved_ie(self)


if __name__ == "__main__":
    unittest.main()
