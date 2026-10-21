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


def native_dispatch(run, script, output):
    # A preflight cleanup receipt cannot prove a subsequent RPC closed its doc.
    status=Path(output)/'native-status.json'
    if status.exists():status.replace(Path(output)/'preflight-native-status.json')
    return run(script)


def select_export_strategy():
    # Retain the released method when the existing native benchmark RAM floor
    # cannot be met. History export saved time but used ~0.7 GiB more Photoshop
    # working set in matched 4x trials. Never restart/purge the user's app here.
    try:
        import psutil
        if psutil.virtual_memory().available >= 4*1024**3:return 'history_merged_crop'
    except (ImportError,OSError):pass
    return 'duplicate_merged'


def prepare(source, output, identity, *, number_layer, plaque_layer, total, reference_number, scale=1,
            export_strategy=None,native_benchmark=False,preparation_plan=None,preparation_context=None):
    if preparation_plan is None and (type(scale) is not int or scale not in (1,2,3,4)):
        raise ValueError('Choose native, 2x, 3x or 4x TEST preparation.')
    if export_strategy is None:export_strategy=select_export_strategy()
    if export_strategy not in ('duplicate_merged','history_merged_crop'):
        raise ValueError('Unsupported preparation export strategy.')
    if native_benchmark is True:
        from scripts.benchmark_auto_editions_native_v19 import require_native_owner
        require_native_owner(source,output)
    from scripts.photoshop_dispatch import run
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError('Use a new package directory; existing work is never overwritten.')
    ae.source_identity(identity.get('product_gid'),dict(id=identity.get('file_id'),
        rev=identity.get('revision'),content_hash=identity.get('content_hash')))
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
    if preparation_context is not None:
        from auto_editions_preparation_geometry import for_context
        candidate=for_context([colour['width'],colour['height']],preparation_context,legacy_scale=scale)
        if candidate['references']:preparation_plan=candidate
    if preparation_plan is not None:
        from auto_editions_preparation_geometry import validate
        scale=preparation_plan['scale']
        planned=preparation_plan['output_dimensions']
        validate([colour['width'],colour['height']],planned,
                 dict(plan=preparation_plan,scale=scale,method='native' if scale==1 else 'photoshop_layered_bicubic_smoother',
                      supplier_verified=False,quality_approval_required=scale!=1))
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
    if preparation_plan is not None:
        request.update(target_dimensions=preparation_plan['output_dimensions'],preparation_plan=preparation_plan)
    from auto_editions_role_evidence import resolution
    reviewed=resolution(identity)
    if reviewed and reviewed.get('hidden_number'):request['approved_hidden_number']=reviewed['hidden_number']
    inspector = (ROOT/'scripts/photoshop/inspect_psd_editions.jsx').read_text(encoding='utf-8-sig')
    preparation = (ROOT/'scripts/photoshop/prepare_auto_editions.jsx').read_text(encoding='utf-8-sig')
    def script_for(value):
        return inspector+'\nvar SC_AUTO_EDITIONS_REQUEST = '+json.dumps(value)+';\n'+preparation
    # Durable intent distinguishes pre-COM failures from uncertain RPC cleanup.
    # It is local diagnostic evidence, never part of the preparation identity.
    with (output/'photoshop-dispatch.json').open('x',encoding='utf-8') as dispatched:
        json.dump(dict(export_strategy=export_strategy,started=True),dispatched)
        dispatched.flush();__import__('os').fsync(dispatched.fileno())
    try:
        from auto_editions_preflight import validate,verify_resize
        preflight={**request,'preflight_only':True,'report':str(output/'preflight.json')}
        with measured(timings,'native_preflight',path=output):
            if native_dispatch(run,script_for(preflight),output) != 'AUTO_EDITIONS_PREFLIGHT':
                raise ValueError('Photoshop did not confirm template preflight.')
            inspection=json.loads((output/'preflight.json').read_text(encoding='utf-8-sig'))
            background=validate(output,inspection,identity,total,number_layer,plaque_layer,scale)
            if background:request['opaque_resize_layer']=background
        with measured(timings,'photoshop_prepare',path=output):
            result = native_dispatch(run,script_for(request),output)
    finally:
        # A failed export must retain the same original/staged integrity fence.
        if ae.file_hash(source) != before or ae.file_hash(staged) != staged_hash:
            raise ValueError('Source preservation check failed.')
    if not result.startswith('AUTO_EDITIONS_PREPARED:'):
        raise ValueError('Photoshop did not confirm preparation.')
    report=json.loads((output/'preparation.json').read_text(encoding='utf-8-sig'))
    if background:report['resize_evidence']=verify_resize(output)
    if report.get('source_dimensions')!=[colour['width'],colour['height']]:
        raise ColourReview('Inspector failure: Photoshop source geometry differs from the pinned PSD.')
    if preparation_plan is not None and report.get('dimensions')!=preparation_plan['output_dimensions']:
        raise ValueError('Photoshop output differs from the pinned proportional preparation plan.')
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
        proofs,original_proof=ae.verify_preparation_pixels(manifest,output,reference_number)
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
