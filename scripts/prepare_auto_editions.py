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


def prepare(source, output, identity, *, number_layer, plaque_layer, total, reference_number, scale=1):
    if type(scale) is not int or scale not in (1,2,3,4):
        raise ValueError('Choose native, 2x, 3x or 4x TEST preparation.')
    from scripts.photoshop_dispatch import run
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError('Use a new package directory; existing work is never overwritten.')
    if ae.file_hash(source, dropbox=True) != identity['content_hash']:
        raise ValueError('Source hash does not match the pinned Dropbox revision.')
    before = ae.file_hash(source)
    output.mkdir(parents=True)
    stage = output / 'staging'; stage.mkdir()
    staged = stage / 'input.psd'; shutil.copyfile(source, staged)
    request = dict(stage_root=str(stage),input=str(staged),output_root=str(output),
                   report=str(output/'preparation.json'),number_layer_name=number_layer,
                   plaque_layer_name=plaque_layer,edition_total=total,reference_number=reference_number,scale=scale)
    script = (ROOT/'scripts/photoshop/inspect_psd_editions.jsx').read_text(encoding='utf-8-sig')
    script += '\nvar SC_AUTO_EDITIONS_REQUEST = ' + json.dumps(request) + ';\n'
    script += (ROOT/'scripts/photoshop/prepare_auto_editions.jsx').read_text(encoding='utf-8-sig')
    result = run(script)
    if ae.file_hash(source) != before or ae.file_hash(staged) != before:
        raise ValueError('Source preservation check failed.')
    if not result.startswith('AUTO_EDITIONS_PREPARED:'):
        raise ValueError('Photoshop did not confirm preparation.')
    report=json.loads((output/'preparation.json').read_text(encoding='utf-8-sig'))
    # Measurements must never change the reusable artwork identity.
    timings=report.pop('timings',{})
    (output/'timings.json').write_text(json.dumps(timings))
    def asset(name):
        return dict(name=name,sha256=ae.file_hash(output/name))
    manifest={**report,'schema_version':1,'strategy':'photoshop_number_patches','source':identity,
              'master':asset('master.png'), 'patches':{str(n):asset(f'number-{n}.png') for n in range(1,total+1)}}
    ae.validate_manifest(manifest)
    proofs=[ae.compare_reference(manifest,output,n,output/f'reference-{n}.png')
            for n in sorted({1,reference_number,total})]
    original_proof=ae.compare_original_outside_number(manifest,output,reference_number,output/'original.png')
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (output/'proofs.json').write_text(json.dumps(proofs,indent=2)+'\n')
    (output/'source-proof.json').write_text(json.dumps(original_proof,indent=2)+'\n')
    ae.render_jpg(manifest,output,reference_number,output/f'edition-{reference_number:03}-TEST-NOT-PRINT-READY.jpg')
    return dict(preparation_hash=ae.fingerprint(manifest),proofs=proofs,source_unchanged=True,
                print_ready=False,master_bytes=(output/'master.png').stat().st_size,
                patch_bytes=sum((output/p['name']).stat().st_size for p in manifest['patches'].values()))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request',required=True,help='Saved reviewed preparation request JSON')
    args=parser.parse_args()
    request=json.loads(Path(args.request).read_text(encoding='utf-8-sig'))
    print(json.dumps(prepare(**request),indent=2),flush=True)
