"""Assertions for the currently approved combined IE/two-line footer contract.

Historical geometry and manual Submit expectations belong to saved fixtures;
new records use the current public builder and immutable assigned footer split.
"""
import re
import ads_page as ads
import ads_ie_two_line as footer
from ads_ie_visual_systems import HEADLINES


def current_ie(case, product='Verified Collector Edition', category='Cricket', country='Australia', metadata=None):
    record=ads.build_ads_result_record(product,category,country,'Instant Experience',
        product_url='https://sportscave.com.au/products/verified',variation_token='current-contract',
        product_metadata=metadata if metadata is not None else {'edition_limit':100})
    prompt=record['master_prompt']
    case.assertIn(ads.ADS_IE_COMBINED_EXECUTION_VERSION,prompt)
    case.assertIn(footer.VERSION,record['prompt_contract_version'])
    case.assertIn(product,prompt)
    case.assertIn(f'Sport: {category}; selected market: {country}.',prompt)
    case.assertEqual(prompt.count('\nHEADLINE: '),3)
    case.assertEqual(prompt.count('\nFOOTER SECOND LINE ('),3)
    case.assertNotIn('SUPPORTING LINE:',prompt)
    case.assertNotIn('\nCTA: CLAIM YOUR EDITION',prompt)
    case.assertIn(footer.FOOTER_RULES,prompt)
    case.assertIn('exactly two centred text baselines',prompt)
    case.assertIn('exactly 160 px high',prompt)
    case.assertIn('No collage or triptych',prompt)
    case.assertIn('ORIGINAL product reference',prompt)
    steps = ('1. Resolve all three scenes and final copy', '2. Generate Image 1 (',
             '3. Immediately generate Image 2 (', '4. Immediately generate Image 3 (',
             '5. Create and attach the completed downloadable ad_copy.csv', '6. Display the three matching copy groups')
    positions = [prompt.index(step) for step in steps]
    case.assertEqual(positions, sorted(positions))
    for requirement in ('generate three initial images, one image per ad, in order', 'Deliver exactly three final covers',
                        'Recover or redisplay an existing asset if display fails', 'Never restart the set',
                        '1024 x 1024'):
        case.assertIn(requirement, prompt)
    case.assertEqual(prompt.count(ads.build_instant_experience_fixed_opaque_footer_rules()), 1)
    case.assertIn(','.join(ads.INSTANT_EXPERIENCE_COPY_CSV_HEADERS), prompt)
    briefs=re.findall(r'\nIMAGE GENERATION PROMPT\n(.*?)\nAD COPY\n',prompt,re.S)
    case.assertEqual(len(briefs),3)
    rows=ads.resolve_standard_instant_experience_visuals(product_name=product,category=category,country=country,
        variation_token=record['variation_token'],product_metadata=record['product_metadata'])
    case.assertEqual(len({row['headline_text'] for row in rows}),3)
    for i,(row,brief) in enumerate(zip(rows,briefs),1):
        case.assertIn(row['headline_text'],HEADLINES)
        case.assertIn(footer.image_copy(row),brief)
        image=ads.build_standard_instant_experience_image_prompt(i,row,product_name=product,category=category,country=country)
        case.assertIn(footer.image_copy(row),image)
        case.assertIn('exactly two centred text baselines',image)
        case.assertNotIn('SUPPORTING LINE:',image)
        case.assertEqual(image.count('PRODUCT LOCK — ABSOLUTE'), 1)
        case.assertIn(row['scene_brief'], image)
        case.assertIn(row['camera_side'], image)
        case.assertNotIn('CREATIVE_VARIATION_TOKEN:', image)
        for j, sibling in enumerate(rows, 1):
            if i != j:
                case.assertNotIn(sibling['architecture_style'], brief)
                case.assertNotIn('HEADLINE: ' + sibling['headline_text'], brief)
        case.assertEqual(row['meta_headline_text'],row['supporting_line'] if row['footer_second_line_kind']=='CTA' else 'Claim Your Edition')
    case.assertIs(ads.ensure_current_ads_result_prompt(record),record)
    case.assertEqual(record['master_prompt'],record['generated_ad_output'])
    return record,rows,briefs


