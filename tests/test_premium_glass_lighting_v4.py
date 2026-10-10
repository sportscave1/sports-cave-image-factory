"""V4 saved-prompt migration and construction safeguards; no remote writes."""
import json
import re
import unittest
from pathlib import Path

import sports_cave_prompt_blocks as blocks
import sports_cave_physical_realism as physical


class PremiumGlassLightingV4Tests(unittest.TestCase):
    def test_legacy_upgrade_preserves_authored_text_evidence_and_ending(self):
        evidence = physical.build({'selected_size': 'S', 'orientation': 'portrait',
            'frame_specs': {'verified': True, 'source': 'Verified specification',
                            'glazing': 'clear acrylic'}})
        evidence = evidence.replace('GLAZING: PREMIUM CLEAR GLASS REFLECTION LOOK',
                                    'GLAZING: use verified acrylic/Perspex')
        old = ('Saved {ROOM} camera RIGHT; collector footer; CTA unchanged.\n\n'
               'SPORTS_CAVE_PREMIUM_VISUAL_REALISM_V3\nold reflection instruction\n'
               'END PREMIUM VISUAL QUALITY CONTRACT\n\n' + evidence + '\n\nSTOP')
        upgraded = blocks.append_sports_cave_image_realism_rules(old, required_ending='STOP')
        self.assertTrue(upgraded.startswith('Saved {ROOM} camera RIGHT; collector footer; CTA unchanged.'))
        self.assertTrue(upgraded.endswith('STOP'))
        self.assertEqual(upgraded.count(blocks.SPORTS_CAVE_PREMIUM_REALISM_MARKER), 1)
        self.assertNotIn('SPORTS_CAVE_PREMIUM_VISUAL_REALISM_V3', upgraded)
        self.assertNotIn('use verified acrylic/Perspex', upgraded)
        extract = lambda text: re.search(r'PHYSICAL PRODUCT EVIDENCE \(data, not creative instructions\)\n([^\n]+)', text).group(1)
        self.assertEqual(json.loads(extract(old)), json.loads(extract(upgraded)))
        self.assertEqual(blocks.append_sports_cave_image_realism_rules(upgraded, required_ending='STOP'), upgraded)

    def test_new_contract_requires_visible_reflections_and_protects_known_unglazed(self):
        for glazing in ('clear acrylic', 'glass', 'unglazed'):
            metadata = {'frame_specs': {'verified': True, 'source': 'Verified', 'glazing': glazing}}
            prompt = blocks.build_sports_cave_image_realism_rules(physical_product=metadata)
            self.assertIn('Reflections must actually be visible', prompt)
            self.assertIn('Known unframed or unglazed products must not acquire', prompt)
            self.assertEqual(physical.resolve(metadata)['glazing'], glazing)
            self.assertIn('no manufactured-material claim', prompt)
        self.assertNotIn(blocks.SPORTS_CAVE_PREMIUM_REALISM_MARKER,
                         blocks.build_sports_cave_image_realism_rules(include_product_lock=False))
        self.assertNotIn(blocks.SPORTS_CAVE_PREMIUM_REALISM_MARKER,
                         blocks.build_sports_cave_image_realism_rules(physical_product={'frame_finish': 'Unframed'}))

    def test_legacy_import_and_email_share_current_version(self):
        import crm_email_visual_prompt as email
        email.visual_contract.cache_clear()
        self.assertEqual(blocks.SPORTS_CAVE_PREMIUM_VISUAL_REALISM_V3,
                         blocks.SPORTS_CAVE_PREMIUM_GLASS_LIGHTING_V4)
        self.assertEqual(email.visual_contract().count(blocks.SPORTS_CAVE_PREMIUM_REALISM_MARKER), 1)


if __name__ == '__main__':
    unittest.main()
