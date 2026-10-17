"""Synthetic metadata, byte-preserving exports, scoped policies and recovery."""
import hashlib
import json
from pathlib import Path
import struct
from functools import lru_cache
from unittest.mock import patch
import pytest
from PIL import Image,ImageCms
import auto_editions as ae
from auto_editions_colour_source import inspect_psd,stage_profile,profile_info,ColourReview
from auto_editions_colour_policy import propose,approve,resolve,fingerprint
from auto_editions_colour import restore_export_profiles
from auto_editions_colour_recovery import recover,audit
from tests.test_auto_editions_discovery import database,store,pglite_database,register,tick,asset,PID,rows
from tests.test_auto_editions_reliability import idat


@lru_cache()
def icc():return ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()


def resource(rid,data):
    return b'8BIM'+struct.pack('>H',rid)+b'\0\0'+struct.pack('>I',len(data))+data+b'\0'*(len(data)%2)


def psd(path,profile=b'',extra=b'',width=20,height=10):
    resources=resource(1039,profile) if profile else resource(1041,b'\1')
    resources+=resource(1000,b'unchanged-other-resource')+extra
    path.write_bytes(b'8BPS\0\1'+b'\0'*6+struct.pack('>HIIHH',3,height,width,8,3)+struct.pack('>I',0)
                     +struct.pack('>I',len(resources))+resources+b'layers-fonts-plaque-numbering-composite-bytes')
    return path


def approved(source,profile=None):
    evidence=dict(name='reference-proof',sha256='1'*64,purpose='Synthetic owner-verified print comparison')
    proposal=propose('verified-template-group',profile or icc(),[dict(source=source,provenance=evidence)],[evidence],[evidence])
    return approve(proposal,'synthetic-owner',fingerprint(proposal))


def source():return ae.source_identity(PID,dict(id='id:original',rev='a1',content_hash='a'*64))


def test_untagged_is_supported_metadata_not_corruption(tmp_path):
    original=psd(tmp_path/'original.psd');before=original.read_bytes()
    assert inspect_psd(original)['state']=='untagged'
    proof=stage_profile(original,tmp_path/'candidate.psd',icc())
    assert original.read_bytes()==before and proof['pixels_converted'] is False
    candidate=inspect_psd(tmp_path/'candidate.psd');old=inspect_psd(original)
    assert candidate['icc']==icc()
    assert (tmp_path/'candidate.psd').read_bytes()[candidate['tail_offset']:]==before[old['tail_offset']:]
    assert (1000,resource(1000,b'unchanged-other-resource')) in candidate['blocks']
    assert all(rid!=1041 for rid,_ in candidate['blocks'])


@pytest.mark.parametrize('fault',['truncated','duplicate','conflicting','invalid','oversized'])
def test_inspection_failure_is_never_missing_profile(tmp_path,fault):
    path=psd(tmp_path/'source.psd',icc())
    if fault=='truncated':path.write_bytes(path.read_bytes()[:29])
    if fault=='duplicate':psd(path,icc(),resource(1039,icc()))
    if fault=='conflicting':psd(path,icc(),resource(1041,b'\1'))
    if fault=='invalid':psd(path,b'not-an-icc')
    if fault=='oversized':path.write_bytes(path.read_bytes()[:30]+struct.pack('>I',40*1024*1024))
    with pytest.raises(ColourReview):inspect_psd(path)


def test_no_reassignment_of_tagged_original_or_overwrite(tmp_path):
    path=psd(tmp_path/'tagged.psd',icc())
    with pytest.raises(ColourReview):stage_profile(path,tmp_path/'new.psd',icc())
    target=tmp_path/'existing.psd';target.write_bytes(b'keep')
    with pytest.raises(ValueError):stage_profile(path,target,icc())
    assert target.read_bytes()==b'keep'


def test_all_exports_can_lose_icc_and_recover_from_psd_bytes(tmp_path):
    names=['original.png','master.png','reference-1.png','number-1.png']
    profile=icc();name=profile_info(profile)['description']
    for export in names:Image.new('RGB',(20,10),'red').save(tmp_path/export)
    before={n:idat(tmp_path/n) for n in names}
    report=dict(source_inspection={'document':{'profile':name}},export_profiles={n:name for n in names})
    assert restore_export_profiles(tmp_path,report,names,source_icc=profile)==names
    for n in names:
        assert idat(tmp_path/n)==before[n]
        with Image.open(tmp_path/n) as image:assert image.info['icc_profile']==profile


