"""Offline prompt and delivery regression checks; no live generation or posting."""
from unittest.mock import patch

import ads_page as ads
import ads_generation_review as review
import design_publish_ad as companion
from tests.test_ads_refresh_plan import fixture


def test_review_is_only_intended_prompt_delta_and_refresh_is_unchanged():
    for campaign in ('Instant Experience', 'Carousel', 'Single Image / Video'):
        def build():
            return ads.build_ads_prompt('Collector Cricket Edition', 'Cricket', 'Australia',
                                        campaign, variation_token='review-test')
        with patch.object(ads, 'apply_generation_review', lambda p: p):
            original = build()
            refresh = fixture(campaign)['master_prompt']
        updated = build()
        assert updated == review.apply_generation_review(original)
        assert updated.count(review.RULES) == 1
        assert review.apply_generation_review(updated) == updated
        assert fixture(campaign)['master_prompt'] == refresh
        assert review.VERSION not in refresh
    assert 'No variants, alternatives, correction or replacement generations' not in build_ie()
    assert 'Inspection must not trigger another image' not in build_ie()


def build_ie():
    return ads.build_ads_result_record('Collector Cricket Edition', 'Cricket', 'Australia',
        'Instant Experience', variation_token='review-test')['master_prompt']


def test_review_before_export_and_existing_companion_delivery_is_preserved():
    prompt = build_ie()
    assert prompt.index('4. Immediately generate Image 3') < prompt.index('4b. Complete the final creative review') < prompt.index('5. Create and attach')
    result = {'master_prompt': prompt}
    delivered = companion.delivery_prompt(result, 'Synthetic reference', '/fixture', 'fixture-job')
    assert prompt in delivered
    for name in ('ad_copy.csv', *companion.COVERS.values()):
        assert '/fixture/' + name in delivered
    assert 'SC_AD_READY: fixture-job' in delivered
    assert 'SC_AD_BLOCKED:' in delivered
    assert 'Keep the current CSV format. Do not add image URLs to the CSV.' in delivered


def test_new_ads_final_actions_no_longer_render_separate_review():
    with patch.object(ads, '_render_final_ad_review') as old_review, patch('ads_auto_post.render') as handoff:
        result = {'workflow_mode': ads.ADS_WORKFLOW_MODE_NEW, 'campaign_type': 'Instant Experience'}
        ads._render_ads_final_actions(result, {}, source_matches=True)
        old_review.assert_not_called()
        handoff.assert_called_once_with(ads, result, {}, source_matches=True)
