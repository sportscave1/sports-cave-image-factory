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


def final_audience(shop,store,doc,*,clock=time.monotonic):
    if doc.get('market_audience'):
        from crm_campaign_markets import calculate
        return verified_native_audience(calculate(shop,store,doc.get('smart_hours',16),clock=clock,market=doc['market'])[doc['market']])
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


def production_checks(doc,cfg,env=None,*,reviewed_audience=False):
    from crm_campaign_sections import with_email_defaults
    doc=with_email_defaults(doc,cfg)
    env=os.environ if env is None else env
    checks=preflight(doc,env,cfg)
    live=dict(checks['live'])
    if reviewed_audience:
        # Once queued, the durable reviewed membership replaces the UI count TTL.
        # Fresh consent, email identity and suppression checks still run per send.
        counts=doc.get('counts') or {}
        live['Fresh complete eligible audience']=bool(counts.get('complete') and counts.get('eligible',0)>0)
    live.pop('One-click unsubscribe production path activated',None)
    # Legacy human attestations remain readable in old settings, but are not
    # Campaigns authorization or delivery gates. Validate the actual values.
    for label in ('Business postal address configured and verified',
                  'Contact identity configured and confirmed',
                  'SPF/DKIM verification documented', 'DMARC confirmed before bulk activation',
                  'Resend webhooks proven before bulk activation', 'Market legal review complete',
                  'Broadcast provider activated'):
        live.pop(label,None)
    from crm_resend_marketing import single_email
    from crm_campaign_content import https
    live['Business postal address configured']=len(cfg.get('postal','').strip())>=10
    live['Business contact identity configured']=bool(cfg.get('business') and single_email(cfg.get('contact','')) and https(cfg.get('website','')))
    from crm_campaign_footer import has_unsubscribe_link
    live['Visible unsubscribe footer / functional production link']=bool(not doc.get('html_sections') or has_unsubscribe_link(doc['html_sections']['footer']))
    return {**checks['test'],**live,'Marketing delivery enabled':Config(env).enabled}

def review(shop,store,editor,env=None):
    from email_loading import stage
    doc=deepcopy(editor['document']);doc['copy_reviewed']=True
    with stage('Campaign review','authoritative_audience'):
        state=final_audience(shop,store,doc)
    doc['counts']={k:state[k] for k in ('members','eligible','excluded','complete','checked_at')}
    with stage('Campaign review','render_settings'):
        cfg=store.render_settings(env)
    with stage('Campaign review','production_validation'):
        checks=production_checks(doc,cfg,env)
    blockers=[k for k,v in checks.items() if not v]
    tracking_ok=False
    if editor.get('id'):
        try:
            with stage('Campaign review','tracking_validation'):
                validate_tracking(doc,cfg,editor['id'])
            tracking_ok=True
        except ValueError:blockers.append('Sports Cave OS tracking validation failed')
    from crm_campaign_schedule import plan
    from crm_logic import now
    schedule={}
    try:schedule=plan(doc,state,now())
    except ValueError as exc:blockers.append(str(exc))
    from crm_campaign_snapshot import create
    with stage('Campaign review','snapshot_creation'):
        snapshot_id=create(store,editor,doc,cfg,state,schedule) if not blockers else None
    return {'document':doc,'counts':doc['counts'],'blockers':blockers,'snapshot_id':snapshot_id,'render_settings':cfg,'tracking_ok':tracking_ok}


def validate_tracking(doc,cfg,campaign_id):
    from crm_campaign_content import render_campaign
    from crm_tracking import send_identity
    return render_campaign(doc,cfg,production=True,unsubscribe_url='https://www.sportscaveshop.com/account/unsubscribe',
                           campaign_id=campaign_id,send_id=send_identity(campaign_id))

def send_test(store,user,editor,recipient,operation_id,*,env=None,session=None):
    """One explicit submission confirms reviewed copy; all backend guards still run."""
    require(user,'crm_campaigns_manage')
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

