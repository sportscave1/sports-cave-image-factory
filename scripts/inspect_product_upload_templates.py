"""Read local templates without Photoshop; optionally stage a versioned template.

Never grants colour provenance to uploads. Native reopen remains a separate gate.
"""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from auto_editions_colour_source import inspect_psd,stage_profile,profile_info,_hash
from scripts.benchmark_auto_editions_native_v19 import preflight

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--prepare-template',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];out=root/'output/product-uploads';out.mkdir(parents=True,exist_ok=True)
    assets=Path.home()/'Sportscave Dropbox/Sportscave Team Folder/03_ASSETS'
    reference=json.loads((root/'data/auto_editions_template.json').read_text())
    paths=[assets/'sportscave-new-designs-template.psd',assets/'mockup-product-page-template.psd',
           assets/'mockup-socials-template.psd',assets/'Auto Editions/Templates/SC_Auto_Editions_Base_Template_V1.psd']
    rows=[]
    for path in paths:
        if not path.exists():rows.append(dict(path=str(path),missing=True));continue
        result=inspect_psd(path)
        rows.append(dict(path=str(path),bytes=path.stat().st_size,sha256=_hash(path),
            worker_canvas_supported=result['width']*result['height']<=__import__('auto_editions').WORKER_MAX_PIXELS,
            **{k:result[k] for k in ('state','width','height','mode','depth','profile')}))
    baseline=rows[-1]
    report=dict(templates=rows,native_admission=preflight(),
        prior_native_inspection_matches=baseline.get('sha256')==reference['sha256'],
        prior_native_inspection='data/auto_editions_template.json',
        worker_contract='auto_editions_onboarding.detect + scripts/prepare_auto_editions.py; source geometry, not template coordinates',
        pending_psd_repair_excluded=True,production_modified=False)
    if args.prepare_template and baseline.get('state')=='untagged':
        target=out/'templates/SC_Auto_Editions_Base_Template_V2_sRGB_LOCAL.psd';target.parent.mkdir(exist_ok=True)
        icc=(Path('C:/Windows/System32/spool/drivers/color')/'sRGB Color Space Profile.icm').read_bytes()
        if not target.exists():
            proof=stage_profile(paths[-1],target,icc)
        else:
            original=inspect_psd(paths[-1]);staged=inspect_psd(target)
            original_tail=_hash(paths[-1],original['tail_offset']);staged_tail=_hash(target,staged['tail_offset'])
            if original_tail!=staged_tail:raise ValueError('Local template layers/pixels differ; retain both files for review.')
            proof=dict(source_sha256=_hash(paths[-1]),staged_sha256=_hash(target),layer_pixel_sha256=original_tail,
                       icc_sha256=staged['profile']['sha256'],pixels_converted=False)
        report['local_template']=dict(path=str(target),profile=profile_info(icc),proof=proof,
            scope='Explicit intended sRGB assignment for a versioned future template only. No inferred provenance or workflow membership for historical uploaded designs.',
            native_reopen_verified=False,worker_canvas_supported=baseline['worker_canvas_supported'],
            blocker='Canvas exceeds the existing 95 MP worker budget. No unapproved resize or budget increase performed.' if not baseline['worker_canvas_supported'] else None)
    (out/'template-audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
