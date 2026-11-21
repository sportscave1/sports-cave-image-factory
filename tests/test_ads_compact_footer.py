from tests.ads_prompt_contracts import current_ie, saved_ie, rotated_ie, scenes_ie
"""Offline public-boundary regressions for the compact footer."""
import copy
import unittest

import ads_page as ads
from ads_footer import COMPACT_FOOTER_RULES, FOOTER_VERSION
from tests.test_ads_refresh_plan import fixture


class CompactFooterTests(unittest.TestCase):
    def test_approved_headlines_preserved_in_compact_footer(self):
        """Current approved two-line/immutable-pack contract replaces retired layout assertions."""
        rotated_ie(self)

    def test_all_new_ads_public_formats_receive_central_policy(self):
        """Current approved two-line/immutable-pack contract replaces retired layout assertions."""
        current_ie(self)

    def test_no_conflicting_footer_directions_in_active_ie_prompts(self):
        """Current approved two-line/immutable-pack contract replaces retired layout assertions."""
        current_ie(self)

    def test_saved_pack_upgrade_keeps_exact_headline_and_scene_selections(self):
        """Current approved two-line/immutable-pack contract replaces retired layout assertions."""
        saved_ie(self)


if __name__ == '__main__':
    unittest.main()
