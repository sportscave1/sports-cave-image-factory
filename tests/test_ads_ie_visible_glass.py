"""Offline exported-prompt audit: only glazing wording changes in USA/Australia IE."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
import ads_page as ads
import ads_ie_glazing as glass
import sports_cave_physical_realism as physical

FIXTURE=Path(__file__).parent/'fixtures/ads_ie_glazing_baseline.json'
def digest(value):return hashlib.sha256(value.encode()).hexdigest()
def visuals(args):return ads.resolve_standard_instant_experience_visuals(**{k:v for k,v in args.items() if k!='campaign_type'})

class VisibleGlassTests(unittest.TestCase):
    def test_exported_prompts_change_only_the_audited_glazing_clauses(self):
        for case in json.loads(FIXTURE.read_text()):
            args=case['args'];result=ads.build_ads_result_record(**args)
            with self.subTest(market=args['country'],campaign=args['campaign_type']):
                self.assertEqual(digest(result['master_prompt']),case['expected_prompt_sha256'])
                rows=visuals(args) if args['campaign_type']=='Instant Experience' else []
                unchanged=[{k:v for k,v in row.items() if k not in ('glazing_treatment','scene_brief')} for row in rows]
                self.assertEqual(digest(json.dumps(unchanged,sort_keys=True)),case['unchanged_visuals_sha256'])
                for i,(row,expected) in enumerate(zip(rows,case['expected_standalone_sha256']),1):
                    prompt=ads.build_standard_instant_experience_image_prompt(i,row,product_name=args['product_name'],category=args['category'],country=args['country'])
                    self.assertEqual(digest(prompt),expected)

    def test_shared_individual_and_final_wrappers_agree_for_both_markets(self):
        for country in ('USA','US','United States','Australia','AU'):
            args=dict(product_name='Collector Edition',category='Cricket',country=country,campaign_type='Instant Experience',variation_token='glazing',product_metadata={'edition_limit':100})
            rows=visuals(args);result=ads.build_ads_result_record(**args)
            prompts=[result['master_prompt'],ads.build_instant_experience_shared_template(usa=ads.normalize_country_language_key(country)=='USA',controlled_glazing=True)]
            prompts += [ads.build_standard_instant_experience_image_prompt(i,row,product_name=args['product_name'],category=args['category'],country=country) for i,row in enumerate(rows,1)]
            for prompt in prompts:
                self.assertIn(glass.REQUIREMENT,prompt)
                self.assertNotIn('recognition takes priority over reflection visibility',prompt)
                self.assertIn('controlled portion of the glass',prompt)
                self.assertIn('rather than remove them',prompt)
                self.assertIn('frame-edge highlights alone do not count',prompt)
            for i,row in enumerate(rows,1):
                scene=ads.build_instant_experience_execution_image_brief(i,row)
                self.assertIn(glass.REQUIREMENT,scene)
                self.assertIn(row['reflection_source'],scene)
                self.assertIn(row['reflection_placement'],scene)
            self.assertIn(glass.REQUIREMENT,physical.apply_context(result['master_prompt'],result['product_metadata']))

    def test_saved_explicit_glazing_and_saved_prompt_are_not_upgraded(self):
        for country in ('USA','Australia'):
            args=dict(product_name='Saved Edition',category='Cricket',country=country,campaign_type='Instant Experience',variation_token='saved',product_metadata={'edition_limit':100})
            rows=visuals(args)
            for row in rows:row['glazing_treatment']='Previously approved glazing instructions; preserve verbatim.'
            metadata={'edition_limit':100,'instant_experience_scene_selections':copy.deepcopy(rows)}
            restored=visuals({**args,'product_metadata':metadata})
            self.assertEqual([r['glazing_treatment'] for r in restored],[r['glazing_treatment'] for r in rows])
            saved=ads.build_ads_result_record(**args);saved['master_prompt']='Previously approved complete prompt'
            original=copy.deepcopy(saved)
            self.assertIs(ads.ensure_current_ads_result_prompt(saved),saved)
            self.assertEqual(saved,original)

    def test_refinement_resolver_is_outside_this_upgrade(self):
        rows=ads.resolve_standard_instant_experience_visuals(product_name='Winner',category='Cricket',country='USA',usa_upgrade=False)
        self.assertFalse(any(glass.active(r) for r in rows))

    def test_unframed_does_not_gain_a_pane(self):
        rows=ads.resolve_standard_instant_experience_visuals(product_name='Unframed Print',category='Cricket',country='Australia',product_metadata={'physical_product':{'frame_label':'Unframed'}})
        if physical.is_unframed(rows[0]['physical_product']):
            self.assertTrue(all('no added glazing' in r['glazing_treatment'] for r in rows))
        else:
            self.fail('Unframed fixture was not resolved as unframed')

if __name__=='__main__':unittest.main()
