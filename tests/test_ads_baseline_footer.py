"""Offline regressions for Baseline footer export and unchanged Companion contracts."""
import copy
import pytest
import ads_page as ads
from ads_footer import COMPACT_FOOTER_RULES
import ads_ie_two_line as two
import design_publish_ad as companion


@pytest.mark.parametrize('country', ['USA','Australia','UK','Canada','New Zealand'])
@pytest.mark.parametrize('product,sport', [('Legends Never Die - Kobe vs Jordan Wall Art','NBA'),
                                          ('Silver & Soul - Lewis Hamilton Wall Art','Formula One')])
def test_three_line_export_has_no_conflicting_directions(country,product,sport):
    record=ads.build_ads_result_record(product,sport,country,'Instant Experience',variation_token='footer-test')
    prompt=record['master_prompt']
    for old in ('Render no supporting sentence', 'render no supporting sentence',
                'no supporting sentence or FOMO row', 'Exactly two lines',
                'Render exactly three footer lines', 'No supporting sentence or third line',
                'a supporting sentence or third footer line appears', 'FINAL COMPOSITOR DATA',
                'REFERENCE-LOCKED FOOTER V5'):
        assert old not in prompt, old
    for required in ('exactly 160 px high', 'exactly two centred text baselines',
                     'Title type: 50 px', 'CTA type: 23 px', 'Montserrat Regular',
                     'gold shimmer', 'top separator in place'):
        assert required in prompt, required
    assert prompt.count('\nHEADLINE: ')==3
    assert prompt.count('\nCTA: CLAIM YOUR EDITION')==0
    assert prompt.index('4. Immediately generate Image 3') < prompt.index('4b. Complete the final creative review') < prompt.index('5. Create and attach')
    for row in record['product_metadata']['instant_experience_footer_selections']:
        assert 'HEADLINE: '+row['headline_text'] in prompt
        assert row['footer_second_line'] in prompt and row['meta_headline_text'] in prompt
    delivered=companion.delivery_prompt(record,'fixture reference','/fixture','fixture-job')
    assert 'SC_AD_READY: fixture-job' in delivered and 'SC_AD_BLOCKED:' in delivered
    assert 'Keep the current CSV format. Do not add image URLs to the CSV.' in delivered
    for name in ('ad_copy.csv',*companion.COVERS.values()):assert '/fixture/'+name in delivered


def test_image_call_receives_exact_three_line_copy():
    shared = ads.build_instant_experience_shared_template()
    assert two.FOOTER_RULES in shared
    assert 'exactly two centred text baselines' in shared
    rows = ads.resolve_standard_instant_experience_visuals(product_name='Legends Never Die', category='NBA', country='USA', variation_token='footer-test')
    for index, row in enumerate(rows, 1):
        brief = ads.build_instant_experience_execution_image_brief(index, row)
        assert 'IMAGE GENERATION PROMPT' in brief
        assert 'HEADLINE: ' + row['headline_text'] in brief
        assert row['footer_second_line'] in brief
        assert row['meta_headline_text'] in brief
        standalone = ads.build_standard_instant_experience_image_prompt(index, row, product_name='Legends Never Die', category='NBA', country='USA')
        assert row['footer_second_line'] in standalone
        assert 'COMPOSITOR DATA' not in standalone
        assert two.FOOTER_RULES in standalone


def test_saved_assignments_and_completed_results_are_not_rerolled():
    args=('Silver & Soul - Lewis Hamilton','Formula One','USA','Instant Experience')
    original=ads.build_ads_result_record(*args,variation_token='stable-footer')
    reopened=ads.build_ads_result_record(*args,variation_token='stable-footer',product_metadata=copy.deepcopy(original['product_metadata']))
    for key in ('instant_experience_scene_selections','instant_experience_footer_selections'):
        assert reopened['product_metadata'][key]==original['product_metadata'][key]
    saved=copy.deepcopy(original)
    saved['master_prompt']='Previously submitted immutable prompt'
    saved['generated_ad_output']='Already generated approved output'
    assert ads.ensure_current_ads_result_prompt(saved) is saved


@pytest.mark.parametrize('country', ['Australia', 'USA', 'UK', 'Canada', 'New Zealand'])
def test_seasonal_prompt_cannot_restore_third_footer_line(country):
    from ads_black_friday import build_black_friday_prompt
    prompt = ads.build_ads_prompt('Synthetic Collector Edition', 'Cricket', country,
                                 'Instant Experience', product_metadata={'edition_limit': 100})
    assert build_black_friday_prompt(prompt) == prompt


def test_baseline_sections_and_live_receipt():
    import json
    from pathlib import Path
    from prompt_library import catalog, digest
    from prompt_bundle import bundle_prompt
    original = json.loads(Path('tests/fixtures/ads_v1_baseline_hashes.json').read_text())
    allowed = {'91a51d174a3108ab54cb4f97', 'e4c95a923482686ea19136c3', '3cb795b06730af64f234ddc9',
               '29739817000c06f922bc9c1b', '3ee6646ef382cd48773bc7ae',
               'd9d02cb110b7f42fd61b3196', '7ca8830571db316b90527e08',
               '704462a5b422e7982db8880f', '7c37c4b9ddc9337b4253c1cc',
               '6137aef6ef1b942197a3aa91'}  # Authorized footer, creative review and room-role updates.
    rows = [p for p in catalog() if p.category == 'Ads']
    assert set(original).issubset({p.key for p in rows})
    assert all(p.path in ('ads_ie_two_line.py', 'ads_reserve_scenes.py') for p in rows if p.key not in original)
    for p in rows:
        if p.key in original and p.key not in allowed:
            assert digest(p.text) == original[p.key], p.symbol or p.path
    manifest = json.loads(Path('prompts/releases.json').read_text())
    for p in [bundle_prompt(rows, 'Ads'), *rows]:
        assert manifest[p.key]['hash'] == digest(p.text)
        assert manifest[p.key]['version'] == '2.0'
        assert manifest[p.key]['label'] == 'Baseline 2.0 - Two-line footer'
    labels = json.loads(Path('prompts/version_labels.json').read_text())
    assert labels['44b05012bd22482ab965ad0b01891d3c'] == 'Collector Beta'
    assert all(v['id'] != '44b05012bd22482ab965ad0b01891d3c' for v in manifest.values())