def test_conflicting_export_rejected_before_any_metadata_write(tmp_path):
    profile=icc();name=profile_info(profile)['description']
    Image.new('RGB',(20,10)).save(tmp_path/'original.png')
    # A second valid RGB profile differing in identity must also be rejected.
    changed=bytearray(profile);changed[84:100]=b'1'*16
    Image.new('RGB',(20,10)).save(tmp_path/'master.png',icc_profile=bytes(changed))
    before=(tmp_path/'original.png').read_bytes()
    report=dict(source_inspection={'document':{'profile':name}},export_profiles={n:name for n in ['original.png','master.png']})
    with pytest.raises(ValueError,match='Conflicting'):restore_export_profiles(tmp_path,report,['original.png','master.png'],source_icc=profile)
    assert (tmp_path/'original.png').read_bytes()==before


def test_approval_reused_but_never_guessed_from_title_or_changed_revision():
    policy=approved(source())
    for _ in range(3):assert resolve(source(),[policy])[1]['approval_hash']==policy['approval_hash']
    with pytest.raises(ColourReview):resolve({**source(),'revision':'a2'},[policy])
    with pytest.raises(ColourReview):resolve(source(),[policy,policy])
    policy['members'][0]['source']['revision']='a2'
    with pytest.raises(ColourReview):resolve({**source(),'revision':'a2'},[policy])


def test_no_policy_approval_by_omission_or_stale_review():
    policy=approved(source())
    with pytest.raises(ColourReview):resolve(source(),[])
    policy['status']='awaiting_approval'
    with pytest.raises(ColourReview):resolve(source(),[policy])
    with pytest.raises(ValueError):approve(policy,'owner','0'*64)


def test_colour_recovery_is_opt_in_exact_scoped_and_once_only(store,monkeypatch):
    d,sql=store;register(store);tick(store,[asset()]);job=d.queue.claim('host')
    d.queue.checkpoint(PID,str(job['lease_token']),'host','Blocked','Colour policy awaiting approval',source=source())
    # A completed lease is no longer active but its old expiry is retained.
    sql.execute("UPDATE auto_edition_onboarding SET lease_until=now()-interval '1 second',priority=8")
    before=rows(sql,'edition_allocations'),rows(sql,'product_psd_mappings'),rows(sql,'synthetic_certificates')
    policy=approved(source())
    assert len(recover(d.queue,'owner',policies=[policy]))==1
    assert rows(sql,'auto_edition_onboarding')[0]['status']=='Blocked'
    with pytest.raises(PermissionError):recover(d.queue,'owner',policies=[policy],dry_run=False)
    monkeypatch.setenv('AUTO_EDITIONS_COLOUR_RECOVERY_ENABLED','true')
    assert len(recover(d.queue,'owner',policies=[policy],dry_run=False))==1
    row=rows(sql,'auto_edition_onboarding')[0]
    assert row['priority']==8 and row['source']==source()
    assert before==(rows(sql,'edition_allocations'),rows(sql,'product_psd_mappings'),rows(sql,'synthetic_certificates'))
    assert recover(d.queue,'owner',policies=[policy],dry_run=False)==[]


def test_prepared_packages_are_excluded_from_colour_recovery(store):
    d,sql=store;register(store);tick(store,[asset()]);job=d.queue.claim('host')
    d.queue.checkpoint(PID,str(job['lease_token']),'host','Blocked','Colour policy awaiting approval',source=source())
    sql.execute("INSERT INTO auto_edition_preparations(hash,manifest,proofs,receipts,created_by) VALUES(%s,'{}','[]','{}','fixture')",('1'*64,))
    sql.execute("UPDATE auto_edition_onboarding SET lease_until=now()-interval '1 second',preparation_hash=%s",('1'*64,))
    assert recover(d.queue,'owner',policies=[approved(source())])==[]


