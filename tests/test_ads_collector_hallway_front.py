"""Room-role correction without changing footer, references or durable handoff slots."""
import copy
import subprocess
import pytest
import ads_page as ads
import ads_ie_scenes as scenes
from ads_footer import COMPACT_FOOTER_RULES
from ads_image_contracts import INSTANT_EXPERIENCE_CONCEPTS
from design_publish_ad import COVERS, delivery_prompt


@pytest.mark.parametrize('country', ['USA', 'Australia', 'UK', 'Canada', 'New Zealand'])
def test_second_slot_is_a_front_view_collector_hallway_in_every_export(country):
    result = ads.build_ads_result_record('Synthetic Collector Edition', 'NBA', country,
        'Instant Experience', variation_token='hallway-role', product_metadata={'edition_limit': 100})
    visuals = ads.resolve_standard_instant_experience_visuals(product_name=result['product_name'],
        category='NBA', country=country, variation_token='hallway-role', product_metadata=result['product_metadata'])
    first, second, third = visuals
    assert 'collector hallway' in second['room_type']
    assert 'collector hallway' in second['home_setting'].lower()
    assert second['camera_role'] == 'FRONT'
    assert first['home_setting'] != second['home_setting']
    assert second['spatial_family'] == 'entry gallery axis'
    assert 'Front-view collector hallway' in second['scene_brief']
    standalone = ads.build_standard_instant_experience_image_prompt(2, second,
        product_name=result['product_name'], category='NBA', country=country)
    combined = delivery_prompt(result, 'Verified original product fixture', '/fixture', 'fixture-job')
    for prompt in (standalone, combined):
        assert 'HEADLINE: Claim Your Edition' in prompt
        assert '112 px' in prompt
        for stale in ('ARCHITECTURAL WALL', 'Architectural Wall', 'Artwork-first architectural product wall:',
                      'Ad 2 as the straight-on architectural product wall', 'tiny but recognisable softly lit home-context glimpse'):
            assert stale not in prompt
        assert 'AD 2 ONLY — SINGLE-LINE GUNMETAL BADGE FOOTER' in prompt
        assert 'Never use a previously generated mockup as the artwork source' in prompt
    assert 'SC_AD_READY: fixture-job' in combined and 'SC_AD_BLOCKED:' in combined
    assert 'Filenames identify saved delivery slots' in combined
    assert '/fixture/architectural-wall.jpg' in combined
    assert combined.count('\nHEADLINE: ') == 3
    assert combined.count('\nSUPPORTING LINE: ') == 2
    assert combined.count('\nCTA: CLAIM YOUR EDITION') == 2


def test_all_fresh_second_slot_candidates_have_hallway_depth_and_no_lounge_identity():
    for scene in scenes.SCENES[1]:
        assert 'collector hallway' in scene['room_type']
        assert 'collector hallway' in scene['home_setting'].lower()
        assert any(word in scene['architectural_cue'] for word in ('corridor', 'passage', 'hall'))
        assert 'tiny' not in scene['architectural_cue']


def test_existing_artifact_and_csv_ids_remain_compatible():
    assert COVERS == {'premium_scarcity_right': 'collector-hallway.jpg',
                      'premium_scarcity_front': 'architectural-wall.jpg',
                      'premium_scarcity_left': 'man-cave.jpg'}
    assert INSTANT_EXPERIENCE_CONCEPTS[1]['scene_name'] == 'Collector Hallway Front View'
    result = ads.build_ads_result_record('Synthetic Collector Edition', 'NBA', 'USA',
        'Instant Experience', variation_token='saved-hallway', product_metadata={'edition_limit': 100})
    result.update(master_prompt='Saved submitted prompt', generated_ad_output='Existing output')
    before = copy.deepcopy(result)
    assert ads.ensure_current_ads_result_prompt(result) == before


def test_footer_contract_is_byte_for_byte_unchanged_by_room_correction():
    from pathlib import Path
    before = subprocess.check_output(['git', 'show', 'f4c12e251d3658a3bbde2915c730063f35cb56e0:ads_footer.py'])
    original = {}
    exec(compile(before, '<baseline-footer>', 'exec'), original)
    assert COMPACT_FOOTER_RULES == original['COMPACT_FOOTER_RULES']
