"""Home refresh research, redesign and recommendation handoff contracts."""

from datetime import date
from html import unescape
import re
from unittest.mock import Mock

import crm_growth_reporting
from home_design_refresh import RECOMMENDATION_GUIDANCE, _render_candidate, _refresh_prompt
from home_morning_brief_actions import _prompt


def test_refresh_handoff_uses_shared_single_generation_and_exact_existing_target():
    row = dict(product_id='123', handle='collector', title='Collector', sessions=40,
               suggestion='A crowded title may weaken thumbnail recognition.')
    markup = _render_candidate(row)
    prompt = unescape(re.search(r'data-refresh-prompt="([^"]+)"', markup)[1])
    assert row['suggestion'] in prompt and 'Research hypothesis' in prompt
    assert 'Redesign research lead' in markup
    assert 'Current title (suggestion, not an approved title lock): Collector' in prompt
    assert 'upload_intent (existing_product_refresh)' in prompt
    assert 'existing_shopify_product_id ("gid://shopify/Product/123")' in prompt
    assert 'design_origin (designs_to_refresh)' in prompt
    assert 'one creative image-generation call' in prompt
    assert 'Pass 2' not in prompt and 'STAGING' not in prompt
    assert 'upload_intent (new_product)' not in prompt
    assert '**REVIEW REPLACEMENT RULE**' not in prompt
    assert 'Leave the existing live PSD and Shopify listing untouched' in prompt
    assert 'Publish Now and Publish + ads' in prompt
    # All creative, generation and assembly stages are the same renderer, not copied text.
    new = _prompt('Collector', 'Any suggested story')
    assert prompt.split('**1.', 1)[1].split('**6.', 1)[0] == new.split('**1.', 1)[1].split('**6.', 1)[0]


def test_refresh_inherits_later_changes_from_the_shared_new_design_renderer(monkeypatch):
    import home_morning_brief_actions as actions
    monkeypatch.setattr(actions, 'CREATIVE_REVIEW', 'FUTURE SHARED CREATIVE RULE')
    prompt = _refresh_prompt(dict(title='Collector', product_id='123'), 'https://example.test/product')
    assert prompt.count('FUTURE SHARED CREATIVE RULE') == 1


def test_refresh_rejects_an_ambiguous_product_target():
    import pytest
    with pytest.raises(ValueError, match='exact existing Shopify product ID'):
        _refresh_prompt(dict(title='Collector', product_id='not-an-id'), 'https://example.test/product')


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
