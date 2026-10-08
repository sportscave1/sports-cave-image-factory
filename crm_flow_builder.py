"""Sequence controls around the existing automation store and email composer."""
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
    if not flush_current(force=True):return
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


def step_submit(store,user,row,sid,prefix,action):
    """Form callbacks commit before the dialog re-reads its optimistic revision."""
    from crm_store import StoreUnavailable
    try:
        definition=deepcopy(row['config']['draft'])
        if action=='delete':
            if not st.session_state.get(prefix+'confirm'):raise ValueError('Confirm deletion first. Published histories are retained.')
            definition=edit_sequence(definition,sid,'delete')
        else:
            step=next(s for s in definition['emails'] if s['step_id']==sid)
            step.update(name=st.session_state[prefix+'name'],enabled=st.session_state[prefix+'enabled'])
        save(store,user,row,definition,rerun=False)
    except (ValueError,PermissionError,StoreUnavailable) as exc:
        st.session_state['flow_builder_error']=str(exc) if not isinstance(exc,StoreUnavailable) else 'Storage temporarily unavailable. Retry saving.'


def sequence(store,user,row):
    flow=row['config']['draft'];key='builder-'+str(row['id'])+'-'+str(row['config']['revision'])
    st.caption('TRIGGER · '+TRIGGERS[flow['trigger']][1])
    for i,s in enumerate(flow['emails']):
        amount,unit=delay_controls(s['delay_seconds']);sid=s['step_id'];prefix=key+sid
        st.caption('↓ Wait '+str(amount)+' '+(unit.lower().rstrip('s') if amount==1 else unit.lower())+(' after the previous enabled email' if i else ' after the trigger'))
        with st.container(border=True,key='flow-card-'+sid):
            title,enabled,edit=st.columns([5,1,1])
            title.markdown('**'+(s.get('name') or 'Email '+str(i+1))+'**')
            title.caption(s['document']['content']['subject'] or 'Add a subject in the email editor')
            enabled.caption('Enabled' if s.get('enabled',True) else 'Disabled')
            if edit.button('Edit email',key=prefix+'edit'):
                from crm_campaign_recovery import flush_current
                if flush_current(force=True):
                    st.session_state['automation_step']=sid;st.session_state.pop('automation_editor',None)
                    st.session_state['automation_composing']=True;st.rerun(scope='fragment')
            with st.expander('Step settings'):
                with st.form(prefix+'settings-form'):
                    name=st.text_input('Email name',s.get('name') or 'Email '+str(i+1),max_chars=150,key=prefix+'name')
                    on=st.checkbox('Enable this email',s.get('enabled',True),key=prefix+'enabled')
                    st.form_submit_button('Save step',on_click=step_submit,args=(store,user,row,sid,prefix,'save'))
                cols=st.columns(3)
                for col,label,action,disabled in ((cols[0],'Move up','up',i==0),(cols[1],'Move down','down',i==len(flow['emails'])-1),(cols[2],'Duplicate','duplicate',False)):
                    if col.button(label,key=prefix+action,disabled=disabled):save(store,user,row,edit_sequence(flow,sid,action))
                with st.form(prefix+'delete-form'):
                    confirmed=st.checkbox('Confirm delete email from this draft',key=prefix+'confirm')
                    st.form_submit_button('Delete email',disabled=len(flow['emails'])==1,on_click=step_submit,args=(store,user,row,sid,prefix,'delete'))
    if st.button('+ Add Email',key=key+'add'):
        definition=deepcopy(flow);definition['emails'].append(email_step(delay_seconds=86400));save(store,user,row,definition)
    st.caption('Existing enrollments retain their published sequence. Draft changes take effect for new enrollments after publishing.')


