"""Contract tests: preserved business values, selected mode and saved identity."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import re
import uuid

import pytest
from product_upload_compact import context_from_row, variant_rows, SIZES
from product_upload_prompt_core import PRODUCT_UPLOAD_AUD_PRICING
from product_upload_prompts import build
from product_upload_source import current_source
from tests.test_product_upload_package import saved_row


def fixture(mode='LIVE', sport='NBA', name='Courtside Legacy'):
    row = saved_row()
    row['mode'] = mode
    row['data'].update(name=name + '.psd', basic_validated=True)
    op = row['data']['upload_operation']
    folder = '/Team/04_OUTPUT/product-images/' + sport + '/' + name
    old = op['output']['folder']
    op['output'].update(design_name=name, sport_category=sport, folder=folder)
    row['data']['mockups_context'] = dict(design_name=name, sport_category=sport)
    record = row['data']['mockup_saves']['saved']
    record['target'] = folder
    record['receipt']['destination'] = folder
    record['receipt']['webp_folder'] = dict(path=folder+'/WEBP', id='id:folder-'+row['id'])
    for file in record['receipt']['successes']:
        file['metadata']['path_display'] = file['metadata']['path_display'].replace(old, folder)
        file['metadata']['id'] += '-' + row['id']
    row['data']['mockup_save_token'] = 'save-' + row['id']
    op['output']['save_token'] = row['data']['mockup_save_token']
    return row


def prompt(row, load=None):
    return build(row['mode'], row['data']['name'], source=current_source(row),
                 metadata=context_from_row(row), load=load or (lambda key, default, **kw: default))


@pytest.mark.parametrize('mode', ['DRAFT', 'LIVE', 'UPDATE'])
def test_compact_order_transfer_and_no_legacy_gates(mode):
    row = fixture(mode)
    text = prompt(row)
    assert re.findall(r'^([1-8])\. ', text, re.M) == list('12345678')
    assert text.count('"folder_path"') == 1
    assert text.count('Obtain fresh download links') == 1
    assert 'single-use' in text and 'HEAD request' in text and 'local-file/imageFile' in text
    assert not any(word in text for word in (
        'before any Shopify write', 'stop before', 'MANDATORY FINAL', 'FINAL QA CHECKLIST',
        'product_sport_tags.classify_product', '"content_hash"', '"revision"', '"version"'))
    assert len(text) < 14000
    for value in ('MAP', 'allocations', 'counters', 'history', 'original filenames'):
        assert value in text
    if mode == 'DRAFT':
        assert 'Create as DRAFT, published false' in text
        assert 'Set available quantity exactly 20' not in text
        assert 'Facebook & Instagram' not in text
    elif mode == 'LIVE':
        for channel in ('Online Store', 'Facebook & Instagram', 'Google & YouTube', 'Shop', 'Pinterest', 'Linktree'):
            assert channel in text
        assert 'Set available quantity exactly 20' in text
        assert 'SET 20 on retry, never increment' in text
        assert 'PRODUCT PUBLISHED LIVE — EDITION SETUP PENDING' in text
    else:
        assert 'Never create a product in Update Existing mode' in text
        assert 'Media-only update: preserve title' in text
        assert '45–70 words' not in text
        assert 'Set available quantity exactly 20' not in text


def test_all_sixteen_prices_skus_dimensions_and_business_values():
    rows = variant_rows({})
    assert len(rows) == 16
    for frame, suffix in zip(('Black', 'Oak', 'White', 'Unframed'), ('B', 'O', 'W', '')):
        frame_rows = [r for r in rows if r['Frame'] == frame]
        assert [r['Size'] for r in frame_rows] == ['XL', 'L', 'M', 'S']
        for i, r in enumerate(frame_rows):
            baseline = PRODUCT_UPLOAD_AUD_PRICING['unframed' if frame == 'Unframed' else 'framed'][i]
            assert (r['price'], r['compare_at_price'], r['saving'], r['discount']) == baseline[1:]
            assert r['sku'] == f'[PREFIX]A{i+1}{suffix}'
    text = prompt(fixture())
    assert all(size in text for size in SIZES)
    for required in ('maximum 60', '35–55', '45–70', '3–7', '50–60', '145–160', '80–140',
                     'Real fans remember this. Own the moment.', 'Sports Cave', 'Framed Art',
                     'Prints in Posters, Prints, & Visual Artwork', 'gift card false',
                     'condition New', 'custom product true', 'Adult/Unisex',
                     'tracked true', 'CONTINUE', 'requires shipping true', 'taxable true'):
        assert required in text


def test_products_do_not_leak_identity_or_unrelated_sport_rules():
    first, second = fixture(), fixture('DRAFT', 'Formula One', 'Monaco Rhythm')
    texts = [prompt(row) for row in (first, second)]
    for row, text, other in ((first, texts[0], texts[1]), (second, texts[1], texts[0])):
        source = current_source(row)
        for value in (source['folder_path'], source['folder_id'], row['id'], source['save_operation'],
                      context_from_row(row)['operation_tag'], source['files'][0]['file_id']):
            assert value in text and value not in other
    assert 'SC_SPORT_BASKETBALL' in texts[0] and 'SC_SPORT_FORMULA_ONE' not in texts[0]
    assert 'SC_SPORT_FORMULA_ONE' in texts[1] and 'SC_SPORT_MOTORSPORT' in texts[1]
    assert 'SC_SPORT_BASEBALL' not in ''.join(texts)
    # Hash-only record changes do not bloat the manifest.
    first['data']['upload_operation']['output']['files'][0]['metadata']['content_hash'] = 'f'*64
    assert prompt(first) == texts[0]


def test_saved_values_and_selected_options_are_preserved():
    row = fixture()
    row['data'].update(
        subjects=['Synthetic Athlete'], customer_facing_title='Synthetic Athlete — Courtside Legacy',
        confirmed_limit=75, worldwide=True, selected_collections=[dict(id='gid://shopify/Collection/42', title='Chosen')],
        publication_settings=dict(channels=['Online Store'], markets=['Australia']),
        inventory=dict(location_id='gid://shopify/Location/10', quantity=7, tracked=False),
        variants=[dict(Frame='Black', Size='XL', sku='EXACTSKU', price='388.00',
                       compare_at_price='', taxable=False, quantity=7)],
        metafields=[dict(namespace='custom', key='material', value='Confirmed material')],
    )
    text = prompt(row)
    for value in ('Synthetic Athlete', 'sc-edition-limit-75', 'Collection/42', '"quantity": 7',
                  '"tracked": false', 'EXACTSKU', '388.00', '"taxable": false', 'Confirmed material'):
        assert value in text
    assert 'Facebook & Instagram' not in text
    assert 'Limited to 100' not in text and 'sc-edition-limit-100' not in text
    row['data']['upload_operation']['product_id'] = 'gid://shopify/Product/123'
    row['data']['upload_operation']['product'] = dict(handle='saved-handle', title='Existing title')
    row['data']['upload_operation']['sync_map'] = dict(confirmed_limit=75)
    row['mode'] = 'UPDATE'
    text = prompt(row)
    assert 'gid://shopify/Product/123' in text and 'saved-handle' in text
    assert 'six Price fields' in text and 'including blanks' in text


def test_approved_extra_manifest_and_actual_order():
    row = fixture()
    source = current_source(row)
    source['files'].append(dict(order=9, role='detail', filename='detail.webp', file_id='id:detail'))
    source['expected_webp_count'] = 9
    text = build('LIVE', 'Test.psd', source=source, metadata=context_from_row(row),
                 load=lambda k, d, **kw: d)
    assert '"expected_webp_count": 9' in text and 'id:detail' in text
    assert text.index('black-frame.webp') < text.index('detail.webp')
    assert 'all 8' not in text and '8 required' not in text


def test_custom_template_clauses_survive_without_repeated_policy():
    row = fixture()
    text = prompt(row, lambda key, default, **kw: default + '\nUse the approved greeting: Sporting memories.\n'
                  'If original-file retrieval or transfer is unsupported, report the exact blocker before any Shopify write.')
    assert text.count('Sporting memories.') == 1
    assert 'before any Shopify write' not in text
    assert 'COMMON PRODUCT BUILD' not in text


def test_plain_legacy_template_is_normalized_too():
    from product_upload_prompt_core import NEW_SHOPIFY_PRODUCT_PROMPT
    text = prompt(fixture(), lambda key, default, **kw: NEW_SHOPIFY_PRODUCT_PROMPT)
    assert len(text) < 14000
    assert 'BRUTAL DRAFT RULE' not in text


def test_existing_full_update_keeps_price_exception_and_scope():
    row = fixture('UPDATE')
    row['data'].update(update_scope='full_standardisation', pricing_update=True, rewrite_description=True)
    text = prompt(row)
    assert '45–70' in text
    assert 'Small to A$169 and Medium to A$209' in text
    assert 'Large/XL/unframed prices' in text
    assert 'Preserve existing status and publication state' in text
    assert 'set ACTIVE' not in text


def test_context_whitelist_and_metadata_race(monkeypatch):
    from product_upload_prompt_copy import prepare
    import product_upload_prompts
    row = fixture()
    row['data']['access_token'] = 'secret-test-value'
    assert 'access_token' not in context_from_row(row)
    class Store:
        def read(self, *a): return row
        @contextmanager
        def locked(self, *a): yield row, None
    def changed(*a, **kw):
        row['data']['customer_facing_title'] = 'Newer title'
        return 'old prompt'
    monkeypatch.setattr(product_upload_prompts, 'build', changed)
    with pytest.raises(ValueError, match='details changed'):
        prepare(Store(), row['id'], 'actor', 'LIVE', current_source(row)['version'])
