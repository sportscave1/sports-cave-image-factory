"""Real disposable PostgreSQL: product scoping cannot weaken readiness fences."""
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from tests.test_auto_editions_jobs import database
from tests.test_auto_editions_eligibility import ready
from tests.test_auto_editions_quality import case, install
from tests.test_auto_editions_discovery import store, pglite_database, PID


@pytest.mark.parametrize('change', ['none', 'mapping', 'source', 'master', 'unapproved', 'not_ready', 'conflict'])
def test_product_scoped_index_matches_full_policy(database, tmp_path, change):
    registry, sql, unit, manifest = ready(database, tmp_path)
    product = unit['shopify_product_gid']
    if change == 'mapping': sql.execute("UPDATE product_psd_mappings SET dropbox_file_id='id:replacement'")
    if change == 'source':
        sql.execute('UPDATE auto_edition_onboarding SET source=%s::jsonb',
                    (json.dumps(dict(manifest['source'], revision='changed')),))
    if change == 'master': sql.execute("UPDATE auto_edition_onboarding SET preparation_hash=%s", ('b'*64,))
    if change == 'unapproved': sql.execute("UPDATE auto_edition_layouts SET approval=approval-'visual_approved'")
    if change == 'not_ready': sql.execute("UPDATE auto_edition_onboarding SET status='Preparing'")
    if change == 'conflict':
        other = deepcopy(manifest)
        other['number_region'] = [1, 1, 2, 2]
        sql.execute("INSERT INTO auto_edition_preparations(hash,manifest,proofs,receipts,created_by) VALUES(%s,%s::jsonb,'[]','{}','admin')", ('b'*64, json.dumps(other)))
        sql.execute("INSERT INTO auto_edition_layouts(product_gid,variant_id,preparation_hash,approval) VALUES(%s,'different',%s,'{}')", (product, 'b'*64))
    full = registry.index()
    scoped = registry.index(product_ids=[product])
    assert dict(scoped) == dict(full)
    assert scoped.hashes == full.hashes
    assert scoped.reasons == full.reasons
    assert registry.index(product_ids=[]) == {}
    assert registry.index(product_ids=['gid://shopify/Product/999']) == {}
    sql.execute('SELECT approval FROM auto_edition_layouts WHERE variant_id=%s', ('gid://shopify/ProductVariant/456',))
    assert sql.fetchone()['approval']['allocation_ids'] == [42]
    if change == 'conflict': assert (product, '*') not in scoped


@pytest.mark.parametrize('change', ['none', 'source', 'expired', 'limit', 'scope', 'policy', 'conflict'])
def test_scoped_production_quality_retains_all_current_fences(case, store, monkeypatch, change):
    import auto_editions_quality as quality
    from auto_editions_quality_store import Quality
    d, sql = install(case, store)
    monkeypatch.setenv('AUTO_EDITIONS_V16_AUTO_APPROVAL_ENABLED', 'true')
    integration = SimpleNamespace(psd_open_metadata=lambda token, fid, **kwargs:
                                  case.source if fid == 'id:original' else case.read(fid))
    assets = SimpleNamespace(integration=integration, token='synthetic', fetch=case.fetch)
    with patch.object(quality, 'standards', return_value=[case.standard]):
        assert Quality(d.connect).run_one(assets)
        if change == 'source': sql.execute("UPDATE auto_edition_onboarding SET source=jsonb_set(source,'{revision}','\"a2\"')")
        if change == 'expired': sql.execute("UPDATE auto_edition_quality_checks SET next_check_at=now()-interval '1 second'")
        if change == 'limit': sql.execute('UPDATE edition_products SET edition_total=4')
        if change == 'scope': case.standard['variant_ids'] = ['999']
        if change == 'policy': case.standard['revoked'] = True
        if change == 'conflict':
            sql.execute("INSERT INTO auto_edition_preparations(hash,manifest,proofs,receipts,created_by) VALUES(%s,%s::jsonb,'[]','{}','owner')", ('f'*64, json.dumps(case.record['manifest'])))
            sql.execute("INSERT INTO auto_edition_layouts(product_gid,variant_id,preparation_hash,approval) VALUES(%s,'999',%s,'{}')", (PID, 'f'*64))
        full = Quality(d.connect).index()
        assert Quality(d.connect).index(product_ids=[PID]) == full
        assert Quality(d.connect).index(product_ids=[]) == {}
        assert Quality(d.connect).index(product_ids=['gid://shopify/Product/999']) == {}
        assert bool(full) == (change == 'none')