def timing(store,user,row):
    flow=deepcopy(row['config']['draft']);key='timing-'+str(row['id'])+'-'+str(row['config']['revision'])
    st.caption('Initial delay starts at the qualifying trigger. Later delays start at provider acceptance of the preceding enabled email.')
    name=st.text_input('Flow name',display_name(row['name']),max_chars=150,key=key+'name')
    flow['trigger']=st.selectbox('Entry trigger',list(TRIGGERS),index=list(TRIGGERS).index(flow['trigger']),format_func=lambda k:TRIGGERS[k][1],key=key+'trigger')
    st.caption('Start · '+TRIGGERS[flow['trigger']][1]+' · Enter flow')
    st.caption('Step · Trigger / Delay · Action / Status · Edit')
    for i,s in enumerate(flow['emails']):
        columns=st.columns([2,2,1,2,1]);columns[0].write(s.get('name') or 'Email '+str(i+1))
        amount,unit=delay_controls(s['delay_seconds'])
        value=columns[1].number_input('Wait',0,525600,amount,key=key+s['step_id']+'delay')
        units=columns[2].selectbox('Unit',['Minutes','Hours','Days'],index=['Minutes','Hours','Days'].index(unit),key=key+s['step_id']+'unit')
        if (value,units)!=(amount,unit):s['delay_seconds']=int(value)*{'Minutes':60,'Hours':3600,'Days':86400}[units]
        columns[3].caption('Send email · '+('Enabled' if s.get('enabled',True) else 'Disabled'))
        if columns[4].button('Edit',key=key+s['step_id']+'edit'):
            st.session_state['automation_step']=s['step_id'];st.session_state['automation_composing']=True
            save(store,user,row,flow,name)
    flow['reentry_days']=st.selectbox('Re-entry cooldown',[0,7,30,90],index=[0,7,30,90].index(flow['reentry_days']),format_func=lambda d:'Once ever' if d==0 else str(d)+' days',key=key+'reentry')
    if flow['trigger']=='win_back':flow['inactive_days']=st.number_input('Days since last purchase',1,3650,flow.get('inactive_days',180),key=key+'days')
    mandatory=flow['trigger'] in ('abandoned','win_back')
    flow['exit_on_purchase']=st.checkbox('Exit after a new purchase',value=True if mandatory else flow.get('exit_on_purchase',False),disabled=mandatory,key=key+'exit'+flow['trigger'])
    st.caption('Exit · Unsubscribe, suppression or invalid recipient · Always enforced before each email')
    from crm_automation_definition import RULE_FIELDS
    rules=st.data_editor(flow['rules'] or [{'field':'market','condition':'is','value':'AU'}],num_rows='dynamic',key=key+'rules',
        column_config={'field':st.column_config.SelectboxColumn('Field',options=list(RULE_FIELDS)),'condition':st.column_config.SelectboxColumn('Condition',options=['is','at_least']),'value':st.column_config.TextColumn('Value')})
    use_rules=st.checkbox('Apply these entry rules (AND)',bool(flow['rules']),key=key+'use-rules')
    flow['rules']=rules if use_rules else []
    st.warning('Check that Shopify or another marketing platform is not sending the same recovery sequence. External sends are not visible to this send ledger.')
    if st.button('Save timing and rules',type='primary',key=key+'save') or st.session_state.pop('flow-save-requested',False):
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
    st.dataframe(simulate(row['config']['draft'],subscribed=subscribed,purchased=purchased,customer={'defaultAddress':{'countryCodeV2':country}},event_facts=facts,exit_after=exit_after),hide_index=True,width='stretch')
    from crm_automation_publication import preflight
    try:preflight(row,row['config']['revision']);st.success('Sequence validation passed. Publication also checks delivery settings and trigger readiness.')
    except ValueError as exc:st.warning(str(exc))
    st.caption('For an internal email preview, select Edit email and use the existing verified Send test control.')


