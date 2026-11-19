"""Offline regressions for Lewis footer export and unchanged Companion contracts."""
import copy
import pytest
import ads_page as ads
from ads_footer import COMPACT_FOOTER_RULES
import design_publish_ad as companion


@pytest.mark.parametrize('country', ['USA','Australia','UK','Canada','New Zealand'])
@pytest.mark.parametrize('product,sport', [('Legends Never Die - Kobe vs Jordan Wall Art','NBA'),
                                          ('Silver & Soul - Lewis Hamilton Wall Art','Formula One')])
def test_two_line_export_has_no_conflicting_directions(country,product,sport):
    record=ads.build_ads_result_record(product,sport,country,'Instant Experience',variation_token='footer-test')
    prompt=record['master_prompt']
    for old in ('SUPPORTING LINE:', 'Use no underline', '100 unadorned', '100 in antique gold with no underline',
                'Allow the foreground copy to sit over it', 'x = 512', 'Compare the middle line',
                'clean Montserrat sans serif', 'medium-weight sans serif', 'headline 42–48 px',
                '0.04–0.06 em', 'sole typography specification for every image and pack',
                'three centred lines', 'all three lines remain readable', 'distinct supporting lines in every set'):
        assert old not in prompt
    for required in ('native 1024 × 209', 'y = 815', 'LEFT of the badge', 'underline ONLY those three digits',
                     'ITALIC serif headline', 'upright classical SERIF capitals', '0.35–0.45 em',
                     'REFERENCE-LOCKED TYPOGRAPHY', 'project source/Assets',
                     'Render no supporting sentence', 'SAME finished composite', 'never a button',
                     'Exclude FINAL COMPOSITOR DATA', 'Do not send the assigned headline, CTA'):
        assert required in prompt
    assert prompt.count('\nHEADLINE: ')==3
    assert prompt.count('\nCTA: CLAIM YOUR EDITION')==3
    assert prompt.index('4. Immediately generate Image 3') < prompt.index('4a. Composite') < prompt.index('4b. Complete the final creative review') < prompt.index('5. Create and attach')
    for row in record['product_metadata']['instant_experience_footer_selections']:
        assert 'HEADLINE: '+row['headline_text'] in prompt
        assert row['supporting_line'] not in prompt
    delivered=companion.delivery_prompt(record,'fixture reference','/fixture','fixture-job')
    assert 'SC_AD_READY: fixture-job' in delivered and 'SC_AD_BLOCKED:' in delivered
    assert 'Keep the current CSV format. Do not add image URLs to the CSV.' in delivered
    for name in ('ad_copy.csv',*companion.COVERS.values()):assert '/fixture/'+name in delivered


def test_room_tool_input_excludes_copy_and_footer_asset():
    shared=ads.build_instant_experience_shared_template()
    for forbidden in ('HEADLINE:', 'CTA:', 'CLAIM YOUR EDITION', 'sports-cave-ad-footer-example.jpg', 'SUPPORTING LINE'):
        assert forbidden not in shared
    rows=ads.resolve_standard_instant_experience_visuals(product_name='Legends Never Die',category='NBA',country='USA',variation_token='footer-test')
    for index,row in enumerate(rows,1):
        brief=ads.build_instant_experience_execution_image_brief(index,row)
        room,compositor=brief.split('END ROOM IMAGE SPECIFICATION')
        assert row['headline_text'] not in room
        assert row['supporting_line'] not in brief
        assert 'HEADLINE: '+row['headline_text'] in compositor
        standalone=ads.build_standard_instant_experience_image_prompt(index,row,product_name='Legends Never Die',category='NBA',country='USA')
        assert 'SUPPORTING LINE:' not in standalone
        assert 'END ROOM IMAGE SPECIFICATION' in standalone
        assert COMPACT_FOOTER_RULES in standalone


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
