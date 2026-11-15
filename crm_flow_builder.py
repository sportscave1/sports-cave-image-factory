"""Sequence controls around the existing automation store and email composer."""
from table_design import TABLE_ROW_HEIGHT
from copy import deepcopy
from datetime import timedelta
import uuid
import streamlit as st
from crm_automation_definition import TRIGGERS, email_step, validate
from crm_automation_timing import delay_controls
from crm_logic import now, date


def display_name(name):
    return 'Abandoned Checkout Recovery' if name == 'Abandoned Checkout — Reminder 1' else name


def edit_sequence(flow,step_id,action):
    result=deepcopy(flow);steps=result['emails']
    index=next(i for i,s in enumerate(steps) if s['step_id']==step_id)
    if action=='duplicate':
        clone=deepcopy(steps[index]);clone['step_id']=str(uuid.uuid4())
        clone['name']=(clone.get('name') or 'Email')+' copy';steps.insert(index+1,clone)
    elif action=='delete':
        if len(steps)==1:raise ValueError('Keep at least one email in the draft.')
        steps.pop(index)
    elif action in ('up','down'):
        target=index+(-1 if action=='up' else 1)
        if not 0<=target<len(steps):raise ValueError('Email is already at the end of the sequence.')
        steps[index],steps[target]=steps[target],steps[index]
    elif action=='toggle':steps[index]['enabled']=not steps[index].get('enabled',True)
    else:raise ValueError('Unknown step action.')
    return validate(result)


def simulate(flow,at=None,*,subscribed=True,purchased=False,customer=None,event_facts=None,exit_after=None):
    """Pure planning only: no database, Shopify, provider, or enrollment writes."""
    validate(flow);at=at or now();rows=[]
    blocked=not subscribed or (purchased and flow.get('exit_on_purchase',flow['trigger'] in ('abandoned','win_back')))
    from crm_automation_definition import qualifies
    rules_pass=qualifies(flow,customer or {'defaultAddress':{'countryCodeV2':'AU'}},event_facts or {})
    for i,s in enumerate(flow['emails']):
        enabled=s.get('enabled',True)
        if enabled:at+=timedelta(seconds=s['delay_seconds'])
        rows.append({'Step':s.get('name') or 'Email '+str(i+1),'Enabled':enabled,
                     'Planned time (UTC)':at.isoformat() if enabled and not blocked and rules_pass else '—',
                     'Outcome':'Disabled' if not enabled else 'Entry rules not matched' if not rules_pass else 'Exit: unsubscribe / purchase' if blocked else 'Eligible only after fresh checks'})
        if exit_after==i+1:blocked=True
    return rows


def save(store,user,row,definition,name=None,*,rerun=True):
    from crm_campaign_recovery import flush_current
    from crm_automation_ui import changed
    if not flush_current(force=True):return False
    # Flush may save only the current email. Merge that document, while an
    # unrelated concurrent edit must still fail the optimistic revision check.
    expected=row['config']['revision'];editor=st.session_state.get('automation_editor')
    if editor and str(editor['id'])==str(row['id']):
        expected=editor['version']
        for step in definition['emails']:
            if step['step_id']==store.step_id:step['document']=deepcopy(editor['document'])
    store.save_flow(user,row['id'],row['name'] if name is None else name,definition,expected)
    st.session_state.pop('automation_editor',None);changed()
    if rerun:st.rerun(scope='fragment')
    return True


def timing(store,user,row):
    flow=deepcopy(row['config']['draft']);key='timing-'+str(row['id'])+'-'+str(row['config']['revision'])
    st.caption('Initial delay starts at the qualifying trigger. Later delays start at provider acceptance of the preceding enabled email.')
    name=st.text_input('Flow name',display_name(row['name']),max_chars=150,key=key+'name')
    flow['trigger']=st.selectbox('Entry trigger',list(TRIGGERS),index=list(TRIGGERS).index(flow['trigger']),format_func=lambda k:TRIGGERS[k][1],key=key+'trigger')
    st.caption('Start · '+TRIGGERS[flow['trigger']][1]+' · Enter flow')
    flow['reentry_days']=st.selectbox('Re-entry cooldown',[0,7,30,90],index=[0,7,30,90].index(flow['reentry_days']),format_func=lambda d:'Once ever' if d==0 else str(d)+' days',key=key+'reentry')
    if flow['trigger']=='win_back':flow['inactive_days']=st.number_input('Days since last purchase',1,3650,flow.get('inactive_days',180),key=key+'days')
    mandatory=flow['trigger'] in ('abandoned','win_back')
    flow['exit_on_purchase']=st.checkbox('Exit after a new purchase',value=True if mandatory else flow.get('exit_on_purchase',False),disabled=mandatory,key=key+'exit'+flow['trigger'])
    st.caption('Exit · Unsubscribe, suppression or invalid recipient · Always enforced before each email')
    from crm_automation_definition import RULE_FIELDS
    rules=st.data_editor(flow['rules'] or [{'field':'market','condition':'is','value':'AU'}],num_rows='dynamic',key=key+'rules',
        column_config={'field':st.column_config.SelectboxColumn('Field',options=list(RULE_FIELDS)),'condition':st.column_config.SelectboxColumn('Condition',options=['is','at_least']),'value':st.column_config.TextColumn('Value')}, row_height=TABLE_ROW_HEIGHT)
    use_rules=st.checkbox('Apply these entry rules (AND)',bool(flow['rules']),key=key+'use-rules')
    flow['rules']=rules if use_rules else []
    st.warning('Check that Shopify or another marketing platform is not sending the same recovery sequence. External sends are not visible to this send ledger.')
    if st.button('Save flow settings',type='primary',key=key+'save'):
        try:validate(flow);save(store,user,row,flow,name)
        except ValueError as exc:st.error(str(exc))


