"""Offline USA policy and non-USA byte-isolation contracts; no application startup."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
import ads_page as ads
import ads_ie_usa as usa
import ads_ie_copy as writing
import ads_ie_legacy_description as legacy
import ads_black_friday

FIXTURES = Path(__file__).parent / 'fixtures' / 'ads_ie_usa_baseline.json'


class USAInstantExperienceTests(unittest.TestCase):
    def record(self, product='Don Mattingly', sport='Baseball', country='USA', metadata=None, **kw):
        return ads.build_ads_result_record(product, sport, country, 'Instant Experience',
            variation_token='usa-isolation-baseline', product_metadata=metadata or {}, **kw)

    def test_non_usa_formats_and_winners_match_pre_edit_baselines(self):
        checked = 0
        for case in json.loads(FIXTURES.read_text(encoding='utf-8')):
            args = case['args']
            if args['country'] == 'USA' and args['campaign_type'] == 'Instant Experience' and not args.get('creative_refresh_context'):
                continue
            with self.subTest(args=args):
                r = ads.build_ads_result_record(**args)
                self.assertEqual(hashlib.sha256(r['master_prompt'].encode()).hexdigest(), case['prompt_sha256'])
                self.assertEqual(hashlib.sha256(json.dumps(r['instant_experience_fingerprints'],sort_keys=True).encode()).hexdigest(), case['visuals_sha256'])
                checked += 1
        self.assertEqual(checked, 39)

    def test_usa_market_normalization_and_footer_claim_gate(self):
        for market in ('USA', 'US', 'United States'):
            for metadata, expected in (({}, usa.FALLBACK), ({'edition_limit':100}, usa.FALLBACK),
                                       ({'no_reprint_verified':True}, usa.FINALITY),
                                       ({'retires_when_sold_out':True}, usa.FINALITY),
                                       ({'no_reprint_verified':False}, usa.FALLBACK)):
                r = self.record(country=market, metadata=metadata)
                fp = r['instant_experience_fingerprints']
                self.assertEqual(len(fp),3)
                self.assertEqual([v['headline_text'] for v in fp], [usa.HEADLINE]*3)
                self.assertEqual([v['supporting_line'] for v in fp], [expected]*3)
                self.assertEqual([v['cta_text'] for v in fp], ['CLAIM YOUR EDITION']*3)
                self.assertEqual([v['route_key'] for v in fp], list(writing.ROUTES))
                for v in fp:
                    self.assertFalse(ads.validate_instant_experience_on_image_copy(v['headline_text'],v['supporting_line'],v['cta_text']))
                self.assertEqual([v['description_style'] for v in fp], list(legacy.NEW_AD_STYLE_KEYS))

    def test_combined_standalone_and_seasonal_rules_agree(self):
        for name, sport in [('Jordan × Kobe','NBA'),('Don Mattingly','Baseball'),('Shohei Ohtani 50/50','Baseball')]:
            r=self.record(name,sport)
            visuals=ads.resolve_standard_instant_experience_visuals(product_name=name,category=sport,country='USA',product_metadata=r['product_metadata'])
            prompts=[r['master_prompt']]+[ads.build_standard_instant_experience_image_prompt(i,v,product_name=name,category=sport,country='USA') for i,v in enumerate(visuals,1)]
            self.assertTrue(ads.validate_instant_experience_set_differentiation(visuals))
            for prompt in prompts:
                for obsolete in ('Select three different approved headlines','Never repeat a headline or subline','AND visible depth arrangement','imperceptible surface reflections','thumbnail-visible glazing','reflections clearly visible at thumbnail','visible at a 256 × 256 preview','all signature and fixed template lines verbatim'):
                    self.assertNotIn(obsolete,prompt)
                self.assertIn('product recognition takes priority over reflection visibility',prompt)
                self.assertIn('Limited to 100 Worldwide',prompt)
                self.assertIn('A limited run of 100 editions.',prompt)
                self.assertIn('18–20%',prompt)
                self.assertIn('1024 x 1024',prompt)
            self.assertEqual(ads_black_friday.build_black_friday_prompt(r['master_prompt']),r['master_prompt'])
            self.assertEqual(r['master_prompt'].count('IMAGE GENERATION PROMPT\n'),3)
            self.assertIn(ads.WRITTEN_META_HEADLINE_INSTRUCTIONS,r['master_prompt'])
            self.assertIn('USA SUPPORTING WORDING',r['master_prompt'])
            self.assertIn('Shop Now',r['master_prompt'])
            self.assertIn('Download Ad 3',r['master_prompt'])

    def test_campaign_moment_keeps_offer_in_copy_and_fixed_footer(self):
        r = self.record(campaign_moment={'type':'Sale Period','name':'Black Friday','market':'Global',
                                       'promotion':'Free shipping','strength':'Campaign-led'})
        self.assertIn('Exact Promotion or Offer entered: Free shipping',r['master_prompt'])
        self.assertEqual(r['master_prompt'].count('SUPPORTING LINE: '+usa.FALLBACK),3)
        self.assertNotIn('SUPPORTING LINE: EARLY BIRD BLACK FRIDAY',r['master_prompt'])
        self.assertEqual(ads_black_friday.build_black_friday_prompt(r['master_prompt']),r['master_prompt'])

    def test_warm_neutrals_repeat_without_forced_slot_colours(self):
        palettes=[set(),set(),set()]
        previous=[]
        for n in range(8):
            v=ads.resolve_standard_instant_experience_visuals(product_name='Don Mattingly',category='Baseball',country='USA',variation_token=str(n),recent_fingerprints=previous)
            self.assertEqual([row['camera_role'] for row in v],['RIGHT','FRONT','LEFT'])
            self.assertEqual([row['room_profile_key'] for row in v],['hallway_gallery','minimal_art_wall','collector_interior'])
            self.assertTrue(all(row['wall_visual_group']=='neutral' for row in v))
            self.assertTrue(all(row['scene_near_signature'] not in {x['scene_near_signature'] for x in previous} for row in v))
            for i,row in enumerate(v):palettes[i].add(row['wall_colour'])
            previous=list(v)+previous[:30]
        self.assertTrue(all(len(p)>1 for p in palettes))
        # Other-product palette alone is not an image near-duplicate or a reason to reject a neutral.
        args=dict(product_name='Jordan × Kobe',category='NBA',country='USA',variation_token='same')
        self.assertEqual(ads.resolve_standard_instant_experience_visuals(**args),ads.resolve_standard_instant_experience_visuals(**args,recent_fingerprints=[{'wall_colour_family':'beige','wall_finish':'fine plaster','copy_product_key':'another product'}]))

    def test_saved_old_and_new_packs_preserve_copy_and_resolved_choices(self):
        current=self.record(metadata={'no_reprint_verified':True})
        old={'campaign_type':'Instant Experience','country':'USA','master_prompt':'Saved pre-upgrade prompt',
             'generated_ad_output':'Approved copy','prompt_contract_version':'old','standard_ads':[{'headline':'Approved headline'}]}
        for r in (old,current):
            before=copy.deepcopy(r)
            self.assertIs(ads.ensure_current_ads_result_prompt(r),r)
            self.assertEqual(r,before)
        args=dict(product_name='Don Mattingly',category='Baseball',country='USA',product_metadata=current['product_metadata'])
        self.assertEqual(ads.resolve_standard_instant_experience_visuals(**args,variation_token='new-token')[0]['scene_signature'],current['instant_experience_fingerprints'][0]['scene_signature'])
        # An explicitly supplied old specification must not opt into USA selection.
        original=ads.resolve_standard_instant_experience_visuals(product_name='Don Mattingly',category='Baseball',country='USA',usa_upgrade=False)
        meta={'instant_experience_scene_selections':[dict(v) for v in original],
              'instant_experience_footer_selections':[dict(v) for v in original]}
        self.assertFalse(usa.enabled('USA',meta))
        preserved=ads.resolve_standard_instant_experience_visuals(product_name='Don Mattingly',category='Baseball',country='USA',product_metadata=meta)
        self.assertEqual([v['headline_text'] for v in preserved],[v['headline_text'] for v in original])
        self.assertEqual([v['wall_colour'] for v in preserved],[v['wall_colour'] for v in original])

    def test_existing_csv_round_trip_preserves_three_distinct_copy_records(self):
        from tests.test_ads_page import instant_experience_csv_notes
        r=self.record()
        notes=instant_experience_csv_notes()
        for i,(key,rows) in enumerate(notes.items()):
            notes[key]=[rows[0]]
            rows[0]['cta']='Claim Your Edition'
            rows[0]['headline']=['The Standard Endures','A Moment That Matters','For Those Who Remember'][i]
        data=ads.build_instant_experience_copy_csv(r,concept_notes=notes)
        parsed=ads.parse_instant_experience_copy_csv(data,r)
        for key in notes:
            self.assertEqual(parsed[key][0]['headline'],notes[key][0]['headline'])
            self.assertEqual(parsed[key][0]['primary_text'],notes[key][0]['primary_text'])
        self.assertEqual(len(parsed),3)


if __name__=='__main__':unittest.main()
