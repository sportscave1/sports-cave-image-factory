"""Owner-approved defaults at public generation/copy boundaries, offline only."""
import copy
import unittest
import ads_page as ads
import sports_cave_physical_realism as physical
import sports_cave_prompt_blocks as blocks
import product_upload_lifestyle as lifestyle

class OwnerDefaultsTests(unittest.TestCase):
    def test_all_meta_formats_generate_with_missing_and_false_legacy_flags(self):
        for campaign in ('Instant Experience','Carousel','Single Image / Video'):
            for refresh in (False,True):
                for legacy in ({}, {'edition_limit':None,'WORLDWIDE_VERIFIED':False,'worldwide_edition_verified':False}):
                    result=ads.build_ads_result_record('Synthetic Collector Edition','Cricket','Australia',campaign,
                        variation_token='owner-defaults',product_metadata=legacy,
                        creative_refresh_context={'winning_primary_text':'Synthetic winner','winning_headline':'Synthetic headline'} if refresh else None)
                    prompt=result['master_prompt']
                    self.assertIn('87 × 62 cm',prompt)
                    self.assertIn('premium glass',prompt)
                    self.assertIn('100 worldwide',prompt)
                    self.assertNotIn('WORLDWIDE_VERIFIED',prompt)
                    self.assertNotIn('request product/variant confirmation',prompt)
                    self.assertNotIn('confirm if unknown',prompt)
                    if campaign=='Instant Experience':
                        selected=result['product_metadata']['instant_experience_footer_selections']
                        self.assertEqual(len({r['headline_text'] for r in selected}),3)
                        self.assertTrue(all(r['headline_text'] in ads.ie_visuals.HEADLINES for r in selected))
                        self.assertIn('headline 42–48 px',prompt)
                        self.assertIn('CTA 26–28 px',prompt)
                        self.assertIn('18–20%',prompt)

    def test_saved_assignments_and_rooms_survive_default_upgrade(self):
        result=ads.build_ads_result_record('Synthetic Collector Edition','Cricket','Australia','Instant Experience',variation_token='saved',product_metadata={'edition_limit':100})
        stale=copy.deepcopy(result)
        stale['prompt_contract_version']='previous-physical-policy'
        for scene in stale['product_metadata']['instant_experience_scene_selections']:
            scene['glazing_treatment']='confirm if unknown; preserve acrylic'
        upgraded=ads.ensure_current_ads_result_prompt(stale)
        self.assertEqual(result['product_metadata']['instant_experience_footer_selections'],upgraded['product_metadata']['instant_experience_footer_selections'])
        for old,new in zip(result['product_metadata']['instant_experience_scene_selections'],upgraded['product_metadata']['instant_experience_scene_selections']):
            self.assertEqual({k:v for k,v in old.items() if k!='glazing_treatment'}, {k:v for k,v in new.items() if k!='glazing_treatment'})
        self.assertNotIn('confirm if unknown',upgraded['master_prompt'])
        self.assertIs(ads.ensure_current_ads_result_prompt(upgraded),upgraded)

    def test_copy_upgrade_retains_authored_scene_and_portrait_scale(self):
        prompt='Keep this exact blue room and left camera.\n\n'+physical.build({'orientation':'portrait'})
        copied=blocks.append_sports_cave_image_realism_rules(prompt)
        self.assertTrue(copied.startswith('Keep this exact blue room and left camera.'))
        self.assertEqual(copied.count(physical.MARKER),1)
        self.assertIn('"width_cm": 62',copied)
        self.assertIn('"height_cm": 87',copied)
        self.assertEqual(copied,blocks.append_sports_cave_image_realism_rules(copied))

    def test_saved_lifestyle_size_and_glazing_clauses_are_upgraded_only(self):
        raw='Exact custom room, right camera.\nWhere the selected product is confirmed as A1, use genuine A1 print dimensions:\n841 × 594 mm\nIf the source frame proportions contradict the intended scale or physical specifications, request clarification.\nPreserve verified product construction. If the actual front is acrylic rather than glass, depict realistic transparent glazing without falsely implying a different manufactured material.'
        text=lifestyle.sequential_instructions(raw)
        self.assertIn('Exact custom room, right camera.',text)
        self.assertIn('87 × 62 cm',text)
        self.assertIn('62 × 87 cm',text)
        self.assertIn('premium glass, not acrylic',text)
        self.assertNotIn('request clarification',text)
        self.assertNotIn('841 × 594',text)
        self.assertIn('100 worldwide',text)

if __name__=='__main__': unittest.main()
