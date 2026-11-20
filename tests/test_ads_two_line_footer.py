"""Real generation, saved-selection and CSV boundaries for the two-line split."""
import copy
import pytest
import ads_page as ads
import ads_ie_two_line as two
from ads_ie_visual_systems import HEADLINES
from design_publish_ad import delivery_prompt


@pytest.mark.parametrize('country', ['USA', 'Australia', 'UK', 'Canada', 'New Zealand'])
def test_image_and_written_headline_are_complementary_across_all_markets(country):
    args = ('Synthetic Collector Edition', 'NBA', country, 'Instant Experience')
    record = ads.build_ads_result_record(*args, variation_token='two-line', product_metadata={'edition_limit':100})
    rows = ads.resolve_standard_instant_experience_visuals(product_name=args[0], category='NBA', country=country,
        variation_token='two-line', product_metadata=record['product_metadata'])
    prompt = record['master_prompt']
    assert two.VERSION in record['prompt_contract_version']
    previous = {**record, 'master_prompt':'Previously submitted Baseline 2.0 three-line output', 'generated_ad_output':'Approved originals'}
    assert ads.ensure_current_ads_result_prompt(previous) is previous
    assert prompt.count('\nHEADLINE: ') == 3
    assert prompt.count('\nFOOTER SECOND LINE (') == 3
    for stale in ('Render exactly three', 'three-line typography', 'SUPPORTING LINE:', '\nCTA: CLAIM YOUR EDITION',
                  'AD 2 ONLY', '112 px', 'gunmetal', 'WRITTEN META HEADLINE — PRODUCT MEANING',
                  'ONE short product-specific emotional headline', 'aim for 2–6 words'):
        assert stale not in prompt, stale
    for index, row in enumerate(rows, 1):
        assert row['headline_text'] in HEADLINES
        if row['footer_second_line_kind'] == 'CTA':
            assert row['footer_second_line'] == 'CLAIM YOUR EDITION'
            assert row['meta_headline_text'] == row['supporting_line']
        else:
            assert row['footer_second_line'] == row['supporting_line']
            assert row['meta_headline_text'] == 'Claim Your Edition'
        brief = ads.build_instant_experience_execution_image_brief(index, row)
        image_part = brief.split('\nAD COPY\n')[0]
        assert two.image_copy(row) in image_part
        assert row['meta_headline_text'] not in image_part
        assert 'META HEADLINE — copy/display/CSV only, never inside the image: ' + row['meta_headline_text'] in brief
        standalone = ads.build_standard_instant_experience_image_prompt(index, row,
            product_name=args[0], category='NBA', country=country)
        assert two.image_copy(row) in standalone and 'SUPPORTING LINE:' not in standalone
        assert 'exactly two centred text baselines' in standalone
    reopened = ads.build_ads_result_record(*args, variation_token='two-line', product_metadata=copy.deepcopy(record['product_metadata']))
    assert reopened['product_metadata']['instant_experience_footer_selections'] == record['product_metadata']['instant_experience_footer_selections']
    assert ads.ensure_current_ads_result_prompt(record) is record
    delivery = delivery_prompt(record, 'Synthetic approved original', '/fixture', 'fixture-job')
    assert two.REVIEW in delivery
    assert 'all three lines must be visible' not in delivery
    assert 'SC_AD_READY: fixture-job' in delivery and 'SC_AD_BLOCKED:' in delivery


def test_randomisation_is_persisted_and_uses_both_kinds_without_rerolling_copy():
    seen = set()
    for token in map(str, range(16)):
        record = ads.build_ads_result_record('Synthetic Collector Edition', 'NBA', 'USA', 'Instant Experience', variation_token=token)
        rows = record['product_metadata']['instant_experience_footer_selections']
        seen.update(row['footer_second_line_kind'] for row in rows)
        assert len({row['headline_text'] for row in rows}) == 3
    assert seen == {'CTA', 'FOMO'}


def test_csv_accepts_unused_line_headlines_without_new_columns_or_route_changes():
    from tests.test_ads_page import instant_experience_csv_notes
    record = ads.build_ads_result_record('Synthetic Collector Edition', 'NBA', 'USA', 'Instant Experience', variation_token='csv-split')
    notes = instant_experience_csv_notes()
    selected = record['product_metadata']['instant_experience_footer_selections']
    for concept, row in zip(ads.INSTANT_EXPERIENCE_CONCEPTS, selected):
        notes[concept['id']][0]['headline'] = row['meta_headline_text']
        notes[concept['id']][0]['cta'] = 'Claim Your Edition'
    data = ads.build_instant_experience_copy_csv(record, concept_notes=notes)
    parsed = ads.parse_instant_experience_copy_csv(data, record)
    assert [parsed[c['id']][0]['headline'] for c in ads.INSTANT_EXPERIENCE_CONCEPTS] == [r['meta_headline_text'] for r in selected]


def test_baseline_two_line_profile_retains_original_height_and_premium_type():
    for text in ('exactly 160 px high', 'top seam is y=864', '50 px Baskerville', '0.03 em',
                 '23 px Montserrat Medium', '22 px Montserrat Regular', '64 px horizontal margins',
                 '32 px top padding', '32 px bottom padding', 'gold shimmer'):
        assert text in two.FOOTER_RULES
