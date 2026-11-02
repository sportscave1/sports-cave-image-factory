"""Source evidence regressions; offline only, no customer or provider writes."""
import copy
import csv
import hashlib
import io
import json
from pathlib import Path
from unittest.mock import patch
import unittest
import ads_page as ads
import ads_refresh_preserve as policy
import ads_refresh_reference as reference
import meta_review_handoff as handoff

FIX=Path(__file__).parent/'fixtures'
PRODUCTS=json.loads((FIX/'refresh_canonical_products.json').read_text(encoding='utf-8'))
WINNERS=(
    dict(product='The Final Lap #17',scene='Grey hallway; dark floating console at left; circular object; warm daylight; wooden floor.',
         headline='The Final Lap #17 Edition',footer='ONLY 100 WILL EVER EXIST',subline='A limited edition for fans of The Final Lap #17.',
         destination='https://fb.com/canvas_doc/3137068479972407',format='SINGLE_IMAGE',conflict='Winner year/details differ from current canonical design.'),
    dict(product='The Mentality Jordan vs Bryant Legacy Edition Wall Art',scene='Close edition on light textured wall; partial living space at left; broad textured dark footer with gold lettering.',
         headline='Built Different.',footer='LIMITED TO 100 WORLDWIDE.',subline='Once it sells out, it’s done.',
         destination='https://fb.com/canvas_doc/2300967130314880',format='SINGLE_IMAGE',conflict='Winner title, border and plaque layout differ from current canonical design.'),
)


def record(winner=WINNERS[0],campaign='Single Image / Video'):
    p=PRODUCTS[WINNERS.index(winner)]
    canonical=reference.canonical_variant_image(p,p['handle'],frame_finish='Black')
    return ads.build_ads_result_record(winner['product'],'Motorsport' if winner==WINNERS[0] else 'NBA','Australia' if winner==WINNERS[0] else 'USA',campaign,
        variation_token='preserve',creative_refresh_context={
            'winning_primary_text':'Exact source primary text','winning_headline':winner['headline'],
            'canonical_reference':canonical,'source_winner':{'creative_format':winner['format'],'destination_url':winner['destination'],
                'scene':winner['scene'],'footer_headline':winner['footer'],'footer_support':winner['subline'],
                'cta':'CLAIM YOUR EDITION','image_sha256':hashlib.sha256(b'original').hexdigest()}})


def executions():
    return [dict(position=i,winner_reference='WINNER_IE',reference_inspected=True,canonical_inspected=True,
                 observations={'scene':'observed source'},keep='All source components except selected written headline',
                 change='Test one written headline',improvement='Test clearer identification',secondary_differences='none',
                 changed_components=['headline'],image_action='reuse_original',unresolved_conflicts=[],image_prompt='WINNER_IE and CANONICAL_PRODUCT. Reuse original bytes; no image generation.') for i in range(1,4)]


