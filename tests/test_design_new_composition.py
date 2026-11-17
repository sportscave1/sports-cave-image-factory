"""New-design creative guidance stays separate from existing edit and delivery rules."""
from home_morning_brief_actions import _prompt
from design_new_composition import (
    COMPLEMENTARY_IMAGES, COMPLETE_COMPOSITION, COLLECTOR_TYPOGRAPHY,
    PURPOSEFUL_ABSTRACT, REVIEW_RELATIONSHIPS, BADGE_PLACEMENT_VERIFICATION,
)
from design_collector_assets import COLLECTOR_ASSET_PLACEMENT
from design_motorsport import MOTORSPORT_ARTWORK


def test_new_design_composes_sources_type_and_badge_without_extra_checkpoints():
    prompt = _prompt('Collector', 'Verified story')
    for guidance in (COMPLEMENTARY_IMAGES, COMPLETE_COMPOSITION, COLLECTOR_TYPOGRAPHY,
                     PURPOSEFUL_ABSTRACT, REVIEW_RELATIONSHIPS, BADGE_PLACEMENT_VERIFICATION):
        assert prompt.count(guidance) == 1
    assert prompt.index(COMPLEMENTARY_IMAGES) < prompt.index('Step 1.')
    assert prompt.count(MOTORSPORT_ARTWORK) == 1
    assert prompt.index(MOTORSPORT_ARTWORK) < prompt.index('Step 1.')
    assert prompt.index(COMPLETE_COMPOSITION) < prompt.index('Step 5.')
    assert prompt.index(REVIEW_RELATIONSHIPS) < prompt.index('**8B.')
    assert prompt.index('**8D.') < prompt.index(BADGE_PLACEMENT_VERIFICATION) < prompt.index('**8E.')
    assert 'same original-source, image-quality and photographic-authenticity checks' in prompt
    assert 'For an event-specific design, supporting photographs must belong to that verified event.' in prompt
    assert 'Keep a single image when it tells the story more powerfully' in prompt
    assert 'not additional image-generation calls' in prompt
    assert 'original canvas coordinates and proportional scale are starting values' in prompt
    assert COLLECTOR_ASSET_PLACEMENT in prompt
    assert 'two separate full-artwork image-generation calls and two confirmed Dropbox saves' in prompt
    assert 'at most two additional image-generation attempts total across both passes' in prompt
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
