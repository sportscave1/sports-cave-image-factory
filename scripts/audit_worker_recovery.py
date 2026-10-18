"""Read-only full-queue snapshot and local retained diagnostics reconciliation.

No application import, provider call, credential read, queue write or Photoshop.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from auto_editions_colour_review import registry
from auto_editions_recovery import classify


def audit(snapshot, local, inventory=()):
    config = dict(policies=registry(), memberships=[], default_group=json.loads(
        (Path(__file__).resolve().parents[1]/'config/auto_editions/colour-runtime-20261017.json').read_text())['default_group'])
    for row in snapshot['audits']:
        if row['event']=='colour_workflow_verified':
            config['memberships'].append(row['detail']['receipt'])
        elif not any(p['approval_hash']==row['detail']['policy']['approval_hash'] for p in config['policies']):
            config['policies'].append(row['detail']['policy'])
    # Local evidence is explanatory only. It cannot create colour provenance.
    retained={};source_observations={}
    failed={r['product_gid']:r for r in snapshot['rows'] if r['status']!='Cloud Ready'}
    if local:
        for folder in local.iterdir():
            if not folder.is_dir():continue
            try:
                job=json.loads((folder/'job-state.json').read_text(encoding='utf-8-sig'))
                context=job['context'];source=context['source']
                row=failed.get(context['product_gid'])
                if row and row.get('source')==source and row['reason'].startswith('Preparation failed: RuntimeError'):
                    # Metadata-only reconciliation of old generic failures.
                    # This observation is never a membership receipt or retry
                    # authority, and does not reread completed design assets.
                    from auto_editions_colour_source import inspect_psd
                    meta=inspect_psd(folder/'input.psd')
                    source_observations[context['product_gid']]=dict(source=source,
                        state=meta['state'],mode=meta['mode'],depth=meta['depth'],
                        path=str(folder/'input.psd'),authority='Archived header observation only; no provenance or approval created.')
                failure=json.loads((folder/'failure-detail.json').read_text(encoding='utf-8-sig'))
                retained.setdefault(context['product_gid'],[]).append(dict(source=source,error=failure.get('message'),path=str(folder/'failure-detail.json')))
            except (OSError,ValueError,KeyError):continue
    rows=[]
    current={r['product_gid']:r['metadata'] for r in inventory}
    for row in snapshot['rows']:
        if row['status']=='Cloud Ready':continue
        row={**row,'inventory_metadata':current.get(row['product_gid'])}
        decision=classify(row,config)
        evidence=[e for e in retained.get(row['product_gid'],[]) if e['source']==row.get('source')]
        rows.append(dict(product_gid=row['product_gid'],**decision,local_failures=evidence,
            source_observation=source_observations.get(row['product_gid'])))
    return dict(total=len(snapshot['rows']),verified_checkpoint=sum(r['status']=='Cloud Ready' for r in snapshot['rows']),
        failed=len(rows),eligible=sum(bool(r['action']) for r in rows),needs_review=sum(not r['action'] for r in rows),
        categories=dict(Counter(r['category'] for r in rows)),rows=rows)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',type=Path,required=True)
    parser.add_argument('--local',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--inventory',type=Path)
    args=parser.parse_args()
    result=audit(json.loads(args.snapshot.read_text(encoding='utf-8')),args.local,json.loads(args.inventory.read_text(encoding='utf-8')) if args.inventory else ())
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'}))
