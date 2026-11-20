"""Offline prompt-boundary checks; these do not claim OCR or image-render guarantees."""
from pathlib import Path
import pytest
import ads_page as ads
from ads_generation_review import RULES
from design_publish_ad import delivery_prompt


@pytest.mark.parametrize('country',['Australia','USA','UK','Canada','New Zealand'])
def test_exact_footer_baselines_reach_every_image_and_final_export(country):
    record=ads.build_ads_result_record('Synthetic Collector Edition','NBA',country,'Instant Experience',
        product_metadata={'edition_limit':100},variation_token='exact-footer')
    prompt=delivery_prompt(record,'Synthetic original reference','/fixture','fixture-job')
    assert prompt.count('\nHEADLINE: ')==3
    assert prompt.count('\nFOOTER SECOND LINE (')==3
    assert 'Render exactly three' not in prompt
    assert 'third text row' in prompt
    assert 'gold 100 digits' in prompt
    assert 'exactly two footer lines' in prompt
    for selected in record['product_metadata']['instant_experience_footer_selections']:
        assert '\nHEADLINE: '+selected['headline_text'] in prompt
        assert selected['footer_second_line'] in prompt
        assert selected['meta_headline_text'] in prompt
    for name in ('ad_copy.csv','collector-hallway.jpg','architectural-wall.jpg','man-cave.jpg'):
        assert '/fixture/'+name in prompt


def test_reserves_are_bounded_missing_slots_and_never_safety_retries():
    from ads_reserve_scenes import RULES
    RULES = ' '.join(RULES.split())
    assert 'three-cover Instant Experience task, never Carousel or Single Image' in RULES
    assert 'provider explicitly identifies a retryable technical failure' in RULES
    assert 'at most two reserve attempts in the pack' in RULES
    assert 'COLLECTOR MAN CAVE' in RULES and 'DARK COLLECTOR STUDIO APARTMENT' in RULES
    assert 'Retain its camera role, product scale, footer wording, route identity, filename and CSV row' in RULES
    assert 'never an additional fourth cover' in RULES
    assert 'safety rejection, moderation_blocked result or unexplained rejection never authorizes' in RULES
    assert 'recovery of the existing bytes, not another image generation' in RULES


def test_project_sources_cannot_describe_a_separate_gold_number_row():
    for name in ('BASELINE_FOOTER_TYPOGRAPHY.txt','PROJECT_ROLE_AND_TASK_PRIORITY.txt'):
        text=(Path('docs/meta_ads_project')/name).read_text(encoding='utf8')
        assert 'exactly two' in text
        assert 'gold 100 digits' in text and 'not a quantity caption' in text
        assert 'Correct defects' in text
        assert 'full number 100 only' not in text
    assert '\nGOLD 100\n' not in (Path('docs/meta_ads_project')/'BASELINE_FOOTER_TYPOGRAPHY.txt').read_text(encoding='utf8')
