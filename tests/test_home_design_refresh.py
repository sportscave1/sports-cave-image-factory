"""Home refresh research, redesign and recommendation handoff contracts."""

from datetime import date
from html import unescape
import re
from unittest.mock import Mock

import crm_growth_reporting
from design_collector_assets import COLLECTOR_ASSET_PLACEMENT
from design_motorsport import MOTORSPORT_ARTWORK
from design_refresh_replacement import REVIEW_REPLACEMENT_RULE
from home_design_refresh import RECOMMENDATION_GUIDANCE, _render_candidate


def test_home_handoff_commissions_two_new_artwork_passes():
    row = dict(product_id='123', handle='collector', title='Collector', sessions=40,
               suggestion='A crowded title may weaken thumbnail recognition.')
    markup = _render_candidate(row)
    prompt = unescape(re.search(r'data-refresh-prompt="([^"]+)"', markup)[1])
    assert row['suggestion'] in prompt and 'Research hypothesis' in prompt
    assert 'Redesign research lead' in markup
    copy = ' '.join(prompt.split())
    checkpoints = (
        'Run a fresh web image search', 'state the strongest hero',
        'Pass 1 must be a complete new flat design', 'make Pass 2 a refinement',
        'Compare and score the original, Pass 1 and Pass 2', 'unique staging path',
        'SMART UPLOAD HANDOFF METADATA', '**REVIEW REPLACEMENT RULE**',
    )
    offsets = [copy.index(checkpoint) for checkpoint in checkpoints]
    assert offsets == sorted(offsets)
    assert prompt.count(MOTORSPORT_ARTWORK) == 1
    assert prompt.index(MOTORSPORT_ARTWORK) < prompt.index('Run a fresh web image search')
    assert 'Reuse a photo from the existing PSD only when' in prompt
    assert 'Do not revert to the old layout' in prompt
    assert 'original editable edition-number layer' in prompt
    assert COLLECTOR_ASSET_PLACEMENT in prompt
    assert REVIEW_REPLACEMENT_RULE in prompt
    assert 'Missing or stale JSON alone must not block replacement.' in prompt
    assert 'Pending cleanup alone does not change an otherwise verified artwork' in prompt
    assert 'update the exact JSON\n   revision to ready_for_review before resuming' in prompt


def test_recommendation_source_supplies_editorial_guidance_with_or_without_traffic(monkeypatch):
    import home_design_refresh

    client = Mock()
    monkeypatch.setattr(crm_growth_reporting, 'GoogleReports', lambda: client)
    read = Mock(return_value={'quality': 'unavailable'})
    monkeypatch.setattr(crm_growth_reporting, '_ga4', read)
    monkeypatch.setattr(home_design_refresh, 'recent_ids', lambda _: ['456'])
    day = date(2026, 11, 16)

    assert crm_growth_reporting.refresh_traffic(day) == {
        'status': 'unavailable', 'recommendation_guidance': RECOMMENDATION_GUIDANCE,
    }
    read.return_value = dict(quality='GA4 verified', start='2026-10-18', end='2026-11-16',
                             timezone='Australia/Sydney', rows=[
                                 {'dimensions': {'landingPage': '/products/collector'},
                                  'metrics': {'sessions': 42}},
                             ])
    result = crm_growth_reporting.refresh_traffic(day)
    assert result['recommendation_guidance'] == RECOMMENDATION_GUIDANCE
    assert 'complete redesign' in RECOMMENDATION_GUIDANCE and 'Weak sales warrant investigation' in RECOMMENDATION_GUIDANCE
    assert result['products'] == [{'handle': 'collector', 'sessions': 42}]
    assert result['excluded_product_ids'] == ['456']
