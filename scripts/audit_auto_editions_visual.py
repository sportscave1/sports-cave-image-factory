"""Read-only local snapshot audit. Never opens Photoshop, uploads or writes SQL."""
import argparse,json,sys
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import auto_editions as ae
import auto_editions_visual as visual

def inspect(row,records):
    m=row['manifest'];digest=ae.fingerprint(m);source=m['source'];checks={}
    try:ae.validate_manifest(m);checks['manifest_valid']=True
    except (ValueError,KeyError,TypeError):checks['manifest_valid']=False
    checks['exact_preparation']=row['preparation_hash']==digest
    checks['mapping_and_checkpoint']=(source==row['source'] and source['file_id']==row['dropbox_file_id']==row['file_id'] and source['product_gid']==row['product_gid'] and m['edition_total']==row['edition_total']==row['current_total'])
    proofs=row.get('proofs') or [];checks['bound_proofs']=bool(proofs) and all(p.get('preparation_hash')==digest for p in proofs)
    checks['original_proof']=any(p.get('outside_number_exact') is True and visual.sha(p.get('original_sha256')) for p in proofs)
    checks['number_reference_proofs']={1,m['edition_total']}<={p.get('number') for p in proofs if p.get('pixel_exact') is True and visual.sha(p.get('reference_sha256'))}
    receipts=row.get('receipts') or {};assets=receipts.get('assets') or []
    expected={m['master']['name']}|{p['name'] for p in m['patches'].values()}
    checks['receipt_structure']=(receipts.get('preparation_hash')==digest and len(assets)==len(expected) and {r.get('name') for r in assets}==expected and len({r.get('file_id') for r in assets})==len(assets) and all(r.get('file_id') and r.get('revision') and type(r.get('bytes')) is int and r['bytes']>0 for r in assets))
    record=dict(manifest=m,proofs=proofs);policy=visual.policy_for(record,records)
    checks['owner_reference_policy']=policy is not None
    reason=('Stored preparation, source identity or proof evidence requires review.' if not all(v for k,v in checks.items() if k!='owner_reference_policy') else
            'Exact trusted artwork references and Shopify relationship lack an approved visual policy.' if not policy else
            'Eligible for full provider/reference verification; snapshot alone cannot approve artwork.')
    return dict(product_gid=row['product_gid'],title=row.get('product_title'),preparation_hash=digest,decision='Needs Review',reason=reason,checks=checks,
                provider_verification_performed=False,regenerated=False,uploaded=False)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--snapshot',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    rows=json.loads(Path(a.snapshot).read_text(encoding='utf-8'));records=visual.policies()
    decisions=[inspect(row,records) for row in rows]
    report=dict(scope='local read-only eligibility audit; no approval writes',designs=len(rows),automatically_approved=0,
                decisions=dict(Counter(x['decision'] for x in decisions)),reasons=dict(Counter(x['reason'] for x in decisions)),rows=decisions)
    Path(a.output).write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in report.items() if k!='rows'}))
if __name__=='__main__':main()
