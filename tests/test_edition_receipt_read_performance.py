"""Compare the released and optimised receipt rules on disposable PostgreSQL."""
from copy import deepcopy
import json
import random
from contextlib import nullcontext
from unittest.mock import MagicMock, patch

import auto_editions_v17 as v17
from tests.test_auto_editions_jobs import database


def legacy_sql(alias='p'):
    total = f"(CASE WHEN {alias}.manifest->>'edition_total' ~ '^[1-9][0-9]{{0,3}}$' THEN ({alias}.manifest->>'edition_total')::int ELSE 0 END)"
    assets = f"CASE WHEN jsonb_typeof({alias}.receipts->'assets')='array' THEN {alias}.receipts->'assets' ELSE '[]'::jsonb END"
    return f"""COALESCE({alias}.receipts->>'preparation_hash'={alias}.hash AND
      (SELECT count(*)={total}+1 AND count(DISTINCT a->>'name')={total}+1
       AND count(DISTINCT a->>'file_id')={total}+1
       AND bool_and(left(COALESCE(a->>'file_id',''),3)='id:' AND COALESCE(a->>'revision','')<>''
         AND (a->>'name'={alias}.manifest->'master'->>'name' OR EXISTS(
           SELECT 1 FROM jsonb_each(CASE WHEN jsonb_typeof({alias}.manifest->'patches')='object'
             THEN {alias}.manifest->'patches' ELSE '{{}}'::jsonb END) patch
           WHERE patch.value->>'name'=a->>'name')))
       FROM jsonb_array_elements({assets}) a),false)"""


def package(total=3):
    manifest = {'edition_total': total, 'master': {'name': 'master.png'},
                'patches': {str(n): {'name': f'number-{n}.png', 'sha256': 'a' * 64}
                            for n in range(1, total + 1)}}
    assets = [{'name': name, 'file_id': f'id:asset-{n}', 'revision': 'a1'}
              for n, name in enumerate(['master.png'] + [f'number-{n}.png' for n in range(1, total + 1)])]
    return manifest, {'preparation_hash': 'b' * 64, 'assets': assets}


def compare(cursor, manifest, receipts, alias='p'):
    cursor.execute(f"SELECT {legacy_sql(alias)} AS before, {v17.receipt_sql(alias)} AS after "
                   f"FROM (SELECT %s::jsonb AS manifest, %s::jsonb AS receipts, %s::text AS hash) {alias}",
                   (json.dumps(manifest), json.dumps(receipts), 'b' * 64))
    result = cursor.fetchone()
    assert result['before'] == result['after'], (manifest, receipts, result)
    return result['after']


def test_valid_and_malformed_receipts_have_identical_decisions(database):
    _, cursor = database
    for alias in ('p', 'prep'):
        manifest, receipts = package()
        assert compare(cursor, manifest, receipts, alias) is True
        for field, value in (('preparation_hash', None), ('preparation_hash', 'changed'),
                             ('assets', []), ('assets', {}), ('assets', None)):
            changed = deepcopy(receipts)
            changed[field] = value
            assert compare(cursor, manifest, changed, alias) is False
        for field, value in (('name', None), ('name', 'unapproved.png'), ('name', 'master.png'),
                             ('file_id', None), ('file_id', 'https://fixture.invalid'),
                             ('file_id', 'id:asset-0'), ('revision', ''), ('revision', None)):
            changed = deepcopy(receipts)
            changed['assets'][1][field] = value
            assert compare(cursor, manifest, changed, alias) is False
        for key, value in (('edition_total', None), ('edition_total', 0), ('edition_total', -1),
                           ('edition_total', '3'), ('edition_total', '03'), ('edition_total', 10000),
                           ('patches', []), ('patches', None), ('master', None)):
            changed = deepcopy(manifest)
            changed[key] = value
            compare(cursor, changed, receipts, alias)
        # UNION must prevent duplicate allowed names from multiplying receipts.
        manifest['patches']['extra'] = {'name': 'master.png'}
        assert compare(cursor, manifest, receipts, alias) is True


def test_deterministic_receipt_mutations_preserve_all_results(database):
    _, cursor = database
    randomizer = random.Random(21)
    for _ in range(100):
        manifest, receipts = package(randomizer.randint(1, 8))
        for _ in range(randomizer.randint(0, 4)):
            asset = randomizer.choice(receipts['assets'])
            field = randomizer.choice(['name', 'file_id', 'revision'])
            asset[field] = randomizer.choice([None, '', 'master.png', 'id:asset-0', 'a1', 'unexpected'])
        compare(cursor, manifest, receipts)


def test_thousand_patch_package_and_missing_patch_have_identical_results(database):
    _, cursor = database
    manifest, receipts = package(1000)
    assert compare(cursor, manifest, receipts) is True
    del manifest['patches']['1000']
    assert compare(cursor, manifest, receipts) is False


def test_sql_composes_inside_multiple_preparation_rows(database):
    _, cursor = database
    manifest, receipts = package()
    cursor.execute(f"""SELECT p.hash, {v17.receipt_sql('p')} AS valid
        FROM (VALUES (%s::text, %s::jsonb, %s::jsonb),
                     (%s::text, %s::jsonb, %s::jsonb)) AS p(hash,manifest,receipts)
        ORDER BY p.hash""", ('b' * 64, json.dumps(manifest), json.dumps(receipts),
                              'c' * 64, json.dumps(manifest), json.dumps(receipts)))
    assert [row['valid'] for row in cursor.fetchall()] == [True, False]


def test_technical_status_omits_unused_manifests_but_legacy_intake_keeps_them():
    import auto_editions_status as status
    pid = 'gid://shopify/Product/123'
    for technical in (True, False):
        connection = MagicMock()
        cursor = connection.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [{'product_gid': pid}]
        with patch('auto_editions_technical.enabled', return_value=technical), \
                patch('auto_editions_technical.colour_snapshot', return_value=nullcontext()), \
                patch('product_upload_services.enabled', return_value=True), \
                patch.object(status, 'project', return_value={'product_gid': pid, 'status': 'fixture'}), \
                patch('auto_editions_repair.display', side_effect=lambda value, *args, **kwargs: value):
            value = status.batch(lambda: connection, [pid])
        sql = cursor.execute.call_args.args[0]
        assert ('AS intake_manifest' in sql) is not technical
        assert ('AS intake_approval' in sql) is not technical
        assert 'AS prepared_source' in sql
        assert 'AS prepared_total' in sql
        assert 'AS receipts_valid' in sql
        assert value['rows'] == [{'product_gid': pid, 'status': 'fixture'}]
