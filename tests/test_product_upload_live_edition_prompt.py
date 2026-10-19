"""Exported prompt contracts; no live Shopify/Edition Ops operations."""
import pytest

from product_upload_prompts import build
from product_upload_source import current_source, execution_opening
from product_upload_identity import correlation_prompt
from tests.test_product_upload_package import saved_row
import product_upload_modes as modes


def exported(selected):
    row = saved_row()  # No edition metadata, number, mapping or mirror.
    source = current_source(row)
    text = build(selected, source=source, load=lambda key, default, **kw: default)
    opening = execution_opening(source)
    return opening + correlation_prompt(row) + text[len(opening):]


def test_live_without_edition_metadata_has_publication_then_pending_handoff():
    text = exported('LIVE')
    assert 'missing edition metadata, an unassigned edition/number, pending PSD mapping' in text
    assert 'alone must not block staging QA or Live publication' in text
    assert 'change this product from DRAFT to ACTIVE' in text
    assert 'Publish this PRODUCT to every discovered enabled required channel' in text
    assert 'PRODUCT PUBLISHED LIVE — EDITION SETUP PENDING' in text
    assert 'The product is published. Purchasing remains disabled until edition setup is completed. Return to Product Uploads → MAP, then complete edition assignment.' in text
    assert text.index('4. ACTIVATE AND PUBLISH') < text.index('EDITION OPS READINESS — REPORT SEPARATELY')
    assert '15428753948979' not in text


def test_archived_message_is_expected_but_purchase_protection_remains():
    text = exported('LIVE')
    assert 'Edition archived — Collector run closed' in text
    assert 'These effects alone must not block\npublication, require unpublishing or trigger a return to Draft' in text
    for rule in ('Do not enable Add to Cart', 'Do not set an archive flag',
                 'Do not invent an edition number, create/reset a run, modify counters, allocate',
                 'editions or mark anything sold', 'Never change edition ledger data or bypass storefront purchasing checks',
                 'as ready to purchase or fully operational until edition readiness is verified'):
        assert rule in text


def test_real_failures_and_same_product_retries_remain():
    text = exported('LIVE')
    for rule in ('classification, media, variants, prices', 'any selected collection publication',
                 'ONLY this newly created product to DRAFT', 'DRAFT FALLBACK UNVERIFIED',
                 'Retries must resume the same product; never restart by creating a replacement',
                 'search Shopify for this exact tag (including drafts)',
                 'resume that product by its stable ID; do not create another'):
        assert rule in text


@pytest.mark.parametrize('selected', ['DRAFT', 'UPDATE'])
def test_other_modes_do_not_gain_pending_edition_live_permission(selected):
    text = exported(selected)
    assert 'PRODUCT PUBLISHED LIVE — EDITION SETUP PENDING' not in text
    assert 'These effects alone must not block' not in text
    if selected == 'DRAFT':
        assert modes.DRAFT_FINAL in text
        assert 'Final Status: DRAFT. Published: false' in text
    else:
        assert 'Never create a product in Update Existing mode' in text
        assert 'Active stays Active.' in text and 'Draft stays Draft.' in text


def test_live_staging_appendices_have_no_unscoped_draft_vetoes():
    text = exported('LIVE')
    lines = text.splitlines()
    for old in modes.LIVE_STAGING_WORDING:
        assert old not in lines
    assert 'After activation, the existing products/update webhook must register' not in text
    assert 'Only if EVERY required check passes report PRODUCT PUBLISHED LIVE' not in text
