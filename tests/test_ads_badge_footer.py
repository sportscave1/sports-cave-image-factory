"""Profile isolation at real generation and automatic-delivery boundaries."""
import hashlib
from io import BytesIO
from pathlib import Path

from PIL import Image
import pytest
import ads_page as ads
import ads_ie_badge as badge
from ads_footer import apply_footer_contract
from design_publish_ad import delivery_prompt


@pytest.mark.parametrize('country', ['USA', 'Australia', 'UK', 'Canada', 'New Zealand'])
def test_badge_profile_isolated_from_normal_footers_and_delivery(country):
    record = ads.build_ads_result_record('Synthetic Collector Edition', 'NBA', country,
        'Instant Experience', product_metadata={'edition_limit': 100}, variation_token='badge-footer')
    prompt = record['master_prompt']
    assert badge.VERSION in prompt
    assert badge.SELECTION_RULES in prompt
    assert prompt.count('\nHEADLINE: ') == 3
    assert prompt.count('\nSUPPORTING LINE: ') == 2
    assert prompt.count('\nCTA: CLAIM YOUR EDITION') == 2
    assert 'Candidate pairs: ' in prompt
    assert len(record['product_metadata']['instant_experience_footer_selections']) == 3
    assert ads._instant_experience_visual_contract_is_current(prompt)
    assert apply_footer_contract(prompt) == prompt
    visuals = ads.resolve_standard_instant_experience_visuals(product_name='Synthetic Collector Edition',
        category='NBA', country=country, product_metadata=record['product_metadata'], variation_token='badge-footer')
    for index, visual in enumerate(visuals, 1):
        call = ads.build_instant_experience_execution_image_brief(index, visual)
        standalone = ads.build_standard_instant_experience_image_prompt(index, visual,
            product_name='Synthetic Collector Edition', category='NBA', country=country)
        for text in (call, standalone):
            if index == 2:
                assert 'HEADLINE: Claim Your Edition' in text
                assert badge.BADGE_URL in text and badge.BADGE_SHA256 in text
                assert '112 px' in text and 'y=912' in text
                for conflict in ('160 px', '15.625%', '84.375%', 'SUPPORTING LINE:',
                                 'CTA: CLAIM YOUR EDITION', 'Render exactly three lines'):
                    assert conflict not in text, conflict
            else:
                assert visual['headline_text'] in text and visual['supporting_line'] in text
                assert '160 px' in text and '0.03 em' in text
                assert badge.BADGE_URL not in text
    delivered = delivery_prompt(record, 'Synthetic original', '/fixture', 'fixture-job')
    assert badge.REVIEW_CHECK in delivered
    assert 'all three lines must be visible' not in delivered
    for filename in ('collector-hallway.jpg', 'architectural-wall.jpg', 'man-cave.jpg', 'ad_copy.csv'):
        assert '/fixture/' + filename in delivered
    assert 'SC_AD_READY: fixture-job' in delivered
    assert 'SC_AD_BLOCKED:' in delivered


def test_shipped_badge_is_original_transparent_png():
    raw = Path('static/ads/blackened-gunmetal-sports-cave-medal.png').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == badge.BADGE_SHA256
    image = Image.open(BytesIO(raw))
    assert image.mode == 'RGBA' and image.size == (1254, 1254)
    assert image.getchannel('A').getextrema() == (0, 255)


def test_non_beta_delivery_keeps_its_original_inspection():
    delivered = delivery_prompt({'master_prompt': 'Previously approved Baseline 2.0'},
        'Synthetic original', '/fixture', 'fixture-job')
    assert 'all three lines must be visible' in delivered
    assert badge.REVIEW_CHECK not in delivered
