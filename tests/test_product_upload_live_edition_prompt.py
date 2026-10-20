"""Selected-mode publication and independent edition setup, without old gates."""
import pytest
from product_upload_prompts import build
from product_upload_source import current_source
from tests.test_product_upload_package import saved_row


def exported(selected):
    return build(selected, source=current_source(saved_row()), load=lambda key, default, **kw: default)


def test_live_without_edition_metadata_has_publication_then_pending_handoff():
    text = exported('LIVE')
    assert 'Pending edition setup alone does not block Live publication' in text
    assert 'set ACTIVE and publish the product AND every selected collection' in text
    assert 'PRODUCT PUBLISHED LIVE — EDITION SETUP PENDING' in text
    assert text.index('7. SELECTED-MODE PUBLICATION') < text.index('8. COMPLETION CHECK')
    assert '15428753948979' not in text


def test_archived_message_is_expected_but_purchase_protection_remains():
    text = exported('LIVE')
    assert 'preserve its archived/unavailable message and disabled purchasing' in text
    assert 'Leave edition numbers, allocations, runs, counters and history untouched' in text
    assert 'do not claim it is ready to purchase' in text


def test_partial_failure_preserves_completed_work_and_same_product_retry():
    text = exported('LIVE')
    assert 'Reuse the saved Shopify product ID or the product with this operation tag' in text
    assert 'never create duplicates' in text
    assert 'Retain completed work on partial failure' in text
    assert 'do not trigger rollback to Draft or unpublishing' in text
    assert 'DRAFT FALLBACK UNVERIFIED' not in text


@pytest.mark.parametrize('selected', ['DRAFT', 'UPDATE'])
def test_other_modes_do_not_gain_live_permission(selected):
    text = exported(selected)
    assert 'PRODUCT PUBLISHED LIVE — EDITION SETUP PENDING' not in text
    assert 'set ACTIVE and publish' not in text
    if selected == 'DRAFT':
        assert 'Create as DRAFT, published false' in text
    else:
        assert 'Never create a product in Update Existing mode' in text
        assert 'Active stays Active, Draft stays Draft' in text


def test_live_has_no_staging_appendix_vetoes():
    text = exported('LIVE')
    for rule in ('Only after all prior', 'Only if EVERY', 'COMMON PRODUCT BUILD',
                 'Never set product status to Active', 'Before upload show a compact table'):
        assert rule not in text
