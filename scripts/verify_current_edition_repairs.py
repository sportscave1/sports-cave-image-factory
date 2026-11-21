"""Verify owner-authorised PSD repair copies against pinned local source files."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts/studio')]

def main():
    import auto_editions as ae
    from PIL import ImageCms
    from auto_editions_colour_source import stage_profile
    from auto_editions_local import processor_lease
    from scripts.photoshop_dispatch import run
    from auto_editions_onboarding import detect
    out=ROOT/'output/edition-repair'
    live=Path.home()/'Sportscave Dropbox/Sportscave Team Folder/02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED'
    captains=live/'Mattingly, Jeter & Judge — The Captains.psd'
    assert ae.file_hash(captains,dropbox=True)=='16e48af3ee7ac0ba8fdeb1c5ba98db12ec89d7ccf4aa15572a27735feddf3006'
    target=out/'captains-srgb.psd'
    if not target.exists():
        proof=stage_profile(captains,target,ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes())
        (out/'captains-profile-proof.json').write_text(json.dumps(proof,indent=2))
    entries=[dict(work_path=str(target),product_gid='gid://shopify/Product/15396974854451',dropbox_file_id='id:u1tYiAa2O-AAAAAAAAAoeQ',dropbox_revision='0165da1c789f69a000000036d367e13'),dict(work_path=str(out/'bear-normalized-v2/bear-repaired.psd'),product_gid='gid://shopify/Product/8882143756595',dropbox_file_id='id:u1tYiAa2O-AAAAAAAAABFw',dropbox_revision='0165da1c13aadf0000000036d367e13')]
    request=dict(stage_root=str(out),output_root=str(out),report_path=str(out/'repaired-inspection.json'),entries=entries,smart_object_depth=0,smart_object_limit=0)
    script='var SC_PSD_INSPECT_REQUEST='+json.dumps(request)+';\n'+(ROOT/'scripts/photoshop/inspect_psd_editions.jsx').read_text(encoding='utf-8-sig')
    lease=processor_lease()
    try:run(script)
    finally:lease.unlink()
    inspected=json.loads((out/'repaired-inspection.json').read_text(encoding='utf-8-sig'))
    rows=[]
    for entry,doc in zip(entries,inspected['documents']):
        if doc.get('error'):raise ValueError(doc['error'])
        roles=detect(doc['inspection'],100)
        rows.append(dict(product_gid=entry['product_gid'],path=entry['work_path'],roles=roles,dropbox_hash=ae.file_hash(entry['work_path'],dropbox=True),profile=doc['inspection']['document']['profile']))
    (out/'verified-sources.json').write_text(json.dumps(rows,indent=2))
    print(json.dumps(rows))
if __name__=='__main__':main()
