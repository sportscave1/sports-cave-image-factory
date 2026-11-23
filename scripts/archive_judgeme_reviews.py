"""Archive a published Judge.me CSV and its image/video files without a database.

Run with --csv <export> --destination <private backup directory>.
Real exports belong outside Git and must never be used in development previews.
This copies files locally; it never imports production data or turns off Judge.me.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from reviews_import import read_csv
from reviews_model import auto_mapping,normalize
from reviews_media import download

def archive(csv_path,destination):
    source=Path(csv_path);dest=Path(destination).resolve()
    root=Path(__file__).resolve().parents[1]
    if dest==root or root in dest.parents:raise ValueError('Use a private directory outside the repository for customer exports.')
    dest.mkdir(parents=True,exist_ok=True);(dest/'media').mkdir(exist_ok=True)
    headers,rows=read_csv(source.read_bytes());mapping=auto_mapping(headers)
    raw_sha=hashlib.sha256(source.read_bytes()).hexdigest()
    backup=dest/('judge-me-published-'+raw_sha[:12]+'.csv')
    if not backup.exists():shutil.copyfile(source,backup)
    result={'export_sha256':raw_sha,'input_rows':len(rows),'published':0,'excluded':0,'invalid':[],'reviews':[],'media':[]}
    for number,raw in enumerate(rows,2):
        try:item=normalize(raw,'judgeme',mapping,'sportscave-nb.myshopify.com')
        except ValueError as exc:result['invalid'].append({'row':number,'reason':str(exc)});continue
        if item['status']!='PUBLISHED':result['excluded']+=1;continue
        result['published']+=1;result['reviews'].append({'row':number,'key':item['dedupe_key'],'type':item['review_type'],'media_count':len(item['media'])})
        for media in item['media']:
            record={'row':number,'review_key':item['dedupe_key'],**media}
            try:
                body,mime,ext=download(media['source_url'],media['kind'],preserve_original=True)
                digest=hashlib.sha256(body).hexdigest();target=dest/'media'/(digest+ext)
                if not target.exists():target.write_bytes(body)
                record.update(status='COPIED',file='media/'+target.name,sha256=digest,size_bytes=len(body),mime_type=mime)
            except Exception:record.update(status='FAILED',error='download_or_validation_failed')
            result['media'].append(record)
    result['media_copied']=sum(m['status']=='COPIED' for m in result['media'])
    result['complete_csv_and_listed_media']=not result['invalid'] and all(m['status']=='COPIED' for m in result['media'])
    result['videos_reconciled']=False # Judge.me CSV never proves that every video was exported.
    (dest/'manifest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--csv',required=True);parser.add_argument('--destination',required=True)
    args=parser.parse_args();result=archive(args.csv,args.destination)
    print(json.dumps({k:v for k,v in result.items() if k not in ('reviews','media')},indent=2))
    sys.exit(0 if result['complete_csv_and_listed_media'] else 1)
