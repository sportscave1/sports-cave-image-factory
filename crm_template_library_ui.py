"""Lazy, fragment-local library and compact inline source editors."""
from copy import deepcopy
from html import escape
import streamlit as st
import os_accounts
from crm_store import StoreUnavailable
from crm_template_library import GROUPS,group_for,rows,source,save_builtin


def select_template(store,row,cfg):
    try:
        if row and row.get('default') in ('header','footer'):
            snapshot=store.email_default(row['default'],cfg)
            data=dict(row=row,html=snapshot['value']['html'],version=snapshot['version'])
        elif row and row.get('default')=='checkout':
            from crm_checkout_template import load
            snapshot=load(store);data=dict(row=row,html=snapshot['html'],version=snapshot['revision'])
        else:
            from crm_campaign_library import template_document
            data=dict(row=row,html=source(store,row) if row else '',document=template_document(store,row) if row and not row.get('builtin') else None)
        st.session_state['compact_template_edit']=data
        st.session_state['compact_template_generation']=st.session_state.get('compact_template_generation',0)+1
    except (ValueError,StoreUnavailable) as exc:st.session_state['compact_template_error']=str(exc)


def close():st.session_state.pop('compact_template_edit',None)


def editor(store,user):
    data=st.session_state['compact_template_edit'];row=data['row'];default=row.get('default') if row else None
    key='compact-template-'+str(st.session_state.get('compact_template_generation',0))
    with st.form(key):
        name=st.text_input('Template name',row['name'] if row else '',disabled=bool(default),max_chars=150)
        group=st.selectbox('Group',GROUPS,index=GROUPS.index(group_for(row)) if row and not default else 0 if default else 6,disabled=bool(default))
        document=deepcopy(data.get('document'))
        if document and document.get('middle_sections'):
            for part in document['middle_sections']:
                if 'html' in part:
                    value=st.text_area((part.get('name') or part['type'].title())+' HTML'+(' (hidden)' if not part['visible'] else ''),part['html'],height=220,key=key+part['id'])
                    if value!=part['html']:part.update(html=value,css_version=1)
        else:html=st.text_area('HTML source',data['html'],height=260)
        a,b=st.columns(2)
        a.form_submit_button('Cancel',on_click=close)
        saved=b.form_submit_button('Save template',type='primary')
    if saved:
        try:
            if default and not html.strip():raise ValueError('Default templates cannot be empty.')
            if default in ('header','footer'):store.save_email_default(user,default,html,data['version'])
            elif default=='checkout':
                from crm_checkout_template import save
                save(store,user,html,data['version'])
            elif row and row.get('builtin'):save_builtin(store,user,row,name,html,group)
            else:
                from crm_campaign_content import new_document
                from crm_middle_sections import commit_middle
                if document and document.get('middle_sections'):commit_middle(document,document['middle_sections'])
                else:document=new_document();document.update(content_mode='HTML',custom_html=html)
                store.save_design(user,name,document,row['id'] if row else None,row['version'] if row else None,library_group=group)
            close();st.toast('Template saved');st.rerun(scope='fragment')
        except (ValueError,PermissionError,StoreUnavailable) as exc:st.error(str(exc))


def toggle(group):
    state=st.session_state.setdefault('compact_template_groups',{})
    state[group]=not state.get(group,False)


@st.fragment
def library(store,user,cfg):
    with st.container(key='crm-compact-library'):
        with st.container(horizontal=True,vertical_alignment='center',key='compact-library-heading'):
            st.markdown('**Templates**')
            st.button('Add template',icon=':material/add:',help='Add template',key='compact-template-add',disabled=not os_accounts.can_access_page(user,'crm_templates_manage'),on_click=select_template,args=(store,None,cfg))
        if st.session_state.get('compact_template_error'):st.error(st.session_state.pop('compact_template_error'))
        if 'compact_template_edit' in st.session_state:editor(store,user);return
        try:available=rows(store)
        except StoreUnavailable:st.caption('Templates temporarily unavailable.');return
        defaults=[dict(id='default-'+kind,name=label,default=kind) for kind,label in [('header','Header'),('footer','Footer'),('checkout','Abandoned Checkout')]]
        groups={group:[] for group in GROUPS};groups['Defaults']=defaults
        for row in available:groups[group_for(row)].append(row)
        opened=st.session_state.get('compact_template_groups',{})
        for group,items in groups.items():
            if not items:continue
            st.button(group+'  ·  '+str(len(items)),icon=':material/keyboard_arrow_down:' if opened.get(group) else ':material/keyboard_arrow_right:',key='compact-group-'+group,on_click=toggle,args=(group,),width='stretch')
            if not opened.get(group):continue
            for row in items:
                with st.container(horizontal=True,vertical_alignment='center',key='compact-row-'+str(row['id'])):
                    st.html('<span class="compact-template-name" title="'+escape(row['name'],quote=True)+'">'+escape(row['name'])+'</span>')
                    allowed=os_accounts.is_admin(user) if row.get('default') in ('header','footer') else os_accounts.can_access_page(user,'crm_automations_manage' if row.get('default') else 'crm_templates_manage')
                    st.button('Edit '+row['name'],icon=':material/edit:',help='Edit '+row['name'],key='compact-edit-'+str(row['id']),disabled=not allowed,on_click=select_template,args=(store,row,cfg))