def test_colour_audit_deduplicates_and_separates_transfer_and_scratch():
    rows=[dict(product_gid='a',reason='Colour policy awaiting approval'),dict(product_gid='b',reason='Photoshop scratch disk failure'),
          dict(product_gid='c',reason='upload interrupted'),dict(product_gid='d',preparation_hash='retained')]
    value=audit(rows+rows)
    assert value['designs']==4 and value['groups']['PREPARED_RETAINED']['count']==1
    assert {'COLOUR_POLICY_PENDING','SCRATCH_DISK','UPLOAD_INTERRUPTED'}<=value['groups'].keys()


@pytest.mark.parametrize('reason',['Inspector failure','ICC export mismatch','Print-colour incompatibility','Photoshop scratch disk failure','upload interrupted'])
def test_unrelated_or_uncertain_failures_never_auto_retry(store,reason):
    d,sql=store;register(store);tick(store,[asset()]);job=d.queue.claim('host')
    d.queue.checkpoint(PID,str(job['lease_token']),'host','Blocked',reason,source=source())
    sql.execute("UPDATE auto_edition_onboarding SET lease_until=now()-interval '1 second'")
    assert recover(d.queue,'owner',policies=[approved(source())])==[]


def test_verified_different_embedded_profile_bytes_are_preserved(tmp_path):
    profile=bytearray(icc());profile[84:100]=b'2'*16;profile=bytes(profile)
    assert profile_info(profile)['sha256']!=profile_info(icc())['sha256']
    assert inspect_psd(psd(tmp_path/'different.psd',profile))['icc']==profile
    for name in ('original.png','master.png'):Image.new('RGB',(20,10)).save(tmp_path/name)
    name=profile_info(profile)['description']
    report=dict(source_inspection={'document':{'profile':name}},export_profiles={n:name for n in ('original.png','master.png')})
    restore_export_profiles(tmp_path,report,['original.png','master.png'],source_icc=profile)
    with Image.open(tmp_path/'master.png') as image:assert image.info['icc_profile']==profile


def test_45_prepared_designs_survive_recovery_and_paid_priority_is_retained(store,monkeypatch):
    from tests.test_auto_editions_v17 import mapping
    d,sql=store
    for n in range(1000,1045):
        pid,fid=mapping(sql,n);d.queue.enqueue(pid,fid,'fixture')
        digest=hashlib.sha256(str(n).encode()).hexdigest()
        sql.execute("INSERT INTO auto_edition_preparations(hash,manifest,proofs,receipts,created_by) VALUES(%s,%s::jsonb,'[]','{}','fixture')",
                    (digest,json.dumps({'source':{'product_gid':pid}})))
        sql.execute("UPDATE auto_edition_onboarding SET status='Blocked',reason='Colour policy awaiting approval',preparation_hash=%s WHERE product_gid=%s",(digest,pid))
    register(store);tick(store,[asset()]);job=d.queue.claim('host')
    assert job['product_gid']==PID
    d.queue.checkpoint(PID,str(job['lease_token']),'host','Blocked','Colour policy awaiting approval',source=source())
    sql.execute("UPDATE auto_edition_onboarding SET lease_until=now()-interval '1 second',priority=8 WHERE product_gid=%s",(PID,))
    before=[r for r in rows(sql,'auto_edition_onboarding') if r['preparation_hash']]
    monkeypatch.setenv('AUTO_EDITIONS_COLOUR_RECOVERY_ENABLED','true')
    assert len(recover(d.queue,'owner',policies=[approved(source())],dry_run=False))==1
    assert before==[r for r in rows(sql,'auto_edition_onboarding') if r['preparation_hash']]
    assert len(before)==45 and d.queue.claim('host')['product_gid']==PID