def queue_campaign(shop,store,user,editor,operation_id,*,env=None,snapshot_id=None):
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
    from crm_campaign_snapshot import load
    reviewed=load(store,identity,snapshot_id)
    if reviewed['campaign_version']!=saved['version']:raise ValueError('Campaign changed; review again.')
    doc=reviewed['document'];state={'recipients':reviewed['recipients']}
    cfg=store.render_settings(env)
    if cfg!=reviewed['render_settings']:raise ValueError('Sender or rendering settings changed; review again.')
    blocked=[k for k,v in production_checks(doc,cfg,env).items() if not v]
    if blocked:raise ValueError('Campaign blocked: '+ '; '.join(blocked))
    validate_tracking(doc,cfg,identity)
    from crm_tracking import send_identity
    from crm_catalogue import Catalogue, refresh_catalogues
    if any(s['type']=='catalogue' and s['visible'] for s in doc.get('middle_sections',[])):
        current=refresh_catalogues(doc,Catalogue(shop),fresh=True)
        if current!=doc:raise ValueError('Catalogue facts changed. Refresh, save and review again.')
    from crm_logic import now
    schedule=reviewed['schedule']
    if not state['recipients']:raise ValueError('No eligible recipients in this reviewed snapshot.')
    if schedule and min(__import__('crm_logic').date(j['due_at']) for j in schedule.values())<=now():
        raise ValueError('Schedule missed; choose a future time and review again.')
    # Only remove newly unsafe recipients. Never add/recalculate a different audience.
    from crm_logic import eligibility,recipient_hash
    from crm_native_unsubscribe import native_unsubscribe_url
    blocked_recipients={}
    for start in range(0,len(state['recipients']),50):
        batch=state['recipients'][start:start+50]
        profiles={c['id']:c for c in shop.customer_batch([r['id'] for r in batch],fresh=True)}
        for recipient in batch:
            customer=profiles.get(recipient['id'])
            valid,reason=eligibility(customer,store.suppressed(recipient['id'],recipient['hash']))
            if valid and recipient_hash(customer.get('email'))!=recipient['hash']:reason='recipient_changed'
            if valid and not reason and not native_unsubscribe_url(customer):reason='missing_shopify_marketing_unsubscribe_url'
            if reason:blocked_recipients[recipient['hash']]=reason
    template=str(uuid.uuid5(uuid.UUID(identity),'campaign-delivery-snapshot'))
    # Same queue and worker, immutable template snapshot; no new storage architecture.
    snapshot={'format':'campaign_delivery_v1','document':doc,'render_settings':cfg,'operation_id':operation,
              'schedule':schedule,'audience_snapshot_id':snapshot_id}
    status='SCHEDULED' if schedule else 'SENDING'
    with store.db() as conn:
        row=conn.execute('SELECT * FROM crm_campaign_drafts WHERE id=%s FOR UPDATE',(identity,)).fetchone()
        prior=conn.execute('SELECT * FROM crm_campaigns WHERE id=%s',(identity,)).fetchone()
        if prior:return {'id':identity,'status':prior['status'],'already_started':True}
        if row['version']!=saved['version'] or row['archived_at']:raise ValueError('Campaign changed; review again.')
        suppressed=conn.execute('''SELECT recipient_hash,shopify_customer_id FROM crm_suppressions WHERE active
          AND (recipient_hash=ANY(%s) OR shopify_customer_id=ANY(%s))''',
          ([r['hash'] for r in state['recipients']],[r['id'] for r in state['recipients']])).fetchall()
        hashes={s['recipient_hash'] for s in suppressed};ids={s['shopify_customer_id'] for s in suppressed}
        for recipient in state['recipients']:
            if recipient['hash'] in hashes or recipient['id'] in ids:blocked_recipients[recipient['hash']]='local_suppression'
        # A real stored definition satisfies the legacy FK; snapshot recipients are
        # already frozen, so this campaign starts at SENDING, never BUILDING.
        segment=conn.execute("INSERT INTO crm_segment_definitions(system_key,name,rules) VALUES(%s,%s,%s::jsonb) RETURNING id",('campaign-snapshot:'+identity,'Frozen campaign audience',json.dumps({'field':'consent','op':'eq','value':'SUBSCRIBED'}))).fetchone()
        conn.execute("INSERT INTO crm_templates(id,template_key,name,kind,content) VALUES(%s,%s,%s,'Campaign',%s::jsonb)",(template,'campaign-delivery:'+identity,saved['name'],json.dumps(snapshot)))
        conn.execute('INSERT INTO crm_template_versions(template_id,version,content) VALUES(%s,1,%s::jsonb)',(template,json.dumps(snapshot)))
        conn.execute('''INSERT INTO crm_campaigns(id,name,template_id,template_version,segment_definition_id,status,
          snapshot_at,audience_snapshot_id,campaign_key,campaign_send_id,scheduled_at,sending_started_at,locked_at,final_recipient_count)
          VALUES(%s,%s,%s,1,%s,%s,%s,%s,%s,%s,%s,%s,now(),%s)''',
          (identity,saved['name'],template,segment['id'],status,reviewed['created_at'],snapshot_id,doc['campaign_key'],send_identity(identity),
           min(j['due_at'] for j in schedule.values()) if schedule else None,now() if not schedule else None,
           len(state['recipients'])-len(blocked_recipients)))
        for recipient in state['recipients']:
            reason=blocked_recipients.get(recipient['hash'],'')
            conn.execute('''INSERT INTO crm_marketing_sends(idempotency_key,shopify_customer_id,recipient_hash,template_id,template_version,campaign_id,due_at,status,error_code)
             VALUES(%s,%s,%s,%s,1,%s,%s,%s,%s) ON CONFLICT DO NOTHING''',('campaign:'+identity+':'+recipient['hash'],recipient['id'],recipient['hash'],template,identity,schedule.get(recipient['hash'],{}).get('due_at') or now(),'BLOCKED' if reason else 'PENDING',reason))
        store._history(conn,{**row,'send_snapshot':{'operation_id':operation,'document':doc,'render_settings':cfg,'recipients':len(state['recipients'])}},'campaign_delivery_queued',str(user.get('id','')),row)
    return {'id':identity,'status':status,'recipients':len(state['recipients'])-len(blocked_recipients),
            'skipped_after_review':len(blocked_recipients),'already_started':False}