def activity(store,row,user=None):
    from crm_automation_home_data import step_metrics
    metrics=step_metrics(store,row['id']);names={s['step_id']:s.get('name') or 'Email '+str(i+1) for i,s in enumerate(row['config']['draft']['emails'])}
    recorded={r['step_id'] for r in metrics}
    metrics+= [dict(step_id=sid,**{k:0 for k in ('sent','queued','failed','skipped','delivered','opened','clicked','bounced','orders')}) for sid in names if sid not in recorded]
    schedule={s['step_id']:s['delay_seconds'] for s in row.get('steps',[])}
    st.dataframe([{'Email':names.get(r['step_id'],'Previous version email'),**{k:v for k,v in r.items() if k!='step_id'},
                  'Delivery %':round(100*r['delivered']/r['sent'],1) if r['sent'] else None,
                  'Published delay (seconds)':schedule.get(r['step_id'])} for r in metrics],hide_index=True,width='stretch')
    from crm_automation_analytics import revenue
    from crm_automation_home import money
    entered=store.q('SELECT count(*) n FROM crm_automation_enrollments WHERE automation_id=%s',(row['id'],),True)['n']
    st.caption(str(entered)+' entered · '+str(sum(r['sent'] for r in metrics))+' sent · '+str(sum(r['queued'] for r in metrics))+' queued · '+str(sum(r['orders'] for r in metrics))+' conversions')
    st.caption('Attributed revenue · '+money(revenue(store,(date(row.get('created_at')) or now()-timedelta(days=36500),now()),row['id'])['revenue'])+' · Per-email unsubscribes unavailable where the source does not attribute an opt-out to a send.')
    st.caption('Sent means provider acceptance. Delivered, opens and clicks require recorded provider events. Removed steps retain their history.')
    health=store.state('worker_health');checked=date(health.get('checked_at'))
    st.caption('Scheduler · '+('Healthy · '+checked.isoformat() if checked and now()-checked<timedelta(minutes=5) else 'No recent worker heartbeat — check the existing CRM worker'))
    journeys=store.q('''SELECT j.id,j.shopify_customer_id AS customer,j.trigger_shopify_id AS reference,
        CASE WHEN j.status='ACTIVE' THEN j.current_step+1 END AS email,
        CASE WHEN j.status='ACTIVE' THEN COALESCE((SELECT s.due_at FROM crm_marketing_sends s WHERE s.enrollment_id=j.id AND s.step_index=j.current_step AND s.status IN ('PENDING','CLAIMED','SUBMITTING') AND NOT s.test_send LIMIT 1),j.next_due_at) END AS next_due_at,j.status,j.stop_reason,
        (SELECT s.status FROM crm_marketing_sends s WHERE s.enrollment_id=j.id AND NOT s.test_send ORDER BY s.created_at DESC LIMIT 1) AS latest_send
        FROM crm_automation_enrollments j WHERE j.automation_id=%s ORDER BY j.updated_at DESC LIMIT 50''',(row['id'],))
    st.dataframe(journeys,hide_index=True,width='stretch')
    if journeys:
        chosen=st.selectbox('View recipient timeline',journeys,format_func=lambda j:str(j['customer'])+' · '+str(j['reference']),key='journey-'+str(row['id']))
        sends=store.q('''SELECT s.id,s.step_index+1 AS email,s.status,s.error_code,s.provider_email_id,s.due_at,s.first_submitted_at,e.event_type,e.occurred_at,
          (SELECT value->>'message' FROM crm_runtime_state WHERE key='checkout-send-error:'||s.id::text) AS error_detail
          FROM crm_marketing_sends s LEFT JOIN crm_delivery_events e ON e.send_id=s.id
          WHERE s.enrollment_id=%s AND NOT s.test_send ORDER BY s.created_at,e.occurred_at''',(chosen['id'],))
        st.dataframe(sends,hide_index=True,width='stretch')
        retryable={s['id']:s for s in sends if s['status']=='FAILED' and s['error_code'] in ('provider_rejected','revalidation_unavailable') and not s['provider_email_id']}
        for send_id,send in retryable.items():
            if st.button('Retry rejected email '+str(send['email']),key='flow-retry-'+str(send_id),disabled=user is None):
                try:store.retry_delivery(user,row['id'],send_id);st.success('Queued for fresh eligibility checks. The existing send identity is retained.');st.rerun()
                except ValueError as exc:st.warning(str(exc))


