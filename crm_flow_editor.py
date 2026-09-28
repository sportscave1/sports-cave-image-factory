"""Inactive flow email authoring. Fork shared templates; never activates or sends a flow."""
from copy import deepcopy
import json
import uuid
import streamlit as st
import os_accounts
from crm_campaign_store import CampaignStore
from crm_navigation import require
from crm_campaign_content import validate_document,MARKETS
from crm_html_workspace import html_document,canvas,workspace_styles
from crm_store import StoreUnavailable


def save_flow_email(store,user,flow,index,doc,template_version):
    require(user,'crm_automations_manage');require(user,'crm_templates_manage');validate_document(doc)
    with store.db() as conn:
        current=conn.execute('SELECT * FROM crm_automations WHERE id=%s FOR UPDATE',(flow['id'],)).fetchone()
        if not current or current['status'] not in ('DRAFT','PAUSED') or str(current['updated_at'])!=str(flow['updated_at']):
            raise ValueError('Flow changed or is not inactive. Reload before editing.')
        if type(index) is not int or not 0<=index<len(current['steps']) or current['steps'][index]['type']!='send':raise ValueError('Choose an existing flow email.')
        reference=current['steps'][index]['template']
        template=conn.execute('SELECT * FROM crm_templates WHERE template_key=%s FOR UPDATE',(reference,)).fetchone()
        if not template or template['version']!=template_version:raise ValueError('Email changed elsewhere. Reload before editing.')
        content={'format':'campaign_blocks_v1','document':deepcopy(doc)}
        # Always fork: no other flow/campaign/template history changes behind the user.
        new_key='flow_email_'+uuid.uuid4().hex
        saved=conn.execute('INSERT INTO crm_templates(template_key,name,kind,content) VALUES(%s,%s,%s,%s::jsonb) RETURNING *',
            (new_key,flow['name']+' · email '+str(index+1),template['kind'],json.dumps(content))).fetchone()
        conn.execute('INSERT INTO crm_template_versions(template_id,version,content) VALUES(%s,%s,%s::jsonb)',(saved['id'],saved['version'],json.dumps(content)))
        steps=deepcopy(current['steps']);steps[index]['template']=new_key
        updated=conn.execute('UPDATE crm_automations SET steps=%s::jsonb,updated_at=now() WHERE id=%s RETURNING *',(json.dumps(steps),flow['id'])).fetchone()
    from crm_service import audit
    audit('flow_email_saved',flow['id'],user)
    return updated,saved