class PreserveWinnerTests(unittest.TestCase):
    def test_new_ads_byte_isolation(self):
        for c in json.loads((FIX/'refresh_preserve_new_ads_baseline.json').read_text()):
            r=ads.build_ads_result_record(**c['args'])
            self.assertEqual(hashlib.sha256(r['master_prompt'].encode()).hexdigest(),c['prompt_sha256'])
            self.assertEqual(hashlib.sha256(json.dumps(r['instant_experience_fingerprints'],sort_keys=True).encode()).hexdigest(),c['visuals_sha256'])

    def test_observed_winners_keep_separate_scenes_and_copy_and_no_preselected_changes(self):
        for w in WINNERS:
            r=record(w);prompt=r['master_prompt'];plan=r['creative_refresh_context']['refresh_plan']
            self.assertEqual(r['campaign_type'],'Instant Experience')
            direct=ads.build_ads_prompt(w['product'],r['category'],r['country'],'Single Image / Video',creative_refresh_context=r['creative_refresh_context'])
            self.assertIn('Campaign format: Instant Experience',direct)
            self.assertEqual(plan['styles'],[])
            self.assertEqual(r['instant_experience_fingerprints'],[])
            self.assertIn(w['scene'],prompt);self.assertIn(w['headline'],prompt);self.assertIn(w['subline'],prompt)
            self.assertTrue(prompt.startswith(policy.VERSION))
            for forbidden in ('Redesign architecture','three genuinely different environments','Select three different approved headlines','Refresh all required CSV copy fields substantially','SPORTS CAVE COMPACT RESTORED SUBHEADLINE FOOTER'):
                self.assertNotIn(forbidden,prompt)
            self.assertIn('ONE declared test component',prompt)
            self.assertIn('reuse the original image bytes',prompt)

    def test_format_hydration_and_csv_use_canvas_evidence(self):
        for w in WINNERS:
            source={'creative_format':'SINGLE_IMAGE','destination_url':w['destination']}
            self.assertEqual(handoff.resolve_campaign_type(source)['campaign_type'],'Instant Experience')
            r=record(w)
            rows=list(csv.DictReader(io.StringIO(ads.build_instant_experience_copy_csv(r,blank=True).decode('utf-8-sig'))))
            self.assertEqual(len(rows),3)
            self.assertTrue(all(x['campaign_type']==ads.INSTANT_EXPERIENCE_COPY_CSV_CAMPAIGN_TYPE for x in rows))
            self.assertEqual([x['route_key'] for x in rows],[c['id'] for c in ads.INSTANT_EXPERIENCE_CONCEPTS])
            self.assertEqual(handoff.resolve_campaign_type({**source,'creative_format':'CAROUSEL'})['campaign_type'],'Carousel')

    def test_canonical_variant_resolution_not_first_image(self):
        for p in PRODUCTS:
            result=reference.canonical_variant_image(p,p['handle'],frame_finish='Black')
            self.assertIn('black',result['url'])
            self.assertNotIn('oak',result['url'])
            with self.assertRaises(ValueError):reference.canonical_variant_image(p,'wrong-edition',frame_finish='Black')
            with self.assertRaises(ValueError):reference.canonical_variant_image(p,p['handle'])
            bad=copy.deepcopy(p);bad['variants'][0]['reference_images'].append({'url':'https://cdn.shopify.com/other.jpg'})
            with self.assertRaises(ValueError):reference.canonical_variant_image(bad,p['handle'],frame_finish='Black')

    def test_actual_bytes_are_embedded_in_existing_clipboard(self):
        html=reference.winning_image_copy_html(b'image bytes','image/png',canonical=True)
        self.assertIn('Copy canonical product image',html)
        self.assertIn('aW1hZ2UgYnl0ZXM=',html)
        self.assertIn('ClipboardItem',html)

    def test_validator_rejects_multiple_changes_and_unresolved_product_conflicts(self):
        r=record();plan=r['creative_refresh_context']['refresh_plan'];rows=executions()
        self.assertEqual(policy.execution_issues(rows,plan,'Instant Experience'),[])
        rows[0]['changed_components']=['headline','lighting']
        self.assertTrue(policy.execution_issues(rows,plan,'Instant Experience'))
        rows=executions();rows[0]['unresolved_conflicts']=[WINNERS[0]['conflict']]
        self.assertTrue(policy.execution_issues(rows,plan,'Instant Experience'))
        rows=executions();rows[0]['image_action']='redraw'
        self.assertTrue(policy.execution_issues(rows,plan,'Instant Experience'))

    def test_original_image_reuse_passes_only_for_original_bytes(self):
        r=record();slots=ads._result_image_slots(r)
        workflow={'ad_notes':{'refresh_executions':executions()},'slots':{s['id']:{'data':b'original'} for s in slots}}
        self.assertEqual(ads._creative_refresh_asset_issues(r,workflow),[])
        workflow['slots'][slots[0]['id']]['data']=b'changed'
        self.assertTrue(ads._creative_refresh_asset_issues(r,workflow))

    def test_canonical_retrieval_uses_bytes_caches_success_and_retries_failure(self):
        from unittest.mock import MagicMock
        st=MagicMock(); p=PRODUCTS[0]
        st.session_state={'meta-review-refresh-source':{'frame_finish':'Black'}}
        row={'shopify_product_id':p['id'],'product_handle':p['handle']}
        with patch('shopify_sync.fetch_product_by_shopify_id',side_effect=[ValueError('Unavailable'),p]) as fetch, patch.object(reference,'load_canonical_bytes',return_value=(b'verified bytes','image/jpeg')) as download, patch('streamlit.components.v1.html') as html:
            reference.render_canonical_reference(st,row,'')
            self.assertNotIn('ads-refresh-canonical-reference',st.session_state)
            reference.render_canonical_reference(st,row,'')
            reference.render_canonical_reference(st,row,'')
            self.assertEqual(fetch.call_count,2)
            download.assert_called_once()
            self.assertEqual(st.session_state['ads-refresh-canonical-reference']['image_sha256'],hashlib.sha256(b'verified bytes').hexdigest())
            self.assertIn('dmVyaWZpZWQgYnl0ZXM=',html.call_args.args[0])

    def test_canonical_ambiguity_requires_selection_and_never_downloads(self):
        from unittest.mock import MagicMock
        st=MagicMock();p=PRODUCTS[0];st.session_state={};st.selectbox.return_value=None
        with patch('shopify_sync.fetch_product_by_shopify_id',return_value=p), patch.object(reference,'load_canonical_bytes') as download:
            reference.render_canonical_reference(st,{'shopify_product_id':p['id'],'product_handle':p['handle']},'')
            download.assert_not_called()
            st.selectbox.assert_called_once()
        for key in ('reference_variants_incomplete',):
            bad=copy.deepcopy(p);bad[key]=True
            with self.assertRaises(ValueError):reference.canonical_variant_image(bad,p['handle'],frame_finish='Black')
        bad=copy.deepcopy(p)
        for v in bad['variants']:v['reference_images_incomplete']=True
        with self.assertRaises(ValueError):reference.canonical_variant_image(bad,p['handle'],frame_finish='Black')

    def test_shopify_optional_query_preserves_default_and_marks_incomplete_media(self):
        import shopify_sync as sync
        raw={'id':'gid://shopify/Product/1','variants':{'nodes':[{'id':'v','media':{'nodes':[{'image':{'url':'https://cdn.shopify.com/exact.jpg'}}],'pageInfo':{'hasNextPage':True}}}]}}
        normalized={'variants':[{'id':'v'}],'metafields':[]}
        with patch.object(sync,'graphql_request',return_value=({'product':raw},'fixture')) as request, patch.object(sync,'normalize_product',side_effect=lambda *a:copy.deepcopy(normalized)):
            result=sync.fetch_product_by_shopify_id('1',config={'store_domain':'example.test'})
            self.assertEqual(request.call_args.args[0],sync.PRODUCT_BY_ID_QUERY)
            self.assertNotIn('reference_images',result['variants'][0])
            result=sync.fetch_product_by_shopify_id('1',config={'store_domain':'example.test'},include_variant_media=True)
            self.assertIn('media(first: 2) { pageInfo { hasNextPage }',request.call_args.args[0])
            self.assertTrue(result['variants'][0]['reference_images_incomplete'])

    def test_source_format_does_not_trust_lookalike_canvas_host(self):
        source={'creative_format':'SINGLE_IMAGE','destination_url':'https://fb.com.attacker.test/canvas_doc/123'}
        self.assertEqual(handoff.resolve_campaign_type(source)['campaign_type'],'Single Image / Video')

    def test_undeclared_copy_changes_are_rejected(self):
        r=record();rows=executions()
        notes={c['id']:[{'primary_text':'Exact source primary text','headline':'Single headline test','cta':''}] for c in ads.INSTANT_EXPERIENCE_CONCEPTS}
        workflow={'ad_notes':{'refresh_executions':rows,'instant_experience_concepts':notes},'slots':{}}
        self.assertEqual(ads.creative_refresh_quality_issues(r,workflow),[])
        notes[ads.INSTANT_EXPERIENCE_CONCEPTS[0]['id']][0]['primary_text']='Unrelated new copy'
        self.assertTrue(any('preserve source primary_text' in x for x in ads.creative_refresh_quality_issues(r,workflow)))

    def test_saved_packages_are_unchanged(self):
        for r in (record(),{'campaign_type':'Carousel','workflow_mode':'creative_refresh','master_prompt':'Old approved prompt','generated_ad_output':'Approved copy'}):
            old=copy.deepcopy(r)
            self.assertIs(ads.ensure_current_ads_result_prompt(r),r)
            self.assertEqual(old,r)


if __name__=='__main__':unittest.main()
