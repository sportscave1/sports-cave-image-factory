"""Explicit campaign send boundary; reuses audience rules and the existing queue."""
from copy import deepcopy
import json
import os
import time
import uuid
from crm_campaign_content import preflight
from crm_audience import selection_page
from crm_navigation import require
from crm_resend import Config, MarketingDisabled
from crm_resend_marketing import single_email

OFF='Marketing delivery is currently OFF. No emails were sent.'
# Existing foundation readiness checks remain fail-closed until individually attested.
ATTESTATIONS={
 'DMARC confirmed before bulk activation':'CRM_DMARC_VERIFIED',
 'Resend webhooks proven before bulk activation':'CRM_RESEND_WEBHOOKS_VERIFIED',
 'Market legal review complete':'CRM_MARKET_REVIEW_VERIFIED',
 'Broadcast provider activated':'CRM_BROADCAST_VERIFIED',
}

def final_audience(shop,store,doc,*,clock=time.monotonic):
    if doc.get('market_audience'):
        from crm_campaign_markets import calculate
        return verified_native_audience(calculate(shop,store,doc.get('smart_hours',16),clock=clock)[doc['market']])
    audience=doc['audience']
    selection=audience if audience['kind']=='Selection' else {'kind':'Selection','name':audience['name'],'include':[audience],'exclude':[]}
    started=clock();state=None
    while state is None or not state['complete']:
        if clock()-started>30:raise ValueError('Audience calculation timed out. Narrow the audience and review again.')
        state=selection_page(shop,store,selection,state,smart_hours=doc.get('smart_hours',16),recipients=True)
    return verified_native_audience(state)

def verified_native_audience(state):
    from crm_native_unsubscribe import native_unsubscribe_url
    if any(not native_unsubscribe_url(state['profiles'].get(r['id'])) for r in state['recipients']):
        raise ValueError('Missing Shopify marketing unsubscribe URL. No campaign was queued; review recipient data.')
    return state


def production_checks(doc,cfg,env=None):
    from crm_campaign_sections import with_email_defaults
    doc=with_email_defaults(doc,cfg)
    env=os.environ if env is None else env
    checks=preflight(doc,env,cfg)
    live=dict(checks['live'])
    live.pop('One-click unsubscribe production path activated',None)
    for label,key in ATTESTATIONS.items():
        live[label]=(doc['market'] in env.get(key,'').split(',')) if key=='CRM_MARKET_REVIEW_VERIFIED' else env.get(key,'').lower()=='true'
    from crm_campaign_footer import has_unsubscribe_link
    live['Visible unsubscribe footer / functional production link']=bool(not doc.get('html_sections') or has_unsubscribe_link(doc['html_sections']['footer']))
    return {**checks['test'],**live,'Marketing delivery enabled':Config(env).enabled}

def review(shop,store,editor,env=None):
    doc=deepcopy(editor['document']);doc['copy_reviewed']=True
    state=final_audience(shop,store,doc)
    doc['counts']={k:state[k] for k in ('members','eligible','excluded','complete','checked_at')}
    cfg=store.render_settings(env)
    checks=production_checks(doc,cfg,env)
    blockers=[k for k,v in checks.items() if not v]
    from crm_campaign_schedule import plan
    from crm_logic import now
    try:plan(doc,state,now())
    except ValueError as exc:blockers.append(str(exc))
    return {'document':doc,'counts':doc['counts'],'blockers':blockers}

def send_test(store,user,editor,recipient,operation_id,*,env=None,session=None):
    """One explicit submission confirms reviewed copy; all backend guards still run."""
    require(user,'crm_campaigns_manage')
    import os_accounts
    if not os_accounts.is_admin(user):raise PermissionError('Only an administrator can send a campaign test.')
    recipient=recipient.strip() if isinstance(recipient,str) else recipient
    if not single_email(recipient):raise ValueError('Enter one valid email address.')
    doc=deepcopy(editor['document']);doc['copy_reviewed']=True
    checks=preflight(doc,env,store.render_settings(env))
    failed=[k for k,v in checks['test'].items() if not v]
    if failed:raise ValueError('Complete before testing: '+ '; '.join(failed))
    saved=store.draft(editor['id']) if editor.get('id') else None
    if not saved or saved['document']!=doc or saved['name']!=editor['name']:
        saved=store.save(user,editor['name'],doc,editor.get('id'),editor.get('version'),env=env)
    editor.update(deepcopy(saved))
    return store.test_campaign(user,saved['id'],saved['version'],recipient=recipient,confirmed=True,operation_id=operation_id,env=env,session=session)

