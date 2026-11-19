"""Refresh publication preserves legacy titles without weakening new-title gates."""
from copy import deepcopy

import pytest

from product_title_rules import apply_rules, publication_metadata
from product_upload_compact import context_from_row
from product_upload_prompts import build
from tests.test_design_review_smart_upload import handoff, parse_handoff, SOURCE, TARGET


@pytest.mark.parametrize('title', [
    'Anthony Edwards Timberwolves Wall Art',
    'An existing approved edition title that is deliberately longer than sixty characters Wall Art',
])
def test_refresh_handoff_reaches_upload_with_original_title_and_exact_target(title):
    details = parse_handoff(handoff(design_title=title, design_origin='designs_to_refresh',
        upload_intent='existing_product_refresh', existing_shopify_product_id=TARGET), SOURCE)
    original = deepcopy(details)
    prompt = build('SMART', 'Approved.psd', metadata=details, automatic=True,
                   load=lambda _, default, **kwargs: default)
    assert TARGET in prompt and title in prompt
    assert 'Preserve existing title' in prompt
    assert 'Media-only update: preserve title, handle, description' in prompt
    assert '"customer_facing_title"' not in prompt
    assert 'never create a new product for this item' in prompt
    assert details == original  # Never mutate saved Review metadata while exporting.
    assert 'Explicitly proposed customer-facing title' not in apply_rules('Upload', details)


def test_saved_failed_refresh_intake_keeps_origin_and_does_not_lose_explicit_edit():
    title = 'Anthony Edwards Timberwolves Wall Art'
    metadata = dict(design_origin='designs_to_refresh', upload_intent='existing_product_refresh',
                    design_name=title, customer_facing_title=title, shopify_product_id=TARGET)
    row = dict(id='00000000-0000-0000-0000-000000000001', data=dict(smart_upload=True, metadata=metadata))
    context = context_from_row(row)
    assert 'customer_facing_title' not in publication_metadata(context)
    assert publication_metadata(context)['existing_product_title'] == title
    # Explicit edits entered after the inherited metadata keep validation.
    row['data']['customer_facing_title'] = 'Unverified replacement title'
    with pytest.raises(ValueError, match='verified original artwork'):
        build('SMART', 'Approved.psd', metadata=context_from_row(row), automatic=True,
              load=lambda _, default, **kwargs: default)


def test_new_product_and_explicit_title_changes_still_require_verified_format_and_length():
    for metadata in (
        dict(customer_facing_title='Anthony Edwards Timberwolves Wall Art'),
        dict(design_origin='designs_to_refresh', upload_intent='new_product',
             design_name='Unformatted title', customer_facing_title='Unformatted title'),
    ):
        with pytest.raises(ValueError, match='verified original artwork'):
            apply_rules('Upload', metadata)
    with pytest.raises(ValueError, match='exceeds 60'):
        apply_rules('Upload', dict(customer_facing_title='X' * 61))
