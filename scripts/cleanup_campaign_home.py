"""Explicit operator tool: preview first, apply reviewed stable IDs atomically.

python scripts/cleanup_campaign_home.py --plan plan.json
python scripts/cleanup_campaign_home.py --plan plan.json --apply --actor ADMIN_ID
Plan: {"keep": [UUID, UUID], "remove": [{"id": UUID, "version": N}, ...]}
No automatic title matching, provider calls, hard deletes, or schema changes.
"""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crm_campaign_store import CampaignStore
from crm_campaign_delete import VISIBLE, ELIGIBLE, tombstone


def inventory(conn):
    return conn.execute('''SELECT d.id,d.name,d.version,d.archived_at,c.status AS delivery_status,
      ('''+ELIGIBLE+''') AS deletable,
      (SELECT count(*) FROM crm_marketing_sends s WHERE s.campaign_id=d.id AND NOT s.test_send
       AND s.status='ACCEPTED' AND s.provider_email_id IS NOT NULL) AS accepted
      FROM crm_campaign_drafts d LEFT JOIN crm_campaigns c ON c.id=d.id
      WHERE '''+VISIBLE+' ORDER BY d.id').fetchall()


def cleanup(store, plan=None, *, apply=False, actor=''):
    with store.db() as conn:
        # Lock stable identities for the complete operation, including retained rows.
        if apply:
            conn.execute('LOCK TABLE crm_campaign_drafts IN SHARE ROW EXCLUSIVE MODE')
            conn.execute('SELECT id FROM crm_campaign_drafts ORDER BY id FOR UPDATE').fetchall()
            conn.execute('SELECT id FROM crm_campaigns ORDER BY id FOR UPDATE').fetchall()
            conn.execute('SELECT id FROM crm_marketing_sends ORDER BY id FOR UPDATE').fetchall()
        before=inventory(conn)
        if not plan: return {'inventory':before,'applied':False}
        keep={str(i) for i in plan['keep']}
        removals={str(r['id']):r['version'] for r in plan['remove']}
        if len(keep)!=2 or len(plan['keep'])!=2 or len(removals)!=len(plan['remove']):
            raise ValueError('Plan must retain exactly two distinct IDs and contain no duplicate removals.')
        if keep & removals.keys() or keep | removals.keys() != {str(r['id']) for r in before}:
            raise ValueError('Plan must cover the entire current visible inventory exactly. Review a fresh inventory.')
        for row in before:
            identity=str(row['id'])
            if identity in keep:
                if not row['accepted']: raise ValueError('Retained campaign lacks a genuine accepted provider receipt.')
            elif row['version']!=removals[identity] or not (row['deletable'] or row['archived_at'] and row['delivery_status'] in (None,'SENT','CANCELLED','FAILED')):
                raise ValueError('Removal changed or contains protected non-archived delivery history.')
        if apply:
            if not actor: raise ValueError('An accountable administrator actor is required.')
            user={'id':actor,'role':'admin','is_active':True}
            for row in before:
                if str(row['id']) in removals:
                    tombstone(conn,store,user,row['id'],row['version'],confirmed=True,historical=True)
        after=inventory(conn) if apply else None
        if apply and {str(r['id']) for r in after}!=keep: raise ValueError('Cleanup verification failed; transaction rolled back.')
        return {'before':before,'preserved':sorted(keep),'tombstoned':sorted(removals) if apply else [],
                'after':after,'applied':apply}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--actor',default='')
    args=parser.parse_args()
    if args.apply and not args.plan: parser.error('--apply requires a reviewed --plan')
    plan=json.loads(args.plan.read_text(encoding='utf-8')) if args.plan else None
    print(json.dumps(cleanup(CampaignStore(),plan,apply=args.apply,actor=args.actor),default=str,indent=2))
