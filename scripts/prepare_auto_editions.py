"""One-time local preparation. Writes only a new package and never saves a PSD.

This is a preparation primitive, not a substitute for OS onboarding acceptance.
The original source, existing mapping and edition allocation are read-only.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import auto_editions as ae
from auto_editions_performance import file_hashes,stage as measured,resources

def native_cleanup_uncertain(output):
    """Only a dispatch that started needs Photoshop cleanup evidence."""
    output=Path(output)
    if not (output/'photoshop-dispatch.json').exists():return False
    try:return json.loads((output/'native-status.json').read_text(encoding='utf-8-sig')).get('owned_document_closed') is not True
    except (OSError,ValueError,AttributeError):return True


def prepare(source, output, identity, *, number_layer, plaque_layer, total, reference_number, scale=1,
            export_strategy='duplicate_merged',native_benchmark=False):
    if type(scale) is not int or scale not in (1,2,3,4):
        raise ValueError('Choose native, 2x, 3x or 4x TEST preparation.')
    if export_strategy not in ('duplicate_merged','history_merged_crop') or (export_strategy!='duplicate_merged' and native_benchmark is not True):
        raise ValueError('Unverified export strategy is restricted to an isolated native benchmark.')
    if native_benchmark is True:
        from scripts.benchmark_auto_editions_native_v19 import require_native_owner
        require_native_owner(source,output)
    from scripts.photoshop_dispatch import run
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError('Use a new package directory; existing work is never overwritten.')
    timings={}
    with measured(timings,'source_checksums'):
        hashes=file_hashes(source)
    if hashes['dropbox'] != identity['content_hash']:
        raise ValueError('Source hash does not match the pinned Dropbox revision.')
    before = hashes['sha256']
    output.mkdir(parents=True)
    from auto_editions_colour_source import inspect_psd,stage_profile,ColourReview
    from auto_editions_colour_policy import resolve
    colour=inspect_psd(source)
    if colour['mode']!=3 or colour['depth']!=8:
        raise ColourReview('Print-colour incompatibility: conversion requires separate approval.')
    policy=None;assignment=None
    icc=colour['icc']
    if not icc:icc,policy=resolve(identity)
    stage = output / 'staging'; stage.mkdir()
    staged = stage / 'input.psd'
    with measured(timings,'source_staging'):
        if policy:assignment=stage_profile(source,staged,icc)
        else:shutil.copyfile(source, staged)
    staged_hash=ae.file_hash(staged)
    if (not policy and staged_hash!=before) or (policy and assignment['source_sha256']!=before):
        raise ValueError('Source preservation check failed before Photoshop preparation.')
    expected_icc=stage/'expected-source.icc';expected_icc.write_bytes(icc)
    request = dict(stage_root=str(stage),input=str(staged),output_root=str(output),
                   icc_path=str(expected_icc),
                   report=str(output/'preparation.json'),number_layer_name=number_layer,
                   plaque_layer_name=plaque_layer,edition_total=total,reference_number=reference_number,scale=scale,
                   export_strategy=export_strategy,native_benchmark=native_benchmark is True)
    from auto_editions_role_evidence import resolution
    reviewed=resolution(identity)
    if reviewed and reviewed.get('hidden_number'):request['approved_hidden_number']=reviewed['hidden_number']
    script = (ROOT/'scripts/photoshop/inspect_psd_editions.jsx').read_text(encoding='utf-8-sig')
    script += '\nvar SC_AUTO_EDITIONS_REQUEST = ' + json.dumps(request) + ';\n'
    script += (ROOT/'scripts/photoshop/prepare_auto_editions.jsx').read_text(encoding='utf-8-sig')
    # Durable intent distinguishes pre-COM failures from uncertain RPC cleanup.
    # It is local diagnostic evidence, never part of the preparation identity.
    with (output/'photoshop-dispatch.json').open('x',encoding='utf-8') as dispatched:
        json.dump(dict(export_strategy=export_strategy,started=True),dispatched)
        dispatched.flush();__import__('os').fsync(dispatched.fileno())
    try:
        with measured(timings,'photoshop_prepare',path=output):
            result = run(script)
    finally:
        # A failed export must retain the same original/staged integrity fence.
        if ae.file_hash(source) != before or ae.file_hash(staged) != staged_hash:
            raise ValueError('Source preservation check failed.')
    if not result.startswith('AUTO_EDITIONS_PREPARED:'):
        raise ValueError('Photoshop did not confirm preparation.')
    report=json.loads((output/'preparation.json').read_text(encoding='utf-8-sig'))
    if report.get('source_dimensions')!=[colour['width'],colour['height']]:
        raise ColourReview('Inspector failure: Photoshop source geometry differs from the pinned PSD.')
    witness=inspect_psd(output/'profile-witness.psd')
    if witness['icc']!=icc:
        raise ColourReview('ICC export mismatch: Photoshop opened the source under a different ICC profile.')
    from auto_editions_colour import restore_export_profiles
    names=['original.png','master.png']+[f'number-{n}.png' for n in range(1,total+1)]
    names += [f'reference-{n}.png' for n in sorted({1,reference_number,total})]
    if reviewed and reviewed.get('hidden_number'):names.append('uncorrected.png')
    with measured(timings,'icc_preservation'):
        restored=restore_export_profiles(output,report,names,source_icc=icc)
    from auto_editions_artwork_recovery import verify_exports
    correction=verify_exports(output,report,identity,names)
    if correction:report['artwork_recovery']=correction
    report['colour_evidence']=dict(source_state=colour['state'],icc_sha256=__import__('hashlib').sha256(icc).hexdigest(),
        policy=policy,assignment=assignment,restored_exports=restored,source_sha256=before,pixels_converted=False)
    # Measurements must never change the reusable artwork identity.
    timings.update(report.pop('timings',{}))
    native_status=output/'native-status.json'
    if native_benchmark and not native_status.exists():
        raise ValueError('Native benchmark cleanup evidence is unavailable; retain processor ownership.')
    if native_status.exists():
        status=json.loads(native_status.read_text(encoding='utf-8-sig'))
        if status.get('completed') is not True or status.get('owned_document_closed') is not True:
            raise ValueError('Photoshop cleanup is incomplete; retain processor ownership for review.')
        timings.update(status['timings'])
        timings['dispatch_and_final_trace_seconds']=round(max(0,timings['photoshop_prepare_seconds']-timings['native_total_ms']/1000),6)
    def asset(name):
        return dict(name=name,sha256=ae.file_hash(output/name))
    with measured(timings,'asset_checksums'):
        manifest={**report,'schema_version':1,'strategy':'photoshop_number_patches','source':identity,
                  'master':asset('master.png'), 'patches':{str(n):asset(f'number-{n}.png') for n in range(1,total+1)}}
    ae.validate_manifest(manifest)
    with measured(timings,'pixel_verification',path=output):
        proofs=[ae.compare_reference(manifest,output,n,output/f'reference-{n}.png')
                for n in sorted({1,reference_number,total})]
        original_proof=ae.compare_original_outside_number(manifest,output,reference_number,output/'original.png')
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (output/'proofs.json').write_text(json.dumps(proofs,indent=2)+'\n')
    (output/'source-proof.json').write_text(json.dumps(original_proof,indent=2)+'\n')
    with measured(timings,'jpg_preview'):
        ae.render_jpg(manifest,output,reference_number,output/f'edition-{reference_number:03}-TEST-NOT-PRINT-READY.jpg')
    timings['source_bytes']=source.stat().st_size
    timings['staged_psd_bytes']=staged.stat().st_size
    timings['generated_bytes']=sum((output/name).stat().st_size for name in names)
    (output/'timings.json').write_text(json.dumps(timings))
    return dict(preparation_hash=ae.fingerprint(manifest),proofs=proofs,source_unchanged=True,
                print_ready=False,master_bytes=(output/'master.png').stat().st_size,
                patch_bytes=sum((output/p['name']).stat().st_size for p in manifest['patches'].values()))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request',required=True,help='Saved reviewed preparation request JSON')
    args=parser.parse_args()
    request=json.loads(Path(args.request).read_text(encoding='utf-8-sig'))
    print(json.dumps(prepare(**request),indent=2),flush=True)