def queue_campaign(shop,store,user,editor,operation_id,*,env=None):
    require(user,'crm_campaigns_manage')
    env=os.environ if env is None else env
    if env.get('CRM_MARKETING_ENABLED','').lower()!='true':raise MarketingDisabled(OFF)
    config=Config(env);config.require_send()
    operation=str(uuid.UUID(str(operation_id)))
    if not editor.get('id'):raise ValueError('Save this draft before sending.')
    identity=str(editor['id'])
    prior=store.q('SELECT * FROM crm_campaigns WHERE id=%s',(identity,),True)
    if prior:return {'id':identity,'status':prior['status'],'already_started':True}
    saved=store.draft(identity)
    if saved['version']!=editor['version'] or saved['document']!=editor['document'] or saved['archived_at']:
        raise ValueError('Save the current editable draft and review again.')
    doc=deepcopy(saved['document']);doc['copy_reviewed']=True
    state=final_audience(shop,store,doc)
    doc['counts']={k:state[k] for k in ('members','eligible','excluded','complete','checked_at')}
    cfg=store.render_settings(env)
    blocked=[k for k,v in production_checks(doc,cfg,env).items() if not v]
    if blocked:raise ValueError('Campaign blocked: '+ '; '.join(blocked))
    from crm_catalogue import Catalogue, refresh_catalogues
    if any(s['type']=='catalogue' and s['visible'] for s in doc.get('middle_sections',[])):
        current=refresh_catalogues(doc,Catalogue(shop),fresh=True)
        if current!=doc:raise ValueError('Catalogue facts changed. Refresh, save and review again.')
    from crm_campaign_schedule import plan
    from crm_logic import now
    schedule=plan(doc,state,now())
    template=str(uuid.uuid5(uuid.UUID(identity),'campaign-delivery-snapshot'))
    # Same queue and worker, immutable template snapshot; no new storage architecture.
    snapshot={'format':'campaign_delivery_v1','document':doc,'render_settings':cfg,'operation_id':operation,'schedule':schedule}
    with store.db() as conn:
        row=conn.execute('SELECT * FROM crm_campaign_drafts WHERE id=%s FOR UPDATE',(identity,)).fetchone()
        prior=conn.execute('SELECT * FROM crm_campaigns WHERE id=%s',(identity,)).fetchone()
        if prior:return {'id':identity,'status':prior['status'],'already_started':True}
        if row['version']!=saved['version'] or row['archived_at']:raise ValueError('Campaign changed; review again.')
        # A real stored definition satisfies the legacy FK; snapshot recipients are
        # already frozen, so this campaign starts at SENDING, never BUILDING.
        segment=conn.execute("INSERT INTO crm_segment_definitions(system_key,name,rules) VALUES(%s,%s,%s::jsonb) RETURNING id",('campaign-snapshot:'+identity,'Frozen campaign audience',json.dumps({'field':'consent','op':'eq','value':'SUBSCRIBED'}))).fetchone()
        conn.execute("INSERT INTO crm_templates(id,template_key,name,kind,content) VALUES(%s,%s,%s,'Campaign',%s::jsonb)",(template,'campaign-delivery:'+identity,saved['name'],json.dumps(snapshot)))
        conn.execute('INSERT INTO crm_template_versions(template_id,version,content) VALUES(%s,1,%s::jsonb)',(template,json.dumps(snapshot)))
        conn.execute("INSERT INTO crm_campaigns(id,name,template_id,template_version,segment_definition_id,status,snapshot_at) VALUES(%s,%s,%s,1,%s,'SENDING',now())",(identity,saved['name'],template,segment['id']))
        for recipient in state['recipients']:
            conn.execute('''INSERT INTO crm_marketing_sends(idempotency_key,shopify_customer_id,recipient_hash,template_id,template_version,campaign_id,due_at)
             VALUES(%s,%s,%s,%s,1,%s,%s) ON CONFLICT DO NOTHING''',('campaign:'+identity+':'+recipient['hash'],recipient['id'],recipient['hash'],template,identity,schedule.get(recipient['hash'],{}).get('due_at') or now()))
        store._history(conn,{**row,'send_snapshot':{'operation_id':operation,'document':doc,'render_settings':cfg,'recipients':len(state['recipients'])}},'campaign_delivery_queued',str(user.get('id','')),row)
    return {'id':identity,'status':'SENDING','recipients':len(state['recipients']),'already_started':False}
