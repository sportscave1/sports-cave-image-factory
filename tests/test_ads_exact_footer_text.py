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
    assert 'These three fields are the complete footer text' in prompt
    assert 'never extract, repeat or retype the number' in prompt
    assert 'count visible text baselines' in prompt
    assert 'Inspect the exported JPEG again' in prompt
    assert 'Emit the completion marker only after' in prompt
    assert prompt.count('Footer baseline map: HEADLINE on line 1; SUPPORTING LINE on line 2; CTA on line 3.')==3
    assert 'Always highlight all three digits' not in prompt
    assert 'full number 100 only' not in prompt
    for selected in record['product_metadata']['instant_experience_footer_selections']:
        assert '\nHEADLINE: '+selected['headline_text'] in prompt
        assert '\nSUPPORTING LINE: '+selected['supporting_line'] in prompt
    for name in ('ad_copy.csv','collector-hallway.jpg','architectural-wall.jpg','man-cave.jpg'):
        assert '/fixture/'+name in prompt


def test_reserve_is_one_missing_slot_and_never_a_safety_retry():
    assert 'three-cover Instant Experience task, never Carousel or Single Image' in RULES
    assert 'provider explicitly identifies a retryable technical failure' in RULES
    assert 'at most one reserve-room attempt' in RULES
    assert 'private collector study or a sunlit reading lounge' in RULES
    assert 'retain its camera role, product scale, footer wording, route identity, filename and CSV row' in RULES
    assert 'never an additional fourth cover' in RULES
    assert 'safety rejection, moderation_blocked result or unexplained rejection never authorizes' in RULES
    assert 'recovery of the existing bytes, not another image generation' in RULES


def test_project_sources_cannot_describe_a_separate_gold_number_row():
    for name in ('BASELINE_FOOTER_TYPOGRAPHY.txt','PROJECT_ROLE_AND_TASK_PRIORITY.txt'):
        text=(Path('docs/meta_ads_project')/name).read_text(encoding='utf8')
        assert 'EXACT FOOTER TEXT AND LINE COUNT' in text
        assert 'Keep those digits on the headline baseline' in text
        assert 'Any extra text, missing field or wrapped field requires correction' in text
        assert 'full number 100 only' not in text
    assert '\nGOLD 100\n' not in (Path('docs/meta_ads_project')/'BASELINE_FOOTER_TYPOGRAPHY.txt').read_text(encoding='utf8')
