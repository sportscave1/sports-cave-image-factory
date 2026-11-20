"""Conditional reserves reach the full pack but never the initial image calls."""
import subprocess
from pathlib import Path
import pytest
import ads_page as ads
import ads_generation_review as review
from ads_reserve_scenes import RULES, VERSION
from ads_ie_two_line import FOOTER_RULES
from design_publish_ad import delivery_prompt


def normalise(text):
    return ' '.join(text.split())


@pytest.mark.parametrize('country', ['USA','Australia','UK','Canada','New Zealand'])
def test_reserves_are_dormant_and_preserve_each_missing_slot(country):
    record = ads.build_ads_result_record('Synthetic Collector Edition', 'NBA', country,
        'Instant Experience', variation_token='reserve-only', product_metadata={'edition_limit':100})
    prompt = delivery_prompt(record, 'Synthetic original', '/fixture', 'fixture-job')
    assert prompt.count(VERSION) == 1
    assert prompt.count('\nHEADLINE: ') == 3
    assert prompt.count('\nFOOTER SECOND LINE (') == 3
    assert 'RESERVE A — OPTIONAL FOURTH CALL: COLLECTOR MAN CAVE' in prompt
    assert 'RESERVE B — OPTIONAL FIFTH CALL: DARK COLLECTOR STUDIO APARTMENT' in prompt
    assert 'small, softly out-of-focus hanging sports keepsakes' in normalise(prompt)
    assert 'If all three images exist, skip this entire reserve section' in normalise(prompt)
    assert "Use Reserve B only if a second distinct original slot" in normalise(prompt)
    assert 'at most two reserve attempts in the pack' in normalise(prompt)
    assert 'Do not use Reserve B as another retry for Reserve A' in normalise(prompt)
    assert 'Label/save the result as the ORIGINAL missing Ad 1/2/3 slot' in normalise(prompt)
    assert 'SC_AD_READY: fixture-job' in prompt and 'SC_AD_BLOCKED:' in prompt
    visuals = ads.resolve_standard_instant_experience_visuals(product_name=record['product_name'],
        category='NBA', country=country, product_metadata=record['product_metadata'], variation_token='reserve-only')
    for index, visual in enumerate(visuals, 1):
        initial = ads.build_instant_experience_execution_image_brief(index, visual)
        assert VERSION not in initial
        assert 'RESERVE A' not in initial and 'RESERVE B' not in initial
        assert visual['footer_second_line'] in initial and visual['meta_headline_text'] in initial


def test_existing_review_and_footer_are_unchanged_except_reserve_tail():
    source = subprocess.check_output(['git','show','dcbbc26e1ba1d3996929f88676aba163e0367385:ads_generation_review.py'])
    original = {}
    exec(compile(source, '<previous-review>', 'exec'), original)
    assert review.RULES.split('RESERVE ROOMS')[0].rstrip() == original['RULES'].split('RESERVE ROOMS')[0].rstrip()
    assert FOOTER_RULES in ads.build_ads_result_record('Synthetic Edition','NBA','USA','Instant Experience')['master_prompt']
    assert 'private collector study or a sunlit reading lounge' not in review.RULES


def test_safety_and_asset_recovery_do_not_trigger_substitutions():
    text = normalise(RULES)
    assert 'provider explicitly identifies a retryable technical failure' in text
    assert 'A safety rejection, moderation_blocked result or unexplained rejection never authorizes' in text
    assert 'recovery of the existing bytes, not another image generation' in text
    assert 'Do not reset this budget on review, reopen or resume' in text
    assert 'never claim three images' in text
    for file in ('PROJECT_ROLE_AND_TASK_PRIORITY.txt','PROJECT_INSTRUCTIONS.txt'):
        project = normalise((Path('docs/meta_ads_project')/file).read_text(encoding='utf8'))
        assert 'retryable technical failure' in project
        assert 'Reserve A' in project and 'Reserve B' in project
        assert 'moderation_blocked' in project
