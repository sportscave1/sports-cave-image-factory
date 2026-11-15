"""Explicit manual first-step dispatch through the existing Engine and send ledger."""
import json
from crm_engine import Engine
from crm_checkout_identity import block_label


def history(store, checkout_key):
    return store.q('''SELECT s.* FROM crm_marketing_sends s
        JOIN crm_automation_enrollments j ON j.id=s.enrollment_id
        JOIN crm_automations a ON a.id=j.automation_id
        WHERE j.checkout_key=%s AND a.trigger_type='abandoned' AND NOT s.test_send
          AND (s.status IN ('ACCEPTED','SUBMITTING','UNCERTAIN') OR s.provider_email_id IS NOT NULL)
        ORDER BY s.created_at LIMIT 1''',(checkout_key,),True)


def outcome(store, enrollment):
    if enrollment['status']=='RECOVERED':return {'state':'DONE','result':'Recovered','delivery':'skipped'}
    receipt=store.q('SELECT * FROM crm_marketing_sends WHERE enrollment_id=%s AND step_index=0 AND NOT test_send',
                    (enrollment['id'],),True)
    if receipt and receipt['status']=='ACCEPTED' and receipt.get('provider_email_id'):
        return {'state':'DONE','result':'Sent','delivery':'sent'}
    if receipt and receipt['status'] in ('FAILED','BLOCKED','UNCERTAIN'):
        error=store.state('checkout-send-error:'+str(receipt['id'])).get('message')
        if receipt['status']=='UNCERTAIN':error='Provider acceptance is uncertain. Held for reconciliation; no resend.'
        if receipt['status']=='BLOCKED':error=block_label(receipt.get('error_code'))+' ('+str(receipt.get('error_code') or 'blocked')+')'
        return {'state':'FAILED','result':error or receipt.get('error_code') or 'Send failed','delivery':'failed'}
    if enrollment['status'] not in ('ACTIVE','COMPLETED'):
        return {'state':'DONE','result':block_label(enrollment.get('stop_reason')),'delivery':'skipped'}
    return {'state':'DONE','result':'Queued','delivery':'queued'}


def dispatch(store,shop,enrollment):
    """Target exactly one first-step receipt; never claim unrelated queued mail."""
    engine=Engine(store,shop)
    engine.config.require_send(False)
    identity=enrollment['id']
    with store.db() as conn:
        row=conn.execute('SELECT * FROM crm_automation_enrollments WHERE id=%s FOR UPDATE',(identity,)).fetchone()
        if row['status']!='ACTIVE' or row['current_step']!=0:
            raise ValueError('Already in flow')
        receipt=conn.execute('SELECT * FROM crm_marketing_sends WHERE enrollment_id=%s AND step_index=0 AND NOT test_send FOR UPDATE',(identity,)).fetchone()
        # Never reset a live lease, uncertain submission, or accepted receipt.
        if receipt and (receipt['status'] in ('CLAIMED','SUBMITTING','UNCERTAIN','ACCEPTED','BLOCKED') or receipt.get('provider_email_id')):
            pass
        else:
            steps=row['steps']
            steps[0]={**steps[0],'manual_checkout':True,'delay_seconds':0}
            conn.execute('UPDATE crm_automation_enrollments SET steps=%s::jsonb,next_due_at=now(),retry_after=NULL,updated_at=now() WHERE id=%s',
                         (json.dumps(steps),identity))
            if receipt and receipt['status']=='FAILED' and receipt.get('error_code') in ('provider_rejected','revalidation_unavailable'):
                conn.execute("UPDATE crm_marketing_sends SET status='PENDING',due_at=now(),lease_until=NULL WHERE id=%s",(receipt['id'],))
            elif receipt and receipt['status']=='PENDING' and receipt.get('error_code')!='provider_rate_limited':
                conn.execute('UPDATE crm_marketing_sends SET due_at=now() WHERE id=%s',(receipt['id'],))
    row=store.q('SELECT * FROM crm_automation_enrollments WHERE id=%s',(identity,),True)
    engine.advance(row)
    receipt=store.q('SELECT * FROM crm_marketing_sends WHERE enrollment_id=%s AND step_index=0 AND NOT test_send',(identity,),True)
    if receipt:
        engine.send_one(send_id=receipt['id'])
        row=store.q('SELECT * FROM crm_automation_enrollments WHERE id=%s',(identity,),True)
        if row['status']=='ACTIVE' and row['current_step']==0:engine.advance(row)
    row=store.q('SELECT * FROM crm_automation_enrollments WHERE id=%s',(identity,),True)
    return outcome(store,row)
