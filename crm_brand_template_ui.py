"""Two compact singleton editors; campaign body templates stay separate."""
import streamlit as st
import os_accounts
from crm_store import StoreUnavailable


@st.dialog('Email default',width='small')
def edit_default(store,user,kind,row):
    st.markdown('**Default '+kind.title()+'**')
    with st.form('email_default_edit_'+kind):
        source=st.text_area(kind.title()+' HTML',row['value']['html'],height=260)
        a,b=st.columns(2)
        cancel=a.form_submit_button('Cancel')
        save=b.form_submit_button('Save default',type='primary')
    if cancel:st.rerun()
    if save:
        try:
            store.save_email_default(user,kind,source,row['version'])
            st.session_state['email_default_notice']='Default '+kind+' saved'
            st.rerun()
        except (ValueError,PermissionError,StoreUnavailable) as exc:st.error(str(exc))


def brand_templates_settings(store,user,cfg=None):
    st.markdown('**Email defaults**')
    if st.session_state.get('email_default_notice'):st.success(st.session_state.pop('email_default_notice'))
    cfg=store.render_settings() if cfg is None else cfg
    rows=store.email_defaults(cfg)
    for kind,row in rows.items():
        label,action=st.columns([3,1],vertical_alignment='center')
        label.write('Default '+kind.title())
        if action.button('Edit',key='edit_email_default_'+kind,disabled=not os_accounts.is_admin(user)):
            edit_default(store,user,kind,row)
