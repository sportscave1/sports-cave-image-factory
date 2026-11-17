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
    assert 'An unavailable storefront message is an observation' in text
    assert 'never force it true to bypass a deliberate restriction' in text
    assert 'Leave edition numbers, allocations, runs, counters and history untouched' in text
    assert 'do not claim it is ready to purchase' in text


@pytest.mark.parametrize('selected', ['DRAFT', 'LIVE', 'UPDATE'])
def test_upload_cannot_turn_pending_setup_into_disabled_edition(selected):
    text = exported(selected)
    assert 'never set edition_enabled=false as a temporary publication, missing-PSD or setup-pending safeguard' in text
    assert 'Leave missing edition fields absent' in text
    assert 'preserve existing fields unchanged' in text
    assert 'PSD attachment is independent of automatic edition registration' in text
    assert text.index('Edition Ops owns') < text.index('2. DROPBOX FOLDER')


@pytest.mark.parametrize('selected', ['DRAFT', 'LIVE', 'UPDATE'])
def test_old_saved_safeguard_and_metafields_cannot_reintroduce_block(selected):
    from tests.test_product_upload_compact import fixture, prompt
    row = fixture(selected)
    row['data']['metafields'] = [
        dict(namespace='sports_cave', key='edition_enabled', value='false'),
        dict(namespace='sports_cave', key='edition_remaining', value='0'),
        dict(namespace='sports_cave', key='material', value='Unrelated verified field'),
        dict(namespace='custom', key='material', value='Verified material'),
    ]
    text = prompt(row, load=lambda key, default, **kw: default + '\n'
                  'Set sports_cave.edition_enabled=false until PSD setup completes.\n'
                  'Block purchasing until the edition is ready.\n'
                  'Use the approved greeting: Sporting memories.')
    assert 'Set sports_cave.edition_enabled=false until PSD setup completes.' not in text
    assert 'Block purchasing until the edition is ready.' not in text
    assert '"key": "edition_enabled"' not in text
    assert '"key": "edition_remaining"' not in text
    assert 'Unrelated verified field' in text
    assert 'Verified material' in text
    assert 'Sporting memories.' in text
    assert 'Edition Ops owns' in text


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


def test_automatic_handoff_keeps_creative_rules_and_uses_one_live_workflow(monkeypatch):
    from product_upload_chat_handoff import CORE, prepare

    row = saved_row()
    row['data']['name'] = 'Jahmyr Gibbs - The Takeover'
    row['data']['smart_upload'] = True
    row['data']['design_review'] = {'decision': 'preparing'}
    row['data']['metadata'] = {'upload_intent': 'new_product', 'review_status': 'needs_attention',
                               'review_notes': 'Unverified print bleed'}
    output = row['data']['upload_operation']['output']
    result = dict(product_name=row['data']['name'], sport_category='NFL Wall Art',
                  product_image_manifest=output['manifest'])
    saved = {item['output_filename'] for item in output['manifest'] if item['slot_id'] in CORE}
    receipt = dict(destination=output['folder'], export_fingerprint='original-core',
                   generation_receipt='fixture', successes=[
                       item for item in output['files'] if item['metadata']['name'] in saved
                   ])
    additions = (
        'Do not publish. Return the draft link.',
        'Create the Shopify product as a draft.',
        '- Invent specifications or materials.',
        'Use only verified details in the variant descriptions.',
    )
    monkeypatch.setattr('prompt_store.get_prompt',
                        lambda _id, default, **kwargs: '\n'.join((default, *additions)))
    creative = 'Use the original scenes.\n  Keep their exact framing, lighting and room requirements.'
    handoff = prepare(result, row, receipt, creative)
    prompt = handoff['prompt']

    assert handoff['automatic']
    assert 'Unverified print bleed' not in prompt
    assert creative in prompt
    assert 'as a file attachment alongside this prompt' in prompt
    assert 'A matching attachment satisfies the reference requirement' in prompt
    assert 'without downloading it again' in prompt
    assert 'report the exact pending action and required approval' in prompt
    assert 'pause the affected step and any later steps' not in prompt
    assert 'retry the affected operation up to twice' in prompt
    assert 'check whether the previous call completed' in prompt
    assert 'Continue other independent cards' in prompt
    assert 'An explicit image safety rejection is different from a temporary tool error' in prompt
    assert 'Do not automatically retry or reword the rejected request' in prompt
    assert 'eight-image verification and publication checks' in prompt
    assert 'The user explicitly authorises' not in prompt
    assert all(item not in prompt for item in additions[:3])
    assert '- Do not invent specifications or materials.' in prompt
    assert additions[3] in prompt
    assert 'Create the product as ACTIVE from the first create call' in prompt
    assert prompt.index('STEP 3') < prompt.index('STEP 4') < prompt.index('STEP 5')
    assert prompt.index('Wait for the published product') < prompt.index('Move that original master') < prompt.index('Open Add / Attach PSD')


    recreated = dict(receipt, recreated_folder=True, successes=[
        {**item, 'metadata': {**item['metadata'], 'id': item['metadata']['id'] + '-recreated',
                              'server_modified': '2026-11-16T12:47:04'}}
        for item in receipt['successes']
    ])
    rebuilt_handoff = prepare(result, row, recreated, creative)
    assert rebuilt_handoff['reference_saved_at'] == '2026-11-16T12:47:04+00:00'
    recreated_id = rebuilt_handoff['companion_id']
    assert recreated_id != handoff['companion_id']
    assert recreated_id == prepare(result, row, {**recreated, 'recreated_folder': False}, creative)['reference_companion_id']
    assert recreated_id == prepare(result, row, recreated, creative)['companion_id']
    row['data']['staff_upload_attempt'] = 'manual-restart-fixture'
    retry = prepare(result, row, receipt, creative)
    assert retry['companion_id'] != handoff['companion_id']
    assert retry['companion_id'] == prepare(result, row, receipt, creative)['companion_id']
    assert str(row['id']) in retry['prompt']  # stable upload correlation