def saved_ie(case):
    import copy
    record,_,_=current_ie(case)
    original=copy.deepcopy(record)
    original['master_prompt']='Previously submitted approved output, kept verbatim'
    original['generated_ad_output']=original['master_prompt']
    original['prompt_contract_version']='Historical saved footer profile'
    before=copy.deepcopy(original)
    case.assertIs(ads.ensure_current_ads_result_prompt(original),original)
    case.assertEqual(original,before)
    reopened=ads.build_ads_result_record(record['product_name'],record['category'],record['country'],'Instant Experience',
        product_metadata=copy.deepcopy(record['product_metadata']),variation_token='different')
    for key in ('instant_experience_scene_selections','instant_experience_footer_selections'):
        case.assertEqual(record['product_metadata'][key],reopened['product_metadata'][key])


def rotated_ie(case):
    seen=set();history=[]
    for seed in map(str,range(16)):
        record=ads.build_ads_result_record('Verified Collector Edition','Cricket','Australia','Instant Experience',
            variation_token=seed,product_metadata={'edition_limit':100},recent_instant_experience_fingerprints=history)
        selected=record['product_metadata']['instant_experience_footer_selections']
        heads=[row['headline_text'] for row in selected]
        case.assertEqual(len(set(heads)),3)
        case.assertTrue(set(heads)<=set(HEADLINES))
        seen.update(heads);history=record['instant_experience_fingerprints']+history
    case.assertEqual(seen,set(HEADLINES))
    # Owner-confirmed edition policy is 100 worldwide; historical evidence-flag pools are retired.
    for context in ({},{'edition_limit':100},{'edition_limit':250}):
        case.assertEqual(set(ads.ie_visuals.eligible_headlines(context)),set(HEADLINES))


def scenes_ie(case):
    record,rows,briefs=current_ie(case,category='Motorsport')
    case.assertEqual(len({r['architecture_style'] for r in rows}),3)
    case.assertEqual(len({r['wall_colour_family'] for r in rows}),3)
    for row in rows:
        case.assertIn(row['collector_detail'],row['scene_brief'])
        case.assertIn('IE CURATED HOMES',row['scene_selection_version'])
    case.assertEqual([r['scene_slot'] for r in rows],[0,1,2])


def copy_styles(case):
    import ads_ie_copy as writing
    import ads_ie_legacy_description as legacy
    case.assertEqual(legacy.NEW_AD_STYLE_KEYS,('legacy_standard','framed_greatness','choose_a_side'))
    for product,sport in (('Verified Basketball Edition','NBA'),('Verified Race Edition','Motorsport')):
        first=writing.cues(product,sport,'Australia','copy-contract',{})
        case.assertEqual([c['description_style'] for c in first],list(legacy.NEW_AD_STYLE_KEYS))
        case.assertEqual(first,writing.cues(product,sport,'Australia','copy-contract',{}))
        rules=legacy.build_new_ad_style_rules(product,sport,{})
        for marker in ("This isn't wall art.","Greatness doesn't fade.","Every collection needs a centrepiece.",
                       'Only 100 collectors can own this one.','never invent'):
            case.assertIn(marker,rules)
        case.assertEqual(rules.count('CTA: Claim Your Edition'),3)
    current_ie(case)


def refresh_contract(case):
    import csv,io
    from tests.test_ads_refresh_preserve import record
    import ads_refresh_distinct as policy
    result=record(historical=False)
    plan=result['creative_refresh_context']['refresh_plan']
    case.assertEqual(plan['version'],policy.VERSION)
    case.assertTrue(result['master_prompt'].startswith(policy.VERSION))
    case.assertEqual(len(ads._result_image_slots(result)),3)
    case.assertEqual(len(set(plan['on_image_headlines'])),3)
    case.assertTrue(set(plan['on_image_headlines'])<=set(HEADLINES))
    for marker in ('WINNER_IE','CANONICAL_PRODUCT','same observed room TYPE','new scene and camera'):
        case.assertIn(marker,result['master_prompt'])
    csv_text=result['master_prompt'].split('DO NOT RETURN A BLANK TEMPLATE\n',1)[1]
    rows=list(csv.DictReader(io.StringIO(csv_text)))
    case.assertEqual(len(rows),3)
    case.assertEqual(tuple(rows[0]),ads.INSTANT_EXPERIENCE_COPY_CSV_HEADERS)
    case.assertTrue(all(set(row)==set(ads.INSTANT_EXPERIENCE_COPY_CSV_HEADERS) for row in rows))
    case.assertIs(ads.ensure_current_ads_result_prompt(result),result)
