"""Compact brand-template controls, confined to Campaign authoring/settings."""
from copy import deepcopy
import streamlit as st
import streamlit.components.v1 as components
import os_accounts
from crm_store import StoreUnavailable
from crm_campaign_sections import section_defaults
from crm_campaign_content import new_document, render_campaign


def template_label(row):
    return row['name']+(' (built-in)' if row.get('builtin') else '')


def section_picker(store,user,kind,source_key,key,cfg,source):
    rows=store.section_templates(kind,cfg);by_id={str(r['id']):r for r in rows}
    if key+'template' not in st.session_state:
        st.session_state[key+'template']=next((i for i,r in by_id.items() if r['content']['html']==source),None)
    elif st.session_state[key+'template'] not in by_id:
        st.session_state[key+'template']=None
    def load():
        selected=st.session_state.get(key+'template')
        # A stale browser label may arrive after options are renamed/removed.
        # It must never overwrite a campaign source or crash the rerun.
        if selected in by_id:st.session_state[source_key]=by_id[selected]['content']['html']
    st.selectbox(kind.title()+' template',[None,*by_id],
        format_func=lambda identity:'Current campaign HTML' if identity is None else template_label(by_id[identity]),
        key=key+'template',on_change=load)


def save_section_control(store,user,kind,source,key):
    if not os_accounts.can_access_page(user,'crm_templates_manage'):return
    with st.popover('Save as '+kind+' template'):
        name=st.text_input('Template name',key=key+'template_name',max_chars=150)
        default=st.checkbox('Make default',key=key+'make_default') if os_accounts.is_admin(user) else False
        if st.button('Save '+kind+' template',key=key+'save_template'):
            try:
                store.save_section_template(user,kind,name,source,make_default=default)
                st.toast(kind.title()+' template saved');st.rerun()
            except (ValueError,PermissionError,StoreUnavailable) as exc:st.error(str(exc))


def brand_templates_settings(store,user):
    st.markdown('#### Email brand templates')
    st.caption('New campaigns inherit defaults. Saved campaigns keep their own HTML.')
    cfg=store.render_settings()
    for kind in ('header','footer'):
        rows=store.section_templates(kind,cfg);by_id={str(r['id']):r for r in rows}
        current=next(str(r['id']) for r in rows if r['is_default'])
        select_key='brand_default_'+kind
        if st.session_state.get(select_key) not in by_id:st.session_state[select_key]=current
        selected=st.selectbox('Default '+kind.title(),list(by_id),format_func=lambda i,choices=by_id:template_label(choices[i]),key=select_key)
        row=by_id[selected]
        with st.container(horizontal=True):
            if st.button('Use as default',key=kind+'_default',disabled=selected==current):
                store.set_section_default(user,kind,selected);st.toast('Default '+kind+' updated');st.rerun()
            if st.button('Edit',key=kind+'_edit'):
                st.session_state['brand_edit']=deepcopy(row)
                for widget in ('brand_edit_name','brand_edit_source','brand_overwrite','brand_delete_confirm'):st.session_state.pop(widget,None)
    edit=st.session_state.get('brand_edit')
    if not edit:return
    kind=edit['content']['section'];builtin=edit.get('builtin',False)
    st.markdown('**Edit '+kind.title()+'**')
    name=st.text_input('Template name',edit['name'],key='brand_edit_name',max_chars=150)
    source=st.text_area(kind.title()+' template HTML',edit['content']['html'],height=230,key='brand_edit_source')
    with st.expander('Preview'):
        doc=new_document();doc.update(content_mode='HTML',custom_html='',html_sections=section_defaults(cfg))
        doc['html_sections'][kind]=source
        try:components.html(render_campaign(doc,cfg)['html'],height=320,scrolling=True)
        except ValueError as exc:st.warning(str(exc))
    confirmed=st.checkbox('Save as the new shared default' if builtin else 'Confirm overwriting this shared template',key='brand_overwrite')
    if st.button('Save shared template',disabled=not confirmed):
        try:
            row=store.save_section_template(user,kind,name,source,identity=None if builtin else edit['id'],version=edit['version'],confirmed=confirmed,make_default=builtin)
            st.session_state['brand_edit']=row;st.session_state.pop('brand_overwrite',None)
            if builtin:st.session_state.pop('brand_default_'+kind,None)
            st.toast('Shared template saved. Existing campaigns are unchanged.');st.rerun()
        except (ValueError,PermissionError,StoreUnavailable) as exc:st.error(str(exc))
    if not builtin:
        defaults=store.section_templates(kind,cfg)
        is_default=any(str(r['id'])==str(edit['id']) and r['is_default'] for r in defaults)
        with st.expander('Delete custom template'):
            st.caption('Delete “'+edit['name']+'” from the template choices. Saved campaign snapshots and audit history are retained.')
            confirm=st.checkbox('Confirm template deletion',key='brand_delete_confirm',disabled=is_default)
            if is_default:st.caption('Choose another default before deleting this template.')
            if st.button('Delete template',disabled=is_default or not confirm):
                try:
                    store.delete_section_template(user,edit['id'],edit['version'],confirmed=confirm)
                    st.session_state.pop('brand_edit',None);st.rerun()
                except (ValueError,PermissionError,StoreUnavailable) as exc:st.error(str(exc))
