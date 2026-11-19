"""The full delivery envelope and audited project sources agree on Baseline."""
from pathlib import Path
import pytest
import ads_page as ads
from ads_footer import COMPACT_FOOTER_RULES
from design_publish_ad import delivery_prompt


@pytest.mark.parametrize('country',['Australia','USA','UK','Canada','New Zealand'])
def test_delivery_and_each_call_keep_assigned_support_and_metallic_seam(country):
    record=ads.build_ads_result_record('Synthetic Cricket Edition','Cricket',country,'Instant Experience',
        product_metadata={'edition_limit':100},variation_token='project-alignment')
    prompt=delivery_prompt(record,'Synthetic original reference','/fixture','fixture-job')
    assert prompt.count('\nSUPPORTING LINE: ')==3
    for row in record['product_metadata']['instant_experience_footer_selections']:
        assert '\nSUPPORTING LINE: '+row['supporting_line'] in prompt
    for forbidden in ('Render no supporting sentence','No supporting sentence on the image',
                      'exactly two footer lines','supporting_line=\'\'',
                      'no decorative flourishes, borders, glow,'):
        assert forbidden not in prompt
    assert 'specular sheen varying softly' in prompt
    assert 'never a uniform flat gold rule' in prompt
    assert 'correct missing footer elements' in prompt.lower()
    assert 'SC_AD_READY: fixture-job' in prompt
    assert 'Do not publish Meta ads' in prompt


def test_audited_project_text_sources_match_current_contract():
    root=Path('docs/meta_ads_project')
    for name in ('PROJECT_ROLE_AND_TASK_PRIORITY.txt','BASELINE_FOOTER_TYPOGRAPHY.txt'):
        source=(root/name).read_text(encoding='utf8')
        assert 'supporting/FOMO sentence' in source
        assert 'shimmer' in source
        assert 'Render no supporting sentence' not in source
        assert 'Check that both lines' not in source
        assert 'CLAIM YOUR EDITION' in source
        assert 'existing' in source and 'approval' in source
    universal=Path('prompts/sports_cave_universal_creative_system.txt').read_text(encoding='utf8')
    assert 'SUPPORTING LINE' in universal
    assert 'No variants, alternatives, correction or replacement generations' not in universal
    assert 'Complete the supplied final creative review' in universal
    assert 'Project image sources are visual references only' in COMPACT_FOOTER_RULES
