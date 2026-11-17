"""New-design creative guidance stays separate from existing edit and delivery rules."""
from home_morning_brief_actions import _prompt
from design_new_composition import (
    COMPLEMENTARY_IMAGES, COMPLETE_COMPOSITION, COLLECTOR_TYPOGRAPHY,
    PURPOSEFUL_ABSTRACT, REVIEW_RELATIONSHIPS, BADGE_PLACEMENT_VERIFICATION,
)
from design_collector_assets import COLLECTOR_LAYER_RULES
from design_motorsport import MOTORSPORT_ARTWORK


def test_new_design_composes_sources_type_and_badge_without_extra_checkpoints():
    prompt = _prompt('Collector', 'Verified story')
    for guidance in (COMPLEMENTARY_IMAGES, COMPLETE_COMPOSITION, COLLECTOR_TYPOGRAPHY,
                     PURPOSEFUL_ABSTRACT, REVIEW_RELATIONSHIPS, BADGE_PLACEMENT_VERIFICATION):
        assert prompt.count(guidance) == 1
    assert prompt.index(COMPLEMENTARY_IMAGES) < prompt.index('**2.')
    assert prompt.count(MOTORSPORT_ARTWORK) == 1
    assert prompt.index(MOTORSPORT_ARTWORK) < prompt.index('**2.')
    assert prompt.index(COMPLETE_COMPOSITION) < prompt.index('**3.')
    assert prompt.index('**4.') < prompt.index(REVIEW_RELATIONSHIPS) < prompt.index('**5.')
    assert prompt.index('**5.') < prompt.index(BADGE_PLACEMENT_VERIFICATION) < prompt.index('**6.')
    assert 'same original-source, image-quality and photographic-authenticity checks' in prompt
    assert 'For an event-specific design, supporting photographs must belong to that verified event.' in prompt
    assert 'Keep a single image when it tells the story more powerfully' in prompt
    assert 'not additional image-generation calls' in prompt
    assert 'Use the master position only if it serves this design' in prompt
    assert prompt.count(COLLECTOR_LAYER_RULES) == 1
    assert 'record the issue as needs_attention even if both layer checks pass' in prompt
    assert 'one full generation, verified final Review PSD, matching JSON and final display' in prompt
    assert 'Retry image generation once only if a technical failure produced no usable output' in prompt
    assert 'Use abstract treatment selectively:' not in prompt
    assert 'Refine their scale, alignment, line spacing and separation' not in prompt


def test_new_creative_rules_do_not_leak_into_edits():
    prompt = _prompt('Collector', 'Verified story', edit={
        'source': {'id': 'id:Original', 'rev': 'abcdef123', 'path_display': '/Review/Collector.psd'},
        'metadata': {'shopify_product_id': 'gid://shopify/Product/123'},
    })
    for guidance in (COMPLEMENTARY_IMAGES, COMPLETE_COMPOSITION, COLLECTOR_TYPOGRAPHY,
                     PURPOSEFUL_ABSTRACT, REVIEW_RELATIONSHIPS, BADGE_PLACEMENT_VERIFICATION,
                     MOTORSPORT_ARTWORK):
        assert guidance not in prompt
