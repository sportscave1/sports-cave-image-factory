"""Small HTML library UI over existing versioned campaign template records."""
from copy import deepcopy
import uuid
import streamlit as st
import os_accounts
from crm_campaign_content import new_document, validate_document
from crm_middle_sections import middle_sections, commit_middle

def library_rows(store):
    # Flow and legacy delivery templates are not editable campaign-library items.
    return store.html_library(metadata=True)


def template_html(store,row):
    from crm_html_workspace import html_document
    from crm_middle_sections import render_middle
    if 'document' not in row['content']:
        loaded=store.get('templates',row['id'])
        if not loaded or loaded['version']!=row['version'] or loaded.get('archived_at'):raise ValueError('Template changed. Reload the template list.')
        row=loaded
    doc=html_document(store.template_document(row))
    return render_middle(doc)[0] if doc.get('middle_sections') else doc.get('custom_html','')

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

@st.dialog('HTML template',width='small')
def edit_template(store,user,row=None):
    with st.form('library_edit'):
        name=st.text_input('Template name',row['name'] if row else '',max_chars=150)
        html=st.text_area('HTML',template_html(store,row) if row else '',height=260)
        a,b=st.columns(2);cancel=a.form_submit_button('Cancel');save=b.form_submit_button('Save template',type='primary')
    if cancel:st.rerun()
    if save:
        try:save_template(store,user,name,html,row);st.rerun()
        except (ValueError,PermissionError) as exc:st.error(str(exc))

@st.dialog('Delete template',width='small')
def delete_template(store,user,row):
    st.write('Delete “'+row['name']+'”?')
    a,b=st.columns(2)
    if a.button('Cancel'):st.rerun()
    if b.button('Delete',type='primary'):
        try:store.archive_design(user,row['id'],row['version']);st.rerun()
        except (ValueError,PermissionError) as exc:st.error(str(exc))

@st.dialog('Choose template',width='small')
def picker(store,doc):
    rows=library_rows(store)
    if not rows:st.caption('Create an HTML template in the Templates tab.');return
    row=st.selectbox('Choose template',rows,format_func=lambda r:r['name'])
    if st.button('Add template',type='primary'):
        try:insert_template(doc,template_html(store,row),row);st.rerun()
        except ValueError as exc:st.error(str(exc))

def library(store,user,doc):
    manage=os_accounts.can_access_page(user,'crm_templates_manage')
    if manage and st.button('+ Add template'):edit_template(store,user)
    rows=library_rows(store)
    if not rows:st.caption('No saved templates yet.')
    for row in rows:
        with st.container(key='library_'+str(row['id'])):
            st.text(row['name'])
            with st.container(horizontal=True,gap='small'):
                if st.button('Use',key='use_'+str(row['id'])):
                    try:insert_template(doc,template_html(store,row),row);st.toast('Template added to HTML');st.rerun()
                    except ValueError as exc:st.error(str(exc))
                if manage:
                    if st.button('Edit',key='edit_'+str(row['id'])):edit_template(store,user,row)
                    if st.button('',icon=':material/delete:',help='Delete template',key='delete_'+str(row['id'])):delete_template(store,user,row)