def test_health_reports_pending_as_review_and_scoped_recovery_counts(store,monkeypatch):
    import worker_health
    d,sql=store;register(store);tick(store,[asset()]);job=d.queue.claim('host')
    d.queue.checkpoint(PID,str(job['lease_token']),'host','Needs PSD Repair','Original PSD colour profile is unavailable',source=source())
    result=worker_health.Health(d.connect).snapshot()
    assert result['colour']==dict(affected=1,repaired=0,remaining=1)
    assert result['jobs'][0]['category']=='Needs Review'
    sql.execute("UPDATE auto_edition_onboarding SET lease_until=now()-interval '1 second'")
    monkeypatch.setenv('AUTO_EDITIONS_COLOUR_RECOVERY_ENABLED','true')
    recover(d.queue,'owner',policies=[approved(source())],dry_run=False)
    logs=worker_health.Health(d.connect).logs()
    assert any(r['code']=='PROFILE_APPROVED' for r in logs['rows'])
    job=d.queue.claim('host');digest='4'*64
    sql.execute("INSERT INTO auto_edition_preparations(hash,manifest,proofs,receipts,created_by) VALUES(%s,%s::jsonb,'[]','{}','fixture')",
                (digest,json.dumps({'source':source()})))
    d.queue.checkpoint(PID,str(job['lease_token']),'host','Blocked','Visual review required',digest=digest,metrics={})
    assert any(r['code']=='COLOUR_RECOVERED' for r in worker_health.Health(d.connect).logs()['rows'])


@pytest.mark.parametrize('untagged,conflict',[(False,False),(True,False),(False,True)])
def test_preparation_checks_actual_icc_bytes_and_preserves_original(tmp_path,monkeypatch,untagged,conflict):
    from scripts.prepare_auto_editions import prepare
    from tests.test_auto_editions import package
    import shutil
    profile=icc()
    original=psd(tmp_path/'input.psd',b'' if untagged else profile,width=200,height=100)
    before=original.read_bytes();identity={**source(),'content_hash':ae.file_hash(original,dropbox=True)}
    if untagged:
        policy_file=tmp_path/'policies.json';policy_file.write_text(json.dumps([approved(identity)]))
        monkeypatch.setenv('AUTO_EDITIONS_COLOUR_POLICIES_FILE',str(policy_file))
    output=tmp_path/'output'
    def photoshop(script):
        manifest=package(output)
        for n in (1,2):
            with ae.compose(manifest,output,n) as image:image.save(output/f'reference-{n}.png')
        shutil.copyfile(output/'reference-1.png',output/'original.png')
        names=[p.name for p in output.glob('*.png')];name=profile_info(profile)['description']
        report={**manifest,'source_inspection':{'document':{'profile':name,'profile_state':'tagged'}},'export_profiles':{n:name for n in names}}
        (output/'preparation.json').write_text(json.dumps(report))
        witness=bytearray(profile)
        if conflict:witness[84:100]=b'3'*16
        psd(output/'profile-witness.psd',bytes(witness),width=1,height=1)
        return 'AUTO_EDITIONS_PREPARED:2'
    with patch('scripts.photoshop_dispatch.run',side_effect=photoshop):
        if conflict:
            with pytest.raises(ColourReview,match='different ICC profile'):
                prepare(original,output,identity,number_layer='number',plaque_layer='plaque',total=2,reference_number=1)
        else:
            result=prepare(original,output,identity,number_layer='number',plaque_layer='plaque',total=2,reference_number=1)
            assert result['source_unchanged'] and result['print_ready'] is False
            manifest=json.loads((output/'manifest.json').read_text())
            assert manifest['colour_evidence']['source_state']==('untagged' if untagged else 'tagged')
            with Image.open(output/'edition-001-TEST-NOT-PRINT-READY.jpg') as image:assert image.info['icc_profile']==profile
    assert original.read_bytes()==before


def test_staged_copy_must_match_source_before_photoshop_opens_it(tmp_path):
    from scripts.prepare_auto_editions import prepare
    original=psd(tmp_path/'source.psd',icc())
    identity={**source(),'content_hash':ae.file_hash(original,dropbox=True)}
    def damaged_copy(src,dst):Path(dst).write_bytes(Path(src).read_bytes()+b'changed')
    with patch('scripts.prepare_auto_editions.shutil.copyfile',side_effect=damaged_copy),patch('scripts.photoshop_dispatch.run') as photoshop:
        with pytest.raises(ValueError,match='before Photoshop'):
            prepare(original,tmp_path/'output',identity,number_layer='number',plaque_layer='plaque',total=2,reference_number=1)
        photoshop.assert_not_called()
