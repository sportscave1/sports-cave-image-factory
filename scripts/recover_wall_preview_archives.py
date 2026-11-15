"""Dry-run by default. Requeue only explicitly named recoverable archive failures.

python scripts/recover_wall_preview_archives.py PREVIEW_UUID [PREVIEW_UUID ...]
Add --apply after reviewing IDs/version/state. Does not send emails or upload files.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wall_preview_crm_store as store


def recover(preview_ids, apply=False):
    results=[]
    with store.transaction() as cur:
        for pid in sorted({store.identifier(value) for value in preview_ids}):
            cur.execute('SELECT id,version FROM public.wall_previews WHERE id=%s FOR UPDATE',(pid,))
            row=dict(cur.fetchone() or {})
            cur.execute('SELECT version,state,reason,image IS NOT NULL AS has_image FROM public.wall_preview_archive_jobs WHERE preview_id=%s FOR UPDATE',(pid,))
            job=dict(cur.fetchone() or {})
            eligible=bool(row and job and row['version']==job['version'] and job['has_image']
                          and job['state']=='failed' and job['reason']=='archive_unavailable')
            if apply and eligible:
                cur.execute("""UPDATE public.wall_preview_archive_jobs SET state='queued',attempts=0,
                    due_at=now(),last_attempt_at=NULL,finished_at=NULL,reason='' WHERE preview_id=%s""",(pid,))
                store.LOG.info('wall_preview_archive_queued preview_id=%s version=%s recovery=true',pid,row['version'])
            results.append({'preview_id':pid,'version':row.get('version'),'state':job.get('state'),
                            'reason':job.get('reason'),'eligible':eligible,'requeued':apply and eligible})
    return results


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('preview_ids',nargs='+')
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    print(json.dumps(recover(args.preview_ids,args.apply),indent=2))
