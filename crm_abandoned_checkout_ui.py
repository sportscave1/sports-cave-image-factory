"""Embedded automation preview; no periodic editor polling or duplicate dialog."""
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
from crm_abandoned_checkout import preview_context,apply_template,TEMPLATE
from crm_checkout_preview import needs_checkout


@st.fragment
def automation_canvas(doc,cfg,key,store):
    from crm_automation_preview_cache import output
    from crm_email_editor_context import current
    from crm_html_workspace import _preview_device
    editor=current(st.session_state,{})
    doc=editor.get('document',doc)
    with st.container(key='crm-composer-preview'):
        with st.container(horizontal=True,vertical_alignment='center'):
            st.markdown('**Email Preview**')
            with st.container(horizontal=True,gap='small',key='crm-preview-devices'):
                mode=st.session_state.get(key+'preview_device','Desktop')
                for label,icon in [('Desktop',':material/desktop_windows:'),('Mobile',':material/smartphone:')]:
                    st.button('',icon=icon,help=label,key=key+'device_'+label,type='primary' if mode==label else 'secondary',on_click=_preview_device,args=(key,label))
                if needs_checkout(doc) and st.button('',icon=':material/refresh:',help='Refresh checkout preview',key=key+'checkout_refresh'):
                    preview_context(st.session_state,store.preview_shop,refresh=True,auto_refresh=False)
        cache,label,warning=output(st.session_state,store,doc,cfg,editor.get('id'))
        if label:st.caption(label)
        if warning:
            from html import escape
            st.html('<small style="color:#96732e">'+escape(warning)+'</small>')
        pending=st.session_state.get('abandoned_preview')
        pending=bool(needs_checkout(doc) and pending and not pending['future'].done())
        was_pending=st.session_state.get(key+'checkout_pending',False)
        if was_pending!=pending:st.session_state[key+'checkout_pending']=pending
        # One completion rerun updates the action-row size from the same output.
        # The keyed component stays mounted; settled editors never request ticks.
        if was_pending and not pending:st.rerun(scope='app')
        component=components.declare_component('crm_automation_stable_preview',path=str(Path(__file__).parent/'components'/'crm_automation_preview'))
        from crm_email_size import meter_html
        component(scope=key,meter=meter_html(cache['size']),html=cache['message']['html'],digest=cache['token'],width=600 if mode=='Desktop' else 390,pending=pending,key=key+'stable_preview',default=None)


def template_control(editor,key):
    import streamlit as st
    context_pair=st.session_state.get('automation_editor_context')
    if not context_pair:return
    store,_=context_pair
    if store.flow(editor['id'])['config']['draft']['trigger']!='abandoned':return
    st.markdown('**'+TEMPLATE+'**')
    if st.button('Use Abandoned Checkout template',key=key+'checkout_template'):
        apply_template(editor['document']);st.rerun()