def builder(store,user,row):
    from crm_automation_ui import changed
    from crm_automation_definition import status
    identity=row['id'];key='flow-top-'+str(identity)
    error=st.session_state.pop('flow_builder_error',None)
    if error:st.warning(error)
    st.html('''<style>.st-key-crm-automation-editor [data-testid="stVerticalBlock"]{gap:8px}
      .st-key-crm-automation-editor button[kind="primary"]{background:#c8a346!important;border-color:#b99436!important;color:#141414!important}
      .st-key-crm-automation-editor button[role="tab"][aria-selected="true"]{color:#947021!important}
      .st-key-crm-automation-editor [data-baseweb="tab-highlight"]{background:#c8a346!important}
      @media(max-width:760px){.st-key-flow-builder-actions [data-testid="stHorizontalBlock"]{flex-wrap:wrap!important;gap:6px!important}
      .st-key-flow-builder-actions [data-testid="stColumn"]{flex:1 1 100px!important;width:auto!important;min-width:0!important}}
      .st-key-crm-automation-editor h3{font-size:20px;padding:0}</style>''')
    st.subheader(display_name(row['name']))
    st.caption({'ACTIVE':'Live','DRAFT':'Draft','PAUSED':'Paused','ARCHIVED':'Archived'}[status(row)]+' · Published version '+str(row['config']['published_version']))
    with st.container(key='flow-builder-actions'):controls=st.columns(5)
    if controls[0].button('Close',key=key+'close'):
        from crm_campaign_recovery import flush_current
        if flush_current(force=True):
            st.session_state.pop('automation_selected',None);st.query_params.pop('automation',None);st.rerun()
    archived=status(row)=='ARCHIVED'
    if controls[1].button('Save Draft',disabled=archived,key=key+'save'):
        st.session_state['flow-save-requested']=True
    if controls[2].button('Test Flow',key=key+'test'):st.session_state[key+'simulation']=not st.session_state.get(key+'simulation',False)
    if controls[3].button('Publish',type='primary',disabled=archived,key=key+'publish'):st.session_state[key+'publish-review']=True
    if row['status'] in ('ACTIVE','PAUSED') and not archived:
        action='pause' if row['status']=='ACTIVE' else 'resume'
        if controls[4].button(action.title(),key=key+action):store.lifecycle(user,identity,action);changed();st.rerun()
    if st.session_state.get(key+'publish-review'):
        st.info('Publish this saved draft for new enrollments. Existing recipients retain their original sequence; historical checkouts are not backfilled.')
        confirm,cancel=st.columns(2)
        if cancel.button('Cancel publication',key=key+'cancel'):st.session_state[key+'publish-review']=False;st.rerun()
        if confirm.button('Confirm publish',key=key+'confirm'):
            try:
                job=store.request_publish(user,identity,row['config']['revision'])
                from crm_automation_home import accepted_publication
                accepted_publication(job);changed();st.session_state[key+'publish-review']=False;st.rerun()
            except (ValueError,PermissionError) as exc:st.error(str(exc))
    publication=row['config'].get('publication',{})
    if publication.get('state')=='PUBLISHING':
        st.info('Publication queued for background validation.')
        from crm_automation_analytics_ui import arm
        arm(key+'publication',2)
    if publication.get('state')=='FAILED':st.error(publication.get('error') or 'Publication failed')
    if st.session_state.get(key+'simulation'):test_flow(row)
    # Streamlit renders only the open tab, so activity SQL is not part of editing.
    tabs=st.tabs(['Flow Builder','Triggers & Timing','Activity'],on_change='rerun',key=key+'tabs')
    for index,(tab,render) in enumerate(zip(tabs,(sequence,timing,lambda store,user,row:activity(store,row,user)))):
        if tab.open:
            with tab:
                if archived and index!=2:
                    st.caption('Archived flow: history is retained.')
                else:render(store,user,row)
    if st.session_state.pop('flow-save-requested',False):
        st.toast('Sequence changes are saved. Publish when ready for new enrollments.')