def flow_workspace(shop,store,actions):
    from crm_campaign_page import test_panel,perform_test
    workspace_styles();drafts=CampaignStore(store.connect)
    with st.spinner('Loading automations…'):
        rows=store.list('automations')
    if not rows:
        st.info('No draft flows yet.')
        if st.button('Initialize draft library'):actions.seed();st.rerun()
        return
    st.caption('● Marketing delivery OFF · Automations inactive')
    selectors=st.columns([3,1])
    row=selectors[0].selectbox('Flow',rows,format_func=lambda r:r['name'])
    sends=[i for i,s in enumerate(row['steps']) if s['type']=='send']
    if not sends:st.info('This flow has no email step.');return
    index=selectors[1].selectbox('Email',sends,format_func=lambda i:'Email '+str(sends.index(i)+1))
    identity=str(row['id'])+':'+str(index)
    record_key='flow_html_'+identity
    if record_key not in st.session_state:
        with st.spinner('Loading automation email…'):
            template=drafts.q('SELECT * FROM crm_templates WHERE template_key=%s',(row['steps'][index]['template'],),True)
            if not template:st.warning('The selected email template is unavailable.');return
            st.session_state[record_key]={'document':html_document(drafts.template_document(template)),'saved':None,'version':template['version'],'flow':deepcopy(row)}
    state=st.session_state[record_key]
    key=record_key+state.setdefault('widget_version',uuid.uuid4().hex)
    if state['saved'] is None:state['saved']=deepcopy(state['document'])
    doc=state['document'];c=doc['content']
    name,subject,preview=st.columns([2,3,3]);name.caption(row['name']+' · '+row['status'])
    c['subject']=subject.text_input('Subject',c['subject'],key=key+'subject')
    c['preheader']=preview.text_input('Preview text',c['preheader'],key=key+'preheader')
    editable=os_accounts.can_access_page(actions.user,'crm_templates_manage') and row['status'] in ('DRAFT','PAUSED')
    with st.container(horizontal=True):
        save=st.button('Save draft',disabled=not editable)
        if st.button('Preview'):st.session_state[key+'view']='Preview'
        if st.button('Send test',disabled=not os_accounts.is_admin(actions.user)):st.session_state[key+'show_test']=True
    request=None;test_editor=None
    with st.container(horizontal=True,key='crm-email-layout'):
        with st.container(width=250,height=540,border=False,key='crm-email-controls'):
            with st.expander('Flow details'):
                st.caption('Inactive email authoring. Existing enrollments retain their version snapshots.')
                st.caption('Unsaved changes' if doc!=state['saved'] else 'Saved')
            with st.expander('Trigger'):
                st.write(row['trigger_type']);st.json(row['config'])
                if row['trigger_type']=='win_back':
                    days=st.number_input('Days since last purchase',1,3650,int(row['config'].get('days',180)))
                    if st.button('Save trigger',disabled=not editable or doc!=state['saved']):
                        config=deepcopy(row['config']);config['days']=days
                        actions.automation(row,row['steps'],config,row['status']);st.session_state.pop(record_key,None);st.rerun()
            with st.expander('Audience'):
                st.caption('Shopify SUBSCRIBED only. Existing trigger, suppression, dedupe and frequency checks remain mandatory. Flow activation is disabled.')
            with st.expander('Email settings'):
                doc['market']=st.selectbox('Market',MARKETS,index=MARKETS.index(doc['market']),key=key+'market')
            with st.expander('Test',expanded=st.session_state.get(key+'show_test',False)):
                st.caption('Internal test only. A separate test draft preserves the reviewed email snapshot.')
                import hashlib
                review_hash=hashlib.sha256(json.dumps({k:v for k,v in doc.items() if k!='copy_reviewed'},sort_keys=True).encode()).hexdigest()[:16]
                reviewed=st.checkbox('Copy and subject reviewed',doc['copy_reviewed'],key=key+'review'+review_hash)
                doc['copy_reviewed']=reviewed
                prepare=st.button('Prepare internal test',disabled=not os_accounts.is_admin(actions.user) or doc!=state['saved'])
                test_editor=st.session_state.get(key+'test_editor')
                if test_editor:
                    request=test_panel(drafts,actions.user,test_editor,key+'test',drafts.render_settings(),pending=False)
            with st.expander('More'):
                st.caption('Email versions are retained as template snapshots. Saving changes only this flow email reference.')
                discard=st.checkbox('Discard unsaved email changes',key=key+'discard') if doc!=state['saved'] else True
                if st.button('Reload saved email',disabled=not discard):
                    st.session_state.pop(record_key,None);st.rerun()
                with st.expander('Workflow configuration'):
                    # Existing step editing stays available but no longer occupies the canvas.
                    from crm_page import legacy_flow_configuration
                    legacy_flow_configuration(store,actions,row)
        with st.container(width='stretch'):canvas(doc,drafts.render_settings(),key)
    if save:
        try:
            with st.spinner('Saving draft…'):
                flow,saved=save_flow_email(drafts,actions.user,state['flow'],index,doc,state['version'])
            state.update(flow=flow,version=saved['version'],saved=deepcopy(doc));st.toast('Flow email draft saved');st.rerun()
        except (ValueError,StoreUnavailable,PermissionError) as exc:st.warning(str(exc))
    if prepare:
        if doc!=state['saved']:st.warning('Save reviewed content first.')
        else:
            st.session_state[key+'test_editor']=drafts.save(actions.user,'Flow internal test · '+row['name'],doc);st.rerun()
    if request:
        if doc!=state['saved'] or doc!=test_editor['document']:st.warning('Save and prepare the current email before testing.')
        else:perform_test(drafts,actions.user,test_editor,key+'test',request)
