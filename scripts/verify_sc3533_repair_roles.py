"""Read-only native verification of the two owner-requested SC3533 PSD roles."""
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts/studio')]


def main():
    import auto_editions as ae
    from auto_editions_role_evidence import REGISTRY
    from auto_editions_onboarding import detect_roles
    from auto_editions_local import processor_lease
    from scripts.photoshop_dispatch import run
    selected=[r for r in json.loads(REGISTRY.read_text())['resolutions']
              if r['source']['product_gid'] in ('gid://shopify/Product/8887166796083','gid://shopify/Product/9434618265907')]
    names=['Mike Tyson Fear Is Like Fire Motivational Wall Art.psd','Roger Federer Grace Under Pressure Wall Art.psd']
    base=Path.home()/'Sportscave Dropbox/Sportscave Team Folder/02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED'
    out=ROOT/'output/sc3533-native-roles';out.mkdir(parents=True,exist_ok=False)
    entries=[]
    for row,name in zip(selected,names):
        source=base/name
        if ae.file_hash(source,dropbox=True)!=row['source']['content_hash']:raise ValueError('Pinned source changed.')
        target=out/name;shutil.copyfile(source,target)
        entries.append(dict(work_path=str(target),product_gid=row['source']['product_gid'],
            dropbox_file_id=row['source']['file_id'],dropbox_revision=row['source']['revision']))
    request=dict(stage_root=str(out),output_root=str(out),report_path=str(out/'inspection.json'),
                 entries=entries,smart_object_depth=0,smart_object_limit=0)
    script='var SC_PSD_INSPECT_REQUEST='+json.dumps(request)+';\n'+(ROOT/'scripts/photoshop/inspect_psd_editions.jsx').read_text(encoding='utf-8-sig')
    lease=processor_lease()
    try:run(script)
    finally:lease.unlink()
    documents=json.loads((out/'inspection.json').read_text(encoding='utf-8-sig'))['documents']
    results=[]
    for selected,entry,doc in zip(selected,entries,documents):
        if doc.get('error'):raise ValueError(doc.get('error_message') or doc['error'])
        roles=detect_roles(doc['inspection'],100,source=selected['source'])
        if ae.file_hash(Path(entry['work_path']),dropbox=True)!=selected['source']['content_hash']:raise ValueError('Inspection changed PSD bytes.')
        results.append(dict(source=selected['source'],roles=roles,source_unchanged=True))
    (out/'verified.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps(results))


if __name__=='__main__':main()