def test_flow(row):
    key='flow-sim-'+str(row['id'])
    st.caption('Simulation only. No customer emails or enrollment changes. Planned times assume immediate provider acceptance; real deferrals shift following steps.')
    subscribed=st.checkbox('Recipient remains eligible / subscribed',True,key=key+'consent')
    purchased=st.checkbox('Customer has purchased',False,key=key+'purchase')
    country=st.text_input('Simulated country code','AU',max_chars=2,key=key+'country').upper()
    exit_after=st.selectbox('Simulate unsubscribe after email',[None,*range(1,len(row['config']['draft']['emails'])+1)],format_func=lambda n:'No later opt-out' if n is None else 'Email '+str(n),key=key+'after')
    product=st.text_input('Simulated purchased product GID','',key=key+'product')
    currency=st.text_input('Simulated order currency','AUD',max_chars=3,key=key+'currency').upper()
    amount=st.number_input('Simulated order value',min_value=0.,value=0.,key=key+'amount')
    facts={'checkout_country':country,'product_purchased':{product},'order_value':{'currencyCode':currency,'amount':str(amount)}}
    st.dataframe(simulate(row['config']['draft'],subscribed=subscribed,purchased=purchased,customer={'defaultAddress':{'countryCodeV2':country}},event_facts=facts,exit_after=exit_after),hide_index=True,width='stretch', row_height=TABLE_ROW_HEIGHT)
    from crm_automation_publication import preflight
    try:preflight(row,row['config']['revision']);st.success('Sequence validation passed. Publication also checks delivery settings and trigger readiness.')
    except ValueError as exc:st.warning(str(exc))
    st.caption('For an internal email preview, select Edit email and use the existing verified Send test control.')


def activity(store,row,user=None,*,rerun_scope='app'):
    health=store.state('worker_health');checked=date(health.get('checked_at'))
    st.caption('Scheduler · '+('Healthy · '+checked.isoformat() if checked and now()-checked<timedelta(minutes=5) else 'No recent worker heartbeat — check the existing CRM worker'))
    journeys=store.q('''SELECT j.id,j.shopify_customer_id AS customer,j.trigger_shopify_id AS reference,
        CASE WHEN j.status='ACTIVE' THEN j.current_step+1 END AS email,
        CASE WHEN j.status='ACTIVE' THEN COALESCE((SELECT s.due_at FROM crm_marketing_sends s WHERE s.enrollment_id=j.id AND s.step_index=j.current_step AND s.status IN ('PENDING','CLAIMED','SUBMITTING') AND NOT s.test_send LIMIT 1),j.next_due_at) END AS next_due_at,j.status,j.stop_reason,
        (SELECT s.status FROM crm_marketing_sends s WHERE s.enrollment_id=j.id AND NOT s.test_send ORDER BY s.created_at DESC LIMIT 1) AS latest_send
        FROM crm_automation_enrollments j WHERE j.automation_id=%s ORDER BY j.updated_at DESC LIMIT 50''',(row['id'],))
    st.dataframe(journeys,hide_index=True,width='stretch', row_height=TABLE_ROW_HEIGHT)
    if journeys:
        chosen=st.selectbox('View recipient timeline',journeys,format_func=lambda j:str(j['customer'])+' · '+str(j['reference']),key='journey-'+str(row['id']))
        sends=store.q('''SELECT s.id,s.step_index+1 AS email,s.status,s.error_code,s.provider_email_id,s.due_at,s.first_submitted_at,e.event_type,e.occurred_at,
          (SELECT value->>'message' FROM crm_runtime_state WHERE key='checkout-send-error:'||s.id::text) AS error_detail
          FROM crm_marketing_sends s LEFT JOIN crm_delivery_events e ON e.send_id=s.id
          WHERE s.enrollment_id=%s AND NOT s.test_send ORDER BY s.created_at,e.occurred_at''',(chosen['id'],))
        st.dataframe(sends,hide_index=True,width='stretch', row_height=TABLE_ROW_HEIGHT)
        retryable={s['id']:s for s in sends if s['status']=='FAILED' and s['error_code'] in ('provider_rejected','revalidation_unavailable') and not s['provider_email_id']}
        for send_id,send in retryable.items():
            if st.button('Retry rejected email '+str(send['email']),key='flow-retry-'+str(send_id),disabled=user is None):
                try:store.retry_delivery(user,row['id'],send_id);st.success('Queued for fresh eligibility checks. The existing send identity is retained.');st.rerun(scope=rerun_scope)
                except ValueError as exc:st.warning(str(exc))


def builder(store,user,row):
    """Compatibility entry point; there is only one flow management frontend."""
    from crm_flow_page import flow_page
    flow_page(getattr(store,'preview_shop',None),store,user,row)
