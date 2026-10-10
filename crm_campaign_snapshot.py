"""Durable review contract, shared by confirmation and the existing queue."""
import json
from copy import deepcopy

def create(store,editor,document,settings,state,schedule):
    if not editor.get('id'):return None
    with store.db() as conn:
        row=conn.execute('SELECT * FROM crm_campaign_drafts WHERE id=%s FOR UPDATE',(editor['id'],)).fetchone()
        if (not row or row['version']!=editor['version'] or row['document']!=editor['document']
                or row['archived_at']):raise ValueError('Save the current draft before reviewing.')
        if conn.execute('SELECT 1 FROM crm_campaigns WHERE id=%s',(row['id'],)).fetchone():
            raise ValueError('This campaign has already been queued.')
        if conn.execute('SELECT 1 FROM crm_campaign_preparation WHERE campaign_id=%s',(row['id'],)).fetchone():
            raise ValueError('This campaign is already accepted. Open its status instead of reviewing another send.')
        counts={k:state[k] for k in ('members','eligible','excluded','complete','checked_at')}
        snapshot=conn.execute('''INSERT INTO crm_campaign_snapshots(campaign_id,campaign_version,document,
          render_settings,counts,recipients,schedule) VALUES(%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb) RETURNING id''',
          (row['id'],row['version'],json.dumps(document),json.dumps(settings),json.dumps(counts),
           json.dumps(state['recipients']),json.dumps(schedule))).fetchone()
        return str(snapshot['id'])

def load(store,identity,snapshot_id):
    if not snapshot_id:raise ValueError('Review the final audience before confirming this send.')
    row=store.q('SELECT * FROM crm_campaign_snapshots WHERE id=%s AND campaign_id=%s',(snapshot_id,identity),True)
    if not row:raise ValueError('Reviewed audience snapshot not found. Review again.')
    return deepcopy(row)
