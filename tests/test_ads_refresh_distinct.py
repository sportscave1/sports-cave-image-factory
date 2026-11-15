"""New refresh policy and saved-contract isolation; offline fixture evidence only."""
import copy
import csv
import io
import unittest
import ads_page as ads
import ads_refresh_distinct as policy
from tests.test_ads_refresh_preserve import record, WINNERS
from tests.test_ads_refresh_plan import fixture
from tests.test_ads_refresh_workflow import winner, TITLE, ROW


def notes(result):
    plan = result['creative_refresh_context']['refresh_plan']
    canonical = result['creative_refresh_context']['canonical_reference']['url']
    return [dict(position=i, winner_reference='WINNER_IE', reference_inspected=True, canonical_inspected=True,
        observations='Synthetic inspected source', source_room_type='hallway', room_type='hallway',
        scene='hallway', keep='Source warm neutral palette', change='New camera and architecture', improvement='Test visibility',
        secondary_differences='New furniture', camera_treatment=f'camera {i}', scene_treatment=f'architecture {i}',
        changed_components=['camera','scene'], image_action='redraw', shared_product_correction='Use canonical printed details',
        canonical_reference=canonical, on_image_headline=plan['on_image_headlines'][i-1], supporting_line='', cta='CLAIM YOUR EDITION',
        unresolved_conflicts=[], image_prompt='WINNER_IE and CANONICAL_PRODUCT',
        visual_checks={k:True for k in ('product_reference_checked','same_room_type','new_camera_and_scene',
            'distinct_from_source_and_siblings','visible_glazing','footer_checked')}) for i in range(1,4)]


class DistinctRefreshTests(unittest.TestCase):
    def test_both_winners_receive_complete_scoped_contract(self):
        for source in WINNERS:
            r=record(source,historical=False); p=r['master_prompt']
            self.assertTrue(p.startswith(policy.VERSION))
            self.assertIn(source['scene'],p)
            self.assertIn('automatically correct it in all three images',p)
            self.assertIn('same observed room TYPE',p)
            self.assertIn('BOTH camera position',p)
            self.assertIn('No supporting sentence on the image',p)
            self.assertIn('VISIBLE PREMIUM GLASS',p)
            self.assertIn('ONE populated downloadable CSV',p)
            self.assertIn('Regenerate a near-duplicate',p)
            self.assertNotIn('ONE declared test component',p)
            self.assertNotIn('copy-only test reuse',p)
            self.assertNotIn('MANDATORY FINAL INSPECTION — NO ADDITIONAL IMAGE GENERATIONS',p)
            rows=list(csv.DictReader(io.StringIO(p.split('DO NOT RETURN A BLANK TEMPLATE\n')[1])))
            self.assertEqual(len(rows),3)
            self.assertEqual(tuple(rows[0]),ads.INSTANT_EXPERIENCE_COPY_CSV_HEADERS)
            self.assertEqual([r['route_key'] for r in rows],[c['id'] for c in ads.INSTANT_EXPERIENCE_CONCEPTS])

    def test_footer_resolved_once_and_approved_distinct(self):
        r=record(historical=False);context=r['creative_refresh_context'];p=context['refresh_plan']
        self.assertEqual(len(set(p['on_image_headlines'])),3)
        self.assertTrue(set(p['on_image_headlines']) <= set(policy.visuals.HEADLINES))
        self.assertEqual(ads.ads_refresh_generation.plan.current_plan(context,r['campaign_type'],r['product_name'],r['category'],'different'),p)
        selected=policy.build_plan({'on_image_headlines':list(policy.visuals.HEADLINES[:3])},'Instant Experience','P','NBA','seed',[], 'id')
        self.assertEqual(selected['on_image_headlines'],list(policy.visuals.HEADLINES[:3]))

    def test_completion_notes_reject_missing_duplicate_wrong_reference_room_or_footer(self):
        r=record(historical=False);p=r['creative_refresh_context']['refresh_plan'];good=notes(r)
        self.assertEqual(policy.execution_issues(good,p),[])
        self.assertTrue(policy.execution_issues(good[:2],p))
        for field,value in [('canonical_reference','wrong'),('room_type','office'),('image_action','reuse_original'),
                            ('supporting_line','Extra sentence'),('camera_treatment','camera 2'),('scene_treatment','architecture 2')]:
            bad=copy.deepcopy(good);bad[0][field]=value
            self.assertTrue(policy.execution_issues(bad,p),field)
        bad=copy.deepcopy(good);bad[0]['visual_checks']['visible_glazing']=False
        self.assertTrue(policy.execution_issues(bad,p))

    def test_current_app_completion_needs_three_actual_assets_and_distinct_copy(self):
        r=record(historical=False)
        rows={c['id']:[dict(primary_text=f'Meaning {i}',headline=f'Belief {i}',cta='Claim Your Edition')]
              for i,c in enumerate(ads.INSTANT_EXPERIENCE_CONCEPTS)}
        workflow={'ad_notes':{'instant_experience_concepts':rows},'slots':{}}
        self.assertTrue(ads.creative_refresh_quality_issues(r,workflow))
        workflow['slots']={s['id']:dict(valid=True,data=f'image{i}'.encode()) for i,s in enumerate(ads._result_image_slots(r))}
        self.assertEqual(ads.creative_refresh_quality_issues(r,workflow),[])
        slots=list(workflow['slots'].values());slots[1]['data']=slots[0]['data']
        self.assertTrue(ads.creative_refresh_quality_issues(r,workflow))
        rows[ads.INSTANT_EXPERIENCE_CONCEPTS[1]['id']][0]['headline']='Belief 0'
        self.assertTrue(policy.copy_issues([v[0] for v in rows.values()],'Instant Experience'))

    def test_new_carousel_source_produces_three_single_ads_legacy_stays_carousel(self):
        source=winner(True)
        r=ads.build_ads_result_record(TITLE,'Football','Australia','Carousel',product_url=ROW['online_store_url'],
            creative_refresh_context={'source_winner':source,'winning_primary_text':'Source','winning_headline':'Source'})
        self.assertEqual(r['campaign_type'],'Single Image / Video')
        self.assertEqual(len(ads._result_image_slots(r)),3)
        self.assertIn('Campaign format: Single Image / Video',r['master_prompt'])
        self.assertNotIn('ONE refreshed 5-CARD',r['master_prompt'])
        rows=list(csv.DictReader(io.StringIO(r['master_prompt'].split('DO NOT RETURN A BLANK TEMPLATE\n')[1])))
        self.assertEqual(len(rows),3);self.assertEqual(tuple(rows[0]),ads.STANDARD_ADS_CSV_HEADERS)
        old=fixture();before=copy.deepcopy(old)
        self.assertEqual(ads.ensure_current_ads_result_prompt(old),before)
        self.assertEqual(old['campaign_type'],'Carousel')
        self.assertIn('ONE refreshed 5-CARD',old['master_prompt'])

    def test_export_setup_notes_accept_new_scene_treatment(self):
        # The notes contract retains the legacy scene key; no new CSV columns.
        r=record(historical=False)
        self.assertIn('room_type, scene, keep',r['master_prompt'])


if __name__=='__main__':unittest.main()
