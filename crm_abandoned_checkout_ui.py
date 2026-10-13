"""Embedded automation preview; no periodic editor polling or duplicate dialog."""
import streamlit as st
import streamlit.components.v1 as components
from crm_abandoned_checkout import preview_context,apply_template,TEMPLATE
from crm_checkout_preview import needs_checkout
from crm_template_modal import template_modal


def automation_canvas(doc,cfg,key,store,*,current_document=True):
    if current_document and getattr(store,'preview_trigger','abandoned')!='abandoned':
        _lifecycle_canvas(doc,cfg,key,store)
        return
    # Only a genuinely pending initial checkout lookup gets a completion timer.
    # The completion app rerun mounts the same native iframe without a timer.
    pin=st.session_state.get('_automation_checkout_pin')
    flow_pin=st.session_state.get('_automation_flow_pin') or {}
    pending=bool(pin and not pin['future'].done() or flow_pin.get('future'))
    st.fragment(run_every=1 if pending else None)(_automation_canvas)(doc,cfg,key,store,current_document=current_document,loading=pending)


@st.fragment
def _lifecycle_canvas(doc,cfg,key,store,*,current_document=True):
    from crm_flow_preview import context,pending,control,NoPreviewCustomer
    from crm_preview_toolbar import toolbar,arm,details
    from crm_email_editor_context import current
    from crm_automation_preview_cache import output
    editor=current(st.session_state,{})
    if current_document:doc=editor.get('document',doc)
    pin=context(st.session_state,store);cache=None;problem='';renderable=False
    try:
        cache,_,warning=output(st.session_state,store,doc,cfg,editor.get('id'))
        renderable=True
    except NoPreviewCustomer as exc:
        problem='' if pending(st.session_state) else str(exc)
        warning=''
    except ValueError as exc:problem=str(exc);warning=''
    pin=context(st.session_state,store);data=pin.get('selected')
    with st.container(key='crm-composer-preview' if current_document else 'crm-readonly-preview-'+key):
        def refresh():context(st.session_state,store,refresh=True)
        toolbar(key,data['label'] if data else 'Loading…' if pending(st.session_state) else 'No example',
                select=lambda:control(st.session_state,store,key),refresh=refresh,
                busy=pending(st.session_state),size=cache['size'] if cache else None,
                warning=problem or pin.get('error','') or warning,
                details=details(cache,doc)+(['Cached example · fresh consent and delivery checks still apply.'] if (data or {}).get('_cached') else []))
        if renderable:
            from crm_local_preview import canvas
            try:canvas(doc,cfg,key,store)
            except NoPreviewCustomer:pass  # Retained iframe survives background work.
        elif not pending(st.session_state):st.caption(problem or 'No eligible customer example is available.')
        if pending(st.session_state):
            import time
            fast=not data or data.get('_cached') or any(not f.done() for f in pin.get('renders',{}).values())
            fast=fast and time.monotonic()<pin.get('paint_until',0)
            arm(key,seconds=.05 if fast else 1)


def _checkout_refresh(store):
    # Existing Abandoned Checkout refresh path, unchanged arguments and waiting.
    preview_context(st.session_state,store.preview_shop,refresh=True,auto_refresh=False,slot='_automation_checkout_pin')
    from concurrent.futures import TimeoutError
    pin=st.session_state.get('_automation_checkout_pin')
    if pin:
        try:pin['future'].result(timeout=10)
        except TimeoutError:st.rerun(scope='app')
        except Exception:pass


