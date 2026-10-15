"""Explicit offline, read-only reconciliation of prepared metadata exports.

Never called by page loading, discovery or claims. Exports must contain recorded
Supabase preparation identities and Dropbox Masters metadata, not PSD contents.
"""
import re
from auto_editions_cloud import DropboxAssets


def reconcile(records, entries, *, complete=False, offset=0, limit=200):
    expected={};issues=[]
    for record in records:
        digest=record.get('hash')
        if not re.fullmatch(r'[a-f0-9]{64}',str(digest or '')):
            issues.append({'reason':'Invalid recorded preparation identity'});continue
        if not record.get('mapped'):
            issues.append({'preparation_hash':digest,'reason':'Orphan recorded preparation; administrator review required'})
        receipts=record.get('receipts',{}).get('assets',[])
        if not receipts:
            issues.append({'preparation_hash':digest,'reason':'Recorded asset identities missing'})
        for receipt in receipts:
            fid=receipt.get('file_id')
            try:path=DropboxAssets.path(digest,receipt['name']).casefold()
            except (KeyError,ValueError):
                issues.append({'preparation_hash':digest,'reason':'Invalid recorded asset identity'});continue
            if not fid or fid in expected:
                issues.append({'preparation_hash':digest,'reason':'Missing or multiply owned recorded file identity'});continue
            expected[fid]=(digest,receipt,path)
    offset=max(0,int(offset));limit=max(1,min(int(limit),200))
    root=(DropboxAssets.ROOT+'/Masters/').casefold()
    for entry in entries[offset:offset+limit]:
        if entry.get('.tag','file')!='file':continue
        fid=entry.get('id');path=str(entry.get('path_display') or entry.get('path_lower') or '').casefold()
        if not path.startswith(root):
            issues.append({'file_id':fid,'reason':'Asset outside approved prepared Masters location'});continue
        known=expected.get(fid)
        if not known:
            issues.append({'file_id':fid,'reason':'Unrecorded prepared asset; preserve and investigate'});continue
        digest,receipt,canonical=known
        if (path!=canonical or entry.get('rev')!=receipt.get('revision')
                or (receipt.get('bytes') is not None and entry.get('size')!=receipt['bytes'])
                or entry.get('name')!=receipt.get('name')):
            issues.append({'file_id':fid,'preparation_hash':digest,'reason':'Recorded asset differs; do not overwrite or relink'})
        elif receipt.get('bytes') is None:
            issues.append({'file_id':fid,'preparation_hash':digest,'reason':'Legacy receipt has no size evidence; verification incomplete'})
    following=offset+limit if offset+limit<len(entries) else None
    # Absence is evidence only with a complete export, never a partial page.
    if complete and following is None:
        present={e.get('id') for e in entries if e.get('.tag','file')=='file'}
        for fid,(digest,_,_) in expected.items():
            if fid not in present:issues.append({'file_id':fid,'preparation_hash':digest,'reason':'Recorded asset missing from complete inventory'})
    return {'read_only':True,'inventory_complete':bool(complete),'issues':issues,'next_offset':following}


if __name__=='__main__':
    import argparse,json
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export',required=True,help='JSON: records, entries, complete; no credentials')
    parser.add_argument('--offset',type=int,default=0)
    args=parser.parse_args();data=json.loads(Path(args.export).read_text(encoding='utf-8'))
    print(json.dumps(reconcile(data['records'],data['entries'],complete=data.get('complete') is True,offset=args.offset),indent=2))
