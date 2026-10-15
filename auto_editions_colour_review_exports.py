"""Rebuild a local review package from retained exports, without Photoshop.

Original staged PSD/PNGs remain read-only. No grants, queues or providers are used.
"""
import json
from pathlib import Path
import shutil
import zipfile
import auto_editions as ae
from auto_editions_colour import restore_export_profiles
from auto_editions_colour_source import inspect_psd
from auto_editions_onboarding import detect_roles
from auto_editions_package import MAX_PACKAGE_BYTES


def stage_export_review(source,folder,output,identity,total):
    source,folder,output=Path(source),Path(folder),Path(output)
    if output.exists():raise ValueError('A new local review directory is required.')
    if ae.file_hash(source,dropbox=True)!=identity['content_hash']:
        raise ValueError('Pinned source content changed.')
    source_before=ae.file_hash(source);binary=inspect_psd(source)
    if binary['state']!='tagged' or binary['mode']!=3 or binary['depth']!=8:
        raise ValueError('Only an existing tagged RGB/8 profile may be preserved here.')
    report_path=folder/'preparation.json'
    report=json.loads(report_path.read_text(encoding='utf-8-sig'))
    if report.get('source_modified') not in (None,False):
        raise ValueError('Retained source modification evidence requires review.')
    if report.get('edition_total')!=total or report.get('source_dimensions')!=[binary['width'],binary['height']]:
        raise ValueError('Retained preparation differs from the current source or edition limit.')
    roles=detect_roles(report.get('source_inspection') or {},total)
    if roles['number_layer']!=report.get('number_layer_name') or roles['plaque_layer']!=report.get('plaque_layer_name'):
        raise ValueError('Retained export layer roles are inconsistent.')
    refs=sorted({1,total})
    names=['original.png','master.png']+[f'number-{n}.png' for n in range(1,total+1)]+[f'reference-{n}.png' for n in refs]
    if set(names)!=set(report.get('export_profiles',{})):raise ValueError('Incomplete or ambiguous retained export set.')
    if sum((folder/name).stat().st_size for name in names)>MAX_PACKAGE_BYTES:
        raise ValueError('Retained exports exceed the package transfer budget.')
    output.mkdir(parents=True)
    before={}
    for name in names:
        path=folder/name
        if path.is_symlink():raise ValueError('Retained symlink export requires review.')
        before[name]=ae.file_hash(path)
        with path.open('rb') as src,(output/name).open('xb') as dst:shutil.copyfileobj(src,dst,4*1024*1024)
    restored=restore_export_profiles(output,report,names,source_icc=binary['icc'])
    report.pop('timings',None)
    def asset(name):return dict(name=name,sha256=ae.file_hash(output/name))
    manifest={**report,'schema_version':1,'strategy':'photoshop_number_patches','source':identity,
        'print_ready':False,
        'master':asset('master.png'),'patches':{str(n):asset(f'number-{n}.png') for n in range(1,total+1)},
        'confirmed_roles':dict(number=roles['number_layer'],plaque=roles['plaque_layer']),
        'colour_evidence':dict(source_state='tagged',icc_sha256=binary['profile']['sha256'],policy=None,
            assignment=None,source_sha256=source_before,restored_exports=restored,pixels_converted=False)}
    ae.validate_manifest(manifest)
    proofs=[ae.compare_reference(manifest,output,n,output/f'reference-{n}.png') for n in refs]
    original=ae.compare_original_outside_number(manifest,output,1,output/'original.png')
    if ae.file_hash(source)!=source_before or any(ae.file_hash(folder/n)!=before[n] for n in names):
        raise ValueError('Original staged source/export integrity check failed.')
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    (output/'proofs.json').write_text(json.dumps(proofs+[original],indent=2),encoding='utf-8')
    (output/'original-export-hashes.json').write_text(json.dumps(before,indent=2),encoding='utf-8')
    archive=output/'review-package.zip'
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_STORED) as package:
        package.write(output/'manifest.json','manifest.json')
        for name in names:package.write(output/name,name)
    if archive.stat().st_size>MAX_PACKAGE_BYTES:raise ValueError('Review package exceeds the transfer budget.')
    result=dict(source=identity,preparation_hash=ae.fingerprint(manifest),package_sha256=ae.file_hash(archive),
        icc_sha256=binary['profile']['sha256'],restored_exports=len(restored),proofs=proofs+[original],
        original_source_unchanged=True,original_exports_unchanged=True,print_ready=False,
        uploaded=False,retry_authorized=False,package_bytes=archive.stat().st_size)
    (output/'review-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result