def _automation_canvas(doc,cfg,key,store,*,current_document=True,loading=False):
    from crm_discount_section import DiscountPresentationError
    from crm_automation_preview_cache import output
    from crm_email_editor_context import current
    from crm_html_workspace import _preview_device
    editor=current(st.session_state,{})
    if current_document:doc=editor.get('document',doc)
    from crm_personalisation import present
    header_checkout=present(doc) and getattr(store,'preview_trigger','abandoned')=='abandoned'
    with st.container(key='crm-composer-preview' if current_document else 'crm-checkout-master-preview'):
        # Streamlit marks retained elements stale during unrelated app reruns.
        # This iframe holds last-good, digest-checked HTML, not a loading result.
        # Only these two automation preview surfaces opt out of stale fading.
        st.html('''<style>
        :is(.st-key-crm-composer-preview,.st-key-crm-checkout-master-preview) [data-testid="stElementContainer"][data-stale="true"]:has(iframe[data-testid="stIFrame"]){opacity:1!important;transition:none!important}
        </style>''')
        from crm_preview_toolbar import toolbar,details
        mode=st.session_state.get(key+'preview_device','Desktop')
        refresh=lambda:_checkout_refresh(store)
        if current_document:
            if getattr(store,'preview_trigger','abandoned')!='abandoned':
                from crm_flow_preview import control,NoPreviewCustomer
                control(st.session_state,store,key)
            # Hydrate the selected preview context once; local section edits no
            # longer depend on a successful whole-document production render.
            try:
                _,label=store.preview_document(doc)
                pass
            except ValueError as exc:
                from crm_flow_preview import NoPreviewCustomer
                if isinstance(exc,NoPreviewCustomer):
                    st.info(str(exc))
                    flow_pin=st.session_state.get('_automation_flow_pin') or {}
                    if bool(flow_pin.get('future'))!=loading:st.rerun(scope='app')
                    return
                label='Draft preview'
            size_cache=None;diagnostic=getattr(store,'preview_warning','')
            try:
                size_cache,_,_=output(st.session_state,store,doc,cfg,editor.get('id'))
            except Exception as exc:
                diagnostic=str(exc) if isinstance(exc,ValueError) else 'Email size unavailable. Correct section errors to calculate.'
            pin=st.session_state.get('_automation_checkout_pin') or {}
            name=(pin.get('last_good') or {}).get('label') or label.removeprefix('Previewing: ').split(' · ')[0]
            toolbar(key,name,refresh=refresh,refresh_enabled=needs_checkout(doc) or header_checkout,
                    size=size_cache['size'] if size_cache else None,warning=diagnostic,
                    details=details(size_cache,doc))
            from crm_local_preview import canvas
            canvas(doc,cfg,key,store)
            pin=st.session_state.get('_automation_checkout_pin')
            pending=bool(pin and not pin['future'].done())
            if loading and not pending:st.rerun(scope='app')
            elif pending and not loading:st.rerun(scope='app')
            return
        last=st.session_state.get(key+'last_good_visual')
        try:
            cache,label,warning=output(st.session_state,store,doc,cfg,editor.get('id'))
            if not cache['message']['html'].strip():raise ValueError('Empty rendered preview')
            if not last or last[0]['html_hash']!=cache['html_hash'] or last[0].get('personalised_headers')!=cache.get('personalised_headers') or last[1:]!=(label,warning):
                st.session_state[key+'last_good_visual']=(cache,label,warning)
        except DiscountPresentationError as exc:
            st.warning('Discount HTML needs attention: '+str(exc))
            # Never show the old offer as if it represented these invalid edits.
            # The current document/Shopify association is retained for correction.
            return
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error('automation_preview_render_failed type=%s',type(exc).__name__)
            st.warning('Preview unavailable. Your draft is retained. Check template variables and section settings, then retry.')
            if not last:
                pin=st.session_state.get('_automation_checkout_pin')
                if loading and pin and pin['future'].done():st.rerun(scope='app')
                return
            return
        name=label.removeprefix('Previewing: ').split(' · ')[0] or 'Draft preview'
        toolbar(key,name,refresh=refresh,refresh_enabled=needs_checkout(doc) or header_checkout,size=cache['size'],warning=warning,
                details=details(cache,doc))
        pending=st.session_state.get('_automation_checkout_pin')
        pending=bool(needs_checkout(doc) and pending and not pending['future'].done())
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
