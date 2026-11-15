"""Offline preview by default. Production execution requires separate owner approval."""
import argparse
import csv
import io
import json
from pathlib import Path
import sys
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import psd_directory
from psd_mapping_store import STORE, preview
from validate_psd_snapshot import validate,NAMES


def load(snapshot):
    validate(snapshot)  # Integrity and all 333/282/40/51 crosschecks, no writes.
    with zipfile.ZipFile(snapshot) as archive:
        rows=[list(csv.DictReader(io.StringIO(archive.read(name).decode('utf-8-sig')))) for name in NAMES]
    return psd_directory.snapshot_mapping(*rows)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('snapshot',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--existing-json',type=Path)
    parser.add_argument('--database-preview',action='store_true')
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--owner-approval',default='')
    parser.add_argument('--reviewed-preview',type=Path)
    args=parser.parse_args()
    if args.execute and (not args.owner_approval.strip() or not args.reviewed_preview):
        parser.error('Execution requires separate owner approval evidence and the reviewed database preview.')
    if args.execute and args.existing_json:
        parser.error('Offline existing JSON cannot authorize database execution.')
    catalogue,candidates=load(args.snapshot)
    if args.execute:
        reviewed=json.loads(args.reviewed_preview.read_text())
        if reviewed.get('mode')!='database-preview':
            parser.error('Execution requires an authoritative database preview, not an offline preview.')
        report=STORE.backfill(candidates,execute=True,approval=args.owner_approval,preview_hash=reviewed['preview_hash'])
        mode='executed'
    elif args.database_preview:
        report=STORE.backfill(candidates)
        mode='database-preview'
    else:
        existing=json.loads(args.existing_json.read_text()) if args.existing_json else {}
        report=preview(candidates,existing,{psd_directory.product_id(row) for row in catalogue})
        mode='offline-preview'
    report.update({'mode':mode,'verified_candidates':282,'unmatched_products':51,'excluded_review_files':40,
                   'counts':{key:len(report[key]) for key in ('insert','preserved','conflicts','missing_products')}})
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,default=str),encoding='utf-8')
    print(json.dumps({key:report[key] for key in ('mode','counts','preview_hash','verified_candidates','unmatched_products','excluded_review_files')},indent=2))
