"""Small HTML library UI over existing versioned campaign template records."""
from copy import deepcopy
import uuid
import inspect
import streamlit as st
import os_accounts
from crm_campaign_content import new_document, validate_document
from crm_middle_sections import middle_sections, commit_middle
from crm_template_cache import cached
from crm_store import StoreUnavailable

# Keyed fragment reruns are available in the newer supported Streamlit runtime.
# Older supported installs retain native dialog closure without failing imports.
COMPOSER_TARGET='crm_campaign_composer' if 'key' in inspect.signature(st.fragment).parameters else None

def library_rows(store):
    # Flow and legacy delivery templates are not editable campaign-library items.
    return cached(store, ('metadata',), lambda: sorted(store.html_library(metadata=True),key=lambda r:(r['name'].casefold(),str(r['id']))))


def template_html(store,row):
    return cached(store, ('body',str(row['id']),row['version']), lambda:_template_html(store,row))


def _template_html(store,row):
    from crm_html_workspace import html_document
    from crm_middle_sections import render_middle
    if 'document' not in row['content']:
        loaded=store.get('templates',row['id'])
        if not loaded or loaded['version']!=row['version'] or loaded.get('archived_at'):raise ValueError('Template changed. Reload the template list.')
        row=loaded
    doc=html_document(store.template_document(row))
    return render_middle(doc)[0] if doc.get('middle_sections') else doc.get('custom_html','')


def insert_saved_template(store,doc,identity,version):
    row=next((r for r in library_rows(store) if str(r['id'])==str(identity) and r['version']==version),None)
    if row is None:raise ValueError('Template could not be loaded.')
    insert_template(doc,template_html(store,row),row)

def save_template(store,user,name,html,row=None):
    if not isinstance(html,str) or not html.strip():raise ValueError('Enter HTML for this template.')
    if row and (row.get('kind')!='Campaign' or row['content'].get('format')!='campaign_blocks_v1'):raise ValueError('Choose a campaign HTML template.')
    doc=new_document();doc.update(content_mode='HTML',custom_html=html)
    return store.save_design(user,name,doc,row['id'] if row else None,row['version'] if row else None)

def insert_template(doc,html,row):
    proposed=deepcopy(doc);sections=middle_sections(proposed)
    if len(sections)==1 and sections[0]['type']=='html' and not sections[0]['html'].strip():
        sections[0].update(html=html,visible=True)
    else:
        sections.append({'id':uuid.uuid4().hex,'type':'html','visible':True,
            'html_number':max(s.get('html_number',0) for s in sections)+1,'html':html})
    commit_middle(proposed,sections)
    proposed['template_ref']={'id':str(row['id']),'version':row['version'],'name':row['name']}
    proposed['copy_reviewed']=False;validate_document(proposed)
    doc.update(proposed)

def template_dialog():
    # Streamlit's decorator exposes no public close handle. Keep this small adapter
    # isolated: close its native dialog during the keyed composer rerun.
    # On an unsupported runtime we fall back to the documented full-app close.
    try:
        from streamlit.delta_generator_singletons import context_dg_stack
        from streamlit.elements.lib.dialog import Dialog
        return next((dg for dg in reversed(context_dg_stack.get()) if isinstance(dg,Dialog)),None)
    except ImportError:return None


def finish_action(target=None, action=None, dialog=None, clear_keys=()):
    """Widget callback: refresh only the owning composer after a successful action."""
    try:
        if action:action()
    except (ValueError,PermissionError,StoreUnavailable) as exc:
        st.session_state['campaign_template_error']=str(exc)
        return
    st.session_state.pop('campaign_template_error',None)
    # A targeted rerun does not garbage-collect widgets owned by the dialog.
    # Cancel must discard edits, and the next Add template form must start blank.
    for key in clear_keys:st.session_state.pop(key,None)
    if dialog and target:st.session_state['campaign_template_close_dialog']=dialog
    st.rerun(scope=target if dialog and target else 'app')


def action_error():
    if st.session_state.get('campaign_template_error'):
        st.error(st.session_state.pop('campaign_template_error'))


@st.dialog('HTML template',width='small')
def edit_template(store,user,row=None,target=None):
    dialog=template_dialog()
    try:
        with st.spinner('Loading template...'):
            source=template_html(store,row) if row else ''
    except (ValueError,StoreUnavailable):st.error('Template could not be loaded.');return
    identity=str(row['id'])+'_'+str(row['version']) if row else 'new'
    name_key='library_name_'+identity;html_key='library_html_'+identity
    def save():
        save_template(store,user,st.session_state[name_key],st.session_state[html_key],row)
    with st.form('library_edit'):
        st.text_input('Template name',row['name'] if row else '',max_chars=150,key=name_key)
        st.text_area('HTML',source,height=260,key=html_key)
        a,b=st.columns(2)
        a.form_submit_button('Cancel',on_click=finish_action,args=(target,None,dialog,(name_key,html_key)))
        b.form_submit_button('Save template',type='primary',on_click=finish_action,args=(target,save,dialog,(name_key,html_key)))
    action_error()


@st.dialog('Delete template',width='small')
def delete_template(store,user,row,target=None):
    dialog=template_dialog()
    st.write('Delete “'+row['name']+'”?')
    a,b=st.columns(2)
    a.button('Cancel',on_click=finish_action,args=(target,None,dialog))
    b.button('Delete',type='primary',on_click=finish_action,
             args=(target,lambda:store.archive_design(user,row['id'],row['version']),dialog))
    action_error()


def library(store,user,doc,target=None):
    if st.session_state.get('campaign_template_notice'):
        st.toast(st.session_state.pop('campaign_template_notice'))
    manage=os_accounts.can_access_page(user,'crm_templates_manage')
    if manage and st.button('+ Add template'):edit_template(store,user,target=target)
    try:rows=library_rows(store)
    except StoreUnavailable:
        st.caption('Templates temporarily unavailable. Campaign editing remains available.');return
    if not rows:st.caption('No saved templates yet.')
    def use(row):
        try:insert_saved_template(store,doc,row['id'],row['version'])
        except (ValueError,StoreUnavailable):
            st.session_state['campaign_template_error']='Template could not be loaded.'
            return
        st.session_state['campaign_template_notice']='Template added to Editor'
        st.rerun(scope=target or 'app')
    action_error()
    for row in rows:
        with st.container(key='library_'+str(row['id'])):
            st.text(row['name'])
            with st.container(horizontal=True,gap='small'):
                st.button('Use',key='use_'+str(row['id']),on_click=use,args=(row,))
                if manage:
                    if st.button('Edit',key='edit_'+str(row['id'])):edit_template(store,user,row,target)
                    if st.button('',icon=':material/delete:',help='Delete template',key='delete_'+str(row['id'])):delete_template(store,user,row,target)
