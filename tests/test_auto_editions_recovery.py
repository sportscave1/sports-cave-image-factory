"""Preview-only legacy recovery and approved-policy reuse; disposable records only."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import hashlib,io
import pytest
from PIL import Image
import auto_editions as ae
import auto_editions_bulk as bulk
import auto_editions_preview_evidence as preview
import auto_editions_technical as technical
from tests.test_auto_editions_bulk import prepared,rebind
from tests.test_auto_editions_technical import flow,store,database,pglite_database,rows,protected


def legacy(root):
    record,assets=prepared(root)
    for a in [record['manifest']['master'],*record['manifest']['patches'].values()]:
        path=root/a['name']
        with Image.open(path) as im:im.save(root/'plain.png',icc_profile=None)
        (root/'plain.png').replace(path);a['sha256']=ae.file_hash(path)
    for receipt in record['receipts']['assets']:receipt.pop('bytes')
    rebind(record)
    return record,assets


def test_legacy_preview_uses_exact_bytes_without_relaxing_readiness(tmp_path):
    record,assets=legacy(tmp_path);before=deepcopy(record)
    with pytest.raises(ValueError,match='receipts'):bulk.evidence(record)
    cache=bulk.ReviewCache();small=cache.get(record,assets.fetch)
    assert small==cache.get(record,assets.fetch) and assets.fetch.call_count==2
    with Image.open(io.BytesIO(small)) as im:
        assert im.format=='JPEG' and im.width<=300 and not im.info.get('icc_profile')
    assert record==before
    with pytest.raises(ValueError,match='ICC'):bulk.inspect_asset(tmp_path,record['manifest']['master'],record['manifest']['dimensions'],lambda *a:None,record['hash'],dict(assets=[dict(r,bytes=(tmp_path/r['name']).stat().st_size) for r in record['receipts']['assets']]))


@pytest.mark.parametrize('fault',['hash','proof','receipt','size','pixels'])
def test_legacy_preview_still_rejects_changed_or_ambiguous_bytes(tmp_path,fault):
    r,assets=legacy(tmp_path)
    if fault=='hash':r['hash']='b'*64
    elif fault=='proof':r['proofs'][-1]['preparation_hash']='b'*64
    elif fault=='receipt':r['receipts']['assets'].pop()
    elif fault=='size':r['receipts']['assets'][0]['bytes']=1
    else:(tmp_path/'master.png').write_bytes(b'changed')
    with pytest.raises(ValueError):bulk.ReviewCache().get(r,assets.fetch)


def test_legacy_preview_keeps_real_current_icc_protection(tmp_path):
    r,assets=legacy(tmp_path)
    r['manifest']['colour_evidence']=dict(icc_sha256='a'*64,pixels_converted=False)
    rebind(r)
    with pytest.raises(ValueError,match='ICC'):bulk.ReviewCache().get(r,assets.fetch)


@pytest.mark.parametrize('revoked',[False,True])
def test_worker_reuses_approved_policy_without_extra_runtime_flag(flow,monkeypatch,revoked):
    d,sql,r,assets,root=flow;before=protected(sql)
    from auto_editions_colour_policy import propose,approve,fingerprint,resolve
    e=dict(name='isolated-evidence',sha256='1'*64,purpose='Synthetic test-only source provenance')
    with Image.open(root/'master.png') as im:icc=im.info['icc_profile']
    p=propose('isolated-approved-source',icc,[dict(source=r['manifest']['source'],provenance=e)],[e],[e])
    p=approve(p,'synthetic-owner',fingerprint(p));_,policy=resolve(r['manifest']['source'],[p])
    r['manifest']['colour_evidence']=dict(icc_sha256=hashlib.sha256(icc).hexdigest(),pixels_converted=False,policy=policy)
    rebind(r)
    from auto_editions_store import Preparations
    Preparations(d.connect).save(r['manifest'],r['proofs'],r['receipts'],'owner')
    sql.execute('UPDATE auto_edition_onboarding SET preparation_hash=%s',(r['hash'],))
    original=assets.integration.psd_open_metadata.side_effect
    # Asset identities/bytes remain unchanged; only the manifest's test policy differs.
    from auto_editions_cloud import DropboxAssets
    def metadata(token,fid,**kw):
        value=original(token,fid,**kw)
        if fid!='id:original':value['path_display']=DropboxAssets.path(r['hash'],value['id'].removeprefix('id:'))
        return value
    assets.integration.psd_open_metadata.side_effect=metadata
    monkeypatch.delenv('AUTO_EDITIONS_COLOUR_POLICY_BACKEND',raising=False)
    monkeypatch.delenv('AUTO_EDITIONS_COLOUR_POLICIES_FILE',raising=False)
    config=dict(policies=[p],memberships=[],default_group='')
    with patch('auto_editions_colour_store.configuration',side_effect=[config,dict(policies=[],memberships=[],default_group='')] if revoked else [config,config]) as read:
        assert technical.Technical(d.connect).run_one(assets)==('Failed' if revoked else 'Cloud Ready')
        assert read.call_count==2  # One batch snapshot and a fresh final fence.
    assert protected(sql)==before
    assert rows(sql,'auto_edition_technical_checks')[0]['state']==('Failed' if revoked else 'Succeeded')
    if revoked:assert not rows(sql,'auto_edition_layouts')
    else:assert not rows(sql,'auto_edition_layouts')[0]['approval'].get('visual_approved')


@pytest.fixture
def repair_flow(flow):
    d,sql,*_=flow
    for name in ('20261015024929_auto_editions_reset_design.sql','20261016210905_auto_editions_reset_cancellation.sql'):
        sql.execute(Path('supabase/migrations',name).read_text(encoding='utf-8'))
    return flow


@pytest.mark.parametrize('changed_source',[False,True])
def test_explicit_export_repair_retains_mapping_old_package_and_numbers(repair_flow,monkeypatch,changed_source):
    import uuid
    import worker_health_queue as queue
    d,sql,r,assets,root=repair_flow;t=technical.Technical(d.connect);t.seed();j=t.claim();t.fail(j,'Embedded ICC profile required.')
    before=protected(sql);old=deepcopy(rows(sql,'auto_edition_preparations'))
    monkeypatch.setenv('AUTO_EDITIONS_V15_ENABLED','true')
    key=str(uuid.uuid4())
    accepted=queue.submit(d.connect,r['manifest']['source']['product_gid'],'owner',key,repair_confirmed=True)
    assert accepted['accepted'] and accepted['status']=='Uploading'
    duplicate=queue.submit(d.connect,r['manifest']['source']['product_gid'],'owner',key,repair_confirmed=True)
    assert duplicate['duplicate'] and duplicate['status']=='Uploading'
    q=rows(sql,'auto_edition_onboarding')[0]
    assert q['replacement']['stage']=='Discovering' and q['replacement']['expected_source']==r['manifest']['source']
    assert q['preparation_hash']==r['hash'] and protected(sql)==before
    assert rows(sql,'auto_edition_preparations')==old
    assert sum(a['event']=='reset_requested' for a in rows(sql,'auto_edition_onboarding_audit'))==1
    from tests.test_auto_editions_discovery import due,asset
    fresh=asset()
    if changed_source:fresh.update(rev='changed',content_hash='b'*64)
    due(sql)
    d.tick(lambda cursor:dict(entries=[fresh],cursor='repair-delta',has_more=False),lambda fid:fresh)
    q=rows(sql,'auto_edition_onboarding')[0]
    assert q['replacement']['stage']==('Failed' if changed_source else 'Queued')
    assert q['preparation_hash']==r['hash'] and protected(sql)==before
    if not changed_source:
        assert d.queue.claim('isolated-companion')['source']==r['manifest']['source']
        assert d.queue.claim('second-companion') is None


@pytest.mark.parametrize('protected_state',['Cloud Ready','Preparing','deferred','lease','source','technical_processing','generation'])
def test_export_repair_protects_successful_active_deferred_changed_source(repair_flow,monkeypatch,protected_state):
    import uuid
    d,sql,r,assets,root=repair_flow;t=technical.Technical(d.connect);t.seed();j=t.claim();t.fail(j,'Embedded ICC profile required.')
    monkeypatch.setenv('AUTO_EDITIONS_V15_ENABLED','true')
    if protected_state in ('Cloud Ready','Preparing'):sql.execute('UPDATE auto_edition_onboarding SET status=%s',(protected_state,))
    elif protected_state=='deferred':sql.execute('UPDATE auto_edition_onboarding SET priority=0')
    elif protected_state=='lease':sql.execute("UPDATE auto_edition_onboarding SET lease_until=now()+interval '1 hour'")
    elif protected_state=='source':sql.execute("UPDATE auto_edition_onboarding SET source=jsonb_set(source,'{revision}','\"changed\"')")
    elif protected_state=='technical_processing':sql.execute("UPDATE auto_edition_technical_checks SET state='Processing',lease_until=now()+interval '1 hour'")
    else:sql.execute("UPDATE auto_edition_onboarding SET updated_at=now()+interval '1 second'")
    before=deepcopy(rows(sql,'auto_edition_onboarding'));mappings=protected(sql)
    with pytest.raises(ValueError):t.repair_exports(r['manifest']['source']['product_gid'],'owner',str(uuid.uuid4()))
    assert rows(sql,'auto_edition_onboarding')==before and protected(sql)==mappings
