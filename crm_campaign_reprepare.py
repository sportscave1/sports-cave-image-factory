"""Explicit recovery only before publication. Unknown delivery is never retried."""
from copy import deepcopy
from crm_navigation import require


def recovery_receipt(editor, receipt):
    # A failed replacement transaction leaves the previous FAILED receipt.
    # Finding that receipt is not evidence that the new recovery was accepted.
    if receipt and editor.get('recovery_operation') and str(receipt.get('operation_id'))==str(editor['recovery_operation']):
        return None
    return receipt


def candidate(store, user, identity):
    require(user,'crm_campaigns_manage')
    return store.q('''SELECT p.* FROM crm_campaign_preparation p WHERE p.campaign_id=%s
      AND p.status='FAILED' AND NOT EXISTS(SELECT 1 FROM crm_campaigns c WHERE c.id=p.campaign_id)
      AND NOT EXISTS(SELECT 1 FROM crm_marketing_sends s WHERE s.campaign_id=p.campaign_id)''',(identity,),True)


def restrict(store, editor, state):
    operation=editor.get('recovery_operation')
    if not operation:return state
    job=store.q('''SELECT p.operation_id,s.recipients FROM crm_campaign_preparation p
      JOIN crm_campaign_snapshots s ON s.id=p.snapshot_id
      WHERE p.campaign_id=%s AND p.status='FAILED'
      AND NOT EXISTS(SELECT 1 FROM crm_campaigns c WHERE c.id=p.campaign_id)
      AND NOT EXISTS(SELECT 1 FROM crm_marketing_sends m WHERE m.campaign_id=p.campaign_id)''',(editor['id'],),True)
    if not job or str(job['operation_id'])!=str(operation):raise ValueError('Recovery changed. Reopen campaign status.')
    allowed={(r['id'],r['hash']) for r in job['recipients']}
    result=deepcopy(state)
    result['recipients']=[r for r in state['recipients'] if (r['id'],r['hash']) in allowed]
    result['eligible']=len(result['recipients'])
    removed=state['eligible']-result['eligible']
    if removed:result['excluded']['outside_original_review']=removed
    return result
