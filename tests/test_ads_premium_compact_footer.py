"""Fresh prompt/export acceptance for one compact three-line geometry."""
from pathlib import Path
import re
import pytest
import ads_page as ads
from ads_footer import COMPACT_FOOTER_RULES
from design_publish_ad import delivery_prompt


def check_profile(prompt):
    for old in ('18–20%', '18-20%', '80–82%', '80-82%', '20–23%',
                '42–48', '24–26', '26–28', '64 px bottom text clearance',
                'within 64 pixels of a canvas edge', '64–72 px safe margins',
                'unchanged headline/CTA typography'):
        assert old not in prompt, old
    for required in ('exactly 160 px high', 'top seam is y=864', '0.03 em letter spacing',
                     'Title type: 50 px', 'Supporting type: 22 px', 'CTA type: 23 px',
                     '0.10 em letter spacing', '16 px bottom padding',
                     'never restyle text printed inside the original framed edition'):
        assert required in prompt, required


@pytest.mark.parametrize('country',['Australia','USA','UK','Canada','New Zealand'])
def test_all_routes_and_delivery_use_one_geometry_without_height_or_padding_conflicts(country):
    record=ads.build_ads_result_record('Synthetic Collector Edition','NBA',country,'Instant Experience',
        product_metadata={'edition_limit':100},variation_token='compact-footer')
    prompt=delivery_prompt(record,'Synthetic approved original','/fixture','fixture-job')
    check_profile(prompt)
    assert prompt.count('\nHEADLINE: ')==3
    assert prompt.count('\nSUPPORTING LINE: ')==3
    assert prompt.count('\nCTA: CLAIM YOUR EDITION')==3
    assert 'SC_AD_READY: fixture-job' in prompt
    assert 'SC_AD_BLOCKED:' in prompt
    rows=ads.resolve_standard_instant_experience_visuals(product_name='Synthetic Collector Edition',
        category='NBA',country=country,variation_token='compact-footer',product_metadata=record['product_metadata'])
    for index,row in enumerate(rows,1):
        standalone=ads.build_standard_instant_experience_image_prompt(index,row,
            product_name='Synthetic Collector Edition',category='NBA',country=country)
        check_profile(standalone)
        assert 'HEADLINE: '+row['headline_text'] in standalone
        assert 'SUPPORTING LINE: '+row['supporting_line'] in standalone
        assert 'CTA: CLAIM YOUR EDITION' in standalone


def test_vertical_budget_is_complete_and_other_ratios_scale_by_width():
    # Parse the actual contract, rather than asserting a duplicate geometry object.
    text=COMPACT_FOOTER_RULES
    pieces=re.findall(r'(\d+) px (?:top padding|headline line box|clear gap|supporting line box|CTA line box|bottom padding)',text)
    assert list(map(int,pieces))==[16,58,6,28,8,28,16]
    assert sum(map(int,pieces))==160
    google=Path('prompts/google_demand_gen_v1.txt').read_text(encoding='utf8')
    assert 'exactly 187.5 px at 1200 px canvas width' in google
    assert 'exactly 150 px at 960 px canvas width' in google
    for old in ('bottom 24–28%', 'bottom 28–32%', 'bottom 20–23%', 'footer recomposed for each ratio'):
        assert old not in google
    check_profile(google)


def test_project_sources_share_type_hierarchy_and_safe_areas():
    for name in ('BASELINE_FOOTER_TYPOGRAPHY.txt','PROJECT_ROLE_AND_TASK_PRIORITY.txt'):
        source=(Path('docs/meta_ads_project')/name).read_text(encoding='utf8')
        check_profile(source)
        assert 'count exactly three visible text baselines' in source
        assert 'No new approval' in source
