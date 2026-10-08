"""Embedded automation preview; no periodic editor polling or duplicate dialog."""
import streamlit as st
import streamlit.components.v1 as components
from crm_abandoned_checkout import preview_context,apply_template,TEMPLATE
from crm_checkout_preview import needs_checkout
from crm_template_modal import template_modal


def automation_canvas(doc,cfg,key,store,*,current_document=True):
    # Only a genuinely pending initial checkout lookup gets a completion timer.
    # The completion app rerun mounts the same native iframe without a timer.
    pin=st.session_state.get('_automation_checkout_pin')
    pending=bool(pin and not pin['future'].done())
    st.fragment(run_every=1 if pending else None)(_automation_canvas)(doc,cfg,key,store,current_document=current_document,loading=pending)


def _automation_canvas(doc,cfg,key,store,*,current_document=True,loading=False):
    from crm_automation_preview_cache import output
    from crm_email_editor_context import current
    from crm_html_workspace import _preview_device
    editor=current(st.session_state,{})
    if current_document:doc=editor.get('document',doc)
    with st.container(key='crm-composer-preview' if current_document else 'crm-checkout-master-preview'):
        # Streamlit marks retained elements stale during unrelated app reruns.
        # This iframe holds last-good, digest-checked HTML, not a loading result.
        # Only these two automation preview surfaces opt out of stale fading.
        st.html('''<style>
        :is(.st-key-crm-composer-preview,.st-key-crm-checkout-master-preview) [data-testid="stElementContainer"][data-stale="true"]:has(iframe[data-testid="stIFrame"]){opacity:1!important;transition:none!important}
        </style>''')
        with st.container(horizontal=True,vertical_alignment='center'):
            st.markdown('**Email Preview**')
            with st.container(horizontal=True,gap='small',key='crm-preview-devices' if current_document else 'crm-master-preview-devices'):
                mode=st.session_state.get(key+'preview_device','Desktop')
                for label,icon in [('Desktop',':material/desktop_windows:'),('Mobile',':material/smartphone:')]:
                    st.button('',icon=icon,help=label,key=key+'device_'+label,type='primary' if mode==label else 'secondary',on_click=_preview_device,args=(key,label))
                if needs_checkout(doc) and st.button('',icon=':material/refresh:',help='Refresh checkout preview',key=key+'checkout_refresh'):
                    preview_context(st.session_state,store.preview_shop,refresh=True,auto_refresh=False,slot='_automation_checkout_pin')
                    # Wait only for this explicit refresh, retaining the browser's
                    # last-good iframe. Never fetch on typing or device changes.
                    from concurrent.futures import TimeoutError
                    pin=st.session_state.get('_automation_checkout_pin')
                    if pin:
                        try:pin['future'].result(timeout=10)
                        except TimeoutError:st.rerun(scope='app')
                        except Exception:pass # preview_context retains last-good.
        last=st.session_state.get(key+'last_good_visual')
        try:
            cache,label,warning=output(st.session_state,store,doc,cfg,editor.get('id'))
            if not cache['message']['html'].strip():raise ValueError('Empty rendered preview')
            if not last or last[0]['html_hash']!=cache['html_hash'] or last[1:]!=(label,warning):
                st.session_state[key+'last_good_visual']=(cache,label,warning)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error('automation_preview_render_failed type=%s',type(exc).__name__)
            st.caption('Preview could not update. '+('Previous preview retained.' if last else 'Retry after checking the template.'))
            if not last:
                pin=st.session_state.get('_automation_checkout_pin')
                if loading and pin and pin['future'].done():st.rerun(scope='app')
                return
            cache,label,warning=last
        if label:st.caption(label)
        if warning:
            from html import escape
            st.html('<small style="color:#96732e">'+escape(warning)+'</small>')
        pending=st.session_state.get('_automation_checkout_pin')
        pending=bool(needs_checkout(doc) and pending and not pending['future'].done())
        from crm_email_size_ui import automation_size_meter
        automation_size_meter(cache)
        components.html(cache['message']['html'],width=600 if mode=='Desktop' else 390,height=520,scrolling=True)
        if loading and not pending:st.rerun(scope='app')
        elif pending and not loading:st.rerun(scope='app')


@template_modal('Default Abandoned Checkout',width='large')
def edit_master(store,user,key):
    from crm_checkout_template import load,save
    from crm_checkout_styles import default_html
    if key+'master_edit' not in st.session_state:st.session_state[key+'master_edit']=load(store)
    row=st.session_state[key+'master_edit']
    if key+'master_html' not in st.session_state:st.session_state[key+'master_html']=row['html']
    source_area,preview_area=st.columns([3,2])
    with source_area:source=st.text_area('Master template HTML / CSS',value=None,height=440,key=key+'master_html')
    with preview_area:
        from copy import deepcopy
        from crm_email_editor_context import current
        from crm_checkout_template import validate
        doc=deepcopy(current(st.session_state,{})['document'])
        try:validate(source);apply_template(doc,source)
        except ValueError as exc:
            st.caption(str(exc));apply_template(doc,row['html'])
        if getattr(store,'email_mode',None)=='automation':
            automation_canvas(doc,store.render_settings(),key+'master_preview_',store,current_document=False)
        else:
            from crm_checkout_preview import document,sample
            from crm_campaign_content import render_campaign
            components.html(render_campaign(document(doc,sample(doc))[0],store.render_settings())['html'],height=440,scrolling=True)
    def reset_html():
        st.session_state[key+'master_html']=default_html()
        row['html']=default_html()
    cancel,reset,commit=st.columns(3)
    if cancel.button('Cancel',key=key+'master_cancel'):
        for suffix in ('master_edit','master_html'):st.session_state.pop(key+suffix,None)
        st.session_state.pop('automation_template_view',None)
        st.rerun()
    reset.button('Reset to default',key=key+'master_reset',on_click=reset_html)
    if commit.button('Save template',key=key+'master_save',type='primary'):
        try:
            save(store,user,source,row['revision'])
            for suffix in ('master_edit','master_html'):st.session_state.pop(key+suffix,None)
            st.session_state.pop('automation_template_view',None)
            st.toast('Template saved');st.rerun()
        except (ValueError,PermissionError) as exc:st.error(str(exc))
